#!/usr/bin/env python3
"""ADIM 5a — 300 belgeyi PDF olarak basar, ALAN kusurlarını enjekte eder.

    etiket_NNN.json  +  govde_NNN.txt          -> belgeler_pdf/belge_NNN.pdf
                     (kusurluysa govdeler_kusurlu/)

ÜÇ KUSUR KATMANI VAR, BU BETİK İKİNCİSİNİ UYGULAR

    4.5  gövde metni    ilgi_kopuk, kapanis_yanlis          22 belge
    5a   BELGE ALANLARI sayi/tarih/konu/imza/muhatap eksik,  88 belge
                        ek beyanı yanlış, sdp uyumsuz,
                        tarih tutarsız
    5b   görüntü        tarama_bozuk                        10 belge

Gövde kusurlu belgelerde metin `govdeler_kusurlu/` klasöründen okunur;
alan kusuru uygulanmaz — bir belgede TEK kusur olur, yoksa sistem
hangisini kaçırdığı ölçülemez.

ETİKET İKİ DEĞER TAŞIR
Enjeksiyon sonrası etikete `kusur_ayrinti` eklenir:

    "sdp": { "kod": "115.02.01" }        <- DOĞRU kod (cevap anahtarı)
    "kusur": "sdp_uyumsuz"
    "kusur_ayrinti": {
        "dogru_deger":    "E-18426575-115.02.01-4471829",
        "enjekte_edilen": "E-18426575-934.01-4471829"
    }

Sistemin görevi doğru kodu tahmin etmek değil UYUMSUZLUĞU YAKALAMAK.
İki değer de kayıtlı olmazsa "sistem uyumsuzluğu buldu mu" sorusu
sorulamaz.

KULLANIM

    python bas_pdf.py --kuru           # ne yapilacagini goster, YAZMA
    python bas_pdf.py --belge 001 005  # belirli belgeler
    python bas_pdf.py --yedek          # etiketleri yedekle, sonra bas
    python bas_pdf.py --temiz-de       # kusursuz surumleri de bas
    python bas_pdf.py                  # 300 belge
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

BURASI = Path(__file__).resolve().parent
DEPO_KOKU = BURASI.parent.parent
sys.path.insert(0, str(DEPO_KOKU))

from src.pdf_render import Kusur, belge_ciz, gonderen_iletisimi  # noqa: E402

ETIKETLER = BURASI / "etiketler"
GOVDELER = BURASI / "govdeler"
GOVDELER_KUSURLU = BURASI / "govdeler_kusurlu"
HEDEF = BURASI / "belgeler_pdf"
# Kusursuz sürümler. Kusur enjeksiyonunun gerçekten çalıştığını
# gözle karşılaştırmak ve teknik raporda "önce/sonra" göstermek
# için. Veri setinin parçası DEĞİL — .gitignore'a alınmalı.
HEDEF_TEMIZ = BURASI / "belgeler_pdf_temiz"
KURUMLAR = DEPO_KOKU / "veri" / "kurumlar"

# Bu adımda uygulanan kusurlar. Diğerleri 4.5'te (gövde) ve 5b'de (görüntü).
BU_ADIM = ("sayi_eksik", "tarih_eksik", "konu_eksik", "imza_eksik",
           "muhatap_belirsiz", "ek_beyani_yanlis", "sdp_uyumsuz",
           "tarih_tutarsiz")

# 4.5'te gövdeye uygulananlar — burada alan kusuru eklenmez.
GOVDE_KUSURLARI = ("ilgi_kopuk", "kapanis_yanlis")

# 5b'de görüntüye uygulanacak — PDF normal basılır.
GORUNTU_KUSURLARI = ("tarama_bozuk",)


# =============================================================================
# İMZALAYAN ADI
# =============================================================================
# Üreteçte imzalayan adı YOK. varlik_havuzu.py'ye eklemek rastgele seçim
# sırasını kaydırır ve 300 etiketi değiştirir; bu yüzden burada belge
# numarasından türetiliyor — tekrarlanabilir, sıra kaymaz.

_AD = ["Ahmet", "Mehmet", "Mustafa", "Ali", "Hüseyin", "Hasan", "İbrahim",
       "Osman", "Yusuf", "Ramazan", "Fatma", "Ayşe", "Emine", "Hatice",
       "Zeynep", "Elif", "Meryem", "Şerife", "Zehra", "Sultan"]
_SOYAD = ["YILMAZ", "KAYA", "DEMİR", "ŞAHİN", "ÇELİK", "YILDIZ", "YILDIRIM",
          "ÖZTÜRK", "AYDIN", "ÖZDEMİR", "ARSLAN", "DOĞAN", "KILIÇ", "ASLAN",
          "ÇETİN", "KARA", "KOÇ", "KURT", "ÖZKAN", "ŞİMŞEK"]


def _imzalayan_ad(belge_no: str) -> str:
    n = int(belge_no)
    return f"{_AD[(n * 7) % len(_AD)]} {_SOYAD[(n * 13) % len(_SOYAD)]}"


def _bilgi_icin(belge_no: str) -> str:
    n = int(belge_no) + 337
    unvan = ("Şef", "Memur", "V.H.K.İ.", "Uzman")[n % 4]
    return (f"{_AD[(n * 11) % len(_AD)]} {_SOYAD[(n * 3) % len(_SOYAD)]} / "
            f"{unvan}")


# =============================================================================
# ALAN KUSURLARI
# =============================================================================
# Her kusur için `kusur_ayrinti` üretilir: doğru değer ve enjekte edilen
# değer birlikte kaydedilir.

# SDP uyumsuzluğu için kullanılacak alakasız kodlar. Belgenin gerçek
# konusuyla ilgisi olmayan, ama var olan kodlar seçilir — uydurma bir kod
# "geçersiz kod" kusuruyla karışırdı, oysa ölçmek istediğimiz
# "kod konuyla uyumsuz" durumu.
_ALAKASIZ_KODLAR = ["934.01", "801", "841.01", "903.02", "602.07",
                    "641.04", "755.02", "175", "125", "858"]


def _tarih_kaydir(tarih_metni: str, gun: int) -> str:
    """gg.aa.yyyy biçimindeki tarihi kaydırır."""
    t = datetime.strptime(tarih_metni, "%d.%m.%Y")
    return (t + timedelta(days=gun)).strftime("%d.%m.%Y")


def alan_kusuru_kur(e: dict) -> tuple[Kusur, dict | None]:
    """Etiketteki kusura göre Kusur nesnesi ve ayrıntı sözlüğü üretir.

    Bazı kusurlar etiketin kendisini de değiştirir (sdp_uyumsuz sayıyı
    değiştirir); o durumda `e` yerinde güncellenir.
    """
    tur = e.get("kusur")
    if tur not in BU_ADIM:
        return Kusur(), None

    no = int(e["belge_no"])

    if tur == "sayi_eksik":
        ay = {"alan": "sayi", "dogru_deger": e.get("sayi"),
              "enjekte_edilen": ""}

    elif tur == "tarih_eksik":
        ay = {"alan": "tarih", "dogru_deger": e.get("tarih"),
              "enjekte_edilen": ""}

    elif tur == "konu_eksik":
        ay = {"alan": "konu", "dogru_deger": e.get("konu"),
              "enjekte_edilen": ""}

    elif tur == "imza_eksik":
        ay = {"alan": "imza", "dogru_deger": "imza bloğu",
              "enjekte_edilen": ""}

    elif tur == "muhatap_belirsiz":
        ay = {"alan": "muhatap", "dogru_deger": e.get("muhatap_makam"),
              "enjekte_edilen": "İLGİLİ MAKAMA"}

    elif tur == "ek_beyani_yanlis":
        # "Ek: 2 sayfa" yazar ama 1 sayfa vardır. Beyan ile gerçek
        # arasındaki fark ölçülebilir olmalı.
        gercek = (e.get("ek") or {}).get("sayfa", 1)
        yanlis = gercek + 1 + (no % 3)
        ay = {"alan": "ek_sayfa", "dogru_deger": gercek,
              "enjekte_edilen": yanlis}

    elif tur == "sdp_uyumsuz":
        # Sayının ortasındaki SDP kodu konuyla ilgisiz bir kodla
        # değiştirilir. ETİKETTEKİ `sdp.kod` DOĞRU KALIR — o cevap
        # anahtarıdır; belgede görünen kod yanlıştır.
        dogru_sayi = e.get("sayi") or ""
        dogru_kod = e["sdp"]["kod"]
        yanlis_kod = next(
            k for k in _ALAKASIZ_KODLAR[no % len(_ALAKASIZ_KODLAR):]
            + _ALAKASIZ_KODLAR if k != dogru_kod)
        yanlis_sayi = dogru_sayi.replace(f"-{dogru_kod}-", f"-{yanlis_kod}-")
        if yanlis_sayi == dogru_sayi:
            # Kod sayıda bulunamadı — enjeksiyon uygulanamaz
            return Kusur(), None
        ay = {"alan": "sayi_sdp_kodu", "dogru_deger": dogru_sayi,
              "enjekte_edilen": yanlis_sayi,
              "dogru_kod": dogru_kod, "enjekte_edilen_kod": yanlis_kod}
        e["sayi"] = yanlis_sayi          # belgede yanlış kod görünecek

    elif tur == "tarih_tutarsiz":
        # İlgi tarihi belge tarihinden SONRA. Belge, cevap verdiği
        # yazıdan önce yazılmış görünür — imkânsız.
        dogru = e["ilgi"]["tarih"]
        yanlis = _tarih_kaydir(e["tarih"], 20 + (no % 40))
        ay = {"alan": "ilgi_tarihi", "dogru_deger": dogru,
              "enjekte_edilen": yanlis, "belge_tarihi": e["tarih"]}

    else:
        return Kusur(), None

    ay["kusur"] = tur
    return Kusur(tur, ay), ay


# =============================================================================
# KOŞUM
# =============================================================================


def kurum_jsonlari() -> dict:
    d = {}
    for dosya, kod in (("kurum.json", "yenimahalle_belediyesi"),
                       ("kurum_gazi.json", "gazi_rektorlugu"),
                       ("kurum_ilmem.json", "ankara_il_mem")):
        yol = KURUMLAR / dosya
        if yol.exists():
            d[kod] = json.loads(yol.read_text(encoding="utf-8"))
    return d


def main() -> int:
    a = argparse.ArgumentParser(description="ADIM 5a PDF uretimi")
    a.add_argument("--kuru", action="store_true", help="goster, YAZMA")
    a.add_argument("--belge", nargs="+", metavar="NO")
    a.add_argument("--temizle", action="store_true", help="eski PDFleri sil")
    a.add_argument("--yedek", action="store_true",
                   help="etiketleri yazmadan once yedekle")
    a.add_argument("--temiz-de", dest="temiz_de", action="store_true",
                   help="kusursuz surumleri de bas (karsilastirma icin)")
    ns = a.parse_args()

    yollar = sorted(ETIKETLER.glob("etiket_*.json"))
    if not yollar:
        raise SystemExit(f"HATA: {ETIKETLER} icinde etiket yok.")
    if ns.belge:
        istenen = {n.zfill(3) for n in ns.belge}
        yollar = [y for y in yollar if y.stem.split("_")[-1] in istenen]

    KJ = kurum_jsonlari()

    print(f"Etiket   : {len(yollar)} adet")
    print(f"Bu adim  : {len(BU_ADIM)} alan kusuru")

    if ns.yedek and not ns.kuru:
        damga = datetime.now().strftime("%Y%m%d_%H%M")
        hedef = BURASI / f"etiketler_yedek_{damga}"
        shutil.copytree(ETIKETLER, hedef)
        print(f"Yedek    : {hedef.name}")

    if ns.temizle and not ns.kuru:
        for k in (HEDEF, HEDEF_TEMIZ):
            if k.exists():
                shutil.rmtree(k)
    if not ns.kuru:
        HEDEF.mkdir(parents=True, exist_ok=True)
        if ns.temiz_de:
            HEDEF_TEMIZ.mkdir(parents=True, exist_ok=True)

    sayac: Counter = Counter()
    atlanan, basilan = [], 0

    for yol in yollar:
        e = json.loads(yol.read_text(encoding="utf-8"))
        no = e["belge_no"]
        tur = e.get("kusur")

        # --- gövde metni: kusurlu sürüm varsa oradan ------------------------
        kusurlu_govde = GOVDELER_KUSURLU / f"govde_{no}.txt"
        if tur in GOVDE_KUSURLARI and kusurlu_govde.exists():
            govde_yolu = kusurlu_govde
        else:
            govde_yolu = GOVDELER / f"govde_{no}.txt"
        if not govde_yolu.exists():
            atlanan.append((no, "govde bulunamadi"))
            continue
        govde = govde_yolu.read_text(encoding="utf-8")

        # --- alan kusuru ----------------------------------------------------
        kusur, ayrinti = alan_kusuru_kur(e)
        if tur in BU_ADIM and ayrinti is None:
            atlanan.append((no, f"{tur}: uygulanacak yer bulunamadi"))
            continue

        # --- gönderen bilgileri --------------------------------------------
        e["imzalayan_ad"] = _imzalayan_ad(no)
        e["bilgi_icin"] = _bilgi_icin(no)
        e["gonderen_iletisim"] = gonderen_iletisimi(
            e, KJ.get(e["alici"]["kurum_kodu"]))

        if ayrinti:
            sayac[tur] += 1
        elif tur in GOVDE_KUSURLARI:
            sayac[f"{tur} (4.5)"] += 1
        elif tur in GORUNTU_KUSURLARI:
            sayac[f"{tur} (5b)"] += 1
        else:
            sayac["kusursuz"] += 1

        if ns.kuru:
            if ayrinti:
                print(f"\nbelge_{no}  [{tur}]")
                print(f"  ONCE : {str(ayrinti['dogru_deger'])[:70]}")
                print(f"  SONRA: {str(ayrinti['enjekte_edilen'])[:70]}")
            continue

        belge_ciz(HEDEF / f"belge_{no}.pdf", e, govde, kusur)
        basilan += 1

        # --- kusursuz sürüm (isteğe bağlı) ----------------------------------
        # Kusur uygulanmamış hâli. sdp_uyumsuz belgede `e["sayi"]` yukarıda
        # bozulduğu için doğru değer geri konur; gövde kusurlularda da
        # temiz metin kullanılır.
        if ns.temiz_de:
            temiz = dict(e)
            if ayrinti and ayrinti.get("alan") == "sayi_sdp_kodu":
                temiz["sayi"] = ayrinti["dogru_deger"]
            temiz_govde = (GOVDELER / f"govde_{no}.txt").read_text(
                encoding="utf-8")
            belge_ciz(HEDEF_TEMIZ / f"belge_{no}.pdf", temiz, temiz_govde,
                      Kusur())

        if ayrinti:
            # Etikete kusur ayrıntısını yaz. `sdp.kod` DOKUNULMAZ —
            # cevap anahtarıdır. `sayi` alanı da orijinaline döndürülür;
            # belgede yanlış kod var, etikette doğrusu durur.
            ham = json.loads(yol.read_text(encoding="utf-8"))
            ham["kusur_ayrinti"] = ayrinti
            yol.write_text(json.dumps(ham, ensure_ascii=False, indent=2)
                           + "\n", encoding="utf-8")

    print("\n" + "=" * 66)
    print(f"SONUÇ: {basilan} PDF basildi" if not ns.kuru
          else "SONUÇ: kuru kosum")
    print("=" * 66)
    for k, n in sorted(sayac.items(), key=lambda x: -x[1]):
        print(f"  {k:<28} {n}")
    if atlanan:
        print(f"\n  ATLANAN {len(atlanan)}:")
        for no, sebep in atlanan:
            print(f"    belge_{no}  {sebep}")

    if ns.kuru:
        print("\n(--kuru: dosya yazilmadi)")
        return 0
    print(f"\n  PDF'ler -> {HEDEF}")
    if ns.temiz_de:
        print(f"  Kusursuz surumler -> {HEDEF_TEMIZ}")
        print("  (karsilastirma icin; .gitignore'a alin)")
    print("\nSIRADAKI: python denetle_pdf.py   (kusur dogrulamasi)")
    return 1 if atlanan else 0


if __name__ == "__main__":
    raise SystemExit(main())
