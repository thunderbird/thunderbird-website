import json
import os
import pulumi
import pulumi_aws as aws
import pulumi_awsx as awsx

config = pulumi.Config()
environment = config.require("environment")
desired_count = config.get_int("desiredCount") or 1
cpu = config.get_int("cpu") or 256
memory = config.get_int("memory") or 512

# SSL Certificate ARN (shared across environments)
CERTIFICATE_ARN = "arn:aws:acm:us-west-2:768512802988:certificate/2cff184f-31a3-4e9e-b478-eff82076f06f"

# Get image URI from environment variable (set by GitHub Actions workflow)
# This ensures Pulumi always uses the image that was just built and pushed
image_uri = os.environ.get("IMAGE_URI")
if not image_uri:
    raise Exception("IMAGE_URI environment variable is required. The workflow must build and push the image first.")

# ECR Repository (still managed by Pulumi for lifecycle policies)
repo = awsx.ecr.Repository(
    "thunderbird-website",
    name=f"thunderbird-website-{environment}",
    force_delete=True,
)

# VPC with public subnets only (no NAT gateways)
vpc = awsx.ec2.Vpc(
    f"thunderbird-website-{environment}",
    cidr_block="10.0.0.0/16",
    number_of_availability_zones=2,
    nat_gateways=awsx.ec2.NatGatewayConfigurationArgs(strategy=awsx.ec2.NatGatewayStrategy.NONE),
)

# Security group for ALB
alb_sg = aws.ec2.SecurityGroup(
    f"alb-sg-{environment}",
    vpc_id=vpc.vpc_id,
    description="ALB security group",
    ingress=[
        aws.ec2.SecurityGroupIngressArgs(protocol="tcp", from_port=80, to_port=80, cidr_blocks=["0.0.0.0/0"]),
        aws.ec2.SecurityGroupIngressArgs(protocol="tcp", from_port=443, to_port=443, cidr_blocks=["0.0.0.0/0"]),
    ],
    egress=[
        aws.ec2.SecurityGroupEgressArgs(protocol="-1", from_port=0, to_port=0, cidr_blocks=["0.0.0.0/0"]),
    ],
)

# Security group for Fargate tasks
task_sg = aws.ec2.SecurityGroup(
    f"task-sg-{environment}",
    vpc_id=vpc.vpc_id,
    description="Fargate task security group",
    ingress=[
        aws.ec2.SecurityGroupIngressArgs(protocol="tcp", from_port=80, to_port=80, security_groups=[alb_sg.id]),
    ],
    egress=[
        aws.ec2.SecurityGroupEgressArgs(protocol="-1", from_port=0, to_port=0, cidr_blocks=["0.0.0.0/0"]),
    ],
)

# Application Load Balancer
alb = aws.lb.LoadBalancer(
    f"thunderbird-website-alb-{environment}",
    name=f"thunderbird-website-{environment}",
    internal=False,
    load_balancer_type="application",
    security_groups=[alb_sg.id],
    subnets=vpc.public_subnet_ids,
)

# Target group with optimized settings for faster deployments
# See: https://nathanpeck.com/speeding-up-amazon-ecs-container-deployments/
target_group = aws.lb.TargetGroup(
    f"tg-{environment}",
    port=80,
    protocol="HTTP",
    target_type="ip",
    vpc_id=vpc.vpc_id,
    # Reduce deregistration delay from 300s to 5s for faster deployments
    deregistration_delay=5,
    health_check=aws.lb.TargetGroupHealthCheckArgs(
        enabled=True,
        path="/en-US/",
        port="traffic-port",
        protocol="HTTP",
        healthy_threshold=2,
        unhealthy_threshold=2,
        timeout=5,
        interval=6,
        matcher="200",
    ),
)

# HTTP listener - redirect to HTTPS
http_listener = aws.lb.Listener(
    f"http-listener-{environment}",
    load_balancer_arn=alb.arn,
    port=80,
    protocol="HTTP",
    default_actions=[aws.lb.ListenerDefaultActionArgs(
        type="redirect",
        redirect=aws.lb.ListenerDefaultActionRedirectArgs(
            port="443",
            protocol="HTTPS",
            status_code="HTTP_301",
        ),
    )],
)

# HTTPS listener with SSL certificate
https_listener = aws.lb.Listener(
    f"https-listener-{environment}",
    load_balancer_arn=alb.arn,
    port=443,
    protocol="HTTPS",
    ssl_policy="ELBSecurityPolicy-TLS13-1-2-2021-06",
    certificate_arn=CERTIFICATE_ARN,
    default_actions=[aws.lb.ListenerDefaultActionArgs(
        type="forward",
        target_group_arn=target_group.arn,
    )],
)

# ECS Cluster
cluster = aws.ecs.Cluster(
    f"cluster-{environment}",
    name=f"thunderbird-website-{environment}",
    settings=[aws.ecs.ClusterSettingArgs(name="containerInsights", value="enabled")],
)

# IAM execution role
execution_role = aws.iam.Role(
    f"execution-role-{environment}",
    name=f"thunderbird-website-execution-role-{environment}",
    assume_role_policy=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Action": "sts:AssumeRole",
            "Effect": "Allow",
            "Principal": {"Service": "ecs-tasks.amazonaws.com"},
        }],
    }),
)

aws.iam.RolePolicyAttachment(
    f"execution-role-policy-{environment}",
    role=execution_role.name,
    policy_arn="arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy",
)

# IAM task role
task_role = aws.iam.Role(
    f"task-role-{environment}",
    name=f"thunderbird-website-task-role-{environment}",
    assume_role_policy=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Action": "sts:AssumeRole",
            "Effect": "Allow",
            "Principal": {"Service": "ecs-tasks.amazonaws.com"},
        }],
    }),
)

# CloudWatch log group
log_group = aws.cloudwatch.LogGroup(
    f"logs-{environment}",
    name=f"/ecs/thunderbird-website-{environment}",
    retention_in_days=30,
)

# Task definition with optimized settings for faster deployments
def create_container_definitions(args):
    image_uri, log_group_name, region = args
    return json.dumps([{
        "name": "web",
        "image": image_uri,
        "essential": True,
        "portMappings": [{"containerPort": 80, "protocol": "tcp"}],
        # Reduce stop timeout from 30s to 5s - container gets SIGKILL faster
        "stopTimeout": 5,
        "healthCheck": {
            "command": ["CMD-SHELL", "curl -f -H 'Host: www.thunderbird.net' http://localhost/en-US/ || exit 1"],
            "interval": 30,
            "timeout": 10,
            "retries": 3,
            "startPeriod": 60,
        },
        "logConfiguration": {
            "logDriver": "awslogs",
            "options": {
                "awslogs-group": log_group_name,
                "awslogs-region": region,
                "awslogs-stream-prefix": "web",
            },
        },
        "environment": [{"name": "ENVIRONMENT", "value": environment}],
    }])

region = aws.get_region()
container_definitions = pulumi.Output.all(image_uri, log_group.name, region.region).apply(create_container_definitions)

task_definition = aws.ecs.TaskDefinition(
    f"task-{environment}",
    family=f"thunderbird-website-{environment}",
    cpu=str(cpu),
    memory=str(memory),
    network_mode="awsvpc",
    requires_compatibilities=["FARGATE"],
    execution_role_arn=execution_role.arn,
    task_role_arn=task_role.arn,
    container_definitions=container_definitions,
)

# ECS Service with optimized deployment settings
service = aws.ecs.Service(
    f"service-{environment}",
    name=f"thunderbird-website-{environment}",
    cluster=cluster.arn,
    task_definition=task_definition.arn,
    desired_count=desired_count,
    launch_type="FARGATE",
    # Faster rolling deployments - allow stopping 50% of tasks before replacements are up
    deployment_minimum_healthy_percent=50,
    deployment_maximum_percent=200,
    network_configuration=aws.ecs.ServiceNetworkConfigurationArgs(
        subnets=vpc.public_subnet_ids,
        security_groups=[task_sg.id],
        assign_public_ip=True,
    ),
    load_balancers=[aws.ecs.ServiceLoadBalancerArgs(
        target_group_arn=target_group.arn,
        container_name="web",
        container_port=80,
    )],
    health_check_grace_period_seconds=30,
    opts=pulumi.ResourceOptions(depends_on=[http_listener, https_listener]),
)

# Outputs
pulumi.export("vpc_id", vpc.vpc_id)
pulumi.export("cluster_name", cluster.name)
pulumi.export("service_name", service.name)
pulumi.export("repository_url", repo.url)
pulumi.export("image_uri", image_uri)

# DNS Configuration - Add CNAME record pointing to this endpoint
pulumi.export("alb_dns_name", alb.dns_name)
pulumi.export("alb_hosted_zone_id", alb.zone_id)
pulumi.export("dns_instructions", alb.dns_name.apply(
    lambda dns: f"Add CNAME pointing your domain to: {dns}"
))

