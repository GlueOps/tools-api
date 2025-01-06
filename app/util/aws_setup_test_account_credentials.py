import boto3
import os
from fastapi import HTTPException
import json



def create_admin_credentials_within_captain_account(aws_sub_account_name):
    aws_access_key = os.getenv("AWS_GLUEOPS_ROCKS_ORG_ACCESS_KEY")
    aws_secret_key = os.getenv("AWS_GLUEOPS_ROCKS_ORG_SECRET_KEY")

    # Initialize AWS clients (using server-side credentials)
    client = boto3.client('organizations', aws_access_key_id=aws_access_key, aws_secret_access_key=aws_secret_key)
    sts_client = boto3.client('sts', aws_access_key_id=aws_access_key, aws_secret_access_key=aws_secret_key)
    
    # Step 1: Check if the current account is the root account
    root_account_id = client.describe_organization()['Organization']['MasterAccountId']
    current_account_id = sts_client.get_caller_identity()['Account']
    
    if current_account_id != root_account_id:
        raise HTTPException(status_code=400, detail="This is not the root account. Exiting.")
    
    # Step 2: Get account ID of the sub-account based on provided account name
    account_name = aws_sub_account_name

    # Initialize a list to store account details
    all_accounts = []
    # Initially set NextToken to None
    next_token = None
    while True:
        # Call list_accounts with the NextToken if available
        if next_token:
            response = client.list_accounts(NextToken=next_token)
        else:
            response = client.list_accounts()
        
        # Add the accounts in the current response to the all_accounts list
        all_accounts.extend(response['Accounts'])
        
        # Check if there is another page of results
        next_token = response.get('NextToken')
        
        # If there's no NextToken, it means we've reached the end of the list
        if not next_token:
            break
    

    sub_account = next(
        (account for account in all_accounts if account['Name'] == account_name), None
    )
    if not sub_account:
        raise HTTPException(status_code=404, detail="Account not found.")
    
    sub_account_id = sub_account['Id']
    
    # Step 3: Assume role in the sub-account to retrieve credentials
    assume_role_response = sts_client.assume_role(
        RoleArn=f"arn:aws:iam::{sub_account_id}:role/OrganizationAccountAccessRole",
        RoleSessionName="SubAccountAccess"
    )
    
    # Step 4: Extract the credentials from the assumed role
    session_token = assume_role_response['Credentials']['SessionToken']
    access_key_id = assume_role_response['Credentials']['AccessKeyId']
    secret_access_key = assume_role_response['Credentials']['SecretAccessKey']
    
    # Set these credentials for subsequent AWS calls
    os.environ['AWS_SESSION_TOKEN'] = session_token
    os.environ['AWS_ACCESS_KEY_ID'] = access_key_id
    os.environ['AWS_SECRET_ACCESS_KEY'] = secret_access_key
    
    # Step 5: Create IAM user and assign a policy (for managing services)
    iam_client = boto3.client('iam')
    iam_user_name = "dev-deployment-svc-account"
    iam_role_name = "glueops-captain-role"
    iam_policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
    
    # Create IAM user
    try:
        iam_client.create_user(UserName=iam_user_name)
        iam_client.attach_user_policy(UserName=iam_user_name, PolicyArn=iam_policy_arn)
    except iam_client.exceptions.EntityAlreadyExistsException:
        pass  # If the user already exists, skip creating it
    
    # Create access keys for the user
    user_keys = iam_client.create_access_key(UserName=iam_user_name)
    access_key = user_keys['AccessKey']['AccessKeyId']
    secret_key = user_keys['AccessKey']['SecretAccessKey']
    
    # Step 6: Create role and attach the policy (if not already created)
    assume_role_policy_document = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "AWS": f"arn:aws:iam::{sub_account_id}:root"
                },
                "Action": "sts:AssumeRole"
            }
        ]
    }
    
    try:
        iam_client.create_role(
            RoleName=iam_role_name,
            AssumeRolePolicyDocument=json.dumps(assume_role_policy_document)
        )
        iam_client.attach_role_policy(RoleName=iam_role_name, PolicyArn=iam_policy_arn)
    except iam_client.exceptions.EntityAlreadyExistsException:
        pass  # If the role already exists, skip creating it
    
    # Get the ARN of the created role
    arn_of_role_created = iam_client.get_role(RoleName=iam_role_name)['Role']['Arn']
    
    # Step 7: Generate the .env content (in the format you provided)
    env_content = f"""
# Run the following in your codespace environment to create your .env for {aws_sub_account_name}:

cat <<ENV >> $(pwd)/.env
export AWS_ACCESS_KEY_ID={access_key}
export AWS_SECRET_ACCESS_KEY={secret_key}
export AWS_DEFAULT_REGION=us-west-2
#aws eks update-kubeconfig --region us-west-2 --name captain-cluster --role-arn {arn_of_role_created}
ENV

# Here is the iam_role_to_assume that you will need to specify in your terraform module for {aws_sub_account_name}:
# {arn_of_role_created}

    """

    return env_content
