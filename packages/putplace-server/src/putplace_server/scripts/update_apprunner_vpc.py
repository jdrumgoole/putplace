#!/usr/bin/env python3
"""
Update an existing AWS AppRunner service to use VPC Connector for fixed IP.

This script updates an AppRunner service configuration to route egress traffic
through a VPC Connector, which provides a static IP address via NAT Gateway.

Prerequisites:
    - VPC Connector already created (run setup_apprunner_fixed_ip.py first)
    - AWS CLI configured with appropriate credentials
    - AppRunner service name or ARN
"""

import json
import subprocess
import sys
from typing import Optional


def run_aws_command(command: list[str]) -> dict:
    """Execute AWS CLI command and return JSON output."""
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True
        )
        if result.stdout.strip():
            return json.loads(result.stdout)
        return {}
    except subprocess.CalledProcessError as e:
        print(f"Error executing command: {' '.join(command)}", file=sys.stderr)
        print(f"Error output: {e.stderr}", file=sys.stderr)
        raise
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON output: {e}", file=sys.stderr)
        print(f"Output was: {result.stdout}", file=sys.stderr)
        raise


def get_service_arn(service_name: str, region: str) -> Optional[str]:
    """Get AppRunner service ARN from service name."""
    print(f"Looking up service: {service_name}...")
    result = run_aws_command([
        "aws", "apprunner", "list-services",
        "--region", region
    ])

    for service in result.get("ServiceSummaryList", []):
        if service["ServiceName"] == service_name:
            return service["ServiceArn"]

    return None


def describe_service(service_arn: str, region: str) -> dict:
    """Get current service configuration."""
    result = run_aws_command([
        "aws", "apprunner", "describe-service",
        "--service-arn", service_arn,
        "--region", region
    ])
    return result["Service"]


def update_service_with_vpc(
    service_arn: str,
    vpc_connector_arn: str,
    region: str
) -> dict:
    """Update AppRunner service to use VPC Connector."""
    print(f"\nUpdating service to use VPC Connector...")
    print(f"Service: {service_arn}")
    print(f"VPC Connector: {vpc_connector_arn}")

    result = run_aws_command([
        "aws", "apprunner", "update-service",
        "--service-arn", service_arn,
        "--network-configuration",
        json.dumps({
            "EgressConfiguration": {
                "EgressType": "VPC",
                "VpcConnectorArn": vpc_connector_arn
            }
        }),
        "--region", region
    ])

    operation_id = result["Service"]["ServiceArn"]
    print(f"✓ Update initiated: {operation_id}")

    return result["Service"]


def wait_for_service_update(service_arn: str, region: str) -> None:
    """Wait for service update to complete."""
    import time

    print("\nWaiting for service update to complete (this may take several minutes)...")

    for i in range(60):  # Wait up to 10 minutes
        service = describe_service(service_arn, region)
        status = service["Status"]

        if status == "RUNNING":
            print("✓ Service update complete and running")
            return
        elif status in ["OPERATION_IN_PROGRESS", "CREATE_FAILED", "DELETE_FAILED"]:
            print(f"  Status: {status} (waiting...)")
            time.sleep(10)
        else:
            print(f"✓ Service status: {status}")
            return

    print("⚠ Service update taking longer than expected. Check AWS console for status.")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Update AppRunner service to use VPC Connector"
    )
    parser.add_argument(
        "service",
        help="AppRunner service name or ARN"
    )
    parser.add_argument(
        "--vpc-connector-arn",
        required=True,
        help="VPC Connector ARN to use"
    )
    parser.add_argument(
        "--region",
        default="eu-west-1",
        help="AWS region (default: eu-west-1)"
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Wait for update to complete"
    )
    args = parser.parse_args()

    print(f"\n=== Updating AppRunner Service with VPC Connector ===\n")

    # Determine if input is ARN or name
    if args.service.startswith("arn:"):
        service_arn = args.service
    else:
        service_arn = get_service_arn(args.service, args.region)
        if not service_arn:
            print(f"❌ Service '{args.service}' not found in region {args.region}",
                  file=sys.stderr)
            sys.exit(1)

    # Get current service configuration
    service = describe_service(service_arn, args.region)
    print(f"Current service: {service['ServiceName']}")
    print(f"Status: {service['Status']}")

    current_egress = service.get("NetworkConfiguration", {}).get(
        "EgressConfiguration", {}
    ).get("EgressType", "DEFAULT")
    print(f"Current egress type: {current_egress}")

    if current_egress == "VPC":
        current_vpc_connector = service["NetworkConfiguration"]["EgressConfiguration"].get(
            "VpcConnectorArn"
        )
        print(f"Current VPC Connector: {current_vpc_connector}")

        if current_vpc_connector == args.vpc_connector_arn:
            print("\n✓ Service is already using the specified VPC Connector")
            return

    # Update service
    try:
        update_service_with_vpc(service_arn, args.vpc_connector_arn, args.region)

        if args.wait:
            wait_for_service_update(service_arn, args.region)

        print("\n=== Update Complete! ===\n")
        print("Your AppRunner service now routes traffic through the VPC Connector.")
        print("All outbound traffic will use the NAT Gateway's static IP address.")

    except Exception as e:
        print(f"\n❌ Update failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
