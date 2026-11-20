"""音声ファイルの文字起こし（faster-whisper をローカルで実行）。"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Callable

from faster_whisper import WhisperModel

# 精度と速度のバランス。GPU があるなら "large-v3"、軽くしたいなら "small"。
MODEL_SIZE = os.getenv("WHISPER_MODEL", "medium")
DEVICE = os.getenv("WHISPER_DEVICE", "auto")  # "cpu" / "cuda" / "auto"
COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "default")

_model: WhisperModel | None = None
_model_lock = threading.Lock()


def _get_model() -> WhisperModel:
    """モデルは重いので初回だけ読み込み、以後は使い回す。"""
    global _model
    with _model_lock:
        if _model is None:
            _model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
        return _model


def _fmt(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def transcribe(
    audio_path: Path,
    language: str = "ja",
    hint: str = "",
    on_progress: Callable[[float], None] | None = None,
) -> str:
    """音声を文字起こしし、[hh:mm:ss] 付きのテキストを返す。"""
    model = _get_model()
    segments, info = model.transcribe(
        str(audio_path),
        language=language or None,
        vad_filter=True,  # 無音区間を飛ばして速く・幻聴を減らす
        beam_size=5,
        # 参加者名・専門用語などを先に与えると、固有名詞の認識精度が上がる
        initial_prompt=hint or None,
    )
    lines: list[str] = []
    for seg in segments:
        text = seg.text.strip()
        if text:
            lines.append(f"[{_fmt(seg.start)}] {text}")
        if on_progress and info.duration:
            on_progress(min(seg.end / info.duration, 1.0))
    return "\n".join(lines)
