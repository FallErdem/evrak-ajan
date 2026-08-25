"""Uçtan uca demo — bir belgenin boru hattındaki yolculuğu, adım adım.

NEREYE:  araclar/
NASIL:   python araclar\\demo.py 048
         python araclar\\demo.py 048 031 025
         python araclar\\demo.py 048 --sahte      LLM YOK, biçimi görmek için

Belge başına en çok 4 LLM çağrısı: Anlama 1, Yönlendirici 0-1
(deterministik hat çözerse 0), Yazar 1-2 (üslup döngüsü).

NE İŞE YARAR
------------
İki iş birden görüyor:

  1  DOĞRULAMA — her düğümün gerçekten çıktı üretip üretmediği tek
     bakışta görünüyor. Özet sayılar "çalışıyor" der ama neyin
     üretildiğini göstermez.

  2  DEMO — Ş 8: "her takımdan geliştirdiği sistemin uçtan uca çalışan
     bir demosunu sunması beklenmektedir." Bu betik o demonun kendisi.

Çıktı bilerek uzun ve okunabilir; ölçüm betiği değil, GÖZLE BAKMA aracı.
Sayı üretmiyor — kalite kararını insan verir.
"""

from __future__ import annotations

import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "src"))

ARAMA_YERLERI = (
    ("deneyler", "adim4", "belgeler_pdf"),
    ("veri", "belgeler"),
    ("ornek",),
)
YAPILANDIRMA_ADAYLARI = ("yapilandirma.qwen.json", "yapilandirma_qwen.json",
                         "yapilandirma.json")

CIZGI = "=" * 74
INCE = "-" * 74


def klasor_bul() -> Path:
    for p in ARAMA_YERLERI:
        y = KOK.joinpath(*p)
        if y.exists() and any(y.glob("belge_*.pdf")):
            return y
    for b in KOK.rglob("belge_*.pdf"):
        return b.parent
    sys.exit("belge_*.pdf bulunamadi.")


def yapilandirma_bul() -> Path:
    for ad in YAPILANDIRMA_ADAYLARI:
        y = KOK / ad
        if y.exists():
            return y
    sys.exit(f"Yapilandirma bulunamadi: {YAPILANDIRMA_ADAYLARI}")


def _sahte_istemci():
    """Yalnızca `--sahte` ile. Biçimi görmek için, kaliteyi göstermez."""
    import json
    import types

    class _C:
        def __init__(self, m):
            self.metin = m
            self.bitis_sebebi = "stop"
            self.sure_ms = 0.0
            self.model = "sahte"
            self.token = types.SimpleNamespace(toplam=0)
            self.kesildi_mi = False

    class _I:
        def metin_uret(self, istem, sistem_istemi=None, ek=None, sicaklik=None):
            ad = (((ek or {}).get("response_format") or {})
                  .get("json_schema", {}).get("name", ""))
            if ad == "resmi_yazi_taslagi":
                kap = "Arz ederim."
                for satir in (istem or "").splitlines():
                    if satir.startswith("KAPANIŞ CÜMLESİ"):
                        kap = satir.split(":", 1)[1].strip() or kap
                        break
                return _C(json.dumps({
                    "tur": "cevap_yazisi", "tur_gerekcesi": "sahte",
                    "konu": "Gelen Yazıya Cevap",
                    "metin": f"İlgide kayıtlı yazı incelenmiştir. {kap}",
                    "eksik_bilgiler": []}, ensure_ascii=False))
            if ad == "birim_yonlendirme":
                en = ((ek or {})["response_format"]["json_schema"]["schema"]
                      ["properties"]["birim"]["enum"])
                return _C(json.dumps({"birim": en[0], "gerekce": "sahte",
                                      "kanit_cumle": "", "guven": "orta"},
                                     ensure_ascii=False))
            return _C(json.dumps({"belge_turu": "talep_yazisi",
                                  "gerekce": "sahte", "talep": "sahte",
                                  "ozet": "sahte"}, ensure_ascii=False))
    return _I()


def _yaz_blok(baslik: str, satirlar: list[str]) -> None:
    print(f"\n{baslik}")
    print(INCE)
    for s in satirlar:
        print(s)


def gosterr(no: str, sonuc, etiket: dict | None) -> None:
    d = sonuc.dosya
    u = d.ustveri

    print(f"\n{CIZGI}")
    print(f"belge_{no}")
    print(CIZGI)

    # -- 1-2 · Okuyucu + Ayrıştırıcı --------------------------------------
    r, a = sonuc.okuma, sonuc.ayristirma
    g = getattr(u, "gonderen", None)
    _yaz_blok("1-2 · OKUYUCU + AYRIŞTIRICI", [
        f"  girdi tipi   : {r.girdi_tipi} ({r.motor})  {r.sayfa_sayisi} sayfa, "
        f"{len(r.satirlar)} satır",
        f"  belge ailesi : {a.aile}",
        f"  sayı         : {u.sayi or '—'}",
        f"  tarih        : {u.tarih or '—'}",
        f"  konu         : {u.konu or '—'}",
        f"  muhatap      : {(getattr(u.muhatap, 'ham', None) or '—')}",
        f"  gönderen     : {(getattr(g, 'birim', None) or getattr(g, 'idare', None) or getattr(g, 'ad', None) or '—')}"
        f"   [{getattr(g, 'tur', '—')}]",
        f"  ilgi         : {len(u.ilgi)} adet" + (
            f" · {u.ilgi[0].tarih} / {u.ilgi[0].sayi}" if u.ilgi else ""),
        f"  ek           : {len(u.ekler)} adet",
        f"  imza         : {u.imza.ad or '—'} · {u.imza.unvan or '—'}",
        f"  gövde        : {len(d.metin or '')} karakter",
        f"      son 60   : ...{(d.metin or '')[-60:]!r}",
    ])
    if a.uyarilar:
        print(f"  uyarılar     : {a.uyarilar}")

    # -- 3 · Anlama --------------------------------------------------------
    s3 = d.siniflandirma
    ic = d.icerik
    _yaz_blok("3 · ANLAMA  (LLM)", [
        f"  belge türü   : {s3.belge_turu}",
        f"  gerekçe      : {s3.gerekce or '—'}",
        f"  SDP kodu     : {getattr(s3.sdp, 'kod', None) or '—'}"
        f"  {getattr(s3.sdp, 'ad', None) or ''}",
        f"  talep        : {ic.talep or '—'}",
        f"  özet         : {(ic.ozet or '—')[:220]}",
    ])
    if etiket:
        bek = etiket.get("belge_turu")
        print(f"  cevap anahtarı: {bek}"
              f"   {'✓' if str(s3.belge_turu).endswith(str(bek) or '') or bek in str(s3.belge_turu) else '(karşılaştır)'}")

    # -- 4 · Denetçi -------------------------------------------------------
    eksikler = ic.eksik_alanlar or []
    satir = [f"  bulunan eksik: {len(eksikler)}"]
    for e in eksikler[:8]:
        satir.append(
            f"      [{e.kural_id or '—'}] {e.onem} · {e.alan}"
            f"{'  · TALEP EDİLEBİLİR' if e.talep_edilebilir else ''}")
        if e.soru:
            satir.append(f"          soru: {e.soru}")
    _yaz_blok("4 · DENETÇİ  (kural motoru, gelen evrak)", satir)

    # -- 11 · Yönlendirici -------------------------------------------------
    y = d.yonlendirme
    yon = sonuc.yonlendirme
    satir = [
        f"  hedef birim  : {y.hedef_birim or '—'}",
        f"  skor         : {y.skor}",
        f"  kaynak       : {y.kaynak}   [hat: {getattr(yon, 'hat', '—')}]",
        f"  gerekçe      : {y.gerekce or '—'}",
        f"  kanıt cümlesi: {(y.kanit_cumle or '—')[:120]}",
    ]
    if y.alternatif_adaylar:
        satir.append("  değerlendirilen diğer birimler:")
        for x in y.alternatif_adaylar[1:5]:
            satir.append(f"      {x.birim_adi or x.birim}  {x.skor}")
    _yaz_blok("11 · YÖNLENDİRİCİ", satir)
    if etiket:
        bek = etiket["alici"]["birim_kodu"]
        print(f"  cevap anahtarı: {bek}   "
              f"{'✓ DOĞRU' if y.hedef_birim == bek else '✗ YANLIŞ'}")

    # -- 9 · Yazar ---------------------------------------------------------
    c = d.cikti_yazi
    ys = sonuc.yazar
    satir = [
        f"  üslup döngüsü: {getattr(ys, 'ozet', '—')}",
    ]
    if ys:
        satir += [
            f"      tur sayısı   : {ys.tur_sayisi}",
            f"      ilk bulgular : {[b.kural_id for b in ys.ilk_bulgular]}",
            f"      kalan        : {[b.kural_id for b in ys.son_bulgular]}",
        ]
        if ys.cakisanlar:
            satir.append(
                f"      kural çakışması (düzeltilmez, taslak doğru): "
                f"{[b.kural_id for b in ys.cakisanlar]}")
    lr = c.linter_raporu
    satir.append(f"  linter       : {lr.denetlenen_kural_sayisi} kural denetlendi, "
                 f"{lr.atlanan_kural_sayisi} atlandı, {len(lr.bulgular)} bulgu")
    satir.append(f"  tür kararı   : {c.tur}")
    satir.append(f"  gerekçe      : {c.tur_gerekcesi or '—'}")
    _yaz_blok("9 · YAZAR  (LLM + üslup döngüsü)", satir)

    print("\n  ÜRETİLEN TASLAK")
    print("  " + "·" * 70)
    for satir_ in (c.baslik or "(başlık yok)").splitlines():
        print(f"  {satir_}")
    print()
    print("  Sayı  :")                 # EBYS/defter atar
    print("  Tarih :")
    print(f"  Konu  : {c.konu or '—'}")
    print()
    for satir_ in (c.muhatap or "—").splitlines():
        print(f"  {satir_}")
    print()
    for satir_ in (c.metin or "(metin üretilmedi)").splitlines():
        print(f"  {satir_}")
    print()
    print(f"  {' ' * 38}[ad EBYS'den]")
    print(f"  {' ' * 38}{c.imza_unvan or '—'}")
    print("  " + "·" * 70)

    # -- eksik bilgi talebi ------------------------------------------------
    t = d.eksik_bilgi_talebi
    if t:
        _yaz_blok("EKSİK BİLGİ TALEBİ  (Ş 6.4.2 madde 5)", [
            f"  muhatap      : {t.muhatap_ad} [{t.muhatap_turu}]",
            f"  dayanak      : {t.dayanak or '—'}",
            *[f"      soru: {q}" for q in t.sorular],
        ])

    # -- 12 · Güven kapısı -------------------------------------------------
    k = d.karar
    satir = [
        f"  karar        : {'OTOMATİK ONAY' if k.otomatik_onay else 'İNSAN ONAYI'}",
        f"  toplam güven : {k.toplam_guven}   eşik {k.esik}",
        f"  durum        : {d.durum}",
    ]
    if sonuc.kapi:
        satir.append(f"  bileşenler   : {sonuc.kapi.bilesenler}")
    for sb in k.sebepler:
        satir.append(f"      sebep: {sb}")
    _yaz_blok("12 · GÜVEN KAPISI", satir)

    # -- defter ------------------------------------------------------------
    try:
        from defter import DefterHatasi, giden_sayi_kur

        sayi = giden_sayi_kur(d, 47)
        _yaz_blok("DEFTER  (giden evrak numarası — sıra no defterden gelir)",
                  [f"  giden sayı   : {sayi}",
                   "  (47 örnek sıra numarası; gerçekte kurum sayacından)"])
    except DefterHatasi as e:
        _yaz_blok("DEFTER", [f"  sayı üretilemedi: {e}"])
    except Exception:  # noqa: BLE001
        pass

    # -- iz kaydı ----------------------------------------------------------
    _yaz_blok("İŞLEM GÜNLÜĞÜ", [
        f"  {i.adim_no:>2} · {i.ajan:14s} {i.sure_ms:7.0f} ms  "
        f"{'ok' if i.basarili else 'HATA'}  {i.ozet or ''}"
        for i in d.iz
    ] + [
        f"  toplam {sonuc.sure_ms:.0f} ms · {sonuc.llm_cagrisi} LLM çağrısı",
    ])
    if sonuc.hatalar:
        print(f"  HATALAR : {sonuc.hatalar}")
    if sonuc.uyarilar:
        print(f"  uyarılar: {sonuc.uyarilar[:5]}")
    if sonuc.atlanan:
        print(f"  atlanan : {sonuc.atlanan}")


def main() -> int:
    import json

    from boru_hatti import isle
    from kural_motoru import KuralMotoru

    numaralar = [a for a in sys.argv[1:] if not a.startswith("--")] or ["048"]
    sahte = "--sahte" in sys.argv

    istemci = _sahte_istemci() if sahte else None
    if not sahte:
        from llm_istemci import istemci_olustur
        istemci = istemci_olustur(yapilandirma_bul())

    denetci = None
    try:
        from denetci import Denetci
        denetci = Denetci()
    except Exception as e:  # noqa: BLE001
        print(f"UYARI: Denetçi kurulamadı ({type(e).__name__}); "
              f"eksik bilgi talebi ölçülemez")

    motor = KuralMotoru()
    klasor = klasor_bul()
    ek = klasor / "etiketler"
    if not ek.exists():
        ek = klasor.parent / "etiketler"

    print(f"kip: {'SAHTE İSTEMCİ' if sahte else 'GERÇEK LLM'}   klasör: {klasor}")

    for no in numaralar:
        pdf = klasor / f"belge_{no}.pdf"
        if not pdf.exists():
            print(f"\nbelge_{no}: PDF yok ({pdf})")
            continue
        ey = ek / f"etiket_{no}.json"
        etiket = json.loads(ey.read_text(encoding="utf-8")) if ey.exists() else None
        sonuc = isle(pdf, istemci, motor, denetci)
        gosterr(no, sonuc, etiket)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
