"""Promote verified public VisionBuddy releases on the Linux web origin."""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import socket
import stat
import subprocess
import tempfile
import time
from urllib.request import Request, urlopen
from zipfile import ZipFile

OWNER = "shynloc"
LIBRARY = "acks-video-visionbuddy"
STUDIO = "talking-head-studio"
MAX_ZIP = 384 * 1024**2
ROOT_FILES = {
    "manifest.json", "VERSION", "README.md", "compatibility.json", "serve.py", "preview.py",
    "launch.py", "requirements.txt", "启动素材库.cmd", "启动素材库.command",
}
VERSION = re.compile(r"\d{1,5}\.\d{1,5}\.\d{1,5}\Z")


def version(value):
    if not isinstance(value, str) or not VERSION.fullmatch(value):
        raise ValueError("Invalid published version")
    return tuple(map(int, value.split(".")))


def open_url(url, timeout=20):
    return urlopen(Request(url, headers={"User-Agent": "VisionBuddy-Origin/1",
        "Accept": "*/*"}), timeout=timeout)


def read(url, limit=1024**2, timeout=20):
    with open_url(url, timeout) as response:
        result = response.read(limit + 1)
    if len(result) > limit:
        raise ValueError("Unexpected response size")
    return result


def latest(repo):
    data = json.loads(read(f"https://api.github.com/repos/{OWNER}/{repo}/releases/latest"))
    tag = data["tag_name"]
    if not tag.startswith("v") or data.get("draft") or data.get("prerelease"):
        raise ValueError("Latest is not a stable release")
    version(tag[1:])
    return tag, data


def fetch_release(tag, release, stage):
    files = {row["name"]: row for row in release["assets"]}
    name = f"visionbuddy-{tag}.zip"
    urls = {key: f"https://github.com/{OWNER}/{LIBRARY}/releases/download/{tag}/{key}"
            for key in (name, "SHA256SUMS.txt")}
    for key, url in urls.items():
        if files[key]["browser_download_url"] != url:
            raise ValueError("Unexpected external download URL")
    checksum = read(urls["SHA256SUMS.txt"], 32768)
    expected = re.search(rb"(?m)^([a-f0-9]{64})  " + re.escape(name.encode()) + rb"\r?$", checksum)
    size = files[name]["size"]
    if not expected or type(size) is not int or not 0 < size <= MAX_ZIP:
        raise ValueError("Missing checksum or invalid archive size")
    path = stage / name
    digest = hashlib.sha256()
    received = 0
    with open_url(urls[name], 90) as response, path.open("wb") as target:
        while block := response.read(1024**2):
            received += len(block)
            if received > size:
                raise ValueError("Archive exceeded its published size")
            digest.update(block)
            target.write(block)
    actual = digest.hexdigest()
    if received != size or actual != expected[1].decode():
        raise ValueError("Archive SHA-256 or length differs from the public release")
    github_digest = files[name].get("digest")
    if github_digest and github_digest != "sha256:" + actual:
        raise ValueError("Archive SHA-256 differs from GitHub")
    return path


def unpack_verified(archive, tag, target):
    with ZipFile(archive) as bundle:
        infos = bundle.infolist()
        names = set()
        if len(infos) > 25000 or sum(info.file_size for info in infos) > MAX_ZIP:
            raise ValueError("Archive exceeds deployment limits")
        for info in infos:
            name = info.filename
            parts = PurePosixPath(name)
            if (not parts.parts or parts.as_posix() != name or parts.is_absolute()
                or any(piece in (".", "..") or piece.endswith((" ", ".")) for piece in parts.parts)
                or any(symbol in name for symbol in ("\\", ":", "\0"))
                or (not name.startswith("site/") and name not in ROOT_FILES)
                or info.is_dir() or stat.S_IFMT(info.external_attr >> 16) not in (0, stat.S_IFREG)
                or name.casefold() in names):
                raise ValueError("Invalid or duplicate archive path")
            names.add(name.casefold())
        release = tag[1:]
        if bundle.read("VERSION").decode().strip() != release:
            raise ValueError("Archive version mismatch")
        manifest = json.loads(bundle.read("manifest.json"))
        pair = json.loads(bundle.read("compatibility.json"))
        if (manifest["schemaVersion"] != 1 or manifest["libraryRelease"] != release
            or any(manifest.get(field) != pair.get(field) for field in ("minimumWorkbench", "rendererVersion"))
            or not isinstance(pair.get("rendererVersion"), int)):
            raise ValueError("Compatibility contract does not match the manifest")
        version(pair["minimumWorkbench"])
        if set(bundle.namelist()) != ROOT_FILES | set(manifest["files"]):
            raise ValueError("Files differ from the release manifest")
        for info in infos:
            raw = bundle.read(info)
            if info.filename.startswith("site/"):
                record = manifest["files"][info.filename]
                if len(raw) != record["size"] or hashlib.sha256(raw).hexdigest() != record["sha256"]:
                    raise ValueError("Invalid release file " + info.filename)
            dest = target / info.filename
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
    return pair


def health(port, release, attempts=24):
    base = f"http://127.0.0.1:{port}"
    for _ in range(attempts):
        try:
            marker = json.loads(read(base + "/latest.json", 32768, 3))
            if marker["libraryRelease"] == release and read(base + "/healthz", 32, 3).strip() == b"ok":
                return
        except (OSError, ValueError):
            pass
        time.sleep(1)
    raise RuntimeError(f"Origin did not become healthy for {release}")


def smoke(target, python, release):
    with closing(socket.socket()) as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    with tempfile.TemporaryFile() as log, subprocess.Popen(
        [str(python), "-B", str(target / "serve.py"), "--host", "127.0.0.1", "--port", str(port)],
        stdout=log, stderr=log
    ) as service:
        try:
            health(port, release)
            site = read(f"http://127.0.0.1:{port}/visual/index.html", 4*1024**2)
            if f"/releases/{release}/site/visual/".encode() not in site:
                raise RuntimeError("Staged site does not load its versioned scripts")
        finally:
            service.terminate()
            service.wait(timeout=10)


def switch(base, target):
    link = base / f".current-next-{os.getpid()}"
    link.symlink_to(target, target_is_directory=True)
    try:
        os.replace(link, base / "current")
    finally:
        link.unlink(missing_ok=True)


def restart():
    subprocess.run(["sudo", "-n", "systemctl", "restart", "visionbuddy.service"], check=True, timeout=45)


def apply(base, port):
    revisions = base / "releases"
    previous = (base / "current").resolve(strict=True)
    if previous.parent != revisions:
        raise ValueError("Current deployment is outside its release directory")
    old = (previous / "VERSION").read_text("utf8").strip()
    tag, metadata = latest(LIBRARY)
    target = revisions / tag[1:]
    release = target.name
    if version(release) <= version(old):
        health(port, old, attempts=3)
        print(f"VisionBuddy {old} is current", flush=True)
        return
    studio, studio_metadata = latest(STUDIO)
    studio_archive = f"talking-head-studio-{studio}.zip"
    if not any(item["name"] == studio_archive for item in studio_metadata["assets"]):
        raise ValueError("Published workbench lacks its downloadable Skill ZIP")
    with tempfile.TemporaryDirectory(prefix=".incoming-", dir=revisions) as temp:
        stage = Path(temp)
        archive = fetch_release(tag, metadata, stage)
        extracted = stage / "application"
        pair = unpack_verified(archive, tag, extracted)
        if version(studio[1:]) < version(pair["minimumWorkbench"]):
            raise ValueError(f"Waiting for Talking Head Studio {pair['minimumWorkbench']}")
        smoke(extracted, base / "venv/bin/python", release)
        if target.exists():
            # A failed attempt may have left the staged revision. Compare all content.
            if not all((target / f.relative_to(extracted)).is_file() and
                       (target / f.relative_to(extracted)).read_bytes() == f.read_bytes()
                       for f in extracted.rglob("*") if f.is_file()):
                raise ValueError("Release directory already exists with different contents")
        else:
            extracted.replace(target)
        switch(base, target)
        try:
            restart()
            health(port, release)
        except Exception:
            switch(base, previous)
            restart()
            health(port, old)
            raise
    print(f"Promoted VisionBuddy {release}; previous release {old} retained", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=Path("/opt/visionbuddy"))
    parser.add_argument("--port", type=int, default=18772)
    args = parser.parse_args()
    apply(args.base.resolve(), args.port)
