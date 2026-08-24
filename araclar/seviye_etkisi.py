"""İlçe MEM seviye değişikliğinin muhatap eşleştirmesine etkisi.

NEREYE:  araclar/
NASIL:   python araclar\\seviye_etkisi.py 50    hızlı deneme
         python araclar\\seviye_etkisi.py       tamamı
ÇIKTI:   seviye_etkisi_sonuc.txt

NEDEN AYRI BETİK — iki koşu yerine bir koşu
-------------------------------------------
`birimler_ilmem.csv`'de yenimahalle_ilce_mem'in `hiyerarsi_seviyesi` alanı
2'den 3'e çıkarıldı. Gerekçe: etiketler İlçe MEM'i şube müdürlüklerinin
ALTINDA konumlandırıyor (İlçe MEM bir şubeye yazdığında hiyerarsi_yonu
"ust", yani şube üst kabul ediliyor), CSV ise ikisini eşit yazmıştı. Bu
yüzden arz/rica yönü 5 belgede yanlış çıkıyordu.

Değişiklik risksiz DEĞİL: `metin.en_iyi_eslesme` hiyerarşi seviyesini
EŞİTLİK BOZUCU olarak kullanıyor ve muhatap eşleştirmesi 300 belgede
ölçülmüş bir sonuç. Seviyeyi kaydırmak o sonucu sessizce bozabilir.

Doğru test "önce koştur, değiştir, sonra koştur"dur — ama o iki ayrı PDF
okuması demek (~35 dk) ve iki koşu arasında OCR'ın aynı çıktıyı vereceği
VARSAYILIR. Bu betik aynı PDF'i bir kez okur ve AYNI muhatap dizesini iki
ayarla değerlendirir. Daha ucuz ve daha kesin: koşular arası varyans yok.

KAPSAM — dürüst sınır
---------------------
Yalnızca `muhatap` alanı ölçülüyor. Diğer altı alan (sayı, tarih, konu,
ilgi, ek, imza) birim tablosuna hiç bakmıyor; saf desen eşleştirmesi
yapıyorlar ve `hiyerarsi_seviyesi` alanından etkilenmeleri mümkün değil.
Bu yüzden `ayristirici_dogrula.py`'nin tamamını iki kez koşturmaya gerek
kalmıyor. Şüphe varsa o koşu yine yapılabilir; bu betik onun yerine
geçmeyi değil, ondan önce cevabı vermeyi amaçlıyor.

ÖN ÖLÇÜM (bu betikten bağımsız, 2026-08-24)
-------------------------------------------
Etiketlerdeki 300 TEMİZ muhatap dizesi ve 10 OCR hasarlı/varyant dize
iki ayarla karşılaştırıldı: sonucu değişen belge SIFIR. Beklenti bu
yönde; bu betik beklentiyi gerçek OCR çıktısında sınıyor.
"""

from __future__ import annotations

import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "src"))

KURUMLAR = KOK / "veri" / "kurumlar"
CSV_DOSYALARI = ("birimler.csv", "birimler_ilmem.csv", "birimler_gazi.csv")

DEGISEN_BIRIM = "yenimahalle_ilce_mem"
ESKI_SEVIYE = 2
YENI_SEVIYE = 3

# birimler.py ile aynı kural — seviye 1 gözetim katmanı, hedef olamaz.
HEDEF_OLAMAYAN_SEVIYE = 1

ARAMA_YERLERI = (
    ("deneyler", "adim4", "belgeler_pdf"),
    ("veri", "belgeler"),
    ("ornek",),
)

CIKTI = KOK / "seviye_etkisi_sonuc.txt"


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


def adaylar(ilce_seviyesi: int) -> list[tuple[str, str, int]]:
    """CSV'yi doğrudan okur; birimler.py'nin önbelleğinden bağımsız.

    İki ayarı aynı süreçte kurabilmek için gerekli — `birimleri_yukle`
    lru_cache'li ve seviye alanını çalışma anında değiştiremiyoruz.
    """
    out: list[tuple[str, str, int]] = []
    for ad in CSV_DOSYALARI:
        yol = KURUMLAR / ad
        with yol.open(encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                sv = int(r["hiyerarsi_seviyesi"])
                if r["birim_kodu"] == DEGISEN_BIRIM:
                    sv = ilce_seviyesi
                if sv == HEDEF_OLAMAYAN_SEVIYE:
                    continue
                out.append((r["birim_kodu"], r["birim_adi"], sv))
    return out


def main() -> int:
    from ayristirici import ayristir
    from metin import en_iyi_eslesme
    from okuyucu import oku

    sinir = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    pdf_klasoru = klasor_bul()
    ek = etiket_klasoru(pdf_klasoru)
    pdfler = sorted(pdf_klasoru.glob("belge_*.pdf"))
    if sinir:
        pdfler = pdfler[:sinir]

    A_eski = adaylar(ESKI_SEVIYE)
    A_yeni = adaylar(YENI_SEVIYE)

    cikti: list[str] = []

    def yaz(s: str = "") -> None:
        print(s)
        cikti.append(s)

    isabet = Counter()
    degisen: list[str] = []
    okunamadi = 0
    muhatapsiz = 0
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
        m = a.ustveri.muhatap
        arama = " ".join(x for x in (getattr(m, "ham", None),
                                     getattr(m, "birim", None)) if x).strip()
        if not arama:
            muhatapsiz += 1
            continue
        n += 1

        k1, o1, _ = en_iyi_eslesme(arama, A_eski)
        k2, o2, _ = en_iyi_eslesme(arama, A_yeni)
        bek = e["alici"]["birim_kodu"]
        isabet["eski dogru"] += (k1 == bek)
        isabet["yeni dogru"] += (k2 == bek)

        if k1 != k2:
            degisen.append(
                f"  {no}  {arama[:50]!r}\n"
                f"        seviye2 -> {k1} ({o1:.2f})\n"
                f"        seviye3 -> {k2} ({o2:.2f})\n"
                f"        beklenen {bek}"
            )

        if i % 25 == 0:
            print(f"    ... {i}/{len(pdfler)}", file=sys.stderr)

    sure = time.perf_counter() - t0

    yaz("=" * 72)
    yaz("İLÇE MEM SEVİYE DEĞİŞİKLİĞİ — MUHATAP EŞLEŞTİRMESİNE ETKİSİ")
    yaz("=" * 72)
    yaz(f"{DEGISEN_BIRIM}: hiyerarsi_seviyesi {ESKI_SEVIYE} -> {YENI_SEVIYE}")
    yaz(f"ölçülen: {n} belge   okunamadı: {okunamadi}   muhatapsız: {muhatapsiz}"
        f"   süre: {sure:.1f} sn")
    yaz(f"aday kümesi: eski {len(A_eski)} birim, yeni {len(A_yeni)} birim")
    yaz()
    yaz("MUHATAP İSABETİ  —  ikisi eşitse değişiklik güvenli")
    yaz("-" * 72)
    yaz(f"  seviye 2 (eski) : {isabet['eski dogru']:4d} / {n}")
    yaz(f"  seviye 3 (yeni) : {isabet['yeni dogru']:4d} / {n}")
    yaz()
    if degisen:
        yaz(f"SONUCU DEĞİŞEN BELGE: {len(degisen)}")
        yaz("-" * 72)
        for s in degisen[:40]:
            yaz(s)
    else:
        yaz("SONUCU DEĞİŞEN BELGE: 0")
        yaz("-" * 72)
        yaz("  Aynı OCR dizesi iki ayarla da aynı birime bağlandı.")
        yaz("  `metin.en_iyi_eslesme` seviyeyi yalnızca EŞİTLİK BOZUCU olarak")
        yaz("  kullanıyor ve İlçe MEM hiçbir belgede başka bir birimle aynı")
        yaz("  eşleşme sınıfında yarışmıyor; bu yüzden kaydırma etkisiz.")
    yaz()

    CIKTI.write_text("\n".join(cikti) + "\n", encoding="utf-8")
    print(f"\nyazildi: {CIKTI}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
