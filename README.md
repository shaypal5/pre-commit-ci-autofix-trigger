# pre-commit-ci-autofix-trigger

A small reusable utility that labels bot-authored pull requests with `pre-commit.ci autofix` when `pre-commit.ci` is failing.

## Why this exists

`pre-commit.ci` can auto-fix pull requests once the `pre-commit.ci autofix` label is present. In many repos, bot-authored PRs (Copilot, Claude, ChatGPT, etc.) should be auto-remediated quickly without manual maintainer intervention.

This project keeps your existing `pre-commit.ci` setup unchanged and adds a minimal reusable workflow + Python CLI that:

1. Reads PR metadata and CI status via GitHub API.
2. Checks whether PR author is in a configurable bot allowlist.
3. Detects failing `pre-commit.ci` signals (check runs and commit statuses).
4. Adds `pre-commit.ci autofix` label when appropriate.

## How it works

Decision logic (idempotent and conservative):

- **Skip** if PR author is not in allowlist.
- **Skip** if label already exists.
- **Skip** if no `pre-commit.ci` checks/statuses are visible.
- **Skip** if `pre-commit.ci` is present and passing.
- **Add label** if allowlisted bot author + `pre-commit.ci` failure + label missing.

`pre-commit.ci` detection is based on names/contexts containing `pre-commit.ci`.

## Safety model

- No checkout of target PR code.
- No execution of untrusted code from downstream repository.
- API-only read/write operations against GitHub.
- Minimal permissions on reusable workflow.
- Intended to be called from downstream `pull_request_target` workflows.

## Quickstart for downstream repos

In your downstream repo, add a tiny caller workflow:

```yaml
name: pre-commit.ci autofix trigger

on:
  pull_request_target:
    types: [opened, synchronize, reopened]

permissions:
  pull-requests: write
  issues: write
  checks: read
  statuses: read
  contents: read

jobs:
  trigger:
    uses: your-org/pre-commit-ci-autofix-trigger/.github/workflows/reusable-autofix-trigger.yml@main
    with:
      pr_number: ${{ github.event.pull_request.number }}
```

If needed, pass custom allowlist/label and optional token override:

```yaml
jobs:
  trigger:
    uses: your-org/pre-commit-ci-autofix-trigger/.github/workflows/reusable-autofix-trigger.yml@main
    with:
      pr_number: ${{ github.event.pull_request.number }}
      bot_logins: copilot-swe-agent,github-copilot[bot],claude[bot]
      label: pre-commit.ci autofix
    secrets:
      github_token: ${{ secrets.GITHUB_TOKEN }}
```

## Reusable workflow inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `pr_number` | yes | n/a | PR number in the caller repo |
| `repo_owner` | no | caller owner | Repository owner to query |
| `repo_name` | no | caller repo name | Repository name to query |
| `bot_logins` | no | `copilot-swe-agent,github-copilot[bot],copilot,claude[bot],claude,chatgpt,openai` | Comma-separated bot allowlist |
| `label` | no | `pre-commit.ci autofix` | Label to apply |
| `dry_run` | no | `false` | Log decision only, no mutation |

Secret:

- `github_token` (optional). If omitted, defaults to `${{ github.token }}`.

## Local CLI usage

Install and run:

```bash
python -m pip install -e .
pre-commit-ci-autofix-trigger \
  --repo-owner your-org \
  --repo-name your-repo \
  --pr-number 123 \
  --github-token "$GITHUB_TOKEN"
```

Optional flags:

- `--head-sha` (otherwise derived from PR)
- `--bot-logins` (comma-separated allowlist)
- `--label` (default `pre-commit.ci autofix`)
- `--dry-run`

## Idempotency and expected behavior

- Re-running on same PR is safe.
- If label already exists, tool exits successfully with no changes.
- If pre-commit.ci signal is not found, tool does nothing.

### Label creation behavior

The tool uses `POST /issues/{issue_number}/labels`. If a label name does not already exist, GitHub may create it implicitly depending on repository settings and token permissions. If GitHub rejects the request, the CLI surfaces a clear error.

## Limitations (v0)

- Label mode only (no comment mode).
- Runs only when invoked by downstream workflow.
- Relies on visible check runs/statuses for the PR head SHA.
- Simple first-page API reads are used (sufficient for expected small signal sets).

## Development

```bash
python -m pip install -e .[dev]
ruff check .
pytest
```
