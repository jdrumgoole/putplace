#!/usr/bin/env python3
"""
Deploy PutPlace to AWS App Runner
Default region: eu-west-1 (Ireland) - closest to Ireland

Usage:
    python deploy/app_runner_deploy.py                    # Deploy to eu-west-1 (Ireland)
    python deploy/app_runner_deploy.py --region us-east-1 # Deploy to specific region
    python deploy/app_runner_deploy.py --help             # Show help
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


class Colors:
    """ANSI color codes for terminal output."""
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    CYAN = '\033[0;36m'
    BOLD = '\033[1m'
    NC = '\033[0m'  # No Color


class AppRunnerDeployer:
    """Deploy PutPlace to AWS App Runner."""

    def __init__(
        self,
        region: str = "eu-west-1",
        service_name: str = "putplace-api",
        interactive: bool = True
    ):
        self.region = region
        self.service_name = service_name
        self.interactive = interactive
        self.ecr_repo_name = "putplace"
        self.cpu = "1 vCPU"
        self.memory = "2 GB"
        self.port = "8000"

        # Will be set during execution
        self.aws_account_id: Optional[str] = None
        self.mongodb_url: Optional[str] = None
        self.s3_bucket_name: Optional[str] = None
        self.google_client_id: Optional[str] = None
        self.admin_username: str = "admin"
        self.admin_password: Optional[str] = None
        self.admin_email: str = "admin@putplace.local"
        self.ecr_uri: Optional[str] = None
        self.access_role_arn: Optional[str] = None
        self.instance_role_arn: Optional[str] = None

    def print_step(self, message: str):
        """Print a step header."""
        print(f"\n{Colors.BLUE}==>{Colors.NC} {Colors.GREEN}{message}{Colors.NC}\n")

    def print_info(self, message: str):
        """Print an info message."""
        print(f"{Colors.BLUE}ℹ{Colors.NC}  {message}")

    def print_success(self, message: str):
        """Print a success message."""
        print(f"{Colors.GREEN}✓{Colors.NC}  {message}")

    def print_warning(self, message: str):
        """Print a warning message."""
        print(f"{Colors.YELLOW}⚠{Colors.NC}  {message}")

    def print_error(self, message: str):
        """Print an error message."""
        print(f"{Colors.RED}✗{Colors.NC}  {message}", file=sys.stderr)

    def run_command(
        self,
        cmd: list[str],
        capture_output: bool = True,
        check: bool = True
    ) -> subprocess.CompletedProcess:
        """Run a shell command."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=capture_output,
                text=True,
                check=check
            )
            return result
        except subprocess.CalledProcessError as e:
            self.print_error(f"Command failed: {' '.join(cmd)}")
            if e.stderr:
                self.print_error(f"Error: {e.stderr}")
            raise

    def check_prerequisites(self):
        """Check that all required tools are installed."""
        self.print_step("Checking prerequisites")

        # Check AWS CLI
        try:
            result = self.run_command(["aws", "--version"])
            self.print_success(f"AWS CLI found: {result.stdout.strip()}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.print_error("AWS CLI is not installed")
            self.print_info("Install: https://aws.amazon.com/cli/")
            sys.exit(1)

        # Check Docker
        try:
            result = self.run_command(["docker", "--version"])
            self.print_success(f"Docker found: {result.stdout.strip()}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.print_error("Docker is not installed")
            self.print_info("Install: https://docs.docker.com/get-docker/")
            sys.exit(1)

        # Check AWS credentials
        try:
            result = self.run_command(
                ["aws", "sts", "get-caller-identity", "--query", "Account", "--output", "text"]
            )
            self.aws_account_id = result.stdout.strip()

            result = self.run_command(
                ["aws", "sts", "get-caller-identity", "--query", "Arn", "--output", "text"]
            )
            aws_user = result.stdout.strip().split('/')[-1]

            self.print_success(f"AWS credentials configured: {aws_user} (Account: {self.aws_account_id})")
        except subprocess.CalledProcessError:
            self.print_error("AWS credentials not configured")
            self.print_info("Run: aws configure")
            sys.exit(1)

        # Check if we're in the right directory
        if not Path("pyproject.toml").exists():
            self.print_error("Must run from project root directory")
            sys.exit(1)
        self.print_success("Running from project root")

    def gather_configuration(self):
        """Gather configuration from user or environment."""
        self.print_step("Configuration")

        self.print_info(f"Region: {self.region}")
        self.print_info(f"Service name: {self.service_name}")
        self.print_info(f"ECR repository: {self.ecr_repo_name}")
        self.print_info(f"CPU: {self.cpu}, Memory: {self.memory}")

        # MongoDB URL
        import os
        self.mongodb_url = os.getenv("MONGODB_URL")

        if not self.mongodb_url:
            if self.interactive:
                self.mongodb_url = input("\nMongoDB URL (mongodb+srv://...): ").strip()
                if not self.mongodb_url:
                    self.print_error("MongoDB URL is required")
                    sys.exit(1)
            else:
                self.print_error("MONGODB_URL environment variable is required in non-interactive mode")
                sys.exit(1)

        self.print_success("MongoDB URL configured")

        # S3 bucket name
        self.s3_bucket_name = os.getenv("S3_BUCKET_NAME")

        if not self.s3_bucket_name:
            if self.interactive:
                user_input = input("S3 bucket name (leave empty to create new): ").strip()
                self.s3_bucket_name = user_input if user_input else f"putplace-files-{self.aws_account_id}"
                if not user_input:
                    self.print_info(f"Will create bucket: {self.s3_bucket_name}")
            else:
                self.s3_bucket_name = f"putplace-files-{self.aws_account_id}"
                self.print_info(f"Will create bucket: {self.s3_bucket_name}")

        # Google OAuth (optional)
        self.google_client_id = os.getenv("GOOGLE_CLIENT_ID")

        if not self.google_client_id and self.interactive:
            self.google_client_id = input("Google OAuth Client ID (optional, press Enter to skip): ").strip()

        # Admin credentials
        self.admin_username = os.getenv("ADMIN_USERNAME", "admin")
        self.admin_email = os.getenv("ADMIN_EMAIL", "admin@putplace.local")
        self.admin_password = os.getenv("ADMIN_PASSWORD")

        if not self.admin_password:
            if self.interactive:
                import getpass
                self.admin_password = getpass.getpass("Admin password (leave empty to auto-generate): ")

            if not self.admin_password:
                # Generate random password
                import secrets
                import string
                alphabet = string.ascii_letters + string.digits
                self.admin_password = ''.join(secrets.choice(alphabet) for _ in range(21))
                self.print_warning(f"Generated admin password: {self.admin_password}")
                self.print_warning("Save this password! It will not be shown again.")
                if self.interactive:
                    input("Press Enter to continue...")

        print()

    def create_s3_bucket(self):
        """Create S3 bucket if it doesn't exist."""
        self.print_step("Setting up S3 bucket")

        # Check if bucket exists
        result = self.run_command(
            ["aws", "s3", "ls", f"s3://{self.s3_bucket_name}"],
            check=False
        )

        if result.returncode == 0:
            self.print_success(f"S3 bucket already exists: {self.s3_bucket_name}")
        else:
            self.print_info(f"Creating S3 bucket: {self.s3_bucket_name}")

            # Create bucket (different command for us-east-1 vs other regions)
            if self.region == "us-east-1":
                self.run_command([
                    "aws", "s3", "mb", f"s3://{self.s3_bucket_name}",
                    "--region", self.region
                ])
            else:
                self.run_command([
                    "aws", "s3", "mb", f"s3://{self.s3_bucket_name}",
                    "--region", self.region
                ])
                # Set location constraint for non-us-east-1 regions
                # Note: mb command handles this automatically in newer AWS CLI versions

            self.print_success("S3 bucket created")

            # Enable versioning
            self.print_info("Enabling versioning...")
            self.run_command([
                "aws", "s3api", "put-bucket-versioning",
                "--bucket", self.s3_bucket_name,
                "--versioning-configuration", "Status=Enabled",
                "--region", self.region
            ])
            self.print_success("Versioning enabled")

    def create_ecr_repository(self):
        """Create ECR repository if it doesn't exist."""
        self.print_step("Setting up ECR repository")

        # Check if repository exists
        result = self.run_command(
            [
                "aws", "ecr", "describe-repositories",
                "--repository-names", self.ecr_repo_name,
                "--region", self.region
            ],
            check=False
        )

        if result.returncode == 0:
            self.print_success(f"ECR repository already exists: {self.ecr_repo_name}")
        else:
            self.print_info(f"Creating ECR repository: {self.ecr_repo_name}")
            self.run_command([
                "aws", "ecr", "create-repository",
                "--repository-name", self.ecr_repo_name,
                "--region", self.region,
                "--image-scanning-configuration", "scanOnPush=true",
                "--encryption-configuration", "encryptionType=AES256"
            ])
            self.print_success("ECR repository created")

        self.ecr_uri = f"{self.aws_account_id}.dkr.ecr.{self.region}.amazonaws.com/{self.ecr_repo_name}"
        self.print_info(f"ECR URI: {self.ecr_uri}")

    def build_and_push_image(self):
        """Build Docker image and push to ECR."""
        self.print_step("Building and pushing Docker image")

        # Login to ECR
        self.print_info("Logging in to ECR...")
        login_password = self.run_command([
            "aws", "ecr", "get-login-password",
            "--region", self.region
        ]).stdout.strip()

        self.run_command(
            [
                "docker", "login",
                "--username", "AWS",
                "--password-stdin",
                f"{self.aws_account_id}.dkr.ecr.{self.region}.amazonaws.com"
            ],
            capture_output=False,
            check=True
        )

        # Note: We need to pipe the password
        process = subprocess.Popen(
            [
                "docker", "login",
                "--username", "AWS",
                "--password-stdin",
                f"{self.aws_account_id}.dkr.ecr.{self.region}.amazonaws.com"
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        process.communicate(input=login_password)

        self.print_success("Logged in to ECR")

        # Build image
        self.print_info("Building Docker image (this may take a few minutes)...")
        self.run_command(
            ["docker", "build", "-t", f"{self.ecr_repo_name}:latest", "."],
            capture_output=False
        )
        self.print_success("Docker image built")

        # Tag image
        self.print_info("Tagging image...")
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.run_command(["docker", "tag", f"{self.ecr_repo_name}:latest", f"{self.ecr_uri}:latest"])
        self.run_command(["docker", "tag", f"{self.ecr_repo_name}:latest", f"{self.ecr_uri}:{timestamp}"])
        self.print_success("Image tagged")

        # Push image
        self.print_info("Pushing image to ECR (this may take a few minutes)...")
        self.run_command(
            ["docker", "push", f"{self.ecr_uri}:latest"],
            capture_output=False
        )
        self.print_success("Image pushed to ECR")

    def create_app_runner_roles(self):
        """Create IAM roles for App Runner."""
        self.print_step("Setting up IAM roles")

        # Access role (for ECR)
        access_role_name = f"AppRunnerECRAccessRole-{self.service_name}"

        result = self.run_command(
            ["aws", "iam", "get-role", "--role-name", access_role_name],
            check=False
        )

        if result.returncode == 0:
            self.print_success("Access role already exists")
        else:
            self.print_info("Creating ECR access role...")

            # Trust policy
            trust_policy = {
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Principal": {"Service": "build.apprunner.amazonaws.com"},
                    "Action": "sts:AssumeRole"
                }]
            }

            self.run_command([
                "aws", "iam", "create-role",
                "--role-name", access_role_name,
                "--assume-role-policy-document", json.dumps(trust_policy)
            ])

            self.run_command([
                "aws", "iam", "attach-role-policy",
                "--role-name", access_role_name,
                "--policy-arn", "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"
            ])

            self.print_success("Access role created")
            time.sleep(10)  # Wait for role to propagate

        result = self.run_command([
            "aws", "iam", "get-role",
            "--role-name", access_role_name,
            "--query", "Role.Arn",
            "--output", "text"
        ])
        self.access_role_arn = result.stdout.strip()

        # Instance role (for S3 access)
        instance_role_name = f"AppRunnerInstanceRole-{self.service_name}"

        result = self.run_command(
            ["aws", "iam", "get-role", "--role-name", instance_role_name],
            check=False
        )

        if result.returncode == 0:
            self.print_success("Instance role already exists")
        else:
            self.print_info("Creating instance role...")

            # Trust policy
            instance_trust_policy = {
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Principal": {"Service": "tasks.apprunner.amazonaws.com"},
                    "Action": "sts:AssumeRole"
                }]
            }

            self.run_command([
                "aws", "iam", "create-role",
                "--role-name", instance_role_name,
                "--assume-role-policy-document", json.dumps(instance_trust_policy)
            ])

            # S3 access policy
            s3_policy = {
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Action": [
                        "s3:GetObject",
                        "s3:PutObject",
                        "s3:DeleteObject",
                        "s3:ListBucket"
                    ],
                    "Resource": [
                        f"arn:aws:s3:::{self.s3_bucket_name}",
                        f"arn:aws:s3:::{self.s3_bucket_name}/*"
                    ]
                }]
            }

            self.run_command([
                "aws", "iam", "put-role-policy",
                "--role-name", instance_role_name,
                "--policy-name", "S3Access",
                "--policy-document", json.dumps(s3_policy)
            ])

            self.print_success("Instance role created")
            time.sleep(10)  # Wait for role to propagate

        result = self.run_command([
            "aws", "iam", "get-role",
            "--role-name", instance_role_name,
            "--query", "Role.Arn",
            "--output", "text"
        ])
        self.instance_role_arn = result.stdout.strip()

    def deploy_to_app_runner(self):
        """Deploy or update App Runner service."""
        self.print_step("Deploying to App Runner")

        # Check if service exists
        result = self.run_command([
            "aws", "apprunner", "list-services",
            "--region", self.region,
            "--query", f"ServiceSummaryList[?ServiceName=='{self.service_name}'].ServiceArn",
            "--output", "text"
        ])

        service_arn = result.stdout.strip()

        # Build environment variables
        env_vars = {
            "MONGODB_URL": self.mongodb_url,
            "MONGODB_DATABASE": "putplace",
            "MONGODB_COLLECTION": "file_metadata",
            "STORAGE_BACKEND": "s3",
            "S3_BUCKET_NAME": self.s3_bucket_name,
            "AWS_REGION": self.region,
            "PUTPLACE_ADMIN_USERNAME": self.admin_username,
            "PUTPLACE_ADMIN_PASSWORD": self.admin_password,
            "PUTPLACE_ADMIN_EMAIL": self.admin_email
        }

        if self.google_client_id:
            env_vars["GOOGLE_CLIENT_ID"] = self.google_client_id

        if service_arn:
            self.print_info("Service exists, updating...")
            # Note: Update is complex with AWS CLI, keeping it simple here
            self.print_warning("Service update via CLI is limited. Consider using AWS Console for updates.")
            self.print_info(f"Service ARN: {service_arn}")
        else:
            self.print_info("Creating new service...")

            # Create service configuration
            config = {
                "ServiceName": self.service_name,
                "SourceConfiguration": {
                    "ImageRepository": {
                        "ImageIdentifier": f"{self.ecr_uri}:latest",
                        "ImageConfiguration": {
                            "Port": self.port,
                            "RuntimeEnvironmentVariables": env_vars
                        },
                        "ImageRepositoryType": "ECR"
                    },
                    "AuthenticationConfiguration": {
                        "AccessRoleArn": self.access_role_arn
                    },
                    "AutoDeploymentsEnabled": False
                },
                "InstanceConfiguration": {
                    "Cpu": self.cpu,
                    "Memory": self.memory,
                    "InstanceRoleArn": self.instance_role_arn
                },
                "HealthCheckConfiguration": {
                    "Protocol": "HTTP",
                    "Path": "/health",
                    "Interval": 30,
                    "Timeout": 10,
                    "HealthyThreshold": 1,
                    "UnhealthyThreshold": 3
                }
            }

            # Write config to temp file
            config_file = Path("/tmp/apprunner-config.json")
            config_file.write_text(json.dumps(config, indent=2))

            result = self.run_command([
                "aws", "apprunner", "create-service",
                "--cli-input-json", f"file://{config_file}",
                "--region", self.region,
                "--query", "Service.ServiceArn",
                "--output", "text"
            ])

            service_arn = result.stdout.strip()
            self.print_success("Service creation initiated")

        self.print_info(f"Service ARN: {service_arn}")

        # Wait for deployment
        self.print_info("Waiting for deployment to complete (this may take 3-5 minutes)...")

        # Poll service status
        max_wait = 300  # 5 minutes
        start_time = time.time()

        while time.time() - start_time < max_wait:
            result = self.run_command([
                "aws", "apprunner", "describe-service",
                "--service-arn", service_arn,
                "--region", self.region,
                "--query", "Service.Status",
                "--output", "text"
            ])

            status = result.stdout.strip()

            if status == "RUNNING":
                break
            elif status in ["CREATE_FAILED", "DELETE_FAILED"]:
                self.print_error(f"Deployment failed with status: {status}")
                sys.exit(1)

            time.sleep(10)
            print(".", end="", flush=True)

        print()  # New line after dots

        # Get service details
        result = self.run_command([
            "aws", "apprunner", "describe-service",
            "--service-arn", service_arn,
            "--region", self.region,
            "--query", "Service.ServiceUrl",
            "--output", "text"
        ])
        service_url = result.stdout.strip()

        result = self.run_command([
            "aws", "apprunner", "describe-service",
            "--service-arn", service_arn,
            "--region", self.region,
            "--query", "Service.Status",
            "--output", "text"
        ])
        service_status = result.stdout.strip()

        self.print_success("Deployment complete!")

        # Print summary
        print()
        print(f"{Colors.GREEN}╔════════════════════════════════════════════════════════════════╗{Colors.NC}")
        print(f"{Colors.GREEN}║                   Deployment Successful!                       ║{Colors.NC}")
        print(f"{Colors.GREEN}╚════════════════════════════════════════════════════════════════╝{Colors.NC}")
        print()
        print(f"{Colors.BLUE}Service URL:{Colors.NC}       https://{service_url}")
        print(f"{Colors.BLUE}API Docs:{Colors.NC}          https://{service_url}/docs")
        print(f"{Colors.BLUE}Health Check:{Colors.NC}      https://{service_url}/health")
        print(f"{Colors.BLUE}Status:{Colors.NC}            {service_status}")
        print(f"{Colors.BLUE}Region:{Colors.NC}            {self.region}")
        print()
        print(f"{Colors.BLUE}Admin Credentials:{Colors.NC}")
        print(f"  Username: {self.admin_username}")
        print(f"  Password: {self.admin_password}")
        print(f"  Email:    {self.admin_email}")
        print()
        print(f"{Colors.YELLOW}⚠  Save these credentials! Password will not be shown again.{Colors.NC}")
        print()
        print(f"{Colors.BLUE}Next steps:{Colors.NC}")
        print(f"  1. Test API: curl https://{service_url}/health")
        print(f"  2. View in console: https://{self.region}.console.aws.amazon.com/apprunner/")
        print(f"  3. Configure custom domain in App Runner console")
        print()

    def deploy(self):
        """Run the complete deployment process."""
        print(f"{Colors.BLUE}")
        print("""
    ____        __  ____  __
   / __ \__  __/ /_/ __ \/ /___ ___________
  / /_/ / / / / __/ /_/ / / __ `/ ___/ _ \\
 / ____/ /_/ / /_/ ____/ / /_/ / /__/  __/
/_/    \__,_/\__/_/   /_/\__,_/\___/\___/

AWS App Runner Deployment Script
        """)
        print(f"{Colors.NC}")

        try:
            self.check_prerequisites()
            self.gather_configuration()
            self.create_s3_bucket()
            self.create_ecr_repository()
            self.build_and_push_image()
            self.create_app_runner_roles()
            self.deploy_to_app_runner()

            self.print_success("All done!")
        except KeyboardInterrupt:
            print()
            self.print_warning("Deployment interrupted by user")
            sys.exit(1)
        except Exception as e:
            self.print_error(f"Deployment failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Deploy PutPlace to AWS App Runner (default: eu-west-1 Ireland)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive deployment to Ireland (default)
  python deploy/app_runner_deploy.py

  # Deploy to specific region
  python deploy/app_runner_deploy.py --region us-east-1

  # Non-interactive deployment
  export MONGODB_URL="mongodb+srv://user:pass@cluster.mongodb.net/putplace"
  export S3_BUCKET_NAME="putplace-files"
  python deploy/app_runner_deploy.py --non-interactive
        """
    )

    parser.add_argument(
        "--region",
        default="eu-west-1",
        help="AWS region (default: eu-west-1 - Ireland)"
    )
    parser.add_argument(
        "--service-name",
        default="putplace-api",
        help="App Runner service name (default: putplace-api)"
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Run without prompts (use environment variables)"
    )

    args = parser.parse_args()

    deployer = AppRunnerDeployer(
        region=args.region,
        service_name=args.service_name,
        interactive=not args.non_interactive
    )

    deployer.deploy()


if __name__ == "__main__":
    main()
