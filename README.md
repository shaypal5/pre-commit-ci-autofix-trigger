# pre-commit-ci-autofix-trigger

A small reusable utility that labels bot-authored pull requests with `pre-commit.ci autofix` when `pre-commit.ci` is failing.

## Why this exists

`pre-commit.ci` can auto-fix pull requests once the `pre-commit.ci autofix` label is present. In many repos, bot-authored PRs (Copilot, Claude, ChatGPT, etc.) should be auto-remediated quickly without manual maintainer intervention.

This project keeps your existing `pre-commit.ci` setup unchanged and adds a minimal reusable workflow + Python CLI that:

1. Reads PR metadata and CI status via GitHub API.
2. Checks whether PR author is in a configurable bot allowlist.
3. Detects failing `pre-commit.ci` signals (check runs and commit statuses).
4. Claims a durable per-commit autofix attempt.
5. Adds `pre-commit.ci autofix` label when appropriate.

## How it works

Decision logic (idempotent and conservative):

- **Skip** if PR author is not in allowlist.
- **Skip** if label already exists.
- **Skip** if no `pre-commit.ci` checks/statuses are visible.
- **Skip** if `pre-commit.ci` is present and passing.
- **Skip** if the PR head commit already has the configured maximum number of autofix attempts.
- **Add label** if allowlisted bot author + `pre-commit.ci` failure + label missing + the managed attempt state stays within the per-head-SHA limit.

`pre-commit.ci` detection is based on names/contexts containing `pre-commit.ci`.
Attempt tracking uses one managed PR issue comment, so it remains durable even when
`pre-commit.ci` removes the autofix label after consuming it.
The reusable workflow also serializes runs by target repository and head SHA, so
parallel `status` events cannot race past the attempt limit.

## Safety model

- No checkout of target PR code.
- No execution of untrusted code from downstream repository.
- API-only read/write operations against GitHub.
- Minimal permissions on reusable workflow.
- Workflow-level concurrency serializes attempts for each target PR head commit.
- Intended to be called from downstream `pull_request_target`, `status`, and/or `check_run` workflows.

## PR agent context integration

This repository self-consumes [`shaypal5/pr-agent-context`](https://github.com/shaypal5/pr-agent-context)
on pull requests.

- [`.github/workflows/ci.yml`](.github/workflows/ci.yml) uploads a combined `coverage.xml` artifact and
  invokes `pr-agent-context` in `coverage_xml_artifact` mode.
- [`.github/workflows/pr-agent-context-refresh.yml`](.github/workflows/pr-agent-context-refresh.yml)
  handles follow-up refreshes after reviews and external check completion.
- The refresh flow reuses coverage from the `CI` workflow with scoped comment updates and suppresses
  no-op all-clear refresh comments.

## Quickstart for downstream repos

Prefer pinning this reusable workflow to a released version such as `@v1.0.0`
instead of `@main` or an ad hoc commit SHA from an unmerged branch.

Versioning guidance:

- use `@v1` in downstream repositories for the stable major line
- use fixed tags such as `@v1.0.0` when you want exact version pinning
- this repository automatically moves the matching major tag when a new
  concrete `v1.x.y` release tag is created
- when pinning the reusable workflow to an exact tag, also pass
  `checkout_ref` with the same tag so the internal checkout uses the same
  released version

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
      checkout_ref: v1.0.0
      pr_number: ${{ github.event.pull_request.number }}
      head_sha: ${{ github.event.pull_request.head.sha }}

  trigger_from_status:
    if: >-
      github.event_name == 'status' &&
      github.event.context == 'pre-commit.ci - pr' &&
      github.event.state == 'failure'
    uses: your-org/pre-commit-ci-autofix-trigger/.github/workflows/reusable-autofix-trigger.yml@v1.0.0
    with:
      checkout_ref: v1.0.0
      head_sha: ${{ github.event.sha }}
```

If needed, pass custom allowlist/label and optional token override:

```yaml
jobs:
  trigger:
    uses: your-org/pre-commit-ci-autofix-trigger/.github/workflows/reusable-autofix-trigger.yml@v1.0.0
    with:
      checkout_ref: v1.0.0
      pr_number: ${{ github.event.pull_request.number }}
      bot_logins: copilot-swe-agent,github-copilot[bot],claude[bot]
      label: pre-commit.ci autofix
    secrets:
      access_token: ${{ secrets.GITHUB_TOKEN }}
```

If you use a fine-grained personal access token for `access_token`, the working
permission set for PR labeling and the managed attempt-state comment is:

- `Issues`: Read and write
- `Pull requests`: Read and write
- `Metadata`: Read-only

In practice, `Issues: Read and write` alone can still produce
`403 Resource not accessible by personal access token` for the label-write
endpoint. If you do not need an override token, prefer the default
`${{ github.token }}`.

## Reusable workflow inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `pr_number` | no | resolved from `head_sha` when omitted | PR number in the caller repo |
| `repo_owner` | no | caller owner | Repository owner to query |
| `repo_name` | no | caller repo name | Repository name to query |
| `checkout_ref` | no | `v1` | Internal checkout ref for `shaypal5/pre-commit-ci-autofix-trigger`; set this to the same exact tag as the reusable workflow when you need fully pinned behavior |
| `head_sha` | no | current PR head, or used to resolve the PR when `pr_number` is omitted | Commit SHA to inspect instead of re-reading the latest PR head |
| `bot_logins` | no | `copilot-swe-agent,github-copilot[bot],copilot,claude[bot],claude,chatgpt,openai` | Comma-separated bot allowlist |
| `label` | no | `pre-commit.ci autofix` | Label to apply |
| `max_attempts_per_head_sha` | no | `2` | Maximum autofix label applications allowed per PR head commit |
| `dry_run` | no | `false` | Log decision only, no mutation |

Secret:

- `access_token` (optional). If omitted, defaults to `${{ github.token }}`.
- For fine-grained PATs used as `access_token`, grant:
  `Issues: Read and write`, `Pull requests: Read and write`, and
  `Metadata: Read-only`.

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
- `--max-attempts-per-head-sha` (default `2`)
- `--dry-run`

## Idempotency and expected behavior

- Re-running on same PR is safe.
- If label already exists, tool exits successfully with no changes.
- If pre-commit.ci signal is not found, tool does nothing.
- If the PR head commit already has the configured maximum number of recorded
  autofix attempts, tool exits successfully with no changes.
- If attempt state cannot be read or written, tool fails closed and does not add
  the label.
- If label writing fails after an attempt is recorded, that record still consumes
  an attempt for the PR head commit.

### Label creation behavior

The tool uses one managed issue comment for durable attempt state and
`POST /issues/{issue_number}/labels` for the autofix trigger. If a label name
does not already exist, GitHub may create it implicitly depending on repository
settings and token permissions.

For override tokens, the required permissions are not purely theoretical. A
fine-grained PAT was observed to succeed only when it had all of:

- `Issues`: Read and write
- `Pull requests`: Read and write
- `Metadata`: Read-only

If GitHub rejects the request, the CLI surfaces a clear error or warning,
depending on the failure mode.

## Current limitations

- Autofix triggering is label-based; one managed comment is used for attempt state.
- Runs only when invoked by downstream workflow.
- Relies on visible check runs/statuses for the PR head SHA.
- Simple first-page check/status reads are used (sufficient for expected small signal sets).

## Development

```bash
python -m pip install -e .[dev]
ruff check .
pytest --cov=src/pre_commit_ci_autofix_trigger --cov-branch --cov-report=xml --cov-report=term
```

## Maintainer release flow

`.github/workflows/release.yml` runs on every push to `main`. When the pushed
commit's version in `pyproject.toml` does not already have a matching tag, the
workflow:

- reads the version from `pyproject.toml`
- creates a matching tag such as `v1.0.0` on the pushed `main` commit if missing
- creates a GitHub release for that tag
- force-updates the matching major tag (`v1`) to the same commit

The major tag move happens inside the same workflow as concrete release
creation. That avoids relying on a second workflow being triggered by a tag
that was itself created via `GITHUB_TOKEN`.
