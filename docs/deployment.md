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
- **`stage` / `prod`**: Removes `/build` to reduce image size. `REPO_BRANCH` is derived from `BUILD_ENV` (`prod` -> `prod`, else -> `master`).

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

A production run does not cancel a production deployment that is already in progress.

Steps:
1. Build Docker image from source and push to ECR
2. Extract built static files and commit to `tb-website-builds`
3. Deploy infrastructure with Pulumi
4. Force ECS service update
5. On production, wait until the ECS service is stable, then purge each configured Cloudflare zone

Stage stops after the ECS update. It does not purge.

#### Production cache purge

The production job reads `vars.CACHE_PURGE_CONFIG` and `secrets.CLOUDFLARE_API_TOKEN`. This repository does not contain those values. Create the variable and secret where the production job can read them before expecting a production deploy to purge.

`CACHE_PURGE_CONFIG` must be exactly one JSON object with a nonempty `zones` array. Each zone has a 32-character hexadecimal `id` and exactly one scope:

- `hosts`: a nonempty array of nonempty hostnames
- `purge_everything`: boolean `true`

Setting both, setting neither, or using the string `"true"` is invalid. Several JSON documents concatenated in one value are also invalid.

`CLOUDFLARE_API_TOKEN` is one token for every configured zone. Give it Cloudflare's Cache Purge permission, limited to those zones. A missing token, an empty token, or a token that contains whitespace fails the job before any request.

The example below uses dummy zone IDs and example hostnames. It is not a production configuration.

```json
{
  "zones": [
    {
      "id": "0123456789abcdef0123456789abcdef",
      "hosts": ["www.example.net", "start.example.net"]
    },
    {
      "id": "fedcba9876543210fedcba9876543210",
      "purge_everything": true
    }
  ]
}
```

The first zone is posted as `{"hosts":["www.example.net","start.example.net"]}`. The second is posted as `{"purge_everything":true}`. Each request goes to `https://api.cloudflare.com/client/v4/zones/{id}/purge_cache`.

Missing or invalid configuration fails the job before those requests. The ECS update and stability wait have already finished, and a failed purge leaves that deployment in place.

A failed connection, a timeout, an HTTP status other than 200, or a body that is not one JSON object with boolean `success` set to `true` fails the job. An earlier zone may already have been purged. Rerun the production job to send every configured purge again. Duplicate purges are acceptable. The workflow keeps no purge state and does not reconcile a partial purge.

Cloudflare accepting the request does not show that every cache has evicted the content.

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
- **`CLOUDFLARE_API_TOKEN`**: Bearer token for the production Cloudflare purge described above. Not stored in this repository.

### OIDC

The GitHub Actions workflow uses OIDC to assume an AWS role for deployment and also to access Pulumi Cloud. The AWS role is configured in `pulumi/setup-oidc-role.sh`.

Deployment and preview builds authenticate Docker separately to private ECR (for image pushes)
and public ECR (for the Lambda Web Adapter pull). Public ECR authentication uses `us-east-1`;
the rest of the deployment continues to use `us-west-2`.

The deployment role needs `ecr-public:GetAuthorizationToken` and `sts:GetServiceBearerToken`
on `*`. For an existing role, apply the updated permissions from `pulumi/setup-oidc-role.sh`
before running the updated deployment workflows. A private ECR login alone leaves public
image pulls anonymous and subject to the public registry's anonymous data limit.
