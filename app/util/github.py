import requests
import os
import json

def call_github_workflow(github_dispatch_url: str, workflow_inputs: dict = None):
    """Calls the github user management workflow

    Returns:
        int: status code
    """
    github_token = os.getenv("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {github_token}", "X-GitHub-Api-Version": "2022-11-28"}
    payload = {"ref": "refs/heads/main"}
    
    if workflow_inputs:
        payload["inputs"] = workflow_inputs

    payload_json = json.dumps(payload)
    response = requests.post(url=github_dispatch_url, data=payload_json, headers=headers)
    return response.status_code  

def nuke_aws_account_workflow(aws_sub_account_name):
    call_github_workflow("https://api.github.com/repos/internal-GlueOps/gha-aws-cleanup/actions/workflows/aws-nuke-account.yml/dispatches", {"AWS_ACCOUNT_NAME_TO_NUKE": aws_sub_account_name})
    return "View all jobs: https://github.com/internal-GlueOps/gha-aws-cleanup/actions/workflows/aws-nuke-account.yml"

def nuke_captain_domain_data_and_backups(captain_domain):
    call_github_workflow("https://api.github.com/repos/internal-GlueOps/gha-aws-cleanup/actions/workflows/nuke-captain-domain-data-and-backups.yml/dispatches", {"CAPTAIN_DOMAIN_TO_NUKE": captain_domain})
    return "View all jobs: https://github.com/internal-GlueOps/gha-aws-cleanup/actions/workflows/nuke-captain-domain-data-and-backups.yml"
