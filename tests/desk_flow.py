"""Exercise desktop and compact-width review, timeline preview and the exported bundle."""

import argparse
from io import BytesIO
import json
import re
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from PIL import Image
from playwright.sync_api import expect, sync_playwright

from test_desk_plan import SCRIPT, SRT


def check(base, video, output, screenshot=None, transcribe=False):
    with TemporaryDirectory() as work, sync_playwright() as pw:
        folder = Path(work)
        srt = folder / "当前字幕.srt"
        srt.write_text(SRT, encoding="utf-8-sig")
        browser = pw.chromium.launch(channel="msedge")
        page = browser.new_page(viewport={"width": 1390, "height": 1030})
        errors, blocked = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def block_remote(route):
            blocked.append(route.request.url)
            route.abort()

        page.route(re.compile(r"^https?://(?!"+re.escape(base.removeprefix("http://")+"/")+r")"), block_remote)
        page.goto(base + "/desk/")
        page.locator("#script").fill(SCRIPT)
        page.locator("#plan-button").click()
        expect(page.locator("#review")).to_be_visible()
        expect(page.locator("#lines")).to_contain_text("纯口播")
        expect(page.locator("#lines")).to_contain_text("稿内指定")
        page.locator("#lines .line").filter(has_text="密封罐").click()
        expect(page.locator("#play")).to_be_enabled(timeout=10000)
        page.locator("#alternate").click()
        expect(page.locator("#choices [aria-pressed=true]")).to_contain_text("DEMO-015")
        expect(page.locator("#play")).to_be_enabled(timeout=10000)
        page.locator("#adopt").click()
        expect(page.locator("#export-count")).to_have_text("已采用 2 条")
        page.locator("#lines .line").filter(has_text="上传完成后").click()
        page.locator("#skip").click()
        expect(page.locator("#lines .line").filter(has_text="上传完成后")).to_contain_text("已跳过")
        page.reload()
        expect(page.locator("#export-count")).to_have_text("已采用 2 条")
        expect(page.locator("#lines .line").filter(has_text="上传完成后")).to_contain_text("已跳过")
        page.locator("#intake summary").click()
        page.get_by_role("button", name="用 SRT 字幕").click()
        page.locator("#srt").set_input_files(srt)
        page.locator("#plan-button").click()
        expect(page.locator("#source-summary")).to_contain_text("SRT 时间码")
        expect(page.locator("#lines .line").filter(has_text="密封罐")).to_contain_text("00:00.440")
        expect(page.locator("#lines .line").filter(has_text="听声音")).to_have_count(0)

        page.locator("#intake summary").click()
        page.get_by_role("button", name="用已有视频").click()
        page.locator("#video-file").set_input_files(video)
        expect(page.locator("#intake-status")).to_contain_text("视频已就绪")
        if transcribe:
            expect(page.locator("#model option[value=medium]")).to_have_count(1)
            page.locator("#model").select_option("medium")
            page.locator("#language").select_option("zh")
            page.locator("#plan-button").click()
            try:
                expect(page.locator("#source-summary")).to_contain_text("本机转写时间码", timeout=100000)
            except AssertionError as exc:
                raise AssertionError(page.locator("#intake-status").text_content()) from exc
            expect(page.locator("#lines")).to_contain_text("密封")
            page.locator("#intake summary").click()
        page.locator("#video-srt").set_input_files(srt)
        page.locator("#plan-button").click()
        page.wait_for_function("!document.getElementById('intake').open")
        expect(page.locator("#source-summary")).to_contain_text("SRT 时间码")
        page.locator("#lines .line").filter(has_text="密封罐").click()
        page.locator("#alternate").click()
        expect(page.locator("#play")).to_be_enabled(timeout=10000)
        page.locator("#clip-start").fill("0.55")
        page.locator("#clip-end").fill("2.15")
        page.locator("#side").select_option("left")
        page.locator("#scale").fill("35")
        page.locator("#play").click()
        page.wait_for_function("document.getElementById('player').currentTime > 0.65")
        expect(page.locator("#overlay")).to_be_visible()
        expect(page.locator("#overlay")).to_have_attribute("data-side", "left")
        page.locator("#adopt").click()

        page.locator("#lines .line").filter(has_text="同步完成后").click()
        page.locator("#alternate").click()
        expect(page.locator("#choices [aria-pressed=true]")).to_contain_text("PAL-015")
        expect(page.locator("#play")).to_be_enabled(timeout=10000)
        page.locator("#adopt").click()
        page.locator("#lines .line").filter(has_text="降噪").click()
        page.locator("#skip").click()
        expect(page.locator("#export-count")).to_have_text("已采用 3 条")
        page.locator("#lines .line").filter(has_text="密封罐").click()
        expect(page.locator("#play")).to_be_enabled(timeout=10000)
        if screenshot:
            page.screenshot(path=str(screenshot))
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        with page.expect_download(timeout=90000) as log:
            page.locator("#export").click()
        log.value.save_as(output)
        page.unroute_all(behavior="wait")
        browser.close()
        assert not errors, errors
        assert not blocked, blocked

        with ZipFile(output) as archive:
            info = json.loads(archive.read("时间与素材.json"))
            adopted = [row for row in info["rows"] if row["state"] == "adopted"]
            self_check = adopted[0]["placement"]
            assert self_check == {"side": "left", "scale": .35, "start": .55, "end": 2.15}, self_check
            assert adopted[0]["time"] == {"start": .44, "end": 2.21}
            assert adopted[1]["variantIds"]["objects"] == "OBJ-017@PAL-013"
            assert adopted[2]["assetRefs"]["palettes"] == "PAL-015"
            assert any(row["state"] == "none" for row in info["rows"])
            assert any(row["state"] == "skipped" for row in info["rows"])
            pack = json.loads(archive.read("素材搭配.json"))
            assert pack["format"] == "talking-head-motion/2" and len(pack["items"]) == 3
            for i, row in enumerate(adopted):
                with Image.open(BytesIO(archive.read(row["poster"]))) as image:
                    lo, hi = image.getchannel("A").getextrema()
                    assert lo == 0 and hi > 32
                path = folder / f"overlay-{i}.mov"
                path.write_bytes(archive.read(row["media"]))
                raw = subprocess.check_output(
                    ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_streams", "-of", "json", str(path)]
                )
                stream = json.loads(raw)["streams"][0]
                assert stream["pix_fmt"].startswith("yuva") and stream["r_frame_rate"] == "25/1"


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("base")
    p.add_argument("--video", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--screenshot", type=Path)
    p.add_argument("--transcribe", action="store_true")
    args = p.parse_args()
    check(args.base.rstrip("/"), args.video, args.output, args.screenshot, args.transcribe)
    print("Review, alternate, skip, persisted decisions, SRT and video placement, and batch export passed.")
