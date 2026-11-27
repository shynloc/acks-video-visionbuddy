"""Prepare the reviewed scene and write compatible multi-item material bundles."""

import base64
from functools import lru_cache
import json
import math
from pathlib import Path
import re
import shutil
import struct
from tempfile import TemporaryDirectory
from zipfile import ZipFile, ZIP_DEFLATED

import preview
import skill_catalog as catalog
import skill_render as render
import desk_plan as planner

MAX_PACK = 512 * 1024 ** 2
CANVAS = (960, 360)


def json_for_html(value):
    return json.dumps(value, ensure_ascii=False).replace("<", r"\u003c")


def static_png(visual):
    try:
        return preview.overlay_png(preview.brief(visual))
    except ModuleNotFoundError as exc:
        if exc.name != "PIL":
            raise
        raise ValueError("同时预览物件和贴纸需要 Pillow。") from exc


def png_uri(data):
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


@lru_cache(maxsize=1)
def canvas_renderer():
    return "\n".join((catalog.ROOT / "site" / file).read_text(encoding="utf8")
                     for file in ("overlay-easing.js", "renderer.js", "illustrations.js"))


def shorter(text, limit=16):
    text = re.sub(r"\s+", " ", text.strip(" ，。！？!?、,.：:　"))
    return text if len(text) <= limit else text[:limit - 1] + "…"


def effect_settings(row, candidate):
    words = row["quote"]
    choices = [shorter(value, 12) for value in re.split(r"首先|先|然后|接着|最后|再(?=.{1,24})", words) if value.strip(" ，。")]
    labels = (choices + ["第一步", "第二步", "第三步"][len(choices):])[:3]
    numbers = planner.comparison_numbers(words)
    values = [float(value) for value in numbers[:2] if len(value) <= 24]
    return dict(title=shorter(words, 20), name=shorter(words, 11), a="变化前", b="变化后",
                labels=labels, values=values if len(values) == 2 and all(map(math.isfinite, values)) else [0, 0],
                colors=preview.resolve_entry("palettes", candidate["visual"]["palettes"])["colors"])


PLAYBACK = """
let loopId = 0
window.previewPlayback = action => {
    cancelAnimationFrame(loopId)
    if (action === 'pause') return
    if (action === 'finish') { window.renderFrame(frames-1,frames);return }
    const start = performance.now()
    const loop = now => {
        const frame = Math.min(frames-1, Math.floor((now-start)/40))
        window.renderFrame(frame, frames)
        if (frame < frames-1) loopId = requestAnimationFrame(loop)
    }
    loopId = requestAnimationFrame(loop)
}
"""


def scene_html(row, candidate, seconds, play):
    if "personal" in candidate:
        import personal_render
        return personal_render.scene_html(personal_render.store.get(candidate["personal"]), play)
    visual = candidate["visual"]
    if candidate["treatment"]:
        demo = catalog.lookup(candidate["treatment"], "demos")[1]
        return catalog.compose_demo(demo, visual, candidate["labels"], seconds, row["quote"], play=play)
    if not candidate["effects"]:
        return (
            '<!doctype html><meta charset="utf-8"><title>口播透明画面</title>'
            '<style>html,body{margin:0;height:100%;background:transparent}'
            'img{display:block;width:100%;height:100%;object-fit:contain}</style>'
            f'<img alt="透明物件或贴纸" src="{png_uri(static_png(visual))}">'
            '<script>window.renderFrame=()=>{}</script>'
        )

    overlay = bool(visual.get("objects") or visual.get("stickers"))
    data = {"ids": candidate["effects"], "settings": effect_settings(row, candidate),
            "seconds": seconds, "play": play}
    if overlay:
        data["picture"] = png_uri(static_png(visual))
    terms = [term for term in catalog.groups()["effects"] if term["id"] in data["ids"]]
    settings = json_for_html({"terms": terms, "quotes": []})
    return (
        '<!doctype html><meta charset="utf-8"><title>透明口播动效</title>'
        '<style>html,body{margin:0;background:transparent}canvas{display:block;width:100%;height:auto}</style>'
        '<canvas width="960" height="360" aria-label="透明口播动画"></canvas>'
        '<script type="application/json" id="scene-data">' + json_for_html(data) + '</script>'
        '<script>const DATA=' + settings + ';\n' + canvas_renderer() + r"""
const d = JSON.parse(document.querySelector('#scene-data').textContent)
const canvas = document.querySelector('canvas')
const frames = Math.max(1,Math.round(d.seconds*25))
window.renderFrame = (frame,total) => draw(canvas,Math.min(1,frame/Math.max(1,total-1)),d.ids,'neutral',false,d.settings)
""" + PLAYBACK + r"""
window.sceneReady = (async () => {
    if (d.picture) {
        const image = new Image()
        image.src = d.picture
        await image.decode()
        d.settings.overlay = true
        d.settings.imageA = image
    }
    window.renderFrame(0,frames)
    if (d.play && !matchMedia('(prefers-reduced-motion: reduce)').matches) window.previewPlayback('restart')
})()
</script>"""
    )


def clip_frames(candidate, place):
    seconds = candidate["seconds"]
    if "start" in place and not candidate["fixedSeconds"]:
        seconds = place["end"] - place["start"]
    return max(1, min(300, round(render.FPS * seconds)))


def preview_html(row, candidate):
    html = scene_html(row, candidate, candidate["seconds"], False)
    # The desk drives this script from the video clock. In a saved HTML file the play button is still available.
    return html + r"""
<script>
const deskStandalone = window.parent === window
if (deskStandalone && window.previewPlayback) {
    const button = document.createElement('button')
    button.textContent='从头试播'
    button.addEventListener('click',()=>window.previewPlayback('restart'))
    document.body.append(button)
}
window.addEventListener('message', async event => {
    if (event.source !== window.parent || event.data?.type !== 'visionbuddy-frame') return
    const { frame, total } = event.data
    if (!Number.isInteger(frame) || !Number.isInteger(total) || frame < 0 || frame >= total || total > 300) return
    await window.sceneReady
    window.previewPlayback?.('pause')
    window.renderFrame?.(frame,total)
})
</script>
"""


def workbench_mark(row, candidate):
    if row["notes"] and not candidate["kit"]:
        return "".join("（画面：" + note + "）" for note in row["notes"])
    demo = catalog.lookup(candidate["treatment"], "demos")[1] if candidate["treatment"] else None
    effect = catalog.lookup(candidate["effects"][0], "effects")[1] if candidate["effects"] else None
    labels = candidate["labels"]
    if demo and demo.get("scene") == "number" and not labels[-1]:
        labels = [*labels[:-1], " "]
    mark = catalog.annotation(candidate["visual"], demo, labels, candidate["seconds"], effect)
    if candidate["cue"]:
        mark = mark[:-2] + "，说到「" + candidate["cue"] + "」时出现。）"
    return mark


def write_row(bundle, stage, row, candidate, place, media, release):
    if "personal" in candidate:
        from personal_render import write_row as write_personal_row
        return write_personal_row(bundle, row, candidate, place, media, release)
    visual = candidate["visual"]
    asset_refs = {key: preview.resolve_entry(key, value)["assetId"] for key, value in visual.items()}
    variant_ids = {key: asset_refs[key] + "@" + asset_refs["palettes"]
                   for key in ("objects", "stickers") if key in visual}
    if candidate["treatment"]:
        asset_refs["treatment"] = catalog.lookup(candidate["treatment"], "demos")[1]["assetId"]
    if candidate["effects"]:
        asset_refs["effects"] = [catalog.lookup(code, "effects")[1]["assetId"] for code in candidate["effects"]]
    if candidate["kit"]:
        asset_refs["kit"] = candidate["kit"]
    files, licenses = render.source_paths(visual)
    frames = clip_frames(candidate, place)
    seconds = frames / render.FPS
    html = scene_html(row, candidate, seconds, True)
    sources = {"scene.html": html.encode("utf8"), **files}
    sources["asset-ids.json"] = render.json_text({key: asset_refs[key] for key in visual}).encode("utf8")
    source_prefix = f"可编辑源件/{row['id']}/"
    master = ending = None
    if media != "source":
        if candidate["effects"] or candidate["treatment"]:
            movie = candidate["animated"] and media == "mov"
            size = CANVAS if candidate["effects"] else render.SIZE
            poster = min(frames - 1, round((frames - 1) * .55)) if candidate["effects"] else frames - 1
            ending, master = render.render(html, frames, stage, movie, size=size, poster=poster)
            master = master or ending
        else:
            ending = stage / "ending.png"
            ending.write_bytes(static_png(visual))
            master = ending
        sources["ending.png"] = ending
    package_sources = {name: source_prefix + name for name in sources}
    for name, value in sources.items():
        render.write_member(bundle, package_sources[name], value)
    record = {
        "assetRefs": asset_refs, "variantIds": variant_ids, "selectedCodes": candidate["codes"],
        "placement": place, "assetSeconds": seconds if candidate["animated"] else None,
        "annotation": workbench_mark(row, candidate), "sources": package_sources,
        "licenses": {key: {**value, "notice": source_prefix + value["notice"]} for key, value in licenses.items()},
    }
    if master is None:
        return record, None
    folder = "透明动画" if master.suffix == ".mov" else "透明图片"
    record["media"] = f"{folder}/{row['id']}{master.suffix}"
    record["poster"] = f"透明定格/{row['id']}.png"
    bundle.write(master, record["media"])
    bundle.write(ending, record["poster"])
    item = render.workbench_item(
        title=candidate["title"], quote=row["quote"], seconds=seconds, release=release,
        visual=visual, refs=asset_refs, variants=variant_ids, master=master, source=sources,
        package_media=record["media"], package_sources=package_sources,
        treatment=candidate["treatment"], offset=row["offset"],
    )
    item["visionbuddyPlacement"] = place
    if master.suffix == ".mov":
        width, height = size
    else:
        with master.open("rb") as file:
            width, height = struct.unpack(">II", file.read(24)[16:24])
    item["visionbuddyMedia"] = {"width": width, "height": height}
    return record, item


def time_label(seconds):
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02}.{ms:03}"


def export(plan, decisions, destination, media="mov", *, state=None):
    if media not in ("mov", "png", "source"):
        raise ValueError("请选择透明 MOV、透明 PNG 或可编辑源件。")
    if destination.suffix.lower() != ".zip" or destination.exists():
        raise ValueError("请指定一个尚未存在的 .zip 文件。")
    from portable_bundle import PROJECT, project_for, write_assets

    approved, summaries = planner.review_choices(plan, decisions)
    project, portable_refs = project_for(plan, {**(state or {}), "decisions": decisions})
    destination = destination.resolve()
    with TemporaryDirectory(prefix="visionbuddy-desk-export-") as temp:
        stage = Path(temp)
        archive = stage / "material.zip"
        items = []
        with ZipFile(archive, "w", ZIP_DEFLATED, compresslevel=2) as bundle:
            for row, candidate, place, summary in approved:
                folder = stage / row["id"]
                folder.mkdir()
                try:
                    record, item = write_row(bundle, folder, row, candidate, place, media, plan["libraryRelease"])
                except ValueError as exc:
                    raise ValueError(f"「{row['quote'][:20]}」导出失败。{exc}") from exc
                summary.update(record)
                if item:
                    items.append(item)
                if bundle.fp.tell() > MAX_PACK:
                    raise ValueError("素材包超过 512 MB，请分几次导出。")

            timeline = {"format": "visionbuddy-timeline/1", "libraryRelease": plan["libraryRelease"],
                        "inputKind": plan["source"]["kind"], "timeBasis": "source" if plan["source"]["kind"] != "script" else None,
                        "rows": summaries, "sourceDuration": plan["source"].get("duration"),
                        "recording": project.get("recording")}
            bundle.writestr("时间与素材.json", render.json_text(timeline))
            bundle.writestr("审核选择.json", render.json_text(decisions))
            bundle.writestr("口播正文.txt", plan["spoken"])
            if plan["source"]["kind"] in ("script", "srt"):
                raw_name = "原稿.txt" if plan["source"]["kind"] == "script" else "原字幕.srt"
                bundle.writestr(raw_name, plan["source"]["text"])
            else:
                bundle.writestr("转写时间码.json", render.json_text(plan["source"]["cues"]))

            lines, marked, workbench_marked = [], [], []
            for summary in summaries:
                marks = "".join("（画面：" + note + "）" for note in summary["notes"])
                annotation = summary.get("annotation", marks)
                marked.append(summary["quote"] + annotation)
                is_personal_note = planner.personal.CODE.search(annotation)
                workbench_marked.append(summary["quote"] + ("" if is_personal_note else annotation))
                if "placement" in summary:
                    place = summary["placement"]
                    clock = (time_label(place["start"]) + " → " + time_label(place["end"])
                             if "start" in place else "待按原句对齐")
                    lines.append(clock + "  " + summary["quote"] + "\n" + summary["annotation"])
                elif summary["state"] == "none":
                    lines.append("纯口播  " + summary["quote"])
            bundle.writestr("带画面标注的稿件.txt", "\n".join(marked) + "\n")
            if marked != workbench_marked:
                bundle.writestr("工作台稿件.txt", "\n".join(workbench_marked) + "\n")
            write_assets(bundle, PROJECT, portable_refs, project)
            bundle.writestr("原句对照.txt", "\n\n".join(lines) + "\n")
            if items:
                bundle.writestr("素材搭配.json", render.json_text({
                    "format": "talking-head-motion/2", "items": items,
                }))
        if archive.stat().st_size > MAX_PACK:
            raise ValueError("素材包超过 512 MB，请分几次导出。")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with archive.open("rb") as ready, destination.open("xb") as output:
            try:
                shutil.copyfileobj(ready, output)
            except OSError:
                output.close()
                destination.unlink()
                raise
    return {"output": str(destination), "count": len(approved), "workbenchImport": bool(items),
            "libraryRelease": plan["libraryRelease"]}
