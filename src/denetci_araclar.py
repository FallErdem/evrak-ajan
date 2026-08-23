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

from typing import Any, Callable

from metin import katla
from veri_yapisi import ALAN_YOLLARI, Dosya

# Modele gösterilecek metin sınırları. Uzun cevap hem tokeni yakar hem
# modelin kendi iddiasını unutmasına yol açar.
DEGER_SINIRI = 300
ALINTI_ASGARI = 8          # bundan kısa "alıntı" kanıt sayılmaz


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


# =============================================================================
# Kayıt defteri ve şema
# =============================================================================

ARACLAR: dict[str, Callable[..., str]] = {
    "belgede_cumle_ara": belgede_cumle_ara,
    "alan_oku": alan_oku,
    "kural_bulgulari": kural_bulgulari,
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
# İLK ÜÇÜ ÖLÇÜLEBİLİR
# -------------------
# Bu üçünün veri setinde cevap anahtarı var ve Katman 2 hiçbirini
# yakalamıyor — Katman 3'ün varlık sebebi tam olarak bu boşluk:
#
#     ilgi_tarihi_tutarsiz   12 belge   104 kuralda karşılığı yok
#     ek_beyani_tutarsiz     10 belge   EK-04 "liste boş olmamalı" der, örtüşmüyor
#     kapanis_yonu_yanlis    10 belge   ME-03 yazılmadı (gönderen çıkarımı yok)
#
# Son ikisi ölçülemez; gerçek dünyada işe yaraması için var. Raporda
# ayrımı açıkça yazılacak.
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
    "ek_beyani_tutarsiz": {
        "alan": "ustveri.ekler",
        "onem": "hata",
        "aciklama": "Beyan edilen ek adedi, ek listesindeki kayıt sayısıyla uyuşmuyor.",
        "modele": (
            "Belgede beyan edilen ek adedi ile ek listesindeki kayıt sayısı "
            "farklı. Örnek: 'EKLER: 3 adet' yazıyor ama altında tek satır var."
        ),
    },
    "kapanis_yonu_yanlis": {
        "alan": "metin",
        "onem": "hata",
        "aciklama": "Kapanış ifadesi gönderenin hiyerarşik konumuna uymuyor.",
        "modele": (
            "Kapanış ifadesi yanlış yönde. 'rica ederim' yalnızca ALT makamlara "
            "yazılır; üst ve aynı düzeydeki makamlara 'arz ederim' kullanılır."
        ),
    },
    "talep_belirsiz": {
        "alan": "metin",
        "onem": "uyari",
        "aciklama": "Belgede tam olarak ne istendiği anlaşılmıyor.",
        "modele": (
            "Belgeyi okuyan memur tam olarak ne yapması gerektiğini "
            "anlayamıyor; talep somut değil."
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
