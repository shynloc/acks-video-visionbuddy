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
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", args.skill_version):
        parser.error("Expected a three-part Skill version.")

    sys.path.insert(0, str(args.library.resolve(strict=True)))
    import serve

    version = args.skill_version
    url = f"https://github.com/shynloc/acks-video-visionbuddy/releases/tag/skill-v{version}"
    marker = "GitHub 仓库 ↗</a>".encode()

    class Handler(serve.Handler):
        def dispatch(self):
            page = serve.LIVE_PAGES.get(urlsplit(self.path).path)
            if page not in ("index.html", "visual/index.html"):
                return super().dispatch()
            css = ' class="act"' if page == "visual/index.html" else ""
            link = f' <a{css} href="{url}">下载 VisionBuddy Skill {version}</a>'.encode()
            body = serve.live_page(page).replace(marker, marker + link, 1)
            return self.response(body, "text/html; charset=utf-8")

    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        server.revisions = args.revisions
        server.serve_forever()


if __name__ == "__main__":
    main()
