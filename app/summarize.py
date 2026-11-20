"""文字起こしテキストを Claude で取りまとめる。"""

from __future__ import annotations

import os

import anthropic

MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")

_client = anthropic.Anthropic()  # ANTHROPIC_API_KEY などから認証情報を読む

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


def summarize(transcript: str, kind: str = "meeting", title: str = "", notes: str = "") -> str:
    if not transcript.strip():
        return "文字起こし結果が空でした。録音に音声が含まれているか確認してください。"

    instruction = TEMPLATES.get(kind, TEMPLATES["meeting"]).format(
        title=title or "（タイトルを内容から付けてください）"
    )
    if notes:
        instruction += f"\n\n補足情報（ユーザー入力）:\n{notes}"

    with _client.beta.messages.stream(
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
                "content": f"<transcript>\n{transcript}\n</transcript>\n\n{instruction}",
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
