"""Build and review local visual suggestions in source sentence order."""

from bisect import bisect_left
from functools import lru_cache
import re

import desk_inputs as inputs
import personal_store as personal
import serve
import skill_catalog as catalog

FORMAT = "visionbuddy-plan/1"
WORDS = re.compile(r"字([一二三])「([^」]{1,26})」")
LENGTH = re.compile(r"时长\s*(\d+)\s*秒")
CUE = re.compile(r"说到\s*[「『“]([^」』”]+)[」』”]")
NUMBER = r"-?\d+(?:\.\d+)?"
NUMBERS = re.compile(r"(?<![\d.])" + NUMBER)
FROM_TO = re.compile(r"(?:从|由)\s*(" + NUMBER + r")[^。.！？?！]{0,14}?(?:到|至|为)\s*(" + NUMBER + ")")
SEARCH_FORMS = str.maketrans("傳開關聲後對較數變點檔這啟狀與從減設步清", "传开关声后对较数变点档这启状与从减设步清")
LAYOUT = {"side": "right", "scale": 0.40}
OVERLAY_EFFECTS = set("""
fade lift slide pop zoomIn blurIn swingIn wipe irisIn vanish drop shrink spinOut
closewipe irisOut pulse tilt float breathe spin pendulum trail
""".split())


def asset_recipe(codes, quote, notes=""):
    visual, effects, slots = {}, [], set()
    demo = kit = palette = None
    for code in codes:
        group, row, shade = catalog.lookup(code)
        if shade:
            if palette and shade["id"] != palette["id"]:
                raise ValueError("这处标注指定了不同的配色，请保留一套。")
            palette = shade
        if group == "palettes":
            if palette and palette["id"] != row["id"]:
                raise ValueError("这处标注指定了不同的配色，请保留一套。")
            palette = row
        elif group in ("objects", "stickers", "styles"):
            if visual.get(group, row["id"]) != row["id"]:
                raise ValueError("一处画面请保留一个同类素材。")
            visual[group] = row["id"]
        elif group == "demos":
            if demo:
                raise ValueError("一处画面请保留一个演示。")
            demo = row
        elif group == "practice":
            if kit:
                raise ValueError("一处画面请保留一套口播搭配。")
            kit = row
        elif group == "effects":
            slot = "demo" if row.get("foreground") else row["group"]
            if slot in slots:
                raise ValueError("一处画面有两个作用相同的动效。")
            slots.add(slot)
            effects.append(row)
        else:
            raise ValueError("这个编号是网页交互组件，可在素材册中单独查看。")

    alternate_demo = bool(kit and demo)
    if kit:
        if demo and demo["assetId"] not in kit["demos"]:
            raise ValueError("所选动作不属于指定的口播搭配。")
        demo = demo or catalog.lookup(kit["demos"][0], "demos")[1]
        visual.setdefault("objects", demo["object"] if demo.get("scene") == "seal" else kit["objects"][0])
        visual.setdefault("stickers", kit["stickers"][0])
    if demo:
        if effects:
            raise ValueError("演示已经带动作，请保留演示或通用动效中的一种。")
        visual.setdefault("objects", demo["object"])
        if (demo["kind"] != "lesson" or demo.get("scene") == "seal") and visual["objects"] != demo["object"]:
            raise ValueError("这个演示需要目录中对应的物件。")
    if not (visual.get("objects") or visual.get("stickers") or effects):
        raise ValueError("配色、网页样式需要搭配物件、贴纸或动效才能导出透明画面。")
    if (visual.get("objects") or visual.get("stickers")) and any(row["id"] not in OVERLAY_EFFECTS for row in effects):
        raise ValueError("这项动效无法套在整张物件或贴纸上。")
    visual["palettes"] = palette["id"] if palette else kit["palette"] if kit else "atelier"

    length = LENGTH.search(notes)
    seconds = int(length[1]) if length else 3
    if not 1 <= seconds <= 12:
        raise ValueError("画面时长须为 1 至 12 秒。")
    cue = CUE.search(notes)
    if cue and quote.count(cue[1]) != 1:
        raise ValueError("「说到」后面的引文须在对应原句中恰好出现一次。")
    labels = list(demo.get("labels", [])) if demo else []
    if demo and demo.get("scene") == "number":
        values = comparison_numbers(quote)
        labels = [*values[:2], numeric_unit(quote, values[1])] if len(values) >= 2 else ["变化前", "变化后", ""]
    for slot, value in WORDS.findall(notes):
        index = "一二三".index(slot)
        if index < len(labels):
            labels[index] = value
    main = kit or demo or (effects[0] if effects else catalog.lookup(
        visual.get("objects") or visual["stickers"], "objects" if "objects" in visual else "stickers")[1])
    display = catalog.title(demo if alternate_demo else main)
    if palette:
        display += " · " + palette["name"]
    return {
        "title": display, "codes": codes, "visual": visual,
        "versionReason": demo["description"] if alternate_demo else "",
        "effects": [entry["id"] for entry in effects], "treatment": demo["id"] if demo else "",
        "kit": kit["assetId"] if kit else "", "labels": labels, "seconds": seconds,
        "fixedSeconds": bool(length), "cue": cue[1] if cue else "",
        "animated": bool(effects or (demo and demo["kind"] != "still")),
        "aspect": [8, 3] if effects else [56, 33],
    }


def comparison_numbers(quote):
    comparable = quote.translate(SEARCH_FORMS)
    if match := FROM_TO.search(comparable):
        return list(match.groups())
    values = NUMBERS.findall(comparable)
    return values if len(values) == 2 else []


def numeric_unit(quote, last_value):
    match = re.search(r"(?<![\d.])" + re.escape(last_value) + r"\s*(%|％|毫秒|秒|分钟|小时|毫升|升|克|公斤|元|倍|厘米|米|毫米|分贝|帧|度|dB|ms|fps)", quote)
    return match[1].replace("％", "%") if match else ""


@lru_cache(maxsize=1)
def named_objects():
    aliases = {
        "adapterhub": ("转接头", "扩展坞", "拓展坞"),
        "laptop": ("笔记本",),
        "headphones": ("头戴耳机", "耳麦"),
        "powerstrip": ("排插", "插线板"),
        "usbc": ("USB-C 线", "数据线"),
    }
    return tuple((item, {item["name"], item["name"][-3:], *aliases.get(item["id"], ())})
                 for item in catalog.groups()["objects"])


def object_mention(quote):
    if not re.search(r"看|打开|转动|点|调|连接|插|放|装|拆|测|侧面|底部|顶部|接口", quote):
        return None
    direct = re.search(r"(?:把|将)(.{1,18}?)(?:插|放|装|拿|拨|按|固定|移到)", quote)
    subject = direct[1] if direct else ""
    matches = [(len(name) + 20 * (name in subject), item) for item, names in named_objects()
               for name in names if len(name) >= 3 and name in quote]
    if not matches:
        return None
    score = max(length for length, _item in matches)
    top = {item["assetId"]: item for length, item in matches if length == score}
    return next(iter(top.values())) if len(top) == 1 else None


def automatic(row):
    original = row["quote"]
    quote = original.translate(SEARCH_FORMS)
    if re.search(r"^(?:大家好|今天(?:给大家|我来|聊聊)|欢迎|感谢|我是|最后感谢|下期再见)", quote):
        return None
    part = next((item for item in catalog.groups()["demos"] if item.get("subjects")
                 and any(word in quote for word in item["subjects"])
                 and any(word in quote for word in item["cues"])), None)
    if re.search(r"密封圈|密封罐", quote) and re.search(r"取|打开|拆|装|清洗", quote):
        offer = (9, "拆开盖子和密封圈，帮助看清部件和操作先后。", [("KIT-001",), ("KIT-001", "DEMO-015")])
    elif (re.search(r"降噪|波形|键盘声", quote) and re.search(r"前后|对比|声音|波形|变|差", quote)
          and not comparison_numbers(quote)):
        offer = (9, "用同尺度的示意波形把两种声音状态并排展示。", [("KIT-002",), ("FX-013",)])
    elif re.search(r"上传|文件传好了|同步完成|同步好了|\bupload(?:ed|ing)?\b", quote, re.I):
        offer = (8, "用进度到勾选的变化指出操作完成的位置。", [("KIT-003",), ("KIT-003", "PAL-015")])
    elif part:
        offer = (9, part["description"], [(part["assetId"],), (part["assetId"], "PAL-015")])
    elif re.search(r"从.+到|降到|升到|增加|减少|降为|提升|降低|对比|前后", quote) and comparison_numbers(quote):
        offer = (9, "用原句里的两个数值显示变化。", [("DEMO-014",), ("DEMO-014", "PAL-015")])
    elif re.search(r"前后|对比|相比|变成|有什么区别", quote):
        offer = (6, "把前后状态并排摆放，方便跟上对比。", [("FX-013",), ("FX-014",)])
    elif re.search(r"先.{1,45}(?:再|然后)|第一步|第二步|接下来.{1,25}(?:再|然后)", quote):
        offer = (6, "按原句顺序依次亮出操作步骤。", [("FX-011",), ("FX-011", "PAL-015")])
    elif item := object_mention(quote):
        code = item["assetId"]
        offer = (5, f"叠加「{item['name']}」的小图，让物件与这句操作对应。", [(code,), (code, "FX-001")])
    else:
        return None
    priority, reason, versions = offer
    candidates = [asset_recipe(list(codes), original) for codes in versions]
    if "同步" in quote:
        for candidate in candidates:
            if candidate["treatment"] == "lesson-status":
                candidate["labels"] = ["正在同步", "同步完成"]
    return priority, reason, candidates


def personal_recipe(item, notes="", quote=""):
    media = item["media"]
    cue = CUE.search(notes)
    if cue and quote.count(cue[1]) != 1:
        raise ValueError("「说到」后面的引文须在对应原句中恰好出现一次。")
    length = LENGTH.search(notes)
    seconds = int(length[1]) if length else media["seconds"] or 3
    if not 0 < seconds <= 12:
        raise ValueError("画面时长须在 12 秒以内。")
    if media["frames"] > 1:
        seconds = min(seconds, media["seconds"])
    return {
        "title": item["name"], "codes": [item["ref"]], "personal": item["ref"], "visual": {},
        "effects": [], "treatment": "", "kit": "", "labels": [], "seconds": seconds,
        "fixedSeconds": bool(length) or media["frames"] > 1, "originalSeconds": media["seconds"],
        "cue": cue[1] if cue else "", "animated": media["frames"] > 1,
        "aspect": [media["width"], media["height"]], "poster": media["poster"],
        "totalFrames": media["frames"], "versionReason": "",
    }


def bound_recipe(notes, quote, versions, *, public_only=False):
    joined = " ".join(notes)
    text = WORDS.sub("", joined)
    codes = list(dict.fromkeys(match[0].upper() for match in sorted(
        [*catalog.CODE.finditer(text), *personal.CODE.finditer(text)], key=lambda hit: hit.start()
    )))
    if not codes:
        raise ValueError("没找到素材编号，请检查这条画面标注。")
    if any(code.startswith("MY-") for code in codes):
        if public_only:
            raise ValueError("个人素材请在本机 VisionBuddy 中使用。")
        if len(codes) != 1:
            raise ValueError("这一句请选择一个个人编号，或一组公共库素材。")
        code = codes[0]
        if "@V" in code:
            return personal_recipe(personal.get(code), joined, quote)
        if code not in versions:
            raise ValueError(f"找不到工程里已登记的 {code}。可指定它的完整版本编号。")
        return personal_recipe(versions[code], joined, quote)
    return asset_recipe(codes, quote, joined)


def recommend(row, entries):
    public = automatic(row)
    matches = personal.search(row["quote"], entries)
    if not matches:
        return public
    _, hit, primary = matches[0]
    reason = f"「{primary['name']}」的登记用途与原句中的「{hit}」匹配。"
    candidates = [{**personal_recipe(primary), "versionReason": reason}]
    if public:
        candidates.extend({**item, "versionReason": item["versionReason"] or public[1]} for item in public[2][:2])
    else:
        candidates.extend({**personal_recipe(item), "versionReason": f"关键词「{term}」与这句口播匹配。"}
                          for _, term, item in matches[1:3])
    return 11, reason, candidates


def default_place(row, candidate, duration):
    place = dict(LAYOUT)
    if row["time"] is None:
        return place
    begin, end = (row["time"][k] for k in ("start", "end"))
    if candidate["cue"]:
        for unit in row["parts"]:
            if candidate["cue"] in unit["quote"]:
                begin = unit["time"]["start"]
                break
    if candidate.get("personal") and candidate["animated"]:
        end = (begin + candidate["seconds"] if row["notes"] and LENGTH.search(" ".join(row["notes"]))
               else min(end, begin + candidate["seconds"]))
    else:
        end = begin + candidate["seconds"] if candidate["fixedSeconds"] else min(end, begin + 12)
    if duration is not None:
        end = min(end, duration)
    place.update(start=begin, end=round(end, 3))
    return place


def validate_review_snapshot(review):
    if not isinstance(review, dict) or len(review) > 5:
        raise ValueError("便携工程的备选画面格式无效。")
    for key, row in review.items():
        if not re.fullmatch(r"r\d{4}", key) or not isinstance(row, dict):
            raise ValueError("便携工程的备选原句无效。")
        choices = row.get("candidates")
        if (not isinstance(row.get("reason"), str) or len(row["reason"]) > 640
                or not isinstance(choices, list) or not 1 <= len(choices) <= 3):
            raise ValueError("便携工程的候选资料不完整。")
        for item in choices:
            if not isinstance(item, dict):
                raise ValueError("便携工程的候选画面格式无效。")
            codes, labels, reason = (item.get(key) for key in ("codes", "labels", "versionReason"))
            if (not isinstance(codes, list) or not 1 <= len(codes) <= 8
                    or any(not isinstance(code, str) or not (catalog.CODE.fullmatch(code) or personal.CODE.fullmatch(code))
                           for code in codes)
                    or not isinstance(labels, list) or len(labels) > 3
                    or any(not isinstance(label, str) or len(label) > 26 for label in labels)
                    or not isinstance(reason, str) or len(reason) > 640):
                raise ValueError("便携工程的候选编号或文字无效。")
    return review


def thaw_offer(row, frozen):
    choices = []
    for item in frozen["candidates"]:
        codes = item["codes"]
        if len(codes) == 1 and personal.CODE.fullmatch(codes[0]):
            choice = personal_recipe(personal.get(codes[0]))
        else:
            choice = asset_recipe(codes, row["quote"])
        if len(item["labels"]) != len(choice["labels"]):
            raise ValueError("便携工程的候选文字与素材不一致。")
        choices.append({**choice, "labels": item["labels"], "versionReason": item["versionReason"]})
    return choices


def build(source, *, fresh=False, public_only=False):
    original = source
    source, cues = inputs.input_source(source)
    frozen = None if fresh or "reviewSnapshot" not in original else validate_review_snapshot(original["reviewSnapshot"])
    if public_only and (original.get("personalSnapshot") or any(
            personal.CODE.fullmatch(code)
            for row in (frozen or {}).values() for item in row["candidates"] for code in item["codes"])):
        raise ValueError("带有个人素材的审核工程请在本机 VisionBuddy 中打开。")
    if frozen is not None:
        source["reviewSnapshot"] = frozen
    entries = [] if public_only else personal.snapshot(original, fresh)
    if entries or "personalSnapshot" in original:
        source["personalSnapshot"] = [entry["ref"] for entry in entries]
    versions = {entry["assetId"]: entry for entry in entries}
    clean, units, bindings, warnings = inputs.manuscript(source, cues)
    if not units or len(units) > inputs.CUE_LIMIT:
        raise ValueError("请提供 1 至 4000 句可读的口播正文。")
    by_first = {binding["sentences"][0]: binding for binding in bindings}
    rows, ranked = [], []
    i = 0
    supplementary = [n for n, c in enumerate(clean) if ord(c) > 0xFFFF]
    while i < len(units):
        binding = by_first.get(i)
        notes = binding["notes"] if binding else []
        last = binding["sentences"][-1] if binding else i
        parts = units[i:last + 1]
        offset = parts[0]["offset"]
        end = parts[-1]["offset"] + len(parts[-1]["quote"])
        quote = clean[offset:end]
        time = None
        if cues is not None:
            time = {"start": parts[0]["time"]["start"], "end": max(part["time"]["end"] for part in parts)}
        row = {
            "id": f"r{len(rows) + 1:04}", "quote": quote,
            "offset": offset + bisect_left(supplementary, offset), "parts": parts, "time": time,
            "notes": notes, "mode": "plain", "reason": "", "candidates": [],
        }
        if notes:
            if all(note in {"无", "无。"} for note in notes):
                row.update(mode="none", reason="稿内已指定纯口播。")
            else:
                try:
                    if any(not note or note in {"无", "无。"} for note in notes):
                        raise ValueError("画面标注不完整，或同时指定了素材与纯口播。")
                    recipe = bound_recipe(notes, quote, versions, public_only=public_only)
                    row.update(mode="fixed", reason="沿用稿内指定的素材。", candidates=[recipe])
                except ValueError as exc:
                    row.update(mode="blocked", reason=str(exc))
        elif frozen is not None:
            if entry := frozen.get(row["id"]):
                row.update(mode="auto", reason=entry["reason"], candidates=thaw_offer(row, entry))
        elif match := recommend(row, entries):
            ranked.append((*match, row))
        rows.append(row)
        i = last + 1

    if frozen is not None and {row["id"] for row in rows if row["mode"] == "auto"} != set(frozen):
        raise ValueError("便携工程的候选画面与原句不匹配。")
    seen = set()
    for _points, reason, candidates, row in sorted(ranked, key=lambda item: -item[0]):
        strongest = candidates[0]["codes"][0]
        if strongest in seen:
            continue
        seen.add(strongest)
        row.update(mode="auto", reason=reason, candidates=candidates)
        if len(seen) == 5:
            break
    for row in rows:
        for choice in row["candidates"]:
            choice["placement"] = default_place(row, choice, source.get("duration"))
    return {"format": FORMAT, "libraryRelease": serve.VERSION, "source": source, "spoken": clean,
            "rows": rows, "warnings": warnings}


def validated_plan(raw):
    if not isinstance(raw, dict) or raw.get("format") != FORMAT or raw.get("libraryRelease") != serve.VERSION:
        raise ValueError("审核稿使用了不同的素材版本，请在对应版本打开。")
    return build(raw.get("source"))


def candidate_at(plan, row_id, index):
    row = next((row for row in plan["rows"] if row["id"] == row_id), None)
    if row is None or type(index) is not int or not 0 <= index < len(row["candidates"]):
        raise ValueError("找不到所选原句的画面版本。")
    return row, row["candidates"][index]


def review_choices(plan, decisions):
    if not isinstance(decisions, dict):
        raise ValueError("审核选择格式无效。")
    approved = []
    summaries = []
    duration = plan["source"].get("duration")
    for row in plan["rows"]:
        selected = decisions.get(row["id"], {})
        if not isinstance(selected, dict):
            raise ValueError("审核选择格式无效。")
        state = selected.get("state", "adopted" if row["mode"] == "fixed" else "pending")
        choice = selected.get("choice", 0)
        if state not in ("adopted", "skipped", "pending"):
            raise ValueError("找不到这条审核状态。")
        summary = {k: row[k] for k in ("id", "quote", "time", "notes", "mode")}
        summary.update(state=row["mode"] if not row["candidates"] else state)
        summaries.append(summary)
        if state != "adopted" or not row["candidates"]:
            continue
        if type(choice) is not int or not 0 <= choice < len(row["candidates"]):
            raise ValueError("选择的替代版本已经无效，请重新试看。")
        candidate = row["candidates"][choice]
        place = {**candidate["placement"], **{key: selected[key] for key in ("side", "scale", "start", "end")
                                               if key in selected}}
        if place["side"] not in ("left", "right") or not inputs.real_number(place["scale"]) or not .20 <= place["scale"] <= .65:
            raise ValueError("画面位置或缩放无效。")
        if row["time"] is not None:
            start, end = place["start"], place["end"]
            if (not inputs.real_number(start) or not inputs.real_number(end) or not 0 <= start < end or end - start > 12.001
                    or (duration is not None and end > duration + .002)):
                raise ValueError(f"「{row['quote'][:24]}」的摆放区间无效。请选择视频内且不超过 12 秒的区间。")
            if candidate.get("personal") and candidate["animated"] and end - start > candidate["originalSeconds"] + .002:
                raise ValueError(f"「{row['quote'][:24]}」的摆放区间不能长于所选个人素材。")
        else:
            place.pop("start", None)
            place.pop("end", None)
        approved.append((row, candidate, place, summary))
    if not 1 <= len(approved) <= 64:
        raise ValueError("请采用 1 至 64 条画面再一起导出。")
    return approved, summaries
