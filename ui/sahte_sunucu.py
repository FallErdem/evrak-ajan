"""
Sahte backend — api_sozlesmesi.md sürüm 2026-08-18-h'yi gerçekler.

İçinde model yok; kayıtlı koşuları gerçekçi gecikmelerle oynatır.
Gerçek backend hazır olunca arayüzde değişen tek şey ortak.tsx'teki API sabiti.

Kurulum : pip install fastapi uvicorn python-multipart
Çalıştır: uvicorn sahte_sunucu:app --reload --port 8000
"""

import asyncio
import copy
import json
import pathlib
import random
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

SURUM = "2026-08-18-h"
HIZ = 1.0  # 0.3 yaparsan demo hızlanır

# ===========================================================================
# 11 ADIM · 8 BİLEŞEN · 2 AJAN  (sözleşme 2.2)
# ===========================================================================

DUGUMLER: list[dict] = [
    {"no": 1, "ad": "okuyucu", "baslik": "Okuyucu",
     "aciklama": "PDF'ten metin ve konum çıkarır",
     "motor": "arac", "bilesen": 1, "bilesen_adi": "Okuyucu", "satir": 1, "ajan": None,
     "temel_ms": 2300},
    {"no": 2, "ad": "ayristirici", "baslik": "Ayrıştırıcı",
     "aciklama": "Sayı, tarih, konu, muhatap, ilgi, imza alanlarına böler",
     "motor": "karma", "bilesen": 2, "bilesen_adi": "Ayrıştırıcı", "satir": 1, "ajan": None,
     "temel_ms": 1350},
    {"no": 3, "ad": "anlama", "baslik": "Anlama",
     "aciklama": "Belge türü, SDP, talep ve varlıkları tek çağrıda çıkarır",
     "motor": "llm", "bilesen": 3, "bilesen_adi": "Anlama", "satir": 1, "ajan": None,
     "temel_ms": 3900},
    {"no": 4, "ad": "eksik_bilgi", "baslik": "Eksik Bilgi Tespiti",
     "aciklama": "Şema, kural ve çıkarım katmanlarında eksikleri bulur",
     "motor": "karma", "bilesen": 4, "bilesen_adi": "Denetçi", "satir": 2,
     "ajan": "AJAN 1 · Denetçi", "temel_ms": 3100},
    {"no": 5, "ad": "mevzuat_danismani", "baslik": "Mevzuat Danışmanı",
     "aciklama": "Dayanak maddesini getirir ve metinde doğrular",
     "motor": "karma", "bilesen": 4, "bilesen_adi": "Denetçi", "satir": 2,
     "ajan": "AJAN 1 · Denetçi", "temel_ms": 2400},
    {"no": 6, "ad": "ozetleyici", "baslik": "Özetleyici",
     "aciklama": "En fazla 1500 karakter, yalnızca belgedeki bilgi",
     "motor": "llm", "bilesen": 5, "bilesen_adi": "Özetleyici", "satir": 3, "ajan": None,
     "temel_ms": 1900},
    {"no": 7, "ad": "karar_verici", "baslik": "Karar Verici",
     "aciklama": "Hangi resmî yazının yazılacağına karar verir",
     "motor": "llm", "bilesen": 6, "bilesen_adi": "Yazar", "satir": 4,
     "ajan": "AJAN 2 · Yazar", "temel_ms": 1100},
    {"no": 8, "ad": "taslak", "baslik": "Taslak",
     "aciklama": "Resmî yazı taslağını üretir",
     "motor": "llm", "bilesen": 6, "bilesen_adi": "Yazar", "satir": 4,
     "ajan": "AJAN 2 · Yazar", "temel_ms": 4100},
    {"no": 9, "ad": "uslup_denetleyici", "baslik": "Üslup Denetleyici",
     "aciklama": "40 kural, deterministik, model çağırmaz",
     "motor": "kural", "bilesen": 6, "bilesen_adi": "Yazar", "satir": 4,
     "ajan": "AJAN 2 · Yazar", "temel_ms": 300},
    {"no": 10, "ad": "yonlendirici", "baslik": "Yönlendirici",
     "aciklama": "3 kurum, 35 birim; SDP tablosu veya çıkarım",
     "motor": "karma", "bilesen": 7, "bilesen_adi": "Yönlendirici", "satir": 5, "ajan": None,
     "temel_ms": 1600},
    {"no": 11, "ad": "guven_kapisi", "baslik": "Güven Kapısı",
     "aciklama": "Otomatik onay mı, insan onayı mı",
     "motor": "arac", "bilesen": 8, "bilesen_adi": "Güven kapısı", "satir": 5, "ajan": None,
     "temel_ms": 40},
]

DUGUM_HARITASI = {d["no"]: d for d in DUGUMLER}
PARALEL_GRUPLAR = [[4, 5]]

# Her adımın evrak sözlüğüne yazdığı alanlar
ADIM_CIKTISI = {
    1:  lambda s: {"sayfa_sayisi": s["sayfa_sayisi"], "karakter": s["karakter"],
                   "girdi_tipi": s["girdi_tipi"]},
    2:  lambda s: {"ustveri": s["ustveri"]},
    3:  lambda s: {"belge_turu": s["belge_turu"], "sdp": s["sdp"],
                   "varliklar": s["varliklar"], "talep": s["talep"]},
    4:  lambda s: {"eksikler": s["eksikler"]},
    5:  lambda s: {"mevzuat": s["mevzuat"]},
    6:  lambda s: {"ozet": s["ozet"]},
    7:  lambda s: {"karar": s["karar"]},
    8:  lambda s: {"taslak": s["taslak"]},
    9:  lambda s: {"uslup_bulgulari": s["uslup_bulgulari"],
                   "linter_tur_sayisi": s["linter_tur_sayisi"]},
    10: lambda s: {"yonlendirme": s["yonlendirme"]},
    11: lambda s: {"guven_kapisi": s["guven_kapisi"]},
}

CIKTI_ANAHTARLARI = [
    "sayfa_sayisi", "karakter", "girdi_tipi", "ustveri", "belge_turu", "sdp",
    "varliklar", "talep", "eksikler", "mevzuat", "ozet", "karar", "taslak",
    "uslup_bulgulari", "linter_tur_sayisi", "yonlendirme", "guven_kapisi",
]

DURUM_ETIKET = {
    "ALINDI": "Alındı", "ISLENIYOR": "İşleniyor",
    "INSAN_ONAYI_BEKLIYOR": "İnsan onayı bekliyor",
    "EKSIK_BILGI_BEKLIYOR": "Eksik bilgi bekliyor",
    "OTOMATIK_ONAYLANDI": "Otomatik onaylandı", "ONAYLANDI": "Onaylandı",
    "REDDEDILDI": "Reddedildi", "HATA": "Hata",
}

SONUCLANMIS = ("ONAYLANDI", "REDDEDILDI", "OTOMATIK_ONAYLANDI")
ACIK = ("INSAN_ONAYI_BEKLIYOR", "EKSIK_BILGI_BEKLIYOR")

# Sözleşme 7.3 — kişisel sayılan varlık tipleri
KISISEL_TIPLER = {"kisi", "tckn", "telefon", "eposta", "adres", "iban",
                  "plaka", "dogum_tarihi"}

# ===========================================================================
# BİRİMLER
# veri/kurumlar/birimler*.csv → birimler.json (elle düzenlenmez).
# Dosya sunucunun yanındaysa oradan okunur; yoksa aşağıdaki gömülü kopya
# kullanılır. Böylece JSON yeniden üretildiğinde sunucu koduna dokunulmaz.
# ===========================================================================

BIRIM_DOSYASI = pathlib.Path(__file__).with_name("birimler.json")

GOMULU_BIRIMLER: list[dict] = [{'kod': 'yenimahalle_belediyesi',
  'ad': 'Yenimahalle Belediye Başkanlığı',
  'kurum': 'Yenimahalle Belediye Başkanlığı',
  'kurum_kodu': 'yenimahalle_belediyesi',
  'ust_birim_kodu': None,
  'seviye': 0,
  'gorev_alani': 'Ankara Büyükşehir Belediyesi sınırları içinde yer alan bir ilçe belediyesidir. '
                 '5393 sayılı Belediye Kanunu m.14 kapsamında imar, kentsel altyapı, çevre ve '
                 'çevre sağlığı, temizlik ve katı atık, zabıta, park ve yeşil alanlar, sosyal '
                 'hizmet ve yardım ile nikâh hizmetlerini yürütür. Karar organları belediye '
                 'meclisi, belediye encümeni ve belediye başkanıdır.',
  'sdp_kodlari': ['010.06', '051', '602.04'],
  'vatandas_yogunlugu': 'dusuk',
  'imza_unvani': 'Belediye Başkanı',
  'detsis_no': '65859045',
  'hedef_olabilir': True},
 {'kod': 'baskan_yrd_1',
  'ad': 'Belediye Başkan Yardımcılığı 1',
  'kurum': 'Yenimahalle Belediye Başkanlığı',
  'kurum_kodu': 'yenimahalle_belediyesi',
  'ust_birim_kodu': 'yenimahalle_belediyesi',
  'seviye': 1,
  'gorev_alani': 'Başkanlık makamı adına bağlı müdürlüklerin koordinasyonunu sağlar, havale ve '
                 'olur süreçlerini yürütür. Kendisine bağlı birimlerin yazışmalarını başkanlık '
                 'adına imzalar.',
  'sdp_kodlari': ['010.06', '051', '622.01'],
  'vatandas_yogunlugu': 'dusuk',
  'imza_unvani': 'Belediye Başkan Yardımcısı',
  'detsis_no': '73293321',
  'hedef_olabilir': False},
 {'kod': 'baskan_yrd_2',
  'ad': 'Belediye Başkan Yardımcılığı 2',
  'kurum': 'Yenimahalle Belediye Başkanlığı',
  'kurum_kodu': 'yenimahalle_belediyesi',
  'ust_birim_kodu': 'yenimahalle_belediyesi',
  'seviye': 1,
  'gorev_alani': 'Başkanlık makamı adına bağlı müdürlüklerin koordinasyonunu sağlar, havale ve '
                 'olur süreçlerini yürütür. Kendisine bağlı birimlerin yazışmalarını başkanlık '
                 'adına imzalar.',
  'sdp_kodlari': ['010.06', '051', '622.01'],
  'vatandas_yogunlugu': 'dusuk',
  'imza_unvani': 'Belediye Başkan Yardımcısı',
  'detsis_no': '15585774',
  'hedef_olabilir': False},
 {'kod': 'baskan_yrd_3',
  'ad': 'Belediye Başkan Yardımcılığı 3',
  'kurum': 'Yenimahalle Belediye Başkanlığı',
  'kurum_kodu': 'yenimahalle_belediyesi',
  'ust_birim_kodu': 'yenimahalle_belediyesi',
  'seviye': 1,
  'gorev_alani': 'Başkanlık makamı adına bağlı müdürlüklerin koordinasyonunu sağlar, havale ve '
                 'olur süreçlerini yürütür. Kendisine bağlı birimlerin yazışmalarını başkanlık '
                 'adına imzalar.',
  'sdp_kodlari': ['010.06', '051', '622.01'],
  'vatandas_yogunlugu': 'dusuk',
  'imza_unvani': 'Belediye Başkan Yardımcısı',
  'detsis_no': '90859947',
  'hedef_olabilir': False},
 {'kod': 'baskan_yrd_4',
  'ad': 'Belediye Başkan Yardımcılığı 4',
  'kurum': 'Yenimahalle Belediye Başkanlığı',
  'kurum_kodu': 'yenimahalle_belediyesi',
  'ust_birim_kodu': 'yenimahalle_belediyesi',
  'seviye': 1,
  'gorev_alani': 'Başkanlık makamı adına bağlı müdürlüklerin koordinasyonunu sağlar, havale ve '
                 'olur süreçlerini yürütür. Kendisine bağlı birimlerin yazışmalarını başkanlık '
                 'adına imzalar.',
  'sdp_kodlari': ['010.06', '051', '622.01'],
  'vatandas_yogunlugu': 'dusuk',
  'imza_unvani': 'Belediye Başkan Yardımcısı',
  'detsis_no': '13025030',
  'hedef_olabilir': False},
 {'kod': 'baskan_yrd_5',
  'ad': 'Belediye Başkan Yardımcılığı 5',
  'kurum': 'Yenimahalle Belediye Başkanlığı',
  'kurum_kodu': 'yenimahalle_belediyesi',
  'ust_birim_kodu': 'yenimahalle_belediyesi',
  'seviye': 1,
  'gorev_alani': 'Başkanlık makamı adına bağlı müdürlüklerin koordinasyonunu sağlar, havale ve '
                 'olur süreçlerini yürütür. Kendisine bağlı birimlerin yazışmalarını başkanlık '
                 'adına imzalar.',
  'sdp_kodlari': ['010.06', '051', '622.01'],
  'vatandas_yogunlugu': 'dusuk',
  'imza_unvani': 'Belediye Başkan Yardımcısı',
  'detsis_no': '66929355',
  'hedef_olabilir': False},
 {'kod': 'yazi_isleri',
  'ad': 'Yazı İşleri Müdürlüğü',
  'kurum': 'Yenimahalle Belediye Başkanlığı',
  'kurum_kodu': 'yenimahalle_belediyesi',
  'ust_birim_kodu': 'baskan_yrd_4',
  'seviye': 2,
  'gorev_alani': 'Belediye meclisi ve encümeninin gündem, karar ve tutanak işlemlerini yürütür. '
                 'Kurum genel evrak giriş-çıkış kayıtlarını tutar, birim arşivi ve belge talebi '
                 'işlemlerini yapar. Meclis kararlarının Ankara Büyükşehir Belediyesine ve ilgili '
                 'birimlere gönderilmesini sağlar.',
  'sdp_kodlari': ['105.04', '110.04', '010.06', '622.02', '805.02.05', '125'],
  'vatandas_yogunlugu': 'orta',
  'imza_unvani': 'Müdür',
  'detsis_no': '15986609',
  'hedef_olabilir': True},
 {'kod': 'mali_hizmetler',
  'ad': 'Mali Hizmetler Müdürlüğü',
  'kurum': 'Yenimahalle Belediye Başkanlığı',
  'kurum_kodu': 'yenimahalle_belediyesi',
  'ust_birim_kodu': 'baskan_yrd_3',
  'seviye': 2,
  'gorev_alani': 'Belediye bütçesinin hazırlanması, uygulanması ve kesin hesap işlemlerini '
                 'yürütür. Muhasebe, ön mali kontrol ve raporlama görevlerini yerine getirir. '
                 'Stratejik plan, performans programı ve faaliyet raporu çalışmalarını koordine '
                 'eder.',
  'sdp_kodlari': ['934.01', '602.04', '602.07', '855', '841.01'],
  'vatandas_yogunlugu': 'dusuk',
  'imza_unvani': 'Müdür',
  'detsis_no': '43195403',
  'hedef_olabilir': True},
 {'kod': 'gelirler',
  'ad': 'Gelirler Müdürlüğü',
  'kurum': 'Yenimahalle Belediye Başkanlığı',
  'kurum_kodu': 'yenimahalle_belediyesi',
  'ust_birim_kodu': 'baskan_yrd_3',
  'seviye': 2,
  'gorev_alani': 'Emlak vergisi, çevre temizlik vergisi ile belediye harç ve ücretlerinin tarh, '
                 'tahakkuk ve tahsil işlemlerini yürütür. Mükellef beyanlarını alır, borç '
                 'sorgulama, muafiyet ve yapılandırma taleplerini karşılar.',
  'sdp_kodlari': ['190.01.07', '855', '858', '622.01'],
  'vatandas_yogunlugu': 'yuksek',
  'imza_unvani': 'Müdür',
  'detsis_no': '30032784',
  'hedef_olabilir': True},
 {'kod': 'imar_sehircilik',
  'ad': 'İmar ve Şehircilik Müdürlüğü',
  'kurum': 'Yenimahalle Belediye Başkanlığı',
  'kurum_kodu': 'yenimahalle_belediyesi',
  'ust_birim_kodu': 'baskan_yrd_5',
  'seviye': 2,
  'gorev_alani': '1/1000 ölçekli uygulama imar planı ve plan değişikliği işlemlerini yürütür, askı '
                 've itiraz süreçlerini yönetir. İmar durum belgesi düzenler, yapı ruhsatı ve yapı '
                 'kullanma izin belgesi verir. İfraz, tevhid, yola terk gibi imar uygulamalarını '
                 've numarataj işlemlerini yapar.',
  'sdp_kodlari': ['115.02.01', '115.02.04', '115.02.08', '115.02.10', '115.01.06', '115.01.08'],
  'vatandas_yogunlugu': 'yuksek',
  'imza_unvani': 'Müdür',
  'detsis_no': '18426575',
  'hedef_olabilir': True},
 {'kod': 'yapi_kontrol',
  'ad': 'Yapı Kontrol Müdürlüğü',
  'kurum': 'Yenimahalle Belediye Başkanlığı',
  'kurum_kodu': 'yenimahalle_belediyesi',
  'ust_birim_kodu': 'baskan_yrd_4',
  'seviye': 2,
  'gorev_alani': 'İlçe sınırlarında denetim yaparak ruhsatsız ve ruhsata aykırı yapıları tespit '
                 'eder, yapı tatil tutanağı düzenleyerek encümene sevk eder. Yapı denetim '
                 'kuruluşlarının hakediş ve seviye tespit işlemlerini takip eder, kaçak yapı '
                 'ihbarlarını değerlendirir.',
  'sdp_kodlari': ['115.02.11', '641.04', '858', '622.01'],
  'vatandas_yogunlugu': 'yuksek',
  'imza_unvani': 'Müdür',
  'detsis_no': '53265760',
  'hedef_olabilir': True},
 {'kod': 'emlak_istimlak',
  'ad': 'Emlak ve İstimlak Müdürlüğü',
  'kurum': 'Yenimahalle Belediye Başkanlığı',
  'kurum_kodu': 'yenimahalle_belediyesi',
  'ust_birim_kodu': 'baskan_yrd_5',
  'seviye': 2,
  'gorev_alani': 'Belediye taşınmazlarının envanterini tutar; satış, kiralama, tahsis, devir ve '
                 'takas işlemlerini 2886 sayılı Kanun hükümlerine göre yürütür. Kamulaştırma ve '
                 'irtifak hakkı işlemlerini yapar, kira sözleşmelerini ve tahsilatını takip eder.',
  'sdp_kodlari': ['752.01', '756.01', '756.02', '641.04'],
  'vatandas_yogunlugu': 'orta',
  'imza_unvani': 'Müdür',
  'detsis_no': '87730597',
  'hedef_olabilir': True},
 {'kod': 'ruhsat_denetim',
  'ad': 'Ruhsat ve Denetim Müdürlüğü',
  'kurum': 'Yenimahalle Belediye Başkanlığı',
  'kurum_kodu': 'yenimahalle_belediyesi',
  'ust_birim_kodu': 'baskan_yrd_4',
  'seviye': 2,
  'gorev_alani': 'Sıhhi, gayrisıhhi ve umuma açık istirahat ve eğlence yerlerine işyeri açma ve '
                 'çalışma ruhsatı düzenler; ruhsat devir, tadil ve iptal işlemlerini yürütür. Ölçü '
                 've tartı aletlerinin beyan ve periyodik muayene işlemlerini yapar.',
  'sdp_kodlari': ['170.01', '175', '858', '622.01', '180.03'],
  'vatandas_yogunlugu': 'yuksek',
  'imza_unvani': 'Müdür',
  'detsis_no': '59553370',
  'hedef_olabilir': True},
 {'kod': 'zabita',
  'ad': 'Zabıta Müdürlüğü',
  'kurum': 'Yenimahalle Belediye Başkanlığı',
  'kurum_kodu': 'yenimahalle_belediyesi',
  'ust_birim_kodu': 'baskan_yrd_5',
  'seviye': 2,
  'gorev_alani': 'Belde düzeni, esnaf denetimi, pazar yerleri ve seyyar satıcılarla ilgili '
                 'tedbirleri alır. Belediye yasaklarına aykırılıklarda idari yaptırım karar '
                 'tutanağı düzenler. Encümen kararlarının tebliğ ve uygulanmasında görev alır.',
  'sdp_kodlari': ['858', '622.01', '170.01'],
  'vatandas_yogunlugu': 'yuksek',
  'imza_unvani': 'Müdür',
  'detsis_no': '50719027',
  'hedef_olabilir': True},
 {'kod': 'fen_isleri',
  'ad': 'Fen İşleri Müdürlüğü',
  'kurum': 'Yenimahalle Belediye Başkanlığı',
  'kurum_kodu': 'yenimahalle_belediyesi',
  'ust_birim_kodu': 'baskan_yrd_5',
  'seviye': 2,
  'gorev_alani': 'Yol, kaldırım ve üstyapı yapım ile bakım-onarım işlerini yürütür. Belediye '
                 'hizmet binaları ile devlet okulları ve mabetlerin onarımını yapar veya yaptırır. '
                 'Yapım işlerinin etüt-proje, ihale, uygulama ve hakediş süreçlerini yönetir.',
  'sdp_kodlari': ['755.01', '755.02', '807.01', '934.01', '602.07'],
  'vatandas_yogunlugu': 'orta',
  'imza_unvani': 'Müdür',
  'detsis_no': '33152401',
  'hedef_olabilir': True},
 {'kod': 'temizlik_isleri',
  'ad': 'Temizlik İşleri Müdürlüğü',
  'kurum': 'Yenimahalle Belediye Başkanlığı',
  'kurum_kodu': 'yenimahalle_belediyesi',
  'ust_birim_kodu': 'baskan_yrd_2',
  'seviye': 2,
  'gorev_alani': 'Evsel katı atıkların toplanması ve taşınması ile cadde-sokak süpürme ve yıkama '
                 'hizmetlerini yürütür. Konteyner temini, bakımı ve dezenfeksiyonunu sağlar. '
                 'Hafriyat ve moloz kaynaklı kirlilik şikayetlerini değerlendirir.',
  'sdp_kodlari': ['155.01', '934.01', '622.01'],
  'vatandas_yogunlugu': 'orta',
  'imza_unvani': 'Müdür',
  'detsis_no': '83011479',
  'hedef_olabilir': True},
 {'kod': 'kultur_sanat_sosyal',
  'ad': 'Kültür, Sanat ve Sosyal İşler Müdürlüğü',
  'kurum': 'Yenimahalle Belediye Başkanlığı',
  'kurum_kodu': 'yenimahalle_belediyesi',
  'ust_birim_kodu': 'baskan_yrd_2',
  'seviye': 2,
  'gorev_alani': 'Meslek edindirme ve hobi kursları ile kültür-sanat etkinliklerini düzenler, '
                 'sosyal tesis ve kültür merkezlerini işletir. İhtiyaç sahibi kişi ve ailelere '
                 'ayni ve nakdi sosyal yardım sağlar. Engelli ve yaşlı vatandaşlara yönelik destek '
                 'hizmetlerini yürütür.',
  'sdp_kodlari': ['815', '120.02', '051', '773', '622.01'],
  'vatandas_yogunlugu': 'yuksek',
  'imza_unvani': 'Müdür',
  'detsis_no': '85330682',
  'hedef_olabilir': True},
 {'kod': 'hukuk_isleri',
  'ad': 'Hukuk İşleri Müdürlüğü',
  'kurum': 'Yenimahalle Belediye Başkanlığı',
  'kurum_kodu': 'yenimahalle_belediyesi',
  'ust_birim_kodu': 'baskan_yrd_3',
  'seviye': 2,
  'gorev_alani': 'Belediye birimlerinin hukuki görüş taleplerini karşılar ve mütalaa verir. '
                 'Kurumun taraf olduğu adli ve idari davalarda belediyeyi temsil eder, dava ve '
                 'icra takiplerini yürütür. Encümen ve meclis kararlarının hukuka uygunluğunu '
                 'değerlendirir.',
  'sdp_kodlari': ['045.02', '641.04', '858', '622.01'],
  'vatandas_yogunlugu': 'dusuk',
  'imza_unvani': 'Müdür',
  'detsis_no': '10578106',
  'hedef_olabilir': True},
 {'kod': 'makine_ikmal',
  'ad': 'Makine İkmal Bakım ve Onarım Müdürlüğü',
  'kurum': 'Yenimahalle Belediye Başkanlığı',
  'kurum_kodu': 'yenimahalle_belediyesi',
  'ust_birim_kodu': 'baskan_yrd_4',
  'seviye': 2,
  'gorev_alani': 'Belediye hizmet araçları ile iş makinelerinin tahsis, görevlendirme, akaryakıt '
                 've sigorta işlemlerini yürütür. Araç ve iş makinesi bakım-onarımını yapar veya '
                 'yaptırır, yedek parça ve malzeme alım süreçlerini yönetir.',
  'sdp_kodlari': ['801', '802', '934.01'],
  'vatandas_yogunlugu': 'dusuk',
  'imza_unvani': 'Müdür',
  'detsis_no': '89052714',
  'hedef_olabilir': True},
 {'kod': 'muhtarlik_isleri',
  'ad': 'Muhtarlık İşleri Müdürlüğü',
  'kurum': 'Yenimahalle Belediye Başkanlığı',
  'kurum_kodu': 'yenimahalle_belediyesi',
  'ust_birim_kodu': 'baskan_yrd_1',
  'seviye': 2,
  'gorev_alani': 'Muhtarlardan ve vatandaşlardan gelen talep, istek ve şikayetleri kayda alır, '
                 'ilgili müdürlüklere yönlendirir ve sonucunu başvuru sahibine bildirir. CİMER, '
                 'çağrı merkezi ve bilgi edinme başvurularının takibini yapar.',
  'sdp_kodlari': ['622.01', '622.02', '805.02.05'],
  'vatandas_yogunlugu': 'yuksek',
  'imza_unvani': 'Müdür',
  'detsis_no': '26888327',
  'hedef_olabilir': True},
 {'kod': 'ankara_il_mem',
  'ad': 'Ankara İl Millî Eğitim Müdürlüğü',
  'kurum': 'Ankara İl Millî Eğitim Müdürlüğü',
  'kurum_kodu': 'ankara_il_mem',
  'ust_birim_kodu': None,
  'seviye': 0,
  'gorev_alani': 'Millî Eğitim Bakanlığının Ankara ilindeki taşra teşkilatıdır. İl genelinde örgün '
                 've yaygın eğitim hizmetlerini planlar, yürütür ve denetler; ilçe millî eğitim '
                 'müdürlükleri ile okul ve kurumları koordine eder.',
  'sdp_kodlari': ['355.02', '010.06', '622.01', '045.02'],
  'vatandas_yogunlugu': 'orta',
  'imza_unvani': 'İl Millî Eğitim Müdürü',
  'detsis_no': '55461037',
  'hedef_olabilir': True},
 {'kod': 'temel_egitim_sb',
  'ad': 'Temel Eğitim Şube Müdürlüğü',
  'kurum': 'Ankara İl Millî Eğitim Müdürlüğü',
  'kurum_kodu': 'ankara_il_mem',
  'ust_birim_kodu': 'ankara_il_mem',
  'seviye': 2,
  'gorev_alani': 'İlkokul ve ortaokul düzeyinde kayıt-kabul, nakil ve kayıt alanı işlemlerini '
                 'yürütür. Yabancı uyruklu öğrencilerin kayıt ve nakil süreçlerini takip eder.',
  'sdp_kodlari': ['205', '210.01', '235', '198.02.01', '802'],
  'vatandas_yogunlugu': 'yuksek',
  'imza_unvani': 'Şube Müdürü',
  'detsis_no': '21291472',
  'hedef_olabilir': True},
 {'kod': 'ortaogretim_sb',
  'ad': 'Ortaöğretim Şube Müdürlüğü',
  'kurum': 'Ankara İl Millî Eğitim Müdürlüğü',
  'kurum_kodu': 'ankara_il_mem',
  'ust_birim_kodu': 'ankara_il_mem',
  'seviye': 2,
  'gorev_alani': 'Ortaöğretim kurumlarında nakil ve geçiş, ödül ve disiplin, yatılılık ve '
                 'bursluluk işlemlerini yürütür. İşletmelerde meslekî eğitim ve staj süreçlerini '
                 'takip eder.',
  'sdp_kodlari': ['210.01', '225.02', '245.04', '250', '198.02.01', '215.01'],
  'vatandas_yogunlugu': 'yuksek',
  'imza_unvani': 'Şube Müdürü',
  'detsis_no': '63971525',
  'hedef_olabilir': True},
 {'kod': 'ozel_egitim_rehberlik_sb',
  'ad': 'Özel Eğitim ve Rehberlik Şube Müdürlüğü',
  'kurum': 'Ankara İl Millî Eğitim Müdürlüğü',
  'kurum_kodu': 'ankara_il_mem',
  'ust_birim_kodu': 'ankara_il_mem',
  'seviye': 2,
  'gorev_alani': 'Özel eğitim hizmetlerini planlar; rehberlik ve araştırma merkezleri aracılığıyla '
                 'değerlendirme kurulu raporu, kaynaştırma ve destek eğitim odası süreçlerini '
                 'yürütür.',
  'sdp_kodlari': ['160.01', '160.01.02', '160.02'],
  'vatandas_yogunlugu': 'yuksek',
  'imza_unvani': 'Şube Müdürü',
  'detsis_no': '87302975',
  'hedef_olabilir': True},
 {'kod': 'ozel_ogretim_sb',
  'ad': 'Özel Öğretim Kurumları Şube Müdürlüğü',
  'kurum': 'Ankara İl Millî Eğitim Müdürlüğü',
  'kurum_kodu': 'ankara_il_mem',
  'ust_birim_kodu': 'ankara_il_mem',
  'seviye': 2,
  'gorev_alani': 'Özel okul, kurs ve dershane niteliğindeki özel öğretim kurumlarının açılış, '
                 'devir ve denetim işlemlerini yürütür; kurs açma taleplerini ve şikayet '
                 'başvurularını değerlendirir.',
  'sdp_kodlari': ['135.03', '622.01', '622.02'],
  'vatandas_yogunlugu': 'orta',
  'imza_unvani': 'Şube Müdürü',
  'detsis_no': '91571118',
  'hedef_olabilir': True},
 {'kod': 'strateji_gelistirme_sb',
  'ad': 'Strateji Geliştirme Şube Müdürlüğü',
  'kurum': 'Ankara İl Millî Eğitim Müdürlüğü',
  'kurum_kodu': 'ankara_il_mem',
  'ust_birim_kodu': 'ankara_il_mem',
  'seviye': 2,
  'gorev_alani': 'İl millî eğitim müdürlüğünün stratejik plan, performans programı ve faaliyet '
                 'raporu çalışmalarını yürütür. Yatırım programı ve ödenek taleplerini hazırlar.',
  'sdp_kodlari': ['602.04', '602.07', '934.01'],
  'vatandas_yogunlugu': 'dusuk',
  'imza_unvani': 'Şube Müdürü',
  'detsis_no': '14588481',
  'hedef_olabilir': True},
 {'kod': 'yenimahalle_ilce_mem',
  'ad': 'Yenimahalle İlçe Millî Eğitim Müdürlüğü',
  'kurum': 'Ankara İl Millî Eğitim Müdürlüğü',
  'kurum_kodu': 'ankara_il_mem',
  'ust_birim_kodu': 'ankara_il_mem',
  'seviye': 2,
  'gorev_alani': 'Yenimahalle ilçesindeki okul ve kurumların iş ve işlemlerini yürütür; '
                 'kayıt-kabul, nakil, taşımalı eğitim ve okul aile birliği işlemlerini takip eder. '
                 'Belediye ve kaymakamlık ile ilçe düzeyinde yazışmaları yapar.',
  'sdp_kodlari': ['205', '210.01', '140', '165.01', '250'],
  'vatandas_yogunlugu': 'yuksek',
  'imza_unvani': 'İlçe Millî Eğitim Müdürü',
  'detsis_no': '93213107',
  'hedef_olabilir': True},
 {'kod': 'gazi_rektorlugu',
  'ad': 'Gazi Üniversitesi Rektörlüğü',
  'kurum': 'Gazi Üniversitesi Rektörlüğü',
  'kurum_kodu': 'gazi_rektorlugu',
  'ust_birim_kodu': None,
  'seviye': 0,
  'gorev_alani': '2547 sayılı Yükseköğretim Kanunu kapsamında eğitim-öğretim, bilimsel araştırma '
                 've yayın faaliyetlerini yürüten devlet üniversitesidir. Senato ve Üniversite '
                 'Yönetim Kurulu kararlarını uygular, akademik ve idari teşkilatı sevk ve idare '
                 'eder.',
  'sdp_kodlari': ['010.06', '050.04', '602.04'],
  'vatandas_yogunlugu': 'dusuk',
  'imza_unvani': 'Rektör',
  'detsis_no': '39985474',
  'hedef_olabilir': True},
 {'kod': 'genel_sekreterlik',
  'ad': 'Genel Sekreterlik',
  'kurum': 'Gazi Üniversitesi Rektörlüğü',
  'kurum_kodu': 'gazi_rektorlugu',
  'ust_birim_kodu': 'gazi_rektorlugu',
  'seviye': 2,
  'gorev_alani': 'Üniversitenin idari teşkilatının başında yer alır; kurul kararlarının yazılması, '
                 'duyurulması ve idari birimler arası koordinasyonun sağlanması işlemlerini '
                 'yürütür. Genel evrak ve arşiv hizmetlerini yönetir.',
  'sdp_kodlari': ['010.06', '050.04', '622.01', '622.02', '805.02.05', '045.02'],
  'vatandas_yogunlugu': 'orta',
  'imza_unvani': 'Genel Sekreter',
  'detsis_no': '82642947',
  'hedef_olabilir': True},
 {'kod': 'ogrenci_isleri_db',
  'ad': 'Öğrenci İşleri Daire Başkanlığı',
  'kurum': 'Gazi Üniversitesi Rektörlüğü',
  'kurum_kodu': 'gazi_rektorlugu',
  'ust_birim_kodu': 'gazi_rektorlugu',
  'seviye': 2,
  'gorev_alani': 'Öğrenci kayıt, kayıt yenileme, nakil, kayıt dondurma ve mezuniyet işlemlerini '
                 'yürütür. Öğrenci belgesi, transkript ve askerlik durum belgesi düzenler. Yatay '
                 'geçiş ve denklik başvurularını işleme alır.',
  'sdp_kodlari': ['302.01', '302.10', '302.11', '302.15', '301.06', '102.03', '302.03', '310'],
  'vatandas_yogunlugu': 'yuksek',
  'imza_unvani': 'Daire Başkanı',
  'detsis_no': '17311665',
  'hedef_olabilir': True},
 {'kod': 'personel_db',
  'ad': 'Personel Dairesi Başkanlığı',
  'kurum': 'Gazi Üniversitesi Rektörlüğü',
  'kurum_kodu': 'gazi_rektorlugu',
  'ust_birim_kodu': 'gazi_rektorlugu',
  'seviye': 2,
  'gorev_alani': 'Akademik ve idari personelin atama, görevlendirme ve özlük işlemlerini yürütür. '
                 'Doçentlik ve unvan sınavlarına ilişkin jüri görevlendirme işlemlerini yapar.',
  'sdp_kodlari': ['903.02', '201', '209', '204.01'],
  'vatandas_yogunlugu': 'dusuk',
  'imza_unvani': 'Daire Başkanı',
  'detsis_no': '42218640',
  'hedef_olabilir': True},
 {'kod': 'muhendislik_fak',
  'ad': 'Mühendislik Fakültesi Dekanlığı',
  'kurum': 'Gazi Üniversitesi Rektörlüğü',
  'kurum_kodu': 'gazi_rektorlugu',
  'ust_birim_kodu': 'gazi_rektorlugu',
  'seviye': 2,
  'gorev_alani': 'Fakülte düzeyinde eğitim-öğretim programlarını yürütür; ders ve sınav '
                 'programlarını düzenler, öğrenci izin ve mazeret taleplerini karara bağlar. '
                 'Zorunlu staj başvuru ve değerlendirme süreçlerini yönetir.',
  'sdp_kodlari': ['104.01', '106', '302.08', '304.03', '773'],
  'vatandas_yogunlugu': 'yuksek',
  'imza_unvani': 'Dekan',
  'detsis_no': '43123369',
  'hedef_olabilir': True},
 {'kod': 'gazi_egitim_fak',
  'ad': 'Gazi Eğitim Fakültesi Dekanlığı',
  'kurum': 'Gazi Üniversitesi Rektörlüğü',
  'kurum_kodu': 'gazi_rektorlugu',
  'ust_birim_kodu': 'gazi_rektorlugu',
  'seviye': 2,
  'gorev_alani': 'Öğretmen yetiştirme programlarını yürütür. Öğretmenlik uygulaması kapsamında il '
                 've ilçe millî eğitim müdürlükleri ile uygulama öğrencisi yerleştirme ve protokol '
                 'yazışmalarını yapar.',
  'sdp_kodlari': ['773', '304.03', '302.08', '106'],
  'vatandas_yogunlugu': 'yuksek',
  'imza_unvani': 'Dekan',
  'detsis_no': '86488853',
  'hedef_olabilir': True},
 {'kod': 'fen_bilimleri_ens',
  'ad': 'Fen Bilimleri Enstitüsü Müdürlüğü',
  'kurum': 'Gazi Üniversitesi Rektörlüğü',
  'kurum_kodu': 'gazi_rektorlugu',
  'ust_birim_kodu': 'gazi_rektorlugu',
  'seviye': 2,
  'gorev_alani': 'Lisansüstü programların eğitim-öğretim işlemlerini yürütür. Tez konusu, danışman '
                 'atama, jüri oluşturma ve tez teslim süreçlerini yönetir; kayıt ve izin '
                 'taleplerini karara bağlar.',
  'sdp_kodlari': ['302.14', '302.01', '302.11', '106'],
  'vatandas_yogunlugu': 'yuksek',
  'imza_unvani': 'Enstitü Müdürü',
  'detsis_no': '47014261',
  'hedef_olabilir': True},
 {'kod': 'sks_db',
  'ad': 'Sağlık Kültür ve Spor Daire Başkanlığı',
  'kurum': 'Gazi Üniversitesi Rektörlüğü',
  'kurum_kodu': 'gazi_rektorlugu',
  'ust_birim_kodu': 'gazi_rektorlugu',
  'seviye': 2,
  'gorev_alani': 'Öğrencilere yönelik burs, kısmi zamanlı çalışma, beslenme ve sağlık hizmetlerini '
                 'yürütür. Öğrenci topluluklarının kuruluş ve etkinlik izin işlemlerini yapar, '
                 'sosyal ve kültürel etkinlikleri düzenler.',
  'sdp_kodlari': ['304.03', '309', '815', '051', '802'],
  'vatandas_yogunlugu': 'yuksek',
  'imza_unvani': 'Daire Başkanı',
  'detsis_no': '98244303',
  'hedef_olabilir': True}]


def _birimleri_yukle() -> tuple[list[dict], str]:
    if BIRIM_DOSYASI.exists():
        try:
            veri = json.loads(BIRIM_DOSYASI.read_text(encoding="utf-8"))
            if isinstance(veri, list) and veri:
                return veri, BIRIM_DOSYASI.name
        except (OSError, ValueError):
            pass
    return GOMULU_BIRIMLER, "gomulu"


BIRIMLER, BIRIM_KAYNAGI = _birimleri_yukle()


BIRIM_HARITASI = {b["kod"]: b for b in BIRIMLER}


def _birim_adi(kod: str | None) -> str | None:
    b = BIRIM_HARITASI.get(kod or "")
    return b["ad"] if b else kod


# ===========================================================================
# MASKELEME  (sözleşme 7)
# ===========================================================================

def _maskele(tur: str, deger: str) -> str:
    """Ham değeri asla göndermiyoruz; maskeleme sunucuda yapılır."""
    if tur == "kisi":
        return " ".join(
            (p[0] + "*" * max(1, len(p) - 1)) if p else p for p in deger.split()
        )
    if tur in ("telefon", "tckn", "iban", "plaka"):
        goster = 3 if len(deger) > 6 else 1
        return deger[:goster] + "*" * max(1, len(deger) - goster - 2) + deger[-2:]
    if tur == "eposta":
        ad, _, alan = deger.partition("@")
        return (ad[:2] + "*" * max(1, len(ad) - 2)) + ("@" + alan if alan else "")
    if tur == "adres":
        parcalar = deger.split()
        return " ".join(parcalar[:2] + ["***"]) if len(parcalar) > 2 else "***"
    if tur == "dogum_tarihi":
        return deger[:4] + "-**-**" if len(deger) >= 4 else "***"
    return deger[0] + "*" * max(1, len(deger) - 1)


def _varlik_sunum(varlik: dict) -> dict:
    """Varlığı arayüze giderken maskeler. sira alanı /ham çağrısı için gerekir."""
    pii = varlik["tur"] in KISISEL_TIPLER
    deger = _maskele(varlik["tur"], varlik["deger"]) if pii else varlik["deger"]
    return {
        "sira": varlik["sira"],
        "tur": varlik["tur"],
        "deger": deger,
        "guven": varlik["guven"],
        "pii": pii,
        "maskelendi": pii,
        "kanit": varlik["kanit"],
        # Maskeli değerin kanıt metni gönderilmez; yoksa metinde ham hâli
        # aranır ve maskeleme delinir.
        "kanit_metin": None if pii else varlik.get("kanit_metin"),
    }


# ===========================================================================
# SENARYOLAR  (sözleşme 5.6 şemasında)
# ===========================================================================

def _alan(deger, guven, yontem, kanit_metin=None, sayfa=1):
    return {"deger": deger, "guven": guven, "yontem": yontem,
            "kanit": {"sayfa": sayfa, "kutu": None} if deger else None,
            "kanit_metin": kanit_metin}


def _bos_ustveri(**dolu):
    alanlar = {a: _alan(None, 0.0, None)
               for a in ("sayi", "tarih", "konu", "muhatap", "ilgi", "imza", "ek", "dagitim")}
    alanlar.update(dolu)
    return alanlar


SENARYOLAR: dict[str, dict[str, Any]] = {

    # -----------------------------------------------------------------------
    # 1 · Yurtdışı denklik şikâyeti — yönlendirme belirsiz, kritik eksik
    # -----------------------------------------------------------------------
    "denklik": {
        "dosya_adi": "belge_099.pdf",
        "gonderen": {"ad": "Derya YILDIZ", "tur": "gercek_kisi"},
        "sayfa_sayisi": 1, "karakter": 1240,
        "girdi_tipi": "taranmis", "ocr_motoru": "rapidocr",
        "linter_geri_gonderme": True,
        "metin": """                                                                    27.03.2026

ANKARA İL MİLLÎ EĞİTİM MÜDÜRLÜĞÜNE

\tYurtdışında tamamladığım ortaöğretim öğrenimime ilişkin denklik başvurumu
27.03.2026 tarihinde yaptım.

\tAncak yurtdışı denklik başvurum dört aydır sonuçlanmadı. Başvuru sürecine
ilişkin tarafıma herhangi bir bilgilendirme de yapılmamıştır.

\tKonunun incelenerek başvurumun sonuçlandırılmasını arz ederim.

                                                                 Derya YILDIZ
""",
        "ustveri": _bos_ustveri(
            tarih=_alan("2026-03-27", 1.0, "regex", "27.03.2026"),
            konu=_alan("Yurtdışı Eğitim Denkliği", 0.66, "llm", None),
            muhatap=_alan("Ankara İl Millî Eğitim Müdürlüğü", 0.62, "llm",
                          "ANKARA İL MİLLÎ EĞİTİM MÜDÜRLÜĞÜNE"),
            imza=_alan("Derya YILDIZ", 0.88, "llm", "Derya YILDIZ"),
        ),
        "belge_turu": {"deger": "sikayet", "guven": 0.84,
                       "gerekce": "Sayı alanı yok, gerçek kişi imzası var, memnuniyetsizlik bildiriliyor."},
        "sdp": {"kod": "215.01", "ad": "Yurtdışı Eğitim Denkliği", "kaynak_sayidan_mi": False},
        "varliklar": [
            {"sira": 0, "tur": "kisi", "deger": "Derya YILDIZ", "guven": 0.93,
             "kanit": {"sayfa": 1, "kutu": None}, "kanit_metin": "Derya YILDIZ"},
            {"sira": 1, "tur": "tarih", "deger": "2026-03-27", "guven": 0.95,
             "kanit": {"sayfa": 1, "kutu": None}, "kanit_metin": "27.03.2026"},
            {"sira": 2, "tur": "kurum", "deger": "Ankara İl Millî Eğitim Müdürlüğü", "guven": 0.90,
             "kanit": {"sayfa": 1, "kutu": None}, "kanit_metin": "ANKARA İL MİLLÎ EĞİTİM MÜDÜRLÜĞÜNE"},
        ],
        "talep": "Yurtdışı denklik başvurusunun sonuçlandırılması.",
        "ozet": ("Derya Yıldız, dört aydır sonuçlanmayan yurtdışı eğitim denklik "
                 "başvurusunun ele alınmasını talep etmektedir."),
        "eksikler": [
            {"alan": "basvuru_numarasi", "onem": "hata", "katman": "kural",
             "dayanak": "Denklik başvurusu dosya numarası olmadan sorgulanamaz",
             "aciklama": "Dilekçede başvuru numarası belirtilmemiş.",
             "soru": "Denklik başvurunuza ait başvuru numarasını paylaşır mısınız?",
             "karsi_taraftan_istenebilir": True, "giderildi": False, "cevap": None},
            {"alan": "iletisim_telefon", "onem": "uyari", "katman": "sema",
             "dayanak": "3071 sayılı Dilekçe Hakkının Kullanılmasına Dair Kanun m.4",
             "aciklama": "Dilekçede iletişim bilgisi bulunmuyor.",
             "soru": "Size ulaşabileceğimiz bir telefon numarası paylaşır mısınız?",
             "karsi_taraftan_istenebilir": True, "giderildi": False, "cevap": None},
        ],
        "mevzuat": [
            {"mevzuat_adi": "Millî Eğitim Bakanlığı Denklik Yönetmeliği", "madde": "m.9",
             "baslik": "Denklik başvurularının sonuçlandırılması",
             "alinti": "Başvurular en geç ... içinde sonuçlandırılır.",
             "gerekce": "Talep denklik süresine ilişkin olduğundan dayanak bu maddedir.",
             "benzerlik": 0.81, "dogrulandi": True},
            {"mevzuat_adi": "3071 sayılı Dilekçe Hakkının Kullanılmasına Dair Kanun", "madde": "m.7",
             "baslik": "Dilekçelerin cevaplandırılması",
             "alinti": "...en geç otuz gün içinde gerekçeli olarak cevap verilir.",
             "gerekce": "Vatandaş dilekçesine cevap süresi bu maddeye tabidir.",
             "benzerlik": 0.74, "dogrulandi": True},
            # Getirildi ama elendi: alıntı metinde doğrulanamadı. Arayüzde gösterilmez.
            {"mevzuat_adi": "Millî Eğitim Bakanlığı Ortaöğretim Kurumları Yönetmeliği",
             "madde": "m.35", "baslik": "Sınıf geçme ve sınav",
             "alinti": "", "gerekce": "Alıntı belge metninde doğrulanamadı.",
             "benzerlik": 0.58, "dogrulandi": False},
        ],
        "karar": {"uretilecek_tur": "cevap_yazisi",
                  "gerekce": "Vatandaş talebi doğrudan cevap gerektiriyor.",
                  "taslak_gerekli": True},
        "taslak": {
            "baslik": "T.C.\nANKARA VALİLİĞİ\nİl Millî Eğitim Müdürlüğü",
            "sayi": None, "tarih": None,
            "konu": "Yurtdışı Eğitim Denkliği Başvurusu",
            "muhatap": "Sayın Derya YILDIZ",
            "govde": ("İlgi dilekçenizde belirtilen yurtdışı eğitim denklik başvurunuza "
                      "ilişkin talebiniz Müdürlüğümüzce incelenmiştir.\n\n"
                      "Millî Eğitim Bakanlığı Denklik Yönetmeliği'nin 9 uncu maddesi uyarınca "
                      "başvurunuzun sonuçlandırılabilmesi için başvuru numaranızın "
                      "Müdürlüğümüze bildirilmesi gerekmektedir.\n\n"
                      "Bilgilerinizi rica ederim."),
            "imza_ad": None, "imza_unvan": "Şube Müdürü",
        },
        "uslup_bulgulari": [
            {"kural_no": "ME-02", "duzey": "hata",
             "mesaj": "Alt makama yazılan yazıda 'arz ederim' kullanılamaz.",
             "mevzuat": "Resmî Yazışma Yönetmeliği m.13", "cozuldu": True},
        ],
        "linter_tur_sayisi": 2,
        "yonlendirme": {
            "birim": "ortaogretim_sb", "birim_adi": "Ortaöğretim Şube Müdürlüğü",
            "skor": 0.71, "geregi_bilgi": "geregi", "kaynak": "llm",
            "gerekce": "Yurtdışı eğitim denkliği bu şube müdürlüğünün görev alanındadır (SDP 215.01).",
            "kanit_cumle": "yurtdışı denklik başvurum dört aydır sonuçlanmadı",
            "alternatifler": [],
            "alternatif_adaylar": [
                {"birim": "temel_egitim_sb", "birim_adi": "Temel Eğitim Şube Müdürlüğü", "skor": 0.64},
                {"birim": "ankara_il_mem", "birim_adi": "Ankara İl Millî Eğitim Müdürlüğü", "skor": 0.31},
            ],
            "kurum_disinda": False,
        },
        "guven_kapisi": {"mod": "INSAN", "skor": 0.71, "esik": 0.85,
                         "sebep": "Yönlendirme güveni düşük: iki birim yakın skorlu (0,71 / 0,64)"},
        "adim_guveni": {3: 0.84, 4: 0.79, 5: 0.81, 6: 0.86, 7: 0.90, 8: 0.88, 10: 0.71},
        "adim_gerekcesi": {
            2: "Sayı alanı bulunamadı; dilekçe olabileceği işaretlendi.",
            3: "Sayı yok, imza gerçek kişi → şikâyet. SDP kodu konudan çıkarıldı, tahmin.",
            4: "Üç katman çalıştı: şema 1, kural 1, çıkarım 0 bulgu.",
            5: "Getirilen iki madde de metinde doğrulandı.",
            8: "Şablon dolduruldu, model yalnızca gövdeyi yazdı.",
            10: "SDP tablosunda karşılık yok (sayı yok); çıkarımla iki birim yakın skorlu.",
            11: "Skor 0,71 < eşik 0,85 → insan onayı.",
        },
    },
}

# -----------------------------------------------------------------------
# 2 · Öğrenci nakil talebi — temiz akış, OTOMATİK ONAY
# -----------------------------------------------------------------------
SENARYOLAR["nakil"] = {
    "dosya_adi": "belge_017.pdf",
    "gonderen": {"ad": "Ankara Valiliği", "tur": "kurum"},
    "sayfa_sayisi": 1, "karakter": 1105,
    "girdi_tipi": "metin_katmanli", "ocr_motoru": None,
    "linter_geri_gonderme": False,
    "metin": """T.C.
ANKARA VALİLİĞİ
İl Yazı İşleri Müdürlüğü

Sayı : E-15843002-210.01-2026/2287                                  05.06.2026
Konu : Öğrenci Nakil İşlemleri

                   ANKARA İL MİLLÎ EĞİTİM MÜDÜRLÜĞÜNE

İlgi : 02.06.2026 tarihli ve E-77120044 sayılı yazı.

\tİlgi yazı ile Valiliğimize intikal eden, ilkokul ve ortaokul düzeyinde
gerçekleştirilen öğrenci nakil işlemlerine ilişkin 2025-2026 eğitim öğretim
yılı verilerinin derlenmesine ihtiyaç duyulmaktadır.

\tSöz konusu verilerin 30.06.2026 tarihine kadar Valiliğimize gönderilmesi
hususunda gereğini rica ederim.

                                                                  Nurten AKGÜL
                                                          İl Yazı İşleri Müdürü
""",
    "ustveri": _bos_ustveri(
        sayi=_alan("E-15843002-210.01-2026/2287", 1.0, "regex", "E-15843002-210.01-2026/2287"),
        tarih=_alan("2026-06-05", 1.0, "regex", "05.06.2026"),
        konu=_alan("Öğrenci Nakil İşlemleri", 0.97, "regex", "Öğrenci Nakil İşlemleri"),
        muhatap=_alan("Ankara İl Millî Eğitim Müdürlüğü", 0.96, "regex",
                      "ANKARA İL MİLLÎ EĞİTİM MÜDÜRLÜĞÜNE"),
        ilgi=_alan("02.06.2026 tarihli ve E-77120044 sayılı yazı", 0.94, "regex",
                   "02.06.2026 tarihli ve E-77120044 sayılı yazı"),
        imza=_alan("Nurten AKGÜL — İl Yazı İşleri Müdürü", 0.93, "llm", "Nurten AKGÜL"),
    ),
    "belge_turu": {"deger": "resmi_yazi", "guven": 0.98,
                   "gerekce": "Sayı, ilgi ve kurum imzası tam; resmî yazı biçiminde."},
    "sdp": {"kod": "210.01", "ad": "Öğrenci Nakil ve Geçiş İşlemleri", "kaynak_sayidan_mi": True},
    "varliklar": [
        {"sira": 0, "tur": "kurum", "deger": "Ankara Valiliği", "guven": 0.96,
         "kanit": {"sayfa": 1, "kutu": None}, "kanit_metin": "ANKARA VALİLİĞİ"},
        {"sira": 1, "tur": "tarih", "deger": "2026-06-30", "guven": 0.94,
         "kanit": {"sayfa": 1, "kutu": None}, "kanit_metin": "30.06.2026"},
        {"sira": 2, "tur": "kisi", "deger": "Nurten AKGÜL", "guven": 0.91,
         "kanit": {"sayfa": 1, "kutu": None}, "kanit_metin": "Nurten AKGÜL"},
    ],
    "talep": "2025-2026 öğretim yılı öğrenci nakil verilerinin 30 Haziran'a kadar bildirilmesi.",
    "ozet": ("Ankara Valiliği, ilkokul ve ortaokul düzeyindeki öğrenci nakil işlemlerine "
             "ilişkin 2025-2026 eğitim öğretim yılı verilerinin 30 Haziran 2026 tarihine "
             "kadar bildirilmesini talep etmektedir."),
    "eksikler": [],
    "mevzuat": [
        {"mevzuat_adi": "Millî Eğitim Bakanlığı Okul Öncesi ve İlköğretim Kurumları Yönetmeliği",
         "madde": "m.25", "baslik": "Nakil ve geçiş işlemleri",
         "alinti": "Öğrencilerin nakilleri e-Okul sistemi üzerinden yapılır.",
         "gerekce": "Talep nakil verilerine ilişkindir.", "benzerlik": 0.88, "dogrulandi": True},
        {"mevzuat_adi": "Millî Eğitim Bakanlığı Ortaöğretim Kurumları Yönetmeliği",
         "madde": "m.28", "baslik": "Nakil şartları",
         "alinti": "", "gerekce": "Belge türüne uymuyor; ortaöğretim maddesi ilkokul talebine dayanak olmaz.",
         "benzerlik": 0.61, "dogrulandi": False},
    ],
    "karar": {"uretilecek_tur": "cevap_yazisi",
              "gerekce": "İlgi tutulan bir yazıya cevap; süre sınırı var.",
              "taslak_gerekli": True},
    "taslak": {
        "baslik": "T.C.\nANKARA VALİLİĞİ\nİl Millî Eğitim Müdürlüğü",
        "sayi": None, "tarih": None,
        "konu": "Öğrenci Nakil İşlemleri",
        "muhatap": "ANKARA VALİLİĞİNE\n(İl Yazı İşleri Müdürlüğü)",
        "govde": ("İlgi yazınızda talep edilen 2025-2026 eğitim öğretim yılı öğrenci nakil "
                  "işlemlerine ilişkin veriler Müdürlüğümüzce derlenmiş olup ekte "
                  "sunulmuştur.\n\n"
                  "Bilgilerinize arz ederim."),
        "imza_ad": None, "imza_unvan": "Şube Müdürü",
    },
    "uslup_bulgulari": [],
    "linter_tur_sayisi": 1,
    "yonlendirme": {
        "birim": "temel_egitim_sb", "birim_adi": "Temel Eğitim Şube Müdürlüğü",
        "skor": 0.93, "geregi_bilgi": "geregi", "kaynak": "sdp_tablosu",
        "gerekce": "SDP kodu 210.01 sayının üçüncü bölümünden okundu; kodu taşıyan üç birim arasından ilkokul/ortaokul kapsamı nedeniyle bu şube seçildi.",
        "kanit_cumle": "ilkokul ve ortaokul düzeyinde gerçekleştirilen öğrenci nakil işlemleri",
        "alternatifler": [],
        "alternatif_adaylar": [
            {"birim": "ortaogretim_sb", "birim_adi": "Ortaöğretim Şube Müdürlüğü", "skor": 0.22},
            {"birim": "strateji_gelistirme_sb", "birim_adi": "Strateji Geliştirme Şube Müdürlüğü", "skor": 0.14},
        ],
        "kurum_disinda": False,
    },
    "guven_kapisi": {"mod": "OTOMATIK", "skor": 0.93, "esik": 0.85,
                     "sebep": "Eksik bilgi yok, SDP tablosundan deterministik eşleşme"},
    "adim_guveni": {3: 0.98, 4: 0.95, 5: 0.90, 6: 0.94, 7: 0.96, 8: 0.92, 10: 0.93},
    "adim_gerekcesi": {
        3: "SDP kodu sayının üçüncü bölümünden okundu (210.01), tahmin yok.",
        10: "SDP tablosu üç aday bıraktı; görev alanı eşleşmesi ayrıştırdı.",
        4: "Üç katman çalıştı: bulgu yok. Belge işlem için yeterli.",
        9: "40 kuralın tamamı ilk turda geçti.",
        11: "Skor 0,93 ≥ eşik 0,85 ve kritik eksik yok → otomatik onay.",
    },
}

# -----------------------------------------------------------------------
# 3 · Ders ücreti itirazı — Gazi Üniversitesi, eşiğin hemen altında
# -----------------------------------------------------------------------
SENARYOLAR["burs"] = {
    "dosya_adi": "belge_204.pdf",
    "gonderen": {"ad": "Emre KOÇAK", "tur": "gercek_kisi"},
    "sayfa_sayisi": 1, "karakter": 980,
    "girdi_tipi": "metin_katmanli", "ocr_motoru": None,
    "linter_geri_gonderme": True,
    "metin": """                                                                    12.04.2026

GAZİ ÜNİVERSİTESİ REKTÖRLÜĞÜNE

\tMühendislik Fakültesi Bilgisayar Mühendisliği Bölümü 3. sınıf öğrencisiyim.
Öğrenci numaram 201812045'tir.

\tBu dönem için yaptığım yemek bursu başvurum, gelir belgesi eksikliği
gerekçesiyle reddedilmiştir. Ancak söz konusu belgeyi 08.04.2026 tarihinde
sisteme yüklemiştim.

\tKonunun yeniden değerlendirilmesini arz ederim.

                                                                   Emre KOÇAK
""",
    "ustveri": _bos_ustveri(
        tarih=_alan("2026-04-12", 0.97, "regex", "12.04.2026"),
        konu=_alan("Yemek Bursu Başvurusuna İtiraz", 0.71, "llm", None),
        muhatap=_alan("Gazi Üniversitesi Rektörlüğü", 0.89, "llm",
                      "GAZİ ÜNİVERSİTESİ REKTÖRLÜĞÜNE"),
        imza=_alan("Emre KOÇAK", 0.86, "llm", "Emre KOÇAK"),
    ),
    "belge_turu": {"deger": "itiraz", "guven": 0.77,
                   "gerekce": "Reddedilen bir işleme karşı yeniden değerlendirme talebi."},
    "sdp": {"kod": "304.03", "ad": "Öğrenci Beslenme ve Barınma İşlemleri", "kaynak_sayidan_mi": False},
    "varliklar": [
        {"sira": 0, "tur": "kisi", "deger": "Emre KOÇAK", "guven": 0.92,
         "kanit": {"sayfa": 1, "kutu": None}, "kanit_metin": "Emre KOÇAK"},
        {"sira": 1, "tur": "ogrenci_no", "deger": "201812045", "guven": 0.96,
         "kanit": {"sayfa": 1, "kutu": None}, "kanit_metin": "201812045"},
        {"sira": 2, "tur": "tarih", "deger": "2026-04-08", "guven": 0.93,
         "kanit": {"sayfa": 1, "kutu": None}, "kanit_metin": "08.04.2026"},
    ],
    "talep": "Reddedilen yemek bursu başvurusunun yeniden değerlendirilmesi.",
    "ozet": ("Emre Koçak, gelir belgesi eksikliği gerekçesiyle reddedilen yemek bursu "
             "başvurusunun, belgeyi süresinde yüklediğini belirterek yeniden "
             "değerlendirilmesini talep etmektedir."),
    "eksikler": [
        {"alan": "gelir_belgesi_tarihi", "onem": "uyari", "katman": "cikarim",
         "dayanak": "Yükleme tarihinin sistem kaydıyla karşılaştırılması gerekir",
         "aciklama": "Belgenin sisteme yüklendiği tarih beyan edilmiş, doğrulanmamış.",
         "soru": "Gelir belgesini yüklediğinize dair sistem çıktısını iletebilir misiniz?",
         "karsi_taraftan_istenebilir": True, "giderildi": False, "cevap": None},
    ],
    "mevzuat": [
        {"mevzuat_adi": "Yükseköğrenim Kredi ve Yurtlar Kurumu Burs-Kredi Yönetmeliği",
         "madde": "m.11", "baslik": "Başvuruların değerlendirilmesi",
         "alinti": "Eksik belge ile yapılan başvurular değerlendirmeye alınmaz.",
         "gerekce": "Reddin dayanağı ve itirazın çerçevesi bu maddedir.",
         "benzerlik": 0.79, "dogrulandi": True},
        {"mevzuat_adi": "2547 sayılı Yükseköğretim Kanunu", "madde": "m.46",
         "baslik": "Öğrenci katkı payları",
         "alinti": "", "gerekce": "Katkı payı ile burs farklı konular; alıntı doğrulanamadı.",
         "benzerlik": 0.54, "dogrulandi": False},
    ],
    "karar": {"uretilecek_tur": "cevap_yazisi",
              "gerekce": "İtiraz doğrudan cevap gerektiriyor.", "taslak_gerekli": True},
    "taslak": {
        "baslik": "T.C.\nGAZİ ÜNİVERSİTESİ REKTÖRLÜĞÜ\nSağlık Kültür ve Spor Daire Başkanlığı",
        "sayi": None, "tarih": None,
        "konu": "Yemek Bursu Başvurusuna İtiraz",
        "muhatap": "Sayın Emre KOÇAK",
        "govde": ("İlgi dilekçenizde belirtilen yemek bursu başvurunuza ilişkin itirazınız "
                  "Daire Başkanlığımızca incelenmiştir.\n\n"
                  "İtirazınızın sonuçlandırılabilmesi için gelir belgesinin sisteme "
                  "yüklendiğine dair kaydın tarafımıza iletilmesi gerekmektedir.\n\n"
                  "Bilgilerinizi rica ederim."),
        "imza_ad": None, "imza_unvan": "Daire Başkanı",
    },
    "uslup_bulgulari": [
        {"kural_no": "BI-07", "duzey": "hata",
         "mesaj": "Muhatap satırı tam unvanla yazılmalı.",
         "mevzuat": "Resmî Yazışma Yönetmeliği m.10", "cozuldu": True},
        {"kural_no": "BI-19", "duzey": "uyari",
         "mesaj": "İlgi satırı belirtilmemiş.",
         "mevzuat": "Resmî Yazışma Yönetmeliği m.11", "cozuldu": True},
    ],
    "linter_tur_sayisi": 2,
    "yonlendirme": {
        "birim": "sks_db", "birim_adi": "Sağlık Kültür ve Spor Daire Başkanlığı",
        "skor": 0.84, "geregi_bilgi": "geregi", "kaynak": "llm",
        "gerekce": "Burs ve yemek yardımı işlemleri bu daire başkanlığının görev alanındadır.",
        "kanit_cumle": "yaptığım yemek bursu başvurum ... reddedilmiştir",
        "alternatifler": [],
        "alternatif_adaylar": [
            {"birim": "ogrenci_isleri_db", "birim_adi": "Öğrenci İşleri Daire Başkanlığı", "skor": 0.38},
            {"birim": "muhendislik_fak", "birim_adi": "Mühendislik Fakültesi Dekanlığı", "skor": 0.21},
        ],
        "kurum_disinda": False,
    },
    "guven_kapisi": {"mod": "INSAN", "skor": 0.84, "esik": 0.85,
                     "sebep": "Skor eşiğin hemen altında (0,84 / 0,85)"},
    "adim_guveni": {3: 0.77, 4: 0.83, 5: 0.79, 6: 0.88, 7: 0.85, 8: 0.86, 10: 0.84},
    "adim_gerekcesi": {
        3: "Sayı yok; itiraz ifadeleri nedeniyle dilekçe yerine itiraz seçildi.",
        4: "Beyan edilen yükleme tarihi doğrulanamadı, çıkarım katmanında işaretlendi.",
        9: "İki bulgu: biri hata düzeyinde, taslak geri gönderildi.",
        11: "Skor 0,84 < eşik 0,85 → insan onayı (sınıra çok yakın).",
    },
}


# -----------------------------------------------------------------------
# 4 · İmar durumu talebi — Yenimahalle Belediyesi
# -----------------------------------------------------------------------
SENARYOLAR["imar"] = {
    "dosya_adi": "belge_142.pdf",
    "gonderen": {"ad": "Ahmet YILMAZ", "tur": "gercek_kisi"},
    "sayfa_sayisi": 1, "karakter": 1060,
    "girdi_tipi": "taranmis", "ocr_motoru": "rapidocr",
    "linter_geri_gonderme": False,
    "metin": """                                                                    11.08.2026

YENİMAHALLE BELEDİYE BAŞKANLIĞINA

\tİlçeniz sınırları içerisinde bulunan 1024 ada 7 parsel sayılı taşınmazın
malikiyim.

\tSöz konusu taşınmaz için imar durum belgesi düzenlenmesini talep ediyorum.
Taşınmaza ilişkin ölçüm işlemleri 30.07.2026 tarihinde tamamlanmıştır.

\tGereğini bilgilerinize arz ederim.

                                                                Ahmet YILMAZ
""",
    "ustveri": _bos_ustveri(
        tarih=_alan("2026-08-11", 0.98, "regex", "11.08.2026"),
        konu=_alan("İmar Durumu Talebi", 0.74, "llm", None),
        muhatap=_alan("Yenimahalle Belediye Başkanlığı", 0.91, "llm",
                      "YENİMAHALLE BELEDİYE BAŞKANLIĞINA"),
        imza=_alan("Ahmet YILMAZ", 0.87, "llm", "Ahmet YILMAZ"),
    ),
    "belge_turu": {"deger": "dilekce", "guven": 0.88,
                   "gerekce": "Sayı alanı yok, gerçek kişi imzası var, talep birinci tekil."},
    "sdp": {"kod": "115.02.01", "ad": "İmar Durumu İşlemleri", "kaynak_sayidan_mi": False},
    "varliklar": [
        {"sira": 0, "tur": "kisi", "deger": "Ahmet YILMAZ", "guven": 0.94,
         "kanit": {"sayfa": 1, "kutu": None}, "kanit_metin": "Ahmet YILMAZ"},
        {"sira": 1, "tur": "ada_parsel", "deger": "1024/7", "guven": 0.91,
         "kanit": {"sayfa": 1, "kutu": None}, "kanit_metin": "1024 ada 7 parsel"},
        {"sira": 2, "tur": "tarih", "deger": "2026-07-30", "guven": 0.95,
         "kanit": {"sayfa": 1, "kutu": None}, "kanit_metin": "30.07.2026"},
    ],
    "talep": "1024 ada 7 parsel için imar durum belgesi düzenlenmesi.",
    "ozet": ("Ahmet Yılmaz, maliki olduğu 1024 ada 7 parsel sayılı taşınmaz için imar "
             "durum belgesi düzenlenmesini talep etmektedir."),
    "eksikler": [
        {"alan": "tapu_belgesi", "onem": "hata", "katman": "mevzuat",
         "dayanak": "Planlı Alanlar İmar Yönetmeliği m.54",
         "aciklama": "Malik olduğu beyan edilmiş, tapu belgesi eklenmemiş.",
         "soru": "Söz konusu taşınmaza ait tapu belgesinin bir örneğini iletebilir misiniz?",
         "karsi_taraftan_istenebilir": True, "giderildi": False, "cevap": None},
    ],
    "mevzuat": [
        {"mevzuat_adi": "Planlı Alanlar İmar Yönetmeliği", "madde": "m.54",
         "baslik": "İmar durumu belgesi",
         "alinti": "İlgilisinin talebi üzerine düzenlenen...",
         "gerekce": "Tapu belgesi zorunluluğu bu maddede tanımlıdır.",
         "benzerlik": 0.86, "dogrulandi": True},
    ],
    "karar": {"uretilecek_tur": "cevap_yazisi",
              "gerekce": "Vatandaş talebi doğrudan cevap gerektiriyor.", "taslak_gerekli": True},
    "taslak": {
        "baslik": "T.C.\nYENİMAHALLE BELEDİYE BAŞKANLIĞI\nİmar ve Şehircilik Müdürlüğü",
        "sayi": None, "tarih": None,
        "konu": "İmar Durumu Talebi",
        "muhatap": "Sayın Ahmet YILMAZ",
        "govde": ("İlgi dilekçenizde belirtilen 1024 ada 7 parsel sayılı taşınmaza ilişkin "
                  "imar durum belgesi talebiniz Müdürlüğümüzce incelenmiştir.\n\n"
                  "Planlı Alanlar İmar Yönetmeliği'nin 54 üncü maddesi uyarınca talebinizin "
                  "sonuçlandırılabilmesi için söz konusu taşınmaza ait tapu belgesinin bir "
                  "örneğinin Müdürlüğümüze iletilmesi gerekmektedir.\n\n"
                  "Bilgilerinizi rica ederim."),
        "imza_ad": None, "imza_unvan": "Müdür",
    },
    "uslup_bulgulari": [],
    "linter_tur_sayisi": 1,
    "yonlendirme": {
        "birim": "imar_sehircilik", "birim_adi": "İmar ve Şehircilik Müdürlüğü",
        "skor": 0.90, "geregi_bilgi": "geregi", "kaynak": "llm",
        "gerekce": "İmar durum belgesi yalnızca bu müdürlükçe düzenlenir.",
        "kanit_cumle": "imar durum belgesi düzenlenmesini talep ediyorum",
        "alternatifler": [],
        "alternatif_adaylar": [
            {"birim": "yapi_kontrol", "birim_adi": "Yapı Kontrol Müdürlüğü", "skor": 0.29},
            {"birim": "emlak_istimlak", "birim_adi": "Emlak ve İstimlak Müdürlüğü", "skor": 0.18},
        ],
        "kurum_disinda": False,
    },
    "guven_kapisi": {"mod": "INSAN", "skor": 0.82, "esik": 0.85,
                     "sebep": "Kritik eksik bilgi var: tapu belgesi"},
    "adim_guveni": {3: 0.88, 4: 0.85, 5: 0.86, 6: 0.89, 7: 0.92, 8: 0.87, 10: 0.90},
    "adim_gerekcesi": {
        4: "Mevzuat katmanı tapu belgesi zorunluluğunu yakaladı, hata düzeyinde.",
        9: "40 kuralın tamamı ilk turda geçti.",
        11: "Yönlendirme güveni yüksek ama kritik eksik var → insan onayı.",
    },
}

SIRA = ["denklik", "imar", "nakil", "burs"]


# ===========================================================================
# DEPO
# ===========================================================================

EVRAKLAR: dict[str, dict] = {}
ABONELER: dict[str, set[asyncio.Queue]] = {}
_sayac = {"i": 0}
DEPO = pathlib.Path(__file__).with_name("evraklar.json")


def _kaydet() -> None:
    try:
        DEPO.write_text(json.dumps(EVRAKLAR, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


# Kayıtta bulunması gereken alanlar. Eski sürümden kalan evraklar.json
# yüklenip demoyu bozmasın diye şema denetimi yapılır.
ZORUNLU_ALANLAR = ("evrak_id", "durum", "dugum_kayitlari", "duzeltmeler", "gunluk")


def _diskten_yukle() -> bool:
    if not DEPO.exists():
        return False
    try:
        kayitlar = json.loads(DEPO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print("[uyarı] evraklar.json okunamadı, yok sayılıyor.")
        return False

    if not isinstance(kayitlar, dict) or not kayitlar:
        return False

    uyumsuz = [
        k for k, e in kayitlar.items()
        if not isinstance(e, dict) or any(a not in e for a in ZORUNLU_ALANLAR)
    ]
    if uyumsuz:
        print(f"[uyarı] evraklar.json eski şemada ({len(uyumsuz)}/{len(kayitlar)} kayıt "
              f"uyumsuz). Dosya yok sayıldı, tohum kayıtlar kuruluyor.")
        return False

    EVRAKLAR.update(kayitlar)
    for e in EVRAKLAR.values():
        if e.get("durum") in ("ALINDI", "ISLENIYOR"):
            e["durum"] = "HATA"
    return True


def _yeni_evrak(senaryo_ad: str, dosya_adi: str | None = None) -> dict:
    s = SENARYOLAR[senaryo_ad]
    return {
        "evrak_id": f"e_{uuid.uuid4().hex[:6]}",
        "calisma_id": f"c_{uuid.uuid4().hex[:4]}",
        "senaryo": senaryo_ad,
        "dosya_adi": dosya_adi or s["dosya_adi"],
        "yuklenme_ts": time.time(),
        "durum": "ALINDI",
        "toplam_ms": 0,
        "dugum_kayitlari": [],
        "gunluk": [],
        "duzeltmeler": [],
        "eksik_bilgi_talebi": None,
        "eksik_bilgi_cevabi": None,
        "sayfa_sayisi": 0,
        **{k: None for k in CIKTI_ANAHTARLARI if k != "sayfa_sayisi"},
    }


def _gunluge_yaz(evrak: dict, aktor: str, olay: str) -> None:
    evrak["gunluk"].append({"ts": time.time(), "aktor": aktor, "olay": olay})


def _dagit(evrak_id: str, olay: dict) -> None:
    for kuyruk in list(ABONELER.get(evrak_id, ())):
        try:
            kuyruk.put_nowait(olay)
        except asyncio.QueueFull:
            pass


def _kayit_bul(evrak: dict, no: int, tur_no: int) -> dict | None:
    for k in evrak["dugum_kayitlari"]:
        if k["no"] == no and k["tur_no"] == tur_no:
            return k
    return None


def _kayit_ac(evrak: dict, no: int, tur_no: int) -> dict:
    """Adım başladı: kaydı 'calisiyor' olarak aç. Her tur ayrı kayıttır."""
    mevcut = _kayit_bul(evrak, no, tur_no)
    if mevcut:
        mevcut["durum"] = "calisiyor"
        return mevcut
    kayit = {"no": no, "ad": DUGUM_HARITASI[no]["ad"], "tur_no": tur_no,
             "durum": "calisiyor", "sure_ms": None, "guven": None,
             "gerekce": None, "cikti": None}
    evrak["dugum_kayitlari"].append(kayit)
    return kayit


def _kayit_kapat(evrak: dict, no: int, tur_no: int, **alanlar) -> None:
    kayit = _kayit_bul(evrak, no, tur_no) or _kayit_ac(evrak, no, tur_no)
    kayit.update(alanlar)


def _anlik_goruntu(evrak: dict) -> dict:
    """Bağlanan istemcinin ekranı sıfırdan değil, mevcut durumdan çizmesi için."""
    return {
        "tur": "anlik_goruntu",
        "evrak_id": evrak["evrak_id"],
        "calisma_id": evrak["calisma_id"],
        "ts": time.time(),
        "durum": evrak["durum"],
        "canli": evrak["durum"] in ("ALINDI", "ISLENIYOR"),
        "toplam_ms": evrak.get("toplam_ms") or 0,
        "dugum_kayitlari": copy.deepcopy(evrak.get("dugum_kayitlari") or []),
    }


# ===========================================================================
# KOŞU
# ===========================================================================

async def _adim_kosu(evrak: dict, no: int, tur_no: int, yayinla) -> int:
    """Tek bir adımı koşturur, kaydını tutar, olaylarını yayınlar."""
    d = DUGUM_HARITASI[no]
    s = SENARYOLAR[evrak["senaryo"]]

    _kayit_ac(evrak, no, tur_no)
    await yayinla("dugum_basladi", dugum=no, dugum_adi=d["ad"],
                  bilesen=d["bilesen"], tur_no=tur_no)

    sure_ms = int(d["temel_ms"] * random.uniform(0.8, 1.25))
    await asyncio.sleep(sure_ms / 1000 * HIZ)

    cikti = copy.deepcopy(ADIM_CIKTISI[no](s))
    evrak.update(cikti)
    guven = s["adim_guveni"].get(no)
    gerekce = s["adim_gerekcesi"].get(no)

    _kayit_kapat(evrak, no, tur_no, durum="tamam", sure_ms=sure_ms,
                 guven=guven, gerekce=gerekce, cikti=cikti)
    await yayinla("dugum_bitti", dugum=no, dugum_adi=d["ad"], bilesen=d["bilesen"],
                  tur_no=tur_no, sure_ms=sure_ms, guven=guven, gerekce=gerekce,
                  cikti=cikti)
    _gunluge_yaz(evrak, "sistem", f"{d['baslik']}: {sure_ms} ms")
    return sure_ms


async def _linter_dongusu(evrak: dict, yayinla) -> int:
    """
    Üslup denetleyici (9) taslağı (8) geri gönderiyor. SEKİZ olay — sözleşme 6.4.
    Adım 8'in birinci turu bu fonksiyondan önce koşmuş olur.
    """
    s = SENARYOLAR[evrak["senaryo"]]
    bulgular = s["uslup_bulgulari"]
    ozet = " · ".join(f"{b['kural_no']}: {b['mesaj']}" for b in bulgular[:2])
    toplam = 0

    # 9 · birinci tur — ihlal bulur ve duraklar
    _kayit_ac(evrak, 9, 1)
    await yayinla("dugum_basladi", dugum=9, dugum_adi="uslup_denetleyici",
                  bilesen=6, tur_no=1)
    sure = int(300 * random.uniform(0.8, 1.25))
    await asyncio.sleep(sure / 1000 * HIZ)
    toplam += sure
    _kayit_kapat(evrak, 9, 1, durum="tamam", sure_ms=sure, gerekce=ozet)
    await yayinla("dugum_duraklatildi", dugum=9, dugum_adi="uslup_denetleyici",
                  bilesen=6, tur_no=1, sure_ms=sure, gerekce=ozet)
    _gunluge_yaz(evrak, "sistem",
                 f"Üslup denetimi: {len(bulgular)} bulgu — taslak geri gönderildi")

    # 8 · ikinci tur — taslak düzeltilir
    _kayit_ac(evrak, 8, 2)
    await yayinla("dugum_tekrar", dugum=8, dugum_adi="taslak", bilesen=6,
                  tur_no=2, gerekce="Bulgular düzeltiliyor.")
    sure = int(1200 * random.uniform(0.8, 1.25))
    await asyncio.sleep(sure / 1000 * HIZ)
    toplam += sure
    cikti8 = copy.deepcopy(ADIM_CIKTISI[8](s))
    evrak.update(cikti8)
    _kayit_kapat(evrak, 8, 2, durum="tamam", sure_ms=sure,
                 guven=s["adim_guveni"].get(8), gerekce="Bulgular düzeltildi.",
                 cikti=cikti8)
    await yayinla("dugum_bitti", dugum=8, dugum_adi="taslak", bilesen=6, tur_no=2,
                  sure_ms=sure, guven=s["adim_guveni"].get(8),
                  gerekce="Bulgular düzeltildi.", cikti=cikti8)

    # 9 · ikinci tur — geçer
    _kayit_ac(evrak, 9, 2)
    await yayinla("dugum_basladi", dugum=9, dugum_adi="uslup_denetleyici",
                  bilesen=6, tur_no=2)
    sure2 = int(300 * random.uniform(0.8, 1.25))
    await asyncio.sleep(sure2 / 1000 * HIZ)
    toplam += sure2
    cikti9 = copy.deepcopy(ADIM_CIKTISI[9](s))
    evrak.update(cikti9)
    _kayit_kapat(evrak, 9, 2, durum="tamam", sure_ms=sure2,
                 gerekce="40 kuralın tamamı geçti.", cikti=cikti9)
    await yayinla("dugum_bitti", dugum=9, dugum_adi="uslup_denetleyici", bilesen=6,
                  tur_no=2, sure_ms=sure2, gerekce="40 kuralın tamamı geçti.",
                  cikti=cikti9)
    _gunluge_yaz(evrak, "sistem", "Üslup denetimi: 2. turda geçti")
    return toplam


async def _kosuyu_oynat(evrak_id: str) -> None:
    evrak = EVRAKLAR[evrak_id]
    s = SENARYOLAR[evrak["senaryo"]]

    async def yayinla(tur: str, **alanlar):
        _dagit(evrak_id, {"tur": tur, "evrak_id": evrak_id,
                          "ts": time.time(), **alanlar})

    evrak["durum"] = "ISLENIYOR"
    await yayinla("durum_degisti", durum="ISLENIYOR")

    toplam = 0
    for no in range(1, 12):
        # 4 ve 5 paralel koşar: ikisi birlikte başlar, bitişleri karışık gelebilir
        if no == 4:
            toplam += max(await asyncio.gather(
                _adim_kosu(evrak, 4, 1, yayinla),
                _adim_kosu(evrak, 5, 1, yayinla),
            ))
            continue
        if no == 5:
            continue
        if no == 9 and s["linter_geri_gonderme"]:
            toplam += await _linter_dongusu(evrak, yayinla)
            continue
        toplam += await _adim_kosu(evrak, no, 1, yayinla)

    evrak["toplam_ms"] = toplam
    kapi = s["guven_kapisi"]
    evrak["durum"] = ("INSAN_ONAYI_BEKLIYOR" if kapi["mod"] == "INSAN"
                      else "OTOMATIK_ONAYLANDI")
    _gunluge_yaz(evrak, "sistem", f"Güven kapısı: {kapi['sebep']}")
    _kaydet()

    await yayinla("durum_degisti", durum=evrak["durum"])
    await yayinla("akis_bitti", durum=evrak["durum"], toplam_ms=toplam)


def _bitmis_kur(senaryo_ad: str, gecmis_sn: float, durum: str | None = None) -> dict:
    """Koşuyu oynatmadan bitmiş evrak üretir — açılış tohumu için."""
    s = SENARYOLAR[senaryo_ad]
    evrak = _yeni_evrak(senaryo_ad)
    evrak["yuklenme_ts"] = time.time() - gecmis_sn
    for k in CIKTI_ANAHTARLARI:
        evrak[k] = copy.deepcopy(s[k])

    toplam = 0
    for d in DUGUMLER:
        no = d["no"]
        turlar = [1, 2] if (no in (8, 9) and s["linter_geri_gonderme"]) else [1]
        for t in turlar:
            sure = int(d["temel_ms"] * random.uniform(0.85, 1.15))
            evrak["dugum_kayitlari"].append({
                "no": no, "ad": d["ad"], "tur_no": t, "durum": "tamam",
                "sure_ms": sure, "guven": s["adim_guveni"].get(no),
                "gerekce": s["adim_gerekcesi"].get(no), "cikti": None,
            })
            if not (no == 5 and t == 1):  # 4 ile paralel, toplam süreye eklenmez
                toplam += sure
            evrak["gunluk"].append({
                "ts": evrak["yuklenme_ts"] + toplam / 1000,
                "aktor": "sistem", "olay": f"{d['baslik']}: {sure} ms"})

    evrak["toplam_ms"] = toplam
    kapi = s["guven_kapisi"]
    evrak["durum"] = durum or ("INSAN_ONAYI_BEKLIYOR" if kapi["mod"] == "INSAN"
                               else "OTOMATIK_ONAYLANDI")
    evrak["gunluk"].append({
        "ts": evrak["yuklenme_ts"] + toplam / 1000 + 0.1,
        "aktor": "sistem", "olay": f"Güven kapısı: {kapi['sebep']}"})
    return evrak


def _tohumla() -> None:
    for ad, gecmis, durum in [("nakil", 47 * 60, None),
                              ("burs", 14 * 60, None),
                              ("imar", 5 * 3600, "ONAYLANDI")]:
        e = _bitmis_kur(ad, gecmis, durum)
        if ad == "imar":
            e["duzeltmeler"].append({
                "tur": "birim", "rol": "birim_sorumlusu", "ts": e["yuklenme_ts"] + 900,
                "eski": "yapi_kontrol", "yeni": "imar_sehircilik",
                "gerekce": "İmar durum belgesi yapı kontrolde düzenlenmez."})
            e["gunluk"].append({
                "ts": e["yuklenme_ts"] + 900, "aktor": "birim_sorumlusu",
                "olay": "birim_degistir — İmar durum belgesi yapı kontrolde düzenlenmez."})
        EVRAKLAR[e["evrak_id"]] = e


# ===========================================================================
# UYGULAMA
# ===========================================================================

@asynccontextmanager
async def _yasam(_app: FastAPI):
    if not _diskten_yukle():
        _tohumla()
        _kaydet()
    yield


app = FastAPI(title="Evrak Ajan Sistemi — Sahte Sunucu", lifespan=_yasam)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"], allow_headers=["*"],
)

ONAYLAYAN = ("birim_sorumlusu", "yonetici")


def _evrak_bul(evrak_id: str) -> dict:
    if evrak_id not in EVRAKLAR:
        raise HTTPException(404, "Evrak bulunamadı")
    return EVRAKLAR[evrak_id]


# ---------------------------------------------------------------- tanım
@app.get("/api/surum")
async def surum():
    return {
        "surum": SURUM,
        "adim_sayisi": len(DUGUMLER),
        "bilesen_sayisi": len({d["bilesen"] for d in DUGUMLER}),
        "ajan_sayisi": len({d["ajan"] for d in DUGUMLER if d["ajan"]}),
        "islemler": ["onayla", "taslak_kaydet", "reddet", "birim_degistir",
                     "eksik_bilgi_iste", "eksik_bilgi_cevabi", "karari_geri_al"],
        "model": "sahte-sunucu (model yok)",
        "birim_kaynagi": BIRIM_KAYNAGI,
    }


@app.get("/api/dugumler")
async def dugum_tanimlari():
    return {
        "dugumler": [{k: d[k] for k in
                      ("no", "ad", "baslik", "aciklama", "motor",
                       "bilesen", "bilesen_adi", "satir", "ajan")}
                     for d in DUGUMLER],
        "paralel_gruplar": PARALEL_GRUPLAR,
    }


@app.get("/api/birimler")
async def birim_listesi():
    return BIRIMLER


# ---------------------------------------------------------------- evrak
@app.post("/api/evrak", status_code=202)
async def evrak_yukle(dosya: UploadFile = File(...)):
    senaryo = SIRA[_sayac["i"] % len(SIRA)]
    _sayac["i"] += 1
    evrak = _yeni_evrak(senaryo, dosya.filename)
    EVRAKLAR[evrak["evrak_id"]] = evrak
    ABONELER[evrak["evrak_id"]] = set()
    _kaydet()
    asyncio.create_task(_kosuyu_oynat(evrak["evrak_id"]))
    return {"evrak_id": evrak["evrak_id"], "calisma_id": evrak["calisma_id"],
            "durum": evrak["durum"]}


def _ozet(e: dict) -> dict:
    eksikler = e.get("eksikler") or []
    yon = e.get("yonlendirme") or {}
    kapi = e.get("guven_kapisi") or {}
    ust = e.get("ustveri") or {}
    return {
        "evrak_id": e["evrak_id"],
        "dosya_adi": e["dosya_adi"],
        "durum": e["durum"],
        "yuklenme_ts": e["yuklenme_ts"],
        "bekleme_sn": int(time.time() - e["yuklenme_ts"]),
        "toplam_ms": e["toplam_ms"],
        "sayi": (ust.get("sayi") or {}).get("deger"),
        "konu": (ust.get("konu") or {}).get("deger"),
        "belge_turu": (e.get("belge_turu") or {}).get("deger"),
        "birim": yon.get("birim"),
        "birim_adi": yon.get("birim_adi"),
        "guven": kapi.get("skor"),
        "esik": kapi.get("esik"),
        "sebep": kapi.get("sebep"),
        "eksik_sayisi": len(eksikler),
        "kritik_eksik_sayisi": sum(
            1 for x in eksikler if x["onem"] == "hata" and not x.get("giderildi")),
        "duzeltme_sayisi": len(e["duzeltmeler"]),
    }


@app.get("/api/evrak")
async def evrak_listesi(x_rol: str = Header(default="kayit_memuru"),
                        x_birim: str | None = Header(default=None)):
    kayitlar = sorted(EVRAKLAR.values(), key=lambda x: -x["yuklenme_ts"])
    # Rol süzmesi sunucuda: birim sorumlusu yalnızca kendi birimini görür
    if x_rol == "birim_sorumlusu" and x_birim:
        kayitlar = [e for e in kayitlar
                    if (e.get("yonlendirme") or {}).get("birim") == x_birim]
    return [_ozet(e) for e in kayitlar]


@app.get("/api/evrak/{evrak_id}")
async def evrak_detay(evrak_id: str):
    e = _evrak_bul(evrak_id)
    cikti = {k: v for k, v in e.items() if k != "senaryo"}
    if e.get("varliklar"):
        cikti["varliklar"] = [_varlik_sunum(v) for v in e["varliklar"]]
    return cikti


@app.get("/api/evrak/{evrak_id}/metin")
async def evrak_metni(evrak_id: str):
    e = _evrak_bul(evrak_id)
    s = SENARYOLAR[e["senaryo"]]
    return {
        "evrak_id": evrak_id, "dosya_adi": e["dosya_adi"],
        "sayfa_sayisi": s["sayfa_sayisi"], "karakter": s["karakter"],
        "girdi_tipi": s["girdi_tipi"], "ocr_motoru": s["ocr_motoru"],
        "metin": s["metin"],
    }


@app.get("/api/evrak/{evrak_id}/varlik/{sira}/ham")
async def varlik_ham(evrak_id: str, sira: int,
                     x_rol: str = Header(default="kayit_memuru")):
    """Kişisel verinin maskesiz hâli. Her çağrı işlem günlüğüne yazılır."""
    e = _evrak_bul(evrak_id)
    varlik = next((v for v in (e.get("varliklar") or []) if v["sira"] == sira), None)
    if varlik is None:
        raise HTTPException(404, "Varlık bulunamadı")
    if varlik["tur"] not in KISISEL_TIPLER:
        raise HTTPException(404, "Bu varlık kişisel veri değil")
    _gunluge_yaz(e, x_rol, f"Kişisel veri açıldı: varlık {sira} ({varlik['tur']})")
    _kaydet()
    return {"sira": sira, "tur": varlik["tur"], "deger": varlik["deger"],
            "acan_rol": x_rol}


@app.get("/api/evrak/{evrak_id}/akis")
async def evrak_akisi(evrak_id: str):
    evrak = _evrak_bul(evrak_id)

    async def uret():
        goruntu = _anlik_goruntu(evrak)
        yield f"data: {json.dumps(goruntu, ensure_ascii=False)}\n\n"
        if not goruntu["canli"]:
            return
        kuyruk: asyncio.Queue = asyncio.Queue()
        ABONELER.setdefault(evrak_id, set()).add(kuyruk)
        try:
            while True:
                olay = await kuyruk.get()
                yield f"data: {json.dumps(olay, ensure_ascii=False)}\n\n"
                if olay.get("tur") == "akis_bitti":
                    break
        finally:
            ABONELER.get(evrak_id, set()).discard(kuyruk)

    return StreamingResponse(
        uret(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------- karar
ALAN_ETIKETLERI = {
    "tapu_belgesi": "Tapu belgesi",
    "iletisim_telefon": "İletişim telefonu",
    "basvuru_numarasi": "Başvuru numarası",
    "gelir_belgesi_tarihi": "Gelir belgesi yükleme kaydı",
}


def _alan_etiketi(alan: str) -> str:
    if alan in ALAN_ETIKETLERI:
        return ALAN_ETIKETLERI[alan]
    metin = alan.replace("_", " ")
    return ("İ" if metin[:1] == "i" else metin[:1].upper()) + metin[1:]


def _eksik_bilgi_talebi(evrak: dict, s: dict, sorular: list[str]) -> dict:
    """Kamuda eksik bilgi istemek bir EKSİK TAMAMLAMA YAZISI'dır."""
    gonderen = s["gonderen"]
    kurum_mu = gonderen["tur"] == "kurum"
    sure_gun = 15 if kurum_mu else 30
    dayanak = ("Resmî Yazışmalarda Uygulanacak Usul ve Esaslar Hakkında Yönetmelik"
               if kurum_mu else
               "3071 sayılı Dilekçe Hakkının Kullanılmasına Dair Kanun m.7 "
               "(30 günlük cevap süresi)")
    bitis = time.localtime(time.time() + sure_gun * 86400)
    son_iso = time.strftime("%Y-%m-%d", bitis)
    son_gosterim = time.strftime("%d.%m.%Y", bitis)

    muhatap = gonderen["ad"].upper() if kurum_mu else f"Sayın {gonderen['ad']}"
    maddeler = "\n".join(f"{i}) {q}" for i, q in enumerate(sorular, 1))
    taslak = evrak.get("taslak") or {}
    talep = (s.get("talep") or "talebiniz").rstrip(".")

    govde = (
        f"{'İlgi yazınızda' if kurum_mu else 'İlgi dilekçenizde'} belirtilen {talep} "
        f"hususunda işlem yapılabilmesi için aşağıdaki bilgi ve belgelere ihtiyaç "
        f"duyulmaktadır:\n\n{maddeler}\n\n"
        f"Söz konusu eksikliklerin {son_gosterim} tarihine kadar Müdürlüğümüze "
        f"iletilmesi hâlinde başvurunuz sonuçlandırılacaktır. Belirtilen sürede "
        f"tamamlanmaması durumunda işlem dosyası mevcut hâliyle "
        f"değerlendirilecektir.\n\n"
        f"Bilgilerinizi {'arz' if kurum_mu else 'rica'} ederim."
    )
    return {
        "ts": time.time(),
        "muhatap_ad": gonderen["ad"], "muhatap_turu": gonderen["tur"],
        "kanal": "Resmî yazı (KEP / posta)" if kurum_mu
                 else "Resmî yazı (posta / e-Devlet)",
        "sure_gun": sure_gun, "son_tarih": son_iso, "dayanak": dayanak,
        "sorular": sorular,
        "yazi": {
            "baslik": taslak.get("baslik", ""), "sayi": None, "tarih": None,
            "konu": "Eksik Bilgi ve Belge Tamamlama", "muhatap": muhatap,
            "govde": govde, "imza_ad": None,
            "imza_unvan": taslak.get("imza_unvan", ""),
        },
        "elle_duzenlendi": False,
    }


def _taslagi_yenile(evrak: dict, s: dict) -> None:
    """Eksik tamamlandı: 'şu belgeyi gönderin' diyen taslak artık geçersiz."""
    giderilen = [e for e in (evrak.get("eksikler") or []) if e.get("giderildi")]
    if not giderilen or not evrak.get("taslak"):
        return
    maddeler = "\n".join(f"{i}) {_alan_etiketi(e['alan'])}: {e.get('cevap', '')}"
                         for i, e in enumerate(giderilen, 1))
    kurum_mu = s["gonderen"]["tur"] == "kurum"
    talep = (s.get("talep") or "talebiniz").rstrip(".")
    evrak["taslak"] = {**evrak["taslak"], "govde": (
        f"{'İlgi yazınızda' if kurum_mu else 'İlgi dilekçenizde'} belirtilen {talep} "
        f"hususundaki başvurunuz, tarafınızca iletilen bilgi ve belgelerle birlikte "
        f"Müdürlüğümüzce yeniden değerlendirilmiştir.\n\n"
        f"Eksikliği bildirilen hususlar aşağıdaki şekilde tamamlanmıştır:\n\n"
        f"{maddeler}\n\n"
        f"Başvurunuz işleme alınmış olup, sonucundan ayrıca bilgi verilecektir.\n\n"
        f"Bilgilerinizi {'arz' if kurum_mu else 'rica'} ederim.")}
    evrak["uslup_bulgulari"] = []
    evrak["linter_tur_sayisi"] = 1


@app.post("/api/evrak/{evrak_id}/eksik_bilgi_onizleme")
async def eksik_bilgi_onizleme(evrak_id: str, govde: dict):
    """Yazıyı üretir, hiçbir durumu değiştirmez."""
    e = _evrak_bul(evrak_id)
    sorular = govde.get("sorular") or []
    if not sorular:
        raise HTTPException(400, "En az bir soru seçilmeli")
    return _eksik_bilgi_talebi(e, SENARYOLAR[e["senaryo"]], sorular)


@app.post("/api/evrak/{evrak_id}/karar")
async def karar_ver(evrak_id: str, govde: dict):
    evrak = _evrak_bul(evrak_id)
    aksiyon = govde.get("aksiyon")
    rol = govde.get("rol", "")
    gerekce = (govde.get("gerekce") or "").strip()

    if rol not in ONAYLAYAN:
        raise HTTPException(403, "Bu rolün onay yetkisi yok")
    if aksiyon in ("reddet", "birim_degistir", "karari_geri_al") and not gerekce:
        raise HTTPException(400, "Bu işlem için gerekçe zorunlu")

    if aksiyon == "onayla":
        if evrak["durum"] not in ACIK:
            raise HTTPException(409, "Bu evrak zaten sonuçlanmış")
        evrak["durum"] = "ONAYLANDI"

    elif aksiyon == "taslak_kaydet":
        for yasak in ("taslak_sayi", "taslak_tarih", "taslak_imza_ad"):
            if govde.get(yasak):
                raise HTTPException(
                    400, "Sayı, tarih ve imzalayan EBYS'de atanır; düzenlenemez")
        guncel = dict(evrak["taslak"] or {})
        degisen = []
        for alan in ("baslik", "konu", "muhatap", "govde"):
            deger = govde.get("taslak_" + alan)
            if deger is not None and deger.strip() and deger != guncel.get(alan):
                guncel[alan] = deger.strip()
                degisen.append(alan)
        if not degisen:
            raise HTTPException(400, "Değişiklik yok")
        evrak["taslak"] = guncel
        evrak["duzeltmeler"].append({"tur": "taslak", "rol": rol,
                                     "ts": time.time(), "alanlar": degisen})
        etiket = {"baslik": "başlık", "konu": "konu",
                  "muhatap": "muhatap", "govde": "gövde"}
        _gunluge_yaz(evrak, rol, "Taslak düzenlendi — " +
                     ", ".join(etiket[a] for a in degisen))
        _kaydet()
        return {"durum": evrak["durum"], "duzeltme_sayisi": len(evrak["duzeltmeler"])}

    elif aksiyon == "reddet":
        if evrak["durum"] not in ACIK:
            raise HTTPException(409, "Bu evrak zaten sonuçlanmış")
        evrak["durum"] = "REDDEDILDI"
        evrak["duzeltmeler"].append({"tur": "red", "rol": rol, "ts": time.time(),
                                     "gerekce": gerekce})

    elif aksiyon == "birim_degistir":
        yeni = govde.get("yeni_birim")
        hedef = BIRIM_HARITASI.get(yeni or "")
        if not hedef or not hedef["hedef_olabilir"]:
            raise HTTPException(400, "Geçersiz hedef birim")
        eski = (evrak.get("yonlendirme") or {}).get("birim")
        evrak["yonlendirme"] = {**(evrak["yonlendirme"] or {}),
                                "birim": yeni, "birim_adi": hedef["ad"]}
        evrak["duzeltmeler"].append({"tur": "birim", "rol": rol, "ts": time.time(),
                                     "eski": eski, "yeni": yeni, "gerekce": gerekce})
        _gunluge_yaz(evrak, rol,
                     f"birim_degistir — {_birim_adi(eski)} → {hedef['ad']} · {gerekce}")
        _kaydet()
        return {"durum": evrak["durum"], "duzeltme_sayisi": len(evrak["duzeltmeler"])}

    elif aksiyon == "eksik_bilgi_iste":
        sorular = govde.get("sorular") or []
        if not sorular:
            raise HTTPException(400, "En az bir soru seçilmeli")
        talep = _eksik_bilgi_talebi(evrak, SENARYOLAR[evrak["senaryo"]], sorular)
        elle = govde.get("yazi")
        if isinstance(elle, dict):
            temiz = {k: v for k, v in elle.items()
                     if v and k in ("baslik", "konu", "muhatap", "govde")}
            if temiz:
                talep["yazi"] = {**talep["yazi"], **temiz}
                talep["elle_duzenlendi"] = True
        evrak["eksik_bilgi_talebi"] = talep
        evrak["durum"] = "EKSIK_BILGI_BEKLIYOR"
        _gunluge_yaz(evrak, rol,
                     f"Eksik tamamlama yazısı üretildi → {talep['muhatap_ad']} "
                     f"({len(sorular)} soru, son tarih {talep['son_tarih']})")
        _kaydet()
        return {"durum": evrak["durum"], "duzeltme_sayisi": len(evrak["duzeltmeler"])}

    elif aksiyon == "eksik_bilgi_cevabi":
        talep = evrak.get("eksik_bilgi_talebi")
        if not talep:
            raise HTTPException(409, "Bu evrakta bekleyen eksik bilgi talebi yok")
        dolu = [c for c in (govde.get("cevaplar") or [])
                if (c.get("cevap") or "").strip()]
        if not dolu:
            raise HTTPException(400, "En az bir soruya cevap girilmeli")
        harita = {c["soru"]: c["cevap"].strip() for c in dolu}
        kalan_kritik = 0
        for eksik in evrak.get("eksikler") or []:
            if eksik["soru"] in harita:
                eksik["giderildi"] = True
                eksik["cevap"] = harita[eksik["soru"]]
            elif eksik["onem"] == "hata" and not eksik.get("giderildi"):
                kalan_kritik += 1
        evrak["eksik_bilgi_cevabi"] = {
            "ts": time.time(), "gonderen": talep["muhatap_ad"],
            "ilgi": (evrak.get("taslak") or {}).get("konu", "") + " · tamamlama",
            "cevaplar": dolu}
        kapi = dict(evrak.get("guven_kapisi") or {})
        eski_skor = kapi.get("skor", 0.0)
        kapi["skor"] = min(0.97, round(eski_skor + 0.10 * len(dolu), 2))
        kapi["mod"] = "INSAN"
        kapi["sebep"] = (f"Eksik bilgi tamamlandı ({len(dolu)} cevap). "
                         "Yeniden değerlendirildi."
                         if kalan_kritik == 0
                         else f"{kalan_kritik} kritik eksik hâlâ açık.")
        evrak["guven_kapisi"] = kapi
        evrak["durum"] = "INSAN_ONAYI_BEKLIYOR"
        _taslagi_yenile(evrak, SENARYOLAR[evrak["senaryo"]])
        _gunluge_yaz(evrak, talep["muhatap_ad"],
                     f"Eksik bilgi cevabı alındı ({len(dolu)} soru)")
        _gunluge_yaz(evrak, "sistem",
                     f"Denetçi, Karar Verici ve Taslak yeniden çalıştırıldı · "
                     f"güven {eski_skor:.2f} → {kapi['skor']:.2f}")
        _kaydet()
        return {"durum": evrak["durum"], "duzeltme_sayisi": len(evrak["duzeltmeler"])}

    elif aksiyon == "karari_geri_al":
        if rol != "yonetici":
            raise HTTPException(403, "Kararı yalnızca Kurum Yöneticisi geri alabilir")
        if evrak["durum"] not in SONUCLANMIS:
            raise HTTPException(409, "Bu evrakta geri alınacak karar yok")
        onceki = evrak["durum"]
        evrak["durum"] = "INSAN_ONAYI_BEKLIYOR"
        evrak["duzeltmeler"].append({"tur": "geri_alma", "rol": rol,
                                     "ts": time.time(), "gerekce": gerekce})
        _gunluge_yaz(evrak, rol,
                     f"Karar geri alındı ({DURUM_ETIKET[onceki]}) — {gerekce}")
        _kaydet()
        return {"durum": evrak["durum"], "duzeltme_sayisi": len(evrak["duzeltmeler"])}

    else:
        raise HTTPException(400, f"Bilinmeyen işlem: {aksiyon}")

    _gunluge_yaz(evrak, rol, aksiyon + (f" — {gerekce}" if gerekce else ""))
    _kaydet()
    return {"durum": evrak["durum"], "duzeltme_sayisi": len(evrak["duzeltmeler"])}


@app.post("/api/sifirla")
async def sifirla():
    EVRAKLAR.clear()
    ABONELER.clear()
    _sayac["i"] = 0
    _tohumla()
    _kaydet()
    return {"durum": "sifirlandi", "kayit": len(EVRAKLAR)}


# ---------------------------------------------------------------- istatistik
@app.get("/api/istatistik")
async def istatistik(x_rol: str = Header(default="kayit_memuru")):
    if x_rol != "yonetici":
        raise HTTPException(403, "İstatistik yalnızca Kurum Yöneticisine açıktır")

    bitmis = [e for e in EVRAKLAR.values() if (e.get("toplam_ms") or 0) > 0]
    if not bitmis:
        return {"toplam_evrak": 0, "bos": True}

    n = len(bitmis)
    sureler = sorted(e["toplam_ms"] for e in bitmis)

    def yuzdelik(dizi: list[int], p: float) -> int:
        if not dizi:
            return 0
        d = sorted(dizi)
        return d[min(len(d) - 1, int(round((len(d) - 1) * p)))]

    # ---- adım bazlı süreler (turlar toplanır) ----
    dugum_dagilimi, adim_ort = [], {}
    for d in DUGUMLER:
        degerler = []
        for e in bitmis:
            toplam = sum((k.get("sure_ms") or 0)
                         for k in (e.get("dugum_kayitlari") or [])
                         if k.get("no") == d["no"])
            degerler.append(toplam)
        ort = round(sum(degerler) / n)
        adim_ort[d["no"]] = ort
        dugum_dagilimi.append({"no": d["no"], "ad": d["ad"], "baslik": d["baslik"],
                               "motor": d["motor"], "ortalama_ms": ort,
                               "p95_ms": yuzdelik(degerler, 0.95)})

    sirali_toplam = sum(adim_ort.values())
    gerceklesen = round(sum(sureler) / n)

    motor_ms: dict[str, int] = {}
    for d in dugum_dagilimi:
        motor_ms[d["motor"]] = motor_ms.get(d["motor"], 0) + d["ortalama_ms"]

    skorlar = [(e.get("guven_kapisi") or {}).get("skor") for e in bitmis]
    skorlar = [s for s in skorlar if s is not None]
    esik = next(((e.get("guven_kapisi") or {}).get("esik") for e in bitmis
                 if (e.get("guven_kapisi") or {}).get("esik")), 0.85)

    yonlendirmeli = [e for e in bitmis if e.get("yonlendirme")]
    duzeltmeler = [
        {"eski": _birim_adi(d.get("eski")), "yeni": _birim_adi(d.get("yeni")),
         "konu": ((e.get("ustveri") or {}).get("konu") or {}).get("deger"),
         "gerekce": d.get("gerekce", "")}
        for e in bitmis for d in e["duzeltmeler"] if d.get("tur") == "birim"
    ]
    yanlis = sum(1 for e in bitmis
                 if any(d.get("tur") == "birim" for d in (e.get("duzeltmeler") or [])))
    isabet = round(1 - yanlis / len(yonlendirmeli), 3) if yonlendirmeli else 0.0

    katman = {"sema": 0, "kural": 0, "mevzuat": 0, "cikarim": 0}
    onem = {"bilgi": 0, "uyari": 0, "hata": 0}
    eksik_toplam = giderilen = 0
    for e in bitmis:
        for x in e.get("eksikler") or []:
            eksik_toplam += 1
            katman[x["katman"]] = katman.get(x["katman"], 0) + 1
            onem[x["onem"]] = onem.get(x["onem"], 0) + 1
            if x.get("giderildi"):
                giderilen += 1

    # Mevzuat eleme — "getirdim ama doğrulayamadım, göstermiyorum".
    # benzerlik bir getirme skoru; dogrulandi Denetçi'nin kendi çıktısını elemesi.
    # İkisi ayrı şeydir, o yüzden belge başına değil pano düzeyinde raporlanır.
    dogr, elen = [], []
    for e in bitmis:
        for mv in e.get("mevzuat") or []:
            (dogr if mv.get("dogrulandi") else elen).append(mv.get("benzerlik") or 0.0)

    kural_siklik: dict[str, dict] = {}
    for e in bitmis:
        for b in e.get("uslup_bulgulari") or []:
            kayit = kural_siklik.setdefault(b["kural_no"], {
                "kural_no": b["kural_no"], "mesaj": b["mesaj"],
                "mevzuat": b["mevzuat"], "duzey": b["duzey"], "adet": 0})
            kayit["adet"] += 1

    def say(fn) -> dict[str, int]:
        d: dict[str, int] = {}
        for e in bitmis:
            k = fn(e)
            if k:
                d[k] = d.get(k, 0) + 1
        return d

    bekleyenler = [e for e in EVRAKLAR.values() if e["durum"] in ACIK]
    bekleme = [int(time.time() - e["yuklenme_ts"]) for e in bekleyenler]
    birim_say = say(lambda e: (e.get("yonlendirme") or {}).get("birim_adi"))

    return {
        "bos": False,
        "toplam_evrak": n,
        "otomatik_onay_orani": round(
            sum(1 for e in bitmis if e["durum"] == "OTOMATIK_ONAYLANDI") / n, 3),
        "insan_duzeltme_orani": round(
            sum(1 for e in bitmis if e.get("duzeltmeler")) / n, 3),
        "ortalama_sure_ms": gerceklesen,
        "p50_sure_ms": yuzdelik(sureler, 0.5),
        "p95_sure_ms": yuzdelik(sureler, 0.95),
        "en_hizli_ms": sureler[0],
        "en_yavas_ms": sureler[-1],
        "dugum_dagilimi": dugum_dagilimi,
        "sirali_toplam_ms": sirali_toplam,
        "gerceklesen_toplam_ms": gerceklesen,
        "motor_ms": motor_ms,
        "guven_skorlari": skorlar,
        "esik": esik,
        "yonlendirme_isabet": isabet,
        "yonlendirme_duzeltmeleri": duzeltmeler,
        "yonlendirilen": len(yonlendirmeli),
        "eksik_katman": katman,
        "eksik_onem": onem,
        "eksik_toplam": eksik_toplam,
        "eksik_giderilen": giderilen,
        "mevzuat_getirilen": len(dogr) + len(elen),
        "mevzuat_dogrulanan": len(dogr),
        "mevzuat_elenen": len(elen),
        "benzerlik_dogrulanan_ort": round(sum(dogr) / len(dogr), 3) if dogr else 0.0,
        "benzerlik_elenen_ort": round(sum(elen) / len(elen), 3) if elen else 0.0,
        "linter_ilk_tur_gecme": round(
            sum(1 for e in bitmis if (e.get("linter_tur_sayisi") or 1) == 1) / n, 3),
        "linter_kurallar": sorted(kural_siklik.values(), key=lambda x: -x["adet"]),
        "durum_dagilimi": say(lambda e: e["durum"]),
        "belge_turu_dagilimi": say(lambda e: (e.get("belge_turu") or {}).get("deger")),
        "birim_dagilimi": sorted(
            [{"birim_adi": k, "adet": v} for k, v in birim_say.items()],
            key=lambda x: -x["adet"]),
        "bekleyen": len(bekleyenler),
        "kritik_eksikli": sum(
            1 for e in EVRAKLAR.values()
            if any(x["onem"] == "hata" and not x.get("giderildi")
                   for x in (e.get("eksikler") or []))),
        "bekleme_ortalama_sn": round(sum(bekleme) / len(bekleme)) if bekleme else 0,
    }
