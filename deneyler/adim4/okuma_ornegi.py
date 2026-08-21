#!/usr/bin/env python3
"""ADIM 1 (Parça 3) — okuyucu testi için örneklem seçer.

    python okuma_ornegi.py           # listeyi bas
    python okuma_ornegi.py --kopyala # okuma_ornegi/ klasörüne kopyala

NE SEÇİYOR VE NEDEN

Okuyucunun zorlanacağı yerler belli. Rastgele 15 PDF bunların çoğunu
kaçırır; bu seçim her zorluğu garanti eder:

    metin katmanlı, kurum yazısı   temel durum
    metin katmanlı, DİLEKÇE        DÜZEN FARKLI — başlık bloğu yok,
                                   alt blok İKİ SÜTUN (solda kimlik,
                                   sağda tarih/imza). Docling sütunları
                                   karıştırabilir.
    metin katmanlı, DAĞITIMLI      "Dağıtım: / Gereği: / Bilgi:" listesi
    metin katmanlı, EKLİ           "Ek: 3 adet" + numaralı liste
    metin katmanlı, UZUN           çok paragraf, sayfa dolu
    temiz tarama                   OCR gerekiyor ama net
    BOZUK tarama                   OCR sınırı: eğri, gürültülü, 150 dpi

Ayrıca her belgede DİPNOT var: ayırıcı çizgi, 8 punto iletişim bilgisi,
QR kod. Docling bunu gövde metniyle karıştırmamalı — okuyucunun ilk
sınavı bu.
"""

from __future__ import annotations

import argparse
import glob
import json
import shutil
from pathlib import Path

BURASI = Path(__file__).resolve().parent
ETIKETLER = BURASI / "etiketler"
PDFLER = BURASI / "belgeler_pdf"
HEDEF = BURASI / "okuma_ornegi"


def sec() -> list[tuple[str, str]]:
    E = [json.loads(Path(f).read_text(encoding="utf-8"))
         for f in sorted(glob.glob(str(ETIKETLER / "etiket_*.json")))]
    secim: dict[str, str] = {}

    def ekle(kosul, gerekce, adet=1):
        n = 0
        for e in E:
            if n >= adet:
                break
            if e["belge_no"] in secim:
                continue
            try:
                if kosul(e):
                    secim[e["belge_no"]] = gerekce
                    n += 1
            except (KeyError, TypeError):
                continue

    metinli = lambda e: e.get("pdf_bicimi") == "metin_katmanli"

    # --- metin katmanlı: yapısal çeşitlilik -------------------------------
    ekle(lambda e: metinli(e) and e["yazan_tipi"] == "kurum"
         and not e.get("kusur") and not e.get("ek")
         and not e.get("dagitim"),
         "metin katmanlı · sade kurum yazısı", 2)

    ekle(lambda e: metinli(e) and e["yazan_tipi"] in ("vatandas", "ogrenci"),
         "metin katmanlı · DİLEKÇE (iki sütunlu alt blok)", 2)

    ekle(lambda e: metinli(e) and e.get("dagitim"),
         "metin katmanlı · DAĞITIMLI (Gereği/Bilgi listesi)", 2)

    ekle(lambda e: metinli(e) and e.get("ek")
         and (e["ek"].get("adet") or 1) > 1,
         "metin katmanlı · ÇOK EKLİ (numaralı liste)", 1)

    ekle(lambda e: metinli(e) and e.get("ek"),
         "metin katmanlı · TEK EKLİ", 1)

    ekle(lambda e: metinli(e) and sum(e["paragraf_cumle_sayilari"]) >= 9,
         "metin katmanlı · UZUN (sayfa dolu)", 1)

    ekle(lambda e: metinli(e) and e["yazan_tipi"] == "ozel_tuzel",
         "metin katmanlı · şirket yazısı", 1)

    # --- taranmış ---------------------------------------------------------
    ekle(lambda e: e.get("pdf_bicimi") == "taranmis"
         and e.get("kusur") != "tarama_bozuk" and not e.get("kusur"),
         "TEMİZ TARAMA · OCR gerekli, net", 3)

    ekle(lambda e: e.get("kusur") == "tarama_bozuk",
         "BOZUK TARAMA · OCR sınırı", 3)

    D = {e["belge_no"]: e for e in E}
    return [(no, f"{g}  [{D[no]['aile']}]") for no, g in sorted(secim.items())]


def main() -> int:
    a = argparse.ArgumentParser()
    a.add_argument("--kopyala", action="store_true")
    ns = a.parse_args()

    secim = sec()
    print(f"{len(secim)} belge\n")
    for no, gerekce in secim:
        print(f"  belge_{no}.pdf   {gerekce}")

    if ns.kopyala:
        if HEDEF.exists():
            shutil.rmtree(HEDEF)
        HEDEF.mkdir()
        for no, _ in secim:
            kaynak = PDFLER / f"belge_{no}.pdf"
            if kaynak.exists():
                shutil.copy2(kaynak, HEDEF / kaynak.name)
        # Etiketleri de koy — okuyucunun çıktısı bunlarla karşılaştırılacak
        for no, _ in secim:
            e = ETIKETLER / f"etiket_{no}.json"
            if e.exists():
                shutil.copy2(e, HEDEF / e.name)
        print(f"\nKopyalandi -> {HEDEF}")
        print("PDF'ler ve ETİKETLERİ birlikte. Etiketler cevap anahtarı;")
        print("okuyucunun çıkardığı metin bunlarla karşılaştırılacak.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
