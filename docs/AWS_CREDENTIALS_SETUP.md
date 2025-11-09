# AWS Credentials Setup - Quick Start Guide

This guide shows you how to quickly configure AWS credentials for PutPlace's S3 storage backend.

## Quick Start Options

### Option 1: AWS Credentials File (Recommended for Development)

**Best for:** Local development, testing, on-premises servers

1. **Create AWS credentials file:**
```bash
mkdir -p ~/.aws
cat > ~/.aws/credentials << 'EOF'
[putplace]
aws_access_key_id = YOUR_ACCESS_KEY_HERE
aws_secret_access_key = YOUR_SECRET_KEY_HERE
EOF
chmod 600 ~/.aws/credentials
```

2. **Configure PutPlace** (`.env` file):
```bash
STORAGE_BACKEND=s3
S3_BUCKET_NAME=your-bucket-name
S3_REGION_NAME=us-east-1
AWS_PROFILE=putplace
```

3. **Start server:**
```bash
uvicorn putplace.main:app
```

That's it! The server will use the `putplace` profile from `~/.aws/credentials`.

---

### Option 2: IAM Role (Recommended for Production on AWS)

**Best for:** EC2, ECS, Lambda, EKS running on AWS

1. **Create IAM policy** with S3 permissions:
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject", "s3:HeadObject"],
    "Resource": "arn:aws:s3:::your-bucket-name/files/*"
  }]
}
```

2. **Attach policy to EC2 instance role** (via AWS Console or CLI)

3. **Configure PutPlace** (`.env` file):
```bash
STORAGE_BACKEND=s3
S3_BUCKET_NAME=your-bucket-name
S3_REGION_NAME=us-east-1
# No AWS credentials needed!
```

4. **Start server:**
```bash
uvicorn putplace.main:app
```

The server automatically uses the IAM role credentials. No keys needed!

---

### Option 3: Environment Variables (Quick Testing)

**Best for:** Quick testing, CI/CD pipelines

1. **Set environment variables:**
```bash
export STORAGE_BACKEND=s3
export S3_BUCKET_NAME=your-bucket-name
export S3_REGION_NAME=us-east-1
export AWS_ACCESS_KEY_ID=YOUR_ACCESS_KEY_HERE
export AWS_SECRET_ACCESS_KEY=YOUR_SECRET_KEY_HERE
```

2. **Start server:**
```bash
uvicorn putplace.main:app
```

**⚠️ Warning:** Credentials are visible in process list. Not recommended for production.

---

## Verification

### Quick Test: Standalone S3/SES Configuration Tests (v0.5.2+)

The fastest way to test your AWS credentials:

```bash
# Test S3 access
putplace_configure S3
# Or: uv run python -m putplace.scripts.putplace_configure S3

# Test SES access
putplace_configure SES
# Or: uv run python -m putplace.scripts.putplace_configure SES

# Test in specific region
putplace_configure S3 --aws-region us-west-2

# Via invoke task
invoke configure --test-mode=S3
invoke configure --test-mode=SES
```

These commands will:
- ✅ Use your AWS credentials (IAM role, profile, or environment variables)
- ✅ Test connectivity to AWS services
- ✅ Show clear success/failure messages
- ✅ Exit with status code 0 (success) or 1 (failure)

### Full Integration Test

Test that your credentials work with the running server:

```bash
# Check if server can connect to S3
curl http://localhost:8000/health

# Upload a test file
curl -X POST http://localhost:8000/put_file \
  -H "Content-Type: application/json" \
  -d '{
    "filepath": "/tmp/test.txt",
    "hostname": "testhost",
    "ip_address": "127.0.0.1",
    "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "file_size": 0,
    "file_mode": 33188,
    "file_uid": 1000,
    "file_gid": 1000,
    "file_mtime": 1609459200.0,
    "file_atime": 1609459200.0,
    "file_ctime": 1609459200.0
  }'
```

Check the server logs for:
- ✅ `"Initialized S3Storage with bucket: ..."`
- ✅ `"Using AWS profile: ..."` (if using profile)
- ✅ `"Using default AWS credential chain"` (if using IAM role)

---

## Troubleshooting

### "Unable to locate credentials"

**Solution:** Check in this order:
1. Is `AWS_PROFILE` set correctly in `.env`?
2. Does `~/.aws/credentials` file exist and have correct permissions (600)?
3. For EC2: Is IAM role attached to the instance?

```bash
# Check credentials file permissions
ls -la ~/.aws/credentials
# Should show: -rw------- (600)

# Check if AWS CLI can access credentials
aws sts get-caller-identity
```

### "Access Denied" errors

**Solution:** Check IAM permissions:
```bash
# Test S3 access with AWS CLI
aws s3 ls s3://your-bucket-name/files/
aws s3 cp /tmp/test.txt s3://your-bucket-name/files/test.txt

# If these work, PutPlace should work too
```

Make sure IAM policy includes: `s3:PutObject`, `s3:GetObject`, `s3:HeadObject`, `s3:DeleteObject`

### "NoSuchBucket" error

**Solution:** Create the S3 bucket:
```bash
# Create bucket
aws s3 mb s3://your-bucket-name --region us-east-1

# Enable versioning (optional but recommended)
aws s3api put-bucket-versioning \
  --bucket your-bucket-name \
  --versioning-configuration Status=Enabled
```

---

## Complete Configuration Examples

### Example 1: Development Setup

```bash
# ~/.aws/credentials
[putplace-dev]
aws_access_key_id = AKIAI...
aws_secret_access_key = wJalr...

# .env
STORAGE_BACKEND=s3
S3_BUCKET_NAME=putplace-dev-bucket
S3_REGION_NAME=us-east-1
AWS_PROFILE=putplace-dev
MONGODB_DATABASE=putplace_dev
```

### Example 2: Production on AWS EC2

```bash
# .env (no credentials needed!)
STORAGE_BACKEND=s3
S3_BUCKET_NAME=putplace-prod-bucket
S3_REGION_NAME=us-west-2
MONGODB_URL=mongodb://prod-db-server:27017
MONGODB_DATABASE=putplace_prod
```

EC2 instance must have IAM role with S3 permissions attached.

### Example 3: Multiple Environments with Profiles

```bash
# ~/.aws/credentials
[putplace-dev]
aws_access_key_id = AKIAI...dev...
aws_secret_access_key = secret...dev...

[putplace-staging]
aws_access_key_id = AKIAI...staging...
aws_secret_access_key = secret...staging...

[putplace-prod]
aws_access_key_id = AKIAI...prod...
aws_secret_access_key = secret...prod...

# .env.dev
AWS_PROFILE=putplace-dev
S3_BUCKET_NAME=putplace-dev-bucket

# .env.staging
AWS_PROFILE=putplace-staging
S3_BUCKET_NAME=putplace-staging-bucket

# .env.prod
AWS_PROFILE=putplace-prod
S3_BUCKET_NAME=putplace-prod-bucket
```

---

## Security Best Practices

✅ **DO:**
- Use IAM roles on AWS infrastructure (no keys needed)
- Use AWS credentials file with profiles for on-premises
- Set `chmod 600 ~/.aws/credentials`
- Use separate credentials for dev/staging/production
- Rotate access keys every 90 days
- Use least-privilege IAM policies

❌ **DON'T:**
- Don't commit `.env` file to git
- Don't use root AWS account credentials
- Don't grant `s3:*` permissions
- Don't share credentials between applications
- Don't log AWS credentials

---

## Next Steps

- 📖 Read the complete **[SECURITY.md](../SECURITY.md)** for comprehensive security guidance
- 🔐 Learn about **AWS Secrets Manager** and **HashiCorp Vault** for advanced secret management
- 📋 Review **IAM policy examples** for least-privilege access
- 🔄 Set up **credential rotation** for long-lived keys

---

## Quick Reference

| Method | Security | Setup | Best For |
|--------|----------|-------|----------|
| IAM Role | ⭐⭐⭐⭐⭐ | Medium | Production on AWS |
| AWS Profile | ⭐⭐⭐⭐ | Easy | Development, On-premises |
| Env Variables | ⭐⭐⭐ | Easy | Testing, CI/CD |
| Hardcoded | ⭐ | Very Easy | Never use! |

**Default recommendation:**
- **Production on AWS:** Use IAM roles
- **Production on-premises:** Use AWS credentials file with profiles
- **Development:** Use AWS credentials file with profiles
- **CI/CD:** Use environment variables from secret manager
