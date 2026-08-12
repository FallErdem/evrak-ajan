#!/usr/bin/env python3
"""ADIM 4.5b — kusur enjeksiyonunun DOĞRU çalıştığını kanıtlar.

Enjeksiyon iki yönde de sınanır:

    1. KUSURLU metin linter'dan GEÇMEMELİ
       Geçiyorsa kusur ya uygulanmamış ya linter yakalayamıyor.

    2. ORİJİNAL metin linter'dan GEÇMELİ
       Geçmiyorsa zaten bozuktu; kusuru biz koymadık.

İkisi birden tutmazsa o belge değerlendirmede kullanılamaz: sistem
kusuru bulamadığında sebebin sistem mi veri mi olduğunu ayıramayız.

AYRICA: kusurun DOĞRU KURALI tetiklediği kontrol edilir. ilgi_kopuk
kusuru ILG-02 vermeli, BCM-01 değil — yanlış kural tetiklenirse
kusur profili ile ölçüm birbirini tutmaz.

KULLANIM

    python denetle_kusur.py
    python denetle_kusur.py --belge 031
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

BURASI = Path(__file__).resolve().parent
DEPO_KOKU = BURASI.parent.parent
sys.path.insert(0, str(DEPO_KOKU))

from src.linter import Etiket, denetle  # noqa: E402

GOVDELER = BURASI / "govdeler"
KUSURLU = BURASI / "govdeler_kusurlu"
ETIKETLER = BURASI / "etiketler"

# Hangi kusur hangi kuralı tetiklemeli.
BEKLENEN_KURAL = {
    "ilgi_kopuk": {"ILG-03", "KPS-01"},
    "kapanis_yanlis": {"ME-03"},
}


def etiket_kur(d: dict) -> Etiket:
    return Etiket(
        belge_no=d["belge_no"],
        yazan_tipi=d["yazan_tipi"],
        hiyerarsi_yonu=d["hiyerarsi_yonu"],
        ilgi_var=bool(d["ilgi"]),
        ek_var=bool(d["ek"]),
        paragraf_cumle_sayilari=d["paragraf_cumle_sayilari"],
        yasakli_adlar=d["yasakli_adlar"],
        anahtar_terimler=d["anahtar_terimler"],
        ek_adi=(d["ek"]["aciklama"] if d.get("ek") else ""),
    )


def main() -> int:
    a = argparse.ArgumentParser(description="ADIM 4.5b enjeksiyon dogrulamasi")
    a.add_argument("--belge", nargs="+", metavar="NO")
    ns = a.parse_args()

    if not KUSURLU.exists():
        raise SystemExit(f"HATA: {KUSURLU} yok. Once kusur_enjekte.py calistirin.")

    yollar = sorted(KUSURLU.glob("govde_*.txt"))
    if ns.belge:
        istenen = {n.zfill(3) for n in ns.belge}
        yollar = [y for y in yollar if y.stem.split("_")[-1] in istenen]

    gecerli, sorunlu = 0, []
    kural_sayaci: Counter = Counter()

    for y in yollar:
        no = y.stem.split("_")[-1]
        e_ham = json.loads((ETIKETLER / f"etiket_{no}.json").read_text(encoding="utf-8"))
        e = etiket_kur(e_ham)
        kusur = e_ham["kusur"]

        kusurlu_metin = y.read_text(encoding="utf-8")
        orijinal = (GOVDELER / f"govde_{no}.txt").read_text(encoding="utf-8")

        r_kusurlu = denetle(kusurlu_metin, e)
        r_orijinal = denetle(orijinal, e)

        kusurlu_kurallar = {b.kural for b in r_kusurlu.hatalar}
        beklenen = BEKLENEN_KURAL.get(kusur, set())

        hatalar = []
        if not r_kusurlu.hatalar:
            hatalar.append("kusurlu metin linter'dan GEÇTİ — kusur uygulanmamış "
                           "veya linter yakalayamıyor")
        elif beklenen and not (kusurlu_kurallar & beklenen):
            hatalar.append(f"yanlış kural tetiklendi: {sorted(kusurlu_kurallar)}, "
                           f"beklenen {sorted(beklenen)}")
        if r_orijinal.hatalar:
            hatalar.append(f"orijinal metin zaten bozuk: "
                           f"{[b.kural for b in r_orijinal.hatalar]}")

        if hatalar:
            sorunlu.append((no, kusur, hatalar))
            print(f"\nbelge_{no}  [{kusur}]")
            for h in hatalar:
                print(f"   x {h}")
        else:
            gecerli += 1
            for k in kusurlu_kurallar:
                kural_sayaci[k] += 1
            if ns.belge:
                print(f"\nbelge_{no}  [{kusur}]  GEÇERLİ")
                print(f"   orijinal : temiz")
                print(f"   kusurlu  : {sorted(kusurlu_kurallar)}")
                ay = e_ham.get("kusur_ayrinti", {})
                if ay:
                    print(f"   ÖNCE     : {str(ay.get('dogru_deger'))[:70]}")
                    print(f"   SONRA    : {str(ay.get('enjekte_edilen'))[:70]}")

    print("\n" + "=" * 66)
    print(f"SONUÇ: geçerli {gecerli} | sorunlu {len(sorunlu)}   "
          f"(toplam {gecerli + len(sorunlu)})")
    print("=" * 66)
    if kural_sayaci:
        print("  tetiklenen kurallar:")
        for k, n in kural_sayaci.most_common():
            print(f"    {k:<10} {n}")
    if sorunlu:
        print(f"\n  Sorunlu belgeler: {', '.join(no for no, _, _ in sorunlu)}")
        print("\n  Bu belgeler değerlendirmede kullanılamaz: sistem kusuru")
        print("  bulamadığında sebebin sistem mi veri mi olduğu ayrılamaz.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
