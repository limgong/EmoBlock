"""Local Basic Pitch integration for turning an audio reference into MIDI."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from runtime_config import data_root
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WORKER = ROOT / "audio_import_worker.py"
SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}


def resolve_basic_pitch_python(explicit=None):
    """Return a Python executable that has the project's Basic Pitch runtime."""
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    configured = os.environ.get("EMOBLOCKS_BASIC_PITCH_PYTHON")
    if configured:
        candidates.append(Path(configured))
    project_root = ROOT.parents[1]
    candidates.extend([
        project_root / "work" / "basic-pitch-venv" / "Scripts" / "python.exe",
        project_root / "work" / "basic-pitch-venv" / "bin" / "python",
        project_root / ".venv-basic-pitch" / "bin" / "python",
        ROOT / ".basic-pitch-venv" / "Scripts" / "python.exe",
    ])
    if importlib.util.find_spec("basic_pitch") is not None:
        candidates.append(Path(sys.executable))
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise RuntimeError(
        "未找到 Basic Pitch 本地环境。请在项目根目录创建 "
        "work/basic-pitch-venv，并安装 requirements-basic-pitch.txt；"
        "也可用 EMOBLOCKS_BASIC_PITCH_PYTHON 指定 Python。"
    )


def _safe_stem(path):
    cleaned = re.sub(r"[^\w\-.]+", "_", path.stem, flags=re.UNICODE).strip("_.")
    return cleaned[:60] or "audio"


def transcribe_audio(audio_path, bpm, output_root=None, python_executable=None,
                     worker_path=None, timeout=1800):
    """Transcribe one audio file and return durable MIDI/provenance paths."""
    source = Path(audio_path).expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"音频文件不存在：{source}")
    if source.suffix.lower() not in SUPPORTED_EXTENSIONS:
        kinds = " / ".join(sorted(ext[1:].upper() for ext in SUPPORTED_EXTENSIONS))
        raise ValueError(f"不支持 {source.suffix or '无扩展名'}；请选择 {kinds} 音频。")
    try:
        bpm = float(bpm)
    except (TypeError, ValueError) as exc:
        raise ValueError("BPM 必须是 40～220 的数字。") from exc
    if not 40 <= bpm <= 220:
        raise ValueError("BPM 必须在 40～220 之间。")

    python = resolve_basic_pitch_python(python_executable)
    worker = Path(worker_path or WORKER).resolve()
    if not worker.is_file():
        raise RuntimeError(f"缺少音频转写组件：{worker}")

    output_root = Path(output_root or data_root() / "audio_imports").resolve()
    fingerprint = hashlib.sha256(
        f"{source}|{source.stat().st_size}|{source.stat().st_mtime_ns}|{bpm}".encode("utf-8")
    ).hexdigest()[:10]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    destination = output_root / f"{stamp}-{_safe_stem(source)}-{fingerprint}"
    destination.mkdir(parents=True, exist_ok=False)
    midi_path = destination / f"{_safe_stem(source)}-basic-pitch.mid"
    metadata_path = destination / "source.json"

    command = [str(python), str(worker), str(source), str(midi_path), str(bpm)]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout,
            check=False, creationflags=creationflags,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Basic Pitch 转写超时；请先裁短音频后重试。") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout or "未知错误").strip()[-1800:]
        raise RuntimeError(f"Basic Pitch 转写失败：\n{detail}")
    if not midi_path.is_file() or midi_path.stat().st_size == 0:
        raise RuntimeError("Basic Pitch 未生成有效 MIDI。")

    summary = {}
    for line in reversed(result.stdout.splitlines()):
        try:
            summary = json.loads(line)
            break
        except json.JSONDecodeError:
            continue
    metadata = {
        "schema": "emoblocks.audio-import.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_audio": str(source),
        "generated_midi": str(midi_path),
        "bpm": bpm,
        "engine": "spotify/basic-pitch 0.4.0",
        "summary": summary,
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "audio_path": str(source),
        "midi_path": str(midi_path),
        "metadata_path": str(metadata_path),
        "bpm": bpm,
        **summary,
    }
