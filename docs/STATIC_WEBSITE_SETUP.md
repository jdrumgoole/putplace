# Static Website Setup for putplace.org

This guide explains the static website infrastructure for putplace.org.

## Architecture

```
┌──────────────┐
│    User      │
└──────┬───────┘
       │ HTTPS
       ▼
┌──────────────────────┐
│   Route 53 DNS       │
│  putplace.org        │
│  www.putplace.org    │
└──────┬───────────────┘
       │ Alias A record
       ▼
┌──────────────────────┐
│   CloudFront CDN     │
│  SSL/TLS Certificate │
│  Edge Caching        │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│   S3 Bucket          │
│  putplace.org        │
│  Static Hosting      │
└──────────────────────┘
```

## Infrastructure Components

### 1. S3 Bucket
- **Bucket name**: `putplace.org`
- **Purpose**: Static file storage
- **Configuration**:
  - Website hosting enabled
  - Public read access
  - Index document: `index.html`
  - Error document: `error.html`

### 2. CloudFront Distribution
- **Distribution ID**: `E1HNPSKP2YEUNY`
- **Domain**: `d293jmofsozqjv.cloudfront.net`
- **Purpose**: CDN with SSL/TLS
- **Configuration**:
  - HTTPS only (redirect HTTP to HTTPS)
  - Gzip compression enabled
  - Cache TTL: 24 hours (86400s)
  - Custom domain aliases: `putplace.org`, `www.putplace.org`

### 3. SSL/TLS Certificate
- **Service**: AWS Certificate Manager (ACM)
- **ARN**: `arn:aws:acm:us-east-1:230950121080:certificate/2c313e33-db37-46a1-920b-9c76d7e7e641`
- **Domains**: `putplace.org`, `www.putplace.org`
- **Validation**: DNS (automatic via Route 53)
- **Region**: us-east-1 (required for CloudFront)

### 4. Route 53 DNS
- **Hosted Zone**: `Z0368516WAMZPIIC7ZI` (putplace.org)
- **Records**:
  - `putplace.org` → Alias A record to CloudFront
  - `www.putplace.org` → Alias A record to CloudFront
  - Certificate validation CNAME records

## Setup Process

### Initial Setup (Already Completed)

```bash
# 1. Create S3 bucket, certificate, and DNS records
invoke setup-static-website --domain=putplace.org

# 2. Wait for certificate validation (~5-10 minutes)
# The task automatically creates Route 53 validation records

# 3. Create CloudFront distribution
invoke create-cloudfront-distribution --domain=putplace.org

# 4. Deploy website content
invoke deploy-website --source-dir=website
```

### Manual Steps if Needed

**Create S3 Bucket:**
```bash
aws s3api create-bucket --bucket putplace.org --region us-east-1

# Configure website hosting
aws s3api put-bucket-website \
  --bucket putplace.org \
  --website-configuration file:///tmp/website-config.json

# Set public read policy
aws s3api put-bucket-policy \
  --bucket putplace.org \
  --policy file:///tmp/bucket-policy.json
```

**Request SSL Certificate:**
```bash
aws acm request-certificate \
  --domain-name putplace.org \
  --subject-alternative-names www.putplace.org \
  --validation-method DNS \
  --region us-east-1
```

**Create CloudFront Distribution:**
```bash
aws cloudfront create-distribution \
  --distribution-config file:///tmp/cloudfront-config.json
```

## Deployment

### Automatic Deployment (Recommended)

The website deploys automatically when you push changes to the `main` branch:

```bash
# Make changes to website content
cd website
vim index.html

# Commit and push
git add .
git commit -m "Update homepage"
git push

# GitHub Actions automatically:
# 1. Syncs files to S3
# 2. Invalidates CloudFront cache
# 3. Website updates within 1-2 minutes
```

### Manual Deployment

```bash
# Deploy website content
invoke deploy-website --source-dir=website

# This will:
# - Sync all files to S3
# - Set cache-control headers (5 minutes)
# - Invalidate CloudFront cache
```

### Deploy from Different Directory

```bash
# Deploy Sphinx documentation
invoke deploy-website --source-dir=docs/_build/html
```

## GitHub Actions Workflow

The workflow (`.github/workflows/deploy-website.yml`) triggers on:
- Push to `main` branch with changes to `website/` directory
- Manual workflow dispatch

**Setup Requirements:**

1. **AWS IAM OIDC Provider** (if not already configured):
```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

2. **IAM Role for GitHub Actions**:
```bash
# Create role with trust policy for GitHub Actions
aws iam create-role \
  --role-name GitHubActionsDeployWebsite \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::230950121080:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:jdrumgoole/putplace:*"
        }
      }
    }]
  }'

# Attach policies for S3 and CloudFront access
aws iam attach-role-policy \
  --role-name GitHubActionsDeployWebsite \
  --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess

aws iam attach-role-policy \
  --role-name GitHubActionsDeployWebsite \
  --policy-arn arn:aws:iam::aws:policy/CloudFrontFullAccess
```

3. **Add GitHub Secret**:
```bash
# Add AWS_DEPLOY_ROLE_ARN to GitHub repository secrets
# Value: arn:aws:iam::230950121080:role/GitHubActionsDeployWebsite
```

## Website Content

### File Structure

```
website/
├── index.html      # Main landing page
├── error.html      # 404 error page
└── README.md       # Documentation
```

### Adding New Pages

```bash
# Create new page
cat > website/about.html << EOF
<!DOCTYPE html>
<html>
<head><title>About PutPlace</title></head>
<body>
  <h1>About PutPlace</h1>
  <p>Information about the service...</p>
</body>
</html>
EOF

# Deploy
git add website/about.html
git commit -m "Add about page"
git push  # Automatically deploys

# Access at: https://putplace.org/about.html
```

### Local Testing

```bash
# Test website locally before deploying
cd website
python -m http.server 8080

# Visit http://localhost:8080
```

## Monitoring and Maintenance

### Check CloudFront Status

```bash
# View distribution status
aws cloudfront get-distribution --id E1HNPSKP2YEUNY

# Check if deployed
aws cloudfront get-distribution \
  --id E1HNPSKP2YEUNY \
  --query 'Distribution.Status' \
  --output text
# Output: Deployed (ready) or InProgress (deploying)
```

### View Access Logs

CloudFront and S3 access logs can be enabled if needed:

```bash
# Enable S3 logging
aws s3api put-bucket-logging \
  --bucket putplace.org \
  --bucket-logging-status file:///tmp/logging-config.json
```

### Cache Invalidation

```bash
# Invalidate specific files
aws cloudfront create-invalidation \
  --distribution-id E1HNPSKP2YEUNY \
  --paths '/index.html' '/about.html'

# Invalidate everything
aws cloudfront create-invalidation \
  --distribution-id E1HNPSKP2YEUNY \
  --paths '/*'
```

### View Metrics

```bash
# CloudFront metrics in CloudWatch
aws cloudwatch get-metric-statistics \
  --namespace AWS/CloudFront \
  --metric-name Requests \
  --dimensions Name=DistributionId,Value=E1HNPSKP2YEUNY \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-02T00:00:00Z \
  --period 3600 \
  --statistics Sum
```

## DNS Configuration

### Current DNS Records

```bash
# View all DNS records for putplace.org
aws route53 list-resource-record-sets \
  --hosted-zone-id Z0368516WAMZPIIC7ZI \
  --query "ResourceRecordSets[?contains(Name, 'putplace.org')]"
```

**Key Records:**
- `putplace.org` (A) → CloudFront alias
- `www.putplace.org` (A) → CloudFront alias
- `app.putplace.org` (CNAME) → App Runner API
- Certificate validation CNAMEs

### Testing DNS Propagation

```bash
# Test CNAME resolution
dig putplace.org A +short
# Should return CloudFront IPs

dig www.putplace.org A +short
# Should return CloudFront IPs

# Test from different DNS servers
dig @8.8.8.8 putplace.org A +short
dig @1.1.1.1 putplace.org A +short
```

## Costs

**Monthly Cost Estimate:**

- **S3 Storage**: ~$0.023/GB = ~$0.10/month (5 GB)
- **S3 Requests**: $0.0004 per 1000 GET = ~$0.40/month (1M requests)
- **CloudFront**: First 1 TB free, then $0.085/GB
- **Route 53**: $0.50/month (hosted zone)
- **ACM Certificate**: FREE

**Total**: ~$1-5/month for typical usage

## Troubleshooting

### Website Not Loading

**Check CloudFront status:**
```bash
aws cloudfront get-distribution --id E1HNPSKP2YEUNY
```
- Status should be "Deployed"
- Initial deployment takes 15-20 minutes

**Check DNS:**
```bash
dig putplace.org A +short
```
- Should return CloudFront IP addresses
- DNS propagation can take 5-10 minutes

**Check S3 bucket:**
```bash
aws s3 ls s3://putplace.org/
```
- Should show index.html and other files

### Certificate Issues

```bash
# Check certificate status
aws acm describe-certificate \
  --certificate-arn arn:aws:acm:us-east-1:230950121080:certificate/2c313e33-db37-46a1-920b-9c76d7e7e641 \
  --region us-east-1

# Should show Status: ISSUED
# Both domains should show ValidationStatus: SUCCESS
```

### 404 Errors

```bash
# Ensure error.html exists in S3
aws s3 ls s3://putplace.org/error.html

# Upload if missing
aws s3 cp website/error.html s3://putplace.org/
```

### Cache Not Invalidating

```bash
# Create manual invalidation
aws cloudfront create-invalidation \
  --distribution-id E1HNPSKP2YEUNY \
  --paths '/*'

# Check invalidation status
aws cloudfront list-invalidations \
  --distribution-id E1HNPSKP2YEUNY
```

## Security Best Practices

1. **S3 Bucket Policy**: Only allow CloudFront access (currently public read)
2. **HTTPS Only**: CloudFront enforces HTTPS
3. **WAF**: Can add AWS WAF for additional protection
4. **Origin Access Identity**: Configure CloudFront OAI for S3

**Restrict S3 to CloudFront only:**
```bash
# Update bucket policy to only allow CloudFront
# This prevents direct S3 website URL access
```

## Cleanup

To remove the static website infrastructure:

```bash
# 1. Delete CloudFront distribution
aws cloudfront delete-distribution \
  --id E1HNPSKP2YEUNY \
  --if-match <ETag>

# 2. Delete S3 bucket contents and bucket
aws s3 rm s3://putplace.org --recursive
aws s3api delete-bucket --bucket putplace.org

# 3. Delete ACM certificate
aws acm delete-certificate \
  --certificate-arn arn:aws:acm:us-east-1:230950121080:certificate/2c313e33-db37-46a1-920b-9c76d7e7e641 \
  --region us-east-1

# 4. Remove Route 53 DNS records
# (Keep the hosted zone if using other services)
```

## Support and Documentation

- **AWS CloudFront**: https://docs.aws.amazon.com/cloudfront/
- **AWS S3 Static Hosting**: https://docs.aws.amazon.com/AmazonS3/latest/userguide/WebsiteHosting.html
- **AWS Certificate Manager**: https://docs.aws.amazon.com/acm/
- **GitHub Actions AWS**: https://github.com/aws-actions/configure-aws-credentials

## invoke Tasks Reference

```bash
# Setup tasks
invoke setup-static-website              # Complete S3 + CloudFront setup
invoke create-cloudfront-distribution    # Create CloudFront distribution

# Deployment tasks
invoke deploy-website                    # Deploy from website/ directory
invoke deploy-website --source-dir=docs  # Deploy from custom directory

# Monitoring tasks
aws cloudfront get-distribution --id E1HNPSKP2YEUNY  # Check status
aws s3 ls s3://putplace.org/                         # List files
```
