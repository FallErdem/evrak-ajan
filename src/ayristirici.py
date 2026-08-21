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
_MUHATAP = re.compile(
    r"^([^a-zçğıöşü]{8,}(?:NE|NA|ne|na))\s*(?:\(([^)]*)\))?\s*$"
)

# Muhatabı belirsiz bırakılmış yazı. Gerçek yazışmada kullanılan bir kalıptır
# ve veri setinde muhatap_belirsiz kusurunun enjekte ettiği değerdir (10 belge,
# etiket kusur_ayrinti.enjekte_edilen = "İLGİLİ MAKAMA").
#
# Ayrı kalıp olarak tutuluyor çünkü iki şey aynı anda doğru olmalı:
# satır BULUNMUŞ sayılmalı ki aile/tarih/imza çağlayanı kopmasın, ama
# muhatap BELİRSİZ işaretlenmeli ki Denetçi bunu eksiklik olarak görsün.
_MUHATAP_BELIRSIZ = re.compile(r"^\s*[İIi]LG[İIi]L[İIi]\s+MAKAM(?:A|LARA)\s*$")
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
_AD_SATIR_SONU = re.compile(rf"({_AD})\s*$")

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
    uyarilar: list[str] = field(default_factory=list)

    @property
    def ozet(self) -> str:
        return f"{len(self.kanit)} alan bulundu"


def _kanit(alinti: str, satir_no: int, guven: float = 1.0,
           aciklama: str | None = None) -> Kanit:
    return Kanit(
        yontem=KanitYontemi.REGEX,
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


def _aile_tespit(satirlar: list[Satir], muhatap_indeksi: int | None) -> str:
    """Belge ailesini başlık bloğundan tespit eder.

    Üç ipucu sırayla denenir. Dilekçenin ayırt edici özelliği başlığın
    HİÇ olmaması: belge doğrudan muhatapla başlıyorsa dilekçedir.
    """
    if muhatap_indeksi is None:
        return "bilinmiyor"
    baslik = satirlar[:muhatap_indeksi]
    if not baslik:
        return "dilekce"
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
    return None


# -----------------------------------------------------------------------------
# Alan çıkarıcılar
# -----------------------------------------------------------------------------


def _sayi_ve_tarih(satirlar: list[Satir], sonuc: AyristirmaSonucu) -> None:
    """Sayı ve tarih aynı satırda durur (yerlesim.yaml alanlar.tarih_konumu).

        Sayı : E-24316060-010.06-66473254 04.05.2026
    """
    for i, s in enumerate(satirlar):
        if not _ETIKET_SAYI.match(s.metin):
            continue
        kalan = _ETIKET_SAYI.sub("", s.metin)

        m = _sayi_ara(kalan)
        if m:
            sonuc.ustveri.sayi = m.group(0)
            sonuc.kanit["ustveri.sayi"] = _kanit(m.group(0), i)
        else:
            # Etiket var, değer yok -> sayi_eksik kusuru. Uydurma yok.
            sonuc.uyarilar.append("Sayı satırı var ama resmî sayı bulunamadı")

        t = _TARIH.search(kalan)
        if t:
            d = _tarihe_cevir(*t.groups())
            if d:
                sonuc.ustveri.tarih = d
                sonuc.ustveri.tarih_metin = t.group(0)
                sonuc.kanit["ustveri.tarih"] = _kanit(t.group(0), i)
        return


def _konu(satirlar: list[Satir], sonuc: AyristirmaSonucu) -> None:
    for i, s in enumerate(satirlar):
        if not _ETIKET_KONU.match(s.metin):
            continue
        deger = _ETIKET_KONU.sub("", s.metin).strip()
        if deger:
            sonuc.ustveri.konu = deger
            sonuc.kanit["ustveri.konu"] = _kanit(deger, i)
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
    sonuc.kanit["ustveri.muhatap"] = _kanit(ham, indeks)

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
    """Dilekçede imza sahibinin adını satır SONUNDA arar.

    Güven 0.75: kurum yazısındakinden düşük, çünkü ad başka metne yapışık
    ve ayrım yalnızca büyük harf kalıbına dayanıyor.
    """
    for i in range(len(satirlar) - 1, sinir - 1, -1):
        m = _AD_SATIR_SONU.search(satirlar[i].metin)
        if not m:
            continue
        ad = m.group(1).strip()
        sonuc.ustveri.imza.ad = ad
        sonuc.ustveri.imza.ham = ad
        sonuc.kanit["ustveri.imza.ad"] = _kanit(
            ad, i, guven=0.75,
            aciklama="Dilekçede ad adres satırına yapışık; satır sonundan alındı",
        )
        return



# -----------------------------------------------------------------------------
# Ana giriş
# -----------------------------------------------------------------------------


def ayristir(satirlar: list[Satir]) -> AyristirmaSonucu:
    """Satırlardan üstveri alanlarını çeker.

    Bulunamayan alan None kalır ve kanıt üretilmez. Uydurma yok:
    bir alanın yokluğu, Denetçi'nin yakalayacağı bir bulgudur.
    """
    sonuc = AyristirmaSonucu()
    if not satirlar:
        sonuc.uyarilar.append("Satır yok")
        return sonuc

    indeks = _muhatap_satirini_bul(satirlar)
    sonuc.muhatap_satiri = indeks
    sonuc.aile = _aile_tespit(satirlar, indeks)
    sinir = indeks if indeks is not None else 0

    _sayi_ve_tarih(satirlar, sonuc)
    _konu(satirlar, sonuc)
    _ilgi(satirlar, sonuc, sinir if sinir else len(satirlar))
    _ekler(satirlar, sonuc)
    _dagitim(satirlar, sonuc)

    if indeks is not None:
        _muhatap(satirlar, sonuc, indeks)
        _vatandas_tarihi(satirlar, sonuc, indeks)
        _imza(satirlar, sonuc, indeks)
    else:
        sonuc.uyarilar.append("Muhatap satırı bulunamadı")

    return sonuc
