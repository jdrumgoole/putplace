# PutPlace Deployment Scripts

This directory contains deployment scripts and configurations for various platforms.

## Quick Deployment Options

### 1. Docker Compose (Local/Testing)

```bash
# From project root
docker-compose up -d

# Access API
open http://localhost:8000/docs

# View logs
docker-compose logs -f putplace

# Stop
docker-compose down
```

### 2. AWS App Runner (Production - Recommended)

See `../AWS_DEPLOYMENT_GUIDE.md` for complete instructions.

Quick deploy:

```bash
# Build and test locally first
docker build -t putplace .
docker run -p 8000:8000 \
  -e MONGODB_URL=mongodb://localhost:27017 \
  putplace

# Deploy to App Runner in Ireland (default)
python deploy/app_runner_deploy.py

# Deploy to specific region
python deploy/app_runner_deploy.py --region us-east-1

# Non-interactive deployment
export MONGODB_URL="mongodb+srv://user:pass@cluster.mongodb.net/putplace"
export S3_BUCKET_NAME="putplace-files"
python deploy/app_runner_deploy.py --non-interactive
```

### 3. AWS ECS Fargate

```bash
# Coming soon - see AWS_DEPLOYMENT_GUIDE.md for manual setup
```

### 4. AWS EC2

```bash
# Coming soon - see AWS_DEPLOYMENT_GUIDE.md for manual setup
```

## Files

- `app_runner_deploy.py` - Python script to deploy to AWS App Runner (Ireland by default)
- `README.md` - This file

## Environment Variables

Create `.env` file or set in deployment platform:

```bash
# Required
MONGODB_URL=mongodb+srv://user:pass@cluster.mongodb.net/putplace
STORAGE_BACKEND=s3
S3_BUCKET_NAME=putplace-files
AWS_REGION=us-east-1

# Optional
GOOGLE_CLIENT_ID=your-client-id
PUTPLACE_ADMIN_USERNAME=admin
PUTPLACE_ADMIN_PASSWORD=secure-password
PUTPLACE_ADMIN_EMAIL=admin@example.com
```

## Cost Comparison

| Option | Monthly Cost | Setup Time | Auto-scaling |
|--------|-------------|------------|--------------|
| Docker Compose (local) | $0 | 5 min | No |
| AWS App Runner | $30-50 | 10 min | Yes |
| AWS ECS Fargate | $80-100 | 30 min | Yes |
| AWS EC2 (t3.medium) | $40-50 | 20 min | Manual |

## Support

See main [AWS_DEPLOYMENT_GUIDE.md](../AWS_DEPLOYMENT_GUIDE.md) for detailed documentation.
