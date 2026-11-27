"""Loopback UI endpoints for the personal materials library."""

import base64
import binascii
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, quote, urlsplit

import desk_server as http
import personal_render as render
import personal_store as store
from personal_media import IMPORT_LIMIT, TYPES, WEB_LIMIT
from skill_catalog import ROOT

PAGES = {"/my-assets": ("my-assets.html", "text/html"), "/my-assets/": ("my-assets.html", "text/html"),
         "/my-assets/app.js": ("my-assets.js", "text/javascript"),
         "/my-assets/style.css": ("my-assets.css", "text/css")}
API = "/api/personal/"


def local_request(handler, write=False):
    return http.same_origin(handler, write) and handler.headers.get("Sec-Fetch-Site") in (None, "none", "same-origin")


def download(handler, item):
    path = store.original_path(item)
    handler.send_response(200)
    handler.send_header("Content-Type", "application/octet-stream")
    handler.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(item["originalName"]))
    handler.send_header("Content-Length", str(path.stat().st_size))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Cross-Origin-Resource-Policy", "same-origin")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.end_headers()
    if handler.command != "HEAD":
        with path.open("rb") as body:
            shutil.copyfileobj(body, handler.wfile)


def get(handler, path, query):
    if path not in PAGES and not path.startswith(API):
        return False
    if not local_request(handler):
        http.json_response(handler, {"error": "请从本机 VisionBuddy 打开「我的素材」。"}, 403)
        return True
    try:
        if path in PAGES:
            filename, mime = PAGES[path]
            http.response(handler, (ROOT / "desk" / filename).read_bytes(), mime)
            return True
        params = parse_qs(query, max_num_fields=3)
        action = path.removeprefix(API)
        code = params.get("ref", [""])[0]
        if action == "library":
            q = params.get("q", [""])[0]
            matches = store.search(q) if q else [(0, "", item) for item in store.list_heads()]
            http.json_response(handler, {"items": [render.public_record(record) for _, _, record in matches]})
        elif action == "versions":
            http.json_response(handler, {"versions": [render.public_record(record) for record in store.revisions(code)]})
        elif action in ("preview", "thumb", "original"):
            item = store.get(code)
            if action == "preview":
                http.response(handler, render.scene_html(item, True).encode("utf8"), "text/html")
            elif action == "thumb":
                http.response(handler, (store.asset_dir(item) / "preview.webp").read_bytes(), "image/webp")
            else:
                download(handler, item)
        else:
            handler.send_error(404)
    except (BrokenPipeError, ConnectionResetError):
        pass
    except (OSError, ValueError, RuntimeError) as exc:
        http.json_response(handler, {"error": str(exc)}, 400)
    return True


def upload(handler):
    if handler.headers.get_content_type() != "application/octet-stream":
        raise ValueError("请选择要导入的本机原件。")
    raw = handler.headers.get("X-VisionBuddy-Metadata", "")
    if not raw or len(raw) > 14_000:
        raise ValueError("素材登记信息过长。")
    try:
        options = json.loads(base64.b64decode(raw, validate=True))
    except (binascii.Error, ValueError) as exc:
        raise ValueError("无法读取素材登记内容。") from exc
    if not isinstance(options, dict):
        raise ValueError("素材登记信息无效。")
    filename = store.text(options, "filename", 260, required=True)
    suffix = Path(filename).suffix.lower()
    kind = TYPES.get(suffix)
    if kind is None:
        raise ValueError("请选择 PNG、SVG、透明视频或单文件 HTML。")
    size = http.read_request(handler, WEB_LIMIT if kind in ("svg", "html") else IMPORT_LIMIT)
    with TemporaryDirectory(prefix="visionbuddy-upload-") as scratch:
        staged = Path(scratch) / ("original" + suffix)
        with staged.open("wb") as file:
            while size:
                chunk = handler.rfile.read(min(size, 1024**2))
                if not chunk:
                    raise ValueError("读取原件中断，请重新导入。")
                size -= len(chunk)
                file.write(chunk)
        return store.save(options, staged, filename, options.get("ref"))


def post(handler):
    action = urlsplit(handler.path).path.removeprefix(API)
    if action not in ("import", "edit", "share", "receive"):
        return handler.send_error(404)
    if not local_request(handler, write=True):
        return http.json_response(handler, {"error": "请从本机 VisionBuddy 提交素材。"}, 403)
    handler.connection.settimeout(75)
    locked = action != "edit"
    if locked and not http.LONG_JOB.acquire(blocking=False):
        return http.json_response(handler, {"error": "本机有素材任务正在运行，请稍后重试。"}, 409)
    try:
        if action in ("share", "receive"):
            from portable_bundle import TEAM, restore, save_team

            with TemporaryDirectory(prefix="visionbuddy-personal-transfer-") as folder:
                archive = Path(folder) / "share.zip"
                if action == "share":
                    save_team(http.read_json(handler).get("refs"), archive)
                    return http.send_bundle(handler, archive, "VisionBuddy-个人素材分享包.zip")
                with archive.open("w+b") as file:
                    http.receive_bundle(handler, file)
                    return http.json_response(handler, restore(file, TEAM), 201)
        if action == "import":
            record = upload(handler)
        else:
            data = http.read_json(handler)
            record = store.save(data, code=data.get("ref"))
        http.json_response(handler, {"item": render.public_record(record)}, 201)
    except (BrokenPipeError, ConnectionResetError):
        pass
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        http.json_response(handler, {"error": str(exc)}, 400)
    finally:
        if locked:
            http.LONG_JOB.release()
