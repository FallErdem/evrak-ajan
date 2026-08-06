#!/usr/bin/env python3
"""ADIM 4.2 — 300 belgenin etiketini (cevap anahtarını) üretir.

    veri/kota.json + veri/taksonomi + veri/kurumlar
                        |
                 src/etiket_uretici.py
                        |
              etiketler/etiket_NNN.json  x300
                        +
              ozet.json  (kota tutturma raporu)

KULLANIM

    python uret_etiket.py --dogrula        # uret, kotayi kontrol et, YAZMA
    python uret_etiket.py                  # uret ve yaz
    python uret_etiket.py --tohum 12345    # farkli tohum
    python uret_etiket.py --ornek 3        # 3 ornek etiketi ekrana bas

NEDEN --dogrula ONCE
Etiket 300 belgenin cevap anahtari. Kota tutmuyorsa (bir kusurdan 3 ornek
cikmissa) uretime devam etmenin anlami yok; once plan duzeltilir.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

BURASI = Path(__file__).resolve().parent
DEPO_KOKU = BURASI.parent.parent
sys.path.insert(0, str(DEPO_KOKU))

from src.etiket_uretici import EtiketUretici, Veri, siparis_listesi_kur  # noqa: E402
from src.varlik_havuzu import VarlikHavuzu  # noqa: E402

HEDEF = BURASI / "etiketler"


def dogrula(etiketler: list[dict], kota: dict) -> list[str]:
    """Uretilen etiketler kotayi tutturuyor mu.

    Her boyut tek tek karsilastirilir. Bir boyut tutmuyorsa hangisi ve ne
    kadar saptigi yazilir.
    """
    hatalar = []

    def kiyas(ad: str, gercek: Counter, beklenen: dict) -> None:
        for anahtar, bek in beklenen.items():
            if str(anahtar).startswith("_"):
                continue
            ger = gercek.get(anahtar, 0)
            if ger != bek:
                hatalar.append(f"{ad}: {anahtar} = {ger}, beklenen {bek}")

    kiyas("kurum", Counter(e["alici"]["kurum_kodu"] for e in etiketler),
          kota["kurumlar"])

    tur_bek = {}
    for grup in ("_vatandas_ve_ozel", "_kurum_yazisi"):
        for t, n in kota["belge_turleri"][grup].items():
            if not t.startswith("_") and t != "toplam":
                tur_bek[t] = n
    kiyas("belge_turu", Counter(e["belge_turu"] for e in etiketler), tur_bek)

    kusur_bek = {k: v["adet"] for k, v in kota["kusurlar"]["profiller"].items()}
    kusur_bek[None] = kota["kusurlar"]["kusursuz"]
    kiyas("kusur", Counter(e["kusur"] for e in etiketler), kusur_bek)

    kiyas("pdf", Counter(e["pdf_bicimi"] for e in etiketler),
          {k: v for k, v in kota["pdf_bicimi"].items() if not k.startswith("_")})

    ilgi = sum(1 for e in etiketler if e["ilgi"])
    if ilgi != kota["ilgi"]["toplam_var"]:
        hatalar.append(f"ilgi: {ilgi}, beklenen {kota['ilgi']['toplam_var']}")
    ek = sum(1 for e in etiketler if e["ek"])
    if ek != kota["ek"]["toplam_var"]:
        hatalar.append(f"ek: {ek}, beklenen {kota['ek']['toplam_var']}")

    # --- kusur x kurum caprazi ---------------------------------------------
    asgari = kota["kusurlar"]["kurum_capraz_asgari"]
    capraz: dict[str, Counter] = {}
    for e in etiketler:
        if e["kusur"]:
            capraz.setdefault(e["kusur"], Counter())[e["alici"]["kurum_kodu"]] += 1
    for kusur, sayac in capraz.items():
        for kurum in kota["kurumlar"]:
            if sayac.get(kurum, 0) < asgari:
                hatalar.append(
                    f"capraz: {kusur} x {kurum} = {sayac.get(kurum,0)}, "
                    f"en az {asgari} olmali")

    # --- on kosullar --------------------------------------------------------
    for e in etiketler:
        k = e["kusur"]
        if k == "ilgi_kopuk" and not e["ilgi"]:
            hatalar.append(f"{e['belge_no']}: ilgi_kopuk ama ilgi yok")
        if k == "tarih_tutarsiz" and not e["ilgi"]:
            hatalar.append(f"{e['belge_no']}: tarih_tutarsiz ama ilgi yok")
        if k == "ek_beyani_yanlis" and not e["ek"]:
            hatalar.append(f"{e['belge_no']}: ek_beyani_yanlis ama ek yok")
        if k == "tarama_bozuk" and e["pdf_bicimi"] != "taranmis":
            hatalar.append(f"{e['belge_no']}: tarama_bozuk ama metin katmanli")
        if k in ("sayi_eksik", "konu_eksik", "sdp_uyumsuz", "kapanis_yanlis") \
                and e["yazan_tipi"] == "vatandas":
            hatalar.append(f"{e['belge_no']}: {k} ama vatandas belgesi")

    # --- ic tutarlilik ------------------------------------------------------
    for e in etiketler:
        if e["yazan_tipi"] == "vatandas" and e["sayi"]:
            hatalar.append(f"{e['belge_no']}: dilekcede sayi olmamali")
        if e["yazan_tipi"] == "kurum" and not e["sayi"]:
            hatalar.append(f"{e['belge_no']}: kurum yazisinda sayi olmali")
        if e["ilgi"]:
            it = e["ilgi"]["tarih"].split("."); bt = e["tarih"].split(".")
            if (it[2], it[1], it[0]) >= (bt[2], bt[1], bt[0]):
                hatalar.append(f"{e['belge_no']}: ilgi tarihi belgeden sonra")

    # --- cesitlilik ---------------------------------------------------------
    ces = kota["cesitlilik"]
    kod_say = Counter(e["sdp"]["kod"] for e in etiketler)
    asan = {k: n for k, n in kod_say.items() if n > ces["sdp_kod_basina_azami"]}
    if asan:
        hatalar.append(f"cesitlilik: SDP kod tavani asildi -> {asan}")
    birim_say = Counter(e["alici"]["birim_kodu"] for e in etiketler)
    dusuk = {b: n for b, n in birim_say.items() if n < ces["birim_basina_asgari"]}
    if dusuk:
        hatalar.append(f"cesitlilik: birim tabani altinda -> {dusuk}")
    konu_say = Counter(e["konu"] for e in etiketler)
    kasan = {k: n for k, n in konu_say.items() if n > ces["ornek_konu_azami_tekrar"]}
    if kasan:
        hatalar.append(f"cesitlilik: konu tekrari asildi -> {list(kasan)[:5]}")

    return hatalar


def ozet_bas(etiketler: list[dict], havuz: VarlikHavuzu) -> dict:
    kod_say = Counter(e["sdp"]["kod"] for e in etiketler)
    birim_say = Counter(e["alici"]["birim_kodu"] for e in etiketler)
    print("\n" + "=" * 66)
    print("DAGILIM")
    print("=" * 66)
    for ad, sayac in [
        ("kurum", Counter(e["alici"]["kurum_kodu"] for e in etiketler)),
        ("gonderen", Counter(e["gonderen"]["tip"] for e in etiketler)),
        ("kapanis", Counter(e["beklenen_kapanis"] for e in etiketler)),
        ("belge turu", Counter(e["belge_turu"] for e in etiketler)),
        ("pdf", Counter(e["pdf_bicimi"] for e in etiketler)),
    ]:
        print(f"  {ad:<12} {dict(sayac.most_common())}")
    print(f"  ilgi var     {sum(1 for e in etiketler if e['ilgi'])}")
    print(f"  ek var       {sum(1 for e in etiketler if e['ek'])}")
    print(f"\n  kusur:")
    for k, n in Counter(e["kusur"] for e in etiketler).most_common():
        print(f"    {str(k):<20} {n}")
    print(f"\n  CESITLILIK")
    print(f"    farkli SDP kodu   {len(kod_say)}  (kod basina {min(kod_say.values())}-{max(kod_say.values())})")
    print(f"    farkli birim      {len(birim_say)}  (birim basina {min(birim_say.values())}-{max(birim_say.values())})")
    print(f"    farkli konu       {len(set(e['konu'] for e in etiketler))}")
    print(f"    farkli gun        {len(set(e['tarih'] for e in etiketler))}")
    print(f"    kisi havuzu       {havuz.istatistik}")
    return {"kod": dict(kod_say), "birim": dict(birim_say)}


def main() -> int:
    a = argparse.ArgumentParser(description="ADIM 4.2 etiket uretimi")
    a.add_argument("--dogrula", action="store_true", help="uret ve kontrol et, YAZMA")
    a.add_argument("--tohum", type=int, help="kota.json'daki tohumu ez")
    a.add_argument("--ornek", type=int, default=0, help="N ornek etiketi ekrana bas")
    a.add_argument("--temizle", action="store_true", help="onceki etiketleri sil")
    ns = a.parse_args()

    veri = Veri.yukle(DEPO_KOKU)
    tohum = ns.tohum or veri.kota["tohum"]
    havuz = VarlikHavuzu(tohum)

    print(f"Tohum   : {tohum}")
    print(f"Hedef   : {veri.kota['toplam']} belge")
    print(f"SDP     : {len(veri.sdp)} kod")
    print(f"Kurum   : {', '.join(veri.kurumlar)}")

    siparisler = siparis_listesi_kur(veri.kota, havuz)
    uretici = EtiketUretici(veri, havuz)
    etiketler = [uretici.uret(i, s) for i, s in enumerate(siparisler, start=1)]

    ozet_bas(etiketler, havuz)

    print("\n" + "=" * 66)
    print("KOTA DOGRULAMA")
    print("=" * 66)
    hatalar = dogrula(etiketler, veri.kota)
    if hatalar:
        for h in hatalar[:25]:
            print(f"  !! {h}")
        if len(hatalar) > 25:
            print(f"  ... ve {len(hatalar)-25} hata daha")
        print(f"\n  TOPLAM {len(hatalar)} HATA")
    else:
        print("  Butun boyutlar kotayi tutturdu.")

    for e in etiketler[:ns.ornek]:
        print("\n" + "-" * 66)
        print(json.dumps(e, ensure_ascii=False, indent=2))

    if ns.dogrula:
        print("\n(--dogrula: dosya yazilmadi)")
        return 1 if hatalar else 0

    if hatalar:
        print("\nHATA VAR — dosya yazilmadi. Once kota.json'u duzeltin.")
        return 1

    if ns.temizle and HEDEF.exists():
        shutil.rmtree(HEDEF)
    HEDEF.mkdir(parents=True, exist_ok=True)
    for e in etiketler:
        (HEDEF / f"etiket_{e['belge_no']}.json").write_text(
            json.dumps(e, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (HEDEF / "_ozet.json").write_text(
        json.dumps({"tohum": tohum, "adet": len(etiketler)},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{len(etiketler)} etiket yazildi -> {HEDEF}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
