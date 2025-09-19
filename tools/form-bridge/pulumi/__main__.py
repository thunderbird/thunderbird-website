import pulumi
import pulumi_aws as aws
import json

# Get configuration
config = pulumi.Config()
stack = pulumi.get_stack()

# Environment validation
if stack not in ["stage", "prod"]:
    raise ValueError(f"Stack must be 'stage' or 'prod', got '{stack}'")

# Create IAM role for Lambda
lambda_role = aws.iam.Role(f"donor-form-bridge-lambda-role-{stack}",
    assume_role_policy=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Action": "sts:AssumeRole",
            "Effect": "Allow",
            "Principal": {
                "Service": "lambda.amazonaws.com"
            }
        }]
    })
)

# Attach basic Lambda execution policy
lambda_policy_attachment = aws.iam.RolePolicyAttachment(f"donor-form-bridge-lambda-policy-{stack}",
    role=lambda_role.name,
    policy_arn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
)

# Create policy for accessing Secrets Manager
secrets_policy = aws.iam.Policy(f"donor-form-bridge-secrets-policy-{stack}",
    policy=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": [
                "secretsmanager:GetSecretValue"
            ],
            "Resource": [
                "arn:aws:secretsmanager:*:*:secret:form-bridge/prod/zendesk*"
            ]
        }]
    })
)

# Attach secrets policy to Lambda role
secrets_policy_attachment = aws.iam.RolePolicyAttachment(f"donor-form-bridge-secrets-policy-attachment-{stack}",
    role=lambda_role.name,
    policy_arn=secrets_policy.arn
)

# Create Lambda function
lambda_function = aws.lambda_.Function(f"donor-form-bridge-lambda-{stack}",
    runtime="python3.9",
    handler="lambda_function.lambda_handler",
    role=lambda_role.arn,
    code=pulumi.FileArchive("../"),  # Reference parent directory containing lambda_function.py
    timeout=30,
    environment=aws.lambda_.FunctionEnvironmentArgs(
        variables={
            "ENVIRONMENT": stack
        }
    ),
    opts=pulumi.ResourceOptions(depends_on=[lambda_policy_attachment, secrets_policy_attachment])
)

# Create Lambda function URL
lambda_url = aws.lambda_.FunctionUrl(f"donor-form-bridge-lambda-url-{stack}",
    function_name=lambda_function.name,
    authorization_type="NONE",
    cors=aws.lambda_.FunctionUrlCorsArgs(
        allow_credentials=False,
        allow_methods=["POST"],
        allow_origins=["*"],
        allow_headers=["*"],
        max_age=86400
    )
)

# Output the Lambda function URL
pulumi.export("lambda_url", lambda_url.function_url)
pulumi.export("lambda_function_name", lambda_function.name)
pulumi.export("environment", stack)

# Setup instructions
pulumi.export("setup_instructions", {
    "usage": "Use the Lambda Function URL in the FormAssembly connector settings"
})
