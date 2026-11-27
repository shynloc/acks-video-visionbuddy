"""Versioned local storage for personal VisionBuddy materials."""

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4

from personal_media import IMPORT_LIMIT, MEDIA_SCHEMA, WEB_LIMIT, input_options, normalize

CODE = re.compile(r"(?<![A-Z0-9])MY-[A-F0-9]{10}(?:@V\d{4,8})?(?![A-Z0-9@])", re.I)
MEDIA_KEY = re.compile(r"[a-f0-9]{64}")
MAX_SNAPSHOT = 2000
SCHEMA = """
CREATE TABLE IF NOT EXISTS revisions (
    id TEXT NOT NULL, version INTEGER NOT NULL, blob TEXT NOT NULL,
    record TEXT NOT NULL, PRIMARY KEY (id, version)
)
"""


def root():
    custom = os.environ.get("VISIONBUDDY_LIBRARY_DIR")
    if custom:
        return Path(custom).expanduser().resolve()
    if os.name == "nt":
        local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    elif sys.platform == "darwin":
        local = Path.home() / "Library/Application Support"
    else:
        local = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return (local / "VisionBuddy" / "我的素材").resolve()


def database():
    return root() / "library.sqlite3"


def reference(asset_id, version):
    return f"{asset_id}@V{version:04d}"


def parse_ref(code):
    if not isinstance(code, str) or not CODE.fullmatch(code.strip()):
        raise ValueError("个人素材编号无效。")
    asset, _, version = code.strip().upper().partition("@V")
    if version and int(version) < 1:
        raise ValueError("个人素材版本无效。")
    return asset, int(version) if version else None


def normalized_record(row):
    item = json.loads(row[3])
    return {**item, "assetId": row[0], "version": row[1], "blob": row[2], "ref": reference(row[0], row[1])}


def list_heads():
    path = database()
    if not path.is_file():
        return []
    with closing(sqlite3.connect(path)) as connection:
        records = connection.execute("""
            SELECT r.id,r.version,r.blob,r.record FROM revisions AS r
            JOIN (SELECT id,max(version) AS version FROM revisions GROUP BY id) AS heads
            ON r.id=heads.id AND r.version=heads.version
            ORDER BY r.rowid DESC
        """).fetchall()
    return [normalized_record(row) for row in records]


def revisions(code):
    asset, _ = parse_ref(code)
    path = database()
    if not path.is_file():
        return []
    with closing(sqlite3.connect(path)) as connection:
        rows = connection.execute(
            "SELECT id,version,blob,record FROM revisions WHERE id=? ORDER BY version DESC", (asset,)
        ).fetchall()
    return [normalized_record(row) for row in rows]


def get(code):
    asset, version = parse_ref(code)
    path = database()
    row = None
    if path.is_file():
        sql = "SELECT id,version,blob,record FROM revisions WHERE id=?"
        with closing(sqlite3.connect(path)) as connection:
            if version is None:
                row = connection.execute(sql + " ORDER BY version DESC LIMIT 1", (asset,)).fetchone()
            else:
                row = connection.execute(sql + " AND version=?", (asset, version)).fetchone()
    if row is None:
        raise ValueError(f"本机素材库找不到 {code}。旧工程需要相应的版本。")
    return normalized_record(row)


def snapshot(source, fresh=False):
    if fresh or "personalSnapshot" not in source:
        return list_heads() if fresh else []
    refs = source["personalSnapshot"]
    if (not isinstance(refs, list) or len(refs) > MAX_SNAPSHOT
            or any(not isinstance(ref, str) or not CODE.fullmatch(ref) or "@V" not in ref for ref in refs)):
        raise ValueError("个人素材版本清单无效。")
    if not refs:
        return []
    path = database()
    if not path.is_file():
        raise ValueError("找不到工程使用的本机素材库。请恢复原素材目录。")
    found = {}
    with closing(sqlite3.connect(path)) as connection:
        for ref in refs:
            asset, version = parse_ref(ref)
            entry = connection.execute(
                "SELECT id,version,blob,record FROM revisions WHERE id=? AND version=?", (asset, version),
            ).fetchone()
            if entry is None:
                raise ValueError(f"找不到旧工程使用的 {ref}。请恢复对应的个人素材版本。")
            found[asset] = normalized_record(entry)
    if len(found) != len(refs):
        raise ValueError("工程只能为每款个人素材指定一个推荐版本。")
    return list(found.values())


def asset_dir(record):
    key = record["blob"]
    if not MEDIA_KEY.fullmatch(key):
        raise ValueError("个人素材文件编号损坏。")
    path = root() / "media" / key
    if not path.is_dir():
        raise ValueError(f"{record['ref']} 的本机文件缺失。")
    return path


def original_path(record):
    return asset_dir(record) / ("original" + record["suffix"])


def text(entry, key, limit, required=False):
    raw = entry.get(key, "")
    if not isinstance(raw, str) or len(raw) > limit or "\0" in raw:
        raise ValueError(f"登记字段长度无效，最多 {limit} 字。")
    clean = raw.strip()
    if required and not clean:
        raise ValueError("请填写素材名称和用途。")
    return clean


def rows_for_metadata(options, filename):
    name = text(options, "name", 96) or (Path(filename).stem[:96] if filename else "")
    if not name:
        raise ValueError("请填写素材名称。")
    keywords = list(dict.fromkeys(term.strip() for term in re.split(r"[,，、;；\n]", text(options, "keywords", 420))
                                  if term.strip()))
    if len(keywords) > 24 or any(len(term) > 48 for term in keywords):
        raise ValueError("最多填写 24 个关键词，每个不超过 48 字。")
    return {
        "name": name, "uses": text(options, "uses", 640, True), "keywords": keywords,
        "rights": {"author": text(options, "author", 160),
                   "license": text(options, "license", 360),
                   "origin": text(options, "origin", 300)},
    }


def digest_file(path):
    check = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            check.update(chunk)
    return check.hexdigest()


def save(options, original=None, filename=None, code=None):
    if not isinstance(options, dict):
        raise ValueError("请提交素材登记信息。")
    existing = get(code) if code else None
    asset = existing["assetId"] if existing else "MY-" + uuid4().hex[:10].upper()
    if not original and existing is None:
        raise ValueError("请先选择要导入的文件。")
    if existing and code and parse_ref(code)[1] is None:
        raise ValueError("换版时请指定正在编辑的具体版本。")
    filename = text({"name": filename or (existing["originalName"] if existing else "")}, "name", 260)
    filename = filename.replace("\\", "/").rsplit("/", 1)[-1]
    if not filename:
        raise ValueError("无法识别文件名。")
    record = rows_for_metadata(options, filename)
    record["originalName"] = filename
    record["created"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if original is None:
        blob = existing["blob"]
        record.update(suffix=existing["suffix"], sourceSha256=existing["sourceSha256"], media=existing["media"])
    else:
        record["suffix"] = Path(filename).suffix.lower()
        if original.suffix.lower() != record["suffix"]:
            # Uploads are staged with the filename's approved suffix by the local API.
            raise ValueError("导入文件的扩展名与登记项不一致。")
        prepared = input_options(record["suffix"], options)
        limit = WEB_LIMIT if prepared["kind"] in ("svg", "html") else IMPORT_LIMIT
        if not 0 < original.stat().st_size <= limit:
            raise ValueError(f"所选格式的文件大小需在 {limit // (1024**2)} MB 以内。")
        source_digest = digest_file(original)
        blob = hashlib.sha256(json.dumps([MEDIA_SCHEMA, source_digest, record["suffix"], prepared],
                                         sort_keys=True).encode("utf8")).hexdigest()
        record["sourceSha256"] = source_digest
        base = root() / "media"
        base.mkdir(parents=True, exist_ok=True)
        final = base / blob
        if not final.exists():
            with TemporaryDirectory(dir=base, prefix=".import-") as stage:
                incoming = Path(stage) / "content"
                incoming.mkdir()
                saved = incoming / ("original" + record["suffix"])
                shutil.copyfile(original, saved)
                if digest_file(saved) != source_digest:
                    raise ValueError("导入期间原文件发生变化，请重新选择。")
                info = normalize(saved, incoming, prepared)
                (incoming / "media.json").write_text(json.dumps(info), encoding="utf8")
                parent = base.resolve()
                if not incoming.resolve().is_relative_to(parent) or final.resolve().parent != parent:
                    raise ValueError("个人素材存储路径无效。")
                try:
                    incoming.rename(final)
                except OSError:
                    if not final.is_dir() or not (final / "media.json").is_file():
                        raise
        record["media"] = json.loads((final / "media.json").read_bytes())
    path = database()
    path.parent.mkdir(parents=True, exist_ok=True)
    version = 1
    with closing(sqlite3.connect(path, timeout=10)) as connection, connection:
        connection.execute(SCHEMA)
        connection.execute("BEGIN IMMEDIATE")
        if existing:
            head = connection.execute("SELECT max(version) FROM revisions WHERE id=?", (asset,)).fetchone()[0]
            if head != existing["version"]:
                raise ValueError("该素材已有更新版本。刷新后从最新版换版。")
            version = head + 1
        connection.execute("INSERT INTO revisions VALUES (?,?,?,?)",
                           (asset, version, blob, json.dumps(record, ensure_ascii=False)))
    return {**record, "assetId": asset, "version": version, "blob": blob, "ref": reference(asset, version)}


def search(query, entries=None):
    if entries is None:
        entries = list_heads()
    if not isinstance(query, str) or len(query) > 120_000:
        raise ValueError("请输入名称、用途或个人素材编号。")
    q = re.sub(r"\s+", " ", query.strip().casefold())
    if not q:
        return [(0, "", item) for item in entries]
    if CODE.fullmatch(q):
        asset, version = parse_ref(q)
        return [(1000, item["name"], item) for item in entries
                if item["assetId"] == asset and (version is None or item["version"] == version)]
    ranked = []
    for item in entries:
        name = item["name"].casefold()
        terms = [name, *[part.casefold() for part in item["keywords"]]]
        terms.extend(part.strip().casefold() for part in re.split(r"[、,，。；;\n]", item["uses"]))
        matches = [term for term in terms if len(term) >= 2 and term in q]
        if matches:
            hit = max(matches, key=len)
            ranked.append((100 + min(len(hit), 30), hit, item))
        elif len(q) >= 2 and any(q in term for term in terms if term):
            ranked.append((70 + min(len(q), 30), q, item))
    return sorted(ranked, key=lambda row: (-row[0], row[2]["assetId"]))
