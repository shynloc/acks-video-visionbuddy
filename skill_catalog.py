"""Read the published VisionBuddy catalog and prepare portable scenes."""

import base64
from functools import lru_cache
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlencode

import preview

ROOT = Path(__file__).resolve().parent
LIBRARY = preview.LIBRARY
GROUPS = ("effects", "demos", "objects", "stickers", "styles", "palettes", "components", "practice")
SEARCH_FIELDS = ("name", "label", "tech", "tags", "keywords", "uses", "summary",
                 "description", "prompt", "parts", "shape", "example", "subjects", "cues")
CODE = re.compile(r"(?<![A-Z0-9])(?:FX|DEMO|OBJ|STK|ICO|WEB|PAL|UI|KIT)-\d+(?:@PAL-\d+)?(?![A-Z0-9])", re.I)


@lru_cache(maxsize=1)
def groups():
    visual = preview.catalog()
    return {
        "effects": json.loads((ROOT / "site/catalog.json").read_bytes())["terms"],
        "demos": preview.treatment_catalog(),
        **{name: visual[name] for name in GROUPS[2:]},
    }


def assets(kind=None):
    for group in (kind,) if kind else GROUPS:
        for row in groups()[group]:
            yield group, row


def lookup(key, kind=None):
    name, separator, color = key.strip().partition("@")
    matches = [(group, row) for group, row in assets(kind)
               if name.casefold() in (row["id"].casefold(), row["assetId"].casefold())]
    if len(matches) > 1:
        raise ValueError(f"{name} 对应多个类别，请使用正式素材编号。")
    if not matches:
        raise ValueError(f"素材库没有找到 {name}。")
    group, row = matches[0]
    if not separator:
        return group, row, None
    palette = preview.resolve_entry("palettes", color)
    if palette["id"] not in row.get("variants", {}):
        raise ValueError(f"{row['assetId']} 没有 {palette['assetId']} 配色变体。")
    return group, row, palette


def asset_code(row, palette=None):
    return row["assetId"] + ("@" + palette["assetId"] if palette else "")


def title(row):
    return row.get("name") or row["label"]


def browser_path(group, row, palette=None):
    if group == "effects":
        page, key = "/index.html", "asset"
    elif group == "demos":
        page, key = "/demos.html", "asset"
    else:
        page, key = "/visual/index.html", "kit" if group == "practice" else "asset"
    return page + "?" + urlencode({key: asset_code(row, palette)})


def summary(group, row, palette=None):
    return {
        "kind": group, "assetId": row["assetId"], "legacyId": row["id"],
        "title": title(row), "variantId": asset_code(row, palette) if palette else None,
        "description": next((row[k] for k in ("reason", "summary", "description", "uses", "prompt") if row.get(k)), ""),
        "previewPath": browser_path(group, row, palette),
    }


def detail(group, row, palette=None):
    files = row["variants"][palette["id"]] if palette else row.get("files", {})
    return {
        **summary(group, row, palette),
        "files": {key: "site/visual/" + path for key, path in files.items()},
        "paletteVariants": [entry["assetId"] for entry in groups()["palettes"]
                            if entry["id"] in row.get("variants", {})],
        "metadata": {key: value for key, value in row.items() if key not in ("files", "variants")},
    }


def normalize(value):
    values = value if isinstance(value, list) else [value]
    return unicodedata.normalize("NFKC", " ".join(values)).casefold()


def find(query, kind, limit):
    query = normalize(query).strip()
    if not query:
        raise ValueError("请输入名称、用途或素材编号。")
    if len(query) > 300:
        raise ValueError("请使用 300 字以内的搜索词。")
    if CODE.fullmatch(query):
        return [summary(*lookup(query, kind))]
    exact = [(group, row) for group, row in assets(kind)
             if query in (row["id"].casefold(), row["assetId"].casefold())]
    if exact:
        return [summary(group, row) for group, row in exact[:limit]]
    codes = {code.split("@")[0].upper() for code in CODE.findall(query)}
    words = set(re.findall(r"[a-z0-9]+", query))
    spans = re.findall(r"[\u3400-\u9fff]+", query)
    phrases = {span[start:start + size] for span in spans for size in range(2, min(6, len(span)) + 1)
               for start in range(len(span) - size + 1)}
    phrases.update(span for span in spans if len(span) == 1)

    def score(row):
        fields = [normalize(row[field]) for field in SEARCH_FIELDS if row.get(field)]
        text = " ".join(fields)
        matches = {p for p in phrases if p in text}
        # Prefer the longest matching phrase over the smaller matches it contains.
        distinctive = (p for p in matches if not any(p != other and p in other for other in matches))
        weight = sum(len(p) ** 2 for p in distinctive)
        word_hits = words.intersection(re.findall(r"[a-z0-9]+", text + " " + row["id"].casefold()))
        tags = normalize(row.get("tags", "")).split()
        return (
            (3000 if row["assetId"] in codes else 0)
            + (150 if query in normalize(title(row)) else 0)
            + (120 if any(query in field for field in fields) else 0)
            + weight + 5 * len(word_hits)
            + 180 * (query in "".join(tags)) + 4 * bool(weight and tags)
        )

    ranked = [(score(row), group, row) for group, row in assets(kind)]
    ranked.sort(key=lambda result: (-result[0], result[2]["assetId"]))
    return [summary(group, row) for points, group, row in ranked[:limit] if points]


def rights(row):
    record = row.get("rights")
    return {**record, "notice": "site/visual/" + record["notice"]} if record else None


def render_template(name, data):
    source = (LIBRARY / name).read_text(encoding="utf8")
    payload = json.dumps(data, ensure_ascii=False).replace("<", r"\u003c")
    return source.replace("__SCENE__", payload, 1)


def image_uri(path):
    mime = "image/svg+xml" if path.endswith(".svg") else "image/png"
    data = base64.b64encode((LIBRARY / path).read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def scene(group, row, args):
    kit = row if group == "practice" else None
    _, demo, _ = lookup(args.demo or kit["demos"][0], "demos") if kit else (group, row, None)
    if args.demo and (not kit or demo["assetId"] not in kit["demos"]):
        raise ValueError("这套搭配中没有所选动作。")
    lesson = demo["kind"] == "lesson"
    mode = demo.get("scene")
    text = args.label
    if text and not lesson:
        raise ValueError("改字仅适用于口播搭配和 DEMO-010 至 DEMO-015。")
    labels = list(demo.get("labels", []))
    if len(text) > len(labels):
        raise ValueError(f"这个动作有 {len(labels)} 个可修改的文字位置。")
    for index, value in enumerate(text):
        if re.search(r"[「」()（）\x00-\x1f]", value) or len(value.strip()) > 26:
            raise ValueError("每段画面文字最多 26 字，请去掉括号、换行和引号「」。")
        if value.strip():
            labels[index] = value.strip()

    object_key = kit["objects"][0] if kit and mode != "seal" else demo["object"]
    obj = preview.resolve_entry("objects", args.object or object_key)
    if args.object and (not lesson or mode != "focus" or (kit and obj["id"] not in kit["objects"])):
        raise ValueError("选用「圈出一个部位」动作后可替换主体。请选择搭配中的物件。")
    sticker_key = args.sticker if args.sticker is not None else (kit["stickers"][0] if kit else None)
    sticker = preview.resolve_entry("stickers", sticker_key) if sticker_key and sticker_key != "none" else None
    palette = preview.resolve_entry("palettes", args.palette or (kit["palette"] if kit else "atelier"))
    visual = {"objects": obj["id"], "palettes": palette["id"]}
    if sticker:
        visual["stickers"] = sticker["id"]
    html = compose_demo(demo, visual, labels, args.seconds, getattr(args, "quote", None))
    return html, demo, labels, visual


def compose_demo(demo, visual, labels, seconds, quote=None, *, play=True):
    obj = preview.resolve_entry("objects", visual["objects"])
    palette = preview.resolve_entry("palettes", visual["palettes"])
    sticker = preview.resolve_entry("stickers", visual["stickers"]) if visual.get("stickers") else None
    mode = demo.get("scene")
    if demo["kind"] == "lesson":
        data = dict(scene=mode, heading=demo["label"], colors=palette["colors"],
                    seconds=seconds, frames=round(seconds * 25), play=play, labels=labels)
        data["anchor"] = next(iter(obj.get("tokens", {}).get("anchors", {}).values()), [.62, .52])
        if mode == "focus":
            data["picture"] = image_uri(obj["variants"][palette["id"]]["preview"])
        if mode == "wave":
            original = preview.resolve_entry("practice", "compare-wave")["originalWave"]
            data["waveBefore"], data["waveAfter"] = original
        if sticker:
            data["sticker"] = image_uri(sticker["variants"][palette["id"]]["vector"])
        return render_template("lesson-demo.html", data)
    defaults = {"scale": "称重 180 克", "jug": "倒到第 3 条刻度"}
    data, _ = preview.scene_data({
        "treatment": demo["id"], "visual": visual,
        "quote": quote or defaults.get(obj["id"], demo["label"]), "seconds": seconds,
    })
    return render_template("part-demo.html", data)


def annotation(visual=None, demo=None, labels=(), seconds=None, effect=None):
    selected = {key: preview.resolve_entry(key, val) for key, val in (visual or {}).items()}
    palette = selected.get("palettes")
    codes = [asset_code(selected["objects"], palette)] if "objects" in selected else []
    if "stickers" in selected:
        codes.append(asset_code(selected["stickers"], palette))
    if palette:
        codes.append(palette["assetId"])
    codes.extend(row["assetId"] for row in (demo, effect) if row)
    notes = ["字" + "一二三"[i] + "「" + label + "」" for i, label in enumerate(labels) if label]
    if seconds:
        notes.append(f"时长 {seconds} 秒")
    return "（画面：用" + "、".join(codes) + ("。" + "，".join(notes) if notes else "") + "。）"
