# AWS App Runner Configuration Guide

This guide explains how to configure PutPlace running on AWS App Runner, particularly for settings that can't be changed by editing config files.

## Overview

AWS App Runner runs containers in a managed environment where you can't directly edit configuration files. Instead, you must use **environment variables** to configure the application.

## Setting Environment Variables

### Method 1: AWS Console (Recommended)

1. **Navigate to your service:**
   - Go to [AWS App Runner Console](https://console.aws.amazon.com/apprunner/home)
   - Select your PutPlace service

2. **Edit configuration:**
   - Click **"Configuration"** tab
   - Click **"Edit"** under "Configure service"
   - Scroll to **"Environment variables"**

3. **Add variables:**
   - Click **"Add environment variable"**
   - Enter key and value
   - Click **"Next"** → **"Deploy"**

4. **Wait for deployment:**
   - Deployment takes 2-3 minutes
   - Service will automatically restart with new configuration

### Method 2: AWS CLI

```bash
# Get your service ARN
aws apprunner list-services \
  --query 'ServiceSummaryList[?ServiceName==`putplace`].ServiceArn' \
  --output text

# Update environment variables
aws apprunner update-service \
  --service-arn "arn:aws:apprunner:region:account:service/putplace/xxx" \
  --source-configuration '{
    "ImageRepository": {
      "ImageConfiguration": {
        "RuntimeEnvironmentVariables": {
          "PUTPLACE_REGISTRATION_ENABLED": "false",
          "PUTPLACE_SENDER_EMAIL": "noreply@putplace.org",
          "PUTPLACE_BASE_URL": "https://your-service.awsapprunner.com",
          "PUTPLACE_EMAIL_AWS_REGION": "eu-west-1"
        }
      }
    }
  }'
```

## Common Configuration Variables

### Email Configuration

```bash
# Email settings (AWS SES)
PUTPLACE_SENDER_EMAIL=noreply@putplace.org
PUTPLACE_BASE_URL=https://your-service.awsapprunner.com
PUTPLACE_EMAIL_AWS_REGION=eu-west-1
```

### Registration Control

```bash
# Enable/disable user registration
PUTPLACE_REGISTRATION_ENABLED=true   # or false
```

### Database Configuration

```bash
# MongoDB settings
MONGODB_URL=mongodb://your-mongodb-server:27017
MONGODB_DATABASE=putplace
MONGODB_COLLECTION=file_metadata
```

### Storage Configuration

```bash
# Storage backend
STORAGE_BACKEND=s3
S3_BUCKET_NAME=your-bucket-name
S3_REGION_NAME=eu-west-1
```

### OAuth Configuration

```bash
# Google OAuth
GOOGLE_CLIENT_ID=123456789-abcdefg.apps.googleusercontent.com
```

## Toggle Registration Script

PutPlace includes a Python script to easily toggle user registration:

### Setup (One Time)

```bash
# Find your service ARN
aws apprunner list-services \
  --query 'ServiceSummaryList[?ServiceName==`putplace`].ServiceArn' \
  --output text

# Export it
export APPRUNNER_SERVICE_ARN="arn:aws:apprunner:eu-west-1:123456:service/putplace/xxx"
```

### Usage

```bash
# Disable registration
invoke toggle-registration --action=disable

# Re-enable registration
invoke toggle-registration --action=enable

# Or use the script directly
uv run python -m putplace.scripts.toggle_registration disable
uv run python -m putplace.scripts.toggle_registration enable
```

### What it does

The script will:
1. Fetch current environment variables from App Runner
2. Update `PUTPLACE_REGISTRATION_ENABLED` to true/false
3. Trigger a deployment with the updated configuration
4. Show deployment status and monitoring commands

### Script Features

- ✅ Preserves all existing environment variables
- ✅ Auto-detects AWS region from service ARN
- ✅ Shows deployment progress
- ✅ Provides monitoring commands
- ✅ No container rebuild needed (just restart)

## Configuration Priority

Settings are loaded in this order (highest priority first):

1. **Environment Variables** (AWS App Runner)
2. **ppserver.toml** (not applicable in App Runner)
3. **Default values** (hardcoded in application)

Since you can't edit files in App Runner, always use environment variables.

## Monitoring Deployment

After updating configuration, monitor the deployment:

```bash
# Check service status
aws apprunner describe-service \
  --service-arn "YOUR_ARN" \
  --query 'Service.Status'

# Watch service logs
aws logs tail /aws/apprunner/putplace/service --follow
```

## Common Use Cases

### Close Registration After Initial Setup

```bash
# After creating admin users, disable public registration
invoke toggle-registration --action=disable
```

### Update Email Sender

```bash
aws apprunner update-service \
  --service-arn "YOUR_ARN" \
  --source-configuration '{
    "ImageRepository": {
      "ImageConfiguration": {
        "RuntimeEnvironmentVariables": {
          "PUTPLACE_SENDER_EMAIL": "new-sender@putplace.org"
        }
      }
    }
  }'
```

### Switch to Different MongoDB Database

```bash
# Update MongoDB database name
aws apprunner update-service \
  --service-arn "YOUR_ARN" \
  --source-configuration '{
    "ImageRepository": {
      "ImageConfiguration": {
        "RuntimeEnvironmentVariables": {
          "MONGODB_DATABASE": "putplace_production"
        }
      }
    }
  }'
```

## Troubleshooting

### Changes not taking effect

- Wait 2-3 minutes for deployment to complete
- Check service status: `aws apprunner describe-service --service-arn "YOUR_ARN"`
- Verify environment variables were set correctly

### Script fails with "No credentials"

```bash
# Configure AWS credentials
aws configure

# Or set temporary credentials
export AWS_ACCESS_KEY_ID=xxx
export AWS_SECRET_ACCESS_KEY=xxx
export AWS_SESSION_TOKEN=xxx
```

### Can't find service ARN

```bash
# List all App Runner services
aws apprunner list-services

# Filter for PutPlace service
aws apprunner list-services \
  --query 'ServiceSummaryList[?ServiceName==`putplace`]'
```

## Best Practices

1. **Use environment variables** for all configuration in App Runner
2. **Never hardcode secrets** in the container image
3. **Use AWS Secrets Manager** for sensitive values (database passwords, API keys)
4. **Test configuration changes** in a dev/staging environment first
5. **Document your environment variables** for team members
6. **Use the toggle script** for frequently changed settings like registration

## See Also

- [AWS App Runner Documentation](https://docs.aws.amazon.com/apprunner/)
- [AWS_DEPLOYMENT_GUIDE.md](./AWS_DEPLOYMENT_GUIDE.md)
- [README.md - Email Confirmation](./README.md#email-confirmation)
