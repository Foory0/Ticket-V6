@echo off
chcp 65001
title Discord Ticket Bot

:START
cls
echo ============================================
echo             تشغيل بوت التذاكر
echo ============================================
echo.

python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo فشل في تثبيت المتطلبات
    pause
    exit
)

cls
echo ============================================
echo          جاري تشغيل البوت...
echo ============================================
echo.

python main.py
echo.
echo ============================================
echo تم إيقاف البوت. إعادة التشغيل خلال 5 ثواني...
echo ============================================
timeout /t 5 /nobreak
goto START 