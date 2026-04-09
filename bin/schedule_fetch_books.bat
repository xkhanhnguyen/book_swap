@echo off
REM ============================================================
REM  Runs fetch_books Django management command.
REM  Called by Windows Task Scheduler automatically.
REM ============================================================

cd /d C:\Users\KhanhNguyen\projects\book_swap
python manage.py fetch_books --limit 50 >> logs\fetch_books.log 2>&1
