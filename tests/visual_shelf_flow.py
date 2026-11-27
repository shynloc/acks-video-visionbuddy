"""Verify the shared website, palette, and transparent asset controls over HTTP."""
import argparse
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin

from PIL import Image
from playwright.sync_api import expect, sync_playwright


def run(url, channel, output=None):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel=channel)
        context = browser.new_context(
            viewport={"width": 1510, "height": 950},
            permissions=["clipboard-read", "clipboard-write"],
        )
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url, wait_until="domcontentloaded")
        base = lambda selector: page.locator(selector)
        tab = lambda name: base("#tabs").get_by_role("button", name=name, exact=True)
        button = lambda name: page.get_by_role("button", name=name, exact=True)
        asset = lambda code: base(f'.entry[data-asset-id="{code}"]')
        tab("网页风格").click()
        expect(base("#grid .entry")).to_have_count(6)
        expect(base("#preview .website nav")).to_be_visible()
        asset("WEB-013").click()
        expect(base("#preview .web-headline")).to_have_text("少一点负担。")
        expect(base("#detail").get_by_role("link", name="Apple · 官网的产品层级与导航")).to_be_visible()
        base("#preview nav").get_by_role("link", name="常见问题").click()
        assert base("#preview").evaluate("(el) => el.scrollTop") > 60
        base(".web-questions summary").first.click()
        expect(base(".web-questions details[open] p").first).to_be_visible()
        button("手机").click()
        assert base(".website").evaluate("(el) => el.clientWidth") <= 324
        button("桌面").click()
        assert base(".website").evaluate("(el) => el.clientWidth") > 324
        asset("WEB-018").click()
        expect(base("#detail").get_by_text("2027 前瞻", exact=True)).to_be_visible()
        if output:
            output.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=output/"整站设计.png")
        button("口播画面版式").click()
        expect(base("#grid .entry")).to_have_count(12)
        asset("WEB-012").click()
        expect(base("#preview .scene.signalcard")).to_be_visible()
        button("整站设计").click()

        tab("配色").click()
        asset("PAL-015").click()
        expect(base("#detail h3")).to_have_text("莫兰迪色系")
        expect(base("#detail .color-chip")).to_have_count(4)
        base("#theme-one").fill("#2368BF")
        base("#harmony").select_option("complementary")
        expect(base("#color-chips .color-chip")).to_have_count(6)
        expect(base("#color-chips")).to_contain_text("#2368BF")
        before = base("#color-chips").inner_text()
        base("#harmony").select_option("analogous")
        assert before != base("#color-chips").inner_text()
        base("#theme-two-on").check()
        base("#theme-two").fill("#DD5730")
        for mode in ("monochrome", "split", "triadic", "tetradic"):
            base("#harmony").select_option(mode)
            expect(base("#color-chips")).to_contain_text("#DD5730")
        button("试到网页上").click()
        assert base("#preview .website").evaluate("(el) => el.style.getPropertyValue('--web-accent')") == "#DD5730"
        button("复制色卡").click()
        text = page.evaluate("navigator.clipboard.readText()")
        assert "#2368BF" in text and "--accent: #DD5730;" in text
        if output:
            page.screenshot(path=output/"自定义色卡.png")
        page.get_by_text("下载这个搭配的素材", exact=True).click()
        with page.expect_download() as download:
            button("保存当前 HTML 样式").click()
        html = Path(download.value.path()).read_text("utf8")
        exported = context.new_page()
        exported.set_content(html)
        expect(exported.locator(".web-footer")).to_be_attached()
        expect(exported.locator(".web-art img").first).to_have_js_property("complete", True)
        assert exported.locator(".website").evaluate("(el) => el.style.getPropertyValue('--web-accent')") == "#DD5730"
        assert "data:image/png;base64," in html
        exported.close()
        button("恢复所选色系").click()
        assert base("#preview .website").evaluate("(el) => el.style.getPropertyValue('--web-accent')") == "#56675C"

        tab("3D 物件").click()
        base("#asset-search").fill("OBJ-025@PAL-015")
        asset("OBJ-025").click()
        expect(base("#detail .asset-id")).to_have_text("OBJ-025@PAL-015")
        tab("贴纸").click()
        base("#asset-search").fill("STK-044@PAL-015")
        asset("STK-044").click()
        expect(base("#detail .asset-id")).to_have_text("STK-044@PAL-015")
        expect(base("#overlay-image")).to_be_visible(timeout=30000)
        response = context.request.get(urljoin(url, base("#overlay-image").get_attribute("src")))
        assert response.ok
        with Image.open(BytesIO(response.body())) as png:
            assert png.getchannel("A").getextrema() == (0, 255)
        button("复制到稿件").click()
        clipboard = page.evaluate("navigator.clipboard.readText()")
        assert "OBJ-025@PAL-015" in clipboard and "STK-044@PAL-015" in clipboard
        page.set_viewport_size({"width": 390, "height": 844})
        tab("网页风格").click()
        expect(base("#preview .website")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+1")
        assert base(".website").evaluate("(el) => el.scrollWidth <= el.clientWidth+1")
        assert not errors, errors
        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--channel", default="msedge")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    run(args.url, args.channel, args.output)
    print("Full responsive websites, palette generation, HTML download, and transparent assets passed.")
