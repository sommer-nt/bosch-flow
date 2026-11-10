"""Produktbilder aus dem Gesamtkatalog (PDF) übernehmen.

    python wp_auslegung/tools/bilder_import.py  KATALOG.pdf  [HPA.pdf]

Holt die unten zugeordneten Bilder mit `pdfimages` (poppler-utils) aus dem Katalog, schneidet weiße Ränder ab,
verkleinert sie (max. 420 px) und speichert sie als JPEG in wp_auslegung/daten/bilder/. Danach
`python wp_auslegung/tools/excel_import.py --nur-einbetten`, damit index.html die Bilder enthält.
Der Katalog selbst wird nicht eingecheckt.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageChops

ZIEL = Path(__file__).resolve().parent.parent / "daten" / "bilder"

# Name: (Quelle "kat"/"hpa", Seite, Bildnummer laut `pdfimages -list`)
BILDER = {
    "CS3800_OS": ("hpa", 2, 0),        # Heat-Pump-Advisor-Ausdruck (Katalog nur als Schnittbild)
    "CS3800_OT": ("kat", 42, 5),
    "AWEi": ("kat", 43, 5),
    "AWMi": ("kat", 44, 4),
    "CS5800_ORS": ("kat", 23, 39),
    "CS5800_ORT": ("kat", 23, 40),
    "CS6800_E": ("kat", 20, 5),
    "CS5800_MB": ("kat", 22, 4),
    "CS8800": ("kat", 2, 4),
    "AWEiD": ("kat", 4, 4),
    "CS5001_22": ("kat", 176, 4),
    "CS5001_42": ("kat", 176, 6),
    "CS7000": ("kat", 86, 3),
    "CS7400": ("kat", 56, 3),
    "CS7800LW": ("kat", 208, 3),
    "SupraecoT": ("kat", 244, 3),
}


def zuschneiden(im: Image.Image) -> Image.Image:
    im = im.convert("RGB")
    rand = ImageChops.difference(im, Image.new("RGB", im.size, (255, 255, 255))).convert("L").point(lambda v: 255 if v > 12 else 0)
    box = rand.getbbox()
    return im.crop(box) if box else im


def main(katalog: Path, hpa: Path | None) -> None:
    ZIEL.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for name, (quelle, seite, nr) in BILDER.items():
            pdf = katalog if quelle == "kat" else hpa
            if pdf is None:
                print(f"{name}: übersprungen (keine HPA-Datei)")
                continue
            praefix = Path(tmp) / f"{name}"
            subprocess.run(["pdfimages", "-png", "-f", str(seite), "-l", str(seite), str(pdf), str(praefix)], check=True)
            datei = Path(f"{praefix}-{nr:03d}.png")
            im = zuschneiden(Image.open(datei))
            im.thumbnail((420, 420))
            im.save(ZIEL / f"{name}.jpg", "JPEG", quality=82, optimize=True)
            print(f"{name}: {im.size[0]}×{im.size[1]}")


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) == 3 else None)
