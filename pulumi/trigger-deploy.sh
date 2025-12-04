#!/bin/bash
# Trigger deployment for Thunderbird website to Fargate
# Usage: ./trigger-deploy.sh [stage|prod]
#
# Requires GITHUB_TOKEN environment variable with repo scope
# Can be run from anywhere

set -e

ENVIRONMENT=${1:-stage}
REPO="thunderbird/thunderbird-website"
EVENT_TYPE="${ENVIRONMENT}"

if [ -z "$GITHUB_TOKEN" ]; then
    echo "ERROR: GITHUB_TOKEN environment variable is required"
    echo "Get a token from: https://github.com/settings/tokens"
    echo "It needs 'repo' scope"
    exit 1
fi

if [ "$ENVIRONMENT" != "stage" ] && [ "$ENVIRONMENT" != "prod" ]; then
    echo "ERROR: Environment must be 'stage' or 'prod'"
    echo "Usage: $0 [stage|prod]"
    exit 1
fi

echo "Triggering deployment for $ENVIRONMENT environment..."
echo "Repository: $REPO"
echo "Event type: $EVENT_TYPE"

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
  -H "Accept: application/vnd.github.v3+json" \
  -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/repos/${REPO}/dispatches" \
  -d "{\"event_type\":\"${EVENT_TYPE}\"}")

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "204" ]; then
    echo "✓ Deployment triggered successfully!"
    echo "Check status at: https://github.com/${REPO}/actions"
else
    echo "ERROR: Failed to trigger deployment"
    echo "HTTP Code: $HTTP_CODE"
    echo "Response: $BODY"
    exit 1
fi

