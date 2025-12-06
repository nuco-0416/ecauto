@echo off
cd /d C:\Users\hiroo\Documents\GitHub\ecauto
venv\Scripts\python.exe inventory\scripts\sync_stock_visibility.py >> logs\sync_stock_visibility.log 2>&1
