"""Boru hattını uçtan uca ölçer ve DÜĞÜM SIRASINI sınar.

NEREYE:  araclar/
NASIL:   python araclar\\boru_hatti_dogrula.py           sahte istemci, BEDAVA
         python araclar\\boru_hatti_dogrula.py 40 --llm  gerçek LLM
ÇIKTI:   boru_hatti_dogrula_sonuc.txt

ÖLÇÜLEN ASIL SORU
=================
    YÖNLENDİRİCİ, YAZAR'DAN ÖNCE Mİ KOŞMALI

Akış diyagramı Yönlendirici'yi (düğüm 11) Ajan 2'den SONRA koymuş.
`boru_hatti.isle` varsayılan olarak ÖNCE koşturuyor. Gerekçe:
`yazar.kim_yaziyor` taslağı hangi birimin imzalayacağını belirlerken
önce `yonlendirme.hedef_birim`e bakıyor, yoksa muhatap satırına düşüyor —
ve 300 belgenin 22'sinde muhatap satırı hedefi SÖYLEMİYOR
("DAĞITIM YERLERİNE" 12, "İLGİLİ MAKAMA" 10).

Bu betik her belgeyi İKİ SIRAYLA da koşturup farkı sayıyor:

    kimlik      taslağı doğru birim mi imzalıyor
    imza unvanı doğru mu
    otomatik onay oranı

Karar rakamla verilsin diye; "mantıken daha iyi" bir ölçüm değildir.

SAHTE İSTEMCİ KİPİ — VARSAYILAN, KREDİ HARCAMAZ
===============================================
Anlama ve Yazar sahte istemciyle koşuyor. Sahte istemci HEP GEÇERLİ
taslak üretiyor; ölçülen şey taslağın kalitesi DEĞİL, boru hattının
yapısı: sıra, kimlik, karar. `--llm` gerçek modeli çağırır.

DİKKAT — SAHTE KİPTE ANLAMA SABİT TÜR DÖNDÜRÜR
Belge türü sahte istemciden geliyor ve bu Denetçi'nin kapsam
denetimini etkiliyor (`kapsama_girer_mi` türe bakıyor). Kritik eksik
sayıları bu kipte GERÇEK DEĞİL; onlar için `--llm` gerekir. Sıra
karşılaştırması ise türden etkilenmiyor — iki kol da aynı türü görüyor.
"""

from __future__ import annotations

import json
import sys
import time
import types
from collections import Counter, defaultdict
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "src"))

ARAMA_YERLERI = (
    ("deneyler", "adim4", "belgeler_pdf"),
    ("veri", "belgeler"),
    ("ornek",),
)
YAPILANDIRMA_ADAYLARI = ("yapilandirma.qwen.json", "yapilandirma_qwen.json",
                         "yapilandirma.json")
CIKTI = KOK / "boru_hatti_dogrula_sonuc.txt"


class _Cevap:
    def __init__(self, metin: str) -> None:
        self.metin = metin
        self.bitis_sebebi = "stop"
        self.sure_ms = 0.0
        self.model = "sahte"
        self.token = types.SimpleNamespace(toplam=0)
        self.kesildi_mi = False


class SahteIstemci:
    """Üç şemaya da cevap verir: Anlama, Yönlendirici, Yazar.

    Şemanın ADINDAN hangi düğümün sorduğunu anlıyor. Ad uyuşmazlığı
    olursa Anlama'ya düşüyor — bu bilinçli: yeni bir şema eklenirse
    ölçüm sessizce yanlış cevap vermek yerine görünür biçimde bozulur.
    """

    def metin_uret(self, istem, sistem_istemi=None, ek=None, sicaklik=None):
        ad = (((ek or {}).get("response_format") or {})
              .get("json_schema", {}).get("name", ""))

        if ad == "resmi_yazi_taslagi":
            kapanis = "Arz ederim."
            for satir in (istem or "").splitlines():
                if satir.startswith("KAPANIŞ CÜMLESİ"):
                    kapanis = satir.split(":", 1)[1].strip() or kapanis
                    break
            return _Cevap(json.dumps({
                "tur": "cevap_yazisi",
                "tur_gerekcesi": "Gelen talebe cevap veriliyor.",
                "konu": "Gelen Yazıya Cevap",
                "metin": f"İlgide kayıtlı yazı incelenmiştir. {kapanis}",
                "eksik_bilgiler": [],
            }, ensure_ascii=False))

        if ad == "birim_yonlendirme":
            sema = ((ek or {})["response_format"]["json_schema"]["schema"])
            kodlar = sema["properties"]["birim"]["enum"]
            return _Cevap(json.dumps({
                "birim": kodlar[0], "gerekce": "görev alanı örtüşüyor",
                "kanit_cumle": "", "guven": "orta",
            }, ensure_ascii=False))

        return _Cevap(json.dumps({
            "belge_turu": "talep_yazisi", "gerekce": "sahte",
            "talep": "Sahte talep", "ozet": "Sahte özet.",
        }, ensure_ascii=False))


def klasor_bul() -> Path:
    for p in ARAMA_YERLERI:
        y = KOK.joinpath(*p)
        if y.exists() and any(y.glob("belge_*.pdf")):
            return y
    for b in KOK.rglob("belge_*.pdf"):
        return b.parent
    sys.exit("belge_*.pdf bulunamadi.")


def etiket_klasoru(pdf_klasoru: Path) -> Path:
    for a in (pdf_klasoru / "etiketler", pdf_klasoru.parent / "etiketler",
              pdf_klasoru):
        if a.exists() and any(a.glob("etiket_*.json")):
            return a
    sys.exit("etiket_*.json bulunamadi.")


def yapilandirma_bul() -> Path:
    for ad in YAPILANDIRMA_ADAYLARI:
        y = KOK / ad
        if y.exists():
            return y
    sys.exit(f"Yapilandirma bulunamadi: {YAPILANDIRMA_ADAYLARI}")


def main() -> int:
    from boru_hatti import isle
    from kural_motoru import KuralMotoru

    sayilar = [a for a in sys.argv[1:] if not a.startswith("--")]
    sinir = int(sayilar[0]) if sayilar else 0
    llm = "--llm" in sys.argv

    if llm:
        from llm_istemci import istemci_olustur
        istemci = istemci_olustur(yapilandirma_bul())
    else:
        istemci = SahteIstemci()

    denetci = None
    denetci_hatasi = None
    try:
        from denetci import Denetci
        denetci = Denetci()
    except Exception as exc:  # noqa: BLE001
        denetci_hatasi = f"{type(exc).__name__}: {exc}"

    pdf_klasoru = klasor_bul()
    ek = etiket_klasoru(pdf_klasoru)
    pdfler = sorted(pdf_klasoru.glob("belge_*.pdf"))
    if sinir:
        pdfler = pdfler[:sinir]

    motor = KuralMotoru()
    cikti: list[str] = []

    def yaz(s: str = "") -> None:
        print(s)
        cikti.append(s)

    # sıra -> sayaçlar
    sira_sonuc: dict[str, Counter] = defaultdict(Counter)
    dugum_sure: dict[str, list[float]] = defaultdict(list)
    dugum_hata = Counter()
    hatalar = Counter()
    kazanilan: list[str] = []
    kaybedilen: list[str] = []
    cagri = 0
    n = 0
    t0 = time.perf_counter()

    for i, pdf in enumerate(pdfler, 1):
        no = pdf.stem.replace("belge_", "")
        ey = ek / f"etiket_{no}.json"
        if not ey.exists():
            continue
        e = json.loads(ey.read_text(encoding="utf-8"))
        bek_birim = e["alici"]["birim_kodu"]
        bek_imza = e["alici"].get("imza_unvani")

        kollar = {}
        for ad, once in (("yonlendirici once", True), ("yazar once", False)):
            try:
                s = isle(pdf, istemci, motor, denetci,
                         yonlendirici_once=once)
            except Exception as exc:  # noqa: BLE001
                hatalar[f"{type(exc).__name__}: {exc}"[:60]] += 1
                continue
            cagri += s.llm_cagrisi
            kollar[ad] = s

            d = s.dosya
            c = sira_sonuc[ad]
            kimlik = (s.yazar.iskelet.kimlik.kod
                      if s.yazar and s.yazar.iskelet else None)
            c["kimlik dogru" if kimlik == bek_birim
              else ("kimlik YANLIS" if kimlik else "kimlik YOK")] += 1
            c["imza dogru" if d.cikti_yazi.imza_unvan == bek_imza
              else ("imza YANLIS" if d.cikti_yazi.imza_unvan
                    else "imza YOK")] += 1
            c["otomatik" if d.karar.otomatik_onay else "insan"] += 1
            c["hedef dogru" if d.yonlendirme.hedef_birim == bek_birim
              else "hedef yanlis"] += 1

            if once:
                for iz in d.iz:
                    dugum_sure[iz.ajan].append(iz.sure_ms)
                    if not iz.basarili:
                        dugum_hata[iz.ajan] += 1
                for h in s.hatalar:
                    hatalar[h[:60]] += 1

        # iki kol arasındaki fark
        a, b = kollar.get("yonlendirici once"), kollar.get("yazar once")
        if a and b:
            ka = (a.yazar.iskelet.kimlik.kod
                  if a.yazar and a.yazar.iskelet else None)
            kb = (b.yazar.iskelet.kimlik.kod
                  if b.yazar and b.yazar.iskelet else None)
            if ka == bek_birim and kb != bek_birim:
                kazanilan.append(f"  {no}  yazar-önce: {kb} -> yön-önce: {ka}")
            elif kb == bek_birim and ka != bek_birim:
                kaybedilen.append(f"  {no}  yön-önce: {ka} -> yazar-önce: {kb}")
        n += 1

        if i % 25 == 0:
            print(f"    ... {i}/{len(pdfler)}", file=sys.stderr)

    sure = time.perf_counter() - t0

    yaz("=" * 72)
    yaz("BORU HATTI — ÖLÇÜM")
    yaz("=" * 72)
    yaz(f"belge: {n}   kip: {'GERÇEK LLM' if llm else 'SAHTE İSTEMCİ (bedava)'}"
        f"   LLM çağrısı: {cagri}   süre: {sure:.0f} sn")
    yaz(f"Denetçi: {'koştu' if denetci else 'KOŞMADI — ' + str(denetci_hatasi)}")
    yaz("Her belge İKİ SIRAYLA da koşturuldu.")
    yaz()

    yaz("1  DÜĞÜM SIRASI — asıl soru")
    yaz("-" * 72)
    yaz(f"  {'sıra':20s} {'kimlik✓':>8s} {'kimlik✗':>8s} {'kimlik yok':>11s} "
        f"{'otomatik':>9s}")
    for ad in ("yonlendirici once", "yazar once"):
        c = sira_sonuc[ad]
        yaz(f"  {ad:20s} {c['kimlik dogru']:8d} {c['kimlik YANLIS']:8d} "
            f"{c['kimlik YOK']:11d} {c['otomatik']:9d}")
    yaz()
    yaz("  'kimlik' = taslağı hangi birimin imzalayacağı. Yanlış birim adına")
    yaz("  imzalanmış yazı, yanlış yönlendirilmiş yazıdan daha kötüdür:")
    yaz("  karşı taraf onu meşru sayar ve işlem yapar.")
    yaz()

    if kazanilan or kaybedilen:
        yaz(f"2  SIRA DEĞİŞİKLİĞİNİN ETKİSİ  (+{len(kazanilan)} / "
            f"-{len(kaybedilen)})")
        yaz("-" * 72)
        for s_ in kazanilan[:25]:
            yaz(s_)
        if kaybedilen:
            yaz("  KAYBEDİLEN:")
            for s_ in kaybedilen[:25]:
                yaz(s_)
        yaz()

    yaz("3  İMZA UNVANI")
    yaz("-" * 72)
    for ad in ("yonlendirici once", "yazar once"):
        c = sira_sonuc[ad]
        yaz(f"  {ad:20s} doğru {c['imza dogru']:4d}  yanlış "
            f"{c['imza YANLIS']:3d}  yok {c['imza YOK']:3d}")
    yaz()

    yaz("4  DÜĞÜM SÜRELERİ  (yönlendirici önce kolundan)")
    yaz("-" * 72)
    yaz(f"  {'düğüm':16s} {'ortalama':>10s} {'en yavaş':>10s} {'hata':>6s}")
    for ad in sorted(dugum_sure, key=lambda k: -sum(dugum_sure[k])):
        v = dugum_sure[ad]
        yaz(f"  {ad:16s} {sum(v) / len(v):9.0f}ms {max(v):9.0f}ms "
            f"{dugum_hata[ad]:6d}")
    yaz()

    if hatalar:
        yaz("5  HATALAR")
        yaz("-" * 72)
        for k, v in hatalar.most_common(15):
            yaz(f"  {v:4d}  {k}")
        yaz()

    CIKTI.write_text("\n".join(cikti) + "\n", encoding="utf-8")
    print(f"\nyazildi: {CIKTI}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
