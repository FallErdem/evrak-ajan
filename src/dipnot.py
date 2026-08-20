"""Sayfa dipnotunu gövdeden ayırır.

SORUN
-----
Resmî yazının altında e-imza bloğu vardır: doğrulama kodu, adres, telefon,
KEP adresi, sayfa numarası. Bunlar gövde metnine karışırsa her şey bozulur —
özet dipnotu anlatır, varlık çıkarımı kurumun telefonunu vatandaşın telefonu
sanır, üslup denetimi olmayan cümleleri denetler.

TUZAK
-----
Anahtar kelimeyle ayırmak YANLIŞTIR. Ölçüldü:

  Kurum yazısında  "Telefon: 0312 315 12 00"   -> dipnot, atılmalı
  Dilekçede        "Telefon: 0508 481 37 25"   -> GÖVDE, kalmalı

Dilekçenin altındaki blok (T.C. Kimlik No, Adres, İmza, Telefon) vatandaşın
kimlik bloğudur ve 3071 sayılı Kanun m.4'ün istediği şeydir. Atılırsa
cevap anahtarındaki TCKN, adres ve telefon kaybolur — üstelik bunlar KVKK
kapsamındaki varlıklar, yani maskelenmesi gereken şeyler.

ÇÖZÜM
-----
İki koşul BİRLİKTE aranır:

  1. Konum   satır sayfanın alt %25'inde mi
  2. İçerik  satırda e-imza dipnotuna özgü bir iz var mı

Ölçüm (16 belgelik örneklem, 10 metin katmanlı):

  gövdenin en aşağı indiği yer     530 punto
  eşik (842 * 0.75)                631 punto
  dipnotun en yukarı çıktığı yer   710 punto
  dilekçe kimlik bloğunun en altı  325 punto

İki yönde de geniş pay var. Eşik sayfa yüksekliğine oranlı tutuldu ki
A4 dışı bir boyut gelirse de çalışsın.

Not: Bu ayrım bizim ürettiğimiz veri setinde deterministik olabilir, çünkü
yerleşim ölçüleri sabitlenmiş ve gövde taşarsa üretici SayfaTasmasi hatası
veriyor (PARCA2_DEVIR_NOTLARI 6.2). Ancak eşik değeri veri/sablon/yerlesim.yaml
KAYNAĞINDAN DEĞİL, 10 belgelik örneklemden ölçülerek türetildi — kaynakla
karşılaştırılması bekliyor.

Aynı şekilde DIPNOT_IZLERI listesi 10 belgede görülen varyantları kapsıyor.
Devir notları 5.5 belge doğrulama kodunun etiket metninin kuruma göre
değiştiğini söylüyor; listenin 300 belgenin tamamını kapsadığı
dipnot_dogrula.py ile ölçülmeden varsayılmamalıdır.

Gerçek dünyada bu kadar temiz olmaz; raporda böyle yazılacak.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# -----------------------------------------------------------------------------
# Ayarlar
# -----------------------------------------------------------------------------

# Sayfanın alt kaçta kaçı dipnot bölgesi sayılsın.
#
# Değer keyfi değil, iki uçtan sıkıştırılarak seçildi:
#
#   ALT SINIR  gövdenin en aşağı indiği yer          530 pt  (187 mm)  ölçüm
#   ÜST SINIR  dipnotun en yukarı çıktığı yer        710 pt  (250 mm)  ölçüm
#
# Üst sınır kaynakla da uyuşuyor: yerlesim.yaml `dipnot.cizgi_alttan: 33 mm`
# diyor (gözlem, 32-34 mm aralığı). Ayırıcı çizgi alttan 33 mm ise sayfa
# üstünden 264 mm'de; çizginin ÜSTÜNDE iki satır dipnot metni var
# (K s.79 yapısı), satır aralığı 14,6 pt ≈ 5,2 mm. 264 - 2×5,2 ≈ 254 mm.
# Ölçülen 250 mm bu hesabın ±3 mm gözlem toleransı içinde.
#
# 0.75 -> A4'te 631 pt (222 mm). Gövdeden 35 mm, dipnottan 28 mm uzakta.
# Sayfa yüksekliğine oranlı tutuldu ki A4 dışı bir boyutta da anlamlı kalsın.
DIPNOT_BOLGESI = 0.75

# Dipnota özgü GÜÇLÜ izler. Kaynak: yerlesim.yaml `dogrulama_kodu.etiketler`
# ve belge_sablonu.json `dipnot_alani.bilesenler`.
#
# Etiket metni kuruma göre değişiyor, üç varyantın hepsi kapsanıyor:
#   üniversite / belediye : "Belge Doğrulama Kodu :"  "Belge Takip Adresi :"
#   il müdürlüğü          : "Doğrulama Kodu:"         "Doğrulama Adresi:"
#
# DİKKAT: buraya "Telefon:", "Adres:", "e-Posta:" gibi genel ifadeler
# EKLENMEZ. Dilekçe gövdesinde geçiyorlar. Konum koşulu onları zaten
# koruyor ama listeyi de temiz tutmak gerekiyor — iki savunma hattı.
DIPNOT_IZLERI = (
    "güvenli elektronik imza",
    "doğrulama kodu",
    "doğrulama adresi",
    "belge takip adresi",
    "kep adresi",
)

# ZAYIF izler — yalnızca güçlü iz hiç bulunamazsa bakılır.
#
# Gerekçe: belge_sablonu.json `dipnot_alani.eimza_oncesi` şunu söylüyor —
# "E-imza öncesi yazılarda doğrulama kodu ve QR yoktur; yalnızca adres
# bloğu ve 'Bilgi için' bulunur." Böyle bir belge veri setinde varsa güçlü
# izlerin hiçbiri tutmaz ve dipnotun TAMAMI gövdeye sızar.
#
# Veri setinin tamamı 2026 tarihli olduğu için bu varyantın bulunmaması
# beklenir, ama beklenti ölçüm değildir. Zayıf eşleşme olduğunda sonuç
# `zayif_eslesme=True` ile işaretlenir; dipnot_dogrula.py bunları ayrıca
# raporlar ki gözle bakılabilsin.
DIPNOT_IZLERI_ZAYIF = (
    "bilgi için:",
    "faks:",
)

# Sayfa numarası: "1/1", "2/5". Dipnot bölgesindeyse atılır.
SAYFA_NO_IZI = "/"


@dataclass
class Satir:
    """Konumuyla birlikte tek satır."""

    y: float
    metin: str
    sayfa: int = 1


@dataclass
class AyrilmisMetin:
    """Ayrıştırma sonucu."""

    govde: str
    dipnot: str
    govde_satirlari: list[Satir] = field(default_factory=list)
    dipnot_satirlari: list[Satir] = field(default_factory=list)
    dipnot_bulundu: bool = False
    zayif_eslesme: bool = False
    esik_y: float = 0.0

    @property
    def ozet(self) -> str:
        return (
            f"gövde {len(self.govde_satirlari)} satır / "
            f"dipnot {len(self.dipnot_satirlari)} satır"
        )


# Gövdede asla meşru olarak bulunamayacak sabit dipnot cümleleri.
#
# Neden gerekli: OCR bazen dipnot cümlesini gövdenin son satırına yapıştırıyor
# (ölçüldü, belge_020):
#
#     "Ek: Tapu fotokopisi (3 Sayfa) Bu belge; güvenli elektronik imza ile..."
#
# Öğenin kutusu Ek satırından başladığı için konum kuralı bunu yakalayamıyor.
# Bu cümleler DEĞİŞMEZ kalıplardır (Y m.23/1, K s.79); silinmeleri gerçek
# içeriği yok edemez. Metin ONARILMIYOR, yalnızca sabit kalıp çıkarılıyor.
KALIP_CUMLELER = (
    r"Bu belge[,;:]?\s*güvenli elektronik imza ile imzalan\w*\.?",
    r"Belge Doğrulama Kodu\s*[:：]?\s*[A-Z0-9\-]{8,}",
    r"Doğrulama Kodu\s*[:：]?\s*[A-Z0-9\-]{8,}",
)


def kalip_cumleleri_ayikla(metin: str) -> tuple[str, list[str]]:
    """Sabit dipnot kalıplarını satırdan çıkarır. (temiz_metin, cikarilanlar)"""
    cikarilan: list[str] = []

    def _yakala(m: re.Match) -> str:
        cikarilan.append(m.group(0).strip())
        return " "

    temiz = metin
    for kalip in KALIP_CUMLELER:
        temiz = re.sub(kalip, _yakala, temiz, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", temiz).strip(), cikarilan


def _dipnot_izi_var(metin: str, zayif: bool = False) -> bool:
    kucuk = metin.casefold()
    izler = DIPNOT_IZLERI_ZAYIF if zayif else DIPNOT_IZLERI
    return any(iz in kucuk for iz in izler)


def _sayfa_numarasi_mi(metin: str) -> bool:
    """'1/1' veya '2/5' gibi."""
    parcalar = metin.strip().split(SAYFA_NO_IZI)
    return (
        len(parcalar) == 2
        and all(p.strip().isdigit() for p in parcalar)
        and len(metin.strip()) <= 8
    )


def _kaliplari_temizle(satirlar: list[Satir]) -> tuple[list[Satir], list[Satir]]:
    """Gövde satırlarından yapışık dipnot kalıplarını ayıklar.

    Çıkarılanlar dipnot listesine ekleniyor ki hiçbir şey kaybolmasın —
    sadece yer değiştirsin.
    """
    temiz: list[Satir] = []
    tasan: list[Satir] = []
    for s in satirlar:
        yeni, cikarilan = kalip_cumleleri_ayikla(s.metin)
        if cikarilan:
            tasan.append(Satir(y=s.y, metin=" ".join(cikarilan), sayfa=s.sayfa))
        if yeni:
            temiz.append(Satir(y=s.y, metin=yeni, sayfa=s.sayfa))
    return temiz, tasan


def dipnotu_ayir(satirlar: list[Satir], sayfa_yuksekligi: float) -> AyrilmisMetin:
    """Satırları gövde ve dipnot diye ikiye ayırır.

    Mantık: dipnot bölgesinde bir iz bulunursa, o satırdan aşağısının TAMAMI
    dipnottur. Blok hâlinde kesilir, satır satır elenmez — çünkü dipnotun
    adres satırında hiçbir iz yoktur ama doğrulama kodu satırının altındadır.

    Hiç iz bulunmazsa dipnot yoktur (dilekçe) ve her şey gövdedir. Bu
    varsayılan güvenli olan: şüphede kalırsa metni SİLMEZ.
    """
    esik = sayfa_yuksekligi * DIPNOT_BOLGESI
    sirali = sorted(satirlar, key=lambda s: s.y)

    baslangic = None
    zayif = False
    for i, s in enumerate(sirali):
        if s.y >= esik and _dipnot_izi_var(s.metin):
            baslangic = i
            break

    if baslangic is None:
        # Güçlü iz yok. E-imza öncesi biçim olabilir (belge_sablonu.json
        # dipnot_alani.eimza_oncesi). Zayıf izlere bakılır ve işaretlenir.
        for i, s in enumerate(sirali):
            if s.y >= esik and _dipnot_izi_var(s.metin, zayif=True):
                baslangic = i
                zayif = True
                break

    if baslangic is None:
        # Dipnot yok. Yine de dipnot bölgesindeki yalnız sayfa numarasını at.
        govde = [
            s
            for s in sirali
            if not (s.y >= esik and _sayfa_numarasi_mi(s.metin))
        ]
        atilan = [s for s in sirali if s not in govde]
        govde, tasan = _kaliplari_temizle(govde)
        atilan = atilan + tasan
        return AyrilmisMetin(
            govde="\n".join(s.metin for s in govde),
            dipnot="\n".join(s.metin for s in atilan),
            govde_satirlari=govde,
            dipnot_satirlari=atilan,
            dipnot_bulundu=False,
            zayif_eslesme=False,
            esik_y=esik,
        )

    govde_s = sirali[:baslangic]
    dipnot_s = sirali[baslangic:]
    govde_s, tasan = _kaliplari_temizle(govde_s)
    dipnot_s = dipnot_s + tasan
    return AyrilmisMetin(
        govde="\n".join(s.metin for s in govde_s),
        dipnot="\n".join(s.metin for s in dipnot_s),
        govde_satirlari=govde_s,
        dipnot_satirlari=dipnot_s,
        dipnot_bulundu=True,
        zayif_eslesme=zayif,
        esik_y=esik,
    )


# -----------------------------------------------------------------------------
# pdfplumber köprüsü — metin katmanlı PDF'ler için
# -----------------------------------------------------------------------------


def pdfden_satirlar(sayfa, yuvarlama: int = 0) -> list[Satir]:
    """pdfplumber sayfasından satır listesi üretir.

    Kelimeler y konumuna göre gruplanır. Aynı satırdaki kelimeler x'e göre
    sıralanır — yoksa "Sayı : E-... 28.04.2026" bozuk sırayla çıkar.
    """
    gruplar: dict[float, list] = {}
    for w in sayfa.extract_words():
        anahtar = round(w["top"], yuvarlama)
        gruplar.setdefault(anahtar, []).append(w)

    satirlar = []
    for y in sorted(gruplar):
        kelimeler = sorted(gruplar[y], key=lambda w: w["x0"])
        satirlar.append(Satir(y=y, metin=" ".join(w["text"] for w in kelimeler)))
    return satirlar
