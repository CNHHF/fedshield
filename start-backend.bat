@echo off
chcp 65001 >nul
setlocal

echo ============================================================
echo  FedShield 隐私计算平台 - 后端启动
echo ============================================================
echo.

cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo [错误] 未检测到 python 命令，请先安装 Python 3.10+ 并加入 PATH
  pause
  exit /b 1
)

echo [1/2] 检查并安装依赖（首次运行需要联网）...
python -m pip install -r requirements.txt --quiet
if errorlevel 1 (
  echo [警告] 依赖安装失败，若已安装可忽略此提示
)

echo.
echo [2/2] 启动后端服务（Ctrl+C 停止）...
echo     健康检查: http://127.0.0.1:5000/api/health
echo     演示账号: risk.officer / FedShield@2026 / MFA 123456
echo.
python run.py

pause
