"""
Captain Manifests utility module.

This module generates YAML manifests for captain deployments using Jinja2 templates.
"""

import os
from jinja2 import Environment, FileSystemLoader


def generate_manifests(captain_domain: str, tenant_github_organization_name: str, tenant_deployment_configurations_repository_name: str) -> dict:
    """
    Generate captain manifests based on the provided configuration.
    
    Args:
        captain_domain: The captain domain (e.g., nonprod.antoniostaqueria.onglueops.com)
        tenant_github_organization_name: The tenant's GitHub organization name
        tenant_deployment_configurations_repository_name: The tenant's deployment configurations repository name
    
    Returns:
        dict: Status response with concatenated YAML manifests
    """
    # Extract environment name from captain_domain (first segment)
    environment_name = captain_domain.split('.')[0]
    
    # Set up Jinja2 environment with custom delimiters to avoid conflict with Go templates
    templates_dir = os.path.join(os.path.dirname(__file__), '..', 'templates', 'captain_manifests')
    env = Environment(
        loader=FileSystemLoader(templates_dir),
        variable_start_string='<%',
        variable_end_string='%>'
    )
    
    # Template variables
    template_vars = {
        'environment_name': environment_name,
        'captain_domain': captain_domain,
        'tenant_github_organization_name': tenant_github_organization_name,
        'tenant_deployment_configurations_repository_name': tenant_deployment_configurations_repository_name
    }
    
    # Render all templates
    namespace_yaml = env.get_template('namespace.yaml.j2').render(template_vars)
    appproject_yaml = env.get_template('appproject.yaml.j2').render(template_vars)
    appset_yaml = env.get_template('appset.yaml.j2').render(template_vars)
    
    # Concatenate all YAMLs with document separators
    return f"{namespace_yaml}\n---\n{appproject_yaml}\n---\n{appset_yaml}"
