"""Depodaki dosyalarin guncel olup olmadigini soyler. Hicbir sey degistirmez."""
import sys
from pathlib import Path
KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK / "src"))

print("DOSYA DURUMU")
print("=" * 52)
for yol, imza, ad in (
    ("src/ayristirici.py",   "def govde_kur(",        "govde_kur tasindi mi"),
    ("src/yazar.py",         "CAKISAN_KURALLAR",      "kural cakismasi"),
    ("src/yonlendirici.py",  "Y-E konudan SDP",       "Y-E hatti"),
    ("src/guven_kapisi.py",  "def degerlendir(",      "guven kapisi"),
    ("src/defter.py",        "def giden_sayi_kur(",   "defter"),
    ("src/boru_hatti.py",    "def isle(",             "boru hatti"),
    ("src/veri_yapisi.py",   'MUHATAP = "muhatap"',   "YonlendirmeKaynagi.MUHATAP"),
    ("veri/taksonomi/sdp_kodlari.csv", "",            "sdp katalogu"),
):
    p = KOK / yol
    if not p.exists():
        print(f"  EKSIK   {ad:28s} {yol}")
        continue
    if imza and imza not in p.read_text(encoding="utf-8", errors="ignore"):
        print(f"  ESKI    {ad:28s} {yol}")
    else:
        print(f"  guncel  {ad:28s} {yol}")

print()
print("ICE AKTARMA")
print("=" * 52)
for m in ("ayristirici", "yazar", "yonlendirici", "guven_kapisi",
          "defter", "boru_hatti", "denetci"):
    try:
        __import__(m)
        print(f"  ok      {m}")
    except Exception as e:
        print(f"  HATA    {m}: {type(e).__name__}: {e}")

try:
    from sdp_katalog import katalog
    print(f"\n  sdp katalogu: {len(katalog())} kod  (115 olmali)")
except Exception as e:
    print(f"\n  sdp katalogu okunamadi: {e}")
