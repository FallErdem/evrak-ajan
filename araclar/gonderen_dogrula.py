"""Gönderen çıkarımını cevap anahtarına karşı ölçer.

NEREYE:  depo kökü (ayristirici_dogrula.py'nin yanına)
NASIL:   python araclar/gonderen_dogrula.py 50     -> hızlı deneme
         python araclar/gonderen_dogrula.py        -> tamamı
ÇIKTI:   gonderen_dogrula_sonuc.txt

NE ÖLÇÜYOR
----------
`ustveri.gonderen` alanı 1.1.0'da eklendi ve Yazar'ın (AJAN 2) tek girdisi:
cevap gelen belgenin GÖNDERENİNE yazılır, arz/rica yönü de ona göre
belirlenir (ME-03). Bu yüzden isabeti ayrı ölçülüyor —
`ayristirici_dogrula.py` yedi alanı sayıyor, gönderen onların içinde yok.

ÜÇ HAT AYRI SAYILIR
-------------------
    H-A  sayının 2. bölümündeki DETSİS -> birim/dış makam kaydı
    H-B  antet bloğu -> TAM ad eşleşmesi
    H-C  dilekçede imza sahibi

Hangi hattın ne kadar iş gördüğü Parça 6'da ablasyon satırı üretiyor:
"DETSİS olmasaydı ne olurdu" sorusunun cevabı buradan çıkar.

İKİ AYRI BAŞARISIZLIK — KARIŞTIRILMAMALI
----------------------------------------
    EKSİK    gönderen bulunamadı, alan boş kaldı
    YANLIŞ   gönderen bulundu ama başka birini gösteriyor

İkisi aynı ağırlıkta DEĞİL. Eksik alan görünür: Denetçi bulgu üretir,
kullanıcı düzeltir. Yanlış alan görünmez: taslak yanlış makama yazılır ve
çıktıya bakan kimse fark etmez. Bu yüzden ayrı raporlanıyorlar ve kabul
ölçütü YANLIŞ üzerinden konuluyor.

ÖLÇÜLEMEYEN VAKA — ceza yazılmaz
--------------------------------
Üç belgenin göndereni veri setinde üretilmiş bir liseye ait
(`gonderen.detsis_kaynagi == "sentetik"`, belge 074/154/172). Bu numaralar
gerçek DETSİS kaydı değil ve birimler*.csv ile kurum*.json'da bulunmaları
beklenmez. Ayrı sayılıyorlar; "eksik" sütununu şişirmemeleri için.
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "src"))

ARAMA_YERLERI = (
    ("deneyler", "adim4", "belgeler_pdf"),
    ("veri", "belgeler"),
    ("ornek", "okuma_ornegi"),
    ("ornek",),
)

CIKTI = KOK / "gonderen_dogrula_sonuc.txt"

# Bu kusur sayı satırını siliyor; DETSİS hattı (H-A) ölür ve H-B devralmak
# zorunda kalır. Ayrı raporlanıyor: H-B'nin gerçek yükü burada görünür.
SAYIYI_SILEN_KUSURLAR = frozenset({"sayi_eksik"})


def klasor_bul() -> Path:
    for p in ARAMA_YERLERI:
        y = KOK.joinpath(*p)
        if y.exists() and any(y.glob("belge_*.pdf")):
            return y
    for b in KOK.rglob("belge_*.pdf"):
        return b.parent
    sys.exit("belge_*.pdf bulunamadi.")


def etiket_klasoru(pdf_klasoru: Path) -> Path:
    for a in (pdf_klasoru / "etiketler", pdf_klasoru.parent / "etiketler", pdf_klasoru):
        if a.exists() and any(a.glob("etiket_*.json")):
            return a
    sys.exit("etiket_*.json bulunamadi.")


# -----------------------------------------------------------------------------
# Karşılaştırma
# -----------------------------------------------------------------------------


def _beklenen(e: dict) -> tuple[str, str | None, str | None]:
    """Etiketten (tip, beklenen_ad, beklenen_detsis) çıkarır."""
    g = e["gonderen"]
    return (g["tip"],
            (g.get("kurum_adi") or g.get("ad") or None),
            (g.get("detsis_no") or "").strip() or None)


def _bulunan(u) -> tuple[str | None, str | None]:
    """Ayrıştırıcıdan (bulunan_ad, bulunan_detsis).

    Ad olarak ÖNCE `birim` alınıyor: etiketler alt birimi gönderen sayıyor
    (belge_031 -> "Mühendislik Fakültesi Dekanlığı", kök kurum değil).
    """
    g = u.gonderen
    return (g.birim or g.idare or g.ad, (g.detsis_no or "").strip() or None)


def _esit(a: str | None, b: str | None) -> bool:
    """Ad karşılaştırması — noktalama ve boşluk farkı sayılmaz.

    ÖLÇÜLDÜ 2026-08-24, belge_055: ayrıştırıcı doğru şirketi buldu ama
    ölçüm YANLIŞ saydı —

        etiket   "Yıldız Hizmetleri Ltd. Şti."
        bulunan  "YILDIZ HİZMETLERİ LTD ŞTİ."
                                 ^ nokta yok

    `katla` büyük/küçük harfi ve Türkçe işaretleri düşürüyor ama noktalamayı
    bırakıyor. Fark tek bir nokta; ölçüm bu yüzden gerçek olmayan bir hata
    raporladı. Ölçüm aracının kendi hatası ayrıştırıcının hatasından daha
    sinsi: sayıyı bozar ve düzeltilecek yeri yanlış gösterir.
    """
    from metin import katla

    if not a or not b:
        return False
    ayikla = str.maketrans("", "", ".,;:'\"()/-")
    return katla(a).translate(ayikla).replace(" ", "") == \
        katla(b).translate(ayikla).replace(" ", "")


def _hat(kanit) -> str:
    """Kanıtın açıklamasından hangi hattın çözdüğünü okur."""
    if kanit is None:
        return "bulunamadi"
    ac = kanit.aciklama or ""
    if "ikinci bölümündeki DETSİS" in ac:
        return "H-A detsis -> ic birim"
    if "dış makam olarak" in ac:
        return "H-A detsis -> dis makam"
    if "antet" in ac:
        return "H-B antet tam eslesme"
    if "imza sahibi" in ac:
        return "H-C dilekce imza"
    if "tüzel kişi" in ac:
        return "H-B antetli kagit (sirket)"
    return "?"


# Bu kusur imza bloğunu SİLİYOR. Dilekçede gönderen imza sahibidir; blok
# silinince ad belgede FİZİKSEL OLARAK YOKTUR ve orada bir ad bulmak
# doğru cevap değil, UYDURMA olurdu.
#
# ÖLÇÜLDÜ 2026-08-24: bulunamayan 18 dilekçenin 8'i bu kusuru taşıyordu.
# Onları "eksik" saymak iki yönden yanlış: (a) sayıyı haksız yere düşürür,
# (b) daha kötüsü, düzeltme hedefi olarak gösterir — birileri bu sayıyı
# iyileştirmek için desen gevşetir ve sistem olmayan adı uydurmaya başlar.
# `ayristirici_dogrula.py` aynı ayrımı "muaf" adıyla zaten yapıyor.
IMZAYI_SILEN_KUSURLAR = frozenset({"imza_eksik"})


def degerlendir(u, e: dict) -> tuple[str, str]:
    """(sonuc, ayrinti). sonuc: dogru | YANLIS | eksik | olculemez"""
    tip, beklenen_ad, beklenen_detsis = _beklenen(e)
    bulunan_ad, bulunan_detsis = _bulunan(u)

    if e["gonderen"].get("detsis_kaynagi") == "sentetik":
        return "olculemez", f"sentetik DETSIS {beklenen_detsis}"

    # Dilekçede gönderen = imza sahibi. Kusur imzayı sildiyse ad belgede yok.
    dilekce = tip in ("gercek_kisi", "ogrenci")
    if dilekce and e.get("kusur") in IMZAYI_SILEN_KUSURLAR:
        if bulunan_ad and not _esit(bulunan_ad, beklenen_ad):
            # Silinmiş bloktan ad ÜRETİLDİ. Bu eksikten kötüdür.
            return "YANLIS", f"imza silinmiş ama ad uyduruldu: {bulunan_ad}"
        return "olculemez", "imza_eksik kusuru: ad belgede yok"

    if bulunan_ad is None and bulunan_detsis is None:
        return "eksik", f"beklenen: {beklenen_ad}"

    # DETSİS varsa o kesin ölçüttür: ad yazımı değişebilir, numara değişmez.
    if beklenen_detsis:
        if bulunan_detsis == beklenen_detsis or _esit(bulunan_ad, beklenen_ad):
            return "dogru", ""
        return "YANLIS", f"beklenen {beklenen_ad} ({beklenen_detsis}), bulunan {bulunan_ad} ({bulunan_detsis})"

    if _esit(bulunan_ad, beklenen_ad):
        return "dogru", ""
    return "YANLIS", f"beklenen {beklenen_ad}, bulunan {bulunan_ad}"


# -----------------------------------------------------------------------------
# Koşu
# -----------------------------------------------------------------------------


def main() -> int:
    from ayristirici import ayristir
    from okuyucu import oku

    sinir = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    pdf_klasoru = klasor_bul()
    ek = etiket_klasoru(pdf_klasoru)
    pdfler = sorted(pdf_klasoru.glob("belge_*.pdf"))
    if sinir:
        pdfler = pdfler[:sinir]

    satirlar_out: list[str] = []

    def yaz(s: str = "") -> None:
        print(s)
        satirlar_out.append(s)

    sonuclar = Counter()
    hatlar = Counter()
    tip_sonuc: dict[str, Counter] = defaultdict(Counter)
    bicim_sonuc: dict[str, Counter] = defaultdict(Counter)
    yanlislar: list[str] = []
    eksikler: list[str] = []
    celiskiler: list[str] = []
    sayisiz: Counter = Counter()
    olculemez_sebep: Counter = Counter()
    okuma_hatasi: list[str] = []
    t0 = time.perf_counter()

    for i, pdf in enumerate(pdfler, 1):
        no = pdf.stem.replace("belge_", "")
        ey = ek / f"etiket_{no}.json"
        if not ey.exists():
            continue
        e = json.loads(ey.read_text(encoding="utf-8"))

        r = oku(pdf)
        if r.hata or not r.satirlar:
            okuma_hatasi.append(f"{no}: {r.hata or 'satir yok'}")
            continue
        a = ayristir(r.satirlar,
                     r.ayrilmis.dipnot_bulundu if r.ayrilmis else None)

        sonuc, ayrinti = degerlendir(a.ustveri, e)
        sonuclar[sonuc] += 1
        if sonuc == "olculemez":
            olculemez_sebep[ayrinti] += 1
        hat = _hat(a.kanit.get("ustveri.gonderen"))
        hatlar[hat] += 1
        tip_sonuc[e["gonderen"]["tip"]][sonuc] += 1
        bicim_sonuc[e.get("pdf_bicimi", "?")][sonuc] += 1

        if e.get("kusur") in SAYIYI_SILEN_KUSURLAR:
            sayisiz[sonuc] += 1

        if sonuc == "YANLIS":
            yanlislar.append(f"  {no}  [{hat}]  {ayrinti}")
        elif sonuc == "eksik":
            eksikler.append(f"  {no}  {ayrinti}")

        for uy in a.uyarilar:
            if "Gönderen çelişkisi" in uy:
                celiskiler.append(f"  {no}  {uy}")

        if i % 25 == 0:
            print(f"    ... {i}/{len(pdfler)}", file=sys.stderr)

    sure = time.perf_counter() - t0
    toplam = sum(sonuclar.values())

    yaz("=" * 72)
    yaz("GÖNDEREN ÇIKARIMI — ÖLÇÜM")
    yaz("=" * 72)
    yaz(f"belge: {toplam}   süre: {sure:.1f} sn   klasör: {pdf_klasoru}")
    yaz()

    yaz("1  GENEL")
    yaz("-" * 72)
    olculebilir = toplam - sonuclar["olculemez"]
    for k in ("dogru", "YANLIS", "eksik", "olculemez"):
        v = sonuclar[k]
        pay = f"%{100 * v / olculebilir:.1f}" if olculebilir and k != "olculemez" else "—"
        yaz(f"  {k:12s} {v:4d}   {pay}")
    yaz()
    yaz("  YANLIS bu ölçümün kritik sayısıdır: eksik alanı Denetçi görür,")
    yaz("  yanlış alanı kimse görmez.")
    if olculemez_sebep:
        yaz()
        yaz("  ölçülemez sebepleri (paydaya girmez — gönderen belgede YOK):")
        for k, v in olculemez_sebep.most_common():
            yaz(f"      {v:3d}  {k}")
    yaz()

    yaz("2  HANGİ HAT ÇÖZDÜ")
    yaz("-" * 72)
    for k, v in hatlar.most_common():
        yaz(f"  {v:4d}  {k}")
    yaz()

    yaz("3  GÖNDEREN TİPİNE GÖRE")
    yaz("-" * 72)
    yaz(f"  {'tip':22s} {'dogru':>6s} {'YANLIS':>7s} {'eksik':>6s}")
    for tip in sorted(tip_sonuc):
        c = tip_sonuc[tip]
        yaz(f"  {tip:22s} {c['dogru']:6d} {c['YANLIS']:7d} {c['eksik']:6d}")
    yaz()

    yaz("4  PDF BİÇİMİNE GÖRE  (hata OCR'da mı mantıkta mı)")
    yaz("-" * 72)
    for b in sorted(bicim_sonuc):
        c = bicim_sonuc[b]
        yaz(f"  {b:18s} dogru {c['dogru']:4d}  YANLIS {c['YANLIS']:3d}  eksik {c['eksik']:3d}")
    yaz()

    if sayisiz:
        yaz("5  SAYISI SİLİNMİŞ BELGELER  (H-A ölür, H-B devralır)")
        yaz("-" * 72)
        yaz(f"  {dict(sayisiz)}")
        yaz()

    if celiskiler:
        yaz(f"6  DETSİS ↔ ANTET ÇELİŞKİSİ  ({len(celiskiler)})")
        yaz("-" * 72)
        for s in celiskiler[:20]:
            yaz(s)
        yaz()

    if yanlislar:
        yaz(f"7  YANLIŞ BULUNANLAR  ({len(yanlislar)})")
        yaz("-" * 72)
        for s in yanlislar[:40]:
            yaz(s)
        yaz()

    if eksikler:
        yaz(f"8  BULUNAMAYANLAR  ({len(eksikler)})")
        yaz("-" * 72)
        for s in eksikler[:40]:
            yaz(s)
        yaz()

    if okuma_hatasi:
        yaz(f"9  OKUNAMAYAN  ({len(okuma_hatasi)})")
        yaz("-" * 72)
        for s in okuma_hatasi[:20]:
            yaz(s)
        yaz()

    CIKTI.write_text("\n".join(satirlar_out) + "\n", encoding="utf-8")
    print(f"\nyazildi: {CIKTI}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
