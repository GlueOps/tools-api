from fastapi import FastAPI, Security, HTTPException, Depends, status, requests, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.security import APIKeyHeader
from typing import Optional, Dict, List
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager
import os, glueops.setup_logging, traceback, base64, yaml, tempfile, json
from schemas.schemas import Message, CreateLightsailRequest, AwsCredentialsRequest, DeleteLightsailRequest, StorageBucketsRequest
from util import storage, aws_lightsail, aws_setup_test_account_credentials
from fastapi.responses import RedirectResponse


# Configure logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logger = glueops.setup_logging.configure(level=LOG_LEVEL)


app = FastAPI()

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


@app.post("/v1/aws-test-account-credentials", response_class=PlainTextResponse)
async def create_credentials_for_aws_captain_account(request: AwsCredentialsRequest):
    """
    If you are testing in AWS/EKS you will need an AWS account to test with. This request will provide you with admin level credentials to the sub account you specify.
    This can also be used to just get Admin access to a desired sub account.
    """
    return aws_setup_test_account_credentials.create_admin_credentials_within_captain_account(request.aws_sub_account_name)


@app.get("/v1/nuke", response_class=PlainTextResponse)
async def nuke_or_cleanup_environments():
    """
     Provides links to Github Actions so that you can nuke your Captain AWS account or reset your captain_domain/environment
    """
    return f"""
     To nuke the AWS account (kubernetes/etc.) run the job here:
     https://github.com/internal-GlueOps/gha-aws-cleanup/actions/workflows/aws-nuke-account.yml

     To nuke the tenant/captain domain data and any backups run the job here: 
     https://github.com/internal-GlueOps/gha-aws-cleanup/actions/workflows/nuke-captain-domain-data-and-backups.yml
     """

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


@app.get("/health")
async def health():
    """health check

    Returns:
        dict: health status
    """
    return {"status": "healthy"}