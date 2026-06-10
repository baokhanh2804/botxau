@echo off
title BotXau Frontend Dashboard
echo [BotXau] Kiem tra va khoi dong Frontend React...

cd frontend

:: Neu chua co node_modules, tu dong chay npm install
if not exist node_modules (
    echo [BotXau] Phat hien node_modules chua duoc cai dat. Dang tu dong chay npm install...
    call npm install
)

echo [BotXau] Dang khoi dong Frontend React...
call npm run dev
pause
