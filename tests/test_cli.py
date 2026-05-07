from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pre_commit_ci_autofix_trigger import cli
from pre_commit_ci_autofix_trigger.attempts import (
    AttemptState,
    build_attempt_state_body,
    new_attempt,
)
from pre_commit_ci_autofix_trigger.github_api import GitHubApiError


def _state_body(*head_shas: str) -> str:
    return build_attempt_state_body(
        AttemptState(
            comment_id=None,
            attempts=[
                new_attempt(head_sha=head_sha, run_id=str(index), run_attempt="1")
                for index, head_sha in enumerate(head_shas, start=1)
            ],
        )
    )


class DummyClient:
    def __init__(self, token: str, owner: str, repo: str):
        self.token = token
        self.owner = owner
        self.repo = repo
        self.added_labels: list[tuple[int, str]] = []
        self.created_comments: list[dict] = []
        self.updated_comments: list[tuple[int, str]] = []
        self.check_run_refs: list[str] = []
        self.status_refs: list[str] = []
        self.commit_pull_refs: list[str] = []
        self._next_comment_id = 100
        self._comment_created_at = datetime(2026, 5, 1, tzinfo=UTC)

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

    def list_issue_comments(self, pr_number: int) -> list[dict]:
        return list(self.created_comments)

    def create_issue_comment(self, pr_number: int, body: str) -> dict:
        comment = {
            "id": self._next_comment_id,
            "body": body,
            "created_at": self._comment_created_at.isoformat().replace("+00:00", "Z"),
        }
        self._next_comment_id += 1
        self._comment_created_at += timedelta(seconds=1)
        self.created_comments.append(comment)
        return comment

    def update_issue_comment(self, comment_id: int, body: str) -> dict:
        self.updated_comments.append((comment_id, body))
        for comment in self.created_comments:
            if comment["id"] == comment_id:
                comment["body"] = body
                return comment
        comment = {
            "id": comment_id,
            "body": body,
            "created_at": "2026-05-01T00:00:01Z",
        }
        self.created_comments.append(comment)
        return comment

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
    assert len(created["client"].created_comments) == 1


def test_cli_allows_second_attempt(monkeypatch) -> None:
    created: dict[str, DummyClient] = {}

    class AttemptLimitClient(DummyClient):
        def __init__(self, token: str, owner: str, repo: str):
            super().__init__(token, owner, repo)
            self.created_comments = [
                {
                    "id": 1,
                    "body": _state_body("abc123"),
                    "created_at": "2026-05-01T00:00:01Z",
                }
            ]

    def _factory(token: str, owner: str, repo: str) -> AttemptLimitClient:
        client = AttemptLimitClient(token, owner, repo)
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
    assert len(created["client"].created_comments) == 1
    assert len(created["client"].updated_comments) == 1


def test_cli_skips_when_attempt_limit_already_reached(monkeypatch, capsys) -> None:
    created: dict[str, DummyClient] = {}

    class LimitReachedClient(DummyClient):
        def __init__(self, token: str, owner: str, repo: str):
            super().__init__(token, owner, repo)
            self.created_comments = [
                {
                    "id": 1,
                    "body": _state_body("abc123", "abc123"),
                    "created_at": "2026-05-01T00:00:01Z",
                },
            ]

    def _factory(token: str, owner: str, repo: str) -> LimitReachedClient:
        client = LimitReachedClient(token, owner, repo)
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

    out = capsys.readouterr().out
    assert rc == 0
    assert "Attempt limit reached" in out
    assert created["client"].added_labels == []
    assert len(created["client"].created_comments) == 1
    assert created["client"].updated_comments == []


def test_cli_label_present_skips_before_attempt_claim(monkeypatch) -> None:
    created: dict[str, DummyClient] = {}

    class LabeledClient(DummyClient):
        def get_pr(self, pr_number: int) -> dict:
            pr = super().get_pr(pr_number)
            pr["labels"] = [{"name": "pre-commit.ci autofix"}]
            return pr

    def _factory(token: str, owner: str, repo: str) -> LabeledClient:
        client = LabeledClient(token, owner, repo)
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
    assert created["client"].created_comments == []
    assert created["client"].added_labels == []


def test_cli_dry_run_does_not_create_attempt_claim(monkeypatch) -> None:
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
            "--dry-run",
        ]
    )

    assert rc == 0
    assert created["client"].created_comments == []
    assert created["client"].added_labels == []


def test_cli_state_change_during_claim_fails_closed(monkeypatch, capsys) -> None:
    created: dict[str, DummyClient] = {}

    class RacingClient(DummyClient):
        def __init__(self, token: str, owner: str, repo: str):
            super().__init__(token, owner, repo)
            self.list_calls = 0
            self.created_comments = [
                {
                    "id": 1,
                    "body": _state_body("abc123"),
                    "created_at": "2026-05-01T00:00:01Z",
                }
            ]

        def list_issue_comments(self, pr_number: int) -> list[dict]:
            self.list_calls += 1
            if self.list_calls == 1:
                return list(self.created_comments)
            return [
                {
                    **self.created_comments[0],
                    "body": _state_body("abc123", "abc123", "abc123"),
                }
            ]

    def _factory(token: str, owner: str, repo: str) -> RacingClient:
        client = RacingClient(token, owner, repo)
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

    err = capsys.readouterr().err
    assert rc == 1
    assert "concurrent autofix attempt state change detected" in err
    assert created["client"].added_labels == []


def test_cli_stale_re_read_that_hides_concurrent_claim_does_not_prove_serialization(
    monkeypatch,
) -> None:
    created: dict[str, DummyClient] = {}

    class StaleReadClient(DummyClient):
        def list_issue_comments(self, pr_number: int) -> list[dict]:
            if not self.created_comments:
                return []
            return [self.created_comments[-1]]

    def _factory(token: str, owner: str, repo: str) -> StaleReadClient:
        client = StaleReadClient(token, owner, repo)
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


def test_cli_rejects_invalid_max_attempts(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "GitHubClient", DummyClient)

    try:
        cli.run(
            [
                "--repo-owner",
                "acme",
                "--repo-name",
                "demo",
                "--pr-number",
                "33",
                "--github-token",
                "x",
                "--max-attempts-per-head-sha",
                "0",
            ]
        )
    except SystemExit as exc:
        assert exc.code == 2
    else:  # pragma: no cover - defensive, assertion should exit first
        raise AssertionError("expected parser.error to exit")

    err = capsys.readouterr().err
    assert "--max-attempts-per-head-sha must be at least 1" in err


def test_cli_rejects_invalid_env_max_attempts(monkeypatch, capsys) -> None:
    monkeypatch.setenv("MAX_ATTEMPTS_PER_HEAD_SHA", "abc")
    monkeypatch.setattr(cli, "GitHubClient", DummyClient)

    try:
        cli.run(
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
    except SystemExit as exc:
        assert exc.code == 2
    else:  # pragma: no cover - defensive, assertion should exit first
        raise AssertionError("expected parser.error to exit")

    err = capsys.readouterr().err
    assert "--max-attempts-per-head-sha must be an integer" in err


def test_cli_comment_read_failure_fails_closed(monkeypatch, capsys) -> None:
    class CommentReadErrorClient(DummyClient):
        def list_issue_comments(self, pr_number: int) -> list[dict]:
            raise GitHubApiError("comments unavailable")

    monkeypatch.setattr(cli, "GitHubClient", CommentReadErrorClient)
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
    assert "unable to read autofix attempt state" in err


def test_cli_comment_write_failure_fails_closed(monkeypatch, capsys) -> None:
    class CommentWriteErrorClient(DummyClient):
        def create_issue_comment(self, pr_number: int, body: str) -> dict:
            raise GitHubApiError("comments unavailable")

    monkeypatch.setattr(cli, "GitHubClient", CommentWriteErrorClient)
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
    assert "unable to write autofix attempt state" in err


def test_cli_comment_update_failure_fails_closed(monkeypatch, capsys) -> None:
    class CommentUpdateErrorClient(DummyClient):
        def __init__(self, token: str, owner: str, repo: str):
            super().__init__(token, owner, repo)
            self.created_comments = [
                {
                    "id": 1,
                    "body": _state_body("different"),
                    "created_at": "2026-05-01T00:00:01Z",
                }
            ]

        def update_issue_comment(self, comment_id: int, body: str) -> dict:
            raise GitHubApiError("comments unavailable")

    monkeypatch.setattr(cli, "GitHubClient", CommentUpdateErrorClient)
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
    assert "unable to write autofix attempt state" in err


def test_cli_comment_create_response_without_id_fails_closed(monkeypatch, capsys) -> None:
    class CommentCreateShapeErrorClient(DummyClient):
        def create_issue_comment(self, pr_number: int, body: str) -> dict:
            self.created_comments.append({"body": body, "created_at": "2026-05-01T00:00:01Z"})
            return {}

    monkeypatch.setattr(cli, "GitHubClient", CommentCreateShapeErrorClient)
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
    assert "unable to identify saved autofix attempt state" in err


def test_cli_comment_verify_read_failure_fails_closed(monkeypatch, capsys) -> None:
    class CommentVerifyReadErrorClient(DummyClient):
        def __init__(self, token: str, owner: str, repo: str):
            super().__init__(token, owner, repo)
            self.list_calls = 0

        def list_issue_comments(self, pr_number: int) -> list[dict]:
            self.list_calls += 1
            if self.list_calls == 1:
                return []
            raise GitHubApiError("comments unavailable")

    monkeypatch.setattr(cli, "GitHubClient", CommentVerifyReadErrorClient)
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
    assert "unable to verify autofix attempt state" in err


def test_cli_comment_claim_not_visible_on_re_read_fails_closed(monkeypatch, capsys) -> None:
    class CommentClaimInvisibleClient(DummyClient):
        def __init__(self, token: str, owner: str, repo: str):
            super().__init__(token, owner, repo)
            self.list_calls = 0

        def list_issue_comments(self, pr_number: int) -> list[dict]:
            self.list_calls += 1
            if self.list_calls == 1:
                return []
            return []

    monkeypatch.setattr(cli, "GitHubClient", CommentClaimInvisibleClient)
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
    assert "saved autofix attempt state was not visible on re-read" in err


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
    created: dict[str, DummyClient] = {}

    class PermissionDeniedClient(DummyClient):
        def add_label(self, pr_number: int, label: str) -> list[dict]:
            raise GitHubApiError(
                "GitHub API POST /repos/acme/demo/issues/33/labels failed: 403 "
                '{"message":"Resource not accessible by integration"}'
            )

    def _factory(token: str, owner: str, repo: str) -> PermissionDeniedClient:
        client = PermissionDeniedClient(token, owner, repo)
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
    out = capsys.readouterr().out
    assert rc == 0
    assert "WARNING: unable to add the autofix label" in out
    assert len(created["client"].created_comments) == 1


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
