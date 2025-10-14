from pydantic import BaseModel, Field
from typing import Dict

class Message(BaseModel):
    message: str = Field(...,example = 'Success')

class ChiselNodesRequest(BaseModel):
    captain_domain: str  = Field(...,example = 'nonprod.foobar.onglueops.rocks')

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

