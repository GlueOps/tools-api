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
    
    try:
        logger.info(f"Generating chisel credentials...")
        credentials_for_chisel = util.chisel.generate_credentials()
        logger.info(f"Successfully generated chisel credentials")
    except Exception as e:
        logger.error(f"Failed to generate chisel credentials: {str(e)}")
        raise

    # Define user data
    user_data_readable = f"""
#cloud-config
package_update: true
runcmd:
    - curl -fsSL https://get.docker.com -o get-docker.sh && sudo sh get-docker.sh && sudo apt install tmux -y
    - sudo docker run -d --restart always -p 9090:9090 -p 443:443 -p 80:80 -it docker.io/jpillora/chisel:1 server --reverse --port=9090 --auth='{credentials_for_chisel}'
"""

    user_data = multiline_to_singleline(user_data_readable)

    try:
        node_count = request.node_count
        logger.info(f"Getting chisel suffixes for {node_count} nodes...")
        suffixes = util.chisel.get_suffixes(node_count)
        logger.info(f"Got suffixes: {suffixes}")
    except Exception as e:
        logger.error(f"Failed to get chisel suffixes: {str(e)}")
        raise

    instance_names = [f"{captain_domain}-{suffix}" for suffix in suffixes]
    ip_addresses = {}

    try:
        delete_existing_servers(request)

        for instance_name in instance_names:
            logger.info(f"Creating chisel node: {instance_name}")
            ip_addresses[instance_name] = create_server(instance_name, captain_domain, user_data)
        
        logger.info(f"All chisel nodes created successfully. IP addresses: {ip_addresses}")
    except Exception as e:
        logger.error(f"Error creating chisel instances for {captain_domain}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error creating instances: {str(e)}")

    try:
        logger.info(f"Generating chisel YAML manifest...")
        yaml_manifest = util.chisel.create_chisel_yaml(captain_domain, credentials_for_chisel, ip_addresses, suffixes)
        logger.info(f"Successfully generated chisel YAML manifest for {captain_domain}")
        return yaml_manifest
    except Exception as e:
        logger.error(f"Failed to generate chisel YAML manifest: {str(e)}")
        raise


def create_server(server_name, captain_domain, user_data_one_line_format):
    try:
        CHISEL_NODE_HCLOUD_INSTANCE_TYPE = os.getenv("CHISEL_HCLOUD_INSTANCE_TYPE")
        logger.info(f"Creating instances of type: {CHISEL_NODE_HCLOUD_INSTANCE_TYPE}")
        
        server_type = ServerType(name=CHISEL_NODE_HCLOUD_INSTANCE_TYPE)
        image = Image(name="debian-12")
        
        logger.info(f"Fetching SSH keys for server {server_name}...")
        ssh_keys = client.ssh_keys.get_all(name="glueops-default-ssh-key")
        logger.info(f"Found {len(ssh_keys)} SSH key(s)")
        
        location = Location(name="hel1")
        
        logger.info(f"Calling Hetzner API to create server {server_name}...")
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
        logger.info(f"Hetzner API call completed for server {server_name}")
    except Exception as e:
        logger.error(f"Failed to create server {server_name}: {str(e)}")
        raise

    server = server_response.server
    #server_response.action.wait_until_finished()
    ipv4_address = server.public_net.ipv4.ip
    logger.info(f"Successfully created chisel node {server_name} with IP: {ipv4_address}")
    return ipv4_address


def delete_existing_servers(request):
    captain_domain = request.captain_domain.strip()
    logger.info(f"Starting deletion of existing chisel nodes for captain_domain: {captain_domain}")
    
    try:
        logger.info(f"Fetching all servers with captain_domain label...")
        servers = client.servers.get_all(label_selector="captain_domain")
        logger.info(f"Found {len(servers)} total server(s) with captain_domain label")
    except Exception as e:
        logger.error(f"Failed to fetch servers from Hetzner API: {str(e)}")
        raise
    deleted_count = 0
    for server in servers:
        logger.info(f"Checking server: {server.name} (captain_domain={server.labels.get('captain_domain', 'N/A')})")
        if server.labels["captain_domain"] == captain_domain:
            try:
                logger.info(f"Deleting chisel node: {server.name}")
                server.delete()
                logger.info(f"Successfully deleted chisel node: {server.name}")
                deleted_count += 1
            except Exception as e:
                logger.error(f"Failed to delete server {server.name}: {str(e)}")
                raise
    logger.info(f"Completed deletion of {deleted_count} chisel node(s) for captain_domain: {captain_domain}")
    return True
        

