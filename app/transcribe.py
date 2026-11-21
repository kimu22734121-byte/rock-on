"""音声ファイルの文字起こし（faster-whisper をローカルで実行）。"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Callable

from faster_whisper import WhisperModel

# 精度と速度のバランス。GPU があるなら "large-v3"、軽くしたいなら "small"。
MODEL_SIZE = os.getenv("WHISPER_MODEL", "medium")
# 既定は CPU。NVIDIA の GPU があっても、GPU 用の部品（CUDA / cuDNN）が入っていない PC が多く、
# そのままだと「cublas64_12.dll が見つからない」で止まるため。GPU を使うなら config.env に WHISPER_DEVICE=cuda。
DEVICE = os.getenv("WHISPER_DEVICE", "cpu")  # "cpu" / "cuda" / "auto"
# CPU では int8 が速い（精度の差はわずか）。GPU では元の精度のまま。
COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8" if DEVICE == "cpu" else "default")

_model: WhisperModel | None = None
_model_lock = threading.Lock()
_force_cpu = False  # GPU で失敗したら、以後は CPU で動かす


def _is_gpu_error(e: Exception) -> bool:
    """NVIDIA の GPU 用部品（CUDA / cuDNN / cuBLAS）が足りないときのエラーか。"""
    text = str(e).lower()
    return any(k in text for k in ("cuda", "cudnn", "cublas", "nvidia", "gpu"))


def _get_model() -> WhisperModel:
    """モデルは重いので初回だけ読み込み、以後は使い回す。"""
    global _model, _force_cpu
    with _model_lock:
        if _model is None:
            device = "cpu" if _force_cpu else DEVICE
            try:
                _model = WhisperModel(MODEL_SIZE, device=device, compute_type=COMPUTE_TYPE)
            except Exception as e:  # noqa: BLE001
                if device == "cpu" or not _is_gpu_error(e):
                    raise
                print(f"[文字起こし] GPU が使えないため CPU に切り替えます: {e}")
                _force_cpu = True
                _model = WhisperModel(MODEL_SIZE, device="cpu", compute_type=COMPUTE_TYPE)
        return _model


def _switch_to_cpu() -> None:
    global _model, _force_cpu
    with _model_lock:
        _force_cpu = True
        _model = None


def _fmt(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def transcribe(*args, **kwargs) -> tuple[str, float]:
    """文字起こし。GPU の部品が足りずに途中で失敗したら、CPU に切り替えてもう一度行う。"""
    try:
        return _transcribe(*args, **kwargs)
    except Exception as e:  # noqa: BLE001
        if _force_cpu or DEVICE == "cpu" or not _is_gpu_error(e):
            raise
        print(f"[文字起こし] GPU で失敗したため CPU でやり直します: {e}")
        _switch_to_cpu()
        return _transcribe(*args, **kwargs)


def _transcribe(
    audio_path: Path,
    language: str = "ja",
    hint: str = "",
    offset: float = 0.0,
    on_progress: Callable[[float], None] | None = None,
) -> tuple[str, float]:
    """音声を文字起こしし、([hh:mm:ss] 付きのテキスト, 音声の長さ秒) を返す。

    offset はタイムスタンプに足す秒数（複数パートをつなぐとき用）。
    """
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
            lines.append(f"[{_fmt(offset + seg.start)}] {text}")
        if on_progress and info.duration:
            on_progress(min(seg.end / info.duration, 1.0))
    return "\n".join(lines), float(info.duration or 0.0)
