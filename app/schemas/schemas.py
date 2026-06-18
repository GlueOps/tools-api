from pydantic import BaseModel, Field
from typing import Dict

class Message(BaseModel):
    message: str = Field(...,example = 'Success')

class VersionResponse(BaseModel):
    version: str = Field(..., example='v1.0.0')
    commit_sha: str = Field(..., example='abc1234567890def1234567890abcdef12345678')
    short_sha: str = Field(..., example='abc1234')
    build_timestamp: str = Field(..., example='2026-01-01T00:00:00Z')
    git_ref: str = Field(..., example='main')

class ChiselNodesRequest(BaseModel):
    captain_domain: str = Field(..., example='nonprod.foobar.onglueops.rocks')
    node_count: int = Field(
        default=3,
        ge=1,
        le=6,
        example=3,
        description="Number of exit nodes to create (1-6, default: 3)"
    )

class ChiselNodesDeleteRequest(BaseModel):
    captain_domain: str = Field(..., example='nonprod.foobar.onglueops.rocks')

class StorageBucketsRequest(BaseModel):
    captain_domain: str = Field(...,example = 'nonprod.foobar.onglueops.rocks')

class AwsCredentialsRequest(BaseModel):
    aws_sub_account_name: str = Field(...,example = 'glueops-captain-foobar')

class AwsNukeAccountRequest(BaseModel):
    aws_sub_account_name: str  = Field(...,example = 'glueops-captain-foobar')

class CaptainDomainNukeDataAndBackupsRequest(BaseModel):
    captain_domain: str = Field(...,example = 'nonprod.foobar.onglueops.rocks')

class ResetGitHubOrganizationRequest(BaseModel):
    captain_domain: str = Field(...,example = 'nonprod.foobar.onglueops.rocks')
    delete_all_existing_repos: bool = Field(...,example = True)
    custom_domain: str = Field(...,example = "example.com")
    enable_custom_domain: bool = Field(...,example = False)

class OpsgenieAlertsManifestRequest(BaseModel):
    captain_domain: str  = Field(...,example = 'nonprod.foobar.onglueops.rocks')
    opsgenie_api_key: str  = Field(...,example = '6825b4ef-4e84-44a1-8450-b46b02852add')

class IncidentioAlertsManifestRequest(BaseModel):
    incidentio_alertmanager_url: str = Field(
        ...,
        example='https://api.incident.io/v2/alert_events/alertmanager/XXXXXXXXXXXXXXXXXXX',
        description='Bare Alertmanager source URL (no ?token= query param). Copy from incident.io UI: Alerts -> Alert sources -> Alertmanager.'
    )
    incidentio_alertmanager_token: str = Field(
        ...,
        example='XXXXXXXXXXXXXXXXXXX',
        description='Secret token for the Alertmanager source. Sent in the Authorization header via a Kubernetes Secret reference.'
    )
    incidentio_heartbeat_url: str = Field(
        ...,
        example='https://api.incident.io/v2/heartbeat/YYYYYYYYYYYYY/ping?token=XXXXXXXXXXXXXXXXXXX',
        description='Full Heartbeat URL including the ?token= query parameter. Copy from incident.io UI: Alerts -> Alert sources -> Heartbeat.'
    )

class CaptainManifestsRequest(BaseModel):
    captain_domain: str = Field(..., example='nonprod.foobar.onglueops.rocks')
    tenant_github_organization_name: str = Field(..., example='development-tenant-foobar')
    tenant_deployment_configurations_repository_name: str = Field(..., example='deployment-configurations')

class KubeApiserverManifestRequest(BaseModel):
    captain_domain: str = Field(
        ...,
        example='nonprod.foobar.onglueops.rocks',
        description='Drives both the SNI host (kube-api.<captain_domain>) and the external-dns target (platform-v2.<captain_domain>).'
    )
    allowed_source_ranges: str = Field(
        ...,
        example='192.0.2.10/32,198.51.100.0/24',
        description='Comma-separated CIDR ranges allowed to reach the kube-apiserver; at least one required. Replace the example (RFC 5737 documentation ranges) with your own IPs.'
    )

class KubeRbacManifestRequest(BaseModel):
    captain_domain: str = Field(
        ...,
        example='nonprod.foobar.onglueops.rocks',
        description='RoleBinding namespace = first label (e.g. "nonprod"); also the OIDC group suffix.'
    )
    tenant_github_organization_name: str = Field(
        ...,
        example='development-tenant-foobar',
        description='OIDC group prefix: oidc:<org>:<captain_domain>-kubectl-<reader|reader-plus|debugger|operator>.'
    )

class GitHubWorkflowRunStatusRequest(BaseModel):
    run_url: str = Field(..., example='https://github.com/internal-GlueOps/gha-tools-api/actions/runs/12345678')

