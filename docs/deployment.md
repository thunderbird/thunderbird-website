# Deployment

This document describes how Thunderbird websites are deployed to AWS Fargate.

## Overview

The websites are containerized using Docker and deployed to AWS Fargate. The deployment is managed using Pulumi (Infrastructure as Code) and GitHub Actions.

### Environments

- **Stage**: Deployed from `master` branch of `tb-website-builds`
  - URLs: `www-stage.thunderbird.net`, `start-stage.thunderbird.net`, `updates-stage.thunderbird.net`, `stage.tb.pro`
- **Production**: Deployed from `prod` branch of `tb-website-builds`
  - URLs: `www.thunderbird.net`, `start.thunderbird.net`, `updates.thunderbird.net`, `tb.pro`

## Triggering Deployments

### Manual Deployment (GitHub UI)

1. Go to the [Actions tab](https://github.com/thunderbird/thunderbird-website/actions)
2. Select "Deploy to Fargate" workflow
3. Click "Run workflow"
4. Select the environment (`stage` or `prod`)
5. Click "Run workflow"

### Automated Deployment (Repository Dispatch)

Deployments can be triggered programmatically using GitHub's repository dispatch API. This is useful for triggering deployments from other repositories (e.g., after `tb-website-builds` is updated).

**Using the trigger script:**

```bash
# Set your GitHub token (needs repo scope)
export GITHUB_TOKEN=your_token_here

# Trigger stage deployment
./pulumi/trigger-deploy.sh stage

# Trigger production deployment
./pulumi/trigger-deploy.sh prod
```

**Using curl directly:**

```bash
# Stage deployment
curl -X POST \
  -H "Accept: application/vnd.github.v3+json" \
  -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/repos/thunderbird/thunderbird-website/dispatches" \
  -d '{"event_type":"stage"}'

# Production deployment
curl -X POST \
  -H "Accept: application/vnd.github.v3+json" \
  -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/repos/thunderbird/thunderbird-website/dispatches" \
  -d '{"event_type":"prod"}'
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

Stack-specific configuration is in:
- `pulumi/Pulumi.stage.yaml` - Stage environment config
- `pulumi/Pulumi.prod.yaml` - Production environment config

## Docker Container

The container is defined in `docker/Dockerfile` with two build modes:

### Local Development (`BUILD_ENV=local`)

Builds the websites from source inside the container:

```bash
docker build -t thunderbird-web .
docker run -p 8080:80 thunderbird-web
```

### Deployment (`BUILD_ENV=stage` or `BUILD_ENV=prod`)

Clones pre-built assets from `tb-website-builds`:

```bash
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
- Builds the Docker container
- Runs pytest inside the container
- Tests all websites with curl requests

### Deploy (`deploy.yml`)

Triggered by:
- Manual workflow dispatch
- Repository dispatch (from other repos)
- Push to `fargate` branch (for testing)

Steps:
1. Build and push Docker image to ECR
2. Deploy infrastructure with Pulumi
3. Force ECS service update

## Permissions

### GitHub Token for Triggering Deploys

To trigger deployments via repository dispatch, you need a GitHub Personal Access Token with `repo` scope.

### OIDC

The GitHub Actions workflow uses OIDC to assume an AWS role for deployment and also to access Pulumi Cloud. The AWS role is configured in `pulumi/setup-oidc-role.sh`.

