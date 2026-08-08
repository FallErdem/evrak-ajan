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

# Paragraf yapısının aileye göre açıklaması. Yalnızca cümle sayısı vermek
# yetmiyor; model paragrafın NE ANLATACAĞINI bilmezse iki paragrafı da aynı
# şeye ayırıyor. ADIM 1'de ölçüldü.
_PARAGRAF_ACIKLAMA = {
    "belge_talebi":     ["talebin konusu, dayanağı ve gerekçesi"],
    "itiraz":           ["önceki karar ve itiraz gerekçesi", "talep"],
    "sikayet":          ["sorunun tanımı ve süresi", "önceki başvuru ve talep"],
    "bilgi_edinme":     ["kanuni dayanak ve talep", "istenen ayrıntı ve bildirim yolu"],
    "belge_cevabi":     ["talebin değerlendirilmesi ve sonucu",
                         "teslim/gönderim koşulları"],
    "kaynak_talebi":    ["mevcut durum ve sonucu", "amaç ve talep"],
    "isbirligi_talebi": ["ortak işin tanımı", "talep"],
    "bilgilendirme":    ["uygulama, kaynağı ve kapsamı", "muhataptan istenenler"],
    "gorus_talebi":     ["konu ve oluşan tereddüt", "talep"],
    "ust_yazi":         ["dayanak ve dönem", "gönderilen eklerin bildirilmesi",
                         "muhataptan istenenler"],
    "tekit":            ["ilgiye atıf ve mevcut durum", "talep ve süre"],
    "olur":             ["konu ve gerekçe", "olur talebi"],
}

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
        return (f"{g['ad']} ({g['bolum']}, {g['sinif']}. sınıf, "
                f"öğrenci no {g['ogrenci_no']})")
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
    sayilar = e["paragraf_cumle_sayilari"]
    aciklamalar = _PARAGRAF_ACIKLAMA.get(e["aile"], [""] * len(sayilar))
    satirlar = []
    for i, n in enumerate(sayilar):
        ac = aciklamalar[i] if i < len(aciklamalar) else ""
        son = " (son cümle kapanış cümlesidir)" if i == len(sayilar) - 1 else ""
        satirlar.append(f"  {i+1}. paragraf — {n} cümle — {ac}{son}")
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
