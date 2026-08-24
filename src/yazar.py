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
