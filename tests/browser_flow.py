"""Exercise the independent gallery on the running offline release or the website."""
import argparse
from io import BytesIO
import re

from PIL import Image
from playwright.sync_api import sync_playwright, expect


def run(base, channel=None, assets=201):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel=channel)
        ctx = browser.new_context(viewport={"width": 1400, "height": 900}, reduced_motion="reduce",
                                  permissions=["clipboard-read", "clipboard-write"])
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.goto(base)
        expect(page.locator("#cards [data-id]")).to_have_count(108)
        page.locator("#search").fill("FX-001")
        card = page.locator("#cards [data-id]")
        expect(card).to_have_count(1)
        card.locator(".pick").click()
        page.locator("#copy-to-script").click()
        expect(page.locator("#notice")).to_contain_text("已复制")
        assert "FX-001" in page.evaluate("navigator.clipboard.readText()")
        page.locator("#jumpmix").click()
        expect(page.locator("#snapshot")).to_be_visible()
        expect(page.locator("#export-mix")).to_be_hidden()
        with page.expect_download() as download:
            page.locator("#snapshot").click()
        with Image.open(download.value.path()) as im:
            assert im.getchannel("A").getextrema()[-1] > 0

        page.locator("#nav-visual").click()
        frame = page.frame_locator("#visual-frame")
        expect(frame.locator("#grid")).to_be_visible()
        frame.locator("#asset-search").fill("OBJ-017@PAL-013")
        frame.locator('[data-asset-id="OBJ-017"]').click()
        expect(frame.locator("#detail code")).to_have_text("OBJ-017@PAL-013")
        expect(frame.locator("#overlay-image")).to_be_visible()
        with Image.open(BytesIO(ctx.request.get(base+frame.locator("#overlay-image").get_attribute("src")).body())) as im:
            assert im.getchannel("A").getextrema() == (0, 255)
        frame.locator("#layout-view").click()
        expect(frame.locator("#preview article")).to_be_visible()
        page.locator("#copy-to-script").click()
        expect(page.locator("#notice")).to_contain_text("已复制")
        assert "OBJ-017@PAL-013" in page.evaluate("navigator.clipboard.readText()")
        link = page.locator("#nav-example").get_attribute("href")
        assert link.startswith("http://127.0.0.1:")
        page.goto(base+"/demos.html")
        expect(page.locator("#demo-cards button")).to_have_count(15 if assets >= 279 else 9)
        page.locator("#demo-search").fill("DEMO-002")
        page.locator('[data-asset-id="DEMO-002"]').click()
        svg = page.frame_locator("#demo-preview").locator("svg")
        expect(svg).to_be_visible()
        page.locator("#demo-copy").click()
        expect(page.locator("#demo-notice")).to_contain_text("已复制")
        assert "DEMO-002" in page.evaluate("navigator.clipboard.readText()")
        page.set_viewport_size({"width":390,"height":844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        latest = ctx.request.get(base+"/latest.json").json()
        manifest = ctx.request.get(base+latest["manifest"]).json()
        assert len(manifest["assets"]) == assets
        assert "OBJ-017" in manifest["assets"]
        assert not errors, errors
        browser.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("base")
    p.add_argument("--channel", default=None)
    p.add_argument("--assets", type=int, default=279)
    args = p.parse_args()
    run(args.base.rstrip("/"), args.channel, args.assets)
    print("FX, transparent overlay, HTML layout, part demo and copy-to-manuscript verified.")
