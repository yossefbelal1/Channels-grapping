@echo off
echo ===================================================
echo   Syncing Channels-grapping to GitHub (main branch)
echo ===================================================
git add .
git commit -m "Auto-sync update: %date% %time%"
git push origin main
echo ===================================================
echo   Sync Completed Successfully!
echo ===================================================
pause
