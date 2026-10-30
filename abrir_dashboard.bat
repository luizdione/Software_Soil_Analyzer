@echo off
rem Soil Analyzer rodando do codigo-fonte (o programa instalado nao precisa disto).
rem Python: variavel SOIL_ANALYZER_PYTHON, ou o "python" do PATH.
rem Dados: variavel ANALISE_SOLO_DADOS, ou Documentos\Soil Analyzer.
cd /d "%~dp0"
if "%SOIL_ANALYZER_PYTHON%"=="" set "SOIL_ANALYZER_PYTHON=python"
"%SOIL_ANALYZER_PYTHON%" desktop\soil_analyzer.py
pause
