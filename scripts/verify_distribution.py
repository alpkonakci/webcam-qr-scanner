"""Check frozen artifacts and source correspondence (not a legal certification)."""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import tarfile
from PyInstaller.archive.readers import CArchiveReader


def verify_exe(path: Path, modified: bool = False):
    archive = CArchiveReader(str(path))
    forbidden = [name for name in archive.toc if "opencv_videoio_ffmpeg" in name.lower()]
    if forbidden:
        raise ValueError(f"Unused FFmpeg plugin remains in EXE: {forbidden}")
    pyz = archive.open_embedded_archive("PYZ.pyz")
    code = pyz.extract("pystray._info")
    marker = "modified-library-20261011"
    if (marker in code.co_consts) != modified:
        raise ValueError("Wrong modified-library build contents")
    for module in ("pystray._win32", "camera", "qr_reader"):
        if module not in pyz.toc:
            raise ValueError(f"Required module missing: {module}")
    if not any(name.endswith("cv2.pyd") for name in archive.toc):
        raise ValueError("OpenCV native module missing")
    return len(archive.toc)


def verify_upstream_sources(source_dir: Path, site_packages: Path):
    checked = {}
    for package, archive_name, prefix in (
        ("pystray", "pystray-0.19.5.tar.gz", "/lib/pystray/"),
        ("certifi", "certifi-2026.7.22.tar.gz", "/certifi/"),
    ):
        count = 0
        with tarfile.open(source_dir / archive_name) as archive:
            for member in archive.getmembers():
                if not member.isfile() or prefix not in member.name:
                    continue
                relative = member.name.split(prefix, 1)[1]
                if not relative.endswith((".py", ".pem")):
                    continue
                installed = site_packages / package / relative
                if not installed.is_file():
                    raise ValueError(f"Upstream source absent from installation: {relative}")
                source = archive.extractfile(member).read()
                # Wheel builds can normalize Python line endings.
                if relative.endswith(".py"):
                    source = source.replace(b"\r\n", b"\n")
                    actual = installed.read_bytes().replace(b"\r\n", b"\n")
                else:
                    actual = installed.read_bytes()
                if hashlib.sha256(source).digest() != hashlib.sha256(actual).digest():
                    raise ValueError(f"Source differs from bundled installation: {package}/{relative}")
                count += 1
        if count < 3:
            raise ValueError(f"Incomplete source archive for {package}")
        checked[package] = count
    return checked


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path)
    parser.add_argument("--modified", action="store_true")
    parser.add_argument("--sources", type=Path)
    parser.add_argument("--site-packages", type=Path)
    args = parser.parse_args()
    if args.exe:
        print("Verified frozen archive entries:", verify_exe(args.exe, args.modified))
    if args.sources:
        print("Verified matching upstream files:", verify_upstream_sources(args.sources, args.site_packages))
