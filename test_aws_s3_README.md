# AWS S3 Test Script

Quick test program to verify AWS S3 bucket creation and file upload functionality.

## What It Does

1. Creates a uniquely named S3 bucket (using timestamp)
2. Uploads a test file to the bucket
3. Verifies the file exists
4. Downloads and verifies the content matches (SHA256 hash)
5. Cleans up by deleting the file and bucket (optional)

## Requirements

Install boto3:

```bash
pip install boto3
```

Or if using the project's S3 optional dependencies:

```bash
uv pip install -e ".[s3]"
```

## AWS Credentials

Configure AWS credentials using one of these methods:

### Option 1: AWS CLI (Recommended)
```bash
aws configure
```

### Option 2: Environment Variables
```bash
export AWS_ACCESS_KEY_ID=your-access-key
export AWS_SECRET_ACCESS_KEY=your-secret-key
export AWS_DEFAULT_REGION=us-east-1
```

### Option 3: AWS Profile
```bash
export AWS_PROFILE=your-profile-name
```

### Option 4: IAM Role
If running on EC2/ECS/Lambda, IAM roles are automatically detected.

## Usage

### Basic Test (auto-cleanup)
```bash
python test_aws_s3.py
```

This will:
- Create a bucket with name like `putplace-test-20251016-143022`
- Upload a test file
- Verify the upload
- Delete the file and bucket

### Keep Bucket for Inspection
```bash
python test_aws_s3.py --keep-bucket
```

### Specify AWS Region
```bash
python test_aws_s3.py --region us-west-2
```

## Example Output

```
======================================================================
AWS S3 Test Program
======================================================================

[1/7] Initializing S3 client (region: us-east-1)...
✓ Successfully connected to AWS S3

[2/7] Generated unique bucket name: putplace-test-20251016-143022

[3/7] Created test file: test-file-abc12345.txt
    Content: Hello from PutPlace S3 test!
    Size: 30 bytes
    SHA256: abc123...

[4/7] Creating S3 bucket: putplace-test-20251016-143022...
✓ Bucket created successfully

[5/7] Uploading file to bucket...
✓ File uploaded successfully: s3://putplace-test-20251016-143022/test-file-abc12345.txt

[6/7] Verifying file exists...
✓ File exists!
    ETag: "abc123..."
    Size: 30 bytes
    Last Modified: 2025-10-16 14:30:25+00:00

[7/7] Downloading and verifying content...
✓ Content verified successfully!
    Original SHA256:    abc123...
    Downloaded SHA256:  abc123...
    Content matches: Hello from PutPlace S3 test!

======================================================================
SUCCESS! All tests passed!
======================================================================

======================================================================
Cleanup
======================================================================

Deleting file: test-file-abc12345.txt...
✓ File deleted

Deleting bucket: putplace-test-20251016-143022...
✓ Bucket deleted

✓ Cleanup complete!
```

## Troubleshooting

### Error: No AWS credentials found
Configure credentials using one of the methods above.

### Error: Access Denied
Ensure your AWS credentials have permissions for:
- `s3:CreateBucket`
- `s3:PutObject`
- `s3:GetObject`
- `s3:DeleteObject`
- `s3:DeleteBucket`
- `s3:ListBucket`

### Error: Bucket name already exists
The script generates unique bucket names, but if you get this error, try running again (it includes timestamp with seconds).

### Manual Cleanup
If the script fails and doesn't clean up:

```bash
# Delete file
aws s3 rm s3://putplace-test-YYYYMMDD-HHMMSS/test-file-*.txt

# Delete bucket
aws s3 rb s3://putplace-test-YYYYMMDD-HHMMSS
```

## Integration with PutPlace

This test script validates the same AWS S3 operations that PutPlace uses in its S3 storage backend (`src/putplace/storage.py`). If this test passes, your AWS credentials are properly configured for PutPlace's S3 storage feature.
