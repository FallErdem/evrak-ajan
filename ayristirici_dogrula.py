"""Ayrıştırıcı'yı 300 belgede cevap anahtarına karşı ölçer.

NEREYE:  depo kökü
NASIL:   python ayristirici_dogrula.py 50     -> hizli deneme (~4 dk)
         python ayristirici_dogrula.py        -> tamami (~20 dk, 50'si OCR)
ÇIKTI:   ayristirici_dogrula_sonuc.txt

ÜÇ BELGE AİLESİ
---------------
    kurum    T.C. başlığı + sayı/konu/ilgi + EBYS dipnotu
    şirket   antetli kâğıt, sayı ve konu VAR, T.C. ve dipnot YOK
             sayı biçimi farklı: 2026/335 (yıl/sıra), DETSİS ve SDP yok
    dilekçe  başlık yok, sayı yok, konu yok

ÖLÇÜLEMEYEN VAKALAR — ceza yazılmaz
-----------------------------------
Bir alanın belgede BULUNMADIĞI veya KASTEN BOZULDUĞU durumlarda
ayrıştırıcının onu bulamaması DOĞRU sonuçtur. Etiket her zaman DOĞRU değeri
tutar; PDF'te olan şey başkadır. Aradaki farkı bilmeden ölçmek, ayrıştırıcıyı
üretecin kasten yaptığı hatadan sorumlu tutmak olur.

2026-08-21 DÜZELTMESİ — bu dosyanın kendi hatasıydı
---------------------------------------------------
Önceki sürüm yalnızca iki kusuru muaf tutuyordu (sayi_eksik, sdp_uyumsuz),
oysa üreteç BEŞ alanı birden siliyor/bozuyor. Ölçüm sonucu (50 belge):

    021, 023  tarih_eksik       -> tarih "bulunamadı" diye ceza yazılmış
    025       imza_eksik        -> imza  "bulunamadı" diye ceza yazılmış
    043, 050  muhatap_belirsiz  -> muhatap "bulunamadı" diye ceza yazılmış

Beş belge, üç alan, hepsi yanlış alarm. PARCA2_DEVIR_NOTLARI 4.4:
"Doğrulayıcı hata verdiğinde önce belgeye bakın." Bu tam o vaka.

MUAF TUTULMAYANLAR — bilinçli karar
-----------------------------------
    ek_beyani_yanlis  Beyanda 3 adet yazar, listede 1 ek vardır. Etiketteki
                      ek.adet LİSTEYİ tutar (=1). Ayrıştırıcı listeyi okur,
                      beyana kanmamalıdır. Ölçülebilir ve ölçülmelidir.
    ilgi_kopuk        İlgi SATIRI sağlamdır; bozulan şey gövdedeki atıftır.
    tarih_tutarsiz    İki tarih de okunabilir; tutarsızlık Denetçi'nin işi.
    kapanis_yanlis    Bu yedi alanın hiçbirine dokunmaz.
    tarama_bozuk      Zor vaka, kusur değil. Ayrıştırıcı bunu geçmeli.

ÜÇ TABLO
--------
1  ALAN BAZINDA İSABET   ölçülebilir alanlarda doğruluk
2  PDF BİÇİMİNE GÖRE     metin katmanlı / taranmış kırılımı — hatanın OCR'da
                         mı mantıkta mı olduğunu ancak bu ayrım gösterir
3  KUSUR TESPİTİ         muaf tutulan alanlarda ayrıştırıcı UYDURDU MU
                         (ADIM 4 kapısı: eksik alan uydurmama >= 0.95)
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK / "src"))

ARAMA_YERLERI = (
    ("deneyler", "adim4", "belgeler_pdf"),
    ("veri", "belgeler"),
    ("ornek", "okuma_ornegi"),
)

ALANLAR = ("sayi", "tarih", "konu", "ilgi", "ek", "muhatap", "imza")

# Hangi kusur hangi alanı ÖLÇÜLEMEZ yapar.
# Kaynak: etiket dosyalarındaki kusur_ayrinti.alan alanı, 300 etikette sayıldı.
KUSUR_ALAN = {
    "sayi_eksik": "sayi",          # 12 belge — sayı satırı boş basılır
    "sdp_uyumsuz": "sayi",         # 12 belge — sayı içindeki SDP kodu bozulur
    "tarih_eksik": "tarih",        # 12 belge — tarih basılmaz
    "konu_eksik": "konu",          # 10 belge — konu satırı boş basılır
    "imza_eksik": "imza",          # 10 belge — imza bloğu basılmaz
    "muhatap_belirsiz": "muhatap",  # 10 belge — "İLGİLİ MAKAMA" basılır
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
    for a in (pdf_klasoru, pdf_klasoru.parent / "etiketler", pdf_klasoru.parent):
        if a.exists() and any(a.glob("etiket_*.json")):
            return a
    for b in KOK.rglob("etiket_*.json"):
        return b.parent
    sys.exit("etiket_*.json bulunamadi.")


def beklentiler(e: dict) -> dict[str, object | None]:
    """Her alan için beklenen değer; None ise o belge o alandan ölçülmez."""
    tip = (e.get("gonderen") or {}).get("tip")
    # Sayı ve konu satırı olan iki aile: kurum ve şirket.
    # Dilekçede ikisi de yok (belge_sablonu.json vatandas_dilekcesi).
    baslikli = tip in ("kurum", "ozel_tuzel_kisi")

    bek: dict[str, object | None] = {
        "sayi": e.get("sayi"),
        "tarih": e.get("tarih"),
        "konu": e.get("konu") if baslikli else None,
        "ilgi": e.get("ilgi"),
        "ek": e.get("ek"),
        "muhatap": e.get("muhatap_makam"),
        "imza": True if baslikli else None,
    }

    # Kasten bozulan alan ölçülmez; ayrı tabloda "uydurdu mu" diye ölçülür.
    muaf = KUSUR_ALAN.get(e.get("kusur"))
    if muaf:
        bek[muaf] = None
    return bek


def bulunanlar(u) -> dict[str, object]:
    return {
        "sayi": u.sayi,
        "tarih": u.tarih.strftime("%d.%m.%Y") if u.tarih else None,
        "konu": u.konu,
        "ilgi": u.ilgi[0] if u.ilgi else None,
        "ek": u.ekler,
        "muhatap": u.muhatap.ham,
        "imza": u.imza.ad,
    }


def dogru_mu(alan: str, bulunan, beklenen) -> bool:
    from metin import katla

    if alan == "ilgi":
        return bool(bulunan) and bulunan.sayi == beklenen.get("sayi")
    if alan == "ek":
        return len(bulunan) == beklenen.get("adet")
    if alan == "muhatap":
        return bool(bulunan) and katla(beklenen) in katla(bulunan)
    if alan == "imza":
        return bool(bulunan)
    return bulunan == beklenen


def konu_katlanmis_dogru_mu(bulunan, beklenen) -> bool:
    """Konu için gevşek karşılaştırma — Türkçe işaretler ve harf boyu düşer.

    Neden ayrı ölçülüyor: OCR "İhtilaflı" kelimesini "ihtilaflı" okuyor
    (belge_009, ölçüldü). İçerik aynı, yalnızca işaret bozuk. Birebir ölçüm
    bunu hata sayar; katlanmış ölçüm saymaz.

    İKİSİ DE RAPORLANIR. Hangisinin doğru ölçüt olduğu bir karardır ve
    tek bir sayının arkasına saklanmamalıdır: konu metni özete ve taslağa
    olduğu gibi taşınıyorsa birebir ölçüm anlamlıdır; yalnızca eşleştirme
    ve sınıflandırma için kullanılıyorsa katlanmış ölçüm anlamlıdır.
    """
    from metin import katla

    return bool(bulunan) and katla(bulunan) == katla(beklenen)


def muhatap_katlanmis_dogru_mu(bulunan, beklenen) -> bool:
    """Muhatap için bulanık karşılaştırma.

    Neden ayrı ölçülüyor: OCR "MİLLÎ" kelimesini "MİLL{" okuyor (belge_009
    ve 032, ölçüldü). Birebir alt dize araması bunu hata sayar. Oysa boru
    hattı muhatabı birimler.json'daki kanonik kayda `en_iyi_eslesme` ile
    BULANIK eşleştiriyor; birebir ölçüm sistemin yapmadığı bir şeyi ölçer.

    İKİSİ DE RAPORLANIR: `muhatap` birebir, `muhatap~` bulanık.
    """
    from metin import icinde_gecer_mi

    if not bulunan:
        return False
    geciyor, _ = icinde_gecer_mi(beklenen, bulunan, esik=0.80)
    return geciyor


def kusur_tespiti(e: dict, bul: dict) -> tuple[bool, str]:
    """Kasten bozulan alanda ayrıştırıcı UYDURDU MU.

    Geçme ölçütü kusura göre değişir:

      sdp_uyumsuz       BELGEYE SADIK olmalı — bozuk sayıyı aynen döndürmeli.
                        Etiketteki düzeltilmiş değeri döndürürse UYDURMUŞ olur.
      muhatap_belirsiz  Doğru kurum adını ÜRETMEMELİ. Belgede "İLGİLİ MAKAMA"
                        yazıyor; oradan kurum adı çıkarmak uydurmadır.
      diğerleri         Alan belgede YOK. None döndürmeli.
    """
    from metin import katla

    kusur = e.get("kusur")
    alan = KUSUR_ALAN[kusur]
    bulunan = bul[alan]
    ayr = e.get("kusur_ayrinti") or {}

    if kusur == "sdp_uyumsuz":
        beklenen = ayr.get("enjekte_edilen")
        return bulunan == beklenen, f"belgedeki bozuk sayı: {beklenen}"

    if kusur == "muhatap_belirsiz":
        dogru = ayr.get("dogru_deger") or ""
        if not bulunan:
            return True, "muhatap üretilmedi"
        uydurdu = bool(dogru) and katla(dogru) in katla(bulunan)
        return not uydurdu, f"belgede yok ama üretildi: {str(bulunan)[:40]}"

    bos = bulunan in (None, "", False) or (isinstance(bulunan, list) and not bulunan)
    return bos, f"belgede yok ama üretildi: {str(bulunan)[:40]}"


def main(argv: list[str]) -> int:
    from ayristirici import ayristir
    from okuyucu import oku

    sinir = next((int(a) for a in argv if a.isdigit()), None)
    klasor = klasor_bul()
    ek = etiket_klasoru(klasor)
    pdfler = sorted(klasor.glob("belge_*.pdf"))
    if sinir:
        pdfler = pdfler[:sinir]

    cikti = KOK / "ayristirici_dogrula_sonuc.txt"
    with cikti.open("w", encoding="utf-8") as f:
        def yaz(s: str = "") -> None:
            print(s)
            f.write(s + "\n")

        yaz(f"klasor: {klasor}   belge: {len(pdfler)}\n")

        dogru = Counter()
        olculen = Counter()
        atlanan = Counter()
        # bicim -> alan -> sayaç
        b_dogru: dict[str, Counter] = defaultdict(Counter)
        b_olculen: dict[str, Counter] = defaultdict(Counter)
        b_belge = Counter()
        konu_katli_dogru = 0
        konu_katli_olculen = 0
        muh_katli_dogru = 0
        muh_katli_olculen = 0
        kusur_gecti = Counter()
        kusur_toplam = Counter()
        kusur_hatalari: list[str] = []
        hatalar: dict[str, list[tuple[str, str, str]]] = {a: [] for a in ALANLAR}
        kanitsiz: list[str] = []
        aile_sayaci = Counter()
        aile_yanlis: list[str] = []
        okuma_hatasi: list[str] = []
        t0 = time.perf_counter()

        for i, pdf in enumerate(pdfler, 1):
            no = pdf.stem.replace("belge_", "")
            ey = ek / f"etiket_{no}.json"
            if not ey.exists():
                continue
            e = json.loads(ey.read_text(encoding="utf-8"))
            bicim = e.get("pdf_bicimi", "bilinmiyor")
            b_belge[bicim] += 1

            r = oku(str(pdf))
            if r.hata or not r.ayrilmis:
                okuma_hatasi.append(f"{no}: {r.hata}")
                continue

            a = ayristir(r.ayrilmis.govde_satirlari)
            bek = beklentiler(e)
            bul = bulunanlar(a.ustveri)

            aile_sayaci[a.aile] += 1
            beklenen_aile = {"kurum": "kurum", "ozel_tuzel_kisi": "sirket"}.get(
                (e.get("gonderen") or {}).get("tip"), "dilekce"
            )
            if a.aile != beklenen_aile and len(aile_yanlis) < 12:
                aile_yanlis.append(
                    f"{no} ({bicim}): {beklenen_aile} beklenirken {a.aile}"
                )

            for alan in ALANLAR:
                if bek[alan] is None:
                    atlanan[alan] += 1
                    continue
                olculen[alan] += 1
                b_olculen[bicim][alan] += 1
                if dogru_mu(alan, bul[alan], bek[alan]):
                    dogru[alan] += 1
                    b_dogru[bicim][alan] += 1
                elif len(hatalar[alan]) < 10:
                    hatalar[alan].append(
                        (f"{no} {bicim[:5]}", str(bek[alan])[:38], str(bul[alan])[:38])
                    )

            # Konu ve muhatap ayrıca gevşek karşılaştırmayla da ölçülür
            if bek["konu"] is not None:
                konu_katli_olculen += 1
                if konu_katlanmis_dogru_mu(bul["konu"], bek["konu"]):
                    konu_katli_dogru += 1
            if bek["muhatap"] is not None:
                muh_katli_olculen += 1
                if muhatap_katlanmis_dogru_mu(bul["muhatap"], bek["muhatap"]):
                    muh_katli_dogru += 1

            # Kusurlu alanda uydurma kontrolü
            kusur = e.get("kusur")
            if kusur in KUSUR_ALAN:
                kusur_toplam[kusur] += 1
                gecti, aciklama = kusur_tespiti(e, bul)
                if gecti:
                    kusur_gecti[kusur] += 1
                elif len(kusur_hatalari) < 12:
                    kusur_hatalari.append(f"{no} {kusur}: {aciklama}")

            # Bulunan her alanın kanıtı olmalı — arayüz vurgulaması buna bağlı
            for anahtar, deger in (("ustveri.sayi", a.ustveri.sayi),
                                   ("ustveri.tarih", a.ustveri.tarih),
                                   ("ustveri.konu", a.ustveri.konu)):
                if deger is not None and anahtar not in a.kanit:
                    kanitsiz.append(f"{no}:{anahtar}")

            if i % 25 == 0:
                print(f"    ... {i}/{len(pdfler)}", flush=True)

        gecen = time.perf_counter() - t0

        # --- 1. tablo -------------------------------------------------------
        yaz("=" * 70)
        yaz("1  ALAN BAZINDA ISABET")
        yaz("=" * 70)
        yaz(f"{'alan':10s} {'dogru':>7s} {'olculen':>8s} {'oran':>7s} {'muaf':>6s}")
        yaz("-" * 44)
        for alan in ALANLAR:
            o = olculen[alan]
            oran = f"{dogru[alan] / o:.0%}" if o else "—"
            yaz(f"{alan:10s} {dogru[alan]:7d} {o:8d} {oran:>7s} {atlanan[alan]:6d}")
        if konu_katli_olculen:
            oran = f"{konu_katli_dogru / konu_katli_olculen:.0%}"
            yaz(f"{'konu~':10s} {konu_katli_dogru:7d} {konu_katli_olculen:8d} "
                f"{oran:>7s} {'':6s}   (katlanmis karsilastirma)")
        if muh_katli_olculen:
            oran = f"{muh_katli_dogru / muh_katli_olculen:.0%}"
            yaz(f"{'muhatap~':10s} {muh_katli_dogru:7d} {muh_katli_olculen:8d} "
                f"{oran:>7s} {'':6s}   (bulanik eslestirme, esik 0.80)")

        # --- 2. tablo -------------------------------------------------------
        yaz("\n" + "=" * 70)
        yaz("2  PDF BICIMINE GORE")
        yaz("=" * 70)
        bicimler = [b for b in ("metin_katmanli", "taranmis", "bilinmiyor")
                    if b_belge[b]]
        tablo_basligi = f"{'alan':10s}" + "".join(f"{b[:14]:>16s}" for b in bicimler)
        yaz(tablo_basligi)
        yaz("-" * len(tablo_basligi))
        for alan in ALANLAR:
            satir = f"{alan:10s}"
            for b in bicimler:
                o = b_olculen[b][alan]
                satir += f"{(f'{b_dogru[b][alan]}/{o}' if o else '—'):>16s}"
            yaz(satir)
        yaz("\nbelge sayisi: " + ", ".join(f"{b} {b_belge[b]}" for b in bicimler))

        # --- 3. tablo -------------------------------------------------------
        yaz("\n" + "=" * 70)
        yaz("3  KUSUR TESPITI  —  kasten bozulan alanda uydurdu mu")
        yaz("=" * 70)
        if not kusur_toplam:
            yaz("  bu ornekleme kusurlu belge dusmedi")
        else:
            yaz(f"{'kusur':20s} {'gecti':>7s} {'toplam':>8s} {'oran':>7s}")
            yaz("-" * 45)
            tg = tt = 0
            for k in sorted(kusur_toplam):
                g, t = kusur_gecti[k], kusur_toplam[k]
                tg += g
                tt += t
                yaz(f"{k:20s} {g:7d} {t:8d} {g / t:>7.0%}")
            yaz("-" * 45)
            yaz(f"{'TOPLAM':20s} {tg:7d} {tt:8d} {tg / tt:>7.0%}"
                f"      kapi: >= 95%   {'GECTI' if tg / tt >= 0.95 else 'KALDI'}")
            if kusur_hatalari:
                yaz("\n  gecemeyenler:")
                for x in kusur_hatalari:
                    yaz(f"    {x}")

        # --- aile -----------------------------------------------------------
        yaz("\nBELGE AILESI")
        for k, v in aile_sayaci.most_common():
            yaz(f"  {k:12s} {v:4d}")
        if aile_yanlis:
            yaz(f"  X {len(aile_yanlis)} yanlis tespit:")
            for x in aile_yanlis:
                yaz(f"      {x}")
        else:
            yaz("  OK tum belgelerde aile dogru tespit edildi")

        yaz("\nHATALAR  (beklenen -> bulunan)")
        for alan in ALANLAR:
            if not hatalar[alan]:
                continue
            yaz(f"\n  {alan}")
            for no, bek, bul in hatalar[alan]:
                yaz(f"    {no}: {bek}")
                yaz(f"         -> {bul}")

        yaz(f"\nKANITSIZ ALAN: {len(kanitsiz)}  {', '.join(kanitsiz[:10]) or '—'}")
        if okuma_hatasi:
            yaz(f"\nOKUMA HATASI: {len(okuma_hatasi)}")
            for x in okuma_hatasi[:8]:
                yaz(f"    {x}")

        yaz(f"\nsure: {gecen:.0f} sn")
        yaz("\nmuaf = alan belgede yok veya kasten bozulmus; 1. tabloda olculmez,")
        yaz("       3. tabloda 'uydurdu mu' diye olculur.")
        yaz(f"\nTam cikti: {cikti}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
