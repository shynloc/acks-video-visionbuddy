"""Preview and package normalized personal materials without running their originals."""

import base64
import json
import math
from pathlib import Path

import personal_store as store
import skill_render as render

WORKBENCH_SAMPLE_LIMIT = 192 * 1024**2


def inline_file(path, mime):
    return "data:" + mime + ";base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def scene_html(record, play=False):
    folder = store.asset_dir(record)
    details = record["media"]
    header = ('<!doctype html><meta charset="utf-8"><title>个人素材试看</title>'
              '<style>html,body{margin:0;height:100%;background:transparent}'
              'canvas,img{display:block;width:100%;height:100%;object-fit:contain}</style>')
    proof = details["proof"]
    if not proof:
        return header + (f'<img alt="个人素材" src="{inline_file(folder / "preview.webp", "image/webp")}">'
                         '<script>window.renderFrame=()=>{}</script>')
    count = proof["count"]
    atlas = [inline_file(folder / f"proof-{i:02}.webp", "image/webp") for i in range(math.ceil(count / 16))]
    data = json.dumps({"width": proof["width"], "height": proof["height"], "count": count,
                       "frames": details["frames"], "poster": details["poster"],
                       "atlas": atlas, "play": play})
    return header + '<canvas aria-label="个人透明素材动画"></canvas><script>const personal=' + data + r""";
const canvas=document.querySelector('canvas')
canvas.width=personal.width
canvas.height=personal.height
const ctx=canvas.getContext('2d')
const images=personal.atlas.map(uri=>{
    const image=new Image()
    image.src=uri
    return image
})
window.renderFrame=(frame,total)=>{
    const index=Math.min(personal.count-1, Math.max(0, Math.round(frame/Math.max(1,total-1)*(personal.count-1))))
    const sheet=images[Math.floor(index/16)]
    if (!sheet.complete || !sheet.naturalWidth) return
    const i=index%16, w=personal.width, h=personal.height
    ctx.clearRect(0,0,w,h)
    ctx.drawImage(sheet, i%4*w, Math.floor(i/4)*h,w,h,0,0,w,h)
}
let id=0
window.previewPlayback=action=>{
    cancelAnimationFrame(id)
    if(action==='pause') return
    if(action==='finish') {window.renderFrame(personal.poster,personal.frames);return}
    const start=performance.now(), frames=personal.frames
    const tick=now=>{
        const frame=Math.min(frames-1,Math.floor((now-start)/40))
        window.renderFrame(frame,frames)
        if(frame<frames-1) id=requestAnimationFrame(tick)
    }
    id=requestAnimationFrame(tick)
}
window.sceneReady=Promise.all(images.map(image=>image.decode())).then(()=>{
    window.renderFrame(personal.poster,personal.frames)
    if(personal.play && !matchMedia('(prefers-reduced-motion: reduce)').matches) window.previewPlayback('restart')
})
</script>"""


def proof_html(record):
    from desk_render import preview_html
    return preview_html({}, {"personal": record["ref"], "seconds": record["media"]["seconds"] or 3})


def public_record(record):
    return {k: v for k, v in record.items() if k != "blob"}


def original_annotation(row, ref):
    if row["notes"]:
        notes = [store.CODE.sub(lambda match: ref if match[0].upper().split("@")[0] == ref.split("@")[0] else match[0], note)
                 for note in row["notes"]]
        return "".join("（画面：" + note + "）" for note in notes)
    return f"（画面：{ref}）"


def file_size(value):
    return value.stat().st_size if isinstance(value, Path) else len(value)


def write_row(bundle, row, candidate, place, media, release):
    selected = store.get(candidate["personal"])
    ref, info = selected["ref"], selected["media"]
    original = store.original_path(selected)
    normalized = store.asset_dir(selected)
    poster = normalized / "poster.png"
    motion = info["frames"] > 1
    seconds = info["seconds"] if motion else candidate["seconds"]
    master = None if media == "source" else normalized / "master.mov" if motion and media == "mov" else poster
    prefix = f"可编辑源件/{row['id']}/"
    source = {"preview.png": poster}
    original_member = prefix + original.name
    # Workbench accepts stills, SVG and HTML inside packageSources. Keep original video as a companion file.
    if original.suffix in (".png", ".svg", ".html", ".htm"):
        name = original.with_suffix(".html").name if original.suffix == ".htm" else original.name
        original_member = prefix + name
        source[name] = original
    else:
        original_member = f"个人原件/{row['id']}/{original.name}"
        bundle.write(original, original_member)
    rights = selected["rights"]
    metadata = {**public_record(selected), "originalMember": original_member}
    source["个人素材.json"] = render.json_text(metadata).encode("utf8")
    names = {name: prefix + name for name in source}
    for name, value in source.items():
        render.write_member(bundle, names[name], value)
    record = {
        "assetRefs": {"personal": selected["assetId"]}, "variantIds": {"personal": ref},
        "selectedCodes": [ref], "personal": metadata, "sources": names, "original": original_member,
        "placement": place, "assetSeconds": seconds if motion else None,
        "annotation": original_annotation(row, ref), "workbenchAnnotation": "",
        "licenses": {ref: {**rights, "notice": names["个人素材.json"]}},
    }
    if master is None:
        return record, None
    if master.stat().st_size + sum(map(file_size, source.values())) > WORKBENCH_SAMPLE_LIMIT:
        raise ValueError("这条素材超过工作台单条素材上限。请换较短的视频或导出 PNG。")
    folder = "透明动画" if master.suffix == ".mov" else "透明图片"
    record["media"] = f"{folder}/{row['id']}{master.suffix}"
    record["poster"] = f"透明定格/{row['id']}.png"
    bundle.write(master, record["media"])
    bundle.write(poster, record["poster"])
    item = render.workbench_item(
        title=selected["name"], quote=row["quote"], seconds=seconds, release=release,
        visual={}, refs=record["assetRefs"], variants=record["variantIds"], master=master, source=source,
        package_media=record["media"], package_sources=names, offset=row["offset"],
    )
    item["visionbuddyPlacement"] = place
    item["visionbuddyMedia"] = {"width": info["width"], "height": info["height"]}
    item["visionbuddyPersonal"] = ref
    return record, item
