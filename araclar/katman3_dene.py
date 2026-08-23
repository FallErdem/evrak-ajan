#!/usr/bin/env python3
"""Denetci Katman 3'u GERCEK modelle tek belgede dener.

Depo kokunden ELLE calistirilir. LLM CAGRISI YAPAR, kredi harcar.

    python araclar/katman3_dene.py                    belge_081
    python araclar/katman3_dene.py 048                baska belge
    python araclar/katman3_dene.py 048 yapilandirma.qwen.json

NE GOSTERIR
-----------
Ajan dongusunun her adimini: model hangi araci hangi argumanla cagirdi,
arac ne gozlem dondurdu, model sonunda ne iddia etti, iddia elendi mi.

Bu ciktinin kendisi sunum malzemesidir - "ajan kendi iddiasini eliyor"
cumlesi burada gorunur hale gelir.

ONCE KATMAN 2, SONRA KATMAN 3
-----------------------------
Denetci Katman 2'yi once kosturur ve `kural_bulgulari` araci onun
ciktisini okur. Boylece model motorun ZATEN buldugu bir eksigi tekrar
iddia etmez.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "src"))
sys.path.insert(0, str(KOK / "araclar"))

from ayristirici import ayristir                                    # noqa: E402
from denetci import AZAMI_TUR, Denetci                              # noqa: E402
from kural_motoru_dogrula import dosya_kur, etiket_klasoru, klasor_bul  # noqa: E402
from llm_istemci import LLMHatasi, istemci_olustur                  # noqa: E402
from okuyucu import oku                                            # noqa: E402

VARSAYILAN_YAPILANDIRMA = "yapilandirma.qwen.json"


def yapilandirma_bul(ad: str) -> Path | None:
    """Yapilandirma deponun neresinde durdugu net degil; sirayla aranir."""
    dogrudan = Path(ad)
    if dogrudan.exists():
        return dogrudan.resolve()
    for aday in (KOK / ad, KOK / "veri" / ad, KOK / "yapilandirma" / ad):
        if aday.exists():
            return aday
    for bulunan in KOK.rglob(ad):
        if ".venv" not in bulunan.parts:
            return bulunan
    return None


def main(argv: list[str]) -> int:
    no = next((a for a in argv if a.isdigit()), "081")
    yap_adi = next((a for a in argv if a.endswith(".json")), VARSAYILAN_YAPILANDIRMA)

    yap = yapilandirma_bul(yap_adi)
    if yap is None:
        print(f"HATA: {yap_adi} bulunamadi.")
        print(f"  {KOK} agacinda arandi. Yolu komut satirindan verin:")
        print("    python araclar/katman3_dene.py 081 yol/yapilandirma.qwen.json")
        return 1

    pdf_klasoru = klasor_bul()
    ek = etiket_klasoru(pdf_klasoru)
    pdf = pdf_klasoru / f"belge_{no}.pdf"
    etiket = ek / f"etiket_{no}.json"
    if not pdf.exists() or not etiket.exists():
        print(f"HATA: {pdf} ya da {etiket} yok")
        return 1

    print("KATMAN 3 DENEMESI - GERCEK MODEL CAGRISI YAPAR")
    print("=" * 72)
    print(f"  yapilandirma : {yap}")
    print(f"  belge        : {pdf.name}")

    e = json.loads(etiket.read_text(encoding="utf-8"))
    print(f"  kusur        : {e.get('kusur')}")
    print(f"  belge turu   : {e.get('belge_turu')}")

    r = oku(str(pdf))
    if r.hata or not r.ayrilmis:
        print(f"OKUMA HATASI: {r.hata}")
        return 1
    a = ayristir(r.ayrilmis.govde_satirlari, dipnot_var=r.ayrilmis.dipnot_bulundu)
    d = dosya_kur(r, a, e)

    print()
    print("GOVDE (modele giden metin)")
    print("-" * 72)
    print((d.metin or "(govde kurulamadi)")[:600])
    print()

    try:
        istemci = istemci_olustur(yap)
    except (LLMHatasi, FileNotFoundError, ValueError) as hata:
        print(f"ISTEMCI KURULAMADI: {hata}")
        return 1

    denetci = Denetci(istemci=istemci)
    try:
        sonuc = denetci.calistir(d)
    except LLMHatasi as hata:
        print(f"LLM HATASI: {hata}")
        return 1

    print("KATMAN 2 (kural motoru)")
    print("-" * 72)
    kural_eksikleri = [x for x in sonuc.eksikler if x.katman == "kural"]
    if not kural_eksikleri:
        print("  bulgu yok")
    for x in kural_eksikleri:
        print(f"  {x.kural_id}  {x.aciklama[:80]}")

    print()
    print(f"KATMAN 3 (ajan dongusu, en fazla {AZAMI_TUR} tur)")
    print("-" * 72)
    if not sonuc.ajan_izi:
        print("  dongu hic kosmadi")
    for adim in sonuc.ajan_izi:
        print(f"  {adim}")

    print()
    print("ELEME")
    print("-" * 72)
    if not sonuc.ajan_elenen:
        print("  elenen iddia yok")
    for x in sonuc.ajan_elenen:
        print(f"  ELENDI: {x}")

    print()
    print("SONUC - arayuze giden JSON")
    print("-" * 72)
    print(json.dumps(
        [x.model_dump(mode="json") for x in d.icerik.eksik_alanlar],
        ensure_ascii=False, indent=2,
    ))

    print()
    print("MALIYET")
    print("-" * 72)
    print(f"  cagri sayisi : {getattr(istemci, 'cagri_sayisi', '?')}")
    print(f"  girdi token  : {getattr(istemci, 'toplam_girdi', '?')}")
    print(f"  cikti token  : {getattr(istemci, 'toplam_genel', '?')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
