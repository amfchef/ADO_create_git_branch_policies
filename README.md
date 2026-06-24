# Azure DevOps Branch Policy Status Check Automation

This script applies Git branch policy status checks to repositories in Azure DevOps based on a JSON config file.

Script file: `status_check.py`
Config file: `status_check_config.json`

## What it does

- Connects to an Azure DevOps organization using a PAT.
- Reads project/repository filters from config.
- Reads desired branch policy configurations from config.
- Loops through selected projects and repositories.
- Targets each repository default branch.
- Applies idempotent behavior:
  - Creates policy if missing.
  - Re-enables policy if it exists but is disabled.
- Writes output reports to the `skandia` folder:
  - `failed_policies.json`
  - `all_existing_policies.json`

## Prerequisites

- Python 3.9+
- Access to Azure DevOps organization
- A PAT (Personal Access Token) with permissions to read/update policy configuration

## Install

1. Create and activate a virtual environment (recommended):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```powershell
pip install -r requirements.txt
```

## Configuration

Create a file named `status_check_config.json` in the same folder as `status_check.py`.

Example:

```json
{
  "organization_url": "https://dev.azure.com/your-org",
  "project_name": "YourProject",
  "pat": "YOUR_PAT",
  "projects": ["*"],
  "repositories": ["*"],
  "branch_policies": [
    {
      "isEnabled": true,
      "isBlocking": false,
      "type": {
        "id": "fa4e907d-c16b-4a4c-9dfa-4906e5d171dd"
      },
      "settings": {
        "displayName": "SonarQube Quality Gate",
        "scope": []
      }
    }
  ]
}
```

### Config fields

- `organization_url`: Azure DevOps org URL.
- `project_name`: Project used by repository/policy API calls in current script.
- `pat`: Personal Access Token.
- `projects`: List of project names to include, or `["*"]` for all projects.
- `repositories`: List of repo names to include, or `["*"]` for all repos.
- `branch_policies`: Policy definitions to create/enable.

## Run

```powershell
python status_check.py
```

## Notes

- The script is intended to process multiple projects using the `projects` filter.
- In the current implementation, repository and policy lookup calls use `project_name` from config for those API endpoints.
- Keep `project_name` aligned with your target if behavior is not as expected.

## Troubleshooting

- `Missing required configuration file`: make sure `status_check_config.json` exists in the script folder.
- Empty repository/default branch errors: the script skips repos without a default branch.
- API failures: verify PAT permissions, organization URL, and policy payload format.
