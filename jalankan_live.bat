@echo off
rem Mesin live IDX: dobel-klik file ini sebelum bursa buka dan biarkan jendelanya terbuka.
rem Situs lokal: http://localhost:8765  (tambahkan --lan di bawah agar bisa dibuka dari HP di Wi-Fi yang sama)
cd /d "%~dp0"
title Mesin live IDX
python live.py %*
pause
