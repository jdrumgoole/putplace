# Security Guide - AWS Credentials and Storage

This document describes secure ways to manage AWS credentials for PutPlace's S3 storage backend.

## Table of Contents

- [Overview](#overview)
- [Credential Methods (Ranked by Security)](#credential-methods-ranked-by-security)
- [Configuration Examples](#configuration-examples)
- [Best Practices](#best-practices)
- [IAM Policy Examples](#iam-policy-examples)

---

## Overview

PutPlace supports multiple methods for AWS credential management. The application uses `aioboto3` (async AWS SDK), which follows the standard **AWS credential chain** in this order:

1. Explicit credentials passed to the application (not recommended)
2. Environment variables
3. AWS credentials file (`~/.aws/credentials`)
4. IAM roles (for EC2/ECS/Lambda/etc.)
5. Container credentials (for ECS tasks)
6. Instance metadata service (for EC2)

---

## Credential Methods (Ranked by Security)

### ⭐⭐⭐⭐⭐ 1. IAM Roles (BEST - Production Recommended)

**Use when:** Running on AWS infrastructure (EC2, ECS, Lambda, EKS, etc.)

**How it works:** AWS automatically provides temporary credentials to your application through the instance metadata service. No credential files or environment variables needed!

**Setup:**

1. **Create IAM Role** with S3 permissions (see [IAM Policy Examples](#iam-policy-examples))
2. **Attach role** to your EC2 instance, ECS task, or Lambda function
3. **Configure PutPlace** - no credentials needed!

**Configuration (.env):**
```bash
STORAGE_BACKEND=s3
S3_BUCKET_NAME=my-putplace-bucket
S3_REGION_NAME=us-east-1
# That's it! No AWS credentials needed
```

**Advantages:**
- ✅ Most secure - no long-lived credentials
- ✅ Automatic credential rotation
- ✅ No credential files to manage
- ✅ Built-in AWS audit trail (CloudTrail)
- ✅ Fine-grained permissions per service

**Disadvantages:**
- ❌ Only works on AWS infrastructure
- ❌ Requires AWS configuration outside the app

---

### ⭐⭐⭐⭐ 2. AWS Credentials File with Named Profiles

**Use when:** Running on-premises or locally, multiple AWS accounts

**How it works:** Store credentials in `~/.aws/credentials` with named profiles. Each profile has separate access keys.

**Setup:**

1. **Create AWS credentials file** at `~/.aws/credentials`:
```ini
[default]
aws_access_key_id = AKIAIOSFODNN7EXAMPLE
aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY

[putplace-prod]
aws_access_key_id = AKIAI44QH8DHBEXAMPLE
aws_secret_access_key = je7MtGbClwBF/2Zp9Utk/h3yCo8nvbEXAMPLEKEY

[putplace-dev]
aws_access_key_id = AKIAI44QH8DHBEXAMPLE
aws_secret_access_key = another-secret-key-here
```

2. **Set file permissions** (IMPORTANT):
```bash
chmod 600 ~/.aws/credentials
```

3. **Configure PutPlace** (.env):
```bash
STORAGE_BACKEND=s3
S3_BUCKET_NAME=my-putplace-bucket
S3_REGION_NAME=us-east-1
AWS_PROFILE=putplace-prod  # Use specific profile
```

**Advantages:**
- ✅ Secure file permissions (600)
- ✅ Multiple profiles for different environments
- ✅ Standard AWS practice
- ✅ Shared with other AWS tools (aws-cli, terraform, etc.)
- ✅ Credentials stored locally, not in code

**Disadvantages:**
- ❌ Long-lived credentials (must rotate manually)
- ❌ Credentials in plaintext (though file-protected)
- ❌ Must secure the server's filesystem

---

### ⭐⭐⭐⭐ 3. Environment Variables (via Secure Secret Management)

**Use when:** Using container orchestration (Docker, Kubernetes) or secret management systems

**How it works:** Store credentials in a secret management system, inject as environment variables at runtime.

**Option A: AWS Secrets Manager**

1. **Store secret in AWS Secrets Manager:**
```bash
aws secretsmanager create-secret \
    --name putplace/aws-credentials \
    --secret-string '{"access_key":"AKIAI...","secret_key":"wJalr..."}'
```

2. **Retrieve in startup script:**
```bash
#!/bin/bash
# startup.sh
SECRET=$(aws secretsmanager get-secret-value \
    --secret-id putplace/aws-credentials \
    --query SecretString --output text)

export AWS_ACCESS_KEY_ID=$(echo $SECRET | jq -r .access_key)
export AWS_SECRET_ACCESS_KEY=$(echo $SECRET | jq -r .secret_key)

# Start application
uvicorn putplace.main:app
```

**Option B: HashiCorp Vault**

1. **Store secret in Vault:**
```bash
vault kv put secret/putplace \
    aws_access_key_id=AKIAI... \
    aws_secret_access_key=wJalr...
```

2. **Retrieve in startup script:**
```bash
#!/bin/bash
export AWS_ACCESS_KEY_ID=$(vault kv get -field=aws_access_key_id secret/putplace)
export AWS_SECRET_ACCESS_KEY=$(vault kv get -field=aws_secret_access_key secret/putplace)

uvicorn putplace.main:app
```

**Option C: Kubernetes Secrets**

1. **Create Kubernetes secret:**
```bash
kubectl create secret generic putplace-aws \
    --from-literal=aws-access-key-id=AKIAI... \
    --from-literal=aws-secret-access-key=wJalr...
```

2. **Mount in pod (deployment.yaml):**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: putplace
spec:
  template:
    spec:
      containers:
      - name: putplace
        image: putplace:latest
        env:
        - name: AWS_ACCESS_KEY_ID
          valueFrom:
            secretKeyRef:
              name: putplace-aws
              key: aws-access-key-id
        - name: AWS_SECRET_ACCESS_KEY
          valueFrom:
            secretKeyRef:
              name: putplace-aws
              key: aws-secret-access-key
        - name: STORAGE_BACKEND
          value: "s3"
        - name: S3_BUCKET_NAME
          value: "my-putplace-bucket"
```

**Advantages:**
- ✅ Centralized secret management
- ✅ Audit logging
- ✅ Secret rotation capabilities
- ✅ Access control policies
- ✅ Encrypted at rest

**Disadvantages:**
- ❌ Additional infrastructure required
- ❌ More complex setup
- ❌ Credentials still in environment at runtime

---

### ⭐⭐⭐ 4. Local Configuration File (.env)

**Use when:** Development, small deployments, single server

**How it works:** Store configuration in a `.env` file with strict file permissions.

**Setup:**

1. **Create .env file** in the application directory:
```bash
# .env
STORAGE_BACKEND=s3
S3_BUCKET_NAME=my-putplace-bucket
S3_REGION_NAME=us-east-1

# Option 1: Use AWS profile (better)
AWS_PROFILE=putplace-prod

# Option 2: Explicit credentials (less secure)
# AWS_ACCESS_KEY_ID=AKIAI44QH8DHBEXAMPLE
# AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

2. **Set strict file permissions:**
```bash
chmod 600 .env
chown putplace:putplace .env  # Application user only
```

3. **Add to .gitignore:**
```bash
echo ".env" >> .gitignore
```

**Advantages:**
- ✅ Simple to set up
- ✅ Easy to change configuration
- ✅ Works anywhere

**Disadvantages:**
- ❌ Credentials in plaintext file
- ❌ Easy to accidentally commit to git
- ❌ Must secure file permissions
- ❌ Hard to rotate credentials

---

### ⭐⭐ 5. Environment Variables (Direct)

**Use when:** Quick testing, CI/CD pipelines

**How it works:** Set environment variables directly in shell or systemd service.

**Setup:**

```bash
export STORAGE_BACKEND=s3
export S3_BUCKET_NAME=my-putplace-bucket
export S3_REGION_NAME=us-east-1
export AWS_ACCESS_KEY_ID=AKIAI44QH8DHBEXAMPLE
export AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY

uvicorn putplace.main:app
```

**Or in systemd service:**
```ini
# /etc/systemd/system/putplace.service
[Service]
Environment="STORAGE_BACKEND=s3"
Environment="S3_BUCKET_NAME=my-putplace-bucket"
Environment="AWS_ACCESS_KEY_ID=AKIAI..."
Environment="AWS_SECRET_ACCESS_KEY=wJalr..."
ExecStart=/usr/local/bin/uvicorn putplace.main:app
```

**Advantages:**
- ✅ Simple
- ✅ No files to manage

**Disadvantages:**
- ❌ Visible in process list (`ps aux | grep AWS`)
- ❌ Stored in shell history
- ❌ Easy to leak in logs
- ❌ Hard to rotate

---

### ⭐ 6. Hardcoded Credentials (NEVER USE IN PRODUCTION)

**Use when:** Never in production! Only for local development/testing.

**Setup (.env):**
```bash
STORAGE_BACKEND=s3
S3_BUCKET_NAME=my-putplace-bucket
AWS_ACCESS_KEY_ID=AKIAI44QH8DHBEXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

**Disadvantages:**
- ❌ Credentials in version control (if committed)
- ❌ Visible to anyone with access
- ❌ Hard to rotate
- ❌ Security nightmare if leaked

---

## Configuration Examples

### Development (Local)

Use AWS credentials file with profile:

```bash
# ~/.aws/credentials
[putplace-dev]
aws_access_key_id = AKIAI...
aws_secret_access_key = wJalr...

# .env
STORAGE_BACKEND=s3
S3_BUCKET_NAME=putplace-dev-bucket
AWS_PROFILE=putplace-dev
```

### Production (AWS EC2/ECS)

Use IAM roles (no credentials needed):

```bash
# .env
STORAGE_BACKEND=s3
S3_BUCKET_NAME=putplace-prod-bucket
S3_REGION_NAME=us-east-1
# No AWS credentials - uses IAM role automatically
```

### Production (On-Premises Server)

Use AWS credentials file with restricted permissions:

```bash
# /etc/putplace/.aws/credentials (owned by putplace user, mode 600)
[default]
aws_access_key_id = AKIAI...
aws_secret_access_key = wJalr...

# /etc/putplace/.env
STORAGE_BACKEND=s3
S3_BUCKET_NAME=putplace-prod-bucket
AWS_PROFILE=default  # Or omit to use default profile
```

### Docker Container

Use secrets mounted as environment variables:

```bash
docker run -d \
  -e STORAGE_BACKEND=s3 \
  -e S3_BUCKET_NAME=putplace-bucket \
  -e AWS_ACCESS_KEY_ID=$(cat /run/secrets/aws_key_id) \
  -e AWS_SECRET_ACCESS_KEY=$(cat /run/secrets/aws_secret) \
  putplace:latest
```

Or mount credentials file:

```bash
docker run -d \
  -v ~/.aws:/root/.aws:ro \
  -e STORAGE_BACKEND=s3 \
  -e S3_BUCKET_NAME=putplace-bucket \
  -e AWS_PROFILE=putplace-prod \
  putplace:latest
```

---

## Best Practices

### ✅ DO:

1. **Use IAM roles** whenever running on AWS infrastructure
2. **Use named profiles** from `~/.aws/credentials` for on-premises
3. **Rotate credentials** regularly (every 90 days)
4. **Use least-privilege** IAM policies (see examples below)
5. **Set restrictive file permissions** (600 for credential files)
6. **Never commit credentials** to version control
7. **Use separate credentials** for dev/staging/production
8. **Enable CloudTrail** for audit logging
9. **Use MFA** for IAM users creating access keys
10. **Monitor for leaked credentials** (AWS Access Analyzer, git-secrets)

### ❌ DON'T:

1. **Don't hardcode credentials** in source code
2. **Don't use root AWS account** credentials
3. **Don't share credentials** between applications
4. **Don't log credentials** (check application logs!)
5. **Don't grant `s3:*` permissions** - use specific actions
6. **Don't commit .env files** to git
7. **Don't use long-lived credentials** when IAM roles are available
8. **Don't store credentials in public repos** (even accidentally)

---

## IAM Policy Examples

### Minimal S3 Policy (Least Privilege)

Grant only the permissions PutPlace needs:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PutPlaceS3Access",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject",
        "s3:HeadObject"
      ],
      "Resource": "arn:aws:s3:::my-putplace-bucket/files/*"
    },
    {
      "Sid": "PutPlaceS3BucketAccess",
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket"
      ],
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

### IAM Role for EC2 Instance

1. **Create IAM policy** (use JSON above)
2. **Create IAM role** for EC2:

```bash
aws iam create-role \
    --role-name PutPlaceEC2Role \
    --assume-role-policy-document '{
      "Version": "2012-10-17",
      "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "ec2.amazonaws.com"},
        "Action": "sts:AssumeRole"
      }]
    }'
```

3. **Attach policy to role:**

```bash
aws iam attach-role-policy \
    --role-name PutPlaceEC2Role \
    --policy-arn arn:aws:iam::ACCOUNT_ID:policy/PutPlaceS3Policy
```

4. **Create instance profile:**

```bash
aws iam create-instance-profile --instance-profile-name PutPlaceEC2Profile
aws iam add-role-to-instance-profile \
    --instance-profile-name PutPlaceEC2Profile \
    --role-name PutPlaceEC2Role
```

5. **Attach to EC2 instance:**

```bash
aws ec2 associate-iam-instance-profile \
    --instance-id i-1234567890abcdef0 \
    --iam-instance-profile Name=PutPlaceEC2Profile
```

---

## Credential Rotation

### Automated Rotation with AWS Secrets Manager

1. **Store credentials in Secrets Manager**
2. **Enable automatic rotation** (every 30/60/90 days)
3. **Update application** to fetch from Secrets Manager on startup

Example rotation Lambda function (Python):

```python
import boto3
import json

def lambda_handler(event, context):
    iam = boto3.client('iam')
    secrets = boto3.client('secretsmanager')

    # Get current secret
    secret_arn = event['SecretId']
    token = event['ClientRequestToken']

    # Create new access key
    username = 'putplace-user'
    new_key = iam.create_access_key(UserName=username)

    # Store new credentials
    new_secret = {
        'access_key': new_key['AccessKey']['AccessKeyId'],
        'secret_key': new_key['AccessKey']['SecretAccessKey']
    }

    secrets.put_secret_value(
        SecretId=secret_arn,
        SecretString=json.dumps(new_secret),
        VersionStages=['AWSPENDING'],
        ClientRequestToken=token
    )

    # Delete old access key (after verification)
    # ... implementation details ...
```

---

## Troubleshooting

### Check Which Credentials Are Being Used

```python
import boto3

# Check current credentials
session = boto3.Session()
credentials = session.get_credentials()
print(f"Access Key: {credentials.access_key[:8]}...")
print(f"Method: {credentials.method}")  # Shows how credentials were obtained
```

### Common Issues

**"Unable to locate credentials"**
- Check AWS_ACCESS_KEY_ID environment variable
- Check ~/.aws/credentials file exists and has correct permissions
- Check AWS_PROFILE is set correctly
- For EC2: Verify IAM role is attached to instance

**"Access Denied"**
- Check IAM policy allows required S3 actions
- Verify bucket name is correct
- Check bucket policy doesn't deny access
- Verify region is correct

**"Credentials expired"**
- IAM role credentials expire automatically (renewed by AWS)
- Access keys don't expire (must be rotated manually)
- Temporary credentials (STS) expire after specified duration

---

## Security Checklist

Before deploying to production:

- [ ] Using IAM roles (if on AWS) or AWS credentials file (if on-premises)
- [ ] NOT using hardcoded credentials in .env or code
- [ ] IAM policy follows least-privilege principle
- [ ] Credentials file has 600 permissions
- [ ] .env file is in .gitignore
- [ ] CloudTrail is enabled for audit logging
- [ ] Credentials are rotated regularly (or using short-lived tokens)
- [ ] Separate credentials for dev/staging/production
- [ ] MFA enabled for IAM users
- [ ] No credentials in application logs

---

## Additional Resources

- [AWS Security Best Practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)
- [AWS Credentials Configuration](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html)
- [IAM Roles for EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/iam-roles-for-amazon-ec2.html)
- [AWS Secrets Manager](https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html)
- [Principle of Least Privilege](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html#grant-least-privilege)
