"""Şartname render — etiketi modele verilecek metne çevirir.

    etiket_001.json  ->  sartname_001.txt  ->  (4.4) LLM  ->  gövde metni

BU DOSYADA LLM YOK. JSON'u düz metne çeviren biçimlendirme katmanı.

ÜÇ TASARIM KARARI

1. YALNIZCA GÖVDEYE GİRECEK ALANLAR ŞARTNAMEYE GİRER.
   Etikette `muhatap_makam`, `dagitim`, `sayi`, `detsis_no` gibi alanlar
   var ama bunları şablon yazacak, model değil. Şartnameye koyarsak
   model gövdeye sızdırır — ADIM 1'de ölçüldü: model başlık kurmaya
   başlıyordu, bu yüzden "YAZMAYACAKLARIN" listesi eklendi.

2. TEK TALİMAT + GEÇERSİZ KILMA BLOĞU.
   Dört yazar tipi var (kurum, vatandaş, öğrenci, özel tüzel kişi) ve
   dilleri farklı. Dört ayrı talimat dosyası tutmak yerine tek dosya +
   tipe göre geçersiz kılma bloğu kullanılıyor. Sebep: yöntem ADIM 1'de
   ölçüldü, 3 vatandaş belgesinin 3'ünde de tuttu.

3. ŞARTNAME DOSYAYA YAZILIR.
   4.4'te bir belge bozuk çıkarsa "modele tam olarak ne gitti" sorusunun
   cevabı dosyada durur. Etiketten yeniden üretip tahmin etmek yerine
   dosya açılır.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

# =============================================================================
# BÖLÜM 1 — SÖZLÜKLER
# =============================================================================

# Belge türünün Türkçe adı. Etiketteki makine adı ("bilgilendirme") modele
# olduğu gibi verilirse ne tür bir yazı olduğu tam anlaşılmıyor.
_TUR_ADI = {
    "dilekce": "vatandaş dilekçesi",
    "sikayet": "şikâyet dilekçesi",
    "bilgi_edinme": "bilgi edinme başvurusu",
    "itiraz": "itiraz dilekçesi",
    "bilgilendirme": "bilgilendirme yazısı (kurumdan kuruma)",
    "talep_yazisi": "talep yazısı (kurumdan kuruma)",
    "cevap_yazisi": "cevap yazısı (kurumdan kuruma)",
    "gorus_talebi": "görüş talebi yazısı",
    "ust_yazi": "üst yazı (ek gönderimi)",
    "tekit_yazisi": "tekit yazısı (hatırlatma)",
    "olur_yazisi": "olur yazısı (makam onayı talebi)",
}

# Hiyerarşi yönünün modele anlatılışı. "alt" gibi tek kelime yeterli değil:
# yönün KİMİN kime göre olduğu belirsiz kalıyor ve model ters çeviriyor.
_YON_ACIKLAMA = {
    "ust": "ÜST — muhatap, gönderenin üstündedir",
    "ayni": "AYNI DÜZEY — aralarında hiyerarşi yoktur",
    "alt": "ALT — muhatap, gönderenin altındadır",
    "gercek_kisi_yazari": "GERÇEK KİŞİ — yazan bir vatandaştır",
    "ozel_tuzel": "ÖZEL HUKUK TÜZEL KİŞİSİ — yazan bir şirket/dernektir",
    "yok": "—",
}

# Kapanış türünün modele anlatılışı.
_KAPANIS_ACIKLAMA = {
    "arz": 'ARZ — metin "arz ederim." ile bitecek',
    "rica": 'RİCA — metin "rica ederim." ile bitecek',
    "karma": 'KARMA — metin "arz/rica ederim." ile bitecek (dağıtımlı yazı)',
    "sunulur": 'SUNULUR — metin "Bilgilerinize sunulur." ile bitecek',
}

# Paragraf İŞLEVLERİ — her paragraf farklı bir soruya cevap verir.
#
# DOLGU METNİ ENGELLEYEN ASIL MEKANİZMA BU. Yalnızca cümle sayısı verilirse
# model uzun belgeyi aynı bilgiyi iki kez söyleyerek dolduruyor — ve bu,
# uydurmadan daha tehlikeli çünkü kural denetleyicisine takılmaz: metinde
# şartname dışı hiçbir bilgi yok, sadece tekrar var.
#
# Yapı: gövde işlevleri sırayla alınır, SON işlev her zaman en sonda durur
# (kapanış cümlesi orada olacak).
_PARAGRAF_ISLEV = {
    "belge_talebi": {
        "tek": "talebin konusu, dayanağı ve gerekçesi",
        "govde": ["talebin konusu ve dayanağı"],
        "son": "talep ve gerekçe"},
    "itiraz": {
        "tek": "önceki karar, itiraz gerekçesi ve talep",
        "govde": ["önceki karar ve sonucu", "itiraz gerekçesi"],
        "son": "yeniden değerlendirme talebi"},
    "sikayet": {
        "tek": "sorun, süresi ve talep",
        "govde": ["sorunun tanımı ve süresi", "sorunun yol açtığı durum"],
        "son": "önceki başvuru ve talep"},
    "bilgi_edinme": {
        "tek": "kanuni dayanak, talep ve bildirim yolu",
        "govde": ["kanuni dayanak ve talep"],
        "son": "istenen ayrıntı ve bildirim yolu"},
    "belge_cevabi": {
        "tek": "talebin değerlendirilmesi ve sonucu",
        "govde": ["talebin değerlendirilmesi ve yapılan inceleme",
                  "değerlendirmenin sonucu",
                  "işlem ayrıntıları ve kapsam"],
        "son": "teslim/bildirim koşulları ve irtibat"},
    "kaynak_talebi": {
        "tek": "mevcut durum, amaç ve talep",
        "govde": ["mevcut durum ve sonucu"],
        "son": "amaç ve talep"},
    "isbirligi_talebi": {
        "tek": "ortak işin tanımı ve talep",
        "govde": ["ortak işin tanımı"],
        "son": "talep"},
    "bilgilendirme": {
        "tek": "uygulama, kapsamı ve istenenler",
        "govde": ["uygulamanın ne olduğu, kaynağı ve yürürlüğü",
                  "kapsamı ve kapsam dışında kalanlar",
                  "uygulama esasları ve geçiş hükmü"],
        "son": "muhataptan istenenler, süre ve irtibat"},
    "gorus_talebi": {
        "tek": "konu, tereddüt ve talep",
        "govde": ["konu ve oluşan tereddüt"],
        "son": "görüş talebi"},
    "ust_yazi": {
        "tek": "dayanak, ekler ve istenenler",
        "govde": ["dayanak, dönem ve kapsam",
                  "gönderilen eklerin bildirilmesi",
                  "eklerin içeriği ve kapsamı"],
        "son": "muhataptan istenenler, süre ve irtibat"},
    "tekit": {
        "tek": "ilgiye atıf, mevcut durum ve talep",
        "govde": ["ilgiye atıf ve mevcut durum"],
        "son": "talep ve süre"},
    "olur": {
        "tek": "konu, gerekçe ve olur talebi",
        "govde": ["konu ve gerekçe"],
        "son": "olur talebi"},
}


def _paragraf_islevleri(aile: str, adet: int) -> list[str]:
    """N paragraf için N işlev döndürür.

    Gövde işlevleri sırayla alınır, son işlev her zaman en sona konur.
    Gövde havuzu yetmezse son işlevden önce genel bir ara işlev eklenir —
    ama bu durum tasarımda oluşmuyor: uzun katman ailelerinin gövde havuzu
    3, azami paragraf sayısı 4.
    """
    t = _PARAGRAF_ISLEV.get(aile)
    if not t:
        return [""] * adet
    if adet == 1:
        return [t["tek"]]
    govde = t["govde"][:adet - 1]
    while len(govde) < adet - 1:
        govde.append("konunun ayrıntıları")
    return govde + [t["son"]]


# Üslup, yazar tipine göre.
_USLUP = {
    "kurum": "resmî, kurumsal",
    "vatandas": "resmî ve saygılı, ama hukuk dili taklidi yapılmaz; "
                "ağdalı bürokratik kalıplar kullanılmaz",
    "ogrenci": "resmî ve saygılı; öğrenci ağzından, ama samimi değil",
    "ozel_tuzel": "resmî, kurumsal; şirket ağzından",
}


# =============================================================================
# BÖLÜM 2 — GEÇERSİZ KILMA BLOKLARI
# =============================================================================

_ORTAK_GECERSIZ = """  - "KİP — ŞAHSİLEŞTİRME YASAĞI" GEÇERSİZ. {kim} kendi ağzından
    yazar; birinci tekil şahıs KULLANILIR.
    Doğru: "talep ediyorum", "tarafıma verilmesini", "ekte sunuyorum"

  - "KURUMLARA ATIF" bölümünün ilk maddesi GEÇERSİZ. Yazan taraf bir
    kamu kurumu değildir; "Müdürlüğümüz", "Başkanlığımız" gibi ifadeler
    KULLANILMAZ. Muhatap kuruma "Müdürlüğünüz", "Başkanlığınız",
    "Rektörlüğünüz" denebilir.

  - "TALEBİ TEK YERDE İFADE ET" GEÇERLİDİR, aynen uygulanır.
  - "BİLGİ UYDURMA" yasağı GEÇERLİDİR, aynen uygulanır.
  - "KAPANIŞ CÜMLESİ" kuralları GEÇERLİDİR."""

_GECERSIZ_KILMA = {
    "vatandas": _ORTAK_GECERSIZ.format(kim="Dilekçeyi bir vatandaş"),
    "ogrenci": _ORTAK_GECERSIZ.format(kim="Dilekçeyi kayıtlı bir öğrenci")
    + """

  - Öğrenci kendini tanıtır: bölüm, sınıf ve öğrenci numarası metinde
    geçmelidir ("... Bölümü {n}. sınıf öğrencisiyim" gibi).""",
    "ozel_tuzel": _ORTAK_GECERSIZ.format(kim="Yazıyı bir şirket yetkilisi")
    + """

  - Şirket kendinden "Şirketimiz" diye söz edebilir.
  - Birinci ÇOĞUL şahıs da serbesttir ("talep ediyoruz").""",
}

_BASLIK_GECERSIZ = {
    "vatandas": "BU BELGE BİR KURUM YAZISI DEĞİL, VATANDAŞ DİLEKÇESİDİR",
    "ogrenci": "BU BELGE BİR KURUM YAZISI DEĞİL, ÖĞRENCİ DİLEKÇESİDİR",
    "ozel_tuzel": "BU BELGE BİR KAMU KURUMU YAZISI DEĞİL, ÖZEL ŞİRKET YAZISIDIR",
}


# =============================================================================
# BÖLÜM 3 — RENDER
# =============================================================================


def _tur_adi(e: dict) -> str:
    """Belge türünün modele söylenen adı yazar tipine göre değişir.

    Ölçülen hata: öğrenci dilekçesine "vatandaş dilekçesi" deniyordu.
    Model üslubu buna göre ayarlıyor; yanlış etiket yanlış dil üretir.
    """
    ad = _TUR_ADI.get(e["belge_turu"], e["belge_turu"])
    if e["yazan_tipi"] == "ogrenci":
        return ad.replace("vatandaş", "öğrenci")
    if e["yazan_tipi"] == "ozel_tuzel":
        return ad.replace("vatandaş dilekçesi", "şirket başvuru yazısı")
    return ad


def _yon_adi(e: dict) -> str:
    if e["yazan_tipi"] == "ogrenci":
        return "GERÇEK KİŞİ — yazan kayıtlı bir öğrencidir"
    if e["yazan_tipi"] == "ozel_tuzel":
        return "ÖZEL HUKUK TÜZEL KİŞİSİ — yazan bir şirkettir"
    return _YON_ACIKLAMA.get(e["hiyerarsi_yonu"], "—")


def _gonderen_satiri(e: dict) -> str:
    g = e["gonderen"]
    if g["tip"] == "ogrenci":
        duzey = (f"{g['sinif']}. sınıf" if g.get("sinif")
                 else g.get("ogrenim_duzeyi", "kayıtlı öğrenci"))
        return f"{g['ad']} ({g['bolum']}, {duzey}, öğrenci no {g['ogrenci_no']})"
    if g["tip"] == "gercek_kisi":
        return f"{g['ad']} (vatandaş)"
    if g["tip"] == "ozel_tuzel_kisi":
        return f"{g['kurum_adi']} (özel hukuk tüzel kişisi)"
    return g["kurum_adi"]


def _muhatap_satiri(e: dict) -> str:
    """Muhatap modele BİLGİ olarak verilir, yazması için değil.

    Model muhatap satırını yazmayacak (şablon yazacak) ama kime yazdığını
    bilmezse üslubu ayarlayamıyor: bakanlığa yazılan yazı ile vatandaşa
    yazılan cevap aynı dille yazılamaz.
    """
    if e["muhatap_makam"] == "DAĞITIM YERLERİNE":
        return "dağıtım yerleri (çok muhataplı yazı)"
    m = e["muhatap_makam"]
    if e.get("muhatap_parantez"):
        m += f" ({e['muhatap_parantez']})"
    return m


def _sar(metin: str, genislik: int, girinti: str) -> str:
    """Uzun değeri KELİME SINIRINDAN sarar.

    Karakter sayısıyla kesmek "başvuru yapı / lmıştır" gibi bölünmelere
    yol açıyordu; model bunu ayrı iki kelime sanabilir.
    """
    satirlar = textwrap.wrap(metin, width=genislik) or [metin]
    return ("\n" + girinti).join(satirlar)


def _somut_bloku(e: dict) -> str:
    satirlar = []
    for anahtar, deger in e["somut_bilgiler"].items():
        girinti = " " * 22
        satirlar.append(f"  - {anahtar:<16}: {_sar(str(deger), 52, girinti)}")
    return "\n".join(satirlar)


def _paragraf_bloku(e: dict) -> str:
    """Paragraf planı. Uzun katmanda HANGİ ALANIN NEREYE gideceğini de yazar.

    Ölçülen sorun: yalnızca cümle sayısı ve işlev verilince bazı alanların
    hangi paragrafa gireceği belirsiz kalıyordu ("Süre" alanı üç ayrı
    paragrafa da uyuyordu). Model ya bir alanı düşürüyor ya iki paragrafta
    tekrarlıyordu.

    Alan listesi verildiğinde her paragrafta alan sayısı cümle sayısına eşit
    olur ve yerleşim belirsizliği ortadan kalkar.
    """
    sayilar = e["paragraf_cumle_sayilari"]
    islevler = _paragraf_islevleri(e["aile"], len(sayilar))
    gruplar = e.get("paragraf_alanlari")
    satirlar = []
    for i, n in enumerate(sayilar):
        son = "  (son cümle kapanış cümlesidir)" if i == len(sayilar) - 1 else ""
        satirlar.append(f"  {i+1}. paragraf — {n} cümle — {islevler[i]}{son}")
        if gruplar and i < len(gruplar):
            satirlar.append(f"        kullanılacak alanlar: "
                            f"{', '.join(gruplar[i])}")
    return "\n".join(satirlar)


def _son_kontrol(e: dict) -> str:
    """Kontrol listesi ŞARTNAMEDEN SONRA gelir.

    ADIM 1'de listeyi şartnameden önce koymuştum; model listeyi okuduktan
    sonra 200 token daha okuyup yazmaya başlıyor ve maddeleri kaçırıyordu.
    Uzun istemlerde model son satırları en iyi hatırlıyor.
    """
    kapanis = e["beklenen_kapanis"]
    beklenen = {
        "arz": '"arz ederim." ',
        "rica": '"rica ederim." ',
        "karma": '"arz/rica ederim." ',
        "sunulur": '"Bilgilerinize sunulur." ',
    }[kapanis]

    maddeler = [
        "Somut bilgilerin hepsi kullanıldı mı",
        "Somut bilgilerde olmayan hiçbir şey eklenmedi mi",
    ]
    if e["yazan_tipi"] == "kurum":
        maddeler.append('"-dik", "-iz", "-yoruz" ekli fiil var mı — '
                        "olmamalı (kapanış hariç)")
    else:
        maddeler.append("Metin yazan kişinin ağzından mı — birinci tekil "
                        "şahıs olmalı")
        maddeler.append('"Müdürlüğümüz" gibi kurum ifadesi var mı — OLMAMALI')
    maddeler.append("Gönderenin veya muhatabın adı gövdede geçiyor mu — geçmemeli")
    maddeler.append(f"Kapanış tam olarak {beklenen}mi")
    maddeler.append("Kapanıştan önce üç nokta veya boş satır var mı — olmamalı")
    if e["ilgi"]:
        maddeler.append("İlk cümle ilgiye atıfla mı başlıyor")
    if e["ek"]:
        maddeler.append("Eke metin içinde atıf yapıldı mı")
    else:
        maddeler.append('Metinde "ek", "ekte", "ilişikte" geçiyor mu — GEÇMEMELİ')
    n = len(e["paragraf_cumle_sayilari"])
    maddeler.append(f"{n} paragraf var mı, cümle sayıları tutuyor mu, "
                    f"aralarında boş satır var mı")

    liste = "\n".join(f"{i+1}. {m}" for i, m in enumerate(maddeler))
    return f"YAZMADAN ÖNCE SON KONTROL:\n{liste}"


def sartname_uret(e: dict) -> str:
    """Etiketi şartname metnine çevirir (talimat bloğu HARİÇ)."""
    parcalar = []

    # --- geçersiz kılma bloğu (varsa) --------------------------------------
    yazan = e["yazan_tipi"]
    if yazan in _GECERSIZ_KILMA:
        cizgi = "=" * 64
        parcalar.append(
            f"{cizgi}\nDİKKAT — {_BASLIK_GECERSIZ[yazan]}\n{cizgi}\n"
            f"Yukarıdaki talimatın şu maddeleri BU BELGE İÇİN GEÇERSİZDİR:\n\n"
            f"{_GECERSIZ_KILMA[yazan]}\n{cizgi}\n"
        )

    # --- şartname ----------------------------------------------------------
    satirlar = [
        "--- SARTNAME ---",
        f"Belge türü        : {_tur_adi(e)}",
        f"Gönderen          : {_gonderen_satiri(e)}",
        f"Muhatap           : {_muhatap_satiri(e)}",
        f"Hiyerarşi yönü    : {_yon_adi(e)}",
        f"Beklenen kapanış  : {_KAPANIS_ACIKLAMA[e['beklenen_kapanis']]}",
        f"İlgi              : {'var' if e['ilgi'] else 'yok'}",
    ]
    if e["ek"]:
        satirlar.append(f"Ek                : var ({e['ek']['aciklama']})")
    else:
        satirlar.append("Ek                : yok")
    satirlar += [
        "",
        "Somut bilgiler (yalnızca bunları kullan, bunların dışına çıkma):",
        _somut_bloku(e),
        "",
        "Paragraf yapısı :",
        _paragraf_bloku(e),
        "",
        "Cümle yoğunluğu : her cümlede en fazla iki bilgi kullan",
        f"Üslup           : "
        f"{_sar(_USLUP.get(yazan, 'resmî, kurumsal'), 52, ' ' * 18)}",
        "--- SARTNAME SONU ---",
    ]
    parcalar.append("\n".join(satirlar))
    parcalar.append(_son_kontrol(e))
    parcalar.append("Çıktın yalnızca metin gövdesi olsun. Başka hiçbir şey yazma.")
    return "\n\n".join(parcalar)


def istem_kur(talimat: str, e: dict) -> str:
    """Talimat + şartname = modele gidecek tam istem.

    Şartname SONA konuyor: uzun istemlerde model sondaki içeriği daha iyi
    tutuyor ve asıl değişken olan kısım şartname. Talimat sabit kaldığı
    için başta durması sorun değil.
    """
    return talimat.rstrip() + "\n\n" + sartname_uret(e).strip() + "\n"


def etiket_yukle(yol: str | Path) -> dict:
    return json.loads(Path(yol).read_text(encoding="utf-8"))
