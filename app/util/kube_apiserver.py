import ipaddress
import re
from fastapi import HTTPException

# RFC 1123 DNS hostname (lowercase labels, dots). Positive allowlist beats a char blocklist.
_HOSTNAME_RE = re.compile(
    r'^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$'
)


def create_kube_apiserver_manifest(request):
    captain_domain = request.captain_domain.strip()
    if not _HOSTNAME_RE.match(captain_domain):
        raise HTTPException(status_code=422, detail="Invalid captain_domain.")

    raw = [c.strip() for c in request.allowed_source_ranges.split(',') if c.strip()]
    if not raw:
        raise HTTPException(
            status_code=422,
            detail="allowed_source_ranges must contain at least one CIDR.",
        )

    normalized = []
    for cidr in raw:
        try:
            net = ipaddress.ip_network(cidr, strict=False)  # tolerate host bits, then normalize
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid CIDR: {cidr!r}")
        if net.prefixlen == 0:
            # 0.0.0.0/0 and ::/0 are an allow-all — refuse to emit an unrestricted apiserver.
            raise HTTPException(status_code=422, detail=f"Refusing allow-all CIDR: {cidr!r}")
        normalized.append(str(net))

    # dedupe on normalized value while preserving order
    seen, cidrs = set(), []
    for n in normalized:
        if n not in seen:
            seen.add(n)
            cidrs.append(n)

    source_range = "\n".join(f'      - "{cidr}"' for cidr in cidrs)

    manifest = f"""
---
apiVersion: v1
kind: Namespace
metadata:
  name: glueops-core-kube-api
---
apiVersion: traefik.io/v1alpha1
kind: MiddlewareTCP
metadata:
  name: kube-apiserver-ip-allowlist
  namespace: glueops-core-kube-api
spec:
  ipAllowList:
    sourceRange:
{source_range}
---
apiVersion: traefik.io/v1alpha1
kind: IngressRouteTCP
metadata:
  name: kube-apiserver-passthrough
  namespace: glueops-core-kube-api
  annotations:
    kubernetes.io/ingress.class: "platform-traefik"
    external-dns.alpha.kubernetes.io/target: "platform-v2.{captain_domain}"
spec:
  entryPoints:
    - websecure
  routes:
    - match: HostSNI(`kube-api.{captain_domain}`)
      middlewares:
        - name: kube-apiserver-ip-allowlist
          namespace: glueops-core-kube-api
      services:
        - name: kubernetes
          namespace: default
          port: 443
  tls:
    # Passthrough: client TLS terminates at the apiserver, not Traefik.
    passthrough: true
---

"""
    return manifest
