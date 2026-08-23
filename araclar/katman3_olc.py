#!/usr/bin/env python3
"""Denetci Katman 3'u bir ORNEKLEM uzerinde olcer. LLM CAGRISI YAPAR.

Depo kokunden ELLE calistirilir.

    python araclar/katman3_olc.py                20 belge (varsayilan)
    python araclar/katman3_olc.py 40             40 belge
    python araclar/katman3_olc.py 20 --hepsi     taranmis belgeleri de kat

MALIYET UYARISI
---------------
Belge basina 3-4 LLM cagrisi, ~8-16k token olculdu (belge_081 ve
belge_048). 20 belge kabaca 70 cagri / ~300k token demektir. Kosturmadan
once krediye bakin.

NEDEN ORNEKLEM, 300 BELGE DEGIL
-------------------------------
Kural motoru deterministik oldugu icin 300 belgede kosturmak bedava.
Katman 3 her belgede LLM cagirir. 300 belge ~1000 cagri eder ve teslime
2 gun kala bu risk alinmaz. Raporda ORNEKLEM oldugu acikca yazilacak.

OLCULEN UC SEY
--------------
1  YANLIS ALARM   kusursuz belgelerde kac bulgu uretildi, hangi kategoride
2  YAKALAMA       Katman 2'nin goremedigi uc kusurda isabet
                     ilgi_tarihi_tutarsiz  <- tarih_tutarsiz      12 belge
                     kapanis_yonu_yanlis   <- kapanis_yanlis      10 belge
3  ELEME          modelin uydurup elenen iddialari (alinti belgede yok)

Ucuncusu ajanligin kaniti: model bir iddia uretir, sistem kanitini belgede
arar, bulamazsa iddiayi ATAR.
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "src"))
sys.path.insert(0, str(KOK / "araclar"))

from ayristirici import ayristir                                      # noqa: E402
from denetci import Denetci                                           # noqa: E402
from katman3_dene import yapilandirma_bul                             # noqa: E402
from kural_motoru_dogrula import dosya_kur, etiket_klasoru, klasor_bul  # noqa: E402
from llm_istemci import istemci_olustur                               # noqa: E402
from okuyucu import oku                                               # noqa: E402

# Cevap anahtari OLMAYAN kategoriler. Kusursuz belgede atesledigi zaman
# "yanlis alarm" saymak yaniltici olur: OLCULDU 2026-08-23, belge_011'de
# model atif_belirsiz dedi ve HAKLIYDI — vatandas bir bagistan soz ediyor
# ama tarih, tutar ve makbuz numarasi yok, memur hangi bagisi arayacagini
# bilemez. Etikette kusur yazmadigi icin olcum onu yanlis alarm sayiyordu.
# Ayri raporlanir: gizlenmez, sisirilmez.
OLCULEMEYEN_KATEGORILER = frozenset({"atif_belirsiz"})

VARSAYILAN_N = 20
VARSAYILAN_YAPILANDIRMA = "yapilandirma.qwen.json"

# Veri setindeki kusur adi  ->  Katman 3'un beklenen kategorisi.
# Yalnizca Katman 2'nin GOREMEDIGI kusurlar burada. Digerlerini kural
# motoru zaten yakaliyor ve `kural_bulgulari` araci modele "tekrar etme"
# diyor.
KUSUR_KATEGORI = {
    # ek_beyani_yanlis CIKARILDI 2026-08-23: kategori kaldirildi cunku
    # "EKLER: 3 adet" beyani modele hic gitmiyor (kaynak.ham_metin'de,
    # isteme yalnizca govde konuyor). Model goremedigini bulamaz; uc
    # kusurlu belgede de dogru davranip eksik_yok dedi.
    "tarih_tutarsiz": "ilgi_tarihi_tutarsiz",
    "kapanis_yanlis": "kapanis_yonu_yanlis",
}


def ornek_sec(etiketler: list[Path], n: int, hepsi: bool) -> list[Path]:
    """Kusursuz ve olculebilir kusurlu belgeleri DENGELI secer.

    Rastgele secim kucuk orneklemde kusurlulari hic getirmeyebilir:
    tarih_tutarsiz 12, ek_beyani_yanlis 10, kapanis_yanlis 10 belge —
    300 icinde %10'dan az. Rastgele 20 belgede biri bile cikmayabilirdi.

    Bu yuzden orneklem yarisi kusursuz, yarisi olculebilir kusurlu olacak
    sekilde kuruluyor. Secim belge numarasina gore SIRALI, boylece ayni
    komut ayni orneklemi verir (tekrarlanabilirlik).
    """
    kusursuz: list[Path] = []
    kusurlu: dict[str, list[Path]] = {k: [] for k in KUSUR_KATEGORI}

    for y in sorted(etiketler):
        e = json.loads(y.read_text(encoding="utf-8"))
        if not hepsi and e.get("pdf_bicimi") != "metin_katmanli":
            continue
        kusur = e.get("kusur")
        if kusur is None:
            kusursuz.append(y)
        elif kusur in kusurlu:
            kusurlu[kusur].append(y)

    yarim = max(1, n // 2)
    secilen: list[Path] = []

    # Kusurlulardan her turden esit pay
    tur_sayisi = len(kusurlu)
    pay = max(1, yarim // tur_sayisi) if tur_sayisi else 0
    for kusur in KUSUR_KATEGORI:
        secilen.extend(kusurlu[kusur][:pay])

    # Kalani kusursuzdan
    secilen.extend(kusursuz[: n - len(secilen)])
    return secilen[:n]


def main(argv: list[str]) -> int:
    n = next((int(a) for a in argv if a.isdigit()), VARSAYILAN_N)
    hepsi = "--hepsi" in argv
    yap_adi = next((a for a in argv if a.endswith(".json")), VARSAYILAN_YAPILANDIRMA)

    yap = yapilandirma_bul(yap_adi)
    if yap is None:
        print(f"HATA: {yap_adi} bulunamadi.")
        return 1

    pdf_klasoru = klasor_bul()
    ek_klasoru = etiket_klasoru(pdf_klasoru)
    etiketler = list(ek_klasoru.glob("etiket_*.json"))
    secilen = ornek_sec(etiketler, n, hepsi)
    if not secilen:
        print("HATA: orneklem bos.")
        return 1

    istemci = istemci_olustur(yap)
    denetci = Denetci(istemci=istemci)

    cikti = KOK / "katman3_olc_sonuc.txt"
    with cikti.open("w", encoding="utf-8") as f:
        def yaz(s: str = "") -> None:
            print(s)
            f.write(s + "\n")

        yaz("KATMAN 3 OLCUMU - ORNEKLEM")
        yaz("=" * 72)
        yaz(f"  yapilandirma  : {yap}")
        yaz(f"  orneklem      : {len(secilen)} belge"
            f"{'' if hepsi else ' (yalnizca metin katmanli)'}")
        yaz("")

        temiz_toplam = 0
        temiz_bulgulu: list[str] = []
        temiz_kategori: Counter = Counter()
        temiz_olculemeyen: list[str] = []
        yakalama_toplam: Counter = Counter()
        yakalama_gecti: Counter = Counter()
        yakalama_ne_dedi: dict[str, list[str]] = {}
        elenen: list[str] = []
        okuma_hatasi: list[str] = []
        t0 = time.perf_counter()

        for i, ey in enumerate(secilen, 1):
            no = ey.stem.replace("etiket_", "")
            pdf = pdf_klasoru / f"belge_{no}.pdf"
            if not pdf.exists():
                continue
            e = json.loads(ey.read_text(encoding="utf-8"))

            r = oku(str(pdf))
            if r.hata or not r.ayrilmis:
                okuma_hatasi.append(f"{no}: {r.hata}")
                continue
            a = ayristir(r.ayrilmis.govde_satirlari,
                         dipnot_var=r.ayrilmis.dipnot_bulundu)
            d = dosya_kur(r, a, e)

            try:
                sonuc = denetci.calistir(d)
            except Exception as hata:  # noqa: BLE001
                okuma_hatasi.append(f"{no}: denetci -> {str(hata)[:80]}")
                continue

            cikarimlar = [x for x in sonuc.eksikler if x.katman == "cikarim"]
            elenen.extend(f"{no}: {x}" for x in sonuc.ajan_elenen)

            # Katman 3'un sectigi kategori izden okunur: "SONUÇ -> kategori"
            secilen_kategori = None
            for satir in sonuc.ajan_izi:
                if "SONUÇ ->" in satir:
                    secilen_kategori = satir.split("SONUÇ ->", 1)[1].strip().split(" ")[0]

            kusur = e.get("kusur")
            if kusur is None:
                temiz_toplam += 1
                if cikarimlar:
                    if secilen_kategori in OLCULEMEYEN_KATEGORILER:
                        temiz_olculemeyen.append(f"{no}:{secilen_kategori}")
                    else:
                        temiz_bulgulu.append(no)
                        temiz_kategori[secilen_kategori or "?"] += 1
            elif kusur in KUSUR_KATEGORI:
                yakalama_toplam[kusur] += 1
                beklenen = KUSUR_KATEGORI[kusur]
                if secilen_kategori == beklenen:
                    yakalama_gecti[kusur] += 1
                yakalama_ne_dedi.setdefault(kusur, []).append(
                    f"{no}:{secilen_kategori}"
                )

            print(f"  ... {i}/{len(secilen)}  belge_{no} "
                  f"kusur={kusur} -> {secilen_kategori}", file=sys.stderr)

        sure = time.perf_counter() - t0

        yaz("OLCUM 1 - YANLIS ALARM (kusursuz belgeler)")
        yaz("-" * 72)
        yaz(f"  kusursuz belge        {temiz_toplam}")
        yaz(f"  bulgu ureten belge    {len(temiz_bulgulu)}"
            + (f"  ({len(temiz_bulgulu)/temiz_toplam:.0%})" if temiz_toplam else ""))
        if temiz_kategori:
            yaz("  kategori dagilimi:")
            for k, adet in temiz_kategori.most_common():
                yaz(f"    {k:24} {adet}")
            yaz(f"  bulgu ureten belgeler: {', '.join(temiz_bulgulu)}")
        if temiz_olculemeyen:
            yaz("")
            yaz(f"  OLCULEMEYEN kategoride bulgu   {len(temiz_olculemeyen)}")
            yaz(f"    {', '.join(temiz_olculemeyen)}")
            yaz("    Bu kategorilerin cevap anahtari YOK; kusursuz belgede")
            yaz("    atesledigi zaman yanlis alarm sayilmiyor, ayri veriliyor.")
        yaz("")

        yaz("OLCUM 2 - YAKALAMA (Katman 2'nin goremedigi kusurlar)")
        yaz("-" * 72)
        if not yakalama_toplam:
            yaz("  orneklemde olculebilir kusurlu belge yok")
        for kusur, beklenen in KUSUR_KATEGORI.items():
            top = yakalama_toplam.get(kusur, 0)
            if not top:
                continue
            gec = yakalama_gecti.get(kusur, 0)
            yaz(f"  {kusur:20} -> {beklenen:22} {gec}/{top} = {gec/top:.0%}")
            yaz(f"       model ne dedi: {', '.join(yakalama_ne_dedi[kusur])}")
        yaz("")

        yaz("OLCUM 3 - ELEME (ajanin kendini denetlemesi)")
        yaz("-" * 72)
        yaz(f"  elenen iddia sayisi   {len(elenen)}")
        for x in elenen[:12]:
            yaz(f"    {x[:110]}")
        yaz("")

        yaz("MALIYET")
        yaz("-" * 72)
        yaz(f"  cagri sayisi          {getattr(istemci, 'cagri_sayisi', '?')}")
        yaz(f"  girdi token           {getattr(istemci, 'toplam_girdi', '?')}")
        yaz(f"  cikti token           {getattr(istemci, 'toplam_genel', '?')}")
        yaz(f"  sure                  {sure:.0f} sn")
        if okuma_hatasi:
            yaz(f"  HATA                  {len(okuma_hatasi)}")
            for h in okuma_hatasi[:8]:
                yaz(f"    {h}")
        yaz("")
        yaz(f"sonuc dosyasi: {cikti}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
