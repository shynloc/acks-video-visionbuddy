# VisionBuddy 视频素材库

VisionBuddy 收录 108 个动效、9 个部位演示、24 个 3D 物件、37 款贴纸、12 种网页风格和 14 套配色。选好后可直接试看，点「复制到稿件」生成带素材编号的画面标注。

[GitHub Releases](https://github.com/shynloc/acks-video-visionbuddy/releases)

## 离线使用

从 Releases 下载最新版的 `visionbuddy-v版本号.zip`，解压整个目录。Windows 双击「启动素材库.cmd」，macOS 可运行 `sh 启动素材库.command`。也可在解压目录运行 `python launch.py`。浏览器会打开本机素材库。

需要 Python 3.10 或更高版本与 Pillow。已有口播导演工作台时可使用同一个 Python 环境。首次缺少 Pillow，可在联网时运行 `python -m pip install -r requirements.txt`。目录、预览、复制标注和素材下载随后可以离线使用。

选素材时可以搜 `OBJ-017@PAL-013` 指定麦克风的配色版本，也可以搜 `FX-001` 找淡入动效。单独一行的画面标注跟上一段，紧跟原句时跟该句。把复制好的标注粘贴到口播导演工作台即可使用。

## 构建

在代码目录运行 `python tools/release.py --output dist`。输出包括离线 ZIP、版本清单和 SHA-256。验证下载的 ZIP 可运行 `python tools/release.py --verify dist/visionbuddy-v1.1.0.zip`。

运行 `python serve.py --port 8772` 可以在本机打开网站。静态文件与组合 PNG 通过同一端口提供服务，`/latest.json` 指出当前发布版本。发布基线与文件校验值记录在清单中。
面向口播创作者的视频素材库，提供动效、贴纸、3D 物件、网页风格与配色。
