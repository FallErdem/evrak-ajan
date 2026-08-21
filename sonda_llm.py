"""LLM sağlayıcı sondası — Anlama'yı yazmadan önce dört şeyi ölçer.

NEREYE:  depo kökü
NASIL:   python sonda_llm.py
ÇIKTI:   ekrana + sonda_llm_sonuc.txt

NEDEN VAR
---------
Parça 1'de verilen iki karar yerel Ollama'da ölçülmüştü:
    K-06  enum kısıtlı şema güvenilir
    K-07  think: false
Yapılandırma artık Gemini 3.6 Flash'a bakıyor. Gemini'nin OpenAI uyumlu
katmanında "think" diye bir parametre YOK, şema da farklı bir alanla
(response_format) geçiyor. Yani iki karar da BAŞKA BİR SİSTEMDE ölçülmüş
sayılır ve devralınamaz.

Bu sonda onları yeniden ölçer. Anlama'nın istemi buna göre yazılacak.

NE ÖLÇER
--------
1  Düz çağrı çalışıyor mu           anahtar, adres, model doğru mu
2  response_format geçiyor mu       şema zorlaması destekleniyor mu
3  Enum kısıtı tutuyor mu           11 belge türü dışına çıkıyor mu
4  Gecikme ve maliyet               300 belgelik koşu kaça mal olur

HİÇBİR ŞEY VARSAYILMAZ. Her testin çıktısı ham hâliyle basılır; başarısız
olan test için ne yapılacağı da yazılır.

MALİYET
-------
Bu sonda 6-8 çağrı yapar. Tam koşudan çok daha ucuzdur ve tam koşunun
maliyetini önceden söyler — asıl amacı da budur.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK / "src"))

YAPILANDIRMA = KOK / "yapilandirma.json"

ARAMA_YERLERI = (
    ("deneyler", "adim4", "belgeler_pdf"),
    ("veri", "belgeler"),
    ("ornek", "okuma_ornegi"),
)

# Sonda hangi belgelerle çalışsın. Biri kurum yazısı, biri dilekçe olmalı;
# ikisi de metin katmanlı seçildi — burada OCR'ı değil MODELİ ölçüyoruz.
BELGELER = ("003", "006")

# Tam koşu büyüklüğü — maliyet kestirimi için.
# 300 belge x tipik 5 çağrı (kalan_plan_8_gun.md, 8 bileşen tablosu).
TAM_KOSU_CAGRI = 300 * 5


def klasor_bul() -> Path | None:
    for p in ARAMA_YERLERI:
        y = KOK.joinpath(*p)
        if y.exists() and any(y.glob("belge_*.pdf")):
            return y
    for b in KOK.rglob("belge_*.pdf"):
        return b.parent
    return None


def belge_turleri() -> list[str]:
    """11 belge türünü kaynaktan okur — elle yazılmaz.

    Önce veri_yapisi.py'deki dondurulmuş enum denenir; bulunamazsa
    kota.json'daki belge_turleri bölümüne düşülür. İkisi de yoksa durur:
    türleri hafızadan yazmak PARCA2_DEVIR_NOTLARI 4.2'nin yasakladığı şey.
    """
    try:
        import enum

        import veri_yapisi

        for ad in dir(veri_yapisi):
            nesne = getattr(veri_yapisi, ad)
            if isinstance(nesne, type) and issubclass(nesne, enum.Enum):
                degerler = [u.value for u in nesne]
                if "dilekce" in degerler:
                    print(f"  belge türleri kaynağı: veri_yapisi.{ad}")
                    return degerler
    except Exception as hata:  # noqa: BLE001
        print(f"  veri_yapisi okunamadı ({hata}), kota.json'a düşülüyor")

    for aday in (KOK / "veri" / "kota.json", KOK / "kota.json"):
        if aday.exists():
            k = json.loads(aday.read_text(encoding="utf-8"))["belge_turleri"]
            turler = [t for bolum in k.values() if isinstance(bolum, dict)
                      for t in bolum if not t.startswith("_") and t != "toplam"]
            print(f"  belge türleri kaynağı: {aday}")
            return turler

    sys.exit("Belge türleri bulunamadı. veri_yapisi.py veya kota.json gerekli.")


def govde_al(klasor: Path | None, no: str) -> str | None:
    if klasor is None:
        return None
    pdf = klasor / f"belge_{no}.pdf"
    if not pdf.exists():
        return None
    from okuyucu import oku

    r = oku(str(pdf))
    if r.hata or not r.ayrilmis:
        return None
    return r.ayrilmis.govde


def kisalt(s: str, n: int = 400) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[:n] + " …"


def main() -> int:
    from llm_istemci import istemci_olustur

    satirlar: list[str] = []

    def yaz(s: str = "") -> None:
        print(s)
        satirlar.append(s)

    yaz("=" * 72)
    yaz("LLM SAGLAYICI SONDASI")
    yaz("=" * 72)

    y = json.loads(YAPILANDIRMA.read_text(encoding="utf-8"))
    yaz(f"  base_url         : {y.get('base_url')}")
    yaz(f"  model            : {y.get('model')}")
    yaz(f"  ek_parametreler  : {json.dumps(y.get('ek_parametreler'), ensure_ascii=False)}")
    yaz()

    try:
        istemci = istemci_olustur(YAPILANDIRMA)
    except Exception as hata:  # noqa: BLE001
        yaz(f"ISTEMCI KURULAMADI: {type(hata).__name__}: {hata}")
        yaz("\nMuhtemel sebep: .gizli/api_anahtari.txt yok veya bos.")
        (KOK / "sonda_llm_sonuc.txt").write_text("\n".join(satirlar), encoding="utf-8")
        return 1

    turler = belge_turleri()
    yaz(f"  {len(turler)} belge türü: {', '.join(turler)}")
    yaz()

    klasor = klasor_bul()
    metinler: dict[str, str] = {}
    for no in BELGELER:
        g = govde_al(klasor, no)
        if g:
            metinler[no] = g
    if not metinler:
        yaz("UYARI: belge okunamadi, gomulu ornek metinle devam ediliyor.")
        metinler["gomulu"] = (
            "YENİMAHALLE BELEDİYE BAŞKANLIĞINA\n"
            "(Temizlik İşleri Müdürlüğü)\n"
            "İlgi'de kayıtlı yazıda Başvuru Cevabının Gönderilmesi talebine yer "
            "verilmiştir. Yapılan değerlendirme sonucunda talep olumlu "
            "karşılanmıştır. İstenen kayıtlar derlenerek hazırlanmıştır. "
            "Konuyla ilgili irtibat Kaymakamlığımızca sağlanmakta olup "
            "bilgilerini ve gereğini rica ederim."
        )

    yaz(f"  sonda belgeleri: {', '.join(metinler)}")
    yaz()

    sistem = (
        "Sen Türk kamu kurumlarının resmî yazışmalarını inceleyen bir "
        "sınıflandırıcısın. Yalnızca belgede yazan bilgiyi kullan. "
        "Emin değilsen 'bilinmiyor' de; tahmin uydurma."
    )

    sema = {
        "type": "json_schema",
        "json_schema": {
            "name": "belge_analizi",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "belge_turu": {"type": "string", "enum": turler + ["bilinmiyor"]},
                    "guven": {"type": "number"},
                    "gerekce": {"type": "string"},
                },
                "required": ["belge_turu", "guven", "gerekce"],
                "additionalProperties": False,
            },
        },
    }

    sonuclar: dict[str, bool] = {}

    # -- 1 -------------------------------------------------------------------
    yaz("-" * 72)
    yaz("1  DUZ CAGRI")
    yaz("-" * 72)
    ilk = next(iter(metinler.values()))
    try:
        c = istemci.metin_uret(
            "Bu belgenin konusunu tek cümleyle yaz:\n\n" + ilk[:2000],
            sistem_istemi=sistem,
        )
        yaz(f"  cevap   : {kisalt(c.metin, 200)}")
        yaz(f"  sure    : {c.sure_ms:.0f} ms   bitis: {c.bitis_sebebi}")
        yaz(f"  token   : {c.token}")
        sonuclar["duz cagri"] = True
    except Exception as hata:  # noqa: BLE001
        yaz(f"  BASARISIZ: {type(hata).__name__}: {hata}")
        yaz("  -> Adres, model adi veya anahtar yanlis. Devami anlamsiz.")
        (KOK / "sonda_llm_sonuc.txt").write_text("\n".join(satirlar), encoding="utf-8")
        return 1
    yaz()

    # -- 2 -------------------------------------------------------------------
    yaz("-" * 72)
    yaz("2  SEMA ZORLAMASI  (response_format)")
    yaz("-" * 72)
    sema_calisiyor = False
    try:
        c = istemci.metin_uret(
            "Bu belgeyi sınıflandır:\n\n" + ilk[:2000],
            sistem_istemi=sistem,
            ek={"response_format": sema},
        )
        yaz(f"  ham cevap: {kisalt(c.metin, 300)}")
        try:
            veri = json.loads(c.metin)
            yaz(f"  JSON     : GECERLI  {json.dumps(veri, ensure_ascii=False)}")
            eksik = [a for a in ("belge_turu", "guven", "gerekce") if a not in veri]
            yaz(f"  alanlar  : {'TAM' if not eksik else 'EKSIK ' + str(eksik)}")
            sema_calisiyor = not eksik
        except json.JSONDecodeError:
            yaz("  JSON     : GECERSIZ — model duz metin dondurdu")
            yaz("  -> response_format yok sayilmis olabilir. Testi 2b cozecek.")
    except Exception as hata:  # noqa: BLE001
        yaz(f"  BASARISIZ: {type(hata).__name__}: {hata}")
        yaz("  -> Saglayici bu alani kabul etmiyor.")
    sonuclar["sema zorlamasi"] = sema_calisiyor
    yaz()

    # -- 2b ------------------------------------------------------------------
    if not sema_calisiyor:
        yaz("-" * 72)
        yaz("2b  YEDEK: sema istemin icinde")
        yaz("-" * 72)
        istem = (
            "Bu belgeyi sınıflandır. YALNIZCA aşağıdaki biçimde JSON döndür, "
            "başka hiçbir şey yazma, kod bloğu kullanma:\n"
            '{"belge_turu": "<liste>", "guven": <0-1>, "gerekce": "<kısa>"}\n'
            f"belge_turu şu listeden biri olmalı: {', '.join(turler)}, bilinmiyor\n\n"
            + ilk[:2000]
        )
        try:
            c = istemci.metin_uret(istem, sistem_istemi=sistem)
            temiz = c.metin.strip().removeprefix("```json").removeprefix("```")
            temiz = temiz.removesuffix("```").strip()
            yaz(f"  ham cevap: {kisalt(c.metin, 300)}")
            try:
                veri = json.loads(temiz)
                yaz(f"  JSON     : GECERLI  {json.dumps(veri, ensure_ascii=False)}")
                sonuclar["yedek sema"] = True
            except json.JSONDecodeError:
                yaz("  JSON     : GECERSIZ")
                sonuclar["yedek sema"] = False
        except Exception as hata:  # noqa: BLE001
            yaz(f"  BASARISIZ: {type(hata).__name__}: {hata}")
            sonuclar["yedek sema"] = False
        yaz()

    # -- 3 -------------------------------------------------------------------
    yaz("-" * 72)
    yaz("3  ENUM KISITI  (K-06 yeniden olcumu)")
    yaz("-" * 72)
    yaz("  Her belge icin donen belge_turu listede mi.")
    disari_cikan = 0
    denenen = 0
    for no, metin in metinler.items():
        try:
            if sema_calisiyor:
                c = istemci.metin_uret(
                    "Bu belgeyi sınıflandır:\n\n" + metin[:2000],
                    sistem_istemi=sistem, ek={"response_format": sema})
            else:
                c = istemci.metin_uret(
                    "Bu belgeyi sınıflandır. YALNIZCA JSON döndür:\n"
                    '{"belge_turu": "...", "guven": 0.0, "gerekce": "..."}\n'
                    f"belge_turu su listeden biri: {', '.join(turler)}, bilinmiyor\n\n"
                    + metin[:2000], sistem_istemi=sistem)
            temiz = c.metin.strip().removeprefix("```json").removeprefix("```")
            temiz = temiz.removesuffix("```").strip()
            tur = json.loads(temiz).get("belge_turu")
            denenen += 1
            icinde = tur in turler or tur == "bilinmiyor"
            if not icinde:
                disari_cikan += 1
            yaz(f"  belge_{no}: {str(tur):20s} {'LISTEDE' if icinde else 'LISTE DISI'}"
                f"   {c.sure_ms:.0f} ms")
        except Exception as hata:  # noqa: BLE001
            yaz(f"  belge_{no}: HATA {type(hata).__name__}: {hata}")
    sonuclar["enum kisiti"] = denenen > 0 and disari_cikan == 0
    yaz()

    # -- 4 -------------------------------------------------------------------
    yaz("-" * 72)
    yaz("4  GECIKME VE MALIYET")
    yaz("-" * 72)
    yaz(f"  {istemci.ozet()}")
    n = istemci.cagri_sayisi or 1
    cagri_basi = istemci.toplam_token / n
    yaz(f"\n  cagri basi ortalama token : {cagri_basi:.0f}")
    yaz(f"  tam kosu ({TAM_KOSU_CAGRI} cagri) : "
        f"{cagri_basi * TAM_KOSU_CAGRI / 1_000_000:.2f} milyon token")
    yaz("\n  Fiyati saglayicinin sayfasindan bakip carpin. Rakam kabul")
    yaz("  edilemezse once ek_parametreler.reasoning_effort'u dusurun,")
    yaz("  sonra istemi kisaltin. Model degistirmek EN SON care.")
    yaz()

    # -- ozet ----------------------------------------------------------------
    yaz("=" * 72)
    yaz("OZET")
    yaz("=" * 72)
    for ad, gecti in sonuclar.items():
        yaz(f"  {ad:20s} {'GECTI' if gecti else 'KALDI'}")
    yaz()
    if sonuclar.get("sema zorlamasi"):
        yaz("  KARAR: Anlama response_format ile yazilir. Ayristirma gerekmez.")
    elif sonuclar.get("yedek sema"):
        yaz("  KARAR: Anlama istem ici sema ile yazilir; cevap kod blogundan")
        yaz("         temizlenip ayristirilir, bozuksa bir kez tekrar sorulur.")
    else:
        yaz("  KARAR: Yapisal cikti alinamiyor. Once bunu cozun; Anlama'yi")
        yaz("         serbest metinden ayristirmak kirilgan olur.")
    yaz()
    yaz(textwrap.fill(
        "Bu sonda hafizadan degil olcumden karar uretir. Ciktisi karar "
        "kaydina K-06 ve K-07'nin Gemini icin yeniden olculmus hali olarak "
        "islenmelidir.", 72))

    (KOK / "sonda_llm_sonuc.txt").write_text("\n".join(satirlar), encoding="utf-8")
    print(f"\nTam cikti: {KOK / 'sonda_llm_sonuc.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
