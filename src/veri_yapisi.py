#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
veri_yapisi.py — Sistemin ortak veri yapısı

TEKNOFEST 2026 · Yapay Zekâ Dil Ajanları Yarışması · 1. Senaryo

Bir evrağın kuruma ulaşmasından taslak yazının üretilmesine kadar geçen bütün
yolculuğu tek bir nesnede tutar. Ajanlar bu nesneyi sırayla doldurur.

TASARIM KURALI — Parça 2'de dondurulur:
    Alan SİLİNMEZ, sadece EKLENİR. Bir ajan bir alana güvenerek yazıldıysa,
    o alanın adı ve tipi projenin sonuna kadar aynı kalır.

ALAN ADLARI NEREDEN GELİYOR:
    rules.yaml'daki 104 kural alanlara yol dizeleriyle atıfta bulunuyor
    (yol: ustveri.sayi, yol: cikti_yazi.metin gibi). Buradaki adlar o
    yollarla birebir aynı tutulmuştur. Ad değiştirmek kural motorunu bozar.

Bölümler (parca_1_detay.md ADIM 5):
     1 Kimlik            8 Mevzuat önerileri
     2 Gelen kayıt       9 Özet
     3 Kaynak           10 Çıktı yazı
     4 Başlık bloğu     11 Yönlendirme
     5 Üstveri          12 Karar
     6 Sınıflandırma    13 İz
     7 Bilgi unsurları

Bu dosya dört bölümde yazıldı:
    1. Sözlük  — izinli değerler                          [BU BÖLÜM]
    2. Kanıt   — güven ve kaynak
    3. Belge   — üstveri ve gövde
    4. Dosya   — kök nesne, yardımcılar, kendi testi

Kaynaklar:
    Y = Resmî Yazışmalarda Uygulanacak Usul ve Esaslar Hakkında Yönetmelik
        (10.06.2020 tarihli ve 31151 sayılı RG)
    K = Aynı Yönetmeliğin Kılavuzu (Cumhurbaşkanlığı, Şubat 2025)
    G = Gizlilik Dereceli Belgelerde Uygulanacak Usul ve Esaslar Hakkında
        Yönetmelik (26.04.2022 tarihli ve 31821 sayılı RG)
    Ş = TEKNOFEST 2026 1. Senaryo Şartnamesi
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from enum import StrEnum
from typing import NamedTuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Veri yapısının sürümü. Alan eklendikçe küçük numara artar.
# Üretilen her dosyaya yazılır; eski çıktıların hangi sürümle üretildiği belli olur.
SURUM = "1.0.0"


# =============================================================================
# 1. BELGE TÜRLERİ — iki ayrı eksen
# =============================================================================
#
# Karıştırılması kolay olduğu için ayrı tutuluyor:
#
#   GelenTur       kuruma ULAŞAN evrağın türü. Sınıflandırma ajanı belirler.
#   UretilecekTur  bizim ÜRETECEĞİMİZ yazının türü. Taslak ajanı belirler.
#
# Örnek: vatandaş dilekçesi gelir (GelenTur), biz cevap yazısı üretiriz
# (UretilecekTur). İkisi aynı belge değildir.


class GelenTur(StrEnum):
    """Kuruma ulaşan evrağın türü."""

    # Kurumdan kuruma yazışmalar
    UST_YAZI = "ust_yazi"
    CEVAP_YAZISI = "cevap_yazisi"
    BILGILENDIRME_YAZISI = "bilgilendirme_yazisi"
    TALEP_YAZISI = "talep_yazisi"
    TEKIT_YAZISI = "tekit_yazisi"          # daha önce yazılana hatırlatma, K 30
    OLUR_YAZISI = "olur_yazisi"            # makam onayı, Y m.17
    # Aşağıdaki ikisinin Yönetmelik'te tanımlı karşılığı YOKTUR; sahada
    # kullanıldıkları için ve risk testinde modeller bu adları ürettiği için
    # listede tutuluyorlar. Parça 4'te etiketli veriye bakıldığında gerçekten
    # ayırt edilebiliyorlar mı diye sınanacak.
    DUYURU = "duyuru"
    GENELGE = "genelge"

    # Gerçek kişiden gelen belgeler
    VATANDAS_DILEKCESI = "vatandas_dilekcesi"
    BILGI_EDINME_BASVURUSU = "bilgi_edinme_basvurusu"
    SIKAYET = "sikayet"

    # Model emin olamadığında. Bu değerin varlığı bir tasarım tercihidir:
    # emin olmadığında tahmin eden bir sistem, sessizce yanlış karar üretir.
    BILINMIYOR = "bilinmiyor"


class UretilecekTur(StrEnum):
    """Üreteceğimiz yazının türü.

    İlk üçü şartname 6.4.2'nin adıyla saydığı türler; sistemin bunları
    üretebilmesi zorunlu. Sonrakiler şartnamenin "alternatif bir resmi
    yazışma türü" ifadesinin karşılığı.
    """

    UST_YAZI = "ust_yazi"                          # Ş 6.4.2
    CEVAP_YAZISI = "cevap_yazisi"                  # Ş 6.4.2
    BILGILENDIRME_YAZISI = "bilgilendirme_yazisi"  # Ş 6.4.2
    OLUR_YAZISI = "olur_yazisi"
    TEKIT_YAZISI = "tekit_yazisi"
    EKSIK_BILGI_TALEBI = "eksik_bilgi_talebi"      # Ş 6.4.2: "gerekli durumlarda
                                                   # eksik bilgi talep edebilmesi"
    TASLAK_GEREKMEZ = "taslak_gerekmez"            # yalnızca bilgi için gelen evrak


# rules.yaml kuralları "kapsam: kurum_yazisi" gibi KATEGORİ adları kullanıyor.
# Kategori bir tür değil, türler kümesidir. Kural motoru bu haritayla eşleştirir.
KATEGORILER: dict[str, frozenset[GelenTur]] = {
    "kurum_yazisi": frozenset({
        GelenTur.UST_YAZI,
        GelenTur.CEVAP_YAZISI,
        GelenTur.BILGILENDIRME_YAZISI,
        GelenTur.TALEP_YAZISI,
        GelenTur.TEKIT_YAZISI,
        GelenTur.OLUR_YAZISI,
        GelenTur.DUYURU,
        GelenTur.GENELGE,
    }),
    "kisi_belgesi": frozenset({
        GelenTur.VATANDAS_DILEKCESI,
        GelenTur.BILGI_EDINME_BASVURUSU,
        GelenTur.SIKAYET,
    }),
}


def kapsama_girer_mi(tur: GelenTur | str | None, kapsam: str) -> bool:
    """Bir belge türü, verilen kapsamın içinde mi.

    Kapsam bir kategori adı ("kurum_yazisi") ya da doğrudan bir tür adı
    ("tekit_yazisi") olabilir; rules.yaml ikisini de kullanıyor.
    """
    if tur is None:
        return False
    tur = str(tur)
    if kapsam in KATEGORILER:
        return tur in {str(t) for t in KATEGORILER[kapsam]}
    return tur == kapsam


# =============================================================================
# 2. İVEDİLİK — Y m.26/1, K 23  (rules.yaml G-03, G-04)
# =============================================================================


class Ivedilik(StrEnum):
    """Süreli yazışma ibaresi. Boş bırakılabilir (süresiz belge)."""

    ACELE = "ACELE"
    GUNLUDUR = "GÜNLÜDÜR"


# Kılavuz 23 bu ibareleri açıkça yasaklıyor. Metinde geçerse hata üretilecek.
# Sözlük olarak burada duruyor ki hem linter hem taslak üreteci aynı listeyi
# kullansın.
YASAKLI_IVEDILIK = ("ÇOK ACELE", "ÇOK İVEDİ", "İVEDİ", "ACİL")


# =============================================================================
# 3. GİZLİLİK DERECESİ — G Yönetmeliği, K 22  (rules.yaml G-01, G-02, EK-05)
# =============================================================================


class GizlilikDerecesi(StrEnum):
    """Millî gizlilik dereceleri.

    "Özel" derecesi 2022'de kaldırıldı; bilerek listede yok (G-02).
    Derecesiz belge için alan boş bırakılır.
    """

    HIZMETE_OZEL = "Hizmete Özel"
    GIZLI = "Gizli"
    COK_GIZLI = "Çok Gizli"


# EK-05: "Ek gizlilik derecesi üst yazıyı aşamaz" kuralı derecelerin
# birbirine göre sırasını bilmeyi gerektiriyor: yok < Hizmete Özel < Gizli < Çok Gizli
_GIZLILIK_SIRASI: dict[str | None, int] = {
    None: 0,
    GizlilikDerecesi.HIZMETE_OZEL: 1,
    GizlilikDerecesi.GIZLI: 2,
    GizlilikDerecesi.COK_GIZLI: 3,
}


def gizlilik_seviyesi(derece: GizlilikDerecesi | str | None) -> int:
    """Gizlilik derecesini karşılaştırılabilir bir sayıya çevirir."""
    if derece is None:
        return 0
    return _GIZLILIK_SIRASI.get(str(derece), 0)


# =============================================================================
# 4. GİRDİ VE DAĞITIM
# =============================================================================


class GirdiTipi(StrEnum):
    """Evrağın sisteme hangi biçimde geldiği. OCR gerekip gerekmediğini belirler."""

    PDF_METINLI = "pdf_metinli"      # metin katmanı var, OCR gerekmez
    PDF_TARAMA = "pdf_tarama"        # görüntü, OCR gerekir
    GORUNTU = "goruntu"              # jpg/png tarama
    DUZ_METIN = "duz_metin"          # txt, doğrudan okunur
    DOCX = "docx"


class DagitimTuru(StrEnum):
    """Y m.19/2 — dağıtım listesindeki muhatabın konumu."""

    GEREGI = "geregi"    # işlemi yapacak olan
    BILGI = "bilgi"      # yalnızca haberdar olacak


class Onem(StrEnum):
    """Linter bulgusunun ağırlığı. rules.yaml'ın 'onem' alanıyla aynı."""

    HATA = "hata"        # yalnızca bu düzeyde bulgu belgeyi geçersiz kılar
    UYARI = "uyari"
    BILGI = "bilgi"


class MuhatapTuru(StrEnum):
    """Muhatabın hukuki niteliği.

    Kapanış ifadesini ve muhatap yazım kurallarını belirliyor:
    M-04/M-05/M-06/M-12 gerçek kişiye, ME-06 kamu dışı tüzel kişiye özel.
    """

    KAMU_IDARESI = "kamu_idaresi"
    GERCEK_KISI = "gercek_kisi"
    OZEL_HUKUK_TUZEL_KISI = "ozel_hukuk_tuzel_kisi"   # şirket, dernek, vakıf
    DAGITIM_YERLERI = "dagitim_yerleri"               # M-11, çok muhataplı
    BILINMIYOR = "bilinmiyor"


class Teskilat(StrEnum):
    """İdarenin merkez mi taşra mı olduğu.

    B-06 merkez biriminin idare adıyla birlikte yazılmasını, B-08 taşrada
    mülki idare bilgisinin bulunmasını istiyor; ikisi de bu ayrımı gerektirir.
    """

    MERKEZ = "merkez"
    TASRA = "tasra"
    BILINMIYOR = "bilinmiyor"


class HiyerarsiYonu(StrEnum):
    """Muhatabın gönderene göre konumu.

    Metnin "arz ederim" mi "rica ederim" mi diye bitmesi buna bağlı (ME-02).
    Alt kurumdan üst kuruma arz, diğer hâllerde rica edilir.
    """

    UST = "ust"          # muhatap daha üst konumda  -> "Arz ederim."
    AYNI = "ayni"        # aynı düzey                -> "Rica ederim."
    ALT = "alt"          # muhatap daha alt konumda  -> "Rica ederim."
    KURUM_DISI = "kurum_disi"
    GERCEK_KISI = "gercek_kisi"   # ME-05 -> "Saygılarımla." vb.


# =============================================================================
# 5. BİLGİ UNSURLARI VE KİŞİSEL VERİ — Ş madde 14 (KVKK)
# =============================================================================


class VarlikTipi(StrEnum):
    """Belgeden çıkarılan bilgi unsurunun türü."""

    KISI_ADI = "kisi_adi"
    TCKN = "tckn"
    IBAN = "iban"
    TELEFON = "telefon"
    EPOSTA = "eposta"
    ADRES = "adres"
    KURUM_ADI = "kurum_adi"
    BIRIM_ADI = "birim_adi"
    UNVAN = "unvan"
    TARIH = "tarih"
    SURE = "sure"
    TUTAR = "tutar"
    MEVZUAT_ATFI = "mevzuat_atfi"
    BELGE_REFERANSI = "belge_referansi"   # başka bir yazının sayısı
    YER = "yer"
    DIGER = "diger"


# Şartname takımı kişisel verilerin korunması mevzuatına uymakla yükümlü
# tutuyor. Maskeleme Parça 3'te yazılacak, ama hangi tipin kişisel veri
# sayıldığı şimdiden burada tanımlı olmalı — yoksa her ajan kendi listesini
# uydurur ve biri unutur.
KISISEL_VERI_TIPLERI: frozenset[VarlikTipi] = frozenset({
    VarlikTipi.KISI_ADI,
    VarlikTipi.TCKN,
    VarlikTipi.IBAN,
    VarlikTipi.TELEFON,
    VarlikTipi.EPOSTA,
    VarlikTipi.ADRES,
})


def kisisel_veri_mi(tip: VarlikTipi | str) -> bool:
    """Bu varlık tipi kişisel veri sayılır mı."""
    return str(tip) in {str(t) for t in KISISEL_VERI_TIPLERI}


# =============================================================================
# 6. KANIT YÖNTEMLERİ VE AJANLAR
# =============================================================================


class KanitYontemi(StrEnum):
    """Bir alanın hangi yolla doldurulduğu.

    İzlenebilirlik için gerekli: "bu bilgiyi düzenli ifadeyle mi buldun,
    modele mi sordun" sorusunun cevabı. Model çıktısı ile kesin eşleşme
    aynı güvenilirlikte değildir.
    """

    REGEX = "regex"              # düzenli ifade, deterministik
    SOZLUK = "sozluk"            # sabit liste eşleşmesi
    KURAL = "kural"              # rules.yaml kuralı
    LLM = "llm"                  # dil modeli çıkarımı
    OCR = "ocr"                  # metin katmanından/OCR'dan doğrudan
    HESAPLAMA = "hesaplama"      # başka alanlardan türetildi
    INSAN = "insan"              # kullanıcı girdi veya düzeltti
    VARSAYILAN = "varsayilan"    # hiçbir kanıt yok, öntanımlı değer


# Ajan kimlikleri. Kasıtlı olarak StrEnum değil — ajan listesi Parça 3-8
# boyunca netleşecek ve katı bir küme her eklemede bu dosyayı değiştirmeyi
# gerektirir. Aşağıdaki liste bir sözleşme değil, adlandırma referansıdır.
AJANLAR = (
    "a1_okuma",            # Parça 3 — OCR / metin çıkarma
    "a2_ayristirma",       # Parça 3 — alanlara bölme
    "a3_siniflandirma",    # Parça 4 — belge türü
    "a4_sdp",              # Parça 4 — standart dosya planı kodu
    "a5_bilgi_cikarma",    # Parça 5 — varlıklar
    "a6_eksik_tespit",     # Parça 5 — eksik alanlar
    "a7_mevzuat",          # Parça 6 — mevzuat eşleştirme
    "a8_ozet",             # Parça 6 — özet
    "a9_tur_karari",       # Parça 7 — hangi yazı üretilecek
    "a10_taslak",          # Parça 7 — taslak metin
    "a11_linter",          # Parça 7 — kural denetimi
    "a12_yonlendirme",     # Parça 8 — birim önerisi
)


# =============================================================================
# 7. ALAN YOLLARI — rules.yaml ile sözleşme
# =============================================================================
#
# rules.yaml kuralları bu dizelerle alanlara atıfta bulunuyor. Kanıt haritası
# da aynı anahtarları kullanır, böylece "hangi kural hangi alana bakıyor" ve
# "o alan nereden geldi" soruları aynı dille cevaplanır.
#
# Bu küme aynı zamanda bir emniyet kemeri: kanıt eklerken yanlış yol yazılırsa
# yakalanır (bkz. Bölüm 4'teki kanit_ekle).

ALAN_YOLLARI: frozenset[str] = frozenset({
    # Gelen kayıt
    "gelen_kayit.kayit_sayisi",
    "gelen_kayit.kayit_tarihi",
    "gelen_kayit.havale_edilen_birimler",
    # Kaynak
    "kaynak.dosya",
    "kaynak.ham_metin",
    "kaynak.sayfalar",
    # Başlık bloğu
    "baslik.tc_var",
    "baslik.idare_adi",
    "baslik.birim_adi",
    # Üstveri
    "ustveri.sayi",
    "ustveri.tarih",
    "ustveri.tarih_metin",
    "ustveri.konu",
    "ustveri.gonderen",
    "ustveri.muhatap",
    "ustveri.muhatap.idare",
    "ustveri.muhatap.birim",
    "ustveri.ilgi",
    "ustveri.ekler",
    "ustveri.dagitim",
    "ustveri.ivedilik",
    "ustveri.gizlilik_derecesi",
    "ustveri.miat",
    "ustveri.imza",
    "ustveri.imza.ad",
    "ustveri.imza.unvan",
    # Alt bilgi
    "altbilgi.iletisim",
    "altbilgi.dogrulama_metni",
    # Metin
    "metin",
    # Sınıflandırma
    "siniflandirma.belge_turu",
    "siniflandirma.sdp.kod",
    "siniflandirma.saklama_suresi",
    # İçerik
    "icerik.talep",
    "icerik.ozet",
    # Çıktı
    "cikti_yazi.tur",
    "cikti_yazi.konu",
    "cikti_yazi.metin",
    # Yönlendirme
    "yonlendirme.hedef_birim",
})


# =============================================================================
# BÖLÜM 2 — KANIT
# =============================================================================
#
# Sistemin her iddiası bir kanıta bağlanır: "bu belgenin konusu şudur" derken
# nereden çıkardığımızı, hangi yöntemle bulduğumuzu ve ne kadar emin olduğumuzu
# da söyleriz.
#
# Bunun iki gerekçesi var. Birincisi şartname: 6.4.1 evrağın "ilgili mevzuata
# göre değerlendirilmesini", 6.4.2 ise "kullanıcıya süreç hakkında açık ve
# anlaşılır bilgilendirme" sunulmasını istiyor. İkincisi pratik: kaynağı
# gösterilemeyen bir çıkarım, kamu evrak sürecinde kullanılamaz.
#
# TASARIMI BELİRLEYEN İKİ ÖLÇÜM
#
# Parça 1 risk testi iki şey gösterdi ve ikisi de buraya yansıdı:
#
#   1. Modeller aralık dışı güven üretiyor. Şema 0-1 aralığını zorlamıyor;
#      703.487 ve 90.0 gibi değerler geldi. Bu yüzden güven ham hâliyle kabul
#      edilmiyor, doğrulanıyor (bkz. Kanit._guveni_dogrula).
#
#   2. Modellerin güveni kalibre değil. Yanlış cevaplarda ortalama güven
#      qwen3.5:9b'de 0.79, turkish-gemma-9b'de 0.938 çıktı. Yani modelin
#      "eminim" demesi doğru olduğu anlamına gelmiyor. Bu yüzden güvenin
#      HANGİ YÖNTEMLE elde edildiği ayrıca tutuluyor: düzenli ifadeyle bulunan
#      bir sayının güveni ile modelin beyan ettiği güven aynı şey değildir.


# Modelin kendi beyan ettiği güven. Ölçüldü, kalibre değil — tek başına
# karar eşiği olarak kullanılmamalı.
BEYAN_YONTEMLERI: frozenset[KanitYontemi] = frozenset({
    KanitYontemi.LLM,
})

# Güveni yapısal olarak belli olan yöntemler. Düzenli ifade eşleştiyse eşleşmiştir;
# burada güven modelin kanaati değil, işlemin kesinliğidir.
KESIN_YONTEMLER: frozenset[KanitYontemi] = frozenset({
    KanitYontemi.REGEX,
    KanitYontemi.SOZLUK,
    KanitYontemi.KURAL,
    KanitYontemi.HESAPLAMA,
    KanitYontemi.INSAN,
})


def beyan_mi(yontem: KanitYontemi | str) -> bool:
    """Bu yöntemin güveni modelin kendi beyanı mı."""
    return str(yontem) in {str(y) for y in BEYAN_YONTEMLERI}


# Karar eşikleri. BAŞLANGIÇ DEĞERLERİDİR — Parça 8'de değerlendirme setiyle
# kalibre edilecek. Risk testinde qwen3.5:9b yanlış cevaplarında ortalama 0.79
# güven verdi; bu, 0.60 gibi bir eşiğin hiçbir şey elemeyeceği anlamına gelir.
ESIK_OTOMATIK_ONAY = 0.85    # bunun üstü insana sorulmadan geçebilir
ESIK_INSAN_ONAYI = 0.60      # bunun altı mutlaka insana gider


class Konum(BaseModel):
    """Bilginin belgede nerede geçtiği.

    Arayüzde belgeyi vurgulamak için gerekli: kullanıcı bir alana tıkladığında
    o bilginin belgenin neresinden geldiğini görebilmeli.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    sayfa: int = Field(default=1, ge=1)
    satir: int | None = Field(default=None, ge=1)
    baslangic: int | None = Field(
        default=None, ge=0, description="sayfa metni içindeki karakter ofseti"
    )
    bitis: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _aralik_tutarli(self) -> Konum:
        if (self.baslangic is not None and self.bitis is not None
                and self.bitis < self.baslangic):
            raise ValueError(
                f"Konum aralığı ters: baslangic={self.baslangic} > bitis={self.bitis}"
            )
        return self


class Kanit(BaseModel):
    """Bir alanın değerinin arkasındaki dayanak.

    Değerin kendisini tutmaz — değer alanın kendi yerinde durur. Bu kutu
    yalnızca "nereden geldi, ne kadar güveniyoruz" sorusunu cevaplar.

    Kanıtlar değiştirilemez (frozen). Bir alan yeniden hesaplanırsa yeni bir
    kanıt üretilir; eskisinin üzerine yazılmaz. Böylece "bu değeri kim, ne
    zaman, neye dayanarak koydu" sorusu her zaman cevaplanabilir.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    yontem: KanitYontemi
    ureten: str = Field(description="ajan kimliği, ör. 'a2_ayristirma'")

    guven: float = Field(default=0.0, ge=0.0, le=1.0)
    guven_gecerliydi: bool = Field(
        default=True,
        description="Ham güven değeri 0-1 aralığında mıydı. False ise model "
                    "sözleşme dışı bir değer üretti ve güven 0.0'a çekildi.",
    )
    guven_ham: str | None = Field(
        default=None,
        description="Aralık dışıysa modelin verdiği özgün değer, denetim için.",
    )

    alinti: str | None = Field(
        default=None, max_length=300,
        description="Belgeden birebir alıntı. Uzun tutulmaz; kanıt, belgenin "
                    "kopyası değil işaretidir.",
    )
    konum: Konum | None = None

    model: str | None = Field(
        default=None, description="LLM kullanıldıysa model adı, ör. 'qwen3.5:9b'"
    )
    kural_id: str | None = Field(
        default=None, description="rules.yaml kuralından geldiyse kural kimliği"
    )
    aciklama: str | None = Field(default=None, max_length=300)

    zaman: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="before")
    @classmethod
    def _guveni_dogrula(cls, veri):
        """Aralık dışı güveni 0.0'a çeker ve bunu işaretler.

        NEDEN 0.0, NEDEN EN YAKIN SINIRA YUVARLAMA DEĞİL:
        Model 90.0 yazdığında bunu 1.0'a çekmek, sözleşmeye uymayan bir cevabı
        "azami güven" hâline getirir ve otomatik onaydan geçirir. Oysa aralık
        dışı bir değerin tek dürüst yorumu şudur: bu modelin güven çıktısına
        güvenilemez. Güvenilemeyen güvenin karşılığı 0'dır — alan insan
        onayına düşer. Yüzdelik sanıp 100'e bölmek de yapılmıyor; 703.487
        yüzdelik değildir, niyet tahmin edilmez.

        Ham değer guven_ham alanında saklanıyor: modelin kalibrasyonunu
        ölçmek isteyen biri bu bilgiyi kaybetmiş olmuyor.
        """
        if not isinstance(veri, dict):
            return veri
        if "guven" not in veri:
            return veri

        ham = veri["guven"]
        if ham is None:
            veri["guven"] = 0.0
            veri["guven_gecerliydi"] = False
            return veri

        # bool, int'in alt sınıfı; True'nun 1.0 sayılmasını istemiyoruz
        if isinstance(ham, bool) or not isinstance(ham, (int, float)):
            veri["guven"] = 0.0
            veri["guven_gecerliydi"] = False
            veri["guven_ham"] = str(ham)[:100]
            return veri

        if not (0.0 <= float(ham) <= 1.0):
            veri["guven"] = 0.0
            veri["guven_gecerliydi"] = False
            veri["guven_ham"] = str(ham)[:100]
            return veri

        veri["guven"] = float(ham)
        return veri

    @property
    def beyan_edilen_guven_mi(self) -> bool:
        """Güven, modelin kendi kanaati mi (kalibre olmayabilir)."""
        return beyan_mi(self.yontem)

    @property
    def otomatik_gecebilir_mi(self) -> bool:
        """Bu kanıt tek başına insan onayı olmadan geçmeye yeter mi."""
        if not self.guven_gecerliydi:
            return False
        return self.guven >= ESIK_OTOMATIK_ONAY

    def __str__(self) -> str:
        p = f"{self.yontem}·{self.ureten}·{self.guven:.2f}"
        return p + ("" if self.guven_gecerliydi else " (güven geçersizdi)")


# -----------------------------------------------------------------------------
# Güven karşılaştırma ve birleştirme
# -----------------------------------------------------------------------------


def daha_guvenilir(yeni: Kanit, mevcut: Kanit) -> bool:
    """Yeni kanıt, mevcut kanıtın yerini almalı mı.

    Sıralama önce YÖNTEME, sonra güvene bakar. Sebebi şu: düzenli ifadeyle
    çıkarılmış bir sayının üzerine, modelin 0.95 güvenle beyan ettiği başka
    bir sayının yazılmasını istemiyoruz. Model kendinden emin olabilir ama
    düzenli ifade metinde gerçekten eşleşmiştir.

    İnsan girdisi her şeyi geçer — kullanıcı düzeltmesi nihaidir.
    """
    if mevcut.yontem == KanitYontemi.INSAN:
        return yeni.yontem == KanitYontemi.INSAN
    if yeni.yontem == KanitYontemi.INSAN:
        return True

    yeni_kesin = not beyan_mi(yeni.yontem)
    mevcut_kesin = not beyan_mi(mevcut.yontem)
    if yeni_kesin != mevcut_kesin:
        return yeni_kesin

    return yeni.guven > mevcut.guven


def en_zayif_halka(kanitlar: list[Kanit] | dict[str, Kanit]) -> float:
    """Bir kanıt kümesinin toplam güveni.

    En düşük güveni döndürür. Ortalama veya çarpım değil, bilerek:

    - ORTALAMA yanıltıcı. Dokuz alanı 0.95, bir alanı 0.10 güvenle bulmuş bir
      belgenin ortalaması 0.86 çıkar ve otomatik onaydan geçer. Oysa o tek
      alan yanlışsa üretilen yazı da yanlıştır.
    - ÇARPIM aşırı karamsar. Bağımsızlık varsayar; 20 alanın her biri 0.95
      olsa bile çarpım 0.36'ya iner ve hiçbir belge geçemez.

    Zincir en zayıf halkası kadar sağlamdır. Hangi halkanın zayıf olduğunu
    görmek isteyen zayif_alanlar() kullanır.
    """
    degerler = list(kanitlar.values()) if isinstance(kanitlar, dict) else list(kanitlar)
    if not degerler:
        return 0.0
    return min(k.guven for k in degerler)


def zayif_alanlar(
    kanitlar: dict[str, Kanit], esik: float = ESIK_INSAN_ONAYI
) -> list[tuple[str, float]]:
    """Eşiğin altında kalan alanlar, en düşükten başlayarak.

    Parça 8'in "insana neyi sorayım" listesi ve arayüzün "şu alanları kontrol
    edin" uyarısı buradan beslenecek.
    """
    dusuk = [
        (yol, k.guven) for yol, k in kanitlar.items()
        if not k.guven_gecerliydi or k.guven < esik
    ]
    return sorted(dusuk, key=lambda x: x[1])


def bilinen_ajan_mi(ureten: str) -> bool:
    """Ajan kimliği planlanan listede geçiyor mu.

    Hata üretmez, yalnızca bilgi verir; ajan listesi kasıtlı olarak açık uçlu.
    """
    return ureten in AJANLAR


# =============================================================================
# BÖLÜM 3 — BELGE
# =============================================================================
#
# Resmî yazının kendi anatomisi. Alan adları rules.yaml'ın yol dizeleriyle
# hizalı, bölümlendirme Yönetmelik'in madde sırasını izliyor.
#
# HER YERDE GEÇEN DESEN: ham + çözümlenmiş
#
# Kuralların büyük bölümü değerin KENDİSİNİ değil, YAZILIŞINI denetliyor:
#
#   M-02  "idare adı büyük harfle ve hâl eki almış olmalı"
#   M-06  "gerçek kişide soyadı büyük harf"
#   K-02  "konu sonunda noktalama olmaz"
#   I-07  "ilgi kalıbı ve nokta"
#   T-02  "tarih gg.aa.yyyy veya '10 Ekim 2019' biçiminde"
#
# Çözümlenmiş bir değer bu soruları cevaplayamaz. "ANKARA VALİLİĞİNE" ile
# "Ankara Valiliği"nin çözümlenmiş hâli aynı, yazılışı farklıdır ve kural
# yazılışa bakar. Bu yüzden alanların çoğu iki hâlde tutuluyor:
#
#   ham     belgede yazdığı gibi, hiç dokunulmadan
#   (diğer) ayrıştırılmış, hesaplanabilir hâl
#
# Plan bu deseni tarih için zaten öngörmüştü (tarih / tarih_metin); burada
# tutarlılık için muhatap, imza, ilgi, ek ve konuya da yayıldı.


class Taraf(BaseModel):
    """Gönderen veya muhatap.

    M bölümündeki 12 kural bu yapıyı denetliyor. `ham` alanı olmadan
    yarısı çalışamaz.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    ham: str | None = Field(
        default=None, max_length=500,
        description="Belgede yazdığı hâliyle, ör. 'TARIM VE ORMAN BAKANLIĞINA'",
    )
    tur: MuhatapTuru = MuhatapTuru.BILINMIYOR

    idare: str | None = Field(default=None, description="ör. 'Tarım ve Orman Bakanlığı'")
    birim: str | None = Field(
        default=None,
        description="parantez içinde yazılan birim, ör. 'Bitkisel Üretim Genel Müdürlüğü'",
    )
    ad: str | None = Field(default=None, description="gerçek kişi ise adı soyadı")
    unvan: str | None = None
    detsis_no: str | None = Field(
        default=None,
        description="DETSİS Devlet Teşkilatı Numarası; B-05 ve S-02 bunu kullanır",
    )
    teskilat: Teskilat = Teskilat.BILINMIYOR

    @property
    def dagitimli_mi(self) -> bool:
        """Muhatap 'DAĞITIM YERLERİNE' mi (M-11, D-01)."""
        return self.tur == MuhatapTuru.DAGITIM_YERLERI


class Imza(BaseModel):
    """İmza bloğu.

    IM bölümündeki 9 kural buraya bakıyor. Yetki devri ("Bakan a.", "Vali a.")
    ve vekâlet ("V.") ayrı alanlarda; IM-06 ve IM-07 bunların biçimini
    denetliyor ve ikisi birbirine karıştırılmamalı.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    ham: str | None = Field(default=None, max_length=300)
    ad: str | None = Field(default=None, description="ör. 'Kemal DOĞANAY'")
    unvan: str | None = Field(default=None, description="ör. 'İl Müdürü'")
    yetki_devri: str | None = Field(
        default=None, description="ör. 'Bakan a.', 'Vali a.', 'Rektör a.'"
    )
    vekaleten: bool = Field(
        default=False, description="unvandan sonra 'V.' ibaresi var mı"
    )


class Ilgi(BaseModel):
    """İlgi tutulan belge.

    I bölümündeki 10 kural burayı denetliyor. `idare` alanı I-08 için gerekli:
    ilgi üçüncü bir kuruma aitse idare adı yazılmalı, muhataba veya bize aitse
    yazılmamalı. Türkçe eki hangi durumun geçerli olduğunu söylüyor —
    "yazımız" bizim, "yazınız" muhatabın, "yazısı" üçüncü kurumun.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    ham: str | None = Field(default=None, max_length=500)
    sira: str | None = Field(
        default=None, max_length=4,
        description="I-06 gereği a, b, c... Tek ilgi varsa harf kullanılmaz.",
    )
    tarih: date | None = None
    tarih_metin: str | None = None
    sayi: str | None = None
    idare: str | None = Field(
        default=None, description="üçüncü kuruma aitse o kurumun adı (I-08)"
    )
    aciklama: str | None = Field(default=None, max_length=300)


class Ek(BaseModel):
    """Belge eki.

    `gizlilik_derecesi` EK-05 için: ekin gizlilik derecesi üst yazınınkinden
    yüksek olamaz. Bu, ekleri ayrı bir nesne yapmayı gerektiren tek alan —
    düz metin listesi olsaydı kural denetlenemezdi.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    ham: str | None = Field(default=None, max_length=300)
    sira: int | None = Field(default=None, ge=1, description="EK-03; tek ekte boş")
    aciklama: str | None = Field(default=None, max_length=300)
    sayfa_sayisi: int | None = Field(
        default=None, ge=1, description="EK-01 gereği parantez içinde belirtilir"
    )
    gizlilik_derecesi: GizlilikDerecesi | None = None
    konulmadi: bool = Field(default=False, description="EK-06 'Ek konulmadı'")


class DagitimSatiri(BaseModel):
    """Dağıtım listesindeki tek muhatap.

    D-02 gereği "Gereği" ve "Bilgi" ayrımı tutulur. D-03 protokol sırasını
    denetleyeceği için `sira` korunuyor — liste yeniden sıralanırsa özgün
    sıra kaybolur ve kural çalışamaz.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    hedef: str = Field(max_length=300)
    tur: DagitimTuru = DagitimTuru.GEREGI
    sira: int | None = Field(default=None, ge=1)
    detsis_no: str | None = None


class BaslikBlogu(BaseModel):
    """Belgenin tepesindeki T.C. / idare / birim bloğu.

    B bölümündeki 8 kural buraya bakıyor.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    ham: str | None = Field(default=None, max_length=500)
    tc_var: bool | None = Field(
        default=None, description="B-01; vatandaş dilekçesinde bulunmaz"
    )
    idare_adi: str | None = Field(default=None, description="B-02, büyük harfle")
    birim_adi: str | None = Field(default=None, description="B-03, ilk harfler büyük")
    mulki_idare: str | None = Field(
        default=None, description="B-08, taşra teşkilatında ör. 'ANKARA VALİLİĞİ'"
    )
    teskilat: Teskilat = Teskilat.BILINMIYOR
    detsis_no: str | None = Field(default=None, description="B-05 kontrolü için")


class AltBilgi(BaseModel):
    """Belgenin alt kısmındaki iletişim ve doğrulama blokları.

    Plan'ın alan listesinde yoktu; GN-05 ve GN-06 kurallarını okurken ortaya
    çıktı. GN-06 iletişim bilgilerinin bulunmasını, GN-05 elektronik imzalı
    belgede doğrulama bilgisinin yer almasını istiyor.

    Ayrıca kişisel veri açısından dikkat gerektiren bir bölge: telefon ve
    e-posta burada bulunur.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    ham: str | None = Field(default=None, max_length=1000)
    adres: str | None = None
    telefon: str | None = None
    faks: str | None = None
    eposta: str | None = None
    web: str | None = None
    ayrintili_bilgi: str | None = Field(
        default=None, description="'Ayrıntılı bilgi için:' satırı"
    )
    dogrulama_metni: str | None = Field(
        default=None, description="GN-05, 5070 sayılı Kanun ibaresi"
    )
    dogrulama_adresi: str | None = None
    dogrulama_kodu: str | None = None


class GelenKayit(BaseModel):
    """Alıcı kurumun evrak kayıt damgası.

    Belgenin KENDİ sayısıyla karıştırılmamalı — bu, belgeyi alan kurumun
    kendi defterine kaydettiği numaradır (Y m.31/5, Örnek 23). YÖK belgesinin
    tepesindeki "Evrak Tarih ve Sayısı: 24/10/2019-20842" bu bloktur ve
    S-04'ün kısa çizgi kuralına tabi değildir.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    ham: str | None = Field(default=None, max_length=300)
    kayit_sayisi: str | None = None
    kayit_tarihi: date | None = None
    havale_edilen_birimler: list[str] = Field(default_factory=list)


class KaynakBilgisi(BaseModel):
    """Evrağın sisteme nereden ve nasıl geldiği.

    `sayfalar` bir metin listesi. Çok sayfalı belgelerde GN-02 ve GN-03
    "başlık sadece ilk sayfada, imza sadece son sayfada" diyor; bu soruya
    ancak sayfa sayfa metin varsa cevap verilebilir. Tek parça `ham_metin`
    yeterli olmuyor.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    dosya: str | None = None
    girdi_tipi: GirdiTipi = GirdiTipi.DUZ_METIN
    sayfalar: list[str] = Field(default_factory=list)
    ham_metin: str | None = Field(
        default=None, description="normalize edilmiş tam metin"
    )
    ocr_motoru: str | None = None
    ocr_guven: float | None = Field(default=None, ge=0.0, le=1.0)

    @property
    def sayfa_sayisi(self) -> int:
        return len(self.sayfalar) if self.sayfalar else 1


class Ustveri(BaseModel):
    """Belgenin üstveri elemanları — Y m.10-19.

    Y m.28/3: "Elektronik ortamda güvenli elektronik imza ile imzalanan
    belgenin üstveri elemanları, belgenin ayrılmaz bir bütünüdür. Tarih ve
    sayı gibi belge görüntüsü üzerinde yer alan bilgiler ile üstveride yer
    alan bilgiler arasında fark olamaz."

    Bu madde GN-01 ve T-04 kurallarının dayanağı ve neden hem `tarih` hem
    `tarih_metin` tuttuğumuzu açıklıyor: biri belgede görünen, diğeri
    üstveride kayıtlı olan. İkisinin farklı olması başlı başına bir hatadır.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    # Sayı — S bölümü, 7 kural
    sayi: str | None = Field(
        default=None, max_length=100,
        description="E-DETSİS-SDP-kayıtno biçiminde; vatandaş dilekçesinde bulunmaz",
    )

    # Tarih — T bölümü, 4 kural
    tarih: date | None = Field(default=None, description="çözümlenmiş hâl")
    tarih_metin: str | None = Field(
        default=None, max_length=50,
        description="belgede yazdığı hâl, ör. '12.05.2026' veya '10 Ekim 2019'",
    )

    # Konu — K bölümü, 5 kural
    konu: str | None = Field(default=None, max_length=250)

    # Taraflar — M bölümü, 12 kural
    gonderen: Taraf = Field(default_factory=Taraf)
    muhatap: Taraf = Field(default_factory=Taraf)

    # İlgi, ek, dağıtım — I, EK, D bölümleri
    ilgi: list[Ilgi] = Field(default_factory=list)
    ekler: list[Ek] = Field(default_factory=list)
    dagitim: list[DagitimSatiri] = Field(default_factory=list)

    # Gizlilik ve süreli yazışma — G bölümü, 8 kural
    ivedilik: Ivedilik | None = None
    gizlilik_derecesi: GizlilikDerecesi | None = None
    miat: date | None = Field(
        default=None, description="G-05: GÜNLÜDÜR ise dolu olmalı"
    )

    # İmza — IM bölümü, 9 kural
    imza: Imza = Field(default_factory=Imza)

    @property
    def dagitimli_mi(self) -> bool:
        """Belge birden fazla muhataba mı gidiyor (D-01, M-11, ME-04)."""
        return bool(self.dagitim) or self.muhatap.dagitimli_mi

    @property
    def azami_ek_gizliligi(self) -> int:
        """Eklerin en yüksek gizlilik seviyesi — EK-05 için."""
        if not self.ekler:
            return 0
        return max(gizlilik_seviyesi(e.gizlilik_derecesi) for e in self.ekler)


# -----------------------------------------------------------------------------
# Sayı ayrıştırma — S-02, S-03, S-07
# -----------------------------------------------------------------------------

# Y m.11/1: hazırlanma süreci harfi + DETSİS numarası + standart dosya planı
# kodu + kayıt numarası, aralarına kısa çizgi.
_SAYI_DESENI = re.compile(r"^([EZO])-(\d{6,10})-(\d{3}(?:\.\d{2}){0,3})-(\d+)$")


class SayiBolumleri(NamedTuple):
    """Sayının dört bölümü. rules.yaml 'ustveri.sayi[bolum:3]' ile SDP'yi ister."""

    surec: str      # bölüm 1 — E, Z veya O
    detsis: str     # bölüm 2
    sdp: str        # bölüm 3 — standart dosya planı kodu
    kayit_no: str   # bölüm 4


def sayi_bolumleri(sayi: str | None) -> SayiBolumleri | None:
    """Sayıyı dört bölüme ayırır; biçim tutmuyorsa None döner.

    S-07 kuralı bu ayrıştırmaya dayanıyor: sayının üçüncü bölümündeki dosya
    planı kodu ile belgeye atanan SDP kodu aynı olmalı. Yani sayısı olan bir
    kurum yazısında SDP kodunu tahmin etmeye gerek yok — okunur.
    """
    if not sayi:
        return None
    m = _SAYI_DESENI.match(sayi.strip())
    if not m:
        return None
    return SayiBolumleri(*m.groups())


if __name__ == "__main__":
    print(f"veri_yapisi.py sürüm {SURUM}")
    print(f"  gelen belge türü      : {len(GelenTur)}")
    print(f"  üretilecek yazı türü  : {len(UretilecekTur)}")
    print(f"  varlık tipi           : {len(VarlikTipi)} "
          f"({len(KISISEL_VERI_TIPLERI)} tanesi kişisel veri)")
    print(f"  tanımlı alan yolu     : {len(ALAN_YOLLARI)}")
