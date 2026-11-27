"""Add the published Skill download to the live pages of the active online library."""

import argparse
from http.server import ThreadingHTTPServer
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--revisions", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18772)
    parser.add_argument("--skill-version", required=True)
    parser.add_argument("--desk-root", type=Path)
    parser.add_argument("--web-origin")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", args.skill_version):
        parser.error("Expected a three-part Skill version.")

    sys.path.insert(0, str(args.library.resolve(strict=True)))
    import serve

    desk = None
    if args.desk_root:
        if not args.web_origin or not urlsplit(args.web_origin).netloc:
            parser.error("--desk-root requires --web-origin")
        sys.path.insert(1, str(args.desk_root.resolve(strict=True)))
        import public_desk as desk

    version = args.skill_version
    url = f"https://github.com/shynloc/acks-video-visionbuddy/releases/tag/skill-v{version}"
    marker = "GitHub 仓库 ↗</a>".encode()

    class Handler(serve.Handler):
        def dispatch(self):
            path = urlsplit(self.path).path
            if desk and desk.get(self, path):
                return
            page = serve.LIVE_PAGES.get(path)
            if page not in ("index.html", "visual/index.html"):
                return super().dispatch()
            css = ' class="act"' if page == "visual/index.html" else ""
            link = f' <a{css} href="{url}">下载 VisionBuddy Skill {version}</a>'.encode()
            if desk:
                link += f' <a{css} href="/desk/">给口播配画面</a>'.encode()
            body = serve.live_page(page).replace(marker, marker + link, 1)
            return self.response(body, "text/html; charset=utf-8")

        def do_POST(self):
            if not desk:
                return self.send_error(404)
            return desk.post(self)

    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        server.revisions = args.revisions
        server.web_origin = args.web_origin
        server.serve_forever()


if __name__ == "__main__":
    main()
