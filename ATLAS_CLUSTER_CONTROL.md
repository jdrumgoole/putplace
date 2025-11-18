# MongoDB Atlas Cluster Control

Control your MongoDB Atlas clusters directly from the command line to save costs by pausing dev/test clusters when not in use.

## Cost Savings

- **Running cluster**: Full compute + storage costs
- **Paused cluster**: ~10% of cost (storage only, no compute)
- **Example**: M10 cluster ~$60/month running → ~$6/month paused

## Setup

### 1. Create MongoDB Atlas Service Account

1. Go to [MongoDB Atlas Console](https://cloud.mongodb.com)
2. Click your profile → **"Organization Access Manager"**
3. Click **"Service Accounts"** tab
4. Click **"Create Service Account"**
5. Name it (e.g., "PutPlace Cluster Control")
6. Give it **"Organization Member"** or **"Project Owner"** permissions
7. Click **"Create"**
8. **Copy the Client ID and Client Secret** (you won't see the secret again!)
9. Save these securely - you'll need them for the next step

### 2. Get Your Project ID

1. In Atlas console, select your project
2. Click **"Settings"** in the left sidebar
3. Copy the **Project ID** (looks like: `5f8a1b2c3d4e5f6a7b8c9d0e`)

### 3. Configure Credentials

**Option A: .env File (Recommended for Local Development)**

Add to your `.env` file in the project root:

```bash
ATLAS_CLIENT_ID="your-client-id"
ATLAS_CLIENT_SECRET="your-client-secret"
ATLAS_PROJECT_ID="your-project-id"
```

**Option B: Environment Variables (Recommended for CI/CD)**

```bash
export ATLAS_CLIENT_ID="your-client-id"
export ATLAS_CLIENT_SECRET="your-client-secret"
export ATLAS_PROJECT_ID="your-project-id"
```

## Usage

### List All Clusters

```bash
invoke atlas-clusters
```

Output:
```
▶️ testcluster
  Status: IDLE
  Tier: M10
  Provider: AWS
  Region: EU_WEST_1

⏸️ dev-cluster
  Status: PAUSED
  Tier: M10
  Provider: AWS
  Region: US_EAST_1
```

### Check Cluster Status

```bash
invoke atlas-status --cluster=testcluster
```

### Pause a Cluster (Save Money!)

```bash
invoke atlas-pause --cluster=testcluster
```

Output:
```
Pausing cluster 'testcluster'...
✓ Cluster 'testcluster' is being paused
  Note: It may take a few minutes to fully pause
  Paused clusters cost ~10% of running cost (storage only)
```

### Resume a Cluster

```bash
invoke atlas-resume --cluster=testcluster
```

Output:
```
Resuming cluster 'testcluster'...
✓ Cluster 'testcluster' is being resumed
  Note: It may take 5-10 minutes for cluster to be fully operational
```

## Direct Python Usage

You can also run the script directly:

```bash
# List clusters
python -m putplace.scripts.atlas_cluster_control list

# Pause cluster
python -m putplace.scripts.atlas_cluster_control pause --cluster testcluster

# Resume cluster
python -m putplace.scripts.atlas_cluster_control resume --cluster testcluster

# Check status
python -m putplace.scripts.atlas_cluster_control status --cluster testcluster
```

## Use Cases

### Development Workflow

```bash
# Start your work day
invoke atlas-resume --cluster=dev-cluster

# ... do your development work ...

# End of day - pause to save costs
invoke atlas-pause --cluster=dev-cluster
```

### Automated Cost Management

Create a cron job or GitHub Action:

```yaml
# .github/workflows/pause-dev-clusters.yml
name: Pause Dev Clusters

on:
  schedule:
    - cron: '0 19 * * 1-5'  # 7 PM weekdays

jobs:
  pause:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Pause dev cluster
        env:
          ATLAS_PUBLIC_KEY: ${{ secrets.ATLAS_PUBLIC_KEY }}
          ATLAS_PRIVATE_KEY: ${{ secrets.ATLAS_PRIVATE_KEY }}
          ATLAS_PROJECT_ID: ${{ secrets.ATLAS_PROJECT_ID }}
        run: |
          pip install requests
          python -m putplace.scripts.atlas_cluster_control pause --cluster dev-cluster
```

### CI/CD Integration

Resume cluster before tests, pause after:

```bash
# Before integration tests
invoke atlas-resume --cluster=test-cluster

# Wait for cluster to be ready
sleep 300  # 5 minutes

# Run tests
pytest tests/

# After tests - pause to save costs
invoke atlas-pause --cluster=test-cluster
```

## Troubleshooting

### "MongoDB Atlas credentials not found"

Make sure you've set either:
- Environment variables: `ATLAS_PUBLIC_KEY`, `ATLAS_PRIVATE_KEY`, `ATLAS_PROJECT_ID`
- Credentials file: `~/.atlas/credentials`

### "401 Unauthorized"

Your API keys might be incorrect or expired. Generate new ones in Atlas console.

### "Forbidden" or "403"

Your API key doesn't have sufficient permissions. It needs "Organization Member" or "Project Owner" role.

### "Cluster not found"

- Check the cluster name is correct (case-sensitive)
- Verify you're using the correct Project ID
- List all clusters: `invoke atlas-clusters`

### "IP not whitelisted"

Add your current IP to the API access list in Atlas console:
1. Go to Organization Settings → API Keys
2. Find your API key
3. Add your IP address to the access list

## Cost Comparison Example

**M10 Cluster in Ireland (eu-west-1):**

| State | Monthly Cost | Savings |
|-------|-------------|---------|
| Running 24/7 | ~$60 | - |
| Paused 12 hours/day | ~$33 | ~$27 (45%) |
| Paused weekends | ~$43 | ~$17 (28%) |
| Paused nights + weekends | ~$25 | ~$35 (58%) |

**Best Practice for Dev/Test:**
- Pause during nights (8 PM - 8 AM)
- Pause during weekends
- Can save 50-60% on cluster costs!

## API Reference

The script uses MongoDB Atlas Administration API v2:
- Base URL: `https://cloud.mongodb.com/api/atlas/v2`
- Documentation: https://www.mongodb.com/docs/atlas/reference/api-resources-spec/

Endpoints used:
- `GET /groups/{projectId}/clusters` - List clusters
- `GET /groups/{projectId}/clusters/{clusterName}` - Get cluster details
- `PATCH /groups/{projectId}/clusters/{clusterName}` - Pause/resume cluster

## Security Notes

- API keys are stored locally and never transmitted except to MongoDB Atlas API
- Use credentials file with `chmod 600` for better security
- Consider using separate API keys for different environments
- Rotate API keys periodically
- Never commit credentials to git

## Support

For issues with the script, check the [PutPlace repository](https://github.com/jdrumgoole/putplace).

For MongoDB Atlas API issues, see [Atlas API Documentation](https://www.mongodb.com/docs/atlas/api/).
