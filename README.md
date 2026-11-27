# VisionBuddy 视频素材库

VisionBuddy 1.3.1 收录 108 个动效、15 个演示、35 个 3D 物件、57 款贴纸、12 个 SVG 图标、21 种网页设计或口播版式、6 组界面组件、22 套配色和 3 套口播搭配。选好后可直接试看，点「复制到稿件」生成带素材编号的画面标注。

[在线素材册](https://videobuddy.acks.com.cn/visual/index.html) · [GitHub 离线包](https://github.com/shynloc/acks-video-visionbuddy/releases) · [配套口播导演工作台](https://github.com/shynloc/talking-head-studio/releases)

## 网页风格与配色

在「风格与素材册」点「网页风格」→「整站设计」。预览可以滚动、点击站内导航、展开问答，也能切换桌面和手机宽度。详情卡说明排版、字体和交互原则，并附参考链接。可在「下载这个搭配的素材」保存独立 HTML。

「配色」内可以直接选莫兰迪、北欧、泥陶等色系，或自己选一到两个主题色。选互补、邻近等搭配方式后，可把带用途与 CSS 的色值复制给助手，也可以先套到网页预览，连同网页一起保存。现成 GLB 和贴纸的颜色版本由库内色系决定。

打开「找一套口播搭配」，输入「文件传好了」「前后对比」或「怎么拆」即可找到可调整的小样。可改字、换动作或贴纸，暂停或看结束帧。接入 VisionBuddy 1.3.1 需要工作台 V3.20.1 或更新版本。可在工作台用本机截图或两段录音生成透明小样，采用时锁定的旧素材版本继续可用。

「整站设计」可搜索和打开条目，「界面组件」可试交互并保存 HTML，「图标与插画」附带来源和许可。Tabler 图标的 MIT 声明随 SVG 原件分发。

## 离线使用

从 Releases 下载最新版的 `visionbuddy-v版本号.zip`，解压整个目录。Windows 双击「启动素材库.cmd」，macOS 可运行 `sh 启动素材库.command`。也可在解压目录运行 `python launch.py`。浏览器会打开本机素材库。

需要 Python 3.10 或更高版本与 Pillow。已有口播导演工作台时可使用同一个 Python 环境。首次缺少 Pillow，可在联网时运行 `python -m pip install -r requirements.txt`。目录、预览、复制标注和素材下载随后可以离线使用。

选素材时可以搜 `OBJ-017@PAL-013` 指定麦克风的配色版本，也可以搜 `FX-001` 找淡入动效。单独一行的画面标注跟上一段，紧跟原句时跟该句。把复制好的标注粘贴到口播导演工作台即可使用。

## 构建

在代码目录运行 `python tools/release.py --output dist`。输出包括离线 ZIP、版本清单和 SHA-256。验证下载的 ZIP 可运行 `python tools/release.py --verify dist/visionbuddy-v1.3.1.zip`。

运行 `python serve.py --port 8772` 可以在本机打开网站。静态文件与组合 PNG 通过同一端口提供服务，`/latest.json` 指出当前发布版本。发布基线与文件校验值记录在清单中。

两仓库的 GitHub Actions 核对兼容版本、共用渲染文件和素材入口，生产站每五分钟检查公开发行。配套工作台的 Skill ZIP 就绪后，服务校验素材包并在临时端口试启动，随后更新公网版本。旧版本保留供已有工程调用。
面向口播创作者的视频素材库，提供动效、贴纸、3D 物件、网页风格与配色。
