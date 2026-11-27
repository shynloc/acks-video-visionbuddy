"""Build the installable VisionBuddy Skill ZIP with its offline library."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
from zipfile import ZipFile, ZIP_DEFLATED

from release import ROOT, RUNTIME_FILES, VERSION, manifest_bytes, sha

sys.path.insert(0, str(ROOT))
from visionbuddy import SKILL_VERSION

FOLDER = "visionbuddy"
FIRST_SKILL = ("SKILL.md", "visionbuddy.py", "skill_catalog.py", "skill_render.py")
REVIEW_SKILL = FIRST_SKILL + (
    "desk_cli.py", "desk_inputs.py", "desk_plan.py", "desk_render.py", "desk_server.py",
    "manuscript_annotations.py", "desk/index.html", "desk/style.css", "desk/app.js",
    "配画面.cmd", "配画面.command",
)
PERSONAL_SKILL = REVIEW_SKILL + (
    "personal_store.py", "personal_media.py", "personal_render.py", "personal_web.py", "personal_cli.py",
    "desk/my-assets.html", "desk/my-assets.css", "desk/my-assets.js",
)
SKILL_FILES = PERSONAL_SKILL + ("portable_bundle.py",)


def member(name):
    return f"{FOLDER}/{name}"


def verify(path):
    with ZipFile(path) as bundle:
        names = bundle.namelist()
        if len({name.casefold() for name in names}) != len(names):
            raise ValueError("Skill 包包含重复路径。")
        for name in names:
            parts = PurePosixPath(name).parts
            if not parts or parts[0] != FOLDER or ".." in parts or "\\" in name or ":" in name:
                raise ValueError(f"Skill 路径无效。{name}")
        manifest = json.loads(bundle.read(member("manifest.json")))
        info = json.loads(bundle.read(member("skill-release.json")))
        if bundle.read(member("VERSION")).decode().strip() != manifest["libraryRelease"]:
            raise ValueError("Skill 包的素材版本与发布清单不一致。")
        if info["libraryRelease"] != manifest["libraryRelease"]:
            raise ValueError("Skill 包的版本记录不一致。")
        members = {**manifest["files"], **info["runtime"]}
        layouts = {"1.0.0": FIRST_SKILL, "1.1.0": REVIEW_SKILL, "1.2.0": PERSONAL_SKILL, SKILL_VERSION: SKILL_FILES}
        required = RUNTIME_FILES + layouts.get(info["skillVersion"], ())
        if set(info["runtime"]) != set(required):
            raise ValueError("Skill 包缺少运行文件。")
        if set(names) != {member(name) for name in (*members, "manifest.json", "skill-release.json")}:
            raise ValueError("Skill 包的文件与清单不一致。")
        if not bundle.read(member("SKILL.md")).startswith(b"---\nname: visionbuddy\n"):
            raise ValueError("找不到 VisionBuddy Skill 入口。")
        for name, record in members.items():
            body = bundle.read(member(name))
            if len(body) != record["size"] or sha(body) != record["sha256"]:
                raise ValueError(f"{name} 校验失败。")
        return info


def build(output):
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"visionbuddy-skill-v{SKILL_VERSION}.zip"
    raw = manifest_bytes()
    library = json.loads(raw)
    runtime = {name: (ROOT / name).read_bytes() for name in RUNTIME_FILES + SKILL_FILES}
    info = {
        "format": "visionbuddy-skill/1", "skillVersion": SKILL_VERSION, "libraryRelease": VERSION,
        "runtime": {name: {"size": len(body), "sha256": sha(body)} for name, body in runtime.items()},
    }
    with ZipFile(archive, "w", ZIP_DEFLATED, compresslevel=3) as bundle:
        bundle.writestr(member("manifest.json"), raw)
        bundle.writestr(member("skill-release.json"), json.dumps(info, ensure_ascii=False, indent=2) + "\n")
        for name in library["files"]:
            bundle.write(ROOT / name, member(name))
        for name in runtime:
            bundle.write(ROOT / name, member(name))
    verify(archive)
    digest = hashlib.sha256()
    with archive.open("rb") as file:
        for data in iter(lambda: file.read(1024**2), b""):
            digest.update(data)
    archive.with_suffix(".zip.sha256").write_text(f"{digest.hexdigest()}  {archive.name}\n", encoding="ascii")
    return archive


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    option = cli.add_mutually_exclusive_group(required=True)
    option.add_argument("--output", type=Path)
    option.add_argument("--verify", type=Path)
    args = cli.parse_args()
    if args.output:
        print(build(args.output.resolve()))
    else:
        result = verify(args.verify)
        print(f"VisionBuddy Skill {result['skillVersion']} | library {result['libraryRelease']}")
