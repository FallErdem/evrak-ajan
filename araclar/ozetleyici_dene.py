#!/usr/bin/env python3
"""Ozetleyici'yi GERCEK modelle tek belgede dener. LLM CAGRISI YAPAR.

Depo kokunden ELLE calistirilir.

    python araclar/ozetleyici_dene.py             belge_030
    python araclar/ozetleyici_dene.py 081         baska belge
    python araclar/ozetleyici_dene.py 081 yapilandirma.qwen.json

Tek cagri, birkac bin token.

NE GOSTERIR
-----------
Modele giden gövdeyi, donen talep ve ozeti, ve SAYISAL DOGRULAMANIN
sonucunu. Ozette gecen her sayi ve tarih kaynakta aranir; bulunamayan
varsa isaretlenir.

Ozet, memurun BELGEYI OKUMAK YERINE okuyacagi metindir. Uydurma bir tarih
ya da tutar oraya girerse memur ona guvenip islem yapar ve kimse fark
etmez — karsilastiracagi bir cevap anahtari yoktur. Dogrulamanin sebebi
budur.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "src"))
sys.path.insert(0, str(KOK / "araclar"))

from ayristirici import ayristir                                      # noqa: E402
from katman3_dene import yapilandirma_bul                             # noqa: E402
from kural_motoru_dogrula import dosya_kur, etiket_klasoru, klasor_bul  # noqa: E402
from llm_istemci import LLMHatasi, istemci_olustur                    # noqa: E402
from okuyucu import oku                                               # noqa: E402
from ozetleyici import Ozetleyici                                     # noqa: E402

VARSAYILAN_YAPILANDIRMA = "yapilandirma.qwen.json"


def main(argv: list[str]) -> int:
    no = next((a for a in argv if a.isdigit()), "030")
    yap_adi = next((a for a in argv if a.endswith(".json")), VARSAYILAN_YAPILANDIRMA)

    yap = yapilandirma_bul(yap_adi)
    if yap is None:
        print(f"HATA: {yap_adi} bulunamadi.")
        print("  Yolu komut satirindan verin:")
        print("    python araclar/ozetleyici_dene.py 030 yol/yapilandirma.qwen.json")
        return 1

    pdf_klasoru = klasor_bul()
    ek = etiket_klasoru(pdf_klasoru)
    pdf = pdf_klasoru / f"belge_{no}.pdf"
    etiket = ek / f"etiket_{no}.json"
    if not pdf.exists() or not etiket.exists():
        print(f"HATA: {pdf} ya da {etiket} yok")
        return 1

    print("OZETLEYICI DENEMESI - GERCEK MODEL CAGRISI YAPAR")
    print("=" * 72)
    print(f"  yapilandirma : {yap}")
    print(f"  belge        : {pdf.name}")

    e = json.loads(etiket.read_text(encoding="utf-8"))
    print(f"  belge turu   : {e.get('belge_turu')}")
    print(f"  kusur        : {e.get('kusur')}")

    r = oku(str(pdf))
    if r.hata or not r.ayrilmis:
        print(f"OKUMA HATASI: {r.hata}")
        return 1
    a = ayristir(r.ayrilmis.govde_satirlari, dipnot_var=r.ayrilmis.dipnot_bulundu)
    d = dosya_kur(r, a, e)

    print()
    print("MODELE GIDEN GOVDE")
    print("-" * 72)
    print((d.metin or "(govde kurulamadi)")[:700])

    try:
        istemci = istemci_olustur(yap)
    except (LLMHatasi, FileNotFoundError, ValueError) as hata:
        print(f"\nISTEMCI KURULAMADI: {hata}")
        return 1

    sonuc = Ozetleyici(istemci).calistir(d)

    print()
    print("CIKTI")
    print("-" * 72)
    print(f"  talep : {sonuc.talep}")
    print(f"  ozet  : {sonuc.ozet}")
    print(f"  uzunluk: talep {len(sonuc.talep or '')} · ozet {len(sonuc.ozet or '')}")

    print()
    print("SAYISAL DOGRULAMA")
    print("-" * 72)
    if not sonuc.bulunan_sayilar:
        print("  ozette denetlenecek sayisal deger yok")
        print("  (bu bir basarisizlik degildir; resmi ozetlerin cogu sayi tasimaz)")
    else:
        print(f"  ozette bulunan sayilar : {', '.join(sonuc.bulunan_sayilar)}")
        if sonuc.dogrulanmayan:
            print(f"  DOGRULANMAYAN          : {', '.join(sonuc.dogrulanmayan)}")
            print("  -> bu degerler kaynak belgede GECMIYOR")
        else:
            print("  hepsi kaynak belgede dogrulandi")

    if sonuc.uyarilar:
        print()
        print("UYARILAR")
        print("-" * 72)
        for u in sonuc.uyarilar:
            print(f"  {u}")

    print()
    print("SOZLESMEYE GIDEN ALANLAR (Icerik)")
    print("-" * 72)
    print(json.dumps(
        {"talep": d.icerik.talep, "ozet": d.icerik.ozet},
        ensure_ascii=False, indent=2,
    ))

    print()
    print("MALIYET")
    print("-" * 72)
    print(f"  cagri sayisi : {getattr(istemci, 'cagri_sayisi', '?')}")
    print(f"  girdi token  : {getattr(istemci, 'toplam_girdi', '?')}")
    print(f"  cikti token  : {getattr(istemci, 'toplam_genel', '?')}")
    print(f"  sure         : {sonuc.sure_ms:.0f} ms")
    return 0 if sonuc.basarili else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
