"""Aşama B — kural motorunun ÖZEL FONKSİYONLARI.

Jenerik işleyicilerin (regex, boş olmalı, alan eşitliği...) çözemediği
denetimler burada yaşar. Her fonksiyon bir kural kimliğine bağlıdır ve
`veri/kural_ekleri.json` içinde `yontem_adi` ile çağrılır.

SÖZLEŞME — jenerik işleyicilerle AYNI
-------------------------------------
    (deger, kural, dosya)  ->  (ihlal_var_mi, alinti)   ya da   None

`deger`, kuralın `yol` alanından motor tarafından okunmuş değerdir. Motor
değişmezi burada da geçerli: alan boşsa fonksiyon hiç çağrılmaz.

`None` dönmek "ATLA" demektir: fonksiyon denetim yapabilmek için gereken
veriyi bulamadı. Motor bunu `atlanan_kural_sayisi`na yazar. Yanlış alarm
üretmektense denetlememek yeğdir — memura olmayan bir ihlali göstermek
sisteme güveni bitirir.
"""

from __future__ import annotations

import re
from typing import Any

# =============================================================================
# S-07 · sdp_kod_celiskisi
# =============================================================================


def sdp_kod_celiskisi(deger: Any, kural: dict, dosya) -> tuple[bool, str | None] | None:
    """Sayıdaki dosya planı kodu ile konunun işaret ettiği kod çelişiyor mu.

    NEDEN ÖZEL FONKSİYON — kuralın ilk hâli KIRIKTI
    ------------------------------------------------
    `kural_listesi.md` S-07'yi şöyle tarif ediyor:

        ustveri.sayi[bolum:3]  =  siniflandirma.sdp.kod

    Bu denetim HİÇ TETİKLENMEZ. Sebep: `siniflandirma.sdp.kod` alanını
    dolduran şey `anlama.sdp_sayidan_oku()` ve o da kodu SAYININ ÜÇÜNCÜ
    BÖLÜMÜNDEN okuyor. Yani karşılaştırmanın iki tarafı da aynı kaynaktan
    geliyor; X ile X karşılaştırılıyor ve sonuç her zaman "eşit" çıkıyor.

    `sdp_uyumsuz` kusuru (12 belge) tam olarak bu alanı bozuyor: konu
    değişmiyor, sayıya YANLIŞ kod basılıyor. Aynı kaynaktan okuyan bir
    denetim bunu göremez.

    İKİ BAĞIMSIZ KAYNAK
    -------------------
        1  ustveri.sayi'nın 3. bölümü      belgenin ÜSTÜNDE yazan kod
        2  konu <-> ornek_konular          belgenin NE HAKKINDA olduğu

    İkincisi kodu belgenin numarasından değil, konusundan türetir. Kusurlu
    belgede numara bozulmuş ama konu sağlam kaldığı için ikisi ayrışır.

    NEDEN GÖVDE DEĞİL KONU
    ----------------------
    ÖLÇÜLDÜ (2026-08-23, belge_001):

        konu   "Boya Badana İşleri Hk."   -> 807.01   oran 1.000
        gövde  (tam paragraf metni)       -> None     oran 0.784

    `konudan_kod_bul` yalnızca TAM alt dize eşleşmesi kabul ediyor
    (sdp_katalog.TAM_ESLESME = 1.0). Katalogdaki konu başlığı gövdenin
    içinde birebir geçmiyor, konu alanında geçiyor. Zaten arşiv pratiğinde
    dosya planı kodunu belirleyen şey konudur, gövde değil.

    Konu boşsa (konu_eksik kusuru, 10 belge) gövdeye düşülür; orada da
    eşleşme çıkmazsa kural atlanır.

    DÜRÜSTLÜK NOTU — RAPORA GİRECEK
    -------------------------------
    Veri setinin `konu` alanları katalogun `ornek_konular` havuzundan
    seçilerek üretildi (YONTEM.md: bu sütun kaynakta yoktur, ekip
    yazmıştır). Dolayısıyla konu ile katalog arasındaki eşleşme bu veri
    setinde olağandışı yüksektir. Yöntemin kendisi geçerlidir — gerçek
    kurumlarda memur da dosya planına konuya bakarak karar verir — ancak
    ölçülen isabet oranı bu veri setine özgüdür ve genelleştirilemez.
    """
    from anlama import sdp_adaylari, sdp_sayidan_oku
    from sdp_katalog import konudan_kod_bul

    # 1) Sayıdan oku. Şirket sayısı (2026/103) DETSİS ve SDP taşımaz.
    sayidan = sdp_sayidan_oku(deger)
    if not sayidan:
        return None

    # 2) Muhataptan aday kod kümesini daralt: ~700 kod -> ~5 kod.
    #    Parça 3'te ölçüldü: doğru kod adayların içinde 132/132 = %100.
    muhatap = getattr(dosya.ustveri, "muhatap", None)
    adaylar = sdp_adaylari(
        getattr(muhatap, "ham", None),
        getattr(muhatap, "birim", None),
    )
    if not adaylar:
        return None

    # 3) Konudan bağımsız olarak kodu bul.
    aranan = dosya.ustveri.konu or dosya.metin
    if not aranan:
        return None
    katalogdan, _oran = konudan_kod_bul(aranan, [a[0] for a in adaylar])
    if not katalogdan:
        return None

    if katalogdan == sayidan:
        return False, None
    return True, f"sayıda {sayidan}, konu {katalogdan} kodunu işaret ediyor"


# =============================================================================
# M-01 · muhatap_var_mi
# =============================================================================


def muhatap_var_mi(deger: Any, kural: dict, dosya) -> tuple[bool, str | None] | None:
    """Belgede TANIMLANABİLİR bir muhatap var mı — Y 14/1.

    İKİ AYRI İHLAL, TEK KURAL
    -------------------------
        1  muhatap alanı boş                    -> ihlal
        2  alan dolu ama bir makama karşılık
           gelmiyor ("İLGİLİ MAKAMA")           -> ihlal

    İSTİSNA — dağıtımlı belge
    -------------------------
    `muhatap.tur == DAGITIM_YERLERI` ise muhatap geçerlidir. M-11 bunu
    açıkça düzenliyor. Bu istisna konmadan ölçüldüğünde 153 kusursuz
    belgenin 5'inde yanlış alarm verildi; beşi de dağıtımlı belgeydi.

    NEDEN JENERİK `bos_olmamali` YETMİYOR
    -------------------------------------
    ÖLÇÜLDÜ 2026-08-23: `muhatap_belirsiz` kusuru muhatabı SİLMİYOR,
    muğlaklaştırıyor. Etiketlerdeki `kusur_ayrinti` on belgede de aynı:

        dogru_deger    : "Ankara İl Millî Eğitim Müdürlüğü"
        enjekte_edilen : "İLGİLİ MAKAMA"

    Alan dolu olduğu için `bos_olmamali` haklı olarak sessiz kalıyor;
    M-01 jenerik yapıldığında ölçüm 0/7 çıktı. `kural_listesi.md`'nin
    bu kuralı `özel fonksiyon muhatap_var_mi` diye işaretlemesi doğruymuş.

    NEDEN KELİME LİSTESİ DEĞİL, TABLO EŞLEŞMESİ
    -------------------------------------------
    "İLGİLİ MAKAMA" dizesini aramak on belgenin onunu da yakalar ama
    ölçtüğü şey yöntem değil, üretecin bastığı dizedir. Üreteç yarın
    "ALAKALI BİRİME" yazsa hiçbir şey bulunmaz.

    Bunun yerine muhatap, `birimler.csv`'den gelen 30 hedef birime karşı
    eşleştirilir. Tanımlanabilir bir makam bulunamıyorsa muhatap
    belirsizdir — dizenin ne olduğundan bağımsız olarak.

    ÖLÇÜLDÜ 2026-08-23, `metin.en_iyi_eslesme` ile:

        "İLGİLİ MAKAMA"                                 -> None    0.00
        "ANKARA İL MİLLÎ EĞİTİM MÜDÜRLÜĞÜNE Ortaöğretim
         Şube Müdürlüğü"                                -> bulundu 1.00
        "YENİMAHALLE BELEDİYE BAŞKANLIĞINA Fen İşleri
         Müdürlüğü"                                     -> bulundu 1.00
        "GAZİ ÜNİVERSİTESİ REKTÖRLÜĞÜNE"                -> bulundu 1.00

    Aynı arama Anlama'nın `sdp_adaylari()` fonksiyonunda da kullanılıyor;
    orada 288/288 doğru ölçülmüştü. İkinci bir uygulama yazılmadı.

    SINIR — RAPORA GİRECEK
    ----------------------
    Eşleştirme, bu çalışmadaki 3 kurumun 35 birimlik kaydına yapılır.
    Kayıtta bulunmayan bir idareye yazılmış meşru bir belge, muhatabı
    belirsiz sayılır. Veri setinin tamamı bu üç kuruma geldiği için burada
    ölçülemiyor; gerçek kullanımda birim kaydının kapsamı genişletilmelidir.
    """
    from birimler import hedef_olabilecekler
    from metin import en_iyi_eslesme
    from veri_yapisi import MuhatapTuru

    muhatap = getattr(dosya.ustveri, "muhatap", None)
    ham = getattr(muhatap, "ham", None) if muhatap else None
    birim = getattr(muhatap, "birim", None) if muhatap else None

    # 1) Alan tamamen boş mu. Motor değişmezi burada UYGULANMAZ: bu kuralın
    #    işi zaten yokluğu denetlemek (jenerik `bos_olmamali` ile aynı rol).
    if not dosya.alan_dolu_mu("ustveri.muhatap"):
        return True, None

    # 2) Dağıtımlı belge mi. Bu MEŞRU bir muhatap biçimidir, belirsizlik
    #    değildir — M-11: "Birden fazla muhataba iletilecek dağıtımlı
    #    belgelerin muhatap bölümüne 'DAĞITIM YERLERİNE' ibaresi yazılır."
    #
    #    ÖLÇÜLDÜ 2026-08-23: bu kontrol yokken 153 kusursuz belgenin
    #    5'inde yanlış alarm verildi; beşi de dağıtımlı belgeydi
    #    (kota.json karma_kapanis: 12 dağıtımlı belge). Dağıtımlı belgede
    #    muhatap bir birim DEĞİLDİR, "dağıtım listesine bakınız" demektir;
    #    birim tablosunda karşılığının bulunmaması beklenen davranıştır.
    #
    #    Karşılaştırma ayrıştırıcının çözümlediği enum'a yapılıyor, metne
    #    değil — "DAĞITIM YERLERİNE" dizesi bu kodda geçmiyor.
    if getattr(muhatap, "tur", None) == MuhatapTuru.DAGITIM_YERLERI:
        return False, None

    # 3) Yazılan şey tanımlanabilir bir makam mı.
    arama = " ".join(x for x in (ham, birim) if x)
    if not arama.strip():
        return True, None

    adaylar = [(b["kod"], b["ad"], b["seviye"]) for b in hedef_olabilecekler()]
    if not adaylar:
        # Birim kaydı yüklenemedi. Denetim yapılamaz; bulgu UYDURULMAZ.
        return None

    kod, _oran, _ad = en_iyi_eslesme(arama, adaylar)
    if kod is None:
        return True, _kisalt(arama)
    return False, None


def _kisalt(metin: str | None, sinir: int = 150) -> str | None:
    if not metin:
        return None
    return " ".join(metin.split())[:sinir]


# =============================================================================
# I-09 · metin_ilgi_atfi
# =============================================================================

# "ilgi" ve çekim ekli hâlleri EŞLEŞİR:  ilgi · ilgide · İlgi'de · ilginin
# "ilgili" ve "ilgilen-" EŞLEŞMEZ:        ilgili · ilgililere · ilgilenmek
#
# NEDEN BU AYRIM ZORUNLU — ölçüldü 2026-08-23:
# Naif bir "ilgi" alt dize araması belge_031'in (ilgi_kopuk kusurlu)
# gövdesinde İKİ eşleşme buluyor, çünkü metin "Konuyla ilgili irtibat"
# diyor. Kural o desenle yazılsaydı ihlali HİÇBİR ZAMAN yakalayamazdı ve
# testte de görünmezdi — bulgu yokluğu "temiz belge" gibi okunur.
#
#     naif  'ilgi'   belge_048 (temiz)   -> 2 eşleşme
#                    belge_031 (kusurlu) -> 2 eşleşme   ikisi de sessiz
#     bu desen       belge_048           -> ["ilgi'de"]
#                    belge_031           -> []          doğru ayrım
_ILGI_ATFI = re.compile(r"\bilgi(?!li|len)", re.IGNORECASE)


def metin_ilgi_atfi(deger: Any, kural: dict, dosya) -> tuple[bool, str | None] | None:
    """İlgi tutulan belgeden metin içinde bahsediliyor mu — K 13.2.

    KUSUR NASIL ÇALIŞIYOR
    ---------------------
    `ilgi_kopuk` (12 belge) ilgi satırını SİLMİYOR; gövdedeki atfı
    kaldırıyor. Etiketteki `kusur_ayrinti` bunu birebir gösteriyor:

        dogru_deger    : "İlgide kayıtlı yazı ile Atama Onayı talebinde…"
        enjekte_edilen : "Söz konusu yazı ile Atama Onayı talebinde…"

    Belgenin üstünde ilgi duruyor, gövde ondan hiç söz etmiyor. Okuyan
    memur hangi yazıya cevap verildiğini metinden anlayamaz.

    NEDEN "anılan yazı" / "söz konusu yazı" ARANMIYOR
    -------------------------------------------------
    Kusurlu belgede bu ifadeler HÂLÂ VAR ("Talep, anılan yazıda belirtilen
    hususlar çerçevesinde…"). Onları aramak kuralı işlevsiz bırakır.
    Aranan şey ilgiye yapılan AÇIK atıftır.

    SINIR — RAPORA GİRECEK
    ----------------------
    K 13.2 bağın İLK PARAGRAFTA kurulmasını istiyor. Gövde satır satır
    okunup boşlukla birleştirildiği için paragraf sınırları elimizde yok
    (`Satir` yalnızca y taşıyor, x taşımıyor). Bu yüzden denetim gövdenin
    TAMAMINDA yapılıyor — kuraldan daha hoşgörülü. Yanlış alarm üretmeyen
    tarafa düşüyor.
    """
    ilgiler = getattr(dosya.ustveri, "ilgi", None)
    if not ilgiler:
        return None                      # ilgi yok, denetlenecek bağ da yok

    govde = dosya.metin
    if not govde or not govde.strip():
        return None                      # gövde kurulamadı; ME-01 bunu bildirir

    if _ILGI_ATFI.search(govde):
        return False, None
    return True, _kisalt(govde[:120])


# =============================================================================
# Kayıt defteri
# =============================================================================
#
# kural_ekleri.json'daki `yontem_adi` buradaki anahtarla eşleşmelidir.
# Eşleşmezse motor YÜKLENME ANINDA hata verir — ilk belgede değil.

OZEL_FONKSIYONLAR = {
    "sdp_kod_celiskisi": sdp_kod_celiskisi,
    "muhatap_var_mi": muhatap_var_mi,
    "metin_ilgi_atfi": metin_ilgi_atfi,
}
