"""Anlama — boru hattının 3. adımı. Belge türü, SDP, talep ve varlıklar.

TEK LLM ÇAĞRISI. Ajan değil: karar vermiyor, döngüye girmiyor, kendi
çıktısını denetlemiyor. Girdi → çıktı dönüşümü.

İKİ KATMAN
----------
Katman 1 modele SORMADAN seçenekleri daraltır, Katman 2 kalanı sorar.

Bu sıralamanın gerekçesi ölçülmüş: 11 türden ortalama 4,37'ye iniyor ve
8 belgede tek aday kalıyor — o belgelerde tür LLM'e hiç sorulmuyor.

KATMAN 1 — deterministik daraltma
---------------------------------
Üç kural, üçü de `veri/kota.json`'dan geliyor ve üçü de 300 etikette
%100 doğrulandı:

  1. GÖNDEREN UYUMU (`tur_gonderen_uyumu`)
     Ayrıştırıcının bulduğu `aile` gönderen tipini veriyor:
         dilekce -> vatandas          -> 4 tür
         sirket  -> ozel_tuzel        -> 3 tür  (dilekçe HARİÇ)
         kurum   -> üst/aynı/alt      -> 7 tür
     Şirketin dilekçe yazamaması taksonomi kuralıdır: dilekçe, evrak
     numarası olmayan, gerçek kişinin verdiği belgedir.

  2. İLGİ VARLIĞI (`ilgi.zorunlu_var` / `zorunlu_yok`)
     ilgi VAR  -> dilekce, sikayet, bilgi_edinme, olur_yazisi elenir
     ilgi YOK  -> cevap_yazisi, tekit_yazisi, ust_yazi elenir
     Ölçüldü: cevap 34/34, tekit 10/10, ust_yazi 18/18 ilgili;
     dilekce 0/66, sikayet 0/33, bilgi_edinme 0/22, olur 0/6 ilgisiz.

  3. EK VARLIĞI (`ek.zorunlu_var`)
     ek YOK -> ust_yazi elenir. Ölçüldü: ust_yazi 18/18 ekli.

GÜVENLİK ÖLÇÜMÜ: 300 belgenin HİÇBİRİNDE daraltma doğru cevabı elemedi.
Bu ölçülmeden daraltma kullanılamazdı — elenen doğru cevap, modelin
asla telafi edemeyeceği bir kayıptır.

`bilinmiyor` her zaman listede kalır: aile tespit edilemediyse (4 belge)
veya kurallar çelişirse model "emin değilim" diyebilmelidir.

KATMAN 2 — modele sorulan
-------------------------
Kalan türler için ayırt edici tanım verilir. Tanımlar UYDURULMADI;
`kota.json`'un yapısal kurallarından türetildi ve raporda böyle
belirtilecek — depoda belge türü tanımı yazan bir taksonomi dosyası YOK
(`veri/taksonomi/YONTEM.md` baştan sona SDP kodları hakkındadır).

Ayrıştırıcının çıkardığı bilgiler isteme HAZIR verilir (ilgi var mı, ek
var mı, kapanış nedir). Model bunları metinden yeniden çıkarmaya
çalışmasın; çıkarırsa hata yapabilir, hazır alırsa yapamaz.

SDP — okunur, tahmin edilmez
----------------------------
SDP kodu resmî sayının ÜÇÜNCÜ bölümünde yazılıdır:

    E-24316060-115.02.01-4471829
                ^^^^^^^^^

Okunabiliyorsa güven 1.0 ile alınır ve modele hiç sorulmaz (168/300
belge). Şirket sayısı (2026/335) SDP taşımaz; dilekçede sayı yoktur.
O 132 belgede model tahmin eder ve güven düşüktür.

ŞEMA ZORLAMASI
--------------
`response_format` ile JSON şeması dayatılır. Ölçüldü (sonda, Gemini):
istem içi şemaya göre çağrıyı 5 kat hızlandırıyor (9,7-13,6 sn → 2,1-2,5
sn) ve JSON geçerliliğini garanti ediyor. Enum daraltması da buradan
uygulanır: model listenin dışına ÇIKAMAZ.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ayristirici import AyristirmaSonucu
from taksonomi import ETIKETTEN_SEMAYA
from veri_yapisi import (
    GelenTur,
    Icerik,
    Kanit,
    KanitYontemi,
    Konum,
    SdpKodu,
    Siniflandirma,
    Varlik,
    VarlikTipi,
)

URETEN = "anlama"

KOK = Path(__file__).resolve().parent.parent
KOTA_YOLU = KOK / "veri" / "kota.json"

# -----------------------------------------------------------------------------
# Katman 1 — daraltma tabloları
# -----------------------------------------------------------------------------

# Ayrıştırıcının `aile` değeri -> kota.json'daki gönderen tipleri
AILE_GONDEREN: dict[str, set[str]] = {
    "dilekce": {"vatandas"},
    "sirket": {"ozel_tuzel"},
    "kurum": {"ust_makam", "ayni_duzey", "alt_makam"},
}

_KOTA_ONBELLEK: dict | None = None


def kota_yukle(yol: Path | None = None) -> dict:
    global _KOTA_ONBELLEK
    if _KOTA_ONBELLEK is None:
        hedef = yol or KOTA_YOLU
        _KOTA_ONBELLEK = json.loads(hedef.read_text(encoding="utf-8"))
    return _KOTA_ONBELLEK


def _kurallar() -> tuple[dict[str, list[str]], set[str], set[str], set[str]]:
    k = kota_yukle()
    uyum = {t: g for t, g in k["tur_gonderen_uyumu"].items()
            if not t.startswith("_")}
    return (uyum,
            set(k["ilgi"]["zorunlu_var"]),
            set(k["ilgi"]["zorunlu_yok"]),
            set(k["ek"]["zorunlu_var"]))


def aday_turler(aile: str, ilgi_var: bool, ek_var: bool) -> list[str]:
    """Katman 1. Etiket sözlüğünde tür adları döner.

    Daraltma hiçbir zaman listeyi boşaltmaz: kurallar çelişirse gönderen
    uyumundan gelen liste korunur. Boş liste modele hiçbir seçenek
    bırakmamak demektir ve sessiz bir başarısızlıktır.
    """
    uyum, ilgi_zorunlu, ilgi_yasak, ek_zorunlu = _kurallar()
    tipler = AILE_GONDEREN.get(aile, set())

    aday = [t for t, g in uyum.items() if set(g) & tipler] if tipler else list(uyum)
    genis = list(aday)

    if ilgi_var:
        aday = [t for t in aday if t not in ilgi_yasak]
    else:
        aday = [t for t in aday if t not in ilgi_zorunlu]
    if not ek_var:
        aday = [t for t in aday if t not in ek_zorunlu]

    return aday or genis


# -----------------------------------------------------------------------------
# Katman 2 — tür tanımları
# -----------------------------------------------------------------------------
#
# TÜRETİLDİ, UYDURULMADI. Her tanımın yanında dayanağı var. Depoda tanım
# dosyası bulunmadığı için kota.json'un yapısal kurallarından çıkarıldı;
# raporda "veri setinden türetildi" diye belirtilecek.

# TANIMLAR VERİDEN ÇIKARILDI — ve bir kez baştan yazıldı.
#
# İlk sürüm soyut kavramlarla yazılmıştı ("üst yazı: asıl içerik ektedir")
# ve ÖLÇÜM YALANLADI: ust_yazi 0/3, vatandas_dilekcesi 0/3. Belgeleri
# okuyunca sebep çıktı — model tanıma doğru uyuyordu, TANIM yanlıştı:
#
#   belge_006 (ust_yazi) gövdesi beş paragraf ve "dağıtımın sağlanması
#   hususunda gereğini rica ederim" diyor. Tanımım "gövde ne talep ne
#   duyuru içerir" diyordu; model haklı olarak talep_yazisi dedi.
#
#   belge_011 (dilekce) "makbuz tarafıma ulaşmamıştır" diyor. Tanımım
#   "ortada yaşanmış bir olumsuzluk YOKTUR" diyordu; doğru cevabı
#   kendi elimle eledim, model bilinmiyor dedi.
#
# İkinci sürüm 300 etiketin somut_bilgiler ALAN ADLARINDAN türetildi.
# Gövde metni bu alanlardan üretiliyor, dolayısıyla her ayırt edici
# öğe belgede GÖRÜNÜR. Ölçülen iskeletler:
#
#   gorus_talebi   Mevcut uygulama + Tereddüt + Sonuç + Talep      20/20
#   talep_yazisi   Ortak iş + Gerekçe + Beklenen katkı + Talep     38/38
#   ust_yazi       Dayanak + Ek1/Ek2 içerikleri + İstenen + Süre   18/18
#   bilgilendirme  Kaynak + Kapsam + Yürürlük + Kapsam dışı        42/42
#   dilekce        Talep + Başvuru şekli + Bildirim tercihi        66/66
#   itiraz         İtiraz konusu + Önceki karar + Gerekçe + Talep  11/11
#
# RAPORDA BELİRTİLECEK: tanımlar veri setinden türetilmiştir; depoda
# belge türü tanımı yazan bağımsız bir taksonomi dosyası yoktur.

TUR_TANIMLARI: dict[str, str] = {
    "dilekce":
        "Vatandaş bir BELGE, hizmet, izin veya işlem İSTER. Metinde şunlar "
        "bulunur: ne istediği, başvuruyu nasıl yaptığı (kayıt bürosu / "
        "e-Devlet), ve sonucun kendisine nasıl bildirilmesini istediği "
        "(SMS / posta / e-posta). Önceki bir kararı tartışmaz, sadece "
        "işini ister.",
    "sikayet":
        "Bir gecikmeden, işleyişten veya davranıştan duyulan "
        "MEMNUNİYETSİZLİĞİ bildirir. Şikâyet edilen somut bir durum ve "
        "genellikle ne kadar süredir devam ettiği yazılıdır.",
    "bilgi_edinme":
        "4982 sayılı Bilgi Edinme Hakkı Kanunu'na dayanarak bilgi veya "
        "belge ister. Kanuna açıkça atıf yapar.",
    "itiraz":
        "ÜÇÜ BİRDEN vardır: (1) daha önce verilmiş bir OLUMSUZ KARAR "
        "('reddedilmiştir', 'uygun görülmemiştir', 'işleme alınmamıştır'), "
        "(2) bu karara karşı bir GEREKÇE ('eksik belge dikkate alınmıştır', "
        "'bilgiler güncellenmiştir'), (3) KARARIN yeniden değerlendirilmesi "
        "talebi. Üçü birden yoksa itiraz değildir.",
    "bilgilendirme":
        "Yeni bir uygulamayı veya düzenlemeyi DUYURUR. Ayırt edici öğeler: "
        "dayandığı kaynak, KAPSAMI kimlerin oluşturduğu, YÜRÜRLÜK tarihi, "
        "KAPSAM DIŞINDA kalanlar ve irtibat bilgisi. Karşı taraftan iş "
        "istemez; kuralı anlatır.",
    "talep_yazisi":
        "İki kurumun ORTAK bir işi vardır ve muhataptan bu işe KATKI "
        "beklenir. Metin ortak işi, gerekçesini ve beklenen katkıyı "
        "anlatır. Görüş değil, somut bir işlem ister.",
    "cevap_yazisi":
        "İlgideki bir talebe CEVAP verir; talebin sonucunu bildirir "
        "('karşılanmıştır', 'uygun görülmüştür', 'mümkün değildir'). "
        "İlgi alanı vardır, eki yoktur.",
    "gorus_talebi":
        "Mevcut uygulamada bir TEREDDÜT veya belirsizlik olduğunu söyler ve "
        "muhatabın DEĞERLENDİRMESİNİ ister. Ayırt edici öğe tereddüttür: "
        "'uygulamada tereddüt doğmuştur', 'tereddüde düşülmüştür'. "
        "Ortak iş yoktur, katkı beklenmez; görüş beklenir.",
    "ust_yazi":
        "EKLERİ İLETİR ve eklerin İÇERİĞİNİ tarif eder ('söz konusu liste "
        "ad soyad ve tarih bilgilerini içermektedir', 'uygulama takvimi "
        "haftalık çizelge biçimindedir'). İlgi de ek de VARDIR. Gövde "
        "eklerin dağıtılmasını veya iletilmesini isteyebilir — bu onu "
        "talep yazısı yapmaz; asıl içerik ektedir.",
    "tekit_yazisi":
        "Daha önce yazılan bir yazıya CEVAP ALINAMADIĞINI söyler ve tekrar "
        "ister. 'Cevap alınamamıştır', 'ivedilikle' ifadeleri geçer.",
    "olur_yazisi":
        "Bir işlem için makam ONAYI (olur) alınmasına yöneliktir. "
        "'Olurlarınıza arz ederim' ile biter.",
    "bilinmiyor":
        "Yukarıdakilerin hiçbirine güvenle yerleştirilemiyor.",
}

SISTEM_ISTEMI = (
    "Türk kamu kurumlarına gelen resmî evrağı inceleyen bir uzmansın. "
    "Yalnızca belgede YAZAN bilgiye dayanarak cevap ver. "
    "Belgede bulunmayan bir bilgiyi tahmin etme, boş bırak."
)

# -----------------------------------------------------------------------------
# İngilizce istem — ölçülecek ikinci sürüm
# -----------------------------------------------------------------------------
#
# Devir notu §4 bunu açık iş olarak bırakmıştı: TR/EN farkı ölçülmedi, ve
# ölçüm tür tanımı İÇERMEYEN zayıf bir istemle yapılmıştı.
#
# TASARIM KARARI — TERİM TÜRKÇE, TANIM İNGİLİZCE.
# `ust_yazi`, `tekit_yazisi`, `olur_yazisi` Türk idare hukukuna özgü
# kavramlar. "cover letter" yazmak modeli başka bir kavrama eşleyebilir;
# üstelik terimler zaten şema enum'unun DEĞERLERİ, çevrilemezler.
# Çevrilen şey yalnızca AÇIKLAMA.
#
# Çıktı dili Türkçe kalmalı: talep, özet ve varlık değerleri doğrudan
# arayüze ve taslağa gidiyor. Sistem istemi bunu açıkça söylüyor.

SISTEM_ISTEMI_EN = (
    "You are an expert reviewing official correspondence received by "
    "Turkish public institutions. Base your answer ONLY on what the "
    "document actually states. Do not guess information that is not in "
    "the document; leave it empty instead. "
    "IMPORTANT: write all free-text output (talep, ozet, entity values, "
    "reasoning) in TURKISH, because these values are shown to Turkish "
    "civil servants and copied into official letters."
)

TUR_TANIMLARI_EN: dict[str, str] = {
    "dilekce":
        "A citizen ASKS FOR a document, service, permit or transaction. The "
        "text states what is wanted, how the application was filed (records "
        "office / e-Devlet), and how the result should be notified (SMS / "
        "post / e-mail). It does not contest an earlier decision.",
    "sikayet":
        "Reports DISSATISFACTION about a delay, a process or someone's "
        "conduct. Names a concrete situation and usually how long it has "
        "been going on.",
    "bilgi_edinme":
        "Requests information or documents under Law No. 4982 on the Right "
        "to Information, citing the law explicitly.",
    "itiraz":
        "ALL THREE are present: (1) a NEGATIVE DECISION already made "
        "('reddedilmiştir', 'uygun görülmemiştir'), (2) a GROUND against "
        "that decision ('eksik belge dikkate alınmıştır'), (3) a request to "
        "RE-EXAMINE THE DECISION. If all three are not present it is not an "
        "itiraz.",
    "bilgilendirme":
        "ANNOUNCES a new practice or regulation. Distinctive elements: its "
        "source, WHO IS COVERED, the EFFECTIVE DATE, WHO IS EXCLUDED, and "
        "contact details. Asks nothing of the recipient.",
    "talep_yazisi":
        "Two institutions share a JOINT TASK and a CONTRIBUTION is expected "
        "from the recipient. The text describes the joint task, its grounds "
        "and the expected contribution. Asks for a concrete action, not an "
        "opinion.",
    "cevap_yazisi":
        "REPLIES to a request referenced in İlgi, reporting its outcome "
        "('karşılanmıştır', 'uygun görülmüştür', 'mümkün değildir'). Has an "
        "İlgi field and no attachment.",
    "gorus_talebi":
        "States that there is a DOUBT or uncertainty in current practice and "
        "asks for the recipient's ASSESSMENT. The distinctive element is the "
        "doubt: 'uygulamada tereddüt doğmuştur'. No joint task, no expected "
        "contribution — an opinion is expected.",
    "ust_yazi":
        "TRANSMITS ATTACHMENTS and describes THEIR CONTENTS ('the list "
        "contains names, units and dates'). Both İlgi and Ek are PRESENT. "
        "The body may ask for the attachments to be distributed — that does "
        "not make it a talep_yazisi; the substance is in the attachment.",
    "tekit_yazisi":
        "States that NO REPLY was received to an earlier letter and asks "
        "again. Contains 'cevap alınamamıştır', 'ivedilikle'.",
    "olur_yazisi":
        "Seeks the APPROVAL (olur) of a superior authority. Ends with "
        "'Olurlarınıza arz ederim'.",
    "bilinmiyor":
        "Cannot be confidently assigned to any of the above.",
}


@dataclass
class AnlamaSonucu:
    siniflandirma: Siniflandirma = field(default_factory=Siniflandirma)
    icerik: Icerik = field(default_factory=Icerik)
    kanit: dict[str, Kanit] = field(default_factory=dict)
    adaylar: list[str] = field(default_factory=list)
    dil: str = "tr"
    llm_kullanildi: bool = False
    sure_ms: float = 0.0
    token: int = 0
    model: str | None = None
    uyarilar: list[str] = field(default_factory=list)

    @property
    def ozet(self) -> str:
        t = self.siniflandirma.belge_turu
        return (f"{t.value if t else '—'}, {len(self.adaylar)} adaydan, "
                f"{len(self.icerik.varliklar)} varlık")


# -----------------------------------------------------------------------------
# SDP — sayıdan okuma
# -----------------------------------------------------------------------------

# E-<DETSİS>-<SDP>-<kayıt>: üçüncü bölüm SDP kodudur.
_SAYIDAN_SDP = re.compile(r"^E-\d{8}-([\d.]+)-\d+$")


def sdp_adaylari(muhatap_ham: str | None,
                 muhatap_birim: str | None = None
                 ) -> list[tuple[str, str, list[str]]]:
    """Muhataptan birimi bulup O BİRİMİN SDP kodlarını döndürür.

    NEDEN — ilk ölçümde SDP tahmini 0/11 = %0 çıktı. Sebep model değil,
    tasarım boşluğuydu: modele ~700 kodluk evrenden serbest tahmin
    yaptırılıyordu ve `440.11.12.10.02.02.00.03.06` gibi uydurma kodlar
    üretiyordu.

    ÖLÇÜLDÜ (SDP'si sayıdan okunamayan 132 belge):
        doğru kod muhatabın biriminin listesinde : 132/132 = %100
        ortalama liste boyu                      : 5,0 kod  (evren ~700)

    Yani daraltma doğru cevabı ASLA elemiyor ve arama uzayını 140 kat
    küçültüyor. Aynı desen belge türünde de kullanıldı.

    (kod, ad, ornek_konular) üçlüleri döner. Ad ve örnek konular modele
    kodun ne kapsadığını söylüyor; çıplak kod listesi seçim için yeterli
    bilgi taşımaz.
    """
    if not muhatap_ham and not muhatap_birim:
        return []
    from birimler import birim_bul, hedef_olabilecekler
    from metin import en_iyi_eslesme
    from sdp_katalog import kod_adi

    # DİKKAT: alt birim ayrı alanda duruyor ve BİRLİKTE aranmalı.
    #     muhatap.ham   "ANKARA İL MİLLÎ EĞİTİM MÜDÜRLÜĞÜNE"
    #     muhatap.birim "Özel Öğretim Kurumları Şube Müdürlüğü"
    # Yalnızca ham ile aranırsa kurumun listesi gelir (4 kod), şubenin
    # değil. Ölçüm ikisini birlikte kullanmıştı; kod da öyle kullanmalı.
    arama = " ".join(x for x in (muhatap_ham, muhatap_birim) if x)
    adaylar = [(b["kod"], b["ad"], b["seviye"]) for b in hedef_olabilecekler()]
    kod, _, _ = en_iyi_eslesme(arama, adaylar)
    birim = birim_bul(kod) if kod else None
    if not birim:
        return []
    from sdp_katalog import ornek_konular
    return [(k, kod_adi(k) or "", ornek_konular(k)) for k in birim["sdp_kodlari"]]


def sdp_sayidan_oku(sayi: str | None) -> str | None:
    """Resmî sayının üçüncü bölümündeki SDP kodunu döndürür.

    Şirket sayısı (2026/335) DETSİS ve SDP taşımaz; None döner ve kod
    tahmin edilmek üzere modele bırakılır.
    """
    if not sayi:
        return None
    m = _SAYIDAN_SDP.match(sayi.strip())
    return m.group(1) if m else None


# -----------------------------------------------------------------------------
# Şema
# -----------------------------------------------------------------------------


def sema_kur(aday_etiketler: list[str], sdp_sorulacak: bool,
             sdp_aday: list[tuple[str, str, list[str]]] | None = None) -> dict:
    """response_format şemasını kurar; enum daraltılmış hâliyle konur.

    Şema `bilinmiyor`u daima içerir. Sayısal kısıt KONMAZ — Ollama'da
    ölçülmüştü: sayısal aralık zorlaması çağrıyı 9 kat yavaşlatıyor ve
    aralık dışı değer üretiyor. Güven ayrı bir alan olarak alınıyor ve
    veri_yapisi.py'nin doğrulayıcısı geçersiz değeri 0.0'a çekiyor.
    """
    turler = sorted({ETIKETTEN_SEMAYA.get(t, t) for t in aday_etiketler})
    if GelenTur.BILINMIYOR.value not in turler:
        turler.append(GelenTur.BILINMIYOR.value)

    ozellikler: dict = {
        "belge_turu": {"type": "string", "enum": turler},
        "belge_turu_gerekcesi": {
            "type": "string",
            "maxLength": 400,
            "description": "Bu türü seçme gerekçen, TEK CÜMLE, en fazla 400 karakter.",
        },
        "belge_turu_guveni": {
            "type": "number",
            "description": "0 ile 1 arasında.",
        },
        "talep": {
            "type": "string",
            "maxLength": 400,
            "description": "Belgenin ne istediği, TEK CÜMLE, en fazla 400 "
                           "karakter. Yoksa boş bırak.",
        },
        "ozet": {
            "type": "string",
            "maxLength": 400,
            "description": "Belgenin özeti, en fazla iki cümle.",
        },
        "varliklar": {
            "type": "array",
            "description": "Belgede GEÇEN varlıklar. Uydurma, yalnızca yazanı al.",
            "items": {
                "type": "object",
                "properties": {
                    "tip": {"type": "string",
                            "enum": [v.value for v in VarlikTipi]},
                    "deger": {"type": "string",
                              "description": "Belgede yazdığı hâliyle."},
                },
                "required": ["tip", "deger"],
                "additionalProperties": False,
            },
        },
    }
    zorunlu = ["belge_turu", "belge_turu_gerekcesi", "belge_turu_guveni",
               "talep", "ozet", "varliklar"]

    if sdp_sorulacak:
        if sdp_aday:
            # Enum: model listenin DIŞINA çıkamaz. Uydurma kod imkânsız.
            ozellikler["sdp_kodu"] = {
                "type": "string",
                "enum": [a[0] for a in sdp_aday],
                "description": "Muhatap birimin baktığı kodlardan biri.",
            }
        else:
            ozellikler["sdp_kodu"] = {
                "type": "string",
                "maxLength": 20,
                "description": "Tahmini standart dosya planı kodu, ör. 622.01. "
                               "Emin değilsen boş bırak.",
            }
        zorunlu.append("sdp_kodu")

    return {
        "type": "json_schema",
        "json_schema": {
            "name": "belge_anlama",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": ozellikler,
                "required": zorunlu,
                "additionalProperties": False,
            },
        },
    }


# -----------------------------------------------------------------------------
# İstem
# -----------------------------------------------------------------------------


# İki dildeki metin kalıpları. Terimler ve belge metni ÇEVRİLMEZ.
_KALIPLAR = {
    "tr": {
        "giris": "Aşağıdaki resmî evrağı incele.",
        "bilinen": "AYRIŞTIRMADAN GELEN BİLGİ (doğrudur, yeniden çıkarma):",
        "aile": "Belge ailesi", "ilgi": "İlgi alanı", "ek": "Ek",
        "konu": "Konu satırı", "muhatap": "Muhatap",
        "var": "VAR", "yok": "YOK", "adet": "VAR ({} adet)",
        "turler": "OLASI BELGE TÜRLERİ — yalnızca bunlardan birini seç:",
        "sdp": ("SDP KODU: bu belgenin sayısı standart dosya planı kodu "
                "taşımıyor. Konuya göre bir kod tahmin et; emin değilsen "
                "boş bırak."),
        "yapisal": ("YAPISAL İPUCU — 300 belgede ölçülen İlgi/Ek örüntüsü. "
                    "Kesin kural değil, güçlü işaret:"),
        "sdp_liste": ("SDP KODU: muhatap birimin baktığı kodlar aşağıda. "
                      "Belgenin konusuna en uygun olanı seç:"),
        "metin": "BELGE METNİ:",
    },
    "en": {
        "giris": "Analyse the official document below.",
        "bilinen": "FACTS FROM PARSING (these are correct, do not re-extract):",
        "aile": "Document family", "ilgi": "İlgi (reference) field",
        "ek": "Ek (attachment)", "konu": "Konu (subject) line",
        "muhatap": "Muhatap (addressee)",
        "var": "PRESENT", "yok": "ABSENT", "adet": "PRESENT ({} item(s))",
        "turler": "POSSIBLE DOCUMENT TYPES — choose exactly one of these:",
        "sdp": ("SDP CODE: this document's number does not carry a standard "
                "filing plan code. Infer one from the subject; leave empty "
                "if unsure."),
        "yapisal": ("STRUCTURAL HINT — İlgi/Ek pattern measured over 300 "
                    "documents. Not a hard rule, but a strong signal:"),
        "sdp_liste": ("SDP CODE: the filing codes handled by the addressee "
                      "unit are listed below. Choose the one that best fits "
                      "the subject of this document:"),
        "metin": "DOCUMENT TEXT (Turkish):",
    },
}


# (ilgi_var, ek_var) -> o profilde ÖLÇÜLEN türler, sıklık sırasıyla.
#
# Enum'dan elenmiyorlar, yalnızca modele işaret veriliyor. Gerekçe:
# kota.json cevap_yazisi'na 0.2, gorus_talebi'ne 0.15 ek olasılığı
# TANIYOR — bu veri setinde hiç çıkmamış olması kuralın kendisi değil.
# Sert eleme yapılsaydı jürinin getireceği bir belgede kurtarılamayan
# hata olurdu.
YAPISAL_ORUNTU: dict[tuple[bool, bool], str] = {
    (True, True): "ust_yazi (18/18) veya bilgilendirme_yazisi (25/42); "
                  "talep_yazisi nadir (2/38)",
    (True, False): "cevap_yazisi (34/34), tekit_yazisi (10/10), "
                   "talep_yazisi (16/38) veya gorus_talebi (7/20)",
    (False, True): "bilgilendirme_yazisi (17/42), olur_yazisi (6/6) veya "
                   "talep_yazisi (3/38)",
    (False, False): "talep_yazisi (17/38) veya gorus_talebi (13/20); "
                    "kurum yazısında başka tür bu profilde ölçülmedi",
}


def istem_kur(govde: str, ayristirma: AyristirmaSonucu,
              aday_etiketler: list[str], sdp_sorulacak: bool,
              dil: str = "tr",
              sdp_aday: list[tuple[str, str, list[str]]] | None = None) -> str:
    """İstemi kurar. Ayrıştırıcının bildiği her şey HAZIR verilir.

    dil: "tr" veya "en". İkisi de aynı bilgiyi taşır; yalnızca yönerge
    metni ve tür açıklamaları değişir. Belge metni ve tür ADLARI her iki
    sürümde de Türkçe kalır — terimler şema enum'unun değerleridir.
    """
    k = _KALIPLAR.get(dil, _KALIPLAR["tr"])
    tanim_tablosu = TUR_TANIMLARI_EN if dil == "en" else TUR_TANIMLARI
    u = ayristirma.ustveri

    ek_metni = k["adet"].format(len(u.ekler)) if u.ekler else k["yok"]
    bilinen = [
        f"{k['aile']:22s}: {ayristirma.aile}",
        f"{k['ilgi']:22s}: {k['var'] if u.ilgi else k['yok']}",
        f"{k['ek']:22s}: {ek_metni}",
        f"{k['konu']:22s}: {u.konu or '—'}",
        f"{k['muhatap']:22s}: {u.muhatap.ham or '—'}",
    ]

    # İstemdeki ad ile ŞEMADAKİ ad AYNI olmalı.
    #
    # HATA — ölçümde yakalandı: istem "dilekce seç" diyordu ama şema enum'u
    # yalnızca "vatandas_dilekcesi" kabul ediyordu. Model istediği cevabı
    # VEREMİYOR, en yakınına ya da bilinmiyor'a düşüyordu. Başarısız üç
    # sınıf tam olarak adı değişen üç sınıftı:
    #
    #     istem          şema                        F1
    #     dilekce        vatandas_dilekcesi          0.00
    #     bilgi_edinme   bilgi_edinme_basvurusu      0.80
    #     bilgilendirme  bilgilendirme_yazisi        1.00  (önek eşleşiyor)
    #
    # Tanım tablosu etiket adıyla anahtarlı; ETİKET adıyla arayıp ŞEMA
    # adıyla gösteriyoruz.
    tanimlar = "\n".join(
        f"  {ETIKETTEN_SEMAYA.get(t, t):24s} {tanim_tablosu.get(t, '')}"
        for t in aday_etiketler + ["bilinmiyor"]
    )

    parcalar = [k["giris"], "", k["bilinen"], *bilinen, "",
                k["turler"], tanimlar, ""]

    # Yapısal ipucu yalnızca kurum yazısında anlamlı; vatandaş ve şirket
    # belgelerinde ilgi/ek zaten ayırt edici değil.
    if ayristirma.aile == "kurum":
        oruntu = YAPISAL_ORUNTU.get((bool(u.ilgi), bool(u.ekler)))
        if oruntu:
            parcalar += [k["yapisal"], f"  {oruntu}", ""]
    if sdp_sorulacak:
        if sdp_aday:
            # Kod ADIYLA birlikte veriliyor; çıplak kod listesi seçim için
            # yeterli bilgi taşımaz.
            parcalar += [k["sdp_liste"]]
            for kod, ad, ornekler in sdp_aday:
                parcalar.append(f"  {kod:12s} {ad}")
                if ornekler:
                    parcalar.append(f"               örnek konular: "
                                    f"{' | '.join(ornekler)}")
            parcalar += [""]
        else:
            parcalar += [k["sdp"], ""]
    parcalar += [k["metin"], "---", govde.strip(), "---"]
    return "\n".join(parcalar)


# -----------------------------------------------------------------------------
# Ana giriş
# -----------------------------------------------------------------------------


def _kanit(alinti: str, yontem: KanitYontemi, guven: float,
           aciklama: str | None = None) -> Kanit:
    return Kanit(yontem=yontem, ureten=URETEN, guven=guven,
                 alinti=alinti[:300], konum=Konum(sayfa=1),
                 aciklama=aciklama)


def anla(govde: str, ayristirma: AyristirmaSonucu, istemci,
         dil: str = "tr") -> AnlamaSonucu:
    """Belge türünü, SDP'yi, talebi ve varlıkları çıkarır.

    istemci: LLMIstemci örneği. Tek çağrı yapılır.
    dil    : istem dili, "tr" veya "en". Hangisinin daha iyi olduğu
             ÖLÇÜLECEK; varsayılan şu an tr, ölçüm sonrası değişebilir.
    """
    sonuc = AnlamaSonucu()
    u = ayristirma.ustveri

    # --- Katman 1: daraltma -------------------------------------------------
    adaylar = aday_turler(ayristirma.aile, bool(u.ilgi), bool(u.ekler))
    sonuc.adaylar = adaylar

    # --- SDP: sayıdan okunabiliyor mu ---------------------------------------
    sdp_kodu = sdp_sayidan_oku(u.sayi)
    if sdp_kodu:
        sonuc.siniflandirma.sdp = SdpKodu(kod=sdp_kodu, kaynak_sayidan_mi=True)
        sonuc.kanit["siniflandirma.sdp"] = _kanit(
            u.sayi or "", KanitYontemi.REGEX, 1.0,
            "Sayının üçüncü bölümünden okundu",
        )

    # --- Tek aday varsa modele hiç sorma ------------------------------------
    if len(adaylar) == 1 and sdp_kodu:
        tur = ETIKETTEN_SEMAYA.get(adaylar[0], adaylar[0])
        sonuc.siniflandirma.belge_turu = GelenTur(tur)
        sonuc.siniflandirma.gerekce = (
            "Gönderen uyumu, ilgi ve ek varlığı tek türe işaret ediyor; "
            "model çağrısı yapılmadı."
        )
        sonuc.kanit["siniflandirma.belge_turu"] = _kanit(
            adaylar[0], KanitYontemi.KURAL, 1.0,
            "kota.json kurallarıyla tek adaya indirildi",
        )
        return sonuc

    # --- Katman 2: tek LLM çağrısı ------------------------------------------
    # --- SDP 2. hat: örnek konu eşleştirme (deterministik) ------------------
    #
    # Sıra önemli: sayıdan OKU -> örnek konuyla EŞLEŞTİR -> modele SOR.
    # Her adım bir öncekinden zayıf, o yüzden sona bırakılıyor.
    sdp_aday = (sdp_adaylari(u.muhatap.ham, u.muhatap.birim)
                if sdp_kodu is None else [])
    if sdp_kodu is None and sdp_aday:
        from sdp_katalog import konudan_kod_bul

        eslesen, oran = konudan_kod_bul(govde, [a[0] for a in sdp_aday])
        if eslesen:
            sonuc.siniflandirma.sdp = SdpKodu(kod=eslesen, kaynak_sayidan_mi=False)
            sonuc.kanit["siniflandirma.sdp"] = _kanit(
                eslesen, KanitYontemi.SOZLUK, min(oran, 0.95),
                f"Muhatap birimin {len(sdp_aday)} kodundan örnek konu "
                f"eşleşmesiyle bulundu (benzerlik {oran:.2f})",
            )
            sdp_kodu = eslesen

    sdp_sorulacak = sdp_kodu is None
    istem = istem_kur(govde, ayristirma, adaylar, sdp_sorulacak, dil, sdp_aday)
    sema = sema_kur(adaylar, sdp_sorulacak, sdp_aday)

    try:
        cevap = istemci.metin_uret(
            istem=istem,
            sistem_istemi=SISTEM_ISTEMI_EN if dil == "en" else SISTEM_ISTEMI,
            ek={"response_format": sema},
        )
    except Exception as e:  # noqa: BLE001
        sonuc.uyarilar.append(f"LLM çağrısı başarısız: {type(e).__name__}: {e}")
        return sonuc

    sonuc.llm_kullanildi = True
    sonuc.dil = dil
    sonuc.sure_ms = cevap.sure_ms
    sonuc.token = cevap.token.toplam
    sonuc.model = cevap.model

    if cevap.kesildi_mi:
        # Yarım JSON ayrıştırılamaz; ayrıştırılsa bile eksik veri sessizce
        # kabul edilmiş olur.
        sonuc.uyarilar.append("Model çıktısı token sınırında kesildi")
        return sonuc

    try:
        veri = json.loads(cevap.metin)
    except json.JSONDecodeError as e:
        sonuc.uyarilar.append(f"Model çıktısı JSON değil: {e}")
        return sonuc

    _cevabi_isle(veri, sonuc, sdp_sorulacak)
    return sonuc


def _kirp(deger: object, sinir: int) -> str | None:
    """Şemanın uzunluk sınırına kırpar.

    NEDEN — ilk ölçümde 8 belge tamamen KAYBOLDU: model 500 karakteri aşan
    gerekçe yazınca Pydantic ValidationError fırlatıyor, çağrı sonucu
    çöpe gidiyor ve belge sınıflandırılmamış sayılıyordu. Doğru cevabı
    uzun yazdığı için kaybetmek saçma.

    Şemaya maxLength eklendi (asıl çözüm); bu kırpma ikinci savunma
    hattı — sağlayıcı maxLength'i uygulamayabilir.
    """
    if not deger:
        return None
    metin = str(deger).strip()
    if not metin:
        return None
    return metin if len(metin) <= sinir else metin[: sinir - 1].rstrip() + "…"


def _cevabi_isle(veri: dict, sonuc: AnlamaSonucu, sdp_sorulacak: bool) -> None:
    """Model cevabını şemaya yazar. Tanınmayan değer sessizce kabul edilmez."""
    ham_tur = (veri.get("belge_turu") or "").strip()
    if ham_tur:
        try:
            sonuc.siniflandirma.belge_turu = GelenTur(ham_tur)
        except ValueError:
            sonuc.uyarilar.append(f"Model tanınmayan tür verdi: {ham_tur!r}")
        else:
            sonuc.siniflandirma.gerekce = _kirp(
                veri.get("belge_turu_gerekcesi"), 500
            )
            sonuc.kanit["siniflandirma.belge_turu"] = _kanit(
                sonuc.siniflandirma.gerekce or ham_tur,
                KanitYontemi.LLM,
                veri.get("belge_turu_guveni", 0.0),
            )

    talep = _kirp(veri.get("talep"), 500)
    if talep:
        sonuc.icerik.talep = talep
        sonuc.kanit["icerik.talep"] = _kanit(talep, KanitYontemi.LLM, 0.75)

    ozet = _kirp(veri.get("ozet"), 500)
    if ozet:
        sonuc.icerik.ozet = ozet

    if sdp_sorulacak:
        # SdpKodu.kod en fazla 20 karakter. Model ilk ölçümde
        # '440.11.12.10.02.02.00.03.06' üretti ve belge kayboldu.
        kod = _kirp(veri.get("sdp_kodu"), 20)
        if kod and len(kod) <= 20:
            # kaynak_sayidan_mi=False: tahmin. Bu ayrım Parça 6'da ablasyon
            # satırı üretiyor — iki yolun isabeti ayrı ölçülebilir.
            sonuc.siniflandirma.sdp = SdpKodu(kod=kod, kaynak_sayidan_mi=False)
            sonuc.kanit["siniflandirma.sdp"] = _kanit(
                kod, KanitYontemi.LLM, 0.50,
                "Sayıda SDP kodu yok; konudan tahmin edildi",
            )

    for ham in veri.get("varliklar") or []:
        tip_ham = (ham.get("tip") or "").strip()
        deger = (ham.get("deger") or "").strip()
        if not deger:
            continue
        try:
            tip = VarlikTipi(tip_ham)
        except ValueError:
            tip = VarlikTipi.DIGER
        # kisisel_veri tipten OTOMATİK türer (veri_yapisi.py); modelin
        # işaretlemeyi unutması mümkün değil.
        sonuc.icerik.varliklar.append(Varlik(tip=tip, deger=deger, ham=deger))
