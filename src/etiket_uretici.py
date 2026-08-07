"""Etiket üreteci — 300 belgenin CEVAP ANAHTARINI üretir.

TEMEL İLKE: ÖNCE CEVAP, SONRA SORU

    YANLIS : belge uret -> sonra "bu neyin belgesi?" diye etiketle
    DOGRU  : etiketi kur -> o etikete uyan belgeyi urettir

Etiket bizim cevap anahtarımız. Belgeden geri çıkarmaya çalışırsak, çıkarma
işlemi hatalıysa cevap anahtarı da hatalı olur ve bunu asla fark edemeyiz.

BU DOSYADA LLM YOK
Kurum seçimi, birim seçimi, SDP kodu, sayı, tarih, kişi, somut bilgiler —
hepsi deterministik Python. LLM yalnızca ADIM 4.4'te devreye girecek ve
sadece metin gövdesini yazacak.

KUSUR ENJEKSİYONU BURADA DEĞİL
Etikete hangi kusurun atandığı yazılır ama kusur uygulanmaz. Uygulama
ADIM 4.5'te, belge kurulduktan sonra yapılır.

KOTA TUTULUR, RASTGELE SEÇİLMEZ
Rastgele dağıtım bir kusurdan 3, başkasından 19 örnek üretir; 3 örnekle
tespit oranı ölçülemez. Üreteç her boyutta kaç belge üreteceğini bilir.
"""

from __future__ import annotations

import csv
import re
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from src.varlik_havuzu import VarlikHavuzu

# =============================================================================
# BÖLÜM 1 — VERİ YÜKLEME
# =============================================================================


@dataclass(frozen=True)
class SdpKodu:
    kod: str
    ad: str
    saklama_suresi: str
    kurum_tipi: str
    vatandas_konusu: bool
    ornek_konular: list[str]
    sikayet_cumleleri: list[str] = field(default_factory=list)

    @property
    def grup_dugumu_mu(self) -> bool:
        """saklama_suresi boşsa bu kod resmî planda bir grup düğümüdür.

        YONTEM.md §7/4. Grup düğümü belge kodu olarak kullanılmamalı;
        altında daha spesifik bir kod vardır.
        """
        return not self.saklama_suresi.strip()


@dataclass(frozen=True)
class Birim:
    birim_kodu: str
    birim_adi: str
    ust_birim_kodu: str
    seviye: int
    gorev_alani: str
    sdp_kodlari: list[str]
    vatandas_yogunlugu: str
    imza_unvani: str
    tipik_muhataplar: list[str]
    detsis_no: str

    @property
    def belge_alabilir_mi(self) -> bool:
        """Kurum (0) ve müdürlük/şube (2) düzeyi evrak alır.

        Başkan yardımcılığı (1) bir koordinasyon katmanıdır; evrak doğrudan
        oraya gitmez, altındaki müdürlüğe gider.
        """
        return self.seviye in (0, 2)


@dataclass(frozen=True)
class Kurum:
    kurum_kodu: str
    kurum_adi: str
    kurum_tipi: str
    teskilat: str
    detsis_no: str
    baslik_bloku: list[str]
    hiyerarsi: dict
    yazisma_bicimi: dict
    muhatap_detsis: dict
    birimler: list[Birim]

    def birim_bul(self, kod: str) -> Birim:
        return next(b for b in self.birimler if b.birim_kodu == kod)

    @property
    def alici_birimler(self) -> list[Birim]:
        return [b for b in self.birimler if b.belge_alabilir_mi]


def sdp_yukle(yol: Path) -> dict[str, SdpKodu]:
    sonuc = {}
    for s in csv.DictReader(yol.open(encoding="utf-8")):
        sonuc[s["kod"]] = SdpKodu(
            kod=s["kod"],
            ad=s["ad"],
            saklama_suresi=s["saklama_suresi"],
            kurum_tipi=s["kurum_tipi"],
            vatandas_konusu=(s["vatandas_konusu"] == "evet"),
            ornek_konular=[k.strip() for k in s["ornek_konular"].split("|") if k.strip()],
            sikayet_cumleleri=[c.strip() for c in
                               s.get("sikayet_cumleleri", "").split("|") if c.strip()],
        )
    return sonuc


def kurum_yukle(kurum_yolu: Path, birim_yolu: Path) -> Kurum:
    k = json.loads(kurum_yolu.read_text(encoding="utf-8"))
    birimler = [
        Birim(
            birim_kodu=b["birim_kodu"],
            birim_adi=b["birim_adi"],
            ust_birim_kodu=b["ust_birim_kodu"],
            seviye=int(b["hiyerarsi_seviyesi"]),
            gorev_alani=b["gorev_alani"],
            sdp_kodlari=[x.strip() for x in b["sdp_kodlari"].split(";") if x.strip()],
            vatandas_yogunlugu=b["vatandas_yogunlugu"],
            imza_unvani=b["imza_unvani"],
            tipik_muhataplar=[x.strip() for x in b["tipik_muhataplar"].split(";") if x.strip()],
            detsis_no=b.get("detsis_no", ""),
        )
        for b in csv.DictReader(birim_yolu.open(encoding="utf-8"))
    ]
    return Kurum(
        kurum_kodu=k["kurum_kodu"],
        kurum_adi=k["kurum_adi"],
        kurum_tipi=k["kurum_tipi"],
        teskilat=k["teskilat"],
        detsis_no=k["detsis_no"],
        baslik_bloku=k["baslik_bloku"],
        hiyerarsi=k.get("hiyerarsi", {}),
        yazisma_bicimi=k.get("yazisma_bicimi", {}),
        muhatap_detsis=k.get("muhatap_detsis", {}),
        birimler=birimler,
    )


@dataclass
class Veri:
    """Üretecin ihtiyaç duyduğu her şey."""

    sdp: dict[str, SdpKodu]
    kurumlar: dict[str, Kurum]
    kota: dict

    @property
    def detsis_defteri(self) -> dict[str, str]:
        """Bilinen bütün makam adı -> DETSİS numarası eşlemesi.

        Ölçülen hata: kod yalnızca ALICININ muhatap_detsis kaydına bakıyordu.
        Yenimahalle Belediyesi, Gazi'nin ve İl MEM'in listesinde yok (kendi
        kurum.json'unda var). Sonuç: belediyeden gelen 15 belgeye gerçek
        numara varken uydurma numara verilmişti.

        Üç kurumun kurum_adi + detsis_no'su ve HER ÜÇÜNÜN muhatap_detsis
        kayıtları birleştiriliyor.
        """
        defter: dict[str, str] = {}
        for k in self.kurumlar.values():
            for ad, v in k.muhatap_detsis.items():
                if v.get("detsis_no"):
                    defter[ad] = v["detsis_no"]
            defter[k.kurum_adi] = k.detsis_no
            for b in k.birimler:
                if b.detsis_no:
                    defter[b.birim_adi] = b.detsis_no
        return defter

    @classmethod
    def yukle(cls, depo_koku: Path) -> "Veri":
        v = depo_koku / "veri"
        kurumlar = {}
        for kj, bc in [
            ("kurum.json", "birimler.csv"),
            ("kurum_gazi.json", "birimler_gazi.csv"),
            ("kurum_ilmem.json", "birimler_ilmem.csv"),
        ]:
            k = kurum_yukle(v / "kurumlar" / kj, v / "kurumlar" / bc)
            kurumlar[k.kurum_kodu] = k
        return cls(
            sdp=sdp_yukle(v / "taksonomi" / "sdp_kodlari.csv"),
            kurumlar=kurumlar,
            kota=json.loads((v / "kota.json").read_text(encoding="utf-8")),
        )


# =============================================================================
# BÖLÜM 2 — SİPARİŞ LİSTESİ
# =============================================================================


@dataclass
class Siparis:
    """Bir belgenin kotadan gelen özellikleri.

    Sipariş, "ne üretilecek" sorusunun cevabı. Henüz hangi birim, hangi kod,
    hangi kişi belli değil — onlar 3. bölümde seçilecek.
    """

    kurum_kodu: str
    gonderen_tipi: str
    belge_turu: str
    ilgi_var: bool
    ek_var: bool
    pdf_bicimi: str
    kusur: str | None
    karma_kapanis: bool = False


def siparis_listesi_kur(kota: dict, havuz: VarlikHavuzu) -> list[Siparis]:
    """Kotayı 300 siparişe açar.

    Sıra önemli: önce en kısıtlı boyut yerleştirilir, sonra gevşekler.
    Ters sırada yapılırsa son boyut için uygun yer kalmaz.

        1. kurum x gonderen_tipi   (capraz tablo, en kati)
        2. belge turu              (gonderen tipiyle uyumlu olmali)
        3. ilgi / ek               (turden gelen zorunluluklar var)
        4. pdf bicimi
        5. kusur                   (on kosullari 3 ve 4'e bagli)
    """
    # --- 1. kurum x gönderen tipi ------------------------------------------
    ham: list[tuple[str, str]] = []
    for gtip, dagilim in kota["gonderen_x_kurum"].items():
        if gtip.startswith("_"):
            continue
        for kurum, adet in dagilim.items():
            ham.extend([(kurum, gtip)] * adet)

    # --- 2. belge türü ------------------------------------------------------
    # Bu bir TAM EŞLEŞME problemi: gönderen arzı 300, tür talebi 300, ve bazı
    # türler yalnızca belirli gönderen tiplerinden gelebilir (tekit yalnızca
    # üst makamdan, olur yalnızca alt makamdan).
    #
    # Açgözlü atama burada tıkanır: bir türü erken tüketirse sonunda
    # eşleşemeyen sipariş kalır. Bu yüzden önce TOPLAM düzeyde maksimum akış
    # çözülüyor (5 gönderen x 11 tür), sonra belgelere dağıtılıyor.
    uyum = kota["tur_gonderen_uyumu"]
    tur_talep = {}
    for grup in ("_vatandas_ve_ozel", "_kurum_yazisi"):
        for tur, adet in kota["belge_turleri"][grup].items():
            if not tur.startswith("_") and tur != "toplam":
                tur_talep[tur] = adet

    gon_arz = Counter(g for _, g in ham)
    tahsis = _akis_coz(gon_arz, tur_talep, uyum)

    # Toplam tahsisi belgelere dağıt
    havuz_tur: dict[str, list[str]] = {}
    for (gtip, tur), adet in tahsis.items():
        havuz_tur.setdefault(gtip, []).extend([tur] * adet)
    for gtip in havuz_tur:
        havuz_tur[gtip] = havuz.karistir(havuz_tur[gtip])

    ham = havuz.karistir(ham)
    atanmis: list[tuple[str, str, str]] = []
    for kurum, gtip in ham:
        atanmis.append((kurum, gtip, havuz_tur[gtip].pop()))

    # --- 3. ilgi ve ek ------------------------------------------------------
    ilgi_zorunlu = set(kota["ilgi"]["zorunlu_var"])
    ilgi_yasak = set(kota["ilgi"]["zorunlu_yok"])
    ek_zorunlu = set(kota["ek"]["zorunlu_var"])
    ek_olasilik = kota["ek"]["olasilik"]

    ilgi_hedef = kota["ilgi"]["toplam_var"]
    ek_hedef = kota["ek"]["toplam_var"]

    ilgiler = [t in ilgi_zorunlu for _, _, t in atanmis]
    # Zorunlu olanlar konduktan sonra kalan kotayı serbest türlere dağıt
    serbest = [i for i, (_, _, t) in enumerate(atanmis)
               if t not in ilgi_zorunlu and t not in ilgi_yasak]
    kalan = ilgi_hedef - sum(ilgiler)
    for i in havuz.karistir(serbest)[:max(0, kalan)]:
        ilgiler[i] = True

    ekler = [t in ek_zorunlu for _, _, t in atanmis]
    aday_ek = [i for i, (_, _, t) in enumerate(atanmis) if t not in ek_zorunlu]
    # Olasılığa göre ağırlıklandır, sonra hedefe göre kırp
    aday_ek.sort(key=lambda i: -ek_olasilik.get(atanmis[i][2], 0.1))
    kalan_ek = ek_hedef - sum(ekler)
    for i in aday_ek[:max(0, kalan_ek)]:
        ekler[i] = True

    # --- 4. PDF biçimi ------------------------------------------------------
    pdf = ["metin_katmanli"] * kota["pdf_bicimi"]["metin_katmanli"] + \
          ["taranmis"] * kota["pdf_bicimi"]["taranmis"]
    pdf = havuz.karistir(pdf)

    # --- birleştir ----------------------------------------------------------
    siparisler = [
        Siparis(kurum_kodu=k, gonderen_tipi=g, belge_turu=t,
                ilgi_var=ilgiler[i], ek_var=ekler[i], pdf_bicimi=pdf[i], kusur=None)
        for i, (k, g, t) in enumerate(atanmis)
    ]

    _kusur_ata(siparisler, kota, havuz)
    _karma_kapanis_ata(siparisler, kota, havuz)
    return siparisler


def _akis_coz(arz: dict[str, int], talep: dict[str, int],
              uyum: dict[str, list[str]]) -> dict[tuple[str, str], int]:
    """Gönderen tipi ile belge türü arasında tam eşleşme bulur.

    Küçük bir maksimum akış problemi (5 x 11). Ford-Fulkerson, BFS ile
    genişleyen yol arar — deterministik, düğüm sırası sabit olduğu için
    aynı girdi hep aynı çıktıyı verir.

        kaynak --arz--> gonderen_tipi --sinirsiz--> belge_turu --talep--> havuz

    Akış toplam talebe eşit değilse plan matematiksel olarak imkânsızdır;
    o durumda hangi kısıtın ihlal edildiğini söyleyerek durur.
    """
    KAYNAK, HAVUZ = "__kaynak__", "__havuz__"
    kapasite: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for g, n in arz.items():
        kapasite[KAYNAK][g] = n
    for t, n in talep.items():
        kapasite[t][HAVUZ] = n
        for g in uyum[t]:
            if g in arz:
                kapasite[g][t] = 10**6

    dugumler = [KAYNAK] + sorted(arz) + sorted(talep) + [HAVUZ]
    akis = 0
    while True:
        # BFS ile genişleyen yol
        onceki: dict[str, str] = {KAYNAK: KAYNAK}
        kuyruk = [KAYNAK]
        while kuyruk and HAVUZ not in onceki:
            u = kuyruk.pop(0)
            for v in dugumler:
                if v not in onceki and kapasite[u][v] > 0:
                    onceki[v] = u
                    kuyruk.append(v)
        if HAVUZ not in onceki:
            break
        # Yol boyunca darboğazı bul ve akıt
        yol, v = [], HAVUZ
        while v != KAYNAK:
            yol.append((onceki[v], v)); v = onceki[v]
        darbogaz = min(kapasite[a][b] for a, b in yol)
        for a, b in yol:
            kapasite[a][b] -= darbogaz
            kapasite[b][a] += darbogaz
        akis += darbogaz

    toplam = sum(talep.values())
    if akis != toplam:
        eksik = {t: talep[t] - kapasite[HAVUZ][t] for t in talep
                 if kapasite[HAVUZ][t] < talep[t]}
        raise RuntimeError(
            f"Kota matematiksel olarak imkansiz: {akis}/{toplam} eslesme kuruldu.\n"
            f"Karsilanamayan turler: {eksik}\n"
            f"kota.json'da tur_gonderen_uyumu veya belge_turleri sayilarini duzeltin."
        )

    return {(g, t): kapasite[t][g] for g in arz for t in talep
            if kapasite[t][g] > 0}


def _on_kosul_saglaniyor_mu(s: Siparis, on_kosul: str | None) -> bool:
    """Kusur enjekte edilebilir mi.

    Ön koşulu sağlamayan belgeye kusur atanırsa ETİKET YALAN SÖYLER:
    'ilgi_kopuk' kusuru olan ama ilgisi olmayan bir belge anlamsızdır ve
    o kusurun tespit oranı ölçülemez hâle gelir.
    """
    if on_kosul is None:
        return True
    if on_kosul == "ilgi_var":
        return s.ilgi_var
    if on_kosul == "ek_var":
        return s.ek_var
    if on_kosul == "taranmis":
        return s.pdf_bicimi == "taranmis"
    if on_kosul == "kurum_yazisi":
        return s.gonderen_tipi not in ("vatandas", "ozel_tuzel")
    raise ValueError(f"Bilinmeyen on kosul: {on_kosul}")


def _kusur_ata(siparisler: list[Siparis], kota: dict, havuz: VarlikHavuzu) -> None:
    """Kusurları ön koşullara ve kurum çaprazına uyarak dağıtır.

    KURUM ÇAPRAZI: her kusur türü üç kurumda da en az N belge. Bir kusur tek
    kurumda toplanırsa, tespit başarısızlığında sebebin kusur mu kurum mu
    olduğunu ayıramayız.
    """
    profiller = kota["kusurlar"]["profiller"]
    asgari = kota["kusurlar"]["kurum_capraz_asgari"]
    kurumlar = list(kota["kurumlar"])

    bos = list(range(len(siparisler)))
    havuz.rnd.shuffle(bos)

    # Zor kusurları (dar ön koşullu) önce yerleştir
    sirali = sorted(
        profiller.items(),
        key=lambda kv: sum(
            1 for i in bos if _on_kosul_saglaniyor_mu(siparisler[i], kv[1]["on_kosul"])
        ),
    )

    for kusur_adi, tanim in sirali:
        hedef, on_kosul = tanim["adet"], tanim["on_kosul"]
        secilen: list[int] = []
        kurum_sayaci = Counter()

        # 1. tur: her kurumdan asgari sayıda
        for kurum in kurumlar:
            uygun = [i for i in bos
                     if siparisler[i].kusur is None
                     and siparisler[i].kurum_kodu == kurum
                     and _on_kosul_saglaniyor_mu(siparisler[i], on_kosul)]
            for i in uygun[:asgari]:
                siparisler[i].kusur = kusur_adi
                secilen.append(i); kurum_sayaci[kurum] += 1

        # 2. tur: kalanı en az yüklü kurumdan doldur
        while len(secilen) < hedef:
            uygun = [i for i in bos
                     if siparisler[i].kusur is None
                     and _on_kosul_saglaniyor_mu(siparisler[i], on_kosul)]
            if not uygun:
                raise RuntimeError(
                    f"'{kusur_adi}' kusuru icin uygun belge kalmadi "
                    f"({len(secilen)}/{hedef}). On kosul: {on_kosul}. "
                    f"kota.json'da bu kusurun adedini dusurun veya on kosulu "
                    f"saglayan belge sayisini artirin."
                )
            uygun.sort(key=lambda i: kurum_sayaci[siparisler[i].kurum_kodu])
            i = uygun[0]
            siparisler[i].kusur = kusur_adi
            secilen.append(i); kurum_sayaci[siparisler[i].kurum_kodu] += 1


def _karma_kapanis_ata(siparisler: list[Siparis], kota: dict, havuz: VarlikHavuzu) -> None:
    """Dağıtımlı yazılara 'arz/rica ederim' kapanışı atar.

    K 13.1: üst, aynı düzey ve alt makamlara birlikte dağıtımlı gönderilen
    yazılar 'Arz ve rica ederim.' ile biter. Yalnızca üst makamdan gelen
    yazılarda anlamlı.
    """
    hedef = kota["karma_kapanis"]["adet"]
    adaylar = [s for s in siparisler if s.gonderen_tipi == "ust_makam"]
    for s in havuz.karistir(adaylar)[:hedef]:
        s.karma_kapanis = True


# =============================================================================
# BÖLÜM 3 — SİPARİŞTEN ETİKETE
# =============================================================================

# Belge türü -> somut bilgi ailesi. Aynı iskeleti paylaşan türler aynı aileye
# girer; 11 tür, 9 aile. Aile sayısı SDP kodu sayısına değil BELGE YAPISINA
# bağlı: "imar durum belgesi talebi" ile "transkript talebi" aynı iskelettir.
_AILE = {
    "dilekce": "belge_talebi",
    "itiraz": "itiraz",
    "sikayet": "sikayet",
    "bilgi_edinme": "bilgi_edinme",
    "cevap_yazisi": "belge_cevabi",
    "talep_yazisi": "kaynak_talebi",   # yön "ust" değilse isbirligi_talebi olur
    "bilgilendirme": "bilgilendirme",
    "gorus_talebi": "gorus_talebi",
    "ust_yazi": "ust_yazi",
    "tekit_yazisi": "tekit",
    "olur_yazisi": "olur",
}

# Aile -> (paragraf sayısı, her paragraftaki cümle sayısı)
_PARAGRAF = {
    "belge_talebi":  [3],
    "itiraz":        [3, 2],
    "sikayet":       [3, 2],
    "bilgi_edinme":  [2, 2],
    "belge_cevabi":  [3, 3],
    "kaynak_talebi": [2, 2],
    "bilgilendirme": [2, 2],
    "gorus_talebi":  [2, 2],
    "isbirligi_talebi": [2, 2],
    "ust_yazi":      [2, 2, 2],
    "tekit":         [2, 2],
    "olur":          [2, 2],
}

# Gönderen tipi -> hiyerarşi yönü (gönderenin alıcıya göre konumu)
_YON = {
    "vatandas": "gercek_kisi_yazari",
    "ozel_tuzel": "ozel_tuzel",
    "ust_makam": "alt",      # gönderen üstte -> muhatap altta -> RİCA
    "ayni_duzey": "ayni",
    "alt_makam": "ust",
}


class EtiketUretici:
    """Siparişi tam etikete dönüştürür.

    SDP kodu seçiminde EN AZ KULLANILAN tercih edilir. Rastgele seçim
    yapılırsa İl MEM'de birkaç kod 6'ya dolar, diğerleri boş kalır ve
    çeşitlilik kotası tutmaz (100 belge / 22 yaprak kod = ortalama 4.5).
    """

    def __init__(self, veri: Veri, havuz: VarlikHavuzu) -> None:
        self.v = veri
        self.h = havuz
        self.kod_sayaci: Counter = Counter()
        self.birim_sayaci: Counter = Counter()
        self.konu_sayaci: Counter = Counter()
        self.gun_sayaci: Counter = Counter()
        self._kayit_taban: dict[str, int] = {}
        self._kayit_hiz: dict[str, int] = {}
        self._sirket_taban: dict[str, int] = {}
        self._sirket_hiz: dict[str, float] = {}
        self._ilk_tarih = datetime.fromisoformat(
            veri.kota['tarih_araligi']['baslangic']).date()
        self.tavan_asimi = 0
        self._sentetik_detsis: dict[str, str] = {}
        self._defter = veri.detsis_defteri
        ces = veri.kota["cesitlilik"]
        self.kod_azami = ces["sdp_kod_basina_azami"]
        self.konu_azami = ces["ornek_konu_azami_tekrar"]
        self.gun_azami = ces["ayni_gun_azami_belge"]

    # -- birim ve kod seçimi -------------------------------------------------

    @staticmethod
    def _isbirligi_mi(s: Siparis) -> bool:
        """Bu sipariş isbirligi_talebi ailesine düşecek mi.

        talep_yazisi + ayni_duzey -> yön "ayni" -> isbirligi_talebi.
        Bunu birim/kod seçiminden ÖNCE bilmek gerekiyor: iki ayrı tüzel
        kişinin ortak işi olan konular sınırlı. Ölçülen hata: üniversite,
        ilçe MEM'den okul aile birliği bağış makbuzu istiyordu.
        """
        return s.belge_turu == "talep_yazisi" and s.gonderen_tipi == "ayni_duzey"

    def _kullanilabilir_kodlar(self, birim: Birim, vatandas: bool) -> list[SdpKodu]:
        """Birimin belge kodu olarak kullanabileceği SDP kodları.

        Grup düğümleri elenir (YONTEM.md §7/4): saklama süresi boş olan kodun
        altında daha spesifik bir kod vardır, belge kodu olarak kullanılmaz.
        """
        kodlar = [self.v.sdp[k] for k in birim.sdp_kodlari
                  if k in self.v.sdp and not self.v.sdp[k].grup_dugumu_mu]
        if vatandas:
            vat = [k for k in kodlar if k.vatandas_konusu]
            return vat or kodlar
        return kodlar

    def _birim_sec(self, kurum: Kurum, s: Siparis) -> Birim:
        """Birimi KAPASİTEYE göre seçer, yüke göre değil.

        Ölçülen sorun: bazı birimlerin çok az kullanılabilir SDP kodu var
        (İl MEM'de bir şube müdürlüğünün tek kodu bulunuyor). Yalnızca "en az
        yüklü birim" kuralıyla seçilirse o birime 14 belge düşer, tek kod 14
        kez kullanılır ve çeşitlilik tavanı (6) aşılır.

        Çözüm: doymamış kodu kalan birimler arasından, yük/kapasite oranı en
        düşük olanı seçmek. Kapasite = kullanılabilir kod sayısı x kod tavanı.

        YEDEKLEME ZİNCİRİ üç kademeli. Tek kademeli olsaydı, vatandaş yoğun
        birimlerin kodları dolduğunda tavan sessizce aşılırdı — ölçülen
        davranış buydu.
        """
        vatandas = s.gonderen_tipi in ("vatandas", "ozel_tuzel")
        hepsi = kurum.alici_birimler
        # İşbirliği talebinde ortak iş kodu olan birimlere DOYMA
        # FİLTRESİNDEN ÖNCE daral. Sonra daraltılırsa, o birimlerin kodları
        # doyduğunda yedekleme devreye girip beyaz liste dışına çıkıyordu.
        if self._isbirligi_mi(s):
            ortak = [b for b in hepsi
                     if _ISBIRLIGI_YAPRAK & set(b.sdp_kodlari)]
            hepsi = ortak or hepsi

        def bosluk_var_mi(b: Birim, vat: bool) -> bool:
            return any(self.kod_sayaci[k.kod] < self.kod_azami
                       for k in self._kullanilabilir_kodlar(b, vat))

        # 1. kademe: gönderen tipiyle uyumlu VE doymamış kodu olan birimler.
        #
        # birimler.csv'deki tipik_muhataplar sütunu bu birimin kimlerle
        # yazıştığını söylüyor; kullanılmazsa gerçek dışı çiftler doğuyor.
        # Ölçülen örnekler: yapı denetim firmasının Temel Eğitim Şubesine
        # diploma teyidi yazması, inşaat şirketinin Okul Aile Birlikleri
        # verisi istemesi.
        uyumlu = _MUHATAP_ESLEME.get(s.gonderen_tipi, set())
        aday_havuz = [b for b in hepsi if uyumlu & set(b.tipik_muhataplar)] or hepsi

        if s.gonderen_tipi == "vatandas":
            yogun = [b for b in aday_havuz
                     if b.vatandas_yogunlugu in ("yuksek", "orta")]
            adaylar = [b for b in yogun if bosluk_var_mi(b, True)]
        else:
            adaylar = [b for b in aday_havuz if bosluk_var_mi(b, vatandas)]

        # 2. kademe: kurumun bütün birimleri, doymamış kodla
        if not adaylar:
            adaylar = [b for b in hepsi if bosluk_var_mi(b, vatandas)]
        # 3. kademe: vatandaş filtresini de bırak
        if not adaylar:
            adaylar = [b for b in hepsi if bosluk_var_mi(b, False)]
        # Son çare: tavan aşılacak, ama sessizce değil
        if not adaylar:
            self.tavan_asimi += 1
            adaylar = hepsi

        # Aynı SDP kodu birden fazla birimde olabilir. Ölçülen örnek: 170.01
        # (Ruhsat) hem Zabıta hem Ruhsat ve Denetim Müdürlüğü'nde. Ruhsat
        # DEVRİ talebi Zabıta'ya gitmez — zabıta denetler, ruhsat düzenlemez.
        # Talep/başvuru DÜZENLEYEN birime, şikâyet/ihbar DENETLEYEN birime.
        if s.belge_turu in ("sikayet", "itiraz"):
            denetim = [b for b in adaylar if _DENETIM_BIRIMI.search(b.birim_adi)]
            adaylar = denetim or adaylar
        elif s.belge_turu in ("dilekce", "talep_yazisi", "cevap_yazisi"):
            duzenleyen = [b for b in adaylar
                          if not _DENETIM_BIRIMI.search(b.birim_adi)]
            adaylar = duzenleyen or adaylar

        def oran(b: Birim) -> float:
            kapasite = len(self._kullanilabilir_kodlar(b, vatandas)) * self.kod_azami
            return self.birim_sayaci[b.birim_kodu] / max(1, kapasite)

        return min(adaylar, key=lambda b: (oran(b), self.h.rnd.random()))

    def _kod_sec(self, birim: Birim, s: Siparis) -> SdpKodu:
        vatandas = s.gonderen_tipi in ("vatandas", "ozel_tuzel")
        adaylar = self._kullanilabilir_kodlar(birim, vatandas)
        if self._isbirligi_mi(s):
            ortak = [k for k in adaylar if k.kod in _ISBIRLIGI_KODLARI]
            adaylar = ortak or adaylar
        else:
            # REZERVASYON: beyaz liste kodları (802, 773, 045.02 gibi ortak
            # kodlar) başka belge türleri tarafından tüketilirse işbirliği
            # talebine yer kalmıyor ve yedekleme beyaz listenin dışına
            # çıkıyordu. Diğer türler bu kodları SON tercih olarak kullanır.
            digerleri = [k for k in adaylar if k.kod not in _ISBIRLIGI_KODLARI]
            adaylar = digerleri or adaylar
        if not adaylar:
            raise RuntimeError(f"{birim.birim_kodu} icin kullanilabilir SDP kodu yok")
        doymamis = [k for k in adaylar if self.kod_sayaci[k.kod] < self.kod_azami]
        if not doymamis:
            # Vatandaş filtresi yüzünden doymuş olabilir; tüm kodlara bak.
            # İŞBİRLİĞİ FİLTRESİ BURADA DA GEÇERLİ — yoksa yedekleme beyaz
            # listenin dışına çıkıyordu (ölçüm: 7 belge).
            tumu = self._kullanilabilir_kodlar(birim, False)
            if self._isbirligi_mi(s):
                tumu = [k for k in tumu if k.kod in _ISBIRLIGI_KODLARI] or tumu
            doymamis = [k for k in tumu if self.kod_sayaci[k.kod] < self.kod_azami]
        adaylar = doymamis or adaylar
        return min(adaylar, key=lambda k: (self.kod_sayaci[k.kod], self.h.rnd.random()))

    def _konu_sec(self, kod: SdpKodu, belge_turu: str) -> str:
        """Konuyu belge TÜRÜNE uygun seçer.

        Ölçülen sorun: örnek konular tür bilgisi taşıyor ("... Talebi",
        "... Şikayeti", "... Hk.") ama seçim buna bakmıyordu. Sonuç:
        belge_turu=dilekce olan bir belgeye "Hafriyat Atığı Şikayeti"
        konusu düşüyordu. Etiket kendi içinde çelişince ölçüm bozulur.
        """
        adaylar = kod.ornek_konular
        # Vatandaş "Tadilat Talebinin Değerlendirilmesi" diye dilekçe yazmaz.
        # "Değerlendirilmesi", "Gönderilmesi", "Duyurulması" kurumun kendi iç
        # yazışma dilidir. Konu havuzunda ağız etiketi yok; son ekten ayırıyoruz.
        if belge_turu in ("dilekce", "sikayet", "itiraz", "bilgi_edinme"):
            dis = [k for k in adaylar if not _KURUM_AGZI_KONU.search(k)]
            adaylar = dis or adaylar

        desen = _TUR_KONU_DESENI.get(belge_turu)
        uygun = [k for k in adaylar if desen.search(k)] if desen else []

        # Yedekleme sırası: TÜR UYUMU çeşitlilikten önce gelir. Türle uyumsuz
        # bir konu etiketi kendi içinde çelişkili yapar (dilekçe belgesine
        # şikâyet konusu); konunun bir kez fazla tekrarlanması ise yalnızca
        # çeşitliliği bir tık düşürür.
        # 1. Türle uyumlu ve doymamış bir örnek konu varsa onu kullan.
        #    Bunlar insan yazımı, en doğal görünenler.
        doymamis = [k for k in uygun if self.konu_sayaci[k] < self.konu_azami]
        if doymamis:
            return min(doymamis, key=lambda k: (self.konu_sayaci[k], self.h.rnd.random()))

        # 2. Türle uyumlu kalmadıysa kodun DİĞER konularına düş.
        #    Kod başına artık 6-7 konu var ve çoğu nötr isim tamlaması
        #    ("Muayene ve Kabul İşlemleri"), her türe oturuyor. Kod adından
        #    türetmek ise yapay başlık üretiyordu ("Mal Alım İşi Hk.").
        digerleri = [k for k in adaylar
                     if self.konu_sayaci[k] < self.konu_azami]
        if digerleri:
            return min(digerleri,
                       key=lambda k: (self.konu_sayaci[k], self.h.rnd.random()))

        # 3. Son çare: kod adından türet. 6-7 konunun hepsi doyduysa.
        for i in range(12):
            t = _konu_turet(kod.ad, belge_turu, i)
            if self.konu_sayaci[t] < self.konu_azami:
                return t
        return _konu_turet(kod.ad, belge_turu, 0)

    # -- tarih ve sayı -------------------------------------------------------

    def _tarih_sec(self, kota: dict) -> date:
        bas = datetime.fromisoformat(kota["tarih_araligi"]["baslangic"]).date()
        bit = datetime.fromisoformat(kota["tarih_araligi"]["bitis"]).date()
        for _ in range(200):
            t = self.h.is_gunu(bas, bit)
            if self.gun_sayaci[t] < self.gun_azami:
                self.gun_sayaci[t] += 1
                return t
        return self.h.is_gunu(bas, bit)

    def _dagitim_listesi(self, kurum: Kurum, gonderen_adi: str,
                         alici_tipi: str) -> dict:
        """Dağıtımlı yazının muhatap listesi — gereği / bilgi ayrımlı.

        ÜÇ ÖLÇÜLEN HATA DÜZELTİLDİ:

        1. Gönderen kendi dağıtımında yer alıyordu. Bir yazı kendi
           dağıtımına kendini yazmaz.
        2. Dağıtım kurum sınırını atlıyordu: YÖK, Gazi'nin fakültelerine
           DOĞRUDAN dağıtım yapmaz — Rektörlüğe yazar, Rektörlük içeride
           dağıtır. Dış kurumun dağıtımı tüzel kişilik düzeyindedir.
        3. Karma kapanış gerekçesizdi. "arz/rica ederim" ancak yazı hem
           ÜST hem AST makamlara gidiyorsa kullanılır.

        Gerçek örnek dayanağı: İŞKUR yazısında "Dağıtım: Üniversite
        Rektörlüklerine", İçişleri yazısında "Gereği: ... Bilgi: 81 İl
        Valiliğine".
        """
        # Dağıtım muhatapları RASTGELE kurum değil, gönderenin kendi
        # kolektif dağıtım kümesidir. Ölçülen hata: YÖK'ün sınav duyurusu
        # dağıtımında "Ankara Valiliği" görünüyordu — YÖK valiliğe sınav
        # duyurusu dağıtmaz.
        # Dağıtım kümesi ALICI KURUM TİPİNİ kapsamalı. Ölçülen hata:
        # Çevre-Şehircilik Bakanlığı belediyeye yazıyordu ama dağıtım
        # ["81 İl Valiliğine", "Çevre ve Şehircilik İl Müdürlüklerine"] idi —
        # belediye hiçbir kalemde yoktu. Bir belediye "81 İl Valiliğine"
        # dağıtımlı bir yazının muhatabı olamaz.
        geregi = _DAGITIM_KUMESI.get((gonderen_adi, alici_tipi)) \
            or _DAGITIM_KUMESI.get(gonderen_adi)
        if geregi is None:
            geregi = [kurum.kurum_adi]
            ayni = [m for m in kurum.hiyerarsi.get("ayni_duzey", [])
                    if m != gonderen_adi]
            geregi += self.h.karistir(ayni)[:1]
        bilgi = _DAGITIM_BILGI.get(gonderen_adi, [])
        # Bilgi kopyası gerçek bir üst/dış makama mı gidiyor?
        ust_var = any(b not in _KENDI_ORGANI.get(gonderen_adi, []) for b in bilgi)
        return {"geregi": geregi, "bilgi": bilgi, "ust_makam_var": ust_var}

    def _somut_makam(self, kurum: Kurum, makam: str, alici_birim: Birim) -> str:
        """Çoğul makam tanımını somut bir birime çevirir.

        kurum.json'daki alt_makamlar listesi TANIM içerir, ad değil:
            "Yenimahalle Belediyesi müdürlükleri"
            "Okul ve kurum müdürlükleri"
            "Gazi Üniversitesi fakülte, enstitü, yüksekokul ve daire başkanlıkları"

        Bir belge "müdürlükler"den gelmez, BELİRLİ BİR müdürlükten gelir.
        Çoğul tanım gönderen adı olarak kalırsa belge gerçek dışı görünür ve
        muhatap satırı kurulamaz.

        Kurum içi birimler birimler.csv'den seçilir (alıcının kendisi hariç).
        Okul gibi veri setimizde bulunmayan birimler için ad üretilir.
        """
        if makam not in _COGUL_MAKAM:
            return makam
        tip = _COGUL_MAKAM[makam]
        if tip == "kurum_ici":
            adaylar = [b for b in kurum.birimler
                       if b.seviye == 2 and b.birim_kodu != alici_birim.birim_kodu]
            if adaylar:
                return self.h.sec(adaylar).birim_adi
            return kurum.kurum_adi
        if tip == "okul":
            # KURGUSAL ad. Gerçek mahalle adı kullanılırsa (Şentepe, Ergazi)
            # o mahallede gerçekten var olan bir okulla çakışma riski doğar.
            return (f"{self.h.sec(_KURGUSAL_OKUL_ADI)} "
                    f"{self.h.sec(['İlkokulu', 'Ortaokulu', 'Anadolu Lisesi', 'Mesleki ve Teknik Anadolu Lisesi'])} "
                    f"Müdürlüğü")
        if tip == "ilce_mem":
            adaylar = [b for b in kurum.birimler if "İlçe" in b.birim_adi]
            if adaylar:
                return self.h.sec(adaylar).birim_adi
        return makam

    def _gonderen_detsis(self, alici: Kurum, makam: str) -> tuple[str, str]:
        """Gönderen makamın DETSİS numarasını bulur.

        Üç kaynak, sırayla:
          1. Alıcının muhatap_detsis kaydı (Valilik, Kaymakamlık, ABB...)
          2. Alıcının kendi birimleri (kurum içi yazışma)
          3. Üretilmiş numara — DETSİS'te sorgulanmamış makamlar için
             (YÖK, MEB, İçişleri Bakanlığı, okullar...)

        3. durumda etikete 'sentetik' işareti konur. Gerçek numara
         sonradan bulunursa hangi belgelerin etkileneceği bilinsin.
        """
        if makam in self._defter:
            return self._defter[makam], "detsis"
        if makam not in self._sentetik_detsis:
            # Ada göre sabit: aynı makam hep aynı numarayı alır
            tohum = sum(ord(c) * (i + 7) for i, c in enumerate(makam))
            self._sentetik_detsis[makam] = str(10_000_000 + tohum % 89_999_999)
        return self._sentetik_detsis[makam], "sentetik"

    def _kayit_no(self, detsis: str, tarih: date, olcek: str = "orta") -> str:
        """Kayıt numarası TARİHTEN ve KURUM ÖLÇEĞİNDEN türetilir.

        İki ayrı hata düzeltildi:
          1. Sıra bozuluyordu (68 kez) — artık tarihe bağlı, monoton.
          2. Ölçek yok sayılıyordu. YÖK 444/gün, il müdürlüğü 726/gün
             çıkıyordu; YÖK bütün üniversitelerle yazışır, daha yavaş
             olamaz. Bir lise ise 7 milyonuncu evrakını çıkarıyordu —
             bin yıllık faaliyet demek.

        Gerçek ölçüm dayanağı: Gazi Ü. Teknoloji Fakültesi 33 günde
        24.159 evrak (~730/gün) ve bu tek bir fakülte.
        """
        alt, ust, taban_alt, taban_ust = _OLCEK[olcek]
        if detsis not in self._kayit_taban:
            self._kayit_taban[detsis] = self.h.rnd.randint(taban_alt, taban_ust)
            self._kayit_hiz[detsis] = self.h.rnd.randint(alt, ust)
        gun = (tarih - self._ilk_tarih).days
        sapma = self.h.rnd.randint(0, max(1, self._kayit_hiz[detsis] // 3))
        return str(self._kayit_taban[detsis] + gun * self._kayit_hiz[detsis] + sapma)

    def _ozel_evrak_no(self, sirket: str, tarih: date) -> str:
        """Özel şirketin kendi evrak numarası — yıl/sıra.

        Ölçülen hata: numaralar tarihten bağımsız rastgeleydi; ocak
        tarihli yazı 2026/8153, mayıs tarihli 2026/210 çıkıyordu. Bir
        Ltd. Şti. yılın 23. gününde 8153. evrakını çıkarmaz.
        """
        if sirket not in self._sirket_taban:
            self._sirket_taban[sirket] = self.h.rnd.randint(5, 60)
            self._sirket_hiz[sirket] = self.h.rnd.uniform(1.5, 8.0)
        gun = (tarih - self._ilk_tarih).days
        no = self._sirket_taban[sirket] + int(gun * self._sirket_hiz[sirket])
        return f"{tarih.year}/{no}"

    # -- somut bilgiler ------------------------------------------------------

    def _somut_bilgiler(self, aile: str, kurum: Kurum, birim: Birim,
                        kod: SdpKodu, konu: str, s: Siparis) -> dict:
        """Belgenin içini dolduran değerler.

        Bunlar etiketin parçası ve aynı zamanda modele verilecek şartnamenin
        'Somut bilgiler' bölümü. Model bunların DIŞINA çıkamaz — ADIM 1'de
        ölçüldü: malzeme verilmezse model uyduruyor.
        """
        h = self.h
        kurum_soz = {"belediye": "Müdürlüğümüz", "universite": "Başkanlığımız",
                     "il_mudurlugu": "Müdürlüğümüz"}[kurum.kurum_tipi]

        if aile == "belge_talebi":
            b = {"Talep": _talep_ifadesi(konu, kod.ad)}
            if _tasinmaz_konusu_mu(kod.kod, konu):
                ada, parsel = h.ada_parsel()
                b["Taşınmaz"] = f"{ada} ada, {parsel} parsel"
            elif kod.kod[:3] in _OGRENCI_ANA_GRUP:
                b["Öğrenim bilgisi"] = h.sec([
                    f"{h.rnd.randint(2016, 2025)} yılı mezunu",
                    f"{h.rnd.choice(['1','2','3','4'])}. sınıf öğrencisi",
                    "lisansüstü programa kayıtlı"])
            # "Kullanım amacı" YALNIZCA bir belge/suret talebinde anlamlı.
            # Ölçülen hata: kamulaştırma bedeli ödeme, borç yapılandırma ve
            # taşımalı eğitim taleplerine de ekleniyordu; oralarda saçmalıyor.
            if _BELGE_TALEBI_MI.search(konu):
                b["Kullanım amacı"] = h.sec(["resmî işlemlerde kullanılmak üzere",
                                             "ilgili kuruma sunulmak üzere",
                                             "başvuru dosyasına eklenmek üzere"])
            else:
                b["Gerekçe"] = h.sec([
                    "mağduriyetin giderilmesi bakımından",
                    "sürecin tamamlanabilmesi için",
                    "mevzuatta öngörülen şartların sağlanması nedeniyle"])
            return b

        if aile == "belge_cevabi":
            b = {"Talep": _talep_ifadesi(konu, kod.ad),
                 "Talebin sonucu": h.sec(["olumlu, işlem tamamlandı",
                                          "olumlu, talep karşılandı",
                                          "olumlu, belge düzenlendi"])}
            if _tasinmaz_konusu_mu(kod.kod):
                ada, parsel = h.ada_parsel()
                b["Taşınmaz"] = f"{ada} ada, {parsel} parsel"
            # Teslim yeri / teslim şartı / geçerlilik alanları VATANDAŞA
            # verilen belge için yazılmıştır. Bir okul, il müdürlüğüne
            # "kimlik ibrazıyla gelin" demez.
            if s.gonderen_tipi in ("vatandas", "ozel_tuzel"):
                b["Teslim yeri"] = f"{kurum_soz} kayıt bürosu"
                b["Teslim şartı"] = h.teslim_sarti()
                b["Geçerlilik"] = h.gecerlilik()
            else:
                b["Dayanak"] = "ilgide kayıtlı yazı"
                b["Gönderilen"] = h.sec([
                    "talep edilen bilgiler ekte sunulmuştur",
                    "konuya ilişkin değerlendirme aşağıda yer almaktadır",
                    "istenen kayıtlar tarafımızca derlenmiştir"])
                b["Ek bilgi"] = h.sec([
                    "ihtiyaç duyulması hâlinde ayrıntılı döküm gönderilebilir",
                    "konuyla ilgili irtibat kişisi Müdürlüğümüzde görevlidir",
                    "süreç Müdürlüğümüzce takip edilmektedir"])
            return b

        if aile == "itiraz":
            return {"İtiraz konusu": _talep_ifadesi(konu, kod.ad),
                    "Önceki karar": "talep olumsuz sonuçlandırılmıştır",
                    "İtiraz gerekçesi": h.sec([
                        "değerlendirmede eksik belge dikkate alınmıştır",
                        "başvuru dosyasındaki bilgiler güncellenmiştir",
                        "benzer başvurular olumlu sonuçlandırılmıştır"]),
                    "Talep": "kararın yeniden değerlendirilmesi"}

        if aile == "sikayet":
            # Şikâyet konusu ALICI KURUMUN görev alanından olmalı. Ölçülen
            # hata: "kaldırım işgali" şikâyeti üniversiteye yazılmıştı;
            # kaldırım belediyenin işidir, üniversiteye yazılmaz.
            return {"Şikâyet konusu": _talep_ifadesi(konu, kod.ad),
                    "Sorun": h.sec(_sikayet_sorunu(kod, kurum.kurum_tipi)),
                    "Süre": h.sikayet_suresi(),
                    "Önceki başvuru": h.onceki_basvuru(),
                    "Talep": "sorunun giderilmesi",
                    # Yer alanı YALNIZCA fiziksel mekân şikâyetlerinde.
                    # Katkı payı veya belge talebi bir idari işlemdir;
                    # fiziksel bir mekânda geçmez.
                    **({"Yer": _sikayet_yeri(h, kurum.kurum_tipi)}
                       if kod.kod[:3] in _FIZIKSEL_MEKAN else {})}

        if aile == "bilgi_edinme":
            # Talep KONUDAN türetilir, kod adından değil. Ölçülen hata:
            # konu "Salon Tahsis Talebi" iken gövde "Öğrenci Toplulukları,
            # Birlikleri vb. konusundaki güncel verilerin paylaşılması"
            # diyordu — konu bireysel işlem, gövde istatistik istiyordu.
            return {"Dayanak": "4982 sayılı Bilgi Edinme Hakkı Kanunu",
                    "Talep": f"{_talep_ifadesi(konu, kod.ad)} işlemlerine "
                             f"ilişkin güncel bilgilerin paylaşılması",
                    "İstenen ayrıntı": h.sec([
                        "yıllara göre sayısal döküm",
                        "işlem sayısı ve ortalama sonuçlanma süresi",
                        "konuya ilişkin yürürlükteki uygulama esasları"]),
                    "Bildirim yolu": h.bildirim_yolu()}

        if aile == "kaynak_talebi":
            return {"Mevcut durum": f"{kod.ad} kapsamındaki iş yükü artmıştır",
                    "Sonuç": h.sec(["mevcut kaynaklar yetersiz kalmaktadır",
                                    "işlemler öngörülen sürede tamamlanamamaktadır",
                                    "ek kapasiteye ihtiyaç duyulmaktadır"]),
                    "Amaç": h.gerekce(),
                    "Talep": h.sec(["gerekli ödeneğin tahsis edilmesi",
                                    "ilave personel görevlendirilmesi",
                                    "teknik destek sağlanması"])}

        if aile == "bilgilendirme":
            return {"Konu": f"{kod.ad} kapsamında yeni bir uygulama yürürlüğe girmiştir",
                    "Kaynak": h.sec(["uygulama Bakanlıkça yürürlüğe konulmuştur",
                                     "karar Makam onayı ile yürürlüğe girmiştir",
                                     "düzenleme ilgili mevzuat gereği yapılmıştır"]),
                    "Kapsam": "bağlı tüm birimler uygulamaya tabidir",
                    "İstenen 1": "uygulamanın ilgililere duyurulması",
                    "İstenen 2": f"sonuçların {_donem(h, kurum.kurum_tipi)} sonunda bildirilmesi"}

        if aile == "isbirligi_talebi":
            # Talep KONUDAN türetilir. Ölçülen hata: konu "Hukuki Görüş
            # Talebi" iken gövdede "iş birliği protokolü düzenlenmesi"
            # isteniyordu; konu ile gövde birbirini tutmuyordu.
            iş = _talep_ifadesi(konu, kod.ad)
            return {"Konu": iş,
                    "Ortak iş": f"{iş} konusunda iki kurumun ortak yürüttüğü işlem",
                    "Talep": _isbirligi_talebi(konu, iş)}

        if aile == "gorus_talebi":
            return {"Konu": kod.ad,
                    "Tereddüt": h.sec([
                        "uygulamada hangi usulün izleneceği açık değildir",
                        "iki farklı düzenleme arasında tereddüt oluşmuştur",
                        "istisna hükmünün kapsamı netleştirilememiştir"]),
                    "Talep": "konu hakkında görüş bildirilmesi"}

        if aile == "ust_yazi":
            n = h.kisi_sayisi()
            return {"Dayanak": "ilgide kayıtlı yazı",
                    "Dönem": _donem(h, kurum.kurum_tipi),
                    "Sayı": f"{n} kayıt",
                    "Ek 1": f"{kod.ad} listesi",
                    "Ek 2": "uygulama takvimi",
                    "İstenen": "listenin ilgili birimlere dağıtılması"}

        if aile == "tekit":
            return {"Dayanak": "ilgide kayıtlı yazı",
                    "Durum": "talep edilen bilgi henüz gönderilmemiştir",
                    "Talep": "ivedilikle gönderilmesi",
                    "Süre": h.sec(["beş iş günü içinde", "en geç bir hafta içinde",
                                   "ay sonuna kadar"])}

        if aile == "olur":
            return {"Konu": kod.ad,
                    "Gerekçe": h.gerekce(),
                    "Talep": "konunun uygun görülmesi hâlinde olur verilmesi"}

        raise ValueError(f"Bilinmeyen aile: {aile}")

    # -- ana dönüşüm ---------------------------------------------------------

    def uret(self, no: int, s: Siparis) -> dict:
        h, kota = self.h, self.v.kota
        kurum = self.v.kurumlar[s.kurum_kodu]
        birim = self._birim_sec(kurum, s)
        kod = self._kod_sec(birim, s)
        konu = self._konu_sec(kod, s.belge_turu)
        aile = _AILE[s.belge_turu]
        tarih = self._tarih_sec(kota)

        self.birim_sayaci[birim.birim_kodu] += 1
        self.kod_sayaci[kod.kod] += 1
        self.konu_sayaci[konu] += 1

        vatandas_yazari = s.gonderen_tipi == "vatandas"
        kisi = h.kisi() if vatandas_yazari else None
        # Üniversiteye yemekhane/derslik şikâyetini sıradan bir vatandaş değil,
        # KAYITLI ÖĞRENCİ yapar. Dilekçesinde öğrenci numarası, bölüm ve sınıf
        # bulunur; vatandaşın bu konuda dilekçe verme sıfatı yoktur.
        ogrenci = (vatandas_yazari and kurum.kurum_tipi == "universite"
                   and s.belge_turu in ("sikayet", "dilekce", "itiraz"))

        # --- gönderen ------------------------------------------------------
        if vatandas_yazari:
            gonderen = {"tip": "ogrenci" if ogrenci else "gercek_kisi",
                        "ad": kisi.tam_ad, "adres": h.adres(),
                        "kurum_adi": None, "detsis_no": None}
            if ogrenci:
                gonderen["ogrenci_no"] = str(h.rnd.randint(2019, 2025)) + \
                    str(h.rnd.randint(100000, 999999))
                # Bölüm ALICI BİRİME bağlı olmalı. Ölçülen hata: Teknoloji
                # Fakültesi öğrencisinin dilekçesi Gazi Eğitim Fakültesi
                # Dekanlığına gidiyordu.
                gonderen["bolum"] = _bolum_sec(h, birim.birim_adi)
                # Kod bazlı asgari sınıf. Staj için en az 3. sınıf, değişim
                # programı ve yatay geçiş için en az 2 (bir dönem öğrenim
                # şartı), mezuniyet işlemleri için 4. Ölçülen hata: 1. sınıf
                # öğrencisi değişim programından dönmüş ve hibe bekliyordu.
                alt = _ASGARI_SINIF.get(kod.kod, 1)
                if re.search(r"staj", konu, re.I):
                    alt = max(alt, 3)
                gonderen["sinif"] = str(h.rnd.randint(alt, 4))
        elif s.gonderen_tipi == "ozel_tuzel":
            # Özel hukuk tüzel kişileri DETSİS'te kayıtlı değildir; yazılarında
            # E- önekli devlet sayısı bulunmaz, kendi evrak numaralarını taşırlar.
            # Şirketin SEKTÖRÜ konuya uymalı. Ölçülen hata: inşaat şirketi
            # özel öğretim CİMER istatistiği, turizm şirketi öğrenci kayıt
            # verisi istiyordu.
            gonderen = {"tip": "ozel_tuzel_kisi",
                        "kurum_adi": f"{h.sec(_SIRKET_ONEK)} "
                                     f"{h.sec(_sirket_turu(kod.kod))}",
                        "ad": None, "adres": h.adres(), "detsis_no": None,
                        "detsis_kaynagi": "yok"}
        else:
            makam_listesi = {
                "ust_makam": kurum.hiyerarsi.get("ust_makamlar", []),
                "ayni_duzey": kurum.hiyerarsi.get("ayni_duzey", []),
                "alt_makam": kurum.hiyerarsi.get("alt_makamlar", []),
            }[s.gonderen_tipi]
            makam = h.sec(makam_listesi) if makam_listesi else kurum.kurum_adi
            makam = self._somut_makam(kurum, makam, birim)
            g_detsis, g_kaynak = self._gonderen_detsis(kurum, makam)
            gonderen = {"tip": "kurum", "kurum_adi": makam, "ad": None,
                        "adres": None, "detsis_no": g_detsis,
                        "detsis_kaynagi": g_kaynak}

        # --- hiyerarşi yönü düzeltmesi -------------------------------------
        # Kota "alt_makam" dediğinde gönderen somut bir birime çevriliyor.
        # O birim alıcıyla AYNI kurumun AYNI seviyesindeyse aralarında
        # hiyerarşi yoktur — "üst" etiketi cevap anahtarını yanlış yapar.
        # Ölçüm: 32 belgede müdürlükten müdürlüğe yazışma "ust" yazılmıştı.
        yon = _YON[s.gonderen_tipi]
        if gonderen["tip"] == "kurum":
            ic = next((b for b in kurum.birimler
                       if b.birim_adi == gonderen["kurum_adi"]), None)
            # İlçe müdürlüğü ve okul, kurumun İÇ BİRİMİ değil AST KURULUŞUDUR.
            # birimler.csv'de aynı seviyede görünüyorlar ama DETSİS hiyerarşisi
            # "İl MEM > İlçe MEM" diyor. Seviye eşitliğine bakıp "ayni"
            # demek cevap anahtarını bozuyordu.
            ast_kurulus = _AST_KURULUS.search(gonderen["kurum_adi"] or "")
            if ic is not None and ic.seviye == birim.seviye and not ast_kurulus:
                yon = "ayni"

        # Ödenek ve personel talebi yalnızca HİYERARŞİK ÜSTTEN istenir.
        # Eşit düzeydeki ayrı tüzel kişiye "ödenek tahsis edin" yazmak hem
        # hukuken hem anlamca geçersiz. Aynı düzey için işbirliği ailesi.
        if aile == "kaynak_talebi" and yon != "ust":
            aile = "isbirligi_talebi"

        # --- muhatap makamı -------------------------------------------------
        # Gerçek yazışmada muhatap TÜZEL KİŞİLİKTİR; dış kurum bir belediyenin
        # iç müdürlüğüne yazmaz, belediye başkanlığına yazar ve evrak içeride
        # havale edilir. birim_kodu havale hedefi olarak kalıyor — sistemin
        # "bu evrak hangi birime düşmeli" görevini test etmek için değerli.
        dis_gonderen = gonderen["tip"] != "kurum" or (
            not any(b.birim_adi == gonderen["kurum_adi"] for b in kurum.birimler))
        # İlçe müdürlüğü KENDİ BAŞLIK BLOĞUNA sahip ayrı bir muhataptır
        # (kurum_ilmem.json > baslik_bloku_ilce). Hem dışarıdan hem il
        # müdürlüğünden yazılırken muhatap kaymakamlıktır — ilçe müdürlüğü
        # il müdürlüğünün iç birimi değil, ayrı bir taşra teşkilatıdır.
        ilce = _ILCE_MUHATAP.get(birim.birim_kodu)
        if ilce:
            muhatap_makam, muhatap_parantez = ilce
        elif dis_gonderen:
            muhatap_makam = kurum.kurum_adi
            muhatap_parantez = birim.birim_adi if birim.seviye == 2 else None
        else:
            muhatap_makam = birim.birim_adi
            muhatap_parantez = None

        # --- kapanış -------------------------------------------------------
        # K 13.1: "arz/rica ederim" YALNIZCA dağıtımlı yazılarda kullanılır
        # (aynı yazı hem üst hem ast makamlara gidiyorsa). Tek muhataplı bir
        # yazıda kullanılamaz. Dağıtım listesi kurulmazsa karma kapanış
        # geçersizdir; bu yüzden liste burada üretiliyor.
        dagitim = None
        if s.karma_kapanis:
            dagitim = self._dagitim_listesi(kurum, gonderen["kurum_adi"] or "",
                                            kurum.kurum_tipi)
            # KARMA ancak "bilgi" listesindeki makam gönderene göre GERÇEK BİR
            # ÜST veya DIŞ KURUM ise geçerli. Kurumun kendi organına bilgi
            # göndermek arz yönü yaratmaz — Yükseköğretim Denetleme Kurulu
            # YÖK'ün üstü değil, kendi organıdır (2547 s. Kanun m.8).
            kapanis = "karma" if dagitim.get("ust_makam_var") else "rica"
            dagitim.pop("ust_makam_var", None)
            # Dağıtımlı yazının TEKİL MUHATABI OLMAZ. Hitap satırı
            # "DAĞITIM YERLERİNE" olur; 19 gerçek yazının dağıtımlı
            # olanlarının tamamında böyle. Alıcı birim `alici` bloğunda
            # havale hedefi olarak zaten duruyor.
            muhatap_makam = "DAĞITIM YERLERİNE"
            muhatap_parantez = None
        elif vatandas_yazari or s.gonderen_tipi == "ozel_tuzel":
            kapanis = "arz"
        else:
            kapanis = kota["kapanis_kurali"][s.gonderen_tipi]

        # --- sayı ----------------------------------------------------------
        # Dilekçede sayı, başlık bloğu ve konu satırı YOKTUR (belge_sablonu.json).
        if vatandas_yazari:
            sayi = None
        elif s.gonderen_tipi == "ozel_tuzel":
            sayi = self._ozel_evrak_no(gonderen["kurum_adi"], tarih)
        else:
            # Gelen belgenin sayısı GÖNDERENİN numarasını taşır. Alıcının
            # numarasına düşmek belgeyi kendi kendine gönderilmiş gösterir.
            kaynak_detsis = gonderen["detsis_no"]
            olcek = _olcek_bul(gonderen["kurum_adi"] or "", kurum.kurum_tipi)
            sayi = f"E-{kaynak_detsis}-{kod.kod}-{self._kayit_no(kaynak_detsis, tarih, olcek)}"

        # --- ilgi ----------------------------------------------------------
        ilgi = None
        if s.ilgi_var:
            it = h.onceki_is_gunu(tarih)
            # İlgi yazısını ALICI BİRİM göndermişti; ilgi sayısı o birimin
            # DETSİS numarasını taşır, kurumun kök numarasını değil.
            ilgi_detsis = birim.detsis_no or kurum.detsis_no
            ilgi = {"tarih": it.strftime("%d.%m.%Y"),
                    "sayi": f"E-{ilgi_detsis}-{kod.kod}-{self._kayit_no(ilgi_detsis, it, _olcek_bul(birim.birim_adi, kurum.kurum_tipi))}"}

        # --- ek ------------------------------------------------------------
        ek = None
        if s.ek_var:
            ek = {"adet": 1 if aile != "ust_yazi" else 2,
                  "aciklama": _EK_ACIKLAMA.get(aile, "İlgili belge"),
                  "sayfa": h.sayfa_sayisi()}

        somut = self._somut_bilgiler(aile, kurum, birim, kod, konu, s)

        # --- linter için ---------------------------------------------------
        yasakli = [kurum.kurum_adi, birim.birim_adi]
        if kurum.kurum_tipi == "belediye":
            yasakli.append("Yenimahalle")
        elif kurum.kurum_tipi == "universite":
            yasakli += ["Gazi Üniversitesi", "Gazi"]
        else:
            yasakli.append("Ankara İl Millî Eğitim Müdürlüğü")

        return {
            "belge_no": f"{no:03d}",
            "tohum": kota["tohum"],
            "alici": {"kurum_kodu": kurum.kurum_kodu, "kurum_adi": kurum.kurum_adi,
                      "kurum_tipi": kurum.kurum_tipi, "birim_kodu": birim.birim_kodu,
                      "birim_adi": birim.birim_adi, "detsis_no": birim.detsis_no,
                      "imza_unvani": birim.imza_unvani},
            "gonderen": gonderen,
            "belge_turu": s.belge_turu,
            "aile": aile,
            # yazan_tipi ÜÇ değer alır: kurum | vatandas | ogrenci.
            # Önce iki değerliydi ve gonderen.tip="ogrenci" ile çelişiyordu;
            # hangisinin cevap anahtarı olduğu belirsiz kalıyordu.
            # Linter açısından ogrenci de vatandaş kaydında yazar (birinci
            # tekil şahıs serbest), ama gönderen sıfatı farklıdır.
            "yazan_tipi": ("ogrenci" if ogrenci
                           else "vatandas" if vatandas_yazari else "kurum"),
            "hiyerarsi_yonu": yon,
            "muhatap_makam": muhatap_makam,
            "muhatap_parantez": muhatap_parantez,
            "dagitim": dagitim,
            "beklenen_kapanis": kapanis,
            "sdp": {"kod": kod.kod, "ad": kod.ad, "saklama_suresi": kod.saklama_suresi},
            "konu": konu,
            "sayi": sayi,
            "tarih": tarih.strftime("%d.%m.%Y"),
            "ilgi": ilgi,
            "ek": ek,
            "somut_bilgiler": somut,
            "paragraf_cumle_sayilari": _PARAGRAF[aile],
            "pdf_bicimi": s.pdf_bicimi,
            "kusur": s.kusur,
            "yasakli_adlar": yasakli,
            "anahtar_terimler": _anahtar_terimler(somut),
        }


_SIRKET_ONEK = ["Anadolu", "Başkent", "Öz", "Yıldız", "Ege", "Kuzey", "Merkez",
                "Güven", "Şafak", "Doruk", "Vizyon", "Atlas"]
_SIRKET_TUR = ["İnşaat Ltd. Şti.", "Yapı Denetim A.Ş.", "Mühendislik Ltd. Şti.",
               "Turizm ve Ticaret A.Ş.", "Eğitim Hizmetleri Ltd. Şti."]

_EK_ACIKLAMA = {
    "belge_talebi": "Tapu fotokopisi",
    "itiraz": "Başvuru evrakı",
    "sikayet": "Fotoğraf",
    "belge_cevabi": "Düzenlenen belge",
    "kaynak_talebi": "İhtiyaç listesi",
    "bilgilendirme": "Uygulama esasları",
    "gorus_talebi": "İlgi yazı ve ekleri",
    "ust_yazi": "Liste ve takvim",
    "tekit": "İlgi yazı sureti",
    "olur": "Taslak metin",
}


def _anahtar_terimler(somut: dict) -> list[str]:
    """Linter'ın 'bu bilgi metne girmiş mi' kontrolü için.

    Uzun cümleler değil, AYIRT EDİCİ parçalar alınır: sayı, özel ad, kısa
    isim tamlaması. Uzun bir cümlenin tamamını aramak yanlış alarm verir —
    model aynı bilgiyi başka kelimelerle yazabilir.
    """
    terimler = []
    for deger in somut.values():
        d = str(deger)
        if len(d) <= 40 and " " in d:
            terimler.append(d)
        else:
            # Sayı içeren parçaları çek (ada/parsel, yıl, kayıt sayısı)
            for parca in d.split(","):
                p = parca.strip()
                if any(c.isdigit() for c in p) and len(p) <= 30:
                    terimler.append(p)
    return terimler[:6]


# =============================================================================
# BÖLÜM 4 — KONU YARDIMCILARI
# =============================================================================

# Örnek konu başlıkları belge türünü zaten ele veriyor:
#   "İmar Durum Belgesi Talebi"   -> dilekçe
#   "Hafriyat Atığı Şikayeti"     -> şikâyet
#   "Genelge Duyurusu Hk."        -> bilgilendirme
# Konu seçimi buna bakmazsa etiket kendi içinde çelişir.
_TUR_KONU_DESENI = {
    "dilekce":       re.compile(r"Talebi|Talep|Başvuru|İsteği|Verilmesi|Düzenlen", re.I),
    "sikayet":       re.compile(r"Şikayet|Şikâyet|Aksaklık|Bildirimi|İhbar", re.I),
    "itiraz":        re.compile(r"İtiraz|Yeniden Değerlendir|İtirazı", re.I),
    "bilgi_edinme":  re.compile(r"Bilgi|Talebi|Başvuru", re.I),
    "bilgilendirme": re.compile(r"Duyuru|Bildiril|Hk\.?$|Yayımlan|Uygulama|Genelge", re.I),
    "talep_yazisi":  re.compile(r"Talebi|Talep|İhtiyaç|İstenmesi", re.I),
    "cevap_yazisi":  re.compile(r"Hk\.?$|Bildiril|Gönderil|Cevap|Sonucu", re.I),
    "gorus_talebi":  re.compile(r"Görüş|Mütalaa", re.I),
    "ust_yazi":      re.compile(r"Gönderil|Liste|Takvim|Sunul", re.I),
    "tekit_yazisi":  re.compile(r"Hk\.?$|Talebi|Bildiril|Tekit", re.I),
    "olur_yazisi":   re.compile(r"Olur|Onay|Uygun|Teklifi", re.I),
}

# Örnek konular, hangi belge türüne hizmet edecekleri bilinmeden yazılmıştı;
# ölçümde tür-konu uyumu ancak %56 çıktı. Uyumlu konu yoksa ya da doyduysa
# konu KOD ADINDAN türetiliyor. Bu hem sınırsız çeşitlilik hem tanım gereği
# tür tutarlılığı sağlar.
_TUR_KONU_KALIBI = {
    "dilekce":       ["{a} Talebi", "{a} Düzenlenmesi Talebi", "{a} Hakkında Başvuru"],
    "sikayet":       ["{a} Hakkında Şikâyet", "{a} Konusunda Aksaklık Bildirimi"],
    "itiraz":        ["{a} Kararına İtiraz", "{a} Hakkındaki Karara İtiraz"],
    "bilgi_edinme":  ["{a} Hakkında Bilgi Edinme Başvurusu", "{a} Bilgi Talebi"],
    "bilgilendirme": ["{a} Hk.", "{a} Uygulaması Hk.", "{a} Duyurusu"],
    "talep_yazisi":  ["{a} Talebi", "{a} Konusunda İhtiyaç Bildirimi"],
    "cevap_yazisi":  ["{a} Hk.", "{a} Başvurusu Hk.", "{a} Talebinin Sonucu"],
    "gorus_talebi":  ["{a} Hakkında Görüş Talebi", "{a} Konusunda Mütalaa Talebi"],
    "ust_yazi":      ["{a} Listesinin Gönderilmesi", "{a} Belgelerinin Gönderilmesi"],
    "tekit_yazisi":  ["{a} Hk. (Tekit)", "{a} Talebinin Tekidi"],
    "olur_yazisi":   ["{a} Oluru", "{a} Konusunda Makam Oluru"],
}

_PARANTEZ = re.compile(r"\s*\([^)]*\)")


def _konu_turet(kod_adi: str, belge_turu: str, i: int) -> str:
    """Kod adından belge türüne uygun konu başlığı üretir.

    "İmar Durumu (Belgesi)" + dilekce -> "İmar Durumu Talebi"
    Parantezli açıklamalar atılır; konu satırında kullanılmaz.
    """
    ad = _PARANTEZ.sub("", kod_adi).strip()
    kaliplar = _TUR_KONU_KALIBI.get(belge_turu, ["{a} Hk."])
    return kaliplar[i % len(kaliplar)].format(a=ad)


# Taşınmaz (ada/parsel) yalnızca gerçekten taşınmaza bağlı konularda anlamlı.
# 115 = İmar İşleri, 752/756 = Emlak ve Yapım. Atık yönetimi veya öğrenci
# belgesi talebinde ada/parsel yazmak belgeyi anlamsız yapar.
# Taşınmaz (ada/parsel) alanı YALNIZCA bu kodlarda görünür.
#
# KELİME EŞLEŞTİRME TERK EDİLDİ. Üç tur denendi ve üçünde de yanlış eşleşme
# çıktı: "Yapılandırma"daki *yapı*, "Stratejik Plan"daki *plan*, "Ruhsat
# Devri"ndeki *ruhsat*. Metinden desen aramak yerine kodun kendisine beyaz
# liste uygulanıyor; kod zaten etikette hazır ve kesin.
#
# 170.01 (işyeri açma ve çalışma ruhsatı) listede YOK: işyeri ruhsatında
# kimlik bilgisi ada/parsel değil, ruhsat numarası ve işyeri adresidir.
_TASINMAZ_KODLARI = frozenset({
    "115.01.06", "115.01.08", "115.02.01", "115.02.04", "115.02.08",
    "115.02.10", "115.02.11", "752.01", "756.01", "756.02", "190.01.07",
})

# Öğrenim bilgisi (sınıf, mezuniyet yılı) yalnızca öğrenci kodlarında.
_OGRENCI_ANA_GRUP = frozenset({"301", "302", "303", "304", "309", "310"})


def _tasinmaz_konusu_mu(kod: str, konu: str = "") -> bool:
    return kod in _TASINMAZ_KODLARI


# Konu başlığını, metin içinde kullanılabilir bir talep ifadesine çevirir.
#   "İmar Durum Belgesi Talebi"  ->  "imar durum belgesi"
#   "Nikah Tarihi Talebi"        ->  "nikah tarihi"
_KONU_EKI = re.compile(
    r"\s*(Talebi|Talep Formu|Başvurusu|Başvuru|Şikayeti|Şikâyeti|İsteği|"
    r"Bildirimi|Duyurusu|Hk\.?|Hakkında)\s*$", re.I)


def _talep_ifadesi(konu: str, kod_adi: str) -> str:
    """Konu başlığından tür ekini atıp gövde metnine uygun hâle getirir.

    Ek atılmazsa metinde "imar durum belgesi talebi talep ediyorum" gibi
    tekrarlar oluşur. Ek atıldıktan sonra bir şey kalmıyorsa kodun adına
    düşülür.
    """
    sade = _KONU_EKI.sub("", konu).strip()
    return (sade or kod_adi)


def _donem(h, kurum_tipi: str) -> str:
    """Dönem ifadesi kurum tipine göre değişir.

    Belediye yazısında "öğretim yılı sonunda" ifadesi kullanılmaz; eğitim
    kurumuna ait bir zaman birimidir ve belgeyi yadırgatır.
    """
    if kurum_tipi in ("universite", "il_mudurlugu"):
        return h.sec(["bahar dönemi", "güz dönemi", "öğretim yılı",
                      "içinde bulunulan öğretim yılı"])
    return h.sec(["yılın ilk yarısı", "üçüncü çeyrek", "içinde bulunulan yıl",
                  "mali yıl"])


# kurum.json'daki alt_makamlar listesi çoğul TANIM içeriyor, tekil AD değil.
# Bunlar gönderen adı olarak kullanılamaz; somut bir birime çevrilmeleri gerekir.
_COGUL_MAKAM = {
    "Yenimahalle Belediyesi müdürlükleri": "kurum_ici",
    "Gazi Üniversitesi fakülte, enstitü, yüksekokul ve daire başkanlıkları": "kurum_ici",
    "İl millî eğitim müdürlüğü şube müdürlükleri": "kurum_ici",
    "İlçe millî eğitim müdürlükleri": "ilce_mem",
    "Okul ve kurum müdürlükleri": "okul",
}


# Şikâyet konusu alıcı kurumun görev alanından seçilir. Belediyeye yazılan
# şikâyet ile üniversiteye yazılan şikâyet aynı olamaz.
_SIKAYET_SORUNLARI = {
    "belediye": [
        "sokaktaki çöp konteyneri düzenli boşaltılmıyor",
        "kaldırım işgali nedeniyle yaya geçişi engelleniyor",
        "gece saatlerinde ruhsatsız çalışma yapılıyor",
        "sokak aydınlatması uzun süredir çalışmıyor",
        "park alanındaki oyun grupları bakımsız durumda",
        "kaçak yapı faaliyeti sürdürülüyor",
        "işyeri çevreye rahatsızlık veren atık bırakıyor",
    ],
    "universite": [
        "yemekhane hizmetinde uzun kuyruk oluşuyor",
        "derslik ısıtma sistemi çalışmıyor",
        "kütüphane çalışma saatleri yetersiz kalıyor",
        "öğrenci servisi güzergâhı ilan edilen saatlere uymuyor",
        "yurt odalarında bakım talebi sonuçlandırılmıyor",
    ],
    "il_mudurlugu": [
        "okul servis aracı ilan edilen güzergâhı izlemiyor",
        "taşımalı eğitim aracı öğrencileri geç alıyor",
        "okul kantininde fiyat listesi asılı değil",
        "sınıf mevcudu ilan edilen sayının üzerinde",
        "servis şoförü belge kontrolü yapılmıyor",
    ],
}

# "Kullanım amacı" alanı yalnızca belge/suret talebinde anlamlı.
_BELGE_TALEBI_MI = re.compile(
    r"belge|suret|örne[kğ]|transkript|diploma|çıktı|rapor|onaylı|yazı", re.I)


# Gönderen tipi -> birimin tipik_muhataplar sütununda aranacak değerler.
# Bir birim bu tiplerden hiçbiriyle yazışmıyorsa o gönderene muhatap olmaz.
_MUHATAP_ESLEME = {
    "vatandas":   {"vatandas"},
    "ozel_tuzel": {"ozel_tuzel_kisi"},
    "ust_makam":  {"valilik", "kaymakamlik", "bakanlik", "buyuksehir_belediyesi",
                   "kurum_ici"},
    "ayni_duzey": {"universite", "il_mudurlugu", "diger_belediye",
                   "buyuksehir_belediyesi"},
    "alt_makam":  {"kurum_ici", "il_mudurlugu"},
}


# Kurgusal okul adları. Gerçek mahalle adı kullanılırsa o mahallede gerçekten
# bulunan bir okulla çakışma riski var; okul adları tamamen uydurma tutuluyor.
# Türkiye'de mahalle/ilçe adı OLMAYAN uydurma adlar. Önceki listede
# "Akpınar" (Balıkesir'de aynı adlı MTAL var) ve "Karataş" (Adana'da ilçe)
# vardı; çakışma riski taşıyordu.
_KURGUSAL_OKUL_ADI = [
    "Yıldıztepe", "Akarsu", "Gülpınar", "Söğütbaşı", "Işıkyurdu",
    "Umutkent", "Bereketli", "Selviçam", "Gökkuşağı", "Aydınyaka",
    "Erdemtepe", "Nurbahçe", "Yeşilyurt Vadi", "Özgüryurt", "Barışkent",
]


# Kurum ölçeğine göre günlük evrak hızı ve yıl başı taban numarası.
# (hiz_alt, hiz_ust, taban_alt, taban_ust)
_OLCEK = {
    "bakanlik":   (3000, 5000, 40_000_000, 90_000_000),
    "valilik":    (1000, 1500,  8_000_000, 20_000_000),
    "buyuksehir": ( 800, 1200,  5_000_000, 15_000_000),
    "universite": ( 700, 1000,  1_000_000,  9_000_000),
    "il_mud":     ( 600,  900,  1_000_000,  9_000_000),
    "ilce_bld":   ( 300,  600,    500_000,  4_000_000),
    "ilce_mud":   ( 150,  300,    100_000,  900_000),
    "okul":       (  15,   40,      1_000,     6_000),
    "orta":       ( 400, 1200,  1_000_000,  8_000_000),
}


def _olcek_bul(makam: str, kurum_tipi: str | None = None) -> str:
    """Makam adından evrak ölçeğini kestirir."""
    m = normalize_ad(makam)
    if "bakanlig" in m or "yuksekogretim kurulu" in m or "cumhurbaskanlig" in m:
        return "bakanlik"
    if "valilig" in m:
        return "valilik"
    if "buyuksehir" in m:
        return "buyuksehir"
    if "okulu" in m or "lisesi" in m or "anaokul" in m:
        return "okul"
    if "ilce" in m or "kaymakamlig" in m:
        return "ilce_mud"
    if "universite" in m or "rektorluk" in m or "fakulte" in m or "enstitu" in m:
        return "universite"
    if "il milli egitim" in m or "il mudurlug" in m:
        return "il_mud"
    if "belediye" in m:
        return "ilce_bld"
    return {"belediye": "ilce_bld", "universite": "universite",
            "il_mudurlugu": "il_mud"}.get(kurum_tipi or "", "orta")


def normalize_ad(s: str) -> str:
    """Ölçek eşleştirmesi için sadeleştirme — Türkçe harfler düzleştirilir."""
    esle = str.maketrans("çğıöşüâîûÇĞİÖŞÜ", "cgiosuaiuCGIOSU")
    return tr_kucult_basit(s.translate(esle))


def tr_kucult_basit(s: str) -> str:
    return s.replace("İ", "i").replace("I", "ı").lower()


# =============================================================================
# ŞİKÂYET HAVUZLARI — SDP KODUNA BAĞLI
# =============================================================================
# Ölçülen sorun: havuz belge ailesine bağlıydı, koda değil. Sonuç: "İzin İşleri
# Hakkında Şikâyet" başlıklı yazının gövdesinde derslik ısıtmasından söz
# ediliyordu. Konu ile gövde kopunca bir uzman anında fark eder.
_SIKAYET_KOD = {
    "155": ["konteyner düzenli boşaltılmıyor",
            "hafriyat atığı kaldırım kenarına bırakılıyor",
            "atık toplama saatleri ilan edilenden farklı"],
    "165": ["kaldırım işgali nedeniyle yaya geçişi engelleniyor",
            "izinsiz seyyar satış yapılıyor",
            "işyeri ilan edilen kapanış saatine uymuyor"],
    "115": ["ruhsata aykırı ilave kat yapılıyor",
            "inşaat çalışması gece saatlerinde sürdürülüyor",
            "kaçak yapı faaliyeti bildirilmesine rağmen sürüyor"],
    "170": ["işyeri ruhsatta belirtilen faaliyet dışında çalışıyor",
            "ruhsatsız işletme faaliyetini sürdürüyor"],
    "180": ["yangın merdiveni kapalı tutuluyor",
            "işyerinde yangın tüpü bulunmuyor"],
    "802": ["servis aracı ilan edilen güzergâhın dışına çıkıyor",
            "servis saatleri ders programıyla uyuşmuyor",
            "servis aracı kapasitesinin üzerinde yolcu alıyor"],
    "140": ["taşıma aracı öğrencileri geç alıyor",
            "taşıma merkezi okul öğrencinin ikametine uzak kalıyor"],
    "302": ["izin talebim otuz gündür sonuçlandırılmadı",
            "kayıt işlemim sistemde görünmüyor",
            "belge talebime yazılı cevap verilmedi"],
    "235": ["yabancı uyruklu öğrencinin kayıt işlemi tamamlanmadı",
            "denklik belgesi işleme alınmadı"],
    "205": ["sınıf mevcudu ilan edilen sayının üzerinde",
            "kayıt alanı dışından öğrenci kabul ediliyor"],
    "807": ["derslik ısıtma sistemi çalışmıyor",
            "bina onarım talebi sonuçlandırılmadı"],
    "304": ["burs ödemesi ilan edilen tarihte yapılmadı",
            "yemekhane hizmetinde uzun kuyruk oluşuyor"],
}

_SIKAYET_VARSAYILAN = {
    "belediye": ["sokak aydınlatması uzun süredir çalışmıyor",
                 "park alanındaki oyun grupları bakımsız durumda",
                 "işyeri çevreye rahatsızlık veren atık bırakıyor"],
    "universite": ["kütüphane çalışma saatleri yetersiz kalıyor",
                   "yurt odalarında bakım talebi sonuçlandırılmıyor",
                   "yemekhane hizmetinde uzun kuyruk oluşuyor"],
    "il_mudurlugu": ["okul kantininde fiyat listesi asılı değil",
                     "servis şoförü belge kontrolü yapılmıyor"],
}


def _sikayet_sorunu(kod: "SdpKodu", kurum_tipi: str) -> list[str]:
    """Şikâyet cümlesi CSV'deki sikayet_cumleleri sütunundan gelir.

    Önceki üç yöntem de yetersizdi:
      1. Belge ailesine bağlı havuz -> kod ile içerik kopuktu
      2. Ana gruba bağlı havuz      -> 115 kodun ancak yarısını kapsıyordu
      3. Kod adından türetme        -> Türkçe bozuluyordu
         ("nakiller işlemlerinde uzun süredir aksama yaşanıyor")

    Artık 50 kodun her biri için elle yazılmış 3 doğal cümle var.
    Üreteç şikâyeti zaten yalnızca o 50 koddan seçiyor; boş kalma
    ihtimali düşük ama yedek havuz duruyor.
    """
    if kod.sikayet_cumleleri:
        return kod.sikayet_cumleleri
    return _SIKAYET_VARSAYILAN.get(kurum_tipi, _SIKAYET_VARSAYILAN["belediye"])


def _sikayet_yeri(h, kurum_tipi: str) -> str:
    """Şikâyetin geçtiği yer kuruma göre değişir.

    Yemekhane kuyruğu veya derslik ısıtması bir MAHALLEDE değil, kampüste
    olur. Mahalle adı yalnızca belediye ve il müdürlüğü şikâyetlerinde
    anlamlı.
    """
    if kurum_tipi == "universite":
        return h.sec(["Merkez Yerleşke", "Beşevler Yerleşkesi",
                      "Gölbaşı Yerleşkesi", "B Blok 3. kat",
                      "Merkez Yerleşke yemekhanesi"])
    if kurum_tipi == "il_mudurlugu":
        return h.sec([f"{h.mahalle()} Mahallesi", "ilçe merkezi",
                      "okul servis güzergâhı"])
    return f"{h.mahalle()} Mahallesi"


_BOLUMLER = [
    "Hukuk Fakültesi", "Mühendislik Fakültesi Bilgisayar Mühendisliği",
    "Gazi Eğitim Fakültesi Sınıf Öğretmenliği", "İktisadi ve İdari Bilimler Fakültesi",
    "Teknoloji Fakültesi Elektrik-Elektronik", "Fen Fakültesi Matematik",
    "Tıp Fakültesi", "Diş Hekimliği Fakültesi", "Mimarlık Fakültesi",
]


# Denetim yapan birimler: şikâyet ve ihbar bunlara gider, talep ve başvuru
# ilgili işlemi DÜZENLEYEN birime.
_DENETIM_BIRIMI = re.compile(r"Zabıta|Denetim|Teftiş|Kontrol", re.I)


# =============================================================================
# DAĞITIM KÜMELERİ — gönderene göre sabit
# =============================================================================
# Ölçülen hata: dağıtım muhatapları rastgele kurum listesinden seçiliyordu ve
# YÖK'ün sınav duyurusu "Ankara Valiliği"ne dağıtılıyor görünüyordu.
# Gerçek örnek dayanağı: İŞKUR yazısında "Dağıtım: Üniversite Rektörlüklerine",
# İçişleri yazısında "Bilgi: 81 İl Valiliğine, Emniyet Genel Müdürlüğüne".
# Dağıtım kümeleri. Anahtar ya (gönderen, alıcı_kurum_tipi) çiftidir ya da
# yalnızca gönderendir. Çift anahtar, dağıtım listesinin ALICIYI KAPSAMASINI
# garantiler: bir belediye "81 İl Valiliğine" dağıtımlı yazının muhatabı olamaz.
_DAGITIM_KUMESI = {
    ("Yükseköğretim Kurulu Başkanlığı", "universite"): ["Üniversite Rektörlüklerine"],
    ("Millî Eğitim Bakanlığı", "il_mudurlugu"):
        ["Valilik Makamlarına", "İl Millî Eğitim Müdürlüklerine"],
    ("Millî Eğitim Bakanlığı", "universite"):
        ["Üniversite Rektörlüklerine", "Valilik Makamlarına"],
    ("İçişleri Bakanlığı", "belediye"):
        ["Belediye Başkanlıklarına", "İl Özel İdarelerine"],
    ("İçişleri Bakanlığı", "il_mudurlugu"): ["81 İl Valiliğine"],
    ("Çevre, Şehircilik ve İklim Değişikliği Bakanlığı", "belediye"):
        ["Belediye Başkanlıklarına", "İl Özel İdarelerine"],
    ("Çevre, Şehircilik ve İklim Değişikliği Bakanlığı", "il_mudurlugu"):
        ["81 İl Valiliğine", "Çevre ve Şehircilik İl Müdürlüklerine"],
    ("Ankara Valiliği", "belediye"):
        ["İlçe Kaymakamlıklarına", "İlçe Belediye Başkanlıklarına"],
    ("Ankara Valiliği", "il_mudurlugu"): ["İl Müdürlüklerine"],
    ("Ankara Valiliği", "universite"):
        ["Üniversite Rektörlüklerine", "İlçe Kaymakamlıklarına"],
    ("Ankara Büyükşehir Belediye Başkanlığı", "belediye"):
        ["İlçe Belediye Başkanlıklarına"],
    ("Yenimahalle Kaymakamlığı", "il_mudurlugu"): ["İlçe Müdürlüklerine"],
    ("Yenimahalle Kaymakamlığı", "belediye"): ["İlçe Belediye Başkanlığına"],
    ("Yenimahalle Kaymakamlığı", "universite"): ["İlgili Kurum ve Kuruluşlara"],
    # Yalnızca gönderene bağlı yedekler
    "Yükseköğretim Kurulu Başkanlığı": ["Üniversite Rektörlüklerine"],
    "Millî Eğitim Bakanlığı": ["Valilik Makamlarına"],
    "İçişleri Bakanlığı": ["81 İl Valiliğine"],
    "Çevre, Şehircilik ve İklim Değişikliği Bakanlığı": ["81 İl Valiliğine"],
    "Ankara Valiliği": ["İlçe Kaymakamlıklarına"],
    "Ankara Büyükşehir Belediye Başkanlığı": ["İlçe Belediye Başkanlıklarına"],
    "Yenimahalle Kaymakamlığı": ["İlçe Müdürlüklerine"],
}

# Bilgi kopyası GERÇEK BİR DIŞ MAKAMA gider. "Bakanlık Makamına" kalıbı ancak
# gönderen bir genel müdürlükse geçerli; bakanlığın kendisi kendi makamına
# bilgi kopyası göndermez.
_DAGITIM_BILGI = {
    "Yükseköğretim Kurulu Başkanlığı": ["Yükseköğretim Denetleme Kuruluna"],
    "Millî Eğitim Bakanlığı": ["Cumhurbaşkanlığına"],
    "Ankara Valiliği": ["İçişleri Bakanlığına"],
    "Ankara Büyükşehir Belediye Başkanlığı": ["Ankara Valiliğine"],
    "İçişleri Bakanlığı": ["Emniyet Genel Müdürlüğüne"],
    "Çevre, Şehircilik ve İklim Değişikliği Bakanlığı": ["81 İl Valiliğine"],
    "Yenimahalle Kaymakamlığı": ["Ankara Valiliğine"],
}


def _isbirligi_talebi(konu: str, is_adi: str) -> str:
    """İşbirliği talebini KONUDAN türetir.

    Konu "Hukuki Görüş Talebi" iken gövdede protokol istemek, konu ile
    gövdeyi koparıyordu.
    """
    k = tr_kucult_basit(konu)
    if "görüş" in k or "mütalaa" in k:
        return f"{is_adi} konusunda görüş bildirilmesi"
    if "protokol" in k or "iş birliği" in k or "işbirliği" in k:
        return "iş birliği protokolü düzenlenmesi"
    if "veri" in k or "bilgi" in k or "istatistik" in k:
        return f"{is_adi} kapsamındaki bilgilerin paylaşılması"
    # Konu "... Uzatılması" ise talep süre uzatımıdır; "öğrenci kabul
    # edilmesi" bambaşka bir işlem. Ölçülen hata: konu "Staj Süresinin
    # Uzatılması Talebi" iken gövde öğrenci kabulü istiyordu.
    if "uzat" in k or "süre" in k:
        return f"{is_adi} konusunda gerekli sürenin tanınması"
    if "tahsis" in k or "salon" in k:
        return "gerekli tahsisin yapılması"
    if "kontenjan" in k or "yeri" in k:
        return f"{is_adi} için kontenjan ayrılması"
    if "staj" in k or "uygulama" in k:
        return f"{is_adi} kapsamında öğrenci kabul edilmesi"
    if "tahsis" in k or "salon" in k or "yer tahsis" in k:
        return "gerekli yer tahsisinin yapılması"
    return f"{is_adi} konusunda gerekli koordinasyonun sağlanması"


def _bolum_sec(h, birim_adi: str) -> str:
    """Öğrencinin bölümü ALICI BİRİME bağlı seçilir.

    Alıcı bir fakülte dekanlığıysa öğrenci o fakültenin öğrencisidir;
    Teknoloji Fakültesi öğrencisinin dilekçesi Gazi Eğitim Fakültesi
    Dekanlığına gitmez.
    """
    for anahtar, bolumler in _FAKULTE_BOLUM.items():
        if anahtar in birim_adi:
            return h.sec(bolumler)
    return h.sec(_BOLUMLER)


_FAKULTE_BOLUM = {
    "Gazi Eğitim": ["Sınıf Öğretmenliği", "Matematik Öğretmenliği",
                    "Türkçe Öğretmenliği", "Rehberlik ve Psikolojik Danışmanlık"],
    "Teknoloji Fakültesi": ["Elektrik-Elektronik Mühendisliği",
                            "Bilgisayar Mühendisliği", "Enerji Sistemleri Mühendisliği"],
    "Mühendislik Fakültesi": ["Makine Mühendisliği", "Endüstri Mühendisliği",
                              "İnşaat Mühendisliği"],
    "Fen Bilimleri": ["Matematik (Yüksek Lisans)", "Kimya (Doktora)",
                      "Biyoloji (Yüksek Lisans)"],
}


# Şirketin sektörü SDP ana grubuna bağlı: bir inşaat şirketi özel öğretim
# istatistiği istemez.
_SIRKET_SEKTOR = {
    "115": ["İnşaat Ltd. Şti.", "Yapı Denetim A.Ş.", "Mimarlık Ltd. Şti."],
    "752": ["İnşaat Ltd. Şti.", "Gayrimenkul Yatırım A.Ş."],
    "755": ["İnşaat Ltd. Şti.", "Mühendislik Ltd. Şti."],
    "756": ["Gayrimenkul Yatırım A.Ş.", "İnşaat Ltd. Şti."],
    "170": ["Gıda Sanayi Ltd. Şti.", "Turizm ve Ticaret A.Ş.", "Market Zinciri A.Ş."],
    "155": ["Çevre Teknolojileri Ltd. Şti.", "Atık Yönetimi A.Ş."],
    "802": ["Taşımacılık Ltd. Şti.", "Turizm ve Ticaret A.Ş."],
    "934": ["Kırtasiye ve Büro Malzemeleri Ltd. Şti.", "Bilişim Sistemleri A.Ş."],
}
_SIRKET_GENEL = ["Danışmanlık Ltd. Şti.", "Ticaret A.Ş.", "Hizmetleri Ltd. Şti."]


def _sirket_turu(kod: str) -> list[str]:
    if kod[:3] in _SIRKET_SEKTOR:
        return _SIRKET_SEKTOR[kod[:3]]
    if kod[:3] in ("301", "302", "303", "304", "309", "310",
                   "205", "210", "215", "135", "198", "235", "245"):
        return ["Eğitim Hizmetleri Ltd. Şti.", "Danışmanlık Ltd. Şti."]
    return _SIRKET_GENEL


# İlçe müdürlükleri ve okullar kurumun İÇ BİRİMİ değil AST KURULUŞUDUR.
# birimler.csv'de aynı seviyede görünürler ama DETSİS hiyerarşisi
# "İl MEM > İlçe MEM > Okul" der; yazışmada alıcı ÜST konumdadır.
_AST_KURULUS = re.compile(r"İlçe|Okulu|Lisesi|Anaokulu|Ortaokulu", re.I)

# Bir kurumun KENDİ ORGANI — bunlara bilgi kopyası göndermek arz yönü
# yaratmaz. Yükseköğretim Denetleme Kurulu YÖK'ün üstü değil, kendi
# organıdır (2547 s. Kanun m.8).
_KENDI_ORGANI = {
    "Yükseköğretim Kurulu Başkanlığı": ["Yükseköğretim Denetleme Kuruluna"],
    "Millî Eğitim Bakanlığı": ["Bakanlık Makamına"],
    "Çevre, Şehircilik ve İklim Değişikliği Bakanlığı": ["Bakanlık Makamına"],
}

# Şikâyetin fiziksel bir mekânı ancak bu kod gruplarında olur.
# 302.x (öğrenci işleri), 622.x (bilgi edinme), 855/858 (mali) idari
# işlemdir; "Merkez Yerleşke yemekhanesi" gibi bir yer bilgisi anlamsız.
_FIZIKSEL_MEKAN = frozenset({
    "115", "155", "165", "170", "175", "180", "752", "755", "756",
    "802", "807", "140", "205",
})


# İlçe müdürlüğü kendi başlık bloğuna sahip ayrı muhataptır; dışarıdan yazan
# kurum il müdürlüğüne değil doğrudan kaymakamlığa yazar
# (kurum_ilmem.json > baslik_bloku_ilce).
_ILCE_MUHATAP = {
    "yenimahalle_ilce_mem": ("Yenimahalle Kaymakamlığı",
                             "İlçe Millî Eğitim Müdürlüğü"),
}

# Kod bazlı asgari sınıf. Erasmus/Farabi başvurusunda en az bir dönem öğrenim
# şartı var; 1. sınıf öğrencisi değişimden dönüp hibe bekliyor olamaz.
_ASGARI_SINIF = {
    "304.03": 3,   # stajlar
    "773": 3,      # staj işleri
    "310": 2,      # öğrenci değişim programları
    "301.06": 2,   # yatay geçiş
    "302.15": 4,   # mezuniyet işlemleri
}

# İki ayrı tüzel kişinin GERÇEKTEN ortak işi olan kodlar. Bu dokuzun dışında
# isbirligi_talebi üretilmez. Ölçülen hata üç turda tekrarlandı: üniversite
# ilçe MEM'den okul aile birliği bağış makbuzu istiyordu.
_ISBIRLIGI_KODLARI = frozenset({
    "355.02",   # Eğitim Fakülteleri İle İlişkiler
    "773",      # Staj İşleri
    "304.03",   # Stajlar
    "250",      # İşletmelerde Meslekî Eğitim
    "815",      # Sosyal Yardım İşleri
    "051",      # Toplantı ve Etkinlik İşleri
    "045.02",   # Hukuki (görüş)
    "802",      # Ulaşım ve Servis İşleri
    "756.01",   # Tahsis, Devir ve Takas
})

# Kurumun kendi iç yazışma diline ait konu ekleri. Vatandaş dilekçesinde
# bulunmaz: vatandaş "Tadilat Talebi" yazar, "Tadilat Talebinin
# Değerlendirilmesi" yazmaz.
_KURUM_AGZI_KONU = re.compile(
    r"(Gönderilmesi|Değerlendirilmesi|Duyurulması|Bildirimi|Onayı|"
    r"Görevlendirme|Tebliği|Raporu|Cetveli|Kararı|Tutanağı|Yayımlan|"
    r"Güncellenmesi|Dağıtımı|İncelenmesi)\s*$", re.I)

# Beyaz listenin YAPRAK olanları. 250 grup düğümüdür (saklama süresi boş,
# altında alt kod var) ve belge kodu olarak kullanılamaz; birim filtresinde
# onu saymak, tek beyaz liste kodu 250 olan birimi uygun sanmaya yol açıyordu.
_ISBIRLIGI_YAPRAK = _ISBIRLIGI_KODLARI - {"250"}
