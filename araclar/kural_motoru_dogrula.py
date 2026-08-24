#!/usr/bin/env python3
"""Kural motorunu veri setinde olcer. Depo kokunden ELLE calistirilir.

    python araclar/kural_motoru_dogrula.py            tamami (~20 dk, 50'si OCR)
    python araclar/kural_motoru_dogrula.py 50         ilk 50 belge
    python araclar/kural_motoru_dogrula.py --metin    yalnizca metin katmanli (hizli)

CIKTI: kural_motoru_dogrula_sonuc.txt

IKI OLCUM
---------
1  YANLIS ALARM   kusursuz 180 belgede motor kac bulgu uretiyor
                  BEKLENEN: SIFIR. Bulgu ureten kural yanlis alarm veriyor
                  demektir ve duzeltilene kadar uygulanir=false yapilir.

2  YAKALAMA       kusurlu belgelerde ilgili kural tetikleniyor mu

Yanlis alarm daha tehlikeli olan taraftir: bulunamayan ihlal gorunmez,
uydurulan ihlal memurun ekraninda gorunur ve sisteme guveni bitirir.

ASAMA A'DA OLCULEBILEN YAKALAMA — dort kusur
--------------------------------------------
    sayi_eksik   12 belge  ->  S-01
    tarih_eksik  12 belge  ->  T-01
    konu_eksik   10 belge  ->  K-01
    imza_eksik   10 belge  ->  IM-01
    sdp_uyumsuz  12 belge  ->  S-07   (Asama B, ozel fonksiyon)
    muhatap_belirsiz 10 belge -> M-01  (jenerik bos_olmamali)

OLCULEMEYENLER ve SEBEBI
------------------------
    sdp_uyumsuz     S-07 Asama B'de yazilacak (ozel fonksiyon, katalog
                    eslesmesi gerekiyor) — su an uygulanir=false
    kapanis_yanlis  ME-02 yalnizca kapanisin VAR OLDUGUNU denetler.
                    Kusur kapanisi silmiyor, YONUNU ters ceviriyor
                    (kota.json kapanis_kurali). Yon denetimi ME-03,
                    Asama B'de.
    digerleri       ozel fonksiyon gerektiriyor, Asama A kapsami disi

DOSYA.METIN NASIL KURULUYOR
---------------------------
Motor ME kurallarini `metin` alaninda kosturuyor: gelen belgenin GOVDESI.
Okuyucu sayfanin tamamini veriyor (dipnotu ayrilmis), ayristirici da
govdenin nerede basladigini (muhatap_satiri) ve bittigini (kapanis_satiri)
biliyor. Govde bu iki sayinin arasidir.

Bu ayrim ONEMLI. Govde yerine sayfanin tamami verilirse ME-02'nin
'$' cipasi imza blogunun ardindan gelen metne takilir ve kural HER
BELGEDE yanlis alarm verir. Olculdu: belge_001'de sayfa "Ek: Genelge
sureti (2 Sayfa)" ile bitiyor, "rica ederim." ile degil.
"""

from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "src"))

from veri_yapisi import Dosya, SdpKodu, Siniflandirma  # noqa: E402
import taksonomi  # noqa: E402
from kural_motoru import KuralMotoru  # noqa: E402

# ayristirici_dogrula.py ile AYNI arama yerleri — iki betik ayrisirsa
# biri baska bir veri setini olcer.
ARAMA_YERLERI = (
    ("deneyler", "adim4", "belgeler_pdf"),
    ("veri", "belgeler"),
    ("ornek", "okuma_ornegi"),
)

# Tamami parantez icinde olan satir: muhatabin birimi. Govde degildir.
_SADECE_PARANTEZ = re.compile(r"^\([^)]{2,}\)$")

# Kusur -> onu yakalamasi BEKLENEN kural. Kaynak: DEVIR_EK2 §2 tablosu,
# Asama A kapsamina indirgenmis hali.
KUSUR_KURAL = {
    "sayi_eksik": "S-01",
    "tarih_eksik": "T-01",
    "konu_eksik": "K-01",
    "imza_eksik": "IM-01",
    "sdp_uyumsuz": "S-07",         # Asama B, 2026-08-23
    "muhatap_belirsiz": "M-01",    # 2026-08-23: ozel fonksiyon degil, jenerik
    "ilgi_kopuk": "I-09",          # 2026-08-23
}

# Asama A'da olculemeyen kusurlar ve sebebi. Raporda gorunur.
OLCULEMEYEN = {
    "kapanis_yanlis": "ME-03 Asama B (ME-02 yalnizca varlik denetler)",
    "ek_beyani_yanlis": "Ek kategorisi, Asama B",
    "tarih_tutarsiz": "Tarih/Ilgi capraz, Asama B",
    "tarama_bozuk": "kural konusu degil, OCR kalitesi",
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


# -----------------------------------------------------------------------------
# Dosya kurma
# -----------------------------------------------------------------------------


def govde_kur(satirlar, a) -> str | None:
    """Gövde metnini muhatap ile kapanış satırı arasindan kurar.

    Iki sinir da ayristiricidan gelir; burada YENIDEN HESAPLANMAZ. Sinirlar
    bulunamazsa None doner ve motor degismezi geregi ME kurallari atlanir —
    yanlis bir govde uydurup kurala vermekten iyidir.

    MUHATAP PARANTEZI GOVDEYE GIRMEZ
    --------------------------------
    Muhatap satirinin hemen altinda muhatabin BIRIMI parantez icinde
    yazilir:

        YENIMAHALLE BELEDIYE BASKANLIGINA
        (Kultur, Sanat ve Sosyal Isler Mudurlugu)     <- govde DEGIL

    `muhatap_satiri + 1`'den baslamak bu satiri govdeye katiyordu.
    OLCULDU 2026-08-23: 8 belgenin 5'inde govde parantezle basliyordu ve
    Ozetleyici bunu govdenin parcasi sanip birimi GONDEREN yapiyordu
    (belge_016: "Muhendislik Fakultesi Dekanligi, ... Gazi Universitesi
    Dekanligindan onay talep etmektedir" — alici uydurulmus).

    Tamami parantez icinde olan bir satir hicbir zaman govde degildir;
    atlaniyor. Yalnizca GOVDENIN BASINDAKI satir denetleniyor — metnin
    icindeki parantezli aciklamalara dokunulmuyor.

    SATIRLAR BOSLUKLA BIRLESTIRILIR, '\\n' ILE DEGIL
    ------------------------------------------------
    PDF'teki satir sonu cumlenin parcasi degil, sayfa yerlesiminin
    artefaktidir. '\\n' ile birlestirildiginde OLCULDU (2026-08-23,
    153 kusursuz belge): ME-02 16 belgede yanlis alarm verdi, cunku
    satir sarmasi kapanis ifadesini ikiye boluyordu:

        'hususunda gereğini arz\\nederim.'      <- 'arz ederim' YOK
        'bilgileri ve gereğini arz/rica\\nederim.'

    Desen literal bosluk ariyor, satir sonu bulamıyor. Duzeltme desende
    degil BURADA yapildi: desen dogru, govde yanlis kurulmustu. Cok
    kelimeli her ifade ayni tuzaga duserdi, yalnizca ME-02 degil.

    SINIR — durust kayit
    --------------------
    Bu birlestirme paragraf sinirlarini da yok eder. Paragraf tespiti
    ilk satirin girintisine (x koordinati) bakmayi gerektirir; dipnot.Satir
    yalnizca y tasiyor, x tasimiyor. Paragraf yapisina bakan bir kural
    yazilacaksa once Satir'a x eklenmelidir. Asama A kurallarinin hicbiri
    paragraf sinirina bakmiyor.
    """
    if a.kapanis_satiri is None:
        return None
    bas = (a.muhatap_satiri + 1) if a.muhatap_satiri is not None else 0
    son = a.kapanis_satiri + 1
    if bas >= son:
        return None

    # Muhatap parantezi: govdenin ilk satiri tamamen parantez icindeyse
    # o satir muhatabin birimidir, atlanir.
    if bas < son and _SADECE_PARANTEZ.match(satirlar[bas].metin.strip()):
        bas += 1
    if bas >= son:
        return None

    return " ".join(s.metin.strip() for s in satirlar[bas:son]).strip() or None


def dosya_kur(r, a, etiket: dict) -> Dosya:
    """Okuyucu + Ayristirici ciktisindan motorun bekledigi Dosya'yi kurar.

    NOT: siniflandirma.belge_turu CEVAP ANAHTARINDAN aliniyor, Anlama'dan
    degil. Sebep: bu betik KURAL MOTORUNU olcuyor, Anlama'yi degil. Anlama
    bir turu yanlis bilirse kural motorunun yanlis alarmi ile Anlama'nin
    hatasi birbirine karisir ve hangisinin kusuru oldugu ayirt edilemez.
    Boru hattinda tur Anlama'dan gelecek (Parca 5).
    """
    d = Dosya()
    d.ustveri = a.ustveri
    d.kanit = dict(a.kanit)
    d.kaynak.ham_metin = "\n".join(s.metin for s in r.satirlar)
    d.metin = govde_kur(r.ayrilmis.govde_satirlari, a)

    tur = taksonomi.etiketten(etiket.get("belge_turu"))
    sdp = (etiket.get("sdp") or {}).get("kod")
    d.siniflandirma = Siniflandirma(
        belge_turu=tur or "bilinmiyor",
        sdp=SdpKodu(kod=sdp) if sdp else SdpKodu(),
    )
    return d


# -----------------------------------------------------------------------------
# Ana akis
# -----------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    from ayristirici import ayristir
    from okuyucu import oku

    sinir = next((int(x) for x in argv if x.isdigit()), None)
    yalniz_metin = "--metin" in argv

    klasor = klasor_bul()
    ek = etiket_klasoru(klasor)
    pdfler = sorted(klasor.glob("belge_*.pdf"))
    if sinir:
        pdfler = pdfler[:sinir]

    motor = KuralMotoru()

    cikti = KOK / "kural_motoru_dogrula_sonuc.txt"
    with cikti.open("w", encoding="utf-8") as f:
        def yaz(s: str = "") -> None:
            print(s)
            f.write(s + "\n")

        yaz("KURAL MOTORU DOGRULAMA")
        yaz("=" * 72)
        yaz(motor.ozet())
        yaz(f"belge klasoru : {klasor}")
        yaz(f"etiket klasoru: {ek}")
        yaz("")

        temiz_belge = 0
        temiz_bicim: Counter = Counter()           # metin_katmanli / taranmis
        temiz_bulgulu: list[str] = []
        bulgulu_bicim: Counter = Counter()
        bulgu_bicim: Counter = Counter()
        yanlis_alarm: Counter = Counter()          # kural -> kac temiz belgede
        yanlis_alarm_ornek: dict[str, list[str]] = defaultdict(list)

        yakalama_toplam: Counter = Counter()
        yakalama_gecti: Counter = Counter()
        yakalama_kacan: dict[str, list[str]] = defaultdict(list)

        atlama_sebep: Counter = Counter()
        metin_kurulamadi: list[str] = []
        okuma_hatasi: list[str] = []
        atlanan_bicim = 0
        denetlenen_toplam = 0
        t0 = time.perf_counter()

        for i, pdf in enumerate(pdfler, 1):
            no = pdf.stem.replace("belge_", "")
            ey = ek / f"etiket_{no}.json"
            if not ey.exists():
                continue
            e = json.loads(ey.read_text(encoding="utf-8"))

            if yalniz_metin and e.get("pdf_bicimi") != "metin_katmanli":
                atlanan_bicim += 1
                continue

            r = oku(str(pdf))
            if r.hata or not r.ayrilmis:
                okuma_hatasi.append(f"{no}: {r.hata}")
                continue

            a = ayristir(r.ayrilmis.govde_satirlari,
                         dipnot_var=r.ayrilmis.dipnot_bulundu)
            d = dosya_kur(r, a, e)
            if d.metin is None:
                metin_kurulamadi.append(no)

            s = motor.calistir(d, hedef="gelen")
            denetlenen_toplam += s.rapor.denetlenen_kural_sayisi
            for at in s.atlamalar:
                atlama_sebep[at.sebep] += 1

            bulunan = {b.kural_id for b in s.rapor.bulgular}
            kusur = e.get("kusur")

            if kusur is None:
                # --- OLCUM 1: yanlis alarm ---
                temiz_belge += 1
                bicim = e.get("pdf_bicimi") or "bilinmiyor"
                temiz_bicim[bicim] += 1
                if bulunan:
                    temiz_bulgulu.append(no)
                    bulgulu_bicim[bicim] += 1
                    bulgu_bicim[bicim] += len(s.rapor.bulgular)
                    for b in s.rapor.bulgular:
                        yanlis_alarm[b.kural_id] += 1
                        if len(yanlis_alarm_ornek[b.kural_id]) < 6:
                            deger = d.deger_al(b.alan)
                            metin = str(deger)
                            # Cogu regex kurali dizenin SONUNA capali
                            # ('...\s*$'). Bas tarafi gostermek teshis icin
                            # ise yaramaz; iki ucu birden yazdiriliyor.
                            bas = metin[:50].replace("\n", "\\n")
                            son = metin[-70:].replace("\n", "\\n")
                            yanlis_alarm_ornek[b.kural_id].append(
                                f"{no}: {b.alan}\n"
                                f"                bas: {bas!r}\n"
                                f"                SON: {son!r}"
                            )
            else:
                # --- OLCUM 2: yakalama ---
                beklenen = KUSUR_KURAL.get(kusur)
                if beklenen:
                    yakalama_toplam[kusur] += 1
                    if beklenen in bulunan:
                        yakalama_gecti[kusur] += 1
                    elif len(yakalama_kacan[kusur]) < 8:
                        yakalama_kacan[kusur].append(no)

            if i % 25 == 0:
                print(f"  ... {i}/{len(pdfler)}", file=sys.stderr)

        sure = time.perf_counter() - t0

        # ------------------------------------------------------------------
        yaz("OLCUM 1 - YANLIS ALARM (kusursuz belgeler)")
        yaz("-" * 72)
        def _kir(c: Counter) -> str:
            return " · ".join(f"{k} {v}" for k, v in sorted(c.items())) or "-"

        yaz(f"  kusursuz belge sayisi     {temiz_belge}   ({_kir(temiz_bicim)})")
        yaz(f"  bulgu ureten belge        {len(temiz_bulgulu)}   ({_kir(bulgulu_bicim)})")
        yaz(f"  toplam yanlis bulgu       {sum(yanlis_alarm.values())}   ({_kir(bulgu_bicim)})")
        yaz("")

        # KAPI yalnizca METIN KATMANLI nufusta. Taranmis belgede alan
        # yoklugu kuralin degil OKUMANIN kusuru: EasyOCR anahtar terimlerin
        # %68'ini koruyor (devir notu §7.3) ve okuyucu.py paragraf ici
        # kelime karisikligini duzeltemedigini kendi docstring'inde yaziyor.
        # Iki nufusu tek sayida toplamak, kural motorunun kalitesini OCR
        # kalitesiyle karistirir ve olcumu okunamaz kilar.
        mk_bulgu = bulgu_bicim.get("metin_katmanli", 0)
        if mk_bulgu == 0:
            yaz("  SONUC (metin katmanli): SIFIR YANLIS ALARM - GECTI")
        else:
            yaz(f"  SONUC (metin katmanli): KALDI - {mk_bulgu} bulgu.")
            yaz("         Bu kurallar duzeltilene kadar uygulanir=false yapilmalidir.")
        tr_bulgu = bulgu_bicim.get("taranmis", 0)
        if tr_bulgu:
            yaz(f"  SONUC (taranmis)      : {tr_bulgu} bulgu - OCR kaybi, kural kusuru DEGIL.")
            yaz("         Raporda ayri verilir; kural motoru olcumune katilmaz.")
        if yanlis_alarm:
            yaz("")
            for kid, adet in yanlis_alarm.most_common():
                oran = adet / temiz_belge if temiz_belge else 0
                yaz(f"    {kid:7} {adet:4} belge  ({oran:.1%})")
                for orn in yanlis_alarm_ornek[kid]:
                    yaz(f"            {orn}")
        yaz("")

        # ------------------------------------------------------------------
        yaz("OLCUM 2 - YAKALAMA (kusurlu belgeler)")
        yaz("-" * 72)
        if not yakalama_toplam:
            yaz("  olculebilir kusurlu belge bulunamadi")
        for kusur, kural in KUSUR_KURAL.items():
            top = yakalama_toplam.get(kusur, 0)
            if not top:
                continue
            gec = yakalama_gecti.get(kusur, 0)
            yaz(f"  {kusur:16} {kural:7} {gec}/{top} = {gec/top:.0%}")
            if yakalama_kacan[kusur]:
                yaz(f"       kacan belgeler: {', '.join(yakalama_kacan[kusur])}")
        yaz("")
        yaz("  ASAMA A'DA OLCULEMEYEN KUSURLAR")
        for kusur, sebep in OLCULEMEYEN.items():
            yaz(f"    {kusur:18} {sebep}")
        yaz("")

        # ------------------------------------------------------------------
        yaz("MOTOR ISLEYISI")
        yaz("-" * 72)
        yaz(f"  denetlenen kural (toplam) {denetlenen_toplam}")
        for sebep, adet in atlama_sebep.most_common():
            yaz(f"  atlanan / {sebep:14} {adet}")
        if metin_kurulamadi:
            yaz(f"  govde kurulamadi          {len(metin_kurulamadi)} belge "
                f"({', '.join(metin_kurulamadi[:12])})")
            yaz("     -> bu belgelerde ME kurallari atlandi (kapanis satiri yok)")
        if okuma_hatasi:
            yaz(f"  OKUMA HATASI              {len(okuma_hatasi)}")
            for h in okuma_hatasi[:10]:
                yaz(f"     {h}")
        if atlanan_bicim:
            yaz(f"  --metin ile atlanan       {atlanan_bicim} taranmis belge")
        yaz(f"  sure                      {sure:.1f} sn")
        yaz("")
        yaz(f"sonuc dosyasi: {cikti}")

        _kapi = bulgu_bicim.get("metin_katmanli", 0)

    return 0 if _kapi == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
