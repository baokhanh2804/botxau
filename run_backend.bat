@echo off
title BotXau Backend Server
echo [BotXau] Dang kiem tra va cai dat cac thu vien Python...
call pip install -r backend/requirements.txt
echo [BotXau] Dang khoi dong Backend FastAPI...
python -m backend.main
pause
