from fastapi import FastAPI, Security, HTTPException, Depends, status, requests, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.security import APIKeyHeader
from typing import Optional, Dict, List
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager
import os, glueops.setup_logging, traceback, base64, yaml, tempfile, json
from schemas.schemas import Message, CreateLightsailRequest, AwsCredentialsRequest, DeleteLightsailRequest, StorageBucketsRequest, AwsNukeAccountRequest, CaptainDomainNukeDataAndBackupsRequest
from util import storage, aws_lightsail, aws_setup_test_account_credentials, github
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
    
    # Return the full stack trace in the response
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal server error occurred.",
            "error": str(exc),
            "traceback": stack_trace,  # Include the full stack trace
        },
    )


@app.post("/v1/storage-buckets", response_class=PlainTextResponse, include_in_schema=False)
async def hello(request: StorageBucketsRequest):
    """
        For the provided captain_domain, this will DELETE and then create new/empty storage buckets for loki, tempo, and thanos.
    """
    return storage.create_all_buckets(request.captain_domain)


@app.post("/v1/setup-aws-account-credentials", response_class=PlainTextResponse)
async def create_credentials_for_aws_captain_account(request: AwsCredentialsRequest):
    """
    If you are testing in AWS/EKS you will need an AWS account to test with. This request will provide you with admin level credentials to the sub account you specify.
    This can also be used to just get Admin access to a desired sub account.
    """
    return aws_setup_test_account_credentials.create_admin_credentials_within_captain_account(request.aws_sub_account_name)


@app.delete("/v1/nuke-aws-captain-account", response_class=PlainTextResponse)
async def nuke_aws_captain_account(request: AwsNukeAccountRequest):
    """
     Submit the AWS account name you want to nuke (e.g. glueops-captain-foobar)
    """
    return github.nuke_aws_account_workflow(request.aws_sub_account_name)

@app.delete("/v1/nuke-captain-domain-data", response_class=PlainTextResponse)
async def nuke_captain_domain_data(request: CaptainDomainNukeDataAndBackupsRequest):
    """
     Submit the captain_domain/tenant you want to nuke (e.g. nonprod.foobar.onglueops.rocks). This will delete all backups and data for the provided captain_domain.
     
     This will remove things like the vault and cert-manager backups.

     Note: this may not delete things like Loki/Thanos/Tempo data as that may be managed outside of AWS.
    """
    return github.nuke_captain_domain_data_and_backups(request.captain_domain)

@app.post("/v1/chisel", response_class=PlainTextResponse, include_in_schema=False)
async def create_chisel_nodes(request: CreateLightsailRequest):
    """
        If you are testing within k3ds you will need chisel to provide you with load balancers.
        For a provided captain_domain this will delete any existing chisel nodes and provision new ones.
        Note: this will generally result in new IPs being provisioned.
    """
    return aws_lightsail.create_lightsail_instances(request)


@app.delete("/v1/chisel", include_in_schema=False)
async def delete_chisel_nodes(request: DeleteLightsailRequest):
    """
        When you are done testing with k3ds this will delete your chisel nodes and save on costs.
    """
    response = aws_lightsail.create_lightsail_instances(request)
    return JSONResponse(status_code=200, content={"message": response})


@app.get("/health", include_in_schema=False)
async def health():
    """health check

    Returns:
        dict: health status
    """
    return {"status": "healthy"}


@app.get("/version")
async def version():
    return {
        "version": os.getenv("VERSION", "unknown"),
        "commit_sha": os.getenv("COMMIT_SHA", "unknown"),
        "build_timestamp": os.getenv("BUILD_TIMESTAMP", "unknown")
    }