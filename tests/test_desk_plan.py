"""Regression coverage for fixed directions, alternatives and timing from SRT."""

from pathlib import Path
import json
import sys
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desk_inputs import read_caption_file, speech_windows
from desk_plan import build, review_choices
from desk_render import export

SCRIPT = (
    "欢迎回来。☕\n先打开密封罐，再取下密封圈清洗。\n"
    "这一句只讲声音。（画面：无）\n"
    "看桌面麦克风。（画面：用 OBJ-017@PAL-013、FX-001，时长 2 秒。）\n"
    "上传完成后，右上角会出现一个勾。\n"
    "开了降噪，键盘声音前后有什么区别？"
)
SRT = """1
00:00:00,440 --> 00:00:02,210
先打开密封罐，
再取下密封圈清洗。

2
00:00:02,250 --> 00:00:03,600
这一句只讲声音。（画面：无）

3
00:00:04,140 --> 00:00:05,530
看桌面麦克风。（画面：用 OBJ-017@PAL-013、FX-001，时长 2 秒。）

4
00:00:06,250 --> 00:00:08,450
同步完成后，右上角会出现一个勾。

5
00:00:09,110 --> 00:00:11,500
开启降噪前后，键盘声音有明显区别。
"""


class DeskPlanTest(unittest.TestCase):
    def test_script_respects_explicit_and_plain_notes(self):
        plan = build({"kind": "script", "text": SCRIPT})
        by_mode = {row["mode"]: row for row in plan["rows"]}
        self.assertEqual(by_mode["none"]["notes"], ["无"])
        self.assertEqual(by_mode["fixed"]["candidates"][0]["codes"], ["OBJ-017@PAL-013", "FX-001"])
        self.assertEqual(by_mode["fixed"]["candidates"][0]["visual"]["palettes"], "tidal")
        self.assertNotIn("画面：", plan["spoken"])
        self.assertEqual(len([row for row in plan["rows"] if row["mode"] == "auto"]), 3)
        self.assertTrue(all(row["time"] is None for row in plan["rows"]))

    def test_paragraph_annotation_and_inline_override_follow_workbench(self):
        plan = build({"kind": "script", "text": (
            "这里看稿件。这里先说一句。（画面：无）这里接着讲。\n（画面：用 FX-001）\n"
            "该用什么？（画面：用 OBJ-988。）\n")})
        self.assertEqual([row["mode"] for row in plan["rows"]], ["fixed", "none", "fixed", "blocked"])
        self.assertEqual(plan["rows"][3]["notes"], ["用 OBJ-988。"])

    def test_srt_milliseconds_manual_placement_and_skip(self):
        plan = build({"kind": "srt", "text": SRT, "duration": 14})
        rows = plan["rows"]
        self.assertEqual(rows[0]["time"], {"start": .440, "end": 2.210})
        self.assertEqual(rows[0]["quote"], "先打开密封罐， 再取下密封圈清洗。")
        self.assertEqual(rows[2]["candidates"][0]["placement"]["end"], 6.14)
        decisions = {rows[0]["id"]: {"state": "adopted", "choice": 1, "start": .55, "end": 2.1, "side": "left"},
                     rows[3]["id"]: {"state": "skipped"}}
        approved, summary = review_choices(plan, decisions)
        self.assertEqual([entry[0]["mode"] for entry in approved], ["auto", "fixed"])
        self.assertEqual(approved[0][1]["codes"], ["KIT-001", "DEMO-015"])
        self.assertEqual(approved[0][2]["start"], .55)
        self.assertEqual(summary[3]["state"], "skipped")
        self.assertEqual(summary[1]["state"], "none")
        with self.assertRaisesRegex(ValueError, "超出视频时长"):
            build({"kind": "srt", "text": SRT, "duration": 5})
        with self.assertRaisesRegex(ValueError, "摆放区间无效"):
            review_choices(plan, {rows[0]["id"]: {"state": "adopted", "end": 90}})

    def test_keep_original_numbers_and_variants(self):
        plan = build({"kind": "script", "text":
                      "第 2 步，噪音从 74 分贝降低到 41 分贝。\n量杯倒到第 3 条刻度。\n把转接头插到笔记本右侧接口。"})
        self.assertEqual(plan["rows"][0]["candidates"][0]["labels"][:2], ["74", "41"])
        self.assertEqual(plan["rows"][0]["candidates"][0]["labels"][2], "分贝")
        self.assertEqual(plan["rows"][1]["candidates"][0]["codes"], ["DEMO-001"])
        self.assertTrue(plan["rows"][2]["candidates"][0]["codes"][0].startswith("OBJ-"))

    def test_source_export_retains_pure_voice_and_review(self):
        plan = build({"kind": "script", "text": SCRIPT})
        with TemporaryDirectory() as work:
            path = Path(work) / "cut.zip"
            auto = next(row["id"] for row in plan["rows"] if row["mode"] == "auto")
            result = export(plan, {auto: {"state": "adopted"}}, path, "source")
            self.assertFalse(result["workbenchImport"])
            with ZipFile(path) as zip_file:
                timeline = json.loads(zip_file.read("时间与素材.json"))
                self.assertTrue(any(row["state"] == "none" for row in timeline["rows"]))
                self.assertEqual(zip_file.read("原稿.txt").decode(), SCRIPT)
                self.assertIn("（画面：无）", zip_file.read("带画面标注的稿件.txt").decode())
                self.assertFalse(any(name.endswith(".mov") for name in zip_file.namelist()))

    def test_native_caption_encoding_and_speech_windows(self):
        with TemporaryDirectory() as work:
            path = Path(work) / "字幕.srt"
            path.write_bytes(SRT.encode("gb18030"))
            self.assertEqual(read_caption_file(path), SRT)
        self.assertEqual(speech_windows("silence_start: 0\nsilence_end: 3", 3), [])
        self.assertEqual(speech_windows("silence_start: 0\nsilence_end: 1\nsilence_start: 3\nsilence_end: 4", 4), [.9, 3.1])


if __name__ == "__main__":
    unittest.main()
