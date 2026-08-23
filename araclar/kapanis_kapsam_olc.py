#!/usr/bin/env python3
"""Hiyerarsi tablosu kapanis yonunu ne kadar dogru veriyor — 300 etikette olcum.

Depo kokunden ELLE calistirilir. LLM CAGRISI YAPMAZ, kredi harcamaz.

    python araclar/kapanis_kapsam_olc.py

NE OLCUYOR
----------
Denetci Katman 3'te modele `makam_konumu(makam_adi)` diye bir arac
verilecek. Arac, gonderenin alici kuruma gore konumunu kurum*.json
hiyerarsi listelerinden okuyup beklenen kapanisi soyleyecek:

    gonderen UST MAKAM ise   ->  beklenen kapanis  RICA
    diger her durumda        ->  beklenen kapanis  ARZ

Bu kural kota.json `kapanis_kurali` blogundan geliyor, uydurulmadi:

    vatandas   arz     ust_makam   RICA
    ozel_tuzel arz     ayni_duzey  arz
    alt_makam  arz

Yani "rica" YALNIZCA ust makam yazarken dogrudur. Aracin guvenilir olmasi
icin ust makamlari kacirmamasi gerekir.

RISK — hangi hata pahali
------------------------
    UST'u kaciririz    -> "arz beklenir" deriz, belge dogru olarak "rica"
                          yazmistir -> YANLIS ALARM. PAHALI.
    UST sanmisizdir    -> "rica beklenir" deriz, belge "arz" yazmistir
                          -> YANLIS ALARM. PAHALI.

Ikisi de yanlis alarm uretir. Bu yuzden esikleri degil, KAPSAMI olcuyoruz:
etiketteki `beklenen_kapanis` cevap anahtaridir.

CIKTI kapanis_kapsam_sonuc.txt dosyasina da yazilir.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "src"))
sys.path.insert(0, str(KOK / "araclar"))

from kural_motoru_dogrula import etiket_klasoru, klasor_bul  # noqa: E402
from metin import benzerlik, katla                            # noqa: E402

KURUM_KLASORU = KOK / "veri" / "kurumlar"

# Alici kurumu kurum*.json ile eslerken kullanilan esik. Adlar birebir
# yazilmiyor ("Gazi Universitesi" / "Gazi Universitesi Rektorlugu"),
# bu yuzden benzerlik kullaniliyor. Esik olculdu degil SECILDI; kapsam
# olcumu zaten yanlis eslesmeyi ortaya cikarir.
KURUM_ESIGI = 0.75


def hiyerarsileri_yukle() -> dict[str, dict]:
    """kurum*.json dosyalarindan {kurum_adi: hiyerarsi} sozlugu."""
    tablo: dict[str, dict] = {}
    if not KURUM_KLASORU.exists():
        sys.exit(f"HATA: {KURUM_KLASORU} bulunamadi.")
    for yol in sorted(KURUM_KLASORU.glob("kurum*.json")):
        d = json.loads(yol.read_text(encoding="utf-8"))
        ad = d.get("kurum_adi")
        if ad:
            tablo[ad] = d.get("hiyerarsi", {}) or {}
    if not tablo:
        sys.exit(f"HATA: {KURUM_KLASORU} icinde kurum*.json yok.")
    return tablo


def konum_bul(gonderen_adi: str | None, alici_adi: str,
              tablo: dict[str, dict]) -> str:
    """Gonderenin aliciya gore konumu.

    Doner: ust_makam | ayni_duzey | alt_makam | bulunamadi | kurum_yok

    Eslesme KATLANMIS alt dize ile yapiliyor (metin.katla): Turkce
    isaretleri dusurur, buyuk/kucuk harfi esitler. Iki yonlu bakiliyor
    cunku listedeki ad bazen daha uzun ("Ankara Buyuksehir Belediye
    Baskanligi"), bazen daha kisa ("Yenimahalle Belediyesi mudurlukleri").
    """
    if not gonderen_adi:
        return "gercek_kisi"

    hiyerarsi = None
    for ad, h in tablo.items():
        if benzerlik(ad, alici_adi) >= KURUM_ESIGI:
            hiyerarsi = h
            break
    if hiyerarsi is None:
        return "kurum_yok"

    g = katla(gonderen_adi)
    for konum, anahtar in (
        ("ust_makam", "ust_makamlar"),
        ("ayni_duzey", "ayni_duzey"),
        ("alt_makam", "alt_makamlar"),
    ):
        for aday in hiyerarsi.get(anahtar, []) or []:
            k = katla(aday)
            if not k:
                continue
            if k in g or g in k:
                return konum
    return "bulunamadi"


def beklenen_kapanis(konum: str) -> str:
    """kota.json kapanis_kurali: RICA yalnizca ust makam yazarken."""
    return "rica" if konum == "ust_makam" else "arz"


def main() -> int:
    tablo = hiyerarsileri_yukle()
    ek = etiket_klasoru(klasor_bul())
    etiketler = sorted(ek.glob("etiket_*.json"))
    if not etiketler:
        sys.exit("HATA: etiket_*.json bulunamadi.")

    cikti = KOK / "kapanis_kapsam_sonuc.txt"
    with cikti.open("w", encoding="utf-8") as f:
        def yaz(s: str = "") -> None:
            print(s)
            f.write(s + "\n")

        yaz("KAPANIS YONU - HIYERARSI TABLOSU KAPSAM OLCUMU")
        yaz("=" * 72)
        yaz(f"  kurum dosyasi : {KURUM_KLASORU}")
        yaz(f"  etiket        : {len(etiketler)} belge")
        yaz(f"  yuklenen kurum: {', '.join(tablo)}")
        yaz("")

        dogru = 0
        yanlis: list[str] = []
        konum_dagilimi: Counter = Counter()
        kacan_ust: list[str] = []       # etiket rica diyor, biz arz dedik
        fazla_ust: list[str] = []       # etiket arz diyor, biz rica dedik
        bulunamayan_gonderenler: Counter = Counter()
        atlanan = 0

        for yol in etiketler:
            e = json.loads(yol.read_text(encoding="utf-8"))
            no = e.get("belge_no", yol.stem)
            etiket_kapanis = e.get("beklenen_kapanis")
            if not etiket_kapanis:
                atlanan += 1
                continue

            gonderen = (e.get("gonderen") or {}).get("kurum_adi")
            alici = (e.get("alici") or {}).get("kurum_adi") or ""
            konum = konum_bul(gonderen, alici, tablo)
            konum_dagilimi[konum] += 1
            if konum in ("bulunamadi", "kurum_yok") and gonderen:
                bulunamayan_gonderenler[gonderen] += 1

            bizim = beklenen_kapanis(konum)
            # karma_kapanis: 12 belge "arz/rica ederim" ile biter
            # (kota.json). Etikette bu deger nasil gorunuyorsa oyle
            # karsilastirilir; esit degilse hata sayilir ve asagida
            # ayrica listelenir.
            if bizim == etiket_kapanis:
                dogru += 1
            else:
                satir = (f"{no}: etiket={etiket_kapanis} biz={bizim} "
                         f"konum={konum} gonderen={gonderen or '(gercek kisi)'}")
                yanlis.append(satir)
                if etiket_kapanis == "rica":
                    kacan_ust.append(satir)
                else:
                    fazla_ust.append(satir)

        toplam = dogru + len(yanlis)
        yaz("SONUC")
        yaz("-" * 72)
        yaz(f"  olculen belge         {toplam}"
            + (f"  (etikette beklenen_kapanis olmayan {atlanan} atlandi)"
               if atlanan else ""))
        if toplam:
            yaz(f"  DOGRU                 {dogru}/{toplam} = {dogru/toplam:.1%}")
            yaz(f"  yanlis                {len(yanlis)}")
        yaz("")

        yaz("KONUM DAGILIMI")
        yaz("-" * 72)
        for k, adet in konum_dagilimi.most_common():
            yaz(f"  {k:16} {adet}")
        yaz("")

        yaz("HATA TURLERI")
        yaz("-" * 72)
        yaz(f"  UST MAKAM KACIRILDI   {len(kacan_ust)}   "
            f"(etiket rica, biz arz dedik)")
        for x in kacan_ust[:15]:
            yaz(f"    {x}")
        yaz(f"  FAZLADAN UST SANILDI  {len(fazla_ust)}   "
            f"(etiket arz, biz rica dedik)")
        for x in fazla_ust[:15]:
            yaz(f"    {x}")
        yaz("")

        if bulunamayan_gonderenler:
            yaz("HIYERARSI TABLOSUNDA BULUNAMAYAN GONDERENLER")
            yaz("-" * 72)
            for ad, adet in bulunamayan_gonderenler.most_common(20):
                yaz(f"  {adet:4}  {ad}")
            yaz("")

        yaz(f"sonuc dosyasi: {cikti}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
