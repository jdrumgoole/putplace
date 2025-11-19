# AWS App Runner Deployment Guide

This guide explains how to deploy PutPlace to AWS App Runner.

## Prerequisites

- AWS account with App Runner access
- GitHub repository containing the PutPlace code
- MongoDB instance (MongoDB Atlas, AWS DocumentDB, or self-hosted)
- AWS CLI installed and configured (optional, for CLI deployment)

## Architecture

```
┌─────────────────┐
│   App Runner    │
│   (PutPlace)    │
│   Port: 8000    │
└────────┬────────┘
         │
         │ HTTPS
         │
┌────────▼────────┐
│    MongoDB      │
│  (Atlas/DocDB)  │
└─────────────────┘
```

## Deployment Methods

### Method 1: Deploy via AWS Console (Recommended)

#### Step 1: Prepare MongoDB Connection

**Option A: MongoDB Atlas (Recommended)**
1. Create a free cluster at [MongoDB Atlas](https://www.mongodb.com/cloud/atlas)
2. Create a database user
3. Whitelist App Runner IP ranges (or use `0.0.0.0/0` for testing)
4. Get connection string: `mongodb+srv://username:password@cluster.mongodb.net/putplace`

**Option B: AWS DocumentDB**
1. Create a DocumentDB cluster in the same VPC
2. Get connection string: `mongodb://username:password@docdb-cluster.cluster-xxxxx.region.docdb.amazonaws.com:27017/putplace`

#### Step 2: Deploy to App Runner

1. Go to [App Runner Console](https://console.aws.amazon.com/apprunner/)
2. Click **Create service**

**Configure Source:**
- **Source**: Repository
- **Provider**: GitHub
- **Connect to GitHub** and authorize AWS App Runner
- **Repository**: Select your PutPlace repository
- **Branch**: `main`
- **Deployment trigger**: Automatic (or Manual)

**Configure Build:**
- **Configuration file**: Use configuration file (`apprunner.yaml`)
- The `apprunner.yaml` file defines:
  - Runtime: Python 3.11
  - Build commands: Install dependencies with uv
  - Run command: Start uvicorn server with 2 workers
  - Health check: `/health` endpoint

**Configure Service:**
- **Service name**: `putplace-api`
- **Virtual CPU**: 1 vCPU (can scale up later)
- **Memory**: 2 GB (can scale up later)

**Configure Environment Variables:**

Add these required environment variables in the console:

| Variable | Value | Example |
|----------|-------|---------|
| `MONGODB_URL` | MongoDB connection string | `mongodb+srv://user:pass@cluster.mongodb.net/` |
| `MONGODB_DATABASE` | Database name | `putplace` |
| `MONGODB_COLLECTION` | Collection name | `file_metadata` |
| `AWS_DEFAULT_REGION` | AWS region | `eu-west-1` |

Optional variables:
- `API_TITLE`: Custom API title (default: "PutPlace File Metadata API")
- `API_DESCRIPTION`: Custom description

**Configure Security:**
- **IAM role**: Create new role or use existing with:
  - `AWSAppRunnerServicePolicyForECRAccess` (if using ECR)
  - Custom policy for SES if using email features:
    ```json
    {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Allow",
          "Action": ["ses:SendEmail", "ses:SendRawEmail"],
          "Resource": "*"
        }
      ]
    }
    ```

**Configure Auto Scaling (Optional):**
- Min instances: 1
- Max instances: 3
- Max concurrency: 100 requests per instance

3. Click **Create & deploy**
4. Wait 5-10 minutes for deployment

#### Step 3: Test the Deployment

Once deployed, App Runner provides a URL like:
```
https://xxxxx.us-east-1.awsapprunner.com
```

Test the endpoints:
```bash
# Health check
curl https://xxxxx.us-east-1.awsapprunner.com/health

# API docs
open https://xxxxx.us-east-1.awsapprunner.com/docs

# Store file metadata
curl -X POST https://xxxxx.us-east-1.awsapprunner.com/put_file \
  -H "Content-Type: application/json" \
  -d '{
    "filepath": "/test/file.txt",
    "hostname": "test-host",
    "ip_address": "192.168.1.1",
    "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  }'
```

### Method 2: Deploy via AWS CLI

```bash
# Create service with configuration file
aws apprunner create-service \
  --service-name putplace-api \
  --source-configuration '{
    "CodeRepository": {
      "RepositoryUrl": "https://github.com/yourusername/putplace",
      "SourceCodeVersion": {
        "Type": "BRANCH",
        "Value": "main"
      },
      "CodeConfiguration": {
        "ConfigurationSource": "API",
        "CodeConfigurationValues": {
          "Runtime": "PYTHON_3",
          "BuildCommand": "pip install -e . && pip install -e .[s3]",
          "StartCommand": "uvicorn putplace.main:app --host 0.0.0.0 --port 8000 --workers 2",
          "Port": "8000",
          "RuntimeEnvironmentVariables": {
            "MONGODB_URL": "your-mongodb-connection-string",
            "MONGODB_DATABASE": "putplace",
            "MONGODB_COLLECTION": "file_metadata",
            "PYTHONUNBUFFERED": "1"
          }
        }
      }
    },
    "AutoDeploymentsEnabled": true
  }' \
  --instance-configuration '{
    "Cpu": "1 vCPU",
    "Memory": "2 GB"
  }' \
  --health-check-configuration '{
    "Protocol": "HTTP",
    "Path": "/health",
    "Interval": 10,
    "Timeout": 5,
    "HealthyThreshold": 1,
    "UnhealthyThreshold": 5
  }' \
  --region us-east-1
```

### Method 3: Deploy with Docker (Alternative)

If you prefer using the Docker image:

1. Build and push to ECR:
```bash
# Create ECR repository
aws ecr create-repository --repository-name putplace --region us-east-1

# Get login credentials
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com

# Build and push
docker build -t putplace .
docker tag putplace:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/putplace:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/putplace:latest
```

2. Create App Runner service with ECR source:
```bash
aws apprunner create-service \
  --service-name putplace-api \
  --source-configuration '{
    "ImageRepository": {
      "ImageIdentifier": "<account-id>.dkr.ecr.us-east-1.amazonaws.com/putplace:latest",
      "ImageRepositoryType": "ECR",
      "ImageConfiguration": {
        "Port": "8000",
        "RuntimeEnvironmentVariables": {
          "MONGODB_URL": "your-mongodb-connection-string"
        }
      }
    },
    "AutoDeploymentsEnabled": true
  }' \
  --region us-east-1
```

## Configuration Details

### apprunner.yaml Structure

The `apprunner.yaml` file contains:

```yaml
version: 1.0
runtime: python311

build:
  commands:
    pre-build:
      - Install uv package manager
    build:
      - Install Python dependencies
    post-build:
      - Verify installation

run:
  runtime-version: "3.11"
  command: uvicorn putplace.main:app --host 0.0.0.0 --port 8000 --workers 2
  network:
    port: 8000
  env:
    - Environment variables (see file for details)

health-check:
  protocol: http
  path: /health
  interval: 10
  timeout: 5
```

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MONGODB_URL` | Yes | - | MongoDB connection string |
| `MONGODB_DATABASE` | No | `putplace` | Database name |
| `MONGODB_COLLECTION` | No | `file_metadata` | Collection name |
| `API_TITLE` | No | `PutPlace API` | API documentation title |
| `API_VERSION` | No | `0.5.8` | API version |
| `PYTHONUNBUFFERED` | No | `1` | Python output buffering |
| `AWS_DEFAULT_REGION` | No | `us-east-1` | AWS region for SES |

### Using AWS Secrets Manager (Recommended for Production)

Store sensitive credentials in Secrets Manager:

1. Create secret:
```bash
aws secretsmanager create-secret \
  --name putplace/mongodb \
  --secret-string '{"MONGODB_URL":"mongodb+srv://user:pass@cluster.mongodb.net/putplace"}' \
  --region us-east-1
```

2. Grant App Runner access:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["secretsmanager:GetSecretValue"],
      "Resource": "arn:aws:secretsmanager:us-east-1:*:secret:putplace/*"
    }
  ]
}
```

3. Reference in environment:
```yaml
env:
  - name: MONGODB_URL
    value-from:
      type: secret
      name: putplace/mongodb
      key: MONGODB_URL
```

## Monitoring and Logs

### View Logs

**AWS Console:**
1. Go to App Runner service
2. Click **Logs** tab
3. View application and deployment logs

**AWS CLI:**
```bash
# Stream application logs
aws logs tail /aws/apprunner/putplace-api/application --follow

# Stream deployment logs
aws logs tail /aws/apprunner/putplace-api/service --follow
```

### CloudWatch Metrics

App Runner automatically creates CloudWatch metrics:
- Request count
- Request latency (p50, p90, p99)
- 4xx/5xx error rates
- Instance count
- CPU/Memory utilization

Access at: CloudWatch Console → Metrics → AppRunner

### Custom Application Metrics

The PutPlace API exposes:
- `/health` - Health check endpoint
- `/metrics` - Prometheus-style metrics (if enabled)

## Troubleshooting

### Common Issues

**1. Build Fails**
```
Error: Failed to install dependencies
```
**Solution:**
- Check `apprunner.yaml` syntax
- Verify Python version compatibility (3.10+)
- Check build logs in CloudWatch

**2. Application Fails to Start**
```
Error: Health check failed
```
**Solution:**
- Verify MongoDB connection string is correct
- Check MongoDB network access (whitelist App Runner IPs)
- Review application logs in CloudWatch
- Test `/health` endpoint locally

**3. MongoDB Connection Timeout**
```
Error: Failed to connect to MongoDB
```
**Solution:**
- For MongoDB Atlas: Whitelist `0.0.0.0/0` (or App Runner NAT Gateway IPs)
- For DocumentDB: Ensure App Runner service is in same VPC
- Verify connection string format
- Check MongoDB user permissions

**4. High Memory Usage**
```
Error: Container exceeded memory limit
```
**Solution:**
- Reduce worker count: `--workers 1`
- Increase instance memory to 3 GB or 4 GB
- Enable auto-scaling with more instances

### Debug Tips

1. **Test locally with same environment:**
```bash
export MONGODB_URL="your-connection-string"
export MONGODB_DATABASE="putplace"
uvicorn putplace.main:app --host 0.0.0.0 --port 8000 --workers 2
```

2. **Check MongoDB connectivity:**
```bash
python -c "from pymongo import MongoClient; client = MongoClient('your-mongodb-url'); print(client.server_info())"
```

3. **Enable verbose logging:**
Add to environment variables:
```
LOG_LEVEL=debug
```

## Costs

App Runner pricing (as of 2024):
- **Provisioned instances**: ~$0.007/hour per GB memory + $0.04/hour per vCPU
- **Request pricing**: $0.40 per million requests
- **Data transfer**: Standard AWS rates

**Example monthly cost:**
- 1 instance (1 vCPU, 2 GB): ~$50-60/month
- + 1M requests: ~$0.40
- + MongoDB Atlas Free Tier: $0
- **Total: ~$50-60/month**

## Scaling

### Automatic Scaling
App Runner automatically scales based on:
- Request volume
- CPU utilization
- Memory usage

Configure in service settings:
- Min instances: 1
- Max instances: 10
- Concurrency: 100 requests/instance

### Manual Scaling
Increase instance resources:
- CPU: 0.25, 0.5, 1, 2, 4 vCPU
- Memory: 0.5, 1, 2, 3, 4 GB

## Security Best Practices

1. **Use VPC Connector** (for private MongoDB):
   - Create VPC connector
   - Connect to private DocumentDB or RDS

2. **Enable AWS WAF**:
   - Protect against common web exploits
   - Rate limiting

3. **Use Secrets Manager**:
   - Store MongoDB credentials securely
   - Rotate credentials automatically

4. **Enable HTTPS only**:
   - App Runner provides automatic SSL/TLS
   - Custom domains supported

5. **IAM roles**:
   - Least privilege access
   - Separate roles for build and runtime

## Custom Domain

1. **Add custom domain:**
```bash
aws apprunner associate-custom-domain \
  --service-arn arn:aws:apprunner:region:account:service/putplace-api \
  --domain-name api.yourdomain.com
```

2. **Update DNS:**
Add CNAME records as instructed by App Runner

3. **SSL Certificate:**
App Runner automatically provisions and manages SSL certificates

## CI/CD Integration

App Runner integrates with:
- **GitHub**: Automatic deployments on push
- **ECR**: Automatic deployments on image push
- **CodePipeline**: Custom deployment workflows

Enable automatic deployments in service configuration.

## Additional Resources

- [AWS App Runner Documentation](https://docs.aws.amazon.com/apprunner/)
- [MongoDB Atlas Documentation](https://docs.atlas.mongodb.com/)
- [PutPlace Documentation](./README.md)
- [FastAPI Deployment Guide](https://fastapi.tiangolo.com/deployment/)

## Support

For issues or questions:
- GitHub Issues: https://github.com/yourusername/putplace/issues
- AWS Support: https://console.aws.amazon.com/support/
