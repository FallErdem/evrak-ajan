"""Yazar — AJAN 2. Şartname 6.4.2: taslak, üslup, eksik bilgi talebi.

BU DOSYA YAZAR'IN DETERMİNİSTİK KATMANI (2a). LLM YOK.
=======================================================
Taslağın dört alanı modele hiç sorulmaz, tablodan hesaplanır:

    muhatap         gelen evrağın göndereni
    baslik          kendi kurumumuzun antet bloğu
    imza_unvan      birimler.csv'deki imza_unvani
    hiyerarsi_yonu  arz mı rica mı

Gerekçe: dördü de KAYIT verisidir. Modele sorulursa uydurma riski girer ve
karşılığında hiçbir şey kazanılmaz — model bu bilgiyi bilemez, ancak tahmin
eder. Modelin karar verdiği şey yazının TÜRÜ, KONUSU ve METNİ (2b) ile
kendi çıktısını beğenip beğenmediği (2c).

ARZ/RİCA YÖNÜ GELEN BELGENİNKİNİN AYNASI DEĞİL
==============================================
En sinsi hata burada. `veri/kota.json > kapanis_kurali` GELEN belgenin
kapanışını verir. Taslak ters yöne gider ve beş durumun DÖRDÜ yön değiştirir:

    gönderen tipi   gelen belge      bizim taslak
    ------------    -----------      ------------
    vatandaş        arz              Bilgilerinize sunulur   (ME-05)
    özel tüzel      arz              rica                    (ME-06)
    üst makam       rica             arz                     (K 13.1)
    aynı düzey      arz              arz                     tek simetrik
    alt makam       arz              rica                    (K 13.1)

ÖLÇÜLDÜ (300 etiket): kota.json tablosunu doğrudan taslağa uygulayan bir
kod 144 belgede yanlış kapanış yazardı ve bunların 108'i vatandaş
dilekçesidir — yani en görünür, jürinin en kolay bakacağı grup.

Kapanış dağılımı da bunu gösteriyor:

    gelen belge     arz 228 · rica  63 · karma 9
    bizim taslak    arz 156 · rica  36 · sunulur 108

YÖNÜ NEREDEN ÇIKARIYORUZ — dört hat
===================================
    H1  gönderen aynı kurumun birimi  -> hiyerarsi_seviyesi farkı
    H2  gönderen başka kamu idaresi   -> yazisma_bicimi tablosu
    H3  gönderen özel tüzel kişi      -> KURUM_DISI  (ME-06)
    H4  gönderen gerçek kişi          -> GERCEK_KISI (ME-05)

H1'de TABLOYA BAKILMAZ ve bu kritik. `yazisma_bicimi`'nde `rica` verilen
satırların tamamı kurum içi KOLEKTİF ifadedir ("Gazi Üniversitesi fakülte,
enstitü, yüksekokul ve daire başkanlıkları") ve kurumun kendi ağzından
yazılmıştır. Seviye 2'deki bir birim onu kendi üzerine uygularsa kardeş
birime "rica" yazar — K 13.1 ihlali. Somut vaka belge_031: Personel Dairesi
Başkanlığı, Mühendislik Fakültesi Dekanlığı'na yazıyor; ikisi de seviye 2,
doğru kapanış arz. `birimler.dogrula()` bu tuzağı yükleme anında denetliyor.

BİLİNMİYOR İLE AYNI AYNI ŞEY DEĞİLDİR
=====================================
İkisi de "arz" üretir (K 13.1 kestirmesi) ama ayrı tutulur ve BILINMIYOR
insan onayına düşer. `HiyerarsiYonu` docstring'i bunu açıkça istiyor:
"eşit olduğunu biliyoruz" ile "bilemedik" aynı şey değildir.

Sözleşme karşılığı: docs/api_sozlesmesi.md · Ş 6.4.2
"""

from __future__ import annotations

from dataclasses import dataclass, field

from veri_yapisi import HiyerarsiYonu, MuhatapTuru

# -----------------------------------------------------------------------------
# Eşikler
# -----------------------------------------------------------------------------

# "Biz kimiz" sorusunda muhatap satırı birim kaydına bağlanırken, altında
# İNSAN ONAYI istenecek eşleşme oranı.
#
# DİKKAT — BU BİR BASTIRMA EŞİĞİ DEĞİL, TIRMANDIRMA EŞİĞİ
# --------------------------------------------------------
# Eşiğin altında kalan birim YİNE KULLANILIYOR; yalnızca `belirsiz=True`
# işaretleniyor ve taslak insan onayına düşüyor. Değeri bastırmak
# ÖLÇÜLDÜ ve KÖTÜ ÇIKTI (300 belge, 2026-08-24):
#
#     bant           doğru   YANLIŞ
#     1.00             250        1
#     0.90-0.99          2        0
#     0.75-0.84         17        3     <- karışık bant
#     <0.75 / yok        0       27
#
# 0,75-0,84 bandında 17 doğru ile 3 yanlış İÇ İÇE. Orada değeri bastırmak
# 3 hata önlemek için 17 doğru kimliği çöpe atardı. Yani ORAN TEK BAŞINA
# BU İKİ POPÜLASYONU AYIRMIYOR ve ayırmadığı için eşik bir karar aracı
# değil, bir uyarı aracıdır.
#
# İki popülasyon şunlar:
#     meşru ad varyantı   'GAZİ ÜNİVERSİTESİNE' -> Gazi Ünv. Rektörlüğü  0.77 ✓
#                         (kota.json baslik_varyanti: %40 bu biçimde)
#     OCR hasarı          'ANKARA İL MİLL{ ...' -> İlçe MEM              0.77 ✗
#
# İkisi aynı oranda. Ayırmak için oran değil, başka bir kanıt gerekir;
# şimdilik ikisi de insana gösteriliyor.
KIMLIK_ESIGI = 0.85


# -----------------------------------------------------------------------------
# Kimlik — taslağı kim yazıyor
# -----------------------------------------------------------------------------


@dataclass
class Kimlik:
    """Taslağı yazan birim ve o birimden türeyen alanlar."""

    birim: dict | None = None
    baslik: str | None = None
    imza_unvan: str | None = None
    oran: float = 0.0
    kaynak: str = "yok"          # yonlendirme | muhatap | yok
    belirsiz: bool = True
    sebep: str | None = None

    @property
    def kod(self) -> str | None:
        return self.birim["kod"] if self.birim else None


def kim_yaziyor(dosya) -> Kimlik:
    """Cevabı hangi birim yazıyor.

    İKİ KAYNAK, SIRAYLA
    -------------------
        1  yonlendirme.hedef_birim   Yönlendirici çalıştıysa kesin cevap
        2  ustveri.muhatap           gelen evrak kime yazılmışsa o birim

    İkincisi Yönlendirici hazır olmadan da Yazar'ın koşmasını sağlıyor.
    Üç örnek belgede etiketle birebir tuttu:

        belge_048  YENİMAHALLE BEL. BŞK. (Kültür, Sanat ve Sosyal İşler Müd.)
                   -> kultur_sanat_sosyal   imza_unvani "Müdür"
        belge_031  PERSONEL DAİRESİ BAŞKANLIĞINA
                   -> personel_db           imza_unvani "Daire Başkanı"
        belge_025  ANKARA İL MEM (Özel Öğretim Kurumları Şube Müd.)
                   -> ozel_ogretim_sb       imza_unvani "Şube Müdürü"

    Aynı arama `anlama.sdp_adaylari()` içinde 288/288 ölçülmüştü; ikinci bir
    uygulama yazılmadı.

    BELİRSİZLİK GİZLENMİYOR
    -----------------------
    Eşleşme `KIMLIK_ESIGI` altındaysa birim yine döndürülür ama
    `belirsiz=True` işaretlenir. Çağıran taraf (2c) bunu görünce taslağı
    insana tırmandırır. Yanlış birim adına imza atılmış bir yazı üretmektense
    eksik bir taslak üretmek yeğdir: eksik görünür, yanlış görünmez.
    """
    from birimler import birim_bul, hedef_olabilecekler, kurum_profili
    from metin import en_iyi_eslesme

    k = Kimlik()

    hedef = getattr(dosya.yonlendirme, "hedef_birim", None)
    if hedef:
        birim = birim_bul(hedef)
        if birim is not None:
            k.birim, k.oran, k.kaynak, k.belirsiz = birim, 1.0, "yonlendirme", False
            _kimligi_tamamla(k, kurum_profili)
            return k
        k.sebep = f"yonlendirme.hedef_birim '{hedef}' birim tablosunda yok"

    muhatap = getattr(dosya.ustveri, "muhatap", None)
    ham = getattr(muhatap, "ham", None) if muhatap else None
    birim_adi = getattr(muhatap, "birim", None) if muhatap else None
    arama = " ".join(x for x in (ham, birim_adi) if x).strip()
    if not arama:
        k.sebep = k.sebep or "Muhatap yazılmamış; taslağı kimin yazdığı bilinmiyor"
        return k

    adaylar = [(b["kod"], b["ad"], b["seviye"]) for b in hedef_olabilecekler()]
    kod, oran, _ad = en_iyi_eslesme(arama, adaylar)
    if kod is None:
        k.sebep = "Muhatap hiçbir birime bağlanamadı"
        return k

    k.birim = birim_bul(kod)
    k.oran = oran
    k.kaynak = "muhatap"
    k.belirsiz = oran < KIMLIK_ESIGI
    if k.belirsiz:
        k.sebep = (f"Muhatap satırı '{arama[:60]}' birime yalnızca {oran:.2f} "
                   f"oranla bağlandı; kimlik doğrulanmalı")
    _kimligi_tamamla(k, kurum_profili)
    return k


def _kimligi_tamamla(k: Kimlik, kurum_profili) -> None:
    """Birim kaydından başlık bloğunu ve imza unvanını türetir.

    Başlık `kurum*.json > baslik_bloku`'ndan geliyor ve `{birim_adi}` yer
    tutucusu birimin adıyla doldurulyor. Taşra kurumunda blok mülki idare
    satırını da taşır (B-08) ve o satır şablonda sabit yazılı:

        T.C. / ANKARA VALİLİĞİ / İl Millî Eğitim Müdürlüğü

    Seviye 0 birimde yer tutucu düşürülüyor: kurum adı zaten ikinci satırda.
    """
    if k.birim is None:
        return
    k.imza_unvan = k.birim.get("imza_unvani")

    profil = kurum_profili(k.birim["kurum_kodu"])
    if not profil:
        return
    blok = profil.get("baslik_bloku") or []
    satirlar: list[str] = []
    for ham in blok:
        s = str(ham)
        if "{birim_adi}" in s:
            if k.birim["seviye"] == 0:
                continue
            s = s.replace("{birim_adi}", k.birim["ad"])
        if "{" in s:                      # doldurulamayan yer tutucu
            continue
        satirlar.append(s)
    k.baslik = "\n".join(satirlar) or None


# -----------------------------------------------------------------------------
# Yön — arz mı rica mı
# -----------------------------------------------------------------------------


@dataclass
class YonKarari:
    yon: HiyerarsiYonu = HiyerarsiYonu.BILINMIYOR
    kapanis: str = ""
    hat: str = "yok"
    aciklama: str | None = None
    belirsiz: bool = True


# Kapanış ifadeleri — HiyerarsiYonu değerinin karşılığı.
#
# Kaynak: K 13.1 ve `HiyerarsiYonu` docstring'i. Metin BURADA sabit değil,
# istem modele bunu VERİYOR; model kapanışı seçmiyor, uyguluyor. ME-02 ve
# ME-03 sonra bunu denetliyor — üretim ile denetim ayrı kalıyor.
KAPANIS = {
    HiyerarsiYonu.UST: "Arz ederim.",
    HiyerarsiYonu.AYNI: "Arz ederim.",
    HiyerarsiYonu.ALT: "Rica ederim.",
    HiyerarsiYonu.KARMA: "Arz ve rica ederim.",
    HiyerarsiYonu.KURUM_DISI: "Rica ederim.",
    HiyerarsiYonu.GERCEK_KISI: "Bilgilerinize sunulur.",
    HiyerarsiYonu.BILINMIYOR: "Arz ederim.",
}


def yonu_belirle(dosya, biz: Kimlik) -> YonKarari:
    """Taslağın muhatabı (= gelen evrağın göndereni) bize göre nerede.

    DİKKAT — ÇERÇEVE FARKI
    ----------------------
    `HiyerarsiYonu` "muhatabın gönderene göre konumu"nu tutuyor. Gelen
    belgede muhatap BİZDİK; taslakta muhatap ONLAR. Yani etiketlerdeki
    `hiyerarsi_yonu` değerinin TERSİ hesaplanıyor. Ölçüm betiği de doğru
    cevabı ters çevirerek üretiyor.
    """
    from birimler import detsis_ile_birim_bul, dis_makam_bul, yazisma_bicimi

    g = getattr(dosya.ustveri, "gonderen", None)
    k = YonKarari()
    if g is None:
        k.aciklama = "Gönderen alanı yok"
        return _tamamla(k)

    # --- H4 · gerçek kişi (ME-05) -----------------------------------------
    if g.tur == MuhatapTuru.GERCEK_KISI:
        k.yon, k.hat, k.belirsiz = HiyerarsiYonu.GERCEK_KISI, "H4 gercek kisi", False
        k.aciklama = "Dilekçe sahibi gerçek kişi; ME-05 kapanışı"
        return _tamamla(k)

    # --- H3 · kamu dışı tüzel kişi (ME-06) --------------------------------
    if g.tur == MuhatapTuru.OZEL_HUKUK_TUZEL_KISI:
        k.yon, k.hat, k.belirsiz = HiyerarsiYonu.KURUM_DISI, "H3 ozel tuzel", False
        k.aciklama = "Kamu dışı tüzel kişi; ME-06 gereği rica"
        return _tamamla(k)

    gonderen_birim = detsis_ile_birim_bul(g.detsis_no)

    # --- H1 · aynı kurumun birimi -> SEVİYE, tabloya bakılmaz -------------
    if (gonderen_birim is not None and biz.birim is not None
            and gonderen_birim["kurum_kodu"] == biz.birim["kurum_kodu"]):
        bizim, onun = biz.birim["seviye"], gonderen_birim["seviye"]
        # Düşük seviye = yüksek makam.
        if onun == bizim:
            k.yon = HiyerarsiYonu.AYNI
        elif onun < bizim:
            k.yon = HiyerarsiYonu.UST
        else:
            k.yon = HiyerarsiYonu.ALT
        k.hat, k.belirsiz = "H1 kurum ici seviye", False
        k.aciklama = (f"Aynı kurum: biz seviye {bizim}, muhatap seviye {onun}. "
                      f"yazisma_bicimi tablosuna BAKILMADI (K 13.1)")
        return _tamamla(k)

    # --- H2 · başka kamu idaresi -> yazisma_bicimi ------------------------
    #
    # Tablo ALICI KURUMUN AĞZINDAN yazılı: kurum.json'daki
    # "Çankaya Belediye Başkanlığı": "arz" satırı "Yenimahalle, Çankaya'ya
    # arz eder" demektir. Dönen değer doğrudan bizim kapanışımızdır,
    # ters çevrilmez.
    ad = None
    if gonderen_birim is not None:
        ad = gonderen_birim["kurum"]        # fakülte/müdürlük -> kök kurum adı
    elif g.detsis_no:
        ad = dis_makam_bul(g.detsis_no)
    if ad is None:
        ad = g.idare

    bizim_kurum = biz.birim["kurum_kodu"] if biz.birim else None
    bicim = yazisma_bicimi(bizim_kurum, ad)
    if bicim == "rica":
        k.yon, k.hat, k.belirsiz = HiyerarsiYonu.ALT, "H2 yazisma_bicimi", False
        k.aciklama = f"'{ad}' kurum kaydında alt makam"
        return _tamamla(k)
    if bicim == "arz":
        # Tablo "arz" diyor ama ÜST mü AYNI mı ayırmıyor. Kapanış aynı
        # olduğu için taslak etkilenmiyor; ayrımı uydurmuyoruz.
        k.yon, k.hat, k.belirsiz = HiyerarsiYonu.AYNI, "H2 yazisma_bicimi", False
        k.aciklama = (f"'{ad}' kurum kaydında üst ya da aynı düzey; "
                      f"tablo ikisini ayırmıyor, kapanış her iki hâlde arz")
        return _tamamla(k)

    k.aciklama = (f"'{ad}' kurum kaydında yok; K 13.1 kestirmesiyle arz "
                  f"ediliyor ama yön DOĞRULANMADI")
    return _tamamla(k)


def _tamamla(k: YonKarari) -> YonKarari:
    k.kapanis = KAPANIS[k.yon]
    return k


# -----------------------------------------------------------------------------
# Taslak iskeleti
# -----------------------------------------------------------------------------


@dataclass
class Iskelet:
    """Modele SORULMAYAN alanlar. 2b bunun üstüne tür, konu ve metin koyar."""

    kimlik: Kimlik = field(default_factory=Kimlik)
    yon: YonKarari = field(default_factory=YonKarari)
    muhatap: str | None = None
    insan_onayi_gerek: bool = False
    sebepler: list[str] = field(default_factory=list)


def iskelet_kur(dosya) -> Iskelet:
    """Taslağın deterministik alanlarını hesaplar ve `dosya.cikti_yazi`'ya yazar.

    `tur`, `konu`, `metin` ELLENMEZ — onlar 2b'nin işi. Bu fonksiyon iki kez
    çağrılırsa aynı sonucu üretir (yan etkisi yalnızca bu üç alanın dışında).
    """
    i = Iskelet()
    i.kimlik = kim_yaziyor(dosya)
    i.yon = yonu_belirle(dosya, i.kimlik)
    i.muhatap = _muhatap_yaz(dosya, i.kimlik)

    if i.kimlik.belirsiz:
        i.sebepler.append(i.kimlik.sebep or "Taslağı yazan birim belirsiz")
    if i.yon.belirsiz:
        i.sebepler.append(i.yon.aciklama or "Hiyerarşi yönü belirlenemedi")
    if not i.muhatap:
        i.sebepler.append("Taslağın muhatabı yazılamadı: gönderen bulunamamış")
    i.insan_onayi_gerek = bool(i.sebepler)

    c = dosya.cikti_yazi
    c.baslik = i.kimlik.baslik
    c.imza_unvan = i.kimlik.imza_unvan
    c.muhatap = i.muhatap
    c.hiyerarsi_yonu = i.yon.yon
    return i


def _muhatap_yaz(dosya, biz: Kimlik) -> str | None:
    """Taslağın muhatap satırı — gelen evrağın göndereni.

    BİÇİM VERİDEN ÖLÇÜLDÜ (300 etiket, 2026-08-24)
    ----------------------------------------------
    Muhatap satırı üç biçimde yazılıyor ve seçimi hiyerarşi belirliyor:

        gönderen ile alıcı aynı kurumda   yalnız birim adı     31/33  %94
        farklı kurum, muhatap alt birim   kurum + (birim)      216
        muhatap kurumun kendisi           yalnız kurum adı      25

    Gerçek belgelerde birebir görülüyor:

        belge_031  Gazi -> Gazi     'PERSONEL DAİRESİ BAŞKANLIĞINA'
        belge_048  Çankaya -> Yenimahalle
                   'YENİMAHALLE BELEDİYE BAŞKANLIĞINA'
                   '(Kültür, Sanat ve Sosyal İşler Müdürlüğü)'

    İlk sürümde kurum adı her zaman yazılıyordu ve belge_031'de
    "Gazi Üniversitesi Rektörlüğü / (Mühendislik Fakültesi Dekanlığı)"
    üretiyordu — kendi kurumunun adını kendine yazmak. Aynı idare içinde
    yazışmada kurum tekrar edilmez.

    EK YÖNELME DURUMU EKLENMİYOR
    ----------------------------
    "-NA" eki ünlü uyumuna ve son sese göre değişiyor: Başkanlığına,
    Rektörlüğüne, Müdürlüğüne. Yanlış ek resmî yazıda göze batar. Kanonik
    ad yazılıyor; eki metin üretiminde model kendi dil bilgisiyle koyacak.
    """
    from birimler import detsis_ile_birim_bul

    g = getattr(dosya.ustveri, "gonderen", None)
    if g is None:
        return None
    if g.tur == MuhatapTuru.GERCEK_KISI:
        return g.ad or None

    birim = detsis_ile_birim_bul(g.detsis_no)
    if birim is not None:
        if birim["seviye"] == 0:
            return birim["ad"]
        if biz.birim is not None and birim["kurum_kodu"] == biz.birim["kurum_kodu"]:
            return birim["ad"]
        return f"{birim['kurum']}\n({birim['ad']})"

    # Dış makam ya da şirket: birim kaydı yok, elimizdeki tek şey ad.
    parcalar = [x for x in (g.idare, g.birim) if x]
    if not parcalar:
        return g.ham or g.ad or None
    if len(parcalar) == 1:
        return parcalar[0]
    return f"{parcalar[0]}\n({parcalar[1]})"


# =============================================================================
# 2b · TÜR KARARI VE TASLAK ÜRETİMİ — LLM
# =============================================================================
#
# Modelin karar verdiği ÜÇ şey: yazının TÜRÜ, KONUSU, METNİ.
# Modelin karar VERMEDİĞİ şey: muhatap, başlık, imza unvanı, arz/rica.
# Onlar 2a'da tablodan hesaplandı ve isteme HAZIR CEVAP olarak giriyor.
#
# İSTEMDEKİ AD İLE ŞEMADAKİ AD AYNI OLMAK ZORUNDA
# -----------------------------------------------
# Anlama'da pahalıya öğrenildi: istem "dilekce" derken şema
# "vatandas_dilekcesi" bekliyordu ve üç sınıf birden kayboldu (F1 0.00).
# Burada o risk YOK, çünkü `UretilecekTur` değerleri zaten şema adları;
# taksonomi köprüsü giden tarafta gerekmiyor. Yine de tür açıklamaları
# ENUM DEĞERİYLE anahtarlanıyor, ayrı bir sözlükle değil.

import json  # noqa: E402
import re  # noqa: E402

from veri_yapisi import UretilecekTur  # noqa: E402

# Şemaya KONMAYACAK tür. Model seçemezse yanlış seçemez.
#
# Gerekçe (devir promptu §5.2): sistem "buna cevap gerekmez" der ve
# yanılırsa vatandaşın dilekçesi cevapsız kalır. Gereksiz taslak üretirse
# memur siler. Hata simetrik değil.
YASAK_TUR = UretilecekTur.TASLAK_GEREKMEZ

TUR_TANIMLARI = {
    UretilecekTur.CEVAP_YAZISI.value:
        "Gelen bir talebe, soruya ya da başvuruya doğrudan cevap verir. "
        "Gelen evrak bir şey İSTİYORSA ve cevaplayabiliyorsak bu seçilir.",
    UretilecekTur.BILGILENDIRME_YAZISI.value:
        "Cevap beklemeyen, karşı tarafı bilgilendiren yazı. Gelen evrak "
        "bilgi vermişse ya da yapılan bir işlem bildiriliyorsa.",
    UretilecekTur.UST_YAZI.value:
        "Bir eki, belgeyi ya da dosyayı iletmek için yazılan kapak yazısı. "
        "Asıl içerik EKTEDİR, yazının kendisi kısadır.",
    UretilecekTur.OLUR_YAZISI.value:
        "Bir işlem için yetkili makamdan onay (olur) alınmasını sağlayan "
        "yazı. Karar verecek makama sunulur.",
    UretilecekTur.TEKIT_YAZISI.value:
        "Daha önce yazılmış ve cevaplanmamış bir yazıyı hatırlatır. "
        "Yalnızca cevapsız kalmış bir ilgi varsa.",
    UretilecekTur.EKSIK_BILGI_TALEBI.value:
        "Gelen evrakta işlem için gereken bilgi ya da belge eksikse, "
        "eksiği tamamlaması istenir. Şartname 6.4.2 son madde.",
}

SISTEM_ISTEMI_YAZAR = (
    "Türk kamu kurumlarında resmî yazı kaleme alan bir uzmansın. "
    "Resmî Yazışmalarda Uygulanacak Usul ve Esaslar Hakkında Yönetmelik'e "
    "uygun, sade ve açık Türkçe yazarsın. "
    "Sana verilmeyen hiçbir bilgiyi UYDURMAZSIN: sayı, tarih, kişi adı, "
    "mevzuat maddesi ya da rakam ekleme. "
    "Yalnızca gelen belgede yazan ve sana verilen bilgiyi kullan."
)


def sema_kur() -> dict:
    """response_format şeması. `taslak_gerekmez` ENUM'A KONMAZ.

    Sayısal kısıt yok — Anlama'da ölçüldü, çağrıyı yavaşlatıyor ve aralık
    dışı değer üretiyor. Uzunluk sınırları VAR: model uzun yazınca Pydantic
    doğrulaması patlıyor ve cevabın tamamı çöpe gidiyordu.
    """
    turler = [t.value for t in UretilecekTur if t is not YASAK_TUR]
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "resmi_yazi_taslagi",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "tur": {"type": "string", "enum": turler},
                    "tur_gerekcesi": {
                        "type": "string", "maxLength": 300,
                        "description": "Bu türü neden seçtin, TEK CÜMLE.",
                    },
                    "konu": {
                        "type": "string", "maxLength": 120,
                        "description": "Yazının konusu. Sonuna NOKTA, "
                                       "'Hk.' ya da başka noktalama KOYMA.",
                    },
                    "metin": {
                        "type": "string", "maxLength": 2000,
                        "description": "Yazının gövdesi. Paragraflar arasında "
                                       "boş satır bırak. Başlık, sayı, tarih, "
                                       "muhatap ve imza YAZMA — onlar ayrıca "
                                       "ekleniyor. Kapanış cümlesini sana "
                                       "verilen hâliyle en sona yaz.",
                    },
                    "eksik_bilgiler": {
                        "type": "array",
                        "description": "Taslağın tamamlanabilmesi için "
                                       "GEREKEN ama sana verilmeyen bilgiler. "
                                       "Metinde [doldurulacak: ...] olarak "
                                       "bıraktığın her şey buraya da yazılır. "
                                       "Yoksa boş dizi.",
                        "items": {"type": "string", "maxLength": 200},
                    },
                },
                "required": ["tur", "tur_gerekcesi", "konu", "metin",
                             "eksik_bilgiler"],
                "additionalProperties": False,
            },
        },
    }


def istem_kur(dosya, isk: Iskelet, bulgular: list | None = None) -> str:
    """İstemi kurar. Deterministik alanlar HAZIR CEVAP olarak verilir.

    `bulgular` doluysa bu bir DÜZELTME turudur (2c). Model kendi önceki
    taslağını ve kural motorunun bulgularını görür, yeniden yazar.
    """
    u = dosya.ustveri
    s = dosya.siniflandirma
    ic = dosya.icerik

    ilgi = "yok"
    if u.ilgi:
        i0 = u.ilgi[0]
        ilgi = f"{i0.tarih or '—'} tarihli ve {i0.sayi or '—'} sayılı yazı"

    satirlar = [
        "GELEN EVRAK",
        "-" * 60,
        f"Gönderen        : {isk.muhatap or '—'}",
        f"Belge türü      : {s.belge_turu.value if s.belge_turu else '—'}",
        f"Konu            : {u.konu or '—'}",
        f"İlgi            : {ilgi}",
        f"Ek              : {len(u.ekler)} adet" if u.ekler else "Ek              : yok",
        f"Talep           : {ic.talep or '—'}",
        f"Özet            : {ic.ozet or '—'}",
        "",
        "Gövde:",
        (dosya.metin or "")[:3000],
        "",
        "CEVABI YAZAN",
        "-" * 60,
        f"Birim           : {isk.kimlik.birim['ad'] if isk.kimlik.birim else '—'}",
        f"İmza unvanı     : {isk.kimlik.imza_unvan or '—'}",
        "",
        "SANA VERİLEN KARARLAR — bunları DEĞİŞTİRME",
        "-" * 60,
        f"Muhatap         : {(isk.muhatap or '—').replace(chr(10), ' ')}",
        f"Hiyerarşi       : {isk.yon.aciklama or '—'}",
        f"KAPANIŞ CÜMLESİ : {isk.yon.kapanis}",
    ]

    # Mevzuat atıfları Denetçi'den geliyor ve DOĞRULANMIŞ. Yazar TAŞIR,
    # üretmez — uydurma madde numarası resmî yazıdaki hata türlerinin en
    # kötüsüdür, çünkü okuyan memur ona güvenip işlem yapar.
    if dosya.mevzuat:
        satirlar += ["", "KULLANABİLECEĞİN MEVZUAT ATIFLARI", "-" * 60]
        for m in dosya.mevzuat:
            parca = getattr(m, "madde", None)
            satirlar.append(f"  {getattr(m, 'ad', '—')}"
                            + (f" {parca}" if parca else ""))
        satirlar.append("  Bu listenin DIŞINDA mevzuat atfı yapma.")
    else:
        satirlar += ["", "Sana mevzuat atfı verilmedi; yazıda mevzuat "
                     "maddesi ANMA."]

    satirlar += [
        "",
        "KURALLAR",
        "-" * 60,
        "1  KONU: yalın bir isim tamlaması yaz. Sonuna nokta, iki nokta ya "
        "da başka noktalama KOYMA. 'Hk.', 'Hk', 'Hakkında' ile de BİTİRME — "
        "kısaltmanın noktasını silmek yetmez, kısaltmanın kendisi konu "
        "alanına yazılmaz. "
        "Doğru: 'Staj Süresinin Uzatılması Talebi' · 'Atama Onayı' · "
        "'Halk Eğitim Kursu Açılması'. "
        "Yanlış: 'Atama Onayı Hk.' · 'Atama Onayı Hk' · 'Atama Onayı.'",
        "2  Kapanış cümlesini sana verildiği gibi, metnin EN SONUNA yaz.",
        f"3  Sayı, tarih ve imzalayan kişinin adını YAZMA — EBYS atar.",
        "4  Gelen evrakta bir ilgi varsa metnin ilk paragrafında ona AÇIKÇA "
        "atıf yap ('İlgide kayıtlı yazı ile...').",
        "5  Verilmeyen hiçbir bilgiyi uydurma. Emin olmadığın rakam, ad ya "
        "da madde numarası yazma.",
        "6  SONUÇ DA UYDURMA. Gelen evrak SOMUT bir veri istiyorsa (sayı, "
        "liste, süre, tutar) ve o veri sana verilmediyse, uydurma ve "
        "olumsuz cevap da verme; yerine [doldurulacak: ...] yaz, memur "
        "doldurur. 'Bilgiye ulaşılamamıştır', 'talebiniz uygun "
        "görülmemiştir' gibi cümleler BİRER KARARDIR, onları vermeye "
        "yetkin yok. "
        "AMA yer tutucuyu GEREKSİZ YERE KULLANMA: gelen evrak somut veri "
        "istemiyorsa yazı yer tutucusuz tamamlanır.",
        "7  GELEN EVRAĞIN CÜMLELERİNİ KOPYALAMA. Sen CEVAP yazıyorsun: "
        "karşı taraf senden bir şey istedi, sen ne yaptığını ya da ne "
        "yapacağını bildiriyorsun. Aynı cümleyi 'Müdürlüğünüzce' yerine "
        "'Müdürlüğümüzce' yazarak geri göndermek cevap DEĞİLDİR; talebi "
        "tekrar etmiş olursun. Gelen evrağı kendi cümlelerinle özetle, "
        "sonra senin tarafında ne olduğunu yaz.",
        "8  Kısa ve resmî yaz; iki ile dört paragraf yeterlidir.",
    ]

    if bulgular:
        satirlar += [
            "",
            "=" * 60,
            "ÖNCEKİ TASLAĞIN KURAL İHLALİ İÇERİYOR — DÜZELT",
            "=" * 60,
            f"Önceki konu : {dosya.cikti_yazi.konu or '—'}",
            "Önceki metin:",
            dosya.cikti_yazi.metin or "—",
            "",
            "Denetim bulguları:",
        ]
        # LinterBulgusu alanları: kural_id · baslik · onem · aciklama ·
        # dayanak · alan · alinti · duzeltme_onerisi.
        #
        # DÜZELTME ÖNERİSİ VE ALINTI DA VERİLİYOR — ölçüldü 2026-08-24:
        # yalnızca kural kimliği verildiğinde istemde "[?]" görünüyordu ve
        # model neyi düzelteceğini bilemiyordu. Kuralın DAYANAĞI da konuyor
        # ki model kuralı ezberlemek yerine gerekçesini görsün.
        for b in bulgular:
            satir = f"  [{getattr(b, 'kural_id', '?')}] " \
                    f"{getattr(b, 'baslik', '') or ''}"
            aciklama = getattr(b, "aciklama", None)
            if aciklama:
                satir += f" — {aciklama}"
            dayanak = getattr(b, "dayanak", None)
            if dayanak:
                satir += f"  (dayanak: {dayanak})"
            satirlar.append(satir)
            alinti = getattr(b, "alinti", None)
            if alinti:
                satirlar.append(f"        sorunlu kısım: {alinti}")
            oneri = getattr(b, "duzeltme_onerisi", None)
            if oneri:
                satirlar.append(f"        öneri: {oneri}")
        satirlar.append("")
        satirlar.append("Bu ihlalleri gideren YENİ bir taslak yaz. "
                        "İhlalle ilgisi olmayan kısımları KORU.")

    return "\n".join(satirlar)


def taslak_uret(dosya, istemci, isk: Iskelet | None = None,
                bulgular: list | None = None) -> list[str]:
    """Tek LLM çağrısı. `dosya.cikti_yazi`'nın tur/konu/metin alanlarını yazar.

    Döner: uyarı listesi (boşsa çağrı temiz geçti).

    Çağrı başarısız olursa alanlar ELLENMEZ. Yarım JSON ayrıştırılmaz:
    Anlama'da ölçüldü, kesilmiş çıktıyı kabul etmek eksik veriyi sessizce
    şemaya sokuyor.
    """
    uyarilar: list[str] = []
    if isk is None:
        isk = iskelet_kur(dosya)

    try:
        cevap = istemci.metin_uret(
            istem=istem_kur(dosya, isk, bulgular),
            sistem_istemi=SISTEM_ISTEMI_YAZAR,
            ek={"response_format": sema_kur()},
        )
    except Exception as e:  # noqa: BLE001
        return [f"LLM çağrısı başarısız: {type(e).__name__}: {e}"]

    if cevap.kesildi_mi:
        return ["Model çıktısı token sınırında kesildi; taslak yazılmadı"]

    try:
        veri = json.loads(cevap.metin)
    except json.JSONDecodeError as e:
        return [f"Model çıktısı JSON değil: {e}"]

    c = dosya.cikti_yazi
    ham_tur = (veri.get("tur") or "").strip()
    try:
        tur = UretilecekTur(ham_tur)
    except ValueError:
        uyarilar.append(f"Model tanınmayan tür verdi: {ham_tur!r}")
        tur = None
    if tur is YASAK_TUR:
        # Şemada yok; buraya düşerse sağlayıcı enum'u uygulamamış demektir.
        uyarilar.append("Model 'taslak_gerekmez' verdi; şemada olmamalıydı")
        tur = None
    if tur is not None:
        c.tur = tur

    c.tur_gerekcesi = _kirp(veri.get("tur_gerekcesi"), 300)
    c.konu = _kirp(veri.get("konu"), 120)
    c.metin = _kirp(veri.get("metin"), 2000)

    eksikler = [s for s in (veri.get("eksik_bilgiler") or []) if str(s).strip()]
    if eksikler:
        # Şartname 6.4.2 son madde: "gerekli durumlarda eksik bilgi talep
        # edebilmesi". Talep nesnesini KURMUYORUZ — muhatap kanalı, süre ve
        # dayanak burada bilinmiyor. Sorular kaydediliyor, gerisi akış
        # katmanının işi.
        dosya.eksik_bilgi_talebi = dosya.eksik_bilgi_talebi or None
        uyarilar.extend(f"Eksik bilgi: {s}" for s in eksikler[:5])

    return uyarilar


def _kirp(deger: object, sinir: int) -> str | None:
    """Şemanın uzunluk sınırına kırpar — ikinci savunma hattı.

    Anlama'da ölçüldü: model sınırı aşınca Pydantic ValidationError
    fırlatıyor ve çağrının TAMAMI çöpe gidiyor. Sağlayıcı maxLength'i
    uygulamayabilir.
    """
    if deger is None:
        return None
    metin = str(deger).strip()
    if not metin:
        return None
    return metin if len(metin) <= sinir else metin[: sinir - 1].rstrip() + "…"


# =============================================================================
# 2c · ÜSLUP DÖNGÜSÜ — YAZAR'I AJAN YAPAN YER
# =============================================================================
#
# LLM ÇAĞIRMAK AJAN OLMAK DEĞİLDİR
# --------------------------------
#     ARAÇ          LLM yok, karar yok
#     LLM ÇAĞRISI   LLM var, karar yok, döngü yok
#     AJAN          LLM var, KARAR verir, KENDİ ÇIKTISINI denetler, DÖNGÜYE girer
#
# Fark davranışta görünür:
#     workflow   yaz -> denetle -> çıktıyı ver        (ihlal varsa da verir)
#     ajan       yaz -> denetle -> GÖR -> DÜZELT -> tekrar denetle
#                                        -> olmazsa PES ET, insana ver
#
# Yazar kendi ürettiğini beğenmeyip değiştiriyor ve ne zaman pes edeceğine
# kendi karar veriyor. Bir workflow bunu yapmaz.
#
# GERÇEK ÖRNEK — ölçüldü 2026-08-24, qwen3.8-27b, üç belgenin ÜÇÜNDE de:
#
#     Tur 1  konu: "Staj Süresinin Uzatılması Talebi Hk."
#            motor: K-02 İHLAL — konu sonunda noktalama (Y 13)
#     Tur 2  konu: "Staj Süresinin Uzatılması Talebi"
#            motor: temiz -> insana sunulur
#
# İstemde "sonuna noktalama KOYMA" AÇIKÇA yazılı olmasına rağmen model üç
# belgede de "Hk." yazdı. Yani döngü süs değil: tek atışlık bir Yazar bu
# üç belgede de Yönetmeliğe aykırı konu üretirdi.
#
# DÖNGÜ SINIRI 2 TUR
# ------------------
# Sınırsız döngü hem kredi yakar hem sonsuza gidebilir. İki tur sonunda
# ihlal kalırsa Yazar PES EDER ve evrağı insana tırmandırır. Pes etmek
# başarısızlık değil, tasarımın parçası: memura "şunu düzeltemedim"
# demek, sessizce hatalı taslak vermekten iyidir.

from veri_yapisi import EvrakDurumu  # noqa: E402

AZAMI_TUR = 2

# -----------------------------------------------------------------------------
# Yazar'ın kendi iç denetimi — kural motorundan AYRI
# -----------------------------------------------------------------------------
#
# İŞ BÖLÜMÜ
#     kural motoru   taslak YÖNETMELİĞE uygun mu     (K-02, ME-01, ME-02...)
#     iç denetim     taslak KENDİNE VERİLENE uygun mu
#
# İkincisini kural motoruna eklemek yanlış olurdu: denetlenen şey mevzuat
# değil, Yazar'ın kendi girdisiyle tutarlılığı. Ayrıca `kural_ekleri.json`
# ve `kural_ozel.py` bu çalışmada başka bir geliştiricinin dosyası.
#
# NEDEN GEREKLİ — ÖLÇÜLDÜ 2026-08-24, üç ayrı istem ayarından sonra
# ------------------------------------------------------------------
# Model her kapatılan kapıda yenisini buluyor:
#
#   ayar 1  konu "Staj ... Talebi Hk."          -> K-02 yakaladı
#   ayar 2  konu "Staj ... Talebi Hk"            -> noktayı sildi, kural sustu
#   ayar 3  konu temiz, ama metin:
#           "...bilgileri EKTE yer almaktadır."  -> OLMAYAN EK uydurdu
#
# Üçüncüsü en tehlikelisi: 4982 sayılı Kanun başvurusuna "bilgiler ektedir"
# demek, başvurucunun olmayan bir eki aramasına ve yasal sürenin boşa
# geçmesine yol açar. İstem ayarı bunu engelleyemedi çünkü sorun üslup
# değil, DOĞRULANABİLİR BİR OLGU İDDİASI.
#
# Deterministik denetim istem ayarından üstün: model ne kadar yaratıcı
# olursa olsun, "ek var" demek elimizdeki ek sayısıyla çelişir ve çelişki
# ölçülebilir.

# Taslakta ek iddiası. "ekle-", "ekip", "ekonomi" gibi kelimeleri
# yakalamamak için sınır konuyor.
_EK_IDDIASI = re.compile(
    r"\b(ek(?:te|ler|inde|imizde)?|ilişikte|ilişik)\b"
    r"(?=[^.]{0,80}?(yer al|sunul|gönderil|iletil|bulun|takdim|ilet))",
    re.IGNORECASE,
)


@dataclass
class IcBulgu:
    """Kural motorunun bulgusuyla aynı şekli taşır ki istem tek yol kullansın."""

    kural_id: str
    baslik: str
    aciklama: str | None = None
    dayanak: str | None = None
    alinti: str | None = None
    duzeltme_onerisi: str | None = None
    onem: str = "hata"


def ic_denetim(dosya) -> list[IcBulgu]:
    """Taslak, kendisine VERİLMEYEN bir şeyi iddia ediyor mu.

    Şu an tek denetim var; liste büyüyebilir ama her yenisi ölçümle
    gerekçelendirilmeli — istem ayarıyla çözülebilen şeyi buraya koymak
    kodu şişirir.
    """
    bulgular: list[IcBulgu] = []
    metin = dosya.cikti_yazi.metin or ""

    # Yazar EK ÜRETMİYOR: `cikti_yazi` şemasında ek alanı yok ve taslağa
    # dosya iliştirilmiyor. Dolayısıyla taslaktaki HER ek iddiası
    # dayanaksızdır — gelen evrakta ek olması da bunu değiştirmez, çünkü
    # gelen evrağın eki bizim yazımızın eki değildir.
    m = _EK_IDDIASI.search(metin)
    if m:
        bulgular.append(IcBulgu(
            kural_id="YZ-01",
            baslik="Taslak, var olmayan bir eke atıf yapıyor",
            aciklama="Bu yazının eki yok. Ek iddiası, okuyanın olmayan bir "
                     "belgeyi aramasına yol açar.",
            dayanak="Yazar iç denetimi",
            alinti=metin[max(0, m.start() - 40):m.end() + 40].strip(),
            duzeltme_onerisi="Ek atfını kaldır. Bilgi elinde yoksa "
                             "[doldurulacak: ...] yer tutucusu kullan.",
        ))
    return bulgular



# Bu önemdeki bulgular düzeltme turunu tetikler. Bilgi düzeyindekiler
# rapora yazılır ama yeniden yazdırmaz — her uyarı için kredi yakmayız.
DUZELTILECEK_ONEMLER = ("hata", "uyari")


@dataclass
class YazarSonucu:
    """Döngünün kaydı. `linter_raporu` boş kalırsa döngü koşmamış demektir."""

    tur_sayisi: int = 0
    ilk_bulgular: list = field(default_factory=list)
    son_bulgular: list = field(default_factory=list)
    duzeltildi: bool = False
    pes_edildi: bool = False
    insan_onayi_gerek: bool = False
    uyarilar: list[str] = field(default_factory=list)
    iskelet: Iskelet | None = None

    @property
    def ozet(self) -> str:
        if self.pes_edildi:
            return (f"{self.tur_sayisi} turda düzeltilemedi, "
                    f"{len(self.son_bulgular)} ihlal kaldı; insana tırmandırıldı")
        if self.duzeltildi:
            return (f"{len(self.ilk_bulgular)} ihlal {self.tur_sayisi}. turda "
                    f"düzeltildi")
        return f"İlk turda temiz ({self.tur_sayisi} tur)"


def _duzeltilecekler(rapor) -> list:
    return [b for b in (rapor.bulgular or [])
            if str(getattr(b, "onem", "")).lower() in DUZELTILECEK_ONEMLER]


def yaz(dosya, istemci, motor=None, azami_tur: int = AZAMI_TUR) -> YazarSonucu:
    """Yazar ajanının tam koşusu: iskelet -> taslak -> denetle -> düzelt.

    `motor` verilmezse KuralMotoru burada kurulur. Ölçüm betikleri motoru
    bir kez kurup tekrar tekrar veriyor — kural dosyası her belgede
    yeniden okunmasın diye.

    `dosya.cikti_yazi.linter_raporu` HER KOŞUDA doldurulur, temiz koşuda da.
    Boş bırakmak "denetlenmedi" ile "denetlendi, temiz çıktı" arasındaki
    farkı yok eder; ikincisi bir sonuçtur ve kaydedilmelidir.
    """
    s = YazarSonucu()
    s.iskelet = iskelet_kur(dosya)
    s.insan_onayi_gerek = s.iskelet.insan_onayi_gerek
    s.uyarilar.extend(s.iskelet.sebepler)

    if motor is None:
        from kural_motoru import KuralMotoru
        motor = KuralMotoru()

    bulgular: list = []
    for tur in range(1, azami_tur + 1):
        s.tur_sayisi = tur
        # 1. turda bulgular boş -> normal üretim; sonrasında düzeltme istemi.
        s.uyarilar.extend(taslak_uret(dosya, istemci, s.iskelet,
                                      bulgular or None))
        if dosya.cikti_yazi.metin is None:
            # Çağrı başarısız; denetlenecek bir şey yok, döngüyü sürdürmek
            # ikinci bir başarısız çağrıdan başka şey getirmez.
            s.pes_edildi = True
            s.insan_onayi_gerek = True
            break

        sonuc = motor.calistir(dosya, hedef="giden")
        # `linter_raporu` KURAL MOTORUNUN kaydıdır; iç denetim bulguları
        # oraya yazılmıyor. Arayüz ve Denetçi o raporu kurallar.json'daki
        # kimliklerle eşleştiriyor; YZ-01 orada yok ve uydurma kimlik
        # göstermek raporu güvenilmez kılar. İç bulgular döngüyü tetikler
        # ve YazarSonucu'na yazılır — görünür ama karışmaz.
        dosya.cikti_yazi.linter_raporu = sonuc.rapor
        bulgular = _duzeltilecekler(sonuc.rapor) + ic_denetim(dosya)
        if tur == 1:
            s.ilk_bulgular = list(bulgular)
        s.son_bulgular = list(bulgular)

        s.uyarilar.extend(f"[{b.kural_id}] {b.baslik}"
                          for b in bulgular if isinstance(b, IcBulgu))

        if not bulgular:
            s.duzeltildi = tur > 1
            break
    else:
        # Döngü sınırı doldu ve hâlâ ihlal var. PES ET.
        s.pes_edildi = True
        s.insan_onayi_gerek = True
        s.uyarilar.append(
            f"Taslak {azami_tur} turda Yönetmeliğe uygun hâle getirilemedi; "
            f"kalan ihlaller: "
            + ", ".join(getattr(b, "kural_id", "?") for b in s.son_bulgular)
        )

    # Uyarılar turlar boyunca birikiyor ve düzeltme turu aynı eksik bilgiyi
    # tekrar bildirdiği için yineleniyordu (ölçüldü, belge_025: 3 eksik bilgi
    # 6 satır olarak göründü). Sıra korunarak tekilleştiriliyor.
    gorulen: set[str] = set()
    s.uyarilar = [u for u in s.uyarilar
                  if not (u in gorulen or gorulen.add(u))]

    dosya.durum = (EvrakDurumu.INSAN_ONAYI_BEKLIYOR if s.insan_onayi_gerek
                   else EvrakDurumu.ISLENIYOR)
    return s
