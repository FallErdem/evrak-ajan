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
# Kayıt defteri
# =============================================================================
#
# kural_ekleri.json'daki `yontem_adi` buradaki anahtarla eşleşmelidir.
# Eşleşmezse motor YÜKLENME ANINDA hata verir — ilk belgede değil.

OZEL_FONKSIYONLAR = {
    "sdp_kod_celiskisi": sdp_kod_celiskisi,
}
