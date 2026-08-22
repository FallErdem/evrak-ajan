"""Anlama'yı gerçek LLM çağrılarıyla ölçer.

NEREYE:  depo kökü
NASIL:   python anlama_dogrula.py yapilandirma.qwen.json 30
         python anlama_dogrula.py yapilandirma.qwen.json 30 tr
         python anlama_dogrula.py yapilandirma.qwen.json 30 en
ÇIKTI:   anlama_dogrula_sonuc_<yapilandirma>.txt

Yapılandırma KOMUT SATIRINDAN alınır; `yapilandirma.json` takas edilmez.
Böylece iki sağlayıcı arka arkaya koşturulup karşılaştırılabilir ve
çıktıda hangisiyle ölçüldüğü yazılı kalır.

NE ÖLÇÜLÜYOR — ADIM 4 kapısı
----------------------------
    belge türü macro-F1   >= 0.85
    SDP okuma             >= 0.98      (sayıdan okunan, LLM'siz)
    SDP tahmin            >= 0.60      (sayısı olmayan belgelerde)

Ayrıca: gecikme, token, daraltmanın kazancı, TR/EN istem karşılaştırması.

MACRO-F1 NEDEN
--------------
Sınıflar çok dengesiz: dilekce 66 belge, olur_yazisi 6. Düz doğruluk
büyük sınıfı ezberleyen bir modeli ödüllendirir. Macro-F1 her sınıfın
F1'ini ayrı hesaplayıp ortalar; küçük sınıfta başarısızlık saklanamaz.

ÖRNEKLEM UYARISI
----------------
Ayrı tutulmuş bir değerlendirme seti YOK. Bu ölçüm geliştirme setinde
yapılıyor; istemi ölçüme bakarak defalarca elden geçirmek skoru şişirir
ve şişmeyi göremeyiz. İKİ-ÜÇ TUR, SONRA DUR.

Örneklem her türden en az bir belge içerecek şekilde seçiliyor
(katmanlı); rastgele 30 belge küçük sınıfları hiç görmeyebilirdi.
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

VARSAYILAN_ADET = 30

AILE_TIPI = {
    "gercek_kisi": "dilekce",
    "ogrenci": "dilekce",
    "ozel_tuzel_kisi": "sirket",
    "kurum": "kurum",
}


# -----------------------------------------------------------------------------
# Dosya bulma
# -----------------------------------------------------------------------------

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


def ornek_sec(klasor: Path, ek: Path, adet: int) -> list[tuple[Path, dict]]:
    """Katmanlı örneklem: her türden en az bir belge.

    Rastgele 30 belge olur_yazisi'ni (6 belge) hiç görmeyebilir ve
    macro-F1 o sınıfta ölçülemez.
    """
    ture_gore: dict[str, list[tuple[Path, dict]]] = defaultdict(list)
    for pdf in sorted(klasor.glob("belge_*.pdf")):
        ey = ek / f"etiket_{pdf.stem.replace('belge_', '')}.json"
        if not ey.exists():
            continue
        e = json.loads(ey.read_text(encoding="utf-8"))
        ture_gore[e["belge_turu"]].append((pdf, e))

    secim: list[tuple[Path, dict]] = []
    # Önce her türden bir tane
    for tur in sorted(ture_gore):
        secim.append(ture_gore[tur][0])
    # Kalan kotayı tür büyüklüğüyle orantılı doldur
    i = 1
    while len(secim) < adet:
        eklendi = False
        for tur in sorted(ture_gore, key=lambda t: -len(ture_gore[t])):
            if len(secim) >= adet:
                break
            if i < len(ture_gore[tur]):
                secim.append(ture_gore[tur][i])
                eklendi = True
        if not eklendi:
            break
        i += 1
    return secim[:adet]


# -----------------------------------------------------------------------------
# Ölçütler
# -----------------------------------------------------------------------------

def macro_f1(ciftler: list[tuple[str | None, str]]) -> tuple[float, dict]:
    """(bulunan, beklenen) çiftlerinden macro-F1.

    Sınıf kümesi BEKLENENlerden alınır: modelin ürettiği ama veri setinde
    hiç olmayan bir sınıf ortalamayı seyreltmemeli.
    """
    siniflar = sorted({b for _, b in ciftler})
    detay: dict[str, dict] = {}
    toplam = 0.0
    for s in siniflar:
        tp = sum(1 for bul, bek in ciftler if bul == s and bek == s)
        fp = sum(1 for bul, bek in ciftler if bul == s and bek != s)
        fn = sum(1 for bul, bek in ciftler if bul != s and bek == s)
        kesinlik = tp / (tp + fp) if tp + fp else 0.0
        duyarlilik = tp / (tp + fn) if tp + fn else 0.0
        f1 = (2 * kesinlik * duyarlilik / (kesinlik + duyarlilik)
              if kesinlik + duyarlilik else 0.0)
        detay[s] = {"f1": f1, "kesinlik": kesinlik, "duyarlilik": duyarlilik,
                    "adet": tp + fn, "dogru": tp}
        toplam += f1
    return (toplam / len(siniflar) if siniflar else 0.0), detay


def yuzdelik(degerler: list[float], p: float) -> float:
    if not degerler:
        return 0.0
    s = sorted(degerler)
    i = min(int(len(s) * p), len(s) - 1)
    return s[i]


# -----------------------------------------------------------------------------
# Koşu
# -----------------------------------------------------------------------------

def dili_kostur(ornekler, istemci, dil: str, yaz) -> dict:
    from anlama import anla
    from ayristirici import ayristir
    from okuyucu import oku
    from taksonomi import etiketten

    yaz(f"\n{'=' * 74}")
    yaz(f"DIL: {dil.upper()}   {len(ornekler)} belge")
    yaz("=" * 74)

    ciftler: list[tuple[str | None, str]] = []
    # SDP UC yoldan cozuluyor, ucu de AYRI olculmeli:
    #   regex   sayidan okundu           -> genellenir
    #   sozluk  katalogda BIREBIR gecti   -> genellenir ama bizde sik
    #   llm     modele soruldu            -> ASIL GENELLEME OLCUSU BU
    sdp_yol = {"regex": [0, 0], "sozluk": [0, 0], "llm": [0, 0]}
    sdp_muaf = 0
    sdp_hatalari: list[tuple[str, str, str, str, list[str]]] = []
    sureler: list[float] = []
    tokenlar: list[int] = []
    aday_sayilari: list[int] = []
    llmsiz = 0
    uyarilar: list[str] = []
    hatalar: list[tuple[str, str, str]] = []
    varlik_sayisi: list[int] = []
    talep_bos = 0

    for i, (pdf, e) in enumerate(ornekler, 1):
        no = pdf.stem.replace("belge_", "")
        r = oku(str(pdf))
        if r.hata or not r.ayrilmis:
            uyarilar.append(f"{no}: okuma hatasi {r.hata}")
            continue
        a = ayristir(r.ayrilmis.govde_satirlari)

        try:
            s = anla(r.govde, a, istemci, dil=dil)
        except Exception as ex:  # noqa: BLE001
            uyarilar.append(f"{no}: {type(ex).__name__}: {ex}")
            continue

        uyarilar += [f"{no}: {x}" for x in s.uyarilar]
        aday_sayilari.append(len(s.adaylar))
        if not s.llm_kullanildi:
            llmsiz += 1
        else:
            sureler.append(s.sure_ms)
            tokenlar.append(s.token)

        # --- belge turu
        beklenen = etiketten(e["belge_turu"])
        bulunan = s.siniflandirma.belge_turu.value if s.siniflandirma.belge_turu else None
        ciftler.append((bulunan, beklenen))
        if bulunan != beklenen and len(hatalar) < 12:
            hatalar.append((no, beklenen or "?", bulunan or "—"))

        # --- SDP: iki yol AYRI olculur, ve bir muafiyet var
        #
        # sdp_uyumsuz kusurlu 12 belgede etiket DUZELTILMIS kodu, belge
        # BOZUK kodu tasir. Anlama belgeye sadik olmali, yani bozuk kodu
        # okumali. Etiketle karsilastirmak dogru davranisa ceza yazar.
        # (Ayni muafiyet ayristirici_dogrula.py'de de var.)
        beklenen_sdp = (e.get("sdp") or {}).get("kod")
        # İKİ MUAFİYET, ikisi de enjekte edilmiş kusurdan:
        #
        #   sdp_uyumsuz      etiket DÜZELTİLMİŞ kodu, belge BOZUK kodu tutar
        #   muhatap_belirsiz muhatap KASTEN okunamaz; SDP adayları muhatabın
        #                    biriminden türediği için aday listesi boş kalır
        #
        # İkincisi ölçümde 4 belgeyi haksız yere düşürüyordu. Boş aday
        # listesi arıza değil, kusurun DOĞRU tespitidir — Denetçi'nin
        # (Parça 4) yakalayacağı eksiklik tam olarak budur.
        if e.get("kusur") in ("sdp_uyumsuz", "muhatap_belirsiz"):
            sdp_muaf += 1
        elif beklenen_sdp:
            kanit = s.kanit.get("siniflandirma.sdp")
            yol = kanit.yontem.value if kanit else "llm"
            hedef = sdp_yol.setdefault(yol, [0, 0])
            hedef[1] += 1
            bulunan_sdp = s.siniflandirma.sdp.kod if s.siniflandirma.sdp else None
            hedef[0] += bulunan_sdp == beklenen_sdp
            if bulunan_sdp != beklenen_sdp and len(sdp_hatalari) < 12:
                # Hangi adaylar sunulmustu — hata modelde mi daraltmada mi?
                from anlama import sdp_adaylari
                adaylar = sdp_adaylari(a.ustveri.muhatap.ham,
                                       a.ustveri.muhatap.birim)
                sdp_hatalari.append((no, yol, beklenen_sdp,
                                     str(bulunan_sdp), [x[0] for x in adaylar]))

        varlik_sayisi.append(len(s.icerik.varliklar))
        if not s.icerik.talep:
            talep_bos += 1

        if i % 10 == 0:
            print(f"    ... {i}/{len(ornekler)}", flush=True)

    f1, detay = macro_f1(ciftler)
    dogru = sum(1 for b, k in ciftler if b == k)

    yaz(f"\nBELGE TURU   macro-F1 {f1:.3f}   duz dogruluk "
        f"{dogru}/{len(ciftler)} = {dogru / len(ciftler):.0%}" if ciftler else "")
    yaz(f"{'sinif':26s} {'F1':>6s} {'kesinlik':>9s} {'duyarlilik':>11s} {'adet':>5s}")
    yaz("-" * 62)
    for s_ad in sorted(detay, key=lambda x: -detay[x]["adet"]):
        d = detay[s_ad]
        yaz(f"{s_ad:26s} {d['f1']:6.2f} {d['kesinlik']:9.2f} "
            f"{d['duyarlilik']:11.2f} {d['adet']:5d}")

    if hatalar:
        yaz("\nYANLIS SINIFLANDIRMALAR (beklenen -> bulunan)")
        for no, bek, bul in hatalar:
            yaz(f"   {no}: {bek} -> {bul}")

    yaz("\nSDP — uc yol ayri")
    for yol, aciklama in (("regex", "sayidan okundu"),
                          ("sozluk", "katalogda birebir"),
                          ("llm", "modele soruldu")):
        d, tp = sdp_yol.get(yol, [0, 0])
        yaz(f"   {yol:8s} {aciklama:20s} {d:3d}/{tp:3d}  "
            f"{(d / tp if tp else 0):.0%}")
    tumu_d = sum(v[0] for v in sdp_yol.values())
    tumu_t = sum(v[1] for v in sdp_yol.values())
    yaz(f"   {'TOPLAM':8s} {'':20s} {tumu_d:3d}/{tumu_t:3d}  "
        f"{(tumu_d / tumu_t if tumu_t else 0):.0%}")
    if sdp_hatalari:
        yaz("\n   HATALAR (beklenen -> bulunan | sunulan adaylar)")
        for no, yol, bek, bul, adaylar in sdp_hatalari:
            icinde = "dogru cevap adaylarda" if bek in adaylar else "DOGRU CEVAP ADAYLARDA YOK"
            yaz(f"      {no} [{yol}] {bek} -> {bul}")
            yaz(f"          adaylar: {adaylar}  ({icinde})")
    if sdp_muaf:
        yaz(f"   {'muaf':18s} {sdp_muaf:3d}      "
            f"sdp_uyumsuz veya muhatap_belirsiz kusurlu")

    yaz("\nDARALTMA")
    if aday_sayilari:
        yaz(f"   ortalama aday : {sum(aday_sayilari) / len(aday_sayilari):.2f} / 11")
        yaz(f"   LLM cagrilmadan cozulen : {llmsiz}/{len(ornekler)}")

    yaz("\nGECIKME VE MALIYET")
    if sureler:
        yaz(f"   cagri sayisi  : {len(sureler)}")
        yaz(f"   p50 / p95     : {yuzdelik(sureler, 0.5):.0f} / "
            f"{yuzdelik(sureler, 0.95):.0f} ms")
        yaz(f"   ortalama token: {sum(tokenlar) / len(tokenlar):.0f}")
        yaz(f"   300 belge tahmini: {sum(tokenlar) / len(tokenlar) * 300 / 1000:.0f}k token")

    yaz("\nDIGER")
    if varlik_sayisi:
        yaz(f"   belge basina varlik: {sum(varlik_sayisi) / len(varlik_sayisi):.1f}")
    yaz(f"   talep bos          : {talep_bos}/{len(ornekler)}")

    if uyarilar:
        yaz(f"\nUYARILAR ({len(uyarilar)})")
        for u in uyarilar[:15]:
            yaz(f"   {u}")

    return {"f1": f1, "dogruluk": dogru / len(ciftler) if ciftler else 0.0,
            "sdp_okuma": sdp_yol["regex"], "sdp_tahmin": sdp_yol["llm"],
            "sdp_sozluk": sdp_yol["sozluk"],
            "p50": yuzdelik(sureler, 0.5), "token": sum(tokenlar)}


def main(argv: list[str]) -> int:
    from llm_istemci import istemci_olustur

    yapilandirma = next((a for a in argv if a.endswith(".json")), None)
    if not yapilandirma:
        sys.exit("Yapilandirma dosyasi verin:\n"
                 "    python anlama_dogrula.py yapilandirma.qwen.json 30")
    if not (KOK / yapilandirma).exists():
        sys.exit(f"Bulunamadi: {yapilandirma}")

    adet = next((int(a) for a in argv if a.isdigit()), VARSAYILAN_ADET)
    diller = [a for a in argv if a in ("tr", "en")] or ["tr", "en"]

    klasor = klasor_bul()
    ek = etiket_klasoru(klasor)
    ornekler = ornek_sec(klasor, ek, adet)

    etiket = Path(yapilandirma).stem
    cikti = KOK / f"anlama_dogrula_sonuc_{etiket}.txt"

    with cikti.open("w", encoding="utf-8") as f:
        def yaz(s: str = "") -> None:
            print(s)
            f.write(s + "\n")

        istemci = istemci_olustur(KOK / yapilandirma)
        yaz(f"yapilandirma : {yapilandirma}")
        yaz(f"model        : {istemci.y.model}")
        yaz(f"belge        : {len(ornekler)}  (katmanli ornekleme)")
        yaz(f"tur dagilimi : "
            f"{dict(Counter(e['belge_turu'] for _, e in ornekler))}")
        yaz(f"diller       : {', '.join(diller)}")

        t0 = time.perf_counter()
        sonuclar = {d: dili_kostur(ornekler, istemci, d, yaz) for d in diller}
        gecen = time.perf_counter() - t0

        yaz(f"\n{'=' * 74}")
        yaz("KARSILASTIRMA VE ADIM 4 KAPISI")
        yaz("=" * 74)
        yaz(f"{'olcut':26s} {'esik':>7s} " +
            " ".join(f"{d.upper():>10s}" for d in diller))
        yaz("-" * 62)

        def satir(ad: str, esik: float, degerler: list[float]) -> None:
            im = " ".join(
                f"{v:10.3f}" if v is not None else f"{'—':>10s}" for v in degerler
            )
            gecti = any(v is not None and v >= esik for v in degerler)
            yaz(f"{ad:26s} {esik:7.2f} {im}   {'GECTI' if gecti else 'KALDI'}")

        satir("belge turu macro-F1", 0.85, [sonuclar[d]["f1"] for d in diller])
        for ad, anahtar, esik in (("SDP okuma (sayidan)", "sdp_okuma", 0.98),
                                  ("SDP katalog (birebir)", "sdp_sozluk", 0.90),
                                  ("SDP tahmin (LLM)", "sdp_tahmin", 0.60)):
            degerler = []
            for d in diller:
                dg, tp = sonuclar[d][anahtar]
                degerler.append(dg / tp if tp else None)
            satir(ad, esik, degerler)

        yaz(f"\n{'p50 gecikme (ms)':26s} {'':7s} " +
            " ".join(f"{sonuclar[d]['p50']:10.0f}" for d in diller))
        yaz(f"{'toplam token':26s} {'':7s} " +
            " ".join(f"{sonuclar[d]['token']:10d}" for d in diller))

        yaz(f"\nistemcinin bildirdigi toplam token: {istemci.toplam_token}")
        yaz(f"sure: {gecen:.0f} sn")
        yaz("\nUYARI: ayri tutulmus degerlendirme seti YOK. Bu olcum gelistirme")
        yaz("setinde yapildi. Istemi olcume bakarak defalarca elden gecirmeyin;")
        yaz("iki-uc tur, sonra durun. Asiri uyum olculemiyor.")
        yaz(f"\nTam cikti: {cikti}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
