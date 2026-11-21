"""録音ファイルを、どの再生ソフトでも早送り・巻き戻しできる m4a に変換する。

ブラウザの録音（MediaRecorder）で作った webm や、iPhone の録音（断片化した mp4）には
全体の長さや目次が入っていないため、Windows の再生ソフトなどでシークできない。
文字起こしの部品（PyAV）に入っている FFmpeg で、AAC の m4a に作り直す。
"""

from __future__ import annotations

import re
from pathlib import Path

import av

# 変換するもの: ブラウザ録音でよく使われる形式と、録音アプリが送る part0.webm / part0.m4a
_CONVERT_EXT = {".webm", ".weba", ".ogg", ".opus", ".oga", ".mkv"}
_RECORDER_NAME = re.compile(r"^part\d+\.(webm|m4a|mp4|aac)$", re.I)


def needs_conversion(original_name: str, saved: Path) -> bool:
    return saved.suffix.lower() in _CONVERT_EXT or bool(_RECORDER_NAME.match(original_name or ""))


def to_m4a(src: Path) -> Path:
    """src を同じ場所の .m4a に変換し、新しいファイルのパスを返す（src は消さない）。"""
    dst = src.with_suffix(".m4a")
    if dst == src:
        dst = src.with_name(src.stem + "_play.m4a")
    tmp = dst.with_name(dst.stem + ".converting.m4a")
    rate = 24000  # 話し声には十分。変換が速く、ファイルも小さい
    with av.open(str(src)) as inp, av.open(str(tmp), "w", format="mp4", options={"movflags": "+faststart"}) as out:
        in_stream = next(s for s in inp.streams if s.type == "audio")
        out_stream = out.add_stream("aac", rate=rate, layout="mono")
        out_stream.bit_rate = 64000
        resampler = av.AudioResampler(format="fltp", layout="mono", rate=rate)
        for frame in inp.decode(in_stream):
            frame.pts = None
            for f in resampler.resample(frame):
                for packet in out_stream.encode(f):
                    out.mux(packet)
        for f in resampler.resample(None):
            for packet in out_stream.encode(f):
                out.mux(packet)
        for packet in out_stream.encode(None):
            out.mux(packet)
    tmp.replace(dst)
    return dst
