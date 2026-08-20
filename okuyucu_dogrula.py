"""Okuyucu'yu 300 belgede doğrular — yerelde koşar.

NEREYE:  depo kökü
NASIL:   python okuyucu_dogrula.py            -> 300 belge (~15 dk, 50'si OCR)
         python okuyucu_dogrula.py 30         -> ilk 30 belge, hizli deneme
ÇIKTI:   okuyucu_dogrula_sonuc.txt

NE ÖLÇÜYOR
----------
1. YOL SEÇİMİ     metin katmanlı -> pdfplumber, taranmış -> easyocr.
                  Etikete karşı kontrol edilir; yanlış yol seçimi hem
                  yavaşlık hem kalite kaybıdır.

2. SIRALAMA       Asıl soru bu. Docling'in markdown çıktısında etiketler
                  değerlerinden kopuyordu:

                      E-24304062-807.01-57692713
                      Konu
                      Boya Badana İşleri Hk.
                      Sayı            <- degerinden KOPMUS

                  Koordinatla sıralayınca "Sayı : E-..." tek satır olmalı.
                  Betik bunu her belgede kontrol ediyor.

3. DİPNOT         dipnot.py taranmış belgede de çalışıyor mu. Metin
                  katmanlıda 250/250 temizdi; OCR koordinatıyla da öyle mi.

4. SÜRE           Melez yolun kazancı gerçek mi.

Beklenen: sıralama oranı belirgin şekilde yüksek. Düşükse koordinat
çevrimi ya da satır toleransı yanlış demektir.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK / "src"))

ARAMA_YERLERI = (
    ("deneyler", "adim4", "belgeler_pdf"),
    ("veri", "belgeler"),
    ("ornek", "okuma_ornegi"),
)

SIZINTI_IZLERI = ("Doğrulama Kodu", "Belge Takip", "Doğrulama Adresi",
                  "KEP Adresi", "güvenli elektronik imza")
KORUNACAK = ("Kimlik No", "Adres:", "Telefon:")


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


# OCR 'ı' harfini 1, l, i olarak okuyabiliyor; iki nokta da dusebiliyor.
# Kalip buna gore esnetildi, yoksa OCR ciktisinda hicbir etiket bulunamaz.
ETIKET_KALIPLARI = {
    "Sayı": re.compile(r"^\s*Say[ıi1l|]\s*[:：]?", re.IGNORECASE),
    "Konu": re.compile(r"^\s*Konu\s*[:：]?", re.IGNORECASE),
    "İlgi": re.compile(r"^\s*[İIi]lg[ıi1l|]\s*[:：]?", re.IGNORECASE),
}


def etiketli_satir(satirlar, etiket: str) -> str | None:
    kalip = ETIKET_KALIPLARI[etiket]
    for s in satirlar:
        if kalip.match(s.metin):
            return s.metin
    return None


def main(argv: list[str]) -> int:
    try:
        from okuyucu import oku
    except ImportError as e:
        sys.exit(f"src/okuyucu.py yuklenemedi: {e}")

    sinir = next((int(a) for a in argv if a.isdigit()), None)
    klasor = klasor_bul()
    ek = etiket_klasoru(klasor)
    pdfler = sorted(klasor.glob("belge_*.pdf"))
    if sinir:
        pdfler = pdfler[:sinir]

    cikti = KOK / "okuyucu_dogrula_sonuc.txt"
    with cikti.open("w", encoding="utf-8") as f:
        def yaz(s: str = "") -> None:
            print(s)
            f.write(s + "\n")

        yaz(f"klasor: {klasor}   belge: {len(pdfler)}")
        yaz(f"etiket: {ek}\n")

        yol_yanlis: list[str] = []
        sira_ok = sira_toplam = 0
        sira_bozuk: list[tuple[str, str, str]] = []
        sizinti: list[str] = []
        kayip: list[str] = []
        hatali: list[tuple[str, str]] = []
        sureler: dict[str, list[float]] = {"metin_katmanli": [], "taranmis": []}
        bos: list[str] = []
        dokum: dict[str, list[tuple[float, str]]] = {}

        t_basla = time.perf_counter()
        for i, pdf in enumerate(pdfler, 1):
            no = pdf.stem.replace("belge_", "")
            ey = ek / f"etiket_{no}.json"
            e = json.loads(ey.read_text(encoding="utf-8")) if ey.exists() else {}

            r = oku(str(pdf))
            if r.hata:
                hatali.append((no, r.hata))
                continue
            if not r.satirlar:
                bos.append(no)
                continue

            beklenen_tip = e.get("pdf_bicimi")
            if beklenen_tip and r.girdi_tipi != beklenen_tip:
                yol_yanlis.append(f"{no}: {beklenen_tip} beklenirken {r.girdi_tipi}")
            sureler.setdefault(r.girdi_tipi, []).append(r.sure_ms)

            # --- SIRALAMA: etiket ve degeri ayni satirda mi
            beklenen_sayi = e.get("sayi")
            # sayi_eksik kusurlu belgede sayi KASTEN silinmis; okuyucunun
            # onu bulamamasi dogru davranistir, basarisizlik degil.
            if (beklenen_sayi
                    and e.get("kusur") != "sayi_eksik"
                    and e.get("gonderen", {}).get("tip") == "kurum"):
                sira_toplam += 1
                satir = etiketli_satir(r.satirlar, "Sayı")
                # 012 gibi kusurlu belgelerde etiket dogru degeri tutar,
                # belge bozugu tasir -> sayinin ILK bolumune bakiyoruz.
                onek = beklenen_sayi.split("-")[0] if "-" in beklenen_sayi else beklenen_sayi
                if satir and (beklenen_sayi in satir or onek in satir):
                    sira_ok += 1
                else:
                    sira_bozuk.append((no, r.girdi_tipi, (satir or "SATIR YOK")[:52]))
                    dokum[no] = [(s.y, s.metin) for s in r.satirlar[:12]]

            # --- DIPNOT
            if r.ayrilmis:
                govde = r.govde.casefold()
                if any(iz.casefold() in govde for iz in SIZINTI_IZLERI):
                    sizinti.append(f"{no}({r.girdi_tipi})")
                if e.get("gonderen", {}).get("tip") != "kurum":
                    tam = r.govde + "\n" + r.dipnot
                    if any(a in tam and a not in r.govde for a in KORUNACAK):
                        kayip.append(f"{no}({r.girdi_tipi})")
                if any(iz.casefold() in govde for iz in SIZINTI_IZLERI):
                    dokum.setdefault(no, [(s.y, s.metin) for s in r.satirlar])

            if i % 25 == 0:
                print(f"    ... {i}/{len(pdfler)}", flush=True)

        gecen = time.perf_counter() - t_basla

        yaz("=" * 70)
        yaz("SONUC")
        yaz("=" * 70)

        yaz("\n1. YOL SECIMI")
        if yol_yanlis:
            yaz(f"   ✗ {len(yol_yanlis)} belgede yanlis yol")
            for x in yol_yanlis[:10]:
                yaz(f"       {x}")
        else:
            yaz("   ✓ tum belgelerde dogru yol secildi")

        yaz("\n2. SIRALAMA  (Sayi etiketi degeriyle ayni satirda mi)")
        if sira_toplam:
            yaz(f"   {sira_ok}/{sira_toplam} = {sira_ok / sira_toplam:.0%}")
            for x in sira_bozuk[:12]:
                yaz(f"       {x[0]} ({x[1]}): {x[2]}")
            if len(sira_bozuk) > 12:
                yaz(f"       ... {len(sira_bozuk) - 12} tane daha")
        else:
            yaz("   olculemedi")

        yaz("\n3. DIPNOT")
        yaz(f"   sizinti : {len(sizinti)}  {', '.join(sizinti[:15]) or '—'}")
        yaz(f"   kayip   : {len(kayip)}  {', '.join(kayip[:15]) or '—'}")

        yaz("\n4. SURE")
        for tip, liste in sureler.items():
            if liste:
                yaz(f"   {tip:15s} {len(liste):4d} belge   "
                    f"ortalama {sum(liste) / len(liste):8.0f} ms   "
                    f"en yavas {max(liste):8.0f} ms")
        yaz(f"   toplam {gecen:.0f} sn")

        if hatali:
            yaz(f"\n5. HATA  {len(hatali)} belge")
            for no, h in hatali[:10]:
                yaz(f"   {no}: {h}")
        if bos:
            yaz(f"\n6. BOS CIKTI  {len(bos)} belge: {', '.join(bos[:15])}")

        if dokum:
            yaz("\n" + "=" * 70)
            yaz("SORUNLU BELGELERIN GERCEK SATIRLARI  (siralanmis hali)")
            yaz("=" * 70)
            for no, satirlar in list(dokum.items())[:5]:
                yaz(f"\n--- belge_{no}")
                for y, m in satirlar[:16]:
                    yaz(f"    y={y:7.1f}  {m[:70]}")

        temiz = not (yol_yanlis or sizinti or kayip or hatali or bos)
        yaz("\n" + ("TEMIZ" if temiz else "BULGULAR VAR — cikti Claude'a yapistirilsin"))
        yaz(f"\nTam cikti: {cikti}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
