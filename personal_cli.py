"""Agent commands for registering and retrieving private materials."""

from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile, ZIP_DEFLATED

import personal_render as render
import personal_store as store
import skill_render


def summary(record):
    return {"kind": "personal", "assetId": record["assetId"], "variantId": record["ref"],
            "title": record["name"], "description": record["uses"], "previewPath": browser_path(record)}


def browser_path(record):
    from urllib.parse import urlencode
    return "/my-assets/?" + urlencode({"ref": record["ref"]})


def register_commands(commands):
    share = commands.add_parser("my-share", help="打包选中的个人素材版本")
    share.add_argument("assets", nargs="+")
    share.add_argument("--output", type=Path, required=True)
    receive = commands.add_parser("my-receive", help="导入个人素材分享包")
    receive.add_argument("archive", type=Path)
    listing = commands.add_parser("my-list", help="列出或搜索本机个人素材")
    listing.add_argument("query", nargs="?", default="")
    versions = commands.add_parser("my-versions", help="列出个人素材的全部版本")
    versions.add_argument("asset")
    upload = commands.add_parser("my-import", help="导入原件或为已有素材换版")
    upload.add_argument("file", type=Path)
    upload.add_argument("--replace", help="当前个人素材的完整版本编号")
    upload.add_argument("--seconds", type=float, help="视频截取或 HTML 试看时长")
    upload.add_argument("--start", type=float, help="视频截取起点")
    upload.add_argument("--canvas", choices=("landscape", "portrait", "square"), help="HTML 画幅")
    edit = commands.add_parser("my-edit", help="保存新的名称、用途或授权登记版本")
    edit.add_argument("asset", help="当前个人素材的完整版本编号")
    for command in (upload, edit):
        command.add_argument("--name")
        command.add_argument("--uses")
        command.add_argument("--keywords", help="多个关键词以逗号分隔")
        command.add_argument("--author")
        command.add_argument("--license")
        command.add_argument("--origin")


def run(args):
    if args.command == "my-share":
        from portable_bundle import save_team
        return save_team(args.assets, args.output)
    if args.command == "my-receive":
        from portable_bundle import TEAM, restore
        return restore(args.archive, TEAM)
    if args.command == "my-list":
        return {"items": [render.public_record(row) for _, _, row in store.search(args.query)]}
    if args.command == "my-versions":
        return {"versions": [render.public_record(row) for row in store.revisions(args.asset)]}
    code = args.replace if args.command == "my-import" else args.asset
    parent = store.get(code) if code else None
    fields = ("name", "uses", "keywords", "author", "license", "origin")
    options = {}
    if parent:
        options.update(name=parent["name"], uses=parent["uses"], keywords="，".join(parent["keywords"]),
                       **parent["rights"])
    options.update({field: getattr(args, field) for field in fields if getattr(args, field) is not None})
    if args.command == "my-edit":
        return {"item": render.public_record(store.save(options, code=code))}
    options.update(seconds=args.seconds, start=args.start, canvas=args.canvas)
    filename = args.file.resolve()
    if not filename.is_file():
        raise ValueError("找不到所选原件。")
    return {"item": render.public_record(store.save(options, filename, args.file.name, code))}


def for_asset(args, release):
    record = store.get(args.asset)
    if args.command == "show":
        return {"asset": {**summary(record), **render.public_record(record)}}
    if args.command == "license":
        return {"assetId": record["assetId"], "licenses": {record["ref"]: record["rights"]}}
    if args.command == "preview":
        if args.output is None:
            return {"assetId": record["assetId"], "ref": record["ref"],
                    "url": f"http://127.0.0.1:{args.port}" + browser_path(record)}
        from desk_cli import save_text
        if args.output.suffix.lower() != ".html":
            raise ValueError("试看输出请使用 .html。")
        path = save_text(args.output, render.proof_html(record))
        return {"output": path, "url": Path(path).as_uri(), "ref": record["ref"]}
    if args.command == "export":
        return export(record, args.output, args.media, args.quote, release)
    raise ValueError("请选择查看、试看或导出个人素材。")


def export(record, path, media, quote, release):
    import shutil

    path = path.resolve()
    if path.suffix.lower() != ".zip" or path.exists():
        raise ValueError("请指定尚未存在的 ZIP 路径。")
    quote = (quote or "").strip()
    row = {"id": "r0001", "quote": quote, "offset": 0, "notes": []}
    choice = {"personal": record["ref"], "seconds": record["media"]["seconds"] or 3}
    with TemporaryDirectory(prefix="visionbuddy-personal-zip-") as scratch:
        staged = Path(scratch) / "asset.zip"
        with ZipFile(staged, "w", ZIP_DEFLATED, compresslevel=2) as bundle:
            detail, item = render.write_row(bundle, row, choice, {}, media, release)
            bundle.writestr("visionbuddy.json", skill_render.json_text(detail))
            if item and quote:
                bundle.writestr("素材搭配.json", skill_render.json_text(
                    {"format": "talking-head-motion/2", "items": [item]}))
        path.parent.mkdir(parents=True, exist_ok=True)
        with staged.open("rb") as source, path.open("xb") as dest:
            try:
                shutil.copyfileobj(source, dest)
            except OSError:
                dest.close()
                path.unlink()
                raise
    return {"output": str(path), "ref": record["ref"], "workbenchImport": bool(item and quote)}
