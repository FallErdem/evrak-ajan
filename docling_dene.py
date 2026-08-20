"""Docling yerel deneme betiği — Erdem'in makinesinde koşacak.

Amaç: 300 PDF'i okumadan önce Docling'in bu veri setinde ne yaptığını görmek.
Özellikle 50 taranmış belgede OCR'ın kurulup kurulmadığını.

Kurulum:
    pip install docling

Kullanım:
    python docling_dene.py ornek_klasoru

Ölçtükleri:
  1. Metin katmanlı PDF'te süre ve karakter sayısı
  2. Taranmış PDF'te OCR çalışıyor mu, hangi motor
  3. Dipnot gövdeye karışıyor mu
  4. Türkçe karakterler bozuluyor mu (İ, ı, ş, ğ, Î)
"""
import sys, time, json
from pathlib import Path

try:
    from docling.document_converter import DocumentConverter
except ImportError:
    sys.exit("docling kurulu degil:  pip install docling")

DIPNOT_IZLERI = ("Doğrulama Kodu", "KEP Adresi", "güvenli elektronik imza")
TURKCE = "İışğçöüŞĞÇÖÜÎ"

def klasor_bul(verilen: str | None) -> Path:
    """PDF klasorunu bulur. Nereden calistirildigindan bagimsiz."""
    adaylar = []
    if verilen:
        adaylar.append(Path(verilen))
    burasi = Path(__file__).resolve().parent
    for kok in (Path.cwd(), burasi, burasi.parent, burasi.parent.parent):
        adaylar += [kok, kok / "ornek" / "okuma_ornegi", kok / "veri" / "belgeler"]

    for a in adaylar:
        if a.exists() and any(a.glob("belge_*.pdf")):
            return a
    # son care: yukaridan asagi tarama
    for kok in (Path.cwd(), burasi.parent, burasi.parent.parent):
        if not kok.exists():
            continue
        for bulunan in kok.rglob("belge_*.pdf"):
            return bulunan.parent
    sys.exit(
        "belge_*.pdf bulunamadi.\n"
        "Klasoru acikca verin, ornek:\n"
        r"    python docling_dene.py C:\Users\iremy\evrak-ajan\ornek\okuma_ornegi"
    )


def main(klasor: str | None) -> None:
    yol = klasor_bul(klasor)
    pdfler = sorted(yol.glob("belge_*.pdf"))
    print(f"klasor: {yol}  ({len(pdfler)} PDF)\n")

    donusturucu = DocumentConverter()
    print(f"{'belge':8s} {'bicim':16s} {'sure':>7s} {'karakter':>9s}  notlar")
    print("-" * 74)

    for pdf in pdfler:
        no = pdf.stem[6:9]
        etiket = yol / f"etiket_{no}.json"
        bicim = "?"
        if etiket.exists():
            bicim = json.loads(etiket.read_text(encoding="utf-8"))["pdf_bicimi"]

        t0 = time.perf_counter()
        try:
            sonuc = donusturucu.convert(str(pdf))
            metin = sonuc.document.export_to_markdown()
        except Exception as e:
            print(f"{no:8s} {bicim:16s} {'—':>7s} {'—':>9s}  HATA: {type(e).__name__}: {e}")
            continue
        sure = time.perf_counter() - t0

        notlar = []
        if not metin.strip():
            notlar.append("BOS CIKTI (OCR calismadi mi?)")
        if any(iz in metin for iz in DIPNOT_IZLERI):
            notlar.append("dipnot govdeye karisti")
        if not any(k in metin for k in TURKCE):
            notlar.append("Turkce karakter yok — kodlama sorunu olabilir")

        print(f"{no:8s} {bicim:16s} {sure:6.1f}s {len(metin):9d}  {' · '.join(notlar) or 'temiz'}")

    print("-" * 74)
    print("Taranmis belgelerde 'BOS CIKTI' varsa OCR kurulmamis demektir:")
    print("    pip install rapidocr-onnxruntime")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
