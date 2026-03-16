from pre_commit_ci_autofix_trigger.logic import (
    decide_autofix,
    is_author_eligible,
    is_pre_commit_signal_name,
    labels_contains,
    parse_allowlist,
)


def test_parse_allowlist_trims_and_normalizes() -> None:
    raw = " Copilot, claude[bot], ,CHATGPT "
    assert parse_allowlist(raw) == {"copilot", "claude[bot]", "chatgpt"}


def test_author_eligibility() -> None:
    allowlist = {"copilot", "claude[bot]"}
    assert is_author_eligible("Copilot", allowlist)
    assert not is_author_eligible("human-user", allowlist)


def test_label_exists_detection() -> None:
    labels = [{"name": "bug"}, {"name": "pre-commit.ci autofix"}]
    assert labels_contains(labels, "pre-commit.ci autofix")
    assert not labels_contains(labels, "different")


def test_pre_commit_signal_name_matching() -> None:
    assert is_pre_commit_signal_name("pre-commit.ci - pr")
    assert is_pre_commit_signal_name("Checks / pre-commit.ci")
    assert not is_pre_commit_signal_name("pytest")


def test_decision_non_bot_author_no_action() -> None:
    decision = decide_autofix(
        author_login="human-user",
        allowlist={"copilot"},
        labels=[],
        target_label="pre-commit.ci autofix",
        check_runs=[{"name": "pre-commit.ci", "conclusion": "failure"}],
        statuses=[],
    )
    assert not decision.should_add_label


def test_decision_bot_failing_and_missing_label_adds() -> None:
    decision = decide_autofix(
        author_login="copilot",
        allowlist={"copilot"},
        labels=[],
        target_label="pre-commit.ci autofix",
        check_runs=[{"name": "pre-commit.ci", "conclusion": "failure"}],
        statuses=[],
    )
    assert decision.should_add_label


def test_decision_bot_failing_but_label_exists_no_action() -> None:
    decision = decide_autofix(
        author_login="copilot",
        allowlist={"copilot"},
        labels=[{"name": "pre-commit.ci autofix"}],
        target_label="pre-commit.ci autofix",
        check_runs=[{"name": "pre-commit.ci", "conclusion": "failure"}],
        statuses=[],
    )
    assert not decision.should_add_label


def test_decision_bot_passing_no_action() -> None:
    decision = decide_autofix(
        author_login="copilot",
        allowlist={"copilot"},
        labels=[],
        target_label="pre-commit.ci autofix",
        check_runs=[{"name": "pre-commit.ci", "conclusion": "success"}],
        statuses=[],
    )
    assert not decision.should_add_label


def test_decision_bot_missing_signal_no_action() -> None:
    decision = decide_autofix(
        author_login="copilot",
        allowlist={"copilot"},
        labels=[],
        target_label="pre-commit.ci autofix",
        check_runs=[{"name": "pytest", "conclusion": "failure"}],
        statuses=[{"context": "ci/test", "state": "failure"}],
    )
    assert not decision.should_add_label


def test_decision_uses_status_failure() -> None:
    decision = decide_autofix(
        author_login="copilot",
        allowlist={"copilot"},
        labels=[],
        target_label="pre-commit.ci autofix",
        check_runs=[],
        statuses=[{"context": "pre-commit.ci - status", "state": "error"}],
    )
    assert decision.should_add_label
