"""Docling sondası — koordinat sistemini ve eğiklik etkisini ölçer.

NEDEN
-----
dipnot.py konumla çalışıyor: "bu satır sayfanın alt %25'inde mi". Metin
katmanlı belgede koordinatı pdfplumber veriyor. Taranmış 50 belgede metin
katmanı YOK — koordinatı Docling'den almak gerekiyor.

İki şey ölçülmeden Docling koordinatı kullanılamaz:

  1. SIFIR NEREDE      Docling y'yi üstten mi alttan mı sayıyor? Yanlış
                       varsayarsam dipnot yerine BAŞLIĞI keserim.
  2. EĞİKLİK NE YAPIYOR tarama_bozuk belgelerde sayfa eğri. OCR bunu
                       düzeltiyor mu, yoksa satır y'leri kayıyor mu?
                       Eşik payımız 72 punto; A4'te 3° eğiklik ~31 punto
                       kayma demek.

Bu betik tahmin etmez, Docling'in verdiği yapıyı OLDUĞU GİBİ döker.

KULLANIM
--------
    python docling_sonda.py                          # klasörü kendi bulur
    python docling_sonda.py deneyler\\adim4\\belgeler_pdf

Üç belge inceler: bir temiz tarama, bir bozuk tarama, bir metin katmanlı
(karşılaştırma tabanı). Toplam ~2 dakika.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent

ARAMA_YERLERI = (
    ("deneyler", "adim4", "belgeler_pdf"),
    ("veri", "belgeler"),
    ("ornek", "okuma_ornegi"),
)

# Dipnotta geçmesi beklenen ifadeler — konumlarını ölçeceğiz.
DIPNOT_IZLERI = ("güvenli elektronik imza", "doğrulama kodu", "kep adresi",
                 "belge takip", "doğrulama adresi")

# Başlıkta geçmesi beklenen — sayfanın ÜSTÜNDE olmalı. Sıfırın nerede
# olduğunu bu ikisinin karşılaştırmasından anlayacağız.
BASLIK_IZLERI = ("t.c.", "valiliği", "başkanlığı", "müdürlüğü", "rektörlüğü")


def klasor_bul(verilen: str | None) -> Path:
    if verilen:
        y = Path(verilen)
        if y.exists():
            return y
    for parcalar in ARAMA_YERLERI:
        y = KOK.joinpath(*parcalar)
        if y.exists() and any(y.glob("belge_*.pdf")):
            return y
    for bulunan in KOK.rglob("belge_*.pdf"):
        return bulunan.parent
    sys.exit("belge_*.pdf bulunamadi. Klasoru arguman olarak verin.")


def etiket_klasoru(pdf_klasoru: Path) -> Path | None:
    for a in (pdf_klasoru, pdf_klasoru.parent / "etiketler", pdf_klasoru.parent):
        if a.exists() and any(a.glob("etiket_*.json")):
            return a
    for b in KOK.rglob("etiket_*.json"):
        return b.parent
    return None


def ornekleri_sec(klasor: Path) -> list[tuple[str, Path, str]]:
    """Bir temiz tarama, bir bozuk tarama, bir metin katmanlı seçer."""
    ek = etiket_klasoru(klasor)
    if ek is None:
        pdfler = sorted(klasor.glob("belge_*.pdf"))[:3]
        return [("bilinmiyor", p, "?") for p in pdfler]

    temiz = bozuk = metinli = None
    for pdf in sorted(klasor.glob("belge_*.pdf")):
        no = pdf.stem.replace("belge_", "")
        ey = ek / f"etiket_{no}.json"
        if not ey.exists():
            continue
        e = json.loads(ey.read_text(encoding="utf-8"))
        bicim, kusur = e.get("pdf_bicimi"), e.get("kusur")
        if bicim == "taranmis" and kusur == "tarama_bozuk" and bozuk is None:
            bozuk = ("taranmis + BOZUK", pdf, e.get("belge_turu", "?"))
        elif bicim == "taranmis" and kusur != "tarama_bozuk" and temiz is None:
            temiz = ("taranmis temiz", pdf, e.get("belge_turu", "?"))
        elif bicim == "metin_katmanli" and metinli is None:
            metinli = ("metin katmanli", pdf, e.get("belge_turu", "?"))
        if temiz and bozuk and metinli:
            break
    return [x for x in (temiz, bozuk, metinli) if x]


def kutu_oku(oge) -> tuple[float, float, float, float, str] | None:
    """Docling ögesinden (sol, ust, sag, alt, kaynak_sistemi) cikarir.

    Docling surumleri arasinda alan adlari degisebiliyor; birkac yol
    deneniyor ve bulunamazsa None donuyor. Tahmin yok.
    """
    prov = getattr(oge, "prov", None)
    if not prov:
        return None
    p = prov[0]
    kutu = getattr(p, "bbox", None)
    if kutu is None:
        return None
    try:
        sol = float(kutu.l)
        sag = float(kutu.r)
        ust = float(kutu.t)
        alt = float(kutu.b)
    except (AttributeError, TypeError, ValueError):
        return None
    kaynak = str(getattr(kutu, "coord_origin", "BELIRTILMEMIS"))
    return sol, ust, sag, alt, kaynak


def belgeyi_incele(etiket: str, pdf: Path, tur: str, donusturucu) -> None:
    print(f"\n{'=' * 72}")
    print(f"{pdf.name}   [{etiket}]   belge turu: {tur}")
    print("=" * 72)

    import time

    t0 = time.perf_counter()
    try:
        sonuc = donusturucu.convert(str(pdf))
    except Exception as e:  # noqa: BLE001
        print(f"  HATA: {type(e).__name__}: {e}")
        return
    sure = time.perf_counter() - t0
    belge = sonuc.document
    print(f"  donusturme suresi: {sure:.1f}s")

    # --- sayfa olculeri ---
    try:
        sayfalar = belge.pages
        ilk = sayfalar[next(iter(sayfalar))] if isinstance(sayfalar, dict) else sayfalar[0]
        boyut = getattr(ilk, "size", None)
        genislik = float(getattr(boyut, "width", 0)) if boyut else 0.0
        yukseklik = float(getattr(boyut, "height", 0)) if boyut else 0.0
        print(f"  sayfa sayisi: {len(sayfalar)}   olcu: {genislik:.0f} x {yukseklik:.0f}")
    except Exception as e:  # noqa: BLE001
        genislik = yukseklik = 0.0
        print(f"  sayfa olcusu okunamadi: {type(e).__name__}: {e}")

    # --- metin ogeleri ---
    ogeler = list(getattr(belge, "texts", []) or [])
    print(f"  metin ogesi: {len(ogeler)}")
    if not ogeler:
        print("  ! metin ogesi yok — koordinat cikarilamaz")
        return

    kutulu = 0
    kaynaklar: set[str] = set()
    baslik_y: list[float] = []
    dipnot_y: list[float] = []
    tum_y: list[float] = []
    egiklik_ornegi: list[tuple[str, float, float, float]] = []

    for oge in ogeler:
        metin = (getattr(oge, "text", "") or "").strip()
        k = kutu_oku(oge)
        if k is None:
            continue
        kutulu += 1
        sol, ust, sag, alt, kaynak = k
        kaynaklar.add(kaynak)
        tum_y.append(ust)
        kucuk = metin.casefold()
        if any(iz in kucuk for iz in DIPNOT_IZLERI):
            dipnot_y.append(ust)
        if any(iz in kucuk for iz in BASLIK_IZLERI) and len(metin) < 80:
            baslik_y.append(ust)
        # Ayni satirin iki ucu arasindaki yukseklik farki egiklige isaret eder
        if len(egiklik_ornegi) < 6 and len(metin) > 40:
            egiklik_ornegi.append((metin[:34], sol, sag, abs(ust - alt)))

    print(f"  kutusu olan: {kutulu} / {len(ogeler)}")
    print(f"  koordinat sistemi: {', '.join(kaynaklar) or 'BULUNAMADI'}")

    # --- ilk ve son ogeler, ham hâliyle ---
    print("\n  ILK 3 OGE (okuma sirasi)")
    for oge in ogeler[:3]:
        k = kutu_oku(oge)
        metin = (getattr(oge, "text", "") or "").strip()[:46]
        print(f"    {('ust=%7.1f alt=%7.1f' % (k[1], k[3])) if k else 'kutu yok  '}  {metin}")
    print("  SON 3 OGE")
    for oge in ogeler[-3:]:
        k = kutu_oku(oge)
        metin = (getattr(oge, "text", "") or "").strip()[:46]
        print(f"    {('ust=%7.1f alt=%7.1f' % (k[1], k[3])) if k else 'kutu yok  '}  {metin}")

    # --- SIFIR NEREDE ---
    print("\n  SIFIR NEREDE")
    if baslik_y and dipnot_y:
        bo, do = sum(baslik_y) / len(baslik_y), sum(dipnot_y) / len(dipnot_y)
        print(f"    baslik ogelerinin ort y : {bo:8.1f}")
        print(f"    dipnot ogelerinin ort y : {do:8.1f}")
        if do > bo:
            print("    -> y USTTEN artiyor (pdfplumber ile ayni). dipnot.py dogrudan calisir.")
        else:
            print("    -> y ALTTAN artiyor. dipnot.py'ye vermeden once cevrilmeli:")
            print(f"       y_ust = sayfa_yuksekligi - y_docling   (yukseklik={yukseklik:.0f})")
    else:
        print(f"    olculemedi (baslik={len(baslik_y)}, dipnot={len(dipnot_y)} oge)")
        if not dipnot_y:
            print("    ! dipnot izi HIC bulunamadi — OCR dipnotu okuyamamis olabilir")

    # --- ESIK PAYI ---
    if yukseklik and dipnot_y and tum_y:
        esik = yukseklik * 0.75
        dipnot_en_yukari = min(dipnot_y)
        govde = [y for y in tum_y if y < dipnot_en_yukari]
        print("\n  ESIK PAYI (y ustten varsayimiyla)")
        print(f"    govdenin en asagisi     : {max(govde) if govde else 0:8.1f}")
        print(f"    esik (yukseklik * 0.75) : {esik:8.1f}")
        print(f"    dipnotun en yukarisi    : {dipnot_en_yukari:8.1f}")
        if govde:
            print(f"    alt pay {esik - max(govde):7.1f}   ust pay {dipnot_en_yukari - esik:7.1f}")
            if esik - max(govde) < 30 or dipnot_en_yukari - esik < 30:
                print("    ! PAY DAR — bu belgede esik guvenli degil")

    # --- EGIKLIK ---
    print("\n  EGIKLIK IZI (satir kutusu yuksekligi)")
    print("    Sayfa egriyse OCR kutulari yatay satiri saramaz ve kutu")
    print("    yuksekligi yazi puntosunun cok uzerine cikar.")
    for metin, sol, sag, kutu_yuk in egiklik_ornegi:
        print(f"    yuk={kutu_yuk:6.1f}  genislik={sag - sol:6.1f}  {metin}")


def main(klasor_yolu: str | None) -> int:
    try:
        from docling.document_converter import DocumentConverter
    except ImportError:
        sys.exit("docling kurulu degil:  pip install docling")

    klasor = klasor_bul(klasor_yolu)
    ornekler = ornekleri_sec(klasor)
    if not ornekler:
        sys.exit(f"{klasor} icinde uygun ornek bulunamadi")

    print(f"klasor: {klasor}")
    print(f"incelenecek: {', '.join(p.name for _, p, _ in ornekler)}")

    donusturucu = DocumentConverter()
    for etiket, pdf, tur in ornekler:
        belgeyi_incele(etiket, pdf, tur, donusturucu)

    print(f"\n{'=' * 72}")
    print("Ciktinin TAMAMINI yapistirin. Ozellikle 'SIFIR NEREDE' ve")
    print("'EGIKLIK IZI' bolumleri — ikisi de tahminle degil olcumle kararlasacak.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else None))
