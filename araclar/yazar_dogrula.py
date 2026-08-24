"""Yazar ajanını örneklem üzerinde ölçer: döngü, kapanış, kopyalama.

NEREYE:  araclar/
NASIL:   python araclar\\yazar_dogrula.py 20          tabakali 20 belge
         python araclar\\yazar_dogrula.py 20 --anlamasiz
         python araclar\\yazar_dogrula.py 0           TAMAMI (300, uzun surer)
ÇIKTI:   yazar_dogrula_sonuc.txt

LLM ÇAĞRISI YAPAR. Belge başına en çok 3 (Anlama + Yazar 2 tur).

TABAKALI ÖRNEKLEM — NEDEN RASTGELE DEĞİL
----------------------------------------
Asıl iddiamız arz/rica asimetrisi ve o beş satırlık bir tablo. Rastgele 20
belge çekilirse `alt` (rica) ve `ozel_tuzel` grupları örnekleme hiç
girmeyebilir — 300 belgede sırasıyla 12 ve 24 tane var. Örneklem
`hiyerarsi_yonu`na göre tabakalanıyor ki her yön en az birkaç belgeyle
temsil edilsin. Seçim tohumlu, yani tekrarlanabilir.

NE ÖLÇÜLÜYOR — ve neyin ölçülemediği
------------------------------------
Taslak metninin CEVAP ANAHTARI YOKTUR; "doğru taslak" diye tek bir metin
yok. Bu yüzden metnin kalitesi ölçülmüyor, ÖLÇÜLEBİLİR ÖZELLİKLERİ
ölçülüyor:

    dongu        kaç belge ilk turda temiz, kaç belge düzeltildi, kaç pes
    tetiklenen   hangi kurallar kaç kez tetiklendi (K-02, ME-*, YZ-01)
    kapanis      verilen kapanış cümlesi metnin sonunda GERÇEKTEN var mı
    kopya        taslak, gelen gövdenin cümlelerini tekrarlıyor mu
    tur          hangi UretilecekTur seçildi
    yer tutucu   kaç taslakta [doldurulacak: ...] kaldı

KOPYA ORANI — belge_048'de gözlenen sorunu sayısallaştırır
----------------------------------------------------------
ÖLÇÜLDÜ 2026-08-24: model gelen gövdedeki cümleyi alıp yalnızca
"Müdürlüğünüzce" -> "Müdürlüğümüzce" çevirip geri yazdı. Ne kural motoru
ne iç denetim bunu görür; linter "0 bulgu" der. Ama kelime örtüşmesi
görür.

Ölçüt: taslaktaki 5 kelimelik pencerelerin kaçı gelen gövdede de aynen
geçiyor. Resmî yazıda kalıp ifadeler ("gereğini arz ederim", "ilgide
kayıtlı yazı") ortaktır, bu yüzden bir miktar örtüşme NORMALDİR ve eşik
tek başına hüküm vermez — dağılım raporlanır, karar insana bırakılır.
"""

from __future__ import annotations

import json
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "src"))

TOHUM = 20260824          # tekrarlanabilir örneklem
PENCERE = 5               # kopya ölçümünde kelime penceresi

ARAMA_YERLERI = (
    ("deneyler", "adim4", "belgeler_pdf"),
    ("veri", "belgeler"),
    ("ornek",),
)
YAPILANDIRMA_ADAYLARI = ("yapilandirma.qwen.json", "yapilandirma_qwen.json",
                         "yapilandirma.json")
CIKTI = KOK / "yazar_dogrula_sonuc.txt"

TERS = {"ust": "alt", "alt": "ust", "ayni": "ayni",
        "ozel_tuzel": "kurum_disi", "gercek_kisi_yazari": "gercek_kisi"}
BEKLENEN_KAPANIS = {
    "ust": "Arz ederim.", "ayni": "Arz ederim.", "alt": "Rica ederim.",
    "kurum_disi": "Rica ederim.", "gercek_kisi": "Bilgilerinize sunulur.",
}


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


def ornek_sec(ek: Path, pdfler: list[Path], n: int) -> list[Path]:
    """hiyerarsi_yonu'na göre tabakalı örneklem. n=0 ise tamamı."""
    if not n:
        return pdfler
    gruplar: dict[str, list[Path]] = defaultdict(list)
    for pdf in pdfler:
        ey = ek / f"etiket_{pdf.stem.replace('belge_', '')}.json"
        if not ey.exists():
            continue
        e = json.loads(ey.read_text(encoding="utf-8"))
        gruplar[e.get("hiyerarsi_yonu", "?")].append(pdf)

    rasgele = random.Random(TOHUM)
    secim: list[Path] = []
    # Her tabakadan orantılı, ama en az 2 — küçük tabakalar kaybolmasın.
    toplam = sum(len(v) for v in gruplar.values())
    for yon, liste in sorted(gruplar.items()):
        pay = max(2, round(n * len(liste) / toplam)) if toplam else 0
        rasgele.shuffle(liste)
        secim.extend(liste[:min(pay, len(liste))])
    rasgele.shuffle(secim)
    return secim[:max(n, len(gruplar) * 2)]


def _kelimeler(metin: str) -> list[str]:
    from metin import katla
    return katla(metin or "").split()


def kopya_orani(taslak: str, govde: str) -> float:
    """Taslaktaki 5'li kelime pencerelerinin kaçı gövdede aynen geçiyor."""
    t, g = _kelimeler(taslak), _kelimeler(govde)
    if len(t) < PENCERE or len(g) < PENCERE:
        return 0.0
    govde_pencereleri = {" ".join(g[i:i + PENCERE])
                         for i in range(len(g) - PENCERE + 1)}
    toplam = len(t) - PENCERE + 1
    ortak = sum(" ".join(t[i:i + PENCERE]) in govde_pencereleri
                for i in range(toplam))
    return ortak / toplam


def main() -> int:
    from anlama import anla
    from ayristirici import ayristir
    from kural_motoru import KuralMotoru
    from llm_istemci import istemci_olustur
    from okuyucu import oku
    from veri_yapisi import Dosya
    from yazar import yaz

    sayilar = [a for a in sys.argv[1:] if not a.startswith("--")]
    n = int(sayilar[0]) if sayilar else 20
    anlamasiz = "--anlamasiz" in sys.argv

    pdf_klasoru = klasor_bul()
    ek = etiket_klasoru(pdf_klasoru)
    pdfler = sorted(pdf_klasoru.glob("belge_*.pdf"))
    secilen = ornek_sec(ek, pdfler, n)

    istemci = istemci_olustur(yapilandirma_bul())
    motor = KuralMotoru()

    cikti: list[str] = []

    def yaz_(s: str = "") -> None:
        print(s)
        cikti.append(s)

    dongu = Counter()
    tetiklenen = Counter()
    turler = Counter()
    kapanis = Counter()
    yon_isabet = Counter()
    kopya_bant = Counter()
    kopyalar: list[tuple[str, float]] = []
    yer_tutuculu = 0
    cagri = 0
    hatalar: list[str] = []
    t0 = time.perf_counter()
    islenen = 0

    for i, pdf in enumerate(secilen, 1):
        no = pdf.stem.replace("belge_", "")
        ey = ek / f"etiket_{no}.json"
        if not ey.exists():
            continue
        e = json.loads(ey.read_text(encoding="utf-8"))

        r = oku(pdf)
        if r.hata or not r.satirlar:
            hatalar.append(f"{no}: okunamadi ({r.hata})")
            continue
        a = ayristir(r.satirlar,
                     r.ayrilmis.dipnot_bulundu if r.ayrilmis else None)
        d = Dosya()
        d.ustveri = a.ustveri
        d.metin = r.govde

        if not anlamasiz:
            try:
                an = anla(r.govde, a, istemci)
                cagri += 1
                d.siniflandirma = an.siniflandirma
                d.icerik = an.icerik
            except Exception as exc:  # noqa: BLE001
                hatalar.append(f"{no}: Anlama {type(exc).__name__}")

        try:
            s = yaz(d, istemci, motor)
        except Exception as exc:  # noqa: BLE001
            hatalar.append(f"{no}: Yazar {type(exc).__name__}: {exc}")
            continue
        cagri += s.tur_sayisi
        islenen += 1

        # -- dongu ----------------------------------------------------------
        if s.pes_edildi:
            dongu["pes edildi"] += 1
        elif s.duzeltildi:
            dongu["duzeltildi"] += 1
        else:
            dongu["ilk turda temiz"] += 1
        for b in s.ilk_bulgular:
            tetiklenen[getattr(b, "kural_id", "?")] += 1

        c = d.cikti_yazi
        turler[str(c.tur)] += 1

        # -- kapanis --------------------------------------------------------
        bek_yon = TERS.get(e["hiyerarsi_yonu"])
        bek_kap = BEKLENEN_KAPANIS.get(bek_yon or "")
        uretilen = s.iskelet.yon.kapanis if s.iskelet else ""
        if bek_kap:
            yon_isabet["dogru" if uretilen == bek_kap else "YANLIS"] += 1
        # Verilen kapanış metnin İÇİNDE gerçekten var mı — istem uyuldu mu.
        govde_son = (c.metin or "")[-160:]
        cekirdek = uretilen.rstrip(".").split()[-2:]
        kapanis["metinde var" if all(k in govde_son for k in cekirdek)
                else "METINDE YOK"] += 1

        # -- kopya ----------------------------------------------------------
        oran = kopya_orani(c.metin or "", r.govde)
        if oran >= 0.50:
            bant = ">=0.50 agir kopya"
        elif oran >= 0.30:
            bant = "0.30-0.49"
        elif oran >= 0.15:
            bant = "0.15-0.29"
        else:
            bant = "<0.15"
        kopya_bant[bant] += 1
        kopyalar.append((no, oran))

        if "[doldurulacak" in (c.metin or ""):
            yer_tutuculu += 1

        print(f"    ... {i}/{len(secilen)}  belge_{no}  {s.ozet}",
              file=sys.stderr)

    sure = time.perf_counter() - t0
    kopyalar.sort(key=lambda x: -x[1])

    yaz_("=" * 72)
    yaz_("YAZAR AJANI — ÖLÇÜM")
    yaz_("=" * 72)
    yaz_(f"belge: {islenen}   LLM çağrısı: {cagri}   süre: {sure:.0f} sn"
         f"   Anlama: {'ATLANDI' if anlamasiz else 'kostu'}")
    yaz_()

    yaz_("1  ÜSLUP DÖNGÜSÜ  —  ajanlığın kanıtı")
    yaz_("-" * 72)
    for k in ("ilk turda temiz", "duzeltildi", "pes edildi"):
        v = dongu[k]
        yaz_(f"  {k:18s} {v:4d}   %{100 * v / islenen:.1f}" if islenen else k)
    yaz_()
    yaz_("  'duzeltildi' = tek atışlık bir Yazar'ın HATALI çıktı vereceği belge.")
    yaz_("  'pes edildi' = insana tırmandırıldı; hata gizlenmedi.")
    yaz_()

    yaz_("2  İLK TURDA TETİKLENEN KURALLAR")
    yaz_("-" * 72)
    if tetiklenen:
        for k, v in tetiklenen.most_common():
            yaz_(f"  {v:4d}  {k}")
    else:
        yaz_("  (hiç ihlal bulunmadı)")
    yaz_()

    yaz_("3  KAPANIŞ")
    yaz_("-" * 72)
    for k, v in yon_isabet.most_common():
        yaz_(f"  yön {k:8s} {v:4d}")
    for k, v in kapanis.most_common():
        yaz_(f"  cümle {k:14s} {v:4d}")
    yaz_()
    yaz_("  'METINDE YOK' = deterministik katman doğru kapanışı verdi ama")
    yaz_("  model onu metnin sonuna yazmadı. İstem uyumu sorunudur.")
    yaz_()

    yaz_("4  SEÇİLEN YAZI TÜRÜ")
    yaz_("-" * 72)
    for k, v in turler.most_common():
        yaz_(f"  {v:4d}  {k}")
    yaz_()

    yaz_("5  KOPYA ORANI  —  taslak gelen gövdeyi tekrarlıyor mu")
    yaz_("-" * 72)
    for b in (">=0.50 agir kopya", "0.30-0.49", "0.15-0.29", "<0.15"):
        if kopya_bant[b]:
            yaz_(f"  {b:20s} {kopya_bant[b]:4d}")
    yaz_()
    yaz_("  En yüksek 10 belge:")
    for no, oran in kopyalar[:10]:
        yaz_(f"      belge_{no}  {oran:.2f}")
    yaz_()
    yaz_("  Resmî yazıda kalıp ifadeler ortaktır; bir miktar örtüşme NORMAL.")
    yaz_("  Eşik tek başına hüküm vermez — yüksek çıkanlara gözle bakılmalı.")
    yaz_()

    yaz_(f"6  YER TUTUCU KALAN TASLAK: {yer_tutuculu}")
    yaz_("-" * 72)
    yaz_("  Bunlar hata değil; memurun dolduracağı alanlar. Sayının yüksek")
    yaz_("  olması modelin veri uydurmak yerine boş bıraktığını gösterir.")
    yaz_()

    if hatalar:
        yaz_(f"7  HATALAR ({len(hatalar)})")
        yaz_("-" * 72)
        for h in hatalar[:20]:
            yaz_(f"  {h}")
        yaz_()

    CIKTI.write_text("\n".join(cikti) + "\n", encoding="utf-8")
    print(f"\nyazildi: {CIKTI}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
