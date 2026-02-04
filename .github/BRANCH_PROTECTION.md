# Branch Protection Rules

This document describes the branch protection rules for this repository.

## Protected Branches

### `main`

- **Require a pull request before merging**
  - Require approvals: 1
  - Dismiss stale PR approvals when new commits are pushed
  - Require review from code owners

- **Require status checks to pass before merging**
  - Status checks:
    - `test` (CI test job)
    - `lint` (CI lint job)
  - Require branches to be up to date before merging

- **Require conversation resolution before merging**

- **Require signed commits** (optional, based on project needs)

- **Require linear history**
  - Prevent merge commits
  - Enforce squash or rebase merging only

- **Do not allow bypassing the above settings**

### `develop`

- **Require a pull request before merging**
  - Require approvals: 1

- **Require status checks to pass before merging**
  - Status checks:
    - `test` (CI test job)
    - `lint` (CI lint job)

- **Require branches to be up to date before merging**

## Branch Naming Convention

- Format: `type/scope/description`
- Examples:
  - `feat/db/migrations-setup`
  - `fix/client/retry-logic`
  - `docs/readme-update`

## Merge Strategy

We use **Squash and Merge** for all PRs to keep a clean linear history.

## Setting Up Branch Protection

To configure these rules in GitHub:

1. Go to **Settings** → **Branches**
2. Click **Add rule** for each protected branch
3. Configure the settings as described above
4. Save changes

## Required Secrets

The following secrets must be configured in GitHub:

- `GITHUB_TOKEN` (automatically provided)

## Required Variables

No additional variables required for basic CI/CD.
