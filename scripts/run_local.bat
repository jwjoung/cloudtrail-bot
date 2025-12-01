@echo off
REM CloudTrail Security Bot - 로컬 실행 스크립트 (Windows)

echo 🚀 CloudTrail Security Bot 로컬 실행 시작...

REM .env 파일 로드
if exist .env (
    echo 📋 .env 파일 로드 중...
    for /f "usebackq tokens=1,2 delims==" %%a in (".env") do (
        if not "%%a"=="" if not "%%a:~0,1%"=="#" (
            set "%%a=%%b"
        )
    )
)

REM 환경 변수 확인
if "%SLACK_BOT_TOKEN%"=="" (
    echo ❌ SLACK_BOT_TOKEN 환경 변수가 설정되지 않았습니다.
    echo 💡 .env 파일을 생성하거나 환경 변수를 설정해주세요.
    exit /b 1
)

if "%SLACK_APP_TOKEN%"=="" (
    echo ❌ SLACK_APP_TOKEN 환경 변수가 설정되지 않았습니다.
    echo 💡 .env 파일을 생성하거나 환경 변수를 설정해주세요.
    exit /b 1
)

REM 기본값 설정
if "%ENV_TYPE%"=="" set ENV_TYPE=dev
if "%AWS_REGION%"=="" set AWS_REGION=ap-northeast-2
set USE_AGENTCORE=false

echo 📋 실행 설정:
echo   - 환경: %ENV_TYPE%
echo   - 리전: %AWS_REGION%
echo   - 모드: 독립 실행 (Socket Mode)

REM 가상환경 활성화 (있는 경우)
if exist .venv\Scripts\activate.bat (
    echo 📦 가상환경 활성화 중...
    call .venv\Scripts\activate.bat
) else if exist venv\Scripts\activate.bat (
    echo 📦 가상환경 활성화 중...
    call venv\Scripts\activate.bat
)

REM 실행
echo 🤖 Bot 시작 중...
python -m src.main

