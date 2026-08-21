"""Ayrıştırıcı'yı 300 belgede cevap anahtarına karşı ölçer.

NEREYE:  depo kökü
NASIL:   python ayristirici_dogrula.py 50     -> hizli deneme (~2 dk)
         python ayristirici_dogrula.py        -> tamami (~18 dk, 50'si OCR)
ÇIKTI:   ayristirici_dogrula_sonuc.txt

ÜÇ BELGE AİLESİ
---------------
    kurum    T.C. başlığı + sayı/konu/ilgi + EBYS dipnotu
    şirket   antetli kâğıt, sayı ve konu VAR, T.C. ve dipnot YOK
             sayı biçimi farklı: 2026/335 (yıl/sıra), DETSİS ve SDP yok
    dilekçe  başlık yok, sayı yok, konu yok

ÖLÇÜLEMEYEN VAKALAR — ceza yazılmaz
-----------------------------------
Bir alanın belgede BULUNMADIĞI durumlarda ayrıştırıcının onu bulamaması
DOĞRU sonuçtur:

1. kusur == "sayi_eksik" olan belgelerde sayı KASTEN silinmiştir.
   Etiket doğru değeri tutar, belge boştur.

2. kusur == "sdp_uyumsuz" olan belgelerde etiket DÜZELTİLMİŞ değeri,
   belge BOZUK değeri taşır. Ayrıştırıcı belgeye sadık olmalıdır.

NOT — 2026-08-20 veri seti düzeltmesi: özel hukuk tüzel kişisi yazıları
dilekçe olarak basılıyordu, artık şirket yazısı olarak basılıyor. O 24
belgede sayı ARTIK ÖLÇÜLEBİLİR; önceki sürümdeki muafiyet kaldırıldı.

Bu ayrımı yapmamak "her enjekte edilen kusur belgeden tespit edilebilir
olmalı" ilkesinin ölçüm tarafıdır: belgeden çıkarılamayan bir etiket
geçerli bir test vakası değildir.
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK / "src"))

ARAMA_YERLERI = (
    ("deneyler", "adim4", "belgeler_pdf"),
    ("veri", "belgeler"),
    ("ornek", "okuma_ornegi"),
)

ALANLAR = ("sayi", "tarih", "konu", "ilgi", "ek", "muhatap", "imza")


def klasor_bul() -> Path:
    for p in ARAMA_YERLERI:
        y = KOK.joinpath(*p)
        if y.exists() and any(y.glob("belge_*.pdf")):
            return y
    for b in KOK.rglob("belge_*.pdf"):
        return b.parent
    sys.exit("belge_*.pdf bulunamadi.")


def etiket_klasoru(pdf_klasoru: Path) -> Path:
    for a in (pdf_klasoru, pdf_klasoru.parent / "etiketler", pdf_klasoru.parent):
        if a.exists() and any(a.glob("etiket_*.json")):
            return a
    for b in KOK.rglob("etiket_*.json"):
        return b.parent
    sys.exit("etiket_*.json bulunamadi.")


def beklentiler(e: dict) -> dict[str, object | None]:
    """Her alan için beklenen değer; None ise o belge o alandan ölçülmez."""
    tip = (e.get("gonderen") or {}).get("tip")
    # Sayı ve konu satırı olan iki aile: kurum ve şirket.
    # Dilekçede ikisi de yok (belge_sablonu.json vatandas_dilekcesi).
    basliкli = tip in ("kurum", "ozel_tuzel_kisi")
    kusur = e.get("kusur")
    sayi = e.get("sayi")

    if kusur in ("sayi_eksik", "sdp_uyumsuz"):
        sayi = None                      # kasten silinmiş / kasten bozulmuş

    return {
        "sayi": sayi,
        "tarih": e.get("tarih"),
        "konu": e.get("konu") if basliкli else None,
        "ilgi": e.get("ilgi"),
        "ek": e.get("ek"),
        "muhatap": e.get("muhatap_makam"),
        "imza": True if basliкli else None,
    }


def bulunanlar(u) -> dict[str, object]:
    return {
        "sayi": u.sayi,
        "tarih": u.tarih.strftime("%d.%m.%Y") if u.tarih else None,
        "konu": u.konu,
        "ilgi": u.ilgi[0] if u.ilgi else None,
        "ek": u.ekler,
        "muhatap": u.muhatap.ham,
        "imza": u.imza.ad,
    }


def dogru_mu(alan: str, bulunan, beklenen) -> bool:
    if alan == "ilgi":
        return bool(bulunan) and bulunan.sayi == beklenen.get("sayi")
    if alan == "ek":
        return len(bulunan) == beklenen.get("adet")
    if alan == "muhatap":
        from metin import katla
        return bool(bulunan) and katla(beklenen) in katla(bulunan)
    if alan == "imza":
        return bool(bulunan)
    return bulunan == beklenen


def main(argv: list[str]) -> int:
    from ayristirici import ayristir
    from okuyucu import oku

    sinir = next((int(a) for a in argv if a.isdigit()), None)
    klasor = klasor_bul()
    ek = etiket_klasoru(klasor)
    pdfler = sorted(klasor.glob("belge_*.pdf"))
    if sinir:
        pdfler = pdfler[:sinir]

    cikti = KOK / "ayristirici_dogrula_sonuc.txt"
    with cikti.open("w", encoding="utf-8") as f:
        def yaz(s: str = "") -> None:
            print(s)
            f.write(s + "\n")

        yaz(f"klasor: {klasor}   belge: {len(pdfler)}\n")

        dogru = Counter()
        olculen = Counter()
        atlanan = Counter()
        hatalar: dict[str, list[tuple[str, str, str]]] = {a: [] for a in ALANLAR}
        kanitsiz: list[str] = []
        aile_sayaci = Counter()
        aile_yanlis: list[str] = []
        okuma_hatasi: list[str] = []
        t0 = time.perf_counter()

        for i, pdf in enumerate(pdfler, 1):
            no = pdf.stem.replace("belge_", "")
            ey = ek / f"etiket_{no}.json"
            if not ey.exists():
                continue
            e = json.loads(ey.read_text(encoding="utf-8"))

            r = oku(str(pdf))
            if r.hata or not r.ayrilmis:
                okuma_hatasi.append(f"{no}: {r.hata}")
                continue

            a = ayristir(r.ayrilmis.govde_satirlari)
            bek = beklentiler(e)
            bul = bulunanlar(a.ustveri)

            aile_sayaci[a.aile] += 1
            beklenen_aile = {"kurum": "kurum", "ozel_tuzel_kisi": "sirket"}.get(
                (e.get("gonderen") or {}).get("tip"), "dilekce"
            )
            if a.aile != beklenen_aile and len(aile_yanlis) < 10:
                aile_yanlis.append(f"{no}: {beklenen_aile} beklenirken {a.aile}")

            for alan in ALANLAR:
                if bek[alan] is None:
                    atlanan[alan] += 1
                    continue
                olculen[alan] += 1
                if dogru_mu(alan, bul[alan], bek[alan]):
                    dogru[alan] += 1
                elif len(hatalar[alan]) < 8:
                    hatalar[alan].append(
                        (no, str(bek[alan])[:38], str(bul[alan])[:38])
                    )

            # Bulunan her alanın kanıtı olmalı — arayüz vurgulaması buna bağlı
            for anahtar, deger in (("ustveri.sayi", a.ustveri.sayi),
                                   ("ustveri.tarih", a.ustveri.tarih),
                                   ("ustveri.konu", a.ustveri.konu)):
                if deger is not None and anahtar not in a.kanit:
                    kanitsiz.append(f"{no}:{anahtar}")

            if i % 25 == 0:
                print(f"    ... {i}/{len(pdfler)}", flush=True)

        gecen = time.perf_counter() - t0

        yaz("=" * 70)
        yaz("ALAN BAZINDA ISABET")
        yaz("=" * 70)
        yaz(f"{'alan':10s} {'dogru':>7s} {'olculen':>8s} {'oran':>7s} {'atlanan':>8s}")
        yaz("-" * 46)
        for alan in ALANLAR:
            o = olculen[alan]
            oran = f"{dogru[alan] / o:.0%}" if o else "—"
            yaz(f"{alan:10s} {dogru[alan]:7d} {o:8d} {oran:>7s} {atlanan[alan]:8d}")

        yaz("\nBELGE AILESI")
        for k, v in aile_sayaci.most_common():
            yaz(f"  {k:12s} {v:4d}")
        if aile_yanlis:
            yaz(f"  ✗ {len(aile_yanlis)} yanlis tespit:")
            for x in aile_yanlis:
                yaz(f"      {x}")
        else:
            yaz("  ✓ tum belgelerde aile dogru tespit edildi")

        yaz("\nHATALAR  (beklenen -> bulunan)")
        for alan in ALANLAR:
            if not hatalar[alan]:
                continue
            yaz(f"\n  {alan}")
            for no, bek, bul in hatalar[alan]:
                yaz(f"    {no}: {bek}")
                yaz(f"         -> {bul}")

        yaz(f"\nKANITSIZ ALAN: {len(kanitsiz)}  {', '.join(kanitsiz[:10]) or '—'}")
        if okuma_hatasi:
            yaz(f"\nOKUMA HATASI: {len(okuma_hatasi)}")
            for x in okuma_hatasi[:8]:
                yaz(f"    {x}")

        yaz(f"\nsure: {gecen:.0f} sn")
        yaz("\natlanan = o belgede alan yok veya kasten bozulmus; olculmez.")
        yaz(f"\nTam cikti: {cikti}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
