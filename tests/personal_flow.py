"""Check personal imports, shared recommendations, revision pinning and portable sources."""

import argparse
from io import BytesIO
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from PIL import Image
from playwright.sync_api import expect, sync_playwright


def selected_item(page):
    return page.locator("#asset-ref").text_content()


def import_file(page, path, title, use, tags, seconds=None):
    if not page.locator("#asset-form-card").evaluate("(el) => el.open"):
        page.locator("#form-label").click()
    page.locator("#asset-file").set_input_files(path)
    page.locator("#asset-name").fill(title)
    page.locator("#asset-uses").fill(use)
    page.locator("#asset-keywords").fill(tags)
    page.locator("#asset-author").fill("VisionBuddy 验收样例")
    page.locator("#asset-origin").fill("本机验收素材")
    page.locator("#asset-license").fill("示例自制，可复用")
    if seconds:
        page.locator("#asset-seconds").fill(str(seconds))
    page.locator("#save-asset").click()
    try:
        expect(page.locator("#detail-status")).to_contain_text("已保存 MY-", timeout=45000)
    except AssertionError as exc:
        raise AssertionError(page.locator("#asset-status").text_content()) from exc
    expect(page.locator("#detail-name")).to_have_text(title)
    expect(page.locator("#detail-license")).to_contain_text("可复用")
    expect(page.locator("#personal-proof")).to_be_visible()
    return selected_item(page)


def export(page, path):
    with page.expect_download(timeout=90000) as download:
        page.locator("#export").click()
    download.value.save_as(path)


def zip_records(path):
    with ZipFile(path) as bundle:
        info = json.loads(bundle.read("时间与素材.json"))
        approved = [item for item in info["rows"] if item["state"] == "adopted"]
        marks = bundle.read("带画面标注的稿件.txt").decode("utf8")
        assert "（画面：无）" in marks
        assert len(approved) == 5
        schema = json.loads(bundle.read("素材搭配.json"))
        assert schema["format"] == "talking-head-motion/2" and len(schema["items"]) == 5
        result = {}
        for row in approved:
            with Image.open(BytesIO(bundle.read(row["poster"]))) as png:
                low, high = png.convert("RGBA").getchannel("A").getextrema()
                assert low == 0 and high > 32
            if "personal" in row:
                personal = row["personal"]
                notice = row["licenses"][personal["ref"]]["notice"]
                assert json.loads(bundle.read(notice))["rights"]["license"] == "示例自制，可复用"
                assert personal["originalMember"] in bundle.namelist()
            result[row["id"]] = (row, bundle.read(row["media"]))
        return result


def run(base, fixtures, output, screenshot=None):
    with TemporaryDirectory() as scratch, sync_playwright() as play:
        work = Path(scratch)
        browser = play.chromium.launch(channel="msedge")
        page = browser.new_page(viewport={"width": 1410, "height": 1050})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/my-assets/")
        png = import_file(page, fixtures / "封箱提示-旧.png", "封箱提示", "给贴封条步骤配画面", "贴封条、封箱")
        expect(page.frame_locator("#personal-proof").locator("img")).to_be_visible()
        svg = import_file(page, fixtures / "录音刻度.svg", "录音刻度", "指出录音刻度和电平位置", "录音刻度")
        html = import_file(page, fixtures / "同步确认.html", "个人同步确认", "同步操作完成演示", "同步成功", 1.4)
        expect(page.frame_locator("#personal-proof").locator("canvas")).to_be_visible()
        movie = import_file(page, fixtures / "进度标记.webm", "个人进度条", "用进度条提示文件下载", "下载进度", 1)
        expect(page.frame_locator("#personal-proof").locator("canvas")).to_be_visible()
        expect(page.locator("#assets [data-asset]")).to_have_count(4)
        page.get_by_role("link", name="给口播配画面").click()
        script = (f"先贴封条，再检查纸箱。\n先打开密封罐，再取下密封圈清洗。\n"
                  f"这里看录音刻度。（画面：{svg}）\n同步成功时看这里。（画面：{html}）\n"
                  f"请看下载进度。（画面：{movie}）\n这一句只保留口播。（画面：无）")
        page.locator("#script").fill(script)
        page.locator("#plan-button").click()
        expect(page.locator("#review")).to_be_visible()
        page.locator("#lines .line").filter(has_text="贴封条").click()
        expect(page.locator("#choices")).to_contain_text(png)
        expect(page.locator("#choices")).to_contain_text("FX-011")
        expect(page.locator("#play")).to_be_enabled()
        page.locator("#adopt").click()
        page.locator("#lines .line").filter(has_text="密封罐").click()
        expect(page.locator("#choices")).to_contain_text("KIT-001")
        page.locator("#adopt").click()
        expect(page.locator("#export-count")).to_have_text("已采用 5 条")
        with page.expect_download() as download:
            page.locator("#save-project").click()
        saved = work / "旧审核工程.zip"
        download.value.save_as(saved)
        original = work / "采用原版.zip"
        export(page, original)
        previous = zip_records(original)
        assert previous["r0001"][0]["selectedCodes"] == [png]

        page.get_by_role("link", name="我的素材").click()
        page.locator("#assets .line").filter(has_text="封箱提示").click()
        expect(page.locator("#asset-ref")).to_have_text(png)
        page.locator("#replace-asset").click()
        second = import_file(page, fixtures / "封箱提示-新.png", "封箱提示新版", "给贴封条步骤配画面", "贴封条、封箱")
        assert second.split("@")[0] == png.split("@")[0] and second.endswith("@V0002")
        page.locator("#asset-versions").select_option(png)
        expect(page.locator("#asset-ref")).to_have_text(png)
        expect(page.locator("#version-note")).to_contain_text("旧版保留")
        expect(page.locator("#replace-asset")).to_be_disabled()
        page.locator("#asset-versions").select_option(second)
        if screenshot:
            page.screenshot(path=screenshot)

        reopened = browser.new_page(viewport={"width": 1160, "height": 930})
        reopened.on("pageerror", lambda error: errors.append(str(error)))
        reopened.goto(base + "/desk/")
        reopened.locator("#project-file").set_input_files(saved)
        expect(reopened.locator("#export-count")).to_have_text("已采用 5 条")
        reopened.locator("#lines .line").filter(has_text="贴封条").click()
        expect(reopened.locator("#choices [aria-pressed=true]")).to_contain_text(png)
        export(reopened, output)
        after = zip_records(output)
        assert previous["r0001"][1] == after["r0001"][1]
        assert previous["r0001"][0]["personal"] == after["r0001"][0]["personal"]
        for identity in ("r0003", "r0004", "r0005"):
            assert previous[identity][1] == after[identity][1], identity
        named = work / "transparent.mov"
        named.write_bytes(after["r0005"][1])
        alpha = subprocess.check_output([
            "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=pix_fmt",
            "-of", "csv=p=0", str(named),
        ]).decode().strip()
        assert alpha.startswith("yuva"), alpha
        reopened.locator("#intake summary").click()
        reopened.locator("#script").fill("先贴封条，再检查纸箱。")
        reopened.locator("#plan-button").click()
        expect(reopened.locator("#choices [aria-pressed=true]")).to_contain_text(second)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        browser.close()
        assert not errors, errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base")
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--screenshot", type=Path)
    args = parser.parse_args()
    run(args.base.rstrip("/"), args.fixtures, args.output, args.screenshot)
    print("Four browser imports, personal and public alternatives, mixed export, and exact old-version reuse passed.")
