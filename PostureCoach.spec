# PostureCoach.spec
import os
from PyInstaller.building.build_main import Analysis, PYZ, EXE

block_cipher = None

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Bundle the MediaPipe model file
        ('pose_landmarker_full.task', '.'),
        # Bundle MediaPipe's internal data files
    ],
    hiddenimports=[
        'mediapipe',
        'mediapipe.tasks',
        'mediapipe.tasks.python',
        'mediapipe.tasks.python.vision',
        'mediapipe.tasks.python.core',
        'customtkinter',
        'pyttsx3',
        'pyttsx3.drivers',
        'pyttsx3.drivers.sapi5',    # Windows TTS driver
        'pyttsx3.drivers.nsss',     # macOS TTS driver
        'pyttsx3.drivers.espeak',   # Linux TTS driver
        'win11toast',
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'cv2',
        'numpy',
        'plyer',
        'plyer.platforms.win.notification',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'scipy',
        'pandas',
        'jupyter',
        'IPython',
        'tkinter.test',
        'unittest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='PostureCoach',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,        # no terminal window — GUI only
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',      # app icon
    onefile=True,         # single .exe file
)