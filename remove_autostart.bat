@echo off
set "LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\rock-on-server.lnk"
if exist "%LNK%" (
  del "%LNK%"
  echo 自動起動を解除しました。
) else (
  echo 自動起動は登録されていません。
)
pause
