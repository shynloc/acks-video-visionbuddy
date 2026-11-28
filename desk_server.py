"""Serve the standalone review desk over the local Skill server."""

import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from threading import Lock
from urllib.parse import parse_qs, quote, urlsplit

import desk_inputs as inputs
import desk_plan as planner
from skill_catalog import ROOT

ASSETS = {"/desk": ("index.html", "text/html"), "/desk/": ("index.html", "text/html"),
          "/desk/style.css": ("style.css", "text/css"), "/desk/app.js": ("app.js", "text/javascript")}
JSON_LIMIT = 3 * 1024 ** 2
LONG_JOB = Lock()


def response(handler, data, content_type, status=200):
    body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode("utf8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type + "; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Referrer-Policy", "no-referrer")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Cross-Origin-Resource-Policy", "same-origin")
    handler.end_headers()
    if handler.command != "HEAD":
        handler.wfile.write(body)


def json_response(handler, data, status=200):
    response(handler, data, "application/json", status)


def same_origin(handler, write=False):
    port = handler.server.server_port
    host = handler.headers.get("Host")
    if host not in (f"127.0.0.1:{port}", f"localhost:{port}"):
        return False
    return not write or handler.headers.get("Origin") == "http://" + host


def get(handler, path):
    if path not in ASSETS and path != "/api/desk/capabilities":
        return False
    if not same_origin(handler):
        json_response(handler, {"error": "请从本机 VisionBuddy 地址打开配画面。"}, 403)
    elif path == "/api/desk/capabilities":
        json_response(handler, {"models": inputs.available_models(), "videoLimit": inputs.VIDEO_LIMIT})
    else:
        name, mime = ASSETS[path]
        response(handler, (ROOT / "desk" / name).read_bytes(), mime)
    return True


def read_request(handler, limit):
    size = int(handler.headers.get("Content-Length", "0"))
    if not 0 < size <= limit:
        raise ValueError("文件为空或超过支持大小。")
    return size


def read_json(handler):
    if handler.headers.get_content_type() != "application/json":
        raise ValueError("请提供审核稿或 JSON 数据。")
    size = read_request(handler, JSON_LIMIT)
    raw = handler.rfile.read(size)
    if len(raw) != size:
        raise ValueError("提交中断，请重试。")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("提交的数据格式无效。")
    return data


def transcribe_upload(handler, query):
    if handler.headers.get_content_type() != "application/octet-stream":
        raise ValueError("请选择需要转写的本机视频。")
    model = query.get("model", [""])[0]
    language = query.get("language", ["auto"])[0]
    if model not in inputs.available_models():
        raise ValueError("所选本机模型不可用。请选择已有模型或导入 SRT。")
    size = read_request(handler, inputs.VIDEO_LIMIT)
    with TemporaryDirectory(prefix="visionbuddy-video-") as folder:
        video = Path(folder) / "source-media"
        with video.open("wb") as file:
            while size:
                data = handler.rfile.read(min(size, 1024**2))
                if not data:
                    raise ValueError("视频读取中断，请重试。")
                size -= len(data)
                file.write(data)
        source = inputs.transcribe(video, model, language)
        if "composition" in query:
            source["composition"] = query["composition"][0]
        return planner.build(source, fresh=True)


def receive_bundle(handler, archive):
    from portable_bundle import LIMIT

    if handler.headers.get_content_type() != "application/octet-stream":
        raise ValueError("请选择本机 ZIP 文件。")
    remaining = read_request(handler, LIMIT)
    while remaining:
        chunk = handler.rfile.read(min(remaining, 1024**2))
        if not chunk:
            raise ValueError("便携包读取中断。")
        archive.write(chunk)
        remaining -= len(chunk)
    archive.seek(0)


def send_bundle(handler, path, name):
    handler.send_response(200)
    handler.send_header("Content-Type", "application/zip")
    handler.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(name))
    handler.send_header("Content-Length", str(path.stat().st_size))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    with path.open("rb") as file:
        shutil.copyfileobj(file, handler.wfile)


def export_response(handler, data, draft=False):
    from desk_render import export
    from portable_bundle import save_project

    plan = planner.build(data.get("source"))
    with TemporaryDirectory(prefix="visionbuddy-download-") as folder:
        path = Path(folder) / "material.zip"
        if draft:
            save_project(plan, data, path)
        else:
            export(plan, data.get("decisions", {}), path, data.get("media", "mov"), state=data)
        send_bundle(handler, path, "VisionBuddy-审核工程.zip" if draft else "VisionBuddy-口播素材包.zip")


def post(handler):
    parsed = urlsplit(handler.path)
    path = parsed.path.removeprefix("/api/desk/")
    if parsed.path != "/api/desk/" + path or path not in ("plan", "preview", "transcribe", "export", "save-project", "open-project"):
        return handler.send_error(404)
    if not same_origin(handler, write=True):
        return json_response(handler, {"error": "请从本机配画面页面提交。"}, 403)
    handler.connection.settimeout(75)
    locked = path in ("transcribe", "export", "save-project", "open-project")
    if locked and not LONG_JOB.acquire(blocking=False):
        return json_response(handler, {"error": "另一个转写或导出正在运行，完成后可重试。"}, 409)
    try:
        if path == "transcribe":
            query = parse_qs(parsed.query, max_num_fields=3)
            json_response(handler, transcribe_upload(handler, query))
        elif path in ("export", "save-project"):
            export_response(handler, read_json(handler), draft=path == "save-project")
        elif path == "open-project":
            from portable_bundle import PROJECT, restore
            with TemporaryDirectory(prefix="visionbuddy-review-upload-") as folder:
                with (Path(folder) / "upload.zip").open("w+b") as archive:
                    receive_bundle(handler, archive)
                    json_response(handler, restore(archive, PROJECT))
        else:
            data = read_json(handler)
            plan = planner.build(data.get("source"), fresh=path == "plan" and data.get("fresh") is True)
            if path == "plan":
                json_response(handler, plan)
            else:
                from desk_render import preview_html

                row, candidate = planner.candidate_at(plan, data.get("row"), data.get("choice", 0))
                response(handler, preview_html(row, candidate).encode("utf8"), "text/html")
    except (BrokenPipeError, ConnectionResetError):
        pass
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        json_response(handler, {"error": str(exc)}, 400)
    finally:
        if locked:
            LONG_JOB.release()
