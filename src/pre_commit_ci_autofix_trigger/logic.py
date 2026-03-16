from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    should_add_label: bool
    reason: str
    pre_commit_state: str


def parse_allowlist(raw: str | None) -> set[str]:
    if not raw:
        return set()
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def is_author_eligible(author_login: str, allowlist: set[str]) -> bool:
    return author_login.lower() in allowlist


def labels_contains(labels: Iterable[dict], target_label: str) -> bool:
    target = target_label.lower()
    for label in labels:
        name = str(label.get("name", "")).lower()
        if name == target:
            return True
    return False


def is_pre_commit_signal_name(name: str) -> bool:
    return "pre-commit.ci" in name.lower()


def has_failing_pre_commit_signal(check_runs: list[dict], statuses: list[dict]) -> bool:
    for check in check_runs:
        if is_pre_commit_signal_name(str(check.get("name", ""))):
            if str(check.get("conclusion", "")).lower() == "failure":
                return True

    for status in statuses:
        if is_pre_commit_signal_name(str(status.get("context", ""))):
            if str(status.get("state", "")).lower() in {"failure", "error"}:
                return True

    return False


def has_any_pre_commit_signal(check_runs: list[dict], statuses: list[dict]) -> bool:
    for check in check_runs:
        if is_pre_commit_signal_name(str(check.get("name", ""))):
            return True
    for status in statuses:
        if is_pre_commit_signal_name(str(status.get("context", ""))):
            return True
    return False


def decide_autofix(
    *,
    author_login: str,
    allowlist: set[str],
    labels: list[dict],
    target_label: str,
    check_runs: list[dict],
    statuses: list[dict],
) -> Decision:
    if not is_author_eligible(author_login, allowlist):
        return Decision(False, f"author '{author_login}' is not in bot allowlist", "not_applicable")

    if labels_contains(labels, target_label):
        return Decision(False, f"label '{target_label}' already present", "unknown")

    if not has_any_pre_commit_signal(check_runs, statuses):
        return Decision(False, "no pre-commit.ci checks/statuses found", "missing")

    if has_failing_pre_commit_signal(check_runs, statuses):
        return Decision(True, "pre-commit.ci failure detected and label missing", "failing")

    return Decision(False, "pre-commit.ci present but not failing", "passing")
