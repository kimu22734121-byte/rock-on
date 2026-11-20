@echo off
setlocal
cd /d "%~dp0"
title 録音まとめサーバー

rem ============================================================
rem  録音まとめサーバー 起動ファイル
rem  ダブルクリックで起動。初回は自動でセットアップします。
rem ============================================================

rem ---- Python 3.10 以上を探す ----
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if defined PY goto have_python
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=python"
if defined PY goto have_python
echo [エラー] Python 3.10 以上が見つかりません。
echo   https://www.python.org/downloads/ から Python 3.12 をインストールしてください。
echo   インストール画面で「Add python.exe to PATH」にチェックを入れてください。
pause
exit /b 1

:have_python
if exist ".venv\Scripts\python.exe" goto have_venv
echo 初回セットアップ中です。数分かかります...
%PY% -m venv .venv
if errorlevel 1 goto fail_venv

:have_venv
set "VPY=%~dp0.venv\Scripts\python.exe"

rem ---- ライブラリ: 初回と requirements.txt が更新されたときだけインストール ----
fc /b requirements.txt ".venv\installed-requirements.txt" >nul 2>&1
if not errorlevel 1 goto deps_ok
echo 必要なライブラリをインストールしています。数分かかります...
"%VPY%" -m pip install --upgrade pip >nul
"%VPY%" -m pip install -r requirements.txt
if errorlevel 1 goto fail_pip
copy /y requirements.txt ".venv\installed-requirements.txt" >nul
:deps_ok

rem ---- 設定 config.env を読み込む ----
if exist config.env for /f "usebackq eol=# tokens=1,* delims==" %%A in ("config.env") do set "%%A=%%B"
if defined ANTHROPIC_API_KEY goto have_key
if defined SKIP_API_KEY goto no_key
echo.
echo Claude API キーを入力してください。https://platform.claude.com で取得できます。
echo   キーがあると、録音後に要約まで自動で作成します。有料、1 時間で約 40 円です。
echo   キーなしで使う場合は、何も入力せずに Enter を押してください。
echo   その場合、要約は claude.ai に貼り付けて作ります。無料です。
echo 入力内容はこのフォルダの config.env に保存され、次回からは聞かれません。
set /p "ANTHROPIC_API_KEY=API キー: "
if defined ANTHROPIC_API_KEY goto save_key
>>config.env echo SKIP_API_KEY=1
echo キーなしで使います。あとから設定するときは config.env を編集してください。
goto no_key
:save_key
>>config.env echo ANTHROPIC_API_KEY=%ANTHROPIC_API_KEY%
echo 保存しました。
goto have_key
:no_key
echo [お知らせ] API キーなしで起動します。要約は claude.ai に貼り付ける方法で作成します。
:have_key
if not defined PORT set "PORT=8000"

rem ---- スマホ用アドレスの表示 ----
where tailscale >nul 2>&1
if errorlevel 1 goto show_banner
echo.
echo ---- Tailscale の公開設定 ----
tailscale serve status
echo   上に https://....ts.net が表示されていれば、末尾に /rec/ を付けてスマホで開きます。
echo   表示されない場合は、別のウィンドウで「tailscale serve --bg %PORT%」を一度実行してください。

:show_banner
echo.
echo ============================================================
echo   まとめサーバーを起動します
echo   PC からは http://localhost:%PORT% を開いてください
echo   このウィンドウを閉じるとサーバーが止まります
echo ============================================================
echo.

:loop
"%VPY%" -m uvicorn app.main:app --host 127.0.0.1 --port %PORT%
echo.
echo サーバーが停止しました。10 秒後に自動で再起動します。
echo 終了する場合は、このウィンドウを閉じてください。
timeout /t 10 /nobreak >nul
goto loop

:fail_venv
echo [エラー] Python の仮想環境を作れませんでした。
pause
exit /b 1

:fail_pip
echo [エラー] ライブラリのインストールに失敗しました。
echo   インターネット接続を確認して、もう一度 start.bat を実行してください。
echo   解決しない場合は Python 3.12 を入れ直し、このフォルダの .venv を削除してから再実行してください。
pause
exit /b 1

