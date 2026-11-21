"""記録フォルダに「要約.html」を作る。

エクスプローラーでダブルクリックするとブラウザで開き、要約・重要マーク・文字起こしを読みながら
録音を再生できる。要約や文字起こしの [hh:mm:ss] を押すと、その時刻から再生する。
"""

from __future__ import annotations

import html
import re
from pathlib import Path

import markdown

VIEW_NAME = "要約.html"

KIND_LABELS = {"meeting": "🗣 会議", "lecture": "📚 講習会", "conversation": "💬 会話", "other": "📝 その他"}
MODEL_LABELS = {
    "claude-opus-5-5": "Opus 5.5",
    "claude-sonnet-5-5": "Sonnet 5.5",
    "claude-haiku-5-5": "Haiku 5.5",
    "claude.ai": "claude.ai（手動）",
}
_TS = re.compile(r"\[(\d{2}):(\d{2}):(\d{2})\]")


def _fmt(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def _link_times(escaped_html: str) -> str:
    """[hh:mm:ss] を、押すとその時刻から再生するリンクにする。"""
    def repl(m: re.Match) -> str:
        sec = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        return f'<a href="#" class="ts" data-t="{sec}">{m.group(0)}</a>'
    return _TS.sub(repl, escaped_html)


def _read(d: Path, name: str) -> str:
    p = d / name
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _yen(usd: float, rate: float) -> str:
    v = usd * rate
    if v < 0.1:
        return "0.1 円未満"
    return f"約 {v:.1f} 円" if v < 1 else f"約 {round(v):,} 円"


def write_view(d: Path, meta: dict, usd_jpy: float = 150.0) -> None:
    title = meta.get("title") or "（無題）"
    summary = _read(d, "summary.md")
    transcript = _read(d, "transcript.txt")
    parts = [p for p in (meta.get("audio_parts") or []) if (d / p).exists()]
    offsets = meta.get("part_offsets") or [0.0] * len(parts)
    if len(offsets) != len(parts):
        offsets = [0.0] * len(parts)

    info = [KIND_LABELS.get(meta.get("kind"), "📝 その他"), (meta.get("created_at") or "").replace("T", " ")[:16]]
    if meta.get("duration"):
        info.append(_fmt(meta["duration"]))
    if summary and meta.get("summary_model"):
        info.append("要約: " + MODEL_LABELS.get(meta["summary_model"], meta["summary_model"]))
    total = float(meta.get("total_cost_usd") or 0)
    if summary and meta.get("summary_model") == "claude.ai":
        info.append("料金: 無料（claude.ai）" + (f"・API {_yen(total, usd_jpy)}" if total else ""))
    elif total:
        info.append("料金: " + _yen(total, usd_jpy))

    if summary:
        # 要約の中の HTML はそのまま表示しない（文字として出す）
        summary_html = _link_times(markdown.markdown(summary.replace("<", "&lt;"), extensions=["tables", "sane_lists"]))
    elif meta.get("summary_deleted"):
        summary_html = '<p class="muted">要約は削除済みです。</p>'
    else:
        summary_html = '<p class="muted">要約はまだありません。</p>'

    if parts:
        audio_html = "".join(
            (f'<div class="muted">パート {i + 1}</div>' if len(parts) > 1 else "")
            + f'<audio controls preload="metadata" src="{html.escape(p)}" data-offset="{offsets[i]}"></audio>'
            for i, p in enumerate(parts)
        )
    elif meta.get("audio_deleted"):
        audio_html = '<p class="muted">録音ファイルは削除済みです。</p>'
    else:
        audio_html = ""

    marks = meta.get("marks") or []
    marks_html = (
        "<section><h2>★ 重要マーク</h2><ul class=\"marks\">"
        + "".join(
            f'<li><a href="#" class="ts" data-t="{int(m["t"])}">[{_fmt(m["t"])}]</a> {html.escape(m.get("note") or "")}</li>'
            for m in marks
        )
        + "</ul></section>"
        if marks else ""
    )

    if transcript:
        tx_html = f'<pre class="tx">{_link_times(html.escape(transcript))}</pre>'
    elif meta.get("transcript_deleted"):
        tx_html = '<p class="muted">文字起こしは削除済みです。</p>'
    else:
        tx_html = '<p class="muted">文字起こしはまだありません。</p>'

    page = f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
  :root {{ --bg:#f6f7f9; --card:#fff; --text:#1d2330; --sub:#5f6b7a; --line:#dde2e8; --accent:#2563eb; --star:#b45309; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#14171c; --card:#1d2129; --text:#e6e9ee; --sub:#9aa5b4; --line:#2e3440; --accent:#60a5fa; --star:#fbbf24; }}
  }}
  body {{ margin:0; background:var(--bg); color:var(--text); font-family:system-ui,"Hiragino Sans","Noto Sans JP","Yu Gothic UI",sans-serif; line-height:1.7; }}
  main {{ max-width:860px; margin:0 auto; padding:24px 16px 64px; }}
  h1 {{ font-size:1.5rem; margin:0 0 4px; }}
  .muted {{ color:var(--sub); font-size:.9rem; }}
  .player {{ position:sticky; top:0; background:var(--bg); padding:10px 0; z-index:2; border-bottom:1px solid var(--line); }}
  audio {{ width:100%; margin-top:4px; }}
  section {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px 20px; margin-top:16px; }}
  section h2:first-child {{ margin-top:0; font-size:1.1rem; }}
  .summary h1 {{ font-size:1.3rem; }} .summary h2 {{ font-size:1.1rem; margin-top:1.4em; }}
  table {{ border-collapse:collapse; width:100%; display:block; overflow-x:auto; }}
  th, td {{ border:1px solid var(--line); padding:6px 8px; }}
  a.ts {{ color:var(--accent); text-decoration:none; font-variant-numeric:tabular-nums; }}
  a.ts:hover {{ text-decoration:underline; }}
  .marks a.ts {{ color:var(--star); font-weight:700; }}
  .tx {{ white-space:pre-wrap; font-family:inherit; font-size:.92rem; margin:0; }}
  details summary {{ cursor:pointer; font-weight:700; }}
</style>
</head>
<body>
<main>
  <h1>{html.escape(title)}</h1>
  <div class="muted">{html.escape(" ・ ".join(i for i in info if i))}</div>
  {f'<div class="player">{audio_html}<div class="muted">[時刻] を押すと、その場面から再生します。</div></div>' if parts else audio_html}
  <section class="summary"><h2>要約</h2>{summary_html}</section>
  {marks_html}
  <section><details{" open" if not summary else ""}><summary>文字起こし</summary>{tx_html}</details></section>
  <p class="muted">録音まとめサーバー（rock-on）で作成。このファイルは、要約や文字起こしが変わると自動で作り直されます。</p>
</main>
<script>
// [hh:mm:ss] を押したら、その時刻を含むパートを、その位置から再生する
document.addEventListener("click", (e) => {{
  const a = e.target.closest("a.ts"); if (!a) return;
  e.preventDefault();
  const t = Number(a.dataset.t);
  const players = [...document.querySelectorAll("audio")];
  if (!players.length) return;
  let target = players[0];
  for (const p of players) if (Number(p.dataset.offset) <= t) target = p;
  players.forEach(p => {{ if (p !== target) p.pause(); }});
  target.currentTime = Math.max(0, t - Number(target.dataset.offset) - 2);
  target.play();
}});
</script>
</body>
</html>
"""
    tmp = d / (VIEW_NAME + ".tmp")
    tmp.write_text(page, encoding="utf-8")
    tmp.replace(d / VIEW_NAME)
