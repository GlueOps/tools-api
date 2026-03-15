import requests
import re
import time
import os, glueops.setup_logging, traceback, json
from fastapi import HTTPException

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logger = glueops.setup_logging.configure(level=LOG_LEVEL)

GITHUB_API_VERSION = "2026-03-10"
REPO = "internal-GlueOps/gha-tools-api"
REPO_API_BASE = f"https://api.github.com/repos/{REPO}"
REPO_HTML_BASE = f"https://github.com/{REPO}"


def _get_headers():
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        raise ValueError("GITHUB_TOKEN environment variable is not set")
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {github_token}",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }


def _get_workflow_run_id(workflow_file: str):
    """Poll for the most recent run of a workflow that was just dispatched.

    Returns:
        dict: run_id and run_url of the workflow run, or None values if not found.
    """
    url = f"{REPO_API_BASE}/actions/workflows/{workflow_file}/runs"
    headers = _get_headers()
    for attempt in range(6):
        time.sleep(2)
        response = requests.get(url, headers=headers, params={"per_page": 1}, timeout=30)
        if response.status_code == 200:
            runs = response.json().get("workflow_runs", [])
            if runs:
                run = runs[0]
                logger.info(f"Found workflow run id={run['id']} for {workflow_file}")
                return {"run_id": run["id"], "run_url": run["html_url"]}
        logger.info(f"Polling for workflow run (attempt {attempt + 1}/6) for {workflow_file}")
    logger.warning(f"Could not find workflow run for {workflow_file} after polling")
    return {"run_id": None, "run_url": None}


def call_github_workflow(github_dispatch_url: str, workflow_inputs: dict = None):
    """Dispatches a GitHub Actions workflow.

    Returns:
        int: status code
    """
    headers = _get_headers()
    payload = {"ref": "refs/heads/main"}

    if workflow_inputs:
        payload["inputs"] = workflow_inputs
    payload_json = json.dumps(payload)
    response = requests.post(url=github_dispatch_url, data=payload_json, headers=headers, timeout=30)
    logger.info(f"Response code: {response.status_code} Submitting GitHub Workflow to:{github_dispatch_url} with inputs: {workflow_inputs}")
    return response.status_code


def _dispatch_and_get_run(workflow_file: str, workflow_inputs: dict = None):
    """Dispatch a workflow and return the response with run details."""
    dispatch_url = f"{REPO_API_BASE}/actions/workflows/{workflow_file}/dispatches"
    all_jobs_url = f"{REPO_HTML_BASE}/actions/workflows/{workflow_file}"
    status_code = call_github_workflow(dispatch_url, workflow_inputs)
    if status_code != 204:
        raise ValueError(f"GitHub workflow dispatch failed with status {status_code}")
    run_info = _get_workflow_run_id(workflow_file)
    return {
        "status_code": status_code,
        "all_jobs_url": all_jobs_url,
        "run_id": run_info["run_id"],
        "run_url": run_info["run_url"],
    }


def get_workflow_run_status(run_url: str):
    """Get the status of a GitHub Actions workflow run from its URL.

    Args:
        run_url: A GitHub Actions run URL, e.g. https://github.com/owner/repo/actions/runs/12345678

    Returns:
        dict: run status details
    """
    match = re.match(r"https://github\.com/([^/]+/[^/]+)/actions/runs/(\d+)", run_url)
    if not match:
        raise HTTPException(status_code=400, detail=f"Invalid GitHub Actions run URL: {run_url}")

    owner_repo = match.group(1)
    run_id = match.group(2)
    api_url = f"https://api.github.com/repos/{owner_repo}/actions/runs/{run_id}"

    response = requests.get(api_url, headers=_get_headers(), timeout=30)
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"GitHub API returned {response.status_code} for run {run_id}")

    data = response.json()
    return {
        "run_id": data["id"],
        "name": data.get("name"),
        "status": data["status"],
        "conclusion": data.get("conclusion"),
        "run_url": data["html_url"],
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
    }


def nuke_aws_account_workflow(aws_sub_account_name):
    return _dispatch_and_get_run(
        "aws-nuke-account.yml",
        {"AWS_ACCOUNT_NAME_TO_NUKE": aws_sub_account_name},
    )


def nuke_captain_domain_data_and_backups(captain_domain):
    return _dispatch_and_get_run(
        "nuke-captain-domain-data-and-backups.yml",
        {"CAPTAIN_DOMAIN_TO_NUKE": captain_domain},
    )


def reset_tenant_github_organization(captain_domain, delete_all_existing_repos, custom_domain, enable_custom_domain):
    return _dispatch_and_get_run(
        "reset-tenant-github-organization.yml",
        {
            "CAPTAIN_DOMAIN": captain_domain,
            "DELETE_ALL_EXISTING_REPOS": str(delete_all_existing_repos),
            "CUSTOM_DOMAIN": custom_domain,
            "ENABLE_CUSTOM_DOMAIN": str(enable_custom_domain),
        },
    )
