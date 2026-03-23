"""PR Preview Infrastructure: Lambda + API Gateway HTTP API per PR.

Environment variables (set by GitHub Actions):
  PREVIEW_SLUG  - DNS-safe slug, e.g. "archive-fix-123"
  IMAGE_URI     - ECR image URI for the preview container
  PREVIEW_SITE  - Canonical site domain to preview (e.g. "www.thunderbird.net", "tb.pro")
"""

import json
import os

import pulumi
import pulumi_aws as aws

config = pulumi.Config()
domain = config.require("domain")
certificate_arn = config.require("certificateArn")

slug = os.environ.get("PREVIEW_SLUG")
if not slug:
    raise Exception("PREVIEW_SLUG environment variable is required")

image_uri = os.environ.get("IMAGE_URI", "not-set")
preview_site = os.environ.get("PREVIEW_SITE", "www.thunderbird.net")
preview_host = f"{slug}.{domain}"

# ---------------------------------------------------------------------------
# Route53 hosted zone lookup
# ---------------------------------------------------------------------------
zone = aws.route53.get_zone(name=domain)

# ---------------------------------------------------------------------------
# IAM role for Lambda execution
# ---------------------------------------------------------------------------
lambda_role = aws.iam.Role(
    "lambda-role",
    name=f"preview-{slug}-lambda",
    assume_role_policy=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Action": "sts:AssumeRole",
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
        }],
    }),
)

aws.iam.RolePolicyAttachment(
    "lambda-basic-execution",
    role=lambda_role.name,
    policy_arn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
)

# ---------------------------------------------------------------------------
# Lambda function (container image via Lambda Web Adapter)
# ---------------------------------------------------------------------------
lambda_function = aws.lambda_.Function(
    "preview-function",
    name=f"preview-{slug}",
    package_type="Image",
    image_uri=image_uri,
    role=lambda_role.arn,
    memory_size=512,
    timeout=30,
    environment=aws.lambda_.FunctionEnvironmentArgs(
        variables={
            "PREVIEW": "true",
            "PREVIEW_SITE": preview_site,
            "PREVIEW_HOST": preview_host,
            "AWS_LWA_PORT": "8080",
        },
    ),
)

# ---------------------------------------------------------------------------
# API Gateway HTTP API
# ---------------------------------------------------------------------------
api = aws.apigatewayv2.Api(
    "preview-api",
    name=f"preview-{slug}",
    protocol_type="HTTP",
)

integration = aws.apigatewayv2.Integration(
    "lambda-integration",
    api_id=api.id,
    integration_type="AWS_PROXY",
    integration_uri=lambda_function.invoke_arn,
    payload_format_version="2.0",
)

route = aws.apigatewayv2.Route(
    "default-route",
    api_id=api.id,
    route_key="$default",
    target=integration.id.apply(lambda id: f"integrations/{id}"),
)

stage = aws.apigatewayv2.Stage(
    "default-stage",
    api_id=api.id,
    name="$default",
    auto_deploy=True,
)

# Allow API Gateway to invoke the Lambda function
aws.lambda_.Permission(
    "apigw-invoke",
    action="lambda:InvokeFunction",
    function=lambda_function.name,
    principal="apigateway.amazonaws.com",
    source_arn=api.execution_arn.apply(lambda arn: f"{arn}/*/*"),
)

# ---------------------------------------------------------------------------
# Custom domain on API Gateway
# ---------------------------------------------------------------------------
domain_name = aws.apigatewayv2.DomainName(
    "preview-domain",
    domain_name=preview_host,
    domain_name_configuration=aws.apigatewayv2.DomainNameDomainNameConfigurationArgs(
        certificate_arn=certificate_arn,
        endpoint_type="REGIONAL",
        security_policy="TLS_1_2",
    ),
)

aws.apigatewayv2.ApiMapping(
    "preview-mapping",
    api_id=api.id,
    domain_name=domain_name.id,
    stage=stage.id,
)

# ---------------------------------------------------------------------------
# Route53 A record -> API Gateway custom domain
# ---------------------------------------------------------------------------
aws.route53.Record(
    "preview-dns",
    zone_id=zone.zone_id,
    name=preview_host,
    type="A",
    aliases=[aws.route53.RecordAliasArgs(
        name=domain_name.domain_name_configuration.target_domain_name,
        zone_id=domain_name.domain_name_configuration.hosted_zone_id,
        evaluate_target_health=False,
    )],
)

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------
pulumi.export("preview_url", f"https://{preview_host}")
pulumi.export("function_name", lambda_function.name)
pulumi.export("api_endpoint", api.api_endpoint)
