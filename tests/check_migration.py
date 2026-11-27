"""Confirm that the independent catalogue, artwork and existing effects match the source checkout."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import preview
from tools.release import entries, manifest


def check(source):
    old = source / "assets/workbench/motion"
    data = manifest()
    aliases = entries()
    assert len(aliases) == 201
    assert set(id.split("-")[0] for id in aliases) == {"FX", "DEMO", "OBJ", "STK", "WEB", "PAL"}
    for name in ("catalog.json", "renderer.js", "illustrations.js", "sample-pack.zip"):
        assert (old/name).read_bytes() == (ROOT/"site"/name).read_bytes(), name
    artwork = {
        file for file in data["files"] if file.startswith("site/visual/")
        and Path(file).suffix.lower() in {".json", ".png", ".svg", ".glb", ".webp"}
    }
    original = {
        "site/" + path.relative_to(old).as_posix() for path in (old/"visual").rglob("*")
        if path.is_file() and path.suffix.lower() in {".json", ".png", ".svg", ".glb", ".webp"}
    }
    assert artwork == original
    for name in artwork:
        assert (old/name.removeprefix("site/")).read_bytes() == (ROOT/name).read_bytes(), name
    obj = preview.brief({"objects": "OBJ-017@PAL-013"})["objects"]
    assert obj["variantId"] == "OBJ-017@PAL-013"
    print(f"{len(aliases)} stable IDs and {len(artwork)} catalogue/variant files match byte for byte.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("source", type=Path)
    check(p.parse_args().source)
