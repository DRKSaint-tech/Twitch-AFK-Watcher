@echo off
REM Change to the directory where your Python script is located
cd /d "%~dp0"

REM Set the path to your Python executable if it's not in your system's PATH
REM For example, if Python is installed at C:\Python39\python.exe
REM SET PYTHON_EXECUTABLE="C:\Python39\python.exe"
REM If Python is in your PATH, you can just use "python" or "py"
SET PYTHON_EXECUTABLE="python"

REM Run your Python script
%PYTHON_EXECUTABLE% twitch_afk.py

REM Optional: Pause at the end if you want to see any console output before the window closes
REM pause