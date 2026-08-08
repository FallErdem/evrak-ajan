#!/usr/bin/env python3
"""ADIM 4.3 — etiketlerden şartname metinlerini üretir.

    etiketler/etiket_NNN.json  +  istemler/talimat_vN.txt
                        |
              src/sartname_render.py
                        |
              sartnameler/sartname_NNN.txt

BU BETİK MODELE HİÇBİR ŞEY GÖNDERMEZ. Ağa çıkmaz, para harcamaz.
Modele gönderme 4.4'ün işi.

KULLANIM

    python hazirla_sartname.py --ornek 3     # 3 ornegi ekrana bas, YAZMA
    python hazirla_sartname.py --belge 018   # tek belge, ekrana
    python hazirla_sartname.py               # 300 sartname dosyasi yaz
    python hazirla_sartname.py --temizle     # once eski dosyalari sil

NEDEN ONCE --ornek
Sartname 300 belgenin tamami icin modele gidecek metin. Bicimde bir hata
varsa 300 belgeye birden yansir. Once uc ornegi GOZLE OKUYUP "bununla
gercek bir resmi yazi yazilabilir mi" diye sormak gerekiyor.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

BURASI = Path(__file__).resolve().parent
DEPO_KOKU = BURASI.parent.parent
sys.path.insert(0, str(DEPO_KOKU))

from src.sartname_render import etiket_yukle, istem_kur, sartname_uret  # noqa: E402

ETIKETLER = BURASI / "etiketler"
ISTEMLER = BURASI / "istemler"
HEDEF = BURASI / "sartnameler"

# Turkce metinde kabaca 3 karakter ~ 1 token. Yalnizca buyukluk fikri icin.
KABA_TOKEN_BOLENI = 3


def talimat_bul() -> Path:
    adaylar = sorted(
        ISTEMLER.glob("talimat_v*.txt"),
        key=lambda p: int(re.search(r"_v(\d+)", p.stem).group(1)),
    )
    if not adaylar:
        raise SystemExit(f"HATA: {ISTEMLER} icinde talimat_vN.txt bulunamadi.")
    return adaylar[-1]


def main() -> int:
    a = argparse.ArgumentParser(description="ADIM 4.3 sartname uretimi")
    a.add_argument("--ornek", type=int, default=0,
                   help="N ornegi ekrana bas, dosya yazma")
    a.add_argument("--belge", nargs="+", metavar="NO",
                   help="belirli belgeleri ekrana bas")
    a.add_argument("--temizle", action="store_true", help="eski dosyalari sil")
    a.add_argument("--tam", action="store_true",
                   help="ornekte talimat blogunu da goster")
    ns = a.parse_args()

    talimat_yolu = talimat_bul()
    talimat = talimat_yolu.read_text(encoding="utf-8")
    yollar = sorted(ETIKETLER.glob("etiket_*.json"))
    if not yollar:
        raise SystemExit(f"HATA: {ETIKETLER} icinde etiket bulunamadi.")

    print(f"Talimat : {talimat_yolu.name}")
    print(f"Etiket  : {len(yollar)} adet")

    # --- ornek gosterimi ---------------------------------------------------
    if ns.ornek or ns.belge:
        if ns.belge:
            istenen = {n.zfill(3) for n in ns.belge}
            secim = [y for y in yollar if y.stem.split("_")[-1] in istenen]
        else:
            # Farkli yazar tiplerinden ornek sec: hepsi kurum yazisi olursa
            # gecersiz kilma bloklarini hic gormeyiz
            gorulen: set[str] = set()
            secim = []
            for y in yollar:
                e = etiket_yukle(y)
                if e["yazan_tipi"] not in gorulen:
                    gorulen.add(e["yazan_tipi"]); secim.append(y)
                if len(secim) >= ns.ornek:
                    break
            secim += [y for y in yollar if y not in secim][:ns.ornek - len(secim)]

        for y in secim:
            e = etiket_yukle(y)
            metin = istem_kur(talimat, e) if ns.tam else sartname_uret(e)
            print("\n" + "=" * 70)
            print(f"  {y.name}   [{e['belge_turu']} / {e['yazan_tipi']} / "
                  f"{e['beklenen_kapanis']}]")
            print("=" * 70)
            print(metin)
        return 0

    # --- dosya yazimi ------------------------------------------------------
    if ns.temizle and HEDEF.exists():
        shutil.rmtree(HEDEF)
    HEDEF.mkdir(parents=True, exist_ok=True)

    boyutlar, tipler = [], Counter()
    for y in yollar:
        e = etiket_yukle(y)
        istem = istem_kur(talimat, e)
        (HEDEF / f"sartname_{e['belge_no']}.txt").write_text(istem, encoding="utf-8")
        boyutlar.append(len(istem))
        tipler[e["yazan_tipi"]] += 1

    ort = sum(boyutlar) / len(boyutlar)
    print(f"\n{len(yollar)} sartname yazildi -> {HEDEF}")
    print(f"  yazar tipi     : {dict(tipler)}")
    print(f"  boyut          : {min(boyutlar)}-{max(boyutlar)} karakter "
          f"(ortalama {ort:.0f})")
    print(f"  kaba token     : ~{ort / KABA_TOKEN_BOLENI:.0f} / belge, "
          f"toplam ~{sum(boyutlar) / KABA_TOKEN_BOLENI:,.0f}")
    print("\n(Bu betik modele hicbir sey gondermedi. Gonderim 4.4'un isi.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
