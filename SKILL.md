---
name: visionbuddy
description: 用 VisionBuddy 为口播稿、SRT 或本机视频逐句推荐画面，支持试看、换版、跳过、采用与批量导出。也可导入个人 PNG、SVG、透明视频和 HTML，登记用途与授权，按原版恢复旧工程。按白话、用途或素材编号搜索，试看透明演示，改字换配色，导出可编辑 HTML、GLB、SVG、PNG 或透明 MOV。支持把画面标注和带原句的素材包带入口播导演工作台。
---

# VisionBuddy

从本 Skill 目录运行 `python -X utf8 visionbuddy.py`，macOS 可用 `python3`。命令读取随 Skill 安装的素材目录，`status` 返回当前 `libraryRelease` 与可用工具。

## 给一整段口播配画面

- 有口播稿用 `plan --script 文件 --output 审核稿.json`。有 SRT 用 `plan --srt 字幕.srt`，有配套视频一起传 `--video 原片.mp4`。只有视频时，按用户选的已安装 Whisper 模型传 `--model`，或在审核页本机转写。
- 用 `serve --desk --open` 进入逐句审核。保留固定编号和「画面：无」。给出真实原句、时间码和理由；原稿没有时间码时保持待对齐。现成波形是示意素材，原片的摆放范围可以在审核页调整。
- 用户采用或跳过后再批量导出。Agent 可用 `plan-preview` 生成特定版本的 HTML，使用已审核的选择文件运行 `plan-export`。带媒体的 ZIP 可由口播导演工作台「打开已有搭配」恢复，并附时间清单。命令示例及本机转写依赖见 [README](README.md#给口播配画面)。


## 我的素材

- 用 `serve --mine --open` 打开本机个人素材库。Agent 可用 `my-import` 登记 PNG、SVG、透明视频和单文件 HTML，再用 `my-list`、`show`、`license` 和 `preview` 查看。
- 新推荐可同时使用个人素材和公共库。用户已经指定个人编号时，保留完整版本，例如 `MY-57B15EAD01@V0001`。用 `my-versions` 查看历史，换版或改授权登记会保存新的版本。
- 旧工程按其保存的版本试看和导出。用「保存审核工程」或 `project-save` 生成含引用素材的 ZIP，换机后通过「打开审核工程」或 `project-open` 恢复。带媒体的 ZIP 可在工作台恢复。参数见 [README](README.md#我的素材)。

## 给单句找素材

1. 先尊重用户已指定的素材编号、`OBJ-017@PAL-013` 这类配色变体和「（画面：无）」标注。按画面目的搜索，例如 `find "文件传好了" --kind practice`，用 `show KIT-003` 看可选动作、贴纸和配色。用 `license ICO-002` 查看实际授权记录。`null` 表示该条目没有单独的许可记录。
2. 用 `serve --asset KIT-003 --open` 打开本机素材册。也可用 `preview KIT-003` 取得运行中的素材册地址。要给用户发送一份可离线打开的定制试看，运行 `preview KIT-003 --label "正在同步" --label "同步完成" --palette PAL-015 --output 试看.html`。
3. 用户选定后用 `export KIT-003 --label "正在同步" --label "同步完成" --palette PAL-015 --output 素材.zip` 保存可编辑演示和所用源件。要透明视频时加 `--media mov`，只要透明定格时加 `--media png`。有原句时可用 `--quote "同步完成后，右上角会出现一个勾。"` 生成原句对照，并让有媒体的 ZIP 可在工作台「打开已有搭配」中恢复。
4. 交付实际可打开的 HTML、媒体或 ZIP。需要用工作台继续制作时可直接用返回的 `annotation`，放在相应原句之后。保留素材包记录的库版本和素材编号。Tabler 图标的许可随源件交付。

浏览、检索和源件导出只需 Python。透明定格需 Playwright 与 Chromium、Edge 或 Chrome。透明 MOV 另需带 `prores_ks` 的 FFmpeg。详细参数、安装步骤和 JSON 字段见 [README](README.md)。工作台可接手素材、时间线和剪辑。
