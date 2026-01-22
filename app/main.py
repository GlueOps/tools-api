from fastapi import FastAPI, Security, HTTPException, Depends, status, requests, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.security import APIKeyHeader
from typing import Optional, Dict, List
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager
import os, glueops.setup_logging, traceback, base64, yaml, tempfile, json
from schemas.schemas import Message, AwsCredentialsRequest, StorageBucketsRequest, AwsNukeAccountRequest, CaptainDomainNukeDataAndBackupsRequest, ChiselNodesRequest, ChiselNodesDeleteRequest, ResetGitHubOrganizationRequest, OpsgenieAlertsManifestRequest
from util import storage, aws_setup_test_account_credentials, github, hetzner, opsgenie
from fastapi.responses import RedirectResponse


# Configure logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logger = glueops.setup_logging.configure(level=LOG_LEVEL)


app = FastAPI(
    title="Tools API",
    description="Various APIs to help you speed up your development and testing.",
    version=os.getenv("VERSION", "unknown"),
    swagger_ui_parameters={"defaultModelsExpandDepth": -1}
)

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Extract the full stack trace
    stack_trace = traceback.format_exc()

    logger.error(f"Exception: {str(exc)} STACK_TRACE: {stack_trace}")
    
    # Return the full stack trace in the response
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal server error occurred.",
            "error": str(exc),
            "traceback": stack_trace,  # Include the full stack trace
        },
    )


@app.post("/v1/storage-buckets", response_class=PlainTextResponse, summary="Create/Re-create storage buckets that can be used for V2 of our monitoring stack that is Otel based")
async def hello(request: StorageBucketsRequest):
    """
        Note: this can be a DESTRUCTIVE operation
        For the provided captain_domain, this will DELETE and then create new/empty storage buckets for loki, tempo, and thanos.
    """
    return storage.create_all_buckets(request.captain_domain)


@app.post("/v1/setup-aws-account-credentials", response_class=PlainTextResponse, summary="Wether it's to create an EKS cluster or to test other things out in an isolated AWS account. These creds will give you Admin level access to the requested account.")
async def create_credentials_for_aws_captain_account(request: AwsCredentialsRequest):
    """
    If you are testing in AWS/EKS you will need an AWS account to test with. This request will provide you with admin level credentials to the sub account you specify.
    This can also be used to just get Admin access to a desired sub account.
    """
    return aws_setup_test_account_credentials.create_admin_credentials_within_captain_account(request.aws_sub_account_name)


@app.delete("/v1/nuke-aws-captain-account", response_class=PlainTextResponse, summary="Run this after you are done testing within AWS. This will clean up orphaned resources. Note: you may have to run this 2x.")
async def nuke_aws_captain_account(request: AwsNukeAccountRequest):
    """
     Submit the AWS account name you want to nuke (e.g. glueops-captain-foobar)
    """
    return github.nuke_aws_account_workflow(request.aws_sub_account_name)

@app.delete("/v1/nuke-captain-domain-data", response_class=PlainTextResponse, summary="Deletes all backups/data for a provided captain_domain. Running this before a cluster creation helps ensure a clean environment.")
async def nuke_captain_domain_data(request: CaptainDomainNukeDataAndBackupsRequest):
    """
     Submit the captain_domain/tenant you want to nuke (e.g. nonprod.foobar.onglueops.rocks). This will delete all backups and data for the provided captain_domain.
     
     This will remove things like the vault and cert-manager backups.

     Note: this may not delete things like Loki/Thanos/Tempo data as that may be managed outside of AWS.
    """
    return github.nuke_captain_domain_data_and_backups(request.captain_domain)


@app.delete("/v1/reset-github-organization", response_class=PlainTextResponse, summary="Resets the GitHub Organization to make it easier to get a new dev cluster runner for Dev")
async def reset_github_organization(request: ResetGitHubOrganizationRequest):
    """
     Submit the dev captain_domain you want to nuke (e.g. nonprod.foobar.onglueops.rocks). This will reset the GitHub organization so that you can easily get up and running with a new dev cluster.
     
     This will reset your deployment-configurations repository, it'll bring over a working regcred, and application repos with working github actions so that you can quickly work on the GlueOps stack.

     WARNING: By default delete_all_existing_repos = True. Please set it to False or make a manual backup if you are concerned about any dataloss within your tenant org (e.g. github.com/development-tenant-*)

    """
    return github.reset_tenant_github_organization(request.captain_domain, request.delete_all_existing_repos, request.custom_domain, request.enable_custom_domain)

@app.post("/v1/chisel", response_class=PlainTextResponse, summary="Creates Chisel nodes for dev/k3d clusters. This allows us to mimic a Cloud Controller for Loadbalancers (e.g. NLBs with EKS)")
async def create_chisel_nodes(request: ChiselNodesRequest):
    """
        If you are testing within k3ds you will need chisel to provide you with load balancers.
        For a provided captain_domain this will delete any existing chisel nodes and provision new ones.
        Note: this will generally result in new IPs being provisioned.
    """
    logger.info(f"Received POST request to create chisel nodes for captain_domain: {request.captain_domain}")
    result = hetzner.create_instances(request)
    logger.info(f"Successfully completed chisel node creation for captain_domain: {request.captain_domain}")
    return result


@app.delete("/v1/chisel", summary="Deletes your chisel nodes. Please run this when you are done with development to save on costs.")
async def delete_chisel_nodes(request: ChiselNodesDeleteRequest):
    """
        When you are done testing with k3ds this will delete your chisel nodes and save on costs.
    """
    logger.info(f"Received DELETE request to delete chisel nodes for captain_domain: {request.captain_domain}")
    response = hetzner.delete_existing_servers(request)
    logger.info(f"Successfully completed chisel node deletion for captain_domain: {request.captain_domain}")
    return JSONResponse(status_code=200, content={"message": "Successfully deleted chisel nodes."})


@app.post("/v1/opsgenie", response_class=PlainTextResponse, summary="Creates Opsgenie Alerts Manifest")
async def create_opsgeniealerts_manifest(request: OpsgenieAlertsManifestRequest):
    """
        Create a opsgenie/alertmanager configuration. Do this for any clusters you want alerts on.
    """
    return opsgenie.create_opsgeniealerts_manifest(request)

@app.get("/health", include_in_schema=False)
async def health():
    """health check

    Returns:
        dict: health status
    """
    return {"status": "healthy"}


@app.get("/version", summary="Contains version information about this tools-api")
async def version():
    return {
        "version": os.getenv("VERSION", "unknown"),
        "commit_sha": os.getenv("COMMIT_SHA", "unknown"),
        "build_timestamp": os.getenv("BUILD_TIMESTAMP", "unknown")
    }
