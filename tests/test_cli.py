from __future__ import annotations

from pre_commit_ci_autofix_trigger import cli
from pre_commit_ci_autofix_trigger.github_api import GitHubApiError


class DummyClient:
    def __init__(self, token: str, owner: str, repo: str):
        self.token = token
        self.owner = owner
        self.repo = repo
        self.added_labels: list[tuple[int, str]] = []
        self.check_run_refs: list[str] = []
        self.status_refs: list[str] = []
        self.commit_pull_refs: list[str] = []

    def get_pr(self, pr_number: int) -> dict:
        return {
            "number": pr_number,
            "user": {"login": "copilot"},
            "head": {"sha": "abc123"},
            "labels": [],
        }

    def list_pulls_for_commit(self, ref: str) -> list[dict]:
        self.commit_pull_refs.append(ref)
        return [
            {
                "number": 77,
                "state": "open",
                "user": {"login": "copilot"},
                "head": {"sha": ref},
                "labels": [],
            }
        ]

    def list_issue_labels(self, pr_number: int) -> list[dict]:
        return []

    def get_check_runs(self, ref: str) -> list[dict]:
        self.check_run_refs.append(ref)
        return [{"name": "pre-commit.ci", "conclusion": "failure"}]

    def get_commit_statuses(self, ref: str) -> list[dict]:
        self.status_refs.append(ref)
        return []

    def add_label(self, pr_number: int, label: str) -> list[dict]:
        self.added_labels.append((pr_number, label))
        return []


def test_cli_dry_run(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "GitHubClient", DummyClient)
    rc = cli.run(
        [
            "--repo-owner",
            "acme",
            "--repo-name",
            "demo",
            "--pr-number",
            "12",
            "--github-token",
            "x",
            "--dry-run",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "Dry-run enabled" in out


def test_cli_adds_label(monkeypatch) -> None:
    created: dict[str, DummyClient] = {}

    def _factory(token: str, owner: str, repo: str) -> DummyClient:
        client = DummyClient(token, owner, repo)
        created["client"] = client
        return client

    monkeypatch.setattr(cli, "GitHubClient", _factory)
    rc = cli.run(
        [
            "--repo-owner",
            "acme",
            "--repo-name",
            "demo",
            "--pr-number",
            "33",
            "--github-token",
            "x",
        ]
    )
    assert rc == 0
    assert created["client"].added_labels == [(33, "pre-commit.ci autofix")]


def test_cli_uses_explicit_head_sha(monkeypatch) -> None:
    created: dict[str, DummyClient] = {}

    def _factory(token: str, owner: str, repo: str) -> DummyClient:
        client = DummyClient(token, owner, repo)
        created["client"] = client
        return client

    monkeypatch.setattr(cli, "GitHubClient", _factory)
    rc = cli.run(
        [
            "--repo-owner",
            "acme",
            "--repo-name",
            "demo",
            "--pr-number",
            "44",
            "--head-sha",
            "override456",
            "--github-token",
            "x",
            "--dry-run",
        ]
    )
    assert rc == 0
    assert created["client"].check_run_refs == ["override456"]
    assert created["client"].status_refs == ["override456"]


def test_cli_resolves_pr_number_from_head_sha(monkeypatch, capsys) -> None:
    created: dict[str, DummyClient] = {}

    def _factory(token: str, owner: str, repo: str) -> DummyClient:
        client = DummyClient(token, owner, repo)
        created["client"] = client
        return client

    monkeypatch.setattr(cli, "GitHubClient", _factory)
    rc = cli.run(
        [
            "--repo-owner",
            "acme",
            "--repo-name",
            "demo",
            "--head-sha",
            "statussha123",
            "--github-token",
            "x",
            "--dry-run",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "PR number: 77" in out
    assert created["client"].commit_pull_refs == ["statussha123"]
    assert created["client"].check_run_refs == ["statussha123"]
    assert created["client"].status_refs == ["statussha123"]


def test_cli_prefers_open_pr_with_matching_head_sha(monkeypatch, capsys) -> None:
    created: dict[str, DummyClient] = {}

    class MatchingDummyClient(DummyClient):
        def list_pulls_for_commit(self, ref: str) -> list[dict]:
            self.commit_pull_refs.append(ref)
            return [
                {
                    "number": 70,
                    "state": "open",
                    "user": {"login": "copilot"},
                    "head": {"sha": "different"},
                    "labels": [],
                },
                {
                    "number": 71,
                    "state": "open",
                    "user": {"login": "copilot"},
                    "head": {"sha": ref},
                    "labels": [],
                },
            ]

    def _factory(token: str, owner: str, repo: str) -> MatchingDummyClient:
        client = MatchingDummyClient(token, owner, repo)
        created["client"] = client
        return client

    monkeypatch.setattr(cli, "GitHubClient", _factory)
    rc = cli.run(
        [
            "--repo-owner",
            "acme",
            "--repo-name",
            "demo",
            "--head-sha",
            "statussha123",
            "--github-token",
            "x",
            "--dry-run",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "PR number: 71" in out


def test_cli_errors_when_multiple_open_prs_remain(monkeypatch, capsys) -> None:
    class AmbiguousDummyClient(DummyClient):
        def list_pulls_for_commit(self, ref: str) -> list[dict]:
            self.commit_pull_refs.append(ref)
            return [
                {
                    "number": 70,
                    "state": "open",
                    "user": {"login": "copilot"},
                    "head": {"sha": "different-a"},
                    "labels": [],
                },
                {
                    "number": 71,
                    "state": "open",
                    "user": {"login": "copilot"},
                    "head": {"sha": "different-b"},
                    "labels": [],
                },
            ]

    monkeypatch.setattr(cli, "GitHubClient", AmbiguousDummyClient)
    rc = cli.run(
        [
            "--repo-owner",
            "acme",
            "--repo-name",
            "demo",
            "--head-sha",
            "statussha123",
            "--github-token",
            "x",
        ]
    )
    err = capsys.readouterr().err
    assert rc == 1
    assert "multiple open pull requests found" in err


def test_cli_treats_label_permission_error_as_nonfatal(monkeypatch, capsys) -> None:
    class PermissionDeniedClient(DummyClient):
        def add_label(self, pr_number: int, label: str) -> list[dict]:
            raise GitHubApiError(
                'GitHub API POST /repos/acme/demo/issues/33/labels failed: 403 '
                '{"message":"Resource not accessible by integration"}'
            )

    monkeypatch.setattr(cli, "GitHubClient", PermissionDeniedClient)
    rc = cli.run(
        [
            "--repo-owner",
            "acme",
            "--repo-name",
            "demo",
            "--pr-number",
            "33",
            "--github-token",
            "x",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "WARNING: unable to add the autofix label" in out


def test_cli_still_fails_for_other_label_errors(monkeypatch, capsys) -> None:
    class OtherLabelErrorClient(DummyClient):
        def add_label(self, pr_number: int, label: str) -> list[dict]:
            raise GitHubApiError(
                "GitHub API POST /repos/acme/demo/issues/33/labels failed: 500 Server Error"
            )

    monkeypatch.setattr(cli, "GitHubClient", OtherLabelErrorClient)
    rc = cli.run(
        [
            "--repo-owner",
            "acme",
            "--repo-name",
            "demo",
            "--pr-number",
            "33",
            "--github-token",
            "x",
        ]
    )
    err = capsys.readouterr().err
    assert rc == 1
    assert "500 Server Error" in err
