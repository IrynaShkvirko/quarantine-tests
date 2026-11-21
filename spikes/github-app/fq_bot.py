# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx", "pyjwt[crypto]"]
# ///
"""M0-12 spike: GitHub App opens a quarantine.yaml PR and merges it itself (D39).

Usage (key stays outside the repo):
  FQ_APP_ID=123 FQ_APP_KEY_PATH=~/.secrets/fq-bot-dev.pem \
  uv run spikes/github-app/fq_bot.py --repo OWNER/fq-sandbox [--also-readme | --delete] [--no-auto-merge]
  uv run spikes/github-app/fq_bot.py --repo OWNER/fq-sandbox --merge PR [--expect-sha SHA]   # App-driven merge

Native auto-merge is kept for reproducing scenario 1: it does NOT apply the App's ruleset bypass.
"""
import argparse
import base64
import os
import re
import time
from pathlib import Path

import httpx
import jwt

API = "https://api.github.com"
TIMEOUT = httpx.Timeout(10.0)


def app_jwt(app_id: str, key_path: str) -> str:
    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + 540, "iss": app_id}
    return jwt.encode(payload, Path(key_path).expanduser().read_text(), algorithm="RS256")


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


def installation_token(repo: str, app_token: str) -> str:
    """Installation token scoped to this one repo and the two permissions the bot needs."""
    r = httpx.get(f"{API}/repos/{repo}/installation", headers=headers(app_token), timeout=TIMEOUT)
    r.raise_for_status()
    url = f"{API}/app/installations/{r.json()['id']}/access_tokens"
    scope = {"repositories": [repo.split("/", 1)[1]],
             "permissions": {"contents": "write", "pull_requests": "write"}}
    r = httpx.post(url, headers=headers(app_token), json=scope, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()["token"]


def put_file(c: httpx.Client, repo: str, path: str, branch: str, content: str) -> None:
    existing = c.get(f"/repos/{repo}/contents/{path}", params={"ref": branch})
    body = {"message": f"chore: update {path}", "branch": branch,
            "content": base64.b64encode(content.encode()).decode()}
    if existing.status_code == 200:
        body["sha"] = existing.json()["sha"]
    c.put(f"/repos/{repo}/contents/{path}", json=body).raise_for_status()


def delete_file(c: httpx.Client, repo: str, path: str, branch: str) -> None:
    existing = c.get(f"/repos/{repo}/contents/{path}", params={"ref": branch})
    existing.raise_for_status()
    body = {"message": f"chore: delete {path}", "branch": branch, "sha": existing.json()["sha"]}
    c.request("DELETE", f"/repos/{repo}/contents/{path}", json=body).raise_for_status()


def merge(repo: str, number: int, expect_sha: str | None = None) -> None:
    """App-driven merge (D39). M3 runs this from a sweep job; here it is called by hand.

    The bot verifies the PR itself before merging, because the required check runs workflow
    code from the PR head and anyone who can push to the branch could rewrite it (§9.5):
    bot author, same-repo branch, exactly quarantine.yaml added or modified, and (with
    --expect-sha) the head is the commit the bot pushed. The merge is pinned to that SHA.
    """
    app_token = app_jwt(os.environ["FQ_APP_ID"], os.environ["FQ_APP_KEY_PATH"])
    app = httpx.get(f"{API}/app", headers=headers(app_token), timeout=TIMEOUT)
    app.raise_for_status()
    bot_login = f"{app.json()['slug']}[bot]"
    token = installation_token(repo, app_token)
    with httpx.Client(base_url=API, headers=headers(token), timeout=TIMEOUT) as c:
        pr = c.get(f"/repos/{repo}/pulls/{number}")
        pr.raise_for_status()
        p = pr.json()
        head_sha = p["head"]["sha"]
        files = c.get(f"/repos/{repo}/pulls/{number}/files")
        files.raise_for_status()
        changed = [(f["filename"], f["status"]) for f in files.json()]
        problems = []
        if p["user"]["login"] != bot_login:
            problems.append(f"author is {p['user']['login']}, not {bot_login}")
        if p["head"]["repo"]["full_name"] != p["base"]["repo"]["full_name"]:
            problems.append("head branch is in another repo")
        if len(changed) != 1 or changed[0][0] != "quarantine.yaml" or changed[0][1] not in ("added", "modified"):
            problems.append(f"changes {changed}, not only quarantine.yaml added/modified")
        if expect_sha and head_sha != expect_sha:
            problems.append(f"head is {head_sha[:7]}, not the bot's commit {expect_sha[:7]}")
        if problems:
            print(f"merge #{number}: refused by the bot: " + "; ".join(problems))
            raise SystemExit(1)
        r = c.put(f"/repos/{repo}/pulls/{number}/merge", json={"merge_method": "squash", "sha": head_sha})
        print(f"merge #{number}: HTTP {r.status_code} {r.json().get('message')}")
        if r.status_code != 200:
            raise SystemExit(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--also-readme", action="store_true", help="scenario 2: touch README.md too")
    ap.add_argument("--delete", action="store_true",
                    help="scenario 4: delete quarantine.yaml so the check fails on a quarantine-only PR")
    ap.add_argument("--merge", type=int, metavar="PR",
                    help="App-driven merge: the bot verifies the PR, then squash-merges it (ruleset B still enforces the check)")
    ap.add_argument("--expect-sha", help="with --merge: refuse unless the PR head is this commit (the one the bot pushed)")
    ap.add_argument("--no-auto-merge", action="store_true", help="skip enablePullRequestAutoMerge")
    args = ap.parse_args()
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", args.repo):
        raise SystemExit("--repo must look like OWNER/NAME")

    if args.merge:
        merge(args.repo, args.merge, args.expect_sha)
        return

    token = installation_token(args.repo, app_jwt(os.environ["FQ_APP_ID"], os.environ["FQ_APP_KEY_PATH"]))
    with httpx.Client(base_url=API, headers=headers(token), timeout=TIMEOUT) as c:
        repo_info = c.get(f"/repos/{args.repo}")
        repo_info.raise_for_status()
        base = repo_info.json()["default_branch"]
        ref = c.get(f"/repos/{args.repo}/git/ref/heads/{base}")
        ref.raise_for_status()
        sha = ref.json()["object"]["sha"]
        branch = f"fq/quarantine-{int(time.time())}"
        c.post(f"/repos/{args.repo}/git/refs", json={"ref": f"refs/heads/{branch}", "sha": sha}).raise_for_status()

        if args.delete:
            delete_file(c, args.repo, "quarantine.yaml", branch)
        else:  # sandbox only: overwrites the whole file
            put_file(c, args.repo, "quarantine.yaml", branch, f"# updated {branch}\ntests: []\n")
        if args.also_readme:
            put_file(c, args.repo, "README.md", branch, f"# fq-sandbox\n{branch}\n")

        pr = c.post(f"/repos/{args.repo}/pulls", json={
            "title": f"chore: quarantine update {branch}", "head": branch, "base": base,
            "body": "M0-12 spike PR"})
        pr.raise_for_status()
        print("PR:", pr.json()["html_url"])
        print("head:", pr.json()["head"]["sha"])  # pass to --merge N --expect-sha

        if not args.no_auto_merge:
            q = ("mutation($id:ID!){enablePullRequestAutoMerge(input:{pullRequestId:$id,"
                 "mergeMethod:SQUASH}){pullRequest{autoMergeRequest{enabledAt}}}}")
            g = c.post("/graphql", json={"query": q, "variables": {"id": pr.json()["node_id"]}})
            g.raise_for_status()
            if g.json().get("errors"):  # GraphQL reports failures with HTTP 200
                raise SystemExit(f"auto-merge not enabled: {g.json()['errors']}")
            print("auto-merge:", g.json())


if __name__ == "__main__":
    main()
