#!/usr/bin/env python3
"""ADIM 4.4c — üretilen gövde metinlerini etiketlerine karşı denetler.

    govdeler/govde_NNN.txt  +  etiketler/etiket_NNN.json
                     |
                src/linter.py
                     |
              rapor + çeşitlilik ölçümü

KULLANIM

    python denetle_govde.py              # mevcut butun govdeleri
    python denetle_govde.py --parti 1    # yalnizca 1. parti (001-020)
    python denetle_govde.py --belge 011  # tek belge, ayrintili
    python denetle_govde.py --sessiz     # yalnizca ozet

NE KONTROL EDER

Linter'in 12 kurali: kapanis ifadesi ve yonu, sahsilestirme, kurum adi
sizmasi, sartname bilgilerinin metne girmesi, ek ve ilgi atfi, metin
tamligi, paragraf/cumle sayilari, yasak bicimler.

Ayrica CESITLILIK olcer: kac farkli ilk cumle, kac cumle tekrarlanmis,
uzunluk dagilimi. Toplu uretimde model kendi onceki metinlerini gorup
onlara benzetiyor; bu olcum onu yakalar.

LINTER'IN SINIRI
Dilbilgisi ve anlam hatalarini yakalayamaz. "Uygulamali okul yonetimlerine
duyurulmasi" gibi bir bozukluk buradan temiz gecer. Uc katmanli savunmanin
ilk katmani: linter (bedava) -> LLM denetcisi -> insan ornekleme.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

BURASI = Path(__file__).resolve().parent
DEPO_KOKU = BURASI.parent.parent
sys.path.insert(0, str(DEPO_KOKU))

from src.linter import Etiket, denetle  # noqa: E402

GOVDELER = BURASI / "govdeler"
ETIKETLER = BURASI / "etiketler"
PARTI_BOYU = 20


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


def cesitlilik(metinler: dict[str, str]) -> None:
    """Toplu üretimin ana riski: model kendi önceki metinlerine benzetiyor."""
    G = list(metinler.values())
    if not G:
        return
    print("\n" + "=" * 66)
    print("ÇEŞİTLİLİK")
    print("=" * 66)

    ilk = [g.split(".")[0].strip() for g in G]
    print(f"  farklı ilk cümle  : {len(set(ilk))}/{len(G)}")

    ilk3 = Counter(" ".join(g.split()[:3]) for g in G)
    print(f"  farklı ilk 3 kelime: {len(ilk3)}")
    for k, n in ilk3.most_common(3):
        if n > 1:
            print(f"      {n}x  \"{k}...\"")

    cumleler = []
    for g in G:
        cumleler += [c.strip().lower()
                     for c in re.split(r"(?<=[.!?])\s+", g)
                     if len(c.strip()) > 25]
    tekrar = [(k, n) for k, n in Counter(cumleler).items() if n > 1]
    oran = sum(n for _, n in tekrar) / max(1, len(cumleler))
    print(f"  aynı cümle 2+ kez : {len(tekrar)} / {len(cumleler)} cümle "
          f"(%{oran*100:.0f})")
    for k, n in sorted(tekrar, key=lambda x: -x[1])[:4]:
        print(f"      {n}x  \"{k[:56]}\"")

    uz = [len(re.findall(r"[.!?]", g)) for g in G]
    kel = [len(g.split()) for g in G]
    print(f"  cümle sayısı      : {min(uz)}-{max(uz)}  "
          f"(ortalama {sum(uz)/len(uz):.1f})")
    print(f"  kelime sayısı     : {min(kel)}-{max(kel)} "
          f"(ortalama {sum(kel)/len(kel):.0f})")

    # EŞİK %10 DEĞİL %30. İlk sürümde %10 yazmıştım ama bu bir ölçüme
    # dayanmıyordu, tahmindi. Resmî yazışma tanımı gereği kalıplıdır: bir
    # bakanlığın kırk genelgesinde "bağlı tüm birimler uygulamaya tabidir"
    # cümlesi kırk kez geçer. Kaçınmak gerçekçiliği bozar.
    #
    # Şartname 6.5'in ölçtüğü çeşitlilik konu, kurum, belge türü ve senaryo
    # çeşitliliğidir — kapanış kalıbının kaç kez tekrarlandığı değil. Asıl
    # bakılacak satır "farklı ilk cümle": aynı kalıpla başlayan belgeler
    # gerçekten tekdüzeliktir.
    if oran > 0.30:
        print("\n  ! Cümle tekrarı %30'un üzerinde — kalıp cümlelerin ötesinde")
        print("    bir tekdüzelik var. Tekrarlayan cümlelere bakın: kapanış")
        print("    ve kapsam kalıpları normaldir, ama gövde cümleleri")
        print("    tekrarlıyorsa parti boyunu düşürün.")
    elif len(set(ilk)) < len(G) * 0.9:
        print("\n  ! Farklı ilk cümle oranı düşük. Model belgeleri aynı")
        print("    kalıpla açıyor — çeşitlilik açısından asıl sorun budur.")


def main() -> int:
    a = argparse.ArgumentParser(description="ADIM 4.4c govde denetimi")
    a.add_argument("--parti", type=int, help="yalnizca bu parti (1 = 001-020)")
    a.add_argument("--belge", nargs="+", metavar="NO", help="belirli belgeler")
    a.add_argument("--sessiz", action="store_true", help="yalnizca ozet")
    ns = a.parse_args()

    yollar = sorted(GOVDELER.glob("govde_*.txt"))
    if not yollar:
        raise SystemExit(f"HATA: {GOVDELER} icinde govde yok. "
                         f"Once parti_ayristir.py calistirin.")

    if ns.belge:
        istenen = {n.zfill(3) for n in ns.belge}
        yollar = [y for y in yollar if y.stem.split("_")[-1] in istenen]
    elif ns.parti:
        alt = (ns.parti - 1) * PARTI_BOYU + 1
        ust = ns.parti * PARTI_BOYU
        yollar = [y for y in yollar
                  if alt <= int(y.stem.split("_")[-1]) <= ust]

    temiz, hatali, sorunlu = 0, 0, []
    kural_sayaci: Counter = Counter()
    metinler: dict[str, str] = {}

    for y in yollar:
        no = y.stem.split("_")[-1]
        ey = ETIKETLER / f"etiket_{no}.json"
        if not ey.exists():
            print(f"belge_{no}  !! etiket bulunamadi")
            continue
        metin = y.read_text(encoding="utf-8")
        metinler[no] = metin.strip()
        r = denetle(metin, etiket_kur(json.loads(ey.read_text(encoding="utf-8"))))

        if r.hatalar:
            hatali += 1
            sorunlu.append(no)
            for b in r.hatalar:
                kural_sayaci[b.kural] += 1
            if not ns.sessiz:
                print(f"\nbelge_{no}  {len(r.hatalar)} hata")
                for b in r.hatalar:
                    print(f"   x {b.kural:<9} {b.mesaj}")
                    if b.kanit:
                        print(f"     kanıt: {str(b.kanit)[:70]}")
        else:
            temiz += 1
            if ns.belge and not ns.sessiz:
                print(f"belge_{no}  temiz")

    print("\n" + "=" * 66)
    print(f"SONUÇ: temiz {temiz} | hatalı {hatali}   (toplam {temiz+hatali})")
    print("=" * 66)
    if kural_sayaci:
        print("  kurala göre:")
        for k, n in kural_sayaci.most_common():
            print(f"    {k:<10} {n}")
        print(f"\n  Hatalı belgeler: {', '.join(sorunlu)}")
        print("\n  Ne yapılır: ilgili partiyi açtığınız sohbete dönüp yalnızca")
        print("  bu numaraları tekrar isteyin, gelen metni ilgili")
        print("  govdeler/govde_NNN.txt dosyasının üzerine yazın.")

    cesitlilik(metinler)
    return 1 if hatali else 0


if __name__ == "__main__":
    raise SystemExit(main())
