# AWS App Runner Quick Start Guide

This guide shows how to deploy PutPlace to AWS App Runner. Runtime
configuration is provided through plain environment variables that are read
from your local shell at deploy time and forwarded to App Runner as
`RuntimeEnvironmentVariables`.

## Overview

The deployment workflow:
1. **Export config** - Set the required environment variables locally
2. **Deploy** - Create App Runner service (manual deployment mode)
3. **Trigger** - Manually deploy code changes

**Key Feature**: Auto-deployment is **disabled by default** - you control when deployments happen.

## Prerequisites

- AWS CLI installed and configured
- MongoDB Atlas free tier account (or other MongoDB)
- GitHub repository with PutPlace code
- Python 3.10+ with uv package manager

## Step 1: Export Runtime Configuration

`invoke deploy-apprunner` reads configuration from your local environment.
Export the values you need before deploying. For example:

```bash
export MONGODB_URL="mongodb+srv://user:pass@cluster.mongodb.net/"
export MONGODB_DATABASE="putplace"
export MONGODB_COLLECTION="file_metadata"

export PUTPLACE_ADMIN_USERNAME="admin"
export PUTPLACE_ADMIN_EMAIL="admin@example.com"
export PUTPLACE_ADMIN_PASSWORD="<a-strong-password>"

export AWS_DEFAULT_REGION="eu-west-1"
export API_TITLE="PutPlace File Metadata API"
export API_VERSION="0.5.8"
export PYTHONUNBUFFERED="1"
export PYTHONDONTWRITEBYTECODE="1"
```

`MONGODB_URL` and `PUTPLACE_ADMIN_PASSWORD` are required; the rest are
optional and only forwarded to App Runner if they are set.

**Save the admin password** in your password manager - it will be needed to
log in to the deployed service.

## Step 2: Deploy to App Runner

Create the App Runner service:

```bash
# Basic deployment (will prompt for GitHub repo URL)
invoke deploy-apprunner

# Specify GitHub repository
invoke deploy-apprunner \
  --github-repo=https://github.com/yourusername/putplace

# Larger instance size
invoke deploy-apprunner \
  --cpu="2 vCPU" \
  --memory="4 GB"

# Different region
invoke deploy-apprunner --region=us-east-1
```

**Important**: The first deployment requires connecting GitHub in the AWS console:
1. Go to [App Runner Console](https://console.aws.amazon.com/apprunner/)
2. Click **Settings** → **Source connections**
3. Click **Add connection** and authorize GitHub
4. Then run `invoke deploy-apprunner` again

## Step 3: Trigger Deployment

Since auto-deployment is disabled, manually trigger deployments:

```bash
# Trigger deployment after code changes
invoke trigger-apprunner-deploy

# Different service name
invoke trigger-apprunner-deploy --service-name=my-service
```

Or use AWS CLI directly:

```bash
aws apprunner start-deployment \
  --service-arn arn:aws:apprunner:region:account:service/putplace-api/xxxxx \
  --region eu-west-1
```

## Step 4: Access Your API

Find your App Runner URL:

```bash
aws apprunner list-services --region eu-west-1
```

Or in the AWS Console:
1. Go to [App Runner Console](https://console.aws.amazon.com/apprunner/)
2. Click on your service
3. Copy the **Default domain** URL

Test the API:

```bash
# Health check
curl https://xxxxx.eu-west-1.awsapprunner.com/health

# API documentation
open https://xxxxx.eu-west-1.awsapprunner.com/docs
```

## Common Tasks

### Update MongoDB Connection or Other Config

```bash
# Re-export the values with the new settings
export MONGODB_URL="mongodb+srv://newuser:newpass@cluster.mongodb.net/"

# Redeploy to push the new RuntimeEnvironmentVariables to App Runner
invoke deploy-apprunner
```

Alternatively, edit the runtime environment variables directly in the App
Runner console under **Configuration → Source → Edit**.

### Enable Auto-Deployment

To enable automatic deployments on git push:

```bash
invoke deploy-apprunner --auto-deploy
```

Or update in AWS Console:
1. Go to App Runner service
2. Click **Configuration** tab
3. Under **Source**, click **Edit**
4. Enable **Automatic deployments**
5. Click **Save**

### View Logs

```bash
# Application logs
aws logs tail /aws/apprunner/putplace-api/application --follow

# Service logs
aws logs tail /aws/apprunner/putplace-api/service --follow
```

Or in AWS Console:
1. Go to App Runner service
2. Click **Logs** tab
3. View **Application logs** or **Service logs**

### Scale the Service

Update instance configuration:

```bash
# Redeploy with different instance size
invoke deploy-apprunner --cpu="2 vCPU" --memory="4 GB"
```

Or in AWS Console:
1. Go to App Runner service
2. Click **Configuration** tab
3. Under **Instance**, click **Edit**
4. Adjust CPU and Memory
5. Click **Save** and **Deploy**

### Delete the Service

```bash
aws apprunner delete-service \
  --service-arn arn:aws:apprunner:region:account:service/putplace-api/xxxxx \
  --region eu-west-1
```

## Deployment Workflow

### Manual Deployment (Default - Recommended)

```bash
# 1. Make code changes
git add .
git commit -m "Update feature"
git push

# 2. Manually trigger deployment
invoke trigger-apprunner-deploy

# 3. Monitor deployment
aws apprunner describe-service \
  --service-arn arn:aws:apprunner:region:account:service/putplace-api/xxxxx
```

**Advantages:**
- Control exactly when deployments happen
- Test changes before deploying
- Avoid accidental deployments
- Better for production environments

### Automatic Deployment (Optional)

```bash
# Enable auto-deploy
invoke deploy-apprunner --auto-deploy

# Now just push to trigger deployment
git push  # Automatically deploys to App Runner
```

**Note**: Auto-deployment triggers on every push to the configured branch.

## Monitoring

### Check Service Status

```bash
# List all services
aws apprunner list-services --region eu-west-1

# Get service details
aws apprunner describe-service \
  --service-arn arn:aws:apprunner:region:account:service/putplace-api/xxxxx
```

### View Metrics

In AWS Console:
1. Go to App Runner service
2. Click **Metrics** tab
3. View:
   - Request count
   - Response time (p50, p90, p99)
   - 4xx/5xx errors
   - Active instances
   - CPU/Memory utilization

Or create CloudWatch dashboard:
```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/AppRunner \
  --metric-name RequestCount \
  --dimensions Name=ServiceName,Value=putplace-api \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-02T00:00:00Z \
  --period 3600 \
  --statistics Sum
```

## Troubleshooting

### Deployment Fails

```bash
# Check service status
aws apprunner describe-service --service-arn <arn>

# View service logs
aws logs tail /aws/apprunner/putplace-api/service --follow
```

**Common issues:**
- **GitHub not connected**: Set up GitHub connection in AWS Console
- **Build fails**: Check Python version, dependencies in pyproject.toml
- **Missing env vars**: Re-export the required variables and rerun deploy

### Application Fails to Start

```bash
# Check application logs
aws logs tail /aws/apprunner/putplace-api/application --follow
```

**Common issues:**
- **MongoDB connection failed**: Verify `MONGODB_URL` value
- **Admin user creation failed**: Check MongoDB permissions
- **Missing environment variables**: Re-export and rerun `invoke deploy-apprunner`

### Health Check Fails

The health check endpoint is `/health`. If it fails:
1. Check application logs for errors
2. Verify MongoDB is accessible
3. Test health check locally: `curl http://localhost:8000/health`

## Cost Estimation

AWS App Runner pricing (as of 2024):

**Basic Setup (1 vCPU, 2 GB):**
- Compute: ~$0.064/hour = ~$46/month
- Requests: $0.40 per million
- Data transfer: Standard AWS rates

**With MongoDB Atlas:**
- App Runner: ~$46/month
- MongoDB Atlas (M0 Free): $0/month
- **Total**: ~$46/month

**Medium Setup (2 vCPU, 4 GB):**
- Compute: ~$0.128/hour = ~$92/month
- **Total with MongoDB**: ~$92/month

## Security Best Practices

1. **Keep secrets out of source control** - export them in your shell or a
   `.env` file that is git-ignored.
2. **Enable HTTPS only** ✓ (App Runner default)
3. **Rotate credentials regularly** - update env vars and redeploy:
   ```bash
   export PUTPLACE_ADMIN_PASSWORD="<new-password>"
   invoke deploy-apprunner
   ```
4. **Monitor access logs** in CloudWatch
5. **Use private VPC** for MongoDB (DocumentDB)
6. **Enable AWS WAF** for additional protection
7. **Set up CloudWatch alarms** for errors and latency

## Custom Domain Configuration

Set up a custom domain (e.g., app.putplace.org) for your App Runner service:

### Step 1: Configure Custom Domain

```bash
# Associate domain with App Runner service
invoke configure-custom-domain --domain=app.putplace.org

# This will output the DNS records needed
```

### Step 2: Create DNS Records

The task automatically creates the necessary Route 53 DNS records:
1. **CNAME record** - Points your domain to App Runner (e.g., `app.putplace.org` → `xxxxx.awsapprunner.com`)
2. **Certificate validation records** - For SSL/TLS certificate (automatically created)

The DNS records are created immediately in Route 53.

### Step 3: Wait for Certificate Validation

```bash
# Check domain status
invoke check-custom-domain --domain=app.putplace.org
```

**Timeline:**
- DNS propagation: 5-10 minutes
- Certificate validation: 5-30 minutes (usually ~10 minutes)

**Status values:**
- `pending_certificate_dns_validation` - Waiting for DNS and cert validation
- `active` - Domain is ready to use

### Step 4: Access Your Custom Domain

Once the status shows `active`, your API will be available at:
```
https://app.putplace.org
```

Test it:
```bash
# Health check
curl https://app.putplace.org/health

# API documentation
open https://app.putplace.org/docs
```

### Troubleshooting Custom Domains

**Check DNS propagation:**
```bash
dig app.putplace.org CNAME +short
# Should return: xxxxx.awsapprunner.com
```

**Check certificate validation records:**
```bash
dig _xxxxx.app.putplace.org CNAME +short
# Should return ACM validation record
```

**Remove custom domain:**
```bash
invoke remove-custom-domain --domain=app.putplace.org
```

## Next Steps

- Configure auto-scaling: Adjust min/max instances
- Set up CI/CD: Integrate with GitHub Actions
- Add monitoring: CloudWatch dashboards and alarms
- Enable S3 storage: Set the relevant S3 env vars and redeploy

## Support

- AWS App Runner Docs: https://docs.aws.amazon.com/apprunner/
- PutPlace Issues: https://github.com/yourusername/putplace/issues
- AWS Support: https://console.aws.amazon.com/support/

## Invoke Tasks Reference

All available App Runner tasks:

```bash
# Deployment
invoke deploy-apprunner                 # Create service (manual mode)
invoke deploy-apprunner --auto-deploy   # Enable auto-deployment
invoke deploy-apprunner --cpu="2 vCPU" --memory="4 GB"  # Custom size
invoke trigger-apprunner-deploy         # Manually trigger deployment

# Custom Domains
invoke configure-custom-domain --domain=app.putplace.org  # Configure custom domain
invoke check-custom-domain --domain=app.putplace.org      # Check domain status
invoke remove-custom-domain --domain=app.putplace.org     # Remove custom domain

# Verification
invoke verify-ses-email --email=user@example.com  # Verify SES email
invoke check-ses-email --email=user@example.com   # Check verification status
invoke list-ses-emails                  # List verified emails
```

For detailed help on any task:
```bash
invoke --help <task-name>
```
