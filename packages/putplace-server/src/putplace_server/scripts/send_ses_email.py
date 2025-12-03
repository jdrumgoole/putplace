#!/usr/bin/env python3
"""Standalone script for sending emails via Amazon SES.

This script allows you to send emails through Amazon SES with configurable
from address, to addresses, subject, and body content.

Requirements:
    - boto3 library installed
    - AWS credentials configured (via environment, ~/.aws/credentials, or IAM role)
    - Verified sender email address in SES
    - SES sandbox lifted or verified recipient addresses

Usage:
    python send_ses_email.py --from sender@example.com \
                             --to recipient@example.com \
                             --subject "Test Email" \
                             --body "This is a test email"

    # HTML email
    python send_ses_email.py --from sender@example.com \
                             --to recipient@example.com \
                             --subject "HTML Email" \
                             --body "<h1>Hello</h1><p>This is HTML</p>" \
                             --html

    # Multiple recipients
    python send_ses_email.py --from sender@example.com \
                             --to user1@example.com user2@example.com \
                             --subject "Announcement" \
                             --body "Important message"

    # With CC and BCC
    python send_ses_email.py --from sender@example.com \
                             --to recipient@example.com \
                             --cc copy@example.com \
                             --bcc blind@example.com \
                             --subject "Meeting Update" \
                             --body "Meeting details..."

    # Body from file
    python send_ses_email.py --from sender@example.com \
                             --to recipient@example.com \
                             --subject "Report" \
                             --body-file report.txt

    # Specify AWS region
    python send_ses_email.py --from sender@example.com \
                             --to recipient@example.com \
                             --subject "Test" \
                             --body "Testing" \
                             --region eu-west-1
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
except ImportError:
    print("Error: boto3 library not installed.")
    print("Install with: pip install boto3")
    sys.exit(1)


def send_email(
    from_address: str,
    to_addresses: List[str],
    subject: str,
    body: str,
    cc_addresses: Optional[List[str]] = None,
    bcc_addresses: Optional[List[str]] = None,
    is_html: bool = False,
    region: str = "eu-west-1",
    aws_profile: Optional[str] = None,
) -> dict:
    """Send an email via Amazon SES.

    Args:
        from_address: Sender email address (must be verified in SES)
        to_addresses: List of recipient email addresses
        subject: Email subject line
        body: Email body content
        cc_addresses: Optional list of CC recipients
        bcc_addresses: Optional list of BCC recipients
        is_html: If True, treat body as HTML content
        region: AWS region for SES (default: eu-west-1)
        aws_profile: Optional AWS profile name from ~/.aws/credentials

    Returns:
        Response dictionary from SES with MessageId

    Raises:
        ClientError: If SES API call fails
        NoCredentialsError: If AWS credentials not found
    """
    # Create SES client
    session_kwargs = {"region_name": region}
    if aws_profile:
        session_kwargs["profile_name"] = aws_profile

    session = boto3.Session(**session_kwargs)
    client = session.client("ses")

    # Build destination
    destination = {"ToAddresses": to_addresses}
    if cc_addresses:
        destination["CcAddresses"] = cc_addresses
    if bcc_addresses:
        destination["BccAddresses"] = bcc_addresses

    # Build message
    body_key = "Html" if is_html else "Text"
    message = {
        "Subject": {"Data": subject, "Charset": "UTF-8"},
        "Body": {body_key: {"Data": body, "Charset": "UTF-8"}},
    }

    # Send email
    response = client.send_email(
        Source=from_address, Destination=destination, Message=message
    )

    return response


def main() -> int:
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Send emails via Amazon SES",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Simple text email
  %(prog)s --from sender@example.com --to recipient@example.com \\
           --subject "Hello" --body "This is a test"

  # HTML email
  %(prog)s --from sender@example.com --to recipient@example.com \\
           --subject "Welcome" --body "<h1>Welcome!</h1>" --html

  # Multiple recipients with CC
  %(prog)s --from sender@example.com \\
           --to user1@example.com user2@example.com \\
           --cc manager@example.com \\
           --subject "Team Update" --body "Please review..."

  # Body from file
  %(prog)s --from sender@example.com --to recipient@example.com \\
           --subject "Report" --body-file report.html --html

  # Specify AWS region
  %(prog)s --from sender@example.com --to recipient@example.com \\
           --subject "Test" --body "Testing" --region eu-west-1

Environment Variables:
  AWS_ACCESS_KEY_ID       AWS access key
  AWS_SECRET_ACCESS_KEY   AWS secret key
  AWS_DEFAULT_REGION      Default AWS region

Note:
  - Sender address must be verified in SES
  - If in SES sandbox, recipient addresses must also be verified
  - Ensure AWS credentials are configured via environment variables,
    ~/.aws/credentials, or IAM role
        """,
    )

    # Required arguments
    parser.add_argument(
        "--from",
        dest="from_address",
        required=True,
        help="Sender email address (must be verified in SES)",
    )
    parser.add_argument(
        "--to",
        dest="to_addresses",
        nargs="+",
        required=True,
        help="Recipient email address(es)",
    )
    parser.add_argument(
        "--subject", required=True, help="Email subject line"
    )

    # Body content (mutually exclusive)
    body_group = parser.add_mutually_exclusive_group(required=True)
    body_group.add_argument("--body", help="Email body content")
    body_group.add_argument(
        "--body-file", type=Path, help="Read email body from file"
    )

    # Optional arguments
    parser.add_argument(
        "--cc", dest="cc_addresses", nargs="+", help="CC recipient(s)"
    )
    parser.add_argument(
        "--bcc", dest="bcc_addresses", nargs="+", help="BCC recipient(s)"
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="Treat body content as HTML instead of plain text",
    )
    parser.add_argument(
        "--region",
        default="eu-west-1",
        help="AWS region for SES (default: eu-west-1)",
    )
    parser.add_argument(
        "--profile",
        dest="aws_profile",
        help="AWS profile name from ~/.aws/credentials",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose output"
    )

    args = parser.parse_args()

    # Read body from file if specified
    if args.body_file:
        if not args.body_file.exists():
            print(f"Error: Body file not found: {args.body_file}", file=sys.stderr)
            return 1
        try:
            body = args.body_file.read_text(encoding="utf-8")
        except Exception as e:
            print(f"Error reading body file: {e}", file=sys.stderr)
            return 1
    else:
        body = args.body

    # Validate email addresses (basic check)
    def is_valid_email(email: str) -> bool:
        return "@" in email and "." in email.split("@")[1]

    if not is_valid_email(args.from_address):
        print(f"Error: Invalid sender email: {args.from_address}", file=sys.stderr)
        return 1

    for email in args.to_addresses:
        if not is_valid_email(email):
            print(f"Error: Invalid recipient email: {email}", file=sys.stderr)
            return 1

    # Print details if verbose
    if args.verbose:
        print(f"From: {args.from_address}")
        print(f"To: {', '.join(args.to_addresses)}")
        if args.cc_addresses:
            print(f"CC: {', '.join(args.cc_addresses)}")
        if args.bcc_addresses:
            print(f"BCC: {', '.join(args.bcc_addresses)}")
        print(f"Subject: {args.subject}")
        print(f"Body type: {'HTML' if args.html else 'Text'}")
        print(f"Region: {args.region}")
        if args.aws_profile:
            print(f"AWS Profile: {args.aws_profile}")
        print(f"Body preview: {body[:100]}...")
        print()

    # Send email
    try:
        response = send_email(
            from_address=args.from_address,
            to_addresses=args.to_addresses,
            subject=args.subject,
            body=body,
            cc_addresses=args.cc_addresses,
            bcc_addresses=args.bcc_addresses,
            is_html=args.html,
            region=args.region,
            aws_profile=args.aws_profile,
        )

        message_id = response.get("MessageId", "unknown")
        print(f"✓ Email sent successfully!")
        print(f"  Message ID: {message_id}")

        if args.verbose:
            print(f"  Request ID: {response['ResponseMetadata']['RequestId']}")
            print(f"  HTTP Status: {response['ResponseMetadata']['HTTPStatusCode']}")

        return 0

    except NoCredentialsError:
        print("Error: AWS credentials not found.", file=sys.stderr)
        print("Configure credentials via:", file=sys.stderr)
        print("  - Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)", file=sys.stderr)
        print("  - ~/.aws/credentials file", file=sys.stderr)
        print("  - IAM role (if running on EC2/ECS/Lambda)", file=sys.stderr)
        return 1

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", str(e))

        print(f"Error: SES API call failed ({error_code})", file=sys.stderr)
        print(f"  {error_message}", file=sys.stderr)

        # Provide helpful hints for common errors
        if error_code == "MessageRejected":
            print("\nCommon causes:", file=sys.stderr)
            print("  - Sender email not verified in SES", file=sys.stderr)
            print("  - Recipient email not verified (if in SES sandbox)", file=sys.stderr)
            print("  - Email content flagged by filters", file=sys.stderr)
        elif error_code == "AccessDenied":
            print("\nCommon causes:", file=sys.stderr)
            print("  - AWS credentials lack SES permissions", file=sys.stderr)
            print("  - Using wrong AWS region", file=sys.stderr)

        return 1

    except Exception as e:
        print(f"Error: Unexpected error occurred: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
