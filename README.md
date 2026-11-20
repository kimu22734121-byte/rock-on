# rock-on — 録音まとめ

会議や講習会を録音すると、**文字起こし → Claude による議事録・講義ノート作成** までを自動で行うアプリです。
次の 2 つのアプリでできています。

| アプリ | URL | 役割 |
|---|---|---|
| 📱 **録音アプリ**（スマホ用 PWA） | `/rec/` | 録音・「ここ重要」マーク・自動送信・まとめの閲覧 |
| 🖥 **まとめサーバー**（PC で動かす） | `/` | 文字起こし（Whisper）・要約（Claude）・PC 用の画面 |

```
 スマホ（iPhone / Android）                  PC（Windows など）
┌──────────────────────┐   HTTPS   ┌──────────────────────────────┐
│ 録音アプリ /rec/        │ ───────▶ │ まとめサーバー                  │
│ ・録音（5秒ごとに端末保存）│  音声送信  │ ・faster-whisper で文字起こし   │
│ ・★ここ重要マーク        │ ◀─────── │ ・Claude API で要約            │
│ ・まとめを見る・共有      │  要約取得  │ ・data/ に保存                │
└──────────────────────┘           └──────────────────────────────┘
```

## 録音アプリ（スマホ）の機能

- **ワンタップ録音**：一時停止・再開、録音レベル表示、録音中は画面が自動で消えない
- **★ ここ重要マーク**：押した時刻を記録。要約でその前後を重点的にまとめ、「重要マーク箇所」の節を作る。タップでメモも付けられる
- **停止したら自動送信**：サーバーに音声を送ると、文字起こしと要約が自動で始まる
- **データを失わない**：
  - 録音は 5 秒ごとにスマホ内（IndexedDB）に保存
  - 電波がなくても録音でき、つながったら自動で送信
  - 送信に失敗したら「記録」タブから再送できる
  - アプリが落ちても、次に開いたときに「送信」または「続きを録音」ができる
- **中断からの自動再開**：iPhone でバックグラウンドに回ってマイクが止まっても、アプリに戻ると続きから録音。中断前後の録音はサーバーでひとつにつながる
- **まとめを見る**：要約・文字起こし・重要マーク・録音の再生、コピーや共有（LINE・メールなど）

### 画面ロック中の録音について（重要）

ブラウザの制限で、Web アプリは画面ロック中の録音を保証できません。

| | 画面ロック・アプリ切り替え時 |
|---|---|
| Android（Chrome） | 多くの機種で録音が続く |
| iPhone（Safari） | 止まることがある → アプリに戻ると自動で続きから録音（中断中の音声は入らない） |

**長い会議では、画面をつけたままにしておくのが確実です**（録音中は自動で消えない設定になっています）。
完全なバックグラウンド録音が必要になったら、この Web アプリを Capacitor でネイティブアプリ化する方法があります。

## セットアップ（Windows）

1. [Python](https://www.python.org/downloads/) をインストール（3.12 以上。インストール画面で **「Add python.exe to PATH」にチェック**）
2. このフォルダの **`start.bat` をダブルクリック**
   - 初回は必要なライブラリを自動でインストールします（数分）
   - Claude API キー（https://console.anthropic.com で取得）を聞かれるので貼り付けて Enter。`config.env` に保存され、次回からは聞かれません
3. 「まとめサーバーを起動します」と表示されたら準備完了。PC のブラウザで http://localhost:8000 を開けます

| ファイル | 役割 |
|---|---|
| `start.bat` | サーバーを起動（初回セットアップ込み。止まっても 10 秒後に自動で再起動） |
| `setup_autostart.bat` | PC にサインインしたとき自動で起動するように登録 |
| `remove_autostart.bat` | 自動起動の登録を解除 |
| `config.env` | API キーなどの設定（`config.env.example` を参照） |

**つけっぱなしの PC で使う場合**：`start.bat` で一度起動できたことを確認してから `setup_autostart.bat` を実行してください。
自動起動はサインイン後に動くので、PC が再起動したときにサインイン画面で止まらないよう、Windows の自動サインインを設定しておくと安心です。

Mac / Linux では次のように起動します。

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
uvicorn app.main:app --port 8000
```

## スマホから使う（HTTPS 化）

スマホのブラウザでマイクを使うには **HTTPS** が必要です。いちばん簡単なのは **Tailscale**（個人利用は無料）です。
自分の端末どうしだけをつなぐので、**外部の人からはアクセスできず安全**で、外出先からも使えます。

1. PC とスマホの両方に [Tailscale](https://tailscale.com/download) を入れて、同じアカウントでログイン
2. Tailscale の管理画面（https://login.tailscale.com/admin/dns）で **MagicDNS** と **HTTPS Certificates** を有効にする
3. `start.bat` でまとめサーバーを起動したまま、別のコマンドプロンプトで:

```bat
tailscale serve --bg 8000
```

4. 表示された `https://<PC名>.<xxxx>.ts.net` に `/rec/` を付けて、スマホで開く
   例: `https://my-pc.tail1234.ts.net/rec/`
5. ホーム画面に追加すると、普通のアプリのように使えます
   - iPhone：Safari の共有ボタン →「ホーム画面に追加」
   - Android：Chrome のメニュー →「アプリをインストール」または「ホーム画面に追加」

> ⚠ このアプリにはログイン機能がありません。`--host 0.0.0.0` やポート開放でインターネットに直接公開しないでください。

## 設定（環境変数）

| 変数 | 既定値 | 説明 |
|---|---|---|
| `WHISPER_MODEL` | `medium` | `small`（軽い）/ `medium` / `large-v3`（高精度、GPU 推奨） |
| `WHISPER_DEVICE` | `auto` | `cpu` / `cuda` / `auto` |
| `WHISPER_COMPUTE_TYPE` | `default` | GPU なら `float16`、CPU で軽くするなら `int8` |
| `CLAUDE_MODEL` | `claude-opus-5-5` | 要約に使う Claude モデル |

初回の文字起こし時に Whisper モデル（medium で約 1.5GB）が自動でダウンロードされます。

**処理時間の目安（1 時間の録音）**：CPU + medium で 30〜60 分ほど、GPU + large-v3 で数分。
CPU で速くしたいときは `WHISPER_MODEL=small` と `WHISPER_COMPUTE_TYPE=int8` を試してください。

## 使い方のコツ

- 「補足」欄に **参加者名・専門用語** を書くと、文字起こしと要約の両方で固有名詞を正しく認識しやすくなります。
- 要約で API エラーが出ても、文字起こしは保存されています。「要約をやり直す」で要約だけ再実行できます。
- スマホは話者の近く（机の中央など）に置くと、認識精度が上がります。

## 構成

```
app/main.py           まとめサーバー（受付・ジョブ管理・結果配信）
app/transcribe.py     faster-whisper による文字起こし
app/summarize.py      Claude API による要約（会議 / 講習会テンプレート、重要マーク反映）
static/index.html     PC 用の画面（録音・アップロード・結果表示）
static/rec/           スマホ用 録音アプリ（PWA）
  index.html          画面と録音処理
  sw.js               オフライン起動用 Service Worker
  manifest.webmanifest, icon-*.png
data/<id>/            録音・文字起こし・要約の保存先（git 管理外）
```

### API（録音アプリ ⇔ サーバー）

| メソッド | パス | 内容 |
|---|---|---|
| POST | `/api/jobs` | 録音を送信（`audio` 複数可、`kind`, `title`, `notes`, `marks`(JSON), `client_id`） |
| GET | `/api/jobs` | 一覧 |
| GET | `/api/jobs/{id}` | 状態・要約・文字起こし・マーク |
| POST | `/api/jobs/{id}/resummarize` | 要約だけやり直す |
| GET | `/api/jobs/{id}/audio/{n}` | 録音（n 番目のパート） |

`client_id` が同じ送信は二重登録されません（通信が切れて再送しても安全）。

## 費用について

Claude API は従量課金です。1 時間の会議（文字起こし 2〜3 万文字ほど）の要約で、数十円程度です。
文字起こしは PC 上で動くため、費用はかかりません。
