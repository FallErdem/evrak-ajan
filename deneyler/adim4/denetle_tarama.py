#!/usr/bin/env python3
"""ADIM 5b doğrulaması — taramanın gerçekten yapıldığını kanıtlar.

DÖRT KONTROL

    1. METİN KATMANI GİTMİŞ olmalı
       Taranmış bir PDF'te metin bulunmaz. Bulunuyorsa dönüşüm olmamış
       ve OCR hiç devreye girmeyecek — 50 belgelik test boşa gider.

    2. GÖRÜNTÜ VAR olmalı
       Sayfada gömülü bir görüntü olmalı ve boyutu makul olmalı.

    3. ÇÖZÜNÜRLÜK doğru olmalı
       Bozuk tarama düşük dpi, temiz tarama yüksek dpi.

    4. METİN KATMANLI 250 BELGE DOKUNULMAMIŞ olmalı
       Yanlış belgeye tarama uygulanmışsa bu kontrol yakalar.

OCR TESTİ YOK
Tesseract dil dosyaları indirilemedi (GitHub erişimi kapalı). OCR'ın
gerçekten okuyabildiği Parça 3'te Docling ile ölçülecek; Docling
RapidOCR veya EasyOCR kullanabiliyor ve onlar modeli pip ile indiriyor.

Bu betik OCR olmadan da taramanın doğru yapıldığını kanıtlıyor:
metin katmanı gitti, görüntü yerinde, çözünürlük beklenen değerde.

KULLANIM

    python denetle_tarama.py
    python denetle_tarama.py --belge 018
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:
    import fitz

BURASI = Path(__file__).resolve().parent
ETIKETLER = BURASI / "etiketler"
PDFLER = BURASI / "belgeler_pdf"

BU_KUSUR = "tarama_bozuk"

# Taranmış PDF'te bulunabilecek en fazla karakter. Sıfır beklenir ama
# bazı üreticiler boş metin nesnesi bırakabiliyor; küçük bir tolerans.
AZAMI_METIN = 20

# Beklenen çözünürlük sınırları. tara_pdf.py bozuk için 150, temiz için
# 300 dpi kullanıyor; A4 yüksekliği 842 punto = 11,69 inç.
A4_INC_YUKSEKLIK = 11.69


def sayfa_bilgisi(yol: Path) -> dict:
    belge = fitz.open(str(yol))
    sayfa = belge[0]
    metin = sayfa.get_text().strip()
    gorseller = sayfa.get_images(full=True)
    bilgi = {"metin_uzunlugu": len(metin), "gorsel_sayisi": len(gorseller),
             "sayfa_sayisi": len(belge), "yukseklik_piksel": 0}
    if gorseller:
        # En büyük görüntünün yüksekliği — dpi hesabı için
        bilgi["yukseklik_piksel"] = max(
            belge.extract_image(g[0])["height"] for g in gorseller)
    belge.close()
    return bilgi


def denetle(e: dict, bilgi: dict) -> list[str]:
    sorunlar = []
    taranmis = e.get("pdf_bicimi") == "taranmis"

    if not taranmis:
        # 4 — metin katmanlı belgeye tarama uygulanmamış olmalı
        if bilgi["metin_uzunlugu"] < 120:
            sorunlar.append("metin katmanlı olmalıydı ama metin yok — "
                            "yanlış belgeye tarama uygulanmış")
        return sorunlar

    # 1 — metin katmanı gitmiş olmalı
    if bilgi["metin_uzunlugu"] > AZAMI_METIN:
        sorunlar.append(f"metin katmanı HÂLÂ var ({bilgi['metin_uzunlugu']} "
                        f"karakter) — tarama uygulanmamış")

    # 2 — görüntü var olmalı
    if bilgi["gorsel_sayisi"] < 1:
        sorunlar.append("sayfada gömülü görüntü yok")
        return sorunlar

    # 3 — çözünürlük beklenen bantta olmalı
    dpi = bilgi["yukseklik_piksel"] / A4_INC_YUKSEKLIK
    bozuk = e.get("kusur") == BU_KUSUR
    if bozuk and not (120 <= dpi <= 190):
        sorunlar.append(f"bozuk tarama ama çözünürlük {dpi:.0f} dpi "
                        f"(beklenen 120-190)")
    if not bozuk and not (260 <= dpi <= 340):
        sorunlar.append(f"temiz tarama ama çözünürlük {dpi:.0f} dpi "
                        f"(beklenen 260-340)")
    return sorunlar


def main() -> int:
    a = argparse.ArgumentParser(description="ADIM 5b tarama dogrulamasi")
    a.add_argument("--belge", nargs="+", metavar="NO")
    ns = a.parse_args()

    yollar = sorted(ETIKETLER.glob("etiket_*.json"))
    if ns.belge:
        istenen = {n.zfill(3) for n in ns.belge}
        yollar = [y for y in yollar if y.stem.split("_")[-1] in istenen]

    gecerli, sorunlu = 0, []
    sayac = {"taranmis_bozuk": 0, "taranmis_temiz": 0, "metin_katmanli": 0}

    for y in yollar:
        no = y.stem.split("_")[-1]
        e = json.loads(y.read_text(encoding="utf-8"))
        pdf = PDFLER / f"belge_{no}.pdf"
        if not pdf.exists():
            sorunlu.append((no, ["PDF bulunamadi"]))
            continue
        try:
            bilgi = sayfa_bilgisi(pdf)
        except Exception as hata:
            sorunlu.append((no, [f"PDF okunamadi: {hata}"]))
            continue

        sorun = denetle(e, bilgi)
        if sorun:
            sorunlu.append((no, sorun))
            print(f"\nbelge_{no}  [{e.get('pdf_bicimi')}"
                  f"{' / ' + e['kusur'] if e.get('kusur') else ''}]")
            for s in sorun:
                print(f"   x {s}")
        else:
            gecerli += 1
            if e.get("pdf_bicimi") != "taranmis":
                sayac["metin_katmanli"] += 1
            elif e.get("kusur") == BU_KUSUR:
                sayac["taranmis_bozuk"] += 1
            else:
                sayac["taranmis_temiz"] += 1

    print("\n" + "=" * 66)
    print(f"SONUÇ: geçerli {gecerli} | sorunlu {len(sorunlu)}   "
          f"(toplam {gecerli + len(sorunlu)})")
    print("=" * 66)
    for k, n in sayac.items():
        print(f"  {k:<20} {n}")
    if sorunlu:
        print(f"\n  Sorunlu: {', '.join(no for no, _ in sorunlu)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
