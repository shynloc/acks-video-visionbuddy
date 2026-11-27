"""Regression checks for stable local versions and older approved projects."""

from pathlib import Path
import os
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import desk_plan
import personal_store as store
from personal_media import alpha_validity


class PersonalTest(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        profile = patch.dict(os.environ, {"VISIONBUDDY_LIBRARY_DIR": str(self.root / "my-library")})
        profile.start()
        self.addCleanup(profile.stop)
        self.options = {"name": "封条标记", "uses": "封条接缝的说明", "keywords": "封条、贴封条",
                        "author": "本机样例", "license": "旧版授权"}

    def still(self, name, color, opaque=False):
        path = self.root / name
        image = Image.new("RGBA", (100, 60), color if opaque else (0, 0, 0, 0))
        if not opaque:
            image.paste(color, (20, 18, 82, 45))
        image.save(path)
        return path

    def test_pin_versions_and_metadata_after_replacement(self):
        original = self.still("before.png", "#002fa7")
        old = store.save(self.options, original, original.name)
        source = {"kind": "script", "text": "先贴封条，再检查纸箱。"}
        first = desk_plan.build(source, fresh=True)
        self.assertEqual(first["rows"][0]["candidates"][0]["personal"], old["ref"])
        self.assertEqual(first["rows"][0]["candidates"][1]["codes"], ["FX-011"])
        updated = self.still("after.png", "#e6833e")
        second = store.save({**self.options, "license": "新版授权"}, updated, updated.name, old["ref"])
        third = store.save({**self.options, "license": "改正登记"}, code=second["ref"])
        self.assertEqual(third["blob"], second["blob"])
        self.assertEqual([item["version"] for item in store.revisions(old["assetId"])], [3, 2, 1])
        self.assertEqual(store.get(old["ref"])["rights"]["license"], "旧版授权")
        self.assertEqual(store.original_path(store.get(old["ref"])).read_bytes(), original.read_bytes())
        self.assertEqual(desk_plan.validated_plan(first)["rows"][0]["candidates"][0]["personal"], old["ref"])
        self.assertEqual(desk_plan.build(source, fresh=True)["rows"][0]["candidates"][0]["personal"], third["ref"])
        # Earlier public-only projects didn't store a local library snapshot.
        selfs = desk_plan.build(source)["rows"][0]["candidates"]
        self.assertNotIn("personal", selfs[0])
        specified = desk_plan.build({"kind": "script", "text": f"这里贴封条。（画面：{old['ref']}）\n继续讲。（画面：无）"},
                                    fresh=True)
        self.assertEqual(specified["rows"][0]["candidates"][0]["personal"], old["ref"])
        self.assertEqual(specified["rows"][1]["mode"], "none")
        with self.assertRaisesRegex(ValueError, "已有更新"):
            store.save(self.options, code=old["ref"])

    def test_opaque_png_keeps_content_and_has_pack_boundary(self):
        source = self.still("opaque.png", "#ed7d43", opaque=True)
        item = store.save(self.options, source, source.name)
        self.assertTrue(item["media"]["padding"])
        with Image.open(store.asset_dir(item) / "poster.png") as png:
            self.assertEqual(png.getchannel("A").getextrema(), (0, 255))
        self.assertEqual(store.original_path(item).read_bytes(), source.read_bytes())
        with self.assertRaisesRegex(ValueError, "没有检测到透明像素"):
            alpha_validity([source], "video")

    def test_reject_invalid_asset_and_missing_revision(self):
        with self.assertRaisesRegex(ValueError, "编号无效"):
            store.get("../a.svg")
        with self.assertRaisesRegex(ValueError, "找不到"):
            desk_plan.build({"kind":"script", "text":"先贴封条。", "personalSnapshot":["MY-AAAABBBB55@V0001"]})


if __name__ == "__main__":
    unittest.main()
