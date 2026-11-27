"""Serve the standalone gallery and the versioned public library."""
import argparse
from functools import lru_cache
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, unquote, urlsplit

import preview

ROOT = Path(__file__).resolve().parent
VERSION = (ROOT / "VERSION").read_text(encoding="utf8").strip()
REPO = "https://github.com/shynloc/acks-video-visionbuddy"
LIVE_PAGES = {"/": "index.html", "/index.html": "index.html",
              "/demos.html": "demos.html", "/visual/index.html": "visual/index.html"}
LOCAL_INCLUDE = re.compile(r'((?:src|href)=")([\w.-]+\.(?:css|js))(")')


@lru_cache(maxsize=256)
def png(recipe):
    return preview.overlay_png(preview.brief(dict(recipe)))


@lru_cache(maxsize=16)
def manifest_at(root):
    bundled = root / "manifest.json"
    if bundled.is_file() or root != ROOT:
        raw = bundled.read_bytes()
    else:
        from tools.release import manifest_bytes
        raw = manifest_bytes()
    return raw, json.loads(raw)["files"]


def live_page(page):
    path = ROOT / "site" / page
    source = path.read_text(encoding="utf8")
    parent = str(Path(page).parent.as_posix())
    directory = "" if parent == "." else parent + "/"
    release = f"/releases/{VERSION}/site/{directory}"

    def pin(match):
        name = match[2]
        url = f"/bootstrap/{VERSION}.js" if page == "index.html" and name == "boot.js" else release + name
        return match[1] + url + match[3]

    return LOCAL_INCLUDE.sub(pin, source).encode()


def live_bootstrap():
    source = (ROOT / "site/boot.js").read_text(encoding="utf8")
    return re.sub(
        r"'(catalog\.json|renderer\.js|illustrations\.js|gallery\.js)'",
        lambda match: f"'/releases/{VERSION}/site/{match[1]}'",
        source,
    ).encode()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "site"), **kwargs)

    def list_directory(self, path):
        self.send_error(404)
        return None

    def response(self, body, mime, cache="no-cache"):
        etag = '"' + hashlib.sha256(body).hexdigest() + '"'
        unchanged = self.headers.get("If-None-Match") == etag
        self.send_response(304 if unchanged else 200)
        self.send_header("Content-Type", mime)
        self.send_header("Cache-Control", cache)
        self.send_header("ETag", etag)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(0 if unchanged else len(body)))
        self.end_headers()
        if not unchanged and self.command == "GET":
            self.wfile.write(body)

    def dispatch(self):
        url = urlsplit(self.path)
        path = url.path
        if path == "/healthz":
            return self.response(b"ok\n", "text/plain")
        if path == "/latest.json":
            data = {
                "libraryRelease": VERSION,
                "manifest": f"/releases/{VERSION}/manifest.json",
                "archive": f"{REPO}/releases/download/v{VERSION}/visionbuddy-v{VERSION}.zip",
            }
            return self.response(json.dumps(data).encode(), "application/json")
        if path in LIVE_PAGES:
            return self.response(live_page(LIVE_PAGES[path]), "text/html; charset=utf-8")
        if path == f"/bootstrap/{VERSION}.js":
            return self.response(live_bootstrap(), "text/javascript; charset=utf-8")
        if path.startswith("/releases/"):
            version, sep, name = unquote(path.removeprefix("/releases/")).partition("/")
            if not sep or not re.fullmatch(r"\d+\.\d+\.\d+", version):
                return self.send_error(404)
            try:
                if version == VERSION:
                    root = ROOT
                else:
                    revisions = self.server.revisions
                    if revisions is None:
                        return self.send_error(404)
                    root = revisions / version
                raw, files = manifest_at(root)
                if name == "manifest.json":
                    return self.response(raw, "application/json", "public, max-age=31536000, immutable")
                if name not in files:
                    return self.send_error(404)
                asset = root / name
                return self.response(asset.read_bytes(), self.guess_type(asset), "public, max-age=31536000, immutable")
            except FileNotFoundError:
                return self.send_error(404)
        if path == "/api/motion/library-preview":
            params = parse_qs(url.query, max_num_fields=8)
            chosen = preview.selection({k: values[0] for k, values in params.items()})
            recipe = tuple(sorted(chosen.items()))
            return self.response(png(recipe), "image/png", "public, max-age=3600")
        if path == "/api/visionbuddy/demo":
            code = parse_qs(url.query, max_num_fields=3).get("asset", [""])[0]
            return self.response(preview.demo_html(code).encode(), "text/html; charset=utf-8")
        if self.command == "HEAD":
            return super().do_HEAD()
        return super().do_GET()

    def do_GET(self):
        try:
            self.dispatch()
        except (ValueError, KeyError):
            self.send_error(404, "Unknown library selection")
        except (BrokenPipeError, ConnectionResetError):
            pass

    do_HEAD = do_GET


def make_server(host, port, revisions=None):
    server = ThreadingHTTPServer((host, port), Handler)
    server.revisions = revisions
    return server


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--host", default="127.0.0.1")
    cli.add_argument("--port", default=8772, type=int)
    cli.add_argument("--revisions", type=Path)
    args = cli.parse_args()
    with make_server(args.host, args.port, args.revisions) as server:
        print(f"http://{args.host}:{server.server_port}", flush=True)
        server.serve_forever()
