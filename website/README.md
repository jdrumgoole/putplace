# PutPlace Website

This directory contains the static website for putplace.org.

## Automatic Deployment

The website is automatically deployed to S3 + CloudFront when changes are pushed to the `main` branch.

### GitHub Actions Workflow

The `.github/workflows/deploy-website.yml` workflow:
1. Detects changes to the `website/` directory
2. Syncs files to S3 bucket: `s3://putplace.org/`
3. Invalidates CloudFront cache for immediate updates

### Manual Deployment

You can also deploy manually using the invoke task:

```bash
invoke deploy-website
```

This will:
- Upload all files from `website/` to S3
- Set appropriate cache control headers
- Invalidate CloudFront cache

## File Structure

- `index.html` - Main landing page
- `error.html` - 404 error page
- `README.md` - This file

## Development

To test the website locally:

```bash
# Using Python's built-in HTTP server
cd website
python -m http.server 8080

# Then visit http://localhost:8080
```

## URLs

- **Production**: https://putplace.org
- **API**: https://app.putplace.org
- **API Docs**: https://app.putplace.org/docs

## Infrastructure

The website is hosted on:
- **S3**: Static file storage
- **CloudFront**: CDN with SSL/TLS certificate
- **Route 53**: DNS management
- **ACM**: SSL certificate for HTTPS

All infrastructure is managed via invoke tasks in `tasks.py`:
- `invoke setup-static-website` - Initial setup
- `invoke create-cloudfront-distribution` - CloudFront configuration
- `invoke deploy-website` - Deploy content
