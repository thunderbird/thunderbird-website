# Donor Support Form Bridge

This bridges the form assembly data from the donor support form into Zendesk via their API.

## Directory Structure

```
form-bridge/
├── lambda_function.py      # Main Lambda function code
├── lambda_test.py         # Unit tests
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

The dropdown field `tfa_95` maps values like `tfa_197` to "Technical support for Thunderbird" and prepends it to the subject.

## Deployment

```bash
cd pulumi
pulumi stack select stage  # or prod
pulumi up
```

## Testing

Run unit tests:
```bash
pytest lambda_test.py
```

Test the deployed Lambda:
```bash
curl -X POST "LAMBDA_URL" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "tfa_95=tfa_197&tfa_211=Test&tfa_163=Test%20message&tfa_1=Name&tfa_10=email%40example.com"
```
