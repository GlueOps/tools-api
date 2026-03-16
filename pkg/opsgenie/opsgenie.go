package opsgenie

import "strings"

// CreateOpsgenieAlertsManifest generates a Kubernetes ArgoCD Application manifest
// for Opsgenie alerting, with captain_domain and opsgenie_api_key substituted
// into the YAML template. Inputs are trimmed (matching Python's .strip()).
func CreateOpsgenieAlertsManifest(captainDomain, opsgenieAPIKey string) string {
	captainDomain = strings.TrimSpace(captainDomain)
	opsgenieAPIKey = strings.TrimSpace(opsgenieAPIKey)

	return `
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
    targetRevision: 0.9.0
    helm:
      values: |
        image:
          registry: ghcr.repo.gpkg.io
          repository: glueops/cluster-monitoring
          tag: v2.0.0@sha256:cc6b9fd4da9e18468aba6757ff6a891d843e2d134884bae0f6404faa520023bb
          pullPolicy: IfNotPresent
        deployment:
          replicas: 1
          enabled: true
          envVariables:
            - name: OPSGENIE_HEARTBEAT_NAME
              value: ` + captainDomain + `
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
                opsgenie_apikey: ` + opsgenieAPIKey + `
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

`
}
