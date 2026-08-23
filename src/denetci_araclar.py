"""Denetçi Katman 3 — modelin çağırabileceği ARAÇLAR.

src/ altında duran, içe aktarılan modüldür.

NEDEN ARAÇ VERİYORUZ
--------------------
Katman 2 (kural motoru) deterministik: kuralı koşturur, bulguyu üretir.
Karar yoktur, döngü yoktur — bir araçtır.

Katman 3'te direksiyon modele geçer. Model belgeyi okur, bir eksik
olduğunu düşünür, ve iddiasını DOĞRULAMAK için hangi aracı ne zaman
çağıracağına KENDİ karar verir. Sonucu görür, yanıldıysa iddiasını geri
alır. Karar + gözlem + düzeltme: ajan budur.

ÜÇ ARAÇ, ÜÇÜ DE DETERMİNİSTİK
-----------------------------
    belgede_cumle_ara(alinti)   iddianın kanıtı belgede gerçekten var mı
    alan_oku(yol)               "ustveri.tarih" ne? boş mu dolu mu
    kural_bulgulari()           Katman 2 ne bulmuş — tekrar etmeyeyim

Hiçbiri yeni mantık içermiyor; hepsi mevcut ve ölçülmüş fonksiyonlara
bağlanıyor (`Dosya.deger_al`, `metin.katla`). Model bunları çağırır ama
sonucu BİZ üretiriz — uydurma buraya sızamaz.

İKİ ELEME KAPISI ARACIN İÇİNDE
------------------------------
1. `alan_oku` yalnızca `ALAN_YOLLARI`'ndaki 43 yolu kabul eder. Model
   uydurma bir yol isterse araç "böyle bir alan yok" der.
2. `belgede_cumle_ara` katlanmış karşılaştırma yapar (Türkçe işaretler ve
   OCR hasarına dayanıklı), ama METNİ ONARMAZ — yalnızca karşılaştırmayı
   esnetir. `src/metin.py`'nin baştan beri izlediği ilke.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from metin import benzerlik, katla
from veri_yapisi import ALAN_YOLLARI, Dosya, MuhatapTuru

# Modele gösterilecek metin sınırları. Uzun cevap hem tokeni yakar hem
# modelin kendi iddiasını unutmasına yol açar.
DEGER_SINIRI = 300
ALINTI_ASGARI = 8          # bundan kısa "alıntı" kanıt sayılmaz

# Hiyerarşi tablosunun kaynağı. CSV/JSON tek kaynak kuralı: bu dosyalar
# elle düzenlenmez, kurum kayıtları oradan okunur.
KURUM_KLASORU = Path(__file__).resolve().parent.parent / "veri" / "kurumlar"

# Alıcı kurumu kurum*.json ile eşlerken kullanılan benzerlik eşiği. Adlar
# birebir yazılmıyor ("Gazi Üniversitesi" / "Gazi Üniversitesi Rektörlüğü").
KURUM_ESIGI = 0.75

_HIYERARSI: dict[str, dict] | None = None


# =============================================================================
# Araç gövdeleri
# =============================================================================


def belgede_cumle_ara(dosya: Dosya, alinti: str = "", **_) -> str:
    """İddianın kanıtı belgede gerçekten geçiyor mu.

    KARŞILAŞTIRMA KATLANMIŞ HÂLDE YAPILIR
    -------------------------------------
    `metin.katla()` Türkçe işaretleri düşürür ve boşlukları toplar:

        "Söz Konusu YAZI"  ->  "soz konusu yazi"

    Sebep `metin.py`'de ölçülmüş: OCR taranmış belgede işaretleri bozuyor
    ("gönderilmiştir" -> "gönderilmistir"). Metin ONARILMAZ, karşılaştırma
    esnetilir. Model doğru cümleyi biraz farklı yazmışsa da eşleşir;
    hiç olmayan bir cümle uydurmuşsa eşleşmez.

    ÇOK KISA ALINTI KANIT SAYILMAZ
    ------------------------------
    Model "yazı" ya da "eksik" gibi tek kelime verirse bu her belgede
    geçer ve doğrulama anlamsızlaşır. Sekiz karakterin altı reddedilir.
    """
    alinti = (alinti or "").strip()
    if len(alinti) < ALINTI_ASGARI:
        return (
            f"HATA: alıntı çok kısa ({len(alinti)} karakter). Kanıt olarak "
            f"belgeden en az {ALINTI_ASGARI} karakterlik bir bölüm ver."
        )

    govde = dosya.metin or ""
    ham = dosya.deger_al("kaynak.ham_metin") or ""
    if not govde and not ham:
        return "HATA: belge metni okunamadı, doğrulama yapılamıyor."

    aranan = katla(alinti)
    if aranan in katla(govde):
        return "BULUNDU: alıntı belgenin gövdesinde geçiyor. İddian doğrulandı."
    if aranan in katla(ham):
        return (
            "BULUNDU: alıntı belgede geçiyor ancak gövdede değil "
            "(başlık, imza veya altbilgi bölümünde)."
        )
    return (
        f"HATA: '{alinti[:80]}' belgede GEÇMİYOR. Bu iddiayı destekleyen bir "
        f"kanıt yok. Ya belgeden birebir başka bir alıntı ver ya da iddiandan "
        f"vazgeç."
    )


def alan_oku(dosya: Dosya, yol: str = "", **_) -> str:
    """Belgenin çözümlenmiş bir alanını okur.

    YALNIZCA TANIMLI YOLLAR
    -----------------------
    `ALAN_YOLLARI` 43 yol taşıyor ve bu küme şemayla hizalı. Model
    uydurma bir yol isterse ("ustveri.imza_sahibi_unvan" gibi — bu yol
    kural listesinde gerçekten yanlış yazılmıştı ve kural aylarca sessizce
    kırık kaldı) araç açıkça "böyle bir alan yok" der.

    Bu bir eleme kapısıdır: modelin var sandığı ama olmayan bir alana
    dayanarak eksik iddia etmesini engeller.
    """
    yol = (yol or "").strip()
    if not yol:
        return "HATA: yol boş. Örnek: 'ustveri.tarih'"
    if yol not in ALAN_YOLLARI:
        return (
            f"HATA: '{yol}' diye bir alan YOK. Tanımlı alanlardan birini seç. "
            f"Sık kullanılanlar: ustveri.sayi, ustveri.tarih, ustveri.konu, "
            f"ustveri.muhatap, ustveri.ilgi, ustveri.ekler, ustveri.imza, metin"
        )

    deger = dosya.deger_al(yol)
    if deger is None:
        return f"{yol} = BOŞ (alan hiç doldurulmamış)"
    if isinstance(deger, (list, tuple)):
        if not deger:
            return f"{yol} = BOŞ LİSTE (hiç kayıt yok)"
        return f"{yol} = {len(deger)} kayıt: {str(deger)[:DEGER_SINIRI]}"
    metin = str(deger).strip()
    if not metin:
        return f"{yol} = BOŞ"
    return f"{yol} = {metin[:DEGER_SINIRI]}"


def kural_bulgulari(dosya: Dosya, **_) -> str:
    """Katman 2'nin bu belgede bulduğu eksikler.

    NEDEN GEREKLİ
    -------------
    Model, kural motorunun ZATEN bulduğu bir eksiği tekrar iddia ederse
    memur aynı uyarıyı iki kez görür. Modelin bunu bilmesi gerekir.

    Liste `dosya.icerik.eksik_alanlar`dan okunuyor; Denetçi Katman 2'yi
    Katman 3'ten ÖNCE koşturduğu için burada dolu olur.
    """
    eksikler = getattr(dosya.icerik, "eksik_alanlar", None) or []
    if not eksikler:
        return (
            "Kural motoru bu belgede hiçbir eksik bulmadı. "
            "Kurallarla yakalanamayan bir eksik var mı, ona bak."
        )
    satirlar = [
        f"- {e.kural_id or '?'}: {e.aciklama}" for e in eksikler if e.aciklama
    ]
    return (
        "Kural motorunun BULDUĞU eksikler (bunları TEKRAR ETME):\n"
        + "\n".join(satirlar)
    )


# -- gönderen ve kapanış yönü -------------------------------------------------

# Antet bloğu, üstveri satırlarında (Sayı / Konu / İlgi) biter.
# Ayrıştırıcının `muhatap_satiri` alanına bağlanmak yerine ham metinden
# kesiliyor: `Dosya` o alanı taşımıyor ve araç yalnızca `Dosya` görüyor.
#
# ÜÇÜ BİRDEN ARANIYOR, YALNIZCA "Sayı" DEĞİL — ölçüldü 2026-08-23:
# `sayi_eksik` kusurlu 12 belgede Sayı satırı silinmiş ama Konu satırı
# duruyor. Yalnızca Sayı aransaydı o belgelerde kesme noktası bulunamaz
# ve araç antet yerine GÖVDEYİ döndürürdü.
_USTVERI_SATIRI = re.compile(r"^\s*(say[iı]|konu|ilgi)\s*[:：]", re.IGNORECASE)
ANTET_AZAMI_SATIR = 6


def antet_oku(dosya: Dosya, **_) -> str:
    """Belgenin antet bloğu — GÖNDEREN orada yazılıdır.

    NEDEN GEREKLİ
    -------------
    `ustveri.gonderen` yolu şemada tanımlı ama ayrıştırıcı onu HİÇ
    doldurmuyor (ölçüldü: grep -> 0 sonuç). Gönderen belgenin ilk
    satırlarındadır.

    Bu araç çıkarım YAPMAZ, ham satırları verir. Göndereni okuma işini
    model yapar; biz yalnızca doğru bölgeyi gösteririz. Böylece
    ayrıştırıcıya eklenecek gönderen çıkarımıyla mantık ÇAKIŞMAZ — o
    deterministik bir alan doldurur, bu araç modele metni gösterir.

    KİŞİ BELGESİNDE ANTET YOKTUR
    ----------------------------
    ÖLÇÜLDÜ 2026-08-23, belge_081: dilekçede Sayı/Konu/İlgi satırlarının
    hiçbiri yok. Kesme noktası bulunamayınca araç ilk altı satırı, yani
    MUHATAP VE GÖVDEYİ döndürüyordu; model "YENİMAHALLE BELEDİYE
    BAŞKANLIĞINA" ifadesini gönderen sanabilirdi. Artık açıkça "antet yok"
    deniyor.
    """
    ham = dosya.deger_al("kaynak.ham_metin") or ""
    if not ham.strip():
        return "HATA: belgenin ham metni okunamadı."

    satirlar = [s.strip() for s in ham.split("\n") if s.strip()]
    antet: list[str] = []
    kesildi = False
    for s in satirlar[:ANTET_AZAMI_SATIR]:
        if _USTVERI_SATIRI.match(s):
            kesildi = True
            break
        antet.append(s)

    if not kesildi or not antet:
        return (
            "Bu belgede antet bloğu YOK. Kurum antetli bir yazı değil; "
            "gönderen büyük olasılıkla gerçek kişi ya da kurum dışı bir "
            "tüzel kişidir. Her iki durumda da beklenen kapanış 'arz ederim'."
        )
    return (
        "Belgenin antet bloğu (gönderen burada yazılıdır):\n"
        + "\n".join(f"  {s}" for s in antet)
    )


def _hiyerarsi_tablosu() -> dict[str, dict]:
    """kurum*.json dosyalarından {kurum_adi: hiyerarsi}. Bir kez okunur."""
    global _HIYERARSI
    if _HIYERARSI is not None:
        return _HIYERARSI
    tablo: dict[str, dict] = {}
    if KURUM_KLASORU.exists():
        for yol in sorted(KURUM_KLASORU.glob("kurum*.json")):
            try:
                d = json.loads(yol.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            ad = d.get("kurum_adi")
            if ad:
                tablo[ad] = d.get("hiyerarsi", {}) or {}
    _HIYERARSI = tablo
    return tablo


def _alici_adaylari(dosya: Dosya) -> list[str]:
    """Belgenin muhatabı olan kurum için ADAY adlar, denenme sırasıyla.

    `ustveri.muhatap.idare` çoğu belgede doğrudan kurum adıdır. Ama
    ÖLÇÜLDÜ 2026-08-23, belge_031: o alan bir BİRİM adı taşıyabiliyor
    ("PERSONEL DAİRESİ BAŞKANLIĞINA"). İlk aday tutmayınca ikinci hat
    devreye giriyor: birim adı `birimler.csv`'deki 35 birimle eşleştirilir
    ve birimin bağlı olduğu kurum okunur.

    Tek adayla dönülüp erken çıkılırsa bu ikinci hat hiç çalışmıyordu —
    ilk sürümün hatası buydu.

    Eşleştirme M-01'de ve Anlama'nın SDP aday üretiminde de kullanılıyor;
    ikinci bir uygulama yazılmadı.
    """
    muhatap = getattr(dosya.ustveri, "muhatap", None)
    idare = getattr(muhatap, "idare", None) if muhatap else None
    ham = getattr(muhatap, "ham", None) if muhatap else None
    birim = getattr(muhatap, "birim", None) if muhatap else None

    adaylar: list[str] = [x for x in (idare, ham) if x]

    arama = " ".join(x for x in (ham, birim, idare) if x).strip()
    if arama:
        try:
            from birimler import birim_bul, birimleri_yukle
            from metin import en_iyi_eslesme

            birim_adaylari = [
                (b["kod"], b["ad"], b["seviye"]) for b in birimleri_yukle()
            ]
            kod, _oran, _ad = en_iyi_eslesme(arama, birim_adaylari)
            if kod:
                kurum = (birim_bul(kod) or {}).get("kurum")
                if kurum:
                    adaylar.append(kurum)
        except ImportError:
            pass

    # Yinelenenleri sırayı bozmadan at
    gorulen: set[str] = set()
    return [a for a in adaylar if not (a in gorulen or gorulen.add(a))]


def makam_konumu(dosya: Dosya, makam_adi: str = "", **_) -> str:
    """Gönderenin alıcıya göre hiyerarşik konumu ve beklenen kapanış.

    KURAL — kota.json `kapanis_kurali`, uydurulmadı
    -----------------------------------------------
        ust_makam   -> RICA        (yalnızca yukarıdan aşağı)
        ayni_duzey  -> arz
        alt_makam   -> arz
        vatandas    -> arz
        ozel_tuzel  -> arz

    Yani "rica" YALNIZCA üst makam yazarken doğrudur. Tabloda bulunamayan
    bir gönderen için doğru cevap "arz"dır.

    ÖLÇÜLDÜ 2026-08-23, 300 etiket (araclar/kapanis_kapsam_olc.py):
        doğru                 291/300 = %97
        ÜST MAKAM KAÇIRILDI     0        <- kritik hata türü, hiç yok
        fazladan üst sanıldı    9        hepsi `karma` kapanışlı belgeler
        tabloda bulunamayan    60        hiçbiri üst makam değil
                                         (Ltd. Şti., müdürlük, ilçe MEM)
    Karma kapanışlılar hariç tutulduğunda isabet 291/291.

    DAĞITIMLI BELGE İSTİSNASI
    -------------------------
    `kota.json karma_kapanis`: 12 belge DAĞITIM YERLERİNE gider ve
    "arz/rica ederim" ile biter. Orada iki yön de meşrudur; araç bunu
    açıkça söyler ki model yanlış alarm üretmesin.
    """
    muhatap = getattr(dosya.ustveri, "muhatap", None)

    # Dağıtımlı belgede kapanış yönü denetlenmez.
    if getattr(muhatap, "tur", None) == MuhatapTuru.DAGITIM_YERLERI:
        return (
            "Bu belge DAĞITIM YERLERİNE gönderilen çok muhataplı bir belgedir. "
            "Böyle belgelerde 'arz ederim', 'rica ederim' ve 'arz/rica ederim' "
            "kapanışlarının hepsi geçerlidir. Kapanış yönünü sorgulama."
        )

    makam_adi = (makam_adi or "").strip()
    if not makam_adi:
        return (
            "HATA: makam_adi boş. Önce antet_oku ile göndereni bul, sonra "
            "adını buraya ver."
        )

    adaylar = _alici_adaylari(dosya)
    if not adaylar:
        return "HATA: belgenin muhatabı okunamadı, konum belirlenemiyor."

    tablo = _hiyerarsi_tablosu()
    if not tablo:
        return "HATA: kurum hiyerarşi tablosu yüklenemedi."

    hiyerarsi = None
    alici = adaylar[0]
    for aday in adaylar:
        for ad, h in tablo.items():
            if benzerlik(ad, aday) >= KURUM_ESIGI:
                hiyerarsi, alici = h, ad
                break
        if hiyerarsi is not None:
            break
    if hiyerarsi is None:
        return (
            f"'{adaylar[0]}' bu çalışmadaki kurum kayıtlarında yok; konum "
            f"belirlenemiyor. Kapanış yönünü sorgulama."
        )

    g = katla(makam_adi)
    for konum, anahtar in (
        ("üst makam", "ust_makamlar"),
        ("aynı düzeyde", "ayni_duzey"),
        ("alt makam", "alt_makamlar"),
    ):
        for aday in hiyerarsi.get(anahtar, []) or []:
            k = katla(aday)
            if k and (k in g or g in k):
                beklenen = "rica ederim" if anahtar == "ust_makamlar" else "arz ederim"
                return (
                    f"'{makam_adi}', '{alici}' makamına göre {konum}. "
                    f"Beklenen kapanış: '{beklenen}'."
                )

    return (
        f"'{makam_adi}' hiyerarşi tablosunda bulunamadı. Tabloda yalnızca üst "
        f"makamlar, aynı düzeydekiler ve alt birimler kayıtlı; bulunamayan bir "
        f"gönderen üst makam DEĞİLDİR. Beklenen kapanış: 'arz ederim'."
    )


# =============================================================================
# Kayıt defteri ve şema
# =============================================================================

ARACLAR: dict[str, Callable[..., str]] = {
    "belgede_cumle_ara": belgede_cumle_ara,
    "alan_oku": alan_oku,
    "kural_bulgulari": kural_bulgulari,
    "antet_oku": antet_oku,
    "makam_konumu": makam_konumu,
}

# OpenAI/OpenRouter araç tanımı biçimi. Model bu açıklamaları okuyup
# hangi aracı çağıracağına karar verir; açıklamalar İSTEMİN parçasıdır.
ARAC_SEMASI: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "belgede_cumle_ara",
            "description": (
                "Bir cümlenin ya da ifadenin belgede geçip geçmediğini kontrol "
                "eder. Bir eksik iddia etmeden ÖNCE kanıtını bununla doğrula. "
                "Belgede olmayan bir şeye dayanarak iddiada bulunma."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "alinti": {
                        "type": "string",
                        "description": (
                            "Belgeden birebir alınmış en az 8 karakterlik bir "
                            "bölüm. Kendi cümlen değil, belgenin cümlesi."
                        ),
                    }
                },
                "required": ["alinti"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "alan_oku",
            "description": (
                "Belgenin çözümlenmiş bir alanını okur ve dolu mu boş mu "
                "söyler. Bir bilginin eksik olduğunu iddia etmeden önce "
                "gerçekten boş olduğunu bununla doğrula."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "yol": {
                        "type": "string",
                        "description": (
                            "Alan yolu. Örnek: ustveri.tarih, ustveri.sayi, "
                            "ustveri.konu, ustveri.muhatap, ustveri.ilgi, "
                            "ustveri.ekler, ustveri.imza, metin"
                        ),
                    }
                },
                "required": ["yol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kural_bulgulari",
            "description": (
                "Kural motorunun bu belgede zaten bulduğu eksikleri listeler. "
                "Aynı eksiği tekrar iddia etmemek için önce buna bak."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "antet_oku",
            "description": (
                "Belgenin antet bloğunu (ilk satırlarını) verir. GÖNDEREN "
                "kurumun adı orada yazılıdır. Kapanış yönünü denetleyeceksen "
                "önce bunu çağır."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "makam_konumu",
            "description": (
                "Bir makamın, belgenin muhatabına göre hiyerarşik konumunu ve "
                "BEKLENEN KAPANIŞ ifadesini söyler. Kapanış yönü hakkında ASLA "
                "tahmin yürütme; önce antet_oku ile göndereni bul, sonra bunu "
                "çağır."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "makam_adi": {
                        "type": "string",
                        "description": (
                            "Antette yazan gönderen kurumun adı. "
                            "Örnek: 'Çankaya Belediye Başkanlığı'"
                        ),
                    }
                },
                "required": ["makam_adi"],
            },
        },
    },
]


# =============================================================================
# Katman 3 kategorileri — modelin seçebileceği TEK küme
# =============================================================================
#
# NEDEN BELGE TÜRÜNE GÖRE DARALTILMADI
# ------------------------------------
# Kategorileri belge türüne göre yazmak, onları KENDİ VERİ SETİMİZDEN
# türetmek olurdu. Sonra "yakaladı" diye ölçtüğümüzde yakaladığı şey bizim
# koyduğumuz şey olurdu. Bu projede aynı tuzağa iki kez düşüldü:
# `ornek_konular` bulanık eşleştirmesi döngüseldi ve kaldırıldı; S-07'nin
# ilk hâli X ile X karşılaştırıyordu ve hiç tetiklenmezdi.
#
# Gerçek kullanımda eksiklik sonsuz çeşitliliktedir. Liste, herhangi bir
# evrakta bir memurun soracağı sorulardan oluşuyor.
#
# İKİSİ ÖLÇÜLEBİLİR
# -----------------
# Bu ikisinin veri setinde cevap anahtarı var ve Katman 2 hiçbirini
# yakalamıyor — Katman 3'ün varlık sebebi tam olarak bu boşluk:
#
#     ilgi_tarihi_tutarsiz   12 belge   104 kuralda karşılığı yok
#     kapanis_yonu_yanlis    10 belge   ME-03 yazılmadı (gönderen çıkarımı yok)
#
# `atif_belirsiz` ölçülemez; gerçek dünyada işe yaraması için var.
#
# ÇIKARILAN İKİ KATEGORİ — ÖLÇÜM SONUCU, 2026-08-23
# -------------------------------------------------
# 20 belgelik örneklemde 11 kusursuz belgenin 4'ünde yanlış alarm çıktı
# (%36). Üçü modelin GÖREMEDİĞİ ya da BİLEMEDİĞİ şey hakkındaydı:
#
#     ek_beyani_tutarsiz   'EKLER: 3 adet' beyanı modele hiç gitmiyor;
#                          o satır kaynak.ham_metin'de, isteme yalnızca
#                          gövde konuyor. Model görmediğini bulamaz;
#                          üç kusurlu belgede de doğru davranıp
#                          'eksik_yok' dedi. Kategori ÇIKARILDI.
#     talep_belirsiz       Veri setinin gövdeleri `somut_bilgiler`
#                          alanlarından üretiliyor ve o alanlar doğası
#                          gereği soyut ("gerekli sürenin tanınması").
#                          Bu soyutluk 300 belgenin hepsinde var, kategori
#                          her temiz belgede ateşleyebilir. ÇIKARILDI.
#
# kapanis_yonu_yanlis ÇIKARILMADI: yanlış alarmın sebebi modelin gönderen
# bilgisine erişememesiydi. `antet_oku` ve `makam_konumu` araçları tam bu
# boşluğu kapatıyor.
#
# `alan` değeri EksikAlan.alan'a yazılır ve arayüz o alanı vurgular.
KATEGORILER: dict[str, dict] = {
    "ilgi_tarihi_tutarsiz": {
        "alan": "ustveri.ilgi",
        "onem": "hata",
        "aciklama": "İlgi tutulan yazının tarihi, belgenin kendi tarihinden sonra.",
        "modele": (
            "İlgi tutulan yazının tarihi, belgenin kendi tarihinden SONRA. "
            "Bir belge kendisinden sonra yazılmış bir yazıya atıf yapamaz."
        ),
    },
    "kapanis_yonu_yanlis": {
        "alan": "metin",
        "onem": "hata",
        "aciklama": "Kapanış ifadesi gönderenin hiyerarşik konumuna uymuyor.",
        "modele": (
            "Kapanış ifadesi gönderenin hiyerarşik konumuna uymuyor. Bunu "
            "İDDİA ETMEDEN ÖNCE antet_oku ile göndereni bul ve makam_konumu "
            "ile beklenen kapanışı sor. Tahmin yürütme."
        ),
    },
    "atif_belirsiz": {
        "alan": "metin",
        "onem": "uyari",
        "aciklama": "Metinde tanımsız bir belgeye atıf yapılıyor.",
        "modele": (
            "Metin 'söz konusu yazı', 'anılan belge' gibi bir atıf yapıyor ama "
            "hangi belge olduğu tarih ve sayı ile belirtilmemiş."
        ),
    },
    "eksik_yok": {
        "alan": None,
        "onem": None,
        "aciklama": None,
        "modele": "Kuralların yakalayamadığı bir eksik bulamadım.",
    },
}


def _sonuc_bildir_semasi() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "sonuc_bildir",
            "description": (
                "İncelemeni bitirdiğinde bunu çağır. Bir eksik bulduysan "
                "kategorisini, gerekçeni ve belgeden birebir alıntını ver. "
                "Bulamadıysan kategori olarak 'eksik_yok' seç."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "kategori": {
                        "type": "string",
                        "enum": list(KATEGORILER),
                        "description": "Bulduğun eksiğin kategorisi.",
                    },
                    "gerekce": {
                        "type": "string",
                        "description": (
                            "Neden bu sonuca vardığın, tek cümle. "
                            "eksik_yok seçtiysen kısa bir açıklama yeter."
                        ),
                    },
                    "alinti": {
                        "type": "string",
                        "description": (
                            "Belgeden BİREBİR alınmış kanıt cümlesi. Kendi "
                            "cümlen değil. eksik_yok seçtiysen boş bırak."
                        ),
                    },
                },
                "required": ["kategori", "gerekce"],
            },
        },
    }


def tum_arac_semasi() -> list[dict]:
    """Modele gönderilecek araç listesi: üç inceleme aracı + sonuç bildirimi.

    `sonuc_bildir` bir "araç" değil, DÖNGÜNÜN ÇIKIŞ KAPISIDIR. Araç
    biçiminde tanımlanmasının sebebi şemanın sağlayıcı tarafından
    zorlanması: `kategori` bir enum ve model onun dışına çıkamaz. Serbest
    metin isteyip sonra ayrıştırmak, Parça 3'te öğrenilen dersin tersi
    olurdu — orada yalnızca enum kısıtının güvenilir biçimde zorlandığı
    ölçülmüştü.
    """
    return ARAC_SEMASI + [_sonuc_bildir_semasi()]


def arac_calistir(ad: str, argumanlar: dict, dosya: Dosya) -> str:
    """Modelin istediği aracı çalıştırır ve gözlemi metin olarak döndürür.

    Bilinmeyen araç adı ÇÖKERTMEZ: model uydurma bir araç adı verebilir ve
    bu bir model hatasıdır. Döngüye açık bir gözlem döndürülür ki model
    kendini düzeltebilsin — ReAct'in "observation" adımı budur.
    """
    fn = ARACLAR.get(ad)
    if fn is None:
        return (
            f"HATA: '{ad}' diye bir araç yok. Kullanabileceğin araçlar: "
            + ", ".join(ARACLAR)
        )
    try:
        return fn(dosya, **(argumanlar or {}))
    except TypeError as e:
        # Model yanlış ya da eksik argüman verdi. Yine model hatası.
        return f"HATA: '{ad}' aracına verilen argümanlar geçersiz ({e})."
