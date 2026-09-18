from fastapi import FastAPI, Security, HTTPException, Depends, status, requests, Request
from fastapi.responses import JSONResponse, PlainTextResponse, HTMLResponse
from fastapi.security import APIKeyHeader
from fastapi.openapi.docs import get_swagger_ui_html
from typing import Optional, Dict, List
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager
import os, glueops.setup_logging, traceback, base64, yaml, tempfile, json
from schemas.schemas import Message, AwsCredentialsRequest, StorageBucketsRequest, AwsNukeAccountRequest, CaptainDomainNukeDataAndBackupsRequest, K3dLbNodesRequest, K3dLbNodesDeleteRequest, ResetGitHubOrganizationRequest, IncidentioAlertsManifestRequest, CaptainManifestsRequest, KubeApiserverManifestRequest, KubeRbacManifestRequest, GitHubWorkflowRunStatusRequest, VersionResponse
from util import storage, aws_setup_test_account_credentials, github, k3d_lb, incidentio, captain_manifests, kube_apiserver, kube_rbac
from fastapi.responses import RedirectResponse


# Configure logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logger = glueops.setup_logging.configure(level=LOG_LEVEL)

# Build metadata, injected as build args by the container image workflow. Read once here so
# the docs page and the /version endpoint cannot drift apart.
VERSION = os.getenv("VERSION", "UNKNOWN")
COMMIT_SHA = os.getenv("COMMIT_SHA", "UNKNOWN")
SHORT_SHA = os.getenv("SHORT_SHA", "UNKNOWN")
BUILD_TIMESTAMP = os.getenv("BUILD_TIMESTAMP", "UNKNOWN")
GIT_REF = os.getenv("GIT_REF", "UNKNOWN")


def _build_line():
    """One-line build identity for the top of the docs page.

    Outside a built image (e.g. `fastapi dev`) these are all UNKNOWN, so the commit is
    rendered as plain text rather than a link that would 404 on GitHub.
    """
    commit = (
        f"[`{SHORT_SHA}`](https://github.com/GlueOps/tools-api/commit/{COMMIT_SHA})"
        if COMMIT_SHA != "UNKNOWN"
        else f"`{SHORT_SHA}`"
    )
    return f"**`{VERSION}`** · commit {commit} · ref `{GIT_REF}` · built {BUILD_TIMESTAMP}\n"


API_DESCRIPTION = _build_line() + """
Internal APIs for GlueOps platform engineers: stand up dev/test infrastructure,
generate cluster manifests, and tear it all down when you are done.

### Conventions

* Most endpoints are keyed on a **`captain_domain`** (e.g. `nonprod.foobar.onglueops.rocks`).
  The first label (`nonprod`) is typically the tenant namespace.
* Manifest endpoints return **plain-text YAML** that you commit to a deployment-configurations
  repository — they do not apply anything to a cluster.
* Every example value in this page is a real, working example. Click **Try it out** on any
  endpoint to fire the request straight from here.

### ⚠️ Destructive endpoints

Operations marked **(destructive)** delete real infrastructure, repositories, or backups.
Double-check the `captain_domain` / account name before running them.

### Other views

[ReDoc](/redoc) · [OpenAPI spec](/openapi.json) ·
the [`tools` CLI](https://github.com/GlueOps/tools-api) wraps every endpoint below for headless machines.
"""

TAGS_METADATA = [
    {
        "name": "AWS",
        "description": "Admin credentials for captain sub-accounts, and cleanup when testing is done.",
    },
    {
        "name": "Storage & Backups",
        "description": "MinIO/S3 buckets for the Otel monitoring stack, plus backup and data cleanup.",
    },
    {
        "name": "GitHub",
        "description": "Tenant organization resets and GitHub Actions workflow status.",
    },
    {
        "name": "Load Balancers",
        "description": (
            "Chisel exit nodes that mimic a cloud controller for load balancers in k3d clusters. "
            "`/v1/k3d-lb-nodes` provisions them on Proxmox, with placement decided by Waggle."
        ),
    },
    {
        "name": "Manifests",
        "description": "Generate Kubernetes/ArgoCD YAML for captain clusters. Output is plain text — nothing is applied.",
    },
    {
        "name": "Alerting",
        "description": "Alertmanager configuration manifests for incident.io.",
    },
]

app = FastAPI(
    title="Tools API",
    description=API_DESCRIPTION,
    version=VERSION,
    openapi_tags=TAGS_METADATA,
    # Swagger UI is served by the custom /docs route below so the CSS can be injected.
    docs_url=None,
    swagger_ui_parameters={
        # Hide the bottom "Schemas" dump; models are shown inline per endpoint.
        "defaultModelsExpandDepth": -1,
        # Land on a scannable list of collapsed operations rather than a wall of forms.
        "docExpansion": "none",
        # Search box that filters by tag/path.
        "filter": True,
        "tryItOutEnabled": True,
        "displayRequestDuration": True,
        "persistAuthorization": True,
        "syntaxHighlight.theme": "obsidian",
    },
)

# Every operation's documented responses are FastAPI boilerplate: an identical 422
# HTTPValidationError, and a 200 whose schema is a bare string or an empty object. Hiding
# the block keeps the useful half of each operation (parameters, examples) on screen. The
# live "Server response" from Try it out lives in the same wrapper, so it is left visible.
SWAGGER_UI_CSS = """
<style>
  .swagger-ui .responses-wrapper > .opblock-section-header { display: none; }
  .swagger-ui table.responses-table:not(.live-responses-table) { display: none; }
</style>
"""


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")


@app.get("/docs", include_in_schema=False)
async def swagger_ui():
    html = get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        # FastAPI only applies these to its own built-in docs route, which we replaced.
        swagger_ui_parameters=app.swagger_ui_parameters,
    )
    return HTMLResponse(html.body.decode().replace("</head>", SWAGGER_UI_CSS + "</head>"))

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


@app.post("/v1/storage-buckets", response_class=PlainTextResponse, tags=["Storage & Backups"], summary="Recreate monitoring storage buckets (destructive)")
async def hello(request: StorageBucketsRequest):
    """
        Create/re-create the storage buckets used by V2 of our monitoring stack (the Otel based one).

        Note: this can be a DESTRUCTIVE operation.
        For the provided captain_domain, this will DELETE and then create new/empty storage buckets for loki, tempo, and thanos.
    """
    return storage.create_all_buckets(request.captain_domain)


@app.post("/v1/setup-aws-account-credentials", response_class=PlainTextResponse, tags=["AWS"], summary="Get admin credentials for an AWS sub-account")
async def create_credentials_for_aws_captain_account(request: AwsCredentialsRequest):
    """
    If you are testing in AWS/EKS you will need an AWS account to test with. This request will provide you with admin level credentials to the sub account you specify.
    This can also be used to just get Admin access to a desired sub account.
    """
    return aws_setup_test_account_credentials.create_admin_credentials_within_captain_account(request.aws_sub_account_name)


@app.delete("/v1/nuke-aws-captain-account", tags=["AWS"], summary="Nuke an AWS sub-account (destructive)")
async def nuke_aws_captain_account(request: AwsNukeAccountRequest):
    """
     Run this after you are done testing within AWS. This will clean up orphaned resources.

     Submit the AWS account name you want to nuke (e.g. glueops-captain-foobar).

     Note: you may have to run this 2x.
    """
    return github.nuke_aws_account_workflow(request.aws_sub_account_name)

@app.delete("/v1/nuke-captain-domain-data", tags=["Storage & Backups"], summary="Delete all backups/data for a captain domain (destructive)")
async def nuke_captain_domain_data(request: CaptainDomainNukeDataAndBackupsRequest):
    """
     Deletes all backups/data for a provided captain_domain. Running this before a cluster creation
     helps ensure a clean environment.

     Submit the captain_domain/tenant you want to nuke (e.g. nonprod.foobar.onglueops.rocks). This will delete all backups and data for the provided captain_domain.
     
     This will remove things like the vault and cert-manager backups.

     Note: this may not delete things like Loki/Thanos/Tempo data as that may be managed outside of AWS.
    """
    return github.nuke_captain_domain_data_and_backups(request.captain_domain)


@app.delete("/v1/reset-github-organization", tags=["GitHub"], summary="Reset a tenant GitHub organization (destructive)")
async def reset_github_organization(request: ResetGitHubOrganizationRequest):
    """
     Resets the GitHub Organization to make it easier to get a new dev cluster running for Dev.

     Submit the dev captain_domain you want to nuke (e.g. nonprod.foobar.onglueops.rocks). This will reset the GitHub organization so that you can easily get up and running with a new dev cluster.
     
     This will reset your deployment-configurations repository, it'll bring over a working regcred, and application repos with working github actions so that you can quickly work on the GlueOps stack.

     WARNING: By default delete_all_existing_repos = True. Please set it to False or make a manual backup if you are concerned about any data loss within your tenant org (e.g. github.com/development-tenant-*)

    """
    return github.reset_tenant_github_organization(request.captain_domain, request.delete_all_existing_repos, request.custom_domain, request.enable_custom_domain)

@app.post("/v1/github/workflow-run-status", tags=["GitHub"], summary="Get the status of a GitHub Actions workflow run")
async def get_workflow_run_status(request: GitHubWorkflowRunStatusRequest):
    """
     Provide a GitHub Actions run URL (e.g. https://github.com/owner/repo/actions/runs/12345678) and get the current status of that workflow run.
     Works for any repo the configured GITHUB_TOKEN has read access to.
    """
    return github.get_workflow_run_status(request.run_url)

@app.post("/v1/k3d-lb-nodes", response_class=PlainTextResponse, tags=["Load Balancers"], summary="Create k3d-lb nodes on Proxmox")
async def create_k3d_lb_nodes(request: K3dLbNodesRequest):
    """
        Creates Chisel nodes on Proxmox (via Waggle placement) for dev/k3d clusters. This allows us to
        mimic a Cloud Controller for Loadbalancers (e.g. NLBs with EKS).

        If you are testing within k3ds you will need chisel to provide you with load balancers.
        For a provided captain_domain this will delete any existing k3d-lb nodes and provision new ones.
        Placement is decided by Waggle (pool per captain_domain); the VMs are then created on the assigned
        Proxmox hypervisors and their IPs are read back through the QEMU guest agent.
        Note: this will generally result in new IPs being provisioned.
    """
    logger.info(f"Received POST request to create k3d-lb nodes for captain_domain: {request.captain_domain}")
    result = await k3d_lb.create_nodes(request)
    logger.info(f"Successfully completed k3d-lb node creation for captain_domain: {request.captain_domain}")
    return result


@app.delete("/v1/k3d-lb-nodes", tags=["Load Balancers"], summary="Delete k3d-lb nodes on Proxmox")
async def delete_k3d_lb_nodes(request: K3dLbNodesDeleteRequest):
    """
        Deletes your k3d-lb nodes. Please run this when you are done with development to free up capacity.

        When you are done testing with k3ds this will delete your k3d-lb nodes (Proxmox VMs + Waggle pool) and free up capacity.
    """
    logger.info(f"Received DELETE request to delete k3d-lb nodes for captain_domain: {request.captain_domain}")
    await k3d_lb.delete_nodes(request.captain_domain)
    logger.info(f"Successfully completed k3d-lb node deletion for captain_domain: {request.captain_domain}")
    return JSONResponse(status_code=200, content={"message": "Successfully deleted k3d-lb nodes."})


@app.post("/v1/incidentio", response_class=PlainTextResponse, tags=["Alerting"], summary="Generate incident.io alerts manifest")
async def create_incidentioalerts_manifest(request: IncidentioAlertsManifestRequest):
    """
        Create an incident.io/alertmanager configuration. Do this for any clusters you want alerts on.
    """
    return incidentio.create_incidentioalerts_manifest(request)

@app.post("/v1/kube-apiserver", response_class=PlainTextResponse, tags=["Manifests"], summary="Generate kube-apiserver exposure manifest")
async def create_kube_apiserver_manifest(request: KubeApiserverManifestRequest):
    """
        Expose the cluster kube-apiserver via Traefik (TLS passthrough + IP allowlist).

        Generate the Namespace + Traefik MiddlewareTCP + IngressRouteTCP manifest that
        exposes the cluster's Kubernetes API server at kube-api.<captain_domain>,
        restricted to the provided IP allowlist, with TLS passthrough.

        Cluster prerequisite: the IngressRouteTCP references the kubernetes Service in the
        default namespace from glueops-core-kube-api, so the platform Traefik must have
        providers.kubernetesCRD.allowCrossNamespace=true or the route is silently dropped.
    """
    return kube_apiserver.create_kube_apiserver_manifest(request)

@app.post("/v1/kube-rbac", response_class=PlainTextResponse, tags=["Manifests"], summary="Generate developer-debug RBAC manifest")
async def create_kube_rbac_manifest(request: KubeRbacManifestRequest):
    """
        Developer-debug RBAC (reader/reader-plus/debugger/operator) for a tenant's namespace.

        Generate the ClusterRoles + namespace-scoped RoleBindings that let a tenant's developers
        debug their workloads (Lens/k9s) in their <environment> namespace via the kube-apiserver
        exposed by /v1/kube-apiserver. The namespace is the first label of captain_domain and the
        RoleBinding subjects are oidc:<tenant_github_organization_name>:<captain_domain>-kubectl-<role>.
        Also includes the hardcoded glueops-super-admins -> cluster-admin ClusterRoleBinding.
    """
    return kube_rbac.create_kube_rbac_manifest(request)

@app.post("/v1/captain-manifests", response_class=PlainTextResponse, tags=["Manifests"], summary="Generate captain manifests")
async def create_captain_manifests(request: CaptainManifestsRequest):
    """
        Generate YAML manifests for captain deployments based on the provided configuration.
    """
    return captain_manifests.generate_manifests(
        request.captain_domain,
        request.tenant_github_organization_name,
        request.tenant_deployment_configurations_repository_name
    )

@app.get("/health", include_in_schema=False)
async def health():
    """health check

    Returns:
        dict: health status
    """
    return {"status": "healthy"}


# Not in the schema: the build metadata is shown at the top of the docs page instead.
# The route stays because the CLI self-updater polls it on every command
# (cli/internal/updater/updater.go).
@app.get("/version", response_model=VersionResponse, include_in_schema=False)
async def version():
    return VersionResponse(
        version=VERSION,
        commit_sha=COMMIT_SHA,
        short_sha=SHORT_SHA,
        build_timestamp=BUILD_TIMESTAMP,
        git_ref=GIT_REF,
    )
