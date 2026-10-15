"""Synthetic QR fixtures for the local browser smoke test; no user photos."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from PIL import Image, ImageOps
from qr_creator import create_qr

out = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "dist" / "mobile-image-qa-20261010"
out.mkdir(parents=True, exist_ok=True)
first = create_qr("https://example.com/image-test", "link").image
second = create_qr("https://example.org/second", "link").image
first.save(out / "link.png")
first.save(out / "link.jpg", quality=95)
first.save(out / "link.webp", lossless=True)
create_qr("Merhaba dünya! Çığ 😀\nİkinci satır.", "text").image.save(out / "text.png")
Image.new("RGB", (400, 400), "white").save(out / "blank.png")
combined = Image.new("RGB", (first.width + second.width + 60, max(first.height, second.height)), "white")
combined.paste(first, (0, 0))
combined.paste(second, (first.width + 60, 0))
combined.save(out / "multiple.png")
ImageOps.invert(first.convert("RGB")).save(out / "inverted.png")
mixed = combined.copy()
mixed.paste(ImageOps.invert(second.convert("RGB")), (first.width + 60, 0))
mixed.save(out / "mixed-polarity.png")
ImageOps.invert(combined.convert("RGB")).save(out / "multiple-inverted.png")
print(out)
