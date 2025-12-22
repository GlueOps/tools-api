import os
from fastapi import FastAPI, Security, HTTPException, Depends, status, requests, Request
import time
import util.chisel
from hcloud import Client
from hcloud.images import Image
from hcloud.server_types import ServerType
from hcloud.images.domain import Image
from hcloud.locations.domain import Location
from hcloud.servers.domain import ServerCreatePublicNetwork
import glueops.setup_logging

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logger = glueops.setup_logging.configure(level=LOG_LEVEL)

client = Client(token=os.getenv("HCLOUD_TOKEN"))

def multiline_to_singleline(input_text: str) -> str:
    """
    Converts a multi-line string to a single-line string with `\\n` replacing newlines.
    
    Args:
        input_text (str): The multi-line input string.
    
    Returns:
        str: Single-line string with `\\n` replacing newlines.
    """
    return input_text.replace("\n", "\n")


def create_instances(request):
    captain_domain = request.captain_domain.strip()
    logger.info(f"Starting chisel node creation for captain_domain: {captain_domain}")
    credentials_for_chisel = util.chisel.generate_credentials()

    # Define user data
    user_data_readable = f"""
#cloud-config
package_update: true
runcmd:
    - curl -fsSL https://get.docker.com -o get-docker.sh && sudo sh get-docker.sh && sudo apt install tmux -y
    - sudo docker run -d --restart always -p 9090:9090 -p 443:443 -p 80:80 -it ghcr.repo.gpkg.io/fyralabs/chisel:v0.1.0-fyra server --reverse --port=9090 --auth='{credentials_for_chisel}'
"""

    user_data = multiline_to_singleline(user_data_readable)

    suffixes = util.chisel.get_suffixes()

    instance_names = [f"{captain_domain}-{suffix}" for suffix in suffixes]
    ip_addresses = {}

    try:
        delete_existing_servers(request)

        for instance_name in instance_names:
            logger.info(f"Creating chisel node: {instance_name}")
            ip_addresses[instance_name] = create_server(instance_name, captain_domain, user_data)
    except Exception as e:
        logger.error(f"Error creating chisel instances for {captain_domain}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error creating instances: {str(e)}")

    return util.chisel.create_chisel_yaml(captain_domain, credentials_for_chisel, ip_addresses, suffixes)


def create_server(server_name, captain_domain, user_data_one_line_format):
    server_type = ServerType(name="cx23")
    image = Image(name="debian-12")
    ssh_keys = client.ssh_keys.get_all(name="glueops-default-ssh-key")
    location = Location(name="hel1")
    server_response = client.servers.create(
                server_name,
                server_type=server_type,
                image=image,
                ssh_keys=ssh_keys,
                location=location,
                user_data=user_data_one_line_format,
                labels={"captain_domain": captain_domain, "chisel_node": "True"},
                public_net=ServerCreatePublicNetwork(
                    enable_ipv4=True,
                    enable_ipv6=False
                )
            )

    server = server_response.server
    #server_response.action.wait_until_finished()
    ipv4_address = server.public_net.ipv4.ip
    logger.info(f"Successfully created chisel node {server_name} with IP: {ipv4_address}")
    return ipv4_address


def delete_existing_servers(request):
    captain_domain = request.captain_domain.strip()
    logger.info(f"Starting deletion of existing chisel nodes for captain_domain: {captain_domain}")
    servers = client.servers.get_all(label_selector="captain_domain")
    deleted_count = 0
    for server in servers:
        if server.labels["captain_domain"] == captain_domain:
            logger.info(f"Deleting chisel node: {server.name}")
            server.delete()
            deleted_count += 1
    logger.info(f"Completed deletion of {deleted_count} chisel node(s) for captain_domain: {captain_domain}")
    return True
        

