# rock-on — 録音まとめ

会議や講習会をブラウザで録音（または録音ファイルをアップロード）すると、
**文字起こし → Claude による議事録・講義ノート作成** までを自動で行う Web アプリです。

- 🎙 ブラウザで録音（一時停止・再開あり、長時間録音対応）／録音済みファイルのアップロード
- 📝 文字起こしは **faster-whisper** を手元の PC で実行（無料・音声は外部に送信されない）
- 🤖 要約は **Claude API**（文字起こしテキストのみ送信）
  - 会議モード: 概要・議題ごとの議論・決定事項・アクションアイテム（担当/期限）・持ち越し課題
  - 講習会モード: 概要・トピック別の内容・重要ポイント・用語集・質疑応答・復習のヒント
- ⏱ 要約の重要箇所にタイムスタンプ付き（録音をその位置から聞き直せる）
- 💾 結果は `data/` に保存され、履歴から再表示・Markdown / テキストでダウンロード可能

## 必要なもの

- Python 3.10 以上
- Claude API キー（https://console.anthropic.com で取得）
- （任意）NVIDIA GPU があると文字起こしが大幅に速くなります

## セットアップ

```bash
python -m venv .venv
source .venv/bin/activate   # Windows は .venv\Scripts\activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...   # Windows は set ANTHROPIC_API_KEY=...
```

## 起動

```bash
uvicorn app.main:app --port 8000
```

ブラウザで **http://localhost:8000** を開きます。

> ⚠ マイク録音は `localhost` または HTTPS のページでしか使えません。
> 別の PC やスマホから使う場合は HTTPS 化（リバースプロキシ等）が必要です。
> ファイルのアップロードはどこからでも使えます。

初回の文字起こし時に Whisper モデル（medium で約 1.5GB）が自動でダウンロードされます。

## 設定（環境変数）

| 変数 | 既定値 | 説明 |
|---|---|---|
| `WHISPER_MODEL` | `medium` | `small`（軽い）/ `medium` / `large-v3`（高精度、GPU 推奨） |
| `WHISPER_DEVICE` | `auto` | `cpu` / `cuda` / `auto` |
| `WHISPER_COMPUTE_TYPE` | `default` | GPU なら `float16`、CPU で軽くするなら `int8` |
| `CLAUDE_MODEL` | `claude-opus-5-5` | 要約に使う Claude モデル |

**処理時間の目安（1 時間の録音）**: CPU + medium で 30〜60 分程度、GPU + large-v3 で数分。
CPU で速くしたい場合は `WHISPER_MODEL=small WHISPER_COMPUTE_TYPE=int8` を試してください。

## 使い方のコツ

- 「補足」欄に **参加者名・専門用語** を書くと、文字起こしと要約の両方で固有名詞の精度が上がります。
- 要約で API エラーが出ても、文字起こしは保存済みです。「要約をやり直す」で要約だけ再実行できます。
- 録音中は PC をスリープさせないでください（対応ブラウザでは画面のスリープを自動で防ぎます）。

## 構成

```
app/main.py        FastAPI サーバー（アップロード受付・ジョブ管理・結果配信）
app/transcribe.py  faster-whisper による文字起こし
app/summarize.py   Claude API による要約（会議 / 講習会テンプレート）
static/index.html  録音・アップロード・結果表示の画面
data/<id>/         録音・文字起こし・要約の保存先（git 管理外）
```

## 費用について

Claude API は従量課金です。1 時間の会議の文字起こし（約 2〜3 万文字）の要約で、おおよそ数十円程度です。
文字起こしはローカル実行のため費用はかかりません。
