# GitHub Settings Checklist

Apply these settings in the GitHub UI for this repository:

1) Branch protection for `main`
- Require pull requests before merging
- Require 1 approval
- Require status checks to pass: the CI workflow check (e.g., "ci / test")
- Block force pushes
- Require conversation resolution (recommended)
- Require code owner reviews (recommended if CODEOWNERS is configured)
- Prefer squash merges or linear history

2) Security & automation
- Enable Dependabot alerts and security updates
- Confirm CodeQL workflow is enabled and scheduled

3) CI verification
- Ensure the CI workflow is required in branch protection rules
