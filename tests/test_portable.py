"""Check clean restores, pinned alternatives, collisions, and archive integrity."""

from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import desk_plan
import personal_store as materials
import portable_bundle as packages


class PortableTest(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.a = self.root / "first"
        self.b = self.root / "second"
        self.meta = {"name":"封箱旧牌", "uses":"贴封条后出现", "keywords":"贴封条、封箱",
                     "author":"示例创作者", "license":"样例授权", "origin":"原创"}
        self.old = self.png("before", "#002fa7")
        self.new = self.png("after", "#ca6f32")

    def png(self, name, color):
        path = self.root / (name + ".png")
        image = Image.new("RGBA", (120, 80))
        image.paste(color, (25, 15, 110, 63))
        image.save(path)
        return path

    def local(self, folder):
        return patch.dict(os.environ, {"VISIONBUDDY_LIBRARY_DIR":str(folder)})

    def test_draft_moves_only_actual_dependencies_after_replacement(self):
        bundle = self.root / "review.zip"
        with self.local(self.a):
            old = materials.save(self.meta,self.old,self.old.name)
            scene = "先贴封条，再检查纸箱。\n这一句只讲声音。（画面：无）\n" + f"最后看看封口。（画面：{old['assetId']}）"
            extra = materials.save({**self.meta, "name":"无关的盆栽", "uses":"盆栽装饰", "keywords":"盆栽"},
                                   self.new, self.new.name)
            plan = desk_plan.build({"kind":"script", "text":scene}, fresh=True)
            newer = materials.save({**self.meta,"name":"封箱新版"}, self.new, self.new.name, old["ref"])
            choice = {"r0001":{"state":"adopted","choice":1},"r0003":{"state":"skipped"}}
            packages.save_project(plan, {"decisions":choice}, bundle)
            with ZipFile(bundle) as archive:
                policy = json.loads(archive.read(packages.MANIFEST))
                self.assertEqual([r["ref"] for r in policy["records"]],[old["ref"]])
                self.assertNotIn(extra["blob"],policy["blobs"])
                self.assertNotIn(newer["blob"],policy["blobs"])
        with self.local(self.b):
            self.assertEqual(materials.list_heads(),[])
            result = packages.restore(bundle,packages.PROJECT)
            self.assertEqual(result["plan"]["rows"],plan["rows"])
            self.assertEqual(result["project"]["decisions"],choice)
            restored=materials.get(old["ref"])
            self.assertEqual(restored,old)
            self.assertEqual(materials.original_path(restored).read_bytes(),self.old.read_bytes())

    def test_team_conflict_preserves_both_and_is_idempotent(self):
        asset_bundle = self.root / "team.zip"
        draft = self.root / "conflicting-review.zip"
        with self.local(self.a):
            first=materials.save(self.meta,self.old,self.old.name)
            packages.save_team([first["ref"]],asset_bundle)
            fixed=desk_plan.build({"kind":"script","text":f"示例里读 {first['assetId']}。请看。（画面：{first['assetId']}）"},fresh=True)
            packages.save_project(fixed,{},draft)
        with self.local(self.b):
            local=materials.save({**self.meta,"name":"另一个同号素材"},self.new,self.new.name)
            with closing(sqlite3.connect(materials.database())) as db, db:
                db.execute("UPDATE revisions SET id=? WHERE id=?",(first["assetId"],local["assetId"]))
            received=packages.restore(asset_bundle,packages.TEAM)
            new_ref=received["versions"][first["ref"]]
            self.assertNotEqual(new_ref,first["ref"])
            self.assertEqual(packages.restore(asset_bundle,packages.TEAM),received)
            self.assertEqual(materials.original_path(materials.get(first["ref"])).read_bytes(),self.new.read_bytes())
            self.assertEqual(materials.original_path(materials.get(new_ref)).read_bytes(),self.old.read_bytes())
            self.assertEqual(len(materials.list_heads()),2)
            restored=packages.restore(draft,packages.PROJECT)
            self.assertIn("读 "+first["assetId"],restored["plan"]["spoken"])
            self.assertEqual(restored["plan"]["rows"][1]["candidates"][0]["personal"],new_ref)

    def test_hash_mismatch_does_not_register_assets(self):
        good, damaged = self.root / "good.zip", self.root / "damaged.zip"
        with self.local(self.a):
            item=materials.save(self.meta,self.old,self.old.name)
            packages.save_team([item["ref"]],good)
        with ZipFile(good) as source, ZipFile(damaged,"w") as target:
            for name in source.namelist():
                raw=source.read(name)
                target.writestr(name,raw if not name.endswith("original.png") else raw[:-1]+bytes([raw[-1]^1]))
        with self.local(self.b):
            with self.assertRaisesRegex(ValueError,"校验失败"):
                packages.restore(damaged,packages.TEAM)
            self.assertEqual(materials.list_heads(),[])


if __name__=="__main__":
    unittest.main()
