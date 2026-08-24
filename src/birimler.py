"""Birim tablosu — CSV'den okur, API sözleşmesinin şekline çevirir.

TEK KAYNAK: veri/kurumlar/birimler*.csv
Bu modülün ürettiği JSON elle düzenlenmez; CSV değişirse yeniden üretilir.

Üç alan CSV'de yoktur, burada hesaplanır:

  sdp_kodlari      "210.01;225.02" tek dize  ->  ["210.01", "225.02"]
  kurum            ust_birim_kodu zinciri köke kadar takip edilerek
  hedef_olabilir   yönlendiricinin aday kümesi

1.1.0'DA EKLENEN — DETSİS ARAMASI VE KURUM PROFİLLERİ
-----------------------------------------------------
Yazar (AJAN 2) taslağın muhatabını ve arz/rica yönünü belirlemek için
"gelen evrağı kim yazdı" sorusunu cevaplamak zorunda. Cevap sayının İKİNCİ
bölümünde yazılı:

    E-90226917-773-3774584
      ^^^^^^^^                Çankaya Belediye Başkanlığı'nın DETSİS numarası

Bu modül o numarayı ada çevirir. İki kayıt taranır:

    birimler*.csv          35 iç birim   -> seviye + imza unvanı da gelir
    kurum*.json muhatap_detsis  10 dış makam  -> yalnızca kanonik ad

ÖLÇÜLDÜ (300 etiket, gonderen.detsis_no cevap anahtarı):
    DETSİS taşıyan belge          168 / 300   (kalanı dilekçe ve şirket)
    43 numaralık indekste bulunan 165 / 168   = %98,2
    bulunamayan                     3         detsis_kaynagi="sentetik",
                                              veri setinde üretilmiş liseler

NEDEN METİN DEĞİL RAKAM
-----------------------
Antetten ad okumak da mümkün ve ikinci hat olarak duruyor. Ama antet OCR'a
açık: ölçüldü, 6 kurum yazısında "T.C." satırı düşmüş (ayristirici
_aile_tespit). Rakam bozulmuyor, ad bozuluyor. Bu yüzden DETSİS birinci hat.

ÇAKIŞMA — iç kayıt önce
-----------------------
İki numara her iki kayıtta birden var: 39985474 (Gazi Rektörlüğü) ve
55461037 (Ankara İl MEM). İkisi de seviye 0 kök kurum; kendi tablolarında
birim, diğer iki kurumun tablosunda dış makam olarak duruyorlar. İç kayıt
önceliklidir çünkü seviye ve imza unvanı taşır; dış kayıt yalnızca ad.
Kayıp yok: kurumlar farklıysa çağıran taraf zaten kök ada düşüp
yazisma_bicimi'ne bakıyor.

Hesabı iki tarafın ayrı ayrı yapması, iki uygulamanın zamanla ayrışması
demektir. Bu yüzden tek yerde yapılıyor: gerçek /api/birimler de,
arayüzün sahte sunucusuna giden JSON da bu fonksiyondan çıkıyor.

Kullanım:
    from birimler import birimleri_yukle, birim_bul, sdp_ile_birim_bul

    for b in birimleri_yukle():
        print(b["kod"], b["ad"])

Sözleşme karşılığı: docs/api_sozlesmesi.md 5.3
"""

from __future__ import annotations

import csv
import json
from functools import lru_cache
from pathlib import Path

# -----------------------------------------------------------------------------
# Yollar
# -----------------------------------------------------------------------------

KOK = Path(__file__).resolve().parent.parent
KURUMLAR_DIZINI = KOK / "veri" / "kurumlar"

# Sıra anlamlıdır: belediye, il MEM, üniversite. Arayüzde bu sırayla listelenir.
CSV_DOSYALARI = ("birimler.csv", "birimler_ilmem.csv", "birimler_gazi.csv")

# Kurum profilleri. Aynı sıra; her dosya kendi `kurum_kodu` alanını taşıdığı
# için indeks dosya adından değil, içerikten kurulur — dosya yeniden
# adlandırılırsa kod kırılmaz.
KURUM_DOSYALARI = ("kurum.json", "kurum_ilmem.json", "kurum_gazi.json")

CIKTI_JSON = KURUMLAR_DIZINI / "birimler.json"


# -----------------------------------------------------------------------------
# Türetme kuralları
# -----------------------------------------------------------------------------

# Hiyerarşi üç kademedir:
#   seviye 0  ->  3 kurum (Yenimahalle Belediyesi, Ankara İl MEM, Gazi Rektörlüğü)
#   seviye 1  ->  5 Belediye Başkan Yardımcılığı
#   seviye 2  ->  27 müdürlük / daire / şube / fakülte
#
# Seviye 1 bir GÖZETİM katmanıdır: başkan yardımcılığına evrak havale edilmez,
# bağlı müdürlüğe edilir. Bu yüzden yönlendiricinin aday kümesi dışındadır.
#
# Kuralı yapısal tutmak önemli: "cevap anahtarında hiç geçmiyor" diye
# çıkarsaydık kendi ölçümümüzü şişirmiş olurduk. Gerekçe idari, istatistiki
# değil. (300 etiket bu kuralı bağımsız olarak doğruluyor — dogrula() bakınız.)
HEDEF_OLAMAYAN_SEVIYE = 1

# Seviye 0 satırları ÇİFTE GÖREVLİDİR: hem kurum hem birim. Ankara İl MEM'e
# 300 belgenin 18'i doğrudan gidiyor. Listeden çıkarılmaz.


def _sayisala(deger: str, varsayilan: int = 0) -> int:
    try:
        return int(str(deger).strip())
    except (TypeError, ValueError):
        return varsayilan


def _kodlari_ayir(ham: str) -> list[str]:
    """'210.01; 225.02 ;' -> ['210.01', '225.02']"""
    if not ham:
        return []
    return [k.strip() for k in ham.split(";") if k.strip()]


def _kok_bul(kod: str, satirlar: dict[str, dict]) -> str:
    """ust_birim_kodu zincirini köke kadar takip eder.

    Döngüye karşı korumalı: bir kod ikinci kez görülürse durur ve o ana
    kadarki en üst kodu döndürür. Veri bozuksa sessizce sonsuz döngüye
    girmektense yanlış ama sonlu bir cevap vermek yeğdir; dogrula() zaten
    yakalar.
    """
    gorulen: set[str] = set()
    su_an = kod
    while True:
        if su_an in gorulen:
            return su_an
        gorulen.add(su_an)
        satir = satirlar.get(su_an)
        if satir is None:
            return su_an
        ust = (satir.get("ust_birim_kodu") or "").strip()
        if not ust:
            return su_an
        su_an = ust


# -----------------------------------------------------------------------------
# Yükleme
# -----------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _ham_satirlar() -> tuple[dict[str, str], ...]:
    """CSV'leri sırayla okur. utf-8-sig: dosyalar BOM taşıyor."""
    satirlar: list[dict[str, str]] = []
    for ad in CSV_DOSYALARI:
        yol = KURUMLAR_DIZINI / ad
        if not yol.exists():
            raise FileNotFoundError(f"Birim dosyası bulunamadı: {yol}")
        with yol.open(encoding="utf-8-sig", newline="") as f:
            satirlar.extend(csv.DictReader(f))
    return tuple(satirlar)


@lru_cache(maxsize=1)
def birimleri_yukle() -> tuple[dict, ...]:
    """35 birimi API sözleşmesinin şeklinde döndürür.

    Sözleşme: docs/api_sozlesmesi.md 5.3
    """
    ham = _ham_satirlar()
    indeks = {s["birim_kodu"]: s for s in ham}

    sonuc: list[dict] = []
    for s in ham:
        kod = s["birim_kodu"]
        seviye = _sayisala(s.get("hiyerarsi_seviyesi"))
        kok_kodu = _kok_bul(kod, indeks)
        kok_satir = indeks.get(kok_kodu, s)

        sonuc.append(
            {
                "kod": kod,
                "ad": s["birim_adi"],
                "kurum": kok_satir["birim_adi"],
                "kurum_kodu": kok_kodu,
                "ust_birim_kodu": (s.get("ust_birim_kodu") or "").strip() or None,
                "seviye": seviye,
                "gorev_alani": (s.get("gorev_alani") or "").strip(),
                "sdp_kodlari": _kodlari_ayir(s.get("sdp_kodlari", "")),
                "vatandas_yogunlugu": (s.get("vatandas_yogunlugu") or "").strip() or None,
                "imza_unvani": (s.get("imza_unvani") or "").strip() or None,
                "detsis_no": (s.get("detsis_no") or "").strip() or None,
                "hedef_olabilir": seviye != HEDEF_OLAMAYAN_SEVIYE,
            }
        )
    return tuple(sonuc)


# -----------------------------------------------------------------------------
# Arama
# -----------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _kod_indeksi() -> dict[str, dict]:
    return {b["kod"]: b for b in birimleri_yukle()}


def birim_bul(kod: str) -> dict | None:
    """Koda göre birim döndürür, yoksa None."""
    return _kod_indeksi().get(kod)


@lru_cache(maxsize=1)
def _sdp_indeksi() -> dict[str, tuple[str, ...]]:
    """SDP kodu -> o koda bakan birim kodları.

    Bir kod birden çok birime düşebilir (ör. 045.02 hem hukuk hem yazı
    işleri). Bu yüzden değer tekil değil, demettir.
    """
    harita: dict[str, list[str]] = {}
    for b in birimleri_yukle():
        for sdp in b["sdp_kodlari"]:
            harita.setdefault(sdp, []).append(b["kod"])
    return {k: tuple(v) for k, v in harita.items()}


def sdp_ile_birim_bul(sdp_kodu: str) -> tuple[str, ...]:
    """SDP kodundan hedef birim(ler)i bulur — yönlendirmenin deterministik hattı.

    SDP kodu, sayının üçüncü bölümünde YAZILIDIR ve okunur, tahmin edilmez.
    Okunabildiğinde hedef birim buradan doğrudan gelir; LLM'e sorulmaz.

    Kod tam eşleşmezse üst kırılıma düşülür: 198.02.01 bulunamazsa 198.02,
    o da yoksa 198 denenir. Dosya planı hiyerarşik olduğu için bu doğrudur.

    Hiçbiri tutmazsa boş demet döner -> yönlendirme LLM'e devredilir.
    """
    if not sdp_kodu:
        return ()
    indeks = _sdp_indeksi()
    parcalar = sdp_kodu.split(".")
    for uzunluk in range(len(parcalar), 0, -1):
        aday = ".".join(parcalar[:uzunluk])
        if aday in indeks:
            return indeks[aday]
    return ()


def hedef_olabilecekler() -> tuple[dict, ...]:
    """Yönlendiricinin aday kümesi — 30 birim."""
    return tuple(b for b in birimleri_yukle() if b["hedef_olabilir"])


# -----------------------------------------------------------------------------
# DETSİS araması — 1.1.0'da eklendi
# -----------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _detsis_indeksi() -> dict[str, dict]:
    """DETSİS numarası -> iç birim kaydı.

    Ölçüldü: 35 birimin 35'inde detsis_no dolu, çakışma yok. Bu yüzden
    değer tekil; sdp_indeksi gibi demet döndürmesine gerek yok. Yine de
    varsayılmıyor — dogrula() çakışmayı kontrol ediyor.
    """
    return {b["detsis_no"]: b for b in birimleri_yukle() if b["detsis_no"]}


def detsis_ile_birim_bul(detsis_no: str | None) -> dict | None:
    """DETSİS numarasından iç birimi bulur, yoksa None.

    SDP aramasının aksine ÜST KIRILIMA DÜŞÜLMEZ. DETSİS hiyerarşik bir kod
    değil, bir kimlik numarasıdır; ilk hanelerini kırpmak başka bir kuruma
    denk gelir. Bulunamadıysa bulunamamıştır.
    """
    if not detsis_no:
        return None
    return _detsis_indeksi().get(str(detsis_no).strip())


# -----------------------------------------------------------------------------
# Kurum profilleri — 1.1.0'da eklendi
# -----------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _kurum_profilleri() -> dict[str, dict]:
    """kurum_kodu -> kurum*.json içeriği.

    Eksik dosya SESSİZCE geçilmez: profil yoksa arz/rica yönü kurum dışı
    muhataplarda hiç belirlenemez ve bu, taslakta yanlış kapanış demektir.
    """
    profiller: dict[str, dict] = {}
    for ad in KURUM_DOSYALARI:
        yol = KURUMLAR_DIZINI / ad
        if not yol.exists():
            raise FileNotFoundError(f"Kurum profili bulunamadı: {yol}")
        veri = json.loads(yol.read_text(encoding="utf-8"))
        kod = veri.get("kurum_kodu")
        if not kod:
            raise ValueError(f"{ad}: kurum_kodu alanı yok")
        profiller[kod] = veri
    return profiller


def kurum_profili(kurum_kodu: str | None) -> dict | None:
    """Kurumun profil sözlüğü (başlık bloğu, hiyerarşi, yazışma biçimi)."""
    if not kurum_kodu:
        return None
    return _kurum_profilleri().get(kurum_kodu)


@lru_cache(maxsize=1)
def _dis_makam_indeksi() -> dict[str, str]:
    """DETSİS numarası -> kanonik dış makam adı.

    Üç profilin `muhatap_detsis` blokları birleştirilir; aynı makam üç
    dosyada da geçtiği için ilk görülen ad kanonik sayılır (üçü de aynı
    yazımı kullanıyor, dogrula() bunu denetliyor).

    İÇ KAYIT ÖNCE: bu indeks yalnızca `detsis_ile_birim_bul` boş dönünce
    kullanılır. Modül başlığındaki çakışma notuna bakınız.
    """
    harita: dict[str, str] = {}
    for profil in _kurum_profilleri().values():
        for ad, kayit in (profil.get("muhatap_detsis") or {}).items():
            no = (kayit.get("detsis_no") or "").strip()
            if no:
                harita.setdefault(no, ad)
    return harita


def dis_makam_bul(detsis_no: str | None) -> str | None:
    """DETSİS numarasından kurum kaydımızda olmayan bir makamın adını verir."""
    if not detsis_no:
        return None
    return _dis_makam_indeksi().get(str(detsis_no).strip())


# -----------------------------------------------------------------------------
# Başlık satırları — 1.1.0'da eklendi
# -----------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _baslik_kaliplari() -> tuple[tuple[str, tuple[str, ...], str], ...]:
    """(kurum_kodu, katlanmış sabit satırlar, son sabit satır) üçlüleri.

    NEDEN TEK SATIR DEĞİL, TAM KALIP — ÖLÇÜLDÜ 2026-08-24
    -----------------------------------------------------
    İlk sürüm tek satıra bakıyordu: antette "ANKARA VALİLİĞİ" geçiyorsa
    gönderen İl MEM'dir diyordu. 300 belgede YANLIŞ çıktı, çünkü o ad İKİ
    ayrı anlamda kullanılıyor:

        T.C. / ANKARA VALİLİĞİ / İl Millî Eğitim Müdürlüğü
             ^ antetin ikinci satırı, gönderen İl MEM

        T.C. / ANKARA VALİLİĞİ
             ^ gönderen valiliğin KENDİSİ

    Tek satıra bakan sürüm ikinci grubu da İl MEM saydı: 26 yanlış çelişki
    uyarısı ve 2 yanlış gönderen (belge_204 ve belge_283) üretti.

    Ayrım kalıbın TAMAMININ bulunmasıdır: valilik satırı ancak yanında
    "İl Millî Eğitim Müdürlüğü" satırı da varsa antet sayılır. Yer
    tutucular ({birim_adi}) ve "T.C." kalıba girmez — biri değişken,
    diğeri her belgede var.
    """
    from metin import katla

    kaliplar: list[tuple[str, tuple[str, ...], str]] = []
    for kod, profil in _kurum_profilleri().items():
        for alan, deger in profil.items():
            if not alan.startswith("baslik_bloku") or not isinstance(deger, list):
                continue
            sabit = [str(s).strip() for s in deger
                     if str(s).strip() and "{" not in str(s)
                     and katla(str(s)) not in ("t.c.", "tc")]
            if sabit:
                kaliplar.append((kod, tuple(katla(s) for s in sabit), sabit[-1]))
    return tuple(kaliplar)


def antet_birimi(metin: str | None) -> dict | None:
    """Antet metni bir kurumun başlık kalıbının TAMAMINI taşıyorsa o birim.

    Kalıbın son sabit satırı hangi birime işaret ettiğini söylüyor:

        "İl Millî Eğitim Müdürlüğü"   -> Ankara İl Millî Eğitim Müdürlüğü
        "İlçe Millî Eğitim Müdürlüğü" -> Yenimahalle İlçe Millî Eğitim Müd.

    İki ad birbirinin alt dizesi değil ("il millî" ile "ilçe millî"
    ayrışıyor), bu yüzden eşleşme tekil kalıyor. Tekil değilse kuruma
    düşülür — kurum doğru, birim belirsiz.

    Birden çok kalıp tutarsa en çok satırlı olan kazanır: daha çok satır
    daha özgül demektir.
    """
    if not metin:
        return None
    from metin import katla

    m = katla(metin)
    en_iyi: tuple[str, tuple[str, ...], str] | None = None
    for kod, satirlar, son in _baslik_kaliplari():
        if all(s in m for s in satirlar):
            if en_iyi is None or len(satirlar) > len(en_iyi[1]):
                en_iyi = (kod, satirlar, son)
    if en_iyi is None:
        return None

    kod, _, son = en_iyi
    parca = katla(son)
    adaylar = [b for b in birimleri_yukle()
               if b["kurum_kodu"] == kod and parca in katla(b["ad"])]
    if len(adaylar) == 1:
        return adaylar[0]
    return birim_bul(kod)


# -----------------------------------------------------------------------------
# Yazışma biçimi — 1.1.0'da eklendi
# -----------------------------------------------------------------------------


def yazisma_bicimi(kurum_kodu: str | None, makam_adi: str | None) -> str | None:
    """Bu kurum, adı geçen makama yazarken 'arz' mı 'rica' mı eder.

    Tablo ALICI KURUMUN AĞZINDAN yazılmıştır: kurum.json'daki
    `"Çankaya Belediye Başkanlığı": "arz"` satırı "Yenimahalle, Çankaya'ya
    arz eder" demektir. Yani dönen değer doğrudan BİZİM TASLAĞIMIZIN
    kapanışıdır; ters çevrilmez.

    KURUM İÇİ İLİŞKİDE BU FONKSİYON ÇAĞRILMAZ
    -----------------------------------------
    Ölçüldü (üç profil): tablolarda `rica` verilen SATIRLARIN TAMAMI kurum
    içi kolektif ifadedir —

        "Yenimahalle Belediyesi müdürlükleri"
        "İl millî eğitim müdürlüğü şube müdürlükleri"
        "Gazi Üniversitesi fakülte, enstitü, yüksekokul ve daire başkanlıkları"

    Bu satırlar KURUMUN KENDİ AĞZINDAN yazılmıştır. Seviye 2'deki bir birim
    onları kendi üzerine uygularsa, kardeş bir birime "rica" yazar ve K 13.1
    ihlal edilir (rica yalnızca aşağı doğru). Somut vaka, belge_031:

        gönderen  Mühendislik Fakültesi Dekanlığı   (Gazi, seviye 2)
        taslağı yazan  Personel Dairesi Başkanlığı  (Gazi, seviye 2)
        tablo der      "fakülte ... başkanlıkları" -> rica     YANLIŞ
        doğrusu        aynı düzey -> arz

    Bu yüzden kurum içi ilişkide yön `hiyerarsi_seviyesi` farkından
    çıkarılır, tabloya hiç bakılmaz. dogrula() ihlali yakalıyor.

    Ad tam eşleşmezse Türkçe işaretler düşürülerek bir kez daha denenir;
    kayıtlar bizim, OCR'dan gelmiyorlar, bu yüzden bulanık eşleştirme YOK.
    """
    profil = kurum_profili(kurum_kodu)
    if profil is None or not makam_adi:
        return None
    tablo = profil.get("yazisma_bicimi") or {}
    if makam_adi in tablo:
        return tablo[makam_adi]

    from metin import katla

    aranan = katla(makam_adi)
    for ad, deger in tablo.items():
        if katla(ad) == aranan:
            return deger
    return None


# -----------------------------------------------------------------------------
# Doğrulama ve üretim
# -----------------------------------------------------------------------------


def dogrula() -> list[str]:
    """Yapısal tutarlılık. Sorun listesi döner; boş liste = temiz."""
    sorunlar: list[str] = []
    birimler = birimleri_yukle()
    kodlar = {b["kod"] for b in birimler}

    if len(kodlar) != len(birimler):
        sorunlar.append("Yinelenen birim_kodu var")

    for b in birimler:
        if b["ust_birim_kodu"] and b["ust_birim_kodu"] not in kodlar:
            sorunlar.append(f"{b['kod']}: üst birim {b['ust_birim_kodu']} tabloda yok")
        if b["kurum_kodu"] not in kodlar:
            sorunlar.append(f"{b['kod']}: kök {b['kurum_kodu']} tabloda yok")
        if b["seviye"] == 0 and b["ust_birim_kodu"]:
            sorunlar.append(f"{b['kod']}: seviye 0 ama üst birimi var")
        if b["hedef_olabilir"] and not b["gorev_alani"]:
            sorunlar.append(f"{b['kod']}: hedef olabilir ama görev alanı boş")
        if b["hedef_olabilir"] and not b["sdp_kodlari"]:
            sorunlar.append(f"{b['kod']}: hedef olabilir ama SDP kodu yok")
        if not b["imza_unvani"]:
            sorunlar.append(f"{b['kod']}: imza unvanı boş")

    # -- 1.1.0: DETSİS ve kurum profilleri ----------------------------------
    sorunlar.extend(_detsis_dogrula(birimler))
    sorunlar.extend(_profil_dogrula(birimler))
    return sorunlar


def _detsis_dogrula(birimler: tuple[dict, ...]) -> list[str]:
    """DETSİS araması güvenilir mi.

    Gönderen çıkarımının birinci hattı bu numaralar. Bir numara iki birime
    düşerse arama sessizce birini seçer ve taslak yanlış muhataba yazılır —
    çıktıya bakan kimse bunu fark etmez. Bu yüzden yükleme anında denetlenir.
    """
    sorunlar: list[str] = []
    gorulen: dict[str, str] = {}
    for b in birimler:
        no = b["detsis_no"]
        if not no:
            sorunlar.append(f"{b['kod']}: DETSİS numarası boş (gönderen araması bu birimi bulamaz)")
            continue
        if no in gorulen:
            sorunlar.append(f"DETSİS {no} iki birimde: {gorulen[no]} ve {b['kod']}")
        gorulen[no] = b["kod"]
    return sorunlar


def _profil_dogrula(birimler: tuple[dict, ...]) -> list[str]:
    """Kurum profilleri kendi içinde ve birim tablosuyla tutarlı mı."""
    from metin import katla

    sorunlar: list[str] = []
    try:
        profiller = _kurum_profilleri()
    except (FileNotFoundError, ValueError) as e:  # noqa: BLE001
        return [str(e)]

    kokler = {b["kod"] for b in birimler if b["seviye"] == 0}
    for kod in sorted(kokler - set(profiller)):
        sorunlar.append(f"{kod}: seviye 0 kurum ama kurum profili yok")

    # Aynı makam adı üç dosyada da aynı numarayı taşımalı; aksi hâlde
    # _dis_makam_indeksi'nin "ilk görüleni al" davranışı keyfîleşir.
    ada_gore: dict[str, str] = {}
    for kk, p in profiller.items():
        for ad, kayit in (p.get("muhatap_detsis") or {}).items():
            no = (kayit.get("detsis_no") or "").strip()
            if not no:
                sorunlar.append(f"{kk}: '{ad}' muhatap_detsis kaydında numara yok")
                continue
            if ada_gore.setdefault(ad, no) != no:
                sorunlar.append(
                    f"'{ad}' iki farklı DETSİS ile kayıtlı: {ada_gore[ad]} / {no} ({kk})"
                )

    # TUZAK KONTROLÜ — yazisma_bicimi'nde 'rica' verilen bir satır, TEK BİR
    # birimin adıysa çelişki vardır. O satırlar kurum içi kolektif ifadedir
    # ve kurum içi yön seviyeden çıkarılır (bkz. yazisma_bicimi docstring).
    # Böyle bir satır eklenirse belge_031 vakası geri gelir: kardeş birime
    # 'rica' yazılır, K 13.1 ihlal edilir ve kural motoru bunu göremez.
    birim_adlari = {katla(b["ad"]): b["kod"] for b in birimler}
    for kk, p in profiller.items():
        for ad, deger in (p.get("yazisma_bicimi") or {}).items():
            if deger == "rica" and katla(ad) in birim_adlari:
                sorunlar.append(
                    f"{kk}: yazisma_bicimi['{ad}'] = rica, ama bu ad birim "
                    f"tablosunda tek bir birime ({birim_adlari[katla(ad)]}) "
                    f"karşılık geliyor. Kurum içi yön seviyeden çıkarılır; "
                    f"bu satır K 13.1 ihlaline yol açar."
                )
            if deger not in ("arz", "rica"):
                sorunlar.append(f"{kk}: yazisma_bicimi['{ad}'] = {deger!r}, 'arz' ya da 'rica' olmalı")

    # Hiyerarşide adı geçen her makamın yazışma biçimi tanımlı olmalı;
    # tanımsız kalan makam taslakta BILINMIYOR'a düşer ve K 13.1 gereği
    # arz üretir — sessiz bir varsayılan, bilerek seçilmiş bir yön değil.
    for kk, p in profiller.items():
        h = p.get("hiyerarsi") or {}
        adlar = set(h.get("ust_makamlar", [])) | set(h.get("ayni_duzey", [])) | \
            set(h.get("alt_makamlar", []))
        eksik = sorted(adlar - set(p.get("yazisma_bicimi") or {}))
        for ad in eksik:
            sorunlar.append(f"{kk}: '{ad}' hiyerarşide var, yazisma_bicimi'nde yok")

    return sorunlar


def json_yaz(yol: Path | None = None) -> Path:
    """Sözleşme şeklindeki JSON'u üretir.

    Bu dosya ELLE DÜZENLENMEZ. Kaynak CSV'dir; değişiklik CSV'de yapılır ve
    bu fonksiyon yeniden koşturulur.
    """
    hedef = yol or CIKTI_JSON
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(
        json.dumps(list(birimleri_yukle()), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return hedef


if __name__ == "__main__":
    birimler = birimleri_yukle()
    print(f"{len(birimler)} birim yüklendi")

    seviyeler: dict[int, int] = {}
    for b in birimler:
        seviyeler[b["seviye"]] = seviyeler.get(b["seviye"], 0) + 1
    for sv in sorted(seviyeler):
        print(f"  seviye {sv}: {seviyeler[sv]}")
    print(f"  hedef olabilir: {len(hedef_olabilecekler())}")
    print(f"  farklı SDP kodu: {len(_sdp_indeksi())}")
    print(f"  DETSİS ile aranabilen birim: {len(_detsis_indeksi())}")
    print(f"  kurum profili: {len(_kurum_profilleri())}")
    print(f"  dış makam (muhatap_detsis): {len(_dis_makam_indeksi())}")
    ortak = set(_detsis_indeksi()) & set(_dis_makam_indeksi())
    if ortak:
        print(f"  her iki kayıtta olan: {len(ortak)} (iç kayıt öncelikli)")
        for no in sorted(ortak):
            print(f"      {no}  {_detsis_indeksi()[no]['ad']}")

    sorunlar = dogrula()
    if sorunlar:
        print(f"\n{len(sorunlar)} SORUN:")
        for s in sorunlar:
            print(f"  ✗ {s}")
        raise SystemExit(1)
    print("\n  ✓ yapısal doğrulama temiz")

    yazilan = json_yaz()
    print(f"  ✓ yazıldı: {yazilan}")
