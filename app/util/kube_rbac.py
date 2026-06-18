import re
from fastapi import HTTPException

# RFC 1123 DNS hostname (multi-label). Mirrors kube_apiserver.py's _HOSTNAME_RE; kept local so this
# module stays independent (same low-coupling style as opsgenie.py / incidentio.py).
_HOSTNAME_RE = re.compile(
    r'^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$'
)
# GitHub org login: 1-39 chars, alphanumerics or single non-leading/trailing hyphens.
_GITHUB_ORG_RE = re.compile(r'^[a-zA-Z0-9](?:-?[a-zA-Z0-9]){0,38}$')


def create_kube_rbac_manifest(request):
    captain_domain = request.captain_domain.strip()
    if not _HOSTNAME_RE.match(captain_domain):
        raise HTTPException(status_code=422, detail="Invalid captain_domain.")

    tenant_org = request.tenant_github_organization_name.strip()
    if not _GITHUB_ORG_RE.match(tenant_org):
        raise HTTPException(status_code=422, detail="Invalid tenant_github_organization_name.")

    namespace = captain_domain.split('.')[0]          # environment_name (e.g. "nonprod")
    group = f"oidc:{tenant_org}:{captain_domain}"      # append -reader / -reader-plus / -debugger / -operator

    manifest = f"""# GlueOps developer-debug RBAC for kube-apiserver access (Lens / k9s).
# No aggregationRules (conflicts with ArgoCD) -- reader / reader-plus / debugger / operator each
# repeat the read set; keep them in sync.

---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: glueops-reader
rules:
  - apiGroups: [""]
    resources:
      - pods
      - pods/status
      - pods/log
      - services
      - endpoints
      - configmaps
      - events
      - persistentvolumeclaims
      - serviceaccounts
      - resourcequotas
      - limitranges
      - replicationcontrollers
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets", "statefulsets", "daemonsets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["controllerrevisions"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["batch"]
    resources: ["jobs", "cronjobs"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["networking.k8s.io"]
    resources: ["ingresses", "networkpolicies"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["autoscaling"]
    resources: ["horizontalpodautoscalers"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["policy"]
    resources: ["poddisruptionbudgets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["metrics.k8s.io"]
    resources: ["pods"]
    verbs: ["get", "list"]
  - apiGroups: ["argoproj.io"]
    resources: ["applications", "applicationsets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["external-secrets.io"]
    resources: ["externalsecrets", "secretstores"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["traefik.io"]  # add "traefik.containo.us" on older Traefik v2
    resources: ["ingressroutes", "ingressroutetcps", "middlewares", "middlewaretcps"]
    verbs: ["get", "list", "watch"]

---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: glueops-reader-plus
rules:
  # read set (in sync with glueops-reader)
  - apiGroups: [""]
    resources:
      - pods
      - pods/status
      - pods/log
      - services
      - endpoints
      - configmaps
      - events
      - persistentvolumeclaims
      - serviceaccounts
      - resourcequotas
      - limitranges
      - replicationcontrollers
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets", "statefulsets", "daemonsets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["controllerrevisions"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["batch"]
    resources: ["jobs", "cronjobs"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["networking.k8s.io"]
    resources: ["ingresses", "networkpolicies"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["autoscaling"]
    resources: ["horizontalpodautoscalers"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["policy"]
    resources: ["poddisruptionbudgets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["metrics.k8s.io"]
    resources: ["pods"]
    verbs: ["get", "list"]
  - apiGroups: ["argoproj.io"]
    resources: ["applications", "applicationsets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["external-secrets.io"]
    resources: ["externalsecrets", "secretstores"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["traefik.io"]
    resources: ["ingressroutes", "ingressroutetcps", "middlewares", "middlewaretcps"]
    verbs: ["get", "list", "watch"]
  # reader-plus only: port-forward (no exec/attach/delete/patch)
  - apiGroups: [""]
    resources: ["pods/portforward"]
    verbs: ["create"]

---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: glueops-debugger
rules:
  # read set (in sync with glueops-reader)
  - apiGroups: [""]
    resources:
      - pods
      - pods/status
      - pods/log
      - services
      - endpoints
      - configmaps
      - events
      - persistentvolumeclaims
      - serviceaccounts
      - resourcequotas
      - limitranges
      - replicationcontrollers
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets", "statefulsets", "daemonsets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["controllerrevisions"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["batch"]
    resources: ["jobs", "cronjobs"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["networking.k8s.io"]
    resources: ["ingresses", "networkpolicies"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["autoscaling"]
    resources: ["horizontalpodautoscalers"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["policy"]
    resources: ["poddisruptionbudgets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["metrics.k8s.io"]
    resources: ["pods"]
    verbs: ["get", "list"]
  - apiGroups: ["argoproj.io"]
    resources: ["applications", "applicationsets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["external-secrets.io"]
    resources: ["externalsecrets", "secretstores"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["traefik.io"]
    resources: ["ingressroutes", "ingressroutetcps", "middlewares", "middlewaretcps"]
    verbs: ["get", "list", "watch"]
  # debug verbs
  - apiGroups: [""]
    resources:
      - pods/exec
      - pods/attach
      - pods/portforward
    verbs: ["create"]
  - apiGroups: [""]
    resources: ["pods/ephemeralcontainers"]
    verbs: ["update", "patch"]
  - apiGroups: ["apps"]  # rollout restart (patch restartedAt); selfHeal may revert
    resources: ["deployments", "statefulsets", "daemonsets"]
    verbs: ["patch"]
  - apiGroups: [""]  # delete a stuck pod (selfHeal-safe restart)
    resources: ["pods"]
    verbs: ["delete"]

---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: glueops-operator
rules:
  - apiGroups: [""]
    resources:
      - pods
      - pods/status
      - pods/log
      - services
      - endpoints
      - configmaps
      - events
      - persistentvolumeclaims
      - serviceaccounts
      - resourcequotas
      - limitranges
      - replicationcontrollers
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets", "statefulsets", "daemonsets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["controllerrevisions"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["batch"]
    resources: ["jobs", "cronjobs"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["networking.k8s.io"]
    resources: ["ingresses", "networkpolicies"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["autoscaling"]
    resources: ["horizontalpodautoscalers"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["policy"]
    resources: ["poddisruptionbudgets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["metrics.k8s.io"]
    resources: ["pods"]
    verbs: ["get", "list"]
  - apiGroups: ["argoproj.io"]
    resources: ["applications", "applicationsets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["external-secrets.io"]
    resources: ["externalsecrets", "secretstores"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["traefik.io"]
    resources: ["ingressroutes", "ingressroutetcps", "middlewares", "middlewaretcps"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources:
      - pods/exec
      - pods/attach
      - pods/portforward
    verbs: ["create"]
  - apiGroups: [""]
    resources: ["pods/ephemeralcontainers"]
    verbs: ["update", "patch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "statefulsets", "daemonsets"]
    verbs: ["patch"]
  - apiGroups: ["*"]  # delete any namespaced resource (incl. secrets/PVCs/rolebindings)
    resources: ["*"]
    verbs: ["delete", "deletecollection"]

---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: glueops-reader
  namespace: "{namespace}"
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: glueops-reader
subjects:
  - kind: Group
    name: {group}-kubectl-reader
    apiGroup: rbac.authorization.k8s.io
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: glueops-reader-plus
  namespace: "{namespace}"
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: glueops-reader-plus
subjects:
  - kind: Group
    name: {group}-kubectl-reader-plus
    apiGroup: rbac.authorization.k8s.io
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: glueops-debugger
  namespace: "{namespace}"
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: glueops-debugger
subjects:
  - kind: Group
    name: {group}-kubectl-debugger
    apiGroup: rbac.authorization.k8s.io
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: glueops-operator
  namespace: "{namespace}"
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: glueops-operator
subjects:
  - kind: Group
    name: {group}-kubectl-operator
    apiGroup: rbac.authorization.k8s.io
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: glueops-super-admins
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-admin
subjects:
  - kind: Group
    name: oidc:glueops-cluster-admins:super_admins
    apiGroup: rbac.authorization.k8s.io
"""
    return manifest
