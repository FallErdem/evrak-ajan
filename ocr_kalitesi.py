"""OCR kalite ölçümü — motorları cevap anahtarına karşı karşılaştırır.

NEREYE:  depo kökü (dipnot_dogrula.py ile aynı yer)
NASIL:   python ocr_kalitesi.py              -> 8 belge, tüm motorlar (~10 dk)
         python ocr_kalitesi.py 50           -> 50 belge, uyarı verir
         python ocr_kalitesi.py 8 easyocr    -> tek motor

NEDEN
-----
docling_sonda.py taranmış belgede ciddi bozulma gösterdi. Temiz taramada,
300 dpi:

    gerçek   "...Boya Badana İşleri kapsamında tutanak tutulmuştur"
    OCR      "by da b b  b bda   bdn tutulmuştur"
    gerçek   "Sayı : E-24304062-..."
    OCR      "Say1 : E-24304062-..."

Sebep muhtemelen dil ayarı: Docling dil kodlarını "latin" model setine
eşliyor, çünkü Çince model kelime aralarını düşürüyor. Bizim koşumuzda
dil HİÇ ayarlanmamıştı, yani Çince model kullanıldı.

Bu betik üç şeyi karşılaştırır:
    rapidocr_tr   aynı motor, ama lang=["tr"]  -> bedava düzeltme mi?
    easyocr       Türkçe destekli (80+ dil listesinde tr var)
    tesseract     tur dil paketi, sistem kurulumu gerektirir

ÖLÇÜT — cevap anahtarına karşı, tahmin yok
------------------------------------------
    sayi        birebir eşleşme (rakam, dile bağlı değil)
    tarih       birebir eşleşme
    sdp         sayının 3. bölümünden okunuyor
    terim       etiketteki anahtar_terimler metinde bulunuyor mu (bulanık)
    turkce      İ ı ş ğ ç ö ü karakterleri korunmuş mu
    dipnot      dipnot.py'nin aradığı iz tanınıyor mu

Hangi motorun seçileceği bu tablodan çıkacak, hissiyattan değil.
"""

from __future__ import annotations

import logging
import os
import warnings

# Torch ve RapidOCR uyari seli ciktiyi okunamaz hale getiriyordu. Uyarilar
# bilgi tasimiyor (pin_memory, quantize_per_tensor) ama olcum tablosunu
# bogduklari icin susturuluyorlar.
warnings.filterwarnings("ignore")
os.environ.setdefault("PYTHONWARNINGS", "ignore")
for _ad in ("docling", "RapidOCR", "rapidocr", "easyocr", "torch", "PIL"):
    logging.getLogger(_ad).setLevel(logging.ERROR)

import json
import re
import sys
import time
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

KOK = Path(__file__).resolve().parent

ARAMA_YERLERI = (
    ("deneyler", "adim4", "belgeler_pdf"),
    ("veri", "belgeler"),
    ("ornek", "okuma_ornegi"),
)

VARSAYILAN_ORNEK = 8
UYARI_ESIGI = 12          # bunun üstünde onay ister

TURKCE_HARFLER = "İıŞşĞğÇçÖöÜüÂâÎî"
DIPNOT_IZLERI = ("güvenli elektronik imza", "doğrulama kodu",
                 "belge takip", "doğrulama adresi", "kep adresi")


# =============================================================================
# Motorlar
# =============================================================================

def motor_rapidocr_tr():
    """Mevcut motor, ama dil ayarlı. En ucuz ihtimal."""
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    ayar = PdfPipelineOptions()
    ayar.do_ocr = True
    ayar.ocr_options = RapidOcrOptions(lang=["tr"])
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=ayar)}
    )


def motor_easyocr():
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import EasyOcrOptions, PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    ayar = PdfPipelineOptions()
    ayar.do_ocr = True
    ayar.ocr_options = EasyOcrOptions(lang=["tr"])
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=ayar)}
    )


def motor_tesseract():
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TesseractCliOcrOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    ayar = PdfPipelineOptions()
    ayar.do_ocr = True
    ayar.ocr_options = TesseractCliOcrOptions(lang=["tur"])
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=ayar)}
    )


def motor_varsayilan():
    """Hiçbir ayar yapılmamış hâli — şu anki durumumuz, karşılaştırma tabanı."""
    from docling.document_converter import DocumentConverter

    return DocumentConverter()


MOTORLAR = {
    "varsayilan": motor_varsayilan,
    "rapidocr_tr": motor_rapidocr_tr,
    "easyocr": motor_easyocr,
    "tesseract": motor_tesseract,
}


# =============================================================================
# Ölçüm
# =============================================================================

def sadelestir(metin: str) -> str:
    """Boşlukları toparlar, karşılaştırma için."""
    return re.sub(r"\s+", " ", metin or "").strip()


def bulanik_var_mi(aranan: str, metin: str, esik: float = 0.75) -> bool:
    """Aranan ifade metinde yaklaşık olarak geçiyor mu.

    OCR harf hatası yaptığı için birebir arama haksızlık olur. Kayan
    pencereyle en iyi benzerliğe bakılır.
    """
    aranan = sadelestir(aranan).casefold()
    metin = sadelestir(metin).casefold()
    if not aranan:
        return False
    if aranan in metin:
        return True
    n = len(aranan)
    if len(metin) < n:
        return SequenceMatcher(None, aranan, metin).ratio() >= esik
    adim = max(1, n // 4)
    en_iyi = 0.0
    for i in range(0, len(metin) - n + 1, adim):
        oran = SequenceMatcher(None, aranan, metin[i:i + n + adim]).ratio()
        if oran > en_iyi:
            en_iyi = oran
        if en_iyi >= esik:
            return True
    return en_iyi >= esik


def turkce_orani(metin: str) -> float:
    """Türkçe harflerin, olması gereken yerlerde korunma oranı.

    Doğrudan ölçemeyiz (gerçek metin elimizde yok), ama vekil bir ölçüt var:
    Türkçe bir metinde bu harfler yaklaşık %4-7 sıklıkta geçer. Sıfıra
    yakınsa motor onları başka harfe çevirmiş demektir.
    """
    if not metin:
        return 0.0
    sayac = sum(1 for k in metin if k in TURKCE_HARFLER)
    harfler = sum(1 for k in metin if unicodedata.category(k).startswith("L"))
    return sayac / harfler if harfler else 0.0


def etiket_metni(etiket: dict) -> str:
    """Cevap anahtarindaki gercek Turkce metni toplar.

    Belgenin tam metni elimizde yok (taranmis), ama konu, somut bilgiler ve
    anahtar terimler gercek metinden geliyor. Turkce harf orani icin
    guvenilir bir taban olusturuyorlar.
    """
    parcalar = [etiket.get("konu") or "", etiket.get("muhatap_makam") or ""]
    parcalar += [str(v) for v in (etiket.get("somut_bilgiler") or {}).values()]
    parcalar += list(etiket.get("anahtar_terimler") or [])
    return " ".join(parcalar)


def belgeyi_olc(metin: str, etiket: dict) -> dict:
    """Tek belgede tek motorun sonucunu ölçer."""
    sonuc: dict[str, object] = {}

    beklenen_sayi = etiket.get("sayi")
    sonuc["sayi"] = None if not beklenen_sayi else (
        sadelestir(beklenen_sayi) in sadelestir(metin)
    )

    beklenen_tarih = etiket.get("tarih")
    sonuc["tarih"] = None if not beklenen_tarih else (beklenen_tarih in metin)

    # SDP kodu sayinin 3. bolumunde YAZILI. Sayisi olmayan belgede
    # (vatandas dilekcesi) metinde hic gecmez -> olculemez, basarisizlik degil.
    sdp = (etiket.get("sdp") or {}).get("kod")
    sonuc["sdp"] = None if (not sdp or not beklenen_sayi) else (sdp in metin)

    terimler = etiket.get("anahtar_terimler") or []
    bulunan = sum(1 for t in terimler if bulanik_var_mi(t, metin))
    sonuc["terim_bulunan"] = bulunan
    sonuc["terim_toplam"] = len(terimler)

    # Turkce harf orani mutlak degil, BELGENIN KENDI beklenen oranina gore.
    # 300 etiketten olculen taban: ortanca %11.8, ortalama %11.7, en dusuk %4.4.
    # Sabit bir esik ("%4-7 normaldir") YANLIS olurdu; belgeden belgeye
    # degisiyor. Her belge kendi cevap anahtarindaki metne karsi olculuyor.
    beklenen = turkce_orani(etiket_metni(etiket))
    olculen = turkce_orani(metin)
    sonuc["turkce"] = olculen
    sonuc["turkce_pay"] = (olculen / beklenen) if beklenen > 0 else None

    # E-imza dipnotu yalnizca KURUM yazilarinda var. Dilekcede yok
    # (yerlesim.yaml dilekce.yapi) -> orada aranmasi anlamsiz.
    kurum_yazisi = (etiket.get("gonderen") or {}).get("tip") == "kurum"
    kucuk = metin.casefold()
    sonuc["dipnot"] = (
        any(iz in kucuk for iz in DIPNOT_IZLERI) if kurum_yazisi else None
    )

    sonuc["karakter"] = len(metin)
    return sonuc


# =============================================================================
# Örnek seçimi
# =============================================================================

def klasor_bul(verilen: str | None) -> Path:
    if verilen:
        y = Path(verilen)
        if y.exists():
            return y
    for parcalar in ARAMA_YERLERI:
        y = KOK.joinpath(*parcalar)
        if y.exists() and any(y.glob("belge_*.pdf")):
            return y
    for b in KOK.rglob("belge_*.pdf"):
        return b.parent
    sys.exit("belge_*.pdf bulunamadi.")


def etiket_klasoru(pdf_klasoru: Path) -> Path | None:
    for a in (pdf_klasoru, pdf_klasoru.parent / "etiketler", pdf_klasoru.parent):
        if a.exists() and any(a.glob("etiket_*.json")):
            return a
    for b in KOK.rglob("etiket_*.json"):
        return b.parent
    return None


def ornekleri_sec(klasor: Path, adet: int) -> list[tuple[Path, dict]]:
    """Taranmış belgelerden karışık örneklem. Bozuk taramalar dahil edilir."""
    ek = etiket_klasoru(klasor)
    if ek is None:
        sys.exit("etiket_*.json bulunamadi — cevap anahtari olmadan olcum yapilamaz")

    temizler: list[tuple[Path, dict]] = []
    bozuklar: list[tuple[Path, dict]] = []
    for pdf in sorted(klasor.glob("belge_*.pdf")):
        ey = ek / f"etiket_{pdf.stem.replace('belge_', '')}.json"
        if not ey.exists():
            continue
        e = json.loads(ey.read_text(encoding="utf-8"))
        if e.get("pdf_bicimi") != "taranmis":
            continue
        (bozuklar if e.get("kusur") == "tarama_bozuk" else temizler).append((pdf, e))

    # Bozuklar zor vaka; oranlarını gerçek dağılımın üstünde tutuyoruz ki
    # en kötü durumu görebilelim.
    bozuk_payi = max(1, adet // 3)
    secim = bozuklar[:bozuk_payi] + temizler[: adet - min(bozuk_payi, len(bozuklar))]
    return secim[:adet]


# =============================================================================
# Ana akış
# =============================================================================

def main(argv: list[str]) -> int:
    adet = VARSAYILAN_ORNEK
    istenen_motorlar = list(MOTORLAR)
    klasor_arg = None

    for a in argv:
        if a.isdigit():
            adet = int(a)
        elif a in MOTORLAR:
            istenen_motorlar = [a]
        else:
            klasor_arg = a

    klasor = klasor_bul(klasor_arg)
    ornekler = ornekleri_sec(klasor, adet)
    if not ornekler:
        sys.exit("taranmis belge bulunamadi")

    tahmin_dk = len(ornekler) * len(istenen_motorlar) * 30 / 60
    print(f"klasor   : {klasor}")
    print(f"belge    : {len(ornekler)}  ({', '.join(p.stem[-3:] for p, _ in ornekler)})")
    print(f"motor    : {', '.join(istenen_motorlar)}")
    print(f"tahmini sure: ~{tahmin_dk:.0f} dakika (CPU, ilk motorda model indirme haric)")

    if len(ornekler) > UYARI_ESIGI:
        print(f"\n! {len(ornekler)} belge x {len(istenen_motorlar)} motor UZUN SURER.")
        cevap = input("  Devam edilsin mi? (e/h): ").strip().lower()
        if cevap not in ("e", "evet", "y", "yes"):
            return 0
    print()

    tablo: dict[str, list[dict]] = {}

    for motor_adi in istenen_motorlar:
        print(f"--- {motor_adi} " + "-" * (56 - len(motor_adi)))
        try:
            donusturucu = MOTORLAR[motor_adi]()
        except ImportError as e:
            print(f"    ATLANDI — kurulu degil: {e}")
            print(f"    kurulum:  pip install \"docling[{motor_adi.split('_')[0]}]\"\n")
            continue
        except Exception as e:  # noqa: BLE001
            print(f"    ATLANDI — {type(e).__name__}: {e}\n")
            continue

        olcumler: list[dict] = []
        for pdf, etiket in ornekler:
            no = pdf.stem.replace("belge_", "")
            t0 = time.perf_counter()
            try:
                metin = donusturucu.convert(str(pdf)).document.export_to_markdown()
            except Exception as e:  # noqa: BLE001
                print(f"    {no}  HATA {type(e).__name__}: {str(e)[:50]}")
                continue
            sure = time.perf_counter() - t0
            o = belgeyi_olc(metin, etiket)
            o["no"], o["sure"] = no, sure
            o["bozuk"] = etiket.get("kusur") == "tarama_bozuk"
            olcumler.append(o)

            def im(v: object) -> str:
                return "—" if v is None else ("✓" if v else "✗")

            print(
                f"    {no}{'*' if o['bozuk'] else ' '} {sure:5.1f}s  "
                f"sayi {im(o['sayi'])}  tarih {im(o['tarih'])}  sdp {im(o['sdp'])}  "
                f"terim {o['terim_bulunan']}/{o['terim_toplam']}  "
                f"turkce {o['turkce']:.1%}"
                + (f" ({o['turkce_pay']:.0%} tabanin)" if o["turkce_pay"] else "")
                + f"  dipnot {im(o['dipnot'])}"
            )
        tablo[motor_adi] = olcumler
        print()

    # -------------------------------------------------------------------------
    if not tablo:
        print("Hicbir motor calismadi.")
        return 1

    print("=" * 74)
    print("OZET  (* = tarama_bozuk dahil)")
    print("=" * 74)
    print(f"{'motor':14s} {'sayi':>6s} {'tarih':>6s} {'sdp':>6s} "
          f"{'terim':>7s} {'turkce':>7s} {'taban%':>7s} {'dipnot':>7s} {'sure':>7s}")
    print("-" * 74)

    def _pay_ort(olcumler: list[dict]) -> str:
        paylar = [o["turkce_pay"] for o in olcumler if o.get("turkce_pay")]
        return f"{sum(paylar) / len(paylar):.0%}" if paylar else "—"

    def oran(olcumler: list[dict], anahtar: str) -> str:
        gecerli = [o for o in olcumler if o[anahtar] is not None]
        if not gecerli:
            return "—"
        return f"{sum(1 for o in gecerli if o[anahtar]) / len(gecerli):.0%}"

    for motor_adi, olcumler in tablo.items():
        if not olcumler:
            continue
        t_bulunan = sum(o["terim_bulunan"] for o in olcumler)
        t_toplam = sum(o["terim_toplam"] for o in olcumler)
        print(
            f"{motor_adi:14s} {oran(olcumler, 'sayi'):>6s} {oran(olcumler, 'tarih'):>6s} "
            f"{oran(olcumler, 'sdp'):>6s} "
            f"{(t_bulunan / t_toplam if t_toplam else 0):>6.0%} "
            f"{sum(o['turkce'] for o in olcumler) / len(olcumler):>7.1%} "
            f"{_pay_ort(olcumler):>7s} "
            f"{oran(olcumler, 'dipnot'):>7s} "
            f"{sum(o['sure'] for o in olcumler) / len(olcumler):>6.1f}s"
        )

    print("-" * 74)
    print("turkce  : Turkce harflerin tum harflere orani (ham olcum)")
    print("taban%  : belgenin KENDI cevap anahtarindaki orana gore yuzde.")
    print("          %100 = Turkce harfler tamamen korunmus.")
    print("          300 etiketten olculen taban: ortanca %11.8")
    print("sdp/dipnot: '—' = o belgede zaten yok, olculemez (basarisizlik degil)")
    print("\nCiktinin tamamini yapistirin.")
    return 0


class _CiftYazici:
    """Ciktiyi hem ekrana hem dosyaya yazar.

    Konsol ciktisi uzun ve kesiliyordu; tam sonuc dosyada kalsin.
    """

    def __init__(self, dosya):
        self.dosya = dosya
        self.ekran = sys.__stdout__

    def write(self, s):
        self.ekran.write(s)
        self.dosya.write(s)

    def flush(self):
        self.ekran.flush()
        self.dosya.flush()


if __name__ == "__main__":
    cikti_yolu = KOK / "ocr_kalitesi_sonuc.txt"
    with cikti_yolu.open("w", encoding="utf-8") as f:
        sys.stdout = _CiftYazici(f)
        try:
            kod = main(sys.argv[1:])
        finally:
            sys.stdout = sys.__stdout__
    print(f"\nTam cikti: {cikti_yolu}")
    raise SystemExit(kod)