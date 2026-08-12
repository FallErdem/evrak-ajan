#!/usr/bin/env python3
"""ADIM 4.5 — gövde metnine kusur enjekte eder.

    govdeler/govde_NNN.txt  +  etiketler/etiket_NNN.json
                     |
              kusur_enjekte.py
                     |
    govdeler_kusurlu/govde_NNN.txt     (yalnızca kusurlu belgeler)
    etiketler/etiket_NNN.json          (kusur_ayrinti alanı eklenir)

ORIJINAL GOVDELER KORUNUR. Kusurlu metinler AYRI klasore yaziliyor;
enjeksiyon geri alinabilir olmali. Bu turda uc kez ureteci degistirip
uretilmis govdeleri gecersiz kildik, ayni hatayi tekrarlamayalim.

BU ADIMDA YALNIZCA IKI KUSUR VAR
Kusurlarin cogu govdeye degil BELGE ALANLARINA dokunuyor ve PDF
kurulurken uygulanacak:

    4.5 govde        ilgi_kopuk, kapanis_yanlis              22 belge
    5a  PDF alanlari sayi/tarih/konu/imza/muhatap eksik,
                     ek beyani yanlis, sdp uyumsuz,
                     tarih tutarsiz                          88 belge
    5b  tarama       tarama_bozuk                            10 belge

ETIKET IKI DEGER TASIR
Enjeksiyon sonrasi etikete `kusur_ayrinti` alani eklenir:

    "sdp": { "kod": "115.02.01" }        <- DOGRU kod (cevap anahtari)
    "kusur": "sdp_uyumsuz"
    "kusur_ayrinti": {
        "dogru_deger":    "115.02.01",
        "enjekte_edilen": "934.01"       <- belgede GORUNEN yanlis kod
    }

Sistemin gorevi dogru kodu tahmin etmek degil UYUMSUZLUGU YAKALAMAK.
Iki deger de kayitli olmazsa "sistem uyumsuzlugu buldu mu" sorusu
sorulamaz.

KULLANIM

    python kusur_enjekte.py --kuru      # ne yapilacagini goster, YAZMA
    python kusur_enjekte.py             # enjekte et
    python kusur_enjekte.py --temizle   # once eski ciktilari sil
    python kusur_enjekte.py --belge 031 # tek belge, ayrintili
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

BURASI = Path(__file__).resolve().parent
DEPO_KOKU = BURASI.parent.parent
sys.path.insert(0, str(DEPO_KOKU))

GOVDELER = BURASI / "govdeler"
ETIKETLER = BURASI / "etiketler"
HEDEF = BURASI / "govdeler_kusurlu"

# Bu adımda uygulanan kusurlar. Diğerleri 5a ve 5b'de.
BU_ADIM = ("ilgi_kopuk", "kapanis_yanlis")


# =============================================================================
# ilgi_kopuk
# =============================================================================
# Belgenin başında "İlgi : 12.02.2026 tarihli yazı" satırı duruyor ama
# metin ona hiç değinmiyor — kopuk.
#
# CÜMLE SİLİNMİYOR, DEĞİŞTİRİLİYOR. Silinseydi paragraf yapısı bozulurdu
# (3 cümlelik paragraf 2 cümle olur) ve linter BCM-01 verirdi; ikinci bir
# kusur eklemiş olurduk ve hangisini ölçtüğümüz karışırdı.
#
# Gerçek hayattaki karşılığı: memur ilgi satırını koymuş ama metinde ona
# değinmeyi unutmuş.

_ILGI_BASLANGICI = re.compile(
    r"^\s*İlgi'?\s*(?:de|'de|de)?\s+(?:kayıtlı|belirtilen|sayılı|yer alan)?\s*",
    re.IGNORECASE)

# İlgi atfı içeren ama cümle başında olmayan ifadeler de temizlenir.
# Değiştirme İKİ AŞAMALI. Tek desenle yapılınca "ilgide belirtilen yazı"
# ifadesi "söz konusu yazı yazı" oluyordu — desen "yazı" kelimesini
# kapsamadığı için ortada kalıyordu.
#
# Önce "yazı" içeren tam kalıplar, sonra kalan ilgi ibareleri.
_ILGI_TAM_KALIP = re.compile(
    r"\b(i̇?lgi'?de\s+(?:kayıtlı|belirtilen|sayılı|yer alan)\s+yazı(?:\w*)?|"
    r"i̇?lgi\s+yazı(?:\w*)?|i̇?lgide\s+belirtilen\s+yazı(?:\w*)?)",
    re.IGNORECASE)

_ILGI_ICI = re.compile(
    r"\b(i̇?lgi'?de\s+(?:kayıtlı|belirtilen|sayılı|yer alan)|i̇?lgide)\b",
    re.IGNORECASE)


# İlgi ibaresi çıkarıldıktan sonra kalan bağlaç artıkları:
#   "İlgi'de kayıtlı yazı ile X konusunda"  ->  "ile X konusunda"
_BAGLAC_ARTIGI = re.compile(r"^\s*(ile|ilgili olarak|gereğince|uyarınca)\s+")


def _ilk_harfi_buyut(metin: str) -> str:
    """Cümle başı büyük harfle başlar."""
    m = metin.lstrip()
    return m[:1].upper() + m[1:] if m else metin


def _ilgi_temizle(metin: str) -> str:
    """İlgi atıflarını nötr karşılıklarıyla değiştirir.

    Sırayla: önce "yazı" içeren tam kalıplar, sonra kalan ibareler.
    Ters sırada yapılırsa "söz konusu yazı yazı" gibi bozuk çıktı olur.
    """
    metin = _ILGI_TAM_KALIP.sub("söz konusu yazı", metin)
    return _ILGI_ICI.sub("daha önce", metin)

# Değiştirme cümlesi YAZAN TİPİNE göre seçilir.
#
# Ölçülen hata: "Konu Müdürlüğümüzce ele alınmıştır." cümlesi bir vatandaş
# dilekçesine konulunca VTD-01 tetikleniyordu — vatandaş kendinden
# "Müdürlüğümüz" diye söz etmiş oluyor. Kusur ilgi_kopuk olmalıydı,
# ikinci bir kusur eklemiş olduk.
_ILGISIZ_ACILIS_KURUM = [
    "Konuya ilişkin çalışmalar sürdürülmektedir.",
    "Konu Müdürlüğümüzce ele alınmıştır.",
    "Aşağıdaki hususların bildirilmesine ihtiyaç duyulmuştur.",
    "Konuyla ilgili değerlendirme yapılmıştır.",
    "Söz konusu hususta işlem başlatılmıştır.",
]

_ILGISIZ_ACILIS_KISI = [
    "Konuyla ilgili olarak başvuruda bulunuyorum.",
    "Aşağıdaki hususu bilgilerinize sunuyorum.",
    "Konuya ilişkin talebimi iletiyorum.",
    "Bu dilekçemi söz konusu husus için veriyorum.",
    "Aşağıda belirttiğim durum hakkında başvuruyorum.",
]


def _ilgi_kopuk(govde: str, tohum: int,
                yazan_tipi: str = "kurum") -> tuple[str, dict] | None:
    """Metindeki BÜTÜN ilgi atıflarını kaldırır.

    YALNIZCA İLK CÜMLE YETMİYOR. Ölçülen örnek:

        1. cümle: "İlgi'de kayıtlı yazı ile ... talebinde bulunulmuştur."
        2. cümle: "Söz konusu talep ilgide belirtilen yazı çerçevesinde..."

    İlk cümle değiştirildi ama ikincisi kaldı; metin hâlâ ilgiden söz
    ediyordu ve linter kusuru yakalamadı. Kusur uygulanmamış sayılır.

    İki aşama:
      1. İlk cümle "İlgi..." ile başlıyorsa tamamen değiştirilir
      2. Metnin KALANINDAKİ bütün ilgi ibareleri nötr karşılıklarıyla
         değiştirilir

    Cümle SİLİNMİYOR, değiştiriliyor: silinseydi paragraf yapısı bozulur
    (3 cümlelik paragraf 2 olur), linter BCM-01 verirdi ve ikinci bir
    kusur eklemiş olurduk.
    """
    paragraflar = govde.strip().split("\n\n")
    ilk = paragraflar[0]
    cumleler = re.split(r"(?<=[.!?])\s+", ilk)
    if not cumleler:
        return None

    onceki_hali = ilk
    degisti = False

    # 1. AŞAMA: yalnızca ilgi ibaresini çıkar — EN AZ MÜDAHALE.
    #
    # Cümlenin geri kalanı korunur. İlk cümle şartnamedeki anahtar terimi
    # taşıyor olabilir ("İlgi'de kayıtlı yazı ile TAŞIT KAYIT İŞLEMLERİ
    # konusunda..."); cümleyi tamamen değiştirmek o terimi de siler ve
    # KPS-01 tetiklenir — ikinci bir kusur eklemiş oluruz.
    for i, par in enumerate(paragraflar):
        temiz = _ilgi_temizle(par)
        # Cümle başındaki "İlgi'de kayıtlı yazı ile" gibi bağlaçlı
        # açılışlar da temizlenir; kalan cümle büyük harfle başlatılır.
        temiz = _ILGI_BASLANGICI.sub("", temiz)
        temiz = _BAGLAC_ARTIGI.sub("", temiz)
        if temiz != par:
            paragraflar[i] = _ilk_harfi_buyut(temiz)
            degisti = True

    # 2. AŞAMA: ibare çıkarma yetmediyse ilk cümleyi tamamen değiştir.
    ilk_yeni = paragraflar[0]
    if _ILGI_BASLANGICI.match(ilk_yeni) or _ILGI_TAM_KALIP.search(ilk_yeni):
        cumleler = re.split(r"(?<=[.!?])\s+", ilk_yeni)
        havuz = (_ILGISIZ_ACILIS_KURUM if yazan_tipi == "kurum"
                 else _ILGISIZ_ACILIS_KISI)
        cumleler[0] = havuz[tohum % len(havuz)]
        paragraflar[0] = " ".join(cumleler)
        degisti = True

    if not degisti:
        return None

    yeni_govde = "\n\n".join(paragraflar) + "\n"

    # Kanıt 1: hiçbir ilgi atfı kalmamalı
    if (_ILGI_ICI.search(yeni_govde) or _ILGI_TAM_KALIP.search(yeni_govde)
            or _ILGI_BASLANGICI.match(yeni_govde)):
        return None

    return yeni_govde, {
        "yontem": "ilgi_atiflari_kaldirildi",
        "dogru_deger": onceki_hali[:120],
        "enjekte_edilen": paragraflar[0][:120],
    }


# =============================================================================
# kapanis_yanlis
# =============================================================================
# Kılavuz 13.1: rica YALNIZCA aşağı doğru; üst ve aynı düzeydeki makamlara
# arz edilir. Bu kusurda yön TERS ÇEVRİLİYOR.
#
# Yalnızca fiil değişir, cümlenin geri kalanı korunur:
#     "...duyurulması hususunda gereğini rica ederim."
#  -> "...duyurulması hususunda gereğini arz ederim."

_KAPANIS_DESENI = re.compile(
    r"\b(arz\s*/\s*rica|arz\s+ve\s+rica|arz|rica)(\s+ederim)\b", re.IGNORECASE)

# Ters çevirme tablosu. Karma kapanış ("arz/rica") dağıtımlı yazılarda
# kullanılır; tersi tek bir yöne sabitlemektir.
_TERS = {
    "arz": "rica",
    "rica": "arz",
    "arz/rica": "arz",
    "arz / rica": "arz",
    "arz ve rica": "rica",
}


def _kapanis_yanlis(govde: str, beklenen: str) -> tuple[str, dict] | None:
    """Kapanış fiilini ters çevirir.

    SON eşleşme değiştirilir: metnin ortasında "arz" geçebilir
    ("önem arz etmektedir" gibi), kapanış her zaman sondadır.
    """
    eslesmeler = list(_KAPANIS_DESENI.finditer(govde))
    if not eslesmeler:
        return None

    son = eslesmeler[-1]
    bulunan = re.sub(r"\s+", " ", son.group(1).strip().lower())
    yeni_fiil = _TERS.get(bulunan)
    if not yeni_fiil:
        return None

    yeni = govde[:son.start(1)] + yeni_fiil + govde[son.end(1):]
    return yeni, {
        "yontem": "kapanis_ters_cevrildi",
        "dogru_deger": bulunan,
        "enjekte_edilen": yeni_fiil,
        "beklenen_kapanis": beklenen,
    }


# =============================================================================
# KOŞUM
# =============================================================================


# Hangi kusur hangi kuralı tetiklemeli. Başka kural çıkarsa yan etkidir.
_BEKLENEN_KURAL = {
    "ilgi_kopuk": {"ILG-03"},
    "kapanis_yanlis": {"ME-03"},
}


def _yan_etki(metin: str, e: dict, kusur: str) -> list[str]:
    """Kusurlu metinde beklenenden başka kural tetikleniyor mu."""
    from src.linter import Etiket, denetle
    et = Etiket(
        belge_no=e["belge_no"], yazan_tipi=e["yazan_tipi"],
        hiyerarsi_yonu=e["hiyerarsi_yonu"], ilgi_var=bool(e["ilgi"]),
        ek_var=bool(e["ek"]),
        paragraf_cumle_sayilari=e["paragraf_cumle_sayilari"],
        yasakli_adlar=e["yasakli_adlar"],
        anahtar_terimler=e["anahtar_terimler"],
        ek_adi=(e["ek"]["aciklama"] if e.get("ek") else ""),
    )
    cikan = {b.kural for b in denetle(metin, et).hatalar}
    return sorted(cikan - _BEKLENEN_KURAL.get(kusur, set()))


def main() -> int:
    a = argparse.ArgumentParser(description="ADIM 4.5 kusur enjeksiyonu")
    a.add_argument("--kuru", action="store_true", help="goster, YAZMA")
    a.add_argument("--temizle", action="store_true", help="eski ciktilari sil")
    a.add_argument("--belge", nargs="+", metavar="NO", help="belirli belgeler")
    ns = a.parse_args()

    etiket_yollari = sorted(ETIKETLER.glob("etiket_*.json"))
    if not etiket_yollari:
        raise SystemExit(f"HATA: {ETIKETLER} icinde etiket yok.")

    hedefler = []
    for y in etiket_yollari:
        e = json.loads(y.read_text(encoding="utf-8"))
        if e.get("kusur") not in BU_ADIM:
            continue
        if ns.belge and e["belge_no"] not in {n.zfill(3) for n in ns.belge}:
            continue
        hedefler.append((y, e))

    print(f"Etiket   : {len(etiket_yollari)} adet")
    print(f"Bu adim  : {', '.join(BU_ADIM)}")
    print(f"Hedef    : {len(hedefler)} belge")

    if ns.temizle and HEDEF.exists() and not ns.kuru:
        shutil.rmtree(HEDEF)
    if not ns.kuru:
        HEDEF.mkdir(parents=True, exist_ok=True)

    basarili, atlanan = [], []
    sayac: Counter = Counter()

    for etiket_yolu, e in hedefler:
        no = e["belge_no"]
        govde_yolu = GOVDELER / f"govde_{no}.txt"
        if not govde_yolu.exists():
            atlanan.append((no, "govde bulunamadi"))
            continue

        govde = govde_yolu.read_text(encoding="utf-8")
        kusur = e["kusur"]

        if kusur == "ilgi_kopuk":
            sonuc = _ilgi_kopuk(govde, int(no), e["yazan_tipi"])
        elif kusur == "kapanis_yanlis":
            sonuc = _kapanis_yanlis(govde, e["beklenen_kapanis"])
        else:
            sonuc = None

        if sonuc is None:
            atlanan.append((no, f"{kusur}: uygulanacak yer bulunamadi"))
            continue

        yeni_govde, ayrinti = sonuc
        if yeni_govde == govde:
            atlanan.append((no, f"{kusur}: metin degismedi"))
            continue

        # ENJEKSIYON IKINCI BIR KUSUR URETMEMELI. Kusurlu metinde
        # BEKLENEN kuraldan başka hata çıkarsa belge ölçümde kullanılamaz:
        # sistem kusuru bulamadığında hangi kusurun kaçırıldığı belirsiz
        # kalır. Ölçülen örnek: ilgi cümlesi değiştirilirken şartnamedeki
        # bir bilgi siliniyor ve KPS-01 tetikleniyordu.
        yan = _yan_etki(yeni_govde, e, kusur)
        if yan:
            atlanan.append((no, f"{kusur}: yan etki -> {yan}"))
            continue

        sayac[kusur] += 1
        basarili.append(no)

        if ns.belge or ns.kuru:
            print(f"\n--- belge_{no}  [{kusur}] ---")
            print(f"  yontem : {ayrinti['yontem']}")
            print(f"  ONCE   : {str(ayrinti['dogru_deger'])[:76]}")
            print(f"  SONRA  : {str(ayrinti['enjekte_edilen'])[:76]}")

        if ns.kuru:
            continue

        (HEDEF / f"govde_{no}.txt").write_text(yeni_govde, encoding="utf-8")
        e["kusur_ayrinti"] = ayrinti
        etiket_yolu.write_text(
            json.dumps(e, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("\n" + "=" * 66)
    print(f"SONUÇ: {len(basarili)} belgeye kusur enjekte edildi")
    print("=" * 66)
    for k, n in sayac.most_common():
        print(f"  {k:<18} {n}")
    if atlanan:
        print(f"\n  ATLANAN {len(atlanan)}:")
        for no, sebep in atlanan:
            print(f"    belge_{no}  {sebep}")

    if ns.kuru:
        print("\n(--kuru: dosya yazilmadi)")
        return 0

    print(f"\n  Kusurlu govdeler -> {HEDEF}")
    print(f"  Orijinaller {GOVDELER} icinde DOKUNULMADAN duruyor.")
    print("\nSIRADAKI: python denetle_kusur.py   (enjeksiyon dogrulamasi)")
    return 1 if atlanan else 0


if __name__ == "__main__":
    raise SystemExit(main())
