# Storage Backends

PutPlace supports multiple storage backends for file content. File metadata is always stored in MongoDB, while actual file content can be stored in different backends.

## Overview

### Available Backends

- **Local Filesystem** - Store files on local disk
- **AWS S3** - Store files in Amazon S3

### Storage Architecture

```
┌──────────────┐
│   Client     │
└──────┬───────┘
       │
       │ 1. Send metadata
       ▼
┌──────────────┐     ┌──────────────┐
│  PutPlace    │────▶│   MongoDB    │
│     API      │     │  (metadata)  │
└──────┬───────┘     └──────────────┘
       │
       │ 2. Upload content
       ▼
┌──────────────┐
│   Storage    │
│   Backend    │
└──────┬───────┘
       │
   ┌───┴────┐
   │        │
   ▼        ▼
┌──────┐ ┌────┐
│Local │ │ S3 │
└──────┘ └────┘
```

## Local Filesystem Storage

### Overview

Store files on local disk. Best for:
- Development and testing
- Single-server deployments
- Fast local access
- No cloud dependencies

### Configuration

**Using ppserver.toml (recommended):**
```toml
[storage]
backend = "local"
path = "/var/putplace/files"
```

**Environment variables:**
```bash
STORAGE_BACKEND=local
STORAGE_PATH=/var/putplace/files
```

**In .env file (legacy):**
```bash
# Storage Backend
STORAGE_BACKEND=local
STORAGE_PATH=/var/putplace/files
```

### Directory Structure

Files are distributed across 256 subdirectories based on the first two characters of their SHA256 hash:

```
/var/putplace/files/
├── 00/
│   ├── 00a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6...
│   └── 00f9e8d7c6b5a4938271605948372615049382716050483726...
├── 01/
│   └── 01b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5...
├── 02/
│   └── ...
├── ...
└── ff/
    └── ffa1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4...
```

**Why 256 subdirectories?**
- Prevents too many files in single directory
- Better filesystem performance
- Evenly distributes files (SHA256 is uniformly random)

### Setup

#### 1. Create Storage Directory

```bash
# Create directory
sudo mkdir -p /var/putplace/files

# Set ownership
sudo chown $USER:$USER /var/putplace/files

# Set permissions
chmod 755 /var/putplace/files
```

#### 2. Verify Permissions

```bash
# Test write access
touch /var/putplace/files/test
rm /var/putplace/files/test

# Check permissions
ls -ld /var/putplace/files
# Should show: drwxr-xr-x
```

#### 3. Configure PutPlace

```bash
# In .env file
STORAGE_BACKEND=local
STORAGE_PATH=/var/putplace/files
```

#### 4. Start Server

```bash
uvicorn putplace.main:app
```

You should see:
```
INFO: Initialized local storage backend at /var/putplace/files
```

### Disk Space Management

#### Check Disk Usage

```bash
# Total storage used
du -sh /var/putplace/files

# Per-directory usage
du -h --max-depth=1 /var/putplace/files | sort -hr

# Number of files
find /var/putplace/files -type f | wc -l
```

#### Cleanup Old Files

```bash
# Find files older than 90 days
find /var/putplace/files -type f -mtime +90

# Delete files older than 90 days (BE CAREFUL!)
find /var/putplace/files -type f -mtime +90 -delete
```

#### Monitor Disk Space

Add to cron for daily monitoring:

```bash
#!/bin/bash
# /usr/local/bin/check-putplace-disk.sh

THRESHOLD=80  # Alert at 80% usage
USAGE=$(df -h /var/putplace/files | tail -1 | awk '{print $5}' | sed 's/%//')

if [ "$USAGE" -gt "$THRESHOLD" ]; then
    echo "WARNING: PutPlace storage at ${USAGE}% usage"
    # Send alert (e.g., email, Slack, etc.)
fi
```

### Performance Considerations

**Pros:**
- Very fast (no network latency)
- Simple setup
- No external dependencies
- No usage costs

**Cons:**
- Limited to single server
- No built-in replication
- Manual backup required
- Disk space limited

**Optimization tips:**
1. Use SSD for storage path
2. Monitor disk I/O
3. Consider RAID for redundancy
4. Regular backups essential

## AWS S3 Storage

### Overview

Store files in Amazon S3. Best for:
- Multi-server deployments
- Cloud-native infrastructure
- Scalability requirements
- High durability needs (99.999999999%)

### Configuration

**Using ppserver.toml (recommended):**
```toml
[storage]
backend = "s3"
s3_bucket_name = "my-putplace-bucket"
s3_region_name = "us-east-1"
s3_prefix = "files/"

[aws]
# Use IAM role (recommended) or AWS profile
profile = "putplace"
```

**Environment variables:**
```bash
STORAGE_BACKEND=s3
S3_BUCKET_NAME=my-putplace-bucket
S3_REGION_NAME=us-east-1
S3_PREFIX=files/
S3_STORAGE_CLASS=STANDARD

# Optional: AWS credentials (recommended to use IAM roles instead)
AWS_PROFILE=putplace
# OR
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

**In .env file (legacy):**
```bash
# Storage Backend
STORAGE_BACKEND=s3
S3_BUCKET_NAME=my-putplace-bucket
S3_REGION_NAME=us-east-1
S3_PREFIX=files/
S3_STORAGE_CLASS=STANDARD

# AWS Credentials (use IAM role if on EC2/ECS)
AWS_PROFILE=putplace
```

### S3 Key Structure

Files are stored with keys following the same distribution pattern:

```
s3://my-putplace-bucket/
└── files/
    ├── 00/
    │   ├── 00a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6...
    │   └── 00f9e8d7c6b5a4938271605948372615049382716050483726...
    ├── 01/
    │   └── 01b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5...
    └── ...
```

**Key format:** `{prefix}{sha256[:2]}/{sha256}`

### Setup

#### 1. Create S3 Bucket

```bash
# Create bucket
aws s3 mb s3://my-putplace-bucket --region us-east-1

# Enable versioning (optional, for recovery)
aws s3api put-bucket-versioning \
  --bucket my-putplace-bucket \
  --versioning-configuration Status=Enabled

# Enable encryption
aws s3api put-bucket-encryption \
  --bucket my-putplace-bucket \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      }
    }]
  }'
```

#### 2. Configure IAM Policy

**For EC2/ECS (using IAM role):**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::my-putplace-bucket/files/*"
    },
    {
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::my-putplace-bucket",
      "Condition": {
        "StringLike": {
          "s3:prefix": "files/*"
        }
      }
    }
  ]
}
```

**For IAM user:**

Same policy, then attach to user or create access keys.

#### 3. Configure Credentials

**Option A: IAM Role (Recommended for EC2/ECS)**

No configuration needed! PutPlace automatically uses instance metadata:

```bash
# In .env - no AWS credentials needed
STORAGE_BACKEND=s3
S3_BUCKET_NAME=my-putplace-bucket
S3_REGION_NAME=us-east-1
```

**Option B: AWS Profile**

```bash
# Configure AWS CLI
aws configure --profile putplace
# Enter access key, secret key, region

# In .env
STORAGE_BACKEND=s3
S3_BUCKET_NAME=my-putplace-bucket
S3_REGION_NAME=us-east-1
AWS_PROFILE=putplace
```

**Option C: Environment Variables**

```bash
# In .env
STORAGE_BACKEND=s3
S3_BUCKET_NAME=my-putplace-bucket
S3_REGION_NAME=us-east-1
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

See [SECURITY.md](../SECURITY.md) for detailed credential setup.

#### 4. Test Connection

```bash
# Test S3 access
aws s3 ls s3://my-putplace-bucket --profile putplace

# Test upload
echo "test" > /tmp/test.txt
aws s3 cp /tmp/test.txt s3://my-putplace-bucket/test.txt --profile putplace

# Test download
aws s3 cp s3://my-putplace-bucket/test.txt /tmp/test-download.txt --profile putplace

# Cleanup
aws s3 rm s3://my-putplace-bucket/test.txt --profile putplace
rm /tmp/test.txt /tmp/test-download.txt
```

#### 5. Start Server

```bash
uvicorn putplace.main:app
```

You should see:
```
INFO: Initialized S3 storage backend: bucket=my-putplace-bucket, region=us-east-1
```

### Storage Classes

S3 offers different storage classes for cost optimization:

#### STANDARD (Default)

```bash
S3_STORAGE_CLASS=STANDARD
```

- **Use case:** Frequently accessed files
- **Durability:** 99.999999999% (11 9's)
- **Availability:** 99.99%
- **Cost:** $0.023/GB/month (us-east-1)

#### STANDARD_IA (Infrequent Access)

```bash
S3_STORAGE_CLASS=STANDARD_IA
```

- **Use case:** Accessed less than monthly
- **Durability:** 99.999999999%
- **Availability:** 99.9%
- **Cost:** $0.0125/GB/month + retrieval fees

#### INTELLIGENT_TIERING

```bash
S3_STORAGE_CLASS=INTELLIGENT_TIERING
```

- **Use case:** Unknown or changing access patterns
- **Automatically moves between tiers**
- **Cost:** $0.023/GB/month + monitoring fee

#### GLACIER

```bash
S3_STORAGE_CLASS=GLACIER
```

- **Use case:** Archival, rarely accessed
- **Retrieval time:** Minutes to hours
- **Cost:** $0.004/GB/month + retrieval fees

### Lifecycle Policies

Automatically transition files to cheaper storage classes:

```bash
# Create lifecycle policy
aws s3api put-bucket-lifecycle-configuration \
  --bucket my-putplace-bucket \
  --lifecycle-configuration '{
    "Rules": [{
      "Id": "TransitionToIA",
      "Status": "Enabled",
      "Prefix": "files/",
      "Transitions": [
        {
          "Days": 30,
          "StorageClass": "STANDARD_IA"
        },
        {
          "Days": 90,
          "StorageClass": "GLACIER"
        }
      ]
    }]
  }'
```

**Effect:**
- Files accessed frequently: STANDARD
- After 30 days: STANDARD_IA
- After 90 days: GLACIER

### Cost Estimation

**Example: 1TB storage, 100GB monthly uploads**

**STANDARD:**
- Storage: 1000 GB × $0.023 = $23/month
- PUT requests: 100,000 × $0.005/1000 = $0.50/month
- **Total: ~$23.50/month**

**STANDARD_IA (after 30 days):**
- Storage: 1000 GB × $0.0125 = $12.50/month
- PUT requests: $0.50/month
- Retrieval: Depends on access patterns
- **Total: ~$13-15/month**

**INTELLIGENT_TIERING:**
- Storage: Varies based on access
- Monitoring: 1000 GB × $0.0025 = $2.50/month
- **Total: ~$15-25/month**

Use [AWS Pricing Calculator](https://calculator.aws/) for accurate estimates.

### Performance Considerations

**Pros:**
- Highly scalable (unlimited storage)
- Highly durable (99.999999999%)
- No server maintenance
- Multi-region replication available
- Cost-effective for large datasets

**Cons:**
- Network latency for uploads/downloads
- Data transfer costs
- API request costs
- More complex setup

**Optimization tips:**
1. Use same region as PutPlace server
2. Enable S3 Transfer Acceleration for global access
3. Use VPC endpoints to avoid data transfer costs
4. Monitor CloudWatch metrics
5. Use lifecycle policies for cost optimization

### Monitoring

#### CloudWatch Metrics

```bash
# Monitor bucket size
aws cloudwatch get-metric-statistics \
  --namespace AWS/S3 \
  --metric-name BucketSizeBytes \
  --dimensions Name=BucketName,Value=my-putplace-bucket Name=StorageType,Value=StandardStorage \
  --start-time 2025-01-01T00:00:00Z \
  --end-time 2025-01-15T00:00:00Z \
  --period 86400 \
  --statistics Average

# Monitor request count
aws cloudwatch get-metric-statistics \
  --namespace AWS/S3 \
  --metric-name NumberOfObjects \
  --dimensions Name=BucketName,Value=my-putplace-bucket Name=StorageType,Value=AllStorageTypes \
  --start-time 2025-01-01T00:00:00Z \
  --end-time 2025-01-15T00:00:00Z \
  --period 86400 \
  --statistics Average
```

#### Cost Monitoring

```bash
# Enable bucket metrics
aws s3api put-bucket-metrics-configuration \
  --bucket my-putplace-bucket \
  --id PutPlaceMetrics \
  --metrics-configuration '{
    "Id": "PutPlaceMetrics",
    "Filter": {
      "Prefix": "files/"
    }
  }'
```

## Switching Storage Backends

### From Local to S3

#### 1. Set up S3 (see above)

#### 2. Migrate existing files

```bash
#!/bin/bash
# migrate-local-to-s3.sh

LOCAL_PATH="/var/putplace/files"
S3_BUCKET="my-putplace-bucket"
S3_PREFIX="files/"

# Sync files to S3
aws s3 sync "$LOCAL_PATH" "s3://$S3_BUCKET/$S3_PREFIX" \
  --storage-class STANDARD \
  --metadata sha256verified=true

# Verify file count
LOCAL_COUNT=$(find "$LOCAL_PATH" -type f | wc -l)
S3_COUNT=$(aws s3 ls "s3://$S3_BUCKET/$S3_PREFIX" --recursive | wc -l)

echo "Local files: $LOCAL_COUNT"
echo "S3 files: $S3_COUNT"

if [ "$LOCAL_COUNT" -eq "$S3_COUNT" ]; then
    echo "✓ Migration complete!"
else
    echo "✗ File count mismatch!"
    exit 1
fi
```

#### 3. Update configuration

```bash
# In .env
# STORAGE_BACKEND=local  # Comment out
STORAGE_BACKEND=s3
S3_BUCKET_NAME=my-putplace-bucket
S3_REGION_NAME=us-east-1
```

#### 4. Restart server

```bash
sudo systemctl restart putplace
```

#### 5. Verify

```bash
# Test upload
python ppclient.py /tmp/test.txt

# Check server logs
sudo journalctl -u putplace -f
```

#### 6. Cleanup (optional)

After verifying S3 works:

```bash
# Backup local files first!
tar -czf /backup/putplace-files-$(date +%Y%m%d).tar.gz /var/putplace/files

# Remove local files
rm -rf /var/putplace/files/*
```

### From S3 to Local

Reverse of above process.

## Hybrid Storage

Currently, PutPlace does not support hybrid storage (using both local and S3 simultaneously). You must choose one backend.

**Workaround:** Use multiple PutPlace instances with different storage backends.

## Backup and Recovery

### Local Filesystem Backup

```bash
#!/bin/bash
# backup-local-storage.sh

BACKUP_DIR="/backup/putplace"
STORAGE_PATH="/var/putplace/files"
DATE=$(date +%Y%m%d)

# Create incremental backup
rsync -av --link-dest="$BACKUP_DIR/latest" \
  "$STORAGE_PATH/" \
  "$BACKUP_DIR/$DATE/"

# Update latest symlink
ln -snf "$BACKUP_DIR/$DATE" "$BACKUP_DIR/latest"

# Remove backups older than 30 days
find "$BACKUP_DIR" -maxdepth 1 -type d -mtime +30 -exec rm -rf {} \;
```

### S3 Backup

S3 is already highly durable. Additional backup options:

**Cross-region replication:**
```bash
# Enable replication to another region
aws s3api put-bucket-replication \
  --bucket my-putplace-bucket \
  --replication-configuration file://replication.json
```

**Versioning:**
```bash
# Enable versioning (keeps old versions)
aws s3api put-bucket-versioning \
  --bucket my-putplace-bucket \
  --versioning-configuration Status=Enabled
```

**Backup to Glacier:**

Use lifecycle policies to automatically archive to Glacier (see above).

## Troubleshooting

### Local Storage Issues

**Permission denied:**
```bash
# Fix ownership
sudo chown -R $USER:$USER /var/putplace/files

# Fix permissions
chmod -R 755 /var/putplace/files
```

**Disk full:**
```bash
# Check disk space
df -h /var/putplace/files

# Find large files
du -h --max-depth=1 /var/putplace/files | sort -hr | head -20

# Cleanup old files (carefully!)
find /var/putplace/files -type f -mtime +90 -delete
```

### S3 Storage Issues

**Connection timeout:**
```bash
# Check network connectivity
curl -I https://s3.us-east-1.amazonaws.com

# Check AWS credentials
aws sts get-caller-identity --profile putplace

# Check S3 access
aws s3 ls s3://my-putplace-bucket --profile putplace
```

**Access denied:**
```bash
# Verify IAM policy
aws iam get-user-policy --user-name putplace-user --policy-name putplace-s3-access

# Test permissions
aws s3 cp /tmp/test.txt s3://my-putplace-bucket/test.txt --profile putplace
```

**High costs:**
```bash
# Check storage class
aws s3api head-object --bucket my-putplace-bucket --key files/00/00abc123...

# Check lifecycle policies
aws s3api get-bucket-lifecycle-configuration --bucket my-putplace-bucket

# Review CloudWatch metrics
# See monitoring section above
```

## Next Steps

- [Configuration Reference](configuration.md) - Storage configuration options
- [Security Guide](../SECURITY.md) - AWS credentials and security
- [Deployment Guide](deployment.md) - Production deployment
- [Troubleshooting](troubleshooting.md) - Common issues
