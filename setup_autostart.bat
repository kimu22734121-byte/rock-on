@echo off
setlocal
cd /d "%~dp0"
rem PC にサインインしたとき、まとめサーバーを最小化した状態で自動起動するように登録します。
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path ([Environment]::GetFolderPath('Startup')) 'rock-on-server.lnk')); $s.TargetPath = '%~dp0start.bat'; $s.WorkingDirectory = '%~dp0'; $s.WindowStyle = 7; $s.Save()"
if errorlevel 1 goto fail
echo.
echo 自動起動を登録しました。
echo 次回から、PC にサインインすると自動でまとめサーバーが起動します（最小化されたウィンドウ）。
echo 解除するには remove_autostart.bat を実行してください。
echo.
echo ※ 先に start.bat を一度実行して、初回セットアップと API キーの入力を済ませておいてください。
pause
exit /b 0
:fail
echo [エラー] 登録に失敗しました。
pause
exit /b 1
