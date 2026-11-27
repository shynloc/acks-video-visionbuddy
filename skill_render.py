"""Export portable VisionBuddy source files and optional transparent media."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

import preview
from skill_catalog import LIBRARY, annotation, asset_code, rights, scene, title

FPS = 25
SIZE = (1120, 660)


def json_text(data):
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def render(html, frames, destination, movie=False, *, size=SIZE, poster=None):
    try:
        from playwright.sync_api import Error as BrowserError, sync_playwright
    except ImportError as exc:
        raise ValueError("导出 PNG 或 MOV 需要 Playwright。请运行 python -m pip install playwright。") from exc
    ffmpeg = shutil.which("ffmpeg") if movie else None
    if movie and not ffmpeg:
        raise ValueError("导出透明 MOV 需要 PATH 中的 FFmpeg。")
    poster = frames - 1 if poster is None else poster
    ending = destination / "ending.png"
    sequence = destination / "frames.png"
    try:
        with sync_playwright() as pw:
            browser = None
            for channel in (None, "msedge", "chrome"):
                try:
                    browser = pw.chromium.launch(channel=channel, headless=True)
                    break
                except BrowserError:
                    continue
            if browser is None:
                raise ValueError("找不到可用浏览器。请运行 python -m playwright install chromium。")
            try:
                context = browser.new_context(
                    viewport={"width": size[0], "height": size[1]},
                    reduced_motion="reduce", service_workers="block", offline=True,
                )
                page = context.new_page()
                page.set_content(html, wait_until="load")
                page.evaluate("document.fonts.ready")
                page.evaluate("Promise.resolve(window.sceneReady)")
                page.evaluate("""async () => {
                    const d = JSON.parse(document.querySelector('#scene-data').textContent)
                    await Promise.all(['png','picture','sticker'].filter(key => d[key]).map(key => {
                        const image = new Image()
                        image.src = d[key]
                        return image.decode()
                    }))
                }""")
                indices = range(frames) if movie else (poster,)
                with sequence.open("wb") as stream:
                    for i in indices:
                        page.evaluate("([i,n]) => window.renderFrame(i,n)", [i, frames])
                        png = page.screenshot(omit_background=True)
                        if movie:
                            stream.write(png)
                        if i == poster:
                            ending.write_bytes(png)
            finally:
                browser.close()
    except BrowserError as exc:
        raise ValueError(f"透明画面渲染失败。{exc}") from exc
    if not movie:
        return ending, None
    master = destination / "overlay.mov"
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-xerror", "-f", "image2pipe",
         "-framerate", str(FPS), "-c:v", "png", "-i", str(sequence), "-frames:v", str(frames),
         "-an", "-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuva444p10le",
         "-alpha_bits", "16", "-threads", "4", str(master)],
        stdin=subprocess.DEVNULL, capture_output=True, timeout=180,
    )
    if result.returncode:
        raise ValueError("透明 MOV 编码失败。请检查 FFmpeg 的 prores_ks 支持。"
                         + result.stderr.decode("utf8", "replace")[-300:])
    return ending, master


def source_paths(visual):
    spec = preview.brief(visual)
    paths = {}
    licenses = {}
    for key in ("objects", "stickers"):
        if key not in spec:
            continue
        entry = spec[key]
        for filename in entry["files"].values():
            path = Path(filename)
            paths[entry["id"] + path.suffix] = path
        record = rights(entry)
        if record:
            notice = LIBRARY / entry["rights"]["notice"]
            paths[notice.name] = notice
            licenses[entry["assetId"]] = {**record, "notice": notice.name}
    return paths, licenses


def source_digest(master_name, master, sources):
    """Match talking-head-motion/2 restore's content-addressed sample ID."""
    values = {master_name: master, **{"sources/" + name: value for name, value in sources.items()}}
    result = hashlib.sha256()
    for name in sorted(values, key=str.casefold if os.name == "nt" else None):
        value = values[name]
        result.update(name.encode("utf8") + b"\0")
        result.update(hashlib.sha256(value.read_bytes() if isinstance(value, Path) else value).digest())
    return result.hexdigest()


def write_member(bundle, name, value):
    if isinstance(value, Path):
        bundle.write(value, name)
    else:
        bundle.writestr(name, value)


def workbench_item(*, title, quote, seconds, release, visual, refs, variants, master, source,
                   package_media, package_sources, treatment="", offset=0):
    item = dict(title=title, quote=quote, offset=offset, seconds=seconds,
                libraryRelease=release, visual={k: refs[k] for k in visual},
                assetRefs=refs, variantIds=variants, producer="VisionBuddy",
                packageMedia=package_media, packageSources=package_sources,
                sample={"id": source_digest("media" + master.suffix, master, source)})
    if treatment:
        item["treatment"] = treatment
    return item


def export(group, row, variant, args, release):
    destination = args.output.resolve()
    if destination.suffix.lower() != ".zip":
        raise ValueError("导出路径请使用 .zip。")
    if destination.exists():
        raise FileExistsError(f"输出文件已存在。{destination}")
    if args.quote and not args.quote.strip():
        raise ValueError("原句不能只有空白。")
    if group not in ("demos", "practice", "objects", "stickers"):
        raise ValueError("命令行支持导出口播搭配、演示、3D 物件、贴纸和图标。其他素材可在浏览器中查看。")

    demo = None
    labels = []
    with tempfile.TemporaryDirectory(prefix="visionbuddy-") as directory:
        stage = Path(directory)
        ending = None
        source = {}
        if group in ("demos", "practice"):
            html, demo, labels, visual = scene(group, row, args)
            source["scene.html"] = html.encode("utf8")
            if args.media != "source":
                ending, master = render(html, args.seconds * FPS, stage, args.media == "mov")
                source[ending.name] = ending
                master = master or ending
            else:
                master = None
        else:
            if args.media == "mov" or args.demo or args.label or args.object or args.sticker is not None:
                raise ValueError("静态素材可以按配色导出原件和透明 PNG。动画与改字请用口播搭配或演示。")
            palette = preview.resolve_entry("palettes", args.palette or (variant or {"id": "atelier"})["id"])
            if variant and palette["id"] != variant["id"]:
                raise ValueError("素材编号和 --palette 指定了不同配色。")
            visual = {group: row["id"], "palettes": palette["id"]}
            master = LIBRARY / row["variants"][palette["id"]]["preview"]

        files, licenses = source_paths(visual)
        source.update(files)
        refs = {key: preview.resolve_entry(key, value)["assetId"] for key, value in visual.items()}
        variants = {key: refs[key] + "@" + refs["palettes"] for key in ("objects", "stickers") if key in refs}
        if demo:
            refs["treatment"] = demo["assetId"]
        mark = annotation(visual, demo, labels, args.seconds if demo else None)
        source["asset-ids.json"] = json_text({k: v for k, v in refs.items() if k != "treatment"}).encode("utf8")
        source_prefix = "可编辑源件/"
        license_records = {code: {**record, "notice": source_prefix + record["notice"]}
                           for code, record in licenses.items()}
        result = {
            "format": "visionbuddy-export/1", "libraryRelease": release, "assetId": row["assetId"],
            "assetRefs": refs, "variantIds": variants, "annotation": mark,
            "quote": args.quote, "labels": labels, "seconds": args.seconds if demo else None,
            "media": None, "ending": None, "sources": {name: source_prefix + name for name in source},
            "licenses": license_records, "workbenchImport": False,
        }
        if master:
            is_movie = master.suffix == ".mov"
            result["media"] = ("透明动画/" if is_movie else "透明图片/") + row["assetId"] + master.suffix
            result["workbenchImport"] = bool(args.quote)
        if ending:
            result["ending"] = "透明定格/" + row["assetId"] + ".png"

        archive = stage / "export.zip"
        with ZipFile(archive, "w", ZIP_DEFLATED, compresslevel=3) as bundle:
            for name, value in source.items():
                write_member(bundle, result["sources"][name], value)
            if master:
                bundle.write(master, result["media"])
            if ending:
                bundle.write(ending, result["ending"])
            bundle.writestr("visionbuddy.json", json_text(result))
            bundle.writestr("原句对照.txt", ((args.quote + "\n") if args.quote else "") + mark + "\n")
            if result["workbenchImport"]:
                item = workbench_item(
                    title=title(row), quote=args.quote, seconds=args.seconds, release=release,
                    visual=visual, refs=refs, variants=variants, master=master, source=source,
                    package_media=result["media"], package_sources=result["sources"],
                    treatment=demo["id"] if demo else "",
                )
                bundle.writestr("素材搭配.json", json_text({"format": "talking-head-motion/2", "items": [item]}))

        destination.parent.mkdir(parents=True, exist_ok=True)
        with archive.open("rb") as ready, destination.open("xb") as output:
            try:
                shutil.copyfileobj(ready, output)
            except OSError:
                output.close()
                destination.unlink()
                raise
    return {**result, "output": str(destination)}
