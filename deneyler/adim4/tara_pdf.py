#!/usr/bin/env python3
"""ADIM 5b — taranmış belgeleri simüle eder.

    belgeler_pdf/belge_NNN.pdf          (metin katmanlı)
              |
        tara_pdf.py
              |
    belgeler_pdf/belge_NNN.pdf          (GÖRÜNTÜ, metin katmanı YOK)

NE YAPIYOR
Kotada 50 belge `pdf_bicimi: taranmis`. Gerçek hayatta kurumlara kâğıt
evrak da geliyor: vatandaş dilekçe yazar, elden verir, memur tarar.
Tarayıcıdan çıkan PDF GÖRÜNTÜDÜR — içinde metin yoktur, sistem OCR
yapmak zorundadır.

    250 belge   metin katmanlı    -> DOKUNULMAZ
     50 belge   taranmış          -> görüntüye çevrilir
       10  tarama_bozuk           -> eğrilik + gürültü + kontrast + düşük dpi
       40  temiz tarama           -> düz, net, 300 dpi

TEMİZ TARAMA KUSUR DEĞİLDİR
40 belgenin 13'ünde BAŞKA bir kusur var (sayi_eksik, konu_eksik gibi).
Onlara tarama bozukluğu UYGULANMAZ. Sebep: sistem sayıyı bulamadığında
sebebi ayırt edemeyiz —

    (a) sayı gerçekten silinmiş     <- ölçmek istediğimiz
    (b) OCR okuyamadı               <- ölçmediğimiz

Düz ve net tararsak belirsizlik kalkar: OCR okur, sayı yoksa gerçekten
yoktur.

BOZULMA ŞİDDETİ: ORTA
Hafif olsa kusur ölçülemez; ağır olsa OCR hiç çalışmaz ve sistemin suçu
olmayan hatalar çıkar. Hedef: karakterlerin %5-10'u yanlış okunacak ama
alanlar bulunabilir kalacak.

KULLANIM

    python tara_pdf.py --kuru         # ne yapilacagini goster, YAZMA
    python tara_pdf.py --belge 018    # tek belge
    python tara_pdf.py --yedek        # once metin katmanli halini yedekle
    python tara_pdf.py                # 50 belge
"""

from __future__ import annotations

import argparse
import io
import json
import random
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

# `import fitz` eski API; PyMuPDF 1.25+ uyarı veriyor ve gelecekte
# kaldırılacak. `pymupdf` doğru ad, eski sürümlerde çalışması için
# yedekli import.
try:
    import pymupdf as fitz
except ImportError:
    import fitz
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

BURASI = Path(__file__).resolve().parent
ETIKETLER = BURASI / "etiketler"
PDFLER = BURASI / "belgeler_pdf"

# Bu adımda işlenen kusur.
BU_KUSUR = "tarama_bozuk"

# =============================================================================
# TARAMA AYARLARI
# =============================================================================
# Temiz tarama: iyi bir ofis tarayıcısının varsayılanı.
TEMIZ_DPI = 300

# Bozuk tarama: hızlı tarama ayarı, eğri konmuş kâğıt, tozlu cam.
BOZUK_DPI = 150

# Eğrilik derecesi. Gerçekte 5 derece de olur ama o zaman OCR tamamen
# çöker; biz zorlaştırıyoruz, imkânsızlaştırmıyoruz.
EGRILIK_ARALIGI = (0.6, 2.0)

# Kontrast çarpanı. 1.0 = değişiklik yok. Soluk baskı / eski toner.
KONTRAST_ARALIGI = (0.62, 0.78)

# Sayfaya serpilen benek sayısı (toz, tarayıcı camı lekesi).
BENEK_ARALIGI = (140, 340)

# Hafif bulanıklık: düşük dpi taramada kenarlar yumuşar.
BULANIKLIK = 0.6


def _bozulma_uygula(gorsel: Image.Image, tohum: int) -> Image.Image:
    """Taranmış belgeye ORTA şiddette bozulma uygular.

    Sıra önemli: önce döndürme (kenar boşluğu oluşur), sonra gürültü,
    en son kontrast ve bulanıklık — gerçek bir taramada da bozulmalar
    bu sırayla birikir.
    """
    rng = random.Random(tohum)
    g = gorsel.convert("L")             # gri tonlama — tarayıcı çıktısı gibi

    # 1) EĞRİLİK — kâğıt tarayıcıya düz konmamış
    aci = rng.uniform(*EGRILIK_ARALIGI) * rng.choice((1, -1))
    g = g.rotate(aci, resample=Image.BICUBIC, expand=False, fillcolor=248)

    # 2) GÜRÜLTÜ — toz ve leke
    ciz = ImageDraw.Draw(g)
    gen, yuk = g.size
    for _ in range(rng.randint(*BENEK_ARALIGI)):
        x, y = rng.randrange(gen), rng.randrange(yuk)
        r = rng.choice((0, 0, 0, 1, 1, 2))          # çoğu tek piksel
        ton = rng.randint(40, 150)
        ciz.ellipse((x - r, y - r, x + r, y + r), fill=ton)

    # 3) KENAR GÖLGESİ — tarayıcı kapağı tam kapanmamış
    # Bir kenarda hafif koyulaşma; gerçek taramalarda çok yaygın.
    kenar = rng.choice(("sol", "sag", "ust"))
    kalinlik = rng.randint(6, 16)
    if kenar == "sol":
        ciz.rectangle((0, 0, kalinlik, yuk), fill=rng.randint(150, 200))
    elif kenar == "sag":
        ciz.rectangle((gen - kalinlik, 0, gen, yuk),
                      fill=rng.randint(150, 200))
    else:
        ciz.rectangle((0, 0, gen, kalinlik), fill=rng.randint(150, 200))

    # 4) KONTRAST — soluk baskı
    g = ImageEnhance.Contrast(g).enhance(rng.uniform(*KONTRAST_ARALIGI))

    # 5) BULANIKLIK — düşük çözünürlük etkisi
    g = g.filter(ImageFilter.GaussianBlur(BULANIKLIK))
    return g


def _temiz_tara(gorsel: Image.Image) -> Image.Image:
    """Düz ve net tarama. Yalnızca gri tonlamaya çevirir.

    Metin katmanı gider ama görüntü kalitesi yüksek kalır — OCR rahat
    okur. Bozulma UYGULANMAZ.
    """
    return gorsel.convert("L")


def gorsele_cevir(pdf_yolu: Path, dpi: int) -> Image.Image:
    """PDF'in ilk sayfasını görüntüye çevirir."""
    belge = fitz.open(str(pdf_yolu))
    sayfa = belge[0]
    pix = sayfa.get_pixmap(dpi=dpi)
    gorsel = Image.open(io.BytesIO(pix.tobytes("png")))
    belge.close()
    return gorsel


def gorseli_pdf_yap(gorsel: Image.Image, hedef: Path, dpi: int) -> None:
    """Görüntüyü tek sayfalık PDF'e gömer.

    Sonuç PDF'te METİN KATMANI YOKTUR — Docling OCR yapmak zorunda kalır.
    Sayfa boyutu A4 olarak korunur; dpi bilgisi görüntüye yazılır.
    """
    tampon = io.BytesIO()
    gorsel.save(tampon, format="JPEG", quality=82, dpi=(dpi, dpi))
    tampon.seek(0)

    belge = fitz.open()
    # A4 punto cinsinden: 595 x 842
    sayfa = belge.new_page(width=595, height=842)
    sayfa.insert_image(fitz.Rect(0, 0, 595, 842), stream=tampon.read())
    belge.save(str(hedef), garbage=4, deflate=True)
    belge.close()


def main() -> int:
    a = argparse.ArgumentParser(description="ADIM 5b tarama simulasyonu")
    a.add_argument("--kuru", action="store_true", help="goster, YAZMA")
    a.add_argument("--belge", nargs="+", metavar="NO")
    a.add_argument("--yedek", action="store_true",
                   help="metin katmanli halini yedekle")
    ns = a.parse_args()

    if not PDFLER.exists():
        raise SystemExit(f"HATA: {PDFLER} yok. Once bas_pdf.py calistirin.")

    hedefler = []
    for y in sorted(ETIKETLER.glob("etiket_*.json")):
        e = json.loads(y.read_text(encoding="utf-8"))
        if e.get("pdf_bicimi") != "taranmis":
            continue
        if ns.belge and e["belge_no"] not in {n.zfill(3) for n in ns.belge}:
            continue
        hedefler.append(e)

    bozuk = [e for e in hedefler if e.get("kusur") == BU_KUSUR]
    temiz = [e for e in hedefler if e.get("kusur") != BU_KUSUR]

    print(f"Taranacak : {len(hedefler)} belge")
    print(f"  bozuk   : {len(bozuk)}  (egrilik + gurultu + kontrast + "
          f"{BOZUK_DPI} dpi)")
    print(f"  temiz   : {len(temiz)}  (duz, net, {TEMIZ_DPI} dpi)")
    baska = Counter(e.get("kusur") for e in temiz if e.get("kusur"))
    if baska:
        print(f"  temiz taramada BASKA kusur tasiyanlar: {dict(baska)}")
        print("    (bunlara tarama bozuklugu UYGULANMAZ)")

    if ns.yedek and not ns.kuru:
        damga = datetime.now().strftime("%Y%m%d_%H%M")
        yedek = BURASI / f"belgeler_pdf_metinli_{damga}"
        yedek.mkdir(exist_ok=True)
        for e in hedefler:
            kaynak = PDFLER / f"belge_{e['belge_no']}.pdf"
            if kaynak.exists():
                shutil.copy2(kaynak, yedek / kaynak.name)
        print(f"Yedek     : {yedek.name} ({len(hedefler)} dosya)")

    if ns.kuru:
        print("\n(--kuru: dosya yazilmadi)")
        return 0

    sayac, atlanan = Counter(), []
    for e in hedefler:
        no = e["belge_no"]
        yol = PDFLER / f"belge_{no}.pdf"
        if not yol.exists():
            atlanan.append((no, "PDF bulunamadi"))
            continue

        if e.get("kusur") == BU_KUSUR:
            gorsel = _bozulma_uygula(gorsele_cevir(yol, BOZUK_DPI), int(no))
            dpi = BOZUK_DPI
            sayac["bozuk tarama"] += 1
        else:
            gorsel = _temiz_tara(gorsele_cevir(yol, TEMIZ_DPI))
            dpi = TEMIZ_DPI
            sayac["temiz tarama"] += 1

        gorseli_pdf_yap(gorsel, yol, dpi)

    print("\n" + "=" * 66)
    print(f"SONUÇ: {sum(sayac.values())} belge taranmış hâle getirildi")
    print("=" * 66)
    for k, n in sayac.most_common():
        print(f"  {k:<18} {n}")
    if atlanan:
        print(f"\n  ATLANAN {len(atlanan)}:")
        for no, sebep in atlanan:
            print(f"    belge_{no}  {sebep}")

    print("\nSIRADAKI: python denetle_tarama.py")
    return 1 if atlanan else 0


if __name__ == "__main__":
    raise SystemExit(main())
