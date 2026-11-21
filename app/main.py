"""会議・講習会の録音を文字起こしして要約する Web アプリ。

起動: uvicorn app.main:app --reload
"""

from __future__ import annotations

import json
import os
import re
import secrets
import threading
import traceback
import uuid
from datetime import datetime
from pathlib import Path

import anthropic
from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .summarize import KINDS, api_available, manual_prompt, summarize
from .transcribe import transcribe

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

app = FastAPI(title="録音まとめ")

# GitHub Pages に置いた録音アプリ（別のアドレス）からの接続を許可する。
# 許可するのはここに書いたサイトだけ（他のサイトからは録音や要約を読めない）。
# config.env の ALLOWED_ORIGINS で変更できる（カンマ区切り）。
ALLOWED_ORIGINS = [
    o.strip().rstrip("/")
    for o in os.getenv("ALLOWED_ORIGINS", "https://kimu22734121-byte.github.io").split(",")
    if o.strip()
]


app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    # 公開サイト（GitHub Pages）から Tailscale 内の PC へ接続するときの、ブラウザの事前確認に応える
    allow_private_network=True,
)


# 文字起こしは CPU/GPU を大きく使うので、同時に 1 件ずつ処理する
_work_lock = threading.Lock()
_create_lock = threading.Lock()


# 保存フォルダ名 = ジョブ ID。録音日時から始まるので、エクスプローラーで探しやすい。
# 例: data/20261120-143005-a1b2c3d4/
_ID_RE = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{8}$")


def _new_job_id() -> str:
    return f"{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(4)}"


def _job_dir(job_id: str) -> Path:
    if not _ID_RE.match(job_id):
        try:
            uuid.UUID(job_id)  # 以前の形式の ID
        except ValueError:
            raise HTTPException(404, "ジョブが見つかりません")
    d = DATA_DIR / job_id
    if not d.is_dir():
        raise HTTPException(404, "ジョブが見つかりません")
    return d


def _fmt(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


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
        return "Claude API の認証に失敗しました。API キーを確認するか、「claude.ai に貼り付けて要約」を使ってください。"
    if isinstance(e, anthropic.PermissionDeniedError) or "credit balance" in str(e).lower():
        return "Claude API のクレジットが不足しています。チャージするか、「claude.ai に貼り付けて要約」を使ってください。"
    if isinstance(e, anthropic.RateLimitError):
        return "Claude API の利用上限に達しました。少し待って「要約をやり直す」を押してください。"
    if isinstance(e, anthropic.APIConnectionError):
        return "Claude API に接続できませんでした。ネットワークを確認してください。"
    if isinstance(e, anthropic.APIStatusError):
        return f"Claude API エラー ({e.status_code}): {e.message}"

    # ここから先は文字起こし（PC 側）のエラー。原因ごとに、次にすることを案内する。
    detail = f"{type(e).__name__}: {e}"[:300]
    text = detail.lower()
    if isinstance(e, MemoryError) or "out of memory" in text or "bad_alloc" in text:
        hint = ("PC のメモリが足りませんでした。config.env に WHISPER_MODEL=small と書いて start.bat を起動し直し、"
                "「やり直す」を押してください。")
    elif any(k in text for k in ("huggingface", "hf_hub", "localentrynotfound", "connection", "timed out", "proxy", "ssl")):
        hint = ("文字起こしモデルのダウンロードに失敗しました（初回だけ約 1.5GB をダウンロードします）。"
                "PC のインターネット接続を確認して「やり直す」を押してください。")
    elif any(k in text for k in ("invaliddata", "invalid data", "could not find codec", "no audio", "audio stream",
                                  "end of file", "moov atom")):
        hint = "録音ファイルを読み込めませんでした。録音が短すぎるか、ファイルが壊れている可能性があります。"
    elif isinstance(e, (FileNotFoundError, PermissionError)):
        hint = "録音ファイルが見つからないか、開けませんでした。data フォルダを移動・削除していないか確認してください。"
    else:
        hint = "「やり直す」を押してみてください。同じエラーが続く場合は、この文章を Claude に伝えてください。"
    return f"処理に失敗しました。{hint}（詳細: {detail}）"


def _summary_kwargs(meta: dict) -> dict:
    return dict(
        kind=meta.get("kind", "meeting"),
        title=meta.get("title", ""),
        notes=meta.get("notes", ""),
        marks=meta.get("marks", []),
        instructions=meta.get("instructions", ""),
    )


def _summarize_job(d: Path, transcript: str) -> None:
    meta = _read_meta(d)
    if meta.get("summary_mode") == "manual":
        _write_meta(d, status="transcribed", message="文字起こし完了。claude.ai に貼り付けて要約してください", progress=1.0)
        return
    _write_meta(d, status="summarizing", message="Claude で要約中…", progress=1.0)
    summary = summarize(transcript, **_summary_kwargs(meta))
    (d / "summary.md").write_text(summary, encoding="utf-8")
    _write_meta(d, status="done", message="完了")


def _process(d: Path, parts: list[Path] | None) -> None:
    """録音（途中で中断された場合は複数パート）を文字起こしして要約する。

    parts が None のときは保存済みの文字起こしを使って要約だけ行う。
    """
    try:
        if parts is not None:
            _write_meta(d, status="queued", message="順番待ち中…")
            with _work_lock:
                meta = _read_meta(d)
                _write_meta(d, status="transcribing", message="文字起こし中…", progress=0.0)
                texts: list[str] = []
                offset = 0.0
                for i, part in enumerate(parts):
                    if i:
                        texts.append(f"[{_fmt(offset)}] （録音が一時中断され、ここから再開）")
                    text, duration = transcribe(
                        part,
                        language=meta.get("language", "ja"),
                        hint=meta.get("notes", ""),
                        offset=offset,
                        on_progress=lambda p, i=i: _write_meta(d, progress=round((i + p) / len(parts), 3)),
                    )
                    if text:
                        texts.append(text)
                    offset += duration
                transcript = "\n".join(texts)
                (d / "transcript.txt").write_text(transcript, encoding="utf-8")
                _write_meta(d, duration=round(offset, 1))
        else:
            transcript = (d / "transcript.txt").read_text(encoding="utf-8")
        _summarize_job(d, transcript)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        _write_meta(d, status="error", message=_error_message(e))


def _parse_marks(raw: str) -> list[dict]:
    """録音アプリの「重要」マーク: [{"t": 秒, "note": "メモ"}, ...]"""
    try:
        items = json.loads(raw or "[]")
    except json.JSONDecodeError:
        raise HTTPException(400, "marks の形式が正しくありません")
    marks = []
    for m in items if isinstance(items, list) else []:
        try:
            t = max(0.0, float(m.get("t", 0)))
        except (TypeError, ValueError, AttributeError):
            continue
        marks.append({"t": round(t, 1), "note": str(m.get("note", ""))[:200]})
    return sorted(marks, key=lambda m: m["t"])[:500]


def _find_by_client_id(client_id: str) -> str | None:
    if not client_id:
        return None
    for d in DATA_DIR.iterdir():
        if (d / "meta.json").exists() and _read_meta(d).get("client_id") == client_id:
            return d.name
    return None


@app.post("/api/jobs")
async def create_job(
    audio: list[UploadFile] = File(...),
    kind: str = Form("meeting"),
    title: str = Form(""),
    notes: str = Form(""),
    instructions: str = Form(""),
    language: str = Form("ja"),
    marks: str = Form("[]"),
    client_id: str = Form(""),
    summary_mode: str = Form("auto"),
):
    """録音を受け付ける。audio は複数可（録音が中断・再開された場合のパート）。

    client_id は録音アプリが付ける ID。通信が切れて再送されても二重登録しない。
    kind: "meeting"（会議）/ "lecture"（講習会）/ "conversation"（会話）/ "other"（その他）
    instructions: まとめ方の希望（任意。例: 「3 行で」「手順書の形で」）
    summary_mode: "auto"（Claude API で自動要約）/ "manual"（claude.ai に貼り付けて要約）
    """
    client_id = client_id.strip()[:100]
    with _create_lock:
        if existing := _find_by_client_id(client_id):
            return {"id": existing, "duplicate": True}
        job_id = _new_job_id()
        d = DATA_DIR / job_id
        d.mkdir()
        _write_meta(d, id=job_id, client_id=client_id, status="uploading", created_at=datetime.now().isoformat(timespec="seconds"))

    parts: list[Path] = []
    for i, up in enumerate(audio):
        suffix = Path(up.filename or "").suffix.lower() or ".webm"
        if not suffix[1:].isalnum() or len(suffix) > 6:
            suffix = ".bin"
        path = d / f"audio_{i:03d}{suffix}"
        with path.open("wb") as f:
            while chunk := await up.read(1024 * 1024):
                f.write(chunk)
        parts.append(path)

    _write_meta(
        d,
        kind=kind if kind in KINDS else "other",
        title=title.strip(),
        notes=notes.strip(),
        instructions=instructions.strip()[:2000],
        language=language,
        marks=_parse_marks(marks),
        # API キーがなければ自動要約はできないので手動にする
        summary_mode="auto" if summary_mode == "auto" and api_available() else "manual",
        audio_parts=[p.name for p in parts],
        status="queued",
        message="受け付けました",
        progress=0.0,
    )
    threading.Thread(target=_process, args=(d, parts), daemon=True).start()
    return {"id": job_id}


@app.get("/api/jobs")
def list_jobs():
    jobs = []
    for d in DATA_DIR.iterdir():
        if (d / "meta.json").exists():
            m = _read_meta(d)
            if m.get("status") == "uploading":
                continue
            jobs.append({k: m.get(k) for k in ("id", "title", "kind", "created_at", "status", "duration", "summary_mode")})
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


@app.get("/api/config")
def get_config():
    """画面側で「自動要約」を選べるかどうかを判断するための情報。"""
    return {"api_available": api_available()}


@app.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: str):
    """文字起こしから最初にやり直す（文字起こしで失敗したときなど）。保存済みの録音を使う。"""
    d = _job_dir(job_id)
    meta = _read_meta(d)
    if meta.get("status") in ("queued", "transcribing", "summarizing"):
        raise HTTPException(409, "いま処理中です。終わるまでお待ちください")
    parts = [d / p for p in meta.get("audio_parts") or ([meta["audio"]] if meta.get("audio") else [])]
    if not parts or not all(p.exists() for p in parts):
        raise HTTPException(400, "録音ファイルが見つかりません")
    _write_meta(d, status="queued", message="やり直しを受け付けました", progress=0.0)
    threading.Thread(target=_process, args=(d, parts), daemon=True).start()
    return {"ok": True}


@app.post("/api/jobs/{job_id}/resummarize")
def resummarize(job_id: str):
    """文字起こしは再利用して、Claude API で要約する（やり直し・手動から自動への切り替え）。"""
    d = _job_dir(job_id)
    if not (d / "transcript.txt").exists():
        raise HTTPException(400, "文字起こしがまだありません")
    if not api_available():
        raise HTTPException(400, "API キーが設定されていないため自動要約は使えません")
    _write_meta(d, summary_mode="auto")
    threading.Thread(target=_process, args=(d, None), daemon=True).start()
    return {"ok": True}


@app.get("/api/jobs/{job_id}/prompt", response_class=PlainTextResponse)
def get_manual_prompt(job_id: str):
    """claude.ai に貼り付ける用のテキスト（要約の指示 + 文字起こし）。"""
    d = _job_dir(job_id)
    p = d / "transcript.txt"
    if not p.exists():
        raise HTTPException(400, "文字起こしがまだありません")
    return manual_prompt(p.read_text(encoding="utf-8"), **_summary_kwargs(_read_meta(d)))


@app.post("/api/jobs/{job_id}/summary")
def save_manual_summary(job_id: str, summary: str = Body(..., embed=True)):
    """claude.ai で作った要約を貼り付けて保存する。"""
    d = _job_dir(job_id)
    summary = summary.strip()
    if not summary:
        raise HTTPException(400, "要約が空です")
    (d / "summary.md").write_text(summary + "\n", encoding="utf-8")
    _write_meta(d, status="done", message="完了", summary_mode="manual")
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
@app.get("/api/jobs/{job_id}/audio/{part}")
def download_audio(job_id: str, part: int = 0):
    d = _job_dir(job_id)
    meta = _read_meta(d)
    parts = meta.get("audio_parts") or ([meta["audio"]] if meta.get("audio") else [])
    if not 0 <= part < len(parts):
        raise HTTPException(404)
    return FileResponse(d / parts[part])


# スマホ用の録音アプリ（GitHub Pages と同じファイル）
app.mount("/rec", StaticFiles(directory=ROOT / "docs", html=True), name="rec")
# PC 用の画面
app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")
