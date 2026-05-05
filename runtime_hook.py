# runtime_hook.py
# Fixes file paths when running as a PyInstaller bundle
import sys
import os

if getattr(sys, 'frozen', False):
    # Running as compiled exe
    # sys._MEIPASS is the temp folder PyInstaller extracts to
    os.environ['POSTURECOACH_BASE_DIR'] = sys._MEIPASS
else:
    # Running as normal Python script
    os.environ['POSTURECOACH_BASE_DIR'] = os.path.dirname(
        os.path.abspath(__file__))