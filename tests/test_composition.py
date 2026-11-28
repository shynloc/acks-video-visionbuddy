import unittest
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desk_plan import build, review_choices
from desk_render import export
from portable_bundle import PROJECT, restore

class CompositionTest(unittest.TestCase):
    def test_two_directions_survive_export_and_restore(self):
        source = {"kind":"srt","text":"1\n00:00:00,200 --> 00:00:02,400\n看桌面麦克风。（画面：用 OBJ-017。）"}
        for direction, scale in [('presenter', .4), ('demo', .3)]:
            with self.subTest(direction=direction), TemporaryDirectory() as tmp:
                plan = build({**source, "composition":direction})
                place = plan['rows'][0]['candidates'][0]['placement']
                self.assertEqual((place['scale'], place['start']), (scale, .2))
                decisions = {'r0001': {'state':'adopted','side':'left'}}
                path = Path(tmp) / 'review.zip'
                export(plan, decisions, path, 'source')
                with ZipFile(path) as archive:
                    timing = json.loads(archive.read('时间与素材.json'))
                self.assertEqual(timing['composition'], direction)
                self.assertEqual(timing['rows'][0]['placement']['side'],'left')
                result = restore(path, PROJECT)
                self.assertEqual(result['plan']['source']['composition'],direction)
                self.assertEqual(result['project']['decisions'],decisions)

    def test_mixed_decisions_override_suggestions_and_restore(self):
        source = {'kind':'script','composition':'mixed','text':
                  '我信任自己的判断。（画面：用 OBJ-017。）先打开文件，再导入图片。谢谢。（画面：无。）'}
        plan = build(source)
        self.assertEqual([r['suggestedComposition'] for r in plan['rows']], ['presenter','demo','presenter'])
        choices = {'r0001':{'composition':'demo'}, 'r0002':{'state':'adopted','suggestedComposition':'demo',
                   'composition':'presenter'}, 'r0003':{'suggestedComposition':'demo'}}
        approved, rows = review_choices(plan, choices)
        self.assertEqual([r['composition'] for r in rows], ['demo','presenter','presenter'])
        self.assertEqual([r['compositionOrigin'] for r in rows], ['user','user','user'])
        self.assertEqual([item[2]['scale'] for item in approved], [.30,.40])
        with TemporaryDirectory() as tmp:
            archive = Path(tmp)/'mixed.zip'
            export(plan, choices, archive, 'source')
            reopened = restore(archive, PROJECT)
            self.assertEqual(reopened['project']['decisions'],choices)
            with ZipFile(archive) as zipped:
                exported = json.loads(zipped.read('时间与素材.json'))
            self.assertEqual(exported['composition'], 'mixed')
            self.assertEqual([r['composition'] for r in exported['rows']], ['demo','presenter','presenter'])
        choices['r0002'].pop('composition')
        _, rows = review_choices(plan, choices)
        self.assertEqual((rows[1]['composition'],rows[1]['compositionOrigin']),('demo','auto'))
        choices['r0002']['composition'] = 'mixed'
        with self.assertRaises(ValueError):
            review_choices(plan,choices)

    def test_legacy_and_repeated_steps(self):
        source = {'kind':'script','text':'先打开设备，再连接线缆。先选图片，再预览结果。'}
        old, demo = build(source), build({**source,'composition':'demo'})
        self.assertNotIn('composition',old['source'])
        self.assertEqual(sum(row['mode']=='auto' for row in old['rows']),1)
        self.assertEqual(sum(row['mode']=='auto' for row in demo['rows']),2)
        with self.assertRaises(ValueError):
            build({**source,'composition':'unknown'})
