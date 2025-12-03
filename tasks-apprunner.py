"""AWS App Runner invoke tasks for PutPlace deployment.

These tasks handle AWS App Runner deployment, configuration, and management.
They have been separated from the main tasks.py for better organization.

Usage:
    # Import these tasks in tasks.py or use directly
    invoke configure-apprunner
    invoke deploy-apprunner
    invoke trigger-apprunner-deploy
"""

import os

from invoke import task


@task
def configure_apprunner(c, region="eu-west-1", mongodb_url=None, non_interactive=False):
    """Configure PutPlace for AWS App Runner deployment.

    Creates AWS Secrets Manager secrets with MongoDB connection, admin user,
    and API configuration for App Runner deployment.

    Requirements:
        - AWS CLI installed and configured
        - MongoDB connection string (MongoDB Atlas recommended)
        - boto3 library installed

    Args:
        region: AWS region for deployment (default: eu-west-1)
        mongodb_url: MongoDB connection string (will prompt if not provided)
        non_interactive: Skip prompts and use defaults (default: False)

    Examples:
        # Interactive mode (recommended)
        invoke configure-apprunner

        # Non-interactive with MongoDB Atlas
        invoke configure-apprunner --mongodb-url="mongodb+srv://user:pass@cluster.mongodb.net/"

        # Different region
        invoke configure-apprunner --region=us-east-1
    """
    import shlex

    cmd = [
        "uv", "run", "python", "-m",
        "putplace.scripts.putplace_configure",
        "--create-aws-secrets",
        "--aws-region", region
    ]

    if non_interactive:
        cmd.append("--non-interactive")

    if mongodb_url:
        cmd.append("--mongodb-url")
        cmd.append(mongodb_url)

    print(f"Configuring PutPlace for App Runner deployment in {region}...")
    print("This will create secrets in AWS Secrets Manager.\n")

    result = c.run(shlex.join(cmd), warn=True, pty=True)

    if result.ok:
        print(f"\n✓ Configuration complete!")
        print(f"\nNext steps:")
        print(f"  1. Review the secrets in AWS Secrets Manager console")
        print(f"  2. Deploy to App Runner: invoke deploy-apprunner --region={region}")
    else:
        print(f"\n✗ Configuration failed")
        print("\nCommon issues:")
        print("  - AWS credentials not configured")
        print("  - boto3 not installed (pip install boto3)")
        print("  - MongoDB connection string invalid")


@task
def setup_github_connection(c, region="eu-west-1"):
    """Check and guide setup of GitHub connection for App Runner.

    App Runner requires a GitHub connection to deploy from GitHub repositories.
    This task checks if a connection exists and provides setup instructions.

    Args:
        region: AWS region (default: eu-west-1)

    Examples:
        invoke setup-github-connection
        invoke setup-github-connection --region=us-east-1
    """
    import json

    print(f"Checking GitHub connections in {region}...\n")

    # List connections
    connections_cmd = f"aws apprunner list-connections --region {region}"
    result = c.run(connections_cmd, warn=True, hide=True)

    if not result.ok:
        print("✗ Failed to list connections")
        print("\nMake sure AWS CLI is configured and you have App Runner permissions.")
        return 1

    connections = json.loads(result.stdout)
    connection_list = connections.get('ConnectionSummaryList', [])

    if not connection_list:
        print("⚠️  No GitHub connections found")
    else:
        print(f"Found {len(connection_list)} connection(s):\n")
        for conn in connection_list:
            status = conn.get('Status', 'UNKNOWN')
            status_icon = '✓' if status == 'AVAILABLE' else '✗'
            print(f"{status_icon} {conn['ConnectionName']}")
            print(f"  Provider: {conn.get('ProviderType', 'Unknown')}")
            print(f"  Status: {status}")
            print(f"  ARN: {conn['ConnectionArn']}")
            print()

    # Check for available GitHub connection
    github_available = any(
        conn.get('ProviderType') == 'GITHUB' and conn.get('Status') == 'AVAILABLE'
        for conn in connection_list
    )

    if github_available:
        print("✓ GitHub connection is ready!")
        print(f"\nYou can now deploy with: invoke deploy-apprunner --region={region}")
    else:
        print("\n" + "="*60)
        print("GitHub Connection Setup Instructions")
        print("="*60)
        print("\nOption 1: AWS Console (Recommended)")
        print(f"1. Open: https://console.aws.amazon.com/apprunner/home?region={region}#/settings")
        print("2. Click the 'Source connections' tab")
        print("3. Click 'Add connection' button")
        print("4. Select 'GitHub' as the source code provider")
        print("5. Click 'Add connection'")
        print("6. Authorize AWS App Runner in GitHub")
        print("7. Give the connection a name (e.g., 'github-connection')")
        print("8. Click 'Connect'")
        print("\nOption 2: AWS CLI")
        print(f"aws apprunner create-connection \\")
        print(f"  --connection-name github-connection \\")
        print(f"  --provider-type GITHUB \\")
        print(f"  --region {region}")
        print("\nNote: You'll still need to complete GitHub authorization in the console.")
        print(f"\nAfter setup, verify with: invoke setup-github-connection --region={region}")


@task
def deploy_apprunner(
    c,
    service_name="putplace-api",
    region="eu-west-1",
    github_repo="https://github.com/jdrumgoole/putplace",
    github_branch="main",
    cpu="1 vCPU",
    memory="2 GB",
    auto_deploy=False
):
    """Deploy PutPlace to AWS App Runner.

    Creates or updates an App Runner service with manual deployment trigger.
    Requires AWS Secrets Manager secrets to be created first.

    Requirements:
        - AWS CLI installed and configured
        - Secrets created (run: invoke configure-apprunner first)
        - GitHub repository access (will prompt for connection)

    Args:
        service_name: App Runner service name (default: putplace-api)
        region: AWS region (default: eu-west-1)
        github_repo: GitHub repository URL (default: https://github.com/jdrumgoole/putplace)
        github_branch: Git branch to deploy (default: main)
        cpu: CPU allocation (default: 1 vCPU)
        memory: Memory allocation (default: 2 GB)
        auto_deploy: Enable automatic deployment on git push (default: False - manual only)

    Examples:
        # Deploy with defaults (uses jdrumgoole/putplace repo)
        invoke deploy-apprunner

        # Deploy with custom repository
        invoke deploy-apprunner --github-repo=https://github.com/user/putplace

        # Different instance size
        invoke deploy-apprunner --cpu="2 vCPU" --memory="4 GB"

        # Enable auto-deploy on commits
        invoke deploy-apprunner --auto-deploy

    Notes:
        - By default, deployment is MANUAL only (no auto-deploy on commits)
        - Use App Runner console or CLI to trigger deployments manually
        - Automatic deployments can be enabled with --auto-deploy flag
    """
    import json

    # Check for uncommitted changes
    print("Checking git status...")
    git_status = c.run("git status --porcelain", hide=True, warn=True)

    if git_status.ok and git_status.stdout.strip():
        print("\n⚠️  You have uncommitted changes!")
        print("\nUncommitted files:")
        for line in git_status.stdout.strip().split('\n'):
            print(f"  {line}")
        print("\nPlease commit or stash your changes before deploying:")
        print("  git add .")
        print("  git commit -m 'Your commit message'")
        print("  git push")
        print(f"\nThen run: invoke deploy-apprunner --region={region}")
        return 1

    # Check if local branch is up to date with remote
    print("Checking if local branch is up to date...")
    git_fetch = c.run("git fetch", hide=True, warn=True)
    if git_fetch.ok:
        git_status_remote = c.run(f"git status -uno", hide=True, warn=True)
        if git_status_remote.ok and "Your branch is behind" in git_status_remote.stdout:
            print("\n⚠️  Your local branch is behind the remote!")
            print("\nPull the latest changes:")
            print("  git pull")
            print(f"\nThen run: invoke deploy-apprunner --region={region}")
            return 1
        elif git_status_remote.ok and "Your branch is ahead" in git_status_remote.stdout:
            print("\n⚠️  Your local branch is ahead of the remote!")
            print("\nPush your changes:")
            print("  git push")
            print(f"\nThen run: invoke deploy-apprunner --region={region}")
            return 1

    print("✓ Git status clean and up to date\n")

    print(f"{'='*60}")
    print(f"Deploying PutPlace to AWS App Runner")
    print(f"{'='*60}")
    print(f"Service name: {service_name}")
    print(f"Region: {region}")
    print(f"Repository: {github_repo}")
    print(f"Branch: {github_branch}")
    print(f"Instance: {cpu}, {memory}")
    print(f"Auto-deploy: {'Enabled' if auto_deploy else 'Disabled (manual only)'}")
    print(f"{'='*60}\n")

    # Check for GitHub connection
    print("Checking GitHub connection...")
    connections_cmd = f"aws apprunner list-connections --region {region}"
    conn_result = c.run(connections_cmd, warn=True, hide=True)

    github_connection_arn = None
    if conn_result.ok:
        connections = json.loads(conn_result.stdout)
        for conn in connections.get('ConnectionSummaryList', []):
            if conn.get('ProviderType') == 'GITHUB' and conn.get('Status') == 'AVAILABLE':
                github_connection_arn = conn['ConnectionArn']
                print(f"✓ GitHub connection found: {conn['ConnectionName']}")
                print(f"  ARN: {github_connection_arn}")
                break

    if not github_connection_arn:
        print("\n⚠️  GitHub connection not configured!")
        print(f"\nRun this command for setup instructions:")
        print(f"  invoke setup-github-connection --region={region}")
        return 1

    # Check if service already exists
    print("\nChecking if service exists...")
    check_cmd = f"aws apprunner list-services --region {region}"
    check_result = c.run(check_cmd, warn=True, hide=True)

    service_exists = False
    if check_result.ok:
        import json
        services = json.loads(check_result.stdout)
        for svc in services.get('ServiceSummaryList', []):
            if svc['ServiceName'] == service_name:
                service_exists = True
                service_arn = svc['ServiceArn']
                print(f"✓ Service exists: {service_arn}")
                break

    if service_exists:
        print(f"\n⚠️  Service '{service_name}' already exists")
        print("To update the service, trigger a manual deployment:")
        print(f"  aws apprunner start-deployment --service-arn {service_arn} --region {region}")
        return 0

    # Create new service
    print("\nCreating App Runner service...")

    # Build code configuration values with secrets
    # First, get the actual secret ARNs with their random suffixes
    secrets_arns = {}
    for secret_name in ['putplace/mongodb', 'putplace/admin', 'putplace/aws-config']:
        describe_cmd = f"aws secretsmanager describe-secret --secret-id {secret_name} --region {region}"
        result = c.run(describe_cmd, hide=True, warn=True)
        if result.ok:
            secret_info = json.loads(result.stdout)
            secrets_arns[secret_name] = secret_info['ARN']

    # Format: {"ENV_VAR_NAME": "arn:aws:secretsmanager:region:account:secret:name-SUFFIX:json_key::"}
    runtime_env_secrets = {}
    # MongoDB secrets
    for key in ['MONGODB_URL', 'MONGODB_DATABASE', 'MONGODB_COLLECTION']:
        runtime_env_secrets[key] = f"{secrets_arns['putplace/mongodb']}:{key}::"
    # Admin secrets
    for key in ['PUTPLACE_ADMIN_USERNAME', 'PUTPLACE_ADMIN_EMAIL', 'PUTPLACE_ADMIN_PASSWORD']:
        runtime_env_secrets[key] = f"{secrets_arns['putplace/admin']}:{key}::"
    # AWS/API secrets
    for key in ['AWS_DEFAULT_REGION', 'API_TITLE', 'API_VERSION', 'PYTHONUNBUFFERED', 'PYTHONDONTWRITEBYTECODE']:
        runtime_env_secrets[key] = f"{secrets_arns['putplace/aws-config']}:{key}::"

    # Build source configuration with API-based configuration
    # Set PYTHONPATH as an environment variable to avoid shell quoting issues
    source_config = {
        "CodeRepository": {
            "RepositoryUrl": github_repo,
            "SourceCodeVersion": {
                "Type": "BRANCH",
                "Value": github_branch
            },
            "CodeConfiguration": {
                "ConfigurationSource": "API",
                "CodeConfigurationValues": {
                    "Runtime": "PYTHON_311",
                    "RuntimeEnvironmentSecrets": runtime_env_secrets,
                    "RuntimeEnvironmentVariables": {
                        "PYTHONPATH": "/app/packages"
                    },
                    "BuildCommand": "python3.11 -m pip install --target=/app/packages .[s3]",
                    "StartCommand": "python3.11 -m uvicorn putplace.main:app --host 0.0.0.0 --port 8000 --workers 2",
                    "Port": "8000"
                }
            }
        },
        "AuthenticationConfiguration": {
            "ConnectionArn": github_connection_arn
        },
        "AutoDeploymentsEnabled": auto_deploy
    }

    # Write source config to temp file
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(source_config, f)
        source_config_file = f.name

    try:
        # Get or create instance role ARN
        # Get AWS account ID from environment or use AWS CLI
        aws_account_id = os.getenv("AWS_ACCOUNT_ID")
        if not aws_account_id:
            result = c.run("aws sts get-caller-identity --query Account --output text", hide=True, warn=True)
            if result.ok:
                aws_account_id = result.stdout.strip()
            else:
                print("Error: Could not determine AWS account ID. Set AWS_ACCOUNT_ID environment variable.")
                return
        instance_role_arn = f"arn:aws:iam::{aws_account_id}:role/AppRunnerPutPlaceInstanceRole"

        create_cmd = f"""aws apprunner create-service \\
            --service-name {service_name} \\
            --source-configuration file://{source_config_file} \\
            --instance-configuration Cpu="{cpu}",Memory="{memory}",InstanceRoleArn="{instance_role_arn}" \\
            --region {region}"""

        print("\nExecuting:")
        print(create_cmd)
        print()

        result = c.run(create_cmd, warn=True, hide=False)

        if result.ok:
            # Parse service ARN from response
            response = json.loads(result.stdout)
            service_arn = response['Service']['ServiceArn']
            service_url = response['Service'].get('ServiceUrl', 'Pending...')

            print(f"\n✓ App Runner service created successfully!")
            print(f"\nService: {service_name}")
            print(f"Region: {region}")
            print(f"Service ARN: {service_arn}")
            print(f"Service URL: https://{service_url}" if service_url != 'Pending...' else "Service URL: Pending...")

            # Monitor deployment status
            print(f"\nMonitoring deployment status...")
            print("This may take 5-10 minutes. Press Ctrl+C to stop monitoring (deployment will continue).\n")

            import time
            max_attempts = 60  # 10 minutes max
            attempt = 0

            while attempt < max_attempts:
                describe_cmd = f"aws apprunner describe-service --service-arn {service_arn} --region {region}"
                describe_result = c.run(describe_cmd, warn=True, hide=True)

                if describe_result.ok:
                    service_data = json.loads(describe_result.stdout)
                    status = service_data['Service']['Status']

                    if status == 'RUNNING':
                        service_url = service_data['Service']['ServiceUrl']
                        print(f"\n{'='*60}")
                        print(f"✓ Deployment successful!")
                        print(f"{'='*60}")
                        print(f"\nService Status: RUNNING")
                        print(f"Service URL: https://{service_url}")
                        print(f"\nTest endpoints:")
                        print(f"  Health: https://{service_url}/health")
                        print(f"  API Docs: https://{service_url}/docs")
                        print(f"\nNext steps:")
                        print(f"  1. Grant IAM role access to secrets:")
                        print(f"     Action: secretsmanager:GetSecretValue")
                        print(f"     Resource: arn:aws:secretsmanager:{region}:*:secret:putplace/*")
                        if not auto_deploy:
                            print(f"\n  2. Manual deployment mode enabled.")
                            print(f"     Trigger deployments with:")
                            print(f"     invoke trigger-apprunner-deploy --service-name={service_name}")
                        break
                    elif status in ['CREATE_FAILED', 'DELETE_FAILED']:
                        print(f"\n✗ Deployment failed with status: {status}")
                        print(f"\nCheck logs:")
                        print(f"  aws logs tail /aws/apprunner/{service_name}/service --follow --region {region}")
                        break
                    else:
                        # Show progress
                        print(f"[{attempt+1}/{max_attempts}] Status: {status}...", end='\r')
                        time.sleep(10)
                        attempt += 1
                else:
                    print(f"\n⚠️  Failed to check service status")
                    break

            if attempt >= max_attempts:
                print(f"\n⚠️  Deployment monitoring timed out after 10 minutes")
                print(f"The deployment is still in progress. Check status with:")
                print(f"  aws apprunner describe-service --service-arn {service_arn} --region {region}")
        else:
            print(f"\n✗ Failed to create service")
            print("\nCommon issues:")
            print("  - GitHub connection not configured (set up in AWS console)")
            print("  - Invalid repository URL")
            print("  - Insufficient IAM permissions")
            print("  - Service name already exists")

    finally:
        import os
        os.unlink(source_config_file)


@task
def trigger_apprunner_deploy(c, service_name="putplace-api", region="eu-west-1"):
    """Trigger a manual deployment for App Runner service.

    Use this to deploy code changes when auto-deploy is disabled.

    Args:
        service_name: App Runner service name (default: putplace-api)
        region: AWS region (default: eu-west-1)

    Examples:
        invoke trigger-apprunner-deploy
        invoke trigger-apprunner-deploy --service-name=my-service
    """
    import json

    # Check for uncommitted changes
    print("Checking git status...")
    git_status = c.run("git status --porcelain", hide=True, warn=True)

    if git_status.ok and git_status.stdout.strip():
        print("\n⚠️  You have uncommitted changes!")
        print("\nUncommitted files:")
        for line in git_status.stdout.strip().split('\n'):
            print(f"  {line}")
        print("\nPlease commit or stash your changes before deploying:")
        print("  git add .")
        print("  git commit -m 'Your commit message'")
        print("  git push")
        print(f"\nThen run: invoke trigger-apprunner-deploy --service-name={service_name}")
        return 1

    # Check if local branch is up to date with remote
    print("Checking if local branch is up to date...")
    git_fetch = c.run("git fetch", hide=True, warn=True)
    if git_fetch.ok:
        git_status_remote = c.run(f"git status -uno", hide=True, warn=True)
        if git_status_remote.ok and "Your branch is behind" in git_status_remote.stdout:
            print("\n⚠️  Your local branch is behind the remote!")
            print("\nPull the latest changes:")
            print("  git pull")
            print(f"\nThen run: invoke trigger-apprunner-deploy --service-name={service_name}")
            return 1
        elif git_status_remote.ok and "Your branch is ahead" in git_status_remote.stdout:
            print("\n⚠️  Your local branch is ahead of the remote!")
            print("\nPush your changes:")
            print("  git push")
            print(f"\nThen run: invoke trigger-apprunner-deploy --service-name={service_name}")
            return 1

    print("✓ Git status clean and up to date\n")

    print(f"Triggering deployment for {service_name} in {region}...")

    # Get service ARN
    list_cmd = f"aws apprunner list-services --region {region}"
    result = c.run(list_cmd, hide=True, warn=True)

    if not result.ok:
        print("✗ Failed to list services")
        return 1

    import json
    services = json.loads(result.stdout)

    service_arn = None
    for svc in services.get('ServiceSummaryList', []):
        if svc['ServiceName'] == service_name:
            service_arn = svc['ServiceArn']
            break

    if not service_arn:
        print(f"✗ Service not found: {service_name}")
        print(f"\nAvailable services:")
        for svc in services.get('ServiceSummaryList', []):
            print(f"  - {svc['ServiceName']}")
        return 1

    # Start deployment
    deploy_cmd = f"aws apprunner start-deployment --service-arn {service_arn} --region {region}"
    result = c.run(deploy_cmd, warn=True, hide=True)

    if result.ok:
        print(f"\n✓ Deployment triggered successfully")

        # Monitor deployment status
        print(f"\nMonitoring deployment status...")
        print("This may take 3-5 minutes. Press Ctrl+C to stop monitoring (deployment will continue).\n")

        import time
        import json
        max_attempts = 30  # 5 minutes max
        attempt = 0

        while attempt < max_attempts:
            describe_cmd = f"aws apprunner describe-service --service-arn {service_arn} --region {region}"
            describe_result = c.run(describe_cmd, warn=True, hide=True)

            if describe_result.ok:
                service_data = json.loads(describe_result.stdout)
                status = service_data['Service']['Status']

                if status == 'RUNNING':
                    service_url = service_data['Service']['ServiceUrl']
                    print(f"\n{'='*60}")
                    print(f"✓ Deployment successful!")
                    print(f"{'='*60}")
                    print(f"\nService Status: RUNNING")
                    print(f"Service URL: https://{service_url}")
                    print(f"\nTest endpoints:")
                    print(f"  Health: https://{service_url}/health")
                    print(f"  API Docs: https://{service_url}/docs")
                    break
                elif status in ['CREATE_FAILED', 'DELETE_FAILED', 'OPERATION_FAILED']:
                    print(f"\n✗ Deployment failed with status: {status}")
                    print(f"\nCheck logs:")
                    print(f"  aws logs tail /aws/apprunner/{service_name}/application --follow --region {region}")
                    break
                else:
                    # Show progress
                    print(f"[{attempt+1}/{max_attempts}] Status: {status}...", end='\r')
                    time.sleep(10)
                    attempt += 1
            else:
                print(f"\n⚠️  Failed to check service status")
                break

        if attempt >= max_attempts:
            print(f"\n⚠️  Deployment monitoring timed out after 5 minutes")
            print(f"The deployment is still in progress. Check status with:")
            print(f"  aws apprunner describe-service --service-arn {service_arn} --region {region}")
    else:
        print(f"\n✗ Failed to trigger deployment")


@task
def list_apprunner_secrets(c, region="eu-west-1", show_values=False):
    """List PutPlace secrets from AWS Secrets Manager.

    Args:
        region: AWS region (default: eu-west-1)
        show_values: Show actual secret values (default: False - only shows keys)

    Examples:
        invoke list-apprunner-secrets
        invoke list-apprunner-secrets --show-values
        invoke list-apprunner-secrets --region=us-east-1
    """
    import json

    secret_names = [
        'putplace/mongodb',
        'putplace/admin',
        'putplace/aws-config'
    ]

    print(f"Listing PutPlace secrets in {region}...\n")

    for secret_name in secret_names:
        # Check if secret exists
        describe_cmd = f"aws secretsmanager describe-secret --secret-id {secret_name} --region {region}"
        result = c.run(describe_cmd, warn=True, hide=True)

        if not result.ok:
            print(f"✗ {secret_name}: Not found")
            continue

        # Get secret metadata
        secret_info = json.loads(result.stdout)
        created_date = secret_info.get('CreatedDate', 'Unknown')
        last_changed = secret_info.get('LastChangedDate', 'Unknown')

        print(f"✓ {secret_name}")
        print(f"  Created: {created_date}")
        print(f"  Last Changed: {last_changed}")

        if show_values:
            # Get secret value
            get_cmd = f"aws secretsmanager get-secret-value --secret-id {secret_name} --region {region}"
            value_result = c.run(get_cmd, warn=True, hide=True)

            if value_result.ok:
                secret_data = json.loads(value_result.stdout)
                secret_string = json.loads(secret_data['SecretString'])

                print(f"  Values:")
                for key, value in secret_string.items():
                    # Mask passwords
                    if 'PASSWORD' in key.upper():
                        display_value = '*' * len(value) if value else '(empty)'
                    else:
                        display_value = value
                    print(f"    {key}: {display_value}")
            else:
                print(f"  Values: Unable to retrieve")
        else:
            # Get secret value to show keys only
            get_cmd = f"aws secretsmanager get-secret-value --secret-id {secret_name} --region {region}"
            value_result = c.run(get_cmd, warn=True, hide=True)

            if value_result.ok:
                secret_data = json.loads(value_result.stdout)
                secret_string = json.loads(secret_data['SecretString'])
                keys = list(secret_string.keys())
                print(f"  Keys: {', '.join(keys)}")
            else:
                print(f"  Keys: Unable to retrieve")

        print()

    print("Tip: Use --show-values to see actual secret values (passwords will be masked)")


@task
def delete_apprunner_secrets(c, region="eu-west-1", force=False):
    """Delete PutPlace secrets from AWS Secrets Manager.

    Args:
        region: AWS region (default: eu-west-1)
        force: Force delete without recovery period (default: False)

    Examples:
        invoke delete-apprunner-secrets
        invoke delete-apprunner-secrets --force
    """
    import shlex

    cmd = [
        "uv", "run", "python", "-m",
        "putplace.scripts.putplace_configure",
        "--delete-aws-secrets",
        "--aws-region", region
    ]

    if force:
        cmd.append("--force-delete")

    print(f"Deleting PutPlace secrets from {region}...")
    result = c.run(shlex.join(cmd), warn=True, pty=True)

    if not result.ok:
        print("\nTo delete secrets manually:")
        print(f"  aws secretsmanager delete-secret --secret-id putplace/mongodb --region {region}")
        print(f"  aws secretsmanager delete-secret --secret-id putplace/admin --region {region}")
        print(f"  aws secretsmanager delete-secret --secret-id putplace/aws-config --region {region}")


@task
def configure_custom_domain(c, domain, service_name="putplace-api", region="eu-west-1"):
    """Configure a custom domain for App Runner service.

    This will:
    1. Associate the custom domain with the App Runner service
    2. Provide DNS records to add to Route 53

    Args:
        domain: Custom domain name (e.g., app.putplace.org)
        service_name: App Runner service name (default: putplace-api)
        region: AWS region (default: eu-west-1)

    Examples:
        invoke configure-custom-domain --domain=app.putplace.org
    """
    import json

    print(f"\n{'='*60}")
    print(f"Configuring Custom Domain for App Runner")
    print(f"{'='*60}")
    print(f"Domain: {domain}")
    print(f"Service: {service_name}")
    print(f"Region: {region}")
    print(f"{'='*60}\n")

    # Get service ARN
    print("Finding App Runner service...")
    list_cmd = f"aws apprunner list-services --region {region}"
    result = c.run(list_cmd, warn=True, hide=True)

    if not result.ok:
        print("✗ Failed to list services")
        return 1

    services = json.loads(result.stdout)
    service_arn = None

    for svc in services.get('ServiceSummaryList', []):
        if svc['ServiceName'] == service_name:
            service_arn = svc['ServiceArn']
            break

    if not service_arn:
        print(f"✗ Service not found: {service_name}")
        return 1

    print(f"✓ Found service: {service_arn}\n")

    # Associate custom domain
    print(f"Associating custom domain '{domain}'...")
    associate_cmd = f"aws apprunner associate-custom-domain --service-arn {service_arn} --domain-name {domain} --region {region}"
    result = c.run(associate_cmd, warn=True, hide=False)

    if result.ok:
        response = json.loads(result.stdout)

        print(f"\n{'='*60}")
        print(f"✓ Custom domain association initiated!")
        print(f"{'='*60}\n")

        # Extract DNS records
        dns_target = response.get('DNSTarget', 'N/A')
        custom_domain = response.get('CustomDomain', {})
        cert_validation_records = custom_domain.get('CertificateValidationRecords', [])

        print(f"DNS Configuration Required:")
        print(f"{'='*60}\n")

        # CNAME record for the domain
        print(f"1. Add CNAME record for your domain:")
        print(f"   Type: CNAME")
        print(f"   Name: {domain}")
        print(f"   Value: {dns_target}")
        print(f"   TTL: 300 (or your preference)\n")

        # Certificate validation records
        if cert_validation_records:
            print(f"2. Add certificate validation records:")
            for i, record in enumerate(cert_validation_records, 1):
                print(f"\n   Record {i}:")
                print(f"   Type: {record.get('Type', 'CNAME')}")
                print(f"   Name: {record.get('Name', 'N/A')}")
                print(f"   Value: {record.get('Value', 'N/A')}")
                print(f"   Status: {record.get('Status', 'PENDING')}")

        print(f"\n{'='*60}")
        print(f"Route 53 Setup Commands:")
        print(f"{'='*60}\n")

        # Get hosted zone ID
        print("Finding Route 53 hosted zone for putplace.org...")
        zone_cmd = "aws route53 list-hosted-zones-by-name --dns-name putplace.org --max-items 1"
        zone_result = c.run(zone_cmd, warn=True, hide=True)

        if zone_result.ok:
            zones = json.loads(zone_result.stdout)
            hosted_zones = zones.get('HostedZones', [])

            if hosted_zones:
                zone_id = hosted_zones[0]['Id'].split('/')[-1]

                print(f"✓ Found hosted zone: {zone_id}\n")
                print(f"Run these commands to create DNS records:\n")

                # CNAME record for domain
                print(f"# 1. Create CNAME record for {domain}")
                print(f'cat > /tmp/change-batch-cname.json << EOF')
                print(f'{{')
                print(f'  "Changes": [{{')
                print(f'    "Action": "UPSERT",')
                print(f'    "ResourceRecordSet": {{')
                print(f'      "Name": "{domain}",')
                print(f'      "Type": "CNAME",')
                print(f'      "TTL": 300,')
                print(f'      "ResourceRecords": [{{')
                print(f'        "Value": "{dns_target}"')
                print(f'      }}]')
                print(f'    }}')
                print(f'  }}]')
                print(f'}}')
                print(f'EOF')
                print(f'\naws route53 change-resource-record-sets \\')
                print(f'  --hosted-zone-id {zone_id} \\')
                print(f'  --change-batch file:///tmp/change-batch-cname.json\n')

                # Certificate validation records
                if cert_validation_records:
                    for i, record in enumerate(cert_validation_records, 1):
                        print(f"# {i+1}. Create certificate validation record {i}")
                        print(f'cat > /tmp/change-batch-cert-{i}.json << EOF')
                        print(f'{{')
                        print(f'  "Changes": [{{')
                        print(f'    "Action": "UPSERT",')
                        print(f'    "ResourceRecordSet": {{')
                        print(f'      "Name": "{record.get("Name", "")}",')
                        print(f'      "Type": "{record.get("Type", "CNAME")}",')
                        print(f'      "TTL": 300,')
                        print(f'      "ResourceRecords": [{{')
                        print(f'        "Value": "{record.get("Value", "")}"')
                        print(f'      }}]')
                        print(f'    }}')
                        print(f'  }}]')
                        print(f'}}')
                        print(f'EOF')
                        print(f'\naws route53 change-resource-record-sets \\')
                        print(f'  --hosted-zone-id {zone_id} \\')
                        print(f'  --change-batch file:///tmp/change-batch-cert-{i}.json\n')

        print(f"{'='*60}")
        print(f"Next Steps:")
        print(f"{'='*60}")
        print(f"1. Create the DNS records shown above in Route 53")
        print(f"2. Wait for DNS propagation (5-10 minutes)")
        print(f"3. Wait for certificate validation (5-30 minutes)")
        print(f"4. Check domain status:")
        print(f"   invoke check-custom-domain --domain={domain}")
        print(f"\nOnce validated, your service will be available at:")
        print(f"  https://{domain}")

    else:
        print(f"\n✗ Failed to associate custom domain")
        print(f"\nCommon issues:")
        print(f"  - Domain already associated with another service")
        print(f"  - Invalid domain name format")
        print(f"  - Service not in RUNNING state")


@task
def check_custom_domain(c, domain, service_name="putplace-api", region="eu-west-1"):
    """Check status of custom domain configuration.

    Args:
        domain: Custom domain name (e.g., app.putplace.org)
        service_name: App Runner service name (default: putplace-api)
        region: AWS region (default: eu-west-1)

    Examples:
        invoke check-custom-domain --domain=app.putplace.org
    """
    import json

    # Get service ARN
    list_cmd = f"aws apprunner list-services --region {region}"
    result = c.run(list_cmd, warn=True, hide=True)

    if not result.ok:
        print("✗ Failed to list services")
        return 1

    services = json.loads(result.stdout)
    service_arn = None

    for svc in services.get('ServiceSummaryList', []):
        if svc['ServiceName'] == service_name:
            service_arn = svc['ServiceArn']
            break

    if not service_arn:
        print(f"✗ Service not found: {service_name}")
        return 1

    # Describe custom domain
    describe_cmd = f"aws apprunner describe-custom-domains --service-arn {service_arn} --region {region}"
    result = c.run(describe_cmd, warn=True, hide=True)

    if result.ok:
        response = json.loads(result.stdout)
        custom_domains = response.get('CustomDomains', [])

        print(f"\n{'='*60}")
        print(f"Custom Domain Status")
        print(f"{'='*60}\n")

        domain_found = False
        for custom_domain in custom_domains:
            if custom_domain.get('DomainName') == domain:
                domain_found = True
                status = custom_domain.get('Status', 'UNKNOWN')

                print(f"Domain: {domain}")
                print(f"Status: {status}")
                print(f"DNS Target: {response.get('DNSTarget', 'N/A')}\n")

                # Certificate validation records
                cert_records = custom_domain.get('CertificateValidationRecords', [])
                if cert_records:
                    print(f"Certificate Validation Records:")
                    for record in cert_records:
                        print(f"  Name: {record.get('Name', 'N/A')}")
                        print(f"  Status: {record.get('Status', 'PENDING')}")
                        print()

                if status == 'active':
                    print(f"✓ Domain is active and ready!")
                    print(f"\nYour service is available at:")
                    print(f"  https://{domain}")
                elif status == 'pending_certificate_dns_validation':
                    print(f"⏳ Waiting for DNS validation...")
                    print(f"\nMake sure the DNS records are created in Route 53.")
                elif status == 'creating':
                    print(f"⏳ Domain configuration in progress...")
                else:
                    print(f"⚠️  Status: {status}")

                break

        if not domain_found:
            print(f"✗ Domain '{domain}' not found in service configuration")
            print(f"\nAssociated domains:")
            for custom_domain in custom_domains:
                print(f"  - {custom_domain.get('DomainName', 'N/A')}")
    else:
        print(f"✗ Failed to describe custom domains")


@task
def remove_custom_domain(c, domain, service_name="putplace-api", region="eu-west-1"):
    """Remove a custom domain from App Runner service.

    Args:
        domain: Custom domain name (e.g., app.putplace.org)
        service_name: App Runner service name (default: putplace-api)
        region: AWS region (default: eu-west-1)

    Examples:
        invoke remove-custom-domain --domain=app.putplace.org
    """
    import json

    # Get service ARN
    list_cmd = f"aws apprunner list-services --region {region}"
    result = c.run(list_cmd, warn=True, hide=True)

    if not result.ok:
        print("✗ Failed to list services")
        return 1

    services = json.loads(result.stdout)
    service_arn = None

    for svc in services.get('ServiceSummaryList', []):
        if svc['ServiceName'] == service_name:
            service_arn = svc['ServiceArn']
            break

    if not service_arn:
        print(f"✗ Service not found: {service_name}")
        return 1

    print(f"Removing custom domain '{domain}' from {service_name}...")

    disassociate_cmd = f"aws apprunner disassociate-custom-domain --service-arn {service_arn} --domain-name {domain} --region {region}"
    result = c.run(disassociate_cmd, warn=True, hide=False)

    if result.ok:
        print(f"\n✓ Custom domain removed successfully")
        print(f"\nDon't forget to remove the DNS records from Route 53 if no longer needed.")
    else:
        print(f"\n✗ Failed to remove custom domain")


@task
def setup_apprunner_fixed_ip(c, region="eu-west-1", project_name="putplace"):
    """Setup fixed IP address for AppRunner instance (for MongoDB Atlas).

    Creates VPC infrastructure with NAT Gateway to provide a static Elastic IP
    for AppRunner egress traffic. This is required for MongoDB Atlas IP whitelisting.

    Args:
        region: AWS region (default: eu-west-1)
        project_name: Project name for resource tagging (default: putplace)

    Examples:
        invoke setup-apprunner-fixed-ip
        invoke setup-apprunner-fixed-ip --region=us-east-1
        invoke setup-apprunner-fixed-ip --region=eu-west-1 --project-name=myapp

    Cost: ~$32/month for NAT Gateway + data transfer costs

    See: APPRUNNER_FIXED_IP.md for detailed documentation
    """
    c.run(f"uv run python -m putplace.scripts.setup_apprunner_fixed_ip --region {region} --project-name {project_name}")


@task
def update_apprunner_vpc(c, service, vpc_connector_arn, region="eu-west-1", wait=True):
    """Update AppRunner service to use VPC Connector for fixed IP.

    Args:
        service: AppRunner service name or ARN
        vpc_connector_arn: VPC Connector ARN to use
        region: AWS region (default: eu-west-1)
        wait: Wait for update to complete (default: True)

    Examples:
        invoke update-apprunner-vpc \\
            --service=putplace-service \\
            --vpc-connector-arn="arn:aws:apprunner:eu-west-1:xxx:vpcconnector/putplace-vpc-connector/1/xxx"

        invoke update-apprunner-vpc \\
            --service=putplace-service \\
            --vpc-connector-arn="arn:..." \\
            --region=us-east-1 \\
            --wait=False

    Prerequisites:
        Run setup-apprunner-fixed-ip first to create VPC Connector

    See: APPRUNNER_FIXED_IP.md for detailed documentation
    """
    wait_flag = "--wait" if wait else ""
    c.run(f"uv run python -m putplace.scripts.update_apprunner_vpc {service} --vpc-connector-arn '{vpc_connector_arn}' --region {region} {wait_flag}")
