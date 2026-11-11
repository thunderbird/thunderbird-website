# Deployment

This document describes how Thunderbird websites are built and deployed to AWS Fargate.

## Overview

All environments (local, stage, prod) build the websites from source inside a Docker container. The "Build and Deploy" GitHub Actions workflow handles the full pipeline: Docker build, ECR push, static file archival to `tb-website-builds`, and Fargate deployment via Pulumi.

### Environments

- **Stage**: Built from `master` branch
  - URLs: `www-stage.thunderbird.net`, `start-stage.thunderbird.net`, `updates-stage.thunderbird.net`, `stage.tb.pro`, `roadmaps-stage.thunderbird.net`
- **Production**: Built from `prod` branch
  - URLs: `www.thunderbird.net`, `start.thunderbird.net`, `updates.thunderbird.net`, `tb.pro`, `roadmaps.thunderbird.net`
- **PR Preview**: Per-pull-request, on-demand
  - URLs: `{branch}-{pr}.thunderbird.dev` (e.g., `archive-fix-123.thunderbird.dev`)

Built static files are committed to https://github.com/thunderbird/tb-website-builds as a record of what is deployed (`master` branch for stage, `prod` branch for production).

## Triggering Builds and Deployments

### Automatic (Push)

Pushing to `master` or `prod` on this repository triggers a full build and deploy for the corresponding environment.

External repositories also trigger builds via `repository_dispatch`:
- **thunderbird-notes**: `master` push triggers stage, `prod` push triggers production
- **thunderbird.net-l10n**: `master` push triggers stage
- **product-details**: `production` push triggers production

### Manual (GitHub UI)

1. Go to the [Actions tab](https://github.com/thunderbird/thunderbird-website/actions)
2. Select "Build and Deploy" workflow
3. Click "Run workflow"
4. Select the environment (`stage` or `prod`)
5. Click "Run workflow"

### Manual (Repository Dispatch)

Builds can be triggered programmatically using GitHub's repository dispatch API:

**Using the trigger script:**

```bash
export GITHUB_TOKEN=your_token_here
./pulumi/trigger-deploy.sh stage   # or prod
```

**Using curl directly:**

```bash
curl -X POST \
  -H "Accept: application/vnd.github.v3+json" \
  -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/repos/thunderbird/thunderbird-website/dispatches" \
  -d '{"event_type":"stage"}'
```

## Infrastructure

The infrastructure is defined in the `pulumi/` directory using Python.

### Components

- **VPC**: Public subnets in multiple availability zones
- **Application Load Balancer**: SSL termination, routes traffic to ECS tasks
- **ECS Cluster**: Runs the Fargate tasks
- **ECR Repository**: Stores Docker images
- **IAM Roles**: Execution and task roles for ECS

### Configuration

Project-level defaults (region, certificate ARN) are in `pulumi/Pulumi.yaml`. Stack-specific overrides:
- `pulumi/Pulumi.stage.yaml` - Stage environment config
- `pulumi/Pulumi.prod.yaml` - Production environment config

## Docker Container

The container is defined in `docker/Dockerfile`. All environments build from source. `BUILD_ENV` controls post-build behavior:

- **`local`** (default): Keeps `/build` directory so pytest can run inside the container. Used by `container-test.yml` and local development.
- **`stage` / `prod`**: Removes `/build` to reduce image size. `DEPLOY_ENV` selects that mode and the `REPO_BRANCH` used when the image build clones external repositories (`prod` for production, `master` for stage). The website files are the checked-out source, not that branch name.

All environments compile translations and build all sites from source.

The default final stage, `lambda`, includes the Lambda Web Adapter for preview deployments.
The `website` stage contains the same application without the Lambda extension and can be
built with `--target website` when running outside Lambda.

```bash
# Local development
docker build -t thunderbird-web .
docker run -p 8080:80 thunderbird-web

# Stage/prod (used by CI)
docker build --build-arg BUILD_ENV=stage -t thunderbird-web:stage .
docker build --build-arg BUILD_ENV=prod -t thunderbird-web:prod .
```

## Development Container

For local development using VS Code's Dev Containers feature:

1. Install the "Dev Containers" extension
2. Open the repository in VS Code
3. Click "Reopen in Container" when prompted
4. The container will build and start Apache automatically

## CI/CD Workflows

### Container Test (`container-test.yml`)

Runs on every push/PR to `master`:
- Builds the `website` target with `BUILD_ENV=local`, skipping the Lambda extension so fork PRs do not need AWS credentials
- Runs pytest inside the container

### Build and Deploy (`deploy.yml`)

Triggered by:
- Push to `master` or `prod` branches
- Manual workflow dispatch
- Repository dispatch (from external repos like thunderbird-notes, l10n, product-details)

The build step runs `deployment_image.py` with Python 3 and Docker Buildx. Buildx metadata identifies the image pushed by that run. The commit SHA and `latest` tags remain published. Extraction and Pulumi use `repository@sha256:<64 hex digits>` from that metadata, not those tags.

`DEPLOY_ENV` selects the stage or production repository and the external `REPO_BRANCH`. The website files are the checked-out source. For an automatic push, that checkout is the `master` or `prod` commit that triggered the run. A manual run checks out the selected ref, which can differ from `DEPLOY_ENV`.

Provenance attestations are disabled. The previous `docker build` and `docker push` published one image manifest. Buildx would otherwise make the recorded root digest an attestation index.

Missing, malformed, or inconsistent metadata fails the build step, before publication and Pulumi. Publication extracts that digest-pinned image. When the local daemon does not already have it, Docker pulls it with the ECR login from the same job. That login is the existing push credential. No separate registry permission is added.

Steps:
1. Build the checked-out source, push it, and publish the digest reference
2. Publish that image's archive to `tb-website-builds`. Production also persists the purge intent and writes a receipt
3. Deploy infrastructure with Pulumi using the same reference as `IMAGE_URI`
4. Force ECS service update

The purge command is not part of this workflow yet. Step 4 does not record an ECS deployment id or call `purge`.

`persist_deployment_intent` is implemented and records one deployment intent. Production publication calls it before replacing the archive and before Pulumi. A failure stops the job. Stage publication does not record an intent. Persisting the intent does not establish deployment readiness or authorize a purge.

`read_content_snapshot` is implemented. The caller provides a completed, stable artifact directory. The function reads that directory into relative path-to-bytes records and does not create an atomic filesystem snapshot. Production publication uses that read on the archive extracted from the pinned image.

`prepare_deployment_intent` is implemented. Credentials are required for every zone used by a managed hostname, and each one must be locally well-formed. It then fingerprints a completed artifact directory and persists that intent. The check does not prove Cloudflare authorization or zone access. Production publication calls it before Pulumi. `docs/examples/cache-purge.example.json` is a non-production illustration with no tokens and is not a fallback configuration.

`extract_pinned_content` is implemented. It creates a stopped container from the digest-pinned image and copies `/var/www/html/start/.` into a temporary directory. That copy is the archived site tree only, not server configuration outside it. Cleanup tries to remove that invocation's container and directory when create returns an id, times out, is interrupted, or returns an unusable result. An interruption or exit from the extraction is propagated. Cleanup is best-effort: it does not survive process termination or daemon failure as a transactional rollback.

`publish_pinned_release` is implemented. It publishes one pinned archive and, on production, persists that intent first. `deploy.yml` calls it through `deployment_cli.py publish` before Pulumi. The builds repository is cloned from its plain URL, with a shallow `master` checkout for stage and `prod` for production. An in-progress production run is not cancelled by a later production run in the same `deploy-prod` group. Stage still cancels an in-progress stage run. That group is not a purge lock, and the workflow does not call `purge`. Cancellation of a Git command inside publication still signals that process and briefly reaps it. That cleanup is best-effort when termination cannot be confirmed, and outstanding purge work is retained. A push that already reached the remote stays there.

`purge_ready_deployment` is implemented. It purges pending hostnames for the expected intent, one configured zone at a time, after a ready observation of this run's deployment. Each zone starts only from the revision used to plan that work, or from the revision this run last wrote. An unexpected revision stops the run before that zone is polled or purged. The caller must serialize production deployments. Readiness observations and state checks are not locks. `deploy.yml` does not call this function. A purge Cloudflare accepted but this function did not persist can remain pending and may be repeated. The Cloudflare request and the state write are not one atomic update.

`deployment_cli.py` provides `publish` and `purge`. The workflow runs `publish` from the website checkout and passes the builds checkout explicitly. It does not run `purge`. The example configuration is not a fallback. Production's identity is `${GITHUB_RUN_ID}.${GITHUB_RUN_ATTEMPT}`.

`CACHE_PURGE_CONFIG` is a non-secret Actions variable, separate from the production secrets. Set it on the production environment, or on the repository when that environment does not. Its value is the purge configuration JSON. The publication step writes that value to a file under `RUNNER_TEMP` and passes the file to `publish`. The JSON is not interpolated into the shell script and is not printed. Stage does not read it. `CACHE_PURGE_ZONE_CREDENTIALS` is a required production secret. The workflow passes it only as that environment variable. Whether the secret is actually configured in production is unverified. GitHub supplies a missing variable or secret as an empty string, and the publication script still starts the CLI. Empty configuration or empty credentials fail during CLI validation, before extraction, state publication, or receipt creation. The receipt is `${RUNNER_TEMP}/purge-receipt.json`, outside the builds checkout, and is not consumed by a later step yet. State is `refs/heads/purge-state` and `prod.json`. An invalid configuration or credential, or a failed state write, archive publication, or receipt write, fails the publication step and prevents Pulumi.

`publish` calls `publish_pinned_release`. Stage does not read purge configuration, `CACHE_PURGE_ZONE_CREDENTIALS`, or purge state, and it does not write a receipt. Production requires an explicit configuration file, that variable, a unique intent identity, the state location, and a receipt path. `CACHE_PURGE_ZONE_CREDENTIALS` is a JSON object mapping zone aliases to API tokens. It is not a command argument. Malformed JSON, a duplicate alias, or a token the purge client would refuse is rejected without echoing the document. After publication succeeds, the command writes the returned state with `encode_purge_state` and replaces the receipt only when the file is complete. A filesystem failure while writing it prints `receipt could not be written`, removes that attempt's temporary file, leaves the previous receipt in place, and does not roll back the archive or the persisted intent.

Documented validation and coordinator errors are printed. Any other failure prints `deployment command failed` and does not include the exception, a traceback, a response body, the environment, or the credential document. Either failure exits nonzero.

`purge` reads the receipt with `decode_purge_state` and uses its intent only. The caller repeats the run identity and digest-pinned image and passes this run's ECS deployment id. The command does not select the deployment that is currently PRIMARY. Pending work and revision checks come from the remote state. Publish installs askpass only for its own Git commands and restores the previous Git environment before it returns. Purge does not install authentication. The caller must already provide noninteractive Git authentication for that command.

These examples use fake values:

```
CACHE_PURGE_ZONE_CREDENTIALS='{"example":"fake-token"}' \
python3 deployment_cli.py publish \
    --image example.invalid/website@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
    --environment prod \
    --checkout /tmp/builds \
    --remote https://example.invalid/builds.git \
    --message 1001.2 \
    --configuration /tmp/cache-purge.json \
    --identity 1001.2 \
    --state-ref refs/heads/purge-state \
    --state-path prod.json \
    --receipt /tmp/purge-receipt.json
```

```
CACHE_PURGE_ZONE_CREDENTIALS='{"example":"fake-token"}' \
python3 deployment_cli.py purge \
    --configuration /tmp/cache-purge.json \
    --receipt /tmp/purge-receipt.json \
    --identity 1001.2 \
    --image example.invalid/website@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
    --workspace /tmp/builds \
    --remote https://example.invalid/builds.git \
    --state-ref refs/heads/purge-state \
    --state-path prod.json \
    --cluster example-cluster \
    --service example-service \
    --region example-region \
    --deployment-id deployment-1
```

### PR Preview (`preview.yml`)

Triggered when a `preview` or `preview:<site>` label is added to a non-fork PR. Subsequent pushes auto-rebuild while the label is present.

- **Deploy**: Builds container, deploys Lambda + API Gateway via Pulumi, comments preview URL on PR
- **Destroy**: Tears down all preview resources when a labeled PR is closed

## PR Preview Deployments

Pull requests from non-fork branches can get preview deployments at `{branch}-{pr}.thunderbird.dev`. Previews use AWS Lambda (container image via Lambda Web Adapter) behind API Gateway HTTP API, so they cost nothing when idle.

### How It Works

1. Add a `preview` label to a non-fork PR (or `preview:<name>` to target a specific site)
2. The workflow builds the Docker image, pushes to ECR, and deploys a Lambda function + API Gateway with a custom domain
3. A comment is posted on the PR with the preview URL
4. Subsequent pushes auto-rebuild while the label is present
5. When the PR is closed, all preview resources are destroyed and ECR images cleaned up

### Site Selection

The label controls which site is previewed. Use `preview` for the default (`www.thunderbird.net`) or `preview:<name>` matching a `build-site.py` argument (e.g. `preview:tbpro`, `preview:startpage`).

### Preview Infrastructure

Defined in `pulumi/preview/`. Each PR gets its own Pulumi stack with:
- Lambda function (container image)
- API Gateway HTTP API
- Custom domain + Route53 record

### Prerequisites

Preview deployments depend on: a `*.thunderbird.dev` ACM wildcard certificate (ARN in `pulumi/preview/Pulumi.yaml`), the IAM permissions from `pulumi/setup-oidc-role.sh`, and a `thunderbird-website-preview` ECR repository.

## Permissions

### Variables

- **`CACHE_PURGE_CONFIG`**: Non-secret production configuration. The value is the purge configuration JSON, not the example file. The workflow passes it as the `CACHE_PURGE_CONFIG` environment variable. Local tests do not establish the value configured in production.

### Secrets

- **`TB_BUILDS_KEY`**: GitHub PAT or App token with `contents:write` on `thunderbird/tb-website-builds`, used to push the archive branch and to create or update `refs/heads/purge-state`. The workflow passes it as `TB_BUILDS_KEY` and does not put it in a remote URL. Local tests do not establish that the production token has that ref permission.
- **`TB_BUILDS_GIT_EMAIL`**: Committer email for the bot identity used in `tb-website-builds` commits.
- **`CACHE_PURGE_ZONE_CREDENTIALS`**: Required production secret. A JSON object mapping zone aliases to API tokens, passed only through that environment variable. Local tests do not establish that this secret is configured in production.

### OIDC

The GitHub Actions workflow uses OIDC to assume an AWS role for deployment and also to access Pulumi Cloud. The AWS role is configured in `pulumi/setup-oidc-role.sh`.

Deployment and preview builds authenticate Docker separately to private ECR (for image pushes)
and public ECR (for the Lambda Web Adapter pull). Public ECR authentication uses `us-east-1`;
the rest of the deployment continues to use `us-west-2`.

The deployment role needs `ecr-public:GetAuthorizationToken` and `sts:GetServiceBearerToken`
on `*`. For an existing role, apply the updated permissions from `pulumi/setup-oidc-role.sh`
before running the updated deployment workflows. A private ECR login alone leaves public
image pulls anonymous and subject to the public registry's anonymous data limit.
