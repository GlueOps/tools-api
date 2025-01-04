from pydantic import BaseModel, Field
from typing import Dict

class Message(BaseModel):
    message: str = Field(...,example = 'Success')


class CreateLightsailRequest(BaseModel):
    captain_domain: str
    region: str

class DeleteLightsailRequest(BaseModel):
    captain_domain: str
    region: str


class StorageBucketsRequest(BaseModel):
    captain_domain: str

class AwsCredentialsRequest(BaseModel):
    aws_sub_account_name: str

