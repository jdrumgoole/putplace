# AppRunner Fixed IP Setup for MongoDB Atlas

This guide explains how to configure AWS App Runner with a fixed IP address for MongoDB Atlas IP whitelisting.

## Overview

AWS App Runner uses dynamic IP addresses by default, which is incompatible with MongoDB Atlas's IP whitelist requirements. To provide a static IP address, we route App Runner's egress traffic through a VPC with a NAT Gateway that has a fixed Elastic IP address.

### Architecture

```
AppRunner Service
    ↓
VPC Connector (Private Subnet)
    ↓
NAT Gateway (Public Subnet) ← Elastic IP (Static)
    ↓
Internet (MongoDB Atlas)
```

### Cost Considerations

- **NAT Gateway**: ~$32/month + data transfer costs (~$0.045/GB)
- **Elastic IP**: Free when attached to NAT Gateway
- **VPC Connector**: No additional cost

## Prerequisites

- AWS CLI configured with appropriate credentials
- AWS account with permissions to create VPC resources
- Existing AppRunner service (or ready to deploy one)
- MongoDB Atlas cluster

## Quick Start

### Step 1: Create VPC Infrastructure with Fixed IP

Run the setup script to create all required AWS resources:

```bash
# Using uv (recommended)
uv run python -m putplace.scripts.setup_apprunner_fixed_ip

# Custom region (default is eu-west-1)
uv run python -m putplace.scripts.setup_apprunner_fixed_ip --region us-east-1

# Custom project name for resource tagging
uv run python -m putplace.scripts.setup_apprunner_fixed_ip --project-name myapp
```

This script will:
1. Create a VPC with DNS hostnames enabled
2. Create public and private subnets in different availability zones
3. Create and attach an Internet Gateway
4. Allocate an Elastic IP address
5. Create a NAT Gateway with the Elastic IP
6. Configure route tables for proper traffic flow
7. Create a security group for egress traffic
8. Create a VPC Connector for AppRunner

**Expected output:**
```
=== Setting up AppRunner Fixed IP in eu-west-1 ===

Creating VPC...
✓ VPC created: vpc-xxxxx
✓ DNS hostnames enabled
Creating Internet Gateway...
✓ Internet Gateway created: igw-xxxxx
✓ Internet Gateway attached to VPC
Creating public subnet...
✓ Public subnet created: subnet-xxxxx
Creating private subnet...
✓ Private subnet created: subnet-xxxxx
Allocating Elastic IP...
✓ Elastic IP allocated: 52.xxx.xxx.xxx
Creating NAT Gateway (this takes a few minutes)...
✓ NAT Gateway created: nat-xxxxx
Waiting for NAT Gateway to become available...
✓ NAT Gateway is available
Configuring public subnet route table...
✓ Public route table configured
✓ Public subnet associated with route table
Creating private subnet route table...
✓ Private route table created: rtb-xxxxx
✓ Private route table configured with NAT Gateway
✓ Private subnet associated with route table
Creating security group...
✓ Security group created: sg-xxxxx
✓ Security group configured for outbound traffic
Creating VPC Connector...
✓ VPC Connector created: arn:aws:apprunner:...

=== Setup Complete! ===

Static IP Address: 52.xxx.xxx.xxx
VPC Connector ARN: arn:aws:apprunner:eu-west-1:xxxxx:vpcconnector/putplace-vpc-connector/1/xxxxx

Next steps:
1. Add 52.xxx.xxx.xxx to MongoDB Atlas IP whitelist
2. Update your AppRunner service to use the VPC Connector
   (Use ARN: arn:aws:apprunner:...)

✓ Configuration saved to apprunner_fixed_ip_config.json
```

**Save the following information:**
- **Static IP Address**: Add this to MongoDB Atlas IP whitelist
- **VPC Connector ARN**: Used to update AppRunner service

### Step 2: Add IP to MongoDB Atlas Whitelist

1. Log in to [MongoDB Atlas](https://cloud.mongodb.com/)
2. Navigate to your cluster
3. Click "Network Access" in the left sidebar
4. Click "Add IP Address"
5. Enter the static IP address from Step 1
6. Add a description: "AppRunner Static IP"
7. Click "Confirm"

### Step 3: Update AppRunner Service

Update your existing AppRunner service to use the VPC Connector:

```bash
# Using service name
uv run python -m putplace.scripts.update_apprunner_vpc \
  putplace-service \
  --vpc-connector-arn "arn:aws:apprunner:eu-west-1:xxxxx:vpcconnector/putplace-vpc-connector/1/xxxxx" \
  --wait

# Using service ARN
uv run python -m putplace.scripts.update_apprunner_vpc \
  "arn:aws:apprunner:eu-west-1:xxxxx:service/putplace-service/xxxxx" \
  --vpc-connector-arn "arn:aws:apprunner:..." \
  --wait
```

The `--wait` flag will wait for the update to complete (recommended).

**Expected output:**
```
=== Updating AppRunner Service with VPC Connector ===

Looking up service: putplace-service...
Current service: putplace-service
Status: RUNNING
Current egress type: DEFAULT

Updating service to use VPC Connector...
Service: arn:aws:apprunner:...
VPC Connector: arn:aws:apprunner:...
✓ Update initiated: arn:aws:apprunner:...

Waiting for service update to complete (this may take several minutes)...
  Status: OPERATION_IN_PROGRESS (waiting...)
  Status: OPERATION_IN_PROGRESS (waiting...)
✓ Service update complete and running

=== Update Complete! ===

Your AppRunner service now routes traffic through the VPC Connector.
All outbound traffic will use the NAT Gateway's static IP address.
```

### Step 4: Verify Connection

Test your AppRunner service to ensure it can connect to MongoDB Atlas:

```bash
# Get your AppRunner service URL
aws apprunner describe-service \
  --service-arn "arn:aws:apprunner:..." \
  --region eu-west-1 \
  --query 'Service.ServiceUrl' \
  --output text

# Test the health endpoint
curl https://your-service-url.awsapprunner.com/health
```

If the health check succeeds, your AppRunner service is successfully connecting to MongoDB Atlas using the static IP.

## Configuration Files

### apprunner_fixed_ip_config.json

The setup script creates a configuration file with the following structure:

```json
{
  "elastic_ip": "52.xxx.xxx.xxx",
  "vpc_connector_arn": "arn:aws:apprunner:eu-west-1:xxxxx:vpcconnector/putplace-vpc-connector/1/xxxxx",
  "vpc_id": "vpc-xxxxx",
  "region": "eu-west-1"
}
```

This file can be used for automation or reference.

## Manual Setup (Alternative)

If you prefer to use AWS CLI directly or need to customize the setup:

### 1. Create VPC
```bash
aws ec2 create-vpc \
  --cidr-block 10.0.0.0/16 \
  --region eu-west-1 \
  --tag-specifications 'ResourceType=vpc,Tags=[{Key=Name,Value=putplace-vpc}]'

# Enable DNS hostnames
aws ec2 modify-vpc-attribute \
  --vpc-id vpc-xxxxx \
  --enable-dns-hostnames \
  --region eu-west-1
```

### 2. Create Internet Gateway
```bash
aws ec2 create-internet-gateway \
  --region eu-west-1 \
  --tag-specifications 'ResourceType=internet-gateway,Tags=[{Key=Name,Value=putplace-igw}]'

aws ec2 attach-internet-gateway \
  --internet-gateway-id igw-xxxxx \
  --vpc-id vpc-xxxxx \
  --region eu-west-1
```

### 3. Create Subnets
```bash
# Public subnet (for NAT Gateway)
aws ec2 create-subnet \
  --vpc-id vpc-xxxxx \
  --cidr-block 10.0.1.0/24 \
  --availability-zone eu-west-1a \
  --region eu-west-1 \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=putplace-public-subnet}]'

# Private subnet (for AppRunner)
aws ec2 create-subnet \
  --vpc-id vpc-xxxxx \
  --cidr-block 10.0.2.0/24 \
  --availability-zone eu-west-1b \
  --region eu-west-1 \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=putplace-private-subnet}]'
```

### 4. Create NAT Gateway
```bash
# Allocate Elastic IP
aws ec2 allocate-address \
  --domain vpc \
  --region eu-west-1 \
  --tag-specifications 'ResourceType=elastic-ip,Tags=[{Key=Name,Value=putplace-nat-eip}]'

# Create NAT Gateway
aws ec2 create-nat-gateway \
  --subnet-id subnet-xxxxx \
  --allocation-id eipalloc-xxxxx \
  --region eu-west-1 \
  --tag-specifications 'ResourceType=natgateway,Tags=[{Key=Name,Value=putplace-nat}]'

# Wait for NAT Gateway to become available (takes a few minutes)
aws ec2 describe-nat-gateways \
  --nat-gateway-ids nat-xxxxx \
  --region eu-west-1 \
  --query 'NatGateways[0].State'
```

### 5. Configure Route Tables
```bash
# Get main route table ID
aws ec2 describe-route-tables \
  --filters "Name=vpc-id,Values=vpc-xxxxx" \
  --region eu-west-1 \
  --query 'RouteTables[0].RouteTableId' \
  --output text

# Add route to Internet Gateway (public subnet)
aws ec2 create-route \
  --route-table-id rtb-xxxxx \
  --destination-cidr-block 0.0.0.0/0 \
  --gateway-id igw-xxxxx \
  --region eu-west-1

# Create private route table
aws ec2 create-route-table \
  --vpc-id vpc-xxxxx \
  --region eu-west-1 \
  --tag-specifications 'ResourceType=route-table,Tags=[{Key=Name,Value=putplace-private-rt}]'

# Add route to NAT Gateway (private subnet)
aws ec2 create-route \
  --route-table-id rtb-yyyyy \
  --destination-cidr-block 0.0.0.0/0 \
  --nat-gateway-id nat-xxxxx \
  --region eu-west-1

# Associate private subnet with private route table
aws ec2 associate-route-table \
  --route-table-id rtb-yyyyy \
  --subnet-id subnet-yyyyy \
  --region eu-west-1
```

### 6. Create Security Group
```bash
aws ec2 create-security-group \
  --group-name putplace-vpc-connector-sg \
  --description "Security group for AppRunner VPC Connector" \
  --vpc-id vpc-xxxxx \
  --region eu-west-1

# Allow all outbound traffic
aws ec2 authorize-security-group-egress \
  --group-id sg-xxxxx \
  --ip-permissions IpProtocol=-1,IpRanges=[{CidrIp=0.0.0.0/0}] \
  --region eu-west-1
```

### 7. Create VPC Connector
```bash
aws apprunner create-vpc-connector \
  --vpc-connector-name putplace-vpc-connector \
  --subnets subnet-yyyyy \
  --security-groups sg-xxxxx \
  --region eu-west-1
```

### 8. Update AppRunner Service
```bash
aws apprunner update-service \
  --service-arn "arn:aws:apprunner:..." \
  --network-configuration '{"EgressConfiguration":{"EgressType":"VPC","VpcConnectorArn":"arn:aws:apprunner:..."}}' \
  --region eu-west-1
```

## Troubleshooting

### AppRunner Cannot Connect to MongoDB Atlas

1. **Verify IP whitelist**: Ensure the Elastic IP is added to MongoDB Atlas
2. **Check NAT Gateway status**: Ensure NAT Gateway is in "available" state
3. **Verify route tables**: Ensure private subnet routes through NAT Gateway
4. **Check security group**: Ensure egress traffic is allowed on port 27017
5. **Check MongoDB connection string**: Ensure using correct connection string

```bash
# Check NAT Gateway status
aws ec2 describe-nat-gateways \
  --nat-gateway-ids nat-xxxxx \
  --region eu-west-1 \
  --query 'NatGateways[0].State'

# Check AppRunner VPC Connector status
aws apprunner describe-vpc-connector \
  --vpc-connector-arn "arn:aws:apprunner:..." \
  --region eu-west-1 \
  --query 'VpcConnector.Status'
```

### How to Verify Static IP is Being Used

1. **Create a test endpoint** that returns the outbound IP:
   ```python
   @app.get("/my-ip")
   async def get_my_ip():
       import httpx
       response = await httpx.get("https://api.ipify.org?format=json")
       return response.json()
   ```

2. **Call the endpoint**:
   ```bash
   curl https://your-service-url.awsapprunner.com/my-ip
   ```

3. **Verify the IP matches** your Elastic IP address

### VPC Connector Creation Fails

- **Subnet requirements**: VPC Connector requires private subnets in at least one AZ
- **Security group**: Must be in the same VPC as the subnets
- **Subnet capacity**: Ensure subnet has enough available IP addresses

### AppRunner Service Update Fails

- **Service must be in RUNNING state**: Cannot update while in OPERATION_IN_PROGRESS
- **Valid VPC Connector ARN**: Ensure the ARN is correct and VPC Connector exists
- **IAM permissions**: Ensure you have `apprunner:UpdateService` permission

## Cleanup

To remove all resources and avoid ongoing costs:

### Delete VPC Connector
```bash
aws apprunner delete-vpc-connector \
  --vpc-connector-arn "arn:aws:apprunner:..." \
  --region eu-west-1
```

### Delete NAT Gateway
```bash
# Delete NAT Gateway
aws ec2 delete-nat-gateway \
  --nat-gateway-id nat-xxxxx \
  --region eu-west-1

# Wait for NAT Gateway to be deleted (takes a few minutes)
aws ec2 describe-nat-gateways \
  --nat-gateway-ids nat-xxxxx \
  --region eu-west-1 \
  --query 'NatGateways[0].State'

# Release Elastic IP
aws ec2 release-address \
  --allocation-id eipalloc-xxxxx \
  --region eu-west-1
```

### Delete VPC Resources
```bash
# Delete route table associations
aws ec2 disassociate-route-table \
  --association-id rtbassoc-xxxxx \
  --region eu-west-1

# Delete route tables
aws ec2 delete-route-table \
  --route-table-id rtb-xxxxx \
  --region eu-west-1

# Delete subnets
aws ec2 delete-subnet \
  --subnet-id subnet-xxxxx \
  --region eu-west-1

# Detach and delete Internet Gateway
aws ec2 detach-internet-gateway \
  --internet-gateway-id igw-xxxxx \
  --vpc-id vpc-xxxxx \
  --region eu-west-1

aws ec2 delete-internet-gateway \
  --internet-gateway-id igw-xxxxx \
  --region eu-west-1

# Delete security group
aws ec2 delete-security-group \
  --group-id sg-xxxxx \
  --region eu-west-1

# Delete VPC
aws ec2 delete-vpc \
  --vpc-id vpc-xxxxx \
  --region eu-west-1
```

## Additional Resources

- [AWS App Runner VPC Networking](https://docs.aws.amazon.com/apprunner/latest/dg/network-vpc.html)
- [MongoDB Atlas Network Access](https://docs.atlas.mongodb.com/security/ip-access-list/)
- [AWS NAT Gateway Pricing](https://aws.amazon.com/vpc/pricing/)
- [AWS VPC Connector for App Runner](https://docs.aws.amazon.com/apprunner/latest/dg/network-vpc-connector.html)

## Cost Optimization Tips

1. **Use a single NAT Gateway** for multiple AppRunner services in the same region
2. **Monitor data transfer costs** - NAT Gateway charges for data processed
3. **Consider VPC endpoints** for AWS services (S3, DynamoDB) to avoid NAT Gateway costs
4. **Delete resources** when not in use (development/staging environments)
5. **Use appropriate instance sizes** for MongoDB Atlas to minimize data transfer

## Security Considerations

1. **Least privilege**: Configure security groups to allow only necessary outbound ports
2. **Network ACLs**: Consider additional network ACLs for defense in depth
3. **Monitoring**: Enable VPC Flow Logs to monitor traffic patterns
4. **Regular audits**: Review IP whitelists and remove unused entries
5. **Secrets management**: Use AWS Secrets Manager for MongoDB credentials
