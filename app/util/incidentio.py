def create_incidentioalerts_manifest(request):
    incidentio_alertmanager_url = request.incidentio_alertmanager_url.strip()
    incidentio_alertmanager_token = request.incidentio_alertmanager_token.strip()
    incidentio_heartbeat_url = request.incidentio_heartbeat_url.strip()

    manifest = f"""
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: glueops-core-alerts-incident-io
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
    targetRevision: 0.9.0
    helm:
      values: |
        image:
          registry: ghcr.repo.gpkg.io
          repository: glueops/cluster-monitoring
          tag: v4.0.0@sha256:09c979b662c08de6aaac722f648cbd6e58e89d76a017db782ca6f2810ca4887e
          pullPolicy: IfNotPresent
        deployment:
          replicas: 1
          enabled: true
          envVariables:
            - name: INCIDENT_IO_PING_INTERVAL_MINUTES
              value: 1
          envSecrets:
          - variable: INCIDENT_IO_HEARTBEAT_URL
            secretKey: incidentio_heartbeat_url
            secretName: incident-io-credentials
        secret:
          enabled: false
        customResources:
          - |-
            apiVersion: v1
            kind: Secret
            metadata:
              name: incident-io-credentials
              namespace: glueops-core-alerts
            type: Opaque
            stringData:
              incidentio_alertmanager_token: {incidentio_alertmanager_token}
              incidentio_heartbeat_url: {incidentio_heartbeat_url}
          - |-
            apiVersion: monitoring.coreos.com/v1alpha1
            kind: AlertmanagerConfig
            metadata:
              name: glueops-core-alerts-receivers
              namespace: glueops-core-alerts
            spec:
              receivers:
                - name: glueops-alerts-incident-io
                  webhookConfigs:
                    - url: '{incidentio_alertmanager_url}'
                      sendResolved: true
                      httpConfig:
                        authorization:
                          credentials:
                            name: incident-io-credentials
                            key: incidentio_alertmanager_token
              route:
                groupBy: ['...']
                groupInterval: 5m
                matchers:
                  - name: namespace
                    value: glueops-core-alerts
                receiver: glueops-alerts-incident-io
                repeatInterval: 5m
---

"""

    return manifest
