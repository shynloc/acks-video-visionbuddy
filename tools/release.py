"""Build and verify the online manifest and the offline package from one tree."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text(encoding="utf8").strip()
BASELINE = "2e76812314ab9fced11f12d826bd42c7353d55b3"
REPO = "https://github.com/shynloc/acks-video-visionbuddy"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def entries(root=ROOT):
    def read(name):
        return json.loads((root / "site" / name).read_bytes())

    visual = read("visual/catalog.json")
    groups = {
        "effects": read("catalog.json")["terms"],
        **{kind: visual[kind] for kind in ("objects", "stickers", "styles", "palettes")},
        "demos": read("visual/treatments.json"),
        "components": visual.get("components", []),
        "practice": visual.get("practice", []),
    }
    aliases = {}
    for kind, rows in groups.items():
        for row in rows:
            asset_id = row["assetId"]
            if asset_id in aliases:
                raise ValueError(f"重复编号 {asset_id}")
            aliases[asset_id] = {"kind": kind, "legacyId": row["id"]}
            for collection in [row.get("files", {}), *row.get("variants", {}).values()]:
                for name in collection.values():
                    if not (root / "site/visual" / name).is_file():
                        raise ValueError(f"{asset_id} 缺少 {name}")
    return aliases


def manifest():
    files = {
        path.relative_to(ROOT).as_posix(): {"size": path.stat().st_size, "sha256": sha(path.read_bytes())}
        for path in sorted((ROOT / "site").rglob("*")) if path.is_file()
    }
    pair = json.loads((ROOT / "compatibility.json").read_bytes())
    return {
        "schemaVersion": 1, **pair, "libraryRelease": VERSION,
        "baseline": BASELINE, "assets": entries(), "files": files,
    }


def manifest_bytes():
    return (json.dumps(manifest(), ensure_ascii=False, indent=2) + "\n").encode()


def build(output):
    output.mkdir(parents=True, exist_ok=True)
    raw = manifest_bytes()
    data = json.loads(raw)
    archive = output / f"visionbuddy-v{VERSION}.zip"
    (output / "manifest.json").write_bytes(raw)
    with ZipFile(archive, "w", ZIP_DEFLATED, compresslevel=3) as bundle:
        bundle.writestr("manifest.json", raw)
        for path in data["files"]:
            bundle.write(ROOT / path, path)
        for path in ("README.md", "VERSION", "compatibility.json", "preview.py", "serve.py", "launch.py", "requirements.txt", "启动素材库.cmd", "启动素材库.command"):
            bundle.write(ROOT / path, path)
    verify(archive)
    (output / "SHA256SUMS.txt").write_text(
        f"{sha(archive.read_bytes())}  {archive.name}\n{sha(raw)}  manifest.json\n", encoding="ascii"
    )
    return archive


def verify(archive):
    with ZipFile(archive) as bundle:
        names = bundle.namelist()
        if len({name.casefold() for name in names}) != len(names):
            raise ValueError("离线包包含重复路径")
        for name in names:
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
                raise ValueError(f"离线包包含无效路径 {name}")
        data = json.loads(bundle.read("manifest.json"))
        if set(name for name in names if name.startswith("site/")) != set(data["files"]):
            raise ValueError("离线包文件与清单不一致")
        for name, record in data["files"].items():
            body = bundle.read(name)
            if len(body) != record["size"] or sha(body) != record["sha256"]:
                raise ValueError(f"{name} 校验失败")
        return data


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    options = cli.add_mutually_exclusive_group(required=True)
    options.add_argument("--output", type=Path)
    options.add_argument("--verify", type=Path)
    args = cli.parse_args()
    if args.output:
        print(build(args.output.resolve()))
    else:
        data = verify(args.verify)
        print(data["libraryRelease"], len(data["assets"]), len(data["files"]))
