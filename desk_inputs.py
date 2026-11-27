"""Read manuscript text, subtitle cues, and optional local speech timing."""

from functools import lru_cache
from importlib.util import find_spec
import math
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory
from threading import Lock
import os
from html import unescape

import manuscript_annotations as annotations

TEXT_LIMIT = 120_000
CUE_LIMIT = 4000
VIDEO_LIMIT = 2 * 1024 ** 3
STAMP = re.compile(r"(\d{2,}):([0-5]\d):([0-5]\d)[,.](\d{3})")
TIMING = re.compile(r"^\s*(\S+)\s*-->\s*(\S+)(?:[ \t]+.*)?$")
VOICE_MODELS = ("tiny", "base", "small", "medium", "large", "turbo")
VOICE_LOCK = Lock()
SILENCE = re.compile(r"silence_(start|end):\s*([\d.]+)")


def text_input(value):
    if not isinstance(value, str) or not value.strip() or len(value) > TEXT_LIMIT:
        raise ValueError("请提供 1 至 12 万字的稿件或字幕。")
    return value.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")


def time_value(stamp):
    match = STAMP.fullmatch(stamp)
    if not match:
        raise ValueError(f"SRT 时间码无法读取：{stamp}")
    h, m, s, ms = map(int, match.groups())
    return h * 3600 + m * 60 + s + ms / 1000


def read_srt(text):
    cues = []
    for index, block in enumerate(re.split(r"\n[ \t]*\n", text.strip()), 1):
        lines = block.split("\n")
        if lines[0].strip().isdecimal():
            lines.pop(0)
        timing = TIMING.fullmatch(lines[0]) if lines else None
        if not timing:
            raise ValueError(f"第 {index} 段字幕缺少有效的 SRT 时间行。")
        start, end = map(time_value, timing.groups())
        caption = unescape(re.sub(r"</?(?:i|b|u|font)(?:\s[^<>]*)?>", "", "\n".join(lines[1:]), flags=re.I))
        if not caption.strip():
            raise ValueError(f"第 {index} 段字幕没有正文。")
        cues.append({"start": start, "end": end, "text": caption})
    return cues


def real_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_cues(cues, duration):
    if not isinstance(cues, list) or not 1 <= len(cues) <= CUE_LIMIT:
        raise ValueError("请提供 1 至 4000 段带时间的字幕。")
    validated = []
    previous = -1
    total = 0
    for row in cues:
        start, end, text = (row.get(key) for key in ("start", "end", "text")) if isinstance(row, dict) else (None,) * 3
        if (not real_number(start) or not real_number(end) or not 0 <= start < end
                or previous > start or end > 24 * 3600 or round(start, 3) >= round(end, 3)):
            raise ValueError("字幕起止时间无效或未按起始时间排序。")
        if duration is not None and (start >= duration or end > duration + .15):
            raise ValueError("字幕超出视频时长。请检查这份字幕是否对应当前视频。")
        text = text_input(text).strip()
        total += len(text)
        if total > TEXT_LIMIT:
            raise ValueError("字幕正文最多支持 12 万字。")
        validated.append({"start": round(start, 3), "end": round(end, 3), "text": text})
        previous = start
    return validated


def input_source(source):
    if not isinstance(source, dict):
        raise ValueError("找不到口播稿或字幕。")
    kind = source.get("kind")
    if kind == "script":
        return {"kind": kind, "text": text_input(source.get("text"))}, None
    if kind not in ("srt", "transcript"):
        raise ValueError("请选择口播稿、SRT 或有声视频。")
    duration = source.get("duration")
    if duration is not None and (not real_number(duration) or not 0 < duration <= 24 * 3600):
        raise ValueError("视频时长无效。")
    if kind == "srt":
        text = text_input(source.get("text"))
        return {"kind": kind, "text": text, "duration": duration}, validate_cues(read_srt(text), duration)
    cues = validate_cues(source.get("cues"), duration)
    return {"kind": kind, "cues": cues, "duration": duration}, cues


def cue_lines(text):
    """Join wrapped caption text while retaining separate visual directions."""
    wrapped = []
    for line in text.splitlines():
        if annotations.MARKER.search(line) and not annotations.spoken(line).strip():
            if wrapped:
                yield " ".join(wrapped)
                wrapped = []
            yield line.strip()
        elif line.strip():
            wrapped.append(line.strip())
    if wrapped:
        yield " ".join(wrapped)


def manuscript(source, cues):
    if cues is None:
        clean, units, bindings, errors = annotations.analyze(source["text"])
        return clean, units, bindings, errors
    raw_lines, line_cues = [], []
    for cue in cues:
        for line in cue_lines(cue["text"]):
            raw_lines.append(line)
            if not (annotations.MARKER.search(line) and not annotations.spoken(line).strip()):
                line_cues.append(cue)
    clean, units, bindings, errors = annotations.analyze("\n".join(raw_lines))
    cursor, line_number = 0, 0
    for unit in units:
        line_number += clean.count("\n", cursor, unit["offset"])
        cursor = unit["offset"]
        cue = line_cues[line_number]
        unit["time"] = {key: cue[key] for key in ("start", "end")}
    return clean, units, bindings, errors


def read_caption_file(path):
    data = path.read_bytes()
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("gb18030")


def speech_windows(log, duration):
    if not real_number(duration) or duration <= 0:
        return []
    ranges = []
    cursor = 0.0
    for kind, value in SILENCE.findall(log):
        value = float(value)
        if kind == "start" and value - cursor > .14:
            ranges.extend((max(0., cursor - .10), min(duration, value + .10)))
        if kind == "end":
            cursor = value
    if duration - cursor > .14:
        ranges.extend((max(0., cursor - .10), duration))
    return ranges


def model_directory():
    return Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "whisper"


def available_models():
    if find_spec("whisper") is None or find_spec("torch") is None or not shutil.which("ffmpeg"):
        return []
    return [name for name in VOICE_MODELS if (model_directory() / f"{name}.pt").is_file()]


def probe_duration(video):
    probe = shutil.which("ffprobe")
    if not probe:
        return None
    result = subprocess.run(
        [probe, "-v", "error", "-protocol_whitelist", "file,pipe", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video.resolve())],
        capture_output=True, text=True, timeout=30,
    )
    try:
        return float(result.stdout.strip())
    except ValueError as exc:
        raise ValueError("无法读取视频时长，请确认原片能正常播放。") from exc


@lru_cache(maxsize=1)
def load_voice_model(checkpoint, device):
    import whisper

    return whisper.load_model(str(checkpoint), device=device)


def transcribe(video, model_name, language="auto"):
    if model_name not in available_models():
        raise ValueError("所选本机 Whisper 模型不可用。请选择现有模型或导入配套 SRT。")
    if language not in ("auto", "zh", "en"):
        raise ValueError("语言请选择自动识别、中文或英文。")
    duration = probe_duration(video)
    with TemporaryDirectory(prefix="visionbuddy-audio-") as folder:
        wav = Path(folder) / "audio.wav"
        result = subprocess.run(
            [shutil.which("ffmpeg"), "-nostdin", "-v", "info", "-protocol_whitelist", "file,pipe",
             "-i", str(video.resolve()), "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000",
             "-af", "aresample=async=1:first_pts=0,silencedetect=noise=-46dB:d=0.65",
             "-c:a", "pcm_s16le", str(wav)],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=300,
        )
        if result.returncode:
            raise ValueError("视频没有可转写的音轨，或本机 FFmpeg 无法读取它。")
        log = result.stderr.decode("utf8", "replace")
        spoken_ranges = speech_windows(log, duration)
        if duration is not None and not spoken_ranges:
            raise ValueError("视频声音接近静音，无法定位口播。请导入 SRT 或粘贴口播稿。")
        import torch

        device = "cuda" if torch.cuda.is_available() else "cpu"
        with VOICE_LOCK:
            model = load_voice_model(model_directory() / f"{model_name}.pt", device)
            result = model.transcribe(str(wav), language=None if language == "auto" else language,
                                      verbose=None, fp16=device == "cuda")
    cues = []
    for row in result["segments"]:
        start, end = row["start"], min(row["end"], duration) if duration else row["end"]
        if end > start and row["text"].strip():
            cues.append({"start": start, "end": end, "text": row["text"].strip()})
    if not cues:
        raise ValueError("语音模型没有识别到口播内容。可另选 SRT 或粘贴口播稿。")
    return {"kind": "transcript", "cues": cues, "duration": duration}
