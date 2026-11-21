"""データの保存場所。

複数のサーバーのデータを 1 か所にそろえるため、Windows で D ドライブがある PC では
  D:\\Server\\rock-on\\
      data\\     録音・文字起こし・要約（記録ごとのフォルダ）
      models\\   文字起こしモデル（約 1.5GB）
      _このフォルダについて.txt
に保存する。config.env の STORAGE_DIR で場所を変えられる。
D ドライブがない PC では、これまでどおりプログラムのフォルダの data に保存する。
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# このサーバーの名前（保存先のフォルダ名）。ほかのサーバーと区別するためのもの。
SERVER_NAME = "rock-on"
SERVER_TITLE = "録音まとめサーバー"


def _default_storage() -> Path | None:
    if os.name == "nt" and Path("D:/").exists():
        return Path("D:/Server") / SERVER_NAME
    return None


_env = os.getenv("STORAGE_DIR", "").strip().strip('"')
STORAGE_DIR: Path | None = Path(_env) if _env else _default_storage()

if STORAGE_DIR is not None:
    DATA_DIR = STORAGE_DIR / "data"
    MODELS_DIR: Path | None = STORAGE_DIR / "models"
else:
    DATA_DIR = ROOT / "data"
    MODELS_DIR = None  # 文字起こしモデルは標準の場所（ユーザーフォルダの .cache）

OLD_DATA_DIR = ROOT / "data"


def _write_about() -> None:
    about = STORAGE_DIR / "_このフォルダについて.txt"
    text = (
        f"このフォルダは「{SERVER_TITLE}（{SERVER_NAME}）」のデータです。\r\n"
        "\r\n"
        "  data\\    録音・文字起こし・要約（記録ごとに、日時の名前のフォルダ）\r\n"
        "  models\\  文字起こしモデル（消しても、次に使うときに自動でダウンロードされます）\r\n"
        "\r\n"
        f"プログラムの場所: {ROOT}\r\n"
        "バックアップするときは、このフォルダを丸ごとコピーしてください。\r\n"
    )
    try:
        if not about.exists() or about.read_text(encoding="utf-8-sig") != text:
            about.write_text(text, encoding="utf-8-sig")  # メモ帳で文字化けしないよう BOM 付き
    except OSError:
        pass


def _move_old_records() -> int:
    """以前の保存場所（プログラムのフォルダの data）にある記録を、新しい保存先へ移す。"""
    if DATA_DIR.resolve() == OLD_DATA_DIR.resolve() or not OLD_DATA_DIR.is_dir():
        return 0
    moved = 0
    for d in sorted(OLD_DATA_DIR.iterdir()):
        if not (d / "meta.json").exists():
            continue
        dest = DATA_DIR / d.name
        if dest.exists():
            continue
        shutil.move(str(d), str(dest))
        moved += 1
    # 空になったら古い data フォルダは片づける
    try:
        if not any(OLD_DATA_DIR.iterdir()):
            OLD_DATA_DIR.rmdir()
    except OSError:
        pass
    return moved


def prepare() -> None:
    """保存先を作り、以前の記録を移す。サーバーの起動時に 1 回呼ぶ。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if STORAGE_DIR is not None:
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        _write_about()
    moved = _move_old_records()
    print(f"[保存先] {DATA_DIR}")
    if moved:
        print(f"[保存先] 以前の場所（{OLD_DATA_DIR}）から記録を {moved} 件移しました")
