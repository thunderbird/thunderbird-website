"""Check the deployable package, permissions, and alarms without touching AWS."""

import json
from pathlib import Path
import runpy

import pulumi


def test_production_infrastructure():
    resources = []
    existing_group = '/aws/lambda/donor-form-bridge-lambda-prod-example'

    class Mocks(pulumi.runtime.Mocks):
        def new_resource(self, args):
            resources.append(args)
            outputs = dict(args.inputs)
            outputs.setdefault('name', args.resource_id or args.name)
            outputs.setdefault('arn', f'arn:aws:test:us-east-2:123456789012:{args.name}')
            return args.resource_id or args.name, outputs

        def call(self, args):
            return args.args

    @pulumi.runtime.test
    def build():
        pulumi.runtime.set_mocks(Mocks(), project='donor-form-bridge', stack='prod', preview=False)
        pulumi.runtime.set_all_config({
            'donor-form-bridge:formassemblyAuthSecretId': 'form-bridge/prod/formassembly',
            'donor-form-bridge:lambdaLogGroupName': existing_group,
        })
        infra = runpy.run_path(str(Path(__file__).with_name('pulumi') / '__main__.py'))
        return pulumi.Output.all(infra['lambda_function'].urn, infra['rate_limit_policy'].policy)

    build()
    function = next(r for r in resources if r.typ == 'aws:lambda/function:Function')
    assert function.inputs['runtime'] == 'python3.13'
    assert set(function.inputs['code'].assets) == {
        'lambda_function.py', 'rate_limit.py', 'abuse.py', 'blocked_strings.json',
    }
    assert function.inputs['environment']['variables']['FORMASSEMBLY_AUTH_SECRET_ID'] == 'form-bridge/prod/formassembly'
    policy = next(r for r in resources if r.typ == 'aws:iam/rolePolicy:RolePolicy')
    actions = json.loads(policy.inputs['policy'])['Statement'][0]['Action']
    assert set(actions) == {'dynamodb:GetItem', 'dynamodb:PutItem'}
    log_group = next(r for r in resources if r.typ == 'aws:cloudwatch/logGroup:LogGroup')
    assert log_group.resource_id == existing_group
    assert log_group.inputs['name'] == existing_group
    assert log_group.inputs['retentionInDays'] == 30
    filters = [r for r in resources if r.typ == 'aws:cloudwatch/logMetricFilter:LogMetricFilter']
    assert len(filters) == 1
    assert all(r.inputs['logGroupName'] == existing_group for r in filters)
    assert filters[0].inputs['pattern'] == '{ $.rate_limit_status = "limited" }'
    alarms = [r for r in resources if r.typ == 'aws:cloudwatch/metricAlarm:MetricAlarm']
    assert {r.inputs['metricName'] for r in alarms} == {
        'Url5xxCount', 'RateLimited-prod',
    }
    rate_alarm = next(r for r in alarms if r.inputs['metricName'] == 'RateLimited-prod')
    error_alarm = next(r for r in alarms if r.inputs['metricName'] == 'Url5xxCount')
    assert rate_alarm.inputs['alarmActions'] == error_alarm.inputs['alarmActions']
    assert len(rate_alarm.inputs['alarmActions']) == 1
    assert rate_alarm.inputs['threshold'] == 25
    assert rate_alarm.inputs['period'] == 300
    assert rate_alarm.inputs['evaluationPeriods'] == 1
    assert rate_alarm.inputs['treatMissingData'] == 'notBreaching'
    assert error_alarm.inputs['threshold'] == 1
