"""Evrak kayıt defteri — sayı biçimi ve kayıt damgası.

BU MODÜL SAYAÇ TUTMAZ, VERİTABANI AÇMAZ.
========================================
Defterin kendisi (SQLite, sıra numarası, gelen/giden listeleri) arayüz
tarafında yaşıyor. Burada yalnızca İKİ İŞ var:

    giden_sayi_kur()   sıra numarasını resmî sayı biçimine sokar
    gelen_kayit_kur()  alıcı kurumun kayıt damgasını `dosya.gelen_kayit`e yazar

Sayaç dışarıdan geliyor: çağıran taraf `sira_no` veriyor.

NEDEN BİÇİM BACKEND'DE
----------------------
`veri_yapisi.sayi_bolumleri()` gelen belgelerin sayısını AYRIŞTIRIYOR ve
300 belgede ölçüldü. Defter aynı biçimi yazmazsa kendi ürettiğimiz belgeyi
kendi ayrıştırıcımız okuyamaz. Biçim iki yerde tutulursa zamanla ayrışır —
`birimler.py`'nin baştan beri uyguladığı "hesabı tek yerde yap" kuralı.

`kapali_devre_dogrula()` bunu her koşuda sınıyor: üretilen sayı
`sayi_bolumleri()`'ne verilip aynı üç parça geri alınıyor mu.

SAYI BİÇİMİ — 300 BELGEDE ÖLÇÜLDÜ
=================================
    E-{DETSİS}-{SDP}-{kayıt no}          168 belge, 168'inde bu biçim
      │         │      └─ defterin sıra numarası; sıfır dolgusu YOK
      │         │         (gözlenen basamak sayısı 4-8 arası değişiyor)
      │         └─ dosya planı kodu
      └─ YAZAN birimin DETSİS'i

Doğrulandı: 168 belgenin 168'inde ikinci bölüm gönderenin DETSİS'i,
üçüncü bölüm de belgenin SDP kodu.

    {yıl}/{no}                            24 belge — ŞİRKET yazıları
Bu biçimi ÜRETMİYORUZ. Şirketlerin DETSİS'i yok, o yüzden kendi
numaralandırmalarını kullanıyorlar. Biz kamu idaresiyiz; giden yazımız
her zaman `E-` biçiminde. Okuyabiliyoruz, yazmamız gerekmiyor.

    sayı yok                             108 belge — vatandaş dilekçeleri

ŞEMAYA DOKUNULMADI
==================
`CiktiYazi`'da `sayi` ve `tarih` alanı YOK ve bu kasıtlı — devir promptu
§5.3: "Taslakta sayı, tarih ve imzalayanın adı daima null. EBYS atar."
Bu yüzden `giden_sayi_kur` değeri DÖNDÜRÜYOR, `dosya`ya yazmıyor. Saklama
defterin işi.

`gelen_kayit` ise şemada VAR ve doldurulmayı bekliyordu; oraya yazılıyor.
"""

from __future__ import annotations

from datetime import date

from veri_yapisi import GelenKayit, sayi_bolumleri


class DefterHatasi(ValueError):
    """Sayı üretilemedi.

    SESSİZCE None DÖNMÜYORUZ. Eksik bir sayı, bozuk bir sayıdan daha az
    görünürdür: çağıran taraf onu deftere yazar, belge çıkar, kimse fark
    etmez. İstisna fırlatmak çağıranı karar vermeye zorluyor — kaydı
    sayısız tutmak ya da eksiği tamamlamak.
    """


# -----------------------------------------------------------------------------
# Giden evrak
# -----------------------------------------------------------------------------


def yazan_birim(dosya) -> dict | None:
    """Giden yazıyı hangi birim imzalıyor.

    `yazar.kim_yaziyor` yeniden kullanılıyor; ikinci bir uygulama
    yazılmadı. O fonksiyon önce `yonlendirme.hedef_birim`e bakıyor
    (Yönlendirici koştuysa kesin cevap), yoksa muhatap satırından
    çözüyor — 300 belgede ölçüldü, 269/278 doğru.
    """
    from yazar import kim_yaziyor

    return kim_yaziyor(dosya).birim


def _sdp_kodu(dosya) -> str | None:
    """Giden yazının dosya planı kodu.

    Cevap yazısı gelen evrakla AYNI konuyu taşır, dolayısıyla aynı koda
    girer. Üç kaynak, sırayla:

        1  siniflandirma.sdp.kod    Anlama belirledi
        2  gelen belgenin sayısı    kod belgenin üstünde yazılı
        3  konu -> SDP katalogu     deterministik türetme, LLM yok

    ÜÇÜNCÜ KAYNAK NEDEN GEREKLİ — ölçüldü 2026-08-24, belge_025
    -----------------------------------------------------------
    Şirket yazılarının sayısı `2026/103` biçiminde ve SDP TAŞIMIYOR
    (300 belgenin 24'ü böyle). Anlama koşmadığında ilk iki kaynak da
    boş kalıyor ve cevabımıza sayı üretilemiyor.

    `sdp_katalog.konudan_kod_bul` bu boşluğu dolduruyor ve Yönlendirici'de
    zaten ölçüldü: sayısı olmayan 132 belgede 84'ü tek birime, 45'i doğru
    cevabı içeren dar kümeye düşüyor. Burada kodun kendisi yeterli;
    birime düşürmeye gerek yok.

    DÜRÜSTLÜK NOTU: bu hattın isabeti veri setine özgü olarak yüksek —
    `sdp_katalog.py` docstring'i gerekçesini anlatıyor (konu alanları
    katalogun `ornek_konular` havuzundan seçilerek üretildi).
    """
    sdp = getattr(getattr(dosya, "siniflandirma", None), "sdp", None)
    kod = (getattr(sdp, "kod", None) or "").strip()
    if kod:
        return kod

    bolumler = sayi_bolumleri(getattr(dosya.ustveri, "sayi", None))
    kod = (getattr(bolumler, "sdp", None) or "") if bolumler else ""
    if kod:
        return kod

    from sdp_katalog import katalog, konudan_kod_bul

    konu = getattr(dosya.ustveri, "konu", None)
    if not konu:
        return None
    tum = list(katalog())
    if not tum:
        return None
    kod, _oran = konudan_kod_bul(konu, tum)
    return kod or None


def giden_sayi_kur(dosya, sira_no: int, birim_kodu: str | None = None) -> str:
    """Defterin sıra numarasını resmî sayıya çevirir. Değeri DÖNDÜRÜR.

        giden_sayi_kur(dosya, 47)  ->  "E-85330682-773-47"

    `sira_no` defterden gelir ve kurum başına ayrı sayılır (İrem'in
    kararı, 2026-08-24). Yıl bazında sıfırlanmıyor; sayaç sürekli artıyor.
    Bu yüzden sayının içinde yıl bileşeni yok — zaten gözlenen 168
    belgenin hiçbirinde de yoktu.

    `birim_kodu` verilirse o kullanılır; verilmezse yazan birim
    `yonlendirme.hedef_birim`den ya da muhataptan çözülür.
    """
    if not isinstance(sira_no, int) or sira_no < 1:
        raise DefterHatasi(f"Sıra numarası 1 ya da daha büyük olmalı: {sira_no!r}")

    if birim_kodu:
        from birimler import birim_bul

        birim = birim_bul(birim_kodu)
        if birim is None:
            raise DefterHatasi(f"Birim tabloda yok: {birim_kodu}")
    else:
        birim = yazan_birim(dosya)
        if birim is None:
            raise DefterHatasi(
                "Yazıyı hangi birimin imzalayacağı çözülemedi; "
                "yonlendirme.hedef_birim boş ve muhatap da bir birime "
                "bağlanamadı. Sayı üretilemez."
            )

    detsis = (birim.get("detsis_no") or "").strip()
    if not detsis:
        raise DefterHatasi(f"{birim['kod']}: DETSİS numarası yok")

    kod = _sdp_kodu(dosya)
    if not kod:
        raise DefterHatasi(
            "Dosya planı kodu bulunamadı; ne sınıflandırmada ne de gelen "
            "belgenin sayısında var. Sayı üretilemez."
        )

    sayi = f"E-{detsis}-{kod}-{sira_no}"
    _kapali_devre(sayi, detsis, kod, sira_no)
    return sayi


def _kapali_devre(sayi: str, detsis: str, kod: str, sira_no: int) -> None:
    """Ürettiğimiz sayıyı KENDİ ayrıştırıcımız okuyabiliyor mu.

    Her çağrıda koşuyor ve ucuz. Gerekçesi: biçimi burada yazıyoruz,
    `veri_yapisi.sayi_bolumleri()` orada okuyor. İkisi ayrışırsa ürettiğimiz
    belge kendi boru hattımızdan geçemez ve bu ancak aylar sonra, başka bir
    hatanın peşine düşerken fark edilir.
    """
    b = sayi_bolumleri(sayi)
    if b is None:
        raise DefterHatasi(
            f"Üretilen sayı kendi ayrıştırıcımızca okunamadı: {sayi!r}. "
            f"Biçim ile sayi_bolumleri() ayrışmış."
        )
    beklenen = (detsis, kod, str(sira_no))
    bulunan = (b.detsis, b.sdp, b.kayit_no)
    if bulunan != beklenen:
        raise DefterHatasi(
            f"Sayı geri okunduğunda bölümler tutmadı: {sayi!r} -> "
            f"{bulunan}, beklenen {beklenen}"
        )


# -----------------------------------------------------------------------------
# Gelen evrak
# -----------------------------------------------------------------------------


def gelen_kayit_kur(dosya, sira_no: int, tarih: date | None = None) -> GelenKayit:
    """Alıcı kurumun kayıt damgasını `dosya.gelen_kayit`e yazar.

    BU, BELGENİN KENDİ SAYISI DEĞİL. `GelenKayit` docstring'i uyarıyor:
    belgeyi ALAN kurumun kendi defterine yazdığı numaradır (Y m.31/5,
    Örnek 23). Gelen belgenin üstündeki `ustveri.sayi` gönderenindir ve
    ona dokunulmuyor.

    `ham` alanı damganın okunabilir hâli — gerçek yazılarda belgenin
    tepesine basılan blok:

        Evrak Tarih ve Sayısı: 20/02/2026-47

    `havale_edilen_birimler` Yönlendirici'nin kararından geliyor. Karar
    yoksa boş kalıyor; uydurulmuyor.
    """
    if not isinstance(sira_no, int) or sira_no < 1:
        raise DefterHatasi(f"Sıra numarası 1 ya da daha büyük olmalı: {sira_no!r}")

    gun = tarih or date.today()
    kayit = GelenKayit(
        ham=f"Evrak Tarih ve Sayısı: {gun.strftime('%d/%m/%Y')}-{sira_no}",
        kayit_sayisi=str(sira_no),
        kayit_tarihi=gun,
    )
    hedef = getattr(getattr(dosya, "yonlendirme", None), "hedef_birim", None)
    if hedef:
        kayit.havale_edilen_birimler = [hedef]

    dosya.gelen_kayit = kayit
    return kayit


# -----------------------------------------------------------------------------
# Defterin ihtiyaç duyduğu özet
# -----------------------------------------------------------------------------


def defter_satiri(dosya, yon: str, sira_no: int, sayi: str | None = None) -> dict:
    """Defterde bir satır için gereken alanlar. Saklama ÇAĞIRANIN işi.

    `yon`: "gelen" | "giden"

    Arayüz bu sözlüğü SQLite satırına çevirir. Buradaki iş yalnızca
    "hangi alanlar bir defter satırını oluşturur" sorusunu tek yerde
    cevaplamak; iki uygulama olursa gelen ve giden defterleri farklı
    alanlar tutmaya başlar.
    """
    u = dosya.ustveri
    birim = yazan_birim(dosya)
    hedef = getattr(getattr(dosya, "yonlendirme", None), "hedef_birim", None)
    gonderen = getattr(u, "gonderen", None)

    return {
        "yon": yon,
        "sira_no": sira_no,
        "evrak_id": getattr(dosya, "evrak_id", None),
        "sayi": sayi or (u.sayi if yon == "gelen" else None),
        "tarih": (u.tarih if yon == "gelen" else date.today()),
        "konu": (u.konu if yon == "gelen" else dosya.cikti_yazi.konu),
        "muhatap": (
            _taraf_adi(gonderen) if yon == "gelen" else dosya.cikti_yazi.muhatap
        ),
        "birim": hedef or (birim["kod"] if birim else None),
        "belge_turu": (
            getattr(getattr(dosya, "siniflandirma", None), "belge_turu", None)
        ),
        "durum": getattr(dosya, "durum", None),
    }


def _taraf_adi(taraf) -> str | None:
    if taraf is None:
        return None
    parcalar = [x for x in (getattr(taraf, "birim", None),
                            getattr(taraf, "idare", None),
                            getattr(taraf, "ad", None)) if x]
    return parcalar[0] if parcalar else None
