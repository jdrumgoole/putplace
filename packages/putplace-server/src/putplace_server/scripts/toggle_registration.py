#!/usr/bin/env python3
"""Toggle user registration on AWS App Runner.

This script allows you to enable or disable user registration on a running
App Runner service without redeploying the application.

Usage:
    python -m putplace.scripts.toggle_registration enable
    python -m putplace.scripts.toggle_registration disable

    # Or via invoke:
    invoke toggle-registration --action=enable
    invoke toggle-registration --action=disable

Environment Variables:
    APPRUNNER_SERVICE_ARN: ARN of the App Runner service (required)

Example:
    export APPRUNNER_SERVICE_ARN="arn:aws:apprunner:eu-west-1:123456:service/putplace/abc123"
    python -m putplace.scripts.toggle_registration disable
"""

import argparse
import json
import os
import sys
import time
from typing import Dict, Any, Optional

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
except ImportError:
    print("Error: boto3 is required. Install with: pip install boto3")
    sys.exit(1)


def get_service_arn() -> str:
    """Get App Runner service ARN from environment variable.

    Returns:
        Service ARN

    Raises:
        SystemExit: If ARN not found in environment
    """
    arn = os.environ.get("APPRUNNER_SERVICE_ARN")
    if not arn:
        print("❌ Error: APPRUNNER_SERVICE_ARN environment variable not set")
        print()
        print("Set it with:")
        print('  export APPRUNNER_SERVICE_ARN="arn:aws:apprunner:region:account:service/putplace/xxx"')
        print()
        print("Or find it with:")
        print("  aws apprunner list-services --query 'ServiceSummaryList[?ServiceName==`putplace`].ServiceArn' --output text")
        sys.exit(1)
    return arn


def get_current_env_vars(client: Any, service_arn: str) -> Dict[str, str]:
    """Get current environment variables from App Runner service.

    Args:
        client: boto3 App Runner client
        service_arn: ARN of the service

    Returns:
        Dictionary of current environment variables
    """
    try:
        response = client.describe_service(ServiceArn=service_arn)

        # Navigate to environment variables
        source_config = response.get("Service", {}).get("SourceConfiguration", {})
        image_repo = source_config.get("ImageRepository", {})
        image_config = image_repo.get("ImageConfiguration", {})
        env_vars = image_config.get("RuntimeEnvironmentVariables", {})

        return env_vars if env_vars else {}

    except ClientError as e:
        print(f"❌ Error fetching service configuration: {e}")
        sys.exit(1)


def update_service(client: Any, service_arn: str, env_vars: Dict[str, str]) -> None:
    """Update App Runner service with new environment variables.

    Args:
        client: boto3 App Runner client
        service_arn: ARN of the service
        env_vars: Updated environment variables
    """
    try:
        client.update_service(
            ServiceArn=service_arn,
            SourceConfiguration={
                "ImageRepository": {
                    "ImageConfiguration": {
                        "RuntimeEnvironmentVariables": env_vars
                    }
                }
            }
        )
    except ClientError as e:
        print(f"❌ Error updating service: {e}")
        sys.exit(1)


def get_service_status(client: Any, service_arn: str) -> str:
    """Get current service status.

    Args:
        client: boto3 App Runner client
        service_arn: ARN of the service

    Returns:
        Service status string
    """
    try:
        response = client.describe_service(ServiceArn=service_arn)
        return response.get("Service", {}).get("Status", "UNKNOWN")
    except ClientError:
        return "UNKNOWN"


def toggle_registration(action: str, service_arn: Optional[str] = None) -> None:
    """Toggle registration on App Runner service.

    Args:
        action: "enable" or "disable"
        service_arn: Optional service ARN (uses env var if not provided)
    """
    # Validate action
    if action not in ["enable", "disable"]:
        print(f"❌ Error: Action must be 'enable' or 'disable', got '{action}'")
        sys.exit(1)

    # Get service ARN
    if service_arn is None:
        service_arn = get_service_arn()

    # Determine registration value
    reg_value = "true" if action == "enable" else "false"
    emoji = "🔓" if action == "enable" else "🔒"

    print(f"{emoji} {'Enabling' if action == 'enable' else 'Disabling'} user registration...")
    print()

    # Initialize boto3 client
    try:
        # Extract region from ARN
        # ARN format: arn:aws:apprunner:region:account:service/name/id
        region = service_arn.split(":")[3]
        client = boto3.client("apprunner", region_name=region)
    except (IndexError, NoCredentialsError) as e:
        print(f"❌ Error initializing AWS client: {e}")
        print()
        print("Make sure AWS credentials are configured:")
        print("  aws configure")
        sys.exit(1)

    # Get current environment variables
    print("📥 Fetching current service configuration...")
    env_vars = get_current_env_vars(client, service_arn)

    if not env_vars:
        print("⚠️  No existing environment variables found, creating new ones...")

    # Update the registration flag
    env_vars["PUTPLACE_REGISTRATION_ENABLED"] = reg_value

    print(f"🔄 Updating App Runner service...")
    print(f"   Setting PUTPLACE_REGISTRATION_ENABLED={reg_value}")
    print()

    # Update the service
    update_service(client, service_arn, env_vars)

    print("✅ Service update initiated")
    print()
    print("📊 Checking deployment status...")

    # Wait for deployment to start
    time.sleep(5)

    # Check status
    status = get_service_status(client, service_arn)
    print(f"Current status: {status}")
    print()

    # Print monitoring commands
    print("ℹ️  Monitor deployment with:")
    print(f'  aws apprunner describe-service --service-arn "{service_arn}" --query "Service.Status"')
    print()
    print("Or in AWS Console:")
    print("  https://console.aws.amazon.com/apprunner/home#/services")
    print()

    if action == "disable":
        print("🔒 Registration will be disabled once deployment completes (2-3 minutes)")
    else:
        print("🔓 Registration will be enabled once deployment completes (2-3 minutes)")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Toggle user registration on AWS App Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s enable           Enable user registration
  %(prog)s disable          Disable user registration

Environment Variables:
  APPRUNNER_SERVICE_ARN     ARN of the App Runner service (required)

Setup:
  export APPRUNNER_SERVICE_ARN="arn:aws:apprunner:eu-west-1:123456:service/putplace/abc123"
        """
    )

    parser.add_argument(
        "action",
        choices=["enable", "disable"],
        help="Action to perform: enable or disable registration"
    )

    parser.add_argument(
        "--service-arn",
        help="App Runner service ARN (overrides APPRUNNER_SERVICE_ARN env var)"
    )

    args = parser.parse_args()

    toggle_registration(args.action, args.service_arn)


if __name__ == "__main__":
    main()
