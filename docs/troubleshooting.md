# Troubleshooting Guide

Common issues and solutions for PutPlace server and client.

## Quick Diagnostics

### Health Check

```bash
# Check server health
curl http://localhost:8000/health

# Expected output (healthy):
# {"status":"healthy","database":{"status":"connected","type":"mongodb"}}

# Expected output (degraded):
# {"status":"degraded","database":{"status":"disconnected","type":"mongodb"}}
```

### Check Logs

```bash
# systemd service
sudo journalctl -u putplace -f

# Docker
docker logs -f putplace

# Docker Compose
docker-compose logs -f putplace
```

### Test API Key

```bash
# List API keys
curl -H "X-API-Key: YOUR_KEY" http://localhost:8000/api_keys

# Expected: JSON array of API keys
# If 401: API key invalid
```

## Server Issues

### MongoDB Connection Failures

#### Problem: Cannot connect to MongoDB

**Symptoms:**
```
pymongo.errors.ServerSelectionTimeoutError: localhost:27017: [Errno 111] Connection refused
```

**Diagnosis:**
```bash
# Check if MongoDB is running
sudo systemctl status mongod

# Check MongoDB is listening
sudo netstat -tlnp | grep 27017

# Check MongoDB logs
sudo journalctl -u mongod -f
```

**Solutions:**

1. **Start MongoDB:**
   ```bash
   sudo systemctl start mongod
   sudo systemctl enable mongod  # Auto-start on boot
   ```

2. **Check MongoDB configuration:**
   ```bash
   # Check bind address
   grep bindIp /etc/mongod.conf

   # Should be:
   # bindIp: 127.0.0.1  # For local only
   # bindIp: 0.0.0.0    # For remote connections
   ```

3. **Check firewall:**
   ```bash
   # Allow MongoDB port
   sudo ufw allow 27017/tcp
   ```

4. **Check connection string:**
   ```bash
   # Verify MONGODB_URL in .env
   cat /opt/putplace/.env | grep MONGODB_URL

   # Test connection
   mongosh "$MONGODB_URL"
   ```

---

#### Problem: Authentication failed

**Symptoms:**
```
pymongo.errors.OperationFailure: Authentication failed
```

**Solutions:**

1. **Verify credentials in connection string:**
   ```bash
   MONGODB_URL=mongodb://username:password@localhost:27017
   ```

2. **Create MongoDB user:**
   ```bash
   mongosh
   > use admin
   > db.createUser({
       user: "putplace",
       pwd: "secure_password",
       roles: [{role: "readWrite", db: "putplace"}]
     })
   ```

3. **Update connection string:**
   ```bash
   MONGODB_URL=mongodb://putplace:secure_password@localhost:27017/putplace
   ```

---

#### Problem: Connection timeout

**Symptoms:**
```
pymongo.errors.ServerSelectionTimeoutError: Timed out after 5000ms
```

**Solutions:**

1. **Increase timeout:**
   ```bash
   MONGODB_URL=mongodb://localhost:27017/?serverSelectionTimeoutMS=10000
   ```

2. **Check network connectivity:**
   ```bash
   # Test connection
   telnet mongodb-host 27017

   # Check DNS resolution
   nslookup mongodb-host
   ```

3. **Check MongoDB is accessible:**
   ```bash
   mongosh --host mongodb-host --port 27017
   ```

### Storage Backend Issues

#### Problem: Local storage permission denied

**Symptoms:**
```
PermissionError: [Errno 13] Permission denied: '/var/putplace/files'
```

**Diagnosis:**
```bash
# Check directory exists
ls -ld /var/putplace/files

# Check ownership
ls -ld /var/putplace/files
# Should show: drwxr-xr-x putplace putplace
```

**Solutions:**

1. **Create directory:**
   ```bash
   sudo mkdir -p /var/putplace/files
   ```

2. **Fix ownership:**
   ```bash
   sudo chown -R putplace:putplace /var/putplace/files
   ```

3. **Fix permissions:**
   ```bash
   chmod 755 /var/putplace/files
   ```

4. **Verify:**
   ```bash
   # Test write access
   sudo -u putplace touch /var/putplace/files/test
   sudo -u putplace rm /var/putplace/files/test
   ```

---

#### Problem: Disk full

**Symptoms:**
```
OSError: [Errno 28] No space left on device
```

**Diagnosis:**
```bash
# Check disk space
df -h /var/putplace/files

# Check disk usage
du -sh /var/putplace/files

# Find large files
du -h /var/putplace/files | sort -hr | head -20
```

**Solutions:**

1. **Clean up old files:**
   ```bash
   # Find files older than 90 days
   find /var/putplace/files -type f -mtime +90 -ls

   # Delete files older than 90 days (BE CAREFUL!)
   find /var/putplace/files -type f -mtime +90 -delete
   ```

2. **Archive to S3:**
   ```bash
   # Migrate to S3 storage backend
   # See docs/storage.md
   ```

3. **Expand disk:**
   ```bash
   # Resize partition (varies by system)
   # Or mount additional disk
   ```

---

#### Problem: S3 access denied

**Symptoms:**
```
botocore.exceptions.ClientError: An error occurred (AccessDenied) when calling the PutObject operation
```

**Diagnosis:**
```bash
# Check AWS credentials
aws sts get-caller-identity --profile putplace

# Check S3 access
aws s3 ls s3://my-putplace-bucket --profile putplace

# Try uploading test file
echo "test" > /tmp/test.txt
aws s3 cp /tmp/test.txt s3://my-putplace-bucket/test.txt --profile putplace
```

**Solutions:**

1. **Verify IAM permissions:**
   ```bash
   # Check IAM policy
   aws iam get-user-policy --user-name putplace-user --policy-name putplace-s3-access
   ```

   **Required permissions:**
   ```json
   {
     "Effect": "Allow",
     "Action": [
       "s3:PutObject",
       "s3:GetObject",
       "s3:DeleteObject",
       "s3:ListBucket"
     ],
     "Resource": [
       "arn:aws:s3:::my-putplace-bucket/files/*",
       "arn:aws:s3:::my-putplace-bucket"
     ]
   }
   ```

2. **Verify AWS credentials:**
   ```bash
   # Check credentials file
   cat ~/.aws/credentials

   # Or check environment variables
   env | grep AWS_
   ```

3. **Use IAM role (on EC2/ECS):**
   ```bash
   # Remove explicit credentials
   # Let AWS SDK use instance metadata
   # Update .env:
   STORAGE_BACKEND=s3
   S3_BUCKET_NAME=my-putplace-bucket
   S3_REGION_NAME=us-east-1
   # No AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY
   ```

---

#### Problem: S3 connection timeout

**Symptoms:**
```
botocore.exceptions.ConnectTimeoutError: Connect timeout on endpoint URL
```

**Solutions:**

1. **Check network connectivity:**
   ```bash
   # Test S3 endpoint
   curl -I https://s3.us-east-1.amazonaws.com
   ```

2. **Check proxy settings:**
   ```bash
   # If using proxy
   export HTTP_PROXY=http://proxy.example.com:8080
   export HTTPS_PROXY=http://proxy.example.com:8080
   ```

3. **Increase timeout:**
   ```bash
   # Update code to increase boto3 timeout
   # Or use VPC endpoint for S3
   ```

### Service Won't Start

#### Problem: systemd service fails to start

**Symptoms:**
```bash
sudo systemctl start putplace
# Job for putplace.service failed
```

**Diagnosis:**
```bash
# Check status
sudo systemctl status putplace

# Check logs
sudo journalctl -u putplace -n 50 --no-pager

# Check service file syntax
sudo systemd-analyze verify /etc/systemd/system/putplace.service
```

**Solutions:**

1. **Fix service file:**
   ```bash
   sudo nano /etc/systemd/system/putplace.service

   # Reload after changes
   sudo systemctl daemon-reload
   ```

2. **Check environment file:**
   ```bash
   # Verify .env exists and is readable
   sudo -u putplace cat /opt/putplace/.env
   ```

3. **Test command manually:**
   ```bash
   # Run as putplace user
   sudo -u putplace /opt/putplace/.venv/bin/gunicorn putplace.main:app
   ```

4. **Check permissions:**
   ```bash
   # Verify ownership
   sudo ls -la /opt/putplace/

   # Fix if needed
   sudo chown -R putplace:putplace /opt/putplace/
   ```

---

#### Problem: Port already in use

**Symptoms:**
```
OSError: [Errno 98] Address already in use
```

**Diagnosis:**
```bash
# Check what's using port 8000
sudo netstat -tlnp | grep 8000
sudo lsof -i :8000
```

**Solutions:**

1. **Kill existing process:**
   ```bash
   # Find process ID
   sudo lsof -ti :8000

   # Kill process
   sudo kill $(sudo lsof -ti :8000)
   ```

2. **Use different port:**
   ```bash
   # Edit service file
   sudo nano /etc/systemd/system/putplace.service

   # Change --bind option:
   --bind 127.0.0.1:8001
   ```

---

#### Problem: Module not found

**Symptoms:**
```
ModuleNotFoundError: No module named 'putplace'
```

**Solutions:**

1. **Verify virtual environment:**
   ```bash
   # Check venv exists
   ls -la /opt/putplace/.venv/

   # Recreate if needed
   cd /opt/putplace
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e .
   ```

2. **Check service file ExecStart path:**
   ```bash
   # Should point to venv Python
   ExecStart=/opt/putplace/.venv/bin/gunicorn ...
   ```

## Client Issues

### API Key Problems

#### Problem: No API key provided

**Symptoms:**
```
Warning: No API key provided (authentication may fail)
```

**Solutions:**

1. **Provide via command line:**
   ```bash
   python ppclient.py /path --api-key "YOUR_KEY"
   ```

2. **Provide via environment variable:**
   ```bash
   export PUTPLACE_API_KEY="YOUR_KEY"
   python ppclient.py /path
   ```

3. **Provide via config file:**
   ```bash
   # Create ~/ppclient.conf
   cat > ~/ppclient.conf << EOF
   [DEFAULT]
   api-key = YOUR_KEY
   EOF

   chmod 600 ~/ppclient.conf
   ```

---

#### Problem: 401 Unauthorized

**Symptoms:**
```
Failed to send file.txt: Client error '401 Unauthorized'
```

**Diagnosis:**
```bash
# Test API key
curl -H "X-API-Key: YOUR_KEY" http://localhost:8000/api_keys

# Check API key format (should be 64 hex characters)
echo -n "YOUR_KEY" | wc -c
# Should output: 64
```

**Solutions:**

1. **Verify API key is correct:**
   ```bash
   # List API keys on server
   python -m putplace.scripts.create_api_key --name "new-key"
   ```

2. **Create new API key:**
   ```bash
   # On server
   curl -X POST http://localhost:8000/api_keys \
     -H "X-API-Key: ADMIN_KEY" \
     -H "Content-Type: application/json" \
     -d '{"name": "client-key"}'
   ```

3. **Check if key was revoked:**
   ```bash
   # On server, list keys
   curl -H "X-API-Key: ADMIN_KEY" http://localhost:8000/api_keys
   # Check is_active field
   ```

### Connection Issues

#### Problem: Connection refused

**Symptoms:**
```
Failed to send file.txt: Cannot connect to host localhost:8000
```

**Diagnosis:**
```bash
# Check server is running
curl http://localhost:8000/health

# Check server is listening
sudo netstat -tlnp | grep 8000
```

**Solutions:**

1. **Start server:**
   ```bash
   sudo systemctl start putplace
   ```

2. **Check URL:**
   ```bash
   # Verify URL in client config
   python ppclient.py /path --url http://correct-server:8000/put_file
   ```

3. **Check firewall:**
   ```bash
   # Allow port 8000
   sudo ufw allow 8000/tcp

   # Or test from client
   telnet server-host 8000
   ```

---

#### Problem: Timeout

**Symptoms:**
```
Failed to send file.txt: Timeout
```

**Solutions:**

1. **Increase client timeout:**
   ```python
   # In ppclient.py, modify httpx client
   httpx.Client(timeout=300.0)  # 5 minutes
   ```

2. **Check network latency:**
   ```bash
   ping server-host
   ```

3. **Check server performance:**
   ```bash
   # On server
   top
   # Check CPU/memory usage
   ```

### File Upload Issues

#### Problem: SHA256 mismatch

**Symptoms:**
```
File content SHA256 (abc123...) does not match provided hash (def456...)
```

**Diagnosis:**
```bash
# Verify SHA256 calculation
sha256sum /path/to/file.txt
```

**Solutions:**

1. **File changed during upload:**
   - Ensure file is not being modified during scan
   - Stop processes that might modify the file

2. **Client bug:**
   - Verify client calculates SHA256 correctly
   - Update client to latest version

---

#### Problem: File too large

**Symptoms:**
```
Failed to upload: Request Entity Too Large
```

**Solutions:**

1. **Increase nginx client_max_body_size:**
   ```nginx
   http {
       client_max_body_size 1G;
   }
   ```

2. **Increase gunicorn timeout:**
   ```bash
   --timeout 300  # 5 minutes
   ```

3. **Split large files:**
   - Consider implementing chunked uploads
   - Or exclude large files from scanning

## Performance Issues

### Slow Uploads

**Diagnosis:**
```bash
# Check network bandwidth
iperf3 -s  # On server
iperf3 -c server-host  # On client

# Check disk I/O
iostat -x 1 10

# Check MongoDB performance
mongosh --eval "db.serverStatus()"
```

**Solutions:**

1. **Optimize MongoDB:**
   ```bash
   # Add indexes
   mongosh putplace
   > db.file_metadata.createIndex({sha256: 1})
   > db.file_metadata.createIndex({hostname: 1, filepath: 1})
   ```

2. **Use SSD for storage:**
   - Move /var/putplace/files to SSD
   - Or use S3 storage backend

3. **Increase worker count:**
   ```bash
   # Edit systemd service
   --workers 17  # For 4 CPU cores
   ```

4. **Enable compression:**
   ```nginx
   gzip on;
   gzip_types application/json;
   ```

### High Memory Usage

**Diagnosis:**
```bash
# Check memory usage
free -h

# Check per-process usage
ps aux --sort=-%mem | head -20

# Check Gunicorn workers
ps aux | grep gunicorn
```

**Solutions:**

1. **Reduce worker count:**
   ```bash
   # Edit systemd service
   --workers 4  # Reduce from 9
   ```

2. **Add swap:**
   ```bash
   # Create 2GB swap
   sudo fallocate -l 2G /swapfile
   sudo chmod 600 /swapfile
   sudo mkswap /swapfile
   sudo swapon /swapfile

   # Make permanent
   echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
   ```

3. **Upgrade server:**
   - Add more RAM
   - Or use smaller instance with fewer workers

### Database Performance

**Diagnosis:**
```bash
# Check slow queries
mongosh putplace
> db.setProfilingLevel(2)
> db.system.profile.find().sort({ts:-1}).limit(10).pretty()

# Check collection stats
> db.file_metadata.stats()
```

**Solutions:**

1. **Add missing indexes:**
   ```bash
   > db.file_metadata.getIndexes()
   > db.file_metadata.createIndex({sha256: 1})
   ```

2. **Clean up old data:**
   ```bash
   # Remove entries older than 1 year
   > db.file_metadata.deleteMany({
       mtime: {$lt: new Date(Date.now() - 365*24*60*60*1000)}
     })
   ```

3. **Use MongoDB replica set:**
   - Distribute read load
   - See deployment.md

## Debugging Tips

### Enable Debug Logging

```bash
# In .env
LOG_LEVEL=DEBUG

# Restart service
sudo systemctl restart putplace

# Watch logs
sudo journalctl -u putplace -f
```

### Test API Endpoints

```bash
# Test /put_file
curl -X POST http://localhost:8000/put_file \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "filepath": "/tmp/test.txt",
    "hostname": "test",
    "ip_address": "127.0.0.1",
    "sha256": "abc123...",
    "file_size": 1234,
    "file_mode": 33188,
    "file_uid": 1000,
    "file_gid": 1000,
    "file_mtime": 1609459200.0,
    "file_atime": 1609459200.0,
    "file_ctime": 1609459200.0,
    "is_symlink": false
  }'

# Test /health
curl http://localhost:8000/health

# Test /api_keys
curl -H "X-API-Key: YOUR_KEY" http://localhost:8000/api_keys
```

### Check MongoDB Directly

```bash
mongosh putplace

# Count documents
> db.file_metadata.countDocuments()

# Find recent documents
> db.file_metadata.find().sort({_id:-1}).limit(5).pretty()

# Find by SHA256
> db.file_metadata.findOne({sha256: "abc123..."})

# Check indexes
> db.file_metadata.getIndexes()

# Check API keys
> db.api_keys.find({}, {key_hash: 0}).pretty()
```

## Getting Help

If you've tried these solutions and still have issues:

1. **Check documentation:**
   - [Installation Guide](installation.md)
   - [Configuration Reference](configuration.md)
   - [Deployment Guide](deployment.md)

2. **Search issues:**
   - [GitHub Issues](https://github.com/jdrumgoole/putplace/issues)

3. **File a bug report:**
   - Include error messages
   - Include relevant logs
   - Include configuration (redact secrets!)
   - Include steps to reproduce

4. **Community support:**
   - [GitHub Discussions](https://github.com/jdrumgoole/putplace/discussions)

## Common Error Messages

### "Database not connected"

**Cause:** MongoDB is not running or not accessible

**Fix:** See [MongoDB Connection Failures](#mongodb-connection-failures)

---

### "Storage backend not initialized"

**Cause:** Storage backend configuration is invalid

**Fix:** Check STORAGE_BACKEND, S3_BUCKET_NAME in .env

---

### "Invalid API key"

**Cause:** API key is incorrect or revoked

**Fix:** Create new API key or verify existing one

---

### "File with SHA256 XXX not found"

**Cause:** File metadata does not exist in database

**Fix:** Ensure /put_file was called before /get_file

---

### "Failed to store file content"

**Cause:** Storage backend error (disk full, S3 access denied, etc.)

**Fix:** Check storage backend logs and configuration
