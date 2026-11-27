"""Library composition shared with the migration baseline."""
import base64
import io
import json
from pathlib import Path
import re
from functools import lru_cache

LIBRARY = Path(__file__).resolve().parent / "site" / "visual"


@lru_cache(maxsize=1)
def catalog():
    return json.loads((LIBRARY / "catalog.json").read_text(encoding="utf8"))


def resolve_entry(group, key):
    if isinstance(key, str):
        for entry in catalog()[group]:
            if key == entry["id"] or key.upper() == entry["assetId"]:
                return entry
    raise ValueError("素材册中没有所选搭配。")


def selection(raw=None):
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("风格搭配格式不正确。")
    result = {}
    for group in ("styles", "palettes", "objects", "stickers"):
        key = raw.get(group)
        if key:
            if group in ("objects", "stickers") and isinstance(key, str) and "@" in key:
                key, color = key.split("@", 1)
                palette = resolve_entry("palettes", color)["id"]
                if result.get("palettes", palette) != palette:
                    raise ValueError("所选版本使用不同配色，请用同一套配色。")
                result["palettes"] = palette
            result[group] = resolve_entry(group, key)["id"]
    return result


def brief(raw):
    selected = selection(raw)
    result = {}
    for kind, key in selected.items():
        entry = next(e for e in catalog()[kind] if e["id"] == key)
        result[kind] = {
            k: v for k, v in entry.items() if k not in ("variants", "files", "source")
        }
        if "variants" in entry:
            palette = resolve_entry("palettes", selected.get("palettes", "atelier"))
            result[kind]["variantId"] = entry["assetId"] + "@" + palette["assetId"]
            result[kind]["files"] = {
                k: str(LIBRARY / v)
                for k, v in entry["variants"][
                    selected.get("palettes", "atelier")
                ].items()
            }
    return result


def overlay_png(spec):
    from PIL import Image

    obj, sticker = spec.get("objects"), spec.get("stickers")
    if not (obj or sticker):
        raise ValueError("请从素材册挑一个物件或贴纸。")
    main = (obj or sticker)["files"]["preview"]
    if obj and sticker:
        with (
            Image.open(main) as im,
            Image.open(sticker["files"]["preview"]) as mark,
        ):
            im = im.convert("RGBA")
            mark = mark.convert("RGBA")
            mark.thumbnail(
                (im.width // 3, im.height // 3), Image.Resampling.LANCZOS
            )
            anchors = obj.get("tokens", {}).get("anchors", {})
            tip = sticker.get("tokens", {}).get("anchor")
            x, y = im.width - mark.width - 12, 12
            point_marks = {
                "pin",
                "loupe",
                "focus",
                "leader",
                "tap",
                "dragtrail",
                "rotatearc",
                "dimension",
                "level",
            }
            if sticker["id"] not in point_marks and tip:
                bounds = im.getbbox()
                if bounds:
                    x = min(
                        im.width - mark.width - 4, bounds[2] - mark.width // 3
                    )
                    y = max(4, bounds[1] - mark.height // 4)
            if sticker["id"] in point_marks and anchors and tip:
                target = (
                    "tare"
                    if sticker["id"] == "tap" and "tare" in anchors
                    else next(iter(anchors))
                )
                u, v = anchors[target]
                x = round(u * im.width - tip[0] / 192 * mark.width)
                y = round(v * im.height - tip[1] / 128 * mark.height)
                x = max(0, min(x, im.width - mark.width))
                y = max(0, min(y, im.height - mark.height))
                if sticker["id"] == "loupe":
                    from PIL import ImageDraw

                    radius = max(4, round(33 * mark.width / 192))
                    cx, cy = round(u * im.width), round(v * im.height)
                    half = max(2, radius // 2)
                    zoom = im.crop(
                        (cx - half, cy - half, cx + half, cy + half)
                    ).resize((radius * 2, radius * 2), Image.Resampling.LANCZOS)
                    mask = Image.new("L", zoom.size)
                    ImageDraw.Draw(mask).ellipse(
                        (0, 0, 2 * radius - 1, 2 * radius - 1), fill=255
                    )
                    im.paste(
                        zoom,
                        (
                            x + round(78 * mark.width / 192) - radius,
                            y + round(51 * mark.height / 128) - radius,
                        ),
                        mask,
                    )
            im.alpha_composite(mark, (x, y))
            result = io.BytesIO()
            im.save(result, format="PNG")
            return result.getvalue()
    return Path(main).read_bytes()


@lru_cache(maxsize=1)
def treatment_catalog():
    return json.loads((LIBRARY / "treatments.json").read_text(encoding="utf8"))


def resolve_treatment(key, object_id=None):
    for entry in treatment_catalog():
        if key in (entry["id"], entry["assetId"]) and (not object_id or entry["object"] == object_id):
            return entry
    raise ValueError("没有找到这个部位演示。")


def scene_data(context):
    treatment = resolve_treatment(context["treatment"], context["visual"].get("objects"))
    visual = context["visual"]
    spec = brief(visual)
    obj = spec["objects"]
    palette = spec.get("palettes") or brief({"palettes": "atelier"})["palettes"]
    quote = context["quote"]
    unit = (
        r"(?:千克|公斤|克|kg|g)"
        if treatment["object"] == "scale"
        else r"(?:毫升|升|mL|ml|L)"
    )
    values = re.findall(
        r"(?<![\d.])(?:\d+(?:\.\d+)?|[零一二三四五六七八九十百千万两半]+)\s*" + unit,
        quote,
        re.I,
    )
    value = values[-1].strip() if values else ""
    ordinal = re.search(r"第([一二三四五1-5])(?:条|格|道)", quote)
    mark = "第" + ordinal[1] + "条刻度" if ordinal else ""
    position = (
        "一二三四五".find(ordinal[1]) + 1
        if ordinal and not ordinal[1].isdigit()
        else int(ordinal[1])
        if ordinal
        else 3
    )
    callouts = {
        "level": mark or value or "液面位置",
        "tare": "归零按键",
        "display": value or "秤面读数",
        "jaw": "夹口",
        "pocket": "侧袋开口",
    }
    data = dict(
        object=treatment["object"],
        kind=treatment["kind"],
        part=treatment["part"],
        colors=palette["colors"],
        value=value or "✓",
        finalLabel=value or "查看读数",
        callout=callouts[treatment["part"]],
        fillY=237 - (position - 1) * 25,
        anchor=obj["tokens"]["anchors"][treatment["part"]],
    )
    data["frames"] = context.get("seconds", 3) * 25
    data["style"] = visual.get("styles", "field")
    if "stickers" in spec:
        sticker = Path(spec["stickers"]["files"]["vector"])
        data["sticker"] = "data:image/svg+xml;base64," + base64.b64encode(
            sticker.read_bytes()
        ).decode("ascii")
    if treatment["kind"] == "still":
        data["png"] = "data:image/png;base64," + base64.b64encode(
            Path(obj["files"]["preview"]).read_bytes()
        ).decode("ascii")
    return data, spec


def demo_html(code):
    entry = resolve_treatment(code)
    quote = {"scale": "称重 180 克", "jug": "倒到第 3 条刻度"}.get(entry["object"], entry["label"])
    data, _ = scene_data(dict(
        treatment=entry["id"], visual={"objects": entry["object"], "palettes": "atelier"},
        quote=quote, seconds=3,
    ))
    template = (LIBRARY / "part-demo.html").read_text(encoding="utf8")
    payload = json.dumps(data, ensure_ascii=False).replace("<", r"\u003c")
    return template.replace("__SCENE__", payload)
