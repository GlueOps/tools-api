package captain

import "strings"

// extractEnvironmentName returns the first segment before the first dot.
// e.g., "nonprod" from "nonprod.foobar.onglueops.rocks".
func extractEnvironmentName(captainDomain string) string {
	return strings.SplitN(captainDomain, ".", 2)[0]
}

// GenerateManifests renders all 3 captain manifests (Namespace, AppProject,
// ApplicationSet) and concatenates them with YAML document separators.
func GenerateManifests(captainDomain, tenantOrg, tenantRepo string) string {
	envName := extractEnvironmentName(captainDomain)

	r := strings.NewReplacer(
		"<% environment_name %>", envName,
		"<% captain_domain %>", captainDomain,
		"<% tenant_github_organization_name %>", tenantOrg,
		"<% tenant_deployment_configurations_repository_name %>", tenantRepo,
	)

	namespace := r.Replace(namespaceTemplate)
	appproject := r.Replace(appprojectTemplate)
	appset := r.Replace(appsetTemplate)

	return namespace + "\n---\n" + appproject + "\n---\n" + appset
}

const namespaceTemplate = `apiVersion: v1
kind: Namespace
metadata:
  labels:
    kubernetes.io/metadata.name: <% environment_name %>
  name: <% environment_name %>`

const appprojectTemplate = `apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: <% environment_name %>
spec:
  sourceNamespaces:
  - '<% environment_name %>'
  clusterResourceBlacklist:
  - group: '*'
    kind: '*'
  namespaceResourceBlacklist:
  - group: '*'
    kind: 'Namespace'
  - group: '*'
    kind: 'CustomResourceDefinition'
  destinations:
  - name: '*'
    namespace: '<% environment_name %>'
    server: '*'
  - name: '*'
    namespace: 'glueops-core'
    server: '*'
  roles:
  - description: <% tenant_github_organization_name %>:developers
    groups:
    - "<% tenant_github_organization_name %>:developers"
    policies:
    - p, proj:<% environment_name %>:read-only, applications, get, <% environment_name %>/*, allow
    - p, proj:<% environment_name %>:read-only, applications, sync, <% environment_name %>/*, allow
    - p, proj:<% environment_name %>:read-only, logs, *, <% environment_name %>/*, allow
    - p, proj:<% environment_name %>:read-only, applications, action/external-secrets.io/ExternalSecret/refresh, <% environment_name %>/*, allow
    - p, proj:<% environment_name %>:read-only, exec, *, <% environment_name %>/*, allow
    - p, proj:<% environment_name %>:read-only, applications, action/apps/Deployment/restart, <% environment_name %>/*, allow
    - p, proj:<% environment_name %>:read-only, applications, delete/*/Pod/*/*, <% environment_name %>/*, allow
    - p, proj:<% environment_name %>:read-only, applications, delete/*/Deployment/*/*, <% environment_name %>/*, allow
    - p, proj:<% environment_name %>:read-only, applications, delete/*/ReplicaSet/*/*, <% environment_name %>/*, allow
    - p, proj:<% environment_name %>:read-only, applications, action/batch/CronJob/create-job, <% environment_name %>/*, allow
    - p, proj:<% environment_name %>:read-only, applications, action/batch/Job/terminate, <% environment_name %>/*, allow
    name: read-only
  sourceRepos:
  - https://helm.gpkg.io/project-template
  - https://helm.gpkg.io/service
  - https://incubating-helm.gpkg.io/project-template
  - https://incubating-helm.gpkg.io/service
  - https://incubating-helm.gpkg.io/platform
  - https://github.com/<% tenant_github_organization_name %>/<% tenant_deployment_configurations_repository_name %>
  - https://github.com/<% tenant_github_organization_name %>/*
  - https://github.com/GlueOps/*`

const appsetTemplate = `apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: <% environment_name %>-application-set
  namespace: glueops-core
spec:
  goTemplate: true
  generators:
  - git:
      repoURL: https://github.com/<% tenant_github_organization_name %>/<% tenant_deployment_configurations_repository_name %>
      revision: HEAD
      directories:
      - path: 'apps/*/envs/*'
      - path: 'apps/*/envs/previews'
        exclude: true
  template:
    metadata:
      name: '{{ index .path.segments 1 | replace "." "-"  | replace "_" "-" }}-{{ .path.basenameNormalized }}'
      namespace: <% environment_name %>
      annotations:
        preview_environment: 'false'
    spec:
      destination:
        namespace: <% environment_name %>
        server: https://kubernetes.default.svc
      project: <% environment_name %>
      sources:
      - chart: app
        helm:
          valueFiles:
          - '$values/common/common-values.yaml'
          - '$values/env-overlays/<% environment_name %>/env-values.yaml'
          - '$values/apps/{{ index .path.segments 1 }}/base/base-values.yaml'
          - '$values/{{ .path.path }}/values.yaml'
          values: |-
            captain_domain: <% captain_domain %>

        repoURL: https://helm.gpkg.io/project-template
        targetRevision: 0.9.0
      - repoURL: https://github.com/<% tenant_github_organization_name %>/<% tenant_deployment_configurations_repository_name %>
        targetRevision: main
        ref: values
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
        retry:
          backoff:
            duration: 5s
            factor: 2
            maxDuration: 3m0s
          limit: 2
        syncOptions:
        - CreateNamespace=true`
