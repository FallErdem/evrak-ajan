#!/usr/bin/env python3
"""ADIM 4.4e — dilekçe parti cevabını ayrıştırır ve gövdelerin üzerine yazar.

    cevaplar/dilekce_cevap_NN.txt  ->  govdeler/govde_NNN.txt

DİKKAT: MEVCUT GÖVDELERİN ÜZERİNE YAZAR.
Yalnızca `belge_talebi` ailesindeki 66 dilekçe etkilenir; diğer 234
belge dokunulmaz. Yine de ilk çalıştırmadan önce yedek alınması
önerilir — `--yedek` seçeneği bunu kendisi yapar.

Kontroller `parti_ayristir.py` ile aynı: eksik belge, mükerrer numara,
sıra bozukluğu, boş veya çok kısa gövde. Biri tutmuyorsa DOSYA YAZMAZ.

KULLANIM

    python dilekce_ayristir.py 01 --kuru     # kontrol et, YAZMA
    python dilekce_ayristir.py 01 --yedek    # once yedek al, sonra yaz
    python dilekce_ayristir.py 01
    python dilekce_ayristir.py --hepsi
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

BURASI = Path(__file__).resolve().parent

PARTILER = BURASI / "partiler_dilekce"
CEVAPLAR = BURASI / "cevaplar"
GOVDELER = BURASI / "govdeler"

AYRAC = re.compile(r"^#{2,4}\s*BELGE\s*(\d{1,3})\s*$", re.IGNORECASE | re.MULTILINE)
ASGARI_UZUNLUK = 80


def parti_numaralari(parti_no: str) -> list[str]:
    yol = PARTILER / f"dilekce_parti_{parti_no}.numaralar"
    if not yol.exists():
        raise SystemExit(f"HATA: {yol} yok. "
                         f"Once dilekce_parti_hazirla.py calistirin.")
    return yol.read_text(encoding="utf-8").split()


def ayristir(parti_no: str, kuru: bool) -> tuple[int, list[str], list[str]]:
    cevap_yolu = CEVAPLAR / f"dilekce_cevap_{parti_no}.txt"
    if not cevap_yolu.exists():
        raise SystemExit(
            f"HATA: {cevap_yolu} yok.\n"
            f"Sohbetten gelen cevabin TAMAMINI bu dosyaya yapistirin.")

    beklenen = parti_numaralari(parti_no)
    parcalar = AYRAC.split(cevap_yolu.read_text(encoding="utf-8"))
    if len(parcalar) < 3:
        return 0, ["Hicbir '### BELGE NNN' ayraci bulunamadi."], []

    onsoz = parcalar[0].strip()
    bulunan: dict[str, str] = {}
    for i in range(1, len(parcalar) - 1, 2):
        no = parcalar[i].zfill(3)
        if no in bulunan:
            return 0, [f"Belge {no} iki kez gecmis."], []
        bulunan[no] = parcalar[i + 1].strip()

    hatalar, uyarilar = [], []
    if onsoz and len(onsoz) > 20:
        uyarilar.append(f"Ilk ayractan once metin vardi, atildi: "
                        f"{onsoz[:50]!r}")

    eksik = [n for n in beklenen if n not in bulunan]
    fazla = [n for n in bulunan if n not in beklenen]
    if eksik:
        hatalar.append(f"EKSIK belge: {eksik}")
    if fazla:
        hatalar.append(f"FAZLA/YANLIS numara: {fazla}")
    kisa = [n for n, g in bulunan.items() if len(g) < ASGARI_UZUNLUK]
    if kisa:
        hatalar.append(f"COK KISA govde: {kisa}")

    if hatalar:
        return 0, hatalar, uyarilar
    if kuru:
        return len(bulunan), [], uyarilar

    for no, govde in bulunan.items():
        (GOVDELER / f"govde_{no}.txt").write_text(govde + "\n",
                                                  encoding="utf-8")
    return len(bulunan), [], uyarilar


def yedek_al() -> Path:
    damga = datetime.now().strftime("%Y%m%d_%H%M")
    hedef = BURASI / f"govdeler_yedek_{damga}"
    shutil.copytree(GOVDELER, hedef)
    return hedef


def main() -> int:
    a = argparse.ArgumentParser(description="ADIM 4.4e dilekce ayristirma")
    a.add_argument("parti", nargs="?", help="parti numarasi, or. 01")
    a.add_argument("--hepsi", action="store_true")
    a.add_argument("--kuru", action="store_true", help="kontrol et, YAZMA")
    a.add_argument("--yedek", action="store_true",
                   help="yazmadan once govdeler klasorunu yedekle")
    ns = a.parse_args()

    if ns.hepsi:
        numaralar = sorted(p.stem.split("_")[-1]
                           for p in CEVAPLAR.glob("dilekce_cevap_*.txt"))
        if not numaralar:
            raise SystemExit(f"HATA: {CEVAPLAR} icinde dilekce cevabi yok.")
    elif ns.parti:
        numaralar = [ns.parti.zfill(2)]
    else:
        raise SystemExit("Parti numarasi verin veya --hepsi kullanin.")

    if ns.yedek and not ns.kuru:
        y = yedek_al()
        print(f"Yedek alindi -> {y}\n")

    toplam, sorunlu = 0, []
    for no in numaralar:
        adet, hatalar, uyarilar = ayristir(no, ns.kuru)
        for u in uyarilar:
            print(f"dilekce_parti_{no}  ! {u}")
        if hatalar:
            print(f"dilekce_parti_{no}  !! AYRISTIRILAMADI")
            for h in hatalar:
                print(f"     {h}")
            sorunlu.append(no)
        else:
            durum = "kontrol edildi" if ns.kuru else "YAZILDI"
            print(f"dilekce_parti_{no}  {adet} govde {durum}")
            toplam += adet

    print(f"\nToplam {toplam} govde. Sorunlu parti: {sorunlu or 'yok'}")
    if sorunlu:
        return 1
    if not ns.kuru and toplam:
        print("\nSIRADAKI: python denetle_govde.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
