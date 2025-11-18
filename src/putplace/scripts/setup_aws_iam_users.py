#!/usr/bin/env python3
"""
Setup IAM users for PutPlace with S3 and SES access.

Creates three environments: dev, test, prod
Each with its own IAM user, S3 bucket, and limited permissions.

Prerequisites:
    - AWS CLI configured with admin permissions
    - boto3 installed

Usage:
    python -m putplace.scripts.setup_aws_iam_users
    python -m putplace.scripts.setup_aws_iam_users --region us-east-1
    python -m putplace.scripts.setup_aws_iam_users --skip-buckets  # If buckets exist
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    print("Error: boto3 not installed. Install with: pip install boto3")
    sys.exit(1)


class AWSIAMSetup:
    """Manages AWS IAM user setup for PutPlace environments."""

    def __init__(self, region: str = "eu-west-1", project_name: str = "putplace"):
        self.region = region
        self.project_name = project_name
        self.iam = boto3.client('iam')
        self.s3 = boto3.client('s3', region_name=region)
        self.environments = ['dev', 'test', 'prod']
        self.credentials = {}

    def create_s3_bucket(self, bucket_name: str) -> bool:
        """Create S3 bucket if it doesn't exist."""
        try:
            # Check if bucket exists
            try:
                self.s3.head_bucket(Bucket=bucket_name)
                print(f"  ✓ Bucket '{bucket_name}' already exists")
                return True
            except ClientError:
                pass

            # Create bucket
            print(f"  → Creating bucket '{bucket_name}'...")

            if self.region == 'us-east-1':
                # us-east-1 doesn't need LocationConstraint
                self.s3.create_bucket(Bucket=bucket_name)
            else:
                self.s3.create_bucket(
                    Bucket=bucket_name,
                    CreateBucketConfiguration={'LocationConstraint': self.region}
                )

            # Enable versioning
            self.s3.put_bucket_versioning(
                Bucket=bucket_name,
                VersioningConfiguration={'Status': 'Enabled'}
            )

            # Block public access
            self.s3.put_public_access_block(
                Bucket=bucket_name,
                PublicAccessBlockConfiguration={
                    'BlockPublicAcls': True,
                    'IgnorePublicAcls': True,
                    'BlockPublicPolicy': True,
                    'RestrictPublicBuckets': True
                }
            )

            print(f"  ✓ Bucket '{bucket_name}' created with versioning and public access blocked")
            return True

        except ClientError as e:
            print(f"  ✗ Failed to create bucket '{bucket_name}': {e}")
            return False

    def create_iam_policy(self, env: str, bucket_name: str) -> Optional[str]:
        """Create IAM policy for environment."""
        policy_name = f"{self.project_name}-{env}-policy"

        policy_document = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "S3BucketAccess",
                    "Effect": "Allow",
                    "Action": [
                        "s3:ListBucket",
                        "s3:GetBucketLocation"
                    ],
                    "Resource": f"arn:aws:s3:::{bucket_name}"
                },
                {
                    "Sid": "S3ObjectAccess",
                    "Effect": "Allow",
                    "Action": [
                        "s3:PutObject",
                        "s3:GetObject",
                        "s3:DeleteObject",
                        "s3:ListMultipartUploadParts",
                        "s3:AbortMultipartUpload"
                    ],
                    "Resource": f"arn:aws:s3:::{bucket_name}/*"
                },
                {
                    "Sid": "SESEmailAccess",
                    "Effect": "Allow",
                    "Action": [
                        "ses:SendEmail",
                        "ses:SendRawEmail",
                        "ses:GetSendQuota"
                    ],
                    "Resource": "*"
                }
            ]
        }

        try:
            # Check if policy exists
            try:
                account_id = boto3.client('sts').get_caller_identity()['Account']
                policy_arn = f"arn:aws:iam::{account_id}:policy/{policy_name}"
                self.iam.get_policy(PolicyArn=policy_arn)
                print(f"  ✓ Policy '{policy_name}' already exists")
                return policy_arn
            except ClientError:
                pass

            # Create policy
            print(f"  → Creating policy '{policy_name}'...")
            response = self.iam.create_policy(
                PolicyName=policy_name,
                PolicyDocument=json.dumps(policy_document),
                Description=f"S3 and SES access for PutPlace {env} environment"
            )
            policy_arn = response['Policy']['Arn']
            print(f"  ✓ Policy created: {policy_arn}")
            return policy_arn

        except ClientError as e:
            print(f"  ✗ Failed to create policy '{policy_name}': {e}")
            return None

    def create_iam_user(self, env: str) -> bool:
        """Create IAM user for environment."""
        user_name = f"{self.project_name}-{env}"

        try:
            # Check if user exists
            try:
                self.iam.get_user(UserName=user_name)
                print(f"  ✓ User '{user_name}' already exists")
                return True
            except ClientError:
                pass

            # Create user
            print(f"  → Creating user '{user_name}'...")
            self.iam.create_user(
                UserName=user_name,
                Tags=[
                    {'Key': 'Project', 'Value': self.project_name},
                    {'Key': 'Environment', 'Value': env},
                    {'Key': 'ManagedBy', 'Value': 'setup_aws_iam_users.py'}
                ]
            )
            print(f"  ✓ User '{user_name}' created")
            return True

        except ClientError as e:
            print(f"  ✗ Failed to create user '{user_name}': {e}")
            return False

    def attach_policy_to_user(self, env: str, policy_arn: str) -> bool:
        """Attach policy to IAM user."""
        user_name = f"{self.project_name}-{env}"

        try:
            print(f"  → Attaching policy to user '{user_name}'...")
            self.iam.attach_user_policy(
                UserName=user_name,
                PolicyArn=policy_arn
            )
            print(f"  ✓ Policy attached to '{user_name}'")
            return True

        except ClientError as e:
            print(f"  ✗ Failed to attach policy to '{user_name}': {e}")
            return False

    def create_access_key(self, env: str) -> Optional[dict]:
        """Create access key for IAM user."""
        user_name = f"{self.project_name}-{env}"

        try:
            # Delete old keys if they exist (max 2 keys per user)
            print(f"  → Checking existing access keys for '{user_name}'...")
            response = self.iam.list_access_keys(UserName=user_name)

            if len(response['AccessKeyMetadata']) >= 2:
                print(f"  ⚠ User has 2 access keys (max). Deleting oldest...")
                oldest_key = sorted(
                    response['AccessKeyMetadata'],
                    key=lambda x: x['CreateDate']
                )[0]
                self.iam.delete_access_key(
                    UserName=user_name,
                    AccessKeyId=oldest_key['AccessKeyId']
                )
                print(f"  ✓ Deleted old key: {oldest_key['AccessKeyId']}")

            # Create new access key
            print(f"  → Creating access key for '{user_name}'...")
            response = self.iam.create_access_key(UserName=user_name)
            access_key = response['AccessKey']

            credentials = {
                'access_key_id': access_key['AccessKeyId'],
                'secret_access_key': access_key['SecretAccessKey'],
                'user_name': user_name,
                'environment': env
            }

            print(f"  ✓ Access key created: {access_key['AccessKeyId']}")
            return credentials

        except ClientError as e:
            print(f"  ✗ Failed to create access key for '{user_name}': {e}")
            return None

    def save_credentials(self, output_dir: Path) -> None:
        """Save credentials to files."""
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save individual .env files for each environment
        for env, creds in self.credentials.items():
            env_file = output_dir / f".env.{env}"
            bucket_name = f"{self.project_name}-{env}"

            content = f"""# PutPlace {env.upper()} Environment - AWS Credentials
# Generated by setup_aws_iam_users.py

# AWS Credentials
AWS_ACCESS_KEY_ID={creds['access_key_id']}
AWS_SECRET_ACCESS_KEY={creds['secret_access_key']}

# S3 Configuration
STORAGE_BACKEND=s3
S3_BUCKET_NAME={bucket_name}
S3_REGION_NAME={self.region}
S3_PREFIX=files/

# MongoDB (update as needed)
MONGODB_URL=mongodb://localhost:27017
MONGODB_DATABASE=putplace_{env}
MONGODB_COLLECTION=file_metadata

# API Configuration
API_TITLE=PutPlace API ({env.upper()})
API_VERSION=0.7.0
API_DESCRIPTION=File metadata storage service - {env.upper()}
ALLOW_REGISTRATION={"true" if env == "dev" else "false"}
"""

            env_file.write_text(content)
            env_file.chmod(0o600)
            print(f"  ✓ Saved: {env_file}")

        # Save AWS credentials file format
        aws_creds_file = output_dir / "aws_credentials"
        aws_config_file = output_dir / "aws_config"

        creds_content = ""
        config_content = ""

        for env, creds in self.credentials.items():
            profile_name = f"{self.project_name}-{env}"
            creds_content += f"""[{profile_name}]
aws_access_key_id = {creds['access_key_id']}
aws_secret_access_key = {creds['secret_access_key']}

"""
            config_content += f"""[profile {profile_name}]
region = {self.region}
output = json

"""

        aws_creds_file.write_text(creds_content)
        aws_creds_file.chmod(0o600)
        print(f"  ✓ Saved: {aws_creds_file}")

        aws_config_file.write_text(config_content)
        aws_config_file.chmod(0o600)
        print(f"  ✓ Saved: {aws_config_file}")

        # Save summary JSON
        summary_file = output_dir / "setup_summary.json"
        summary = {
            'project': self.project_name,
            'region': self.region,
            'environments': {}
        }

        for env, creds in self.credentials.items():
            summary['environments'][env] = {
                'user_name': creds['user_name'],
                'access_key_id': creds['access_key_id'],
                'bucket_name': f"{self.project_name}-{env}",
                'profile_name': f"{self.project_name}-{env}"
            }

        summary_file.write_text(json.dumps(summary, indent=2))
        print(f"  ✓ Saved: {summary_file}")

    def setup(self, skip_buckets: bool = False) -> bool:
        """Run complete setup for all environments."""
        print(f"\n{'='*60}")
        print(f"Setting up AWS IAM for PutPlace")
        print(f"{'='*60}")
        print(f"Project: {self.project_name}")
        print(f"Region: {self.region}")
        print(f"Environments: {', '.join(self.environments)}\n")

        try:
            for env in self.environments:
                print(f"\n{'='*60}")
                print(f"Environment: {env.upper()}")
                print(f"{'='*60}\n")

                bucket_name = f"{self.project_name}-{env}"

                # Step 1: Create S3 bucket
                if not skip_buckets:
                    if not self.create_s3_bucket(bucket_name):
                        print(f"⚠ Continuing despite bucket creation failure...")

                # Step 2: Create IAM policy
                policy_arn = self.create_iam_policy(env, bucket_name)
                if not policy_arn:
                    print(f"✗ Failed to create policy for {env}")
                    return False

                # Step 3: Create IAM user
                if not self.create_iam_user(env):
                    print(f"✗ Failed to create user for {env}")
                    return False

                # Step 4: Attach policy to user
                if not self.attach_policy_to_user(env, policy_arn):
                    print(f"✗ Failed to attach policy for {env}")
                    return False

                # Step 5: Create access key
                credentials = self.create_access_key(env)
                if not credentials:
                    print(f"✗ Failed to create access key for {env}")
                    return False

                self.credentials[env] = credentials

            # Step 6: Save credentials
            print(f"\n{'='*60}")
            print(f"Saving Credentials")
            print(f"{'='*60}\n")

            output_dir = Path.cwd() / "aws_credentials_output"
            self.save_credentials(output_dir)

            # Success summary
            print(f"\n{'='*60}")
            print(f"Setup Complete!")
            print(f"{'='*60}\n")

            print("Created resources:")
            for env in self.environments:
                print(f"\n{env.upper()}:")
                print(f"  User: {self.project_name}-{env}")
                print(f"  Bucket: {self.project_name}-{env}")
                print(f"  Profile: {self.project_name}-{env}")

            print(f"\nCredentials saved to: {output_dir}/")
            print("\nNext steps:")
            print(f"1. Copy .env.{self.environments[0]} to your droplet's /opt/putplace/putplace/.env")
            print("2. Or merge aws_credentials into ~/.aws/credentials")
            print("3. Restart your PutPlace service")
            print("\nSecurity:")
            print(f"  chmod 600 {output_dir}/.env.*")
            print("  Never commit these files to git!")
            print()

            return True

        except Exception as e:
            print(f"\n✗ Setup failed: {e}")
            return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Setup AWS IAM users for PutPlace environments",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--region',
        default='eu-west-1',
        help='AWS region (default: eu-west-1)'
    )
    parser.add_argument(
        '--project-name',
        default='putplace',
        help='Project name for resource naming (default: putplace)'
    )
    parser.add_argument(
        '--skip-buckets',
        action='store_true',
        help='Skip S3 bucket creation (if buckets already exist)'
    )

    args = parser.parse_args()

    setup = AWSIAMSetup(region=args.region, project_name=args.project_name)

    if setup.setup(skip_buckets=args.skip_buckets):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
