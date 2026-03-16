from __future__ import annotations

from dataclasses import dataclass

try:
    import requests
except ImportError:  # pragma: no cover - exercised only in constrained envs
    requests = None


class GitHubApiError(RuntimeError):
    """Raised when the GitHub API returns an unexpected response."""


@dataclass
class GitHubClient:
    token: str
    owner: str
    repo: str
    api_base: str = "https://api.github.com"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _request(self, method: str, path: str, **kwargs: object) -> dict | list:
        url = f"{self.api_base}{path}"
        if requests is None:
            raise GitHubApiError("The 'requests' package is required to call the GitHub API")
        response = requests.request(method, url, headers=self._headers(), timeout=20, **kwargs)
        if response.status_code >= 400:
            detail = response.text.strip()
            raise GitHubApiError(
                f"GitHub API {method} {path} failed: {response.status_code} {detail}"
            )
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise GitHubApiError(
                f"GitHub API {method} {path} returned non-JSON response: {exc}"
            ) from exc

    def get_pr(self, pr_number: int) -> dict:
        return self._request("GET", f"/repos/{self.owner}/{self.repo}/pulls/{pr_number}")

    def list_issue_labels(self, pr_number: int) -> list[dict]:
        data = self._request("GET", f"/repos/{self.owner}/{self.repo}/issues/{pr_number}/labels")
        if not isinstance(data, list):
            raise GitHubApiError(
                "Unexpected response shape from labels endpoint: "
                f"expected list, got {type(data).__name__}"
            )
        return data

    def get_check_runs(self, ref: str) -> list[dict]:
        data = self._request(
            "GET",
            f"/repos/{self.owner}/{self.repo}/commits/{ref}/check-runs",
        )
        if not isinstance(data, dict):
            raise GitHubApiError(
                "Unexpected response shape from check-runs endpoint: "
                f"expected dict, got {type(data).__name__}"
            )
        return list(data.get("check_runs", []))

    def get_commit_statuses(self, ref: str) -> list[dict]:
        data = self._request(
            "GET",
            f"/repos/{self.owner}/{self.repo}/commits/{ref}/status",
        )
        if not isinstance(data, dict):
            raise GitHubApiError(
                "Unexpected response shape from commit-status endpoint: "
                f"expected dict, got {type(data).__name__}"
            )
        return list(data.get("statuses", []))

    def add_label(self, pr_number: int, label: str) -> list[dict]:
        data = self._request(
            "POST",
            f"/repos/{self.owner}/{self.repo}/issues/{pr_number}/labels",
            json={"labels": [label]},
        )
        if not isinstance(data, list):
            raise GitHubApiError(
                "Unexpected response shape from add-label endpoint: "
                f"expected list, got {type(data).__name__}"
            )
        return data
