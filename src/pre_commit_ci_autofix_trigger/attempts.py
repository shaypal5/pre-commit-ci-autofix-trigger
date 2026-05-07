from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

STATE_MARKER = "<!-- pre-commit-ci-autofix-trigger:state schema=v1 -->"
_STATE_JSON_RE = re.compile(rf"{re.escape(STATE_MARKER)}.*?```json\s*(.*?)\s*```", re.DOTALL)


@dataclass(frozen=True)
class Attempt:
    head_sha: str
    claimed_at: str
    run_id: str
    run_attempt: str


@dataclass(frozen=True)
class AttemptState:
    comment_id: int | None
    attempts: list[Attempt]


def new_attempt(
    *,
    head_sha: str,
    run_id: str | None,
    run_attempt: str | None,
    claimed_at: datetime | None = None,
) -> Attempt:
    return Attempt(
        head_sha=head_sha,
        claimed_at=(claimed_at or datetime.now(UTC)).isoformat(),
        run_id=run_id or "",
        run_attempt=run_attempt or "",
    )


def _attempt_from_raw(raw: Any) -> Attempt | None:
    if not isinstance(raw, dict):
        return None
    head_sha = str(raw.get("head_sha", ""))
    if not head_sha:
        return None
    return Attempt(
        head_sha=head_sha,
        claimed_at=str(raw.get("claimed_at", "")),
        run_id=str(raw.get("run_id", "")),
        run_attempt=str(raw.get("run_attempt", "")),
    )


def parse_attempt_state_comment(comment: dict) -> AttemptState | None:
    body = str(comment.get("body", ""))
    match = _STATE_JSON_RE.search(body)
    if not match:
        return None

    try:
        payload = json.loads(match.group(1))
        comment_id = int(comment["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None

    if payload.get("schema") != "v1":
        return None

    attempts = [
        attempt
        for raw_attempt in payload.get("attempts", [])
        if (attempt := _attempt_from_raw(raw_attempt)) is not None
    ]
    return AttemptState(comment_id=comment_id, attempts=attempts)


def load_attempt_state(comments: list[dict]) -> AttemptState:
    states = [
        state for comment in comments if (state := parse_attempt_state_comment(comment)) is not None
    ]
    if not states:
        return AttemptState(comment_id=None, attempts=[])
    return AttemptState(
        comment_id=states[0].comment_id,
        attempts=[attempt for state in states for attempt in state.attempts],
    )


def attempts_for_head(state: AttemptState, *, head_sha: str) -> list[Attempt]:
    return [attempt for attempt in state.attempts if attempt.head_sha == head_sha]


def append_attempt(state: AttemptState, attempt: Attempt) -> AttemptState:
    return AttemptState(comment_id=state.comment_id, attempts=[*state.attempts, attempt])


def build_attempt_state_body(state: AttemptState) -> str:
    payload = {
        "schema": "v1",
        "attempts": [
            {
                "head_sha": attempt.head_sha,
                "claimed_at": attempt.claimed_at,
                "run_id": attempt.run_id,
                "run_attempt": attempt.run_attempt,
            }
            for attempt in state.attempts
        ],
    }
    return (
        f"{STATE_MARKER}\n"
        "pre-commit.ci autofix trigger state\n\n"
        "This managed comment records autofix label attempts by PR head commit. "
        "Do not edit it manually.\n\n"
        "```json\n"
        f"{json.dumps(payload, indent=2, sort_keys=True)}\n"
        "```"
    )
