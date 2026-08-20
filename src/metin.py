"""Metin karşılaştırma yardımcıları — OCR hasarına dayanıklı eşleştirme.

TEMEL İLKE: METİN ONARILMAZ, KARŞILAŞTIRMA ESNETİLİR.

OCR taranmış belgede Türkçe işaretleri bozuyor (ölçüldü, ocr_karsilastir.py):

    gerçek   "Fen Bilimleri Enstitüsü Müdürlüğü"
    OCR      "fen bilimleri enstitusu mudurlugu"
    gerçek   "gönderilmiştir"
    OCR      "gönderilmistir"

İki yol vardı:

  A) Metni onarmak — OCR çıktısını modele verip "düzelt" demek.
     REDDEDİLDİ: model olmayan kelime uydurur. Resmî evrakta uydurma,
     kayıptan beterdir; kayıp görünür, uydurma görünmez.

  B) Karşılaştırmayı esnetmek — metne dokunmamak, eşleştirirken iki
     tarafta da işaretleri düşürmek. Hiçbir şey uydurulmaz, hiçbir şey
     silinmez. SEÇİLEN YOL.

Bozuk yazım sisteme girmez: eşleştirme kanonik kayda (birimler.csv,
rules.yaml) yapılır ve çıktıya kanonik yazım yazılır. OCR metni yalnızca
"hangi kayıt bu" sorusunu cevaplamak için kullanılır.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

# Türkçe işaretli harf -> sade karşılığı.
# 'İ' ve 'ı' elle veriliyor: Python'un lower/casefold'u bunları Türkçe
# kurallarına göre çevirmiyor ('İ'.lower() 'i̇' üretir, iki kod noktası).
_KATLAMA = str.maketrans({
    "İ": "i", "I": "i", "ı": "i",
    "Ş": "s", "ş": "s",
    "Ğ": "g", "ğ": "g",
    "Ç": "c", "ç": "c",
    "Ö": "o", "ö": "o",
    "Ü": "u", "ü": "u",
    "Â": "a", "â": "a",
    "Î": "i", "î": "i",
    "Û": "u", "û": "u",
})

# OCR'ın sık karıştırdığı biçimsel çiftler. Yalnızca KARŞILAŞTIRMADA
# uygulanır; metin bunlarla değiştirilmez.
_OCR_KARISIKLIGI = str.maketrans({"1": "i", "l": "i", "0": "o", "|": "i"})


def bosluk_topla(metin: str) -> str:
    return re.sub(r"\s+", " ", metin or "").strip()


def katla(metin: str) -> str:
    """Türkçe işaretleri düşürür, küçük harfe çevirir, boşlukları toplar.

    >>> katla("Fen Bilimleri Enstitüsü Müdürlüğü")
    'fen bilimleri enstitusu mudurlugu'
    >>> katla("MÜDÜRLÜĞÜNE") == katla("mudurlugune")
    True
    """
    metin = (metin or "").translate(_KATLAMA).lower()
    metin = unicodedata.normalize("NFD", metin)
    metin = "".join(k for k in metin if not unicodedata.combining(k))
    return bosluk_topla(metin)


def katla_sert(metin: str) -> str:
    """katla() + OCR'ın sık karıştırdığı rakam/harf çiftleri.

    Yalnızca gevşek eşleştirme gerektiğinde kullanılır; sayı ve tarih gibi
    RAKAM taşıyan alanlarda ASLA kullanılmaz — '1'i 'i' yapmak sayıyı bozar.
    """
    return bosluk_topla(katla(metin).translate(_OCR_KARISIKLIGI))


def benzerlik(a: str, b: str) -> float:
    """İki metnin katlanmış hâlleri arasında 0-1 benzerlik."""
    ka, kb = katla(a), katla(b)
    if not ka or not kb:
        return 0.0
    if ka == kb:
        return 1.0
    return SequenceMatcher(None, ka, kb).ratio()


def icinde_gecer_mi(aranan: str, metin: str, esik: float = 0.80) -> tuple[bool, str]:
    """Aranan ifade metinde (katlanmış hâliyle) yaklaşık geçiyor mu.

    (geciyor_mu, en_benzer_parca) döner. İkinci değer hata ayıklama için:
    kelimenin NEYE dönüştüğünü gösterir.
    """
    a, m = katla(aranan), katla(metin)
    if not a or not m:
        return False, ""
    if a in m:
        return True, a
    n = len(a)
    if len(m) < n:
        return SequenceMatcher(None, a, m).ratio() >= esik, m
    adim = max(1, n // 6)
    en_iyi, parca = 0.0, ""
    for i in range(0, len(m) - n + 1, adim):
        p = m[i:i + n + adim]
        oran = SequenceMatcher(None, a, p).ratio()
        if oran > en_iyi:
            en_iyi, parca = oran, p
        if en_iyi >= esik:
            break
    return en_iyi >= esik, parca


def en_iyi_eslesme(
    metin: str,
    adaylar: list[tuple[str, str, int]],
    esik: float = 0.75,
) -> tuple[str | None, float, str | None]:
    """Metinde geçen en özgül adayı bulur.

    adaylar: (kod, ad, seviye) üçlüleri — birimler.py'nin ürettiği yapı.
    Döner: (kod, oran, eslesen_ad); bulunamazsa (None, 0.0, None).

    ÖZGÜLLÜK — bir muhatap satırında hem kurum hem birim geçer:

        "Yenimahalle Belediye Başkanlığı Fen İşleri Müdürlüğü"

    İkisi de tam eşleşir, birini seçmek gerekiyor.

    ÖLÇÜLDÜ, ilk denemem yanlıştı: "daha uzun ad daha özgüldür" sanmıştım
    ama "Yenimahalle Belediye Başkanlığı" (31) "Fen İşleri Müdürlüğü"nden
    (20) uzun; uzunluk kurumu seçiyor ve isabet %47'de kalıyor.

    Doğru ölçüt HİYERARŞİ SEVİYESİ: seviye 2 (şube/müdürlük) seviye 0
    (kurum) üstünde. Bu ölçütle isabet %90.
    """
    m = katla(metin)
    if not m:
        return None, 0.0, None

    bulunanlar: list[tuple[int, float, int, str, str]] = []
    for kod, ad, seviye in adaylar:
        a = katla(ad)
        if not a:
            continue
        if a in m:
            bulunanlar.append((seviye, 1.0, len(a), kod, ad))
            continue
        oran = SequenceMatcher(None, a, m).ratio()
        if oran >= esik:
            bulunanlar.append((seviye, oran, len(a), kod, ad))

    if not bulunanlar:
        return None, 0.0, None
    _, oran, _, kod, ad = max(bulunanlar)
    return kod, oran, ad
