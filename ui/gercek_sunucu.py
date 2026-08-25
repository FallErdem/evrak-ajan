"""Gerçek backend — `boru_hatti.isle()` çağırır, arayüz sözleşmesini konuşur.

    pip install fastapi uvicorn python-multipart
    uvicorn gercek_sunucu:app --reload --port 8000

`sahte_sunucu.py` SİLİNMİYOR. Rolü değişiyor: çevrimdışı demo yedeği.
Demo günü GPU ya da ağ giderse aynı arayüz aynı portta ona bağlanır.
Bu yüzden iki sunucu da 8000'de koşar ve arayüzde tek satır bile
değişmez.

BORU HATTINA DOKUNULMUYOR
========================
`src/boru_hatti.py` İrem'in dosyası ve donmuş sayılıyor (devir notu §9).
Bu sunucu sırayı KENDİ KURMUYOR — `isle()` çağırıyor. Sıranın elle
kurulması bu projede üç kez yapıldı ve üçünde de yanlış kuruldu;
`boru_hatti` docstring'i bedelini yazıyor: 300 belgede ME-02 yanlış
alarmı ve %0 otomatik onay.

CANLI AKIŞ — `_iz` SARMALAYICISI
================================
`isle()` senkron koşuyor ve `Dosya`yı İÇERİDE kuruyor; dışarıdan
yoklanacak bir nesne yok. Bunun yerine modül düzeyindeki
`boru_hatti._iz` fonksiyonu sarmalanıyor: `isle()` onu adım adım
çağırdığı için her adım bitişi anında görülüyor.

Bu bir GEÇİCİ ÇÖZÜM. Temizi `isle()`'ye isteğe bağlı bir olay geri
çağırımı eklemektir; o geldiğinde aşağıdaki sarmalayıcı silinmeli.
Sarmalayıcı asıl fonksiyonu çağırıyor ve dönüşünü değiştirmiyor —
boru hattının davranışı aynı kalıyor.

ÖZETLEYİCİ
==========
2026-08-25'e kadar `isle()` içinde çağrılmıyordu ve sunucu onu koşu
bittikten sonra kendisi çağırıyordu. Artık boru hattının içinde,
Denetçi'den sonra. Sunucu tarafındaki geçici çözüm kaldırıldı.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

KOK = Path(__file__).resolve().parent.parent
for yol in (KOK / "src", KOK / "araclar"):
    if str(yol) not in sys.path:
        sys.path.insert(0, str(yol))

import sunum  # noqa: E402
from depo import Defter, EvrakDeposu  # noqa: E402

YUKLEME_KLASORU = Path(__file__).resolve().parent / "yuklenen"
YAPILANDIRMA_ADAYLARI = ("yapilandirma.qwen.json", "yapilandirma_qwen.json",
                         "yapilandirma.json")

ONAYLAYAN = ("birim_sorumlusu", "yonetici")
KABUL_EDILEN_UZANTILAR = {".pdf", ".png", ".jpg", ".jpeg", ".txt"}

# Denetçi'nin 3. katmanı (ReAct araç döngüsü) açılsın mı.
#
# AÇIK — 2026-08-25 kararı.
# Katman 2 deterministik: kuralı biz seçer, biz koştururuz (21 kural,
# 153 kusursuz belgede 0 yanlış alarm). Katman 3'te direksiyon modelde:
# belgeyi okur, eksik olduğuna kanaat getirir, iddiasını doğrulamak için
# hangi aracı çağıracağına kendi karar verir. "Ajan 1" adının asıl
# karşılığı bu döngü; kapalıyken Denetçi bir ajan değil, bir kural motoru.
#
# ÖLÇÜLDÜ (katman3_olc_sonuc.txt, 20 belgelik örneklem):
#   yanlış alarm   10 kusursuz belgede 0
#   yakalama       ilgi tarihi tutarsız 5/5 · kapanış yönü 4/5
#   maliyet        76 çağrı / 20 belge = belge başına ~3,8 çağrı
#
# Yani belge maliyeti kabaca 2 katına çıkıyor (~4 -> ~8 çağrı). Örneklem
# 300 değil 20 belge; katman 2'nin "153 kusursuz belgede 0 yanlış alarm"
# güvencesi buraya UZANMIYOR.
#
# AÇILIRKEN YAPILAN İKİNCİ DEĞİŞİKLİK: katman 3'ün `kapanis_yonu_yanlis`
# kategorisi `denetci_araclar.KATEGORILER` içinde `hata` idi ve bu, ME-02
# düşürmesinin katman 3 karşılığı. Uyarıya çekildi; çekilmeseydi katman 3
# açıldığı an aynı belge bir katman yukarıdan yine bloke olur ve
# `denetci.GELEN_BLOKE_ETMEYEN` kararı sessizce etkisiz kalırdı.
#
# Kapatmak için: False yapın. Denetçi istemcisiz kurulur, yalnızca
# deterministik katmanlar koşar.
KATMAN3_ACIK = True

DEPO = EvrakDeposu()
DEFTER = Defter()

# Boru hattının pahalı tekil nesneleri. `boru_hatti.isle()` docstring'i
# uyarıyor: motor verilmezse kural dosyası HER BELGEDE yeniden okunur.
_MOTOR = None
_DENETCI = None
_ISTEMCI = None
_ISTEMCI_HATASI: str | None = None

# Aboneler: evrak_id -> SSE kuyrukları
ABONELER: dict[str, set[asyncio.Queue]] = {}

# Aynı anda tek koşu. `isle()` bloke ediyor ve `_iz` sarmalayıcısı
# modül düzeyinde tek; iki koşu paralel gitse olaylar karışırdı.
_KOSU_KILIDI = asyncio.Lock()


# =============================================================================
# Kurulum
# =============================================================================


def _yapilandirma_bul() -> Path | None:
    for ad in YAPILANDIRMA_ADAYLARI:
        y = KOK / ad
        if y.exists():
            return y
    return None


def _bilesenleri_kur() -> None:
    """Motor, denetçi ve LLM istemcisi — uygulama ömrü boyunca tek örnek."""
    global _MOTOR, _DENETCI, _ISTEMCI, _ISTEMCI_HATASI

    from kural_motoru import KuralMotoru

    _MOTOR = KuralMotoru()

    # İstemci ÖNCE kurulur: Denetçi'nin 3. katmanı ona bağlı.
    yapilandirma = _yapilandirma_bul()
    if yapilandirma is None:
        _ISTEMCI = None
        _ISTEMCI_HATASI = f"Yapılandırma bulunamadı: {YAPILANDIRMA_ADAYLARI}"
    else:
        try:
            from llm_istemci import istemci_olustur

            _ISTEMCI = istemci_olustur(yapilandirma)
        except Exception as e:  # noqa: BLE001
            # LLM'siz kip: Anlama ve Yazar atlanır, gerisi koşar. Kredi ya da
            # ağ yokken sunucunun hiç açılmaması daha kötü olurdu.
            _ISTEMCI = None
            _ISTEMCI_HATASI = f"LLM istemcisi kurulamadı: {type(e).__name__}: {e}"

    try:
        from denetci import Denetci

        _DENETCI = Denetci(istemci=_ISTEMCI if KATMAN3_ACIK else None)
    except Exception as e:  # noqa: BLE001
        # Denetçi kurulamazsa boru hattı çalışmaya devam eder, yalnızca
        # eksik tespiti yapılamaz. Sessiz geçilmiyor: /api/surum yazıyor.
        _DENETCI = None
        _ISTEMCI_HATASI = f"Denetçi kurulamadı: {type(e).__name__}: {e}"


@asynccontextmanager
async def _yasam(_app: FastAPI):
    YUKLEME_KLASORU.mkdir(exist_ok=True)
    sayi = DEPO.yukle()
    _bilesenleri_kur()
    print(f"[gercek_sunucu] {sayi} evrak yüklendi · "
          f"LLM {'var' if _ISTEMCI else 'YOK'} · "
          f"Denetçi {'var' if _DENETCI else 'YOK'} · "
          f"katman 3 {'AÇIK' if KATMAN3_ACIK and _ISTEMCI else 'kapalı'}")
    if _ISTEMCI_HATASI:
        print(f"[gercek_sunucu] {_ISTEMCI_HATASI}")
    yield


app = FastAPI(title="Evrak Ajan Sistemi — Gerçek Sunucu", lifespan=_yasam)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                   "http://localhost:5174", "http://127.0.0.1:5174"],
    allow_methods=["*"], allow_headers=["*"],
)


# =============================================================================
# Birimler — tek kaynak `birimler.py`
# =============================================================================


def _birimleri_yukle() -> list[dict]:
    """Gerçek `/api/birimler`, `birimler.birimleri_yukle()`den çıkar.

    `birimler.py` docstring'i bunu şart koşuyor: hem gerçek uç nokta hem
    sahte sunucunun JSON'u aynı fonksiyondan üretilmeli, yoksa iki liste
    ayrışır ve yönlendirme hedefi arayüzde bulunamaz.
    """
    from birimler import birimleri_yukle

    return [dict(b) for b in birimleri_yukle()]


BIRIMLER = _birimleri_yukle()
BIRIM_HARITASI = {b["kod"]: b for b in BIRIMLER}


def _birim_adi(kod: str | None) -> str | None:
    b = BIRIM_HARITASI.get(kod or "")
    return b["ad"] if b else None


def _kurum_kodu(birim_kodu: str | None) -> str | None:
    """Birimin bağlı olduğu kurum. Defter sayacının anahtarı bu.

    `birimler.py` `kurum_kodu`yu `ust_birim_kodu` zincirini kökene kadar
    yürüyerek türetiyor; burada yeniden hesaplanmıyor.
    """
    b = BIRIM_HARITASI.get(birim_kodu or "")
    return b["kurum_kodu"] if b else None


def _sun(kayit: dict) -> dict:
    return sunum.evrak_sun(kayit, _birim_adi)


# =============================================================================
# Günlük ve olay dağıtımı
# =============================================================================


def _gunluge_yaz(kayit: dict, aktor: str, olay: str) -> None:
    kayit.setdefault("gunluk", []).append(
        {"ts": time.time(), "aktor": aktor, "olay": olay})


def _dagit(evrak_id: str, olay: dict) -> None:
    """Olayı abone kuyruklarına koyar. Olay döngüsü iş parçacığında koşar."""
    for kuyruk in list(ABONELER.get(evrak_id, ())):
        kuyruk.put_nowait(olay)


def _olay(evrak_id: str, tur: str, **alanlar) -> dict:
    return {"tur": tur, "evrak_id": evrak_id, "ts": time.time(), **alanlar}


def _anlik_goruntu(kayit: dict) -> dict:
    d = kayit["dosya"]
    canli = str(d.durum) in ("ALINDI", "ISLENIYOR")
    return _olay(
        d.evrak_id, "anlik_goruntu",
        calisma_id=kayit["calisma_id"],
        canli=canli,
        durum=str(d.durum),
        toplam_ms=round(kayit.get("toplam_ms") or 0),
        dugum_kayitlari=sunum.dugum_kayitlari_sun(d, kayit.get("linter_tur", 1)),
    )


# =============================================================================
# `_iz` sarmalayıcısı — canlı adım olayları
# =============================================================================

import boru_hatti  # noqa: E402

_ASIL_IZ = boru_hatti._iz
_ETKIN_KANCA = None  # koşu sırasında doldurulur; kilit tekliği garanti eder


def _iz_sarmalayici(dosya, ajan, adim, t0, *args, **kwargs):
    """Asıl `_iz`i çağırır, sonra olayı yayınlar. Davranışı değiştirmez."""
    _ASIL_IZ(dosya, ajan, adim, t0, *args, **kwargs)
    kanca = _ETKIN_KANCA
    if kanca is not None:
        try:
            kanca(dosya, dosya.iz[-1])
        except Exception:  # noqa: BLE001
            # Yayın hatası boru hattını DÜŞÜRMEZ. Arayüz olay kaçırabilir;
            # bitmiş koşu `anlik_goruntu` ile zaten yeniden çizilebiliyor.
            pass


boru_hatti._iz = _iz_sarmalayici


# =============================================================================
# Koşu
# =============================================================================


def _sonraki_adim(no: int) -> int | None:
    sira = sunum.KOSMA_SIRASI
    try:
        i = sira.index(no)
    except ValueError:
        return None
    return sira[i + 1] if i + 1 < len(sira) else None


def _adim_olayi(evrak_id: str, dosya, no: int, tur: str, **ek) -> dict:
    tanim = sunum.DUGUM_HARITASI[no]
    return _olay(evrak_id, tur, dugum=no, dugum_adi=tanim["ad"],
                 bilesen=tanim["bilesen"], tur_no=1, **ek)


async def _kosuyu_baslat(evrak_id: str) -> None:
    """Boru hattını iş parçacığında koşturur, olayları canlı yayınlar."""
    global _ETKIN_KANCA

    async with _KOSU_KILIDI:
        kayit = DEPO.al(evrak_id)
        if kayit is None:
            return
        dongu = asyncio.get_running_loop()
        t_bas = time.perf_counter()

        # Kanca İŞ PARÇACIĞINDA koşuyor; olayı orada kurup olay döngüsüne
        # aktarıyoruz. `adim_ciktisi` de orada okunuyor — Dosya'yı mutasyona
        # uğratan iş parçacığı bu, dolayısıyla tutarlı bir an görüyor.
        def kanca(dosya, iz) -> None:
            no = sunum.DUGUM_NO.get(iz.ajan)
            if no is None:
                return
            # Gerçek `Dosya`yı koşu BİTMEDEN kayda bağlıyoruz. `isle()` onu
            # içeride kuruyor ve ancak sonunda döndürüyor; beklersek koşu
            # ortasında sayfayı yenileyen kullanıcı boş ekran görür —
            # `anlik_goruntu` yer tutucu boş dosyadan üretilirdi.
            #
            # `Dosya()` KENDİ evrak_id'sini üretiyor. Depo anahtarı ile
            # gövdedeki kimlik ayrışırsa arayüz künyeyi açar, sonraki her
            # çağrısı 404 döner. Kimliği kendi anahtarımıza sabitliyoruz.
            dosya.evrak_id = evrak_id
            dosya.dosya_adi = kayit["dosya_adi"]
            kayit["dosya"] = dosya
            bitti = _adim_olayi(
                evrak_id, dosya, no, "dugum_bitti",
                sure_ms=round(iz.sure_ms), guven=iz.guven,
                gerekce=(iz.hata or iz.ozet),
                cikti=sunum.adim_ciktisi(dosya, no))
            dongu.call_soon_threadsafe(_dagit, evrak_id, bitti)

            if not iz.basarili:
                dongu.call_soon_threadsafe(
                    _dagit, evrak_id,
                    _olay(evrak_id, "hata", dugum=no, hata=iz.hata or "adım başarısız"))

            sonraki = _sonraki_adim(no)
            if sonraki is not None:
                dongu.call_soon_threadsafe(
                    _dagit, evrak_id,
                    _adim_olayi(evrak_id, dosya, sonraki, "dugum_basladi"))

        from veri_yapisi import EvrakDurumu

        kayit["dosya"].durum = EvrakDurumu.ISLENIYOR
        _dagit(evrak_id, _olay(evrak_id, "durum_degisti", durum="ISLENIYOR"))
        _dagit(evrak_id, _adim_olayi(evrak_id, None, 1, "dugum_basladi"))

        _ETKIN_KANCA = kanca
        try:
            sonuc = await asyncio.to_thread(
                boru_hatti.isle, kayit["yol"], _ISTEMCI, _MOTOR, _DENETCI)
        except Exception as e:  # noqa: BLE001
            _ETKIN_KANCA = None
            kayit["dosya"].durum = "HATA"  # type: ignore[assignment]
            _gunluge_yaz(kayit, "sistem", f"Boru hattı patladı: {type(e).__name__}: {e}")
            _dagit(evrak_id, _olay(evrak_id, "hata", hata=f"{type(e).__name__}: {e}"))
            _dagit(evrak_id, _olay(evrak_id, "akis_bitti", durum="HATA", toplam_ms=0))
            DEPO.kaydet()
            return
        finally:
            _ETKIN_KANCA = None

        dosya = sonuc.dosya
        # Okuyucu `Dosya.kaynak`ın hepsini doldurmuyor; sayfa sayısı ve
        # girdi tipi `OkumaSonucu`da. Arayüzün künyesi bunları istiyor.
        if sonuc.okuma is not None:
            dosya.kaynak.sayfalar = [""] * max(1, sonuc.okuma.sayfa_sayisi)
            tip = sunum.GIRDI_TIPI.get(sonuc.okuma.girdi_tipi)
            if tip:
                dosya.kaynak.girdi_tipi = tip
            dosya.kaynak.ocr_motoru = sonuc.okuma.motor

        # -- kaydı tamamla --------------------------------------------------
        kayit["dosya"] = dosya
        kayit["toplam_ms"] = round((time.perf_counter() - t_bas) * 1000)
        kayit["linter_tur"] = getattr(sonuc.yazar, "tur_sayisi", 1) or 1
        kayit["hatalar"] = list(sonuc.hatalar)
        kayit["uyarilar"] = list(sonuc.uyarilar)
        kayit["atlanan"] = list(sonuc.atlanan)
        kayit["llm_cagrisi"] = sonuc.llm_cagrisi
        # Evrak, Yönlendirici'nin işaret ettiği birimin kuyruğunda başlar.
        kayit["sevk"] = {
            "bulundugu_birim": dosya.yonlendirme.hedef_birim,
            "gonderen_birim": None,
            "gelis_ts": time.time(),
            "kaydedildi": False,
            "gelen_mi": False,
        }

        _gunluge_yaz(kayit, "sistem",
                     f"Sınıflandırma: {dosya.siniflandirma.belge_turu}")
        _gunluge_yaz(kayit, "sistem",
                     f"Yönlendirme: {_birim_adi(dosya.yonlendirme.hedef_birim) or '—'} "
                     f"({dosya.yonlendirme.skor:.2f} · {dosya.yonlendirme.kaynak})")
        if kayit["linter_tur"] > 1:
            _gunluge_yaz(kayit, "sistem",
                         f"Üslup denetleyici {kayit['linter_tur']}. turda geçti")
        _gunluge_yaz(kayit, "sistem",
                     f"Güven kapısı: {'otomatik onay' if dosya.karar.otomatik_onay else 'insan onayına düştü'} "
                     f"({dosya.karar.toplam_guven:.2f} / {dosya.karar.esik:.2f})")
        for h in sonuc.hatalar:
            _gunluge_yaz(kayit, "sistem", f"HATA · {h}")

        # Otomatik onay da BİR GÖNDERİMDİR: yazı çıkar, giden deftere yazılır
        # ve muhatap kurum içiyse onun kuyruğuna düşer. İnsan onayıyla tek
        # farkı kimin karar verdiği.
        if dosya.karar.otomatik_onay:
            try:
                _gonder(kayit, "sistem")
            except Exception as e:  # noqa: BLE001
                _gunluge_yaz(kayit, "sistem",
                             f"Otomatik gönderim yapılamadı: {type(e).__name__}: {e}")

        DEPO.kaydet()
        _dagit(evrak_id, _olay(evrak_id, "durum_degisti", durum=str(dosya.durum)))
        _dagit(evrak_id, _olay(evrak_id, "akis_bitti", durum=str(dosya.durum),
                               toplam_ms=kayit["toplam_ms"]))


# =============================================================================
# Uç noktalar — tanım
# =============================================================================


def _evrak_bul(evrak_id: str) -> dict:
    kayit = DEPO.al(evrak_id)
    if kayit is None:
        raise HTTPException(404, "Evrak bulunamadı")
    return kayit


@app.get("/api/surum")
async def surum():
    return {
        "surum": sunum.SURUM,
        "adim_sayisi": len(sunum.DUGUMLER),
        "bilesen_sayisi": len({d["bilesen"] for d in sunum.DUGUMLER}),
        "ajan_sayisi": len({d["ajan"] for d in sunum.DUGUMLER if d["ajan"]}),
        "islemler": ["onayla", "taslak_kaydet", "reddet", "birim_degistir",
                     "eksik_bilgi_iste", "eksik_bilgi_cevabi", "karari_geri_al",
                     "deftere_kaydet"],
        # Model adı `LLMIstemci.y.model`de; istemcinin kendi üstünde `model`
        # diye bir alan yok. Yoksa LLM'siz kipteyiz ve bu görünür kalmalı —
        # jüri karşısında "taslak neden boş" sorusunun cevabı budur.
        "model": getattr(getattr(_ISTEMCI, "y", None), "model", None)
                 or "LLM YOK (deterministik kip)",
        "birim_kaynagi": "src/birimler.py",
        "katman3": bool(KATMAN3_ACIK and _ISTEMCI),
        "uyari": _ISTEMCI_HATASI,
    }


@app.get("/api/dugumler")
async def dugum_tanimlari():
    # `paralel_gruplar` boş: gerçek boru hattında eş zamanlı koşan adım yok.
    # Sahte sunucu Denetçi'yi ikiye bölüp paralel gösteriyordu; gerçekte
    # Denetçi tek çağrı ve katmanları içeride sırayla koşuyor.
    return {"dugumler": sunum.DUGUMLER, "paralel_gruplar": []}


@app.get("/api/birimler")
async def birim_listesi():
    return BIRIMLER


# =============================================================================
# Uç noktalar — evrak
# =============================================================================


@app.post("/api/evrak", status_code=202)
async def evrak_yukle(dosya: UploadFile = File(...)):
    ad = Path(dosya.filename or "evrak.pdf").name
    if Path(ad).suffix.lower() not in KABUL_EDILEN_UZANTILAR:
        raise HTTPException(
            400, f"Desteklenmeyen dosya türü: {Path(ad).suffix or '(uzantısız)'}")

    evrak_id = uuid.uuid4().hex[:12]
    hedef = YUKLEME_KLASORU / f"{evrak_id}_{ad}"
    with hedef.open("wb") as f:
        shutil.copyfileobj(dosya.file, f)

    from veri_yapisi import Dosya

    bos = Dosya()
    bos.evrak_id = evrak_id
    bos.dosya_adi = ad
    kayit = {
        "dosya": bos,
        "calisma_id": "c_" + uuid.uuid4().hex[:6],
        "dosya_adi": ad,
        "yol": str(hedef),
        "yuklenme_ts": time.time(),
        "toplam_ms": 0,
        "linter_tur": 1,
        "gunluk": [],
        "sevk": None,
        "defter_kaydi": None,
    }
    _gunluge_yaz(kayit, "sistem", f"Evrak alındı: {ad}")
    DEPO.ekle(kayit)
    ABONELER.setdefault(evrak_id, set())

    asyncio.create_task(_kosuyu_baslat(evrak_id))
    return {"evrak_id": evrak_id, "calisma_id": kayit["calisma_id"],
            "durum": "ALINDI"}


@app.get("/api/evrak")
async def evrak_listesi(x_rol: str = Header(default="kayit_memuru"),
                        x_birim: str | None = Header(default=None)):
    kayitlar = DEPO.hepsi()
    if x_rol == "birim_sorumlusu" and x_birim:
        # Süzme SEVK'e bakıyor, yönlendirmeye değil: evrak onaylanıp başka
        # birime gittiğinde eski birimin kuyruğunda kalmamalı. Sevk yoksa
        # (koşu bitmemiş) yönlendirmeye düşülüyor.
        kayitlar = [k for k in kayitlar
                    if ((k.get("sevk") or {}).get("bulundugu_birim")
                        or k["dosya"].yonlendirme.hedef_birim) == x_birim]
    return [sunum.ozet_sun(k, _birim_adi) for k in kayitlar]


@app.get("/api/evrak/{evrak_id}")
async def evrak_detay(evrak_id: str):
    return _sun(_evrak_bul(evrak_id))


@app.get("/api/evrak/{evrak_id}/metin")
async def evrak_metni(evrak_id: str):
    kayit = _evrak_bul(evrak_id)
    d = kayit["dosya"]
    return {
        "evrak_id": evrak_id, "dosya_adi": kayit["dosya_adi"],
        "sayfa_sayisi": d.kaynak.sayfa_sayisi,
        "karakter": len(d.kaynak.ham_metin or ""),
        "girdi_tipi": sunum._d(d.kaynak.girdi_tipi),
        "ocr_motoru": d.kaynak.ocr_motoru,
        "metin": d.kaynak.ham_metin or "",
    }


@app.get("/api/evrak/{evrak_id}/varlik/{sira}/ham")
async def varlik_ham(evrak_id: str, sira: int,
                     x_rol: str = Header(default="kayit_memuru")):
    """Kişisel verinin maskesiz hâli. Her çağrı işlem günlüğüne yazılır."""
    kayit = _evrak_bul(evrak_id)
    varliklar = kayit["dosya"].icerik.varliklar or []
    if not 1 <= sira <= len(varliklar):
        raise HTTPException(404, "Varlık bulunamadı")
    varlik = varliklar[sira - 1]
    if not varlik.kisisel_veri:
        raise HTTPException(404, "Bu varlık kişisel veri değil")
    _gunluge_yaz(kayit, x_rol,
                 f"Kişisel veri açıldı: varlık {sira} ({varlik.tip})")
    DEPO.kaydet()
    return {"sira": sira, "tur": str(varlik.tip), "deger": varlik.deger,
            "acan_rol": x_rol}


@app.get("/api/evrak/{evrak_id}/akis")
async def evrak_akisi(evrak_id: str):
    kayit = _evrak_bul(evrak_id)

    async def uret():
        goruntu = _anlik_goruntu(kayit)
        yield f"data: {json.dumps(goruntu, ensure_ascii=False)}\n\n"
        if not goruntu["canli"]:
            return
        kuyruk: asyncio.Queue = asyncio.Queue()
        ABONELER.setdefault(evrak_id, set()).add(kuyruk)
        try:
            while True:
                olay = await kuyruk.get()
                yield f"data: {json.dumps(olay, ensure_ascii=False)}\n\n"
                if olay.get("tur") == "akis_bitti":
                    break
        finally:
            ABONELER.get(evrak_id, set()).discard(kuyruk)

    return StreamingResponse(
        uret(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# =============================================================================
# Sevk — giden yazının hangi birime ulaştığı
# =============================================================================


def _alici_birim(dosya) -> str | None:
    """Onaylanan yazı hangi birime gidiyor.

    ÜÇ HAT, SIRAYLA — ilk ikisi deterministik
    -----------------------------------------
    1  Gönderenin DETSİS'i. Cevap yazısı, gelen evrağın GÖNDERENİNE gider;
       DETSİS bir kimliktir ve `birimler.detsis_ile_birim_bul` onu tabloda
       arar. OCR harfleri bozuyor ama rakamları bozmuyor: 165/168 (%98,2).

    2  Metin eşleşmesi. DETSİS yoksa taslağın muhatap satırı ya da
       gönderenin idare/birim adı birim tablosuyla eşleştirilir.
       `metin.en_iyi_eslesme` zaten Yönlendirici'de ölçülmüş hat.

    3  Hiçbiri tutmazsa None: muhatap gerçek kişi ya da şirkettir
       (300 belgenin 132'si böyle). Kurum dışına giden yazı için gelen
       defteri açılmaz, yalnızca giden defterine yazılır.

    YÖNLENDİRMEYE BAKMIYORUZ — kasıtlı. `yonlendirme.hedef_birim` evrağı
    İÇERİDE hangi birimin ele alacağını söylüyor; evrak zaten oradadır.
    Cevabın nereye gittiği ayrı bir sorudur.
    """
    from birimler import detsis_ile_birim_bul

    gonderen = getattr(dosya.ustveri, "gonderen", None)
    detsis = getattr(gonderen, "detsis_no", None)
    if detsis:
        birim = detsis_ile_birim_bul(detsis)
        if birim:
            return birim["kod"]

    from metin import en_iyi_eslesme

    adaylar = [(b["kod"], b["ad"], b["seviye"]) for b in BIRIMLER]
    for aday_metin in (dosya.cikti_yazi.muhatap,
                       getattr(gonderen, "ham", None),
                       getattr(gonderen, "idare", None),
                       getattr(gonderen, "birim", None)):
        if not aday_metin:
            continue
        kod, _oran, _ad = en_iyi_eslesme(str(aday_metin), adaylar)
        if kod:
            return kod
    return None


def _defter_satiri(dosya, yon: str, sira_no: int, sayi: str | None) -> dict:
    """Satır alanları `src/defter.py`den gelir; burada uydurulmaz.

    `defter_satiri` `yazar.kim_yaziyor` çağırıyor ve o da patlayabilir.
    Patlarsa defter kaydı kaybolmamalı — asgari alanlarla yazılıyor ve
    eksiklik görünür kalıyor.
    """
    from defter import defter_satiri

    try:
        return defter_satiri(dosya, yon, sira_no, sayi)
    except Exception:  # noqa: BLE001
        u = dosya.ustveri
        return {"yon": yon, "sira_no": sira_no, "evrak_id": dosya.evrak_id,
                "sayi": sayi or (u.sayi if yon == "gelen" else None),
                "tarih": u.tarih, "konu": u.konu or dosya.cikti_yazi.konu,
                "muhatap": dosya.cikti_yazi.muhatap,
                "belge_turu": dosya.siniflandirma.belge_turu,
                "durum": dosya.durum}


def _giden_deftere_yaz(kayit: dict) -> dict | None:
    """Onaylanan yazıyı gönderen birimin giden defterine kaydeder.

    SAYI ANCAK SIRA NUMARASI KESİNLEŞİNCE KURULUR. Bu yüzden önce satır
    yazılıyor (numara orada atomik olarak veriliyor), sonra sayı
    üretilip satıra işleniyor. Ters sırada eş zamanlı iki onay aynı
    sayıyı alırdı.
    """
    dosya = kayit["dosya"]
    gonderen_birim = ((kayit.get("sevk") or {}).get("bulundugu_birim")
                      or dosya.yonlendirme.hedef_birim)
    kurum = _kurum_kodu(gonderen_birim)
    if not gonderen_birim or not kurum:
        return None

    satir = _defter_satiri(dosya, "giden", 0, None)
    kaydedilen = DEFTER.yaz("giden", kurum, gonderen_birim, dosya.evrak_id, satir)

    if not kaydedilen.get("sayi"):
        from defter import DefterHatasi, giden_sayi_kur

        try:
            # Sayı BİRİMİN DETSİS'ini taşıyor, sıra numarası KURUM defterinden
            # geliyor. İkisi bilerek farklı: sayı yazıyı kimin imzaladığını,
            # numara kurumun kaçıncı yazısı olduğunu söylüyor.
            sayi = giden_sayi_kur(dosya, kaydedilen["sira_no"], gonderen_birim)
            DEFTER.sayiyi_isle("giden", kurum, dosya.evrak_id, sayi)
            kaydedilen["sayi"] = sayi
        except DefterHatasi as e:
            # Sessizce None dönmüyoruz: kayıt sayısız kalıyor ve sebebi
            # işlem günlüğüne yazılıyor. `defter.py` docstring'inin kuralı.
            _gunluge_yaz(kayit, "sistem", f"Giden sayı üretilemedi — {e}")
    return kaydedilen


def _gelen_deftere_yaz(kayit: dict, birim: str) -> dict:
    """Alıcı kurumun gelen defterine kaydeder ve damgayı basar."""
    dosya = kayit["dosya"]
    kurum = _kurum_kodu(birim)
    if not kurum:
        raise HTTPException(409, "Birimin bağlı olduğu kurum çözülemedi")
    satir = _defter_satiri(dosya, "gelen", 0, None)
    kaydedilen = DEFTER.yaz("gelen", kurum, birim, dosya.evrak_id, satir)

    from defter import gelen_kayit_kur

    try:
        gelen_kayit_kur(dosya, kaydedilen["sira_no"])
    except Exception:  # noqa: BLE001
        pass
    return kaydedilen


def _gonder(kayit: dict, aktor: str) -> None:
    """Onaylanan yazıyı gönderir: giden defteri + alıcıya sevk.

    HEM insan onayı HEM otomatik onay buradan geçiyor. Otomatik onay
    "gönderilmiş sayılmaz" olsaydı %71,7'lik otomatik onay oranının
    tamamı defterde görünmezdi ve giden evrak defteri yalnızca insanın
    dokunduğu belgeleri sayardı — defterin anlamı bu değil.
    """
    dosya = kayit["dosya"]
    giden = _giden_deftere_yaz(kayit)
    alici = _alici_birim(dosya)
    gonderen_birim = (kayit.get("sevk") or {}).get("bulundugu_birim")
    sayi_notu = (f" · giden sayı {giden['sayi']}"
                 if giden and giden.get("sayi") else "")

    if alici and alici != gonderen_birim:
        kayit["sevk"] = {
            "bulundugu_birim": alici,
            "gonderen_birim": gonderen_birim,
            "gelis_ts": time.time(),
            "kaydedildi": False,
            "gelen_mi": True,
        }
        _gunluge_yaz(kayit, aktor,
                     f"Onaylandı ve gönderildi → {_birim_adi(alici)}{sayi_notu}")
    else:
        # Muhatap kurum dışı (gerçek kişi, şirket, tabloda olmayan idare).
        # Gelen defteri açılmıyor — o defter bizim kurumumuzun defteri.
        _gunluge_yaz(kayit, aktor,
                     f"Onaylandı · muhatap kurum dışında, gelen defteri "
                     f"açılmadı{sayi_notu}")
    kayit["defter_kaydi"] = _defter_kaydini_topla(dosya.evrak_id)


def _defter_kaydini_topla(evrak_id: str) -> dict:
    satirlar = DEFTER.satirlar()
    return {
        yon: next((s for s in satirlar
                   if s["evrak_id"] == evrak_id and s["yon"] == yon), None)
        for yon in ("gelen", "giden")
    }


# =============================================================================
# Uç noktalar — karar
# =============================================================================


@app.post("/api/evrak/{evrak_id}/eksik_bilgi_onizleme")
async def eksik_bilgi_onizleme(evrak_id: str, govde: dict):
    """Yazıyı gösterir, hiçbir durumu değiştirmez.

    Talebi Yazar zaten koşu sırasında kurdu (`yazar._talep_kur`); burada
    yalnızca SEÇİLEN sorulara göre süzülüyor. Yeniden üretilmiyor:
    sorular `kurallar.json`da yazılı ve mevzuat diliyle kurulmuş,
    yeniden üretmek onları modele yazdırmak olurdu.
    """
    kayit = _evrak_bul(evrak_id)
    sorular = govde.get("sorular") or []
    if not sorular:
        raise HTTPException(400, "En az bir soru seçilmeli")

    talep = kayit["dosya"].eksik_bilgi_talebi
    if talep is None:
        raise HTTPException(409, "Bu evrakta karşı taraftan istenebilir eksik yok")

    sunulan = sunum.talep_sun(talep)
    sunulan["sorular"] = [s for s in sunulan["sorular"] if s in sorular] or sorular
    return sunulan


@app.post("/api/evrak/{evrak_id}/karar")
async def karar_ver(evrak_id: str, govde: dict):
    kayit = _evrak_bul(evrak_id)
    dosya = kayit["dosya"]
    aksiyon = govde.get("aksiyon")
    rol = govde.get("rol", "")
    gerekce = (govde.get("gerekce") or "").strip()

    if rol not in ONAYLAYAN:
        raise HTTPException(403, "Bu rolün onay yetkisi yok")
    if aksiyon in ("reddet", "birim_degistir", "karari_geri_al") and not gerekce:
        raise HTTPException(400, "Bu işlem için gerekçe zorunlu")

    from veri_yapisi import Duzeltme, EvrakDurumu, InsanKarari

    simdi = datetime.now(timezone.utc)
    durum = str(dosya.durum)

    def _karari_isle(insan_karari) -> None:
        dosya.karar.insan_karari = insan_karari
        dosya.karar.karar_veren_rol = rol
        dosya.karar.karar_zamani = simdi
        if gerekce:
            dosya.karar.karar_gerekcesi = gerekce[:1000]

    # -- onayla --------------------------------------------------------------
    if aksiyon == "onayla":
        if durum not in sunum.ACIK:
            raise HTTPException(409, "Bu evrak zaten sonuçlanmış")
        dosya.durum = EvrakDurumu.ONAYLANDI
        _karari_isle(InsanKarari.ONAYLANDI)
        _gonder(kayit, rol)

    # -- taslak_kaydet -------------------------------------------------------
    elif aksiyon == "taslak_kaydet":
        for yasak in ("taslak_sayi", "taslak_tarih", "taslak_imza_ad"):
            if govde.get(yasak):
                raise HTTPException(
                    400, "Sayı, tarih ve imzalayan EBYS'de atanır; düzenlenemez")
        c = dosya.cikti_yazi
        # Sözleşme alan adı -> şema alan adı. `govde` şemada `metin`.
        esleme = {"baslik": "baslik", "konu": "konu",
                  "muhatap": "muhatap", "govde": "metin"}
        degisen = []
        for sozlesme_ad, sema_ad in esleme.items():
            yeni = govde.get("taslak_" + sozlesme_ad)
            if yeni is not None and yeni.strip() and yeni.strip() != getattr(c, sema_ad):
                setattr(c, sema_ad, yeni.strip())
                degisen.append(sozlesme_ad)
        if not degisen:
            raise HTTPException(400, "Değişiklik yok")
        dosya.duzeltmeler.append(
            Duzeltme(tur="taslak", rol=rol, zaman=simdi, alanlar=degisen))
        etiket = {"baslik": "başlık", "konu": "konu",
                  "muhatap": "muhatap", "govde": "gövde"}
        _gunluge_yaz(kayit, rol,
                     "Taslak düzenlendi — " + ", ".join(etiket[a] for a in degisen))

    # -- reddet --------------------------------------------------------------
    elif aksiyon == "reddet":
        if durum not in sunum.ACIK:
            raise HTTPException(409, "Bu evrak zaten sonuçlanmış")
        dosya.durum = EvrakDurumu.REDDEDILDI
        _karari_isle(InsanKarari.REDDEDILDI)
        dosya.duzeltmeler.append(
            Duzeltme(tur="red", rol=rol, zaman=simdi, gerekce=gerekce[:1000]))
        _gunluge_yaz(kayit, rol, f"Reddedildi — {gerekce}")

    # -- birim_degistir ------------------------------------------------------
    elif aksiyon == "birim_degistir":
        yeni = govde.get("yeni_birim")
        hedef = BIRIM_HARITASI.get(yeni or "")
        if not hedef or not hedef.get("hedef_olabilir"):
            raise HTTPException(400, "Geçersiz hedef birim")
        eski = dosya.yonlendirme.hedef_birim
        dosya.yonlendirme.hedef_birim = yeni
        # Kaynak İNSAN oluyor: yönlendirme başarımı ölçümü sistemin kendi
        # kararıyla insanınkini karıştırmamalı.
        from veri_yapisi import YonlendirmeKaynagi

        dosya.yonlendirme.kaynak = YonlendirmeKaynagi.INSAN
        kayit["sevk"] = {
            "bulundugu_birim": yeni,
            "gonderen_birim": eski,
            "gelis_ts": time.time(),
            "kaydedildi": False,
            "gelen_mi": True,
        }
        dosya.duzeltmeler.append(Duzeltme(
            tur="birim", rol=rol, zaman=simdi,
            alanlar=[eski or "—", yeni], gerekce=gerekce[:1000]))
        _karari_isle(InsanKarari.BIRIM_DEGISTIRILDI)
        _gunluge_yaz(kayit, rol,
                     f"Yönlendirme değiştirildi — {_birim_adi(eski) or '—'} → "
                     f"{hedef['ad']} · {gerekce}")

    # -- deftere_kaydet ------------------------------------------------------
    elif aksiyon == "deftere_kaydet":
        sevk = kayit.get("sevk") or {}
        birim = sevk.get("bulundugu_birim")
        if not birim:
            raise HTTPException(409, "Bu evrak henüz bir birime sevk edilmemiş")
        if sevk.get("kaydedildi"):
            raise HTTPException(409, "Bu evrak zaten deftere kaydedilmiş")
        kaydedilen = _gelen_deftere_yaz(kayit, birim)
        sevk["kaydedildi"] = True
        kayit["sevk"] = sevk
        kayit["defter_kaydi"] = _defter_kaydini_topla(evrak_id)
        _gunluge_yaz(kayit, rol,
                     f"Gelen defterine kaydedildi — {_birim_adi(birim)} "
                     f"sıra no {kaydedilen['sira_no']}")

    # -- eksik_bilgi_iste ----------------------------------------------------
    elif aksiyon == "eksik_bilgi_iste":
        sorular = govde.get("sorular") or []
        if not sorular:
            raise HTTPException(400, "En az bir soru seçilmeli")
        talep = dosya.eksik_bilgi_talebi
        if talep is None:
            raise HTTPException(409, "Bu evrakta karşı taraftan istenebilir eksik yok")
        talep.sorular = [s for s in talep.sorular if s in sorular] or list(sorular)
        elle = govde.get("yazi")
        if isinstance(elle, dict) and talep.yazi is not None:
            esleme = {"baslik": "baslik", "konu": "konu",
                      "muhatap": "muhatap", "govde": "metin"}
            degisti = False
            for sozlesme_ad, sema_ad in esleme.items():
                deger = elle.get(sozlesme_ad)
                if deger and deger.strip():
                    setattr(talep.yazi, sema_ad, deger.strip())
                    degisti = True
            talep.elle_duzenlendi = degisti
        dosya.durum = EvrakDurumu.EKSIK_BILGI_BEKLIYOR
        _karari_isle(InsanKarari.EKSIK_BILGI_ISTENDI)
        _gunluge_yaz(kayit, rol,
                     f"Eksik tamamlama yazısı gönderildi → {talep.muhatap_ad or '—'} "
                     f"({len(talep.sorular)} soru)")

    # -- eksik_bilgi_cevabi --------------------------------------------------
    elif aksiyon == "eksik_bilgi_cevabi":
        talep = dosya.eksik_bilgi_talebi
        if talep is None:
            raise HTTPException(409, "Bu evrakta bekleyen eksik bilgi talebi yok")
        dolu = [c for c in (govde.get("cevaplar") or [])
                if (c.get("cevap") or "").strip()]
        if not dolu:
            raise HTTPException(400, "En az bir soruya cevap girilmeli")
        harita = {c["soru"]: c["cevap"].strip() for c in dolu}
        kalan_kritik = 0
        for eksik in (dosya.icerik.eksik_alanlar or []):
            if eksik.soru in harita:
                eksik.giderildi = True
                eksik.cevap = harita[eksik.soru][:1000]
            elif str(eksik.onem) == "hata" and not eksik.giderildi:
                kalan_kritik += 1

        from veri_yapisi import EksikBilgiCevabi

        dosya.eksik_bilgi_cevabi = EksikBilgiCevabi(
            zaman=simdi, gonderen=talep.muhatap_ad,
            ilgi=(dosya.cikti_yazi.konu or "") + " · tamamlama",
            cevaplar=[{"soru": c["soru"], "cevap": c["cevap"].strip()} for c in dolu])

        # Güven kapısını YENİDEN KOŞTURUYORUZ, elle skor artırmıyoruz.
        # Sahte sunucu skoru "+0.10 × cevap" diye tahmin ediyordu; gerçek
        # kapı beş girdiye bakıyor ve kritik eksik kapandıysa zaten çıkıyor.
        try:
            from guven_kapisi import degerlendir

            degerlendir(dosya)
        except Exception as e:  # noqa: BLE001
            _gunluge_yaz(kayit, "sistem", f"Güven kapısı yeniden koşamadı: {e}")
        if str(dosya.durum) not in sunum.SONUCLANMIS:
            dosya.durum = EvrakDurumu.INSAN_ONAYI_BEKLIYOR
        _gunluge_yaz(kayit, talep.muhatap_ad or "karşı taraf",
                     f"Eksik bilgi cevabı alındı ({len(dolu)} soru)")
        _gunluge_yaz(kayit, "sistem",
                     f"Güven kapısı yeniden değerlendirdi · güven "
                     f"{dosya.karar.toplam_guven:.2f} · kalan kritik eksik {kalan_kritik}")

    # -- karari_geri_al ------------------------------------------------------
    elif aksiyon == "karari_geri_al":
        if rol != "yonetici":
            raise HTTPException(403, "Kararı yalnızca Kurum Yöneticisi geri alabilir")
        if durum not in sunum.SONUCLANMIS:
            raise HTTPException(409, "Bu evrakta geri alınacak karar yok")
        dosya.durum = EvrakDurumu.INSAN_ONAYI_BEKLIYOR
        _karari_isle(InsanKarari.GERI_ALINDI)
        dosya.duzeltmeler.append(
            Duzeltme(tur="geri_alma", rol=rol, zaman=simdi, gerekce=gerekce[:1000]))
        _gunluge_yaz(kayit, rol,
                     f"Karar geri alındı ({sunum.DURUM_ETIKET.get(durum, durum)}) — {gerekce}")

    else:
        raise HTTPException(400, f"Bilinmeyen işlem: {aksiyon}")

    DEFTER.durumu_guncelle(evrak_id, str(dosya.durum))
    DEPO.kaydet()
    return {"durum": str(dosya.durum), "duzeltme_sayisi": len(dosya.duzeltmeler)}


# =============================================================================
# Uç noktalar — evrak kayıt defteri
# =============================================================================


@app.get("/api/defter")
async def defter_listesi(
    yon: str | None = Query(default=None, pattern="^(gelen|giden)$"),
    kurum: str | None = None,
    q: str | None = None,
    x_rol: str = Header(default="kayit_memuru"),
    x_birim: str | None = Header(default=None),
):
    """Gelen ve giden defteri. Sıra numarası KURUM başına 1'den artar.

    Birim sorumlusu kendi KURUMUNUN defterini görüyor, kendi biriminin
    değil — defter kurumun defteridir. Satırdaki `birim_adi` hangi
    birimin işlediğini söylüyor.
    """
    if x_rol == "birim_sorumlusu" and x_birim:
        kurum = _kurum_kodu(x_birim)
    satirlar = DEFTER.satirlar(yon=yon, kurum=kurum, q=q)
    for s in satirlar:
        s["birim_adi"] = _birim_adi(s["birim"])
        s["kurum_adi"] = _birim_adi(s["kurum"])
    return satirlar


@app.get("/api/defter/ozet")
async def defter_ozeti():
    ozet = DEFTER.ozet()
    for s in ozet:
        s["kurum_adi"] = _birim_adi(s["kurum"])
    return ozet


# =============================================================================
# Uç noktalar — istatistik
# =============================================================================


@app.get("/api/istatistik")
async def istatistik(x_rol: str = Header(default="kayit_memuru")):
    if x_rol != "yonetici":
        raise HTTPException(403, "İstatistik yalnızca Kurum Yöneticisine açıktır")

    kayitlar = [k for k in DEPO.hepsi() if str(k["dosya"].durum) != "HATA"]
    if not kayitlar:
        return {"toplam_evrak": 0, "bos": True}

    import statistics

    dosyalar = [k["dosya"] for k in kayitlar]
    sureler = sorted(round(k.get("toplam_ms") or 0) for k in kayitlar)
    otomatik = sum(1 for d in dosyalar if d.karar.otomatik_onay)
    duzeltmeli = sum(1 for d in dosyalar if d.duzeltmeler)

    # Düğüm dağılımı: her adımın ortalama ve p95 süresi, iz kayıtlarından.
    adim_sureleri: dict[int, list[float]] = {}
    for d in dosyalar:
        for iz in d.iz:
            no = sunum.DUGUM_NO.get(iz.ajan)
            if no:
                adim_sureleri.setdefault(no, []).append(iz.sure_ms)

    def _p(degerler: list[float], oran: float) -> float:
        if not degerler:
            return 0.0
        sirali = sorted(degerler)
        return sirali[min(len(sirali) - 1, int(len(sirali) * oran))]

    dugum_dagilimi = [
        {"no": t["no"], "ad": t["ad"], "baslik": t["baslik"], "motor": t["motor"],
         "ortalama_ms": round(statistics.fmean(adim_sureleri.get(t["no"], [0]))),
         "p95_ms": round(_p(adim_sureleri.get(t["no"], [0.0]), 0.95))}
        for t in sunum.DUGUMLER
    ]
    sirali_toplam = sum(x["ortalama_ms"] for x in dugum_dagilimi)

    motor_ms: dict[str, float] = {}
    for t in sunum.DUGUMLER:
        motor_ms[t["motor"]] = motor_ms.get(t["motor"], 0.0) + sum(
            adim_sureleri.get(t["no"], []))

    eksik_katman: dict[str, int] = {}
    eksik_onem: dict[str, int] = {}
    eksik_toplam = eksik_giderilen = 0
    for d in dosyalar:
        for e in (d.icerik.eksik_alanlar or []):
            eksik_toplam += 1
            eksik_giderilen += bool(e.giderildi)
            eksik_katman[str(e.katman)] = eksik_katman.get(str(e.katman), 0) + 1
            eksik_onem[str(e.onem)] = eksik_onem.get(str(e.onem), 0) + 1

    linter_kurallar: dict[str, dict] = {}
    ilk_tur_gecen = 0
    for k, d in zip(kayitlar, dosyalar):
        ilk_tur_gecen += (k.get("linter_tur") or 1) == 1
        for b in (d.cikti_yazi.linter_raporu.bulgular or []):
            satir = linter_kurallar.setdefault(
                b.kural_id, {"kural_no": b.kural_id, "mesaj": b.baslik,
                             "mevzuat": b.dayanak or "", "duzey": str(b.onem),
                             "adet": 0})
            satir["adet"] += 1

    durum_dagilimi: dict[str, int] = {}
    tur_dagilimi: dict[str, int] = {}
    birim_dagilimi: dict[str, int] = {}
    for d in dosyalar:
        durum_dagilimi[str(d.durum)] = durum_dagilimi.get(str(d.durum), 0) + 1
        tur = str(d.siniflandirma.belge_turu)
        tur_dagilimi[tur] = tur_dagilimi.get(tur, 0) + 1
        if d.yonlendirme.hedef_birim:
            ad = _birim_adi(d.yonlendirme.hedef_birim) or d.yonlendirme.hedef_birim
            birim_dagilimi[ad] = birim_dagilimi.get(ad, 0) + 1

    yon_duzeltmeleri = [
        {"eski": x.alanlar[0] if x.alanlar else "—",
         "yeni": x.alanlar[1] if len(x.alanlar) > 1 else "—",
         "konu": str(d.ustveri.konu or ""), "gerekce": x.gerekce or ""}
        for d in dosyalar for x in d.duzeltmeler if x.tur == "birim"
    ]
    yonlendirilen = sum(1 for d in dosyalar if d.yonlendirme.hedef_birim)

    mevzuat_getirilen = sum(len(d.mevzuat or []) for d in dosyalar)
    mevzuat_dogrulanan = sum(1 for d in dosyalar for m in (d.mevzuat or [])
                             if m.dogrulandi)

    bekleyen = sum(1 for d in dosyalar if str(d.durum) in sunum.ACIK)
    return {
        "bos": False,
        "toplam_evrak": len(kayitlar),
        "otomatik_onay_orani": otomatik / len(kayitlar),
        "insan_duzeltme_orani": duzeltmeli / len(kayitlar),
        "ortalama_sure_ms": round(statistics.fmean(sureler)),
        "p50_sure_ms": round(statistics.median(sureler)),
        "p95_sure_ms": round(_p([float(x) for x in sureler], 0.95)),
        "en_hizli_ms": sureler[0],
        "en_yavas_ms": sureler[-1],
        "dugum_dagilimi": dugum_dagilimi,
        "sirali_toplam_ms": sirali_toplam,
        "gerceklesen_toplam_ms": round(statistics.fmean(sureler)),
        "motor_ms": {k: round(v) for k, v in motor_ms.items()},
        "guven_skorlari": [float(d.karar.toplam_guven) for d in dosyalar],
        "esik": float(dosyalar[0].karar.esik),
        "yonlendirme_isabet": (
            (yonlendirilen - len(yon_duzeltmeleri)) / yonlendirilen
            if yonlendirilen else 0.0),
        "yonlendirme_duzeltmeleri": yon_duzeltmeleri,
        "yonlendirilen": yonlendirilen,
        "eksik_katman": eksik_katman,
        "eksik_onem": eksik_onem,
        "eksik_toplam": eksik_toplam,
        "eksik_giderilen": eksik_giderilen,
        "mevzuat_getirilen": mevzuat_getirilen,
        "mevzuat_dogrulanan": mevzuat_dogrulanan,
        "mevzuat_elenen": mevzuat_getirilen - mevzuat_dogrulanan,
        "linter_ilk_tur_gecme": ilk_tur_gecen / len(kayitlar),
        "linter_kurallar": sorted(linter_kurallar.values(),
                                  key=lambda x: -x["adet"]),
        "durum_dagilimi": durum_dagilimi,
        "belge_turu_dagilimi": tur_dagilimi,
        "birim_dagilimi": sorted(
            ({"birim_adi": a, "adet": n} for a, n in birim_dagilimi.items()),
            key=lambda x: -x["adet"]),
        "bekleyen": bekleyen,
        "kritik_eksikli": sum(1 for d in dosyalar if d.icerik.kritik_eksikler),
        "bekleme_ortalama_sn": round(statistics.fmean(
            [time.time() - k["yuklenme_ts"] for k in kayitlar
             if str(k["dosya"].durum) in sunum.ACIK] or [0])),
    }


@app.delete("/api/evrak/{evrak_id}")
async def evrak_sil(evrak_id: str, x_rol: str = Header(default="kayit_memuru")):
    """Tek evrağı siler. Deneme koşularını temizlemek için.

    DEFTER SATIRI SİLİNMEZ. Deftere yazılmış bir kaydı geri almak defterde
    boşluk bırakır ve boşluk denetimde cevaplanamaz bir soru olur; gerçek
    kurumlarda da kayıt silinmez. Evrak listeden kalkar, defter satırı
    kalır ve o satıra tıklanınca artık künye açılmaz.
    """
    if x_rol != "yonetici":
        raise HTTPException(403, "Evrak silmeyi yalnızca Kurum Yöneticisi yapabilir")
    kayit = _evrak_bul(evrak_id)
    defterde = [s for s in DEFTER.satirlar() if s["evrak_id"] == evrak_id]
    DEPO.kayitlar.pop(evrak_id, None)
    ABONELER.pop(evrak_id, None)
    DEPO.kaydet()
    return {"durum": "silindi", "evrak_id": evrak_id,
            "dosya_adi": kayit["dosya_adi"],
            "defterde_kalan_satir": len(defterde)}


@app.post("/api/sifirla")
async def sifirla(
    evraklar: bool = Query(default=True, description="işlenmiş evrakları sil"),
    defter: bool = Query(default=True, description="gelen/giden defterini sil"),
):
    """Demo öncesi temizlik.

    Varsayılan HER ŞEYİ siler — işlenmiş evraklar, gelen defteri, giden
    defteri. Sıra numaraları 1'den başlar.

    İkisi ayrı ayrı kapatılabilir çünkü aynı şey değiller:

        ?defter=false     Evraklar gider, defter numaraları KALIR. Deneme
                          koşularını temizleyip defteri sürdürmek için.
        ?evraklar=false   Defter sıfırlanır, işlenmiş evraklar kalır. Yeni
                          bir demo turuna aynı belgelerle başlamak için.

    Yarıda kalan bir koşu varsa (`ISLENIYOR`) o koşunun iş parçacığı
    sürmeye devam eder ve bittiğinde silinmiş bir kayda yazmaya çalışır;
    bu sessizce yutulur. Koşu bitmeden sıfırlamayın.
    """
    onceki_evrak = len(DEPO.kayitlar)
    onceki_defter = len(DEFTER.satirlar())

    if evraklar:
        DEPO.temizle()
        DEPO.kaydet()
        ABONELER.clear()
    if defter:
        DEFTER.temizle()

    return {
        "durum": "sifirlandi",
        "silinen_evrak": onceki_evrak if evraklar else 0,
        "silinen_defter_satiri": onceki_defter if defter else 0,
        "kalan_evrak": len(DEPO.kayitlar),
        "kalan_defter_satiri": len(DEFTER.satirlar()),
    }
