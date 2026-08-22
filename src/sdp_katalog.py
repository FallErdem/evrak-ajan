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


if __name__ == "__main__":
    k = katalog()
    print(f"katalog: {_katalog_yolu()}")
    print(f"{len(k)} kod")
    for ornek in ("215.01", "755.01", "198.02.01", "yok.123"):
        print(f"  {ornek:12s} -> {kod_adi(ornek)}")
