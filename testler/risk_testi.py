#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
risk_testi.py — PARÇA 1 / ADIM 3

Amaç: elimizdeki donanımda hangi modelin bu proje için kullanılabilir olduğunu
ölçmek. Geliştirme değil, risk testi. Çıktısı bir tablodur; o tablo Parça 4'teki
model kararının ve Parça 9'daki demo kararının dayanağı olacak.

Ölçülen yedi ölçüt:
  A   Model yanıt veriyor mu
  B   Türkçe resmî belgeyi anlıyor mu (serbest metin)
  C1  Geçerli JSON üretiyor mu
  C2  Doğru enum değerini seçiyor mu
  C3  Emin olmadığında bunu söyleyebiliyor mu (belirsizlik farkındalığı)
  C4  Türkçe karakterler bozulmuyor mu
  D   Üretim hızı ve ilk metin gecikmesi (düşünme açık/kapalı ayrı)

Ek olarak, bedava geldiği için ölçülenler:
  - Tutarlılık: aynı belgeye verilen N cevap birbiriyle aynı mı
  - Yanlış cevaplardaki ortalama güven: güven eşiğiyle ayıklama yapılabilir mi
  - Uçtan uca süre tahmini (ADIM 4 hesabı, otomatik)

Kullanım:
    python testler/risk_testi.py --kendi-testi     # Ollama'ya dokunmadan denetim
    python testler/risk_testi.py --hizli           # kısa duman testi
    python testler/risk_testi.py                   # tam koşu

Not: Türkçe metin yardımcıları (tr_kucult, sadelestir, bozuk_turkce_mi) ADIM 5'te
src/turkce.py dosyasına taşınacak. Şimdilik betik kendi kendine yetsin diye burada.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover
    print("HATA: 'requests' kurulu değil. Sanal ortamı etkinleştirip kurun:")
    print("  pip install requests")
    sys.exit(1)


# =============================================================================
# AYARLAR
# =============================================================================

OLLAMA = "http://localhost:11434"

# Ollama modeli 5 dakika sonra bellekten atıyor. Uzun koşunun ortasında bu olursa
# tek bir istek anormal yavaş görünür ve medyan bozulur. Her istekte gönderiyoruz.
KEEP_ALIVE = "30m"

# Bağlam uzunluğu bütün ölçümlerde aynı kalmalı, yoksa iki makinenin ya da iki
# modelin sayıları karşılaştırılamaz. Değiştirirseniz karar_kaydi.md'ye yazın.
NUM_CTX = 4096

# 0 olsa tekrarlar birbirinin kopyası olur ve tutarlılık ölçülemez.
SICAKLIK = 0.3

ZAMAN_ASIMI = 900  # saniye; ilk yükleme yavaş diskte uzun sürebiliyor

MODELLER_VARSAYILAN = [
    "alibayram/kumru",
    "qwen3.5:9b",
    "alibayram/turkish-gemma-9b-v0.1",
]

# Bütün modellere aynı sistem istemi gidiyor — karşılaştırma adil olsun diye.
# Modelin kendi Modelfile'ındaki SYSTEM satırını geçersiz kılar.
SISTEM_ISTEMI = (
    "Sen bir Türk kamu kurumunun evrak kayıt biriminde çalışan uzmandır. "
    "Resmî yazışma kurallarını bilirsin ve gelen belgeleri türlerine göre "
    "sınıflandırırsın. Yanıtlarını Türkçe verirsin."
)

BELGE_TURLERI = [
    "ust_yazi",
    "cevap_yazisi",
    "bilgilendirme_yazisi",
    "vatandas_dilekcesi",
    "duyuru",
    "bilinmiyor",
]

SEMA = {
    "type": "object",
    "properties": {
        "belge_turu": {"type": "string", "enum": BELGE_TURLERI},
        "guven": {"type": "number", "minimum": 0, "maximum": 1},
        "gerekce": {"type": "string", "maxLength": 300},
    },
    "required": ["belge_turu", "guven", "gerekce"],
}

ESIKLER = {
    "B_dogru_oran": 0.80,   # 5 belgede en az 4
    "C1_gecerli": 1.00,     # 20/20
    "C2_dogru": 0.85,       # 20'de en az 17
    "C3_belirsizlik": 0.80,
    "C4_turkce": 1.00,
}

# ADIM 4 hesabının varsayımları
UCTAN_UCA_CAGRI = 8
CAGRI_BASINA_TOKEN = 200


# =============================================================================
# TÜRKÇE METİN YARDIMCILARI
# =============================================================================

_TR_BUYUK_ESLEME = str.maketrans({"I": "ı", "İ": "i"})

_KATLAMA = str.maketrans(
    {
        "ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
        "â": "a", "î": "i", "û": "u", "Â": "a", "Î": "i", "Û": "u",
    }
)

# Latin-5 / Windows-1254 karışmasının klasik izleri ve UTF-8'in cp1252 olarak
# okunmasından doğan diziler.
_MOJIBAKE_IZLERI = (
    "\ufffd",           # replacement character
    "Ã", "Å", "Ä",      # UTF-8 baytları cp1252 olarak okunmuş
    "þ", "ð", "ý",      # Latin-5'te ş, ğ, ı yerine geçen harfler
    "Þ", "Ð", "Ý",
)


def tr_kucult(metin: str) -> str:
    """Türkçe uyumlu küçük harfe çevirme.

    Python'un .lower() metodu 'İ' harfini 'i' + birleşen nokta olarak
    çözümlüyor; bu, sonraki karşılaştırmaları sessizce bozuyor.
    """
    return metin.translate(_TR_BUYUK_ESLEME).lower()


def sadelestir(metin: str) -> str:
    """Anahtar kelime eşleştirmesi için: küçült, diakritikleri düzleştir.

    Yalnızca puanlamada kullanılır — modelin 'dilekçe' yerine 'dilekce'
    yazması puanı düşürmesin diye.
    """
    return " ".join(tr_kucult(metin).translate(_KATLAMA).split())


def bozuk_turkce_mi(metin: str) -> tuple[bool, str]:
    """Metinde karakter bozulması var mı. (bozuk_mu, sebep) döner."""
    if not metin:
        return False, ""
    for iz in _MOJIBAKE_IZLERI:
        if iz in metin:
            return True, f"mojibake izi: {iz!r}"
    # Ayrık diakritik: 'ş' harfi 's' + birleşen çengel olarak gelmiş olabilir.
    if unicodedata.normalize("NFC", metin) != metin:
        return True, "ayrık diakritik (NFC değil)"
    return False, ""


def turkce_gorunuyor_mu(metin: str) -> bool:
    """Kaba bir dil sezgisi: metin Türkçe mi, yoksa model İngilizce'ye mi kaçtı."""
    if not metin:
        return False
    kucuk = tr_kucult(metin)
    if any(h in kucuk for h in "çğıöşü"):
        return True
    isaretler = (
        " bir ", " ve ", " bu ", " ile ", " için ", " olan ",
        "belge", "yazı", "kurum", "dilekçe", "dır", "dir",
    )
    return sum(1 for i in isaretler if i in kucuk) >= 2


# =============================================================================
# OLLAMA İSTEMCİSİ
# =============================================================================

@dataclass
class Yanit:
    """Tek bir model çağrısının sonucu ve zamanlaması."""
    metin: str = ""
    dusunce: str = ""
    ilk_parca_ms: float | None = None   # herhangi bir parça geldi
    ilk_metin_ms: float | None = None   # ilk görünür metin parçası geldi
    duvar_saati_ms: float = 0.0
    uretilen_token: int = 0
    uretim_ns: int = 0
    istem_token: int = 0
    istem_ns: int = 0
    yukleme_ns: int = 0
    hata: str | None = None

    @property
    def basarili(self) -> bool:
        return self.hata is None and bool(self.metin.strip())

    @property
    def token_sn(self) -> float | None:
        if self.uretim_ns <= 0 or self.uretilen_token <= 0:
            return None
        return self.uretilen_token / (self.uretim_ns / 1e9)


def _istek(yol: str, govde: dict | None = None, yontem: str = "POST") -> Any:
    url = f"{OLLAMA}{yol}"
    try:
        if yontem == "GET":
            r = requests.get(url, timeout=30)
        else:
            r = requests.post(url, json=govde or {}, timeout=60)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"_hata": str(e)}


def ollama_ayakta_mi() -> tuple[bool, str]:
    c = _istek("/api/version", yontem="GET")
    if "_hata" in c:
        return False, c["_hata"]
    return True, c.get("version", "bilinmiyor")


def kurulu_modeller() -> list[str]:
    c = _istek("/api/tags", yontem="GET")
    if "_hata" in c:
        return []
    return [m.get("name", "") for m in c.get("models", [])]


def model_yetenekleri(model: str) -> list[str]:
    c = _istek("/api/show", {"model": model})
    if "_hata" in c:
        c = _istek("/api/show", {"name": model})  # eski sürümler
    if "_hata" in c:
        return []
    return c.get("capabilities", []) or []


def dusunebilir_mi(model: str) -> bool:
    return "thinking" in model_yetenekleri(model)


def gpu_orani(model: str) -> float | None:
    """Modelin ne kadarı VRAM'de. 1.0 = tamamı GPU'da.

    Model yüklü değilse None döner. 1.0'ın altındaysa katmanlar CPU'ya taşmış
    demektir ve o modelin hız ölçümü güvenilmez.
    """
    c = _istek("/api/ps", yontem="GET")
    if "_hata" in c:
        return None
    for m in c.get("models", []):
        if model in (m.get("name"), m.get("model")):
            boyut = m.get("size", 0)
            vram = m.get("size_vram", 0)
            if boyut > 0:
                return round(vram / boyut, 4)
    return None


def sohbet(
    model: str,
    istem: str,
    *,
    sema: dict | None = None,
    dusun: bool | None = None,
    sicaklik: float = SICAKLIK,
    num_ctx: int | None = None,
    num_predict: int | None = None,
    sistem: str | None = SISTEM_ISTEMI,
) -> Yanit:
    """Ollama /api/chat çağrısı, akışlı.

    Akış kullanmamızın tek sebebi zamanlama: ilk token gecikmesini duvar saatiyle
    ölçmek istiyoruz. stream=False ile bu sayı elde edilemiyor.
    """
    mesajlar: list[dict] = []
    if sistem:
        mesajlar.append({"role": "system", "content": sistem})
    mesajlar.append({"role": "user", "content": istem})

    # Varsayılanı tanım anında değil çağrı anında okuyoruz; --baglam sonradan
    # NUM_CTX'i değiştirdiğinde ölçümler yeni değeri kullansın.
    if num_ctx is None:
        num_ctx = NUM_CTX

    secenekler: dict[str, Any] = {"temperature": sicaklik, "num_ctx": num_ctx}
    if num_predict is not None:
        secenekler["num_predict"] = num_predict

    govde: dict[str, Any] = {
        "model": model,
        "messages": mesajlar,
        "options": secenekler,
        "keep_alive": KEEP_ALIVE,
        "stream": True,
    }
    if sema is not None:
        govde["format"] = sema
    if dusun is not None:
        govde["think"] = dusun

    y = Yanit()
    t0 = time.perf_counter()
    try:
        r = requests.post(
            f"{OLLAMA}/api/chat", json=govde, timeout=ZAMAN_ASIMI, stream=True
        )
        if r.status_code >= 400:
            y.hata = f"HTTP {r.status_code}: {r.text[:300]}"
            return y

        metin_parcalari: list[str] = []
        dusunce_parcalari: list[str] = []

        for satir in r.iter_lines():
            if not satir:
                continue
            try:
                parca = json.loads(satir.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                y.hata = f"akış çözümlenemedi: {e}"
                return y

            simdi = (time.perf_counter() - t0) * 1000
            if y.ilk_parca_ms is None:
                y.ilk_parca_ms = simdi

            mesaj = parca.get("message") or {}
            icerik = mesaj.get("content") or ""
            dusunce = mesaj.get("thinking") or ""

            if icerik:
                if y.ilk_metin_ms is None:
                    y.ilk_metin_ms = simdi
                metin_parcalari.append(icerik)
            if dusunce:
                dusunce_parcalari.append(dusunce)

            if parca.get("done"):
                y.uretilen_token = parca.get("eval_count", 0) or 0
                y.uretim_ns = parca.get("eval_duration", 0) or 0
                y.istem_token = parca.get("prompt_eval_count", 0) or 0
                y.istem_ns = parca.get("prompt_eval_duration", 0) or 0
                y.yukleme_ns = parca.get("load_duration", 0) or 0

        y.metin = "".join(metin_parcalari)
        y.dusunce = "".join(dusunce_parcalari)
        y.duvar_saati_ms = (time.perf_counter() - t0) * 1000
        return y

    except requests.exceptions.Timeout:
        y.hata = f"zaman aşımı ({ZAMAN_ASIMI} sn)"
        return y
    except Exception as e:
        y.hata = f"{type(e).__name__}: {e}"
        return y


# =============================================================================
# VERİ YÜKLEME
# =============================================================================

@dataclass
class Belge:
    id: str
    dosya: str
    metin: str
    belge_turu: str
    alternatif_kabul: list[str] = field(default_factory=list)
    b_dahil: bool = True
    c3_dahil: bool = False
    b_gecme_grup: int = 2
    b_kavram_gruplari: list[list[str]] = field(default_factory=list)
    b_yasakli_kavramlar: list[str] = field(default_factory=list)


def belgeleri_yukle(dizin: Path) -> list[Belge]:
    anahtar_yolu = dizin / "cevap_anahtari.json"
    if not anahtar_yolu.exists():
        raise FileNotFoundError(f"Cevap anahtarı bulunamadı: {anahtar_yolu}")

    anahtar = json.loads(anahtar_yolu.read_text(encoding="utf-8"))
    belgeler: list[Belge] = []

    for kayit in anahtar["belgeler"]:
        yol = dizin / kayit["dosya"]
        if not yol.exists():
            raise FileNotFoundError(f"Belge dosyası eksik: {yol}")
        tur = kayit["belge_turu"]
        if tur not in BELGE_TURLERI:
            raise ValueError(f"{kayit['id']}: tanımsız belge türü {tur!r}")
        for alt in kayit.get("alternatif_kabul", []):
            if alt not in BELGE_TURLERI:
                raise ValueError(f"{kayit['id']}: tanımsız alternatif {alt!r}")

        belgeler.append(
            Belge(
                id=kayit["id"],
                dosya=kayit["dosya"],
                metin=yol.read_text(encoding="utf-8"),
                belge_turu=tur,
                alternatif_kabul=kayit.get("alternatif_kabul", []),
                b_dahil=kayit.get("b_dahil", True),
                c3_dahil=kayit.get("c3_dahil", False),
                b_gecme_grup=kayit.get("b_gecme_grup", 2),
                b_kavram_gruplari=kayit.get("b_kavram_gruplari", []),
                b_yasakli_kavramlar=kayit.get("b_yasakli_kavramlar", []),
            )
        )
    return belgeler


# =============================================================================
# TESTLER
# =============================================================================

def test_a(model: str) -> dict:
    """Model yanıt veriyor mu, hangi dilde."""
    y = sohbet(
        model,
        "Resmî bir yazının başlık bölümünde hangi bilgiler bulunur? "
        "İki cümleyle açıkla.",
        dusun=False if dusunebilir_mi(model) else None,
        num_predict=200,
    )
    return {
        "gecti": y.basarili,
        "turkce": turkce_gorunuyor_mu(y.metin),
        "hata": y.hata,
        "yanit": y.metin.strip()[:400],
    }


def _b_puanla(belge: Belge, yanit: str) -> dict:
    """Serbest metin cevabı kavram gruplarıyla puanla."""
    sade = sadelestir(yanit)

    yasakli_bulunan = [
        k for k in belge.b_yasakli_kavramlar if sadelestir(k) in sade
    ]
    vurulan = 0
    grup_detay = []
    for grup in belge.b_kavram_gruplari:
        vuran = [k for k in grup if sadelestir(k) in sade]
        if vuran:
            vurulan += 1
        grup_detay.append({"grup": grup, "vuran": vuran})

    gecti = vurulan >= belge.b_gecme_grup and not yasakli_bulunan
    return {
        "gecti": gecti,
        "vurulan_grup": vurulan,
        "gereken_grup": belge.b_gecme_grup,
        "yasakli_bulunan": yasakli_bulunan,
        "grup_detay": grup_detay,
    }


def test_b(model: str, belgeler: list[Belge]) -> dict:
    """Türkçe resmî belgeyi anlıyor mu — serbest metin, kavram grubu puanlaması."""
    dusun = False if dusunebilir_mi(model) else None
    kayitlar = []
    for belge in [b for b in belgeler if b.b_dahil]:
        istem = (
            "Aşağıdaki metin ne tür bir resmî belgedir? Tek cümleyle açıkla.\n\n"
            "--- BELGE BAŞLANGICI ---\n"
            f"{belge.metin}\n"
            "--- BELGE SONU ---"
        )
        y = sohbet(model, istem, dusun=dusun, num_predict=250)
        if not y.basarili:
            kayitlar.append(
                {"belge": belge.id, "gecti": False, "hata": y.hata, "yanit": ""}
            )
            continue
        puan = _b_puanla(belge, y.metin)
        puan.update(
            {
                "belge": belge.id,
                "beklenen_tur": belge.belge_turu,
                "yanit": y.metin.strip(),
                "turkce": turkce_gorunuyor_mu(y.metin),
            }
        )
        kayitlar.append(puan)

    toplam = len(kayitlar)
    dogru = sum(1 for k in kayitlar if k.get("gecti"))
    return {
        "dogru": dogru,
        "toplam": toplam,
        "oran": (dogru / toplam) if toplam else 0.0,
        "esik": ESIKLER["B_dogru_oran"],
        "gecti": (dogru / toplam) >= ESIKLER["B_dogru_oran"] if toplam else False,
        "kayitlar": kayitlar,
    }


def _sema_istemi(metin: str) -> str:
    return (
        "Aşağıdaki belgeyi sınıflandır. Belgenin türünden emin değilsen "
        "belge_turu alanına 'bilinmiyor' yaz ve guven değerini düşük ver.\n\n"
        "--- BELGE BAŞLANGICI ---\n"
        f"{metin}\n"
        "--- BELGE SONU ---"
    )


def test_c(model: str, belgeler: list[Belge], tekrar: int) -> dict:
    """Şemalı çıktı: geçerlilik, doğruluk, Türkçe bütünlüğü, tutarlılık."""
    dusun = False if dusunebilir_mi(model) else None
    hedefler = [b for b in belgeler if b.b_dahil]

    kayitlar: list[dict] = []
    belge_bazli: dict[str, list[str | None]] = {b.id: [] for b in hedefler}

    for belge in hedefler:
        for tur_no in range(tekrar):
            y = sohbet(
                model,
                _sema_istemi(belge.metin),
                sema=SEMA,
                dusun=dusun,
                num_predict=400,
            )
            kayit: dict[str, Any] = {
                "belge": belge.id,
                "tur": tur_no + 1,
                "beklenen": belge.belge_turu,
                "hata": y.hata,
            }

            if not y.basarili:
                kayit.update(
                    {"gecerli_json": False, "sema_uyumlu": False,
                     "dogru": False, "turkce_saglam": False, "secilen": None}
                )
                kayitlar.append(kayit)
                belge_bazli[belge.id].append(None)
                continue

            try:
                cikti = json.loads(y.metin)
                kayit["gecerli_json"] = True
            except json.JSONDecodeError as e:
                kayit.update(
                    {"gecerli_json": False, "sema_uyumlu": False, "dogru": False,
                     "turkce_saglam": False, "secilen": None,
                     "cozumleme_hatasi": str(e), "ham": y.metin[:300]}
                )
                kayitlar.append(kayit)
                belge_bazli[belge.id].append(None)
                continue

            secilen = cikti.get("belge_turu")
            guven = cikti.get("guven")
            gerekce = cikti.get("gerekce") or ""

            alanlar_tam = all(k in cikti for k in SEMA["required"])
            enum_ici = secilen in BELGE_TURLERI
            guven_gecerli = isinstance(guven, (int, float)) and 0 <= guven <= 1
            kayit["sema_uyumlu"] = bool(alanlar_tam and enum_ici and guven_gecerli)

            kabul = [belge.belge_turu, *belge.alternatif_kabul]
            kayit["dogru"] = secilen in kabul
            kayit["tam_isabet"] = secilen == belge.belge_turu

            bozuk, sebep = bozuk_turkce_mi(gerekce)
            kayit["turkce_saglam"] = not bozuk
            kayit["turkce_sebep"] = sebep
            kayit["gerekce_turkce"] = turkce_gorunuyor_mu(gerekce)

            kayit.update({"secilen": secilen, "guven": guven,
                          "gerekce": gerekce[:250]})
            kayitlar.append(kayit)
            belge_bazli[belge.id].append(secilen)

    n = len(kayitlar)

    def oran(anahtar: str) -> float:
        return (sum(1 for k in kayitlar if k.get(anahtar)) / n) if n else 0.0

    # Tutarlılık: aynı belgeye verilen cevaplar birbiriyle aynı mı
    tutarli_belge = sum(
        1 for cevaplar in belge_bazli.values()
        if cevaplar and len(set(cevaplar)) == 1
    )

    # Yanlış cevaplarda ortalama güven — güven eşiğiyle ayıklama yapılabilir mi
    yanlis_guvenler = [
        k["guven"] for k in kayitlar
        if k.get("gecerli_json") and not k.get("dogru")
        and isinstance(k.get("guven"), (int, float))
    ]
    dogru_guvenler = [
        k["guven"] for k in kayitlar
        if k.get("dogru") and isinstance(k.get("guven"), (int, float))
    ]

    c1 = oran("gecerli_json")
    c2 = oran("dogru")
    c4 = oran("turkce_saglam")

    return {
        "toplam_deneme": n,
        "C1_gecerli_json": c1,
        "C1_gecti": c1 >= ESIKLER["C1_gecerli"],
        "C2_dogru": c2,
        "C2_gecti": c2 >= ESIKLER["C2_dogru"],
        "C2_tam_isabet": oran("tam_isabet"),
        "sema_uyumlu": oran("sema_uyumlu"),
        "C4_turkce_saglam": c4,
        "C4_gecti": c4 >= ESIKLER["C4_turkce"],
        "gerekce_turkce_orani": oran("gerekce_turkce"),
        "tutarli_belge": tutarli_belge,
        "belge_sayisi": len(hedefler),
        "yanlisda_ortalama_guven": (
            round(statistics.fmean(yanlis_guvenler), 3) if yanlis_guvenler else None
        ),
        "dogruda_ortalama_guven": (
            round(statistics.fmean(dogru_guvenler), 3) if dogru_guvenler else None
        ),
        "kayitlar": kayitlar,
    }


def test_c3(model: str, belgeler: list[Belge], tekrar: int) -> dict:
    """Belirsizlik farkındalığı: bozuk belgede 'bilinmiyor' ya da düşük güven."""
    hedefler = [b for b in belgeler if b.c3_dahil]
    if not hedefler:
        return {"atlandi": True, "sebep": "c3_dahil işaretli belge yok"}

    dusun = False if dusunebilir_mi(model) else None
    kayitlar = []
    for belge in hedefler:
        for tur_no in range(tekrar):
            y = sohbet(
                model, _sema_istemi(belge.metin), sema=SEMA,
                dusun=dusun, num_predict=400,
            )
            kayit: dict[str, Any] = {"belge": belge.id, "tur": tur_no + 1,
                                     "hata": y.hata}
            if not y.basarili:
                kayit["gecti"] = False
                kayitlar.append(kayit)
                continue
            try:
                cikti = json.loads(y.metin)
            except json.JSONDecodeError:
                kayit.update({"gecti": False, "ham": y.metin[:300]})
                kayitlar.append(kayit)
                continue

            secilen = cikti.get("belge_turu")
            guven = cikti.get("guven")
            dusuk_guven = isinstance(guven, (int, float)) and guven < 0.5
            kayit.update(
                {
                    "secilen": secilen,
                    "guven": guven,
                    "bilinmiyor_dedi": secilen == "bilinmiyor",
                    "dusuk_guven": dusuk_guven,
                    "gecti": secilen == "bilinmiyor" or dusuk_guven,
                    "gerekce": (cikti.get("gerekce") or "")[:250],
                }
            )
            kayitlar.append(kayit)

    n = len(kayitlar)
    gecen = sum(1 for k in kayitlar if k.get("gecti"))
    oran = (gecen / n) if n else 0.0
    return {
        "atlandi": False,
        "gecen": gecen,
        "toplam": n,
        "oran": oran,
        "esik": ESIKLER["C3_belirsizlik"],
        "gecti": oran >= ESIKLER["C3_belirsizlik"],
        "kayitlar": kayitlar,
    }


def test_d(model: str, belge: Belge, tekrar: int) -> dict:
    """Hız: üretim hızı ve ilk metin gecikmesi, düşünme açık ve kapalı."""
    istem = (
        "Aşağıdaki belgeyi 150-200 kelimeyle özetle. Özet, belgenin kimden "
        "kime gönderildiğini, ne talep edildiğini ve varsa süreleri içermelidir.\n\n"
        "--- BELGE BAŞLANGICI ---\n"
        f"{belge.metin}\n"
        "--- BELGE SONU ---"
    )

    dusunur = dusunebilir_mi(model)
    kipler: list[tuple[str, bool | None]] = [("dusunme_kapali", False if dusunur else None)]
    if dusunur:
        kipler.append(("dusunme_acik", True))

    sonuc: dict[str, Any] = {"dusunme_yetenegi": dusunur, "kipler": {}}

    for kip_adi, dusun in kipler:
        olcumler = []
        for _ in range(tekrar):
            y = sohbet(model, istem, dusun=dusun, num_predict=600)
            if not y.basarili:
                olcumler.append({"hata": y.hata})
                continue
            olcumler.append(
                {
                    "token_sn": y.token_sn,
                    "uretilen_token": y.uretilen_token,
                    "dusunce_karakter": len(y.dusunce),
                    "ilk_parca_ms": y.ilk_parca_ms,
                    "ilk_metin_ms": y.ilk_metin_ms,
                    "duvar_saati_ms": y.duvar_saati_ms,
                    "istem_token": y.istem_token,
                }
            )

        gecerli = [o for o in olcumler if o.get("token_sn")]
        if gecerli:
            med_tok = statistics.median(o["token_sn"] for o in gecerli)
            ilk_metinler = [
                o["ilk_metin_ms"] for o in gecerli if o.get("ilk_metin_ms")
            ]
            med_ilk_metin = statistics.median(ilk_metinler) if ilk_metinler else 0.0
            med_toplam = statistics.median(o["duvar_saati_ms"] for o in gecerli)
            med_token = statistics.median(o["uretilen_token"] for o in gecerli)
            # İki tahmin: ADIM 4'ün varsayımıyla (200 token/çağrı) ve gerçekten
            # ölçülen token sayısıyla. Düşünme açıkken ikisi çok ayrışır —
            # ayrışmanın büyüklüğü düşünmenin demo maliyetidir.
            tahmin_sn = (UCTAN_UCA_CAGRI * CAGRI_BASINA_TOKEN) / med_tok
            olculen_tahmin_sn = (UCTAN_UCA_CAGRI * med_token) / med_tok
            sonuc["kipler"][kip_adi] = {
                "token_sn": round(med_tok, 1),
                "ilk_metin_ms": round(med_ilk_metin, 0),
                "toplam_ms": round(med_toplam, 0),
                "uretilen_token_medyan": med_token,
                "uctan_uca_olculen_sn": round(olculen_tahmin_sn, 1),
                "dusunce_karakter_medyan": statistics.median(
                    o["dusunce_karakter"] for o in gecerli
                ),
                "uctan_uca_tahmin_sn": round(tahmin_sn, 1),
                "karar": _hiz_karari(med_tok),
                "olcumler": olcumler,
            }
        else:
            sonuc["kipler"][kip_adi] = {"hata": "geçerli ölçüm yok",
                                        "olcumler": olcumler}
    return sonuc


def _hiz_karari(token_sn: float) -> str:
    if token_sn >= 80:
        return "Yerel yeter, GPU gerekmez"
    if token_sn >= 40:
        return "Sınırda — çıktı kısaltarak kurtarılabilir"
    if token_sn >= 15:
        return "Demo için kiralık GPU gerekir"
    return "Geliştirme de zorlaşır, kiralama öne çekilmeli"


# =============================================================================
# KOŞU VE RAPOR
# =============================================================================

def modeli_kosturt(model: str, belgeler: list[Belge], args) -> dict:
    print(f"\n{'=' * 70}\nMODEL: {model}\n{'=' * 70}")
    sonuc: dict[str, Any] = {
        "model": model,
        "yetenekler": model_yetenekleri(model),
        "dusunme_yetenegi": dusunebilir_mi(model),
    }

    if "a" in args.testler:
        print("  Test A — yanıt veriyor mu ...", end="", flush=True)
        t0 = time.perf_counter()
        sonuc["A"] = test_a(model)
        print(f" {'GEÇTİ' if sonuc['A']['gecti'] else 'GEÇMEDİ'}"
              f" ({time.perf_counter() - t0:.1f} sn)")
        if not sonuc["A"]["gecti"]:
            print(f"    hata: {sonuc['A']['hata']}")
            sonuc["not"] = "Test A geçmedi, sonraki testler atlandı."
            return sonuc

    # GPU kontrolü: model artık yüklü olduğu için burada anlamlı
    oran = gpu_orani(model)
    sonuc["gpu_orani"] = oran
    if oran is None:
        print("  ! GPU oranı okunamadı (model bellekten atılmış olabilir)")
    elif oran < 0.99:
        print(f"  ! UYARI: modelin yalnızca %{oran * 100:.0f}'ı GPU'da. "
              "Hız ölçümleri güvenilmez.")
    else:
        print("  GPU: %100 (tamamı VRAM'de)")

    if "b" in args.testler:
        print("  Test B — Türkçe resmî belge anlama ...", end="", flush=True)
        t0 = time.perf_counter()
        sonuc["B"] = test_b(model, belgeler)
        b = sonuc["B"]
        print(f" {b['dogru']}/{b['toplam']} ({time.perf_counter() - t0:.1f} sn)")

    if "c" in args.testler:
        print(f"  Test C — şemalı çıktı ({args.tekrar} tur × 5 belge) ...",
              end="", flush=True)
        t0 = time.perf_counter()
        sonuc["C"] = test_c(model, belgeler, args.tekrar)
        c = sonuc["C"]
        print(f" JSON %{c['C1_gecerli_json'] * 100:.0f} · "
              f"doğru %{c['C2_dogru'] * 100:.0f} "
              f"({time.perf_counter() - t0:.1f} sn)")

        print("  Test C3 — belirsizlik farkındalığı ...", end="", flush=True)
        t0 = time.perf_counter()
        sonuc["C3"] = test_c3(model, belgeler, args.c3_tekrar)
        c3 = sonuc["C3"]
        if c3.get("atlandi"):
            print(" atlandı")
        else:
            print(f" {c3['gecen']}/{c3['toplam']} "
                  f"({time.perf_counter() - t0:.1f} sn)")

    if "d" in args.testler:
        hedef = next((b for b in belgeler if b.b_dahil), belgeler[0])
        print(f"  Test D — hız ({args.d_tekrar} tekrar) ...", end="", flush=True)
        t0 = time.perf_counter()
        sonuc["D"] = test_d(model, hedef, args.d_tekrar)
        kapali = sonuc["D"]["kipler"].get("dusunme_kapali", {})
        if kapali.get("token_sn"):
            print(f" {kapali['token_sn']} tok/s "
                  f"({time.perf_counter() - t0:.1f} sn)")
        else:
            print(" ölçülemedi")

    return sonuc


def rapor_yaz(rapor: dict, cikti_dizini: Path) -> tuple[Path, Path]:
    cikti_dizini.mkdir(parents=True, exist_ok=True)
    damga = datetime.now().strftime("%Y%m%d_%H%M")

    json_yolu = cikti_dizini / f"risk_testi_{damga}.json"
    json_yolu.write_text(
        json.dumps(rapor, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md_yolu = cikti_dizini / f"risk_testi_{damga}.md"
    md_yolu.write_text(markdown_rapor(rapor), encoding="utf-8")
    return md_yolu, json_yolu


def _y(deger: bool | None) -> str:
    if deger is None:
        return "—"
    return "✓" if deger else "✗"


def markdown_rapor(rapor: dict) -> str:
    o = rapor["ortam"]
    s = [
        "# Risk Testi Raporu — PARÇA 1 / ADIM 3",
        "",
        f"**Tarih:** {o['tarih']}  ",
        f"**Ollama:** {o['ollama_surumu']}  ",
        f"**Bağlam:** {o['num_ctx']} · **Sıcaklık:** {o['sicaklik']} · "
        f"**keep_alive:** {o['keep_alive']}  ",
        f"**Makine notu:** {o.get('makine', '(belirtilmedi — --makine ile geçin)')}",
        "",
        "> Ölçüm koşulları yeniden üretilebilirlik için kaydedilmiştir "
        "(şartname madde 13.1). Ham yanıtların tamamı eşlik eden JSON dosyasındadır.",
        "",
        "## Kalite",
        "",
        "| Model | A yanıt | B anlama | C1 JSON | C2 doğru | C3 belirsizlik "
        "| C4 Türkçe | Tutarlılık | Yanlışta güven |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    for m in rapor["modeller"]:
        ad = m["model"]
        a = m.get("A", {})
        b = m.get("B", {})
        c = m.get("C", {})
        c3 = m.get("C3", {})

        # Test A hiç koşulmadıysa (--testler b,c) modeli başarısız göstermeyelim.
        if not a.get("gecti", True):
            s.append(f"| `{ad}` | ✗ | — | — | — | — | — | — | — |")
            continue

        b_hucre = (f"{b.get('dogru', 0)}/{b.get('toplam', 0)} "
                   f"{_y(b.get('gecti'))}" if b else "—")
        c1 = (f"%{c['C1_gecerli_json'] * 100:.0f} {_y(c['C1_gecti'])}"
              if c else "—")
        c2 = (f"%{c['C2_dogru'] * 100:.0f} {_y(c['C2_gecti'])}" if c else "—")
        c4 = (f"%{c['C4_turkce_saglam'] * 100:.0f} {_y(c['C4_gecti'])}"
              if c else "—")
        c3_h = ("atlandı" if c3.get("atlandi")
                else (f"{c3.get('gecen', 0)}/{c3.get('toplam', 0)} "
                      f"{_y(c3.get('gecti'))}" if c3 else "—"))
        tut = (f"{c['tutarli_belge']}/{c['belge_sayisi']}" if c else "—")
        yg = (str(c.get("yanlisda_ortalama_guven"))
              if c and c.get("yanlisda_ortalama_guven") is not None
              else "— (yanlış yok)")

        s.append(f"| `{ad}` | ✓ | {b_hucre} | {c1} | {c2} | {c3_h} | {c4} "
                 f"| {tut} | {yg} |")

    s += [
        "",
        f"Eşikler: B ≥ %{ESIKLER['B_dogru_oran'] * 100:.0f} · "
        f"C1 = %100 · C2 ≥ %{ESIKLER['C2_dogru'] * 100:.0f} · "
        f"C3 ≥ %{ESIKLER['C3_belirsizlik'] * 100:.0f} · C4 = %100",
        "",
        "## Hız ve ADIM 4 hesabı",
        "",
        f"Varsayım: uçtan uca {UCTAN_UCA_CAGRI} LLM çağrısı × "
        f"{CAGRI_BASINA_TOKEN} çıktı token = "
        f"{UCTAN_UCA_CAGRI * CAGRI_BASINA_TOKEN} token.",
        "",
        "| Model | Kip | tok/s | İlk metin (ms) | Üretilen token | "
        "Tahmin (200 tk) | Tahmin (ölçülen) | Karar | GPU |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    for m in rapor["modeller"]:
        d = m.get("D")
        gpu = m.get("gpu_orani")
        gpu_h = "—" if gpu is None else f"%{gpu * 100:.0f}"
        if not d:
            s.append(f"| `{m['model']}` | — | — | — | — | — | — | — | {gpu_h} |")
            continue
        for kip, v in d["kipler"].items():
            if "token_sn" not in v:
                s.append(f"| `{m['model']}` | {kip} | ölçülemedi | — | — | — "
                         f"| — | — | {gpu_h} |")
                continue
            s.append(
                f"| `{m['model']}` | {kip} | {v['token_sn']} "
                f"| {v['ilk_metin_ms']:.0f} | {v['uretilen_token_medyan']:.0f} "
                f"| {v['uctan_uca_tahmin_sn']} sn "
                f"| {v['uctan_uca_olculen_sn']} sn | {v['karar']} | {gpu_h} |"
            )

    s += [
        "",
        "## Okuma notları",
        "",
        "- **C1 neredeyse bedava.** Ollama şemayı üretim sırasında dilbilgisi "
        "kısıtı olarak uyguluyor; model şema dışına çıkamıyor. C1'in %100 "
        "olması bir başarı göstergesi değil, aksi bir arıza göstergesidir.",
        "- **Asıl sayı C2 ve 'yanlışta güven'.** Yanlışta ortalama güven "
        "yüksekse (>0.7) model kalibre değildir; Parça 8'deki \"güven düşükse "
        "insana sor\" kapısı çalışmaz ve seçici doğruluk ölçülemez.",
        "- **Tutarlılık doğruluktan bağımsızdır.** Tutarlı ama yanlış model, "
        "istem düzeltmesiyle kurtarılabilir; tutarsız model kurtarılamaz.",
        "- **C3 modelin dürüstlüğünü ölçer.** Okunamayan bir parçaya yüksek "
        "güvenle tür atayan model, gerçek OCR hatalarında sessizce yanlış "
        "karar üretir.",
        "- **Düşünme kipi kıyaslaması** Parça 10'un ablasyon tablosunda "
        "doğrudan bir satırdır.",
        "",
        "## Karar kaydına yazılacaklar",
        "",
        "- [ ] Hangi model hangi ölçütte eşiği geçti / geçmedi",
        "- [ ] Ölçülen hız ve uçtan uca tahmin (iki makine ayrı)",
        "- [ ] GPU kiralama kararı ve gerekçesi (Parça 4'te tekrar bakılacak)",
        "- [ ] Eşiği geçmeyen ölçüt varsa uygulanan B planı",
        "",
    ]
    return "\n".join(s)


# =============================================================================
# KENDİ TESTİ (Ollama'ya dokunmadan)
# =============================================================================

def kendi_testi(veri_dizini: Path) -> int:
    print("Kendi testi — Ollama'ya bağlanılmıyor.\n")
    hatalar = 0

    def kontrol(ad: str, kosul: bool, ayrinti: str = "") -> None:
        nonlocal hatalar
        if kosul:
            print(f"  ✓ {ad}")
        else:
            hatalar += 1
            print(f"  ✗ {ad}" + (f" — {ayrinti}" if ayrinti else ""))

    print("Türkçe yardımcıları:")
    kontrol("tr_kucult('IŞIK') == 'ışık'", tr_kucult("IŞIK") == "ışık",
            f"gelen: {tr_kucult('IŞIK')!r}")
    kontrol("tr_kucult('İSTANBUL') == 'istanbul'",
            tr_kucult("İSTANBUL") == "istanbul",
            f"gelen: {tr_kucult('İSTANBUL')!r}")
    kontrol("sadelestir('Dilekçe') == 'dilekce'",
            sadelestir("Dilekçe") == "dilekce",
            f"gelen: {sadelestir('Dilekçe')!r}")
    kontrol("sadelestir idempotent",
            sadelestir(sadelestir("Dağıtım Yerlerine"))
            == sadelestir("Dağıtım Yerlerine"))
    kontrol("temiz Türkçe bozuk sayılmıyor",
            not bozuk_turkce_mi("Bilgilerinizi ve gereğini rica ederim.")[0])
    kontrol("mojibake yakalanıyor", bozuk_turkce_mi("gereðini")[0])
    kontrol("replacement char yakalanıyor", bozuk_turkce_mi("g\ufffdrek")[0])
    kontrol("ayrık diakritik yakalanıyor",
            bozuk_turkce_mi(unicodedata.normalize("NFD", "gereği"))[0])
    kontrol("Türkçe sezgisi çalışıyor",
            turkce_gorunuyor_mu("Bu bir üst yazıdır.")
            and not turkce_gorunuyor_mu("This is a cover letter."))

    print("\nVeri kümesi:")
    try:
        belgeler = belgeleri_yukle(veri_dizini)
        kontrol(f"{len(belgeler)} belge yüklendi", len(belgeler) >= 6)
        kontrol("Test B'ye dahil 5 belge var",
                len([b for b in belgeler if b.b_dahil]) == 5,
                f"gelen: {len([b for b in belgeler if b.b_dahil])}")
        kontrol("C3 belgesi işaretli",
                any(b.c3_dahil for b in belgeler))
        turler = {b.belge_turu for b in belgeler if b.b_dahil}
        kontrol("beş farklı belge türü kapsanıyor", len(turler) == 5,
                f"gelen: {sorted(turler)}")
        for b in belgeler:
            kontrol(f"{b.id} metni boş değil", len(b.metin.strip()) > 100)
        for b in [x for x in belgeler if x.b_dahil]:
            kontrol(f"{b.id} kavram grupları yeterli",
                    len(b.b_kavram_gruplari) >= b.b_gecme_grup)
    except Exception as e:
        hatalar += 1
        print(f"  ✗ veri yüklenemedi — {type(e).__name__}: {e}")

    print("\nŞema:")
    kontrol("enum 'bilinmiyor' içeriyor", "bilinmiyor" in BELGE_TURLERI)
    kontrol("şartname 6.4.2'nin üç türü şemada",
            all(t in BELGE_TURLERI for t in
                ("ust_yazi", "cevap_yazisi", "bilgilendirme_yazisi")))
    kontrol("şema JSON'a çevrilebiliyor",
            isinstance(json.dumps(SEMA), str))

    print(f"\n{'Tümü geçti.' if hatalar == 0 else f'{hatalar} kontrol başarısız.'}")
    return 0 if hatalar == 0 else 1


# =============================================================================
# GİRİŞ
# =============================================================================

def main() -> int:
    global NUM_CTX

    # Windows konsolu cp1254 olabiliyor; Türkçe çıktı bozulmasın.
    for akis in (sys.stdout, sys.stderr):
        try:
            akis.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    p = argparse.ArgumentParser(
        description="PARÇA 1 / ADIM 3 — model risk testi",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--modeller", nargs="+", default=MODELLER_VARSAYILAN,
                   help="test edilecek modeller")
    p.add_argument("--veri", type=Path, default=Path("veri/risk_testi"),
                   help="belge ve cevap anahtarı dizini")
    p.add_argument("--cikti", type=Path, default=Path("degerlendirme"),
                   help="rapor dizini")
    p.add_argument("--tekrar", type=int, default=4,
                   help="Test C'de belge başına tur (5 belge × tur = deneme)")
    p.add_argument("--c3-tekrar", type=int, default=5,
                   help="Test C3'te tur sayısı")
    p.add_argument("--d-tekrar", type=int, default=3,
                   help="Test D'de ölçüm tekrarı")
    p.add_argument("--baglam", type=int, default=NUM_CTX,
                   help="num_ctx; bütün ölçümlerde aynı kalmalı")
    p.add_argument("--testler", default="a,b,c,d",
                   help="koşulacak testler, virgülle: a,b,c,d")
    p.add_argument("--makine", default="",
                   help="rapora yazılacak makine notu, ör: 'RTX 2070 8GB'")
    p.add_argument("--hizli", action="store_true",
                   help="duman testi: tekrarları 1'e indirir")
    p.add_argument("--kendi-testi", action="store_true",
                   help="Ollama'ya bağlanmadan dosya ve yardımcı denetimi")
    args = p.parse_args()

    if args.kendi_testi:
        return kendi_testi(args.veri)

    if args.hizli:
        args.tekrar, args.c3_tekrar, args.d_tekrar = 1, 2, 1
        print("Hızlı kip: tekrarlar 1'e indirildi. Sonuçlar karar için "
              "kullanılmaz, yalnızca akış denetimi.\n")

    NUM_CTX = args.baglam
    args.testler = [t.strip().lower() for t in args.testler.split(",")]

    ayakta, surum = ollama_ayakta_mi()
    if not ayakta:
        print(f"HATA: Ollama'ya bağlanılamadı ({OLLAMA}) — {surum}")
        print("Ollama çalışıyor mu? Kontrol: curl http://localhost:11434")
        return 1
    print(f"Ollama {surum} · bağlam {NUM_CTX} · sıcaklık {SICAKLIK} "
          f"· keep_alive {KEEP_ALIVE}")

    try:
        belgeler = belgeleri_yukle(args.veri)
    except Exception as e:
        print(f"HATA: veri yüklenemedi — {e}")
        return 1
    print(f"{len(belgeler)} belge yüklendi "
          f"({len([b for b in belgeler if b.b_dahil])} temiz, "
          f"{len([b for b in belgeler if b.c3_dahil])} bozuk)")

    kurulu = kurulu_modeller()
    hedef_modeller = []
    for m in args.modeller:
        if m in kurulu or any(k.startswith(m + ":") for k in kurulu):
            hedef_modeller.append(m)
        else:
            print(f"! {m} kurulu değil, atlanıyor. İndirmek için: "
                  f"ollama pull {m}")
    if not hedef_modeller:
        print("HATA: test edilecek kurulu model yok.")
        return 1

    baslangic = time.perf_counter()
    rapor: dict[str, Any] = {
        "ortam": {
            "tarih": datetime.now(timezone.utc).astimezone().isoformat(
                timespec="seconds"),
            "ollama_surumu": surum,
            "num_ctx": NUM_CTX,
            "sicaklik": SICAKLIK,
            "keep_alive": KEEP_ALIVE,
            "sistem_istemi": SISTEM_ISTEMI,
            "makine": args.makine,
            "testler": args.testler,
            "tekrar": args.tekrar,
            "hizli_kip": args.hizli,
        },
        "esikler": ESIKLER,
        "modeller": [],
    }

    for model in hedef_modeller:
        rapor["modeller"].append(modeli_kosturt(model, belgeler, args))

    rapor["ortam"]["toplam_sure_sn"] = round(time.perf_counter() - baslangic, 1)

    md_yolu, json_yolu = rapor_yaz(rapor, args.cikti)
    print(f"\n{'=' * 70}")
    print(markdown_rapor(rapor))
    print(f"{'=' * 70}")
    print(f"Rapor  : {md_yolu}")
    print(f"Ham veri: {json_yolu}")
    print(f"Süre   : {rapor['ortam']['toplam_sure_sn']} sn")
    return 0


if __name__ == "__main__":
    sys.exit(main())
