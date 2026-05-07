from __future__ import annotations

from datetime import UTC, datetime

from pre_commit_ci_autofix_trigger.attempts import (
    AttemptState,
    append_attempt,
    attempts_for_head,
    build_attempt_state_body,
    load_attempt_state,
    new_attempt,
    parse_attempt_state_comment,
)


def _comment(comment_id: int, body: str) -> dict:
    return {"id": comment_id, "body": body, "created_at": "2026-05-01T00:00:00Z"}


def _attempt(head_sha: str):
    return new_attempt(
        head_sha=head_sha,
        run_id="987",
        run_attempt="2",
        claimed_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
    )


def test_build_and_parse_managed_state_comment() -> None:
    state = AttemptState(comment_id=None, attempts=[_attempt("abc123")])
    body = build_attempt_state_body(state)

    parsed = parse_attempt_state_comment(_comment(10, body))

    assert parsed is not None
    assert parsed.comment_id == 10
    assert len(parsed.attempts) == 1
    assert parsed.attempts[0].head_sha == "abc123"
    assert "pre-commit.ci autofix trigger state" in body


def test_malformed_and_unrelated_comments_are_ignored() -> None:
    comments = [
        _comment(1, "plain comment"),
        _comment(2, "<!-- pre-commit-ci-autofix-trigger:state schema=v2 -->"),
        _comment(3, "<!-- pre-commit-ci-autofix-trigger:state schema=v1 -->\n```json\nbad\n```"),
    ]

    assert load_attempt_state(comments) == AttemptState(comment_id=None, attempts=[])


def test_invalid_attempt_entries_are_ignored() -> None:
    body = (
        "<!-- pre-commit-ci-autofix-trigger:state schema=v1 -->\n"
        "```json\n"
        '{"schema": "v1", "attempts": [null, {"head_sha": ""}, {"head_sha": "abc123"}]}\n'
        "```"
    )

    parsed = parse_attempt_state_comment(_comment(10, body))

    assert parsed is not None
    assert [attempt.head_sha for attempt in parsed.attempts] == ["abc123"]


def test_state_comment_with_wrong_payload_schema_is_ignored() -> None:
    body = (
        "<!-- pre-commit-ci-autofix-trigger:state schema=v1 -->\n"
        "```json\n"
        '{"schema": "v2", "attempts": [{"head_sha": "abc123"}]}\n'
        "```"
    )

    assert parse_attempt_state_comment(_comment(10, body)) is None


def test_attempts_are_filtered_by_head_sha() -> None:
    state = AttemptState(
        comment_id=10,
        attempts=[_attempt("abc123"), _attempt("different"), _attempt("abc123")],
    )

    attempts = attempts_for_head(state, head_sha="abc123")

    assert len(attempts) == 2
    assert all(attempt.head_sha == "abc123" for attempt in attempts)


def test_multiple_state_comments_are_folded_into_first_comment() -> None:
    first = AttemptState(comment_id=None, attempts=[_attempt("abc123")])
    second = AttemptState(comment_id=None, attempts=[_attempt("def456")])

    state = load_attempt_state(
        [
            _comment(10, build_attempt_state_body(first)),
            _comment(11, build_attempt_state_body(second)),
        ]
    )

    assert state.comment_id == 10
    assert [attempt.head_sha for attempt in state.attempts] == ["abc123", "def456"]


def test_append_attempt_preserves_existing_state_comment_id() -> None:
    state = AttemptState(comment_id=10, attempts=[_attempt("abc123")])

    updated = append_attempt(state, _attempt("def456"))

    assert updated.comment_id == 10
    assert [attempt.head_sha for attempt in updated.attempts] == ["abc123", "def456"]
