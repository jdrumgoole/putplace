#!/usr/bin/env python3
"""
Setup script to create a fixed IP address for AWS AppRunner instance.

This script creates the necessary AWS infrastructure to provide a static IP address
for AppRunner, which is required for MongoDB Atlas IP whitelisting.

Architecture:
    VPC -> Public Subnet (NAT Gateway with Elastic IP)
        -> Private Subnet (AppRunner via VPC Connector)
        -> Internet via NAT Gateway (fixed IP)

Prerequisites:
    - AWS CLI configured with appropriate credentials
    - Sufficient permissions to create VPC, NAT Gateway, and AppRunner resources
"""

import json
import subprocess
import sys
import time
from typing import Optional


class AppRunnerIPSetup:
    """Manages AWS infrastructure setup for AppRunner fixed IP."""

    def __init__(self, region: str = "eu-west-1", project_name: str = "putplace"):
        self.region = region
        self.project_name = project_name
        self.vpc_id: Optional[str] = None
        self.igw_id: Optional[str] = None
        self.public_subnet_id: Optional[str] = None
        self.private_subnet_id: Optional[str] = None
        self.nat_gateway_id: Optional[str] = None
        self.elastic_ip: Optional[str] = None
        self.vpc_connector_arn: Optional[str] = None

    def run_aws_command(self, command: list[str]) -> dict:
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

    def create_vpc(self) -> str:
        """Create VPC for AppRunner."""
        print("Creating VPC...")
        result = self.run_aws_command([
            "aws", "ec2", "create-vpc",
            "--cidr-block", "10.0.0.0/16",
            "--region", self.region,
            "--tag-specifications",
            f"ResourceType=vpc,Tags=[{{Key=Name,Value={self.project_name}-vpc}}]"
        ])
        self.vpc_id = result["Vpc"]["VpcId"]
        print(f"✓ VPC created: {self.vpc_id}")

        # Enable DNS hostnames
        self.run_aws_command([
            "aws", "ec2", "modify-vpc-attribute",
            "--vpc-id", self.vpc_id,
            "--enable-dns-hostnames",
            "--region", self.region
        ])
        print("✓ DNS hostnames enabled")

        return self.vpc_id

    def create_internet_gateway(self) -> str:
        """Create and attach Internet Gateway."""
        print("Creating Internet Gateway...")
        result = self.run_aws_command([
            "aws", "ec2", "create-internet-gateway",
            "--region", self.region,
            "--tag-specifications",
            f"ResourceType=internet-gateway,Tags=[{{Key=Name,Value={self.project_name}-igw}}]"
        ])
        self.igw_id = result["InternetGateway"]["InternetGatewayId"]
        print(f"✓ Internet Gateway created: {self.igw_id}")

        # Attach to VPC
        self.run_aws_command([
            "aws", "ec2", "attach-internet-gateway",
            "--internet-gateway-id", self.igw_id,
            "--vpc-id", self.vpc_id,
            "--region", self.region
        ])
        print("✓ Internet Gateway attached to VPC")

        return self.igw_id

    def create_subnets(self) -> tuple[str, str]:
        """Create public and private subnets."""
        print("Creating public subnet...")
        result = self.run_aws_command([
            "aws", "ec2", "create-subnet",
            "--vpc-id", self.vpc_id,
            "--cidr-block", "10.0.1.0/24",
            "--availability-zone", f"{self.region}a",
            "--region", self.region,
            "--tag-specifications",
            f"ResourceType=subnet,Tags=[{{Key=Name,Value={self.project_name}-public-subnet}}]"
        ])
        self.public_subnet_id = result["Subnet"]["SubnetId"]
        print(f"✓ Public subnet created: {self.public_subnet_id}")

        print("Creating private subnet...")
        result = self.run_aws_command([
            "aws", "ec2", "create-subnet",
            "--vpc-id", self.vpc_id,
            "--cidr-block", "10.0.2.0/24",
            "--availability-zone", f"{self.region}b",
            "--region", self.region,
            "--tag-specifications",
            f"ResourceType=subnet,Tags=[{{Key=Name,Value={self.project_name}-private-subnet}}]"
        ])
        self.private_subnet_id = result["Subnet"]["SubnetId"]
        print(f"✓ Private subnet created: {self.private_subnet_id}")

        return self.public_subnet_id, self.private_subnet_id

    def create_nat_gateway(self) -> tuple[str, str]:
        """Create NAT Gateway with Elastic IP."""
        print("Allocating Elastic IP...")
        result = self.run_aws_command([
            "aws", "ec2", "allocate-address",
            "--domain", "vpc",
            "--region", self.region,
            "--tag-specifications",
            f"ResourceType=elastic-ip,Tags=[{{Key=Name,Value={self.project_name}-nat-eip}}]"
        ])
        allocation_id = result["AllocationId"]
        self.elastic_ip = result["PublicIp"]
        print(f"✓ Elastic IP allocated: {self.elastic_ip}")

        print("Creating NAT Gateway (this takes a few minutes)...")
        result = self.run_aws_command([
            "aws", "ec2", "create-nat-gateway",
            "--subnet-id", self.public_subnet_id,
            "--allocation-id", allocation_id,
            "--region", self.region,
            "--tag-specifications",
            f"ResourceType=natgateway,Tags=[{{Key=Name,Value={self.project_name}-nat}}]"
        ])
        self.nat_gateway_id = result["NatGateway"]["NatGatewayId"]
        print(f"✓ NAT Gateway created: {self.nat_gateway_id}")

        # Wait for NAT Gateway to become available
        print("Waiting for NAT Gateway to become available...")
        for i in range(30):
            result = self.run_aws_command([
                "aws", "ec2", "describe-nat-gateways",
                "--nat-gateway-ids", self.nat_gateway_id,
                "--region", self.region
            ])
            state = result["NatGateways"][0]["State"]
            if state == "available":
                print("✓ NAT Gateway is available")
                break
            print(f"  Status: {state} (waiting...)")
            time.sleep(10)
        else:
            raise RuntimeError("NAT Gateway did not become available in time")

        return self.nat_gateway_id, self.elastic_ip

    def configure_route_tables(self) -> None:
        """Configure route tables for public and private subnets."""
        print("Configuring public subnet route table...")

        # Get the main route table
        result = self.run_aws_command([
            "aws", "ec2", "describe-route-tables",
            "--filters", f"Name=vpc-id,Values={self.vpc_id}",
            "--region", self.region
        ])
        main_route_table_id = result["RouteTables"][0]["RouteTableId"]

        # Add route to Internet Gateway for public subnet
        self.run_aws_command([
            "aws", "ec2", "create-route",
            "--route-table-id", main_route_table_id,
            "--destination-cidr-block", "0.0.0.0/0",
            "--gateway-id", self.igw_id,
            "--region", self.region
        ])
        print("✓ Public route table configured")

        # Associate public subnet with main route table
        self.run_aws_command([
            "aws", "ec2", "associate-route-table",
            "--route-table-id", main_route_table_id,
            "--subnet-id", self.public_subnet_id,
            "--region", self.region
        ])
        print("✓ Public subnet associated with route table")

        print("Creating private subnet route table...")
        result = self.run_aws_command([
            "aws", "ec2", "create-route-table",
            "--vpc-id", self.vpc_id,
            "--region", self.region,
            "--tag-specifications",
            f"ResourceType=route-table,Tags=[{{Key=Name,Value={self.project_name}-private-rt}}]"
        ])
        private_route_table_id = result["RouteTable"]["RouteTableId"]
        print(f"✓ Private route table created: {private_route_table_id}")

        # Add route to NAT Gateway for private subnet
        self.run_aws_command([
            "aws", "ec2", "create-route",
            "--route-table-id", private_route_table_id,
            "--destination-cidr-block", "0.0.0.0/0",
            "--nat-gateway-id", self.nat_gateway_id,
            "--region", self.region
        ])
        print("✓ Private route table configured with NAT Gateway")

        # Associate private subnet with private route table
        self.run_aws_command([
            "aws", "ec2", "associate-route-table",
            "--route-table-id", private_route_table_id,
            "--subnet-id", self.private_subnet_id,
            "--region", self.region
        ])
        print("✓ Private subnet associated with route table")

    def create_security_group(self) -> str:
        """Create security group for VPC Connector."""
        print("Creating security group...")
        result = self.run_aws_command([
            "aws", "ec2", "create-security-group",
            "--group-name", f"{self.project_name}-vpc-connector-sg",
            "--description", "Security group for AppRunner VPC Connector",
            "--vpc-id", self.vpc_id,
            "--region", self.region,
            "--tag-specifications",
            f"ResourceType=security-group,Tags=[{{Key=Name,Value={self.project_name}-vpc-connector-sg}}]"
        ])
        security_group_id = result["GroupId"]
        print(f"✓ Security group created: {security_group_id}")

        # Allow all outbound traffic
        self.run_aws_command([
            "aws", "ec2", "authorize-security-group-egress",
            "--group-id", security_group_id,
            "--ip-permissions",
            "IpProtocol=-1,IpRanges=[{CidrIp=0.0.0.0/0}]",
            "--region", self.region
        ])
        print("✓ Security group configured for outbound traffic")

        return security_group_id

    def create_vpc_connector(self, security_group_id: str) -> str:
        """Create VPC Connector for AppRunner."""
        print("Creating VPC Connector...")
        result = self.run_aws_command([
            "aws", "apprunner", "create-vpc-connector",
            "--vpc-connector-name", f"{self.project_name}-vpc-connector",
            "--subnets", self.private_subnet_id,
            "--security-groups", security_group_id,
            "--region", self.region
        ])
        self.vpc_connector_arn = result["VpcConnector"]["VpcConnectorArn"]
        print(f"✓ VPC Connector created: {self.vpc_connector_arn}")

        return self.vpc_connector_arn

    def setup(self) -> dict[str, str]:
        """Run complete setup and return configuration."""
        print(f"\n=== Setting up AppRunner Fixed IP in {self.region} ===\n")

        try:
            # Create VPC infrastructure
            self.create_vpc()
            self.create_internet_gateway()
            self.create_subnets()
            self.create_nat_gateway()
            self.configure_route_tables()

            # Create VPC Connector
            security_group_id = self.create_security_group()
            self.create_vpc_connector(security_group_id)

            print("\n=== Setup Complete! ===\n")
            print(f"Static IP Address: {self.elastic_ip}")
            print(f"VPC Connector ARN: {self.vpc_connector_arn}")
            print("\nNext steps:")
            print(f"1. Add {self.elastic_ip} to MongoDB Atlas IP whitelist")
            print("2. Update your AppRunner service to use the VPC Connector")
            print(f"   (Use ARN: {self.vpc_connector_arn})")

            return {
                "elastic_ip": self.elastic_ip,
                "vpc_connector_arn": self.vpc_connector_arn,
                "vpc_id": self.vpc_id,
                "region": self.region,
            }

        except Exception as e:
            print(f"\n❌ Setup failed: {e}", file=sys.stderr)
            print("\nYou may need to manually clean up resources.", file=sys.stderr)
            sys.exit(1)


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Setup fixed IP address for AWS AppRunner instance"
    )
    parser.add_argument(
        "--region",
        default="eu-west-1",
        help="AWS region (default: eu-west-1)"
    )
    parser.add_argument(
        "--project-name",
        default="putplace",
        help="Project name for resource tagging (default: putplace)"
    )
    args = parser.parse_args()

    setup = AppRunnerIPSetup(region=args.region, project_name=args.project_name)
    config = setup.setup()

    # Save configuration to file
    output_file = "apprunner_fixed_ip_config.json"
    with open(output_file, "w") as f:
        json.dump(config, f, indent=2)
    print(f"\n✓ Configuration saved to {output_file}")


if __name__ == "__main__":
    main()
