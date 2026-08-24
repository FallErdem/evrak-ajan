"""Yazar'ın deterministik katmanını (2a) cevap anahtarına karşı ölçer.

NEREYE:  araclar/
NASIL:   python araclar\\yon_dogrula.py 50     hızlı deneme
         python araclar\\yon_dogrula.py        tamamı
ÇIKTI:   yon_dogrula_sonuc.txt

LLM ÇAĞRISI YOK. Bu kapı kredi harcamadan geçilir.

ÜÇ ŞEY ÖLÇÜLÜYOR
----------------
    kimlik    taslağı yazan birim doğru mu   (etiket: alici.birim_kodu)
    yon       arz/rica yönü doğru mu         (etiket: hiyerarsi_yonu'nun TERSİ)
    imza      imza unvanı doğru mu           (etiket: alici.imza_unvani)

ÇERÇEVE — dikkat
----------------
Etiketteki `hiyerarsi_yonu` GELEN belgenin yönüdür: muhatabın (bizim)
gönderene göre konumu. Taslakta roller yer değişiyor, muhatap onlar oluyor.
Doğru cevap bu yüzden TERS çevriliyor:

    etiket 'ust'                -> taslak 'alt'         rica
    etiket 'alt'                -> taslak 'ust'         arz
    etiket 'ayni'               -> taslak 'ayni'        arz     tek simetrik
    etiket 'ozel_tuzel'         -> taslak 'kurum_disi'  rica
    etiket 'gercek_kisi_yazari' -> taslak 'gercek_kisi' sunulur

Beşin dördü yön değiştiriyor. `kota.json > kapanis_kurali` tablosunu
doğrudan taslağa uygulayan bir kod 300 belgenin 144'ünde yanılırdı; bu
betiğin varlık sebebi o hatayı görünür tutmak.

KİMLİK EŞİĞİ KALİBRASYONU
-------------------------
`yazar.KIMLIK_ESIGI` üç gözlemle 0,85 seçildi, ölçüm değil. Bu betik
eşleşme oranını bantlar hâlinde raporluyor ve her bantta isabeti veriyor;
300 belgelik koşudan sonra eşik oradan okunacak.
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
    ("ornek",),
)

CIKTI = KOK / "yon_dogrula_sonuc.txt"

# Etiketin GELEN çerçevesindeki yönü -> taslağın GİDEN çerçevesindeki yönü.
TERS = {
    "ust": "alt",
    "alt": "ust",
    "ayni": "ayni",
    "ozel_tuzel": "kurum_disi",
    "gercek_kisi_yazari": "gercek_kisi",
}

# Beklenen kapanış — yazar.KAPANIS ile aynı olmalı, ayrı yazılıyor ki
# ölçüm ölçtüğü koddan bağımsız kalsın. İkisi ayrışırsa test bunu görür.
BEKLENEN_KAPANIS = {
    "ust": "Arz ederim.",
    "ayni": "Arz ederim.",
    "alt": "Rica ederim.",
    "karma": "Arz ve rica ederim.",
    "kurum_disi": "Rica ederim.",
    "gercek_kisi": "Bilgilerinize sunulur.",
}

# Dağıtımlı belgede gelen yazı "arz ve rica" ile biter ama BİZİM taslağımız
# tek bir muhataba gider; karma kapanış taslakta oluşamaz. Bu belgelerde yön
# ölçülüyor, kapanış ölçülmüyor.
DAGITIMLI = "dagitim"


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


def _bant(oran: float) -> str:
    if oran >= 1.0:
        return "1.00  tam eslesme"
    if oran >= 0.90:
        return "0.90-0.99"
    if oran >= 0.85:
        return "0.85-0.89"
    if oran >= 0.75:
        return "0.75-0.84"
    return "<0.75 / yok"


def main() -> int:
    from ayristirici import ayristir
    from okuyucu import oku
    from veri_yapisi import Dosya
    from yazar import KIMLIK_ESIGI, iskelet_kur

    sinir = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    pdf_klasoru = klasor_bul()
    ek = etiket_klasoru(pdf_klasoru)
    pdfler = sorted(pdf_klasoru.glob("belge_*.pdf"))
    if sinir:
        pdfler = pdfler[:sinir]

    cikti: list[str] = []

    def yaz(s: str = "") -> None:
        print(s)
        cikti.append(s)

    kimlik = Counter()
    yon = Counter()
    imza = Counter()
    hatlar = Counter()
    bant_isabet: dict[str, Counter] = defaultdict(Counter)
    yon_karisim: Counter = Counter()
    tirmandirilan = Counter()
    kimlik_sebep: Counter = Counter()
    kimlik_hata: list[str] = []
    yon_hata: list[str] = []
    t0 = time.perf_counter()
    n = 0

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
        d.metin = r.govde
        isk = iskelet_kur(d)
        n += 1

        # -- kimlik ---------------------------------------------------------
        #
        # İKİ VAKA MUHATAP SATIRINDAN TÜRETİLEMEZ — ÖLÇÜLDÜ 2026-08-24
        # -----------------------------------------------------------
        #     dağıtımlı belge      muhatap "DAĞITIM YERLERİNE" (M-11)
        #     muhatap_belirsiz     muhatap "İLGİLİ MAKAMA" (kasten bozulmuş)
        #
        # 27 "eksik" kimliğin 22'si bu ikisiydi. İkisinde de belgenin
        # üstünde hangi birime geldiği YAZMIYOR; cevabı Yönlendirici verir
        # ve `yonlendirme.hedef_birim` dolunca `kim_yaziyor` onu ilk sırada
        # kullanır. Bunları eksik saymak Yazar'ı, yapmadığı bir işin
        # eksiğiyle suçlamak olur.
        dagitimli = (e.get("muhatap_makam") == "DAĞITIM YERLERİNE"
                     or bool(e.get("dagitim")))
        belirsiz_kusur = e.get("kusur") == "muhatap_belirsiz"
        bek_kod = e["alici"]["birim_kodu"]
        bul_kod = isk.kimlik.kod

        if (dagitimli or belirsiz_kusur) and bul_kod is None:
            kimlik["olculemez"] += 1
            kimlik_sebep["dağıtımlı belge" if dagitimli
                         else "muhatap_belirsiz kusuru"] += 1
            k_ok = None
        else:
            k_ok = bul_kod == bek_kod
            kimlik["dogru" if k_ok else ("YANLIS" if bul_kod else "eksik")] += 1
            bant_isabet[_bant(isk.kimlik.oran)]["dogru" if k_ok else "YANLIS"] += 1
            if not k_ok:
                kimlik_hata.append(
                    f"  {no}  beklenen {bek_kod}, bulunan {bul_kod} "
                    f"(oran {isk.kimlik.oran:.2f}, {isk.kimlik.kaynak})")

        # -- imza unvani ----------------------------------------------------
        bek_imza = e["alici"].get("imza_unvani")
        if k_ok is None:
            imza["olculemez"] += 1
        else:
            imza["dogru" if d.cikti_yazi.imza_unvan == bek_imza
                 else ("YANLIS" if d.cikti_yazi.imza_unvan else "eksik")] += 1

        # -- yon ------------------------------------------------------------
        bek_yon = TERS.get(e["hiyerarsi_yonu"])
        bul_yon = str(d.cikti_yazi.hiyerarsi_yonu or "")
        hatlar[isk.yon.hat] += 1
        if bek_yon is None:
            yon["olculemez"] += 1
        else:
            bek_kap = BEKLENEN_KAPANIS.get(bek_yon)
            # Kapanış eşitse yön doğru sayılıyor: UST ile AYNI aynı kapanışı
            # üretiyor ve tablo ikisini ayırmıyor; ayırmadığımız bir şeyi
            # yanlış saymak ölçümü kirletir. Ayrım yalnızca insan onayı
            # kararında önemli ve o da ayrıca raporlanıyor.
            if bul_yon == bek_yon:
                yon["dogru"] += 1
            elif isk.yon.kapanis == bek_kap:
                yon["kapanis dogru, yon farkli"] += 1
                yon_karisim[f"{bek_yon} -> {bul_yon}"] += 1
            else:
                yon["YANLIS"] += 1
                yon_hata.append(
                    f"  {no}  beklenen {bek_yon} ({bek_kap}), "
                    f"bulunan {bul_yon} ({isk.yon.kapanis})  [{isk.yon.hat}]")

        if isk.insan_onayi_gerek:
            for s in isk.sebepler:
                tirmandirilan[s[:60]] += 1

        if i % 25 == 0:
            print(f"    ... {i}/{len(pdfler)}", file=sys.stderr)

    sure = time.perf_counter() - t0

    yaz("=" * 72)
    yaz("YAZAR 2a — KİMLİK, YÖN, KAPANIŞ (LLM yok)")
    yaz("=" * 72)
    yaz(f"belge: {n}   süre: {sure:.1f} sn   KIMLIK_ESIGI = {KIMLIK_ESIGI}")
    yaz()

    yaz("1  TASLAĞI KİM YAZIYOR")
    yaz("-" * 72)
    payda = kimlik["dogru"] + kimlik["YANLIS"] + kimlik["eksik"]
    for k in ("dogru", "YANLIS", "eksik"):
        pay = f"%{100 * kimlik[k] / payda:.1f}" if payda else "—"
        yaz(f"  {k:12s} {kimlik[k]:4d}   {pay}")
    yaz(f"  {'olculemez':12s} {kimlik['olculemez']:4d}   —")
    for k, v in kimlik_sebep.most_common():
        yaz(f"      {v:4d}  {k}")
    yaz()
    yaz("  ölçülemez = alıcı birim muhatap satırından türetilemez; cevabı")
    yaz("  Yönlendirici verir (yonlendirme.hedef_birim).")
    yaz()

    yaz("2  İMZA UNVANI")
    yaz("-" * 72)
    for k in ("dogru", "YANLIS", "eksik", "olculemez"):
        yaz(f"  {k:12s} {imza[k]:4d}")
    yaz()

    yaz("3  ARZ / RİCA YÖNÜ")
    yaz("-" * 72)
    for k, v in yon.most_common():
        yaz(f"  {k:28s} {v:4d}")
    if yon_karisim:
        yaz()
        yaz("  yön farklı ama kapanış aynı (tablo üst/aynı ayırmıyor):")
        for k, v in yon_karisim.most_common():
            yaz(f"      {v:4d}  {k}")
    yaz()

    yaz("4  HANGİ HAT KARAR VERDİ")
    yaz("-" * 72)
    for k, v in hatlar.most_common():
        yaz(f"  {v:4d}  {k}")
    yaz()

    yaz("5  KİMLİK EŞİĞİ KALİBRASYONU  —  KIMLIK_ESIGI buradan okunacak")
    yaz("-" * 72)
    yaz(f"  {'bant':18s} {'dogru':>6s} {'YANLIS':>7s}")
    for b in ("1.00  tam eslesme", "0.90-0.99", "0.85-0.89",
              "0.75-0.84", "<0.75 / yok"):
        c = bant_isabet[b]
        if c:
            yaz(f"  {b:18s} {c['dogru']:6d} {c['YANLIS']:7d}")
    yaz()
    yaz("  Eşik, YANLIŞ'ların yoğunlaştığı bandın üstüne konur. Bir bantta")
    yaz("  hem doğru hem yanlış varsa oran tek başına ayırmıyor demektir.")
    yaz()

    if tirmandirilan:
        yaz("6  İNSAN ONAYINA TIRMANDIRILANLAR")
        yaz("-" * 72)
        for k, v in tirmandirilan.most_common(10):
            yaz(f"  {v:4d}  {k}")
        yaz()

    if kimlik_hata:
        yaz(f"7  KİMLİK HATALARI  ({len(kimlik_hata)})")
        yaz("-" * 72)
        for s in kimlik_hata[:30]:
            yaz(s)
        yaz()

    if yon_hata:
        yaz(f"8  YÖN HATALARI  ({len(yon_hata)})")
        yaz("-" * 72)
        for s in yon_hata[:30]:
            yaz(s)
        yaz()

    CIKTI.write_text("\n".join(cikti) + "\n", encoding="utf-8")
    print(f"\nyazildi: {CIKTI}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
