"""`Dosya` -> arayüz sözleşmesi JSON'u. Tek eşleme yeri.

NEDEN AYRI MODÜL
================
`veri_yapisi.Dosya` ile arayüzün beklediği şema aynı şey DEĞİL ve
olmamalı. Şema mevzuata göre kurulmuş (`ustveri.muhatap` bir `Taraf`
nesnesi, `icerik.eksik_alanlar` bir `EksikAlan` listesi); sözleşme ise
ekranda çizilecek şeye göre kurulmuş (`muhatap` tek dize, `eksikler`
düzleştirilmiş). İkisini birbirine çeviren kod bir yerde toplanmazsa
her uç noktada yeniden yazılır ve zamanla ayrışır.

AD KAYMALARI — hepsi burada, başka yerde tekrar edilmiyor
----------------------------------------------------------
    sözleşme                        veri_yapisi
    eksikler[]                      icerik.eksik_alanlar
    eksik.karsi_taraftan_istenebilir  EksikAlan.talep_edilebilir
    taslak.govde                    CiktiYazi.metin
    taslak.sayi/tarih/imza_ad       YOK — daima null, EBYS atar
    yonlendirme.birim               Yonlendirme.hedef_birim
    yonlendirme.geregi_bilgi        Yonlendirme.dagitim_turu
    guven_kapisi.*                  Karar.*

KİŞİSEL VERİ MASKELEME SUNUCUDA
===============================
Ham değer arayüze hiç gitmiyor. `/varlik/{sira}/ham` ayrı bir uç nokta
ve her çağrısı işlem günlüğüne yazılıyor. Maskeli değerin `kanit_metin`i
de gönderilmiyor: gönderilse arayüz o metni belgede arar ve maskeleme
delinir.
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
if str(KOK / "src") not in sys.path:
    sys.path.insert(0, str(KOK / "src"))

from veri_yapisi import Dosya  # noqa: E402

SURUM = "2026-08-25-g"

# =============================================================================
# KANONİK DÜĞÜM TABLOSU
# =============================================================================
#
# Depoda ÜÇ farklı numaralandırma dolaşıyor ve üçü de birbirini tutmuyor:
#
#     ui/arayuz_sozlesmesi.md   12 düğüm   (eski akış diyagramı, ölü)
#     ui/sahte_sunucu.py        11 düğüm
#     boru_hatti._iz()           7 düğüm   adım no 1,2,3,4,11,9,12
#
# Bu tablo dördüncüsünü eklemiyor; ARAYÜZE GÖSTERİLEN tek tabloyu
# tanımlıyor ve `_iz()`'in yazdığı AJAN ADINA göre eşliyor. Numara
# yalnızca görüntü sırasıdır, kimlik değildir — adlar zaten benzersiz.
#
# Sekiz bileşen, iki ajan, dört tek atışlık LLM çağrısı. "Sekiz ajanımız
# var" demek şişirme olurdu; ajan yalnızca kendi döngüsünü kuran ikisi.

DUGUMLER: list[dict] = [
    {"no": 1, "ad": "okuyucu", "baslik": "Okuyucu",
     "aciklama": "PDF'ten metin ve konum çıkarır; taranmışsa OCR",
     "motor": "arac", "bilesen": 1, "bilesen_adi": "Okuyucu",
     "satir": 1, "ajan": None},
    {"no": 2, "ad": "ayristirici", "baslik": "Ayrıştırıcı",
     "aciklama": "Sayı, tarih, konu, muhatap, ilgi, imza alanlarına böler",
     "motor": "karma", "bilesen": 2, "bilesen_adi": "Ayrıştırıcı",
     "satir": 2, "ajan": None},
    {"no": 3, "ad": "anlama", "baslik": "Anlama",
     "aciklama": "Belge türü, SDP, talep ve varlıkları tek çağrıda çıkarır",
     "motor": "llm", "bilesen": 3, "bilesen_adi": "Anlama",
     "satir": 3, "ajan": None},
    {"no": 4, "ad": "denetci", "baslik": "Denetçi",
     "aciklama": "21 kural · şema, kural ve çıkarım katmanlarında eksikleri bulur",
     "motor": "karma", "bilesen": 4, "bilesen_adi": "Denetçi",
     "satir": 4, "ajan": "AJAN 1 · Denetçi"},
    {"no": 5, "ad": "ozetleyici", "baslik": "Özetleyici",
     "aciklama": "Tek atış · sayısal doğrulama, jeton eşleşmeli",
     "motor": "llm", "bilesen": 5, "bilesen_adi": "Özetleyici",
     "satir": 5, "ajan": None},
    {"no": 6, "ad": "yonlendirici", "baslik": "Yönlendirici",
     "aciklama": "Beş hat · %95'i LLM'siz; SDP tablosu veya muhatap satırı",
     "motor": "karma", "bilesen": 6, "bilesen_adi": "Yönlendirici",
     "satir": 6, "ajan": None},
    {"no": 7, "ad": "yazar", "baslik": "Yazar",
     "aciklama": "Kimlik, yön, taslak ve üslup döngüsü",
     "motor": "llm", "bilesen": 7, "bilesen_adi": "Yazar",
     "satir": 7, "ajan": "AJAN 2 · Yazar"},
    {"no": 8, "ad": "guven_kapisi", "baslik": "Güven Kapısı",
     "aciklama": "Beş girdi, hepsi VE ile · otomatik onay mı, insan mı",
     "motor": "arac", "bilesen": 8, "bilesen_adi": "Güven kapısı",
     "satir": 8, "ajan": None},
]

DUGUM_NO = {d["ad"]: d["no"] for d in DUGUMLER}
DUGUM_HARITASI = {d["no"]: d for d in DUGUMLER}

# Gerçek koşma sırası — tablo sırasıyla aynı. Özetleyici 2026-08-25'te
# `boru_hatti.isle()` içine alındı (Denetçi'den sonra); sunucunun onu
# ayrıca çağırdığı geçici çözüm kaldırıldı.
KOSMA_SIRASI: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7, 8)

# Boru hattı bittiğinde kesin olarak koşmuş sayılmayan adımlar.
# `istemci=None` kipinde Anlama ve Yazar atlanıyor.
ATLANABILIR = {3, 7}

# `Onem` -> sözleşme `EksikOnem`. Değerler zaten aynı; eşleme, ikisi
# ayrışırsa sessiz kalmasın diye açıkça yazılı.
ONEM = {"hata": "hata", "uyari": "uyari", "bilgi": "bilgi"}

# ÜÇ AYRI GİRDİ TİPİ SÖZCÜĞÜ — hepsi burada buluşuyor.
#
#   okuyucu.OkumaSonucu.girdi_tipi   metin_katmanli | taranmis | bos
#   veri_yapisi.GirdiTipi            pdf_metinli | pdf_tarama | goruntu |
#                                    duz_metin | docx
#   sözleşme (tipler.ts GirdiTipi)   metin_katmanli | taranmis | duz_metin
#
# Eşlemesiz atama sessizce düşüyordu: `KaynakBilgisi` `validate_assignment`
# açık ve "metin_katmanli" `GirdiTipi`de yok, dolayısıyla alan varsayılan
# `duz_metin`de kalıyor ve arayüz her belgeyi "düz metin" gösteriyordu.
GIRDI_TIPI = {
    "metin_katmanli": "pdf_metinli",
    "taranmis": "pdf_tarama",
    "goruntu": "goruntu",
    "bos": "duz_metin",
}

# Şema değeri -> sözleşme değeri (arayüzün etiket haritasındaki anahtarlar).
GIRDI_TIPI_SOZLESME = {
    "pdf_metinli": "metin_katmanli",
    "pdf_tarama": "taranmis",
    "goruntu": "taranmis",
    "duz_metin": "duz_metin",
    "docx": "duz_metin",
}

DURUM_ETIKET = {
    "ALINDI": "Alındı", "ISLENIYOR": "İşleniyor",
    "INSAN_ONAYI_BEKLIYOR": "İnsan onayı bekliyor",
    "EKSIK_BILGI_BEKLIYOR": "Eksik bilgi bekliyor",
    "OTOMATIK_ONAYLANDI": "Otomatik onaylandı", "ONAYLANDI": "Onaylandı",
    "REDDEDILDI": "Reddedildi", "HATA": "Hata",
}

SONUCLANMIS = ("ONAYLANDI", "REDDEDILDI", "OTOMATIK_ONAYLANDI")
ACIK = ("INSAN_ONAYI_BEKLIYOR", "EKSIK_BILGI_BEKLIYOR")


# =============================================================================
# Küçük yardımcılar
# =============================================================================


def _d(deger) -> str | None:
    """Enum, tarih ve None'ı arayüzün okuyabileceği dizeye çevirir."""
    if deger is None:
        return None
    if isinstance(deger, (date, datetime)):
        return deger.isoformat()
    metin = str(deger).strip()
    return metin or None


def _iso(deger) -> str | None:
    return deger.isoformat() if isinstance(deger, (date, datetime)) else None


def _ts(zaman) -> float:
    """datetime -> unix saniye. Arayüz her yerde saniye bekliyor."""
    return zaman.timestamp() if isinstance(zaman, datetime) else 0.0


# =============================================================================
# Üstveri alanları
# =============================================================================


def alan(dosya: Dosya, yol: str, deger=None) -> dict:
    """Sözleşme 5.6.3'teki beş parçalı alan kutusu.

    `guven` ve `yontem` uydurulmuyor: `dosya.kanit` haritasından geliyor.
    Kanıt yoksa güven 0.0 ve yöntem null — "bilmiyoruz" görünür kalıyor.
    """
    ham = deger if deger is not None else dosya.deger_al(yol)
    metin = _d(ham)
    k = dosya.kanit.get(yol)
    konum = getattr(k, "konum", None) if k else None
    return {
        "deger": metin,
        "guven": float(getattr(k, "guven", 0.0) or 0.0) if metin else 0.0,
        "yontem": _d(getattr(k, "yontem", None)) if k else None,
        # `kutu` Parça 5'e ertelendi; sözleşme 8.3 gereği daima null.
        "kanit": {"sayfa": getattr(konum, "sayfa", 1) or 1, "kutu": None} if metin else None,
        "kanit_metin": getattr(k, "alinti", None) if k else None,
    }


def _taraf_metni(taraf) -> str | None:
    """Muhatap/gönderen satırının ekranda görünecek hâli."""
    if taraf is None:
        return None
    for ad in ("ham", "idare", "birim", "ad"):
        deger = getattr(taraf, ad, None)
        if deger:
            return str(deger)
    return None


def ustveri_sun(dosya: Dosya) -> dict:
    """Sekiz üstveri alanı. İsimler sözleşmeden, değerler şemadan."""
    u = dosya.ustveri
    ilgi = "; ".join(x.ham for x in (u.ilgi or []) if getattr(x, "ham", None))
    ekler = "; ".join(x.ham for x in (u.ekler or []) if getattr(x, "ham", None))
    dagitim = "; ".join(x.hedef for x in (u.dagitim or []) if getattr(x, "hedef", None))

    imza_parcalari = [x for x in (getattr(u.imza, "ad", None),
                                  getattr(u.imza, "unvan", None)) if x]
    imza = " — ".join(imza_parcalari) or getattr(u.imza, "ham", None)

    return {
        "sayi": alan(dosya, "ustveri.sayi"),
        "tarih": alan(dosya, "ustveri.tarih", u.tarih_metin or u.tarih),
        "konu": alan(dosya, "ustveri.konu"),
        "muhatap": alan(dosya, "ustveri.muhatap", _taraf_metni(u.muhatap)),
        "ilgi": alan(dosya, "ustveri.ilgi", ilgi),
        "imza": alan(dosya, "ustveri.imza", imza),
        "ek": alan(dosya, "ustveri.ekler", ekler),
        "dagitim": alan(dosya, "ustveri.dagitim", dagitim),
    }


# =============================================================================
# Varlıklar — maskeleme
# =============================================================================


def maskele(tur: str, deger: str) -> str:
    """Ham değer arayüze hiç gitmez; maskeleme burada yapılır."""
    if not deger:
        return ""
    if tur in ("kisi", "ad_soyad"):
        return " ".join(
            (p[0] + "*" * max(1, len(p) - 1)) if p else p for p in deger.split()
        )
    if tur in ("telefon", "tckn", "iban", "plaka", "vergi_no"):
        goster = 3 if len(deger) > 6 else 1
        return deger[:goster] + "*" * max(1, len(deger) - goster - 2) + deger[-2:]
    if tur == "eposta":
        ad, _, kalan = deger.partition("@")
        return (ad[:2] + "*" * max(1, len(ad) - 2)) + ("@" + kalan if kalan else "")
    if tur == "adres":
        parcalar = deger.split()
        return " ".join(parcalar[:2] + ["***"]) if len(parcalar) > 2 else "***"
    if tur == "dogum_tarihi":
        return deger[:4] + "-**-**" if len(deger) >= 4 else "***"
    return deger[0] + "*" * max(1, len(deger) - 1)


def varlik_sun(varlik, sira: int) -> dict:
    """`sira` alanı `/varlik/{sira}/ham` çağrısı için gerekli."""
    tur = _d(varlik.tip) or "bilinmiyor"
    pii = bool(varlik.kisisel_veri)
    deger = varlik.maskeli_deger or maskele(tur, varlik.deger) if pii else varlik.deger
    konum = varlik.konum
    return {
        "sira": sira,
        "tur": tur,
        "deger": deger,
        # Varlıklar Anlama'nın tek çağrısından geliyor; alan başına ayrı
        # güven yok. 0.0 yerine sınıflandırmanın güveni yazılmıyor —
        # başka bir alanın güvenini buraya taşımak uydurma olurdu.
        "guven": 0.0,
        "pii": pii,
        "maskelendi": pii,
        "kanit": {"sayfa": getattr(konum, "sayfa", 1) or 1, "kutu": None} if konum else None,
        # Maskeli değerin kanıt metni GÖNDERİLMEZ; gönderilse arayüz onu
        # metinde arar ve maskeleme delinir.
        "kanit_metin": None if pii else None,
    }


# =============================================================================
# Bölümler
# =============================================================================


def eksikler_sun(dosya: Dosya) -> list[dict]:
    return [
        {
            "alan": e.alan,
            "onem": ONEM.get(_d(e.onem) or "uyari", "uyari"),
            "katman": _d(e.katman) or "cikarim",
            "dayanak": e.dayanak or (e.kural_id or ""),
            "aciklama": e.aciklama,
            "soru": e.soru or e.aciklama,
            "karsi_taraftan_istenebilir": bool(e.talep_edilebilir),
            "giderildi": bool(e.giderildi),
            "cevap": e.cevap,
        }
        for e in (dosya.icerik.eksik_alanlar or [])
    ]


def mevzuat_sun(dosya: Dosya) -> list[dict]:
    return [
        {
            "mevzuat_adi": m.mevzuat_adi,
            "madde": m.madde or "",
            "baslik": "",
            "alinti": m.alinti or "",
            "gerekce": m.kural_id or "",
            "benzerlik": float(m.benzerlik or 0.0),
            "dogrulandi": bool(m.dogrulandi),
        }
        for m in (dosya.mevzuat or [])
    ]


def taslak_sun(yazi) -> dict | None:
    """`CiktiYazi` -> sözleşme `Taslak`.

    `sayi`, `tarih` ve `imza_ad` DAİMA null. Şemada karşılıkları yok ve
    bu kasıtlı: EBYS'de kayıt ve imza anında atanıyorlar.
    """
    if yazi is None or not (yazi.metin or "").strip():
        return None
    return {
        "baslik": yazi.baslik or "",
        "sayi": None,
        "tarih": None,
        "konu": yazi.konu or "",
        "muhatap": yazi.muhatap or "",
        "govde": yazi.metin or "",
        "imza_ad": None,
        "imza_unvan": yazi.imza_unvan or "",
    }


def uslup_sun(yazi, ic_bulgular: list[dict] | None = None) -> list[dict]:
    """Üslup bulguları — kural motoru raporu ARTI Yazar'ın iç denetimi.

    Yazar'ın üslup döngüsü bulguları düzeltip yeniden koşuyor; `linter_raporu`
    SON turun raporu. Dolayısıyla orada duran her bulgu ÇÖZÜLEMEYENDİR.

    İÇ DENETİM BULGULARI RAPORDA YOK — bilerek
    ------------------------------------------
    `yaz()` YZ-01/YZ-02'yi `linter_raporu`na yazmıyor; o rapor
    `kurallar.json` kimlikleriyle eşleşiyor ve uydurma kimlik onu
    güvenilmez kılardı. Ama bu bulgular döngüyü tetikleyip belgeyi insana
    tırmandırabiliyor. Yalnızca raporu göstermek, eskalasyonun SEBEBİNİ
    gizlemek olurdu — sunucu onları ayrıca taşıyor.
    """
    if yazi is None:
        return list(ic_bulgular or [])
    rapordan = [
        {
            "kural_no": b.kural_id,
            "duzey": ONEM.get(_d(b.onem) or "uyari", "uyari"),
            "mesaj": b.baslik,
            "mevzuat": b.dayanak or "",
            "aciklama": b.aciklama,
            "alinti": b.alinti,
            "oneri": b.duzeltme_onerisi,
            "cozuldu": False,
        }
        for b in (yazi.linter_raporu.bulgular or [])
    ]
    return rapordan + list(ic_bulgular or [])


def yonlendirme_sun(dosya: Dosya, birim_adi) -> dict | None:
    y = dosya.yonlendirme
    if not y or not y.hedef_birim:
        return None
    return {
        "birim": y.hedef_birim,
        "birim_adi": birim_adi(y.hedef_birim) or y.hedef_birim,
        "skor": float(y.skor or 0.0),
        "geregi_bilgi": _d(y.dagitim_turu) or "geregi",
        "gerekce": y.gerekce or "",
        "kanit_cumle": y.kanit_cumle or "",
        "kaynak": _d(y.kaynak) or "bilinmiyor",
        "alternatifler": [],
        "alternatif_adaylar": [
            {"birim": a.birim,
             "birim_adi": a.birim_adi or birim_adi(a.birim) or a.birim,
             "skor": float(a.skor or 0.0)}
            for a in (y.alternatif_adaylar or [])
        ],
        "kurum_disinda": bool(y.kurum_disinda),
    }


def kapi_sun(dosya: Dosya) -> dict:
    """`Karar` -> sözleşme `guven_kapisi`.

    `sebep` sebeplerin birleşimi. Boşsa "eşiğin üstünde" yazılmıyor —
    kapının kendi cümlesi yoksa uydurulmuyor, kısa bir olgu yazılıyor.
    """
    k = dosya.karar
    return {
        "mod": "OTOMATIK" if k.otomatik_onay else "INSAN",
        "skor": float(k.toplam_guven or 0.0),
        "esik": float(k.esik or 0.85),
        "sebep": " · ".join(k.sebepler) if k.sebepler else
                 (f"Toplam güven {k.toplam_guven:.2f}, eşik {k.esik:.2f}."),
    }


def talep_sun(talep) -> dict | None:
    """`EksikBilgiTalebi` -> sözleşme.

    `sure_gun`, `son_tarih` ve `kanal` BOŞ GELEBİLİR ve bu kasıtlı:
    süreyi mevzuat verir, `yazar._talep_kur` onu uydurmuyor. Arayüz
    null'a dayanıklı olmalı.
    """
    if talep is None:
        return None
    return {
        "ts": _ts(talep.zaman),
        "muhatap_ad": talep.muhatap_ad or "",
        "muhatap_turu": ("gercek_kisi"
                         if _d(talep.muhatap_turu) == "gercek_kisi" else "kurum"),
        "kanal": talep.kanal,
        "sure_gun": talep.sure_gun,
        "son_tarih": _iso(talep.son_tarih),
        "dayanak": talep.dayanak or "",
        "sorular": list(talep.sorular or []),
        "yazi": taslak_sun(talep.yazi),
        "elle_duzenlendi": bool(talep.elle_duzenlendi),
    }


def cevap_sun(cevap) -> dict | None:
    if cevap is None:
        return None
    return {
        "ts": _ts(cevap.zaman),
        "gonderen": cevap.gonderen or "",
        "ilgi": cevap.ilgi or "",
        "cevaplar": [{"soru": c.get("soru", ""), "cevap": c.get("cevap", "")}
                     for c in (cevap.cevaplar or [])],
    }


def duzeltmeler_sun(dosya: Dosya) -> list[dict]:
    return [
        {"tur": x.tur, "rol": x.rol, "ts": _ts(x.zaman),
         "alanlar": list(x.alanlar or []), "gerekce": x.gerekce}
        for x in (dosya.duzeltmeler or [])
    ]


# =============================================================================
# Düğüm kayıtları — akış ekranı
# =============================================================================


def adim_ciktisi(dosya: Dosya, no: int) -> dict | None:
    """Bir adımın `Dosya`ya yazdığı bölüm. Yan panelin "ham çıktı" kutusu.

    `sahte_sunucu.ADIM_CIKTISI`nın gerçek karşılığı. Değerler `Dosya`dan
    okunuyor, ayrıca saklanmıyor: iki kopya zamanla ayrışır.
    """
    u = dosya.ustveri
    if no == 1:
        return {"girdi_tipi": _d(dosya.kaynak.girdi_tipi),
                "sayfa_sayisi": dosya.kaynak.sayfa_sayisi,
                "karakter": len(dosya.kaynak.ham_metin or "")}
    if no == 2:
        return {"sayi": _d(u.sayi), "tarih": _d(u.tarih), "konu": _d(u.konu),
                "muhatap": _taraf_metni(u.muhatap),
                "ilgi_sayisi": len(u.ilgi or []), "ek_sayisi": len(u.ekler or []),
                "govde_karakter": len(dosya.metin or "")}
    if no == 3:
        return {"belge_turu": _d(dosya.siniflandirma.belge_turu),
                "sdp_kodu": _d(dosya.siniflandirma.sdp.kod),
                "talep": dosya.icerik.talep,
                "varlik_sayisi": len(dosya.icerik.varliklar or [])}
    if no == 4:
        return {"eksik_sayisi": len(dosya.icerik.eksik_alanlar or []),
                "kritik": len(dosya.icerik.kritik_eksikler),
                "mevzuat_sayisi": len(dosya.mevzuat or [])}
    if no == 5:
        return {"ozet_karakter": len(dosya.icerik.ozet or ""),
                "ozet": (dosya.icerik.ozet or "")[:400]}
    if no == 6:
        y = dosya.yonlendirme
        return {"hedef_birim": y.hedef_birim, "skor": y.skor,
                "kaynak": _d(y.kaynak), "aday_sayisi": len(y.alternatif_adaylar or [])}
    if no == 7:
        c = dosya.cikti_yazi
        return {"tur": _d(c.tur), "konu": c.konu,
                "metin_karakter": len(c.metin or ""),
                "linter_bulgu": len(c.linter_raporu.bulgular or []),
                "denetlenen_kural": c.linter_raporu.denetlenen_kural_sayisi}
    if no == 8:
        k = dosya.karar
        return {"otomatik_onay": k.otomatik_onay, "toplam_guven": k.toplam_guven,
                "esik": k.esik, "sebepler": k.sebepler}
    return None


def dugum_kayitlari_sun(dosya: Dosya, tur_sayisi: int = 1) -> list[dict]:
    """`dosya.iz` -> sözleşme `dugum_kayitlari`.

    `_iz()` `tur_no`, `gerekce` ve `cikti` yazmıyor; üçü de burada
    türetiliyor:
        gerekce  <- IzKaydi.ozet   (adımın kendi tek satırlık özeti)
        cikti    <- adim_ciktisi() (Dosya'nın o adıma ait bölümü)
        tur_no   <- Yazar için linter tur sayısı, diğerlerinde 1
    """
    kayitlar = []
    for iz in dosya.iz:
        no = DUGUM_NO.get(iz.ajan)
        if no is None:
            continue
        kayitlar.append({
            "no": no,
            "ad": iz.ajan,
            "tur_no": tur_sayisi if no == DUGUM_NO["yazar"] else 1,
            "durum": "tamam" if iz.basarili else "hata",
            "sure_ms": round(iz.sure_ms),
            "guven": iz.guven,
            "gerekce": iz.hata or iz.ozet,
            "cikti": adim_ciktisi(dosya, no),
        })
    return kayitlar


# =============================================================================
# Tam evrak ve liste özeti
# =============================================================================


def evrak_sun(kayit: dict, birim_adi) -> dict:
    """`GET /api/evrak/{id}` gövdesi.

    `kayit` sunucunun tuttuğu sarmalayıcı: `dosya` (Dosya) artı koşuya
    ait olup şemaya girmeyen alanlar (yüklenme zamanı, günlük, sevk).
    """
    d: Dosya = kayit["dosya"]
    u = d.ustveri
    sdp = d.siniflandirma.sdp

    return {
        "evrak_id": d.evrak_id,
        "calisma_id": kayit["calisma_id"],
        "dosya_adi": kayit["dosya_adi"],
        "yuklenme_ts": kayit["yuklenme_ts"],
        "durum": _d(d.durum),
        "toplam_ms": round(kayit.get("toplam_ms") or d.karar.toplam_sure_ms or 0),
        "sayfa_sayisi": d.kaynak.sayfa_sayisi,
        "karakter": len(d.kaynak.ham_metin or "") or None,
        "girdi_tipi": GIRDI_TIPI_SOZLESME.get(_d(d.kaynak.girdi_tipi) or "", "duz_metin"),

        "dugum_kayitlari": dugum_kayitlari_sun(d, kayit.get("linter_tur", 1)),

        "ustveri": ustveri_sun(d),
        "belge_turu": {
            "deger": _d(d.siniflandirma.belge_turu) or "bilinmiyor",
            "guven": float(getattr(
                d.kanit.get("siniflandirma.belge_turu"), "guven", 0.0) or 0.0),
            "gerekce": d.siniflandirma.gerekce or "",
        },
        "sdp": ({"kod": sdp.kod, "ad": sdp.ad or "",
                 "kaynak_sayidan_mi": bool(sdp.kaynak_sayidan_mi)}
                if sdp.kod else None),
        "varliklar": [varlik_sun(v, i + 1)
                      for i, v in enumerate(d.icerik.varliklar or [])],
        "talep": d.icerik.talep,
        "ozet": d.icerik.ozet,
        "eksikler": eksikler_sun(d),
        "mevzuat": mevzuat_sun(d),
        "karar": ({"uretilecek_tur": _d(d.cikti_yazi.tur) or "",
                   "gerekce": d.cikti_yazi.tur_gerekcesi or "",
                   "taslak_gerekli": _d(d.cikti_yazi.tur) != "taslak_gerekmez"}
                  if d.cikti_yazi.tur else None),
        "taslak": taslak_sun(d.cikti_yazi),
        "uslup_bulgulari": uslup_sun(d.cikti_yazi, kayit.get("ic_bulgular")),
        "linter_tur_sayisi": kayit.get("linter_tur"),
        # Döngü pes etti mi. `linter_tur_sayisi` tek başına yanıltıyor:
        # 2 tur "ikinci turda geçti" de olabilir, "iki turda düzeltemedi"
        # de. İkisi arayüzde aynı rozeti üretiyordu.
        "linter_pes_edildi": bool(kayit.get("linter_pes")),
        "yonlendirme": yonlendirme_sun(d, birim_adi),
        "guven_kapisi": kapi_sun(d),

        "gunluk": list(kayit.get("gunluk") or []),
        "duzeltmeler": duzeltmeler_sun(d),
        "eksik_bilgi_talebi": talep_sun(d.eksik_bilgi_talebi),
        "eksik_bilgi_cevabi": cevap_sun(d.eksik_bilgi_cevabi),

        # Sözleşmeye EKLEME. Arayüz bilmiyorsa yok sayar; bilen sürüm
        # gelen/giden defterini ve birimler arası sevki buradan okur.
        "sevk": kayit.get("sevk"),
        "defter_kaydi": kayit.get("defter_kaydi"),
    }


def ozet_sun(kayit: dict, birim_adi) -> dict:
    """`GET /api/evrak` liste satırı."""
    import time

    d: Dosya = kayit["dosya"]
    eksikler = d.icerik.eksik_alanlar or []
    y = d.yonlendirme
    k = d.karar
    sevk = kayit.get("sevk") or {}
    birim = sevk.get("bulundugu_birim") or y.hedef_birim

    return {
        "evrak_id": d.evrak_id,
        "dosya_adi": kayit["dosya_adi"],
        "durum": _d(d.durum),
        "yuklenme_ts": kayit["yuklenme_ts"],
        "bekleme_sn": int(time.time() - kayit["yuklenme_ts"]),
        "toplam_ms": round(kayit.get("toplam_ms") or 0),
        "sayi": _d(d.ustveri.sayi),
        "konu": _d(d.ustveri.konu),
        "belge_turu": _d(d.siniflandirma.belge_turu),
        "birim": birim,
        "birim_adi": birim_adi(birim) if birim else None,
        "guven": float(k.toplam_guven or 0.0),
        "esik": float(k.esik or 0.85),
        "sebep": " · ".join(k.sebepler) if k.sebepler else "",
        "eksik_sayisi": len(eksikler),
        "kritik_eksik_sayisi": sum(
            1 for e in eksikler if _d(e.onem) == "hata" and not e.giderildi),
        "duzeltme_sayisi": len(d.duzeltmeler or []),
    }
