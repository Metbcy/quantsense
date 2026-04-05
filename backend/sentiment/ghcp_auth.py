"""GitHub Copilot device-flow auth for LLM access."""
from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

CLIENT_ID = "Iv1.b507a08c87ecfe98"
TOKEN_PATH = Path.home() / ".config" / "ghcp" / "token.json"
COPILOT_ENDPOINT = "https://api.individual.githubcopilot.com"

DEFAULT_HEADERS = {
    "Copilot-Integration-Id": "vscode-chat",
    "Editor-Version": "vscode/1.95.0",
}


def _load_cache() -> dict | None:
    try:
        return json.loads(TOKEN_PATH.read_text()) if TOKEN_PATH.exists() else None
    except Exception:
        return None


def _save_cache(data: dict) -> None:
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(json.dumps(data, indent=2))


def device_flow_login() -> str:
    """Run the GitHub device-flow OAuth and return a GitHub access token."""
    resp = httpx.post(
        "https://github.com/login/device/code",
        json={"client_id": CLIENT_ID, "scope": ""},
        headers={"Accept": "application/json"},
    )
    info = resp.json()

    print(f"\n\U0001f510 GitHub Authentication Required")
    print(f"   Visit:  {info['verification_uri']}")
    print(f"   Enter:  {info['user_code']}\n")
    print("   Waiting for authorization...\n")

    deadline = time.time() + info["expires_in"]
    interval = info.get("interval", 5)

    while time.time() < deadline:
        time.sleep(interval)
        r = httpx.post(
            "https://github.com/login/oauth/access_token",
            json={
                "client_id": CLIENT_ID,
                "device_code": info["device_code"],
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
            headers={"Accept": "application/json"},
        )
        data = r.json()
        if "access_token" in data:
            print("   \u2705 Authenticated!\n")
            return data["access_token"]
        if data.get("error") == "slow_down":
            interval += 5
        elif data.get("error") != "authorization_pending":
            raise RuntimeError(
                f"Auth failed: {data.get('error_description', data.get('error'))}"
            )

    raise RuntimeError("Authentication timed out")


def _get_copilot_token(github_token: str) -> dict:
    resp = httpx.get(
        "https://api.github.com/copilot_internal/v2/token",
        headers={
            "Authorization": f"token {github_token}",
            "Accept": "application/json",
        },
    )
    resp.raise_for_status()
    return resp.json()


def get_token() -> str:
    """Return a valid Copilot session token, authenticating if needed."""
    cache = _load_cache()

    if cache and cache.get("copilot_token") and cache.get("copilot_expires_at"):
        if time.time() < cache["copilot_expires_at"] - 60:
            return cache["copilot_token"]

    if cache and cache.get("github_token"):
        try:
            cp = _get_copilot_token(cache["github_token"])
            cache["copilot_token"] = cp["token"]
            cache["copilot_expires_at"] = cp["expires_at"]
            _save_cache(cache)
            return cp["token"]
        except Exception:
            pass

    gh_token = device_flow_login()
    cp = _get_copilot_token(gh_token)
    _save_cache(
        {
            "github_token": gh_token,
            "copilot_token": cp["token"],
            "copilot_expires_at": cp["expires_at"],
        }
    )
    return cp["token"]
