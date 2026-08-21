@echo off
cd /d "%~dp0"

echo ============================================================
echo   Anta BI MCP server (external, port 8002)
echo ============================================================

if defined ANTA_MCP_API_KEY goto RUN

echo.
echo ANTA_MCP_API_KEY is not set in environment.
set /p "ANTA_MCP_API_KEY=Enter API key (leave empty for open mode / local debug only): "
echo.

:RUN
if "%ANTA_MCP_API_KEY%"=="" (
  echo [WARN] No API key -> OPEN mode. Do NOT expose to the internet this way.
) else (
  echo [OK]   Auth enabled (Authorization: Bearer ^<ANTA_MCP_API_KEY^>)
)
echo.
echo Endpoint: http://0.0.0.0:8002/mcp
echo Press Ctrl+C to stop.
echo.

".venv\Scripts\anta-mcp.exe" --host 0.0.0.0 --port 8002
