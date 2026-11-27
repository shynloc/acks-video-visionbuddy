"""Portable review projects and explicitly selected personal-material bundles."""

from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import sqlite3
from tempfile import TemporaryDirectory
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

import personal_store as store
from personal_media import IMPORT_LIMIT, MOV_LIMIT, TYPES, WEB_LIMIT

PROJECT = "visionbuddy-project-bundle/1"
TEAM = "visionbuddy-personal-bundle/1"
PROJECT_FORMAT = "visionbuddy-project/1"
MANIFEST = "VisionBuddy-便携清单.json"
PROJECT_FILE = "审核工程.json"
LIMIT = 512 * 1024**2
HEADER = 4 * 1024**2
ASSET_PREFIX = "个人素材库/media/"
ROW_CODE = re.compile(r"r\d{4}")
META_KEYS = frozenset({"name", "uses", "keywords", "rights", "originalName", "created",
                       "suffix", "sourceSha256", "media"})


def text(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def hash_value(data):
    return hashlib.sha256(text(data).encode("utf8")).hexdigest()


def profile(plan):
    profile = {}
    refs = set()
    for row in plan["rows"]:
        for candidate in row["candidates"]:
            if candidate.get("personal"):
                refs.add(candidate["personal"])
        if row["mode"] == "auto":
            profile[row["id"]] = {
                "reason": row["reason"],
                "candidates": [{key: candidate[key] for key in ("codes", "labels", "versionReason")}
                               for candidate in row["candidates"]],
            }
    return profile, refs


def project_for(plan, state):
    offers, refs = profile(plan)
    source = dict(plan["source"])
    source["personalSnapshot"] = [ref for ref in source.get("personalSnapshot", []) if ref in refs]
    source["reviewSnapshot"] = offers
    project = {"format": PROJECT_FORMAT, "libraryRelease": plan["libraryRelease"], "source": source,
               "decisions": state.get("decisions", {})}
    for key in ("selected", "mode", "recording"):
        if state.get(key) is not None:
            project[key] = state[key]
    validate_project_shape(project)
    return project, sorted(refs)


def paths_for(record):
    files = {"original" + record["suffix"], "media.json", "poster.png", "preview.webp"}
    proof = record["media"].get("proof")
    if proof:
        files.add("master.mov")
        files.update(f"proof-{i:02}.webp" for i in range(math.ceil(proof["count"] / 16)))
    return files


def file_manifest(folder, names):
    return {name: {"size": (folder / name).stat().st_size, "sha256": store.digest_file(folder / name)}
            for name in sorted(names)}


def write_assets(bundle, kind, refs, project=None):
    records, blobs = [], {}
    if len(refs) > 128:
        raise ValueError("每个便携包最多包含 128 个个人素材版本。")
    for ref in dict.fromkeys(refs):
        record = store.get(ref)
        records.append(record)
        key = record["blob"]
        if key in blobs:
            continue
        folder = store.asset_dir(record)
        files = file_manifest(folder, paths_for(record))
        if sum(info["size"] for group in [*blobs.values(), files] for info in group.values()) > LIMIT:
            raise ValueError("便携素材超过 512 MB，请分成较小的素材包。")
        blobs[key] = files
        for name in files:
            bundle.write(folder / name, ASSET_PREFIX + key + "/" + name)
    manifest = {"format": kind, "records": records, "blobs": blobs}
    if project is not None:
        payload = text(project).encode("utf8")
        manifest["projectSha256"] = hashlib.sha256(payload).hexdigest()
        bundle.writestr(PROJECT_FILE, payload)
    raw = text(manifest).encode("utf8")
    if len(raw) > HEADER:
        raise ValueError("便携包清单过大。")
    bundle.writestr(MANIFEST, raw)


def archive_to(path, kind, refs, project=None):
    path = path.resolve()
    if path.suffix.lower() != ".zip" or path.exists():
        raise ValueError("请指定一个尚未存在的 .zip 文件。")
    with TemporaryDirectory(prefix="visionbuddy-portable-") as temp:
        archive = Path(temp) / "portable.zip"
        with ZipFile(archive, "w", ZIP_DEFLATED, compresslevel=2) as bundle:
            write_assets(bundle, kind, refs, project)
        if archive.stat().st_size > LIMIT:
            raise ValueError("便携包超过 512 MB，请分包保存。")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as dest, archive.open("rb") as src:
            try:
                shutil.copyfileobj(src, dest)
            except OSError:
                dest.close()
                path.unlink()
                raise
    return {"output": str(path), "versions": len(refs)}


def save_project(plan, state, output):
    project, refs = project_for(plan, state)
    return archive_to(output, PROJECT, refs, project)


def save_team(refs, output):
    if not isinstance(refs, list) or not 1 <= len(refs) <= 128 or any(not isinstance(ref, str) for ref in refs):
        raise ValueError("请选择要分享的个人素材版本。")
    chosen = list(dict.fromkeys(store.get(ref)["ref"] for ref in refs))
    return archive_to(output, TEAM, chosen)


def valid_number(number, low, high):
    return type(number) in (float, int) and math.isfinite(number) and low <= number <= high


def validate_record(record):
    if not isinstance(record, dict) or set(record) != META_KEYS | {"assetId", "version", "blob", "ref"}:
        raise ValueError("便携包中的素材登记字段无效。")
    ref = record["ref"]
    asset, version = store.parse_ref(ref)
    if not version or record["assetId"] != asset or record["version"] != version or ref != store.reference(asset, version):
        raise ValueError("便携包中的个人素材版本无效。")
    for key in ("blob", "sourceSha256"):
        if not isinstance(record[key], str) or not store.MEDIA_KEY.fullmatch(record[key]):
            raise ValueError("便携包中的素材校验编号无效。")
    limits = {"name": 96, "uses": 640, "originalName": 260, "created": 64}
    for key, limit in limits.items():
        if not store.text(record, key, limit, required=True):
            raise ValueError("便携包中的名称或原件信息无效。")
    if any(char in record["originalName"] for char in ("/", "\\", "\0")):
        raise ValueError("便携包中的原件名称无效。")
    rights = record["rights"]
    if not isinstance(rights, dict) or set(rights) != {"author", "license", "origin"}:
        raise ValueError("便携包中的授权记录无效。")
    for key, limit in (("author", 160), ("license", 360), ("origin", 300)):
        store.text(rights, key, limit)
    tags = record["keywords"]
    if (not isinstance(tags, list) or len(tags) > 24
            or any(not isinstance(tag, str) or not 0 < len(tag) <= 48 for tag in tags)):
        raise ValueError("便携包中的素材关键词无效。")
    suffix, media = record["suffix"], record["media"]
    if not isinstance(suffix, str) or suffix not in TYPES or not isinstance(media, dict):
        raise ValueError("便携包中的素材格式无效。")
    prepared = media.get("import")
    if not isinstance(prepared, dict) or prepared.get("kind") != TYPES[suffix]:
        raise ValueError("便携包中的素材类型不一致。")
    if any(type(media.get(key)) is not int or not 1 <= media[key] <= high
           for key, high in (("width", 4096), ("height", 4096), ("frames", 300))):
        raise ValueError("便携包中的素材尺寸或帧数无效。")
    frames, proof = media["frames"], media.get("proof")
    if (type(media.get("poster")) is not int or not 0 <= media["poster"] < frames
            or not valid_number(media.get("seconds"), 0, 12)
            or media["seconds"] != (frames / 25 if frames > 1 else 0)):
        raise ValueError("便携包中的素材时长无效。")
    if (frames > 1) != bool(proof):
        raise ValueError("便携包缺少对应的动画小样。")
    if proof and (not isinstance(proof, dict) or any(type(proof.get(key)) is not int or not 1 <= proof[key] <= high
                                                    for key, high in (("count", 96), ("width", 300), ("height", 300)))):
        raise ValueError("便携包中的动画小样尺寸无效。")
    return record


def validate_project_shape(project):
    import desk_inputs
    import serve

    if (not isinstance(project, dict) or project.get("format") != PROJECT_FORMAT
            or project.get("libraryRelease") != serve.VERSION or not isinstance(project.get("decisions"), dict)):
        raise ValueError("审核工程格式或公共素材库版本不匹配。")
    source, _ = desk_inputs.input_source(project.get("source"))
    if len(project["decisions"]) > desk_inputs.CUE_LIMIT:
        raise ValueError("审核工程包含过多选择。")
    for key, value in project["decisions"].items():
        if (not ROW_CODE.fullmatch(key) or not isinstance(value, dict)
                or value.get("state", "pending") not in ("pending", "adopted", "skipped")
                or type(value.get("choice", 0)) is not int or not 0 <= value.get("choice", 0) <= 2):
            raise ValueError("审核工程选择格式无效。")
    if project.get("mode") not in (None, "script", "srt", "video"):
        raise ValueError("审核工程来源无效。")
    return source


def read_struct(bundle, filename, max_size=HEADER):
    if bundle.getinfo(filename).file_size > max_size:
        raise ValueError("便携包清单过大。")
    return json.loads(bundle.read(filename))


def receive_files(bundle, manifest, folder):
    records, blobs = manifest.get("records"), manifest.get("blobs")
    if not isinstance(records, list) or len(records) > 128 or not isinstance(blobs, dict):
        raise ValueError("便携包素材清单无效。")
    records = [validate_record(record) for record in records]
    if len({r["ref"] for r in records}) != len(records):
        raise ValueError("便携包含重复素材版本。")
    media = {}
    for record in records:
        old = media.setdefault(record["blob"], record)
        if old["media"] != record["media"] or old["suffix"] != record["suffix"] or old["sourceSha256"] != record["sourceSha256"]:
            raise ValueError("便携包中同一原件的登记不一致。")
    if set(media) != set(blobs):
        raise ValueError("便携包媒体和登记缺项。")
    total = 0
    members = set()
    for key, record in media.items():
        files = blobs[key]
        if not isinstance(files, dict) or set(files) != paths_for(record):
            raise ValueError("便携包媒体文件不完整。")
        target = folder / key
        target.mkdir()
        for name, check in files.items():
            limit = (WEB_LIMIT if record["suffix"] in (".svg", ".html", ".htm") else IMPORT_LIMIT) if name.startswith("original") else MOV_LIMIT
            if name == "media.json":
                limit = 32768
            if not isinstance(check, dict) or type(check.get("size")) is not int or not 0 < check["size"] <= limit:
                raise ValueError("便携包中的媒体文件大小无效。")
            total += check["size"]
            if total > LIMIT:
                raise ValueError("便携包媒体超过 512 MB。")
            member = ASSET_PREFIX + key + "/" + name
            members.add(member)
            if bundle.getinfo(member).file_size != check["size"]:
                raise ValueError("便携包内媒体大小不一致。")
            output = target / name
            with bundle.open(member) as src, output.open("xb") as dest:
                shutil.copyfileobj(src, dest)
            if store.digest_file(output) != check.get("sha256"):
                raise ValueError("便携包媒体校验失败。")
        if (files["original" + record["suffix"]]["sha256"] != record["sourceSha256"]
                or json.loads((target / "media.json").read_bytes()) != record["media"]):
            raise ValueError("便携包原件和素材台账不一致。")
    if {name for name in bundle.namelist() if name.startswith(ASSET_PREFIX)} != members:
        raise ValueError("便携包包含未登记的个人素材文件。")
    return records, blobs


def locate_blob(key, files, folder, root):
    target = root / key
    suffix = hash_value([key, files])
    for choice in (target, root / suffix):
        if choice.exists():
            if choice.is_dir() and all((choice / k).is_file() for k in files) and file_manifest(choice, files) == files:
                return choice.name
            continue
        if choice.resolve().parent != root.resolve() or not folder.resolve().is_relative_to(root.resolve()):
            raise ValueError("便携素材目录无效。")
        try:
            folder.rename(choice)
            return choice.name
        except OSError:
            if choice.is_dir() and all((choice / k).is_file() for k in files) and file_manifest(choice, files) == files:
                return choice.name
            raise
    raise ValueError("本机有两份校验冲突的素材文件，请检查素材目录。")


def restore_records(records, blobs, folder):
    if not records:
        return {}
    path = store.database()
    root = path.parent / "media"
    root.mkdir(parents=True, exist_ok=True)
    # The staging directory lives under media so promotion is an atomic rename.
    localized = {key: locate_blob(key, files, folder / key, root) for key, files in blobs.items()}
    groups = {}
    for record in records:
        groups.setdefault(record["assetId"], []).append(record)
    remapped = {}
    with closing(sqlite3.connect(path, timeout=10)) as db, db:
        db.execute(store.SCHEMA)
        db.execute("BEGIN IMMEDIATE")
        for asset, versions in groups.items():
            target = asset
            sources = [(record["version"], localized[record["blob"]],
                        {key: record[key] for key in META_KEYS}) for record in versions]
            attempt = 0
            while True:
                collision = False
                for version, blob, metadata in sources:
                    row = db.execute("SELECT blob,record FROM revisions WHERE id=? AND version=?", (target, version)).fetchone()
                    if row and (row[0] != blob or json.loads(row[1]) != metadata):
                        collision = True
                        break
                if not collision:
                    break
                attempt += 1
                target = "MY-" + hash_value([asset, sorted(sources, key=lambda pair: pair[0]), attempt])[:10].upper()
            for version, blob, metadata in sources:
                db.execute("INSERT OR IGNORE INTO revisions VALUES (?,?,?,?)",
                           (target, version, blob, text(metadata)))
                remapped[store.reference(asset, version)] = store.reference(target, version)
    return remapped


def apply_refs(project, refs):
    import manuscript_annotations as annotations

    source = project["source"]
    pinned = {ref.split("@")[0]: ref for ref in source.get("personalSnapshot", [])}

    def change(match):
        code = match[0].upper()
        if code in refs:
            return refs[code]
        old = pinned.get(code, code)
        if old in refs and old != refs[old]:
            return refs[old].split("@")[0]
        return match[0]

    def script(text_value):
        lines = []
        for line in text_value.split("\n"):
            for start, end, _ in reversed(list(annotations.markers(line))):
                line = line[:start] + store.CODE.sub(change, line[start:end]) + line[end:]
            lines.append(line)
        return "\n".join(lines)

    if source["kind"] in ("script", "srt"):
        source["text"] = script(source["text"])
    else:
        for cue in source.get("cues", []):
            cue["text"] = script(cue["text"])
    source["personalSnapshot"] = [refs.get(ref, ref) for ref in source.get("personalSnapshot", [])]
    for row in source.get("reviewSnapshot", {}).values():
        for candidate in row["candidates"]:
            candidate["codes"] = [refs.get(code, code) for code in candidate["codes"]]
    return project


def restore(archive, expected):
    import desk_plan

    try:
        with ZipFile(archive) as bundle:
            names = bundle.namelist()
            if len(names) > 5000 or len({name.casefold() for name in names}) != len(names):
                raise ValueError("便携包包含重复项或过多文件。")
            manifest = read_struct(bundle, MANIFEST)
            if not isinstance(manifest, dict) or manifest.get("format") != expected:
                raise ValueError("请选对应的 VisionBuddy 审核工程包或个人素材包。")
            project = None
            if expected == PROJECT:
                entry = bundle.getinfo(PROJECT_FILE)
                if entry.file_size > HEADER:
                    raise ValueError("审核工程清单过大。")
                raw = bundle.read(PROJECT_FILE)
                if hashlib.sha256(raw).hexdigest() != manifest.get("projectSha256"):
                    raise ValueError("审核工程校验失败。")
                project = json.loads(raw)
                validate_project_shape(project)
                desk_plan.validate_review_snapshot(project["source"].get("reviewSnapshot", {}))
            media = store.root() / "media"
            media.mkdir(parents=True, exist_ok=True)
            with TemporaryDirectory(dir=media, prefix=".receive-") as directory:
                folder = Path(directory)
                records, blobs = receive_files(bundle, manifest, folder)
                if project:
                    unpacked = {record["ref"] for record in records}
                    snapshot = project["source"].get("personalSnapshot", [])
                    if (not isinstance(snapshot, list) or any(not isinstance(ref, str) or ref not in unpacked for ref in snapshot)):
                        raise ValueError("审核工程的个人素材清单缺少版本。")
                    for row in project["source"].get("reviewSnapshot", {}).values():
                        if any(store.CODE.fullmatch(code) and code not in unpacked
                               for item in row["candidates"] for code in item["codes"]):
                            raise ValueError("审核工程的备选画面缺少素材版本。")
                refs = restore_records(records, blobs, folder)
    except (BadZipFile, KeyError, UnicodeError) as exc:
        raise ValueError("找不到完整的 VisionBuddy 便携文件。") from exc
    if project:
        project = apply_refs(project, refs)
        return {"project": project, "plan": desk_plan.build(project["source"]), "versions": refs}
    return {"versions": refs}
