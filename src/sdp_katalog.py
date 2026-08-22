"""SDP katalogu — kod ile adını eşleştirir.

NEREDEN: veri/taksonomi/sdp_kodlari.csv

NEDEN GEREKLİ
-------------
Anlama'da SDP kodu tahmin edilirken modele çıplak kod listesi vermek
yetmiyor:

    ["215.01", "225.02", "245.04", "250"]

Bu liste modele hiçbir şey söylemiyor. Adıyla birlikte verilince seçim
anlamlı hale geliyor:

    215.01  Yurtdışı Eğitim Denkliği
    225.02  Öğrenci Nakil ve Geçiş İşlemleri
    245.04  Yatılılık ve Bursluluk

Katalog `ornek_konular` sütunu da taşıyor; ileride eşleştirmeyi
güçlendirmek gerekirse oradan yararlanılabilir.
"""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent

# Katalog birden çok yerde bulunabiliyor; sırayla denenir.
ARAMA_YERLERI = (
    KOK / "veri" / "taksonomi" / "sdp_kodlari.csv",
    KOK / "veri" / "sdp_kodlari.csv",
    KOK / "taksonomi" / "sdp_kodlari.csv",
)


def _katalog_yolu() -> Path | None:
    for y in ARAMA_YERLERI:
        if y.exists():
            return y
    for y in KOK.rglob("sdp_kodlari.csv"):
        return y
    return None


@lru_cache(maxsize=1)
def katalog() -> dict[str, dict]:
    """kod -> {ad, saklama_suresi, ornek_konular}

    Katalog bulunamazsa BOŞ döner ve çağıran taraf ada erişemez. Bu
    sessiz bir bozulma değil: sdp_adaylari() kodları yine döndürür,
    yalnızca adları boş kalır.
    """
    yol = _katalog_yolu()
    if yol is None:
        return {}
    kayitlar: dict[str, dict] = {}
    with yol.open(encoding="utf-8-sig", newline="") as f:
        for satir in csv.DictReader(f):
            kod = (satir.get("kod") or "").strip()
            if not kod:
                continue
            kayitlar[kod] = {
                "ad": (satir.get("ad") or "").strip(),
                "saklama_suresi": (satir.get("saklama_suresi") or "").strip() or None,
                "ornek_konular": [
                    k.strip() for k in (satir.get("ornek_konular") or "").split("|")
                    if k.strip()
                ],
            }
    return kayitlar


def ornek_konular(kod: str, azami: int = 3) -> list[str]:
    """Kodun örnek konu başlıkları — LLM istemine konur.

    Model anlamsal eşleştirme yapabilsin diye. Dize benzerliğinin
    yakalayamadığı parafrazları model yakalar.
    """
    kayit = katalog().get((kod or "").strip())
    return kayit["ornek_konular"][:azami] if kayit else []


def kod_adi(kod: str | None) -> str | None:
    """SDP kodunun adı. Bulunamazsa üst kırılıma düşülür.

    Dosya planı hiyerarşik: 198.02.01 yoksa 198.02, o da yoksa 198.
    """
    if not kod:
        return None
    k = katalog()
    parcalar = kod.split(".")
    for uzunluk in range(len(parcalar), 0, -1):
        aday = ".".join(parcalar[:uzunluk])
        if aday in k:
            return k[aday]["ad"] or None
    return None


def saklama_suresi(kod: str | None) -> str | None:
    if not kod:
        return None
    kayit = katalog().get(kod.strip())
    return kayit["saklama_suresi"] if kayit else None


# -----------------------------------------------------------------------------
# Konu eşleştirme
# -----------------------------------------------------------------------------

# YALNIZCA TAM ALT DİZE EŞLEŞMESİ KABUL EDİLİR.
#
# İlk sürüm 0.60 bulanık eşiği kullanıyordu ve %95 isabet ölçüyordu. O sayı
# GEÇERSİZDİ. YONTEM.md `ornek_konular` sütunu için açıkça şunu diyor:
#
#     "Bu sütun kaynakta yoktur; kurumsal yazışma pratiğinden yazılmıştır.
#      Veri setinin en yumuşak kısmı budur — kodlar doğrulanabilir,
#      konu başlıkları doğrulanamaz."
#
# Üreteç belgenin konusunu bu listeden SEÇTİ. Gövdeyi aynı listeye karşı
# bulanık eşleştirmek "üretecin kullandığı dizeyi bulabildim" demektir;
# genelleme ölçüsü değildir. Ölçülen dağılım:
#
#     tam alt dize      37 belge (%28)  isabet 36/37
#     bulanık 0.60-0.99 92 belge (%70)  isabet 87/92   <- döngüsel
#     eşleşme yok        3 belge (%2)
#
# Tam alt dize farklıdır: belgede katalogdaki konu başlığı BİREBİR
# yazıyorsa eşleştirmek her veri setinde meşrudur. Yalnızca bizim
# setimizde %28 sıklıkla oluyor; gerçekte daha seyrek olur.
#
# Bulanık bölge LLM'e devredildi. Maliyeti YOK: SDP zaten belge türüyle
# aynı çağrıda soruluyor, yalnızca istem biraz uzuyor. Model anlamsal
# eşleştirme yapar — "yaptığım yardımın belgesi" ile "Bağış Makbuzu"yu
# bağlayabilir; dize benzerliği bağlayamaz.
TAM_ESLESME = 1.0


def konudan_kod_bul(
    metin: str, adaylar: list[str], esik: float = TAM_ESLESME
) -> tuple[str | None, float]:
    """Belge metnini aday kodların ÖRNEK KONULARIYLA eşleştirir.

    NEDEN — LLM'e aday listesi vermek SDP tahminini %0'dan %46'ya çıkardı
    ama orada takıldı (5 adaydan seçim, rastgele %20). Katalogda
    `ornek_konular` sütunu duruyordu ve kullanılmıyordu:

        622.02  Belge Talepleri
                "Belge Talebinin Karşılanamaması" | "Suret Talebi" | ...

    Gerçek dosya planlarında bu sütun tam da memurun "bu evrak hangi koda
    girer" diye bakması için vardır. Kullanmak standart arşiv yöntemidir.

    ÖLÇÜLDÜ:
        LLM tahmini (5 adaydan)         : %46
        örnek konu eşleştirme           : %95   (132 belge)
        gerçek gövde metniyle doğrulama : 3/3

    DÜRÜSTLÜK NOTU — RAPORA GİRECEK:
    Veri setinin `konu` alanları bu `ornek_konular` havuzundan seçilerek
    üretildi. Dolayısıyla %95 iyimser bir sayıdır; gerçek dünyada konu
    ifadesi katalogla birebir örtüşmez. Yöntemin kendisi geçerlidir,
    ölçülen oran bu veri setine özgüdür.

    Döner: (kod, benzerlik). Eşik altında (None, benzerlik) döner ve
    çağıran taraf LLM'e devreder.
    """
    from metin import katla

    m = katla(metin)
    if not m or not adaylar:
        return None, 0.0

    k = katalog()
    en_iyi_oran, en_iyi_kod = 0.0, None
    for kod in adaylar:
        kayit = k.get(kod) or {}
        # Kodun ADI da aday: bazı belgeler kod adını doğrudan kullanıyor.
        for ornek in [kayit.get("ad", "")] + kayit.get("ornek_konular", []):
            if not ornek:
                continue
            oran = _en_iyi_pencere(katla(ornek), m)
            if oran > en_iyi_oran:
                en_iyi_oran, en_iyi_kod = oran, kod

    if en_iyi_oran < esik:
        return None, en_iyi_oran
    return en_iyi_kod, en_iyi_oran


def _en_iyi_pencere(aranan: str, metin: str) -> float:
    """Aranan ifadenin metindeki en iyi eşleşme oranı."""
    from difflib import SequenceMatcher

    if not aranan:
        return 0.0
    if aranan in metin:
        return 1.0
    if len(metin) <= len(aranan):
        return SequenceMatcher(None, aranan, metin).ratio()
    adim = max(1, len(aranan) // 3)
    en_iyi = 0.0
    for i in range(0, len(metin) - len(aranan) + 1, adim):
        oran = SequenceMatcher(None, aranan, metin[i:i + len(aranan) + adim]).ratio()
        if oran > en_iyi:
            en_iyi = oran
        if en_iyi >= 0.95:
            break
    return en_iyi


if __name__ == "__main__":
    k = katalog()
    print(f"katalog: {_katalog_yolu()}")
    print(f"{len(k)} kod")
    for ornek in ("215.01", "755.01", "198.02.01", "yok.123"):
        print(f"  {ornek:12s} -> {kod_adi(ornek)}")
