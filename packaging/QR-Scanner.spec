# Project-authored MIT build recipe. No upstream PyInstaller hook was copied.
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH).parent
dx_data, dx_binaries, dx_imports = collect_all('dxcam')
replacement = os.environ.get('WQRS_BUILD_IMPORT_PATH')
probe = os.environ.get('WQRS_REBUILD_PROBE') == '1'
a = Analysis(
    [str(root / 'launcher.py')],
    pathex=([replacement] if replacement else []) + [str(root)],
    binaries=dx_binaries,
    datas=dx_data + [(str(root / 'assets/QR-Scanner.ico'), 'assets')],
    hiddenimports=['bridge.pairing_controller', 'bridge.realtime', 'pystray._win32'] + dx_imports,
    hookspath=[], hooksconfig={},
    runtime_hooks=[str(root / 'scripts/rebuild_probe.py')] if probe else [],
    excludes=[], noarchive=False, optimize=0,
)
# This app opens local camera indices with MSMF/DirectShow, not video files
# or network streams. Drop only the unused separately-loaded FFmpeg plugin.
# Keep OpenCV itself, native Windows camera backends and image codecs.
a.binaries = [entry for entry in a.binaries
              if not Path(entry[0]).name.lower().startswith('opencv_videoio_ffmpeg')]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [], name='QR-Scanner',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False,
    version=str(root / 'assets/windows-version-info.txt'),
    icon=str(root / 'assets/QR-Scanner.ico'),
)
