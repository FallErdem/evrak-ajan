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

from enum import StrEnum

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
    "ustveri.imza_sahibi_unvan",
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


if __name__ == "__main__":
    print(f"veri_yapisi.py sürüm {SURUM}")
    print(f"  gelen belge türü      : {len(GelenTur)}")
    print(f"  üretilecek yazı türü  : {len(UretilecekTur)}")
    print(f"  varlık tipi           : {len(VarlikTipi)} "
          f"({len(KISISEL_VERI_TIPLERI)} tanesi kişisel veri)")
    print(f"  tanımlı alan yolu     : {len(ALAN_YOLLARI)}")
