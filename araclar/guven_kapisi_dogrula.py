"""Güven kapısını ölçer. Kritik soru: otomatik onaylananlarda hata var mı.

NEREYE:  araclar/
NASIL:   python araclar\\guven_kapisi_dogrula.py            LLM YOK, bedava
         python araclar\\guven_kapisi_dogrula.py --llm      tam boru hattı
         python araclar\\guven_kapisi_dogrula.py 50 --llm
ÇIKTI:   guven_kapisi_dogrula_sonuc.txt

VARSAYILAN KİP KREDİ HARCAMAZ
-----------------------------
LLM'siz kipte Yönlendirici deterministik hatlarla, Yazar da SAHTE
İSTEMCİ ile koşuyor. Sahte istemci hep aynı geçerli taslağı döndürüyor;
ölçülen şey taslağın kalitesi DEĞİL, kapının mantığı: hangi belge hangi
sebeple insana düşüyor.

`--llm` verilirse gerçek boru hattı koşar ve otomatik onay oranı gerçek
taslaklarla ölçülür.

ÖLÇÜLEN KRİTİK SAYI
===================
    OTOMATİK ONAYLANANLARDA YANLIŞ YÖNLENDİRME

Oraya bir hata sızarsa kimse görmez — belge memurun önüne hiç gelmeden
yanlış birime gider. Bu sayı SIFIR olmak zorunda; değilse eşik yükselmeli.

İnsana düşenlerde hata olması sorun değil: memur zaten bakıyor. Ama
insana düşenlerin ÇOĞU doğruysa kapı fazla temkinli demektir ve o da
ayrı bir maliyet — memur zamanı. İki tabloda birden raporlanıyor.

CEVAP ANAHTARI
--------------
`etiket.alici.birim_kodu` — evrağın gerçekte geldiği birim. Yalnızca
yönlendirme doğrulanabiliyor; taslak metninin cevap anahtarı yok.
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
# `govde_kur` src/ayristirici.py'de. Kendi kopyamı ÇIKARMIYORUM: gövdeyi
# yanlış kurmak ME kurallarında yanlış alarm üretiyor ve bu iki kez
# ölçülmüş, iki kez düzeltilmiş bir hata. İkinci bir uygulama o
# düzeltmeyi kaybeder.

ARAMA_YERLERI = (
    ("deneyler", "adim4", "belgeler_pdf"),
    ("veri", "belgeler"),
    ("ornek",),
)
YAPILANDIRMA_ADAYLARI = ("yapilandirma.qwen.json", "yapilandirma_qwen.json",
                         "yapilandirma.json")
CIKTI = KOK / "guven_kapisi_dogrula_sonuc.txt"

# Karşılaştırma için denenen eşikler. Yönlendirici skorları kesikli
# olduğundan aradaki değerler aynı sonucu verir; bantların sınırları
# seçildi.
ESIKLER = (0.85, 0.95)


class _SahteCevap:
    def __init__(self, metin: str) -> None:
        self.metin = metin
        self.bitis_sebebi = "stop"
        self.sure_ms = 0.0
        self.model = "sahte"
        self.token = types.SimpleNamespace(toplam=0)
        self.kesildi_mi = False


class SahteIstemci:
    """Hep aynı geçerli taslağı döndürür. Kredi harcamaz.

    Taslak bilerek KURALLARA UYGUN: konu noktalamasız, kapanış metnin
    sonunda, ek iddiası yok. Böylece kapının kararı taslak kalitesinden
    değil, ÖLÇÜLEN diğer bileşenlerden geliyor.
    """

    def metin_uret(self, istem, sistem_istemi=None, ek=None, sicaklik=None):
        # Kapanış istemin içinde veriliyor; oradan okuyup sona koyuyoruz ki
        # ME-02 tetiklenmesin ve kapı taslak yüzünden bloke olmasın.
        kapanis = "Arz ederim."
        for satir in (istem or "").splitlines():
            if satir.startswith("KAPANIŞ CÜMLESİ"):
                kapanis = satir.split(":", 1)[1].strip() or kapanis
                break
        return _SahteCevap(json.dumps({
            "tur": "cevap_yazisi",
            "tur_gerekcesi": "Gelen talebe cevap veriliyor.",
            "konu": "Gelen Yazıya Cevap",
            "metin": f"İlgide kayıtlı yazı incelenmiştir. {kapanis}",
            "eksik_bilgiler": [],
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
    from ayristirici import ayristir, govde_kur
    from guven_kapisi import degerlendir
    from kural_motoru import KuralMotoru
    from okuyucu import oku
    from veri_yapisi import Dosya
    from yazar import yaz
    from yonlendirici import yonlendir

    sayilar = [a for a in sys.argv[1:] if not a.startswith("--")]
    sinir = int(sayilar[0]) if sayilar else 0
    llm = "--llm" in sys.argv

    if llm:
        from llm_istemci import istemci_olustur
        istemci = istemci_olustur(yapilandirma_bul())
        yon_istemci = istemci
    else:
        istemci = SahteIstemci()
        yon_istemci = None

    denetci = None
    denetci_hatasi = None
    try:
        from denetci import Denetci
        denetci = Denetci()
    except Exception as exc:  # noqa: BLE001
        denetci_hatasi = f"{type(exc).__name__}: {exc}"

    anla = None
    if llm:
        from anlama import anla as _anla
        anla = _anla

    pdf_klasoru = klasor_bul()
    ek = etiket_klasoru(pdf_klasoru)
    pdfler = sorted(pdf_klasoru.glob("belge_*.pdf"))
    if sinir:
        pdfler = pdfler[:sinir]

    motor = KuralMotoru()
    cikti: list[str] = []

    def yaz_(s: str = "") -> None:
        print(s)
        cikti.append(s)

    # eşik -> sonuç sayaçları
    esik_sonuc: dict[float, Counter] = defaultdict(Counter)
    engel_sayaci = Counter()
    sebep_sayaci = Counter()
    sizanlar: dict[float, list[str]] = defaultdict(list)
    bilesen_sifir = Counter()
    n = 0
    cagri = 0
    t0 = time.perf_counter()

    for i, pdf in enumerate(pdfler, 1):
        no = pdf.stem.replace("belge_", "")
        ey = ek / f"etiket_{no}.json"
        if not ey.exists():
            continue
        e = json.loads(ey.read_text(encoding="utf-8"))

        r = oku(pdf)
        if r.hata or not r.satirlar:
            continue
        a = ayristir(r.satirlar,
                     r.ayrilmis.dipnot_bulundu if r.ayrilmis else None)
        d = Dosya()
        d.ustveri = a.ustveri
        d.kanit = dict(a.kanit)
        d.metin = govde_kur(r.ayrilmis.govde_satirlari, a)

        if anla is not None:
            try:
                an = anla(r.govde, a, istemci)
                cagri += 1
                d.siniflandirma, d.icerik = an.siniflandirma, an.icerik
            except Exception:  # noqa: BLE001
                pass
        if denetci is not None:
            try:
                denetci.calistir(d)
            except Exception:  # noqa: BLE001
                pass

        yon = yonlendir(d, yon_istemci)
        if yon.llm_kullanildi:
            cagri += 1
        try:
            ys = yaz(d, istemci, motor)
            cagri += ys.tur_sayisi if llm else 0
        except Exception:  # noqa: BLE001
            continue
        n += 1

        bek = e["alici"]["birim_kodu"]
        dogru_yon = d.yonlendirme.hedef_birim == bek

        for esik in ESIKLER:
            s = degerlendir(d, yazar_sonucu=ys, yonlendirme_sonucu=yon,
                            esik=esik)
            if s.otomatik:
                esik_sonuc[esik]["otomatik · dogru" if dogru_yon
                                 else "otomatik · YANLIS"] += 1
                if not dogru_yon:
                    sizanlar[esik].append(
                        f"  {no}  beklenen {bek}, bulunan "
                        f"{d.yonlendirme.hedef_birim} "
                        f"(yön skoru {d.yonlendirme.skor})")
            else:
                esik_sonuc[esik]["insan · dogru" if dogru_yon
                                 else "insan · yanlis"] += 1
            if esik == ESIKLER[0]:
                for g in s.engelleyen:
                    engel_sayaci[g] += 1
                for sb in s.sebepler:
                    sebep_sayaci[sb[:70]] += 1
                for ad, v in s.bilesenler.items():
                    if v == 0.0:
                        bilesen_sifir[ad] += 1

        if i % 25 == 0:
            print(f"    ... {i}/{len(pdfler)}", file=sys.stderr)

    sure = time.perf_counter() - t0

    yaz_("=" * 72)
    yaz_("GÜVEN KAPISI — ÖLÇÜM")
    yaz_("=" * 72)
    yaz_(f"belge: {n}   kip: {'TAM BORU HATTI (LLM)' if llm else 'SAHTE İSTEMCİ (LLM yok)'}"
         f"   LLM çağrısı: {cagri}   süre: {sure:.0f} sn")
    yaz_(f"Denetçi: {'koştu' if denetci else 'KOŞMADI — ' + str(denetci_hatasi)}")
    if not llm:
        yaz_("Sahte istemci hep geçerli taslak üretiyor; taslak kalitesi")
        yaz_("ölçülmüyor, kapının MANTIĞI ölçülüyor.")
    yaz_()

    yaz_("1  EŞİĞE GÖRE OTOMATİK ONAY")
    yaz_("-" * 72)
    yaz_(f"  {'eşik':6s} {'otomatik':>9s} {'oran':>7s} "
         f"{'SIZAN HATA':>11s} {'insana düşen':>13s}")
    for esik in ESIKLER:
        c = esik_sonuc[esik]
        oto = c["otomatik · dogru"] + c["otomatik · YANLIS"]
        ins = c["insan · dogru"] + c["insan · yanlis"]
        pay = f"%{100 * oto / n:.1f}" if n else "—"
        yaz_(f"  {esik:<6.2f} {oto:9d} {pay:>7s} "
             f"{c['otomatik · YANLIS']:11d} {ins:13d}")
    yaz_()
    yaz_("  SIZAN HATA = otomatik onaylandı ama yanlış birime yönlendirildi.")
    yaz_("  Bu sayı SIFIR olmak zorunda; değilse eşik yükseltilmeli.")
    yaz_()

    yaz_("2  İNSANA DÜŞENLER GEREKLİ MİYDİ")
    yaz_("-" * 72)
    for esik in ESIKLER:
        c = esik_sonuc[esik]
        ins = c["insan · dogru"] + c["insan · yanlis"]
        if not ins:
            continue
        yaz_(f"  eşik {esik:.2f} · insana düşen {ins:3d} — "
             f"{c['insan · yanlis']} tanesinde yönlendirme gerçekten yanlıştı, "
             f"{c['insan · dogru']} tanesi doğruydu")
    yaz_()
    yaz_("  'doğruydu' olanlar yanlış alarm DEĞİL: kapı yönlendirmeden başka")
    yaz_("  şeye de bakıyor (kritik eksik, taslak, kimlik). Ama sayı çok")
    yaz_("  yüksekse kapı fazla temkinli demektir ve memur zamanı maliyeti var.")
    yaz_()

    yaz_(f"3  HANGİ BİLEŞEN ENGELLEDİ  (eşik {ESIKLER[0]:.2f})")
    yaz_("-" * 72)
    for k, v in engel_sayaci.most_common():
        yaz_(f"  {v:4d}  {k}")
    yaz_()

    yaz_("4  EN SIK SEBEPLER")
    yaz_("-" * 72)
    for k, v in sebep_sayaci.most_common(12):
        yaz_(f"  {v:4d}  {k}")
    yaz_()

    for esik in ESIKLER:
        if sizanlar[esik]:
            yaz_(f"5  SIZAN HATALAR · eşik {esik:.2f}  ({len(sizanlar[esik])})")
            yaz_("-" * 72)
            for s_ in sizanlar[esik][:30]:
                yaz_(s_)
            yaz_()

    CIKTI.write_text("\n".join(cikti) + "\n", encoding="utf-8")
    print(f"\nyazildi: {CIKTI}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
