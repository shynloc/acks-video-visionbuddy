# VisionBuddy 视频素材库

VisionBuddy 1.3.1 收录 108 个动效、15 个演示、35 个 3D 物件、57 款贴纸、12 个 SVG 图标、21 种网页设计或口播版式、6 组界面组件、22 套配色和 3 套口播搭配。选好后可直接试看，点「复制到稿件」生成带素材编号的画面标注。

[在线素材册](https://videobuddy.acks.com.cn/visual/index.html) · [GitHub 离线包](https://github.com/shynloc/acks-video-visionbuddy/releases) · [配套口播导演工作台](https://github.com/shynloc/talking-head-studio/releases)

[在线给口播配画面](https://videobuddy.acks.com.cn/desk/)支持口播稿、SRT 或配套原片试看，可保存审核工程和导出可编辑源件。

[网页版我的素材](https://videobuddy.acks.com.cn/my-assets/)可导入、试看、换版和修改登记。原件及历史版本保存在当前浏览器，可以逐版下载原件。

## 网页风格与配色

在「风格与素材册」点「网页风格」→「整站设计」。预览可以滚动、点击站内导航、展开问答，也能切换桌面和手机宽度。详情卡说明排版、字体和交互原则，并附参考链接。可在「下载这个搭配的素材」保存独立 HTML。

「配色」内可以直接选莫兰迪、北欧、泥陶等色系，或自己选一到两个主题色。选互补、邻近等搭配方式后，可把带用途与 CSS 的色值复制给助手，也可以先套到网页预览，连同网页一起保存。现成 GLB 和贴纸的颜色版本由库内色系决定。

打开「找一套口播搭配」，输入「文件传好了」「前后对比」或「怎么拆」即可找到可调整的小样。可改字、换动作或贴纸，暂停或看结束帧。接入 VisionBuddy 1.3.1 需要工作台 V3.20.1 或更新版本。可在工作台用本机截图或两段录音生成透明小样，采用时锁定的旧素材版本继续可用。

「整站设计」可搜索和打开条目，「界面组件」可试交互并保存 HTML，「图标与插画」附带来源和许可。Tabler 图标的 MIT 声明随 SVG 原件分发。

## 离线使用

从 Releases 下载最新版的 `visionbuddy-v版本号.zip`，解压整个目录。Windows 双击「启动素材库.cmd」，macOS 可运行 `sh 启动素材库.command`。也可在解压目录运行 `python launch.py`。浏览器会打开本机素材库。

需要 Python 3.10 或更高版本。目录、演示、复制标注和素材下载可离线使用。若需要把物件和贴纸合成一张透明 PNG，可在联网时运行 `python -m pip install -r requirements.txt` 安装 Pillow。

选素材时可以搜 `OBJ-017@PAL-013` 指定麦克风的配色版本，也可以搜 `FX-001` 找淡入动效。单独一行的画面标注跟上一段，紧跟原句时跟该句。把复制好的标注粘贴到口播导演工作台即可使用。

## 安装独立 Skill

将 `visionbuddy-skill-v版本号.zip` 解压到 Codex 的 Skill 目录，校对目录结构为 `visionbuddy/SKILL.md`。Windows 可用 PowerShell 的 `Expand-Archive`，macOS 可用 `unzip`。本机 Codex 可放在 `~/.codex/skills/` 或当前项目的 `.agents/skills/`。重新打开 Codex 对话后使用 `$visionbuddy`。也可以解压到普通目录，直接运行同一个命令行。Skill ZIP 已带对应的离线库，无需另外下载。 [下载独立 Skill 1.3.0](https://github.com/shynloc/acks-video-visionbuddy/releases/tag/skill-v1.3.0)

以下命令从解压后的 `visionbuddy` 目录运行。macOS 可把 `python` 换成 `python3`。

```text
python -X utf8 visionbuddy.py status
python -X utf8 visionbuddy.py find "文件传好了" --kind practice
python -X utf8 visionbuddy.py show OBJ-017@PAL-013
python -X utf8 visionbuddy.py license ICO-002
python -X utf8 visionbuddy.py serve --asset KIT-003 --open
```

`preview KIT-003` 返回运行中的本机素材册地址。使用自定义端口时，给 `serve` 和 `preview` 传相同的 `--port`。也可以直接生成一份离线试玩或素材包。

```text
python -X utf8 visionbuddy.py preview KIT-003 --label "正在同步" --label "同步完成" --palette PAL-015 --output 试看.html
python -X utf8 visionbuddy.py export KIT-003 --label "正在同步" --label "同步完成" --palette PAL-015 --quote "同步完成后，右上角会出现一个勾。" --output 同步演示.zip
python -X utf8 visionbuddy.py export OBJ-017@PAL-013 --output 麦克风.zip
```

口播搭配可用 `--demo` 选套内动作，用 `--sticker` 换贴纸或填 `none` 移除。圈出部位时还可以用 `--object` 换主体。部分演示从 `--quote` 读实际刻度或读数。动效词条、配色、网页风格和交互组件可在浏览器中查阅，网页样式和互动组件可在素材册保存 HTML。

演示默认保存可编辑源件。加 `--media png` 可同时保存透明定格，加 `--media mov` 可同时保存 25 fps 透明 ProRes 4444 MOV 和定格。用 `python -m pip install playwright` 启用定格导出。可用系统 Edge、Chrome，或者用 `python -m playwright install chromium` 安装浏览器。MOV 还需让带 `prores_ks` 编码器的 FFmpeg 可从 PATH 调用。多个库内素材合成 PNG 时需要 Pillow。

导出包里的 `visionbuddy.json` 记录库版本、素材和变体编号、源件位置和授权。把输出的画面标注紧跟原句粘回口播导演工作台，可沿用同一款搭配。指定 `--quote` 且包内有 PNG 或 MOV 时，工作台「打开已有搭配」可直接恢复整个 ZIP。

命令输出为 UTF-8 JSON，根字段 `schemaVersion`、`skillVersion` 和 `libraryRelease` 适用于所有命令。`find` 的 `matches` 含稳定编号和 `previewPath`，`show` 的 `asset` 还含元数据、可用配色和相对 Skill 根目录的素材文件路径。`license` 返回按编号索引的授权记录，`null` 表示目录没有单独声明。可预期的运行错误以非零退出码和 `error` 返回。


## 给口播配画面

Windows 可双击独立包里的「配画面.cmd」，macOS 可运行 `sh 配画面.command`。也可执行 `python -X utf8 visionbuddy.py serve --desk --open`，或从本机素材册点「给口播配画面」。

| 手里的资料 | 入口 |
| --- | --- |
| 口播稿 | 粘贴全文，点「推荐画面」。原句是摆放依据，具体时间留待对齐原片。 |
| SRT 字幕 | 选字幕后沿用每段的时间码。字幕内的画面标注和稿件使用同一套规则。 |
| 已有视频 | 选本机视频和配套 SRT 后试摆。只有视频时，可选已有 Whisper 模型做本机转写。 |

稿内素材编号、配色变体和「（画面：无）」先锁定，再挑少量适合自动配画面的原句。指定的素材默认纳入导出，可临时跳过。编号有冲突或找不到时，保留原标注并显示原因。自动推荐卡可试看、换一版、采用、跳过或恢复待选。同一份字幕的多句话可以共享一个字幕区间。有原片时，点「试看此句」播放选定区间，可改出现和结束秒数、左右位置与画面宽度。浏览器会在本机保留审核选择，重新打开时可选择原视频继续。

选择「导出已采用素材」会生成批量 ZIP。里面有透明视频或静帧、可编辑源件、原句对照和 `时间与素材.json`。带媒体的 ZIP 可在口播导演工作台 V3.20.1 或更新版的「打开已有搭配」中恢复。原句、锁定的库版本和媒体会随 ZIP 带入工作台，时间线按清单中的摆放数据对齐。也可把 `带画面标注的稿件.txt` 粘进工作台继续制作。

视频和配套 SRT 在本机浏览器试看。本机转写需安装 `openai-whisper`、PyTorch 和 FFmpeg，并在 `~/.cache/whisper` 或 `$XDG_CACHE_HOME/whisper` 已有模型文件。VisionBuddy 会列出可用模型。转写期间的输入和音频临时文件在本机处理，视频本体不随素材包导出。

### Agent 命令

```text
python -X utf8 visionbuddy.py plan --script 口播稿.txt --output 审核稿.json
python -X utf8 visionbuddy.py plan --video 原片.mp4 --srt 字幕.srt --output 审核稿.json
python -X utf8 visionbuddy.py plan --video 原片.mp4 --model medium --language zh --output 审核稿.json
python -X utf8 visionbuddy.py plan-preview 审核稿.json --row r0002 --choice 1 --output 试看.html
python -X utf8 visionbuddy.py plan-export 审核稿.json --review 审核选择.json --output 口播素材包.zip
```

`plan` 返回 `visionbuddy-plan/1`，每行有原句、原始时间码、稿内标注、推荐理由和备选版本。`--choice` 从 0 开始。经审核后可填写选择，例如 `{"r0002":{"state":"adopted","choice":1},"r0005":{"state":"skipped"}}`。有时间码时，可加 `start`、`end`（秒）、`side`（`left` 或 `right`）和 `scale`（0.20 到 0.65）。批量导出也支持 `--media png` 或 `--media source`。


## 我的素材

在本机配画面页或素材册打开「我的素材」，也可运行 `python -X utf8 visionbuddy.py serve --mine --open`。登记名称、用途、关键词、作者、来源和授权。用途和关键词用于推荐，授权随采用的素材导出。

- PNG 和 SVG 可作为静态画面。不透明的平面素材会保留原内容并在外侧加入透明留白。
- 透明视频支持 MOV、WebM、MKV 和 MP4。文件须实际带 Alpha，可选起点及最长 12 秒的导出片段，完整原件也会保存。导入需要 FFmpeg 与 FFprobe。
- HTML 支持可离线打开的 UTF-8 单文件。可选画幅和时长，支持静帧、CSS 动画和 `window.renderFrame(frame,total)`。SVG 和 HTML 导入需要本机浏览器与 Playwright。试看使用已生成的小样，原件可下载，也会随素材包提供。

个人素材有固定编号，例如 `MY-57B15EAD01`。后缀 `@V0001` 表示一个具体版本。换文件或修改登记都会新增一版，旧文件、用途和授权记录会保留。新推荐使用最新版，旧审核工程沿用保存的素材版本。可在配画面页「保存审核工程」和「打开审核工程」。稿内可用「（画面：MY-57B15EAD01@V0001）」指定原版。

ZIP 可混合个人和公共素材。口播导演工作台用「打开已有搭配」恢复包内的透明 PNG、MOV 和源件。个人编号、版本和授权写在每款的 `个人素材.json` 中。个人视频的完整原件位于 VisionBuddy ZIP 的「个人原件」。粘贴稿件时可用 `工作台稿件.txt` 传递公共编号，再从 ZIP 恢复个人画面。`带画面标注的稿件.txt` 和 `审核工程.json` 保留个人版本。

个人数据默认保存在 Windows 的 `%LOCALAPPDATA%/VisionBuddy/我的素材`、macOS 的 `~/Library/Application Support/VisionBuddy/我的素材` 或 Linux 的本机数据目录。可用环境变量 `VISIONBUDDY_LIBRARY_DIR` 指定目录。独立移机可保存审核工程 ZIP，完整备份素材库时可迁移数据库和媒体。Skill 更新时个人素材独立保存。

```text
python -X utf8 visionbuddy.py my-import 封箱提示.png --uses "贴封条步骤小样" --keywords "贴封条,封箱" --license "原创，可改作"
python -X utf8 visionbuddy.py my-list 封箱
python -X utf8 visionbuddy.py my-import 封箱提示新版.png --replace MY-57B15EAD01@V0001
python -X utf8 visionbuddy.py my-versions MY-57B15EAD01
python -X utf8 visionbuddy.py preview MY-57B15EAD01@V0001 --output 原版试看.html
python -X utf8 visionbuddy.py plan-export 审核工程.json --output 口播素材包.zip
```


## 迁移审核工程与分享素材

「保存审核工程」生成可恢复的 ZIP，含原句、审核选择和当前方案引用的个人版本。可在没有原个人库的电脑打开。旧 JSON 仍可从「打开审核工程」读取。ZIP 默认保留原片关联信息，换机后重新选本机原片即可继续试看。已采用素材的导出 ZIP 同时可供 VisionBuddy 恢复和工作台导入。

工作台开发版的「时间线」内选择「导入 VisionBuddy」，用带 PNG 或 MOV 的素材 ZIP 检查摆放，再加入草稿。工作台按保留的原片片段换算时间码，跨剪点时会按片段保留透明动画的播放位置。需要按原句定位时可在导入面板切换。重复导入会显示当前已在时间线的画面。

在「我的素材」中勾选素材，再点「保存已选素材」。对方用「导入素材分享包」恢复。包包含所选版本的原件、预览和登记。相同版本可复用，本机与包内同编号同版本内容冲突时会为导入内容建立独立编号。

```text
python -X utf8 visionbuddy.py project-save 审核工程.json --output 审核工程.zip
python -X utf8 visionbuddy.py project-open 审核工程.zip --output 恢复后.json
python -X utf8 visionbuddy.py my-share MY-57B15EAD01@V0001 --output 分享素材.zip
python -X utf8 visionbuddy.py my-receive 分享素材.zip
```

## 构建

在代码目录运行 `python tools/release.py --output dist`。输出包括离线 ZIP、版本清单和 SHA-256。验证下载的 ZIP 可运行 `python tools/release.py --verify dist/visionbuddy-v1.3.1.zip`。

构建独立 Skill 用 `python -X utf8 tools/skill_release.py --output dist`，会生成版本化 Skill ZIP 及 SHA-256。可用 `python -X utf8 tools/skill_release.py --verify dist/visionbuddy-skill-v1.3.0.zip` 检查运行文件和素材清单。

运行 `python serve.py --port 8772` 可以在本机打开网站。静态文件与组合 PNG 通过同一端口提供服务，`/latest.json` 指出当前发布版本。发布基线与文件校验值记录在清单中。

两仓库的 GitHub Actions 核对兼容版本、共用渲染文件和素材入口，生产站每五分钟检查公开发行。配套工作台的 Skill ZIP 就绪后，服务校验素材包并在临时端口试启动，随后更新公网版本。旧版本保留供已有工程调用。
面向口播创作者的视频素材库，提供动效、贴纸、3D 物件、网页风格与配色。
