import boto3
import random
import string
import os
from fastapi import FastAPI, Security, HTTPException, Depends, status, requests, Request
import time

REGION_NAMES = {
    "us-east-1": "US East (N. Virginia)",
    "us-east-2": "US East (Ohio)",
    "us-west-2": "US West (Oregon)",
    "eu-west-1": "EU (Ireland)",
    "eu-west-2": "EU (London)",
    "eu-west-3": "EU (Paris)",
    "eu-central-1": "EU (Frankfurt)",
    "ap-southeast-1": "Asia Pacific (Singapore)",
    "ap-southeast-2": "Asia Pacific (Sydney)",
    "ap-northeast-1": "Asia Pacific (Tokyo)",
    "ap-northeast-2": "Asia Pacific (Seoul)",
    "ap-south-1": "Asia Pacific (Mumbai)",
    "ca-central-1": "Canada (Central)",
    "eu-north-1": "EU (Stockholm)"
}

# Delete existing instances if they exist
suffixes = ["exit1", "exit2"]

def delete_lightsail_instances(request):
    region = request.region

    # Set AWS region
    boto3.setup_default_session(region_name=region)
    
    captain_domain = request.captain_domain.strip()
    instance_names = [f"{captain_domain}-{suffix}" for suffix in suffixes]
    aws_access_key = os.getenv("AWS_LIGHTSAIL_ACCESS_KEY")
    aws_secret_key = os.getenv("AWS_LIGHTSAIL_SECRET_KEY")

    # Fetch Lightsail bundle and availability zone
    lightsail_client = boto3.client("lightsail", aws_access_key_id=aws_access_key, aws_secret_access_key=aws_secret_key)

    for instance_name in instance_names:
        try:
            lightsail_client.delete_instance(instanceName=instance_name)
        except lightsail_client.exceptions.NotFoundException:
            pass  # Instance does not exist, continue
    
    return "All instances were deleted"

def create_lightsail_instances(request):
    if request.region not in REGION_NAMES:
        raise HTTPException(status_code=400, detail="Invalid region.")

    captain_domain = request.captain_domain.strip()
    region = request.region

    # Set AWS region
    boto3.setup_default_session(region_name=region)

    # Generate chisel credentials
    def generate_credentials():
        return (
            "".join(random.choices(string.ascii_letters + string.digits, k=15))
            + ":"
            + "".join(random.choices(string.ascii_letters + string.digits, k=15))
        )

    credentials_for_chisel = generate_credentials()

    aws_access_key = os.getenv("AWS_LIGHTSAIL_ACCESS_KEY")
    aws_secret_key = os.getenv("AWS_LIGHTSAIL_SECRET_KEY")



    # Fetch Lightsail bundle and availability zone
    lightsail_client = boto3.client("lightsail", aws_access_key_id=aws_access_key, aws_secret_access_key=aws_secret_key)
    ec2_client = boto3.client("ec2", aws_access_key_id=aws_access_key, aws_secret_access_key=aws_secret_key)

    try:
        bundle_id = lightsail_client.get_bundles()["bundles"][0]["bundleId"]
        blueprint_id = "debian_12"
        first_az = ec2_client.describe_availability_zones()["AvailabilityZones"][0]["ZoneName"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching AWS resources: {str(e)}")

    # Define user data
    user_data = f"""#!/bin/bash

# Some regions appear to be problematic on DNS resolution
sleep 15;

curl -fsSL https://get.docker.com -o get-docker.sh && sudo sh get-docker.sh && sudo apt install tmux -y

# Run chisel
sudo docker run -d --restart always -p 9090:9090 -p 443:443 -p 80:80 -it jpillora/chisel server --reverse --port=9090 --auth='{credentials_for_chisel}'
"""

    instance_names = [f"{captain_domain}-{suffix}" for suffix in suffixes]
    ip_addresses = {}

    try:
        delete_lightsail_instances(request)

        # Create instances
        for instance_name in instance_names:
            lightsail_client.create_instances(
                instanceNames=[instance_name],
                bundleId=bundle_id,
                blueprintId=blueprint_id,
                availabilityZone=first_az,
                userData=user_data,
            )
            time.sleep(1)  # Ensure the instance is being created before opening ports

        time.sleep(60)  # Wait for instances to initialize

        for instance_name in instance_names:
            lightsail_client.open_instance_public_ports(
                instanceName=instance_name,
                portInfo={"fromPort": 0, "toPort": 65535, "protocol": "all"},
            )

            # Retrieve public IP
            instance_info = lightsail_client.get_instance(instanceName=instance_name)
            ip_addresses[instance_name] = instance_info["instance"]["publicIpAddress"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating instances: {str(e)}")

    # Generate Kubernetes manifest
    manifest = f"""
kubectl apply -k https://github.com/FyraLabs/chisel-operator?ref=v0.4.1

kubectl apply -f - <<YAML
apiVersion: v1
kind: Secret
metadata:
  name: selfhosted
  namespace: chisel-operator-system
type: Opaque
stringData:
  auth: "{credentials_for_chisel}"
---
"""
    for suffix in suffixes:
        manifest += f"""
apiVersion: chisel-operator.io/v1
kind: ExitNode
metadata:
  name: {suffix}
  namespace: chisel-operator-system
spec:
  host: "{ip_addresses[f'{captain_domain}-{suffix}']}"
  port: 9090
  auth: selfhosted
---
"""

    return manifest