"""Public web review using only published library assets."""

import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from threading import BoundedSemaphore
from urllib.parse import urlsplit
from zipfile import BadZipFile, ZipFile

import desk_plan as planner
import desk_server as http
from portable_bundle import MANIFEST, PROJECT, PROJECT_FILE, read_struct, save_project, validate_project_shape


DESK = Path(__file__).resolve().parent / "desk"
PERSONAL_PAGES = {
    "/my-assets": ("my-assets.html", "text/html"),
    "/my-assets/": ("my-assets.html", "text/html"),
    "/my-assets/app.js": ("my-assets.js", "text/javascript"),
    "/my-assets/browser.js": ("browser-assets.js", "text/javascript"),
    "/my-assets/style.css": ("my-assets.css", "text/css"),
}
POSTS = {"plan", "preview", "save-project", "open-project", "export"}
CAPACITY = BoundedSemaphore(4)
INPUT_LIMIT = 2 * 1024**2
EXPORT_LIMIT = 15


def same_site(handler, write=False):
    base = handler.server.web_origin
    return (handler.headers.get("Host") == urlsplit(base).netloc
            and (not write or handler.headers.get("Origin") == base))


def page():
    html = (DESK / "index.html").read_text(encoding="utf8")
    html = html.replace("<body>", '<body data-online="true">', 1)
    html = html.replace('id="plan-button" type="submit"', 'id="plan-button" type="submit" disabled', 1)
    html = html.replace("从原句找到值得配图的地方，试看后把采用的画面一起带走。",
                        "稿件和字幕由网站生成画面建议。配套原片在浏览器中播放。", 1)
    html = html.replace("配套 SRT <span class=\"note\">可选</span>", "配套 SRT", 1)
    html = html.replace("优先使用配套 SRT。只有视频时，可用已安装的 Whisper 模型本机转写。",
                        "选择视频和配套 SRT 后，可以在原片上逐句试看。", 1)
    html = re.sub(r'<option value="(?:mov|png)">[^<]*</option>', "", html)
    return html.encode("utf8")


def personal_page():
    html = (DESK / "my-assets.html").read_text(encoding="utf8")
    return (html
            .replace("<body>", '<body data-browser-assets="true">', 1)
            .replace('  <script src="/my-assets/app.js"', '  <script src="/my-assets/browser.js" defer></script>\n'
                     '  <script src="/my-assets/app.js"', 1)
            .replace("给本机原件登记用途。给口播配画面时，个人素材会和公共库一起参与推荐。",
                     "原件和版本记录保存在当前浏览器。", 1)
            .replace("导入本机素材", "导入素材", 1)
            .replace("推荐关键词", "关键词", 1)
            .replace("支持 PNG、SVG、带 Alpha 的视频和可离线打开的单文件 HTML。",
                     "支持 PNG、SVG、浏览器可播放的视频，以及单文件 HTML／CSS 预览。", 1)
            .replace("本机素材库", "浏览器素材库", 1)
            .replace("本机素材和预览", "浏览器素材和预览", 1)
            .replace("正在读取本机素材…", "正在读取浏览器素材…", 1)
            .replace('class="actions sharing"', 'class="actions sharing" hidden', 1)
            .replace('sandbox="allow-scripts"', 'sandbox=""', 1)
            .replace('class="primary" id="save-asset"', 'class="primary" id="save-asset" disabled', 1)
            .encode("utf8"))


def get(handler, path):
    entry = http.ASSETS.get(path) or PERSONAL_PAGES.get(path)
    if not entry:
        return False
    if not same_site(handler):
        http.json_response(handler, {"error": "请从 VisionBuddy 在线素材册打开。"}, 403)
    else:
        filename, mime = entry
        content = page() if filename == "index.html" else (
            personal_page() if filename == "my-assets.html" else (DESK / filename).read_bytes())
        http.response(handler, content, mime)
    return True


def open_project(raw):
    try:
        with ZipFile(BytesIO(raw)) as archive:
            names = archive.namelist()
            if len(names) > 400 or len(names) != len(set(names)):
                raise ValueError("审核工程包文件数量无效。")
            manifest = read_struct(archive, MANIFEST)
            if not isinstance(manifest, dict) or manifest.get("format") != PROJECT:
                raise ValueError("请选择 VisionBuddy 审核工程 ZIP。")
            if manifest.get("records") != [] or manifest.get("blobs") != {}:
                raise ValueError("带有个人素材的审核工程请在本机 VisionBuddy 打开。")
            entry = archive.getinfo(PROJECT_FILE)
            if entry.file_size > INPUT_LIMIT:
                raise ValueError("审核工程清单过大。")
            body = archive.read(entry)
            if hashlib.sha256(body).hexdigest() != manifest.get("projectSha256"):
                raise ValueError("审核工程校验失败。")
            project = json.loads(body)
    except (BadZipFile, KeyError, UnicodeError) as exc:
        raise ValueError("找不到完整的 VisionBuddy 审核工程包。") from exc
    validate_project_shape(project)
    plan = planner.build(project["source"], public_only=True)
    planner.review_choices(plan, project["decisions"])
    return {"project": project, "plan": plan}


def post(handler):
    parsed = urlsplit(handler.path)
    path = parsed.path.removeprefix("/api/desk/")
    if parsed.path != "/api/desk/" + path or path not in POSTS:
        return handler.send_error(404)
    if not same_site(handler, write=True):
        return http.json_response(handler, {"error": "请从 VisionBuddy 在线页面提交。"}, 403)
    if not CAPACITY.acquire(blocking=False):
        return http.json_response(handler, {"error": "当前任务较多，请稍后重试。"}, 503)
    handler.connection.settimeout(12)
    try:
        size = http.read_request(handler, INPUT_LIMIT)
        if path == "open-project":
            if handler.headers.get_content_type() != "application/octet-stream":
                raise ValueError("请选择审核工程 ZIP。")
            raw = handler.rfile.read(size)
            if len(raw) != size:
                raise ValueError("审核工程读取中断。")
            return http.json_response(handler, open_project(raw))
        data = http.read_json(handler)
        plan = planner.build(data.get("source"), fresh=path == "plan" and data.get("fresh") is True, public_only=True)
        if path == "plan":
            return http.json_response(handler, plan)
        if path == "preview":
            from desk_render import preview_html
            row, candidate = planner.candidate_at(plan, data.get("row"), data.get("choice", 0))
            return http.response(handler, preview_html(row, candidate).encode("utf8"), "text/html")
        approved, _ = planner.review_choices(plan, data.get("decisions", {}))
        if len(approved) > EXPORT_LIMIT:
            raise ValueError(f"一次最多打包 {EXPORT_LIMIT} 条画面，请按口播段落分批导出。")
        with TemporaryDirectory(prefix="visionbuddy-public-") as folder:
            target = Path(folder) / "review.zip"
            if path == "save-project":
                save_project(plan, data, target)
                return http.send_bundle(handler, target, "VisionBuddy-审核工程.zip")
            if data.get("media") != "source":
                raise ValueError("在线版支持导出可编辑源件。请在独立 Skill 中生成 PNG 或 MOV。")
            from desk_render import export
            export(plan, data.get("decisions", {}), target, "source", state=data)
            return http.send_bundle(handler, target, "VisionBuddy-口播素材包.zip")
    except (BrokenPipeError, ConnectionResetError, TimeoutError):
        pass
    except (ValueError, TypeError) as exc:
        http.json_response(handler, {"error": str(exc)}, 400)
    except (OSError, RuntimeError):
        http.json_response(handler, {"error": "处理失败，请稍后重试。"}, 500)
    finally:
        CAPACITY.release()
