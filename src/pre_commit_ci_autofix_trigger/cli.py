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
    parser.add_argument("--pr-number", type=int)
    parser.add_argument("--head-sha")
    parser.add_argument("--bot-logins", default=os.getenv("BOT_LOGINS", DEFAULT_BOT_LOGINS))
    parser.add_argument("--label", default=os.getenv("AUTOFIX_LABEL", "pre-commit.ci autofix"))
    parser.add_argument("--github-token", default=os.getenv("GITHUB_TOKEN"))
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _resolve_pr(
    client: GitHubClient, pr_number: int | None, head_sha: str | None
) -> tuple[int, dict]:
    if pr_number is not None:
        return pr_number, client.get_pr(pr_number)

    if not head_sha:
        raise GitHubApiError("either PR number or head SHA is required")

    pulls = client.list_pulls_for_commit(head_sha)
    if not pulls:
        raise GitHubApiError(f"no pull requests found for commit {head_sha}")

    exact_open_matches = [
        pull
        for pull in pulls
        if str(pull.get("state", "")).lower() == "open"
        and str(pull.get("head", {}).get("sha", "")) == head_sha
    ]
    if len(exact_open_matches) > 1:
        raise GitHubApiError(
            f"multiple open pull requests found for commit {head_sha}; please pass --pr-number"
        )
    if exact_open_matches:
        chosen = exact_open_matches[0]
    else:
        open_pulls = [pull for pull in pulls if str(pull.get("state", "")).lower() == "open"]
        if len(open_pulls) > 1:
            raise GitHubApiError(
                f"multiple open pull requests found for commit {head_sha}; please pass --pr-number"
            )
        chosen = open_pulls[0] if open_pulls else pulls[0]

    resolved_pr_number = chosen.get("number")
    if not isinstance(resolved_pr_number, int):
        raise GitHubApiError(
            "Unexpected response shape from commit-pulls endpoint: missing numeric PR number"
        )
    return resolved_pr_number, chosen


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

    if args.pr_number is None and not args.head_sha:
        parser.error("either --pr-number or --head-sha is required")

    if not args.github_token:
        parser.error("GitHub token required via --github-token or GITHUB_TOKEN")

    print(f"Repository: {owner}/{repo}")

    allowlist = parse_allowlist(args.bot_logins)
    print(f"Configured bot allowlist size: {len(allowlist)}")

    client = GitHubClient(token=args.github_token, owner=owner, repo=repo)

    try:
        pr_number, pr = _resolve_pr(client, args.pr_number, args.head_sha)
        author_login = str(pr.get("user", {}).get("login", ""))
        head_sha = args.head_sha or str(pr.get("head", {}).get("sha", ""))
        labels_raw = pr.get("labels")
        labels = labels_raw if labels_raw is not None else client.list_issue_labels(pr_number)

        if not head_sha:
            raise GitHubApiError("PR head SHA missing from API response")

        print(f"PR number: {pr_number}")
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

        client.add_label(pr_number, args.label)
        print(f"Added label '{args.label}' to PR #{pr_number}.")
        return 0
    except GitHubApiError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
