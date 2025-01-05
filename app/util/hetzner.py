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


client = Client(token=os.getenv("HCLOUD_TOKEN"))

def multiline_to_singleline(input_text: str) -> str:
    """
    Converts a multi-line string to a single-line string with `\\n` replacing newlines.
    
    Args:
        input_text (str): The multi-line input string.
    
    Returns:
        str: Single-line string with `\\n` replacing newlines.
    """
    return input_text.replace("\n", "\\n")


def create_instances(request):
    captain_domain = request.captain_domain.strip()
    credentials_for_chisel = util.chisel.generate_credentials()

    # Define user data
    user_data_readable = f"""#cloud-config
package_update: true
runcmd:
  - curl -fsSL https://get.docker.com -o get-docker.sh && sudo sh get-docker.sh && sudo apt install tmux -y
  - sudo docker run -d --restart always -p 9090:9090 -p 443:443 -p 80:80 -it jpillora/chisel:v1.10.1 server --reverse --port=9090 --auth='{credentials_for_chisel}'
"""

    user_data = multiline_to_singleline(user_data_readable)

    suffixes = util.chisel.get_suffixes()

    instance_names = [f"{captain_domain}-{suffix}" for suffix in suffixes]
    ip_addresses = {}

    try:
        delete_existing_servers(request)

        for instance_name in instance_names:
            ip_addresses[instance_name] = create_server(instance_name, captain_domain, user_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating instances: {str(e)}")

    return util.chisel.create_chisel_yaml(captain_domain, credentials_for_chisel, ip_addresses, suffixes)


def create_server(server_name, captain_domain, user_data_one_line_format):
    server_type = ServerType(name="cx22")
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
                labels={"captain_domain": captain_domain},
                public_net=ServerCreatePublicNetwork(
                    enable_ipv4=True,
                    enable_ipv6=False
                )
            )

    server = server_response.server
    #server_response.action.wait_until_finished()
    return(server.public_net.ipv4.ip)


def delete_existing_servers(request):
    captain_domain = request.captain_domain.strip()
    servers = client.servers.get_all(label_selector="captain_domain")
    for server in servers:
        if server.labels["captain_domain"] == captain_domain:
            server.delete()
    return True
        

