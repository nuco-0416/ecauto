@echo off
cd /d C:\Users\hiroo\Documents\GitHub\ecauto
venv\Scripts\python.exe platforms\base\scripts\sync_prices.py >> logs\sync_prices.log 2>&1
