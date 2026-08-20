"""OCR çıktısını cevap anahtarıyla yan yana döker — gözle bakmak için.

NEREYE:  depo kökü
NASIL:   python ocr_karsilastir.py                 -> 4 ilginç belge
         python ocr_karsilastir.py 017 007 001     -> seçtiğiniz belgeler
ÇIKTI:   ocr_karsilastir_sonuc.txt  (tam metin, konsol kesse de durur)

NEDEN
-----
ocr_kalitesi.py rakam veriyor: "terim %68". Ama HANGİ kelimenin NEYE
dönüştüğünü göstermiyor. Bu betik ham metni döküyor ki gözle bakılabilsin.

İKİNCİ İŞİ — ölçülecek bir soru var
------------------------------------
Kaybolan şey çoğunlukla Türkçe işaretli harfler: Değişikliği -> Degisikligi.
Bunu düzeltmenin iki yolu var:

  A) METNİ ONARMAK   OCR çıktısını LLM'e verip "düzelt" demek.
                     TEHLİKELİ: model olmayan kelime uydurabilir. Resmî
                     evrakta uydurma, kayıptan beterdir.

  B) ARAMAYI ESNETMEK  Metne dokunmamak, ama karşılaştırırken Türkçe
                     işaretleri iki tarafta da düşürmek.
                     Değişikliği ve Degisikligi aynı sayılır.

B seçeneği hiçbir şey uydurmaz. Ama işe yarıyor mu? Betik her terimi İKİ
KEZ arıyor — ham hâliyle ve işaretler düşürülmüş hâliyle — ve iki oranı
yan yana basıyor. Fark büyükse B yeterli demektir, LLM onarımına gerek yok.
"""

from __future__ import annotations

import logging
import os
import unicodedata
import warnings

warnings.filterwarnings("ignore")
os.environ.setdefault("PYTHONWARNINGS", "ignore")
for _ad in ("docling", "RapidOCR", "rapidocr", "easyocr", "torch", "PIL"):
    logging.getLogger(_ad).setLevel(logging.ERROR)

import json  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from difflib import SequenceMatcher  # noqa: E402
from pathlib import Path  # noqa: E402

KOK = Path(__file__).resolve().parent

ARAMA_YERLERI = (
    ("deneyler", "adim4", "belgeler_pdf"),
    ("veri", "belgeler"),
    ("ornek", "okuma_ornegi"),
)

# Varsayılan örneklem: her biri farklı bir zorluğu temsil ediyor.
VARSAYILAN = ["017", "007", "001", "035"]

# Türkçe işaretli harf -> sade karşılığı.
# 'İ' ve 'ı' özel: Python'un casefold'u bunları doğru çevirmiyor.
KATLAMA = str.maketrans({
    "İ": "i", "I": "i", "ı": "i",
    "Ş": "s", "ş": "s", "Ğ": "g", "ğ": "g",
    "Ç": "c", "ç": "c", "Ö": "o", "ö": "o", "Ü": "u", "ü": "u",
    "Â": "a", "â": "a", "Î": "i", "î": "i", "Û": "u", "û": "u",
})


def sadelestir(m: str) -> str:
    return re.sub(r"\s+", " ", m or "").strip()


def katla(m: str) -> str:
    """Türkçe işaretleri düşürür. Metni DEĞİŞTİRMEZ, yalnızca karşılaştırma için."""
    m = (m or "").translate(KATLAMA).lower()
    m = unicodedata.normalize("NFD", m)
    return "".join(k for k in m if not unicodedata.combining(k))


def en_iyi_parca(aranan: str, metin: str) -> tuple[float, str]:
    """Aranan ifadeye en çok benzeyen metin parçasını ve oranını döndürür.

    Asıl değeri burada: kelimenin NEYE dönüştüğünü gösteriyor.
    """
    aranan = sadelestir(aranan)
    metin = sadelestir(metin)
    if not aranan or not metin:
        return 0.0, ""
    n = len(aranan)
    if metin.find(aranan) >= 0:
        return 1.0, aranan
    adim = max(1, n // 6)
    en_iyi, parca = 0.0, ""
    for i in range(0, max(1, len(metin) - n + 1), adim):
        p = metin[i:i + n + adim]
        oran = SequenceMatcher(None, aranan, p).ratio()
        if oran > en_iyi:
            en_iyi, parca = oran, p
    return en_iyi, parca


def klasor_bul() -> Path:
    for parcalar in ARAMA_YERLERI:
        y = KOK.joinpath(*parcalar)
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


def easyocr_donusturucu():
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import EasyOcrOptions, PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    ayar = PdfPipelineOptions()
    ayar.do_ocr = True
    ayar.ocr_options = EasyOcrOptions(lang=["tr"])
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=ayar)}
    )


def belgeyi_dok(no: str, pdf: Path, etiket: dict, metin: str, sure: float,
                yaz) -> tuple[int, int, int]:
    """Tek belgeyi döker. (terim_sayisi, ham_bulunan, katlanmis_bulunan) döner."""
    yaz("=" * 78)
    yaz(f"belge_{no}   {etiket.get('belge_turu')}   "
        f"{etiket.get('pdf_bicimi')}   kusur={etiket.get('kusur')}   {sure:.1f}s")
    yaz("=" * 78)

    yaz("\n--- CEVAP ANAHTARI ---")
    yaz(f"  konu        : {etiket.get('konu')}")
    yaz(f"  sayi        : {etiket.get('sayi')}")
    yaz(f"  tarih       : {etiket.get('tarih')}")
    sdp = etiket.get("sdp") or {}
    yaz(f"  sdp         : {sdp.get('kod')}  {sdp.get('ad')}")
    yaz(f"  hedef birim : {(etiket.get('alici') or {}).get('birim_adi')}")
    muh = " ".join(x for x in (etiket.get("muhatap_makam"),
                               etiket.get("muhatap_parantez")) if x)
    yaz(f"  muhatap     : {muh}")

    yaz("\n--- OCR CIKTISI (ham, oldugu gibi) ---")
    for satir in (metin or "").splitlines():
        if satir.strip():
            yaz(f"  | {satir}")

    yaz("\n--- ALAN KONTROLU ---")
    for ad, beklenen in (("sayi", etiket.get("sayi")),
                         ("tarih", etiket.get("tarih")),
                         ("sdp kodu", sdp.get("kod") if etiket.get("sayi") else None)):
        if not beklenen:
            yaz(f"  {ad:10s} : — (bu belgede yok)")
            continue
        yaz(f"  {ad:10s} : {'✓ bulundu' if beklenen in metin else '✗ BULUNAMADI'}"
            f"   beklenen: {beklenen}")

    yaz("\n--- ANAHTAR TERIMLER: ham arama ve isaretler dusurulmus arama ---")
    terimler = etiket.get("anahtar_terimler") or []
    ham_b = kat_b = 0
    for t in terimler:
        h_oran, h_parca = en_iyi_parca(t, metin)
        k_oran, _ = en_iyi_parca(katla(t), katla(metin))
        h_var, k_var = h_oran >= 0.75, k_oran >= 0.75
        ham_b += h_var
        kat_b += k_var
        yaz(f"  aranan     : {t}")
        yaz(f"  metinde    : {h_parca or '(benzer parca yok)'}")
        yaz(f"  ham        : {h_oran:.0%} {'✓' if h_var else '✗'}"
            f"      katlanmis : {k_oran:.0%} {'✓' if k_var else '✗'}"
            f"{'   <-- KATLAMA KURTARDI' if k_var and not h_var else ''}")
        yaz("")

    # Birimin adı muhatap satırında geçiyor mu — yönlendirmenin 2. şeridi
    birim_adi = (etiket.get("alici") or {}).get("birim_adi")
    if birim_adi:
        b_oran, b_parca = en_iyi_parca(katla(birim_adi), katla(metin))
        yaz("--- YONLENDIRME 2. SERIDI: birim adi metinde geciyor mu ---")
        yaz(f"  aranan  : {birim_adi}")
        yaz(f"  metinde : {b_parca or '(yok)'}")
        yaz(f"  benzerlik: {b_oran:.0%} {'✓' if b_oran >= 0.75 else '✗'}")
    yaz("")
    return len(terimler), ham_b, kat_b


def main(argv: list[str]) -> int:
    numaralar = [a for a in argv if a.isdigit()] or VARSAYILAN
    klasor = klasor_bul()
    ek = etiket_klasoru(klasor)

    try:
        donusturucu = easyocr_donusturucu()
    except ImportError as e:
        sys.exit(f'easyocr kurulu degil: {e}\n  pip install "docling[easyocr]"')

    cikti = KOK / "ocr_karsilastir_sonuc.txt"
    toplam = ham_top = kat_top = 0

    with cikti.open("w", encoding="utf-8") as f:
        def yaz(s: str = "") -> None:
            print(s)
            f.write(s + "\n")

        yaz(f"OCR: docling + easyocr(tr)   klasor: {klasor}")
        yaz(f"belgeler: {', '.join(numaralar)}\n")

        for no in numaralar:
            pdf = klasor / f"belge_{no}.pdf"
            ey = ek / f"etiket_{no}.json"
            if not pdf.exists() or not ey.exists():
                yaz(f"belge_{no}: dosya bulunamadi, atlandi\n")
                continue
            etiket = json.loads(ey.read_text(encoding="utf-8"))
            t0 = time.perf_counter()
            try:
                metin = donusturucu.convert(str(pdf)).document.export_to_markdown()
            except Exception as e:  # noqa: BLE001
                yaz(f"belge_{no}: HATA {type(e).__name__}: {e}\n")
                continue
            t, h, k = belgeyi_dok(no, pdf, etiket, metin, time.perf_counter() - t0, yaz)
            toplam += t
            ham_top += h
            kat_top += k

        yaz("=" * 78)
        yaz("TOPLAM")
        yaz("=" * 78)
        if toplam:
            yaz(f"  terim, ham arama        : {ham_top}/{toplam} = {ham_top / toplam:.0%}")
            yaz(f"  terim, isaretler dusuk  : {kat_top}/{toplam} = {kat_top / toplam:.0%}")
            fark = kat_top - ham_top
            yaz(f"  katlamanin kurtardigi   : {fark} terim")
            yaz("")
            if fark > 0:
                yaz("  -> Kayip agirlikli olarak TURKCE ISARETLERDE.")
                yaz("     Arama esnetmek yeterli; LLM ile metin onarimina gerek yok.")
            else:
                yaz("  -> Kayip isaretlerde DEGIL, harflerin kendisinde.")
                yaz("     Arama esnetmek yetmiyor; baska bir yol gerekiyor.")
        yaz(f"\nTam cikti: {cikti}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
