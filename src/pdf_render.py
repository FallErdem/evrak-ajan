"""Resmî yazı PDF üreteci.

    govde_NNN.txt  +  etiket_NNN.json  ->  belge_NNN.pdf

ÖLÇÜLER
Ölçülerin tamamı `veri/sablon/yerlesim.yaml` dosyasında dayanaklarıyla
kayıtlı; norm olanla gözlem olan orada ayrılmıştır.

İLK SÜRÜMDE 13 ÖLÇÜ YANLIŞTI. Kenar boşluklarını 2,5 cm sanmıştım;
Yönetmelik m.8/1 üst/sol/sağ için 1,5 cm diyor. Paragraf girintisi
1,25 cm (m.16/4), 1 cm koymuştum. Metin iki yana hizalı olmalı, sola
dayamıştım. Ölçüyü tahmin etmek eksik bırakmaktan kötü: yanlış ölçü
doğru görünüyor ve fark edilmiyor.

BAŞLIK, AMBLEM, İMZA VE DİPNOT GÖNDERENE AİTTİR
İlk sürümde bunlar ALICIYA göre kuruluyordu ve belge kendi kendine
gönderilmiş görünüyordu. Yönetmelik m.10: başlık bloğu yazıyı GÖNDEREN
idarenin adını taşır.

İKİ BELGE TÜRÜ
Kurum yazısı ile vatandaş dilekçesi TAMAMEN FARKLI kurulur:

    kurum yazısı : amblem + başlık + sayı/tarih/konu/ilgi + hitap +
                   gövde + imza + ek + dipnot (QR dahil)
    dilekçe      : hitap + gövde + iki sütunlu alt blok
                   (başlık bloğu, sayı ve konu satırı YOKTUR)
"""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, pi, sin
from pathlib import Path

import reportlab
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas

# =============================================================================
# FONT
# =============================================================================
# Yönetmelik m.7/1: Times New Roman 12 punto veya Arial 11 punto.
#
# reportlab'ın gömülü Times-Roman'ı Türkçe karakterleri DESTEKLEMİYOR.
# Üç aday sınandı, üçünde de ĞÜŞİÖÇ ğüşıöç âîû eksiksiz:
#
#   LiberationSerif  -> Times New Roman ile METRİK UYUMLU. Norma en yakın.
#   DejaVuSerif      -> serif ama TNR'den geniş
#   Vera             -> sans-serif, reportlab ile GÖMÜLÜ gelir
#
# Sıra: önce LiberationSerif (çoğu Linux'ta var), sonra DejaVuSerif,
# son çare Vera. Vera her ortamda çalışır çünkü reportlab ile birlikte
# gelir — Windows'ta da.

_RL_FONT = Path(reportlab.__file__).parent / "fonts"

_FONT_ADAYLARI = [
    ("LiberationSerif",
     "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf"),
    ("DejaVuSerif",
     "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"),
    ("Vera",
     str(_RL_FONT / "Vera.ttf"),
     str(_RL_FONT / "VeraBd.ttf")),
]

NORMAL, KALIN = "BelgeNormal", "BelgeKalin"
_kayitli = False
_kullanilan_font = ""


def fontlari_kaydet() -> str:
    """Kullanılabilir en uygun fontu kaydeder, adını döndürür."""
    global _kayitli, _kullanilan_font
    if _kayitli:
        return _kullanilan_font
    for ad, normal_yol, kalin_yol in _FONT_ADAYLARI:
        if not (Path(normal_yol).exists() and Path(kalin_yol).exists()):
            continue
        try:
            pdfmetrics.registerFont(TTFont(NORMAL, normal_yol))
            pdfmetrics.registerFont(TTFont(KALIN, kalin_yol))
            _kayitli, _kullanilan_font = True, ad
            return ad
        except Exception:
            continue
    raise RuntimeError("Türkçe destekli font bulunamadı.")


# =============================================================================
# SAYFA ÖLÇÜLERİ — KURUM YAZISI
# =============================================================================
SAYFA_G, SAYFA_Y = A4

# Yönetmelik m.8/1
UST = 15 * mm
SOL = 15 * mm
SAG = 15 * mm
# Alt kenar için NORM YOK; Kılavuz s.10 "azami 0,5 cm" tavsiyesi.
ALT = 5 * mm

YAZI_G = SAYFA_G - SOL - SAG            # 180 mm
ORTA_HIZA = SOL + YAZI_G / 2            # 105 mm — konu bunu geçemez (m.13/1)

# Yönetmelik m.7/1
PUNTO = 12
PUNTO_KUCUK = 8         # dipnot (m.7/1: 8 puntoya kadar)
# NORM YOK. Gözlemlenen 13,8 (Word "tek") biraz sıkışık duruyordu;
# okunabilirlik için hafif artırıldı.
SATIR = 14.6

# Yönetmelik m.16/4
PARAGRAF_GIRINTI = 12.5 * mm

# Yönetmelik m.15/3: Sayı, Konu, İlgi iki noktaları AYNI HİZADA.
# Hiza kuralı norm, mm değerleri gözlem.
IKI_NOKTA_X = SOL + 11 * mm
DEGER_X = SOL + 18 * mm
KONU_AZAMI_G = ORTA_HIZA - DEGER_X      # ~72 mm

# Yönetmelik m.17/1: "yazı alanının en sağında ORTALANARAK".
# Blok sağ yarıya yerleşir, satırlar bloğun içinde ortalanır.
IMZA_MERKEZ_X = 150 * mm

# Kılavuz s.11: logo üstten 0,5 cm, soldan 1,5 cm.
# Boyut için norm yok; gerçek belgelerde 19-22 mm ölçüldü.
AMBLEM_BOY = 20 * mm
AMBLEM_UST = 5 * mm

# Norm yok, gözlem: ayırıcı çizgi alt kenardan 32-34 mm.
DIPNOT_CIZGI_ALTTAN = 33 * mm
QR_BOY = 13 * mm

# =============================================================================
# SAYFA ÖLÇÜLERİ — DİLEKÇE
# =============================================================================
# RESMÎ YAZIŞMA YÖNETMELİĞİ DİLEKÇEYİ KAPSAMAZ. Tek bağlayıcı norm
# 3071 sayılı Kanun m.4'tür ve o da yalnızca İÇERİK zorunluluğu koyar
# (ad-soyad, imza, adres), biçim koymaz.
#
# Aşağıdaki ölçüler gerçek bir dilekçe formundan (docx XML, tam değer)
# alındı — resmî yazıdan FARKLI, Word varsayılanına yakın.
D_UST = 20 * mm
D_SOL = 25 * mm
D_SAG = 25 * mm
D_ALT = 25 * mm
D_YAZI_G = SAYFA_G - D_SOL - D_SAG


# =============================================================================
# TÜRKÇE YARDIMCI
# =============================================================================


def tr_buyut(metin: str) -> str:
    """Türkçeye uygun büyük harf.

    Python'un upper() metodu "i" harfini "I" yapar, "İ" değil:
        "Yenimahalle".upper()   ->  "YENIMAHALLE"   (yanlış)
        tr_buyut("Yenimahalle") ->  "YENİMAHALLE"   (doğru)
    """
    return metin.replace("i", "İ").replace("ı", "I").upper()


# =============================================================================
# AMBLEM
# =============================================================================
# KURGUSAL. Gerçek kurum logoları telif kapsamında; depoya konamaz.
# Vektörel çizilir, dosya bağımlılığı yoktur.
#
# AMBLEMDE METİN YOKTUR. drawString ile harf yazılınca metin çıkarımında
# ikinci bir "T.C." görünüyordu; gerçek bir kurum armasında metin
# katmanı yoktur. Harf yerine geometrik işaret çizilir — Docling bunu
# görmez ama insan gözüyle kurumlar ayırt edilir.


def _amblem_tipi(e: dict) -> str:
    """Amblem GÖNDERENE aittir, alıcıya değil.

    Ölçülen hata: belgeyi Çevre Bakanlığı yazıyordu ama sol üstte
    belediye amblemi vardı.
    """
    ad = e["gonderen"].get("kurum_adi") or ""
    if "Bakanlığı" in ad or "Kurulu" in ad:
        return "merkezi"
    if "Valiliği" in ad or "Kaymakamlığı" in ad:
        return "mulki"
    if "Belediye" in ad:
        return "belediye"
    if "Üniversite" in ad or "Rektörlük" in ad:
        return "universite"
    if any(k in ad for k in ("Millî Eğitim", "Milli Eğitim", "Okulu",
                             "Lisesi", "Ortaokulu")):
        return "il_mudurlugu"
    # Kurum içi birim: alıcının kurum tipi geçerli
    return e["alici"]["kurum_tipi"]


def _amblem_ciz(c, kurum_tipi: str, x: float, y: float) -> None:
    """Sol üst köşeye kurgusal amblem çizer. (x, y) sol alt köşe."""
    b = AMBLEM_BOY
    orta_x, orta_y = x + b / 2, y + b / 2
    c.saveState()
    c.setStrokeColorRGB(0.25, 0.25, 0.3)
    c.setLineWidth(1.1)

    # --- dış çerçeve --------------------------------------------------------
    if kurum_tipi == "belediye":
        c.circle(orta_x, orta_y, b / 2, stroke=1, fill=0)
        c.circle(orta_x, orta_y, b / 2 - 1.6 * mm, stroke=1, fill=0)
    elif kurum_tipi == "universite":
        c.setLineWidth(1.3)
        p = c.beginPath()
        p.moveTo(orta_x, y + b)
        p.lineTo(x + b, orta_y)
        p.lineTo(orta_x, y)
        p.lineTo(x, orta_y)
        p.close()
        c.drawPath(p, stroke=1, fill=0)
    elif kurum_tipi == "merkezi":
        p = c.beginPath()
        for i in range(6):
            a = pi / 3 * i - pi / 6
            px, py = orta_x + b / 2 * cos(a), orta_y + b / 2 * sin(a)
            p.moveTo(px, py) if i == 0 else p.lineTo(px, py)
        p.close()
        c.drawPath(p, stroke=1, fill=0)
    elif kurum_tipi == "mulki":
        c.roundRect(x, y, b, b, 3 * mm, stroke=1, fill=0)
        c.roundRect(x + 1.5 * mm, y + 1.5 * mm, b - 3 * mm, b - 3 * mm,
                    2 * mm, stroke=1, fill=0)
    else:  # il_mudurlugu
        c.rect(x, y, b, b, stroke=1, fill=0)
        c.rect(x + 1.6 * mm, y + 1.6 * mm, b - 3.2 * mm, b - 3.2 * mm,
               stroke=1, fill=0)

    # --- iç işaret (metin değil, çizgi) -------------------------------------
    c.setLineWidth(0.9)
    ib = b * 0.24
    if kurum_tipi == "belediye":
        for i in (-1, 0, 1):
            c.line(orta_x - ib, orta_y + i * ib * 0.55,
                   orta_x + ib, orta_y + i * ib * 0.55)
    elif kurum_tipi == "universite":
        c.line(orta_x - ib, orta_y - ib * 0.4, orta_x, orta_y + ib * 0.3)
        c.line(orta_x, orta_y + ib * 0.3, orta_x + ib, orta_y - ib * 0.4)
        c.line(orta_x, orta_y + ib * 0.3, orta_x, orta_y - ib * 0.5)
    elif kurum_tipi == "merkezi":
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            c.line(orta_x, orta_y, orta_x + dx * ib, orta_y + dy * ib)
    elif kurum_tipi == "mulki":
        c.line(orta_x - ib, orta_y - ib, orta_x + ib, orta_y + ib)
        c.line(orta_x - ib, orta_y + ib, orta_x + ib, orta_y - ib)
    else:
        tp = c.beginPath()
        tp.moveTo(orta_x, orta_y + ib)
        tp.lineTo(orta_x + ib, orta_y - ib * 0.5)
        tp.lineTo(orta_x - ib, orta_y - ib * 0.5)
        tp.close()
        c.drawPath(tp, stroke=1, fill=0)
    c.restoreState()


# =============================================================================
# METİN YARDIMCILARI
# =============================================================================


def _sar(c, metin: str, genislik: float, font: str, punto: int) -> list[str]:
    """Metni sütun genişliğine göre KELİME SINIRINDAN sarar."""
    satirlar, gecerli = [], ""
    for kelime in metin.split():
        deneme = f"{gecerli} {kelime}".strip()
        if c.stringWidth(deneme, font, punto) <= genislik:
            gecerli = deneme
        else:
            if gecerli:
                satirlar.append(gecerli)
            gecerli = kelime
    if gecerli:
        satirlar.append(gecerli)
    return satirlar or [""]


def _sar_girintili(c, metin: str, ilk_genislik: float, genislik: float,
                   font: str, punto: int) -> list[str]:
    """Metni sarar; İLK SATIR girinti kadar dar olur."""
    satirlar, gecerli = [], ""
    for kelime in metin.split():
        hedef = ilk_genislik if not satirlar else genislik
        deneme = f"{gecerli} {kelime}".strip()
        if c.stringWidth(deneme, font, punto) <= hedef:
            gecerli = deneme
        else:
            if gecerli:
                satirlar.append(gecerli)
            gecerli = kelime
    if gecerli:
        satirlar.append(gecerli)
    return satirlar or [""]


def _iki_yana_yaz(c, satir: str, x: float, y: float, genislik: float,
                  font: str, punto: int, son_satir: bool) -> None:
    """Satırı iki yana hizalayarak yazar (Yönetmelik m.16/4).

    Paragrafın SON satırı hizalanmaz — sola dayalı kalır, aksi hâlde
    tek kelimelik son satır sayfa boyunca yayılır.
    """
    kelimeler = satir.split()
    if son_satir or len(kelimeler) < 2:
        c.setFont(font, punto)
        c.drawString(x, y, satir)
        return

    # KELİME KELİME drawString KULLANILMAZ. Denendi ve metin çıkarımını
    # bozdu: her kelime ayrı bir metin nesnesi olduğu için pypdf ve
    # Docling her kelimeyi AYRI SATIR olarak okuyor.
    #
    # setWordSpace tek bir metin nesnesi üretir, kelime aralarını PDF
    # düzeyinde genişletir. Görünüm aynı, metin katmanı bozulmuyor.
    # Bu, sistemin belgeyi okuyabilmesi için kritik.
    #
    # setWordSpace CANVAS DURUMUNU değiştirir ve sonraki drawString
    # çağrılarına sızar — imza ve dipnot satırlarında da kelime araları
    # genişliyordu. saveState/restoreState ile sınırlandırılıyor.
    ek_bosluk = (genislik - c.stringWidth(satir, font, punto)) / (
        len(kelimeler) - 1)
    c.saveState()
    t = c.beginText(x, y)
    t.setFont(font, punto)
    t.setWordSpace(ek_bosluk)
    t.textLine(satir)
    c.drawText(t)
    c.restoreState()


def _yaz(c, metin: str, x: float, y: float, font: str = NORMAL,
         punto: int = PUNTO) -> float:
    c.setFont(font, punto)
    c.drawString(x, y, metin)
    return y - SATIR


def _yaz_sarmali(c, metin: str, x: float, y: float, genislik: float,
                 font: str = NORMAL, punto: int = PUNTO) -> float:
    c.setFont(font, punto)
    for satir in _sar(c, metin, genislik, font, punto):
        c.drawString(x, y, satir)
        y -= SATIR
    return y


def _govde_ciz(c, govde: str, y: float, sol: float, genislik: float) -> float:
    """Gövde metnini Yönetmelik m.16/4'e göre çizer.

    - Paragraf başı 1,25 cm girintili
    - Metin iki yana hizalı (son satır hariç)
    - Paragraflar arasında SATIR BOŞLUĞU YOK; ayrım yalnızca girintiyle
    """
    for paragraf in govde.strip().split("\n\n"):
        p = " ".join(paragraf.split())
        if not p:
            continue
        ilk_g = genislik - PARAGRAF_GIRINTI
        satirlar = _sar_girintili(c, p, ilk_g, genislik, NORMAL, PUNTO)
        for i, satir in enumerate(satirlar):
            x = sol + (PARAGRAF_GIRINTI if i == 0 else 0)
            g = ilk_g if i == 0 else genislik
            _iki_yana_yaz(c, satir, x, y, g, NORMAL, PUNTO,
                          son_satir=(i == len(satirlar) - 1))
            y -= SATIR
    return y


def _dogrulama_kodu(belge_no: str) -> str:
    """Kurgusal belge doğrulama kodu.

    Gerçek örnekler: BSDSHHL742, BS5SZNT943. Belge numarasından
    türetilir; aynı belge her zaman aynı kodu alır.
    """
    harfler = "ABCDEFGHJKLMNPRSTUVYZ"
    n = int(belge_no)
    return ("BS"
            + harfler[(n * 7) % len(harfler)]
            + harfler[(n * 13) % len(harfler)]
            + harfler[(n * 3) % len(harfler)]
            + f"{(n * 8641) % 10000:04d}")


# =============================================================================
# GÖNDEREN BİLGİLERİ
# =============================================================================
# Başlık, amblem, imza ve dipnot GÖNDERENE aittir. İlk sürümde bunlar
# alıcıya göre kuruluyordu ve belge kendi kendine gönderilmiş
# görünüyordu.

_DIS_KURUM_BASLIK = {
    "Millî Eğitim Bakanlığı": ["T.C.", "MİLLÎ EĞİTİM BAKANLIĞI"],
    "İçişleri Bakanlığı": ["T.C.", "İÇİŞLERİ BAKANLIĞI"],
    "Çevre, Şehircilik ve İklim Değişikliği Bakanlığı":
        ["T.C.", "ÇEVRE, ŞEHİRCİLİK VE İKLİM DEĞİŞİKLİĞİ BAKANLIĞI"],
    "Yükseköğretim Kurulu Başkanlığı":
        ["T.C.", "YÜKSEKÖĞRETİM KURULU BAŞKANLIĞI"],
    "Ankara Valiliği": ["T.C.", "ANKARA VALİLİĞİ"],
    "Yenimahalle Kaymakamlığı": ["T.C.", "YENİMAHALLE KAYMAKAMLIĞI"],
    "Ankara Büyükşehir Belediye Başkanlığı":
        ["T.C.", "ANKARA BÜYÜKŞEHİR BELEDİYE BAŞKANLIĞI"],
    "Çankaya Belediye Başkanlığı": ["T.C.", "ÇANKAYA BELEDİYE BAŞKANLIĞI"],
    "Yenimahalle Belediye Başkanlığı":
        ["T.C.", "YENİMAHALLE BELEDİYE BAŞKANLIĞI"],
    "Ankara İl Millî Eğitim Müdürlüğü":
        ["T.C.", "ANKARA VALİLİĞİ", "İl Millî Eğitim Müdürlüğü"],
    "Gazi Üniversitesi Rektörlüğü": ["T.C.", "GAZİ ÜNİVERSİTESİ REKTÖRLÜĞÜ"],
    "Gazi Üniversitesi": ["T.C.", "GAZİ ÜNİVERSİTESİ REKTÖRLÜĞÜ"],
}

# Kurum içi birimler için üst kurum. Gönderen "Fen İşleri Müdürlüğü" ise
# başlığın ikinci satırı bağlı olduğu idarenin adıdır.
_BIRIM_UST_KURUM = {
    "belediye": "YENİMAHALLE BELEDİYE BAŞKANLIĞI",
    "universite": "GAZİ ÜNİVERSİTESİ REKTÖRLÜĞÜ",
    "il_mudurlugu": "ANKARA VALİLİĞİ",
}


def _baslik_kur(e: dict) -> list[str]:
    """Başlık bloğu GÖNDERENE aittir (Yönetmelik m.10).

    1. satır T.C., 2. satır İDARENİN adı, 3. satır BİRİMİN adı — yazıyı
    GÖNDEREN idarenin ve biriminin adı.
    """
    if e.get("gonderen_baslik"):
        return e["gonderen_baslik"]

    ad = e["gonderen"].get("kurum_adi") or ""
    if ad in _DIS_KURUM_BASLIK:
        return _DIS_KURUM_BASLIK[ad]

    # Okullar ve ilçe müdürlükleri kaymakamlığa bağlıdır (m.10/3)
    if any(k in ad for k in ("Okulu", "Lisesi", "Ortaokulu", "İlçe")):
        return ["T.C.", "YENİMAHALLE KAYMAKAMLIĞI", ad]

    # KURUM İÇİ BİRİM. İl MEM'de şube müdürlüğü başlıkta GÖRÜNMEZ.
    ust = _BIRIM_UST_KURUM.get(e["alici"]["kurum_tipi"])
    if ust:
        if e["alici"]["kurum_tipi"] == "il_mudurlugu":
            return ["T.C.", ust, "İl Millî Eğitim Müdürlüğü"]
        return ["T.C.", ust, ad]

    return ["T.C.", tr_buyut(ad)]


# Gönderen makamın imza unvanı. Gerçek yazışmada imzalayan çoğu zaman
# birimin başı değildir ("Müdür a. / Şube Müdürü"); bu ayrıntı etikette
# `imzalayan_unvan` alanıyla da verilebilir.
_GONDEREN_UNVAN = {
    "Millî Eğitim Bakanlığı": "Bakan a. / Genel Müdür",
    "İçişleri Bakanlığı": "Bakan a. / Genel Müdür",
    "Çevre, Şehircilik ve İklim Değişikliği Bakanlığı":
        "Bakan a. / Genel Müdür",
    "Yükseköğretim Kurulu Başkanlığı": "Başkan a. / Genel Sekreter",
    "Ankara Valiliği": "Vali a. / Vali Yardımcısı",
    "Yenimahalle Kaymakamlığı": "Kaymakam",
    "Ankara Büyükşehir Belediye Başkanlığı": "Başkan a. / Daire Başkanı",
    "Çankaya Belediye Başkanlığı": "Başkan a. / Daire Başkanı",
    "Yenimahalle Belediye Başkanlığı": "Başkan a. / Müdür",
    "Ankara İl Millî Eğitim Müdürlüğü": "Müdür a. / Şube Müdürü",
    "Gazi Üniversitesi Rektörlüğü": "Rektör a. / Genel Sekreter",
    "Gazi Üniversitesi": "Rektör a. / Genel Sekreter",
}


def _gonderen_unvani(e: dict) -> str:
    ad = e["gonderen"].get("kurum_adi") or ""
    if ad in _GONDEREN_UNVAN:
        return _GONDEREN_UNVAN[ad]
    if any(k in ad for k in ("Okulu", "Lisesi", "Ortaokulu")):
        return "Okul Müdürü"
    if "İlçe" in ad:
        return "İlçe Millî Eğitim Müdürü"
    if "Dekanlığı" in ad:
        return "Dekan"
    if "Enstitüsü" in ad:
        return "Müdür"
    if "Daire Başkanlığı" in ad:
        return "Daire Başkanı"
    return "Müdür"


# Dış kurumların iletişim bilgisi. Kurgusal ama tutarlı: aynı kurum her
# belgede aynı adresi taşır. Gerçek adres kullanmak gereksiz risk;
# kurum adları zaten gerçek.
_DIS_KURUM_ILETISIM = {
    "Millî Eğitim Bakanlığı": {
        "adres": "Atatürk Bulvarı No: 98 Bakanlıklar ÇANKAYA/ANKARA",
        "telefon": "0312 413 10 00", "kep_adresi": "meb@hs01.kep.tr"},
    "İçişleri Bakanlığı": {
        "adres": "İnönü Bulvarı No: 4 Bakanlıklar ÇANKAYA/ANKARA",
        "telefon": "0312 422 40 00", "kep_adresi": "icisleri@hs01.kep.tr"},
    "Çevre, Şehircilik ve İklim Değişikliği Bakanlığı": {
        "adres": "Mustafa Kemal Mah. Dumlupınar Bulvarı No: 278 ÇANKAYA/ANKARA",
        "telefon": "0312 410 10 00", "kep_adresi": "csb@hs01.kep.tr"},
    "Yükseköğretim Kurulu Başkanlığı": {
        "adres": "Üniversiteler Mah. 1600. Cadde No: 10 Bilkent ÇANKAYA/ANKARA",
        "telefon": "0312 298 70 00", "kep_adresi": "yok@hs01.kep.tr"},
    "Ankara Valiliği": {
        "adres": "Ulus Meydanı ALTINDAĞ/ANKARA",
        "telefon": "0312 306 60 00", "kep_adresi": "ankara@hs01.kep.tr"},
    "Yenimahalle Kaymakamlığı": {
        "adres": "Ragıp Tüzün Cad. No: 45 YENİMAHALLE/ANKARA",
        "telefon": "0312 315 12 00", "kep_adresi": "yenimahalle@hs01.kep.tr"},
    "Ankara Büyükşehir Belediye Başkanlığı": {
        "adres": "Emniyet Mah. Hipodrom Cad. No: 5 YENİMAHALLE/ANKARA",
        "telefon": "0312 507 10 00", "kep_adresi": "abb@hs01.kep.tr"},
    "Çankaya Belediye Başkanlığı": {
        "adres": "Ziyabey Cad. No: 9 Balgat ÇANKAYA/ANKARA",
        "telefon": "0312 458 89 00", "kep_adresi": "cankaya@hs03.kep.tr"},
}


def gonderen_iletisimi(e: dict, kurum_json: dict | None = None) -> dict:
    """Gönderenin iletişim bilgisi.

    Üç kurumumuzdan biriyse kendi kurum.json'undan, dış kurumsa
    yukarıdaki tablodan gelir.
    """
    ad = e["gonderen"].get("kurum_adi") or ""
    if ad in _DIS_KURUM_ILETISIM:
        return _DIS_KURUM_ILETISIM[ad]
    if kurum_json and ad == kurum_json.get("kurum_adi"):
        return kurum_json.get("iletisim", {})
    # Kurum içi birim: alıcı kurumun iletişim bilgisi geçerli
    if kurum_json and not ad.endswith(("Bakanlığı", "Valiliği",
                                       "Kaymakamlığı")):
        return kurum_json.get("iletisim", {})
    return {}


def _hitap_kur(e: dict) -> str:
    """Muhatap adını yönelme hâline çevirir (Yönetmelik m.14)."""
    m = e.get("muhatap_makam") or e["alici"]["kurum_adi"]
    if m == "DAĞITIM YERLERİNE":
        return m
    son = m.strip()
    if son.endswith(("ğı", "ği", "ğu", "ğü")):
        return tr_buyut(son + "na")
    if son.endswith(("lık", "lik", "luk", "lük")):
        return tr_buyut(son + "a")
    if son.endswith(("i", "ı", "u", "ü", "e", "a")):
        return tr_buyut(son + "ne")
    return tr_buyut(son + "e")


# =============================================================================
# KUSUR
# =============================================================================


@dataclass
class Kusur:
    """Bu belgeye hangi ALAN kusuru uygulanacak.

    Gövde kusurları (ilgi_kopuk, kapanis_yanlis) ADIM 4.5'te metne
    uygulandı; buradakiler belge alanlarına uygulanır.
    """

    tur: str | None = None
    ayrinti: dict | None = None

    def var_mi(self, ad: str) -> bool:
        return self.tur == ad


# =============================================================================
# KURUM YAZISI
# =============================================================================


def kurum_yazisi_ciz(c, e: dict, govde: str, kusur: Kusur) -> None:
    """Bir kurum yazısını sayfaya çizer."""
    c.setFillColorRGB(0, 0, 0)

    # --- amblem (sol üst) ---------------------------------------------------
    # Kılavuz s.11: logo üstten 0,5 cm, soldan 1,5 cm. Logo kullanılsa
    # bile BAŞLIK yine 1,5 cm'den başlar — logo başlığı aşağı itmez.
    _amblem_ciz(c, _amblem_tipi(e), SOL, SAYFA_Y - AMBLEM_UST - AMBLEM_BOY)

    # --- başlık bloğu -------------------------------------------------------
    # Yönetmelik m.10/2: ortalanmış, azami 4 satır (K s.13). Logo kenarda
    # durduğu için çakışma olmaz (logo 15-35 mm, başlık 50-160 mm).
    y = SAYFA_Y - UST
    c.setFillColorRGB(0, 0, 0)
    for i, satir in enumerate(_baslik_kur(e)[:4]):
        c.setFont(KALIN if i <= 1 else NORMAL, PUNTO)
        c.drawCentredString(SAYFA_G / 2, y, satir)
        y -= SATIR

    # Yönetmelik m.11/2: başlık ile sayı arası 2 satır boşluk
    y -= 2 * SATIR

    # --- sayı / tarih -------------------------------------------------------
    # Yönetmelik m.15/3: "Sayı", "Konu" ve "İlgi" yan başlıklarından
    # sonraki İKİ NOKTA AYNI HİZADA yazılır.
    sayi_metni = "" if kusur.var_mi("sayi_eksik") else (e.get("sayi") or "")
    c.setFont(NORMAL, PUNTO)
    c.drawString(SOL, y, "Sayı")
    c.drawString(IKI_NOKTA_X, y, ":")
    c.drawString(DEGER_X, y, sayi_metni)
    # m.12/1: tarih sayı ile AYNI SATIRDA, yazı alanının en sağında
    if not kusur.var_mi("tarih_eksik"):
        c.drawRightString(SOL + YAZI_G, y, e["tarih"])
    y -= SATIR

    # --- konu ---------------------------------------------------------------
    # m.13/1: konu yazı alanının DİKEY ORTA HİZASINI geçemez.
    if not kusur.var_mi("konu_eksik"):
        c.drawString(SOL, y, "Konu")
        c.drawString(IKI_NOKTA_X, y, ":")
        y = _yaz_sarmali(c, e["konu"], DEGER_X, y, KONU_AZAMI_G)

    # --- ilgi ---------------------------------------------------------------
    if e.get("ilgi"):
        tarih = e["ilgi"]["tarih"]
        if kusur.var_mi("tarih_tutarsiz") and kusur.ayrinti:
            tarih = kusur.ayrinti.get("enjekte_edilen", tarih)
        metin = f"{tarih} tarihli ve {e['ilgi']['sayi']} sayılı yazı."
        c.setFont(NORMAL, PUNTO)
        c.drawString(SOL, y, "İlgi")
        c.drawString(IKI_NOKTA_X, y, ":")
        # m.15/4: devam satırları yan başlığın altı boş bırakılarak
        y = _yaz_sarmali(c, metin, DEGER_X, y, SOL + YAZI_G - DEGER_X)

    # m.14/1: konu ile muhatap arası 2 satır boşluk
    y -= 2 * SATIR

    # --- hitap --------------------------------------------------------------
    if kusur.var_mi("muhatap_belirsiz"):
        hitap, parantez = "İLGİLİ MAKAMA", None
    else:
        hitap = _hitap_kur(e)
        parantez = e.get("muhatap_parantez")
    c.setFont(NORMAL, PUNTO)
    c.drawCentredString(SAYFA_G / 2, y, hitap)
    y -= SATIR
    if parantez:
        # M-07: parantez içi birime yönelme hâl eki GETİRİLMEZ
        c.drawCentredString(SAYFA_G / 2, y, f"({parantez})")
        y -= SATIR
    # m.16/2: ilgi varsa 1 satır, yoksa 2 satır boşluk
    y -= (1 if e.get("ilgi") else 2) * SATIR

    # --- gövde --------------------------------------------------------------
    y = _govde_ciz(c, govde, y, SOL, YAZI_G)

    # --- imza ---------------------------------------------------------------
    if not kusur.var_mi("imza_eksik"):
        # m.17/1: "Metnin bitiminden itibaren İKİ İLÂ DÖRT SATIR boşluk
        # bırakılarak, ... yazı alanının en sağında ORTALANARAK".
        #
        # "Ortalanarak" sağa dayalı demek DEĞİL: blok sağ yarıya yerleşir
        # ve satırlar bloğun İÇİNDE ortalanır. Gerçek belgelerde ad ve
        # unvan satırlarının merkezleri 1 mm içinde çakışıyor.
        y -= 3 * SATIR
        c.setFont(NORMAL, PUNTO)
        c.drawCentredString(IMZA_MERKEZ_X, y, e.get("imzalayan_ad", "Ad SOYAD"))
        y -= SATIR
        unvan = e.get("imzalayan_unvan") or _gonderen_unvani(e)
        # m.17/9: yetki devri ibaresi ("Bakan a.") ikinci satırda
        for parca in str(unvan).split(" / "):
            c.drawCentredString(IMZA_MERKEZ_X, y, parca)
            y -= SATIR

    # --- ek -----------------------------------------------------------------
    if e.get("ek"):
        # m.18/1: "imza bölümünden sonra uygun satır boşluğu bırakılarak,
        # yazı alanının SOLUNDAN". Yönetmelik sayı vermiyor; gerçek
        # belgelerde 1-5 satır arası, 2 varsayılan.
        y -= 2 * SATIR
        sayfa = e["ek"].get("sayfa", 1)
        if kusur.var_mi("ek_beyani_yanlis") and kusur.ayrinti:
            sayfa = kusur.ayrinti.get("enjekte_edilen", sayfa)
        # m.18/2: adet/sayfa parantez içinde
        y = _yaz(c, f"Ek: {e['ek']['aciklama']} ({sayfa} sayfa)", SOL, y)

    # --- dağıtım ------------------------------------------------------------
    if e.get("dagitim"):
        y -= SATIR
        y = _yaz(c, "DAĞITIM:", SOL, y)
        for m in e["dagitim"].get("geregi", []):
            y = _yaz(c, m, SOL, y)
        if e["dagitim"].get("bilgi"):
            y = _yaz(c, "Bilgi:", SOL, y)
            for m in e["dagitim"]["bilgi"]:
                y = _yaz(c, m, SOL, y)

    _dipnot_ciz(c, e)


def _dipnot_ciz(c, e: dict) -> None:
    """Sayfa altı iletişim bilgileri (Kılavuz s.79).

    ÇİZGİNİN ÜSTÜNDE (2 satır):
      1. ORTALANMIŞ: "Bu belge, güvenli elektronik imza ile imzalanmıştır."
      2. SOLDA doğrulama kodu, SAĞDA takip adresi

    AYIRICI ÇİZGİ zorunlu (Y m.23/1), yazı alanı genişliğince.

    ÇİZGİNİN ALTINDA:
      SOLDA adres/telefon/faks/e-posta/KEP, SAĞDA "Bilgi için:"

    Sayfa numarası iletişim bilgilerinin ALTINDA ve sayfa ORTASINDA
    (Y m.27/1).
    """
    kod = _dogrulama_kodu(e["belge_no"])
    cizgi_y = DIPNOT_CIZGI_ALTTAN
    c.setFont(NORMAL, PUNTO_KUCUK)
    c.setFillColorRGB(0.25, 0.25, 0.3)

    # --- çizginin üstü ------------------------------------------------------
    c.drawCentredString(SAYFA_G / 2, cizgi_y + 2.2 * SATIR,
                        "Bu belge, güvenli elektronik imza ile imzalanmıştır.")
    c.drawString(SOL, cizgi_y + 1.2 * SATIR, f"Belge Doğrulama Kodu: {kod}")
    c.drawRightString(SOL + YAZI_G, cizgi_y + 1.2 * SATIR,
                      "Belge Takip Adresi: https://www.turkiye.gov.tr/ebys")

    # --- ayırıcı çizgi (Y m.23/1) -------------------------------------------
    c.setStrokeColorRGB(0.45, 0.45, 0.5)
    c.setLineWidth(0.5)
    c.line(SOL, cizgi_y, SOL + YAZI_G, cizgi_y)

    # --- çizginin altı ------------------------------------------------------
    # İletişim bilgisi GÖNDERENE ait. Belgeyi bakanlık yazıyorsa altında
    # belediyenin adresi olamaz.
    ile = e.get("gonderen_iletisim") or {}
    y = cizgi_y - SATIR * 0.85
    adres = ile.get("adres") or e["gonderen"].get("kurum_adi", "")
    if adres:
        c.drawString(SOL, y, adres[:88])
        y -= SATIR * 0.85
    satir2 = " ".join(p for p in (
        f"Telefon: {ile['telefon']}" if ile.get("telefon") else "",
        f"Faks: {ile['faks']}" if ile.get("faks") else "",
        f"e-Posta: {ile['eposta']}" if ile.get("eposta") else "") if p)
    if satir2:
        c.drawString(SOL, y, satir2[:88])
        y -= SATIR * 0.85
    if ile.get("kep_adresi"):
        c.drawString(SOL, y, f"KEP Adresi: {ile['kep_adresi']}")

    if e.get("bilgi_icin"):
        c.drawRightString(SOL + YAZI_G, cizgi_y - SATIR * 0.85,
                          f"Bilgi için: {e['bilgi_icin']}")

    # --- karekod (Y m.24/1): iletişim alanının EN SAĞI ----------------------
    try:
        w = qr.QrCodeWidget(
            f"{e['gonderen'].get('kurum_adi', '')}|{e.get('sayi', '')}|"
            f"https://www.turkiye.gov.tr/ebys|{kod}")
        b = w.getBounds()
        d = Drawing(QR_BOY, QR_BOY,
                    transform=[QR_BOY / (b[2] - b[0]), 0, 0,
                               QR_BOY / (b[3] - b[1]), 0, 0])
        d.add(w)
        renderPDF.draw(d, c, SOL + YAZI_G - QR_BOY, ALT + 2 * mm)
    except Exception:
        # QR çizilemezse belge yine de geçerli; sessizce atlanır.
        pass

    # --- sayfa numarası (Y m.27/1) -----------------------------------------
    c.setFont(NORMAL, PUNTO_KUCUK)
    c.drawCentredString(SAYFA_G / 2, ALT, "1/1")
    c.setFillColorRGB(0, 0, 0)


# =============================================================================
# VATANDAŞ DİLEKÇESİ
# =============================================================================


def dilekce_ciz(c, e: dict, govde: str, kusur: Kusur) -> None:
    """Vatandaş/öğrenci dilekçesi.

    BAŞLIK BLOĞU, SAYI VE KONU SATIRI YOKTUR. Belge doğrudan muhatap
    makamla başlar.

    Kurum yazısından üç yapısal farkı:
      1. Kendi kenar boşlukları (üst 2, sol/sağ/alt 2,5 cm)
      2. Alt blok İKİ SÜTUN: solda kimlik/adres/telefon, sağda tarih ve
         imza. Sol sola dayalı, sağ sağa dayalı.
      3. Ek listesi "EKLER:" başlığıyla ve sol kenardan
    """
    # Belge tamamen siyah. Amblem ve dipnot çiziminde gri kullanılıyor;
    # dilekçede o bölümler yok ama durum sızıntısına karşı sıfırlanıyor.
    c.setFillColorRGB(0, 0, 0)
    c.setStrokeColorRGB(0, 0, 0)
    y = SAYFA_Y - D_UST - 3 * SATIR

    # --- hitap --------------------------------------------------------------
    if kusur.var_mi("muhatap_belirsiz"):
        hitap, parantez = "İLGİLİ MAKAMA", None
    else:
        hitap = _hitap_kur(e)
        parantez = e.get("muhatap_parantez")

    c.setFont(NORMAL, PUNTO)
    c.drawCentredString(SAYFA_G / 2, y, hitap)
    y -= SATIR
    if parantez:
        c.drawCentredString(SAYFA_G / 2, y, f"({parantez})")
        y -= SATIR
    y -= 3 * SATIR

    # --- gövde --------------------------------------------------------------
    y = _govde_ciz(c, govde, y, D_SOL, D_YAZI_G)

    # --- alt blok: İKİ SÜTUN, aynı hizadan başlar --------------------------
    #
    # Ölçülen hata: sağ sütun (tarih/ad/imza) ile sol sütun (kimlik/
    # adres/telefon) üst üste iki KAT hâlinde yazılıyordu. Gerçek dilekçe
    # formlarında ikisi YAN YANA durur.
    #
    # TAMAMI GÖVDE PUNTOSUNDA. Önce küçük punto kullanılmıştı ve yazılar
    # soluk görünüyordu.
    y -= 3 * SATIR
    ust_y = y
    g = e["gonderen"]
    sag_kenar = SAYFA_G - D_SAG

    c.setFillColorRGB(0, 0, 0)
    c.setFont(NORMAL, PUNTO)

    # SAĞ SÜTUN — tarih, ad, imza (sağa dayalı)
    sag_y = ust_y
    if not kusur.var_mi("tarih_eksik"):
        c.drawRightString(sag_kenar, sag_y, e["tarih"])
        sag_y -= SATIR
    if not kusur.var_mi("imza_eksik"):
        sag_y -= SATIR * 0.4
        ad = g.get("ad", "")
        c.drawRightString(sag_kenar, sag_y, ad)
        sag_y -= SATIR
        # "İmza" ADIN ORTASINA hizalanır: blok sağa dayalı ama içindeki
        # satırlar birbirine göre ortalı durur.
        ad_g = c.stringWidth(ad, NORMAL, PUNTO)
        c.drawCentredString(sag_kenar - ad_g / 2, sag_y, "İmza")
        # "İmza" satırının ALTINDA ıslak imza için boşluk; dilekçe
        # e-imzalı değildir.
        sag_y -= SATIR * 1.6

    # SOL SÜTUN — kimlik ve iletişim (sola dayalı)
    # 3071 m.4 zorunlu: ad-soyad, imza, adres. TCKN ve telefon kanunen
    # zorunlu değil ama kurum formları çoğunlukla istiyor.
    sol_y = ust_y
    c.setFont(NORMAL, PUNTO)
    if g.get("tckn"):
        c.drawString(D_SOL, sol_y, f"T.C. Kimlik No: {g['tckn']}")
        sol_y -= SATIR
    if g.get("ogrenci_no"):
        c.drawString(D_SOL, sol_y, f"Öğrenci No: {g['ogrenci_no']}")
        sol_y -= SATIR
    adres = g.get("adres", "")
    if adres:
        # Adres sağ sütuna taşmamalı
        etiket_g = c.stringWidth("Adres: ", NORMAL, PUNTO)
        adres_g = (sag_kenar - 60 * mm) - (D_SOL + etiket_g)
        c.drawString(D_SOL, sol_y, "Adres:")
        for satir in _sar(c, adres, adres_g, NORMAL, PUNTO):
            c.drawString(D_SOL + etiket_g, sol_y, satir)
            sol_y -= SATIR
    if g.get("telefon"):
        c.drawString(D_SOL, sol_y, f"Telefon: {g['telefon']}")
        sol_y -= SATIR

    # Ek listesi iki sütunun ALTINDAN başlar
    y = min(sol_y, sag_y)

    # --- ek listesi (SOL kenar, "EKLER:") ----------------------------------
    # Dilekçede "EKLER:" kullanılıyor — resmî yazının "Ek:" biçiminden
    # farklı. Norm yok, gerçek formlardan gözlem.
    if e.get("ek"):
        y -= 2 * SATIR
        adet = e["ek"].get("adet", 1)
        if kusur.var_mi("ek_beyani_yanlis") and kusur.ayrinti:
            adet = kusur.ayrinti.get("enjekte_edilen", adet)
        c.setFillColorRGB(0, 0, 0)
        y = _yaz(c, "EKLER:", D_SOL, y)
        _yaz(c, f"{adet} Adet {e['ek']['aciklama']}", D_SOL, y)


# =============================================================================
# GİRİŞ NOKTASI
# =============================================================================


def belge_ciz(yol: Path, e: dict, govde: str,
              kusur: Kusur | None = None) -> None:
    """Bir belgeyi PDF olarak yazar.

    Kimlik ve telefon numaraları burada eklenir — üreteçte değil.
    Üreteci değiştirmek rastgele seçim sırasını kaydırır ve 300 etiketin
    tamamını değiştirir; üretilmiş gövdeler geçersiz olur. Bu numaralar
    belge numarasından türetilir, tekrarlanabilir.
    """
    # Modül `src/` içine konulup "src.pdf_render" olarak da, doğrudan da
    # çağrılabilir. İki import yolu da denenir.
    try:
        from src.kimlik_uretici import kisi_bilgileri_ekle
    except ImportError:
        from kimlik_uretici import kisi_bilgileri_ekle

    e = kisi_bilgileri_ekle(e)
    fontlari_kaydet()
    kusur = kusur or Kusur()

    c = rl_canvas.Canvas(str(yol), pagesize=A4)
    c.setTitle(f"Belge {e['belge_no']}")
    c.setAuthor(e["gonderen"].get("kurum_adi") or e["gonderen"].get("ad", ""))
    c.setSubject(e.get("konu", ""))

    if e["yazan_tipi"] == "kurum":
        kurum_yazisi_ciz(c, e, govde, kusur)
    else:
        dilekce_ciz(c, e, govde, kusur)
    c.save()
