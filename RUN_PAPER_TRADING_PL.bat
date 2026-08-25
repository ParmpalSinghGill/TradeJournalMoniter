@echo off
cd /d "%~dp0"
echo ====================================================
echo     Paper Trading P^&L Calculator
echo ====================================================
python src\calculate_paper_trading_pl.py
echo.
echo ====================================================
echo Execution complete. Results saved in paper_trading_with_pl.csv
echo ====================================================
pause
