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
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Veri yapısının sürümü. Alan eklendikçe küçük numara artar.
# Üretilen her dosyaya yazılır; eski çıktıların hangi sürümle üretildiği belli olur.
SURUM = "1.2.0"


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

    # 1.2.0'da eklendi — veri setinde var, şemada yoktu.
    #
    # Ölçüldü (300 etiket): itiraz 11, gorus_talebi 20 belge. Bu iki değer
    # olmadan 31 belgede DOĞRU cevap fiziksel olarak verilemiyordu: Anlama'nın
    # şeması bu enum'dan üretiliyor ve model enum dışına çıkamıyor.
    #
    # ADIM 4 kapısı belge türü macro-F1 >= 0.85 istiyor. İki sınıf sıfır
    # kalırsa 11 sınıflı ortalamanın tavanı 9/11 = 0.818'dir; eşik
    # matematiksel olarak geçilemezdi.
    #
    # Değer EKLENDİ, hiçbiri yeniden adlandırılmadı. Veri setindeki adlar
    # (dilekce, bilgi_edinme, bilgilendirme) farklı; eşleme src/taksonomi.py
    # içindedir. Yeniden adlandırma rules.yaml'daki 104 kuralı sessizce
    # kırabilirdi — donma kuralı: alan silinmez, eklenir.
    ITIRAZ = "itiraz"
    GORUS_TALEBI = "gorus_talebi"

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
        # 1.2.0: gorus_talebi 20/20 belgede KURUMDAN geliyor, hepsinin
        # sayısı var. Ölçüldü, atanmadı.
        GelenTur.GORUS_TALEBI,
    }),
    "kisi_belgesi": frozenset({
        GelenTur.VATANDAS_DILEKCESI,
        GelenTur.BILGI_EDINME_BASVURUSU,
        GelenTur.SIKAYET,
        # 1.2.0: itiraz 11 belgede gerçek kişi (8), şirket (2), öğrenci (1)
        # tarafından yazılmış; 9'unun sayısı yok. Kişi belgesi.
        GelenTur.ITIRAZ,
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
    """Gizlilik derecesini karşılaştırılabilir bir sayıya çevirir.

    Tanınmayan bir derece HATA VERİR, sessizce 0 dönmez. Sebebi güvenlik:
    0 "derecesiz" anlamına geliyor. Tanınmayan bir metin — ör. OCR'ın
    "Çok Gizli"yi "Cok Gizli" diye okuması — sessizce 0 sayılsaydı, EK-05'in
    "ekin gizliliği üst yazıyı aşamaz" denetimi Çok Gizli bir eki fark
    etmeden geçirirdi. Gürültülü girdinin çıkardığı bir denetimin sessizce
    başarılı görünmesi, açıkça çökmesinden kötüdür.

    Derecesiz belge için None veya boş dize verilir.
    """
    if derece is None:
        return 0
    metin = str(derece).strip()
    if not metin:
        return 0
    if metin not in _GIZLILIK_SIRASI:
        raise ValueError(
            f"Tanınmayan gizlilik derecesi: {derece!r}. "
            f"İzinli değerler: {[str(g) for g in GizlilikDerecesi]} veya None. "
            f"Belgede yazan ham metin ustveri.gizlilik_ham alanında tutulur."
        )
    return _GIZLILIK_SIRASI[metin]


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

    Metnin "arz" mı "rica" mı diye bitmesi buna bağlı (ME-02, K 13.1).
    Kural tek yönlüdür: RİCA YALNIZCA AŞAĞI DOĞRU. Üst ve aynı düzeydeki
    makamlara arz edilir — idare içinde aynı düzeydeki birimler arasında da
    (K 13.1: "Teftiş Kurulu Başkanlığı - Personel Genel Müdürlüğü vb.").

    Hiyerarşi mevzuatla net tanımlanmamışsa Kılavuz "arz" demeyi öneriyor;
    bu yüzden BILINMIYOR da arz üretir, ama ayrı tutulur: "eşit olduğunu
    biliyoruz" ile "bilemedik" aynı şey değildir ve ikincisi insan onayına
    düşmelidir.
    """

    UST = "ust"          # muhatap daha üst          -> "Arz ederim."
    AYNI = "ayni"        # aynı düzey                -> "Arz ederim."
    ALT = "alt"          # muhatap daha alt          -> "Rica ederim."
    KARMA = "karma"      # dağıtımlı: üst+aynı+alt   -> "Arz ve rica ederim."
    KURUM_DISI = "kurum_disi"     # ME-06 kamu dışı  -> "Rica ederim."
    GERCEK_KISI = "gercek_kisi"   # ME-05            -> "Saygılarımla." vb.
    BILINMIYOR = "bilinmiyor"     # K 13.1 kestirme  -> "Arz ederim."


# -----------------------------------------------------------------------------
# 4.1 İş akışı sözlükleri — 1.1.0'da eklendi
# -----------------------------------------------------------------------------
#
# Bu dördü belgenin kendi anatomisine değil, belgenin SİSTEM İÇİNDEKİ
# yolculuğuna ait. Kaynakları Yönetmelik değil, docs/api_sozlesmesi.md.
# Arayüzün beklediği değerlerle birebir aynı tutulmuştur; birinde değişiklik
# diğerini kırar.


class EvrakDurumu(StrEnum):
    """Evrağın boru hattındaki konumu — api_sozlesmesi.md 3.1.

    Belgenin içeriğiyle ilgisi yok; işin nerede olduğunu söyler.
    """

    ALINDI = "ALINDI"                                # yüklendi, henüz koşmadı
    ISLENIYOR = "ISLENIYOR"
    INSAN_ONAYI_BEKLIYOR = "INSAN_ONAYI_BEKLIYOR"
    EKSIK_BILGI_BEKLIYOR = "EKSIK_BILGI_BEKLIYOR"    # karşı taraftan bilgi istendi
    OTOMATIK_ONAYLANDI = "OTOMATIK_ONAYLANDI"        # güven kapısı geçirdi
    ONAYLANDI = "ONAYLANDI"                          # insan onayladı
    REDDEDILDI = "REDDEDILDI"
    HATA = "HATA"


class Motor(StrEnum):
    """Bir adımı ne çalıştırıyor.

    İstatistikteki "zamanın nereye gittiği" çubuğu bu dörtlüyü ayrı gösterir.
    ARAC ve KURAL payı, "her şeyi modele sormadık" iddiasının rakamıdır.
    """

    ARAC = "arac"        # model çağırmayan dış araç: Docling, OCR, eşik hesabı
    KURAL = "kural"      # deterministik kural motoru (rules.yaml)
    LLM = "llm"          # dil modeli çağrısı
    KARMA = "karma"      # kural ve model birlikte


class InsanKarari(StrEnum):
    """İnsanın evrak hakkında verdiği karar.

    Karar.insan_onayi_gerekli "insana sorulmalı mı" der; bu alan "insan ne
    dedi" sorusunu cevaplar. İkisi ayrı sorudur ve ikisi de kayda değer:
    Ş 6.4.2 (5) eksik bilgi talebini zorunlu yetenek sayıyor, yani iade
    akışının izi kalmalı.
    """

    YOK = "yok"                          # henüz karar verilmedi
    ONAYLANDI = "onaylandi"
    REDDEDILDI = "reddedildi"
    BIRIM_DEGISTIRILDI = "birim_degistirildi"
    EKSIK_BILGI_ISTENDI = "eksik_bilgi_istendi"
    GERI_ALINDI = "geri_alindi"


class EksikKatman(StrEnum):
    """Eksikliğin hangi katmanda tespit edildiği — Denetçi'nin üç katmanı.

    Ajan bu üçünü sırayla değerlendirip hangisinin uygulanacağına karar
    veriyor. Katmanı kaydetmek iki işe yarıyor: kullanıcıya dayanağı
    göstermek, ve Parça 6'da "hangi katman ne kadar iş görüyor" ölçümü.
    """

    SEMA = "sema"            # zorunlu alan boş — deterministik
    KURAL = "kural"          # rules.yaml kuralı ihlal edilmiş — araç
    MEVZUAT = "mevzuat"      # mevzuat bir belge/bilgi istiyor
    CIKARIM = "cikarim"      # kural dışı, model çıkarımı


class DugumDurumu(StrEnum):
    """Tek bir adımın o andaki hâli — api_sozlesmesi.md 5.6.2."""

    BEKLIYOR = "bekliyor"
    CALISIYOR = "calisiyor"
    TAMAM = "tamam"
    HATA = "hata"
    ATLANDI = "atlandi"


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
    "ustveri.ivedilik_ham",
    "ustveri.gizlilik_derecesi",
    "ustveri.gizlilik_ham",
    "ustveri.miat",
    "ustveri.imza",
    "ustveri.imza.ad",
    "ustveri.imza.unvan",
    # Alt bilgi
    "altbilgi.adres",
    "altbilgi.telefon",
    "altbilgi.eposta",
    "altbilgi.dogrulama_metni",
    "altbilgi.dogrulama_kodu",
    # Metin
    "metin",
    # Sınıflandırma
    "siniflandirma.belge_turu",
    "siniflandirma.sdp.kod",
    "siniflandirma.sdp.saklama_suresi",
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


# Yöntemlerin güvenilirlik sırası.
#
# Başlangıçta bunu ikili bir ayrım olarak yazmıştım (kesin / beyan) ve iki
# yöntem hiçbir kümeye girmiyordu: OCR ve VARSAYILAN. Kümesiz kalan yöntem
# "kesin" sayılıyor, öntanımlı bir değer modelin gerçek çıkarımının üzerine
# yazabiliyordu. Sıralı öncelik hem bu boşluğu kapatıyor hem de aradaki
# dereceleri ifade edebiliyor.
#
# Sıralamanın mantığı: kullanıcı düzeltmesi nihaidir; metinde eşleşen bir
# desen modelin kanaatinden güvenilirdir; OCR ölçülmüş ama gürültülüdür;
# modelin beyanı kalibre değildir; öntanımlı değer hiçbir şeye dayanmaz.
YONTEM_ONCELIGI: dict[KanitYontemi, int] = {
    KanitYontemi.INSAN: 100,       # kullanıcı düzeltmesi — her şeyi geçer
    KanitYontemi.REGEX: 80,        # metinde gerçekten eşleşti
    KanitYontemi.SOZLUK: 80,
    KanitYontemi.KURAL: 80,
    KanitYontemi.HESAPLAMA: 75,    # başka alanlardan türetildi
    KanitYontemi.OCR: 60,          # ölçülmüş güven, ama gürültülü
    KanitYontemi.LLM: 40,          # beyan edilen güven, kalibre değil
    KanitYontemi.VARSAYILAN: 0,    # dayanağı yok
}

# Güveni modelin kendi beyanı olan yöntemler. Risk testinde ölçüldü:
# yanlış cevaplarda ortalama güven qwen3.5:9b'de 0.79, gemma'da 0.938.
BEYAN_YONTEMLERI: frozenset[KanitYontemi] = frozenset({
    KanitYontemi.LLM,
})


def yontem_onceligi(yontem: KanitYontemi | str) -> int:
    """Yöntemin güvenilirlik sırası. Tanımsız yöntem en düşük sayılır."""
    try:
        return YONTEM_ONCELIGI[KanitYontemi(str(yontem))]
    except (ValueError, KeyError):
        return 0


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

        METİN GİRDİ DE REDDEDİLİR. Pydantic normalde "0.5" dizesini 0.5'e
        çevirir; burada bilerek çevirmiyoruz. Şema sayı tipi dayattığı için
        dize gelmesi zaten sözleşme ihlalidir ve tolere edilmesi, sonraki
        ihlalleri görünmez kılar.
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

    Önce YÖNTEME, sonra güvene bakar. Sebebi şu: düzenli ifadeyle çıkarılmış
    bir sayının üzerine, modelin 0.99 güvenle beyan ettiği başka bir sayının
    yazılmasını istemiyoruz. Model kendinden emin olabilir ama düzenli ifade
    metinde gerçekten eşleşmiştir.

    Eşit öncelikte olanlar güvene göre karşılaştırılır. Geçersiz güvenli bir
    kanıt, geçerli güvenli olanın yerini alamaz — sözleşme dışı çıktı üreten
    bir model tercih edilmez.
    """
    yeni_o = yontem_onceligi(yeni.yontem)
    mevcut_o = yontem_onceligi(mevcut.yontem)
    if yeni_o != mevcut_o:
        return yeni_o > mevcut_o

    if yeni.guven_gecerliydi != mevcut.guven_gecerliydi:
        return yeni.guven_gecerliydi

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
    #
    # Bu ikisinde ham alan ayrıca gerekli. Belgede "ACİL" veya "Özel" yazıyor
    # olabilir; ikisi de mevzuata aykırı ve çözümlenmiş alana yazılamaz, ama
    # KAYDEDİLMELİ. Belge reddedilmiyor — kusuru raporlanıyor, ve raporda
    # "belgede ne yazıyordu" sorusunun cevabı bulunmalı (G-02, G-04).
    ivedilik: Ivedilik | None = None
    ivedilik_ham: str | None = Field(
        default=None, max_length=50,
        description="Belgede yazdığı hâl. Mevzuata aykırıysa ivedilik boş kalır, "
                    "bu alan dolu olur.",
    )
    gizlilik_derecesi: GizlilikDerecesi | None = None
    gizlilik_ham: str | None = Field(
        default=None, max_length=50,
        description="Belgede yazdığı hâl; kaldırılmış 'Özel' derecesi burada durur.",
    )
    miat: date | None = Field(
        default=None, description="G-05: GÜNLÜDÜR ise dolu olmalı"
    )

    @property
    def ivedilik_gecerli_mi(self) -> bool:
        """Belgede ivedilik ibaresi var ama mevzuata uygun değil mi (G-04)."""
        return not (self.ivedilik is None and self.ivedilik_ham)

    @property
    def gizlilik_gecerli_mi(self) -> bool:
        """Belgede gizlilik derecesi var ama mevzuata uygun değil mi (G-02)."""
        return not (self.gizlilik_derecesi is None and self.gizlilik_ham)

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


# =============================================================================
# BÖLÜM 4 — DOSYA
# =============================================================================
#
# Bölüm 3 gelen evrağın anatomisini tanımladı. Bu bölüm, o anatominin üzerine
# sistemin ÜRETTİKLERİNİ ekliyor ve hepsini tek bir kök nesnede topluyor.
#
# Şartnamenin iki görevi burada karşılık buluyor:
#
#   6.4.1 — Evrak Sınıflandırma ve İçerik Analizi
#           Siniflandirma · Icerik (özet, varlıklar, eksik alanlar) · Mevzuat
#
#   6.4.2 — Resmî Yazı Taslaklama ve Birim Yönlendirme
#           CiktiYazi (taslak + linter raporu) · Yonlendirme · Karar
#
# İz kaydı ise 6.4.2'nin "kullanıcıya süreç hakkında açık ve anlaşılır
# bilgilendirme sunması" isteğinin kaynağı.


# -----------------------------------------------------------------------------
# 4.1 Sınıflandırma — Ş 6.4.1
# -----------------------------------------------------------------------------


class SdpKodu(BaseModel):
    """Standart dosya planı ataması.

    Sayısı olan bir kurum yazısında bu kod TAHMİN EDİLMEZ, sayının üçüncü
    bölümünden okunur (bkz. sayi_bolumleri). Tahmin yalnızca üç durumda
    gerekir: vatandaş dilekçesinde, ürettiğimiz taslakta, ve gelen koddaki
    tutarlılığı denetlerken (S-07).
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    kod: str | None = Field(default=None, max_length=20, description="ör. '010.06.01'")
    ana_grup: str | None = Field(default=None, max_length=10, description="ör. '010'")
    ad: str | None = Field(default=None, max_length=200)
    saklama_suresi: str | None = Field(
        default=None,
        description="SDP'den gelir. Şartname 6.2 arşivlemeyi anıyor ama zorunlu "
                    "yetenek listesine almamış; bu alan bedava kazanç.",
    )
    kaynak_sayidan_mi: bool = Field(
        default=False, description="Kod sayıdan okunduysa True, tahminse False"
    )


class Siniflandirma(BaseModel):
    """Gelen evrağın türü ve dosyalama kodu."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    belge_turu: GelenTur = GelenTur.BILINMIYOR
    sdp: SdpKodu = Field(default_factory=SdpKodu)
    gerekce: str | None = Field(default=None, max_length=500)
    alternatif_turler: list[GelenTur] = Field(
        default_factory=list,
        description="Model ikinci ve üçüncü adayları da verdiyse. İnsan onayı "
                    "ekranında seçenek olarak gösterilir.",
    )


# -----------------------------------------------------------------------------
# 4.2 İçerik analizi — Ş 6.4.1
# -----------------------------------------------------------------------------


class Varlik(BaseModel):
    """Belgeden çıkarılan tek bir bilgi unsuru.

    `kisisel_veri` alanı tipe göre otomatik dolar; ajanın işaretlemeyi
    unutması mümkün değil. Maskeleme Parça 3'te yazılacak, ama işaret
    şimdiden burada.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    tip: VarlikTipi
    deger: str = Field(max_length=500)
    ham: str | None = Field(default=None, max_length=500)
    konum: Konum | None = None
    kisisel_veri: bool = False
    maskeli_deger: str | None = Field(
        default=None, description="ör. '105******40'; maskeleme Parça 3'te"
    )

    @model_validator(mode="after")
    def _kisisel_veriyi_isaretle(self) -> Varlik:
        # Tipten çıkan sonucu ajanın kararına bırakmıyoruz: bir ajan unutursa
        # kişisel veri maskelenmeden geçer. Tip kişisel veriyse işaret zorunlu.
        if kisisel_veri_mi(self.tip) and not self.kisisel_veri:
            object.__setattr__(self, "kisisel_veri", True)
        return self


class EksikAlan(BaseModel):
    """Belgede bulunması gereken ama bulunmayan bilgi — Ş 6.4.1 (3).

    `kural_id` doluysa eksiklik mevzuat kaynaklıdır ve kullanıcıya dayanağı
    gösterilebilir. Boşsa çıkarım yoluyla tespit edilmiştir.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    alan: str = Field(max_length=100, description="ör. 'ustveri.sayi'")
    aciklama: str = Field(max_length=300)
    onem: Onem = Onem.UYARI
    kural_id: str | None = Field(default=None, description="ör. 'S-01'")
    dayanak: str | None = Field(
        default=None, max_length=500, description="mevzuat alıntısı"
    )
    talep_edilebilir: bool = Field(
        default=False,
        description="Ş 6.4.2 (5): sistem bu eksiği karşı taraftan isteyebilir mi",
    )

    # -- 1.1.0'da eklendi ---------------------------------------------------
    katman: EksikKatman = Field(
        default=EksikKatman.CIKARIM,
        description="Denetçi'nin hangi katmanında bulundu",
    )
    soru: str | None = Field(
        default=None, max_length=300,
        description="Eksiği karşı taraftan istemek için kurulmuş cümle. "
                    "`aciklama` sistemin kendine notu, `soru` vatandaşa "
                    "sorulacak hâli — ikisi aynı şey değil.",
    )
    giderildi: bool = Field(
        default=False, description="Karşı taraftan cevap geldi ve eksik kapandı"
    )
    cevap: str | None = Field(default=None, max_length=1000)


class Icerik(BaseModel):
    """Belgenin ne dediği — Ş 6.4.1 (2), (3) ve (5)."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    talep: str | None = Field(
        default=None, max_length=500, description="Belge ne istiyor, tek cümle"
    )
    ozet: str | None = Field(default=None, max_length=1500)
    varliklar: list[Varlik] = Field(default_factory=list)
    eksik_alanlar: list[EksikAlan] = Field(default_factory=list)

    @property
    def kisisel_veriler(self) -> list[Varlik]:
        return [v for v in self.varliklar if v.kisisel_veri]

    @property
    def kritik_eksikler(self) -> list[EksikAlan]:
        return [e for e in self.eksik_alanlar if e.onem == Onem.HATA]


# -----------------------------------------------------------------------------
# 4.3 Mevzuat önerileri — Ş 6.4.1 (4)
# -----------------------------------------------------------------------------


class MevzuatOnerisi(BaseModel):
    """İlgili olduğu değerlendirilen mevzuat maddesi.

    `dogrulandi` ayrı bir alan çünkü benzerlik skoru tek başına yetmiyor:
    metinsel olarak benzeyen bir madde konu olarak alakasız olabilir.
    Getirme ile doğrulama iki ayrı adım.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    mevzuat_adi: str = Field(max_length=300)
    madde: str | None = Field(default=None, max_length=50)
    alinti: str | None = Field(
        default=None, max_length=1000, description="mevzuat metninden birebir"
    )
    benzerlik: float | None = Field(
        default=None, ge=0.0, le=1.0, description="getirme skoru"
    )
    dogrulandi: bool = Field(
        default=False, description="ikinci bir adım gerçekten ilgili olduğunu onayladı mı"
    )
    kural_id: str | None = Field(default=None, description="rules.yaml'dan geldiyse")


# -----------------------------------------------------------------------------
# 4.4 Linter — kural denetimi çıktısı
# -----------------------------------------------------------------------------


class LinterBulgusu(BaseModel):
    """Tek bir kural ihlali.

    Kullanıcıya gösterilecek üç şey: ne yanlış (kural), neden yanlış
    (dayanak), nerede yanlış (konum/alinti).
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    kural_id: str = Field(max_length=20)
    baslik: str = Field(max_length=200)
    onem: Onem
    aciklama: str | None = Field(default=None, max_length=500)
    dayanak: str | None = Field(
        default=None, max_length=1000, description="mevzuat alıntısı"
    )
    alan: str | None = Field(default=None, description="ör. 'ustveri.sayi'")
    alinti: str | None = Field(default=None, max_length=300)
    konum: Konum | None = None
    duzeltme_onerisi: str | None = Field(default=None, max_length=500)


class LinterRaporu(BaseModel):
    """Bir belgenin kural denetimi sonucu."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    bulgular: list[LinterBulgusu] = Field(default_factory=list)
    denetlenen_kural_sayisi: int = Field(default=0, ge=0)
    atlanan_kural_sayisi: int = Field(
        default=0, ge=0, description="kapsam dışı veya ön koşulu eksik kurallar"
    )

    @property
    def hatalar(self) -> list[LinterBulgusu]:
        return [b for b in self.bulgular if b.onem == Onem.HATA]

    @property
    def uyarilar(self) -> list[LinterBulgusu]:
        return [b for b in self.bulgular if b.onem == Onem.UYARI]

    @property
    def gecti_mi(self) -> bool:
        """rules.yaml'ın kuralı: yalnızca 'hata' düzeyi belgeyi düşürür."""
        return not self.hatalar


# -----------------------------------------------------------------------------
# 4.5 Üretilen yazı ve yönlendirme — Ş 6.4.2
# -----------------------------------------------------------------------------


class CiktiYazi(BaseModel):
    """Sistemin ürettiği taslak — Ş 6.4.2 (1) ve (2).

    Taslağın kendi sayısı, tarihi ve imzası burada YOK: bunlar EBYS'de kayıt
    ve imza anında atanır, taslak aşamasında bilinmez. Gerekirse sonradan
    eklenir (yapı kuralı: alan silinmez, eklenir).
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    tur: UretilecekTur | None = None
    tur_gerekcesi: str | None = Field(default=None, max_length=500)
    sablon: str | None = Field(default=None, description="kullanılan şablon adı")
    konu: str | None = Field(default=None, max_length=250)
    metin: str | None = Field(default=None, description="taslağın gövdesi")
    hiyerarsi_yonu: HiyerarsiYonu | None = Field(
        default=None, description="ME-02/ME-03: arz mı rica mı bunu belirliyor"
    )
    linter_raporu: LinterRaporu = Field(default_factory=LinterRaporu)

    # -- 1.1.0'da eklendi ---------------------------------------------------
    #
    # Sınıfın docstring'i taslağın sayı, tarih ve imzasının burada OLMADIĞINI
    # söylüyor ve bu hâlâ geçerli — o üçü EBYS'de kayıt ve imza anında atanır.
    # Aşağıdaki üçü farklı: taslak yazılırken BİLİNİYORLAR.
    #
    #   baslik       gönderen idarenin başlık bloğu, kurum profilinden gelir
    #   muhatap      gelen evrağın göndereni, zaten elimizde
    #   imza_unvan   birimler.csv'deki imza_unvani sütunu
    #
    # İmzanın unvanı ile imzalayanın adı ayrı tutuluyor: unvan taslak anında
    # bilinir ve yazının altında görünmelidir, ad imza anında atanır. Bu
    # yüzden imza_ad diye bir alan YOK ve eklenmeyecek.

    baslik: str | None = Field(
        default=None, max_length=500,
        description="ör. 'T.C.\\nANKARA VALİLİĞİ\\nİl Millî Eğitim Müdürlüğü'",
    )
    muhatap: str | None = Field(default=None, max_length=300)
    imza_unvan: str | None = Field(
        default=None, max_length=100, description="ör. 'Şube Müdürü'"
    )


class YonlendirmeAdayi(BaseModel):
    """Aday birim ve skoru — 1.1.0'da eklendi."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    birim: str = Field(max_length=100, description="birim_kodu, ör. 'ortaogretim_sb'")
    birim_adi: str | None = Field(default=None, max_length=200)
    skor: float = Field(default=0.0, ge=0.0, le=1.0)


class YonlendirmeKaynagi(StrEnum):
    """Hedef birim nasıl bulundu — 1.1.0'da eklendi.

    SDP kodu sayının üçüncü bölümünden OKUNUR, tahmin edilmez. Kod okunduysa
    birimler.csv'nin sdp_kodlari sütunundan hedef doğrudan bulunur ve bu
    deterministik bir sonuçtur. Tahmin yalnızca sayısı olmayan belgelerde
    (vatandaş dilekçesi) gerekir.

    Ayrımı tutmak Parça 6'da ablasyon satırı üretiyor: iki yolun isabeti
    ayrı ölçülebilir.

    İkinci deterministik hat MUHATAP'tır: SDP kodu taşımayan belgelerde
    (dilekçe, şirket yazısı — 132/300) hedef birim muhatap satırında
    yazılıdır. Ayrı değer tutuluyor ki ablasyon ölçümünde SDP hattıyla
    karışmasın.
    """

    SDP_TABLOSU = "sdp_tablosu"   # deterministik
    MUHATAP = "muhatap"           # deterministik — muhatap satırında birim yazılı
    LLM = "llm"                   # tahmin
    INSAN = "insan"               # kullanıcı birimi değiştirdi
    BILINMIYOR = "bilinmiyor"


class Yonlendirme(BaseModel):
    """Evrağın hangi birime gideceği — Ş 6.4.2 (3)."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    hedef_birim: str | None = Field(default=None, max_length=200)
    dagitim_turu: DagitimTuru = DagitimTuru.GEREGI
    gerekce: str | None = Field(default=None, max_length=500)
    alternatifler: list[str] = Field(
        default_factory=list,
        description="KULLANILMIYOR. 1.1.0'da yerini alternatif_adaylar aldı; "
                    "tipini değiştirmek alan silmekle eş değer olduğu için "
                    "burada bırakıldı. Yeni kod alternatif_adaylar kullanır.",
    )
    kurum_disinda: bool = Field(
        default=False, description="Evrak yanlış kuruma gelmişse True"
    )

    # -- 1.1.0'da eklendi ---------------------------------------------------
    skor: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Seçilen birimin skoru. Güven kapısının baktığı değer",
    )
    kanit_cumle: str | None = Field(
        default=None, max_length=500,
        description="Belgede yönlendirmeyi gerektiren cümle. Birebir alıntı; "
                    "bulunamadıysa None — uydurulmaz.",
    )
    kaynak: YonlendirmeKaynagi = YonlendirmeKaynagi.BILINMIYOR
    alternatif_adaylar: list[YonlendirmeAdayi] = Field(
        default_factory=list,
        description="İkinci ve üçüncü aday birimler skorlarıyla. Yönlendirme "
                    "hatası pahalı olduğu için kullanıcıya seçenek sunulur.",
    )


# -----------------------------------------------------------------------------
# 4.6 Karar ve iz
# -----------------------------------------------------------------------------


class Karar(BaseModel):
    """Sistem bu belgeyi insana sormadan geçirebilir mi."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    otomatik_onay: bool = False
    insan_onayi_gerekli: bool = True
    sebepler: list[str] = Field(
        default_factory=list, description="insan onayı neden gerekli"
    )
    toplam_guven: float = Field(default=0.0, ge=0.0, le=1.0)
    toplam_sure_ms: float = Field(default=0.0, ge=0.0)

    # -- 1.1.0'da eklendi ---------------------------------------------------
    esik: float = Field(
        default=0.85, ge=0.0, le=1.0,
        description="Güven kapısının eşiği. Kayıtla birlikte tutulur çünkü "
                    "eşik sonradan değişirse eski kararlar hangi eşikle "
                    "verildiği bilinmeden yorumlanamaz.",
    )

    # İnsanın ne dediği. insan_onayi_gerekli "sorulmalı mı", bunlar "ne dedi".
    insan_karari: InsanKarari = InsanKarari.YOK
    karar_veren_rol: str | None = Field(
        default=None, max_length=50, description="ör. 'birim_sorumlusu'"
    )
    karar_zamani: datetime | None = None
    karar_gerekcesi: str | None = Field(
        default=None, max_length=1000,
        description="reddet, birim_degistir ve karari_geri_al için zorunlu",
    )


class IzKaydi(BaseModel):
    """Bir ajanın tek çalıştırması.

    Ş 6.4.2 (4) kullanıcıya süreç hakkında açık ve anlaşılır bilgilendirme
    sunulmasını istiyor; arayüzdeki "hangi ajan ne yaptı, ne kadar sürdü"
    paneli bu listeden besleniyor. Aynı zamanda Parça 9'un gecikme ölçümünün
    ham verisi.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    ajan: str
    model: str | None = None
    basarili: bool = True
    hata: str | None = Field(default=None, max_length=500)
    sure_ms: float = Field(default=0.0, ge=0.0)
    istem_token: int | None = Field(default=None, ge=0)
    uretilen_token: int | None = Field(default=None, ge=0)
    zaman: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # -- 1.1.0'da eklendi ---------------------------------------------------
    #
    # Bu altı alan arayüzün akış ekranını besliyor. Bitmiş bir koşu SSE
    # olmadan yeniden çizilebilmeli: kullanıcı sayfayı yenilediğinde veya
    # kuyruktan eski bir evrağa tıkladığında ekran boş kalmamalı.
    # api_sozlesmesi.md 5.6.2 (dugum_kayitlari) buradan üretiliyor.

    adim_no: int | None = Field(
        default=None, ge=1, le=99,
        description="Düğüm tablosundaki sıra, 1-11. Tablo /api/dugumler'den "
                    "geldiği ve Parça 4'te değişebileceği için üst sınır geniş.",
    )
    durum: DugumDurumu = DugumDurumu.TAMAM
    tur_no: int = Field(
        default=1, ge=1,
        description="Kaçıncı tur. Üslup döngüsü taslağı geri gönderirse artar; "
                    "döngü yaşanmayan adımlarda daima 1. Her tur AYRI kayıttır.",
    )
    guven: float | None = Field(default=None, ge=0.0, le=1.0)
    gerekce: str | None = Field(default=None, max_length=500)
    cikti: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict,
        description="Adımın kısa çıktı özeti, ör. {'sayfa_sayisi': 1}. "
                    "Yan panelde gösterilir; büyük veri buraya konmaz.",
    )
    ozet: str | None = Field(
        default=None, max_length=200,
        description="İnsan okuyacak tek satır, ör. '9 alan bulundu, 1 eksik'",
    )


# -----------------------------------------------------------------------------
# 4.7 Kök nesne
# -----------------------------------------------------------------------------


class Duzeltme(BaseModel):
    """İnsanın sistem çıktısına yaptığı bir müdahale — 1.1.0'da eklendi.

    Ş 9'un puanladığı ölçütlerden biri insan müdahale oranı. Müdahaleyi
    saymak için önce kaydetmek gerekiyor. Hangi alanların değiştiği de
    tutuluyor: Parça 6'da "model en çok neyi yanlış yapıyor" sorusunun
    cevabı buradan çıkar.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    tur: str = Field(
        max_length=30, description="taslak | birim | red | geri_alma"
    )
    rol: str = Field(max_length=50, description="ör. 'birim_sorumlusu'")
    zaman: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    alanlar: list[str] = Field(
        default_factory=list, description="değiştirilen alan adları, ör. ['govde']"
    )
    gerekce: str | None = Field(default=None, max_length=1000)


class EksikBilgiTalebi(BaseModel):
    """Karşı taraftan eksik bilgi isteme yazısı — 1.1.0'da eklendi.

    Ş 6.4.2 (5) bunu zorunlu yetenek sayıyor: sistem eksik bilgi talep
    edebilmeli. Talebin kendisi de resmî bir yazıdır, bu yüzden yazi alanı
    CiktiYazi tipindedir ve linter'dan geçer.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    zaman: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    muhatap_ad: str | None = Field(default=None, max_length=200)
    muhatap_turu: MuhatapTuru = MuhatapTuru.BILINMIYOR
    kanal: str | None = Field(
        default=None, max_length=100, description="ör. 'Resmî yazı (posta / e-Devlet)'"
    )
    sure_gun: int | None = Field(default=None, ge=1, le=365)
    son_tarih: date | None = Field(
        default=None,
        description="ISO tarih. Sunucu asla gg.aa.yyyy göndermez; "
                    "biçimlendirme arayüzün işi.",
    )
    dayanak: str | None = Field(
        default=None, max_length=300,
        description="Süreyi veren mevzuat, ör. '3071 s.K. m.7 (30 gün)'",
    )
    sorular: list[str] = Field(default_factory=list)
    yazi: CiktiYazi | None = None
    elle_duzenlendi: bool = False


class EksikBilgiCevabi(BaseModel):
    """Karşı taraftan gelen cevap — 1.1.0'da eklendi.

    Gerçekte bu ayrı bir evraktır ve ilgi ile bağlanır. Parça 5'te
    ilgi_evrak_id alanı eklenecek; şimdilik aynı dosya üzerinde tutuluyor.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    zaman: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    gonderen: str | None = Field(default=None, max_length=200)
    ilgi: str | None = Field(
        default=None, max_length=100, description="cevabın atıf yaptığı sayı"
    )
    cevaplar: list[dict[str, str]] = Field(
        default_factory=list, description="[{'soru': ..., 'cevap': ...}]"
    )


class Dosya(BaseModel):
    """Bir evrağın tüm yolculuğu.

    12 ajan bu nesneyi sırayla doldurur. Alan adları rules.yaml'ın yol
    dizeleriyle hizalı; deger_al() ile nokta yollarından okunabilir.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    # 1 · Kimlik
    evrak_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    olusturma_zamani: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    surum: str = SURUM

    # 2-5 · Gelen evrak
    gelen_kayit: GelenKayit = Field(default_factory=GelenKayit)
    kaynak: KaynakBilgisi = Field(default_factory=KaynakBilgisi)
    baslik: BaslikBlogu = Field(default_factory=BaslikBlogu)
    ustveri: Ustveri = Field(default_factory=Ustveri)
    metin: str | None = Field(default=None, description="gelen belgenin gövdesi")
    altbilgi: AltBilgi = Field(default_factory=AltBilgi)

    # 6-9 · Görev 1 çıktıları
    siniflandirma: Siniflandirma = Field(default_factory=Siniflandirma)
    icerik: Icerik = Field(default_factory=Icerik)
    mevzuat: list[MevzuatOnerisi] = Field(default_factory=list)

    # 10-11 · Görev 2 çıktıları
    cikti_yazi: CiktiYazi = Field(default_factory=CiktiYazi)
    yonlendirme: Yonlendirme = Field(default_factory=Yonlendirme)

    # 12-13 · Karar ve iz
    karar: Karar = Field(default_factory=Karar)
    iz: list[IzKaydi] = Field(default_factory=list)

    # 14 · İş akışı — 1.1.0'da eklendi
    #
    # Buraya kadarki her şey BELGENİN anatomisi. Aşağıdakiler belgenin sistem
    # içindeki yolculuğu ve insanın ona dokunuşları. Ayrı tutuluyorlar çünkü
    # kural motoru bunlara bakmaz; arayüz ve rapor bakar.
    durum: EvrakDurumu = EvrakDurumu.ALINDI
    dosya_adi: str | None = Field(
        default=None, max_length=255, description="ör. 'belge_099.pdf'"
    )
    duzeltmeler: list[Duzeltme] = Field(
        default_factory=list,
        description="İnsanın yaptığı her düzeltme. Ş 9 'insan müdahale oranı' "
                    "ölçümü ve Parça 6'daki hata analizi buradan çıkar.",
    )
    eksik_bilgi_talebi: EksikBilgiTalebi | None = None
    eksik_bilgi_cevabi: EksikBilgiCevabi | None = None

    # Kanıt haritası — anahtarlar rules.yaml'ın yol dizeleriyle aynı
    kanit: dict[str, Kanit] = Field(default_factory=dict)

    # -- yol çözümleme ------------------------------------------------------

    def deger_al(self, yol: str, varsayilan=None):
        """Nokta yolundan değer okur: deger_al('ustveri.muhatap.birim').

        Kural motorunun ihtiyacı olan çözümleyici. rules.yaml'ın
        'ustveri.sayi[bolum:3]' gibi özel sözdizimi burada desteklenmiyor;
        o, motorun kendi işi (sayi_bolumleri ile çözülür).
        """
        dugum = self
        for parca in yol.split("."):
            if isinstance(dugum, dict):
                dugum = dugum.get(parca)
            else:
                dugum = getattr(dugum, parca, None)
            if dugum is None:
                return varsayilan
        return dugum

    def alan_dolu_mu(self, yol: str) -> bool:
        """Bu alana gerçekten bir şey yazılmış mı.

        "Boş değil mi" diye bakmak yetmiyor: Taraf() ve Imza() gibi iç
        nesneler default_factory ile her zaman oluşuyor, GelenTur.BILINMIYOR
        da bir öntanımlı. Bunları "dolu" saymak kanitsiz_alanlar()'ı
        kullanılamaz hâle getiriyordu — boş bir Dosya'da bile dört alan
        rapor ediliyordu.

        Doğru ölçüt öntanımlıdan sapmadır: değer, hiç dokunulmamış bir
        Dosya'daki karşılığından farklıysa doldurulmuş demektir.
        """
        deger = self.deger_al(yol)
        if deger is None:
            return False
        return deger != _varsayilan_dosya().deger_al(yol)

    # -- kanıt --------------------------------------------------------------

    def kanit_ekle(self, yol: str, kanit: Kanit, zorla: bool = False) -> bool:
        """Bir alana kanıt iliştirir. Eklendiyse True döner.

        Mevcut kanıt daha güvenilirse yenisi REDDEDİLİR — modelin, düzenli
        ifadeyle bulunmuş bir değerin kanıtını ezmesini engeller. zorla=True
        bu korumayı devre dışı bırakır; kasıtlı olmadıkça kullanılmamalı.

        Tanımsız bir yola kanıt eklenmesi hata verir. Sebebi kişisel deneyim
        değil, tasarım: 'ustveri.sayı' (Türkçe ı ile) diye sessizce yanlış
        anahtar yazılırsa, o kanıt hiçbir zaman bulunamaz ve alan kanıtsız
        sayılır. Hatanın belirtisi çıktığı yerden çok uzakta görünür.
        """
        if yol not in ALAN_YOLLARI:
            raise ValueError(
                f"Tanımsız alan yolu: {yol!r}. "
                f"ALAN_YOLLARI kümesine ekleyin veya yazımı düzeltin."
            )
        mevcut = self.kanit.get(yol)
        if mevcut is not None and not zorla and not daha_guvenilir(kanit, mevcut):
            return False
        self.kanit[yol] = kanit
        return True

    def guven(self, yol: str, varsayilan: float = 0.0) -> float:
        k = self.kanit.get(yol)
        return k.guven if k else varsayilan

    def kanitsiz_alanlar(self) -> list[str]:
        """Dolu olduğu hâlde kanıtı bulunmayan alanlar.

        Kanıt haritasının zayıf noktası eklemeyi unutmaktır. Bu fonksiyon o
        unutmayı bir teste bağlanabilir hâle getiriyor.
        """
        return sorted(
            yol for yol in ALAN_YOLLARI
            if self.alan_dolu_mu(yol) and yol not in self.kanit
        )

    def gecersiz_kanit_anahtarlari(self) -> list[str]:
        """ALAN_YOLLARI'nda tanımlı olmayan kanıt anahtarları.

        kanit_ekle() yol adını denetliyor, ama sözlüğe doğrudan yazmak
        (d.kanit["yol"] = ...) o denetimi atlıyor. Bu fonksiyon ve aşağıdaki
        doğrulayıcı, atlanan durumu yakalar.
        """
        return sorted(y for y in self.kanit if y not in ALAN_YOLLARI)

    @model_validator(mode="after")
    def _kanit_anahtarlarini_dogrula(self) -> Dosya:
        gecersiz = self.gecersiz_kanit_anahtarlari()
        if gecersiz:
            raise ValueError(
                f"Kanıt haritasında tanımsız alan yolu: {gecersiz}. "
                f"ALAN_YOLLARI kümesine ekleyin veya yazımı düzeltin."
            )
        return self

    def zayif_alanlar(self, esik: float = ESIK_INSAN_ONAYI) -> list[tuple[str, float]]:
        return zayif_alanlar(self.kanit, esik)

    def toplam_guven_hesapla(self) -> float:
        """En zayıf halka. Sonucu karar bloğuna da yazar."""
        deger = en_zayif_halka(self.kanit)
        self.karar.toplam_guven = deger
        return deger

    # -- özetler ------------------------------------------------------------

    @property
    def kisisel_veri_var_mi(self) -> bool:
        return bool(self.icerik.kisisel_veriler)

    @property
    def toplam_sure_ms(self) -> float:
        return sum(k.sure_ms for k in self.iz)

    def ozet_satiri(self) -> str:
        """Günlüğe ve arayüze tek satırlık durum."""
        return (
            f"{self.evrak_id} · {self.siniflandirma.belge_turu} · "
            f"güven {self.karar.toplam_guven:.2f} · "
            f"{len(self.cikti_yazi.linter_raporu.hatalar)} hata · "
            f"{self.toplam_sure_ms:.0f} ms"
        )

    @classmethod
    def json_semasi(cls) -> dict:
        """Veri yapısından JSON şeması üretir.

        risk_testi.py'de şemayı elle yazmıştım; buradan üretilen şema tek
        kaynak olur ve yapı değiştiğinde modele giden şema kendiliğinden
        güncellenir.
        """
        return cls.model_json_schema()


_VARSAYILAN_DOSYA: Dosya | None = None


def _varsayilan_dosya() -> Dosya:
    """Hiç dokunulmamış bir Dosya. alan_dolu_mu karşılaştırması için.

    Bir kez üretilip yeniden kullanılıyor; her çağrıda yeni nesne kurmak
    43 alan × belge sayısı kadar gereksiz iş demek.
    """
    global _VARSAYILAN_DOSYA
    if _VARSAYILAN_DOSYA is None:
        _VARSAYILAN_DOSYA = Dosya()
    return _VARSAYILAN_DOSYA


# =============================================================================
# KENDİ TESTİ
# =============================================================================


def _kendi_testi() -> int:
    """Yapının iç tutarlılığını denetler. Dış bağımlılığı yoktur.

    ADIM 5'in bitti kriteri: boş bir evrak nesnesi oluşturulabiliyor, JSON'a
    çevrilebiliyor, JSON şeması üretilebiliyor. Üçü de burada sınanıyor,
    üstüne yapının kendi içindeki sözleşmeler de denetleniyor.
    """
    hatalar = 0

    def kontrol(ad: str, kosul: bool, ayrinti: str = "") -> None:
        nonlocal hatalar
        if kosul:
            print(f"  ✓ {ad}")
        else:
            hatalar += 1
            print(f"  ✗ {ad}" + (f" — {ayrinti}" if ayrinti else ""))

    print("Sözlük:")
    kontrol("her belge türü bir kategoride",
            not (set(GelenTur) - set().union(*KATEGORILER.values())
                 - {GelenTur.BILINMIYOR}))
    kontrol("şartname 6.4.2'nin üç türü üretilebilir listesinde",
            all(t in set(UretilecekTur) for t in
                ("ust_yazi", "cevap_yazisi", "bilgilendirme_yazisi")))
    kontrol("her kanıt yöntemine öncelik atanmış",
            set(KanitYontemi) == set(YONTEM_ONCELIGI),
            f"eksik: {set(KanitYontemi) - set(YONTEM_ONCELIGI)}")
    kontrol("varsayılan en düşük öncelikte",
            yontem_onceligi(KanitYontemi.VARSAYILAN)
            < min(yontem_onceligi(y) for y in KanitYontemi
                  if y != KanitYontemi.VARSAYILAN))
    kontrol("insan en yüksek öncelikte",
            yontem_onceligi(KanitYontemi.INSAN)
            == max(YONTEM_ONCELIGI.values()))
    kontrol("gizlilik sırası artan",
            gizlilik_seviyesi(None)
            < gizlilik_seviyesi(GizlilikDerecesi.HIZMETE_OZEL)
            < gizlilik_seviyesi(GizlilikDerecesi.GIZLI)
            < gizlilik_seviyesi(GizlilikDerecesi.COK_GIZLI))
    kontrol("kaldırılan 'Özel' derecesi listede değil",
            "Özel" not in {str(g) for g in GizlilikDerecesi})
    kontrol("yasaklı ivedilik ibareleri izinli kümede değil",
            not ({i.upper() for i in YASAKLI_IVEDILIK}
                 & {str(i).upper() for i in Ivedilik}))

    print("\nGüven doğrulama:")
    for ham, beklenen_gecerli in [(0.85, True), (703.487, False), (90.0, False),
                                  (1.75, False), (-0.2, False), (True, False),
                                  ("yüksek", False), (None, False), (1.0, True)]:
        k = Kanit(yontem=KanitYontemi.LLM, ureten="test", guven=ham)
        kontrol(f"guven={ham!r} -> {k.guven:.2f}",
                k.guven_gecerliydi is beklenen_gecerli and 0.0 <= k.guven <= 1.0)

    print("\nYöntem önceliği:")
    regex = Kanit(yontem=KanitYontemi.REGEX, ureten="a2_ayristirma", guven=0.70)
    llm = Kanit(yontem=KanitYontemi.LLM, ureten="a3_siniflandirma", guven=0.99)
    insan = Kanit(yontem=KanitYontemi.INSAN, ureten="kullanici", guven=0.30)
    varsayilan = Kanit(yontem=KanitYontemi.VARSAYILAN, ureten="sistem", guven=0.99)
    kontrol("LLM(0.99) regex(0.70)'i ezemiyor", not daha_guvenilir(llm, regex))
    kontrol("regex(0.70) LLM(0.99)'u eziyor", daha_guvenilir(regex, llm))
    kontrol("insan(0.30) regex(0.70)'i eziyor", daha_guvenilir(insan, regex))
    kontrol("varsayılan(0.99) LLM(0.99)'u ezemiyor",
            not daha_guvenilir(varsayilan, llm))

    print("\nSayı ayrıştırma:")
    kontrol("yeni biçim çözümleniyor",
            sayi_bolumleri("E-71368504-010.06.01-4471829").sdp == "010.06.01")
    kontrol("2020 öncesi biçim reddediliyor",
            sayi_bolumleri("96321565-774.09.03-E.79291") is None)
    kontrol("eğik çizgili biçim reddediliyor",
            sayi_bolumleri("E/68103562/823.02/138739") is None)
    kontrol("boş sayı çökmüyor", sayi_bolumleri(None) is None)

    print("\nKişisel veri:")
    v = Varlik(tip=VarlikTipi.TCKN, deger="10000000140")
    kontrol("TCKN otomatik kişisel veri işaretleniyor", v.kisisel_veri)
    kontrol("kurum adı kişisel veri sayılmıyor",
            not Varlik(tip=VarlikTipi.KURUM_ADI, deger="YÖK").kisisel_veri)

    print("\nMevzuata aykırı ibareler kayıt altına alınıyor:")
    u = Ustveri(ivedilik_ham="ACİL", gizlilik_ham="Özel")
    kontrol("ACİL ham alanda saklanıyor, çözümlenmiş boş",
            u.ivedilik_ham == "ACİL" and u.ivedilik is None)
    kontrol("G-04 ihlali tespit ediliyor", not u.ivedilik_gecerli_mi)
    kontrol("G-02 ihlali tespit ediliyor", not u.gizlilik_gecerli_mi)
    kontrol("kurallara uygun belgede ihlal yok",
            Ustveri(ivedilik=Ivedilik.ACELE).ivedilik_gecerli_mi)
    kontrol("ivedilik hiç yoksa ihlal yok", Ustveri().ivedilik_gecerli_mi)

    print("\nAlan yolları — yapıyla sözleşme:")
    d = Dosya()
    cozulmeyen = []
    for yol in sorted(ALAN_YOLLARI):
        dugum = d
        for parca in yol.split("."):
            if not hasattr(dugum, parca):
                cozulmeyen.append(yol)
                break
            dugum = getattr(dugum, parca)
            if dugum is None:
                break
    kontrol(f"{len(ALAN_YOLLARI)} yolun tamamı yapıda karşılık buluyor",
            not cozulmeyen, f"çözülmeyen: {cozulmeyen}")
    kontrol("deger_al nokta yolundan okuyor",
            Dosya(metin="deneme").deger_al("metin") == "deneme")
    kontrol("deger_al olmayan yolda çökmüyor",
            d.deger_al("yok.boyle.bir.sey") is None)

    print("\nKanıt haritası:")
    d2 = Dosya(ustveri=Ustveri(sayi="E-71368504-010.06.01-4471829"))
    kontrol("tanımsız yol reddediliyor",
            _hata_veriyor_mu(lambda: d2.kanit_ekle(
                "ustveri.sayı", Kanit(yontem=KanitYontemi.REGEX, ureten="x"))))
    kontrol("kanıtsız dolu alan yakalanıyor",
            "ustveri.sayi" in d2.kanitsiz_alanlar())
    d2.kanit_ekle("ustveri.sayi", regex)
    kontrol("kanıt eklenince listeden düşüyor",
            "ustveri.sayi" not in d2.kanitsiz_alanlar())
    kontrol("zayıf kanıt mevcut kanıdı ezemiyor",
            d2.kanit_ekle("ustveri.sayi", llm) is False)
    kontrol("insan kanıtı ezebiliyor",
            d2.kanit_ekle("ustveri.sayi", insan) is True)
    kontrol("zorla=True korumayı aşıyor",
            d2.kanit_ekle("ustveri.sayi", llm, zorla=True) is True)

    print("\nToplam güven:")
    d3 = Dosya()
    d3.kanit["ustveri.sayi"] = Kanit(yontem=KanitYontemi.REGEX, ureten="a", guven=0.95)
    d3.kanit["ustveri.konu"] = Kanit(yontem=KanitYontemi.LLM, ureten="b", guven=0.95)
    d3.kanit["siniflandirma.belge_turu"] = Kanit(
        yontem=KanitYontemi.LLM, ureten="c", guven=0.35)
    kontrol("en zayıf halka alınıyor (ortalama değil)",
            abs(d3.toplam_guven_hesapla() - 0.35) < 1e-9)
    kontrol("zayıf alan raporlanıyor",
            d3.zayif_alanlar()[0][0] == "siniflandirma.belge_turu")

    print("\nLinter raporu:")
    r = LinterRaporu(bulgular=[
        LinterBulgusu(kural_id="S-01", baslik="Sayı zorunludur", onem=Onem.HATA),
        LinterBulgusu(kural_id="I-05", baslik="İlgiler sırasında değil",
                      onem=Onem.UYARI),
    ])
    kontrol("yalnızca hata düzeyi raporu düşürüyor",
            not r.gecti_mi and len(r.hatalar) == 1 and len(r.uyarilar) == 1)
    kontrol("hatasız rapor geçiyor", LinterRaporu().gecti_mi)

    print("\nGerileme kontrolleri (düzeltilmiş hatalar):")
    # 1) alan_dolu_mu öntanımlıyı dolu sayıyordu; boş Dosya'da 4 alan
    #    "kanıtsız" diye raporlanıyor ve fonksiyon teste bağlanamıyordu.
    kontrol("boş Dosya'da kanıtsız alan yok", Dosya().kanitsiz_alanlar() == [])
    dd = Dosya()
    dd.ustveri.konu = "X"
    kontrol("doldurulan alan kanıtsız olarak yakalanıyor",
            dd.kanitsiz_alanlar() == ["ustveri.konu"])
    # 2) kanit sözlüğüne doğrudan yazmak yol denetimini atlıyordu.
    dd2 = Dosya()
    dd2.kanit["uydurma.yol"] = Kanit(yontem=KanitYontemi.REGEX, ureten="t")
    kontrol("tanımsız kanıt anahtarı tespit ediliyor",
            dd2.gecersiz_kanit_anahtarlari() == ["uydurma.yol"])
    kontrol("tanımsız kanıt anahtarı JSON turunda yakalanıyor",
            _hata_veriyor_mu(
                lambda: Dosya.model_validate_json(dd2.model_dump_json())))
    # 3) gizlilik_seviyesi tanınmayan dereceyi sessizce 0 sayıyordu;
    #    EK-05 denetimi gürültülü girdide sessizce geçerdi.
    kontrol("tanınmayan gizlilik derecesi hata veriyor",
            _hata_veriyor_mu(lambda: gizlilik_seviyesi("Cok Gizli")))
    kontrol("boş gizlilik derecesi hata vermiyor", gizlilik_seviyesi("") == 0)

    print("\nBitti kriteri (ADIM 5):")
    bos = Dosya()
    kontrol("boş evrak nesnesi oluşturuluyor", isinstance(bos, Dosya))
    j = bos.model_dump_json()
    kontrol("JSON'a çevriliyor", len(j) > 0)
    kontrol("JSON'dan geri okunuyor",
            Dosya.model_validate_json(j).evrak_id == bos.evrak_id)
    sema = Dosya.json_semasi()
    kontrol("JSON şeması üretiliyor",
            isinstance(sema, dict) and "properties" in sema)
    kontrol("şemada belge türü enum'u yer alıyor",
            "GelenTur" in str(sema))

    print(f"\n{'Tümü geçti.' if hatalar == 0 else f'{hatalar} kontrol başarısız.'}")
    return 0 if hatalar == 0 else 1


def _hata_veriyor_mu(fn) -> bool:
    try:
        fn()
        return False
    except Exception:
        return True


if __name__ == "__main__":
    import sys as _sys

    print(f"veri_yapisi.py sürüm {SURUM}")
    print(f"  gelen belge türü      : {len(GelenTur)}")
    print(f"  üretilecek yazı türü  : {len(UretilecekTur)}")
    print(f"  varlık tipi           : {len(VarlikTipi)} "
          f"({len(KISISEL_VERI_TIPLERI)} tanesi kişisel veri)")
    print(f"  tanımlı alan yolu     : {len(ALAN_YOLLARI)}")
    print()
    _sys.exit(_kendi_testi())
