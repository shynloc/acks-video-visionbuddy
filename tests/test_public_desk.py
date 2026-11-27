import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import unittest
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = {"kind": "script", "text": "打开麦克风。（画面：OBJ-017 PAL-013）"}


class PublicDeskTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        cls.base = f"http://127.0.0.1:{port}"
        cls.server = subprocess.Popen(
            [sys.executable, "-B", str(ROOT / "tools/online_skill_site.py"), "--library", str(ROOT),
             "--revisions", str(ROOT), "--port", str(port), "--skill-version", "1.3.0",
             "--desk-root", str(ROOT), "--web-origin", cls.base],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.addClassCleanup(cls.stop)
        for _ in range(40):
            try:
                if cls.request("/healthz").strip() == b"ok":
                    return
            except URLError:
                time.sleep(.2)
        raise RuntimeError("Public site did not start")

    @classmethod
    def stop(cls):
        cls.server.terminate()
        cls.server.wait(8)

    @classmethod
    def request(cls, path, payload=None, *, origin=None):
        binary = isinstance(payload, bytes)
        data = payload if binary or payload is None else json.dumps(payload).encode()
        headers = {"Origin": cls.base if origin is None else origin,
                   "Content-Type": "application/octet-stream" if binary else "application/json"}
        with urlopen(Request(cls.base + path, data=data, headers=headers), timeout=15) as reply:
            return reply.read()

    def test_public_review_and_portability(self):
        self.assertIn(b'href="/desk/"', self.request("/visual/index.html"))
        self.assertIn(b'data-online="true"', self.request("/desk/"))
        plan = json.loads(self.request("/api/desk/plan", {"source": SCRIPT, "fresh": True}))
        row = plan["rows"][0]
        self.assertEqual(row["mode"], "fixed")
        self.assertIn("OBJ-017", row["candidates"][0]["codes"])
        data = {"source": plan["source"], "decisions": {row["id"]: {"state": "adopted", "choice": 0}},
                "mode": "script", "selected": row["id"]}
        preview = self.request("/api/desk/preview", {"source": plan["source"], "row": row["id"]})
        self.assertTrue(preview.startswith(b"<!doctype html>"))
        package = self.request("/api/desk/save-project", data)
        restored = json.loads(self.request("/api/desk/open-project", package))
        self.assertEqual(restored["project"]["decisions"], data["decisions"])
        export = self.request("/api/desk/export", {**data, "media": "source"})
        with ZipFile(BytesIO(export)) as archive:
            timeline = json.loads(archive.read("时间与素材.json"))
        self.assertEqual(timeline["rows"][0]["state"], "adopted")
        self.assertEqual(timeline["rows"][0]["assetRefs"]["objects"], "OBJ-017")

    def test_srt_and_public_boundary(self):
        srt = {"kind": "srt", "text": "1\n00:00:01,250 --> 00:00:04,000\n打开麦克风。\n"}
        plan = json.loads(self.request("/api/desk/plan", {"source": srt}))
        self.assertEqual(plan["rows"][0]["time"], {"start": 1.25, "end": 4})
        with self.assertRaises(HTTPError) as cross_site:
            self.request("/api/desk/plan", {"source": SCRIPT}, origin="https://example.com")
        self.assertEqual(cross_site.exception.code, 403)
        with self.assertRaises(HTTPError) as personal:
            self.request("/api/desk/plan", {"source": {**SCRIPT, "personalSnapshot": ["MY-00000000@V0001"]}})
        self.assertEqual(personal.exception.code, 400)
        for path in ("/api/desk/transcribe", "/api/personal/import"):
            with self.assertRaises(HTTPError) as unavailable:
                self.request(path, b"data")
            self.assertEqual(unavailable.exception.code, 404)
