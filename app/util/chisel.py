import secrets
import string

def generate_credentials():
    character_pool = string.ascii_letters + string.digits
    return (
        "".join(secrets.choice(character_pool) for _ in range(15))  # Generate 15 secure characters
        + ":"
        + "".join(secrets.choice(character_pool) for _ in range(15))  # Generate another 15 secure characters
    )

def get_suffixes():
  return ["exit1", "exit2"]


def create_chisel_yaml(captain_domain, credentials_for_chisel, ip_addresses, suffixes):
    manifest = f"""
kubectl apply -k https://github.com/FyraLabs/chisel-operator?ref=v0.3.4

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
      manifest += f"""apiVersion: chisel-operator.io/v1
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
    manifest += f"""
YAML
"""

    return manifest


