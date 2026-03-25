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
- Builds the Docker container with `BUILD_ENV=local`
- Runs pytest inside the container

### Build and Deploy (`deploy.yml`)

Triggered by:
- Push to `master` or `prod` branches
- Manual workflow dispatch
- Repository dispatch (from external repos like thunderbird-notes, l10n, product-details)

Steps:
1. Build Docker image from source and push to ECR
2. Extract built static files and commit to `tb-website-builds`
3. Deploy infrastructure with Pulumi
4. Force ECS service update

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
