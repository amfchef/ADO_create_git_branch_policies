import json
import os
import requests
from requests.auth import HTTPBasicAuth

"""
Assignment
Write an automation that is Idempotent for:
- Creating one or more Git branch policy status checks (e.g. SonarQube Quality Gate) with configuration
    - for the default branch in all repositories in a project
- The automation reads the above input and configuration from a json or yaml file
    - is manageable and easy to maintain through its lifecycle
    - preferably written in PowerShell but Python is also fine
    - and with a descriptive how-to in README.md
"""
# Load configuration data
CONFIG_FILE = "status_check_config.json"

# Stop early if config file is missing
if not os.path.exists(CONFIG_FILE):
    raise FileNotFoundError(f"Missing required configuration file: {CONFIG_FILE}")

# Read all settings from JSON config
with open(CONFIG_FILE, "r") as f:
    config = json.load(f)

# Filters for which projects and repos to process
INCLUDE_PROJECTS = config.get("projects", [])
INCLUDE_REPOSITORIES = config.get("repositories", [])
BRANCH_POLICIES = config.get("branch_policies", [])

# API Configuration Details
ORG_URL = config["organization_url"].rstrip("/")  # Remove trailing slash to build safe URLs
PROJECT = config["project_name"]
AUTH = HTTPBasicAuth("", config["pat"])  # Use PAT for Azure DevOps auth
API_VERSION = "6.0"  # Supported by ADO Server 2020 and Services
STATUS_CHECKS = config["branch_policies"]  # Desired policies from config

FAILED_POLICIES = {}
workspace = "skandia"

# Create output folder once if needed
if not os.path.exists(workspace):
    os.makedirs(workspace)


def print_to_json_file(dict, file_name):
    # Save debug/report data as formatted JSON
    data = json.dumps(dict, indent=3, ensure_ascii=False)
    with open(f"{workspace}/{file_name}.json", "w", encoding='utf-8') as outfile:
        outfile.write(data)


def list_repositories():
    """Fetches all Git repositories inside the target project."""
    try:
        # Get repositories for configured project
        url = f"{ORG_URL}/{PROJECT}/_apis/git/repositories?api-version={API_VERSION}"
        response = requests.get(url, auth=AUTH)
        if not response.ok:
            print(f"[E] Failed to fetch repositories. Response: {response} - {response.text}")
            return []
        return response.json().get("value", [])
    except Exception as e:
        print(f"[E] Failed to fetch repositories. Error: {e}")
        return []


def get_existing_policies(repo_id, repo_name, branch_name="refs/heads/master"):
    """Retrieves all branch policies currently active in the repository."""
    existing_branch_policies = {}
    # Read policy configs bound to one repo + one branch
    url = f"{ORG_URL}/{PROJECT}/_apis/git/policy/configurations?repositoryId={repo_id}&refName={branch_name}&api-version=7.0"

    response = requests.get(url, auth=AUTH)

    if not response.ok:
        print(f"[E] Failed to fetch policies for repo: {repo_name}. Response: {response} - {response.text}")
        return existing_branch_policies
    
    for existing_policy in response.json().get("value", []):
        #if not existing_policy["isEnabled"]:continue
        # Remove noisy metadata before storing results
        del existing_policy["createdBy"]
        # Index by policy type id for quick lookup
        existing_branch_policies[existing_policy["type"]["id"]] = existing_policy

    return existing_branch_policies


def create_branch_policy(project, policy_config, repo_name):
    try:
        # Create a new policy when missing
        url = f"{ORG_URL}/{project}/_apis/policy/configurations?api-version=7.0"
        response = requests.post(url, json=policy_config, auth=AUTH)
        if not response.ok:
            print(f"[E] Failed to create policy: {response} - {response.text}")
            policy_config["error"] = response.json()["message"]
            FAILED_POLICIES[repo_name] = policy_config  # Track failures for report
            return None
        print(f"[I] Policy created successfully. Repo: {repo_name}. Policy: {policy_config.get('displayName')}")
        return response.json()
    
    except Exception as e:
        print(f"[E] Failed to create policy for repo: {repo_name}. Error: {e}")
        policy_config["error"] = str(e)
        FAILED_POLICIES[repo_name] = policy_config
        return None

def update_branch_policy(project, policy_config, repo_name, configurationId):
    try:
        # Update existing policy (used here to re-enable disabled policy)
        url = f"{ORG_URL}/{project}/_apis/policy/configurations/{configurationId}?api-version=7.0"
        response = requests.put(url, json=policy_config, auth=AUTH)
        if not response.ok:
            print(f"[E] Failed to update policy: {response} - {response.text}")
            policy_config["error"] = response.json()["message"]
            FAILED_POLICIES[repo_name] = policy_config
            return None
        print(f"[I] Policy updated successfully. Repo: {repo_name}. Policy: {policy_config.get('displayName')}")
        return response.json()
    
    except Exception as e:
        print(f"[E] Failed to update policy for repo: {repo_name}. Error: {e}")
        policy_config["error"] = str(e)
        FAILED_POLICIES[repo_name] = policy_config
        return None


def list_projects():
    # Get all projects to apply include filter
    url = f"{ORG_URL}/_apis/projects?api-version=7.0"
    response = requests.get(url, auth=AUTH)
    if not response.ok:
        print(f"[E] Failed to list projects: {response} - {response.text}")
        return None
    return response.json()


def main():
    all_existing_policies = {}
    projects = list_projects()
    for project in projects.get("value", []):
        # Process project if listed, or all when '*' is used
        if INCLUDE_PROJECTS == ['*'] or project["name"] in INCLUDE_PROJECTS:
            all_existing_policies[project["name"]] = {}
            repos = list_repositories()
    
            for repo in repos:
                repo_name = repo["name"]
                repo_id = repo["id"]
                # Process repo if listed, or all when '*' is used
                if INCLUDE_REPOSITORIES == ['*'] or repo_name in INCLUDE_REPOSITORIES:

                    default_branch = repo.get("defaultBranch")
                    # Skip repos without a usable default branch
                    if not default_branch:
                        print(f"[E] Repo '{repo_name}': Skipped (No default branch or empty repository).")
                        continue

                    existing_policies = get_existing_policies(repo_id, repo_name, default_branch)
                    all_existing_policies[project["name"]][repo_name] = existing_policies
                    
                    for new_policy in STATUS_CHECKS:
                        # Bind desired policy to repo default branch
                        new_policy["settings"]["scope"] = [{"refName": default_branch, "repositoryId": repo["id"], "matchKind": "Exact"}]
                        # Idempotent rule 1: create only when missing
                        if not new_policy["type"]["id"] in existing_policies:
                            print(f"[I] Policy Missing: {new_policy['type']['id']} is not configured.")
                            
                            create_branch_policy(project["name"], new_policy, repo_name)
                        
                        # Idempotent rule 2: enable when policy exists but is disabled
                        elif existing_policies[new_policy["type"]["id"]]["isEnabled"] == False:
                            print(f"[I] Policy Disabled: {new_policy['type']['id']}. Enabling it.")
                            update_branch_policy(project["name"], new_policy, repo_name, existing_policies[new_policy["type"]["id"]]["id"])


    # Save reports for troubleshooting and audit
    print_to_json_file(FAILED_POLICIES, "failed_policies")
    print_to_json_file(all_existing_policies, "all_existing_policies")

if __name__ == "__main__":
    main()
