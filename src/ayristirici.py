"""Ayrıştırıcı — boru hattının 2. adımı. Satırlardan üstveri alanlarını çeker.

MELEZ bileşen: gövdesi regex, belirsiz alanlar Anlama adımına bırakılır.
Bu dosyada LLM YOK.

Girdi : Okuyucu'nun ürettiği Satir listesi
Çıktı : Ustveri + her alan için Kanit

NEDEN REGEX YETİYOR
-------------------
Resmî yazının başlık bloğu Yönetmelik m.10-14 ile SABİTLENMİŞ:

    Sayı : E-24316060-010.06-66473254 04.05.2026
    Konu : Genelgenin İlgili Birimlere Dağıtımı
    İlgi : 10.04.2026 tarihli ve E-55461037-010.06-1868571 sayılı yazı.

    ANKARA İL MİLLÎ EĞİTİM MÜDÜRLÜĞÜNE

Ölçüldü (300 etiket): tarih 300/300 gg.aa.yyyy; sayı 168/168 kurum
yazısında E-DETSİS-SDP-SIRA; ilgi 120/120 {tarih, sayı}; ek 90/90
{adet, açıklama, sayfa}. Sıfır çeşitlilik. Modele sormak israf olurdu.

İKİ BELGE AİLESİ, İKİ YAPI
--------------------------
belge_sablonu.json vatandas_dilekcesi:

    "Dilekçenin resmî yazıdan yapısal farkı: BAŞLIK BLOĞU YOKTUR,
     SAYI SATIRI YOKTUR, KONU SATIRI YOKTUR."

Dilekçe doğrudan muhatapla başlar; tarih kimlik bloğuna gömülüdür:

    T.C. Kimlik No: 92088712760 29.04.2026

Ek listesi de farklı: kurumda "Ek: Tapu fotokopisi (1 Sayfa)",
dilekçede "EKLER: 1 adet" + "1 - Tapu fotokopisi".

ÖLÇÜLEMEYEN 24 BELGE — dürüst kayıt
-----------------------------------
24 belgenin etiketinde "2026/335" biçimli sayı var ama PDF bunu BASMIYOR
(hepsi ozel_tuzel_kisi gönderenli, 22'si bilgi edinme). Şablon zaten
dilekçede sayı satırı olmadığını söylüyor.

Bu belgelerde sayi=None DOĞRU sonuçtur. Değerlendirmede sayı skorundan
çıkarılmalıdır; yoksa var olmayan bir şeyi bulamadığı için ceza yazılır.

KANIT
-----
Her alan için Kanit üretilir: hangi yöntem, hangi güven, hangi satır,
hangi alıntı. `alinti` belgede BİREBİR geçen metindir — arayüz vurgulamayı
bunun üzerinden yapıyor. Bulunamayan alan için kanıt üretilmez ve değer
None kalır; uydurulmaz.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from dipnot import Satir
from veri_yapisi import (
    DagitimSatiri,
    DagitimTuru,
    Ek,
    Ilgi,
    Imza,
    Kanit,
    KanitYontemi,
    Konum,
    MuhatapTuru,
    Ustveri,
)

URETEN = "ayristirici"

# -----------------------------------------------------------------------------
# Kalıplar
# -----------------------------------------------------------------------------
#
# OCR 'ı' harfini 1, l, i olarak okuyabiliyor ve iki noktayı düşürebiliyor
# (ölçüldü, belge_020). Etiket kalıpları buna göre esnek; DEĞER kalıpları
# ise sıkı, çünkü uydurma bir sayı kabul etmektense boş bırakmak yeğdir.

_ETIKET_SAYI = re.compile(r"^\s*Say[ıi1l|]\s*[:：]?\s*", re.IGNORECASE)
_ETIKET_KONU = re.compile(r"^\s*Konu\s*[:：]?\s*", re.IGNORECASE)
# İki nokta OCR'da düşüyor (ölçüldü, tani.py belge_020/032/035:
# "İlgi 03.02.2026 tarihli ve E-... sayılı yazı."). Zorunlu tutulursa
# taranmış belgede ilgi hiç bulunamıyor; isteğe bağlı yapılırsa gövdedeki
# "İlgide kayıtlı..." atfı da eşleşir. Çözüm: iki noktayı gevşet, yerine
# DEĞERİN TARİHLE BAŞLAMASINI zorunlu tut. 120 ilgi satırının tamamı
# "gg.aa.yyyy tarihli ve ... sayılı yazı." biçiminde (kota.json ilgi).
_ETIKET_ILGI = re.compile(
    r"^\s*[İIi]lg[ıi1l|]\s*[:：]?\s+(?=\d{2}\.\d{2}\.\d{4})", re.IGNORECASE
)

# İki sayı biçimi var, ikisi de geçerli:
#
#   kurum   E-24316060-115.02.01-4471829   E-<DETSİS>-<SDP>-<kayıt>
#   şirket  2026/335                        <yıl>/<sıra>
#
# Şirket biçimi Resmî Yazışma Yönetmeliği'ne tabi değil (Yönetmelik özel
# hukuk tüzel kişilerini kapsamaz), bu yüzden DETSİS ve SDP taşımıyor.
# Pratik sonuç: şirket yazısında SDP kodu sayıdan OKUNAMAZ, tahmin edilir.
_SAYI_KURUM = re.compile(r"\bE-\d{8}-[\d.]+-\d+\b")
_SAYI_SIRKET = re.compile(r"\b(?:19|20)\d{2}/\d{1,6}\b")


def _sayi_ara(metin: str):
    """Önce kurum biçimi denenir; o daha özgül olduğu için önceliklidir."""
    return _SAYI_KURUM.search(metin) or _SAYI_SIRKET.search(metin)

# gg.aa.yyyy — 300/300 belgede bu biçim
_TARIH = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b")

# "Ek: Tapu fotokopisi (1 Sayfa)"  /  "Ek : Liste (2 Sayfa)"
_EK_KURUM = re.compile(r"^\s*Ek\s*[:：]\s*(.+?)\s*\((\d+)\s*Sayfa\)", re.IGNORECASE)
# "EKLER: 1 adet" (dilekçe)  /  "Ek: 2 adet" (kurum, çok ekli)
# Ölçüldü: 90 belgenin 72'sinde tek ek, 18'inde iki ek. Tek ekte açıklama
# aynı satırda, çok ekte alta numaralı liste geliyor.
_EK_SAYILI = re.compile(r"^\s*(?:EKLER|Ek)\s*[:：]\s*(\d+)\s*adet", re.IGNORECASE)
# "1 - Tapu fotokopisi"  /  "1 - Liste ve takvim (1) (2 Sayfa)"
# Tire OCR'da düşüyor (ölçüldü, belge_017: "1 Önceki basvuru sureti").
# İsteğe bağlı yapıldı; kalıp yalnızca "N adet" satırının ALTINDA veya
# ONUN KALANINDA kullanıldığı için serbest metinle karışmıyor.
_EK_MADDE = re.compile(
    r"^\s*(\d+)\s*[-–.]?\s*(.+?)(?:\s*\((\d+)\s*Sayfa\))?\s*$", re.IGNORECASE
)

_DAGITIM_BASLIK = re.compile(r"^\s*(DAĞITIM|DAGITIM)\s*[:：]?\s*$", re.IGNORECASE)
_GEREGI = re.compile(r"^\s*Gereği\s*[:：]?\s*$", re.IGNORECASE)
_BILGI = re.compile(r"^\s*Bilgi\s*[:：]?\s*$", re.IGNORECASE)

# Muhatap: büyük harfli, yönelme hâlinde biten satır.
# "ANKARA İL MİLLÎ EĞİTİM MÜDÜRLÜĞÜNE", "DAĞITIM YERLERİNE"
# OCR muhatap satırını ALTINDAKİ parantezli birim satırıyla BİRLEŞTİRİYOR
# (ölçüldü, tani.py — 6 taranmış belgenin 6'sında):
#
#     'YENİMAHALLE BELEDİYE BAŞKANLIĞINA (Fen İşleri Müdürlüğü)'
#
# Parantezin içi küçük harfli olduğu için "satırın tamamı büyük harf" kuralı
# çöküyor ve muhatap bulunamıyor. Muhatap bulunamayınca başlık/gövde sınırı
# da yok oluyor; aile, ilgi, tarih ve imza birlikte düşüyor. Tek kırık halka,
# dört kayıp.
#
# belge_009 taranmışlar içinde muhatabı yakalanan tek belgeydi. Sebebi şans
# değil: o belgede parantez satırı hiç yok.
#
# Çözüm: parantezli kuyruğu kalıbın DIŞINDA tut, ikinci gruba al.
# Acilis parantezi OCR'da dusuyor (olculdu, tani.py belge_089):
#     'GAZİ ÜNİVERSİTESİNE Öğrenci İşleri Daire Başkanlığı)'
# Bu yüzden '(' isteğe bağlı, ')' zorunlu. Kapanış parantezi güçlü bir çıpa:
# gövde cümlesi parantezle bitmez.
_MUHATAP = re.compile(
    r"^([^a-zçğıöşü]{8,}(?:NE|NA|ne|na))\s*(?:\(?([^)]*)\))?\s*$"
)

# Muhatabı belirsiz bırakılmış yazı. Gerçek yazışmada kullanılan bir kalıptır
# ve veri setinde muhatap_belirsiz kusurunun enjekte ettiği değerdir (10 belge,
# etiket kusur_ayrinti.enjekte_edilen = "İLGİLİ MAKAMA").
#
# Ayrı kalıp olarak tutuluyor çünkü iki şey aynı anda doğru olmalı:
# satır BULUNMUŞ sayılmalı ki aile/tarih/imza çağlayanı kopmasın, ama
# muhatap BELİRSİZ işaretlenmeli ki Denetçi bunu eksiklik olarak görsün.
_MUHATAP_BELIRSIZ = re.compile(r"^\s*[İIi]LG[İIi]L[İIi]\s+MAKAM(?:A|LARA)\s*$")

# Geniş muhatap kalıbı — yönelme hâlinin diğer biçimleri.
#
# NE/NA yalnızca İYELİK EKİ ALMIŞ adlarda çıkıyor:
#     Başkanlığı  -> Başkanlığı+NA        Müdürlüğü -> Müdürlüğü+NE
# İyelik eki almayan birim adı doğrudan yönelme alıyor ve başka harfle bitiyor:
#     Sekreterlik -> SEKRETERLİĞE         Daire Başkanlığı -> ...
#
# Ölçüldü (300 belge): belge_290'da muhatap 'GENEL SEKRETERLİĞE'. Kalıp
# görmedi, muhatap bulunamadı, ve konu devam satırı muhatabı yuttu:
#     konu -> 'Onaylı Örnek Talebi GENEL SEKRETERLİĞE'
#
# Ölçüt gevşetiliyor ama iki koruma var:
#   1. Bu kalıp ÜÇÜNCÜ turda deneniyor; NE/NA ve belirsiz kalıplar önce
#      kazanıyor. Yalnızca hiçbir aday yoksa devreye giriyor.
#   2. Satırda BOŞLUK zorunlu. Kurum adı çok kelimelidir; bu koşul
#      'ÇANKAYA/ANKARA' gibi tek parça büyük harfli dizileri eliyor.
#
# Nominatif kurum adları -I/-İ/-U/-Ü ile biter (Başkanlığı, Valiliği,
# Müdürlüğü, Rektörlüğü); yönelme -A/-E ile. Ayrım bu yüzden çalışıyor.
_MUHATAP_GENIS = re.compile(
    r"^([^a-zçğıöşü]{3,}\s[^a-zçğıöşü]{2,}[AEae])\s*(?:\(?([^)]*)\))?\s*$"
)
_PARANTEZ = re.compile(r"^\s*\((.+)\)\s*$")

# İmza bloğu: "Zeynep YILDIRIM Vali a. İl Millî Eğitim Müdürü"
# "Vali a." / "Bakan a." — yetki devri satırı, tek başına durur
_YETKI_DEVRI = re.compile(r"^(Vali|Bakan|Rektör|Başkan|Müdür|Kaymakam)\s*a\.\s*$")

# Kapanış: "...arz ederim." / "...rica ederim." / "...arz ve talep ederim."
#
# SATIR SONUNA ÇIPALANMIYOR. İki gerçek vaka çıpayı kırdı (ölçüldü, tani.py):
#
#     belge_009  '...gereğini arz ederim:.'      iki noktalama üst üste
#     belge_035  '...gereğini rica ederim. beş'  OCR "beş"i cümle sonuna atmış
#
# İkincisi okuyucu.py'nin dürüstçe kaydettiği sınır: bir OCR öğesinin
# İÇİNDEKİ kelime karışıklığı düzeltilemiyor. Çıpa bu karışıklığa dayanamaz.
#
# Çıpasız kalmak güvenli, çünkü _imza döngüsü "ederim" geçen SON satırı
# seçiyor ve kapanış cümlesi belgenin son cümlesidir.
_KAPANIS = re.compile(r"\bederim\b", re.IGNORECASE)

# "Zeynep YILDIRIM" — ad büyük harfle başlar, SOYAD tamamen büyük
_AD = r"[A-ZÇĞİÖŞÜ][a-zçğıöşüâî]+(?:\s+[A-ZÇĞİÖŞÜ][a-zçğıöşüâî]+)*\s+[A-ZÇĞİÖŞÜ]{2,}"
_AD_SOYAD = re.compile(rf"^{_AD}$")

# Ad satırının SONUNDA "İmza" kelimesi durabiliyor — ölçüldü 2026-08-24,
# gönderen ölçümünün açtığı körlük:
#
#     belge_017  'Öğrenci No: 2021452403 26.03.2026 Sultan AVCI İmza'
#     belge_070  'Adres: ... Telefon: 0558 330 46 50 26.01.2026 Onur ÖZKAN İmza'
#
# Özgün belgede "İmza" sağdaki imza kutusunun etiketi; okuyucu satırı
# soldan sağa birleştirdiği için adın peşine yapışıyor. Eski desen satır
# sonuna çıpalıydı ve bu satırları HİÇ görmüyordu.
#
# NEDEN FARK EDİLMEDİ: `ayristirici_dogrula.py` imza alanında 110 belgeyi
# muaf tutuyor ve dilekçeler o muafiyetin içinde. `_dilekce_imzasi`
# bugüne kadar ölçülmemişti; gönderen çıkarımı onu ilk kez bir sayıya
# bağladı (86/108 = %80).
#
# Kelime İSTEĞE BAĞLI ve YAKALANMIYOR: yalnızca çıpanın önünden geçmesine
# izin veriliyor, ada dahil edilmiyor.
_AD_SATIR_SONU = re.compile(rf"({_AD})(?:\s+[İIi]mza)?\s*$")

# İkinci geçiş: ad satırın ORTASINDA. Yalnızca `_dilekce_imzasi`'nın birinci
# geçişi hiçbir satırda tutmazsa kullanılır — bkz. oradaki ölçüm notu.
_AD_ORTA = re.compile(rf"({_AD})")

# OCR imza bloğunun üç satırını tek satıra sıkıştırıyor (ölçüldü, tani.py):
#     'Osman ASLAN Bakan a Genel Müdür'   (nokta da düşmüş: "Bakan a")
# _AD_SOYAD satırın TAMAMININ ad-soyad olmasını istediği için tutmuyor ve
# imza taranmış belgelerde 0/6 kalıyordu.
_IMZA_TEK_SATIR = re.compile(
    rf"^({_AD})\s+((?:Vali|Bakan|Rektör|Başkan|Müdür|Kaymakam)\s*a\.?)?\s*(.*)$"
)


# Belge ailesi — başlık bloğundan tespit edilir.
#
#   T.C. var           -> kurum yazısı  (Yönetmelik'e tabi, EBYS dipnotu var)
#   başlık var, T.C. yok -> şirket yazısı (antetli kâğıt, dipnot YOK)
#   başlık yok         -> vatandaş dilekçesi (sayı ve konu satırı yok)
#
# Ayrım sonraki adımlara gerekiyor: şirket yazısında doğrulama kodu ve QR
# aranmamalı, yokluğu eksiklik sayılmamalıdır.
# OCR başlık bloğunu tek satıra sıkıştırıyor (ölçüldü, tani.py):
#     'T.C. ÇANKAYA BELEDİYE BAŞKANLIĞI T.C. ÇANKAYA BELEDİYE BAŞKANLIĞI'
# Bu yüzden satırın TAMAMI değil, İÇİNDE aranıyor (search).
# "T.C. Kimlik No" dışarıda bırakıldı: dilekçe gövdesinde geçiyor,
# başlık sanılmamalı.
_TC_BASLIK = re.compile(r"\bT\.?\s*C\b\.?(?![\s.]*Kimlik)")
_SIRKET_EKI = re.compile(r"\b(Ltd\.?\s*Şti\.?|A\.?\s*Ş\.?|Limited|Anonim)\b",
                         re.IGNORECASE)


@dataclass
class AyristirmaSonucu:
    ustveri: Ustveri = field(default_factory=Ustveri)
    aile: str = "bilinmiyor"          # kurum | sirket | dilekce
    kanit: dict[str, Kanit] = field(default_factory=dict)
    muhatap_satiri: int | None = None      # gövdenin nerede başladığı
    kapanis_satiri: int | None = None      # gövdenin nerede bittiği
    uyarilar: list[str] = field(default_factory=list)

    @property
    def ozet(self) -> str:
        return f"{len(self.kanit)} alan bulundu"


def _kanit(alinti: str, satir_no: int, guven: float = 1.0,
           aciklama: str | None = None,
           yontem: KanitYontemi = KanitYontemi.REGEX) -> Kanit:
    """Alan kanıtı üretir.

    `yontem` 1.1.0'da parametre oldu. Varsayılan REGEX; mevcut çağrıların
    hiçbiri değişmedi. Gönderen çıkarımı SOZLUK kullanıyor: değer metinden
    desenle değil, birim/kurum KAYDINDAN geliyor. İkisini aynı yöntem adıyla
    kaydetmek izlenebilirliği bozardı — "bu adı nereden buldun" sorusunun
    cevabı farklı.
    """
    return Kanit(
        yontem=yontem,
        ureten=URETEN,
        guven=guven,
        alinti=alinti[:300],
        konum=Konum(sayfa=1, satir=satir_no + 1),   # Konum 1 tabanli
        aciklama=aciklama,
    )


def _tarihe_cevir(gun: str, ay: str, yil: str) -> date | None:
    try:
        return date(int(yil), int(ay), int(gun))
    except ValueError:
        return None


# -----------------------------------------------------------------------------
# Yapı tespiti
# -----------------------------------------------------------------------------


def _aile_tespit(satirlar: list[Satir], muhatap_indeksi: int | None,
                 dipnot_var: bool | None = None) -> str:
    """Belge ailesini başlık bloğundan tespit eder.

    Dilekçenin ayırt edici özelliği başlığın HİÇ olmaması: belge doğrudan
    muhatapla başlıyorsa dilekçedir.

    EN GÜÇLÜ İPUCU DİPNOT — metinsel değil, yapısal
    -----------------------------------------------
    EBSY dipnotu (güvenli elektronik imza + doğrulama kodu) yalnızca kamu
    kurumunun EBYS'sinden çıkan yazıda bulunur. Şirket antetli kâğıdında da,
    vatandaş dilekçesinde de yoktur — Resmî Yazışma Yönetmeliği özel hukuk
    tüzel kişilerini kapsamaz, dilekçe de EBYS üretimi değildir.

    Bu ayrım OCR'a bağımlı DEĞİL: dipnot bir metin değil, sayfanın altındaki
    bir blok. Okuyucu onu zaten ayırıyor.

    NEDEN GEREKLİ (ölçüldü, 300 belge koşusu + tani.py):
    OCR "T.C." başlığını düşürebiliyor ve 6 kurum yazısı 'sirket' sanıldı:

        belge_053  'ANKARA VALİLİĞİ İl Milli Eğitim Müdürlüğü'   <- T.C. yok
        belge_084  'YENİMAHALLE KAYMAKAMLIĞI'                    <- T.C. yok

    İkisinde de dipnot_bulundu=True. Yapısal ipucu metinsel ipucunun
    kaçırdığını yakalıyor. T.C. araması yedek olarak duruyor: dipnot
    bilgisi geçirilmezse (dipnot_var=None) eski davranış sürer.
    """
    if muhatap_indeksi is None:
        return "bilinmiyor"
    baslik = satirlar[:muhatap_indeksi]
    if not baslik:
        return "dilekce"
    if dipnot_var is True:
        return "kurum"
    for s in baslik:
        if _TC_BASLIK.search(s.metin):
            return "kurum"
    for s in baslik:
        if _SIRKET_EKI.search(s.metin):
            return "sirket"
    # Başlıkta sayı/konu satırı varsa kurumsal bir yazıdır; hangisi
    # olduğu belirsizse şirket varsayılır (T.C. bulunamadı).
    for s in baslik:
        if _ETIKET_SAYI.match(s.metin) or _ETIKET_KONU.match(s.metin):
            return "sirket"
    return "dilekce"


def _muhatap_satirini_bul(satirlar: list[Satir]) -> int | None:
    """Muhatap satırı başlık bloğunu gövdeden ayırır.

    Hem kurum yazısında hem dilekçede var; ikisinde de büyük harfli ve
    yönelme hâlinde biter. Bulunması kritik: "İlgi :" alanı ile gövdedeki
    "İlgide kayıtlı yazı" ifadesini ayırmanın yolu bu.
    """
    for i, s in enumerate(satirlar):
        if _MUHATAP.match(s.metin.strip()):
            return i
    # Belirsiz muhatap ikinci turda aranır: gerçek bir makam adı varsa
    # o kazanmalı, "İLGİLİ MAKAMA" ancak başka aday yoksa kabul edilir.
    for i, s in enumerate(satirlar):
        if _MUHATAP_BELIRSIZ.match(s.metin.strip()):
            return i
    # Üçüncü tur: yönelme hâlinin NE/NA dışındaki biçimleri.
    for i, s in enumerate(satirlar):
        if _MUHATAP_GENIS.match(s.metin.strip()):
            return i
    return None


# -----------------------------------------------------------------------------
# Alan çıkarıcılar
# -----------------------------------------------------------------------------


# İlgi satırının değişmez izi. Başlık bloğunda arama yaparken ilgi satırı
# ELENMELİDİR: içinde de resmî sayı ve tarih var, ama onlar BAŞKA belgenin.
_ILGI_IZI = re.compile(r"tarihli\s+ve|say[ıi]l[ıi]\s+yaz", re.IGNORECASE)

# Etiket satırının çevresinde kaç satır aranacağı.
_BASLIK_YARICAPI = 3


def _baslik_penceresi(satirlar: list[Satir], i: int):
    """Sayı etiketinin çevresindeki güvenli satırlar.

    İlgi, konu ve muhatap satırları elenir — oralardaki sayı ve tarih bu
    belgeye ait değildir.
    """
    for j in range(max(0, i - _BASLIK_YARICAPI),
                   min(len(satirlar), i + _BASLIK_YARICAPI + 1)):
        if j == i:
            continue
        metin = satirlar[j].metin
        cikti = metin.strip()
        if _ETIKET_ILGI.match(metin) or _ILGI_IZI.search(metin):
            continue
        if _ETIKET_KONU.match(metin):
            continue
        if _MUHATAP.match(cikti) or _MUHATAP_GENIS.match(cikti):
            continue
        yield j, metin


def _sayi_ve_tarih(satirlar: list[Satir], sonuc: AyristirmaSonucu) -> None:
    """Sayı ve tarih aynı satırda durur (yerlesim.yaml alanlar.tarih_konumu).

        Sayı : E-24316060-010.06-66473254 04.05.2026

    OCR bu düzeni iki şekilde bozabiliyor (ölçüldü, tani.py):

        belge_100   'Sayı E-32625594-106-46817055'      etiket + sayı
                    '23.03.2026'                        tarih ALT SATIRDA
        belge_208   'E-10213773-120.02-15060727 28.05.2026'   değer ÜSTTE
                    'Sayı'                                    etiket ALTTA

    Bu yüzden etiket satırı boş kalırsa çevresindeki başlık satırlarına
    bakılıyor. İlgi satırı elenir: oradaki sayı ve tarih BAŞKA belgeye ait.
    Bu yoldan gelen değerlerin güveni düşük (0.85) ve kanıtı ayrı satırı
    gösterir.
    """
    for i, s in enumerate(satirlar):
        if not _ETIKET_SAYI.match(s.metin):
            continue
        kalan = _ETIKET_SAYI.sub("", s.metin)

        m = _sayi_ara(kalan)
        if m:
            sonuc.ustveri.sayi = m.group(0)
            sonuc.kanit["ustveri.sayi"] = _kanit(m.group(0), i)

        t = _TARIH.search(kalan)
        if t:
            d = _tarihe_cevir(*t.groups())
            if d:
                sonuc.ustveri.tarih = d
                sonuc.ustveri.tarih_metin = t.group(0)
                sonuc.kanit["ustveri.tarih"] = _kanit(t.group(0), i)

        if sonuc.ustveri.sayi is None:
            for j, metin in _baslik_penceresi(satirlar, i):
                m2 = _sayi_ara(metin)
                if m2:
                    sonuc.ustveri.sayi = m2.group(0)
                    sonuc.kanit["ustveri.sayi"] = _kanit(
                        m2.group(0), j, guven=0.85,
                        aciklama="OCR sayıyı etiketinden ayırmış",
                    )
                    break
            else:
                # Etiket var, değer hiçbir yerde yok -> sayi_eksik. Uydurma yok.
                sonuc.uyarilar.append(
                    "Sayı satırı var ama resmî sayı bulunamadı")

        if sonuc.ustveri.tarih is None:
            for j, metin in _baslik_penceresi(satirlar, i):
                t2 = _TARIH.search(metin)
                if t2:
                    d2 = _tarihe_cevir(*t2.groups())
                    if d2:
                        sonuc.ustveri.tarih = d2
                        sonuc.ustveri.tarih_metin = t2.group(0)
                        sonuc.kanit["ustveri.tarih"] = _kanit(
                            t2.group(0), j, guven=0.85,
                            aciklama="OCR tarihi sayı satırından ayırmış",
                        )
                        break
        return


# Konu satırının sonuna sürüklenmiş tarih. OCR'da görülüyor (ölçüldü):
#     belge_265  'Kararın Uygulanması Hk. 29.04.2026'
# Sayı satırındaki tarih konu satırına düşmüş. Konu asla tarihle bitmez,
# bu yüzden ayıklamak güvenlidir — ve tarih hâlâ boşsa oradan kurtarılır.
_KONU_SONU_TARIH = re.compile(r"\s+(\d{2}\.\d{2}\.\d{4})\s*$")

# Aynı sürüklenmenin yarım hâli:  'Uygulama Öğretmeni Görevlendirmesi 18.'
_KONU_SONU_PARCA = re.compile(r"\s+\d{1,2}\.\s*$")

# Konu ikinci satıra taşmışsa devam satırı bunların HİÇBİRİ olmamalı.
_KONU_SINIRI = (_ETIKET_SAYI, _ETIKET_ILGI, _MUHATAP, _MUHATAP_BELIRSIZ,
                _MUHATAP_GENIS, _DAGITIM_BASLIK, _EK_KURUM, _EK_SAYILI,
                _PARANTEZ)

# Devam satırı kısa olur; bu uzunluğu aşan satır gövde metnidir.
_KONU_DEVAM_AZAMI = 45


def _konu_devami_mi(metin: str) -> bool:
    """Bu satır konunun ikinci satırı olabilir mi."""
    if not metin or len(metin) > _KONU_DEVAM_AZAMI:
        return False
    if any(k.match(metin) for k in _KONU_SINIRI):
        return False
    # İçinde resmî sayı varsa bu bir ilgi/sayı satırıdır, konu değil.
    return not _sayi_ara(metin)


def _konu(satirlar: list[Satir], sonuc: AyristirmaSonucu) -> None:
    for i, s in enumerate(satirlar):
        if not _ETIKET_KONU.match(s.metin):
            continue
        deger = _ETIKET_KONU.sub("", s.metin).strip()

        # Uzun konu ikinci satıra taşıyor (ölçüldü, 5 metin katmanlı belge):
        #     'Konu : Genelge Uygulamasında Karşılaşılan'
        #     'Tereddütler'
        # En çok iki devam satırı alınır; sınır kalıpları döngüyü keser.
        son_satir = i
        for j in range(i + 1, min(i + 3, len(satirlar))):
            devam = satirlar[j].metin.strip()
            if not _konu_devami_mi(devam):
                break
            deger = f"{deger} {devam}".strip()
            son_satir = j

        # Sürüklenmiş tarihi ayıkla, tarih boşsa kurtar.
        t = _KONU_SONU_TARIH.search(deger)
        if t:
            deger = _KONU_SONU_TARIH.sub("", deger).strip()
            if sonuc.ustveri.tarih is None:
                g, a, y = t.group(1).split(".")
                d = _tarihe_cevir(g, a, y)
                if d:
                    sonuc.ustveri.tarih = d
                    sonuc.ustveri.tarih_metin = t.group(1)
                    sonuc.kanit["ustveri.tarih"] = _kanit(
                        t.group(1), i, guven=0.70,
                        aciklama="OCR tarihi konu satırına sürüklemiş",
                    )
        deger = _KONU_SONU_PARCA.sub("", deger).strip()

        if deger:
            sonuc.ustveri.konu = deger
            sonuc.kanit["ustveri.konu"] = _kanit(
                deger, i,
                guven=1.0 if son_satir == i else 0.90,
                aciklama=None if son_satir == i else "Konu iki satıra taşmış",
            )
        return


def _ilgi(satirlar: list[Satir], sonuc: AyristirmaSonucu, sinir: int) -> None:
    """İlgi alanını çeker — yalnızca BAŞLIK BLOĞUNDAN.

    Kritik ayrım: "İlgi" hem alan hem gövde ifadesi olarak geçiyor.

        başlık : "İlgi : 10.04.2026 tarihli ve E-... sayılı yazı."   <- alan
        gövde  : "İlgide kayıtlı yazıda belirtilen hususlar..."      <- atıf
        gövde  : "İlgi'de kayıtlı yazı Okul Yeri Tahsis..."          <- atıf

    İkisini karıştırmak gövdenin ilk cümlesini ilgi alanı sanmak demektir.
    Ayrım iki katmanlı: (1) yalnızca muhatap satırının ÜSTÜNE bakılır,
    (2) kalıp iki nokta üst üste ZORUNLU tutulur ("İlgide" eşleşmez).
    """
    for i, s in enumerate(satirlar[:sinir]):
        if not _ETIKET_ILGI.match(s.metin):
            continue
        kalan = _ETIKET_ILGI.sub("", s.metin).strip()
        ilgi = Ilgi(ham=kalan)
        t = _TARIH.search(kalan)
        if t:
            ilgi.tarih = _tarihe_cevir(*t.groups())
            ilgi.tarih_metin = t.group(0)
        m = _sayi_ara(kalan)
        if m:
            ilgi.sayi = m.group(0)
        sonuc.ustveri.ilgi.append(ilgi)
        sonuc.kanit["ustveri.ilgi"] = _kanit(kalan, i)
        return


def _ekler(satirlar: list[Satir], sonuc: AyristirmaSonucu) -> None:
    """İki biçim: kurum yazısında tek satır, dilekçede iki satır."""
    for i, s in enumerate(satirlar):
        m = _EK_KURUM.match(s.metin)
        if m:
            sonuc.ustveri.ekler.append(
                Ek(ham=s.metin.strip(), sira=1,
                   aciklama=m.group(1).strip(), sayfa_sayisi=int(m.group(2)))
            )
            sonuc.kanit["ustveri.ekler"] = _kanit(s.metin.strip(), i)
            return

        m = _EK_SAYILI.match(s.metin)
        if m:
            adet = int(m.group(1))
            # OCR "EKLER: 1 adet" ile madde satırını birleştirebiliyor
            # (ölçüldü, belge_007: "EKLER: 1 adet 1 Başvuru formu").
            kalan = s.metin[m.end():].strip()
            if kalan:
                mk = _EK_MADDE.match(kalan)
                if mk:
                    sonuc.ustveri.ekler.append(
                        Ek(ham=kalan, sira=int(mk.group(1)),
                           aciklama=mk.group(2).strip(),
                           sayfa_sayisi=int(mk.group(3)) if mk.group(3) else None)
                    )
            for j in range(i + 1, min(i + 1 + adet + 2, len(satirlar))):
                mm = _EK_MADDE.match(satirlar[j].metin)
                if not mm:
                    continue
                sonuc.ustveri.ekler.append(
                    Ek(ham=satirlar[j].metin.strip(),
                       sira=int(mm.group(1)),
                       aciklama=mm.group(2).strip(),
                       sayfa_sayisi=int(mm.group(3)) if mm.group(3) else None)
                )
            sonuc.kanit["ustveri.ekler"] = _kanit(s.metin.strip(), i)
            return


def _dagitim(satirlar: list[Satir], sonuc: AyristirmaSonucu) -> None:
    """Dağıtım bloğu: 'Gereği:' ve 'Bilgi:' altındaki satırlar.

    Yalnızca 12/300 belgede var (ölçüldü) ama çoklu muhatap demek ve
    yönlendirmeyi doğrudan etkiliyor.
    """
    tur: DagitimTuru | None = None
    basladi = False
    for i, s in enumerate(satirlar):
        metin = s.metin.strip()
        if _DAGITIM_BASLIK.match(metin):
            basladi = True
            sonuc.kanit["ustveri.dagitim"] = _kanit(metin, i)
            continue
        if _GEREGI.match(metin):
            tur, basladi = DagitimTuru.GEREGI, True
            continue
        if _BILGI.match(metin):
            tur, basladi = DagitimTuru.BILGI, True
            continue
        if not basladi or not metin:
            continue
        if tur is None:
            continue
        # Dağıtım satırları muhatap adıdır; kalıp satırı değil.
        if len(metin) < 4 or _ETIKET_SAYI.match(metin):
            continue
        sonuc.ustveri.dagitim.append(
            DagitimSatiri(hedef=metin.lstrip("-– ").strip(), tur=tur,
                          sira=len(sonuc.ustveri.dagitim) + 1)
        )


def _muhatap(satirlar: list[Satir], sonuc: AyristirmaSonucu, indeks: int) -> None:
    ham = satirlar[indeks].metin.strip()

    # Belirsiz muhatap: satır var, makam adı yok. Uydurulmaz, işaretlenir.
    if _MUHATAP_BELIRSIZ.match(ham):
        sonuc.ustveri.muhatap.ham = ham
        sonuc.ustveri.muhatap.tur = MuhatapTuru.KAMU_IDARESI
        sonuc.uyarilar.append("Muhatap belirsiz: makam adı yazılmamış")
        sonuc.kanit["ustveri.muhatap"] = _kanit(
            ham, indeks, guven=0.30,
            aciklama="Belgede makam adı yerine genel ifade var",
        )
        return

    # Parantezli birim aynı satıra yapışmış olabilir (OCR).
    m = _MUHATAP.match(ham)
    genis = m is None
    if genis:
        m = _MUHATAP_GENIS.match(ham)
    makam = m.group(1).strip() if m else ham
    yapisik_birim = m.group(2).strip() if m and m.group(2) else None

    sonuc.ustveri.muhatap.ham = ham
    sonuc.ustveri.muhatap.idare = makam
    # "DAĞITIM YERLERİNE" özel bir muhatap türü — tek bir idare değil.
    sonuc.ustveri.muhatap.tur = (
        MuhatapTuru.DAGITIM_YERLERI
        if "DAĞITIM" in ham.upper() or "DAGITIM" in ham.upper()
        else MuhatapTuru.KAMU_IDARESI
    )
    sonuc.kanit["ustveri.muhatap"] = _kanit(
        ham, indeks,
        guven=0.85 if genis else 1.0,
        aciklama="Yönelme eki NE/NA dışı biçimde" if genis else None,
    )

    if yapisik_birim:
        sonuc.ustveri.muhatap.birim = yapisik_birim
        sonuc.kanit["ustveri.muhatap.birim"] = _kanit(
            ham, indeks, guven=0.90,
            aciklama="OCR muhatap ve birim satırlarını birleştirmiş",
        )
        return

    # Alt birim bir sonraki satırda, parantez içinde
    if indeks + 1 < len(satirlar):
        m = _PARANTEZ.match(satirlar[indeks + 1].metin.strip())
        if m:
            birim = m.group(1).strip()
            sonuc.ustveri.muhatap.birim = birim
            sonuc.kanit["ustveri.muhatap.birim"] = _kanit(
                satirlar[indeks + 1].metin.strip(), indeks + 1
            )


# -----------------------------------------------------------------------------
# Gönderen — 1.1.0'da eklendi
# -----------------------------------------------------------------------------
#
# NEDEN GEREKLİ
# -------------
# Yazar (AJAN 2) cevabı GELEN BELGENİN GÖNDERENİNE yazar. Gönderen
# bilinmeden taslağın muhatabı yazılamaz, arz/rica yönü de belirlenemez
# (ME-03). `ustveri.gonderen` yolu ALAN_YOLLARI'nda baştan tanımlıydı ama
# hiçbir zaman doldurulmuyordu.
#
# ÜÇ HAT, GÜÇLÜDEN ZAYIFA
# -----------------------
#   H-A  sayının 2. bölümü -> DETSİS -> birim/makam kaydı
#   H-B  antet bloğu       -> ad eşleştirme -> birim kaydı
#   H-C  dilekçede imza sahibi (gerçek kişi)
#
# NEDEN RAKAM ÖNCE, AD SONRA
# --------------------------
# Antetten ad okumak OCR'a açık. Ölçüldü (_aile_tespit notu): 6 kurum
# yazısında "T.C." satırı düşmüş, iki belgede başlık tek satıra sıkışmış.
# Sayının içindeki DETSİS numarası bozulmuyor — rakam, harf değil.
#
# ÖLÇÜLDÜ (300 etiket, `gonderen.detsis_no` cevap anahtarı):
#     DETSİS taşıyan belge           168 / 300
#     birimler.py indeksinde bulunan 165 / 168 = %98,2
#     bulunamayan                      3        veri setinde üretilmiş
#                                               liseler (detsis_kaynagi
#                                               = "sentetik")
# Kalan 132 belge dilekçe ve şirket yazısı; onlarda DETSİS zaten yok ve
# H-B/H-C devreye giriyor.
#
# İKİ HAT ÇELİŞİRSE
# -----------------
# DETSİS kazanır, ama çelişki UYARI olarak kaydedilir ve kanıtın
# açıklamasına yazılır. Sessizce birini seçmek, `sdp_kod_celiskisi`'nde
# öğrenilen dersin tekrarı olurdu: iki bağımsız kaynağın ayrışması bir
# arıza değil, BULGUDUR.

# Antet bloğu bu etiketlerden biriyle biter. Sayı/Konu/İlgi satırları ad
# eşleştirmesine girmemeli: ilgi satırı BAŞKA bir kurumun adını taşıyabilir.
_ANTET_BITISI = (_ETIKET_SAYI, _ETIKET_KONU, _ETIKET_ILGI)

# "T.C." tek başına bir idare adı değil; başlığın ilk satırıdır (Y 10/2).
_SADECE_TC = re.compile(r"^\s*T\.?\s*C\.?\s*$", re.IGNORECASE)


def _antet_bloku(satirlar: list[Satir], indeks: int | None) -> list[tuple[int, str]]:
    """Muhatap satırından önceki SAF başlık satırları.

    Ölçüldü (belge_025/031/048): muhatap satırının üstündeki blok başlığı
    ve etiketli alanları birlikte taşıyor —

        T.C. · GAZİ ÜNİVERSİTESİ REKTÖRLÜĞÜ · Mühendislik Fakültesi
        Dekanlığı · 'Sayı : ...' · 'Konu : ...' · 'İlgi : ...'

    İlk etiketli satırdan itibarası kesilir. Kesmezsek ilgi satırındaki
    üçüncü kurumun adı gönderen sanılabilir.

    MUHATAP SATIRI YOKSA ANTET DE YOKTUR — ölçüldü 2026-08-24
    ---------------------------------------------------------
    `indeks is None` iken bloğu belgenin tamamına açmak felakete yol
    açıyor: dilekçede Sayı/Konu satırı bulunmadığı için hiçbir yerde
    kesilmiyor ve MUHATAP SATIRI bloğun içine giriyor. belge_225 ve
    belge_234'te tam bu oldu —

        beklenen  Kemal ÖZKAN  (dilekçeyi yazan vatandaş)
        bulunan   Temel Eğitim Şube Müdürlüğü  (dilekçenin YAZILDIĞI yer)

    Gönderen ile muhatap birbirine karıştı; üstelik ikisi de tam eşleşme
    olduğu için güven yüksek göründü. Antetin bittiği yeri söyleyen tek
    çıpa muhatap satırıdır; çıpa yoksa bu hat KOŞMAZ. Sayısı olan belgede
    H-A zaten çalışıyor (belge_173 ve belge_181 böyle kurtuldu).
    """
    if indeks is None:
        return []
    blok: list[tuple[int, str]] = []
    for i in range(min(indeks, len(satirlar))):
        metin = satirlar[i].metin.strip()
        if any(k.match(metin) for k in _ANTET_BITISI):
            break
        if metin and not _SADECE_TC.match(metin):
            blok.append((i, metin))
    return blok


def _gonderen_detsisten(sonuc: AyristirmaSonucu) -> tuple[dict | None, str | None, str | None]:
    """Sayının 2. bölümünden gönderen kaydını arar.

    Döner: (ic_birim_kaydi, dis_makam_adi, detsis_no)
    Üçü de None ise sayı yok, biçimi tutmuyor ya da numara kayıtta değil.
    """
    from birimler import detsis_ile_birim_bul, dis_makam_bul
    from veri_yapisi import sayi_bolumleri

    bolumler = sayi_bolumleri(sonuc.ustveri.sayi)
    if bolumler is None:
        # Şirket sayısı (2026/103) DETSİS taşımaz; desen zaten tutmaz.
        return None, None, None
    no = bolumler.detsis
    birim = detsis_ile_birim_bul(no)
    if birim is not None:
        return birim, None, no
    return None, dis_makam_bul(no), no


# Dış makam adayları bu önekle işaretlenir; iç birim kodlarıyla
# karışmasınlar diye. Seviyeleri -1: tam eşleşme berabere kalırsa iç kayıt
# kazanır (modül başlığındaki "iç kayıt önce" kuralıyla aynı yön).
_DIS_ONEK = "dis:"
_DIS_SEVIYE = -1


def _gonderen_antetten(
    blok: list[tuple[int, str]]
) -> tuple[dict | None, str | None, float, int | None]:
    """Antet satırlarından gönderen kaydı arar. TAM EŞLEŞME ZORUNLU.

    Döner: (ic_birim_kaydi, dis_makam_adi, oran, satir_no)

    NEDEN BULANIK EŞLEŞTİRME YOK — muhataptan farklı bir problem
    ------------------------------------------------------------
    `metin.en_iyi_eslesme` muhatap için yazıldı ve orada varsayılan eşik
    0,75 doğru: 300 belgenin 300'ünde muhatap bu üç kurumun birimlerinden
    biri, yani DOĞRU CEVAP TABLODA. Gönderende bu geçerli değil —
    ölçüldü (300 etiket): 86 belge dış makamdan, 24'ü şirketten geliyor
    ve o adlar birim tablosunda YOK.

    Doğru cevabın tabloda olmadığı bir aramada bulanık eşik yanlış cevap
    üretir. ÖLÇÜLDÜ 2026-08-24:

        "ÇANKAYA BELEDİYE BAŞKANLIĞI"
            -> "Yenimahalle Belediye Başkanlığı"   oran 0.759

    Eşik 0,75. Yani sayısı silinmiş (sayi_eksik kusuru, 12 belge) bir
    Çankaya yazısında gönderen KENDİMİZ sanılırdı ve Yazar kendi kurumuna
    cevap yazardı. Bulgu değil, sessiz hata.

    Bu yüzden eşik 1,0: yalnızca katlanmış hâliyle BİREBİR geçen ad kabul
    edilir. Antet, gönderenin kendi EBYS'sinin bastığı kanonik addır;
    muhatap satırı gibi elle kısaltılmış değildir. Tutmuyorsa boş dönmek,
    yanlış birim döndürmekten iyidir — eksik alanı Denetçi görür, yanlış
    alanı kimse görmez.

    SINIR — RAPORA GİRECEK
    ----------------------
    İl MEM taşra başlığıdır ve mülki idare satırı taşır:

        T.C. / ANKARA VALİLİĞİ / İl Millî Eğitim Müdürlüğü

    Kurumun KENDİ kök adı ("Ankara İl Millî Eğitim Müdürlüğü") bu blokta
    birebir GEÇMEZ. Böyle bir yazıda H-B kök birimi bulamaz; tam eşleşen
    tek ad "Ankara Valiliği" olur ve gönderen valilik sanılır. Bu vaka
    yalnızca (a) gönderen İl MEM'in kendisiyse ve (b) sayı silinmişse
    ortaya çıkar; H-A varken hiç tetiklenmez. gonderen_dogrula.py bu
    durumu ayrı sayıyor.
    """
    if not blok:
        return None, None, 0.0, None
    from birimler import (
        _dis_makam_indeksi,
        antet_birimi,
        birim_bul,
        birimleri_yukle,
    )
    from metin import en_iyi_eslesme

    arama = " ".join(m for _, m in blok)
    adaylar = [(b["kod"], b["ad"], b["seviye"]) for b in birimleri_yukle()]
    adaylar += [(_DIS_ONEK + ad, ad, _DIS_SEVIYE)
                for ad in _dis_makam_indeksi().values()]

    kod, oran, ad = en_iyi_eslesme(arama, adaylar, esik=1.0)
    if kod is None:
        return None, None, oran, None

    if not kod.startswith(_DIS_ONEK):
        return birim_bul(kod), None, oran, blok[0][0]

    # Eşleşen ad bir DIŞ MAKAM. İki ihtimal var ve ayrılmaları şart:
    #
    #   1  gerçekten o makam yazmış      -> gönderen odur
    #   2  o ad bir kurumun ANTETİ       -> gönderen o kurumun birimi
    #
    # Ayrım, kurumun başlık kalıbının TAMAMININ antette bulunmasıdır.
    # ÖLÇÜLDÜ 2026-08-24: tek satıra bakan sürüm 26 yanlış çelişki ve
    # 2 yanlış gönderen üretti (belge_204, belge_283 — gerçekten valilik
    # ve kaymakamlık yazısı oldukları hâlde İl MEM sanıldılar).
    kurum_birimi = antet_birimi(arama)
    if kurum_birimi is None:
        return None, ad, oran, blok[0][0]
    return kurum_birimi, None, oran, blok[0][0]


def _sirket_adi(blok: list[tuple[int, str]]) -> tuple[str | None, int | None]:
    """Antetli kâğıttan şirket adını çeker.

    Şirket antetinde ad, adres ve telefon alt alta duruyor (ölçüldü,
    belge_025):

        EGE EĞİTİM HİZMETLERİ LTD. ŞTİ.
        Ergazi Mahallesi Zeytin Sokağı No: 112/8 Yenimahalle/ANKARA
        Tel: 0508 511 86 25

    Önce ticaret unvanı ekini (_SIRKET_EKI) taşıyan satır aranıyor; yoksa
    bloğun ilk satırı alınıyor.

    SINIR — RAPORA GİRECEK: bu kural TEK belgede (belge_025) gözlendi.
    Veri setinde 24 özel tüzel kişi yazısı var; oran ölçülmeden
    varsayılmamalı. gonderen_dogrula.py bunları ayrı raporluyor.
    """
    for i, metin in blok:
        if _SIRKET_EKI.search(metin):
            return metin, i
    return (blok[0][1], blok[0][0]) if blok else (None, None)


def _gonderen(satirlar: list[Satir], sonuc: AyristirmaSonucu,
              indeks: int | None) -> None:
    """Gelen belgeyi kimin yazdığını belirler. Bulunamazsa alan boş kalır."""
    from veri_yapisi import MuhatapTuru, Teskilat

    g = sonuc.ustveri.gonderen
    blok = _antet_bloku(satirlar, indeks)
    if blok:
        g.ham = " / ".join(m for _, m in blok)[:500]

    # --- H-C: dilekçe. Başlık bloğu YOKTUR, gönderen imza sahibidir. ------
    if sonuc.aile == "dilekce":
        ad = sonuc.ustveri.imza.ad
        if not ad:
            sonuc.uyarilar.append("Dilekçede imza sahibi bulunamadı; gönderen belirlenemedi")
            return
        g.ad = ad
        g.ham = g.ham or ad
        g.tur = MuhatapTuru.GERCEK_KISI
        imza_kaniti = sonuc.kanit.get("ustveri.imza.ad")
        sonuc.kanit["ustveri.gonderen"] = Kanit(
            yontem=KanitYontemi.HESAPLAMA,
            ureten=URETEN,
            # Güven imza kanıtından DEVRALINIYOR, yeniden uydurulmuyor:
            # gönderen bu belgede imzadan türetilmiş bir değerdir ve
            # ondan daha güvenilir olamaz.
            guven=imza_kaniti.guven if imza_kaniti else 0.70,
            alinti=ad[:300],
            konum=imza_kaniti.konum if imza_kaniti else None,
            aciklama="Dilekçede başlık bloğu yoktur; gönderen imza sahibidir",
        )
        return

    # --- H-A: DETSİS -------------------------------------------------------
    birim, dis_makam, detsis_no = _gonderen_detsisten(sonuc)

    # --- H-B: antet. H-A tutsa da koşuyor, çünkü ÇAPRAZ DOĞRULAMA yapıyor.
    # `sdp_kod_celiskisi`'nde öğrenilen ders: iki bağımsız kaynağın
    # ayrışması bir arıza değil, bulgudur. Sessizce birini seçmek, çelişkiyi
    # görünmez kılar.
    antet_birim, antet_dis, oran, antet_satiri = _gonderen_antetten(blok)

    sayi_kaniti = sonuc.kanit.get("ustveri.sayi")
    sayi_satiri = (sayi_kaniti.konum.satir - 1
                   if sayi_kaniti and sayi_kaniti.konum and sayi_kaniti.konum.satir
                   else 0)

    def _celiski_bildir(detsis_kaydi: dict | None, detsis_adi: str,
                        antet_kaydi: dict | None, antet_adi: str | None) -> bool:
        """İki hat gerçekten farklı bir MAKAM mı gösteriyor.

        AYNI KURUMUN İKİ BİRİMİ ÇELİŞKİ DEĞİLDİR. Antet bloğu birden çok
        satır taşır ve H-B tam eşleşmeyle bunlardan birini seçer; DETSİS
        daha özgül olanı verir. İkisi aynı kurumdaysa ayrışma değil,
        çözünürlük farkıdır.

        ÖLÇÜLDÜ 2026-08-24 (300 belge): bu ayrım konmadan 15 belgede
        yanlış alarm verildi — 14'ü "sayı İl MEM diyor, antet Ankara
        Valiliği diyor", 1'i Yenimahalle Kaymakamlığı. Üçü de aynı
        belgenin antet satırları. Yanlış alarm bu projede en tehlikeli
        hata türü; çelişki uyarısı ancak GERÇEK ayrışmada verilir.
        """
        if not antet_adi or antet_adi == detsis_adi:
            return False
        if (detsis_kaydi is not None and antet_kaydi is not None
                and detsis_kaydi["kurum_kodu"] == antet_kaydi["kurum_kodu"]):
            return False
        sonuc.uyarilar.append(
            f"Gönderen çelişkisi: sayıdaki DETSİS {detsis_no} "
            f"'{detsis_adi}' diyor, antet '{antet_adi}' diyor. DETSİS esas alındı."
        )
        return True

    if birim is not None:
        _birimi_yaz(g, birim, MuhatapTuru.KAMU_IDARESI, Teskilat)
        g.detsis_no = detsis_no
        antet_adi = antet_birim["ad"] if antet_birim else antet_dis
        celiski = _celiski_bildir(birim, birim["ad"], antet_birim, antet_adi)
        sonuc.kanit["ustveri.gonderen"] = _kanit(
            sonuc.ustveri.sayi or "", sayi_satiri,
            guven=0.90 if celiski else 1.0,
            aciklama=("Sayının ikinci bölümündeki DETSİS numarasından bulundu"
                      + ("; antet başka bir makam gösteriyor" if celiski else "")),
            yontem=KanitYontemi.SOZLUK,
        )
        return

    if dis_makam is not None:
        g.idare = dis_makam
        g.detsis_no = detsis_no
        g.tur = MuhatapTuru.KAMU_IDARESI
        antet_adi = antet_birim["ad"] if antet_birim else antet_dis
        celiski = _celiski_bildir(None, dis_makam, antet_birim, antet_adi)
        sonuc.kanit["ustveri.gonderen"] = _kanit(
            sonuc.ustveri.sayi or "", sayi_satiri,
            guven=0.90 if celiski else 1.0,
            aciklama=("DETSİS numarası kurum kaydımızda dış makam olarak bulundu"
                      + ("; antet başka bir makam gösteriyor" if celiski else "")),
            yontem=KanitYontemi.SOZLUK,
        )
        return

    # --- H-B tek başına ----------------------------------------------------
    if antet_birim is not None or antet_dis is not None:
        if antet_birim is not None:
            _birimi_yaz(g, antet_birim, MuhatapTuru.KAMU_IDARESI, Teskilat)
            gosterilen = antet_birim["ad"]
        else:
            g.idare = antet_dis
            g.tur = MuhatapTuru.KAMU_IDARESI
            gosterilen = antet_dis
        sonuc.kanit["ustveri.gonderen"] = _kanit(
            g.ham or gosterilen, antet_satiri or 0,
            # Tam eşleşme olsa bile DETSİS hattının 1,0'ına çıkarılmıyor:
            # eşleşen ad antette OCR'dan geçmiş, numara geçmemişti.
            guven=0.90,
            aciklama=("Sayıda kullanılabilir DETSİS yok; gönderen antet "
                      "bloğundan tam ad eşleşmesiyle bulundu"),
            yontem=KanitYontemi.SOZLUK,
        )
        return

    # --- Şirket: kayıtta olmayan tüzel kişi --------------------------------
    if sonuc.aile == "sirket":
        ad, satir = _sirket_adi(blok)
        if ad:
            g.idare = ad[:300]
            g.tur = MuhatapTuru.OZEL_HUKUK_TUZEL_KISI
            sonuc.kanit["ustveri.gonderen"] = _kanit(
                ad, satir or 0, guven=0.80,
                aciklama="Antetli kâğıt; kamu kaydında bulunmayan tüzel kişi",
            )
            return

    if detsis_no:
        sonuc.uyarilar.append(
            f"Gönderen DETSİS {detsis_no} kurum kaydında yok ve antet "
            f"eşleşmedi; gönderen belirlenemedi"
        )
    else:
        sonuc.uyarilar.append("Gönderen belirlenemedi")


def _birimi_yaz(g, birim: dict, tur, Teskilat) -> None:
    """Birim kaydını Taraf alanlarına dağıtır.

    `idare` KÖK KURUM, `birim` alt birimdir. Seviye 0 kaydında ikisi aynı
    şey olurdu; o durumda birim boş bırakılıyor — "Gazi Üniversitesi
    Rektörlüğü (Gazi Üniversitesi Rektörlüğü)" anlamsız.
    """
    from birimler import kurum_profili

    g.idare = birim["kurum"]
    g.birim = birim["ad"] if birim["seviye"] != 0 else None
    g.tur = tur
    profil = kurum_profili(birim["kurum_kodu"])
    if profil and profil.get("teskilat"):
        try:
            g.teskilat = Teskilat(profil["teskilat"])
        except ValueError:
            pass


def _vatandas_tarihi(satirlar: list[Satir], sonuc: AyristirmaSonucu,
                     sinir: int) -> None:
    """Dilekçede tarih kimlik bloğuna gömülü, etiketi yok.

        T.C. Kimlik No: 92088712760 29.04.2026
        Adres:Demetevler Mahallesi Nergis Sokak No: 82/14 29.04.2026

    Gövdede geçen tarihlerle karışmasın diye YALNIZCA muhatap satırının
    ALTINDAKİ son tarih alınıyor — imza bloğu belgenin sonundadır.
    Güven 0.90: konum çıkarımına dayanıyor, etiketli alan kadar kesin değil.
    """
    if sonuc.ustveri.tarih is not None:
        return
    son: tuple[str, int] | None = None
    for i in range(sinir, len(satirlar)):
        t = _TARIH.search(satirlar[i].metin)
        if t:
            son = (t.group(0), i)
    if son is None:
        return
    m = _TARIH.search(son[0])
    d = _tarihe_cevir(*m.groups()) if m else None
    if d:
        sonuc.ustveri.tarih = d
        sonuc.ustveri.tarih_metin = son[0]
        sonuc.kanit["ustveri.tarih"] = _kanit(
            son[0], son[1], guven=0.90,
            aciklama="Dilekçede tarih etiketi yok; imza bloğundan çıkarıldı",
        )


def _imza(satirlar: list[Satir], sonuc: AyristirmaSonucu, sinir: int) -> None:
    """İmza bloğunu çeker. İki aile, iki yapı.

    KURUM YAZISI — kapanıştan sonra alt alta:

        gereğini arz ederim.
        Zeynep YILDIRIM            <- ad
        Vali a.                    <- yetki devri (İSTEĞE BAĞLI)
        İl Millî Eğitim Müdürü     <- unvan

    Yetki devri her zaman yok; bazen doğrudan unvan gelir (Mehmet ŞİMŞEK /
    Kaymakam). İlk yazdığım kural yetki devrini ZORUNLU sayıyordu ve
    imzaların yarısını kaçırdı.

    DİLEKÇE — ad adres satırının SONUNA yapışık, çünkü özgün belgede
    adres solda, ad sağda yan yana duruyor:

        Adres:Çiğdemtepe Mahallesi Ihlamur Caddesi No: 99/20 Hatice KOÇ
    """
    kapanis = None
    for i in range(sinir, len(satirlar)):
        if _KAPANIS.search(satirlar[i].metin):
            kapanis = i
    if kapanis is None:
        _dilekce_imzasi(satirlar, sonuc, sinir)
        return

    # Gövdenin bittiği satır. Zaten hesaplandı; dışarı vermezsek her
    # kullanacak olan yeniden hesaplar. Dosya.metin bu sayıdan kurulur.
    sonuc.kapanis_satiri = kapanis

    ad = unvan = yetki = None
    ad_satiri = unvan_satiri = None
    for i in range(kapanis + 1, min(kapanis + 5, len(satirlar))):
        metin = satirlar[i].metin.strip()
        if not metin or _DAGITIM_BASLIK.match(metin) or metin.lower().startswith("ek"):
            break
        if _YETKI_DEVRI.match(metin):
            yetki = metin
            continue
        if ad is None and _AD_SOYAD.match(metin):
            ad, ad_satiri = metin, i
            continue
        if unvan is None and metin.strip().casefold() not in ("imza", "i̇mza"):
            unvan, unvan_satiri = metin, i

    if ad is None:
        # Üç satır tek satıra sıkışmış olabilir (OCR).
        for i in range(kapanis + 1, min(kapanis + 5, len(satirlar))):
            metin = satirlar[i].metin.strip()
            if not metin or metin.lower().startswith("ek"):
                break
            m = _IMZA_TEK_SATIR.match(metin)
            if m:
                ad, ad_satiri = m.group(1).strip(), i
                yetki = (m.group(2) or "").strip() or None
                unvan = (m.group(3) or "").strip() or None
                if unvan and unvan.casefold() in ("imza", "i̇mza"):
                    unvan = None
                unvan_satiri = i
                break

    if ad is None:
        _dilekce_imzasi(satirlar, sonuc, sinir)
        return

    sonuc.ustveri.imza.ad = ad
    sonuc.ustveri.imza.unvan = unvan
    sonuc.ustveri.imza.yetki_devri = yetki
    sonuc.ustveri.imza.ham = " ".join(x for x in (ad, yetki, unvan) if x)
    sonuc.kanit["ustveri.imza.ad"] = _kanit(ad, ad_satiri, guven=0.85)
    if unvan:
        sonuc.kanit["ustveri.imza.unvan"] = _kanit(unvan, unvan_satiri, guven=0.85)
    sonuc.kanit["ustveri.imza"] = _kanit(sonuc.ustveri.imza.ham, ad_satiri, guven=0.85)


def _dilekce_imzasi(satirlar: list[Satir], sonuc: AyristirmaSonucu,
                    sinir: int) -> None:
    """Dilekçede imza sahibinin adını arar. İki geçiş.

    Güven 0.75: kurum yazısındakinden düşük, çünkü ad başka metne yapışık
    ve ayrım yalnızca büyük harf kalıbına dayanıyor.

    GEÇİŞ 1 — satır sonu.  Düzgün yerleşimde ad kimlik bloğunun son
    öğesidir: 'Adres: ... No: 99/20 Hatice KOÇ'.

    GEÇİŞ 2 — satır ortası.  Taranmış belgede OCR kimlik bloğunun üç dört
    satırını tek satıra sıkıştırıyor ve ad ORTADA kalıyor (ölçüldü
    2026-08-24, tani_dilekce.py):

        belge_155  '... Öğrenci No: 2023337225 Salih TURAN Adres: Barıştepe
                    Mahallesi ... İmza Yenimahalle/ANKARA Telefon: ...'
        belge_299  '... Adres: Yakacık Mahallesi Papatya Sokak No: 119/8
                    Elif TURAN Yenimahalle/ANKARA İmza Telefon: ...'

    İkinci geçiş yalnızca birincisi hiçbir satırda tutmazsa koşar; düzgün
    belgelerde davranış değişmez.

    YANLIŞ BULUŞ RİSKİ ÖLÇÜLDÜ — sıfır çıktı ama sıfır değil
    -------------------------------------------------------
    Tanı çıktısındaki 33 gerçek kimlik bloğu satırında ikinci geçiş 2 doğru
    ad kazandırdı, 0 yanlış üretti. Riskli kalıp şudur: OCR "Yenimahalle/
    ANKARA" içindeki eğik çizgiyi BOŞLUĞA çevirirse 'Yenimahalle ANKARA'
    ad kalıbına uyar. Bu 300 belgede hiç görülmedi ve BİRİNCİ GEÇİŞ DE aynı
    tuzağa düşüyor — ikinci geçiş yeni risk eklemiyor, mevcut riski
    paylaşıyor. Rapora böyle yazılacak.
    """
    for desen, nerede in ((_AD_SATIR_SONU, "satır sonundan"),
                          (_AD_ORTA, "satır içinden")):
        for i in range(len(satirlar) - 1, sinir - 1, -1):
            m = desen.search(satirlar[i].metin)
            if not m:
                continue
            ad = m.group(1).strip()
            sonuc.ustveri.imza.ad = ad
            sonuc.ustveri.imza.ham = ad
            sonuc.kanit["ustveri.imza.ad"] = _kanit(
                ad, i, guven=0.75,
                aciklama=f"Dilekçede ad adres bloğuna yapışık; {nerede} alındı",
            )
            return



# -----------------------------------------------------------------------------
# Ana giriş
# -----------------------------------------------------------------------------


def ayristir(satirlar: list[Satir],
             dipnot_var: bool | None = None) -> AyristirmaSonucu:
    """Satırlardan üstveri alanlarını çeker.

    dipnot_var: okuyucunun `ayrilmis.dipnot_bulundu` değeri. Verilirse
    kurum/şirket ayrımı bununla yapılır — bkz. _aile_tespit. Verilmezse
    eski davranış sürer, çağıranların hiçbiri kırılmaz.

    Bulunamayan alan None kalır ve kanıt üretilmez. Uydurma yok:
    bir alanın yokluğu, Denetçi'nin yakalayacağı bir bulgudur.
    """
    sonuc = AyristirmaSonucu()
    if not satirlar:
        sonuc.uyarilar.append("Satır yok")
        return sonuc

    indeks = _muhatap_satirini_bul(satirlar)
    sonuc.muhatap_satiri = indeks
    sonuc.aile = _aile_tespit(satirlar, indeks, dipnot_var)
    sinir = indeks if indeks is not None else 0

    _sayi_ve_tarih(satirlar, sonuc)
    _konu(satirlar, sonuc)
    _ilgi(satirlar, sonuc, sinir if sinir else len(satirlar))
    _ekler(satirlar, sonuc)
    _dagitim(satirlar, sonuc)

    if indeks is not None:
        _muhatap(satirlar, sonuc, indeks)
        # Gövdeden tarih çıkarımı YALNIZCA dilekçede meşru. Kurum ve şirket
        # yazısında tarihin yeri bellidir (sayı satırı); orada yoksa YOKTUR.
        # Gövdeden tahmin etmek uydurmadır — ölçüldü, belge_100 ve belge_208'de
        # gövdedeki "01.01.2026 tarihinde yürürlüğe girmiştir" cümlesi belge
        # tarihi sanılıyordu. Eksik alan sessizdir, yanlış alan değildir.
        if sonuc.aile == "dilekce":
            _vatandas_tarihi(satirlar, sonuc, indeks)
        _imza(satirlar, sonuc, indeks)
    else:
        sonuc.uyarilar.append("Muhatap satırı bulunamadı")

    # Gönderen EN SONDA: H-A sayıya, H-C imzaya dayanıyor ve ikisi de
    # yukarıda dolduruluyor. Sıra değiştirilirse hatlar sessizce çalışmaz.
    #
    # MUHATAP SATIRI BULUNAMASA DA KOŞUYOR. Ölçüldü 2026-08-24: belge_173 ve
    # belge_181'de (ikisi de taranmış) muhatap satırı yakalanamadı, ama
    # SAYI SAĞLAMDI ve DETSİS okunabiliyordu. Bu çağrı `if indeks is not
    # None` bloğunun içindeyken iki belge sırf muhatap yüzünden gönderensiz
    # kalıyordu. Gönderen çıkarımının muhatapla bir işi yok; bağımlılık
    # tesadüfiydi.
    _gonderen(satirlar, sonuc, indeks)

    return sonuc
