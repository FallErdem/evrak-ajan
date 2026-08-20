"""Dipnot ayrımını 300 belgenin TAMAMINDA doğrular — yerelde koşar.

NEDEN
-----
dipnot.py'nin eşiği ve iz listesi 10 belgelik örneklemden ölçüldü. 10'da
geçmesi 250'de geçtiği anlamına gelmez. Bu betik üç şeyi arıyor:

  1. SIZINTI     dipnot izi gövdede kalmış -> özet ve varlık çıkarımı bozulur
  2. KAYIP       dilekçenin kimlik bloğu dipnota düşmüş -> TCKN, adres,
                 telefon kaybolur; hem cevap anahtarı hem KVKK varlıkları
  3. ZAYIF       güçlü iz bulunamadı, zayıf ize düşüldü -> e-imza öncesi
                 biçim olabilir (belge_sablonu.json dipnot_alani.eimza_oncesi)

Ayrıca eşiğin iki uçtaki payını 300 belgede yeniden ölçer. Pay daralıyorsa
eşik yanlış yerdedir.

KULLANIM
--------
    python dipnot_dogrula.py                    # varsayılan: veri/belgeler
    python dipnot_dogrula.py C:\\yol\\belgeler   # açık yol

Yalnızca metin katmanlı PDF'lere bakar; taranmışlarda metin katmanı yoktur,
onlar OCR'dan sonra ayrı ölçülecek.

ÇIKTI
-----
Sorun yoksa "TEMIZ" yazar ve 0 döner. Sorun varsa belge numaralarını
listeler ve 1 döner.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK / "src"))

try:
    import pdfplumber
except ImportError:
    sys.exit("pdfplumber kurulu degil:  pip install pdfplumber")

from dipnot import dipnotu_ayir, pdfden_satirlar  # noqa: E402

# Belgelerin bulunabilecegi yerler, sirayla denenir.
ARAMA_YERLERI = (
    ("deneyler", "adim4", "belgeler_pdf"),
    ("veri", "belgeler"),
    ("ornek", "okuma_ornegi"),
)

# Gövdede ASLA bulunmaması gereken ifadeler.
SIZINTI_IZLERI = (
    "Doğrulama Kodu",
    "Belge Takip",
    "Doğrulama Adresi",
    "KEP Adresi",
    "güvenli elektronik imza",
)

# Dilekçe gövdesinde KALMASI gereken ifadeler.
KORUNACAK = ("T.C. Kimlik No", "Adres:", "Telefon:")

VATANDAS_TURLERI = {"dilekce", "bilgi_edinme", "sikayet", "basvuru", "itiraz"}


_ETIKET_KLASORU: Path | None = None


def etiket_klasoru_bul(pdf_klasoru: Path) -> Path | None:
    """etiket_*.json dosyalarinin klasorunu bir kez bulur ve akilda tutar."""
    global _ETIKET_KLASORU
    if _ETIKET_KLASORU is not None:
        return _ETIKET_KLASORU
    adaylar = [
        pdf_klasoru,
        pdf_klasoru.parent / "etiketler",
        pdf_klasoru.parent / "etiketler_json",
        pdf_klasoru.parent,
    ]
    for a in adaylar:
        if a.exists() and any(a.glob("etiket_*.json")):
            _ETIKET_KLASORU = a
            return a
    for bulunan in KOK.rglob("etiket_*.json"):   # son care
        _ETIKET_KLASORU = bulunan.parent
        return _ETIKET_KLASORU
    return None


def etiket_oku(klasor: Path, no: str) -> dict | None:
    ek = etiket_klasoru_bul(klasor)
    if ek is None:
        return None
    yol = ek / f"etiket_{no}.json"
    if not yol.exists():
        return None
    return json.loads(yol.read_text(encoding="utf-8"))


def klasor_bul(verilen: str | None) -> Path | None:
    """PDF klasorunu bulur. Once bilinen yerlere bakar, sonra tarar."""
    if verilen:
        y = Path(verilen)
        return y if y.exists() else None
    for parcalar in ARAMA_YERLERI:
        y = KOK.joinpath(*parcalar)
        if y.exists() and any(y.glob("belge_*.pdf")):
            return y
    for bulunan in KOK.rglob("belge_*.pdf"):   # son care
        return bulunan.parent
    return None


def main(klasor_yolu: str | None = None) -> int:
    klasor = klasor_bul(klasor_yolu)
    if klasor is None or not klasor.exists():
        klasor = Path(klasor_yolu) if klasor_yolu else KOK
        print(f"Klasor bulunamadi: {klasor}")
        print("Belgelerin bulundugu klasoru argüman olarak verin:")
        print(r"    python dipnot_dogrula.py C:\Users\...\veri\belgeler")
        return 1

    pdfler = sorted(klasor.rglob("belge_*.pdf"))
    if not pdfler:
        print(f"{klasor} icinde belge_*.pdf yok")
        return 1

    ek = etiket_klasoru_bul(klasor)
    print(f"{len(pdfler)} PDF bulundu: {klasor}")
    print(f"etiketler: {ek if ek else 'BULUNAMADI — kontroller kisitli'}\n")

    sizinti: list[str] = []
    kayip: list[tuple[str, list[str]]] = []
    zayif: list[str] = []
    etiketsiz: list[str] = []
    okunamayan: list[tuple[str, str]] = []
    atlanan = 0

    en_derin_govde = 0.0        # gövdenin en aşağı indiği nokta
    en_yuksek_dipnot = 10_000.0  # dipnotun en yukarı çıktığı nokta
    en_derin_belge = en_yuksek_belge = "—"

    for pdf in pdfler:
        no = pdf.stem.replace("belge_", "")
        etiket = etiket_oku(klasor, no)
        if etiket is None:
            etiketsiz.append(no)
            bicim, tur = "?", "?"
        else:
            bicim = etiket.get("pdf_bicimi", "?")
            tur = etiket.get("belge_turu", "?")

        if bicim == "taranmis":
            atlanan += 1
            continue

        try:
            with pdfplumber.open(pdf) as p:
                sayfa = p.pages[0]
                sonuc = dipnotu_ayir(pdfden_satirlar(sayfa), sayfa.height)
        except Exception as e:  # noqa: BLE001
            okunamayan.append((no, f"{type(e).__name__}: {e}"))
            continue

        govde_kucuk = sonuc.govde.casefold()
        if any(iz.casefold() in govde_kucuk for iz in SIZINTI_IZLERI):
            sizinti.append(no)

        if tur in VATANDAS_TURLERI:
            tamami = sonuc.govde + "\n" + sonuc.dipnot
            eksilen = [a for a in KORUNACAK if a in tamami and a not in sonuc.govde]
            if eksilen:
                kayip.append((no, eksilen))

        if sonuc.zayif_eslesme:
            zayif.append(no)

        if sonuc.govde_satirlari:
            derin = max(s.y for s in sonuc.govde_satirlari)
            if derin > en_derin_govde:
                en_derin_govde, en_derin_belge = derin, no
        if sonuc.dipnot_satirlari:
            yuksek = min(s.y for s in sonuc.dipnot_satirlari)
            if yuksek < en_yuksek_dipnot:
                en_yuksek_dipnot, en_yuksek_belge = yuksek, no

    # -------------------------------------------------------------------------
    incelenen = len(pdfler) - atlanan - len(okunamayan)
    print(f"incelenen (metin katmanli) : {incelenen}")
    print(f"atlanan (taranmis)         : {atlanan}")
    if okunamayan:
        print(f"okunamayan                 : {len(okunamayan)}")

    print("\nESIK PAYI")
    if en_yuksek_dipnot < 10_000:
        esik = 842 * 0.75
        print(f"  govdenin en asagi indigi : {en_derin_govde:6.0f} pt  (belge {en_derin_belge})")
        print(f"  esik                     : {esik:6.0f} pt")
        print(f"  dipnotun en yukari ciktigi: {en_yuksek_dipnot:6.0f} pt  (belge {en_yuksek_belge})")
        alt_pay = esik - en_derin_govde
        ust_pay = en_yuksek_dipnot - esik
        print(f"  alt pay {alt_pay:6.0f} pt   ust pay {ust_pay:6.0f} pt")
        if alt_pay < 30 or ust_pay < 30:
            print("  ⚠ PAY DARALDI — esik yanlis yerde olabilir, gozle bakin")
    else:
        print("  (dipnot bulunan belge yok)")

    print("\nBULGULAR")
    temiz = True
    if sizinti:
        temiz = False
        print(f"  ✗ SIZINTI  {len(sizinti)} belge — dipnot govdede kaldi")
        print(f"      {', '.join(sizinti[:25])}{' ...' if len(sizinti) > 25 else ''}")
    if kayip:
        temiz = False
        print(f"  ✗ KAYIP    {len(kayip)} belge — dilekce kimlik blogu dipnota dustu")
        for no, alanlar in kayip[:15]:
            print(f"      {no}: {', '.join(alanlar)}")
    if zayif:
        temiz = False
        print(f"  ⚠ ZAYIF    {len(zayif)} belge — guclu iz yok, zayif ize dusuldu")
        print(f"      {', '.join(zayif[:25])}{' ...' if len(zayif) > 25 else ''}")
        print("      Bunlar e-imza oncesi bicim olabilir. Gozle bakin.")
    if okunamayan:
        temiz = False
        print(f"  ✗ OKUNAMAYAN {len(okunamayan)} belge")
        for no, hata in okunamayan[:10]:
            print(f"      {no}: {hata}")
    if etiketsiz:
        print(f"  · etiketi bulunamayan {len(etiketsiz)} belge (kontrol kisitli)")

    if temiz:
        print("  ✓ sizinti yok, kayip yok, zayif eslesme yok")
        print("\nTEMIZ")
        return 0

    print("\nSORUN VAR — cikti Claude'a yapistirilsin")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else None))
