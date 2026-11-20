"""会議・講習会の録音を文字起こしして要約する Web アプリ。

起動: uvicorn app.main:app --reload
"""

from __future__ import annotations

import json
import threading
import traceback
import uuid
from datetime import datetime
from pathlib import Path

import anthropic
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .summarize import summarize
from .transcribe import transcribe

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

app = FastAPI(title="録音まとめ")

# 文字起こしは CPU/GPU を大きく使うので、同時に 1 件ずつ処理する
_work_lock = threading.Lock()


def _job_dir(job_id: str) -> Path:
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(404, "ジョブが見つかりません")
    d = DATA_DIR / job_id
    if not d.is_dir():
        raise HTTPException(404, "ジョブが見つかりません")
    return d


def _read_meta(d: Path) -> dict:
    return json.loads((d / "meta.json").read_text(encoding="utf-8"))


def _write_meta(d: Path, **updates) -> dict:
    meta = _read_meta(d) if (d / "meta.json").exists() else {}
    meta.update(updates)
    tmp = d / "meta.json.tmp"
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(d / "meta.json")
    return meta


def _error_message(e: Exception) -> str:
    if isinstance(e, anthropic.AuthenticationError) or "authentication method" in str(e):
        return "Claude API の認証に失敗しました。ANTHROPIC_API_KEY を設定してください。"
    if isinstance(e, anthropic.RateLimitError):
        return "Claude API の利用上限に達しました。少し待って「要約をやり直す」を押してください。"
    if isinstance(e, anthropic.APIConnectionError):
        return "Claude API に接続できませんでした。ネットワークを確認してください。"
    if isinstance(e, anthropic.APIStatusError):
        return f"Claude API エラー ({e.status_code}): {e.message}"
    return f"処理に失敗しました: {e}"


def _summarize_job(d: Path, transcript: str) -> None:
    meta = _read_meta(d)
    _write_meta(d, status="summarizing", message="Claude で要約中…", progress=1.0)
    summary = summarize(
        transcript,
        kind=meta.get("kind", "meeting"),
        title=meta.get("title", ""),
        notes=meta.get("notes", ""),
    )
    (d / "summary.md").write_text(summary, encoding="utf-8")
    _write_meta(d, status="done", message="完了")


def _process(d: Path, audio: Path | None) -> None:
    """audio が None のときは保存済みの文字起こしを使って要約だけ行う。"""
    try:
        if audio is not None:
            _write_meta(d, status="queued", message="順番待ち中…")
            with _work_lock:
                _write_meta(d, status="transcribing", message="文字起こし中…", progress=0.0)
                transcript = transcribe(
                    audio,
                    language=_read_meta(d).get("language", "ja"),
                    hint=_read_meta(d).get("notes", ""),
                    on_progress=lambda p: _write_meta(d, progress=round(p, 3)),
                )
                (d / "transcript.txt").write_text(transcript, encoding="utf-8")
        else:
            transcript = (d / "transcript.txt").read_text(encoding="utf-8")
        _summarize_job(d, transcript)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        _write_meta(d, status="error", message=_error_message(e))


@app.post("/api/jobs")
async def create_job(
    audio: UploadFile = File(...),
    kind: str = Form("meeting"),
    title: str = Form(""),
    notes: str = Form(""),
    language: str = Form("ja"),
):
    job_id = str(uuid.uuid4())
    d = DATA_DIR / job_id
    d.mkdir()
    suffix = Path(audio.filename or "").suffix.lower() or ".webm"
    if not suffix[1:].isalnum() or len(suffix) > 6:
        suffix = ".bin"
    audio_path = d / f"audio{suffix}"
    with audio_path.open("wb") as f:
        while chunk := await audio.read(1024 * 1024):
            f.write(chunk)

    _write_meta(
        d,
        id=job_id,
        kind=kind if kind in ("meeting", "lecture") else "meeting",
        title=title.strip(),
        notes=notes.strip(),
        language=language,
        audio=audio_path.name,
        created_at=datetime.now().isoformat(timespec="seconds"),
        status="queued",
        message="受け付けました",
        progress=0.0,
    )
    threading.Thread(target=_process, args=(d, audio_path), daemon=True).start()
    return {"id": job_id}


@app.get("/api/jobs")
def list_jobs():
    jobs = []
    for d in DATA_DIR.iterdir():
        if (d / "meta.json").exists():
            m = _read_meta(d)
            jobs.append({k: m.get(k) for k in ("id", "title", "kind", "created_at", "status")})
    jobs.sort(key=lambda j: j.get("created_at") or "", reverse=True)
    return jobs


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    d = _job_dir(job_id)
    meta = _read_meta(d)
    for name, key in (("transcript.txt", "transcript"), ("summary.md", "summary")):
        p = d / name
        meta[key] = p.read_text(encoding="utf-8") if p.exists() else None
    return meta


@app.post("/api/jobs/{job_id}/resummarize")
def resummarize(job_id: str):
    """文字起こしは再利用して要約だけやり直す（API エラー時など）。"""
    d = _job_dir(job_id)
    if not (d / "transcript.txt").exists():
        raise HTTPException(400, "文字起こしがまだありません")
    threading.Thread(target=_process, args=(d, None), daemon=True).start()
    return {"ok": True}


@app.get("/api/jobs/{job_id}/summary.md", response_class=PlainTextResponse)
def download_summary(job_id: str):
    p = _job_dir(job_id) / "summary.md"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="text/markdown; charset=utf-8", filename="summary.md")


@app.get("/api/jobs/{job_id}/transcript.txt", response_class=PlainTextResponse)
def download_transcript(job_id: str):
    p = _job_dir(job_id) / "transcript.txt"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="text/plain; charset=utf-8", filename="transcript.txt")


@app.get("/api/jobs/{job_id}/audio")
def download_audio(job_id: str):
    d = _job_dir(job_id)
    return FileResponse(d / _read_meta(d)["audio"])


app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")
