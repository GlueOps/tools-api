import string


def create_opsgeniealerts_manifest(request):
    captain_domain = request.captain_domain.strip()
    opsgenie_api_key = request.opsgenie_api_key.strip()

    manifest = f"""
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: glueops-core-alerts-opsgenie
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  destination:
    name: "in-cluster"
    namespace: glueops-core-alerts
  project: glueops-core
  syncPolicy:
    syncOptions:
      - CreateNamespace=true  
      - Replace=true
    automated:
      prune: true
      selfHeal: true
    retry:
      backoff:
        duration: 10s
        factor: 2
        maxDuration: 3m0s
      limit: 5
  source:
    repoURL: https://helm.gpkg.io/project-template
    chart: app
    targetRevision: 0.8.1
    helm:
      values: |
        appName: 'glueops-core-alerts-opsgenie'
        image:
          registry: replicas.mirror.gpkg.io/proxy-ghcr-io
          repository: glueops/cluster-monitoring
          tag: v0.8.2@sha256:06bad372dfd21d2bf807d26fb6d354f885d7e4fe63a2108f7446f20be2b5413d
          pullPolicy: IfNotPresent
        deployment:
          replicas: 1
          enabled: true
          envVariables:
            - name: OPSGENIE_HEARTBEAT_NAME
              value: {captain_domain}
            - name: OPSGENIE_PING_INTERVAL_MINUTES
              value: 1
          envSecrets:
          - variable: OPSGENIE_API_KEY
            secretKey: opsgenie_apikey
            secretName: glueops-core-alerts-opsgenie-glueops-alerts
        secret:
          enabled: true
          secrets:
            glueops-alerts:
              data:
                opsgenie_apikey: {opsgenie_api_key}
        customResources:
          - |-
            apiVersion: monitoring.coreos.com/v1alpha1
            kind: AlertmanagerConfig
            metadata:
              name: glueops-core-alerts-opsgenie
              namespace: glueops-core-alerts
            spec:
              receivers:
              - name: glueops-alerts
                opsgenieConfigs:
                - apiKey:
                    key: opsgenie_apikey
                    name: glueops-core-alerts-opsgenie-glueops-alerts
                  apiURL: https://api.opsgenie.com/
                  sendResolved: true
                  updateAlerts: true
              route:
                groupBy:
                - '...'
                groupInterval: 5m
                matchers:
                - name: namespace
                  value: glueops-core-alerts
                receiver: glueops-alerts
                repeatInterval: 5m
---

"""

    return manifest


