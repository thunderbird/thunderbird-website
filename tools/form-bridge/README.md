# Donor Support Form Bridge

This bridges the form assembly data from the donor support form into Zendesk via their API.

## Directory Structure

```
form-bridge/
├── lambda_function.py      # Main Lambda function code
├── abuse.py                # String matching and rule loading
├── blocked_strings.json    # Editable abuse rules
├── rate_limit.py           # Atomic per-IP allowance
├── lambda_test.py         # Unit tests
├── rate_limit_test.py      # Limit, concurrency, and identity tests
├── README.md             # This file
└── pulumi/               # Pulumi infrastructure code
    ├── __main__.py       # Main Pulumi program
    ├── Pulumi.yaml       # Pulumi project configuration
    ├── Pulumi.stage.yaml # Stage environment config
    └── Pulumi.prod.yaml  # Production environment config
```

## Form Assembly to Zendesk Field Mappings

| Form Assembly Field | Zendesk Field | Description |
|-------------------|---------------|-------------|
| `tfa_95` | Subject Prefix | Dropdown selection (prepended to subject) |
| `tfa_211` | Subject | Ticket subject line |
| `tfa_163` | Comment Body | Main ticket content |
| `tfa_1` | Requester Name | Person submitting form |
| `tfa_10` | Requester Email | Contact email |
| `submitter_ip` | Form submitter IP and audit metadata | Connector formula `%%IP_ADDRESS%%`; not a browser input |

The dropdown field `tfa_95` maps values like `tfa_197` to "Technical support for Thunderbird" and prepends it to the subject.

## Submitter IP forwarding and logging

In the FormAssembly HTTPS connector, add an outgoing field named `submitter_ip`
and use `%%IP_ADDRESS%%` as its formula value. This must be a connector mapping,
not a hidden field that the respondent fills in. Existing mappings stay the same.
IP anonymization must be disabled in FormAssembly to retain the full address.

Production requires the connector's HTTP Basic credentials before processing
any form data. Configure them in FormAssembly's **Remote Script & Authentication**
settings and store the same username and password as JSON in AWS Secrets Manager
at `form-bridge/prod/formassembly`. The Pulumi setting `formassemblyAuthSecretId`
passes the secret name to Lambda; the secret value is never stored in Pulumi
configuration or the repository. The Lambda rejects missing or incorrect
credentials with HTTP 401 and fails closed with HTTP 503 if the secret cannot be
read. Have a FormAssembly administrator save the connector credentials before
deploying this branch to production, then verify a real submission immediately.
Direct unauthenticated calls to the Lambda URL cannot create tickets or consume
rate-limit allowances.

An authenticated connector can supply `submitter_ip` regardless of its outgoing
address. In environments without a configured authentication secret, the bridge
accepts this field only when Lambda's `requestContext.http.sourceIp` matches a
trusted FormAssembly connector address. The default addresses are the
[published US connector addresses](https://help.formassembly.com/help/ip-whitelisting-for-formassembly).
For other hosting regions or changed addresses, set `FORMASSEMBLY_TRUSTED_IPS` to
a comma-separated list (Pulumi setting `formassemblyTrustedIps`). This IP list
is a compatibility fallback, not authentication of an individual tenant.

Set `ZENDESK_SUBMITTER_IP_FIELD_ID` to the ID of an agent-only text ticket field
(Pulumi setting `zendeskSubmitterIpFieldId`). A valid forwarded address is saved
in that field and in Zendesk audit `metadata.custom.submitter_ip`, together with
the Lambda request ID. Zendesk's system audit IP continues to identify the API
connection. The respondent IP is never added to the public ticket comment.
Production uses the agent-only **Form submitter IP** field (`56354955452947`) on
the **Donor Support** ticket form.

Each invocation writes a `donor_form_submission` JSON record to the Lambda's
CloudWatch log group, including rejected submissions. It contains `connection_ip`,
`submitter_ip`, `submitter_ip_status`, `request_id`, `auth_status` when enabled,
and, on successful ticket creation, `zendesk_ticket_id`. Status is `forwarded`,
`missing`, `invalid`, or `untrusted_source`. Missing or invalid forwarding leaves
`submitter_ip` null. With rate limiting enabled, a trusted relay must supply a
valid submitter IP. CloudTrail cannot record this forwarded form field, so use
the application log for respondent IPs.

The existing Lambda URL 5xx alarm remains in place. A second alarm uses that same
SNS topic only when at least 25 submissions hit the rate limit in five minutes;
an isolated rejection does not trigger it. Log events expire after 30 days in
production and staging. The `lambdaLogGroupName` setting imports each existing
deployment's log group so Pulumi maintains that retention policy; omit it for a
new deployment to create a group with the same 30-day retention. Imported groups
keep their existing tags, and removing a group from Pulumi does not delete it.

Example CloudWatch Logs Insights query (select the Lambda log group):

```sql
fields @timestamp, request_id, connection_ip, submitter_ip, submitter_ip_status, zendesk_ticket_id
| filter event = "donor_form_submission"
| sort @timestamp desc
| limit 100
```

## Known abuse filtering

Edit `blocked_strings.json` to add rules; every string value in the parsed form
is checked, including email and fields added in the future. A JSON string
blocks that phrase; an array requires all its phrases in the same field:

```json
[
  "one blocked phrase",
  ["both this phrase", "and this phrase"]
]
```

The file retains the four observed abuse patterns, without automatic expiry.
Matching ignores case, Unicode compatibility variants, punctuation, and
whitespace. `DONOR_ABUSE_SIGNATURES` can override the entire file (Pulumi
setting `abuseSignatures`); omit that override to use the checked-in rules.

A matching request is acknowledged with HTTP 200 without calling Zendesk,
preventing a connector error from causing repeat delivery. Its structured
CloudWatch record includes `outcome=blocked`,
`block_reason=known_abuse_signature`, and `block_rule=donor-abuse-N` (the
one-based position of the configured group), alongside the usual IP metadata.
The rule is not disclosed in the response, and the blocked message and email
are not logged. Unmatched requests continue through normal ticket creation.

To disable the filter, set `DONOR_ABUSE_SIGNATURES` to `[]`, or set
`abuseSignatures` to an empty list in Pulumi. Invalid configuration logs an error and disables filtering
rather than rejecting all support requests.

## One submission per IP every 12 hours

Pulumi provisions an on-demand DynamoDB table and passes its name in
`DONOR_RATE_LIMIT_TABLE`. The Lambda checks the last successful submission before
contacting Zendesk and records a new 12-hour window only after Zendesk accepts
the ticket. Other requests for that IP receive HTTP 429 with a
`Retry-After` header until 43,200 seconds have elapsed; rejected attempts do
not extend the window. Different emails and different FormAssembly relay
addresses do not create new allowances. IPv6 addresses in the same `/64`
share an allowance so rotating privacy addresses cannot bypass the limit.
People sharing an IPv4 address or IPv6 `/64` share the same limit.

The limit uses an authenticated FormAssembly connector's `submitter_ip`. In
environments without connector authentication, direct callers use their observed
connection IP. A connector without a valid forwarded IP
receives HTTP 503, as does a failed rate-limit lookup, so neither silently bypasses the
limit. IPv4-mapped IPv6 addresses share the IPv4 allowance. The table stores
SHA-256 IP keys, request IDs, and expiry times. Strongly consistent reads check
the expiry even before DynamoDB's asynchronous TTL cleanup removes old rows.

Phrase-blocked, invalid, failed, and unfinished requests consume no allowance.
The check and post-success write are separate, so simultaneous submissions from
the same IP can both create tickets. If recording the allowance fails after
Zendesk accepts a ticket, the Lambda logs the error and still acknowledges the
created ticket. Logs include
`rate_limit_status`, and rate-limited requests include
`block_reason=ip_rate_limit` and the remaining `retry_after` seconds.

Zendesk calls disable automatic HTTP retries and redirects.
Ticket creation includes Zendesk's supported
[`Idempotency-Key`](https://developer.zendesk.com/api-reference/ticketing/introduction/#idempotency),
using the Lambda request ID. This key protects repeated requests within that
invocation; a new FormAssembly delivery has a new ID and is not deduplicated by
this key.

Without `DONOR_RATE_LIMIT_TABLE` the limiter is disabled; both Pulumi stacks
configure the table automatically. Deploy using Pulumi so all four runtime
files are included in the Lambda package.

## Deployment

The Lambda uses Python 3.13 and packages only `lambda_function.py`, `rate_limit.py`,
`abuse.py`, and `blocked_strings.json` through Pulumi's `AssetArchive`.

```bash
cd pulumi
pulumi stack select stage  # or prod
pulumi up
```

After deployment to stage, you can run a quick curl test as described below as a final check that is everything is working. This should create a test ticket in Zendesk and return the API response.

## Testing

Run unit and infrastructure tests with Python 3.13:
```bash
python -m pip install -r requirements-test.txt
python -m pytest lambda_test.py rate_limit_test.py pulumi_test.py
```

CI runs these checks in the AWS Lambda Python 3.13 image pinned by digest in
`Dockerfile.test` and prints its bundled SDK versions before installing test
dependencies. Dependabot checks weekly for image digest and GitHub Actions
updates; image updates stay within the Python 3.13 runtime series. The SDK
request-shape tests validate the read and post-success write API calls.

Test the deployed Lambda, lambda-url is returned by the Pulumi script after deployment:
```bash
curl -X POST "https://lambda-url" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "tfa_95=tfa_197" \
  -d "tfa_211=TEST - Form submission integration test" \
  -d "tfa_163=This is a test of the donor form bridge Lambda function. Please ignore this ticket." \
  -d "tfa_1=Yourname" \
  -d "tfa_10=youremail@thunderbird.net" \
  | jq .
```

This creates a real ticket and consumes the caller's allowance, so repeating it
within 12 hours returns HTTP 429. When testing an authenticated environment,
supply the connector's Basic credentials and a valid `submitter_ip`. For a
repeatable check that creates no ticket or allowance, use a known blocked phrase
in the message and verify `outcome=blocked` in CloudWatch.
