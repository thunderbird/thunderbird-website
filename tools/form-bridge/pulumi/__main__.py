import pulumi
import pulumi_aws as aws
import json
from pathlib import Path

# Get configuration
config = pulumi.Config()
stack = pulumi.get_stack()
lambda_environment = {"ENVIRONMENT": stack}
submitter_ip_field_id = config.get("zendeskSubmitterIpFieldId")
if submitter_ip_field_id:
    lambda_environment["ZENDESK_SUBMITTER_IP_FIELD_ID"] = submitter_ip_field_id
trusted_ips = config.get("formassemblyTrustedIps")
if trusted_ips is not None:
    lambda_environment["FORMASSEMBLY_TRUSTED_IPS"] = trusted_ips
formassembly_auth_secret_id = config.get("formassemblyAuthSecretId")
if formassembly_auth_secret_id:
    lambda_environment["FORMASSEMBLY_AUTH_SECRET_ID"] = formassembly_auth_secret_id
abuse_signatures = config.get_object("abuseSignatures")
if abuse_signatures is not None:
    lambda_environment["DONOR_ABUSE_SIGNATURES"] = json.dumps(abuse_signatures, ensure_ascii=False)

rate_limit_table = aws.dynamodb.Table(
    f"donor-form-rate-limit-{stack}",
    billing_mode="PAY_PER_REQUEST",
    hash_key="ip_key",
    attributes=[aws.dynamodb.TableAttributeArgs(name="ip_key", type="S")],
    ttl=aws.dynamodb.TableTtlArgs(attribute_name="expires_at", enabled=True),
)
lambda_environment["DONOR_RATE_LIMIT_TABLE"] = rate_limit_table.name

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
                "arn:aws:secretsmanager:*:*:secret:form-bridge/prod/zendesk*",
                *([f"arn:aws:secretsmanager:*:*:secret:{formassembly_auth_secret_id}*"]
                  if formassembly_auth_secret_id else []),
            ]
        }]
    })
)

# Attach secrets policy to Lambda role
secrets_policy_attachment = aws.iam.RolePolicyAttachment(f"donor-form-bridge-secrets-policy-attachment-{stack}",
    role=lambda_role.name,
    policy_arn=secrets_policy.arn
)

rate_limit_policy = aws.iam.RolePolicy(
    f"donor-form-rate-limit-policy-{stack}",
    role=lambda_role.name,
    policy=rate_limit_table.arn.apply(lambda arn: json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": ["dynamodb:GetItem", "dynamodb:PutItem"],
            "Resource": arn,
        }],
    })),
)

# Create Lambda function
lambda_function = aws.lambda_.Function(f"donor-form-bridge-lambda-{stack}",
    runtime="python3.13",
    handler="lambda_function.lambda_handler",
    role=lambda_role.arn,
    code=pulumi.AssetArchive({
        filename: pulumi.FileAsset(str(Path(__file__).resolve().parent.parent / filename))
        for filename in ("lambda_function.py", "rate_limit.py", "abuse.py", "blocked_strings.json")
    }),
    timeout=30,
    environment=aws.lambda_.FunctionEnvironmentArgs(
        variables=lambda_environment
    ),
    opts=pulumi.ResourceOptions(depends_on=[lambda_policy_attachment, secrets_policy_attachment, rate_limit_policy])
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

# Create SNS topic for alerts
sns_topic = aws.sns.Topic(f"donor-form-bridge-alerts-{stack}",
    name=f"donor-form-bridge-5xx-errors-{stack}",
    display_name="Donor Form Bridge"
)

# Adopt existing groups so Pulumi maintains retention without replacing them.
existing_log_group = config.get("lambdaLogGroupName")
log_group = aws.cloudwatch.LogGroup(
    f"donor-form-logs-{stack}",
    name=existing_log_group or lambda_function.name.apply(lambda name: f"/aws/lambda/{name}"),
    retention_in_days=30,
    opts=pulumi.ResourceOptions(
        import_=existing_log_group,
        retain_on_delete=True,
        ignore_changes=["tags", "tagsAll"] if existing_log_group else None,
    ),
)

rate_limit_metric = aws.cloudwatch.LogMetricFilter(
    f"donor-form-rate-limit-filter-{stack}",
    log_group_name=log_group.name,
    pattern='{ $.rate_limit_status = "limited" }',
    metric_transformation=aws.cloudwatch.LogMetricFilterMetricTransformationArgs(
        name=f"RateLimited-{stack}", namespace="DonorFormBridge", value="1", default_value=0,
    ),
)
rate_limit_alarm = aws.cloudwatch.MetricAlarm(
    f"donor-form-rate-limit-alarm-{stack}",
    alarm_description=f"At least 25 donor submissions rate-limited in five minutes ({stack})",
    namespace="DonorFormBridge", metric_name=f"RateLimited-{stack}",
    statistic="Sum", period=300, evaluation_periods=1, threshold=25,
    comparison_operator="GreaterThanOrEqualToThreshold",
    alarm_actions=[sns_topic.arn], treat_missing_data="notBreaching",
    opts=pulumi.ResourceOptions(depends_on=[rate_limit_metric]),
)

# Create CloudWatch alarm for 5xx errors
error_5xx_alarm = aws.cloudwatch.MetricAlarm(f"donor-form-bridge-5xx-alarm-{stack}",
    name=f"donor-form-bridge-5xx-errors-{stack}",
    alarm_description=f"Alarm when Lambda function returns 5xx errors ({stack})",

    # Use AWS Lambda's built-in Url5xxCount metric for Function URLs
    metric_name="Url5xxCount",
    namespace="AWS/Lambda",
    statistic="Sum",
    dimensions={
        "FunctionName": lambda_function.name
    },

    # Alarm configuration
    period=300,  # 5 minutes
    evaluation_periods=1,
    threshold=1,  # Alert on any 5xx error
    comparison_operator="GreaterThanOrEqualToThreshold",

    # Send notification to SNS topic
    alarm_actions=[sns_topic.arn],
    treat_missing_data="notBreaching"
)

# Output the Lambda function URL
pulumi.export("lambda_url", lambda_url.function_url)
pulumi.export("lambda_function_name", lambda_function.name)
pulumi.export("environment", stack)
pulumi.export("sns_topic_arn", sns_topic.arn)
pulumi.export("alarm_name", error_5xx_alarm.name)
pulumi.export("rate_limit_table_name", rate_limit_table.name)

# Setup instructions
pulumi.export("setup_instructions", {
    "usage": "Use the Lambda Function URL in the FormAssembly connector settings"
})
