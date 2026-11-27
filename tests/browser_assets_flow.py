"""Verify the online personal library with synthetic files in a fresh browser."""

import argparse
from io import BytesIO
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

from PIL import Image
from playwright.sync_api import expect, sync_playwright


def run(base, folder):
    folder.mkdir(parents=True, exist_ok=True)
    image = BytesIO()
    Image.new("RGBA", (32, 24), (40, 90, 170, 170)).save(image, format="PNG")
    raw = image.getvalue()
    png = {"name": "first.png", "mimeType": "image/png", "buffer": raw}
    svg = {"name": "second.svg", "mimeType": "image/svg+xml",
           "buffer": b'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="30"><rect width="40" height="30" fill="orange"/></svg>'}
    html = {"name": "scene.html", "mimeType": "text/html",
            "buffer": b'<style>h2{color:navy}</style><h2>Local HTML preview</h2><img src="https://example.invalid/no-upload"><script>document.querySelector("h2").textContent="Unexpected"</script>'}
    video = folder / "sample.mp4"
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i",
         "color=blue:s=160x120:d=2:r=12", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)], check=True,
    )
    requests = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge" if os.name == "nt" else None, headless=True)
        context = browser.new_context(accept_downloads=True, viewport={"width": 1230, "height": 850})
        page = context.new_page()
        page.set_default_timeout(35000)
        context.on("request", lambda request: requests.append((request.method, request.url)))
        page.goto(base + "/visual/index.html", wait_until="domcontentloaded")
        page.get_by_role("link", name="我的素材", exact=True).click()
        expect(page.locator("body")).to_have_attribute("data-browser-assets", "true")
        expect(page.locator("#assets")).to_contain_text("还没有个人素材")

        def add(file, name, uses, license):
            expect(page.locator("#asset-form-card:not([open]) > summary")).to_be_visible()
            page.locator("#asset-form-card > summary").click()
            page.locator("#asset-file").set_input_files(file)
            page.locator("#asset-name").fill(name)
            page.locator("#asset-uses").fill(uses)
            page.locator("#asset-license").fill(license)
            page.locator("#save-asset").click()
            expect(page.locator("#detail-name")).to_have_text(name)

        add(png, "原版图标", "口播片头", "仅本人使用")
        first = page.locator("#asset-ref").inner_text()
        assert re.fullmatch(r"MY-[0-9A-F]{10}@V0001", first)
        expect(page.locator("#own-stage img")).to_have_attribute("src", re.compile(r"^blob:"))
        assert page.locator("#own-stage img").evaluate("img => img.decode().then(() => img.naturalWidth)") == 32

        page.locator("#replace-asset").click()
        page.locator("#asset-file").set_input_files(svg)
        page.locator("#asset-name").fill("新版图标")
        page.locator("#save-asset").click()
        second = first.replace("@V0001", "@V0002")
        expect(page.locator("#asset-ref")).to_have_text(second)
        assert page.locator("#own-stage img").evaluate("img => img.decode().then(() => img.naturalWidth)") == 40
        page.locator("#edit-asset").click()
        page.locator("#asset-license").fill("团队可改作")
        page.locator("#save-asset").click()
        third = first.replace("@V0001", "@V0003")
        expect(page.locator("#asset-ref")).to_have_text(third)
        expect(page.locator("#detail-license")).to_have_text("团队可改作")

        page.reload(wait_until="domcontentloaded")
        expect(page.locator("#asset-ref")).to_have_text(third)
        page.locator("#asset-versions").select_option(first)
        expect(page.locator("#detail-name")).to_have_text("原版图标")
        expect(page.locator("#detail-license")).to_have_text("仅本人使用")
        with page.expect_download() as download:
            page.locator("#download-original").click()
        restored = folder / download.value.suggested_filename
        download.value.save_as(restored)
        assert restored.read_bytes() == raw

        add(video, "试看视频", "口播放片", "自制")
        expect(page.locator("#own-stage video")).to_have_attribute("src", re.compile(r"^blob:"))
        page.locator("#own-stage video").evaluate("""video => new Promise((resolve, reject) => {
          if (video.readyState) return resolve()
          if (video.error) return reject(Error('Video failed to open'))
          video.addEventListener('loadedmetadata', resolve, {once:true})
          video.addEventListener('error', () => reject(Error('Video failed to open')), {once:true})
        })""")

        add(html, "本地网页", "试看版式", "自制")
        frame = page.frame_locator("#personal-proof")
        expect(frame.locator("h2")).to_have_text("Local HTML preview")
        expect(page.locator("#personal-proof")).to_have_attribute("sandbox", "")
        page.locator("#asset-search").fill("口播片头")
        expect(page.locator("#assets button")).to_have_count(1)
        expect(page.locator("#assets button")).to_contain_text("新版图标")

        isolated = browser.new_context()
        second_page = isolated.new_page()
        second_page.goto(base + "/my-assets/", wait_until="domcontentloaded")
        expect(second_page.locator("#assets")).to_contain_text("还没有个人素材")
        isolated.close()
        browser.close()
    assert not [url for method, url in requests
                if method != "GET" or "/api/personal/" in url or urlsplit(url).hostname == "example.invalid"]
    print("Browser-only import, PNG/SVG/video/HTML preview, version history, refresh and original download passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    run(args.url, args.out)
