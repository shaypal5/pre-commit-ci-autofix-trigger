from __future__ import annotations

from pre_commit_ci_autofix_trigger import cli


class DummyClient:
    def __init__(self, token: str, owner: str, repo: str):
        self.token = token
        self.owner = owner
        self.repo = repo
        self.added_labels: list[tuple[int, str]] = []

    def get_pr(self, pr_number: int) -> dict:
        return {
            "user": {"login": "copilot"},
            "head": {"sha": "abc123"},
            "labels": [],
        }

    def list_issue_labels(self, pr_number: int) -> list[dict]:
        return []

    def get_check_runs(self, ref: str) -> list[dict]:
        return [{"name": "pre-commit.ci", "conclusion": "failure"}]

    def get_commit_statuses(self, ref: str) -> list[dict]:
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
