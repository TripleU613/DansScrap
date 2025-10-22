@echo off
setlocal enabledelayedexpansion

REM ------------------------------------------------------------
REM  DansDeals Tech Talk Scraper launcher
REM ------------------------------------------------------------

set "PYTHON_EXE=C:\Users\usher\AppData\Local\Programs\Python\Python313\python.exe"
set "PROJECT_DIR=%~dp0dansdeals_play"
set "SPIDER=tech_talk"

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Expected Python executable not found at %PYTHON_EXE%
    echo         Update PYTHON_EXE inside run_tech_talk.bat if Python lives elsewhere.
    goto :eof
)

if not exist "%PROJECT_DIR%\scrapy.cfg" (
    echo [ERROR] Could not find scrapy project at %PROJECT_DIR%
    goto :eof
)

pushd "%PROJECT_DIR%" >nul

:menu
echo;
echo ===============================================
echo  DansDeals Tech Talk Scraper
echo ===============================================
echo   1 ^) Quick smoke test  (1 board page, 1 topic, 1 topic page)
echo   2 ^) Full Tech Talk crawl (board 8, posts enabled)
echo   3 ^) Custom run (choose options)
echo   Q ^) Quit
echo ===============================================
set /p "CHOICE=Select an option: "
echo;

if "%CHOICE%"=="" goto :menu
if /I "%CHOICE%"=="Q" goto :cleanup
if "%CHOICE%"=="1" goto :quick
if "%CHOICE%"=="2" goto :full
if "%CHOICE%"=="3" goto :custom

echo [WARN] Unrecognized choice "%CHOICE%". Exiting.
goto :cleanup

:quick
set "ARGS=-a max_board_pages=1 -a max_topics=1 -a topic_max_pages=1 -a bootstrap=auto --set PLAYWRIGHT_STATE_TTL=43200"
set "DESC=Quick smoke test"
goto :prompt_cf_mode

:full
set "ARGS=-a board=8 -a fetch_posts=true -a bootstrap=auto --set PLAYWRIGHT_STATE_TTL=43200"
set "DESC=Full Tech Talk board crawl"
goto :prompt_cf_mode

:custom
set "ARGS="
set "DESC=Custom run"

set "DEFAULT_BOARD=8"
set /p "BOARD_ID=Board ID [8]: "
if "%BOARD_ID%"=="" set "BOARD_ID=%DEFAULT_BOARD%"

set "DEFAULT_FETCH=true"
set /p "FETCH_POSTS=Fetch posts? (true/false) [true]: "
if "%FETCH_POSTS%"=="" set "FETCH_POSTS=%DEFAULT_FETCH%"

set /p "MAX_BOARD=Max board pages (blank=all): "
set /p "MAX_TOPICS=Max topics (blank=all): "
set /p "MAX_TOPIC_PAGES=Max topic pages (blank=all): "

set /p "BOOTSTRAP=Bootstrap CF session? (auto/skip) [auto]: "
if "%BOOTSTRAP%"=="" set "BOOTSTRAP=auto"

set /p "STATE_TTL=Storage state TTL in seconds [43200]: "
if "%STATE_TTL%"=="" set "STATE_TTL=43200"

set "ARGS=-a board=%BOARD_ID% -a fetch_posts=%FETCH_POSTS% --set PLAYWRIGHT_STATE_TTL=%STATE_TTL%"
if not "%MAX_BOARD%"=="" set "ARGS=%ARGS% -a max_board_pages=%MAX_BOARD%"
if not "%MAX_TOPICS%"=="" set "ARGS=%ARGS% -a max_topics=%MAX_TOPICS%"
if not "%MAX_TOPIC_PAGES%"=="" set "ARGS=%ARGS% -a topic_max_pages=%MAX_TOPIC_PAGES%"
if /I "%BOOTSTRAP%"=="skip" (
    set "ARGS=%ARGS% -a bootstrap=skip"
) else (
    set "ARGS=%ARGS% -a bootstrap=auto"
)
goto :prompt_cf_mode

:prompt_cf_mode
set "CF_MODE=auto"
echo Cloudflare handling mode:
echo   1 ^) Auto (tries to solve automatically)
echo   2 ^) Manual (you solve in your own browser; no auto refresh)
set /p "CF_CHOICE=Select mode [1]: "
if "%CF_CHOICE%"=="2" set "CF_MODE=manual"
set "ARGS=%ARGS% -a cf_mode=%CF_MODE%"
echo;
goto :run

:run
echo [INFO] %DESC%
echo [INFO] Working directory: %PROJECT_DIR%
echo [INFO] Command: scrapy crawl %SPIDER% %ARGS%
echo [NOTE] Keep the Chromium window visible. If a Cloudflare checkbox appears, the bot will try to solve it,
echo        but you may need to click it manually when prompted. A second Chrome window may open first to
echo        capture cookies; complete the check there and, when the console says so, type DONE (or SKIP) and/or
echo        press Enter. The helper window now stays open until you decide to close it. If Cloudflare still
echo        loops, choose manual mode and solve the challenge directly in the Playwright window before pressing Enter.
echo;

"%PYTHON_EXE%" -m scrapy crawl %SPIDER% %ARGS%
set "EXITCODE=%ERRORLEVEL%"
echo;
if "%EXITCODE%"=="0" (
    echo [INFO] Scrapy finished successfully.
) else (
    echo [ERROR] Scrapy exited with code %EXITCODE%.
)
echo;
pause

:cleanup
popd >nul
endlocal
