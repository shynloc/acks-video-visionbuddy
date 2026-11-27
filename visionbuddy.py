"""Search, preview and export the offline VisionBuddy library."""

import argparse
from collections import Counter
from http.server import ThreadingHTTPServer
from importlib.util import find_spec
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from urllib.parse import parse_qs, urlsplit
import webbrowser

import serve
import skill_catalog as catalog

SKILL_VERSION = "1.3.0"
SCHEMA_VERSION = 1
SELECTION_SCRIPT = """
<script>
(() => {
  const code = new URLSearchParams(location.search).get('asset')
  const visual = location.pathname === '/visual/index.html'
  const search = document.getElementById(visual ? 'asset-search' : 'search')
  const select = () => {
    if (!search?.oninput) return false
    search.value = code
    search.dispatchEvent(new Event('input'))
    if (visual) {
      const card = [...document.querySelectorAll('#grid [data-asset-id]')]
        .find(el => el.dataset.assetId === code.split('@')[0])
      card?.click()
    }
    return true
  }
  if (!select()) {
    const observer = new MutationObserver(() => { if (select()) observer.disconnect() })
    observer.observe(document.getElementById('filters'), {childList:true})
  }
})()
</script>
"""


class LocalGallery(serve.Handler):
    def dispatch(self):
        url = urlsplit(self.path)
        if url.path.startswith(("/my-assets", "/api/personal/")):
            import personal_web

            if personal_web.get(self, url.path, url.query):
                return
        if url.path.startswith(("/desk", "/api/desk/")):
            import desk_server

            if desk_server.get(self, url.path):
                return
        if url.path in ("/index.html", "/visual/index.html"):
            script = ""
            query = parse_qs(url.query, max_num_fields=12)
            if "asset" in query:
                asset = catalog.lookup(query["asset"][0])
                if url.path + "?" + url.query == catalog.browser_path(*asset):
                    script = SELECTION_SCRIPT
            visual = url.path == "/visual/index.html"
            if visual or script:
                html = serve.live_page(serve.LIVE_PAGES[url.path]).decode("utf8")
                if visual and "inline" not in query:
                    html = html.replace("</header>", ('<a class="act" href="/desk/">给口播配画面</a>'
                                                     '<a class="act" href="/my-assets/">我的素材</a></header>'), 1)
                head, tail = html.rsplit("</html>", 1)
                return self.response((head + script + "</html>" + tail).encode("utf8"),
                                     "text/html; charset=utf-8")
        return super().dispatch()

    def do_POST(self):
        if urlsplit(self.path).path.startswith("/api/personal/"):
            import personal_web
            return personal_web.post(self)
        import desk_server
        return desk_server.post(self)



def metadata():
    return {
        "schemaVersion": SCHEMA_VERSION,
        "skillVersion": SKILL_VERSION,
        "libraryRelease": serve.VERSION,
    }


def emit(data):
    print(json.dumps({**metadata(), **data}, ensure_ascii=False), flush=True)


def options(parser):
    parser.add_argument("--demo", help="KIT 内所选 DEMO 编号")
    parser.add_argument("--palette", help="配色编号，如 PAL-015")
    parser.add_argument("--object", help="圈出部位时使用的物件编号")
    parser.add_argument("--sticker", help="贴纸或图标编号，none 表示移除")
    parser.add_argument("--label", action="append", default=[], help="按顺序改字，可重复")
    parser.add_argument("--seconds", type=int, choices=range(1, 13), default=3, metavar="1-12")
    parser.add_argument("--quote", help="口播原句，可用于部位读数和工作台素材包")


def parser():
    cli = argparse.ArgumentParser(description=__doc__)
    commands = cli.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="版本、素材类别和可选工具")
    find = commands.add_parser("find", help="按名称、用途、中文短句或编号查素材")
    find.add_argument("query")
    find.add_argument("--kind", choices=(*catalog.GROUPS, "personal"))
    find.add_argument("--limit", type=int, default=8, metavar="1-279")
    for name, help_text in (("show", "读取素材详情"), ("license", "查素材授权记录")):
        detail = commands.add_parser(name, help=help_text)
        detail.add_argument("asset")
    proof = commands.add_parser("preview", help="得到本机浏览器地址或生成可编辑试看 HTML")
    proof.add_argument("asset")
    proof.add_argument("--port", type=int, default=8772)
    proof.add_argument("--output", type=Path, help="保存搭配或演示 HTML")
    options(proof)
    export = commands.add_parser("export", help="保存可编辑源件和可选的透明 PNG 或 MOV")
    export.add_argument("asset")
    export.add_argument("--output", type=Path, required=True, help="输出 ZIP 路径")
    export.add_argument("--media", choices=("source", "png", "mov"), default="source")
    options(export)
    server = commands.add_parser("serve", help="启动离线素材册")
    server.add_argument("--port", type=int, default=8772, help="0 为选择可用端口")
    entry = server.add_mutually_exclusive_group()
    entry.add_argument("--asset", help="打开指定素材")
    entry.add_argument("--desk", action="store_true", help="进入口播稿、SRT 或视频配画面")
    entry.add_argument("--mine", action="store_true", help="打开我的素材")
    plan = commands.add_parser("plan", help="从口播稿、SRT 或视频生成逐句推荐")
    plan.add_argument("--script", type=Path)
    plan.add_argument("--srt", type=Path)
    plan.add_argument("--video", type=Path)
    plan.add_argument("--model", help="已有本机 Whisper 模型，如 medium")
    plan.add_argument("--language", default="auto", choices=("auto", "zh", "en"))
    plan.add_argument("--output", type=Path, help="保存审核方案 JSON")
    planned_preview = commands.add_parser("plan-preview", help="保存指定原句的一款试看 HTML")
    planned_preview.add_argument("plan", type=Path)
    planned_preview.add_argument("--row", required=True)
    planned_preview.add_argument("--choice", type=int, default=0)
    planned_preview.add_argument("--output", type=Path, required=True)
    batch = commands.add_parser("plan-export", help="批量导出审核采用的素材")
    batch.add_argument("plan", type=Path)
    batch.add_argument("--review", type=Path, help="按原句编号索引的审核选择 JSON")
    batch.add_argument("--output", type=Path, required=True)
    batch.add_argument("--media", choices=("mov", "png", "source"), default="mov")
    server.add_argument("--open", action="store_true", help="打开默认浏览器")
    save = commands.add_parser("project-save", help="保存可跨机恢复的审核工程 ZIP")
    save.add_argument("project", type=Path)
    save.add_argument("--review", type=Path)
    save.add_argument("--output", type=Path, required=True)
    load = commands.add_parser("project-open", help="恢复审核工程 ZIP 及引用的个人素材")
    load.add_argument("project", type=Path)
    load.add_argument("--output", type=Path)
    from personal_cli import register_commands

    register_commands(commands)
    return cli


def run(args):
    from personal_cli import browser_path, for_asset, run as run_personal, summary
    import personal_store as own

    command = args.command
    if command.startswith("my-"):
        return run_personal(args)
    if command == "status":
        counts = Counter(group for group, _ in catalog.assets())
        return {
            "assets": sum(counts.values()), "groups": counts, "personalAssets": len(own.list_heads()),
            "compatibility": json.loads((catalog.ROOT / "compatibility.json").read_bytes()),
            "optional": {
                "pillow": find_spec("PIL") is not None,
                "playwright": find_spec("playwright") is not None,
                "ffmpeg": shutil.which("ffmpeg") is not None,
            },
        }
    if command == "find":
        total = sum(len(rows) for rows in catalog.groups().values()) + len(own.list_heads())
        if not 1 <= args.limit <= total:
            raise ValueError(f"结果数量应为 1 到 {total}。")
        if not args.query.strip():
            raise ValueError("请输入名称、用途或素材编号。")
        if own.CODE.fullmatch(args.query.strip()):
            rows = [summary(own.get(args.query))] if args.kind in (None, "personal") else []
        else:
            ids = [summary(item) for _, _, item in own.search(args.query)] if args.kind in (None, "personal") else []
            hits = catalog.find(args.query, args.kind, args.limit) if args.kind != "personal" else []
            rows = [*ids, *hits][:args.limit]
        return {"query": args.query, "matches": rows}
    if command == "serve":
        path = "/desk/" if args.desk else "/my-assets/" if args.mine else "/visual/index.html"
        if args.asset:
            path = browser_path(own.get(args.asset)) if own.CODE.fullmatch(args.asset.strip()) else catalog.browser_path(*catalog.lookup(args.asset))
        with ThreadingHTTPServer(("127.0.0.1", args.port), LocalGallery) as server:
            server.revisions = None
            url = f"http://127.0.0.1:{server.server_port}" + path
            emit({"url": url, "port": server.server_port})
            if args.open:
                opener = threading.Timer(0.3, webbrowser.open, (url,))
                opener.daemon = True
                opener.start()
            server.serve_forever()
        return None

    if command in ("plan", "plan-preview", "plan-export", "project-save", "project-open"):
        from desk_cli import run as run_desk
        return run_desk(args)
    if own.CODE.fullmatch(args.asset.strip()):
        return for_asset(args, serve.VERSION)
    group, row, variant = catalog.lookup(args.asset)
    if command == "show":
        return {"asset": catalog.detail(group, row, variant)}
    if command == "license":
        selected = [row]
        if group == "practice":
            selected.extend(catalog.lookup(key, "stickers")[1] for key in row["stickers"])
        return {"assetId": row["assetId"],
                "licenses": {item["assetId"]: catalog.rights(item) for item in selected}}
    if command == "preview":
        if args.output is None:
            if any((args.demo, args.palette, args.object, args.sticker is not None, args.label, args.quote,
                    args.seconds != 3)):
                raise ValueError("自定义试看请指定 --output 文件.html。")
            return {
                "assetId": row["assetId"],
                "url": f"http://127.0.0.1:{args.port}" + catalog.browser_path(group, row, variant),
            }
        if group not in ("demos", "practice") or args.output.suffix.lower() != ".html":
            raise ValueError("可编辑试看需要口播搭配或演示编号以及 .html 输出路径。")
        html, demo, labels, visual = catalog.scene(group, row, args)
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf8", newline="\n") as file:
            file.write(html)
        return {
            "assetId": row["assetId"], "output": str(output), "url": output.as_uri(),
            "annotation": catalog.annotation(visual, demo, labels, args.seconds),
        }

    from skill_render import export
    return export(group, row, variant, args, serve.VERSION)


def main():
    sys.stdout.reconfigure(encoding="utf8")
    args = parser().parse_args()
    try:
        result = run(args)
        if result is not None:
            emit(result)
        return 0
    except KeyboardInterrupt:
        return 0 if args.command == "serve" else 130
    except (OSError, ValueError, RuntimeError, OverflowError, subprocess.TimeoutExpired) as exc:
        emit({"error": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
