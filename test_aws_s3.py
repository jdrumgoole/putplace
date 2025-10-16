#!/usr/bin/env python
"""Quick test program to verify AWS S3 bucket creation and file upload.

This script:
1. Creates a uniquely named S3 bucket
2. Uploads a test file to the bucket
3. Verifies the file exists
4. Downloads and verifies the content
5. Cleans up (optional)

Requirements:
    pip install boto3

Usage:
    python test_aws_s3.py [--keep-bucket]

Environment variables:
    AWS_PROFILE: AWS profile to use (optional)
    AWS_ACCESS_KEY_ID: AWS access key (optional)
    AWS_SECRET_ACCESS_KEY: AWS secret key (optional)
    AWS_DEFAULT_REGION: AWS region (default: us-east-1)
"""

import argparse
import hashlib
import sys
import time
from datetime import datetime

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
except ImportError:
    print("Error: boto3 not installed. Install it with: pip install boto3")
    sys.exit(1)


def generate_unique_bucket_name() -> str:
    """Generate a unique bucket name using timestamp and hash."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    # S3 bucket names must be lowercase and can't contain underscores
    bucket_name = f"putplace-test-{timestamp}"
    return bucket_name


def create_test_file(content: str = "Hello from PutPlace S3 test!") -> tuple[str, bytes]:
    """Create test file content and return filename and bytes."""
    content_bytes = content.encode('utf-8')
    sha256_hash = hashlib.sha256(content_bytes).hexdigest()
    return f"test-file-{sha256_hash[:8]}.txt", content_bytes


def main():
    parser = argparse.ArgumentParser(description="Test AWS S3 bucket creation and file upload")
    parser.add_argument(
        "--keep-bucket",
        action="store_true",
        help="Keep the bucket after test (don't clean up)"
    )
    parser.add_argument(
        "--region",
        default="us-east-1",
        help="AWS region (default: us-east-1)"
    )
    args = parser.parse_args()

    print("=" * 70)
    print("AWS S3 Test Program")
    print("=" * 70)

    # Initialize S3 client
    try:
        print(f"\n[1/7] Initializing S3 client (region: {args.region})...")
        s3_client = boto3.client('s3', region_name=args.region)

        # Test credentials by listing buckets
        s3_client.list_buckets()
        print("✓ Successfully connected to AWS S3")

    except NoCredentialsError:
        print("✗ Error: No AWS credentials found!")
        print("\nPlease configure AWS credentials using one of these methods:")
        print("  1. AWS CLI: aws configure")
        print("  2. Environment variables: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY")
        print("  3. AWS credentials file: ~/.aws/credentials")
        print("  4. IAM role (if running on EC2/ECS/Lambda)")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Error connecting to AWS: {e}")
        sys.exit(1)

    # Generate unique bucket name
    bucket_name = generate_unique_bucket_name()
    print(f"\n[2/7] Generated unique bucket name: {bucket_name}")

    # Create test file
    filename, content_bytes = create_test_file()
    original_sha256 = hashlib.sha256(content_bytes).hexdigest()
    print(f"\n[3/7] Created test file: {filename}")
    print(f"    Content: {content_bytes.decode('utf-8')}")
    print(f"    Size: {len(content_bytes)} bytes")
    print(f"    SHA256: {original_sha256}")

    bucket_created = False
    file_uploaded = False

    try:
        # Create bucket
        print(f"\n[4/7] Creating S3 bucket: {bucket_name}...")

        # Note: us-east-1 doesn't need LocationConstraint
        if args.region == 'us-east-1':
            s3_client.create_bucket(Bucket=bucket_name)
        else:
            s3_client.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={'LocationConstraint': args.region}
            )

        bucket_created = True
        print(f"✓ Bucket created successfully")

        # Wait a moment for bucket to be ready
        time.sleep(2)

        # Upload file
        print(f"\n[5/7] Uploading file to bucket...")
        s3_client.put_object(
            Bucket=bucket_name,
            Key=filename,
            Body=content_bytes,
            ContentType='text/plain'
        )
        file_uploaded = True
        print(f"✓ File uploaded successfully: s3://{bucket_name}/{filename}")

        # Verify file exists
        print(f"\n[6/7] Verifying file exists...")
        response = s3_client.head_object(Bucket=bucket_name, Key=filename)
        print(f"✓ File exists!")
        print(f"    ETag: {response['ETag']}")
        print(f"    Size: {response['ContentLength']} bytes")
        print(f"    Last Modified: {response['LastModified']}")

        # Download and verify content
        print(f"\n[7/7] Downloading and verifying content...")
        response = s3_client.get_object(Bucket=bucket_name, Key=filename)
        downloaded_content = response['Body'].read()
        downloaded_sha256 = hashlib.sha256(downloaded_content).hexdigest()

        if downloaded_sha256 == original_sha256:
            print(f"✓ Content verified successfully!")
            print(f"    Original SHA256:    {original_sha256}")
            print(f"    Downloaded SHA256:  {downloaded_sha256}")
            print(f"    Content matches: {downloaded_content.decode('utf-8')}")
        else:
            print(f"✗ Content mismatch!")
            print(f"    Original SHA256:    {original_sha256}")
            print(f"    Downloaded SHA256:  {downloaded_sha256}")
            raise ValueError("Downloaded content does not match original!")

        print("\n" + "=" * 70)
        print("SUCCESS! All tests passed!")
        print("=" * 70)

    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_msg = e.response['Error']['Message']
        print(f"\n✗ AWS Error ({error_code}): {error_msg}")
        sys.exit(1)

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        # Cleanup
        if not args.keep_bucket:
            print("\n" + "=" * 70)
            print("Cleanup")
            print("=" * 70)

            try:
                if file_uploaded:
                    print(f"\nDeleting file: {filename}...")
                    s3_client.delete_object(Bucket=bucket_name, Key=filename)
                    print("✓ File deleted")

                if bucket_created:
                    print(f"\nDeleting bucket: {bucket_name}...")
                    s3_client.delete_bucket(Bucket=bucket_name)
                    print("✓ Bucket deleted")

                print("\n✓ Cleanup complete!")

            except Exception as e:
                print(f"\n✗ Cleanup error: {e}")
                print(f"\nManual cleanup required:")
                print(f"  Bucket: {bucket_name}")
                print(f"  File: {filename}")
                print(f"\nTo delete manually:")
                print(f"  aws s3 rm s3://{bucket_name}/{filename}")
                print(f"  aws s3 rb s3://{bucket_name}")

        else:
            print("\n" + "=" * 70)
            print("Bucket Retained (--keep-bucket flag used)")
            print("=" * 70)
            print(f"\nBucket: {bucket_name}")
            print(f"File: s3://{bucket_name}/{filename}")
            print(f"\nTo delete manually:")
            print(f"  aws s3 rm s3://{bucket_name}/{filename}")
            print(f"  aws s3 rb s3://{bucket_name}")


if __name__ == "__main__":
    main()
