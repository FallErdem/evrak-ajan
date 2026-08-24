"""Tek belgede Yazar'ı uçtan uca koşturur ve taslağı ekrana basar.

NEREYE:  araclar/
NASIL:   python araclar\\yazar_dene.py 048
         python araclar\\yazar_dene.py 048 --anlamasiz    tek LLM çağrısı
         python araclar\\yazar_dene.py 048 031 025

KREDİ UYARISI
-------------
Varsayılan olarak İKİ LLM çağrısı yapılır: önce Anlama (belge türü, talep,
özet), sonra Yazar (taslak). Üslup döngüsü her belgede EN FAZLA 2 tur koşar; ihlal bulunursa ikinci bir
Yazar çağrısı daha yapılır. Yani belge başına en çok 3 çağrı (Anlama + 2 tur).

`--anlamasiz` verilirse Anlama atlanır ve
yalnızca Yazar koşar — istemdeki "Belge türü / Talep / Özet" satırları boş
gider. Taslağın kalitesi düşer ama tek çağrıyla ne çıktığı görülür.

Ölçüm değil, GÖZLE BAKMA aracıdır. Sayı üretmez; çıktının resmî yazıya
benzeyip benzemediğine insan karar verir. Ölçüm 2c bittikten sonra ayrı
bir betikle yapılacak.
"""

from __future__ import annotations

import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "src"))

ARAMA_YERLERI = (
    ("deneyler", "adim4", "belgeler_pdf"),
    ("veri", "belgeler"),
    ("ornek",),
)

YAPILANDIRMA_ADAYLARI = (
    "yapilandirma.qwen.json",
    "yapilandirma_qwen.json",
    "yapilandirma.json",
)


def klasor_bul() -> Path:
    for p in ARAMA_YERLERI:
        y = KOK.joinpath(*p)
        if y.exists() and any(y.glob("belge_*.pdf")):
            return y
    for b in KOK.rglob("belge_*.pdf"):
        return b.parent
    sys.exit("belge_*.pdf bulunamadi.")


def yapilandirma_bul() -> Path:
    for ad in YAPILANDIRMA_ADAYLARI:
        y = KOK / ad
        if y.exists():
            return y
    sys.exit(f"Yapilandirma bulunamadi. Aranan: {YAPILANDIRMA_ADAYLARI}")


def main() -> int:
    from anlama import anla
    from ayristirici import ayristir
    from llm_istemci import istemci_olustur
    from okuyucu import oku
    from veri_yapisi import Dosya
    from kural_motoru import KuralMotoru
    from yazar import yaz

    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    anlamasiz = "--anlamasiz" in sys.argv
    if not argv:
        argv = ["048"]

    klasor = klasor_bul()
    yap = yapilandirma_bul()
    istemci = istemci_olustur(yap)
    motor = KuralMotoru()   # bir kez kurulur, her belgede yeniden okunmaz
    print(f"yapilandirma: {yap.name}   klasor: {klasor}")
    print(f"Anlama {'ATLANIYOR' if anlamasiz else 'kosacak'}; "
          f"belge basina {1 if anlamasiz else 2} LLM cagrisi\n")

    for no in argv:
        pdf = klasor / f"belge_{no}.pdf"
        if not pdf.exists():
            print(f"belge_{no}: PDF yok ({pdf})")
            continue

        r = oku(pdf)
        if r.hata or not r.satirlar:
            print(f"belge_{no}: okunamadi ({r.hata})")
            continue
        a = ayristir(r.satirlar,
                     r.ayrilmis.dipnot_bulundu if r.ayrilmis else None)

        d = Dosya()
        d.ustveri = a.ustveri
        d.metin = r.govde

        if not anlamasiz:
            an = anla(r.govde, a, istemci)
            d.siniflandirma = an.siniflandirma
            d.icerik = an.icerik
            if an.uyarilar:
                print(f"  [Anlama uyarisi] {an.uyarilar}")

        s = yaz(d, istemci, motor)
        isk = s.iskelet
        uyarilar = s.uyarilar

        c = d.cikti_yazi
        print("=" * 72)
        print(f"belge_{no}")
        print("=" * 72)
        print(f"  biz        : {isk.kimlik.kod}  (oran {isk.kimlik.oran:.2f}, "
              f"{isk.kimlik.kaynak})")
        print(f"  yon        : {c.hiyerarsi_yonu}  ->  {isk.yon.kapanis}"
              f"   [{isk.yon.hat}]")
        print(f"  tur        : {c.tur}")
        print(f"  gerekce    : {c.tur_gerekcesi}")
        print(f"  DONGU      : {s.ozet}")
        print(f"               tur {s.tur_sayisi} · ilk bulgular "
              f"{[b.kural_id for b in s.ilk_bulgular]} · kalan "
              f"{[b.kural_id for b in s.son_bulgular]}")
        lr = c.linter_raporu
        print(f"  linter     : {lr.denetlenen_kural_sayisi} kural denetlendi, "
              f"{lr.atlanan_kural_sayisi} atlandi, {len(lr.bulgular)} bulgu")
        print(f"  insan onayi: {s.insan_onayi_gerek}  {isk.sebepler}")
        print(f"  durum      : {d.durum}")
        if uyarilar:
            print(f"  UYARI      : {uyarilar}")
        print()
        print("-" * 72)
        print(c.baslik or "(baslik yok)")
        print()
        print("Sayı  :")            # EBYS atar
        print("Konu  : " + (c.konu or "—"))
        print()
        print((c.muhatap or "—"))
        print()
        print(c.metin or "(metin uretilmedi)")
        print()
        print(" " * 40 + "[ad EBYS'den]")
        print(" " * 40 + (c.imza_unvan or "—"))
        print("-" * 72)
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
