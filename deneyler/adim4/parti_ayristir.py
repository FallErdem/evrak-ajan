#!/usr/bin/env python3
"""ADIM 4.4b — sohbetten kopyalanan parti cevabını tek tek dosyalara böler.

    cevaplar/cevap_01.txt  ->  govdeler/govde_001.txt ... govde_020.txt

NEDEN BETİK, ELLE DEĞİL
Toplu çıktı tek blok gelir. Elle bölerseniz BİR BELGE ATLANDIĞINDA bütün
numaralandırma kayar ve etiketlerle eşleşme sessizce bozulur. 300 belgenin
ölçümü çöper, üstelik fark edilmez.

Bu betik şunları kontrol eder:
  - Kaç blok geldi, beklenen kadar mı
  - Numaralar partide beklenen numaralarla eşleşiyor mu
  - Eksik veya fazla numara var mı
  - Boş veya çok kısa gövde var mı
  - Model ayraç biçimini bozmuş mu

Bunlardan biri tutmuyorsa DOSYA YAZMAZ ve ne olduğunu söyler.

KULLANIM

    python parti_ayristir.py 01           # cevap_01.txt'yi ayristir
    python parti_ayristir.py 01 --kuru    # kontrol et, YAZMA
    python parti_ayristir.py --hepsi      # mevcut butun cevaplari
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BURASI = Path(__file__).resolve().parent
DEPO_KOKU = BURASI.parent.parent
sys.path.insert(0, str(DEPO_KOKU))

from src.sartname_render import etiket_yukle  # noqa: E402

ETIKETLER = BURASI / "etiketler"
PARTILER = BURASI / "partiler"
CEVAPLAR = BURASI / "cevaplar"
HEDEF = BURASI / "govdeler"

# Model bazen "### BELGE 001", bazen "###BELGE 001", bazen "### Belge 001"
# yazıyor. Ayraç tanıma esnek, numara tanıma katı.
AYRAC = re.compile(r"^#{2,4}\s*BELGE\s*(\d{1,3})\s*$", re.IGNORECASE | re.MULTILINE)

ASGARI_UZUNLUK = 80   # bundan kısa gövde muhtemelen kesilmiş


def parti_numaralari(parti_no: str) -> list[str]:
    """Bu partide hangi belge numaraları bekleniyor.

    Ayrı bir `.numaralar` dosyasından okunuyor. Parti metninden regex ile
    çıkarmak, başlıktaki biçim açıklamasını da yakalıyordu; etiket
    klasöründen yeniden hesaplamak ise parti boyutu değişmişse yanlış
    sonuç verir.
    """
    yol = PARTILER / f"parti_{parti_no}.numaralar"
    if not yol.exists():
        raise SystemExit(f"HATA: {yol} yok. Once parti_hazirla.py calistirin.")
    return yol.read_text(encoding="utf-8").split()


def ayristir(parti_no: str, kuru: bool) -> tuple[int, list[str], list[str]]:
    cevap_yolu = CEVAPLAR / f"cevap_{parti_no}.txt"
    if not cevap_yolu.exists():
        raise SystemExit(
            f"HATA: {cevap_yolu} yok.\n"
            f"Sohbetten gelen cevabin TAMAMINI bu dosyaya yapistirin.")

    beklenen = parti_numaralari(parti_no)
    ham = cevap_yolu.read_text(encoding="utf-8")

    # Ayraçlara göre böl
    parcalar = AYRAC.split(ham)
    # split sonucu: [onsoz, no1, govde1, no2, govde2, ...]
    if len(parcalar) < 3:
        return 0, ["Hicbir '### BELGE NNN' ayraci bulunamadi.",
                   "Model bicimi bozmus olabilir; cevabin ilk satirlarina bakin."], []

    onsoz = parcalar[0].strip()
    bulunan: dict[str, str] = {}
    for i in range(1, len(parcalar) - 1, 2):
        no = parcalar[i].zfill(3)
        govde = parcalar[i + 1].strip()
        if no in bulunan:
            return 0, [f"Belge {no} iki kez gecmis."], []
        bulunan[no] = govde

    # Hatalar üretimi DURDURUR, uyarılar yalnızca bildirilir. Modelin
    # kısa bir önsöz yazması belgeyi bozmuyor — ayrıştırıcı onu zaten
    # atıyor. Ama tekrarlıyorsa isteme bir madde eklemek gerekebilir.
    hatalar, uyarilar = [], []
    if onsoz and len(onsoz) > 20:
        uyarilar.append(f"Ilk ayractan once {len(onsoz)} karakterlik metin "
                        f"vardi, atildi: {onsoz[:50]!r}")

    eksik = [n for n in beklenen if n not in bulunan]
    fazla = [n for n in bulunan if n not in beklenen]
    if eksik:
        hatalar.append(f"EKSIK belge: {eksik}")
    if fazla:
        hatalar.append(f"FAZLA/YANLIS numara: {fazla}")

    if list(bulunan) != [n for n in beklenen if n in bulunan]:
        hatalar.append("Belgelerin SIRASI sartnamelerdeki sirayla ayni degil.")

    kisa = [n for n, g in bulunan.items() if len(g) < ASGARI_UZUNLUK]
    if kisa:
        hatalar.append(f"COK KISA govde (kesilmis olabilir): {kisa}")

    bos = [n for n, g in bulunan.items() if not g]
    if bos:
        hatalar.append(f"BOS govde: {bos}")

    if hatalar:
        return 0, hatalar, uyarilar

    if kuru:
        return len(bulunan), [], uyarilar

    HEDEF.mkdir(parents=True, exist_ok=True)
    for no, govde in bulunan.items():
        (HEDEF / f"govde_{no}.txt").write_text(govde + "\n", encoding="utf-8")
    return len(bulunan), [], uyarilar


def main() -> int:
    a = argparse.ArgumentParser(description="ADIM 4.4b parti ayristirma")
    a.add_argument("parti", nargs="?", help="parti numarasi, or. 01")
    a.add_argument("--hepsi", action="store_true", help="butun cevaplari ayristir")
    a.add_argument("--kuru", action="store_true", help="kontrol et, YAZMA")
    ns = a.parse_args()

    if ns.hepsi:
        numaralar = sorted(p.stem.split("_")[-1] for p in CEVAPLAR.glob("cevap_*.txt"))
        if not numaralar:
            raise SystemExit(f"HATA: {CEVAPLAR} icinde cevap dosyasi yok.")
    elif ns.parti:
        numaralar = [ns.parti.zfill(2)]
    else:
        raise SystemExit("Parti numarasi verin veya --hepsi kullanin.")

    toplam, sorunlu = 0, []
    for no in numaralar:
        adet, hatalar, uyarilar = ayristir(no, ns.kuru)
        for u in uyarilar:
            print(f"parti_{no}  ! {u}")
        if hatalar:
            print(f"parti_{no}  !! AYRISTIRILAMADI")
            for h in hatalar:
                print(f"     {h}")
            sorunlu.append(no)
        else:
            durum = "kontrol edildi" if ns.kuru else "yazildi"
            print(f"parti_{no}  {adet} govde {durum}")
            toplam += adet

    print(f"\nToplam {toplam} govde. Sorunlu parti: {sorunlu or 'yok'}")
    if sorunlu:
        print("\nSorunlu partide ne yapilir:")
        print("  - Cevabin TAMAMINI kopyaladiginizdan emin olun")
        print("  - Model bicimi bozduysa sohbette 'ayraclari duzelt' deyin")
        print("  - Eksik belge varsa yalnizca onlari tekrar isteyin")
        return 1
    if not ns.kuru and toplam:
        print(f"\nSIRADAKI: python denetle_govde.py   (linter kontrolu)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
