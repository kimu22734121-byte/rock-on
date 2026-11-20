"""文字起こしテキストを Claude で取りまとめる。

要約の方法は 2 通り:
- 自動: Claude API で要約（API キーが必要・従量課金）
- 手動: 要約の指示と文字起こしをまとめたテキスト（manual_prompt）を作り、
        ユーザーが claude.ai（無料プランでも可）に貼り付けて要約してもらう
"""

from __future__ import annotations

import os

import anthropic

MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")

_client: anthropic.Anthropic | None = None


def api_available() -> bool:
    """Claude API のキーが設定されているか（自動要約が使えるか）。"""
    return bool(os.getenv("ANTHROPIC_API_KEY", "").strip() or os.getenv("ANTHROPIC_AUTH_TOKEN", "").strip())


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # ANTHROPIC_API_KEY などから認証情報を読む
    return _client

SYSTEM_PROMPT = """あなたは会議・講習会の記録係です。
音声認識による文字起こしを読み、参加しなかった人が読んでも内容が分かる日本語の記録を Markdown で作成します。

- 文字起こしには誤認識・言い淀み・重複が含まれます。文脈から正しい語を推測して整えてください。ただし推測で事実を付け足さないでください。
- 聞き取れず判断できない箇所は「（聞き取り不明）」と書いてください。
- 重要な発言には文字起こしのタイムスタンプ [hh:mm:ss] を添えてください。後で録音を確認できるようにするためです。
- 文字起こしにない情報（日付・参加者名など）は書かず、該当項目は「記載なし」としてください。"""

TEMPLATES = {
    "meeting": """これは会議の録音です。次の構成でまとめてください。

# {title}
## 概要
（3〜5行）
## 議題と議論の内容
（議題ごとに見出しを立て、主な意見・論点を箇条書き）
## 決定事項
## アクションアイテム
| 内容 | 担当者 | 期限 |
## 未解決の課題・次回への持ち越し""",
    "lecture": """これは講習会・セミナーの録音です。次の構成でまとめてください。

# {title}
## 概要
（3〜5行）
## 主なトピック
（トピックごとに見出しを立て、説明された内容を整理）
## 重要なポイント・覚えておくべきこと
## 用語・キーワード
（講義に出てきた専門用語と簡単な説明）
## 質疑応答
## 復習・実践のために""",
}


def _fmt(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def build_user_message(
    transcript: str,
    kind: str = "meeting",
    title: str = "",
    notes: str = "",
    marks: list[dict] | None = None,
) -> str:
    """要約の指示と文字起こしをまとめたユーザーメッセージを作る。"""
    instruction = TEMPLATES.get(kind, TEMPLATES["meeting"]).format(
        title=title or "（タイトルを内容から付けてください）"
    )
    if notes:
        instruction += f"\n\n補足情報（ユーザー入力）:\n{notes}"
    if marks:
        listed = "\n".join(f"- [{_fmt(m['t'])}] {m.get('note') or '（メモなし）'}" for m in marks)
        instruction += (
            "\n\n録音中にユーザーが「ここ重要」とマークした時刻です。"
            "各時刻の前後（おおむね 1 分前〜30 秒後）で話されていた内容を特に重視してまとめに反映し、"
            "最後に「## 重要マーク箇所」という節を設けて、マークごとに時刻と、その場面で話されていた要点を 1〜3 行で書いてください。"
            "タイムスタンプは録音全体での経過時間です（多少ずれることがあります）。\n" + listed
        )
    return f"<transcript>\n{transcript}\n</transcript>\n\n{instruction}"


def manual_prompt(transcript: str, **kwargs) -> str:
    """claude.ai に貼り付けるための 1 つのテキスト（役割の説明 + 指示 + 文字起こし）。"""
    return f"{SYSTEM_PROMPT}\n\n{build_user_message(transcript, **kwargs)}"


def summarize(transcript: str, **kwargs) -> str:
    """Claude API で要約する。kwargs は build_user_message と同じ。"""
    if not transcript.strip():
        return "文字起こし結果が空でした。録音に音声が含まれているか確認してください。"

    with _get_client().beta.messages.stream(
        model=MODEL,
        max_tokens=64000,
        system=SYSTEM_PROMPT,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium"},
        # 安全分類器が誤って拒否した場合、サーバー側で別モデルに切り替えて続行する
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[
            {
                "role": "user",
                "content": build_user_message(transcript, **kwargs),
            }
        ],
    ) as stream:
        message = stream.get_final_message()

    if message.stop_reason == "refusal":
        raise RuntimeError("Claude がこの内容の要約を辞退しました。")

    text = "".join(b.text for b in message.content if b.type == "text").strip()
    if message.stop_reason == "max_tokens":
        text += "\n\n（※ 出力上限に達したため、要約が途中で切れています）"
    return text
