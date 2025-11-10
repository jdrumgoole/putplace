# AWS Deployment Guide for PutPlace

This guide covers multiple AWS deployment options for the PutPlace FastAPI server, ranked from simplest to most scalable.

## Quick Comparison

| Option | Best For | Cost | Complexity | Auto-scaling | Cold Starts |
|--------|----------|------|------------|--------------|-------------|
| **AWS App Runner** | Quick start, small teams | $$ | ⭐ Low | ✅ Yes | ✅ No |
| **ECS Fargate** | Production, flexibility | $$$ | ⭐⭐ Medium | ✅ Yes | ✅ No |
| **EC2 + Docker** | Full control, cost-conscious | $ | ⭐⭐ Medium | ❌ Manual | ✅ No |
| **Lambda + API Gateway** | Serverless, variable load | $ | ⭐⭐⭐ High | ✅ Yes | ⚠️ Yes (100-500ms) |
| **Elastic Beanstalk** | Traditional PaaS | $$ | ⭐⭐ Medium | ✅ Yes | ✅ No |

## Recommendation: AWS App Runner ⭐ (Best for PutPlace)

**Why App Runner?**
- ✅ Simplest setup (< 10 minutes)
- ✅ Auto-scales from 0 to thousands of requests
- ✅ Built-in load balancing and HTTPS
- ✅ GitHub integration for CI/CD
- ✅ No container orchestration needed
- ✅ Pay only for what you use
- ✅ Perfect for FastAPI applications

**Estimated Cost:** ~$25-50/month for low-medium traffic

---

# Option 1: AWS App Runner (Recommended)

## Architecture

```
GitHub Repo → App Runner Service → MongoDB Atlas/DocumentDB
                    ↓
                  S3 (file storage)
                    ↓
              CloudWatch Logs
```

## Prerequisites

1. AWS Account with appropriate permissions
2. MongoDB Atlas account (or AWS DocumentDB)
3. Dockerfile for PutPlace (we'll create this)
4. GitHub repository

## Step 1: Create Dockerfile

Create `Dockerfile` in your repository root:

```dockerfile
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:$PATH"

# Copy project files
COPY pyproject.toml ./
COPY src ./src
COPY README.md ./

# Install dependencies (production only)
RUN uv pip install --system -e .

# Install S3 support (optional)
RUN uv pip install --system -e ".[s3]"

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Run with production settings
CMD ["uvicorn", "putplace.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

## Step 2: Create `.dockerignore`

```
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual environments
.venv/
venv/
ENV/
env/

# Testing
.tox/
.coverage
.coverage.*
.cache
htmlcov/
.pytest_cache/

# IDEs
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Project specific
tests/
docs/
.git/
.github/
node_modules/
ppgui-electron/
storage/
*.log
.env
.env.*
```

## Step 3: Set Up MongoDB Atlas

1. **Create MongoDB Atlas Cluster:**
   - Go to https://www.mongodb.com/cloud/atlas
   - Create free tier cluster (M0) or paid tier
   - Note your connection string

2. **Configure Network Access:**
   - Atlas → Network Access → Add IP Address
   - Allow access from anywhere: `0.0.0.0/0` (for App Runner)
   - Or use AWS PrivateLink for better security

3. **Create Database User:**
   - Database Access → Add New Database User
   - Username: `putplace`
   - Password: (generate strong password)
   - Role: `readWrite` on `putplace` database

## Step 4: Deploy to App Runner

### Using AWS Console (Easiest):

1. **Navigate to App Runner:**
   - AWS Console → App Runner → Create service

2. **Source Configuration:**
   - Repository type: **Source code repository**
   - Connect to GitHub (authorize AWS)
   - Select your `putplace` repository
   - Branch: `main`
   - Deployment trigger: **Automatic**

3. **Build Settings:**
   - Build command: (leave default or use `docker build`)
   - Use Dockerfile

4. **Service Settings:**
   - Service name: `putplace-api`
   - Port: `8000`
   - CPU: `1 vCPU`
   - Memory: `2 GB`
   - Environment variables:
     ```
     MONGODB_URL=mongodb+srv://putplace:PASSWORD@cluster.mongodb.net/putplace
     MONGODB_DATABASE=putplace
     MONGODB_COLLECTION=file_metadata
     STORAGE_BACKEND=s3
     S3_BUCKET_NAME=putplace-files
     AWS_REGION=us-east-1
     GOOGLE_CLIENT_ID=your-google-client-id (optional)
     ```

5. **Auto Scaling:**
   - Min instances: `1` (or `0` for cost savings, but has cold start)
   - Max instances: `10`
   - Concurrent requests: `100`

6. **Health Check:**
   - Path: `/health`
   - Interval: `30 seconds`
   - Timeout: `10 seconds`

7. **Create & Deploy:**
   - Review settings
   - Click "Create & deploy"
   - Wait ~5 minutes

8. **Get Your URL:**
   - App Runner provides: `https://random-id.us-east-1.awsapprunner.com`
   - Configure custom domain (optional)

### Using AWS CLI:

Create `apprunner-config.json`:

```json
{
  "SourceConfiguration": {
    "AutoDeploymentsEnabled": true,
    "CodeRepository": {
      "RepositoryUrl": "https://github.com/jdrumgoole/putplace",
      "SourceCodeVersion": {
        "Type": "BRANCH",
        "Value": "main"
      },
      "CodeConfiguration": {
        "ConfigurationSource": "API",
        "CodeConfigurationValues": {
          "Runtime": "PYTHON_3",
          "BuildCommand": "pip install -e .",
          "StartCommand": "uvicorn putplace.main:app --host 0.0.0.0 --port 8000 --workers 4",
          "Port": "8000",
          "RuntimeEnvironmentVariables": {
            "MONGODB_URL": "your-mongodb-url",
            "STORAGE_BACKEND": "s3",
            "S3_BUCKET_NAME": "putplace-files"
          }
        }
      }
    }
  },
  "InstanceConfiguration": {
    "Cpu": "1 vCPU",
    "Memory": "2 GB"
  },
  "HealthCheckConfiguration": {
    "Protocol": "HTTP",
    "Path": "/health",
    "Interval": 30,
    "Timeout": 10,
    "HealthyThreshold": 1,
    "UnhealthyThreshold": 3
  },
  "AutoScalingConfigurationArn": "arn:aws:apprunner:region:account:autoscalingconfiguration/DefaultConfiguration"
}
```

Deploy:

```bash
aws apprunner create-service \
  --service-name putplace-api \
  --source-configuration file://apprunner-config.json \
  --region us-east-1
```

## Step 5: Create S3 Bucket for File Storage

```bash
# Create bucket
aws s3 mb s3://putplace-files --region us-east-1

# Enable versioning (optional)
aws s3api put-bucket-versioning \
  --bucket putplace-files \
  --versioning-configuration Status=Enabled

# Set lifecycle policy (optional - delete old files after 90 days)
cat > lifecycle.json <<EOF
{
  "Rules": [{
    "Status": "Enabled",
    "Id": "DeleteOldFiles",
    "Expiration": {
      "Days": 90
    }
  }]
}
EOF

aws s3api put-bucket-lifecycle-configuration \
  --bucket putplace-files \
  --lifecycle-configuration file://lifecycle.json
```

## Step 6: Configure IAM Role for S3 Access

App Runner needs permissions to access S3:

1. **Create IAM Policy** (`putplace-s3-policy.json`):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::putplace-files",
        "arn:aws:s3:::putplace-files/*"
      ]
    }
  ]
}
```

2. **Create and attach policy:**

```bash
aws iam create-policy \
  --policy-name PutPlaceS3Access \
  --policy-document file://putplace-s3-policy.json

# Attach to App Runner instance role (created automatically)
# Or specify custom role in App Runner configuration
```

## Step 7: Test Deployment

```bash
# Get App Runner URL
APP_URL=$(aws apprunner list-services --query 'ServiceSummaryList[?ServiceName==`putplace-api`].ServiceUrl' --output text)

# Test health endpoint
curl https://$APP_URL/health

# Test API
curl https://$APP_URL/

# Check docs
open https://$APP_URL/docs
```

## Step 8: Configure Custom Domain (Optional)

1. **In App Runner Console:**
   - Service → Custom domains → Add domain
   - Enter: `api.putplace.com`

2. **Update DNS:**
   - Add CNAME record in your DNS provider:
     ```
     api.putplace.com → random-id.us-east-1.awsapprunner.com
     ```

3. **SSL Certificate:**
   - App Runner automatically provisions SSL via AWS Certificate Manager

---

# Option 2: ECS Fargate (More Control)

Best for: Production workloads requiring more control, multiple services

## Architecture

```
ALB → ECS Fargate → MongoDB Atlas/DocumentDB
       (Auto-scaling)
           ↓
         S3
```

## Quick Setup

1. **Create ECR Repository:**

```bash
aws ecr create-repository --repository-name putplace --region us-east-1
```

2. **Build and Push Docker Image:**

```bash
# Login to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

# Build
docker build -t putplace .

# Tag
docker tag putplace:latest ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/putplace:latest

# Push
docker push ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/putplace:latest
```

3. **Create ECS Cluster:**

```bash
aws ecs create-cluster --cluster-name putplace-cluster --region us-east-1
```

4. **Create Task Definition:**

See `ecs-task-definition.json` below.

5. **Create Service with ALB:**

```bash
aws ecs create-service \
  --cluster putplace-cluster \
  --service-name putplace-api \
  --task-definition putplace \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}" \
  --load-balancers "targetGroupArn=arn:aws:elasticloadbalancing:...,containerName=putplace,containerPort=8000"
```

**Full ECS setup guide:** See separate `ECS_DEPLOYMENT.md` (can create if needed)

---

# Option 3: EC2 + Docker Compose (Cost-Effective)

Best for: Small deployments, cost-conscious teams, full control

## Quick Setup

1. **Launch EC2 Instance:**
   - AMI: Amazon Linux 2023
   - Instance type: `t3.medium` (2 vCPU, 4 GB RAM)
   - Security Group: Allow 80, 443, 22

2. **Install Docker:**

```bash
#!/bin/bash
# User data script
yum update -y
yum install -y docker git
systemctl start docker
systemctl enable docker
usermod -aG docker ec2-user

# Install Docker Compose
curl -L "https://github.com/docker/compose/releases/download/v2.23.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose
```

3. **Deploy with Docker Compose:**

Create `docker-compose.yml` on EC2:

```yaml
version: '3.8'

services:
  putplace:
    image: python:3.12-slim
    container_name: putplace-api
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - MONGODB_URL=${MONGODB_URL}
      - MONGODB_DATABASE=putplace
      - STORAGE_BACKEND=s3
      - S3_BUCKET_NAME=putplace-files
      - AWS_REGION=us-east-1
    volumes:
      - ./src:/app/src
      - ./pyproject.toml:/app/pyproject.toml
    working_dir: /app
    command: >
      bash -c "pip install uv &&
               uv pip install --system -e . &&
               uvicorn putplace.main:app --host 0.0.0.0 --port 8000 --workers 4"

  # Optional: Local MongoDB (instead of Atlas)
  mongodb:
    image: mongo:7
    container_name: putplace-mongo
    restart: unless-stopped
    ports:
      - "27017:27017"
    volumes:
      - mongo-data:/data/db
    environment:
      - MONGO_INITDB_ROOT_USERNAME=admin
      - MONGO_INITDB_ROOT_PASSWORD=your-password

  # Nginx reverse proxy with SSL
  nginx:
    image: nginx:alpine
    container_name: putplace-nginx
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - putplace

volumes:
  mongo-data:
```

4. **Start Services:**

```bash
docker-compose up -d
```

**Full EC2 setup guide:** See separate `EC2_DEPLOYMENT.md` (can create if needed)

---

# Environment Variables Reference

Configure these in your deployment platform:

## Required

```bash
# Database
MONGODB_URL=mongodb+srv://user:pass@cluster.mongodb.net/putplace
MONGODB_DATABASE=putplace
MONGODB_COLLECTION=file_metadata

# Storage
STORAGE_BACKEND=s3  # or "local"
S3_BUCKET_NAME=putplace-files
AWS_REGION=us-east-1
```

## Optional

```bash
# OAuth
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com

# Admin User (first startup only)
PUTPLACE_ADMIN_USERNAME=admin
PUTPLACE_ADMIN_PASSWORD=secure-password
PUTPLACE_ADMIN_EMAIL=admin@example.com

# AWS (if not using IAM roles)
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key

# API Settings
API_TITLE=PutPlace API
API_VERSION=0.5.1
```

---

# Cost Estimates

## App Runner (Recommended)

- **Base:** $0.007/vCPU-hour + $0.0008/GB-hour
- **Requests:** $0.10/1M requests
- **Monthly estimate:**
  - 1 vCPU, 2 GB RAM, running 24/7: ~$25-30/month
  - + 1M requests: +$0.10
  - **Total: ~$30-40/month**

## ECS Fargate

- **Compute:** $0.04048/vCPU-hour + $0.004445/GB-hour
- **ALB:** $16.20/month + $0.008/LCU-hour
- **Monthly estimate:**
  - 2 tasks (1 vCPU, 2 GB each), 24/7: ~$60-70/month
  - ALB: ~$20/month
  - **Total: ~$80-100/month**

## EC2 + Docker

- **t3.medium:** $0.0416/hour = ~$30/month
- **EBS:** 30 GB = ~$3/month
- **Data transfer:** ~$5-10/month
- **Total: ~$40-50/month**

## Shared Costs (All Options)

- **MongoDB Atlas M10:** ~$57/month (or M0 free tier)
- **S3 Storage:** $0.023/GB/month (~$2-5/month for typical usage)
- **Data Transfer:** ~$0.09/GB out

---

# Security Best Practices

1. **Use Secrets Manager for sensitive data:**

```bash
aws secretsmanager create-secret \
  --name putplace/mongodb-url \
  --secret-string "mongodb+srv://..."

# Reference in App Runner environment variables
```

2. **Enable VPC for private connectivity:**
   - Use AWS PrivateLink for MongoDB Atlas
   - Keep services in private subnets

3. **Set up WAF for API protection:**

```bash
aws wafv2 create-web-acl \
  --name putplace-waf \
  --scope REGIONAL \
  --default-action Allow={} \
  --rules file://waf-rules.json
```

4. **Enable CloudWatch Logs and Alarms**

5. **Use IAM roles instead of access keys**

---

# Monitoring & Logging

## CloudWatch Configuration

```bash
# Create log group
aws logs create-log-group --log-group-name /aws/apprunner/putplace-api

# Set retention
aws logs put-retention-policy \
  --log-group-name /aws/apprunner/putplace-api \
  --retention-in-days 30
```

## Application Insights

Add to your FastAPI app:

```python
# In main.py
import boto3

cloudwatch = boto3.client('cloudwatch')

@app.middleware("http")
async def log_metrics(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start

    cloudwatch.put_metric_data(
        Namespace='PutPlace',
        MetricData=[{
            'MetricName': 'RequestDuration',
            'Value': duration,
            'Unit': 'Seconds'
        }]
    )
    return response
```

---

# CI/CD Pipeline

## GitHub Actions (Recommended)

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to AWS App Runner

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v2
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1

      - name: Deploy to App Runner
        run: |
          aws apprunner start-deployment \
            --service-arn ${{ secrets.APP_RUNNER_SERVICE_ARN }}
```

---

# Next Steps

1. ✅ Choose deployment option (App Runner recommended)
2. ✅ Set up MongoDB Atlas or DocumentDB
3. ✅ Create Dockerfile
4. ✅ Deploy to AWS
5. ✅ Configure environment variables
6. ✅ Set up custom domain
7. ✅ Enable monitoring
8. ✅ Set up CI/CD

## Need Help?

- [AWS App Runner Docs](https://docs.aws.amazon.com/apprunner/)
- [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/)
- [MongoDB Atlas AWS Integration](https://www.mongodb.com/atlas/aws)

Would you like me to create detailed guides for any specific deployment option?
