@echo off
echo ============================================
echo   Electoral Roll OCR - Setup (v1.1)
echo ============================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.10+ from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    exit /b 1
)
echo [OK] Python found
python --version

REM Check/Install Tesseract
where tesseract >nul 2>&1
if errorlevel 1 (
    if exist "C:\Program Files\Tesseract-OCR\tesseract.exe" (
        echo [OK] Tesseract found at C:\Program Files\Tesseract-OCR\
    ) else (
        echo.
        echo Tesseract OCR not found. Attempting install via winget...
        echo (If winget is not available on your system, this step will fail - that's OK^)
        echo.
        winget install UB-Mannheim.TesseractOCR
        if errorlevel 1 (
            echo.
            echo NOTE: Automatic install failed (winget may not be available on your system^).
            echo Please install Tesseract manually:
            echo   1. Download from: https://github.com/UB-Mannheim/tesseract/wiki
            echo   2. Run the installer (install to: C:\Program Files\Tesseract-OCR\^)
            echo   3. During installation, check "Additional language data" for Tamil support
            echo   4. Re-run this setup.bat after installing Tesseract
        )
    )
) else (
    echo [OK] Tesseract found
)
echo.

REM Check Tamil language data
set TESSDATA=C:\Program Files\Tesseract-OCR\tessdata
if exist "%TESSDATA%\tam.traineddata" (
    echo [OK] Tamil language data found
) else (
    echo.
    echo WARNING: Tamil language data (tam.traineddata) not found.
    echo.
    echo To install Tamil OCR support:
    echo   1. Download tam.traineddata from:
    echo      https://github.com/tesseract-ocr/tessdata_best/raw/main/tam.traineddata
    echo   2. Open Command Prompt as Administrator
    echo   3. Run: copy Downloads\tam.traineddata "%TESSDATA%\tam.traineddata"
    echo.
    echo NOTE: During Tesseract installation, you can also check
    echo       "Additional language data" and "Additional script data"
    echo       to install Tamil support automatically.
)
echo.

REM Install Python dependencies
echo Installing Python dependencies...
pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo ERROR: Failed to install Python dependencies
    exit /b 1
)
echo.
echo [OK] Python dependencies installed

REM Verify installation
echo.
echo Verifying installation...
python -c "import fitz, cv2, pytesseract, numpy, PIL; print('[OK] All Python packages verified')"
if errorlevel 1 (
    echo WARNING: Some Python packages may not be installed correctly
)

echo.
echo ============================================
echo   Setup complete!
echo ============================================
echo.
echo Next steps:
echo   1. Place your electoral roll PDFs in:
echo      Input\ER_Downloads\AC-xxx\english\
echo      Input\ER_Downloads\AC-xxx\tamil\
echo.
echo   2. Split the PDFs:
echo      python split_pdfs.py --ac AC-xxx
echo.
echo   3. Run the extraction:
echo      python extract_ocr.py AC-xxx --workers 4
echo.
echo   4. Merge the outputs:
echo      python merge_outputs.py --ac AC-xxx
echo.
pause
