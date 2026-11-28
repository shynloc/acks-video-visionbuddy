"""Entry points for an agent using the standalone review flow."""

import json
from pathlib import Path

import desk_inputs
import desk_plan
from skill_render import json_text


def save_text(path, content):
    output = path.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf8", newline="\n") as file:
        file.write(content)
    return str(output)


def source_from_arguments(args):
    if args.script:
        if args.srt or args.video:
            raise ValueError("请单独提交口播稿，或提交 SRT 和对应的原片。")
        return {"kind": "script", "text": args.script.read_text(encoding="utf-8-sig")}
    if args.video and not args.video.is_file():
        raise ValueError("找不到已有视频。")
    if args.srt:
        return {"kind": "srt", "text": desk_inputs.read_caption_file(args.srt),
                "duration": desk_inputs.probe_duration(args.video) if args.video else None}
    if args.video and args.model:
        return desk_inputs.transcribe(args.video, args.model, args.language)
    if args.video:
        models = "、".join(desk_inputs.available_models()) or "无"
        raise ValueError(f"已有视频请提供配套 --srt，或明确选择本机转写 --model。现有模型：{models}。")
    raise ValueError("请用 --script、--srt 或 --video 指定输入。")


def run(args):
    if args.command == "project-open":
        from portable_bundle import PROJECT, restore
        result = restore(args.project, PROJECT)
        if args.output:
            result["output"] = save_text(args.output, json_text(result["project"]))
        return result
    if args.command == "project-save":
        from portable_bundle import save_project
        state = json.loads(args.project.read_bytes())
        if not isinstance(state, dict) or state.get("libraryRelease") != desk_plan.serve.VERSION:
            raise ValueError("请打开相同公共库版本的审核工程 JSON。")
        if args.review:
            state["decisions"] = json.loads(args.review.read_bytes())
        return save_project(desk_plan.build(state.get("source")), state, args.output)
    if args.command == "plan":
        source = source_from_arguments(args)
        if args.composition:
            source["composition"] = args.composition
        plan = desk_plan.build(source, fresh=True)
        return {**plan, **({"output": save_text(args.output, json_text(plan))} if args.output else {})}
    packet = json.loads(args.plan.read_bytes())
    if not isinstance(packet, dict):
        raise ValueError("请打开 VisionBuddy 审核工程 JSON。")
    project = packet.get("format") == "visionbuddy-project/1"
    if project:
        packet = {**packet, "format": desk_plan.FORMAT}
    plan = desk_plan.validated_plan(packet)
    if args.command == "plan-preview":
        from desk_render import preview_html

        row, candidate = desk_plan.candidate_at(plan, args.row, args.choice)
        if args.output.suffix.lower() != ".html":
            raise ValueError("试看请保存为 .html。")
        output = save_text(args.output, preview_html(row, candidate))
        return {"output": output, "url": Path(output).as_uri(), "row": row["id"], "quote": row["quote"],
                "selectedCodes": candidate["codes"]}
    from desk_render import export

    choices = json.loads(args.review.read_bytes()) if args.review else packet.get("decisions") if project else None
    if choices is None:
        raise ValueError("请提供 --review 选择文件，或打开已保存的审核工程。")
    return export(plan, choices, args.output, args.media)
