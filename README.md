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
- Intended to be called from downstream `pull_request_target`, `status`, and/or `check_run` workflows.

## Quickstart for downstream repos

Prefer pinning this reusable workflow to a released version such as `@v1.0.0`
instead of `@main` or an ad hoc commit SHA from an unmerged branch.

Versioning guidance:

- use `@v1` in downstream repositories for the stable major line
- use fixed tags such as `@v1.0.0` when you want exact version pinning
- this repository automatically moves the matching major tag when a new
  `v1.x.y` release is published

In your downstream repo, add a caller workflow that runs both when the PR changes
and when `pre-commit.ci` publishes a failing result. PR events alone are not
enough, because the `pre-commit.ci` failure often appears after the initial
`opened`/`synchronize` workflow has already finished.

```yaml
name: pre-commit.ci autofix trigger

on:
  pull_request_target:
    types: [opened, synchronize, reopened]
  status:

permissions:
  pull-requests: write
  issues: write
  checks: read
  statuses: read
  contents: read

jobs:
  trigger_from_pr:
    if: >-
      github.event_name == 'pull_request_target' &&
      (
        github.event.pull_request.user.type == 'Bot' ||
        endsWith(github.event.pull_request.user.login, '[bot]')
      )
    uses: your-org/pre-commit-ci-autofix-trigger/.github/workflows/reusable-autofix-trigger.yml@v1.0.0
    with:
      pr_number: ${{ github.event.pull_request.number }}

  trigger_from_status:
    if: >-
      github.event_name == 'status' &&
      github.event.context == 'pre-commit.ci - pr' &&
      github.event.state == 'failure'
    uses: your-org/pre-commit-ci-autofix-trigger/.github/workflows/reusable-autofix-trigger.yml@v1.0.0
    with:
      head_sha: ${{ github.event.sha }}
```

If needed, pass custom allowlist/label and optional token override:

```yaml
jobs:
  trigger:
    uses: your-org/pre-commit-ci-autofix-trigger/.github/workflows/reusable-autofix-trigger.yml@v1.0.0
    with:
      pr_number: ${{ github.event.pull_request.number }}
      bot_logins: copilot-swe-agent,github-copilot[bot],claude[bot]
      label: pre-commit.ci autofix
    secrets:
      access_token: ${{ secrets.GITHUB_TOKEN }}
```

## Reusable workflow inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `pr_number` | no | resolved from `head_sha` when omitted | PR number in the caller repo |
| `repo_owner` | no | caller owner | Repository owner to query |
| `repo_name` | no | caller repo name | Repository name to query |
| `head_sha` | no | current PR head, or used to resolve the PR when `pr_number` is omitted | Commit SHA to inspect instead of re-reading the latest PR head |
| `bot_logins` | no | `copilot-swe-agent,github-copilot[bot],copilot,claude[bot],claude,chatgpt,openai` | Comma-separated bot allowlist |
| `label` | no | `pre-commit.ci autofix` | Label to apply |
| `dry_run` | no | `false` | Log decision only, no mutation |

Secret:

- `access_token` (optional). If omitted, defaults to `${{ github.token }}`.

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

## Current limitations

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

## Maintainer release flow

`.github/workflows/release.yml` runs on every push to `main`. When the pushed
commit's version in `pyproject.toml` does not already have a matching tag, the
workflow:

- reads the version from `pyproject.toml`
- creates a matching tag such as `v1.0.0` on the pushed `main` commit if missing
- creates a GitHub release for that tag

`.github/workflows/release-tags.yml` runs when a concrete `vX.Y.Z` tag such as
`v1.0.0` is pushed. It force-updates the matching major tag (`v1`) to the same
commit, so downstream repositories pinned to `@v1` receive later compatible
minor and patch releases automatically.
