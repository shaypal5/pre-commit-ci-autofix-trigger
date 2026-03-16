from __future__ import annotations

import argparse
import os
import sys

from pre_commit_ci_autofix_trigger.github_api import GitHubApiError, GitHubClient
from pre_commit_ci_autofix_trigger.logic import decide_autofix, parse_allowlist

DEFAULT_BOT_LOGINS = (
    "copilot-swe-agent,github-copilot[bot],copilot,claude[bot],claude,chatgpt,openai"
)


def _parse_repo_name_from_env() -> tuple[str | None, str | None]:
    repository = os.getenv("GITHUB_REPOSITORY", "")
    if "/" not in repository:
        return None, None
    owner, repo = repository.split("/", 1)
    return owner, repo


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Trigger pre-commit.ci autofix label when conditions match"
    )
    parser.add_argument("--repo-owner", default=os.getenv("GITHUB_REPOSITORY_OWNER"))
    parser.add_argument("--repo-name")
    parser.add_argument("--pr-number", type=int, required=True)
    parser.add_argument("--head-sha")
    parser.add_argument("--bot-logins", default=os.getenv("BOT_LOGINS", DEFAULT_BOT_LOGINS))
    parser.add_argument("--label", default=os.getenv("AUTOFIX_LABEL", "pre-commit.ci autofix"))
    parser.add_argument("--github-token", default=os.getenv("GITHUB_TOKEN"))
    parser.add_argument("--dry-run", action="store_true")
    return parser


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    owner = args.repo_owner
    repo = args.repo_name

    if not (owner and repo):
        env_owner, env_repo = _parse_repo_name_from_env()
        owner = owner or env_owner
        repo = repo or env_repo

    if not owner or not repo:
        parser.error("repo owner and repo name are required (args or GITHUB_REPOSITORY)")

    if not args.github_token:
        parser.error("GitHub token required via --github-token or GITHUB_TOKEN")

    print(f"Repository: {owner}/{repo}")
    print(f"PR number: {args.pr_number}")

    allowlist = parse_allowlist(args.bot_logins)
    print(f"Configured bot allowlist size: {len(allowlist)}")

    client = GitHubClient(token=args.github_token, owner=owner, repo=repo)

    try:
        pr = client.get_pr(args.pr_number)
        author_login = str(pr.get("user", {}).get("login", ""))
        head_sha = args.head_sha or str(pr.get("head", {}).get("sha", ""))
        labels_raw = pr.get("labels")
        labels = labels_raw if labels_raw is not None else client.list_issue_labels(args.pr_number)

        if not head_sha:
            raise GitHubApiError("PR head SHA missing from API response")

        check_runs = client.get_check_runs(head_sha)
        statuses = client.get_commit_statuses(head_sha)

        print(f"PR author: {author_login}")
        print(f"Head SHA: {head_sha}")
        print(f"Found {len(check_runs)} check runs and {len(statuses)} statuses")

        decision = decide_autofix(
            author_login=author_login,
            allowlist=allowlist,
            labels=labels,
            target_label=args.label,
            check_runs=check_runs,
            statuses=statuses,
        )

        print(f"Decision: should_add_label={decision.should_add_label}")
        print(f"Reason: {decision.reason}")

        if not decision.should_add_label:
            print("No action required.")
            return 0

        if args.dry_run:
            print(f"Dry-run enabled; would add label '{args.label}'")
            return 0

        client.add_label(args.pr_number, args.label)
        print(f"Added label '{args.label}' to PR #{args.pr_number}.")
        return 0
    except GitHubApiError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
