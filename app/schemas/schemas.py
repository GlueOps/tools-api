from pydantic import BaseModel, Field
from typing import Dict

class Message(BaseModel):
    message: str = Field(...,example = 'Success')


class CreateLightsailRequest(BaseModel):
    captain_domain: str  = Field(...,example = 'glueops-captain-foobar')
    region: str = Field(...,example = 'us-west-2')

class DeleteLightsailRequest(BaseModel):
    captain_domain: str  = Field(...,example = 'nonprod.foobar.onglueops.rocks')
    region: str = Field(...,example = 'us-west-2')

class StorageBucketsRequest(BaseModel):
    captain_domain: str = Field(...,example = 'nonprod.foobar.onglueops.rocks')

class AwsCredentialsRequest(BaseModel):
    aws_sub_account_name: str = Field(...,example = 'glueops-captain-foobar')

class AwsNukeAccountRequest(BaseModel):
    aws_sub_account_name: str  = Field(...,example = 'glueops-captain-foobar')

class CaptainDomainNukeDataAndBackupsRequest(BaseModel):
    captain_domain: str = Field(...,example = 'nonprod.foobar.onglueops.rocks')
