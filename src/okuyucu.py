"""Okuyucu — boru hattının 1. adımı. PDF'i sıralı satırlara çevirir.

ARAÇ, LLM yok. Girdi: PDF yolu. Çıktı: Satir listesi + dipnot ayrımı.

NEDEN MELEZ
-----------
Ölçüldü (300 belge, ocr_kalitesi.py ve docling_dene.py):

    metin katmanlı 250 belge   pdfplumber  ~0,05 sn   terim %96   koordinat var
    metin katmanlı, OCR ile                ~3    sn   —           bosuna
    taranmış        50 belge   EasyOCR     ~16   sn   terim %68

Metin katmanı varken OCR koşturmak hem 60 kat yavaş hem daha kötü. Docling
metin katmanlı belgede de OCR deniyor ve "text detection result is empty"
deyip atıyor — 250 belgede ~12 dakika boşa gidiyor.

NEDEN KOORDİNAT, MARKDOWN DEĞİL
-------------------------------
Ölçüldü (ocr_karsilastir.py, belge_001 ve belge_035):

    docling export_to_markdown() cikti:
        E-24304062-807.01-57692713
        Konu
        Boya Badana İşleri Hk.
        Sayı                        <- etiket degerinden KOPMUS ve sira bozuk

    belge_035'te "İlgi" etiketi belgenin EN SONUNA dusmus, degeri en basta.

Sebep: iki yana yazılmış metinde kelime araları geniş; OCR blokları ayrı
sanıp kendi okuma sırasını uyduruyor. Ayrıştırıcı "Sayı :" etiketini bulup
sonrasını okuyacak — bu sırayla imkânsız.

Çözüm: markdown'a hiç bakmamak. Öğeleri kutularıyla alıp y'ye, sonra x'e
göre kendimiz sıralamak. Metin ONARILMIYOR, sadece doğru sırayla diziliyor.

SINIR — dürüst kayıt
--------------------
Sıralama, öğeler ARASINDAKİ karışıklığı düzeltir (Sayı/Konu/İlgi ayrımı).
Bir paragrafın İÇİNDEKİ kelime karışıklığını düzeltmez:

    "...genelge sureti ekte gönderilmistir . Söz konusu karar Yeni
     uygulama 01.01.2026 tarihinde yürürlüğe girmistir. yeni olup"

Bu tek bir öğenin içinde ve kutusu tek. Düzeltilemiyor.

KOORDİNAT SİSTEMİ
-----------------
Ölçüldü (docling_sonda.py): Docling BOTTOMLEFT kullanıyor, pdfplumber
TOPLEFT. Ters. Çevrim:  y_ust = sayfa_yuksekligi - y_docling
Bağımsız doğrulaması: belge_002'nin KEP satırı pdfplumber'da üstten 779,
Docling'de alttan 61,6 -> 842 - 61,6 = 780,4. İki ayrı araç, aynı yer.
"""

from __future__ import annotations

import logging
import math
import os
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path

warnings.filterwarnings("ignore")
os.environ.setdefault("PYTHONWARNINGS", "ignore")
for _ad in ("docling", "RapidOCR", "rapidocr", "easyocr", "torch", "PIL"):
    logging.getLogger(_ad).setLevel(logging.ERROR)

from dipnot import AyrilmisMetin, Satir, dipnotu_ayir  # noqa: E402

# -----------------------------------------------------------------------------
# Ayarlar
# -----------------------------------------------------------------------------

# Bir sayfada bu kadar karakterden azsa metin katmanı yok sayılır.
# Taranmış PDF'te pdfplumber boş veya birkaç çöp karakter döndürür;
# metin katmanlı en kısa belgemizde 422 karakter var (ocr_kalitesi ölçümü).
METIN_KATMANI_ESIGI = 120

# Aynı satır sayılma toleransı, punto. 12 punto yazıda satır aralığı 14,6
# (yerlesim.yaml govde.satir_araligi); yarısı güvenli ayrım noktası.
SATIR_TOLERANSI = 6.0

VARSAYILAN_SAYFA_YUKSEKLIGI = 842.0   # A4

# Eğim düzeltme. Taranmış belge kâğıda robotik hassasiyetle konmaz; birkaç
# derece yatık gelir ve satırın solu ile sağı farklı y'ye düşer.
#
# ÖLÇÜLDÜ (belge_012, 145 kelime, 24 gerçek satır, yapay eğiklik):
#
#     eğim   düzeltmesiz            düzeltmeli
#       0°   24 grup,  0 karışık    24 grup, 0 karışık
#       1°   31 grup,  1 karışık    24 grup, 0 karışık
#       2°   34 grup,  6 karışık    24 grup, 0 karışık
#       5°   44 grup, 21 karışık    24 grup, 0 karışık
#
# Denenen bir alternatif: kelimeyi grubun İLKİ yerine SONUNCUSU ile
# karşılaştırmak (zincirleme). 1°'de iyi çalışıyor ama 2°'den sonra ÇÖKÜYOR:
# 24 satır 15 gruba iniyor, yani ayrı satırlar birbirine yapışıyor. Bölünmüş
# satır sonradan birleştirilebilir, yapışmış satır geri ayrılamaz. Bu yüzden
# zincirleme değil, eğim düzeltme seçildi.
EGIM_ARAMA_SINIRI = 6.0    # derece, iki yöne
EGIM_ADIMI = 0.25
EGIM_ASGARI_PARCA = 30     # bundan az parçada açı güvenilir kestirilemez
EGIM_ASGARI_KAZANC = 0.10  # grup sayısı en az %10 azalmazsa dokunma


@dataclass
class OkumaSonucu:
    """Okuyucu'nun çıktısı."""

    satirlar: list[Satir] = field(default_factory=list)
    girdi_tipi: str = "bilinmiyor"      # metin_katmanli | taranmis | bos
    motor: str | None = None            # pdfplumber | easyocr
    sayfa_sayisi: int = 0
    sayfa_yuksekligi: float = VARSAYILAN_SAYFA_YUKSEKLIGI
    sure_ms: float = 0.0
    ayrilmis: AyrilmisMetin | None = None
    hata: str | None = None

    @property
    def govde(self) -> str:
        return self.ayrilmis.govde if self.ayrilmis else ""

    @property
    def dipnot(self) -> str:
        return self.ayrilmis.dipnot if self.ayrilmis else ""

    @property
    def ham_metin(self) -> str:
        return "\n".join(s.metin for s in self.satirlar)

    @property
    def ozet(self) -> str:
        """IzKaydi.ozet alanına yazılacak tek satır."""
        n = len(self.ayrilmis.dipnot_satirlari) if self.ayrilmis else 0
        return (
            f"{self.sayfa_sayisi} sayfa, {self.girdi_tipi}, "
            f"{len(self.satirlar)} satır, {n} satır dipnot ayrıldı"
        )


# -----------------------------------------------------------------------------
# Satır kurma
# -----------------------------------------------------------------------------


def _dondur(parcalar, derece, cx, cy):
    """Parçaları sayfa merkezinde `derece` kadar döndürür."""
    a = math.radians(derece)
    sin_a, cos_a = math.sin(a), math.cos(a)
    return [
        (cy + (x - cx) * sin_a + (y - cy) * cos_a,
         cx + (x - cx) * cos_a - (y - cy) * sin_a,
         metin)
        for y, x, metin in parcalar
    ]


def _grup_sayisi(parcalar) -> int:
    sirali = sorted(parcalar, key=lambda p: (p[0], p[1]))
    n, son = 1, sirali[0][0]
    for p in sirali[1:]:
        if abs(p[0] - son) > SATIR_TOLERANSI:
            n += 1
            son = p[0]
    return n


def _egimi_duzelt(parcalar: list[tuple[float, float, str]]):
    """Sayfa eğikse düzeltir. Doğru açı satırları toplar, yanlış açı dağıtır.

    Ölçüt kendi kendini bulur: grup sayısını en aza indiren açı doğru açıdır.
    Kazanç küçükse dokunulmaz — sayfa zaten düzdür.
    """
    if len(parcalar) < EGIM_ASGARI_PARCA:
        return parcalar, 0.0
    cx = sum(p[1] for p in parcalar) / len(parcalar)
    cy = sum(p[0] for p in parcalar) / len(parcalar)

    taban = _grup_sayisi(parcalar)
    en_iyi_sayi, en_iyi_aci = taban, 0.0
    aci = -EGIM_ARAMA_SINIRI
    while aci <= EGIM_ARAMA_SINIRI:
        if aci:
            n = _grup_sayisi(_dondur(parcalar, aci, cx, cy))
            if n < en_iyi_sayi:
                en_iyi_sayi, en_iyi_aci = n, aci
        aci += EGIM_ADIMI

    if not en_iyi_aci or (taban - en_iyi_sayi) < taban * EGIM_ASGARI_KAZANC:
        return parcalar, 0.0
    return _dondur(parcalar, en_iyi_aci, cx, cy), en_iyi_aci


def _satirlari_kur(parcalar: list[tuple[float, float, str]]) -> list[Satir]:
    """(y_ust, x_sol, metin) üçlülerini sıralı satırlara çevirir.

    Önce y'ye göre gruplanır (tolerans dahilinde aynı satır sayılır), sonra
    her grup x'e göre soldan sağa dizilir. Sıra bozukluğu burada düzelir.
    """
    if not parcalar:
        return []
    parcalar, _aci = _egimi_duzelt(parcalar)
    parcalar = sorted(parcalar, key=lambda p: (p[0], p[1]))

    satirlar: list[Satir] = []
    grup: list[tuple[float, float, str]] = [parcalar[0]]
    for p in parcalar[1:]:
        if abs(p[0] - grup[0][0]) <= SATIR_TOLERANSI:
            grup.append(p)
        else:
            satirlar.append(_grubu_birlestir(grup))
            grup = [p]
    satirlar.append(_grubu_birlestir(grup))
    return satirlar


def _grubu_birlestir(grup: list[tuple[float, float, str]]) -> Satir:
    """Aynı satırdaki parçaları soldan sağa birleştirir, yinelenenleri atar.

    Docling aynı bölgeyi bazen iki kez çıkarıyor (ölçüldü, belge_020):

        Sayı Sayı E-90226917-756.01-3771125 E-90226917-756.01-3771125

    Ayrıştırıcı bunu görürse hangisinin değer olduğunu bilemez. Yalnızca
    ARDIŞIK ve BİREBİR aynı parçalar atılıyor; uzaktaki tekrarlara
    dokunulmuyor, çünkü metinde meşru tekrar olabilir.
    """
    grup = sorted(grup, key=lambda p: p[1])
    parcalar: list[str] = []
    for _, _, ham in grup:
        metin = ham.strip()
        if metin and (not parcalar or parcalar[-1] != metin):
            parcalar.append(metin)
    return Satir(y=grup[0][0], metin=" ".join(parcalar))


# -----------------------------------------------------------------------------
# Yol 1 — metin katmanlı
# -----------------------------------------------------------------------------


def _pdfplumber_ile(yol: Path) -> tuple[list[Satir], int, float]:
    import pdfplumber

    parcalar: list[tuple[float, float, str]] = []
    with pdfplumber.open(str(yol)) as pdf:
        sayfa_sayisi = len(pdf.pages)
        yukseklik = float(pdf.pages[0].height)
        for i, sayfa in enumerate(pdf.pages):
            # Çok sayfalıda sayfaları alt alta ekliyoruz ki sıralama karışmasın.
            kaydirma = i * yukseklik
            for k in sayfa.extract_words():
                parcalar.append(
                    (float(k["top"]) + kaydirma, float(k["x0"]), k["text"])
                )
    return _satirlari_kur(parcalar), sayfa_sayisi, yukseklik


def _metin_katmani_var_mi(yol: Path) -> bool:
    import pdfplumber

    try:
        with pdfplumber.open(str(yol)) as pdf:
            metin = pdf.pages[0].extract_text() or ""
        return len(metin.strip()) >= METIN_KATMANI_ESIGI
    except Exception:  # noqa: BLE001
        return False


# -----------------------------------------------------------------------------
# Yol 2 — taranmış
# -----------------------------------------------------------------------------

_DONUSTURUCU = None


def _easyocr_donusturucu():
    """Docling + EasyOCR(tr). Bir kez kurulur, tekrar kullanılır.

    Model yükleme pahalı; her belgede yeniden kurmak 300 belgede saatler
    ekler.
    """
    global _DONUSTURUCU
    if _DONUSTURUCU is not None:
        return _DONUSTURUCU
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import EasyOcrOptions, PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    ayar = PdfPipelineOptions()
    ayar.do_ocr = True
    ayar.ocr_options = EasyOcrOptions(lang=["tr"])
    _DONUSTURUCU = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=ayar)}
    )
    return _DONUSTURUCU


def _sayfa_yukseklikleri(belge) -> dict[int, float]:
    yukseklikler: dict[int, float] = {}
    try:
        sayfalar = belge.pages
        anahtarlar = sayfalar.keys() if isinstance(sayfalar, dict) else range(len(sayfalar))
        for a in anahtarlar:
            s = sayfalar[a]
            boyut = getattr(s, "size", None)
            yukseklikler[int(a)] = float(getattr(boyut, "height", 0)) or VARSAYILAN_SAYFA_YUKSEKLIGI
    except Exception:  # noqa: BLE001
        pass
    return yukseklikler


def _docling_ile(yol: Path) -> tuple[list[Satir], int, float]:
    belge = _easyocr_donusturucu().convert(str(yol)).document
    yukseklikler = _sayfa_yukseklikleri(belge)
    varsayilan = next(iter(yukseklikler.values()), VARSAYILAN_SAYFA_YUKSEKLIGI)

    parcalar: list[tuple[float, float, str]] = []
    kutusuz = 0
    for oge in getattr(belge, "texts", []) or []:
        metin = (getattr(oge, "text", "") or "").strip()
        if not metin:
            continue
        prov = getattr(oge, "prov", None)
        if not prov:
            kutusuz += 1
            continue
        p = prov[0]
        kutu = getattr(p, "bbox", None)
        if kutu is None:
            kutusuz += 1
            continue
        sayfa_no = int(getattr(p, "page_no", 1) or 1)
        yukseklik = yukseklikler.get(sayfa_no, varsayilan)
        try:
            ust_alttan = float(kutu.t)
            sol = float(kutu.l)
        except (AttributeError, TypeError, ValueError):
            kutusuz += 1
            continue

        # BOTTOMLEFT -> TOPLEFT. Olculdu: docling_sonda.py
        y_ust = yukseklik - ust_alttan
        # Cok sayfalida sayfalari alt alta ekle
        y_ust += (sayfa_no - 1) * yukseklik
        parcalar.append((y_ust, sol, metin))

    if kutusuz:
        logging.getLogger(__name__).warning(
            "%s: %d oge kutusuz, siralamaya girmedi", yol.name, kutusuz
        )
    return _satirlari_kur(parcalar), max(1, len(yukseklikler)), varsayilan


# -----------------------------------------------------------------------------
# Ana giriş
# -----------------------------------------------------------------------------


def oku(pdf_yolu: str | Path, dipnotu_ayikla: bool = True) -> OkumaSonucu:
    """PDF'i okur, satırlara böler, dipnotu ayırır.

    Metin katmanı varsa pdfplumber, yoksa Docling + EasyOCR kullanılır.
    Her iki yol da aynı Satir listesini üretir; sonraki adımlar hangi
    yoldan geldiğini bilmek zorunda değil.
    """
    yol = Path(pdf_yolu)
    t0 = time.perf_counter()
    sonuc = OkumaSonucu()

    if not yol.exists():
        sonuc.hata = f"dosya yok: {yol}"
        return sonuc

    try:
        if _metin_katmani_var_mi(yol):
            satirlar, sayfa, yukseklik = _pdfplumber_ile(yol)
            sonuc.girdi_tipi, sonuc.motor = "metin_katmanli", "pdfplumber"
        else:
            satirlar, sayfa, yukseklik = _docling_ile(yol)
            sonuc.girdi_tipi, sonuc.motor = "taranmis", "easyocr"
    except Exception as e:  # noqa: BLE001
        sonuc.hata = f"{type(e).__name__}: {e}"
        sonuc.sure_ms = (time.perf_counter() - t0) * 1000
        return sonuc

    sonuc.satirlar = satirlar
    sonuc.sayfa_sayisi = sayfa
    sonuc.sayfa_yuksekligi = yukseklik
    if not satirlar:
        sonuc.girdi_tipi = "bos"

    if dipnotu_ayikla and satirlar:
        # Cok sayfalida dipnot HER sayfada olur; su an veri setinin tamami
        # tek sayfa (PARCA2_DEVIR_NOTLARI 6.2 SayfaTasmasi). Cok sayfali
        # dipnot ayrimi Parca 5'e birakildi.
        sonuc.ayrilmis = dipnotu_ayir(satirlar, yukseklik)

    sonuc.sure_ms = (time.perf_counter() - t0) * 1000
    return sonuc
