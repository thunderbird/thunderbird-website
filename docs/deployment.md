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

Missing, malformed, or inconsistent metadata fails the build step, before extraction and Pulumi. `docker create` uses the digest reference. When the local daemon does not already have that image, Docker pulls it with the ECR login from the same job. That login is the existing push credential. No separate registry permission is added.

Steps:
1. Build the checked-out source, push it, and publish the digest reference
2. Extract the built static files from that reference and commit them to `tb-website-builds`
3. Deploy infrastructure with Pulumi using the same reference as `IMAGE_URI`
4. Force ECS service update

`persist_deployment_intent` is implemented and records one deployment intent. `publish_pinned_release` calls it for production before replacing the archive. `deploy.yml` does not call that coordinator yet. The caller must complete configuration and credential checks and successfully persist the deployment intent before Pulumi can expose new content. Persisting the intent does not establish deployment readiness or authorize a purge.

`read_content_snapshot` is implemented. The caller provides a completed, stable artifact directory. The function reads that directory into relative path-to-bytes records and does not create an atomic filesystem snapshot. `deploy.yml` does not call it yet.

`prepare_deployment_intent` is implemented. Credentials are required for every zone used by a managed hostname, and each one must be locally well-formed. It then fingerprints a completed artifact directory and persists that intent. The check does not prove Cloudflare authorization or zone access. `deploy.yml` does not call it yet. `docs/examples/cache-purge.example.json` is a non-production illustration with no tokens and is not a fallback configuration.

`extract_pinned_content` is implemented. It creates a stopped container from the digest-pinned image and copies `/var/www/html/start/.` into a temporary directory. That copy is the archived site tree only, not server configuration outside it. Cleanup tries to remove that invocation's container and directory when create returns an id, times out, is interrupted, or returns an unusable result. An interruption or exit from the extraction is propagated. Cleanup is best-effort: it does not survive process termination or daemon failure as a transactional rollback.

`publish_pinned_release` is implemented. It publishes one pinned archive and, on production, persists that intent first. `deploy.yml` does not call it yet and still creates a container named `extract`. Future integration must serialize running production deployments; that serialization is not active. Cancellation signals this operation's Git processes and briefly reaps them. That cleanup is best-effort when termination cannot be confirmed, and outstanding purge work is retained. A push that already reached the remote stays there. A future zone purge must recheck ECS readiness and current intent ownership before each request. This slice does not send those requests. Readiness polling and Cloudflare remain unwired.

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

### Secrets

- **`TB_BUILDS_KEY`**: GitHub PAT or App token with `contents:write` on `thunderbird/tb-website-builds`, used to push built static files.
- **`TB_BUILDS_GIT_EMAIL`**: Committer email for the bot identity used in `tb-website-builds` commits.

### OIDC

The GitHub Actions workflow uses OIDC to assume an AWS role for deployment and also to access Pulumi Cloud. The AWS role is configured in `pulumi/setup-oidc-role.sh`.

Deployment and preview builds authenticate Docker separately to private ECR (for image pushes)
and public ECR (for the Lambda Web Adapter pull). Public ECR authentication uses `us-east-1`;
the rest of the deployment continues to use `us-west-2`.

The deployment role needs `ecr-public:GetAuthorizationToken` and `sts:GetServiceBearerToken`
on `*`. For an existing role, apply the updated permissions from `pulumi/setup-oidc-role.sh`
before running the updated deployment workflows. A private ECR login alone leaves public
image pulls anonymous and subject to the public registry's anonymous data limit.
