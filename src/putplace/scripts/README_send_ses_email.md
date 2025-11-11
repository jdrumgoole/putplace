# Send SES Email Script

A standalone Python script for sending emails via Amazon Simple Email Service (SES).

## Features

- ✉️ Send text or HTML emails
- 📧 Multiple recipients (To, CC, BCC)
- 📄 Read email body from file
- 🔐 AWS authentication via credentials or IAM role
- 🌍 Specify AWS region
- 🎯 Comprehensive error handling
- 📊 Verbose output mode

## Requirements

```bash
pip install boto3
```

Or with uv:
```bash
uv pip install boto3
```

## AWS Setup

### 1. Verify Email Addresses in SES

Before sending emails, you must verify your sender email address in Amazon SES:

1. Go to the [SES Console](https://console.aws.amazon.com/ses/)
2. Navigate to "Verified identities"
3. Click "Create identity"
4. Enter your email address
5. Click the verification link sent to your email

**Note:** If your account is in the SES sandbox, you must also verify recipient email addresses.

### 2. Request Production Access (Optional)

To send emails to unverified addresses:

1. In the SES Console, go to "Account dashboard"
2. Click "Request production access"
3. Fill out the form explaining your use case
4. Wait for AWS approval (usually 24-48 hours)

### 3. Configure AWS Credentials

Choose one of these methods:

**Environment Variables:**
```bash
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_DEFAULT_REGION=eu-west-1
```

**AWS Credentials File (~/.aws/credentials):**
```ini
[default]
aws_access_key_id = your_access_key
aws_secret_access_key = your_secret_key
region = eu-west-1

[myprofile]
aws_access_key_id = other_access_key
aws_secret_access_key = other_secret_key
```

**IAM Role (Recommended for EC2/ECS/Lambda):**
No configuration needed - the script will automatically use the instance's IAM role.

## Usage Examples

### Basic Text Email

```bash
python send_ses_email.py \
  --from sender@example.com \
  --to recipient@example.com \
  --subject "Hello World" \
  --body "This is a test email"
```

### HTML Email

```bash
python send_ses_email.py \
  --from sender@example.com \
  --to recipient@example.com \
  --subject "Welcome!" \
  --body "<h1>Welcome</h1><p>Thank you for joining us!</p>" \
  --html
```

### Multiple Recipients

```bash
python send_ses_email.py \
  --from sender@example.com \
  --to user1@example.com user2@example.com user3@example.com \
  --subject "Team Announcement" \
  --body "Important update for the team"
```

### With CC and BCC

```bash
python send_ses_email.py \
  --from sender@example.com \
  --to recipient@example.com \
  --cc manager@example.com \
  --bcc audit@example.com \
  --subject "Project Update" \
  --body "Here's the latest status..."
```

### Body from File

```bash
# Text file
python send_ses_email.py \
  --from sender@example.com \
  --to recipient@example.com \
  --subject "Monthly Report" \
  --body-file report.txt

# HTML file
python send_ses_email.py \
  --from sender@example.com \
  --to recipient@example.com \
  --subject "Newsletter" \
  --body-file newsletter.html \
  --html
```

### Specify AWS Region

```bash
python send_ses_email.py \
  --from sender@example.com \
  --to recipient@example.com \
  --subject "Test" \
  --body "Testing from eu-west-1" \
  --region eu-west-1
```

### Use AWS Profile

```bash
python send_ses_email.py \
  --from sender@example.com \
  --to recipient@example.com \
  --subject "Test" \
  --body "Using myprofile credentials" \
  --profile myprofile
```

### Verbose Output

```bash
python send_ses_email.py \
  --from sender@example.com \
  --to recipient@example.com \
  --subject "Test" \
  --body "Detailed output" \
  --verbose
```

Output:
```
From: sender@example.com
To: recipient@example.com
Subject: Test
Body type: Text
Region: eu-west-1
Body preview: Detailed output...

✓ Email sent successfully!
  Message ID: 0102018c9876543210abcdef-12345678-9abc-def0-1234-56789abcdef0-000000
  Request ID: abc123def456-7890-1234-5678-90abcdef1234
  HTTP Status: 200
```

## Command-Line Options

| Option | Description | Required |
|--------|-------------|----------|
| `--from` | Sender email address (must be verified in SES) | Yes |
| `--to` | Recipient email address(es) | Yes |
| `--subject` | Email subject line | Yes |
| `--body` | Email body content (text) | Yes* |
| `--body-file` | Read email body from file | Yes* |
| `--cc` | CC recipient(s) | No |
| `--bcc` | BCC recipient(s) | No |
| `--html` | Treat body as HTML instead of plain text | No |
| `--region` | AWS region for SES (default: eu-west-1) | No |
| `--profile` | AWS profile name from ~/.aws/credentials | No |
| `-v, --verbose` | Enable verbose output | No |

\* Either `--body` or `--body-file` is required (mutually exclusive)

## Error Messages

### Email Address Not Verified

```
Error: SES API call failed (MessageRejected)
  Email address is not verified. The following identities failed the check...

Common causes:
  - Sender email not verified in SES
  - Recipient email not verified (if in SES sandbox)
  - Email content flagged by filters
```

**Solution:** Verify your email address in the SES Console.

### No AWS Credentials

```
Error: AWS credentials not found.
Configure credentials via:
  - Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
  - ~/.aws/credentials file
  - IAM role (if running on EC2/ECS/Lambda)
```

**Solution:** Set up AWS credentials using one of the methods above.

### Access Denied

```
Error: SES API call failed (AccessDenied)
  User is not authorized to perform: ses:SendEmail

Common causes:
  - AWS credentials lack SES permissions
  - Using wrong AWS region
```

**Solution:** Ensure your IAM user/role has the `ses:SendEmail` permission.

## IAM Policy for SES

Minimum IAM policy required:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ses:SendEmail",
        "ses:SendRawEmail"
      ],
      "Resource": "*"
    }
  ]
}
```

For more restrictive access, limit to specific verified identities:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ses:SendEmail",
        "ses:SendRawEmail"
      ],
      "Resource": "arn:aws:ses:us-east-1:123456789012:identity/sender@example.com"
    }
  ]
}
```

## Integration Examples

### Shell Script

```bash
#!/bin/bash
# send_report.sh

RECIPIENT="manager@example.com"
SENDER="reports@example.com"
DATE=$(date +%Y-%m-%d)

# Generate report
./generate_report.sh > /tmp/report.txt

# Send email
python send_ses_email.py \
  --from "$SENDER" \
  --to "$RECIPIENT" \
  --subject "Daily Report - $DATE" \
  --body-file /tmp/report.txt

# Clean up
rm /tmp/report.txt
```

### Python Integration

```python
from putplace.scripts.send_ses_email import send_email

# Send email programmatically
response = send_email(
    from_address="sender@example.com",
    to_addresses=["recipient@example.com"],
    subject="Automated Report",
    body="<h1>Report</h1><p>Content here</p>",
    is_html=True,
    region="eu-west-1"
)

print(f"Email sent with Message ID: {response['MessageId']}")
```

### Cron Job

```cron
# Send daily report at 9 AM
0 9 * * * /usr/bin/python /path/to/send_ses_email.py \
  --from reports@example.com \
  --to team@example.com \
  --subject "Daily Summary" \
  --body-file /var/reports/daily.txt
```

## Testing

The script includes comprehensive tests. Run them with:

```bash
pytest tests/test_send_ses_email.py -v
```

## Troubleshooting

### SES Sandbox Limitations

If you're in the SES sandbox:
- You can only send emails to verified addresses
- Sending is limited to 200 emails per 24 hours
- Maximum send rate is 1 email per second

**Solution:** Request production access in the SES Console.

### Rate Limiting

If you get throttling errors:
```
Error: Throttling: Maximum sending rate exceeded
```

**Solution:**
- Reduce sending rate
- Request a sending rate increase in SES Console
- Implement retry logic with exponential backoff

### Large Emails

SES has a maximum email size of 10 MB (including attachments).

**Solution:**
- Keep emails under 10 MB
- Host large files externally and link to them
- Consider using S3 pre-signed URLs for file sharing

## License

Apache-2.0

## Support

For issues or questions:
- Check the [AWS SES Documentation](https://docs.aws.amazon.com/ses/)
- Review [SES FAQ](https://aws.amazon.com/ses/faqs/)
- Open an issue on GitHub
