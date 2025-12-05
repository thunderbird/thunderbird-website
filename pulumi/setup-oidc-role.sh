#!/bin/bash
# Setup GitHub OIDC provider and IAM role for deploying to Fargate
# You need your AWS credentials in the environment to run this script.
# Run: source ~/credentials.sh && ./setup-oidc-role.sh

set -e

REGION="us-west-2"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
GITHUB_ORG="thunderbird"
GITHUB_REPO="thunderbird-website"
ROLE_NAME="thunderbird-website-deploy"

echo "AWS Account: $ACCOUNT_ID"
echo "Region: $REGION"
echo "GitHub: $GITHUB_ORG/$GITHUB_REPO"

# Check if OIDC provider already exists
OIDC_ARN="arn:aws:iam::${ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
if aws iam get-open-id-connect-provider --open-id-connect-provider-arn "$OIDC_ARN" 2>/dev/null; then
    echo "OIDC provider already exists"
else
    echo "Creating GitHub OIDC provider..."
    aws iam create-open-id-connect-provider \
        --url https://token.actions.githubusercontent.com \
        --client-id-list sts.amazonaws.com \
        --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 1c58a3a8518e8759bf075b76b750d4f2df264fcd
    echo "OIDC provider created"
fi

# Create trust policy
TRUST_POLICY=$(cat <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Federated": "arn:aws:iam::${ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
            },
            "Action": "sts:AssumeRoleWithWebIdentity",
            "Condition": {
                "StringEquals": {
                    "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
                },
                "StringLike": {
                    "token.actions.githubusercontent.com:sub": "repo:${GITHUB_ORG}/${GITHUB_REPO}:*"
                }
            }
        },
        {
            "Effect": "Allow",
            "Principal": {
                "AWS": "arn:aws:iam::${ACCOUNT_ID}:user/sancus"
            },
            "Action": "sts:AssumeRole"
        }
    ]
}
EOF
)

# Permissions policy for Pulumi Fargate deployment
PERMISSIONS_POLICY=$(cat <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "ECR",
            "Effect": "Allow",
            "Action": ["ecr:*"],
            "Resource": ["arn:aws:ecr:${REGION}:${ACCOUNT_ID}:repository/thunderbird-website-*"]
        },
        {
            "Sid": "ECRAuth",
            "Effect": "Allow",
            "Action": ["ecr:GetAuthorizationToken", "ecr:DescribeRepositories"],
            "Resource": "*"
        },
        {
            "Sid": "ECS",
            "Effect": "Allow",
            "Action": ["ecs:*"],
            "Resource": "*",
            "Condition": {
                "StringEquals": {"aws:ResourceTag/Project": "thunderbird-website"}
            }
        },
        {
            "Sid": "ECSGeneral",
            "Effect": "Allow",
            "Action": [
                "ecs:RegisterTaskDefinition",
                "ecs:DeregisterTaskDefinition",
                "ecs:DescribeTaskDefinition",
                "ecs:ListTaskDefinitions",
                "ecs:CreateCluster",
                "ecs:DescribeClusters",
                "ecs:ListClusters",
                "ecs:CreateService",
                "ecs:UpdateService",
                "ecs:DeleteService",
                "ecs:DescribeServices",
                "ecs:ListServices",
                "ecs:DescribeTasks",
                "ecs:ListTasks",
                "ecs:RunTask",
                "ecs:StopTask",
                "ecs:TagResource"
            ],
            "Resource": "*"
        },
        {
            "Sid": "EC2VPC",
            "Effect": "Allow",
            "Action": [
                "ec2:*Vpc*", "ec2:*Subnet*", "ec2:*SecurityGroup*",
                "ec2:*InternetGateway*", "ec2:*RouteTable*", "ec2:*NatGateway*",
                "ec2:*Address*", "ec2:*NetworkInterface*", "ec2:*NetworkAcl*",
                "ec2:*Route", "ec2:DescribeAvailabilityZones", "ec2:CreateTags", "ec2:DeleteTags"
            ],
            "Resource": "*"
        },
        {
            "Sid": "ELB",
            "Effect": "Allow",
            "Action": ["elasticloadbalancing:*"],
            "Resource": "*"
        },
        {
            "Sid": "IAM",
            "Effect": "Allow",
            "Action": [
                "iam:CreateRole", "iam:DeleteRole", "iam:GetRole", "iam:PassRole",
                "iam:AttachRolePolicy", "iam:DetachRolePolicy",
                "iam:PutRolePolicy", "iam:DeleteRolePolicy", "iam:GetRolePolicy",
                "iam:ListRolePolicies", "iam:ListAttachedRolePolicies",
                "iam:TagRole", "iam:UntagRole", "iam:ListInstanceProfilesForRole"
            ],
            "Resource": ["arn:aws:iam::${ACCOUNT_ID}:role/thunderbird-website-*"]
        },
        {
            "Sid": "CloudWatchLogs",
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup", "logs:DeleteLogGroup",
                "logs:PutRetentionPolicy", "logs:TagLogGroup", "logs:UntagLogGroup",
                "logs:ListTagsLogGroup", "logs:ListTagsForResource", "logs:TagResource"
            ],
            "Resource": ["arn:aws:logs:${REGION}:${ACCOUNT_ID}:log-group:/ecs/thunderbird-website-*"]
        },
        {
            "Sid": "CloudWatchLogsDescribe",
            "Effect": "Allow",
            "Action": ["logs:DescribeLogGroups"],
            "Resource": "*"
        },
        {
            "Sid": "AutoScaling",
            "Effect": "Allow",
            "Action": [
                "application-autoscaling:RegisterScalableTarget",
                "application-autoscaling:DeregisterScalableTarget",
                "application-autoscaling:DescribeScalableTargets",
                "application-autoscaling:PutScalingPolicy",
                "application-autoscaling:DeleteScalingPolicy",
                "application-autoscaling:DescribeScalingPolicies",
                "application-autoscaling:DescribeScalingActivities",
                "application-autoscaling:TagResource",
                "application-autoscaling:UntagResource",
                "application-autoscaling:ListTagsForResource"
            ],
            "Resource": "*"
        }
    ]
}
EOF
)

# Check if role exists
if aws iam get-role --role-name "$ROLE_NAME" 2>/dev/null; then
    echo "Role $ROLE_NAME already exists, updating..."
    aws iam update-assume-role-policy \
        --role-name "$ROLE_NAME" \
        --policy-document "$TRUST_POLICY"
else
    echo "Creating IAM role $ROLE_NAME..."
    aws iam create-role \
        --role-name "$ROLE_NAME" \
        --assume-role-policy-document "$TRUST_POLICY" \
        --description "GitHub Actions deployment role for thunderbird-website"
fi

# Create/update the inline policy
echo "Attaching permissions policy..."
aws iam put-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-name "pulumi-fargate-deploy" \
    --policy-document "$PERMISSIONS_POLICY"

echo ""
echo "============================================"
echo "Setup complete!"
echo "Role ARN: arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"
echo ""
echo "Add this secret to GitHub:"
echo "  AWS_ROLE_ARN = arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"
echo "============================================"

