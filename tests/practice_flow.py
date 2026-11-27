"""Exercise three reusable talking-head setups, editable UI and interactive site exports."""
import argparse
import array
from io import BytesIO
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import wave
from zipfile import ZipFile

from PIL import Image
from playwright.sync_api import expect, sync_playwright


def sample_wave(path, amplitude):
    with wave.open(str(path), "wb") as audio:
        audio.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
        audio.writeframes(array.array("h", [amplitude if i % 8 < 4 else -amplitude for i in range(8000)]))


def shelf_test(base, result, app):
    with TemporaryDirectory() as temp, sync_playwright() as pw:
        scratch = Path(temp)
        browser = pw.chromium.launch(channel="msedge")
        context = browser.new_context(viewport={"width":1450,"height":960},
            permissions=["clipboard-read","clipboard-write"], reduced_motion="reduce")
        page = context.new_page()
        errors = []
        page.on("pageerror",lambda error:errors.append(str(error)))
        path = "/motion/visual/index.html" if app else "/visual/index.html"
        page.goto(base+path)
        page.locator("#practice-box summary").click()
        shelf = page.locator("#practice")
        movie = page.frame_locator("iframe.practice-preview")
        search = shelf.get_by_role("searchbox")
        example = [
            ("怎么拆密封圈","KIT-001","先打开密封罐，再取下密封圈清洗。","STK-049"),
            ("降噪前后有什么区别","KIT-002","开通降噪前后，键盘声差很多。","STK-055"),
            ("文件传好了","KIT-003","上传完成后，右上角会出现一个勾。","ICO-002"),
        ]
        output=[]
        for query,kit,quote,sticker in example:
            search.fill(query)
            expect(shelf.locator(".practice-cards button").first).to_have_attribute("data-kit",kit)
            shelf.locator(f'[data-kit="{kit}"]').click()
            if kit=="KIT-001":
                shelf.get_by_label("配图或贴纸").select_option("brushunder")
                shelf.get_by_label("文字 2").fill("拆下清洗")
                expect(movie.locator("svg")).to_contain_text("拆下清洗")
            if kit=="KIT-002" and app:
                sample_wave(scratch/"before.wav",18000)
                sample_wave(scratch/"after.wav",2000)
                shelf.get_by_label("前段音频").set_input_files(scratch/"before.wav")
                expect(shelf.get_by_text("已读取这段录音。")).to_be_visible()
                shelf.get_by_label("后段音频").set_input_files(scratch/"after.wav")
                expect(shelf.get_by_text("波形来自你选择的两段文件",exact=False)).to_be_visible()
                page.wait_for_function("document.querySelector('iframe.practice-preview').contentDocument.querySelector('#scene-data')?.textContent.includes('0.5493')")
                raw = json.loads(movie.locator("#scene-data").text_content())
                assert .5 < raw["waveBefore"][0] < .6 and .05 < raw["waveAfter"][0] < .09
            if kit=="KIT-003" and app:
                pic=scratch/"demo.png"
                Image.new("RGB",(256,110),"#83CBD5").save(pic)
                shelf.get_by_label("截图",exact=True).set_input_files(pic)
                expect(shelf.get_by_text("已换成你的截图。")).to_be_visible()
                page.wait_for_function("document.querySelector('iframe.practice-preview').contentDocument.querySelector('#scene-data')?.textContent.includes('data:image/png;base64,')")
            shelf.get_by_role("button",name="看结束帧",exact=True).click()
            expect(movie.locator("svg")).to_be_visible()
            shelf.get_by_role("button",name="复制到稿件",exact=True).click()
            expect(shelf.get_by_text("已复制，粘贴到对应口播原句后。")).to_be_visible()
            mark=page.evaluate("navigator.clipboard.readText()")
            assert sticker in mark,mark
            output.append(quote+mark)
        page.locator("#practice-box summary").click()

        page.get_by_role("button",name="网页风格",exact=True).click()
        expect(page.locator("#grid .entry")).to_have_count(9)
        page.locator('[data-asset-id="WEB-019"]').click()
        web=page.locator("#preview .website")
        web.get_by_label("按类别筛选").select_option("物件")
        expect(web.locator(".web-record:visible")).to_have_count(1)
        web.get_by_role("button",name="打开详情 · 折叠雨伞").click()
        expect(web.locator("[data-detail-title]")).to_have_text("折叠雨伞")
        web.get_by_role("button",name="返回列表").click()
        expect(web.locator(".web-record:visible")).to_have_count(1)
        page.get_by_role("button",name="手机",exact=True).click()
        assert web.evaluate("(el)=>el.clientWidth<=324")

        page.locator('[data-asset-id="WEB-020"]').click()
        web.get_by_label("按类别筛选").select_option("步骤")
        expect(web.locator(".web-record:visible")).to_have_count(2)
        page.locator('[data-asset-id="WEB-021"]').click()
        web.get_by_label("搜索服务").fill("交通")
        expect(web.locator(".web-record:visible")).to_have_count(1)
        web.get_by_role("button",name="查看办理步骤 · 查询社区交通").click()
        expect(web.locator("[data-detail-title]")).to_have_text("查询社区交通")
        page.get_by_text("下载这个搭配的素材",exact=True).click()
        with page.expect_download() as site_dl:
            page.get_by_role("button",name="保存当前 HTML 样式").click()
        site=Path(site_dl.value.path()).read_text("utf8")
        exported=context.new_page()
        exported.set_content(site)
        exported.get_by_label("搜索服务").fill("借用")
        exported.get_by_role("button",name="查看办理步骤 · 借用共享工具").click()
        expect(exported.locator("[data-detail-title]")).to_have_text("借用共享工具")
        if result:
            result.mkdir(parents=True,exist_ok=True)
            site_dl.value.save_as(result/"服务指南-可操作整站.html")
            page.screenshot(path=result/"整站效果.png")
        exported.close()

        page.get_by_role("button",name="配色",exact=True).click()
        page.locator('[data-asset-id="PAL-022"]').click()
        expect(page.locator(".shelf-samples div")).to_have_count(3)
        page.get_by_role("button",name="网页风格",exact=True).click()
        page.get_by_role("button",name="界面组件",exact=True).click()
        expect(page.locator("#components-box [data-ui-id]")).to_have_count(6)
        page.locator('[data-ui-id="UI-003"]').click()
        ui=page.frame_locator(".component-preview")
        ui.get_by_role("button",name="开始示例上传").click()
        ui.get_by_role("button",name="模拟失败").click()
        expect(ui.get_by_role("status")).to_have_text("连接中断，请重试。")
        ui.get_by_role("button",name="重试").click()
        expect(ui.get_by_role("status")).to_have_text("已上传 · 100%")
        with page.expect_download() as ui_dl:
            page.get_by_role("button",name="保存可操作组件 HTML").click()
        assert "#F5F2FF" in Path(ui_dl.value.path()).read_text("utf8")
        if result:
            ui_dl.value.save_as(result/"上传进度-可操作组件.html")

        page.get_by_role("button",name="图标与插画",exact=True).click()
        asset=page.locator('[data-asset-id="ICO-002"]')
        expect(asset).to_be_visible()
        asset.click()
        expect(page.locator("#detail")).to_contain_text("MIT")
        expect(page.locator("#detail .asset-id")).to_contain_text("ICO-002@PAL-022")
        assert not errors,errors
        if not app:
            browser.close()
            return
        page.goto(base+"/motion/index.html?desk=motion_2e768120000000000000000000000237")
        expect(page.locator("#manuscript")).to_be_visible()
        page.locator("#manuscript").fill("\n\n".join(output))
        cards=page.locator('[data-annotation="specified"]')
        expect(cards).to_have_count(3,timeout=20000)
        for i in range(3):
            cards.nth(i).get_by_role("button",name="准备这版小样").click()
        for i in range(3):
            button=cards.nth(i).locator(".accept")
            expect(button).to_be_visible(timeout=105000)
            button.click()
            expect(button).to_have_attribute("aria-pressed","true")
        with page.expect_download(timeout=90000) as download:
            page.locator("#export-choices").click()
        package=(result or scratch)/"三组口播-混合素材包.zip"
        download.value.save_as(package)
        with ZipFile(package) as zipfile:
            manifest=json.loads(zipfile.read("素材搭配.json"))
            assert [row["assetRefs"]["treatment"] for row in manifest["items"]]==["DEMO-010","DEMO-011","DEMO-012"],manifest
            assert all(row["libraryRelease"]=="1.3.0" and row["packageMedia"].endswith(".mov") for row in manifest["items"])
            assert all("画面：" not in row["quote"] for row in manifest["items"])
            sources=[zipfile.read(item["packageSources"]["scene.html"]).decode("utf8") for item in manifest["items"]]
            assert "拆下清洗" in sources[0]
            assert ".5493" in sources[1] and ".061" in sources[1]
            assert "data:image/png;base64," in sources[2]
            names=[name for name in zipfile.namelist() if name.endswith(".png") and not name.startswith("可编辑源件/")]
            assert len(names)>=3
            for name in names:
                with Image.open(BytesIO(zipfile.read(name))) as png:
                    low,high=png.convert("RGBA").getchannel("A").getextrema()
                    assert low==0 and high>0,name
            assert any(b"MIT License" in zipfile.read(name) for name in zipfile.namelist() if "icon_circle_check.svg" in name)
            for i,item in enumerate(manifest["items"]):
                mov=scratch/f"{i}.mov"
                mov.write_bytes(zipfile.read(item["packageMedia"]))
                fmt=subprocess.check_output(["ffprobe","-v","error","-select_streams","v:0","-show_entries",
                    "stream=pix_fmt","-of","csv=p=0",str(mov)]).decode().strip()
                assert fmt.startswith("yuva"),fmt
        browser.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("base")
    parser.add_argument("--app",action="store_true")
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    shelf_test(args.base,args.output,args.app)
    print("Three plain-language kits, edits, usable websites and components, colors and asset notices passed.")
