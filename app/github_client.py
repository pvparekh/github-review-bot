import os
import httpx
from github import GithubIntegration, Auth
from dotenv import load_dotenv

load_dotenv()

_APP_ID = int(os.environ["GITHUB_APP_ID"])
_PRIVATE_KEY_PATH = os.environ["GITHUB_PRIVATE_KEY_PATH"]

with open(_PRIVATE_KEY_PATH, "r") as f:
    _PRIVATE_KEY = f.read()


def get_installation_token(installation_id: int) -> str:
    auth = Auth.AppAuth(_APP_ID, _PRIVATE_KEY)
    gi = GithubIntegration(auth=auth)
    token = gi.get_access_token(installation_id)
    return token.token


def get_pr_diff(repo_full_name: str, pr_number: int, token: str) -> str:
    url = f"https://api.github.com/repos/{repo_full_name}/pulls/{pr_number}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3.diff",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    with httpx.Client() as client:
        response = client.get(url, headers=headers, follow_redirects=True)
        response.raise_for_status()
        return response.text


def post_review(
    repo_full_name: str,
    pr_number: int,
    token: str,
    summary: str,
    inline_comments: list[dict],
) -> None:
    url = f"https://api.github.com/repos/{repo_full_name}/pulls/{pr_number}/reviews"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    github_comments = [
        {
            "path": c["file"],
            "position": c["position"],
            "body": c["body"],
        }
        for c in inline_comments
    ]

    payload = {
        "body": summary,
        "event": "COMMENT",
        "comments": github_comments,
    }

    with httpx.Client() as client:
        response = client.post(url, headers=headers, json=payload)

        if response.status_code == 422 and github_comments:
            print(
                f"[github] 422 posting {len(github_comments)} inline comments — "
                f"GitHub said: {response.text[:800]}",
                flush=True,
            )
            print("[github] retrying with summary only (no inline comments)", flush=True)
            payload["comments"] = []
            response = client.post(url, headers=headers, json=payload)

        response.raise_for_status()
