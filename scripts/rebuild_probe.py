"""Runtime hook for the modified-library validation build, NEVER normal builds."""
import sys
from pathlib import Path
import pystray._info

assert pystray._info.WQRS_REBUILD_TEST == 'modified-library-20261011'
assert not list(Path(sys._MEIPASS).rglob('opencv_videoio_ffmpeg*.dll'))
