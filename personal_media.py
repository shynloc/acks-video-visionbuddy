"""Prepare local originals for offline preview and Workbench media import."""

import base64
from contextlib import contextmanager
from io import BytesIO
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

FPS = 25
IMPORT_LIMIT = 128 * 1024 ** 2
WEB_LIMIT = 12 * 1024 ** 2
MOV_LIMIT = 156 * 1024 ** 2
VIDEO_FORMATS = {".mov": "mov", ".mp4": "mov", ".webm": "matroska", ".mkv": "matroska"}
TYPES = {".png": "png", ".svg": "svg", ".html": "html", ".htm": "html",
         **{ext: "video" for ext in VIDEO_FORMATS}}
CANVASES = {"landscape": (960, 540), "portrait": (540, 960), "square": (720, 720)}
MEDIA_SCHEMA = 1
PROOF_TILE_COLUMNS = 4
PROOF_TILE_COUNT = 16


def optional_number(value, default, low, high, label):
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        raise ValueError(label + "无效。")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(label + "无效。") from exc
    if not math.isfinite(result) or not low <= result <= high:
        raise ValueError(f"{label}应在 {low:g} 至 {high:g} 秒之间。")
    return round(result, 3)


def input_options(suffix, options):
    kind = TYPES.get(suffix)
    if kind is None:
        raise ValueError("请选择 PNG、SVG、透明 MOV／WebM／MKV／MP4 或单文件 HTML。")
    details = {"kind": kind}
    if kind in ("html", "video"):
        details["seconds"] = optional_number(options.get("seconds"), 3 if kind == "html" else 12,
                                               .04, 12, "截取时长")
    if kind == "video":
        details["start"] = optional_number(options.get("start"), 0, 0, 24 * 3600, "起始时间")
    if kind == "html":
        canvas = options.get("canvas") or "landscape"
        if canvas not in CANVASES:
            raise ValueError("HTML 画幅请选择横版、竖版或方形。")
        details["canvas"] = canvas
    return details


def tools(command, arguments, timeout=90):
    executable = shutil.which(command)
    if not executable:
        raise ValueError(f"此格式需要本机 {command}。")
    completed = subprocess.run([executable, *arguments], stdin=subprocess.DEVNULL,
                               capture_output=True, timeout=timeout)
    if completed.returncode:
        detail = completed.stderr.decode("utf8", "replace").strip().splitlines()
        raise ValueError("媒体读取或编码失败。" + (" " + detail[-1][:180] if detail else ""))
    return completed.stdout


def fit_size(width, height, limit):
    if min(width, height) <= 0:
        raise ValueError("无法读取素材尺寸。")
    scale = min(1, limit / max(width, height))
    return max(2, round(width * scale)), max(2, round(height * scale))


def decode_video(original, folder, options):
    demuxer = VIDEO_FORMATS[original.suffix]
    data = json.loads(tools("ffprobe", [
        "-v", "error", "-protocol_whitelist", "file,pipe", "-f", demuxer,
        "-select_streams", "v:0", "-show_streams", "-of", "json", str(original)
    ], timeout=30))
    if not data.get("streams"):
        raise ValueError("找不到视频画面。")
    stream = data["streams"][0]
    width, height = fit_size(stream["width"], stream["height"], 960)
    codec = stream.get("codec_name")
    # FFmpeg's native VP8/VP9 decoder drops the WebM alpha plane.
    decoder = ["-c:v", "libvpx" + ("-vp9" if codec == "vp9" else "")] if codec in ("vp8", "vp9") else []
    tools("ffmpeg", [
        "-nostdin", "-v", "error", "-protocol_whitelist", "file,pipe", "-f", demuxer,
        *decoder, "-i", str(original), "-ss", str(options["start"]), "-t", str(options["seconds"]),
        "-map", "0:v:0", "-an", "-sn", "-vf", f"fps={FPS},scale={width}:{height},format=rgba",
        "-frames:v", "300", "-threads", "2", str(folder / "%04d.png")
    ], timeout=140)
    frames = sorted(folder.glob("*.png"))
    if not frames:
        raise ValueError("所选时间段没有视频帧，请调整起始时间。")
    return frames


def png_info(path):
    from PIL import Image

    with Image.open(path) as original:
        if original.format != "PNG" or getattr(original, "is_animated", False):
            raise ValueError("请选择单张 PNG。动画请使用透明视频或 HTML。")
        original.verify()


def media_frames(original, folder, options):
    if options["kind"] == "png":
        png_info(original)
        return [original]
    if options["kind"] == "video":
        return decode_video(original, folder, options)
    outcome = subprocess.run([sys.executable, "-X", "utf8", str(Path(__file__).resolve()),
                              str(original), str(folder), json.dumps(options)],
                             stdin=subprocess.DEVNULL, capture_output=True, timeout=230)
    if outcome.returncode:
        message = outcome.stdout.decode("utf8", "replace").strip()
        raise ValueError(message or "SVG 或 HTML 无法生成可用预览。")
    frames = sorted(folder.glob("*.png"))
    if not frames:
        raise ValueError("SVG 或 HTML 没有生成画面。")
    return frames


def alpha_validity(frames, kind):
    from PIL import Image

    pad = False
    transparent = False
    visible = []
    for index, path in enumerate(frames):
        with Image.open(path) as image:
            low, high = image.convert("RGBA").getchannel("A").getextrema()
        pad |= low > 0
        transparent |= low < 255
        if high >= 32:
            visible.append(index)
    if not visible:
        raise ValueError("素材中没有可见内容。")
    if kind == "video" and not transparent:
        raise ValueError("视频没有检测到透明像素，请导入带 Alpha 的原片。")
    return pad, min(visible, key=lambda i: abs(i - (len(frames) - 1) * .55))


def normalized_frame(path, pad, scale_limit):
    from PIL import Image

    with Image.open(path) as original:
        image = original.convert("RGBA")
    width, height = fit_size(*image.size, scale_limit - 20 if pad else scale_limit)
    if image.size != (width, height):
        image = image.resize((width, height), Image.Resampling.LANCZOS)
    if pad:
        canvas = Image.new("RGBA", (width + 20, height + 20))
        canvas.paste(image, (10, 10))
        return canvas
    return image


def normalize(original, destination, options):
    from PIL import Image

    with TemporaryDirectory(prefix="visionbuddy-capture-") as scratch:
        raw = Path(scratch)
        frames = media_frames(original, raw, options)
        pad, poster = alpha_validity(frames, options["kind"])
        is_motion = len(frames) > 1
        limit = 960 if is_motion else 4096
        image = normalized_frame(frames[poster], pad, limit)
        image.save(destination / "poster.png")
        width, height = image.size
        thumb = image.copy()
        thumb.thumbnail((640, 640), Image.Resampling.LANCZOS)
        thumb.save(destination / "preview.webp", format="WEBP", lossless=True, method=2)
        proof = None
        if is_motion:
            sequence = raw / "frames.bin"
            count = min(len(frames), math.ceil(len(frames) / FPS * 8))
            indices = [round(i * (len(frames) - 1) / max(1, count - 1)) for i in range(count)]
            tile_w, tile_h = fit_size(width, height, 300)
            tiles = []
            with sequence.open("wb") as stream:
                for index, frame in enumerate(frames):
                    rgba = normalized_frame(frame, pad, limit)
                    rgba.save(stream, format="PNG", compress_level=1)
                    if index in indices:
                        tiles.append(rgba.resize((tile_w, tile_h), Image.Resampling.LANCZOS))
                        if len(tiles) >= PROOF_TILE_COUNT or index == indices[-1]:
                            page = Image.new("RGBA", (tile_w * PROOF_TILE_COLUMNS, tile_h * math.ceil(len(tiles) / PROOF_TILE_COLUMNS)))
                            for slot, pic in enumerate(tiles):
                                page.paste(pic, (slot % PROOF_TILE_COLUMNS * tile_w, slot // PROOF_TILE_COLUMNS * tile_h))
                            page.save(destination / f"proof-{indices.index(index) // PROOF_TILE_COUNT:02}.webp",
                                      format="WEBP", lossless=True, method=2)
                            tiles.clear()
            master = destination / "master.mov"
            tools("ffmpeg", [
                "-nostdin", "-v", "error", "-xerror", "-f", "image2pipe", "-framerate", str(FPS),
                "-c:v", "png", "-i", str(sequence), "-frames:v", str(len(frames)), "-an",
                "-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuva444p10le", "-alpha_bits", "16",
                "-threads", "4", str(master),
            ], timeout=180)
            if master.stat().st_size > MOV_LIMIT:
                raise ValueError("标准化后的透明视频过大。请选更短的一段。")
            proof = {"count": count, "width": tile_w, "height": tile_h}
        return {"width": width, "height": height, "frames": len(frames), "seconds": len(frames) / FPS if is_motion else 0,
                "poster": poster, "padding": pad, "proof": proof, "import": options}


@contextmanager
def browser_page(size):
    try:
        from playwright.sync_api import Error, sync_playwright
    except ImportError as exc:
        raise ValueError("SVG 和 HTML 导入需要 Playwright 与本机 Chromium、Edge 或 Chrome。") from exc
    with sync_playwright() as play:
        browser = None
        for channel in (None, "msedge", "chrome"):
            try:
                browser = play.chromium.launch(channel=channel)
                break
            except Error:
                continue
        if browser is None:
            raise ValueError("找不到可用浏览器，请安装 Playwright Chromium、Edge 或 Chrome。")
        try:
            context = browser.new_context(viewport={"width": size[0], "height": size[1]},
                                          offline=True, service_workers="block")
            context.route("**/*", lambda route: route.abort())
            page = context.new_page()
            page.set_default_timeout(8000)
            yield page
        except Error as exc:
            raise ValueError("SVG 或 HTML 无法在离线浏览器中生成小样。") from exc
        finally:
            browser.close()


CSP = ("<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; "
       "img-src data: blob:; media-src data: blob:; font-src data:; "
       "style-src 'unsafe-inline'; script-src 'unsafe-inline'; object-src 'none'; "
       "connect-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'none'\">")


def render_svg(page, raw, folder):
    data = "data:image/svg+xml;base64," + base64.b64encode(raw).decode("ascii")
    page.set_content('<!doctype html><meta charset="utf-8">' + CSP +
                     '<style>html,body{margin:0;background:transparent}img{display:block;width:100vw;height:100vh}</style>')
    size = page.evaluate("""async data => {
        const image = new Image()
        image.src = data
        await image.decode()
        document.body.append(image)
        return [image.naturalWidth, image.naturalHeight]
    }""", data)
    width, height = fit_size(*size, 960)
    page.set_viewport_size({"width": width, "height": height})
    page.screenshot(path=folder / "0001.png", omit_background=True)


def render_html(page, source, folder, seconds):
    # Place the policy before user scripts and keep a standards-mode document.
    import re
    source = re.sub(r"^\s*<!doctype[^>]*>", "", source, count=1, flags=re.I)
    page.set_content('<!doctype html><meta charset="utf-8">' + CSP + source, wait_until="load")
    page.evaluate("document.fonts.ready")
    page.evaluate("Promise.resolve(window.sceneReady)")
    clock = page.evaluate("""() => {
        if (typeof window.renderFrame === 'function') {
            window.previewPlayback?.('pause')
            return 'function'
        }
        const effects = document.getAnimations()
        if (!effects.length) return 'still'
        window.visionBuddyAnimations = effects
        effects.forEach(effect => effect.pause())
        return 'css'
    }""")
    count = 1 if clock == "still" else max(1, round(seconds * FPS))
    for index in range(count):
        if clock == "function":
            page.evaluate("([i,n]) => window.renderFrame(i,n)", [index, count])
        if clock == "css":
            page.evaluate("time => window.visionBuddyAnimations.forEach(a => a.currentTime = time)", index * 40)
        page.screenshot(path=folder / f"{index + 1:04}.png", omit_background=True)


def main():
    original, folder = map(Path, sys.argv[1:3])
    options = json.loads(sys.argv[3])
    size = CANVASES.get(options.get("canvas"), CANVASES["landscape"])
    try:
        with browser_page(size) as page:
            if options["kind"] == "svg":
                render_svg(page, original.read_bytes(), folder)
            else:
                render_html(page, original.read_text(encoding="utf-8-sig"), folder, options["seconds"])
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
