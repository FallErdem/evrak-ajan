"""Birim tablosu — CSV'den okur, API sözleşmesinin şekline çevirir.

TEK KAYNAK: veri/kurumlar/birimler*.csv
Bu modülün ürettiği JSON elle düzenlenmez; CSV değişirse yeniden üretilir.

Üç alan CSV'de yoktur, burada hesaplanır:

  sdp_kodlari      "210.01;225.02" tek dize  ->  ["210.01", "225.02"]
  kurum            ust_birim_kodu zinciri köke kadar takip edilerek
  hedef_olabilir   yönlendiricinin aday kümesi

Hesabı iki tarafın ayrı ayrı yapması, iki uygulamanın zamanla ayrışması
demektir. Bu yüzden tek yerde yapılıyor: gerçek /api/birimler de,
arayüzün sahte sunucusuna giden JSON da bu fonksiyondan çıkıyor.

Kullanım:
    from birimler import birimleri_yukle, birim_bul, sdp_ile_birim_bul

    for b in birimleri_yukle():
        print(b["kod"], b["ad"])

Sözleşme karşılığı: docs/api_sozlesmesi.md 5.3
"""

from __future__ import annotations

import csv
import json
from functools import lru_cache
from pathlib import Path

# -----------------------------------------------------------------------------
# Yollar
# -----------------------------------------------------------------------------

KOK = Path(__file__).resolve().parent.parent
KURUMLAR_DIZINI = KOK / "veri" / "kurumlar"

# Sıra anlamlıdır: belediye, il MEM, üniversite. Arayüzde bu sırayla listelenir.
CSV_DOSYALARI = ("birimler.csv", "birimler_ilmem.csv", "birimler_gazi.csv")

CIKTI_JSON = KURUMLAR_DIZINI / "birimler.json"


# -----------------------------------------------------------------------------
# Türetme kuralları
# -----------------------------------------------------------------------------

# Hiyerarşi üç kademedir:
#   seviye 0  ->  3 kurum (Yenimahalle Belediyesi, Ankara İl MEM, Gazi Rektörlüğü)
#   seviye 1  ->  5 Belediye Başkan Yardımcılığı
#   seviye 2  ->  27 müdürlük / daire / şube / fakülte
#
# Seviye 1 bir GÖZETİM katmanıdır: başkan yardımcılığına evrak havale edilmez,
# bağlı müdürlüğe edilir. Bu yüzden yönlendiricinin aday kümesi dışındadır.
#
# Kuralı yapısal tutmak önemli: "cevap anahtarında hiç geçmiyor" diye
# çıkarsaydık kendi ölçümümüzü şişirmiş olurduk. Gerekçe idari, istatistiki
# değil. (300 etiket bu kuralı bağımsız olarak doğruluyor — dogrula() bakınız.)
HEDEF_OLAMAYAN_SEVIYE = 1

# Seviye 0 satırları ÇİFTE GÖREVLİDİR: hem kurum hem birim. Ankara İl MEM'e
# 300 belgenin 18'i doğrudan gidiyor. Listeden çıkarılmaz.


def _sayisala(deger: str, varsayilan: int = 0) -> int:
    try:
        return int(str(deger).strip())
    except (TypeError, ValueError):
        return varsayilan


def _kodlari_ayir(ham: str) -> list[str]:
    """'210.01; 225.02 ;' -> ['210.01', '225.02']"""
    if not ham:
        return []
    return [k.strip() for k in ham.split(";") if k.strip()]


def _kok_bul(kod: str, satirlar: dict[str, dict]) -> str:
    """ust_birim_kodu zincirini köke kadar takip eder.

    Döngüye karşı korumalı: bir kod ikinci kez görülürse durur ve o ana
    kadarki en üst kodu döndürür. Veri bozuksa sessizce sonsuz döngüye
    girmektense yanlış ama sonlu bir cevap vermek yeğdir; dogrula() zaten
    yakalar.
    """
    gorulen: set[str] = set()
    su_an = kod
    while True:
        if su_an in gorulen:
            return su_an
        gorulen.add(su_an)
        satir = satirlar.get(su_an)
        if satir is None:
            return su_an
        ust = (satir.get("ust_birim_kodu") or "").strip()
        if not ust:
            return su_an
        su_an = ust


# -----------------------------------------------------------------------------
# Yükleme
# -----------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _ham_satirlar() -> tuple[dict[str, str], ...]:
    """CSV'leri sırayla okur. utf-8-sig: dosyalar BOM taşıyor."""
    satirlar: list[dict[str, str]] = []
    for ad in CSV_DOSYALARI:
        yol = KURUMLAR_DIZINI / ad
        if not yol.exists():
            raise FileNotFoundError(f"Birim dosyası bulunamadı: {yol}")
        with yol.open(encoding="utf-8-sig", newline="") as f:
            satirlar.extend(csv.DictReader(f))
    return tuple(satirlar)


@lru_cache(maxsize=1)
def birimleri_yukle() -> tuple[dict, ...]:
    """35 birimi API sözleşmesinin şeklinde döndürür.

    Sözleşme: docs/api_sozlesmesi.md 5.3
    """
    ham = _ham_satirlar()
    indeks = {s["birim_kodu"]: s for s in ham}

    sonuc: list[dict] = []
    for s in ham:
        kod = s["birim_kodu"]
        seviye = _sayisala(s.get("hiyerarsi_seviyesi"))
        kok_kodu = _kok_bul(kod, indeks)
        kok_satir = indeks.get(kok_kodu, s)

        sonuc.append(
            {
                "kod": kod,
                "ad": s["birim_adi"],
                "kurum": kok_satir["birim_adi"],
                "kurum_kodu": kok_kodu,
                "ust_birim_kodu": (s.get("ust_birim_kodu") or "").strip() or None,
                "seviye": seviye,
                "gorev_alani": (s.get("gorev_alani") or "").strip(),
                "sdp_kodlari": _kodlari_ayir(s.get("sdp_kodlari", "")),
                "vatandas_yogunlugu": (s.get("vatandas_yogunlugu") or "").strip() or None,
                "imza_unvani": (s.get("imza_unvani") or "").strip() or None,
                "detsis_no": (s.get("detsis_no") or "").strip() or None,
                "hedef_olabilir": seviye != HEDEF_OLAMAYAN_SEVIYE,
            }
        )
    return tuple(sonuc)


# -----------------------------------------------------------------------------
# Arama
# -----------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _kod_indeksi() -> dict[str, dict]:
    return {b["kod"]: b for b in birimleri_yukle()}


def birim_bul(kod: str) -> dict | None:
    """Koda göre birim döndürür, yoksa None."""
    return _kod_indeksi().get(kod)


@lru_cache(maxsize=1)
def _sdp_indeksi() -> dict[str, tuple[str, ...]]:
    """SDP kodu -> o koda bakan birim kodları.

    Bir kod birden çok birime düşebilir (ör. 045.02 hem hukuk hem yazı
    işleri). Bu yüzden değer tekil değil, demettir.
    """
    harita: dict[str, list[str]] = {}
    for b in birimleri_yukle():
        for sdp in b["sdp_kodlari"]:
            harita.setdefault(sdp, []).append(b["kod"])
    return {k: tuple(v) for k, v in harita.items()}


def sdp_ile_birim_bul(sdp_kodu: str) -> tuple[str, ...]:
    """SDP kodundan hedef birim(ler)i bulur — yönlendirmenin deterministik hattı.

    SDP kodu, sayının üçüncü bölümünde YAZILIDIR ve okunur, tahmin edilmez.
    Okunabildiğinde hedef birim buradan doğrudan gelir; LLM'e sorulmaz.

    Kod tam eşleşmezse üst kırılıma düşülür: 198.02.01 bulunamazsa 198.02,
    o da yoksa 198 denenir. Dosya planı hiyerarşik olduğu için bu doğrudur.

    Hiçbiri tutmazsa boş demet döner -> yönlendirme LLM'e devredilir.
    """
    if not sdp_kodu:
        return ()
    indeks = _sdp_indeksi()
    parcalar = sdp_kodu.split(".")
    for uzunluk in range(len(parcalar), 0, -1):
        aday = ".".join(parcalar[:uzunluk])
        if aday in indeks:
            return indeks[aday]
    return ()


def hedef_olabilecekler() -> tuple[dict, ...]:
    """Yönlendiricinin aday kümesi — 30 birim."""
    return tuple(b for b in birimleri_yukle() if b["hedef_olabilir"])


# -----------------------------------------------------------------------------
# Doğrulama ve üretim
# -----------------------------------------------------------------------------


def dogrula() -> list[str]:
    """Yapısal tutarlılık. Sorun listesi döner; boş liste = temiz."""
    sorunlar: list[str] = []
    birimler = birimleri_yukle()
    kodlar = {b["kod"] for b in birimler}

    if len(kodlar) != len(birimler):
        sorunlar.append("Yinelenen birim_kodu var")

    for b in birimler:
        if b["ust_birim_kodu"] and b["ust_birim_kodu"] not in kodlar:
            sorunlar.append(f"{b['kod']}: üst birim {b['ust_birim_kodu']} tabloda yok")
        if b["kurum_kodu"] not in kodlar:
            sorunlar.append(f"{b['kod']}: kök {b['kurum_kodu']} tabloda yok")
        if b["seviye"] == 0 and b["ust_birim_kodu"]:
            sorunlar.append(f"{b['kod']}: seviye 0 ama üst birimi var")
        if b["hedef_olabilir"] and not b["gorev_alani"]:
            sorunlar.append(f"{b['kod']}: hedef olabilir ama görev alanı boş")
        if b["hedef_olabilir"] and not b["sdp_kodlari"]:
            sorunlar.append(f"{b['kod']}: hedef olabilir ama SDP kodu yok")
        if not b["imza_unvani"]:
            sorunlar.append(f"{b['kod']}: imza unvanı boş")

    return sorunlar


def json_yaz(yol: Path | None = None) -> Path:
    """Sözleşme şeklindeki JSON'u üretir.

    Bu dosya ELLE DÜZENLENMEZ. Kaynak CSV'dir; değişiklik CSV'de yapılır ve
    bu fonksiyon yeniden koşturulur.
    """
    hedef = yol or CIKTI_JSON
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(
        json.dumps(list(birimleri_yukle()), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return hedef


if __name__ == "__main__":
    birimler = birimleri_yukle()
    print(f"{len(birimler)} birim yüklendi")

    seviyeler: dict[int, int] = {}
    for b in birimler:
        seviyeler[b["seviye"]] = seviyeler.get(b["seviye"], 0) + 1
    for sv in sorted(seviyeler):
        print(f"  seviye {sv}: {seviyeler[sv]}")
    print(f"  hedef olabilir: {len(hedef_olabilecekler())}")
    print(f"  farklı SDP kodu: {len(_sdp_indeksi())}")

    sorunlar = dogrula()
    if sorunlar:
        print(f"\n{len(sorunlar)} SORUN:")
        for s in sorunlar:
            print(f"  ✗ {s}")
        raise SystemExit(1)
    print("\n  ✓ yapısal doğrulama temiz")

    yazilan = json_yaz()
    print(f"  ✓ yazıldı: {yazilan}")
