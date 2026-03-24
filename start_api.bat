@echo off
echo Starting Engineering Email Intelligence API Server...
echo The API will be available at http://localhost:8000
python -m uvicorn api:app --host 0.0.0.0 --port 8000 --reload
pause
