"""M0-12 spike: create the fq-bot GitHub App from a manifest (one click in the browser).

  python3 spikes/github-app/create_app.py [--name fq-bot-dev] [--port 8765]

Opens a local page that posts the manifest to GitHub. After you click
"Create GitHub App", GitHub redirects back here with a one-time code, which is
exchanged for the App id and private key. The key is written to
~/.secrets/<slug>.pem (mode 600) and never printed. Stdlib only.
"""
import argparse
import html
import json
import os
import secrets
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PERMISSIONS = {"contents": "write", "pull_requests": "write", "metadata": "read", "checks": "read"}
EVENTS = ["pull_request", "push", "check_suite"]


def manifest(name: str, port: int) -> dict[str, object]:
    return {
        "name": name,
        "url": "https://github.com/IrynaShkvirko/quarantine-tests",
        "public": False,  # installable only on the owner's account
        # Webhooks stay disabled in the spike; a real deployment sets a URL and a secret (§13).
        "hook_attributes": {"url": "https://example.invalid/webhooks/github", "active": False},
        "redirect_url": f"http://localhost:{port}/callback",
        "default_permissions": PERMISSIONS,
        "default_events": EVENTS,
    }


def convert(code: str) -> dict[str, object]:
    req = urllib.request.Request(
        f"https://api.github.com/app-manifests/{code}/conversions",
        method="POST",
        headers={"Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 (fixed https URL)
        return json.load(resp)  # type: ignore[no-any-return]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="fq-bot-dev")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    state = secrets.token_urlsafe(16)
    body = json.dumps(manifest(args.name, args.port))
    done: dict[str, object] = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_: object) -> None:  # keep the one-time code out of the terminal
            pass

        def reply(self, text: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(text.encode())

        def do_GET(self) -> None:
            # Reject DNS-rebinding requests: only our own origin may read the state.
            if self.headers.get("Host") not in (f"localhost:{args.port}", f"127.0.0.1:{args.port}"):
                self.send_error(403)
                return
            url = urlparse(self.path)
            if url.path == "/":
                self.reply(
                    f'<form id="f" method="post" action="https://github.com/settings/apps/new?state={state}">'
                    f'<input type="hidden" name="manifest" value="{html.escape(body)}">'
                    "<button>Continue to GitHub</button></form>"
                    "<script>document.getElementById('f').submit()</script>"
                )
                return
            q = parse_qs(url.query)
            if url.path != "/callback" or q.get("state") != [state] or "code" not in q:
                self.send_error(400)
                return
            app = convert(q["code"][0])
            key = Path.home() / ".secrets" / f"{app['slug']}.pem"
            key.parent.mkdir(mode=0o700, exist_ok=True)
            key.parent.chmod(0o700)
            fd = os.open(key, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            os.fchmod(fd, 0o600)  # the mode argument is ignored when the file already exists
            with os.fdopen(fd, "w") as f:
                f.write(str(app["pem"]))
            done.update(id=app["id"], slug=app["slug"], key=str(key))
            self.reply(f"<p>App <b>{html.escape(str(app['slug']))}</b> created. You can close this tab.</p>")

    server = HTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Opening http://localhost:{args.port}/ — click 'Create GitHub App' on GitHub.")
    webbrowser.open(f"http://localhost:{args.port}/")
    while not done:
        server.handle_request()
    print(f"FQ_APP_ID={done['id']}")
    print(f"FQ_APP_KEY_PATH={done['key']}")
    print(f"Install it on the sandbox repo only: https://github.com/apps/{done['slug']}/installations/new")


if __name__ == "__main__":
    main()
