"""Check the installed Skill with a bare Python runtime and a network-blocked browser."""

import argparse
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from PIL import Image
from playwright.sync_api import expect, sync_playwright

QUERY = "文件传好了"
QUOTE = "同步完成后，右上角会出现一个勾。"
EDIT = ("--label", "正在同步", "--label", "同步完成", "--palette", "PAL-015")


def check(archive, channel, media):
    with TemporaryDirectory(prefix="visionbuddy-install-") as directory:
        home = Path(directory)
        with ZipFile(archive) as bundle:
            bundle.extractall(home / "skills")
        installed = home / "skills/visionbuddy"
        env = {**os.environ, "PATH": str(Path(sys.executable).parent)}
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        bare = [sys.executable, "-S", "-X", "utf8", str(installed / "visionbuddy.py")]
        full = [sys.executable, "-X", "utf8", str(installed / "visionbuddy.py")]

        def cli(*args, optional_tools=False, expected=0):
            command = subprocess.run(
                [*(full if optional_tools else bare), *map(str, args)], cwd=home,
                env=None if optional_tools else env, capture_output=True, encoding="utf8", timeout=45,
            )
            assert command.returncode == expected, (command.stdout, command.stderr)
            return json.loads(command.stdout)

        status = cli("status")
        manifest = json.loads((installed / "manifest.json").read_bytes())
        assert status["libraryRelease"] == manifest["libraryRelease"]
        assert status["assets"] == len(manifest["assets"]) == 279
        assert not any(status["optional"].values()), status
        assert (installed / "SKILL.md").is_file()
        for query, code in (
            ("怎么拆密封圈", "KIT-001"), ("降噪前后有什么区别", "KIT-002"), (QUERY, "KIT-003"),
        ):
            assert cli("find", query)["matches"][0]["assetId"] == code
        assert cli("find", "OBJ-017@PAL-013")["matches"][0]["variantId"] == "OBJ-017@PAL-013"
        assert cli("show", "KIT-003@PAL-013", expected=1)["error"]
        icon = cli("license", "ICO-002")["licenses"]["ICO-002"]
        assert icon["license"] == "MIT" and (installed / icon["notice"]).is_file()

        html_path = home / "preview.html"
        proof = cli("preview", "KIT-003", *EDIT, "--output", html_path)
        source_path = home / "source.zip"
        saved = cli("export", "KIT-003", *EDIT, "--quote", QUOTE, "--output", source_path)
        assert proof["annotation"] == saved["annotation"]
        with ZipFile(source_path) as pack:
            assert pack.read(saved["sources"]["scene.html"]) == html_path.read_bytes()
            assert b"MIT License" in pack.read(saved["licenses"]["ICO-002"]["notice"])
        assert cli("export", "KIT-003", "--output", source_path, expected=1)["error"]

        obj_path = home / "object.zip"
        still = cli("export", "OBJ-017@PAL-013", "--output", obj_path)
        with ZipFile(obj_path) as pack, Image.open(BytesIO(pack.read(still["media"]))) as image:
            assert image.getchannel("A").getextrema() == (0, 255)
            assert still["variantIds"]["objects"] == "OBJ-017@PAL-013"
            assert "mic.glb" in still["sources"]

        gallery_log = home / "gallery.log"
        with gallery_log.open("w", encoding="utf8") as log:
            server = subprocess.Popen(
                [*bare, "serve", "--port", "0"], cwd=home, env=env, stdout=subprocess.PIPE,
                stderr=log, encoding="utf8",
            )
            try:
                port = json.loads(server.stdout.readline())["port"]
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(channel=channel)
                    page = browser.new_page(reduced_motion="reduce")
                    page.route("**/*", lambda route: route.continue_()
                               if route.request.url.startswith(f"http://127.0.0.1:{port}/") else route.abort())
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(cli("preview", "KIT-003", "--port", port)["url"])
                    kit = page.locator("#practice")
                    expect(kit.locator('[aria-pressed="true"][data-kit="KIT-003"]')).to_be_visible()
                    kit.get_by_label("文字 2").fill("同步完成")
                    kit.get_by_label("配色").select_option("morandi")
                    frame = page.frame_locator(".practice-preview")
                    page.wait_for_function("""() => {
                        const node = document.querySelector('.practice-preview').contentDocument.querySelector('#scene-data')
                        return node && JSON.parse(node.textContent).labels[1] === '同步完成'
                    }""")
                    kit.get_by_role("button", name="看结束帧").click()
                    expect(frame.locator("svg")).to_contain_text("同步完成")
                    page.goto(cli("preview", "OBJ-017@PAL-013", "--port", port)["url"])
                    expect(page.locator("#grid [data-asset-id=OBJ-017]")).to_have_attribute("aria-pressed", "true")
                    expect(page.locator("#overlay-image")).to_be_visible()
                    expect(page.locator("#choice")).to_contain_text("潮青")
                    page.goto(cli("preview", "FX-001", "--port", port)["url"])
                    expect(page.locator("#search")).to_have_value("FX-001")
                    expect(page.locator(".card[data-id=fade] .playterm")).to_be_visible()
                    page.goto(cli("preview", "UI-003", "--port", port)["url"])
                    expect(page.locator("[data-ui-id=UI-003]")).to_have_attribute("aria-pressed", "true")
                    page.goto(cli("preview", "DEMO-002", "--port", port)["url"])
                    expect(page.locator("#demo-title")).to_contain_text("DEMO-002")

                    offline = browser.new_page(offline=True, reduced_motion="reduce")
                    offline.goto(html_path.as_uri())
                    offline.evaluate("window.previewPlayback('finish')")
                    expect(offline.locator("svg")).to_contain_text("同步完成")
                    colors = offline.locator("#scene-data").text_content()
                    assert json.loads(colors)["colors"] == cli("show", "PAL-015")["asset"]["metadata"]["colors"]
                    assert not errors, errors
                    browser.close()
            finally:
                server.terminate()
                server.wait(timeout=10)
                server.stdout.close()

        if media:
            movie_path = home / "movie.zip"
            movie = cli("export", "KIT-003", *EDIT, "--quote", QUOTE, "--media", "mov",
                        "--output", movie_path, optional_tools=True)
            with ZipFile(movie_path) as pack:
                ending = BytesIO(pack.read(movie["ending"]))
                with Image.open(ending) as image:
                    assert image.getchannel("A").getextrema() == (0, 255)
                inspection = json.loads(pack.read("素材搭配.json"))
                assert inspection["items"][0]["libraryRelease"] == status["libraryRelease"]
                assert inspection["items"][0]["quote"] == QUOTE
                mov = home / "sample.mov"
                mov.write_bytes(pack.read(movie["media"]))
                stream = json.loads(subprocess.check_output(
                    ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_streams", "-of", "json", str(mov)]
                ))["streams"][0]
                assert stream["codec_name"] == "prores" and stream["codec_tag_string"] == "ap4h"
                assert stream["pix_fmt"].startswith("yuva") and stream["nb_frames"] == "75"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--channel", default="msedge")
    parser.add_argument("--media", action="store_true")
    args = parser.parse_args()
    check(args.archive.resolve(), args.channel, args.media)
    print("Isolated installation, offline search and preview, editable source and media checks passed.")
