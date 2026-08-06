#!/usr/bin/env python3
"""ADIM 1 — üretilen metinleri etiketlerine karşı denetler.

    ciktilar/MODEL/belge_NN.txt  +  etiketler/belge_NN.json
                        |
                    src/linter.py
                        |
                 rapor + kosum.py için yeniden üretim listesi

KULLANIM

    python denetle.py                      # varsayılan modeli denetle
    python denetle.py --model gemini-3.6-flash
    python denetle.py --belge 07 08        # yalnızca belirli belgeler
    python denetle.py --ayrintili          # temiz belgelerin metnini de göster
    python denetle.py --sessiz             # yalnızca özet

NEDEN AYRI BİR BETİK
Üretim (kosum.py) ile denetim (bu dosya) ayrı katmanlar. Karıştırılırsa
ikisi de ayrı ayrı test edilemez: üretim çıktısını kendisi denetlerse,
denetimin doğru çalıştığını nasıl anlarız? ADIM 6'da bu ikisi bir
döngüde birleşecek ama kodları ayrı kalacak.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BURASI = Path(__file__).resolve().parent
DEPO_KOKU = BURASI.parent.parent
sys.path.insert(0, str(DEPO_KOKU))

from src.linter import Etiket, Onem, denetle  # noqa: E402

CIKTILAR = BURASI / "ciktilar"
ETIKETLER = BURASI / "etiketler"
YAPILANDIRMA = DEPO_KOKU / "yapilandirma.json"


def varsayilan_model() -> str:
    """Yapılandırmadaki modeli okur; yoksa tek çıktı klasörünü seçer."""
    if YAPILANDIRMA.exists():
        try:
            veri = json.loads(YAPILANDIRMA.read_text(encoding="utf-8"))
            if veri.get("model"):
                return str(veri["model"]).replace("/", "_")
        except json.JSONDecodeError:
            pass
    klasorler = [k.name for k in CIKTILAR.iterdir() if k.is_dir()] if CIKTILAR.exists() else []
    if len(klasorler) == 1:
        return klasorler[0]
    raise SystemExit(
        f"HATA: model belirlenemedi. --model ile verin.\n"
        f"Mevcut çıktı klasörleri: {', '.join(klasorler) or '(yok)'}"
    )


def main() -> int:
    ayrist = argparse.ArgumentParser(description="Üretilen metinleri denetle")
    ayrist.add_argument("--model", help="çıktı klasörünün adı")
    ayrist.add_argument("--belge", nargs="+", metavar="NO", help="ör. 07 08")
    ayrist.add_argument("--ayrintili", action="store_true",
                        help="temiz belgelerin metnini de göster")
    ayrist.add_argument("--sessiz", action="store_true", help="yalnızca özet")
    a = ayrist.parse_args()

    model = a.model or varsayilan_model()
    kaynak = CIKTILAR / model
    if not kaynak.exists():
        raise SystemExit(f"HATA: çıktı klasörü yok: {kaynak}")

    numaralar = (
        [n.zfill(2) for n in a.belge] if a.belge
        else sorted(p.stem.split("_")[-1] for p in kaynak.glob("belge_*.txt"))
    )
    if not numaralar:
        raise SystemExit(f"HATA: {kaynak} içinde belge bulunamadı.")

    print(f"Model  : {model}")
    print(f"Belge  : {len(numaralar)} adet")
    print("=" * 70)

    temiz, hatali, eksik = [], [], []
    toplam_hata = toplam_uyari = 0

    for no in numaralar:
        metin_yolu = kaynak / f"belge_{no}.txt"
        etiket_yolu = ETIKETLER / f"belge_{no}.json"

        if not metin_yolu.exists():
            print(f"belge_{no}  — metin yok: {metin_yolu.name}")
            eksik.append(no)
            continue
        if not etiket_yolu.exists():
            print(f"belge_{no}  — ETİKET YOK: {etiket_yolu.name}")
            eksik.append(no)
            continue

        # Kodlama hatası bütün koşuyu durdurmamalı. Windows'ta cp1252 ile
        # kaydedilmiş tek bir dosya, 450 belgelik denetimi çökertmemeli.
        # Bozuk dosya raporlanır ve sonrakine geçilir.
        try:
            metin = metin_yolu.read_text(encoding="utf-8")
        except UnicodeDecodeError as hata:
            print(f"belge_{no}  ✗ KODLAMA HATASI (konum {hata.start})")
            print(f"   Dosya UTF-8 değil. Not Defteri'nde açıp "
                  f"'Farklı Kaydet' ile kodlamayı UTF-8 seçin.")
            print()
            hatali.append(no)
            toplam_hata += 1
            continue

        etiket = Etiket.yukle(etiket_yolu)
        rapor = denetle(metin, etiket)

        toplam_hata += len(rapor.hatalar)
        toplam_uyari += len(rapor.uyarilar)

        if rapor.temiz_mi and not rapor.uyarilar:
            temiz.append(no)
            if not a.sessiz:
                print(f"belge_{no}  ✓ temiz")
        else:
            if rapor.hatalar:
                hatali.append(no)
            else:
                temiz.append(no)
            if not a.sessiz:
                durum = f"✗ {len(rapor.hatalar)} hata" if rapor.hatalar else "✓ temiz"
                if rapor.uyarilar:
                    durum += f", {len(rapor.uyarilar)} uyarı"
                print(f"belge_{no}  {durum}")
                for b in rapor.bulgular:
                    print(b)

        if a.ayrintili and not a.sessiz:
            print("   " + "-" * 60)
            for satir in metin.strip().splitlines():
                print(f"   | {satir}")
            print("   " + "-" * 60)

        if not a.sessiz:
            print()

    # --- özet ---------------------------------------------------------------
    print("=" * 70)
    print(f"Temiz {len(temiz)} | hatalı {len(hatali)} | eksik {len(eksik)}")
    print(f"Toplam {toplam_hata} hata, {toplam_uyari} uyarı")

    if hatali:
        # Doğrudan kopyalanabilir komut: hatalıları yeniden üret
        print(f"\nHatalı belgeleri yeniden üretmek için:")
        print(f"  python kosum.py --belge {' '.join(hatali)} --yeniden")

    return 1 if hatali else 0


if __name__ == "__main__":
    raise SystemExit(main())
