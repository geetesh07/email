@echo off
title Engineering Email Intelligence
echo ==========================================
echo Engineering Email Intelligence Tool
echo ==========================================
echo.
echo Installing dependencies...
python -m pip install -r requirements.txt
echo.
echo Starting Streamlit App (Frontend/Backend)...
python -m streamlit run app.py
pause
