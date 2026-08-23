#!/usr/bin/env python3
"""Denetci'yi tek bir belgede dener. Depo kokunden calistirilir.

    python araclar/denetci_dene.py            belge_025 (imza_eksik)
    python araclar/denetci_dene.py 001        baska belge
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "src"))
sys.path.insert(0, str(KOK / "araclar"))

from ayristirici import ayristir          # noqa: E402
from denetci import Denetci               # noqa: E402
from kural_motoru_dogrula import dosya_kur, etiket_klasoru, klasor_bul  # noqa: E402
from okuyucu import oku                   # noqa: E402


def main(argv: list[str]) -> int:
    no = argv[0] if argv else "025"
    pdf_klasoru = klasor_bul()
    ek = etiket_klasoru(pdf_klasoru)

    pdf = pdf_klasoru / f"belge_{no}.pdf"
    etiket = ek / f"etiket_{no}.json"
    if not pdf.exists() or not etiket.exists():
        print(f"HATA: {pdf} ya da {etiket} yok")
        return 1

    print(f"belge  : {pdf}")
    e = json.loads(etiket.read_text(encoding="utf-8"))
    print(f"kusur  : {e.get('kusur')}")
    print(f"tur    : {e.get('belge_turu')}\n")

    r = oku(str(pdf))
    if r.hata or not r.ayrilmis:
        print(f"OKUMA HATASI: {r.hata}")
        return 1
    a = ayristir(r.ayrilmis.govde_satirlari, dipnot_var=r.ayrilmis.dipnot_bulundu)
    d = dosya_kur(r, a, e)

    sonuc = Denetci().calistir(d)
    print(sonuc.ozet)
    print(f"talep edilebilir eksik: {sonuc.talep_edilebilir_sayisi}\n")
    print("--- arayuze giden JSON (Icerik.eksik_alanlar) ---")
    print(json.dumps(
        [x.model_dump(mode="json") for x in d.icerik.eksik_alanlar],
        ensure_ascii=False, indent=2,
    ))
    print("\n--- arayuze giden JSON (Dosya.mevzuat) ---")
    print(json.dumps(
        [x.model_dump(mode="json") for x in d.mevzuat],
        ensure_ascii=False, indent=2,
    ))
    gizli = len(sonuc.mevzuat) - len(sonuc.gosterilecek_mevzuat)
    if gizli:
        print(f"\n{gizli} oneri dogrulanamadi, arayuzde GOSTERILMEZ (sozlesme 5.6.5)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
