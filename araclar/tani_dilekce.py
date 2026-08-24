"""Dilekçelerde imza sahibi neden bulunamıyor — teşhis.

NEREYE:  araclar/
NASIL:   python araclar\\tani_dilekce.py            varsayılan liste
         python araclar\\tani_dilekce.py 017 027    belirli belgeler
ÇIKTI:   ekrana; dosya yazmaz

NE GÖSTERİYOR
-------------
Gönderen ölçümünde bulunamayan her dilekçe için:

    kapanış satırı nerede         (_imza buradan aşağı bakıyor)
    kapanıştan sonraki satırlar   (_AD_SOYAD burada aranıyor)
    son 8 satır                   (_dilekce_imzasi buradan geriye tarıyor)
    her satırın hangi desene uyduğu

Böylece "regex neden tutmadı" sorusu tahminle değil, satırla cevaplanır.
"""

from __future__ import annotations

import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "src"))

# Gönderen ölçümünde bulunamayan dilekçeler (2026-08-24 koşusu).
VARSAYILAN = ("017", "027", "070", "072", "077", "097", "098", "099",
              "101", "102", "116", "155", "176", "178", "201", "235",
              "249", "262", "270", "299")

ARAMA_YERLERI = (
    ("deneyler", "adim4", "belgeler_pdf"),
    ("veri", "belgeler"),
    ("ornek",),
)


def klasor_bul() -> Path:
    for p in ARAMA_YERLERI:
        y = KOK.joinpath(*p)
        if y.exists() and any(y.glob("belge_*.pdf")):
            return y
    for b in KOK.rglob("belge_*.pdf"):
        return b.parent
    sys.exit("belge_*.pdf bulunamadi.")


def main() -> int:
    from ayristirici import (
        _AD_SATIR_SONU,
        _AD_SOYAD,
        _IMZA_TEK_SATIR,
        _KAPANIS,
        ayristir,
    )
    from okuyucu import oku

    numaralar = tuple(sys.argv[1:]) or VARSAYILAN
    klasor = klasor_bul()

    for no in numaralar:
        pdf = klasor / f"belge_{no}.pdf"
        if not pdf.exists():
            print(f"--- {no}: PDF yok ({pdf})")
            continue
        r = oku(pdf)
        if r.hata or not r.satirlar:
            print(f"--- {no}: okunamadi ({r.hata})")
            continue
        a = ayristir(r.satirlar,
                     r.ayrilmis.dipnot_bulundu if r.ayrilmis else None)

        kapanis = None
        for i, s in enumerate(r.satirlar):
            if _KAPANIS.search(s.metin):
                kapanis = i

        print(f"\n{'=' * 70}")
        print(f"belge_{no}   aile={a.aile}   muhatap_satiri={a.muhatap_satiri}   "
              f"kapanis={kapanis}   satir={len(r.satirlar)}")
        print(f"  imza.ad   = {a.ustveri.imza.ad!r}")
        print(f"  gonderen  = ad={a.ustveri.gonderen.ad!r} "
              f"idare={a.ustveri.gonderen.idare!r}")
        print(f"  uyarilar  = {a.uyarilar}")
        print(f"{'-' * 70}")
        # Kapanıştan sonrası + son 8 satır, hangisi genişse.
        bas = min(kapanis + 1 if kapanis is not None else len(r.satirlar),
                  max(0, len(r.satirlar) - 8))
        for i in range(bas, len(r.satirlar)):
            m = r.satirlar[i].metin
            isaret = []
            if _AD_SOYAD.match(m.strip()):
                isaret.append("AD_SOYAD")
            g = _AD_SATIR_SONU.search(m)
            if g:
                isaret.append(f"SATIR_SONU->{g.group(1)!r}")
            if _IMZA_TEK_SATIR.match(m.strip()):
                isaret.append("TEK_SATIR")
            print(f"  [{i:3d}] {m!r}")
            if isaret:
                print(f"        ^ {' · '.join(isaret)}")
            else:
                print("        ^ hicbir desen tutmadi")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
