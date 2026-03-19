from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pre_commit_ci_autofix_trigger.github_api import GitHubApiError, GitHubClient


def _make_client() -> GitHubClient:
    return GitHubClient(token="tok", owner="owner", repo="repo")


def _mock_response(
    *,
    status_code: int = 200,
    content: bytes = b"",
    json_data: dict | list | None = None,
    text: str = "",
):
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = content
    resp.text = text
    if json_data is not None:
        resp.json.return_value = json_data
    else:
        resp.json.side_effect = ValueError("No JSON")
    return resp


class TestRequest:
    def test_http_error_raises_github_api_error(self):
        client = _make_client()
        resp = _mock_response(status_code=404, content=b"Not Found", text="Not Found")
        with patch("requests.request", return_value=resp):
            with pytest.raises(GitHubApiError, match="404"):
                client._request("GET", "/some/path")

    def test_empty_body_returns_empty_dict(self):
        client = _make_client()
        resp = _mock_response(status_code=204, content=b"")
        with patch("requests.request", return_value=resp):
            result = client._request("DELETE", "/some/path")
        assert result == {}

    def test_non_json_response_raises_github_api_error(self):
        client = _make_client()
        resp = _mock_response(status_code=200, content=b"<html>bad</html>")
        with patch("requests.request", return_value=resp):
            with pytest.raises(GitHubApiError, match="non-JSON"):
                client._request("GET", "/some/path")

    def test_valid_json_dict_returned(self):
        client = _make_client()
        resp = _mock_response(
            status_code=200, content=b'{"key": "value"}', json_data={"key": "value"}
        )
        with patch("requests.request", return_value=resp):
            result = client._request("GET", "/some/path")
        assert result == {"key": "value"}

    def test_valid_json_list_returned(self):
        client = _make_client()
        resp = _mock_response(status_code=200, content=b"[1,2]", json_data=[1, 2])
        with patch("requests.request", return_value=resp):
            result = client._request("GET", "/some/path")
        assert result == [1, 2]

    def test_500_raises_github_api_error(self):
        client = _make_client()
        resp = _mock_response(status_code=500, content=b"Server Error", text="Server Error")
        with patch("requests.request", return_value=resp):
            with pytest.raises(GitHubApiError, match="500"):
                client._request("GET", "/some/path")


class TestListIssueLabels:
    def test_returns_list(self):
        client = _make_client()
        data = [{"name": "bug"}, {"name": "pre-commit.ci autofix"}]
        resp = _mock_response(status_code=200, content=b"[...]", json_data=data)
        with patch("requests.request", return_value=resp):
            result = client.list_issue_labels(1)
        assert result == data

    def test_non_list_response_raises(self):
        client = _make_client()
        resp = _mock_response(status_code=200, content=b"{}", json_data={"unexpected": "dict"})
        with patch("requests.request", return_value=resp):
            with pytest.raises(GitHubApiError, match="expected list"):
                client.list_issue_labels(1)


class TestListPullsForCommit:
    def test_returns_list(self):
        client = _make_client()
        data = [{"number": 123}]
        resp = _mock_response(status_code=200, content=b"[...]", json_data=data)
        with patch("requests.request", return_value=resp):
            result = client.list_pulls_for_commit("abc123")
        assert result == data

    def test_non_list_response_raises(self):
        client = _make_client()
        resp = _mock_response(status_code=200, content=b"{}", json_data={"unexpected": "dict"})
        with patch("requests.request", return_value=resp):
            with pytest.raises(GitHubApiError, match="expected list"):
                client.list_pulls_for_commit("abc123")


class TestGetCheckRuns:
    def test_returns_check_runs(self):
        client = _make_client()
        data = {"check_runs": [{"name": "pre-commit.ci", "conclusion": "failure"}]}
        resp = _mock_response(status_code=200, content=b"{...}", json_data=data)
        with patch("requests.request", return_value=resp):
            result = client.get_check_runs("abc123")
        assert result == [{"name": "pre-commit.ci", "conclusion": "failure"}]

    def test_missing_check_runs_key_returns_empty(self):
        client = _make_client()
        resp = _mock_response(status_code=200, content=b"{}", json_data={})
        with patch("requests.request", return_value=resp):
            result = client.get_check_runs("abc123")
        assert result == []

    def test_non_dict_response_raises(self):
        client = _make_client()
        resp = _mock_response(status_code=200, content=b"[]", json_data=[])
        with patch("requests.request", return_value=resp):
            with pytest.raises(GitHubApiError, match="expected dict"):
                client.get_check_runs("abc123")


class TestGetCommitStatuses:
    def test_returns_statuses(self):
        client = _make_client()
        data = {"statuses": [{"context": "pre-commit.ci", "state": "failure"}]}
        resp = _mock_response(status_code=200, content=b"{...}", json_data=data)
        with patch("requests.request", return_value=resp):
            result = client.get_commit_statuses("abc123")
        assert result == [{"context": "pre-commit.ci", "state": "failure"}]

    def test_missing_statuses_key_returns_empty(self):
        client = _make_client()
        resp = _mock_response(status_code=200, content=b"{}", json_data={})
        with patch("requests.request", return_value=resp):
            result = client.get_commit_statuses("abc123")
        assert result == []

    def test_non_dict_response_raises(self):
        client = _make_client()
        resp = _mock_response(status_code=200, content=b"[]", json_data=[])
        with patch("requests.request", return_value=resp):
            with pytest.raises(GitHubApiError, match="expected dict"):
                client.get_commit_statuses("abc123")


class TestAddLabel:
    def test_returns_list(self):
        client = _make_client()
        data = [{"name": "pre-commit.ci autofix"}]
        resp = _mock_response(status_code=200, content=b"[...]", json_data=data)
        with patch("requests.request", return_value=resp):
            result = client.add_label(1, "pre-commit.ci autofix")
        assert result == data

    def test_non_list_response_raises(self):
        client = _make_client()
        resp = _mock_response(status_code=200, content=b"{}", json_data={"unexpected": "dict"})
        with patch("requests.request", return_value=resp):
            with pytest.raises(GitHubApiError, match="expected list"):
                client.add_label(1, "pre-commit.ci autofix")
