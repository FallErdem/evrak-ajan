"""Muhatap satırı neden bulunamıyor — tanı betiği.

NEREYE:  depo kökü
NASIL:   python tani.py                 -> varsayılan 7 belge
         python tani.py 001 020 032     -> belirli belgeler
ÇIKTI:   ekrana + tani_sonuc.txt

NE YAPAR
--------
Okuyucu çıktısının ilk 14 satırını, y konumuyla birlikte, olduğu gibi basar.
Her satırın yanına ayrıştırıcının üç kalıbının tutup tutmadığını yazar.

Hiçbir şeyi düzeltmez, ölçmez, yorumlamaz. Sadece GÖSTERİR — çünkü şu an
elimizde 6 belgede muhatap satırının OCR'dan nasıl çıktığına dair veri yok
ve veri olmadan kalıp değiştirmek tahmin olur.

BAKILACAK ŞEY
-------------
Muhatap satırı (ör. "YENİMAHALLE BELEDİYE BAŞKANLIĞINA") listede GÖRÜNÜYOR
ama yanında [muhatap] yazmıyorsa, sorun kalıptadır. Üç olası sebep var ve
çıktı hangisi olduğunu söyler:

  1. Satırda küçük Latin harfi var    -> OCR 'ı' harfini 'l' veya 'i' okumuş
  2. Satır "NE"/"NA" ile bitmiyor      -> OCR son harfleri yutmuş
  3. Satır bir alttaki parantezle birleşmiş -> satır gruplama toleransı

Satır listede HİÇ görünmüyorsa sorun kalıpta değil, okuyucudadır.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK / "src"))

VARSAYILAN = ("001", "007", "017", "020", "032", "035", "009")

ARAMA_YERLERI = (
    ("deneyler", "adim4", "belgeler_pdf"),
    ("veri", "belgeler"),
    ("ornek", "okuma_ornegi"),
)

GOSTERILECEK_SATIR = 14

# Ayrıştırıcıdaki kalıpların BİREBİR kopyası. Bilerek kopyalandı:
# tanı betiği ayrıştırıcı değişse de eski davranışı gösterebilmeli.
_MUHATAP = re.compile(r"^[^a-zçğıöşü]{8,}(NE|NA|ne|na)\s*$")
_TC_BASLIK = re.compile(r"^\s*T\.?\s*C\.?\s*$", re.IGNORECASE)
_PARANTEZ = re.compile(r"^\s*\((.+)\)\s*$")

_KUCUK_LATIN = re.compile(r"[a-zçğıöşü]")


def klasor_bul() -> Path:
    for p in ARAMA_YERLERI:
        y = KOK.joinpath(*p)
        if y.exists() and any(y.glob("belge_*.pdf")):
            return y
    for b in KOK.rglob("belge_*.pdf"):
        return b.parent
    sys.exit("belge_*.pdf bulunamadi.")


def neden_tutmadi(metin: str) -> str:
    """Kalıp neden eşleşmedi — üç adayı sırayla eler."""
    s = metin.strip()
    if _MUHATAP.match(s):
        return ""
    sebepler = []
    kucukler = sorted(set(_KUCUK_LATIN.findall(s)))
    if kucukler:
        sebepler.append(f"küçük harf var: {' '.join(kucukler)}")
    if not s.endswith(("NE", "NA", "ne", "na")):
        sebepler.append(f"sonu 'NE/NA' değil: ...{s[-6:]!r}")
    if len(s) < 10:
        sebepler.append("satır çok kısa")
    return " | ".join(sebepler) or "sebep bulunamadı"


def main(argv: list[str]) -> int:
    from okuyucu import oku

    numaralar = [a for a in argv if a.isdigit()] or list(VARSAYILAN)
    numaralar = [n.zfill(3) for n in numaralar]
    klasor = klasor_bul()

    cikti = KOK / "tani_sonuc.txt"
    with cikti.open("w", encoding="utf-8") as f:
        def yaz(s: str = "") -> None:
            print(s)
            f.write(s + "\n")

        yaz(f"klasor: {klasor}\n")

        for no in numaralar:
            pdf = klasor / f"belge_{no}.pdf"
            if not pdf.exists():
                yaz(f"### belge_{no}  —  DOSYA YOK\n")
                continue

            r = oku(str(pdf))
            if r.hata:
                yaz(f"### belge_{no}  —  OKUMA HATASI: {r.hata}\n")
                continue

            yaz("=" * 78)
            yaz(f"### belge_{no}   {r.girdi_tipi} / {r.motor}   "
                f"{len(r.satirlar)} satır   dipnot_bulundu={r.ayrilmis.dipnot_bulundu if r.ayrilmis else '?'}")
            yaz("=" * 78)

            satirlar = r.ayrilmis.govde_satirlari if r.ayrilmis else r.satirlar
            muhatap_bulundu = False

            for i, s in enumerate(satirlar[:GOSTERILECEK_SATIR]):
                etiketler = []
                if _MUHATAP.match(s.metin.strip()):
                    etiketler.append("MUHATAP")
                    muhatap_bulundu = True
                if _TC_BASLIK.match(s.metin.strip()):
                    etiketler.append("T.C.")
                if _PARANTEZ.match(s.metin.strip()):
                    etiketler.append("parantez")
                im = f"  <- {' '.join(etiketler)}" if etiketler else ""
                yaz(f"  {i:2d} y={s.y:7.1f}  {s.metin!r}{im}")

            if len(satirlar) > GOSTERILECEK_SATIR:
                yaz(f"  ... {len(satirlar) - GOSTERILECEK_SATIR} satır daha")

            if not muhatap_bulundu:
                yaz("\n  MUHATAP BULUNAMADI. Aday satırların elenme sebebi:")
                for i, s in enumerate(satirlar[:GOSTERILECEK_SATIR]):
                    t = s.metin.strip()
                    # Muhatap adayı: uzun, çoğunluğu büyük harf
                    buyuk = sum(1 for k in t if k.isupper())
                    if len(t) >= 10 and buyuk >= len(t) * 0.5:
                        yaz(f"    satır {i}: {neden_tutmadi(t)}")
            yaz()

        yaz(f"Tam cikti: {cikti}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
