#!/usr/bin/env python3
"""ADIM 5b — basılan PDF'lerde kusurun GERÇEKTEN olduğunu kanıtlar.

Enjeksiyon iki yönde sınanır:

    1. Kusurlu belgede DOĞRU DEĞER metinde OLMAMALI
       Varsa kusur uygulanmamış demektir.

    2. Kusursuz belgede bütün alanlar YERİNDE OLMALI
       Eksikse enjeksiyon yanlış belgeye uygulanmış.

İkisi birden tutmazsa o belge değerlendirmede kullanılamaz: sistem
kusuru bulamadığında sebebin sistem mi veri mi olduğunu ayıramayız.

AYRICA metin katmanı kontrol edilir. Belgeler Docling ile okunacak;
metin çıkarılamıyorsa PDF geçersizdir.

KULLANIM

    python denetle_pdf.py
    python denetle_pdf.py --belge 001 018
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from pypdf import PdfReader

BURASI = Path(__file__).resolve().parent
ETIKETLER = BURASI / "etiketler"
PDFLER = BURASI / "belgeler_pdf"

# Kusur türü -> PDF metninde ne olmalı / olmamalı
# DEĞER metinde görünmemeli.
#
# konu_eksik BURADA DEĞİL: konu DEĞERİ gövde metninde zaten geçer
# ("İmar Durum Belgesi Talebi konusunda..."). Silinen şey KONU SATIRIDIR,
# konunun kendisi değil. Bu ayrım gözden kaçmıştı ve doğrulayıcı yanlış
# alarm veriyordu.
GORUNMEMELI = {
    "sayi_eksik": "dogru_deger",
    "tarih_eksik": "dogru_deger",
    "muhatap_belirsiz": "dogru_deger",
    "sdp_uyumsuz": "dogru_deger",
}

# Alan ETİKETİ metinde görünmemeli. Etiketler çıkarımda kendi satırında
# durur: "Sayı\n:\nE-...\nKonu\n:\n..."
ETIKET_GORUNMEMELI = {
    "konu_eksik": "Konu",
}
GORUNMELI = {
    "muhatap_belirsiz": "enjekte_edilen",
    "sdp_uyumsuz": "enjekte_edilen",
    "tarih_tutarsiz": "enjekte_edilen",
}


def metin_al(yol: Path) -> str:
    """PDF'in metin katmanını okur — Docling'in göreceği katman."""
    return PdfReader(str(yol)).pages[0].extract_text()


def denetle(e: dict, metin: str) -> list[str]:
    """Bir belgenin kusur durumunu sınar, sorun listesi döndürür."""
    sorunlar = []
    tur = e.get("kusur")
    ay = e.get("kusur_ayrinti") or {}
    n = re.sub(r"\s+", " ", metin)

    # --- metin katmanı ------------------------------------------------------
    if len(n.strip()) < 120:
        sorunlar.append("metin katmanı boş veya çok kısa — PDF okunamıyor")
        return sorunlar
    if not any(h in n for h in "ğüşıöçİ"):
        sorunlar.append("Türkçe karakter yok — font sorunu")

    # --- kusur enjeksiyonu --------------------------------------------------
    if tur in GORUNMEMELI and ay:
        deger = str(ay.get(GORUNMEMELI[tur]) or "")
        if deger and deger in n:
            sorunlar.append(f"{tur}: doğru değer HÂLÂ görünüyor "
                            f"({deger[:44]}) — kusur uygulanmamış")

    if tur in GORUNMELI and ay:
        deger = str(ay.get(GORUNMELI[tur]) or "")
        if deger and deger not in n:
            sorunlar.append(f"{tur}: enjekte edilen değer görünmüyor "
                            f"({deger[:44]})")

    if tur in ETIKET_GORUNMEMELI:
        etiket = ETIKET_GORUNMEMELI[tur]
        # Kendi satırında duran alan etiketi aranır; gövdedeki
        # "söz konusu" gibi kelimeler eşleşmez.
        satirlar = [x.strip() for x in metin.split("\n")]
        if etiket in satirlar:
            sorunlar.append(f"{tur}: '{etiket}' satırı HÂLÂ duruyor")

    if tur == "imza_eksik":
        # İmzalayan ad basılmamalı. Ad etikette yok (üretimde hesaplanıyor)
        # ama unvan kalıpları aranabilir.
        if re.search(r"\b(Müdür|Bakan a\.|Vali a\.|Rektör a\.|Dekan)\b", n):
            sorunlar.append("imza_eksik: imza bloğu hâlâ görünüyor")

    if tur == "ek_beyani_yanlis" and ay:
        yanlis = str(ay.get("enjekte_edilen"))
        if yanlis and f"({yanlis} sayfa)" not in n and \
                f"{yanlis} Adet" not in n:
            sorunlar.append(f"ek_beyani_yanlis: yanlış beyan görünmüyor "
                            f"({yanlis})")

    # --- kusursuz belgede alanlar yerinde mi -------------------------------
    if not tur:
        if e.get("sayi") and e["sayi"] not in n:
            sorunlar.append("kusursuz ama SAYI görünmüyor")
        if e.get("tarih") and e["tarih"] not in n:
            sorunlar.append("kusursuz ama TARİH görünmüyor")
        if e.get("konu") and e["konu"][:24] not in n:
            sorunlar.append("kusursuz ama KONU görünmüyor")

    return sorunlar


def main() -> int:
    a = argparse.ArgumentParser(description="ADIM 5a kusur dogrulamasi")
    a.add_argument("--belge", nargs="+", metavar="NO")
    ns = a.parse_args()

    if not PDFLER.exists():
        raise SystemExit(f"HATA: {PDFLER} yok. Once bas_pdf.py calistirin.")

    yollar = sorted(PDFLER.glob("belge_*.pdf"))
    if ns.belge:
        istenen = {n.zfill(3) for n in ns.belge}
        yollar = [y for y in yollar if y.stem.split("_")[-1] in istenen]
    if not yollar:
        raise SystemExit("HATA: PDF bulunamadi.")

    gecerli, sorunlu = 0, []
    kusur_sayaci: Counter = Counter()

    for y in yollar:
        no = y.stem.split("_")[-1]
        ey = ETIKETLER / f"etiket_{no}.json"
        if not ey.exists():
            sorunlu.append((no, ["etiket bulunamadi"]))
            continue
        e = json.loads(ey.read_text(encoding="utf-8"))
        try:
            metin = metin_al(y)
        except Exception as hata:
            sorunlu.append((no, [f"PDF okunamadi: {hata}"]))
            continue

        sorun = denetle(e, metin)
        if sorun:
            sorunlu.append((no, sorun))
            print(f"\nbelge_{no}  [{e.get('kusur') or 'kusursuz'}]")
            for s in sorun:
                print(f"   x {s}")
        else:
            gecerli += 1
            kusur_sayaci[e.get("kusur") or "kusursuz"] += 1

    print("\n" + "=" * 66)
    print(f"SONUÇ: geçerli {gecerli} | sorunlu {len(sorunlu)}   "
          f"(toplam {gecerli + len(sorunlu)})")
    print("=" * 66)
    for k, n in sorted(kusur_sayaci.items(), key=lambda x: -x[1]):
        print(f"  {k:<22} {n}")
    if sorunlu:
        print(f"\n  Sorunlu: {', '.join(no for no, _ in sorunlu)}")
        print("\n  Bu belgeler değerlendirmede kullanılamaz: sistem kusuru")
        print("  bulamadığında sebebin sistem mi veri mi olduğu ayrılamaz.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
