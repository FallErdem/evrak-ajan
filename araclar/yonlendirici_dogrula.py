"""Yönlendiriciyi cevap anahtarına karşı ölçer. Hat bazında ablasyon.

NEREYE:  araclar/
NASIL:   python araclar\\yonlendirici_dogrula.py           deterministik, LLM YOK
         python araclar\\yonlendirici_dogrula.py --llm     LLM hatları da koşar
         python araclar\\yonlendirici_dogrula.py 50 --llm  ilk 50 belge
ÇIKTI:   yonlendirici_dogrula_sonuc.txt

VARSAYILAN KİP LLM ÇAĞIRMAZ — kredi harcamadan koşar.
`--llm` verilmezse Y-C ve Y-D atlanır ve o belgeler "çözülemedi" sayılır.
İki kipi ayrı koşturmak asıl ablasyonu verir:

    deterministik kip  ->  SDP ve muhatap hatları tek başına ne kadar çözüyor
    --llm kipi         ->  model kalan belgelerde ne kazandırıyor

CEVAP ANAHTARI
--------------
`etiket.alici.birim_kodu` — evrağın gerçekte hangi birime geldiği.

ÜÇ SONUÇ, KARIŞTIRILMAMALI
--------------------------
    dogru        hedef birim doğru
    YANLIS       hedef bulundu ama başka birim  <- KRİTİK SAYI
    cozulemedi   hedef bulunamadı, insana düştü

`YANLIS` kritiktir: evrak yanlış birime havale edilir ve o birim "bana
gelmez" deyip geri gönderene kadar süre işler. `cozulemedi` görünür bir
sonuçtur — arayüz memura sorar, memur seçer.

SEVİYE 1 DENETİMİ
-----------------
Başkan yardımcılıklarına evrak havale edilmez (`birimler.py`,
HEDEF_OLAMAYAN_SEVIYE). Hedef seviye 1 çıkarsa ayrıca sayılıyor; sıfır
olması beklenen davranıştır.
"""

from __future__ import annotations

import json
import sys
import time
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
CIKTI = KOK / "yonlendirici_dogrula_sonuc.txt"


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
    from birimler import birim_bul
    from okuyucu import oku
    from veri_yapisi import Dosya
    from yonlendirici import yonlendir

    sayilar = [a for a in sys.argv[1:] if not a.startswith("--")]
    sinir = int(sayilar[0]) if sayilar else 0
    llm = "--llm" in sys.argv

    istemci = None
    if llm:
        from llm_istemci import istemci_olustur
        istemci = istemci_olustur(yapilandirma_bul())

    pdf_klasoru = klasor_bul()
    ek = etiket_klasoru(pdf_klasoru)
    pdfler = sorted(pdf_klasoru.glob("belge_*.pdf"))
    if sinir:
        pdfler = pdfler[:sinir]

    cikti: list[str] = []

    def yaz(s: str = "") -> None:
        print(s)
        cikti.append(s)

    genel = Counter()
    hat_sonuc: dict[str, Counter] = defaultdict(Counter)
    kaynak_sayaci = Counter()
    skor_bant: dict[str, Counter] = defaultdict(Counter)
    yanlislar: list[str] = []
    cozulemeyen: list[str] = []
    celiskiler: list[str] = []
    seviye1 = 0
    kanit_dolu = 0
    cagri = 0
    okunamadi = 0
    n = 0
    t0 = time.perf_counter()

    for i, pdf in enumerate(pdfler, 1):
        no = pdf.stem.replace("belge_", "")
        ey = ek / f"etiket_{no}.json"
        if not ey.exists():
            continue
        e = json.loads(ey.read_text(encoding="utf-8"))

        r = oku(pdf)
        if r.hata or not r.satirlar:
            okunamadi += 1
            continue
        a = ayristir(r.satirlar,
                     r.ayrilmis.dipnot_bulundu if r.ayrilmis else None)
        d = Dosya()
        d.ustveri = a.ustveri
        d.kanit = dict(a.kanit)
        d.metin = govde_kur(r.ayrilmis.govde_satirlari, a)

        s = yonlendir(d, istemci)
        n += 1
        if s.llm_kullanildi:
            cagri += 1

        bek = e["alici"]["birim_kodu"]
        y = d.yonlendirme
        if y.hedef_birim is None:
            sonuc = "cozulemedi"
            cozulemeyen.append(f"  {no}  beklenen {bek}  [{s.hat}]")
        elif y.hedef_birim == bek:
            sonuc = "dogru"
        else:
            sonuc = "YANLIS"
            yanlislar.append(
                f"  {no}  beklenen {bek}, bulunan {y.hedef_birim} "
                f"(skor {y.skor}) [{s.hat}]")

        genel[sonuc] += 1
        hat_sonuc[s.hat][sonuc] += 1
        kaynak_sayaci[str(y.kaynak)] += 1

        bant = ("1.00" if y.skor >= 1.0 else
                "0.90-0.99" if y.skor >= 0.90 else
                "0.70-0.89" if y.skor >= 0.70 else
                "0.40-0.69" if y.skor >= 0.40 else "<0.40 / yok")
        skor_bant[bant][sonuc] += 1

        if s.celiski:
            celiskiler.append(f"  {no}  {s.gerekce}")
        if y.kanit_cumle:
            kanit_dolu += 1
        kayit = birim_bul(y.hedef_birim) if y.hedef_birim else None
        if kayit and kayit["seviye"] == 1:
            seviye1 += 1

        if i % 25 == 0:
            print(f"    ... {i}/{len(pdfler)}", file=sys.stderr)

    sure = time.perf_counter() - t0
    payda = genel["dogru"] + genel["YANLIS"] + genel["cozulemedi"]

    yaz("=" * 72)
    yaz("YÖNLENDİRİCİ — ÖLÇÜM")
    yaz("=" * 72)
    yaz(f"belge: {n}   kip: {'LLM ACIK' if llm else 'DETERMINISTIK (LLM yok)'}"
        f"   LLM çağrısı: {cagri}   süre: {sure:.0f} sn")
    if okunamadi:
        yaz(f"okunamadı: {okunamadi}")
    yaz()

    yaz("1  GENEL")
    yaz("-" * 72)
    for k in ("dogru", "YANLIS", "cozulemedi"):
        v = genel[k]
        yaz(f"  {k:12s} {v:4d}   %{100 * v / payda:.1f}" if payda
            else f"  {k:12s} {v:4d}")
    yaz()
    yaz("  YANLIS kritik sayıdır: evrak yanlış birime havale edilir ve o birim")
    yaz("  geri gönderene kadar süre işler. 'cozulemedi' görünür — memur seçer.")
    yaz()

    yaz("2  HAT BAZINDA — ablasyon")
    yaz("-" * 72)
    yaz(f"  {'hat':30s} {'dogru':>6s} {'YANLIS':>7s} {'cozulemedi':>11s}")
    for hat in sorted(hat_sonuc, key=lambda h: -sum(hat_sonuc[h].values())):
        c = hat_sonuc[hat]
        yaz(f"  {hat:30s} {c['dogru']:6d} {c['YANLIS']:7d} {c['cozulemedi']:11d}")
    yaz()
    yaz("  Y-A ve Y-B deterministik, LLM yok. Y-C ve Y-D model kullanıyor.")
    yaz()

    yaz("3  KAYNAK ALANI  (arayüzdeki rozet)")
    yaz("-" * 72)
    for k, v in kaynak_sayaci.most_common():
        yaz(f"  {v:4d}  {k}")
    yaz()

    yaz("4  SKOR KALİBRASYONU  —  yüksek skor gerçekten doğru mu")
    yaz("-" * 72)
    yaz(f"  {'bant':14s} {'dogru':>6s} {'YANLIS':>7s} {'cozulemedi':>11s}")
    for b in ("1.00", "0.90-0.99", "0.70-0.89", "0.40-0.69", "<0.40 / yok"):
        c = skor_bant[b]
        if c:
            yaz(f"  {b:14s} {c['dogru']:6d} {c['YANLIS']:7d} {c['cozulemedi']:11d}")
    yaz()
    yaz("  Yüksek bantta YANLIŞ varsa skor yalan söylüyor demektir; arayüz")
    yaz("  o skora bakarak otomatik onay verecek.")
    yaz()

    yaz("5  YAPISAL DENETİMLER")
    yaz("-" * 72)
    yaz(f"  seviye 1 birime havale (olmamalı) : {seviye1}")
    yaz(f"  çelişki (Y-A ≠ Y-B)               : {len(celiskiler)}")
    yaz(f"  kanıt cümlesi dolu                : {kanit_dolu}")
    yaz()
    for s_ in celiskiler[:10]:
        yaz(s_)
    if celiskiler:
        yaz()

    if yanlislar:
        yaz(f"6  YANLIŞ YÖNLENDİRİLENLER  ({len(yanlislar)})")
        yaz("-" * 72)
        for s_ in yanlislar[:40]:
            yaz(s_)
        yaz()

    if cozulemeyen:
        yaz(f"7  ÇÖZÜLEMEYENLER  ({len(cozulemeyen)})")
        yaz("-" * 72)
        for s_ in cozulemeyen[:40]:
            yaz(s_)
        yaz()

    CIKTI.write_text("\n".join(cikti) + "\n", encoding="utf-8")
    print(f"\nyazildi: {CIKTI}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
