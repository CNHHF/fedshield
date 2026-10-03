@echo off
chcp 65001 >nul
setlocal

echo ============================================================
echo  FedShield 隐私计算平台 - 前端启动
echo ============================================================
echo.

cd /d "%~dp0frontend"

where node >nul 2>nul
if errorlevel 1 (
  echo [错误] 未检测到 node 命令，请先安装 Node.js 18+ 并加入 PATH
  pause
  exit /b 1
)

if not exist node_modules (
  echo [1/2] 首次运行，安装前端依赖（需要联网）...
  call npm install
  if errorlevel 1 (
    echo [错误] npm install 失败，请检查网络或使用国内镜像：npm config set registry https://registry.npmmirror.com
    pause
    exit /b 1
  )
) else (
  echo [1/2] 依赖已存在，跳过安装
)

echo.
echo [2/2] 启动前端开发服务器...
echo     访问地址: http://127.0.0.1:5173
echo     请确保后端已在 http://127.0.0.1:5000 运行
echo.
call npm run dev

pause
