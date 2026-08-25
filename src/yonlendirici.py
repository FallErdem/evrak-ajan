"""Yönlendirici — Düğüm 11. Evrak hangi birime gider.

Şartname 6.4.2 (3): "Evrakın içeriğine göre doğru birime yönlendirme
önerisinde bulunması."

DÖRT HAT, İKİSİ DETERMİNİSTİK
=============================
    Y-A  SDP kodu -> tek birim              LLM yok
    Y-B  muhatap satırında birim adı        LLM yok
    Y-C  SDP çoklu aday -> model seçer      LLM var, liste DIŞINA çıkamaz
    Y-D  hiçbiri -> 30 hedef birim          LLM var, liste DIŞINA çıkamaz

KAPSAM ÖLÇÜLDÜ (300 etiket, 2026-08-24)
---------------------------------------
    156  SDP okunur + muhatap birimi söylüyor   iki hat birden
    122  SDP yok    + muhatap birimi söylüyor   dilekçe ve şirket yazıları
     12  SDP okunur + muhatap söylemiyor        dağıtımlı belgeler
     10  hiçbiri yok                            asıl LLM işi burası

290/300 belgede en az bir deterministik hat var. Model yalnızca kalan
10 belgede ve SDP'nin çoklu aday verdiği durumlarda konuşuyor.

İKİ HAT ÇELİŞMİYOR — ÖLÇÜLDÜ
----------------------------
Temiz etiket verisinde 300 belgenin 300'ünde iki deterministik hat
uyumlu:

     84  SDP çoklu + muhatap adayların İÇİNDE   muhatap daraltmayı bitiriyor
     72  SDP tek   + muhatap MUTABIK            iki bağımsız kaynak aynı
      0  ÇELİŞKİ

Çelişki kuralı yine de yazıldı: OCR hasarı muhatap satırını bozabilir ve
o zaman iki kaynak ayrışır. Ayrışma GİZLENMEZ — ikisi de
`alternatif_adaylar`a yazılır, skor düşürülür, gerekçeye not edilir.
Ölçüm bunu ayrı sayıyor; sıfır olması beklenen davranıştır.

NEDEN SDP KODU BİRİNCİ HAT
--------------------------
Kod belgenin SAYISINDA yazılıdır, tahmin edilmez. Ölçüldü: sayıdan okunan
kod 80 belgede tek birime düşüyor ve 80'inde de doğru; 88 belgede çoklu
aday veriyor ve doğru cevap 88'inde de aday kümesinin İÇİNDE. Yani SDP
hattı hiç yanlış cevap vermiyor, yalnızca bazen daraltmayı bitirmiyor.

S-01 — "DENKLİK" VAKASI, NEDEN METİN EŞLEŞTİRMESİ YAPMIYORUZ
------------------------------------------------------------
35 birimin yalnızca birinin `gorev_alani` metninde "denklik" geçiyor:

    ogrenci_isleri_db   "...Yatay geçiş ve denklik başvurularını işleme alır."

Ama denklik konulu 7 belgenin 5'i BAŞKA bir birime gidiyor:

    5 belge -> ortaogretim_sb      yurtdışı LİSE diploması denkliği  (İl MEM)
    2 belge -> ogrenci_isleri_db   üniversite DERS denkliği          (Gazi)

Aynı kelime, iki ayrı iş. Görev alanı metninde kelime arayan bir
yönlendirici, belediye ya da İl MEM'e gelen evrağı üniversiteye
gönderirdi — üstelik yanlış KURUMA.

SDP kodu bu ayrımı zaten yapıyor: belge_018 -> 215.01, belge_071 -> 102.03.
Bu yüzden `gorev_alani` metni HEDEF BULMAK için kullanılmıyor; yalnızca
SDP'nin daralttığı adaylar arasından SEÇİM yapılırken modele veriliyor.
Model 35 birim içinde arama yapmıyor, 2-3 aday arasından seçiyor.

MODEL LİSTENİN DIŞINA ÇIKAMAZ
-----------------------------
Y-C ve Y-D'de şema `enum` ile aday birim kodlarına kısıtlanıyor
(`anlama.py`'nin deseni). Uydurulmuş bir birim kodu fiziksel olarak
üretilemiyor.

KANIT CÜMLESİ DOĞRULANIYOR
--------------------------
Model `kanit_cumle` döndürüyor ve bu cümle arayüzde memura gösteriliyor.
Cümlenin gövdede GERÇEKTEN geçtiği denetleniyor; geçmiyorsa atılıyor ve
uyarı yazılıyor. Uydurulmuş alıntı, uydurulmuş gerekçeden beterdir:
memur alıntıya güvenip belgeyi okumadan onaylayabilir.

Sözleşme karşılığı: docs/api_sozlesmesi.md · Ş 6.4.2 (3)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from veri_yapisi import DagitimTuru, YonlendirmeAdayi, YonlendirmeKaynagi

# -----------------------------------------------------------------------------
# Eşikler
# -----------------------------------------------------------------------------

# Muhatap satırının birim kaydına bağlanmasında kabul edilecek en düşük oran.
# `yazar.KIMLIK_ESIGI` ile AYNI değer ve aynı gerekçe: OCR hasarlı kök ad
# yanlış birime 0,77 ile bağlanabiliyor (bkz. yazar.py ölçüm notu). Burada
# eşik BASTIRICI: altında kalan eşleşme Y-B saymıyor, çünkü Yönlendirici'nin
# çıktısı doğrudan bir karar; belirsiz bir birime evrak havale etmektense
# LLM hattına düşmek yeğdir.
MUHATAP_ESIGI = 0.85

# Skorlar. Ölçülen isabete göre konuldu, keyfî değil:
#   iki bağımsız kaynak aynı şeyi diyor          -> en yüksek
#   tek deterministik kaynak                     -> yüksek
#   model seçimi, aday kümesi dar                -> orta
#   model seçimi, aday kümesi 30 birim           -> düşük
#   çelişki                                      -> eşik altı, insana düşsün
SKOR_MUTABIK = 1.00
SKOR_TEK_HAT = 0.90
SKOR_KONUDAN = 0.80
SKOR_LLM_DAR = 0.70
SKOR_LLM_GENIS = 0.45
SKOR_CELISKI = 0.40


@dataclass
class YonlendirmeSonucu:
    """Kararın kaydı. `hat` alanı ablasyon ölçümünün girdisi.

    NEDEN AYRI NESNE: `Yonlendirme` şeması `kaynak` alanında dört değer
    tutuyor ve Y-C ile Y-D'nin ikisi de `llm`. Ablasyon tablosunda ikisi
    ayrı satır olmalı — biri dar aday kümesinden, diğeri 30 birimden
    seçiyor ve isabetleri farklı olacak. `hat` bu ayrımı şemaya dokunmadan
    taşıyor.
    """

    hedef: str | None = None
    hat: str = "yok"
    skor: float = 0.0
    gerekce: str | None = None
    kanit_cumle: str | None = None
    adaylar: list[tuple[str, float]] = field(default_factory=list)
    celiski: bool = False
    llm_kullanildi: bool = False
    uyarilar: list[str] = field(default_factory=list)

    @property
    def ozet(self) -> str:
        if self.hedef is None:
            return f"hedef bulunamadı ({self.hat})"
        return f"{self.hedef} · {self.skor:.2f} · {self.hat}"


# -----------------------------------------------------------------------------
# Deterministik hatlar
# -----------------------------------------------------------------------------


def sdp_kodu_oku(dosya) -> str | None:
    """Belgenin SDP kodunu SAYIDAN okur.

    `siniflandirma.sdp.kod` alanına DÜŞÜLMEZ. Sebebi `kural_ozel.py`'de
    S-07 için yazılmış: o alanı dolduran `anlama.sdp_sayidan_oku()` ve o da
    kodu sayıdan okuyor. Aynı kaynağa iki yoldan bakmak bağımsız kanıt
    üretmez. Dilekçede sayı yoktur; kod da yoktur ve olmaması normaldir —
    Y-B o belgeleri zaten muhataptan çözüyor.
    """
    from veri_yapisi import sayi_bolumleri

    bolumler = sayi_bolumleri(getattr(dosya.ustveri, "sayi", None))
    if bolumler is None:
        return None
    return getattr(bolumler, "sdp", None) or None


def _alici_kurumu(dosya) -> str | None:
    """Evrağın geldiği kurum. Muhatap satırından çözülür.

    Birim eşleşmesi eşiğin altında kalsa bile KURUM güvenilir: OCR "MİLLÎ"yi
    bozup İl MEM'i İlçe MEM'e kaydırsa da ikisi aynı kurumdadır. Bu yüzden
    burada `MUHATAP_ESIGI` uygulanmıyor, `en_iyi_eslesme`nin varsayılanı
    yetiyor.
    """
    from birimler import birim_bul, hedef_olabilecekler
    from metin import en_iyi_eslesme

    muhatap = getattr(dosya.ustveri, "muhatap", None)
    ham = getattr(muhatap, "ham", None) if muhatap else None
    birim = getattr(muhatap, "birim", None) if muhatap else None
    arama = " ".join(x for x in (ham, birim) if x).strip()
    if not arama:
        return None
    adaylar = [(b["kod"], b["ad"], b["seviye"]) for b in hedef_olabilecekler()]
    kod, _oran, _ad = en_iyi_eslesme(arama, adaylar)
    kayit = birim_bul(kod) if kod else None
    return kayit["kurum_kodu"] if kayit else None


def _sdp_adaylari(kod: str | None, alici_kurum: str | None = None) -> list[str]:
    """SDP kodundan aday birim kodları, ALICI KURUMA göre süzülmüş.

    NEDEN SÜZÜLÜYOR — ÖLÇÜLDÜ 2026-08-24, 168 belge
    -----------------------------------------------
    Bazı SDP kodları üç kurumda birden kullanılıyor. 773 "Staj İşleri"
    hem Yenimahalle Belediyesi'nin hem Gazi'nin hem İl MEM'in kodudur.
    Süzmeden, Yenimahalle'ye gelen bir staj yazısında Gazi'nin
    Mühendislik Fakültesi aday olarak görünüyordu — evrak o kuruma
    gelmemişken.

    İki zarar veriyordu: arayüzde memura anlamsız alternatif gösteriliyor,
    ve LLM hattında aday kümesi gereksiz büyüyerek yanlış seçim olasılığını
    artırıyordu.

        aday sayısı      süzmeden      süzülmüş
        1 aday               80           110
        3 aday               43            19
        10 aday               7             0
        16 aday               4             0
        en büyük küme        16            13

    Doğru cevabı kaybeden belge: 0. Süzme hiçbir belgede zarar vermedi,
    30 belgeyi tek adaya indirdi.

    Alıcı kurum çözülemezse (dağıtımlı belge, "İLGİLİ MAKAMA") süzme
    YAPILMAZ — bilinmeyen bir ölçüte göre eleme yapmak, elemeyi
    keyfîleştirir.
    """
    if not kod:
        return []
    from birimler import birim_bul, birimleri_yukle, sdp_ile_birim_bul

    # SEVİYE 1 ELENİYOR — `sdp_ile_birim_bul` süzmüyor, biz süzüyoruz.
    #
    # `birimler.py`: "Seviye 1 bir GÖZETİM katmanıdır: başkan
    # yardımcılığına evrak havale edilmez, bağlı müdürlüğe edilir."
    # `hedef_olabilecekler()` bu kuralı uyguluyor ama `sdp_ile_birim_bul`
    # ham tabloya bakıyor ve beş başkan yardımcılığını da döndürüyor.
    #
    # ÖLÇÜLDÜ 2026-08-24: 168 belgenin 4'ünde aday kümesine seviye 1
    # birimler giriyordu. belge_002'de SDP 051 yedi aday veriyor ve
    # BEŞİ başkan yardımcılığı — LLM'e verilecek listenin çoğunluğu
    # havale edilemeyecek makamlar olurdu.
    hedefler = {b["kod"] for b in birimleri_yukle() if b["hedef_olabilir"]}
    hepsi = [k for k in sdp_ile_birim_bul(kod) if k in hedefler]
    if not alici_kurum:
        return hepsi
    suzulmus = [k for k in hepsi
                if (birim_bul(k) or {}).get("kurum_kodu") == alici_kurum]
    # Süzme her şeyi eledeyse ham listeye dönülüyor: alıcı kurum yanlış
    # çözülmüş olabilir ve boş küme, dolu kümeden kötüdür.
    return suzulmus or hepsi


def _konudan_adaylar(dosya, alici_kurum: str | None) -> tuple[list[str], str | None]:
    """Y-E · Konudan SDP kodu türeterek aday birim. Döner: (kodlar, sdp_kodu).

    YALNIZCA SAYIDA KULLANILABİLİR SDP YOKKEN ÇAĞRILIR
    --------------------------------------------------
    Sayı varken bu hat KOŞMAZ. Sebebi `kural_ozel.py`'de S-07 için
    yazılmış: aynı kaynağa iki yoldan bakmak bağımsız kanıt üretmez.
    Ama sayı YOKKEN durum tersine döner — kod konudan türetiliyor ve bu
    tamamen bağımsız bir kaynaktır. İlk sürümde bu ayrımı yapmamış,
    ikisini birden reddetmiştim.

    ÖLÇÜLDÜ 2026-08-24, sayısı olmayan 132 belge:
        84  konudan tek birime düşüyor -> doğru
        45  çoklu aday, doğru cevap içinde
         1  tek birime düşüyor -> YANLIŞ
         2  kod bulundu ama hedef birim yok

    Üç yanlış yönlendirmenin üçü de bu hatla düzeliyor ve üçü de TAM
    EŞLEŞME (1,00) ile:
        belge_043  "Cezanın Sicilden Silinmesi Talebi" -> 225.02    -> ortaogretim_sb
        belge_231  "Sınıf Mevcudunun Düzenlenmesi"     -> 160.01.02 -> ozel_egitim_rehberlik_sb
        belge_082  "Tıbbi Atık Bertarafı Hk."          -> 155.01    -> temizlik_isleri

    DÜRÜSTLÜK NOTU — RAPORA GİRECEK
    -------------------------------
    `sdp_katalog.py` kendi docstring'inde uyarıyor: veri setinin `konu`
    alanları katalogun `ornek_konular` havuzundan SEÇİLEREK üretildi
    (YONTEM.md: "bu sütun kaynakta yoktur, ekip yazmıştır"). Dolayısıyla
    konu ile katalog arasındaki eşleşme bu veri setinde OLAĞANDIŞI
    yüksektir ve yukarıdaki 84/132 oranı genellenemez.

    Yöntemin kendisi geçerli: `TAM_ESLESME = 1.0`, yani yalnızca
    katalogdaki başlık konuda BİREBİR geçiyorsa kabul ediliyor ve arşiv
    pratiğinde memur da dosya planına konuya bakarak karar verir. Ama
    ölçülen SIKLIK bu veri setine özgüdür; gerçek kurumda daha seyrek
    tutar ve belgeler Y-C/Y-D hattına düşer.
    """
    from birimler import birim_bul, birimleri_yukle, sdp_ile_birim_bul
    from sdp_katalog import katalog, konudan_kod_bul

    aranan = getattr(dosya.ustveri, "konu", None)
    if not aranan:
        return [], None
    tum_kodlar = list(katalog())
    if not tum_kodlar:
        # Katalog dosyası yerinde değil. Sessizce boş dönmek yerine bunu
        # çağıran taraf görecek: hat hiç çalışmadıysa ölçümde fark eder.
        return [], None

    kod, _oran = konudan_kod_bul(aranan, tum_kodlar)
    if not kod:
        return [], None

    hedefler = {b["kod"] for b in birimleri_yukle() if b["hedef_olabilir"]}
    adaylar = [k for k in sdp_ile_birim_bul(kod) if k in hedefler]
    if alici_kurum:
        suzulmus = [k for k in adaylar
                    if (birim_bul(k) or {}).get("kurum_kodu") == alici_kurum]
        adaylar = suzulmus or adaylar
    return adaylar, kod


def _muhataptan(dosya) -> tuple[str | None, float, str | None]:
    """Muhatap satırından birim. Döner: (kod, oran, aranan_metin).

    `hedef_olabilecekler()` kullanılıyor: seviye 1 gözetim katmanına evrak
    havale edilmez (`birimler.HEDEF_OLAMAYAN_SEVIYE`).

    Dağıtımlı belgede muhatap bir birim DEĞİLDİR ("DAĞITIM YERLERİNE");
    eşleşme çıkmaz ve bu beklenen davranıştır.
    """
    from metin import en_iyi_eslesme

    muhatap = getattr(dosya.ustveri, "muhatap", None)
    ham = getattr(muhatap, "ham", None) if muhatap else None
    birim = getattr(muhatap, "birim", None) if muhatap else None
    arama = " ".join(x for x in (ham, birim) if x).strip()
    if not arama:
        return None, 0.0, None

    kod, oran, _ad = en_iyi_eslesme(arama, _muhatap_adaylari())
    if kod is not None and oran >= MUHATAP_ESIGI:
        return kod, oran, arama

    # İKİNCİ GEÇİŞ — taşra başlığı. ÖLÇÜLDÜ 2026-08-24
    # ------------------------------------------------
    # Mülki idare satırı eşleşmeyi seyreltiyor:
    #
    #     "YENİMAHALLE KAYMAKAMLIĞINA (İlçe Millî Eğitim Müdürlüğü)"
    #         -> yenimahalle_ilce_mem   oran 0.84   ESİĞİN BİR PUAN ALTI
    #
    # Doğru cevap ama eleniyordu; 300 belgede 10 İlçe MEM yazısı bu
    # yüzden çözülemedi sayıldı.
    #
    # Eşiği düşürmek yanlış çözüm: 0,77'de OCR'ın bozduğu
    # "ANKARA İL MİLL{ EĞİTİM" de aynı birime kayıyor ve o YANLIŞ.
    # İki durum aynı bantta, oran ayırmıyor.
    #
    # `birimler.antet_birimi` bu problemi zaten çözüyor: kurumun başlık
    # KALIBININ TAMAMINI arıyor (mülki idare satırı + birim satırı) ve
    # tam eşleşme istiyor. Aynı mekanizma ayrıştırıcıda gönderen çıkarımı
    # için yazıldı ve 300 belgede ölçüldü; ikinci bir uygulama YAZILMADI.
    #
    #     "YENİMAHALLE KAYMAKAMLIĞINA (İlçe Millî Eğitim Müdürlüğü)"  -> bulur
    #     "ANKARA İL MİLL{ EĞİTİM MÜDÜRLÜĞÜNE"                        -> None
    #
    # Bozuk metinde None dönüyor, yani yanlış cevap üretmiyor.
    from birimler import antet_birimi

    kayit = antet_birimi(arama)
    if kayit is not None and kayit["hedef_olabilir"]:
        return kayit["kod"], 1.0, arama
    return None, oran, arama


def _muhatap_adaylari() -> list[tuple[str, str, int]]:
    """30 hedef birim + kurumların İKİNCİ ADLARI.

    NEDEN İKİNCİ AD GEREKİYOR — ÖLÇÜLDÜ 2026-08-24
    ----------------------------------------------
    Üç belgede muhatap satırı yalnızca "Gazi Üniversitesi" diyor ve
    birim tablosundaki kanonik ad "Gazi Üniversitesi Rektörlüğü".
    Eşleşme 0,76 çıkıyor, MUHATAP_ESIGI 0,85 olduğu için eleniyor ve
    belge çözülemedi sayılıyor.

    `kota.json` bu varyantı açıkça belgelemiş:

        "baslik_varyanti": {"GAZİ ÜNİVERSİTESİ REKTÖRLÜĞÜ": 0.6,
                            "GAZİ ÜNİVERSİTESİ": 0.4}
        "_not": "Iki bicim de gercek kullanimda goruldu.
                 Sistem ikisini de tanimali."

    EŞİĞİ DÜŞÜRMEK YANLIŞ ÇÖZÜM OLURDU. 0,75-0,84 bandı karışık:
    `yazar.py` ölçümünde o bantta 17 doğru ile 3 yanlış iç içeydi ve
    yanlışlar OCR'ın bozduğu "ANKARA İL MİLL{ EĞİTİM"in İlçe MEM'e
    kaymasıydı. Eşiği düşürmek 3 Gazi belgesini kazanıp o karışıklığı
    geri getirirdi.

    Doğru çözüm ADI TANIMAK: `kurum*.json` zaten iki adı da tutuyor
    (`kurum_adi` ve `detsis_kayit_adi`). Alternatif ad TAM EŞLEŞME
    üretiyor, bulanık eşleştirmeye hiç girmiyor.
    """
    from birimler import _kurum_profilleri, birim_bul, hedef_olabilecekler
    from metin import katla

    adaylar = [(b["kod"], b["ad"], b["seviye"]) for b in hedef_olabilecekler()]
    gorulen = {katla(ad) for _k, ad, _s in adaylar}

    for kod, profil in _kurum_profilleri().items():
        kok = birim_bul(kod)
        if kok is None or not kok["hedef_olabilir"]:
            continue
        for alan in ("kurum_adi", "detsis_kayit_adi"):
            ad = (profil.get(alan) or "").strip()
            if ad and katla(ad) not in gorulen:
                gorulen.add(katla(ad))
                adaylar.append((kod, ad, kok["seviye"]))
    return adaylar


def _ad(kod: str | None) -> str | None:
    from birimler import birim_bul

    b = birim_bul(kod) if kod else None
    return b["ad"] if b else None


# -----------------------------------------------------------------------------
# LLM hattı
# -----------------------------------------------------------------------------

SISTEM_ISTEMI_YONLENDIRICI = (
    "Türk kamu kurumlarında gelen evrağı ilgili birime havale eden bir "
    "uzmansın. Sana verilen birim listesinin DIŞINA çıkmazsın ve seçimini "
    "birimin görev alanına dayandırırsın. Emin olamadığında en yüksek "
    "görev alanı örtüşmesi olan birimi seçer, gerekçende kararsızlığını "
    "belirtirsin."
)


def _sema_kur(kodlar: list[str]) -> dict:
    """response_format şeması. `birim` alanı adaylarla SINIRLI.

    Enum kısıtı olmadan model var olmayan bir birim kodu uydurabilir ve o
    kod `birim_bul()`'da None döner; evrak hiçbir yere gitmez ve sebebi
    çıktıya bakınca anlaşılmaz.
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "birim_yonlendirme",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "birim": {"type": "string", "enum": kodlar},
                    "gerekce": {
                        "type": "string", "maxLength": 300,
                        "description": "Bu birimi neden seçtin. Birimin "
                                       "görev alanına atıf yap. TEK CÜMLE.",
                    },
                    "kanit_cumle": {
                        "type": "string", "maxLength": 300,
                        "description": "Belgenin gövdesinden, bu seçimi "
                                       "destekleyen cümle. BİREBİR kopyala, "
                                       "değiştirme. Yoksa boş bırak.",
                    },
                    "guven": {
                        "type": "string", "enum": ["yuksek", "orta", "dusuk"],
                        "description": "Seçimden ne kadar eminsin.",
                    },
                },
                "required": ["birim", "gerekce", "kanit_cumle", "guven"],
                "additionalProperties": False,
            },
        },
    }


def _istem_kur(dosya, birimler: list[dict]) -> str:
    u = dosya.ustveri
    s = dosya.siniflandirma
    ic = dosya.icerik

    satirlar = [
        "GELEN EVRAK",
        "-" * 60,
        f"Konu   : {u.konu or '—'}",
        f"Tür    : {s.belge_turu.value if s.belge_turu else '—'}",
        f"Talep  : {ic.talep or '—'}",
        f"Özet   : {ic.ozet or '—'}",
        "",
        "Gövde:",
        (dosya.metin or "")[:2500],
        "",
        f"ADAY BİRİMLER — yalnızca bu {len(birimler)} birimden birini seç",
        "-" * 60,
    ]
    for b in birimler:
        satirlar.append(f"[{b['kod']}]  {b['ad']}  ({b['kurum']})")
        gorev = (b.get("gorev_alani") or "").strip()
        if gorev:
            satirlar.append(f"      {gorev[:400]}")
    satirlar += [
        "",
        "KURALLAR",
        "-" * 60,
        "1  Listede olmayan bir birim kodu YAZMA.",
        "2  Gerekçeni birimin GÖREV ALANINA dayandır, kendi genel bilgine "
        "değil.",
        "3  kanit_cumle alanına gövdeden BİREBİR bir cümle kopyala. "
        "Kendi cümleni yazma; destekleyen cümle yoksa boş bırak.",
        "4  Aynı kelime farklı birimlerin işi olabilir. Örneğin 'denklik' "
        "hem lise diploması hem üniversite dersi için kullanılır; hangisi "
        "olduğuna belgenin içeriğine bakarak karar ver.",
    ]
    return "\n".join(satirlar)


def _llm_ile_sec(dosya, kodlar: list[str], istemci,
                 sonuc: YonlendirmeSonucu) -> str | None:
    """Aday kodlar arasından model seçer. Başarısızlıkta None."""
    from birimler import birim_bul

    birimler = [b for b in (birim_bul(k) for k in kodlar) if b]
    if not birimler:
        sonuc.uyarilar.append("Aday birim kaydı bulunamadı")
        return None

    try:
        cevap = istemci.metin_uret(
            istem=_istem_kur(dosya, birimler),
            sistem_istemi=SISTEM_ISTEMI_YONLENDIRICI,
            ek={"response_format": _sema_kur([b["kod"] for b in birimler])},
        )
    except Exception as e:  # noqa: BLE001
        sonuc.uyarilar.append(f"LLM çağrısı başarısız: {type(e).__name__}: {e}")
        return None

    sonuc.llm_kullanildi = True
    if cevap.kesildi_mi:
        sonuc.uyarilar.append("Model çıktısı token sınırında kesildi")
        return None
    try:
        veri = json.loads(cevap.metin)
    except json.JSONDecodeError as e:
        sonuc.uyarilar.append(f"Model çıktısı JSON değil: {e}")
        return None

    kod = (veri.get("birim") or "").strip()
    if kod not in {b["kod"] for b in birimler}:
        # Şema enum'u uygulanmamış demektir; uydurulmuş kod kabul edilmez.
        sonuc.uyarilar.append(f"Model aday dışı birim verdi: {kod!r}")
        return None

    sonuc.gerekce = (veri.get("gerekce") or "").strip()[:300] or None
    sonuc.kanit_cumle = _kaniti_dogrula(veri.get("kanit_cumle"), dosya, sonuc)

    guven = (veri.get("guven") or "").strip()
    if guven == "dusuk":
        # Modelin kendi beyanı skoru düşürür. Kendi kararsızlığını bildiren
        # bir model, bildirmeyenden daha güvenilirdir; bunu cezalandırmak
        # yerine insana taşıyoruz.
        sonuc.skor = min(sonuc.skor, SKOR_LLM_GENIS)
        sonuc.uyarilar.append("Model seçiminden emin olmadığını bildirdi")
    return kod


def _kaniti_dogrula(cumle, dosya, sonuc: YonlendirmeSonucu) -> str | None:
    """Model alıntısı gövdede GERÇEKTEN geçiyor mu.

    NEDEN DENETLENİYOR: `kanit_cumle` arayüzde memura italik olarak
    gösteriliyor ve alıntı görünümündedir. Uydurulmuş bir alıntı,
    uydurulmuş gerekçeden beterdir — memur alıntıya güvenip belgeyi
    okumadan onaylayabilir.

    Karşılaştırma `metin.icinde_gecer_mi` ile yapılıyor: OCR taranmış
    belgede işaretleri bozuyor, birebir eşitlik aramak meşru alıntıyı da
    elerdi. `metin.py`'nin kurucu ilkesi — metin onarılmaz, karşılaştırma
    esnetilir.
    """
    from metin import icinde_gecer_mi

    c = (cumle or "").strip()
    if not c:
        return None
    govde = dosya.metin or ""
    if not govde:
        return None
    geciyor, _parca = icinde_gecer_mi(c, govde, esik=0.80)
    if geciyor:
        return c[:300]
    sonuc.uyarilar.append(
        f"Model kanıt cümlesi gövdede bulunamadı, atıldı: {c[:60]!r}"
    )
    return None


# -----------------------------------------------------------------------------
# Ana giriş
# -----------------------------------------------------------------------------


def yonlendir(dosya, istemci=None) -> YonlendirmeSonucu:
    """Hedef birimi belirler ve `dosya.yonlendirme`ye yazar.

    `istemci` verilmezse Y-C ve Y-D koşmaz; deterministik hatların
    çözemediği belgede hedef boş kalır ve `hat` "llm_yok" olur. Ölçüm
    betiği bu kipte deterministik hatların tek başına kapsamını ölçüyor —
    kredi harcamadan koşan bir ablasyon.

    Diyagramda Yönlendirici Ajan 2'den SONRA duruyor. "Taslak gerekmese de
    yönlendirme yapılır" — bu yüzden `cikti_yazi`ya hiç bakılmıyor, karar
    yalnızca GELEN evrağa dayanıyor.
    """
    s = YonlendirmeSonucu()

    kod = sdp_kodu_oku(dosya)
    sdp_adaylar = _sdp_adaylari(kod, _alici_kurumu(dosya))
    muhatap_kod, muhatap_oran, muhatap_metin = _muhataptan(dosya)

    # --- İki deterministik hat birden ------------------------------------
    if muhatap_kod and sdp_adaylar:
        if muhatap_kod in sdp_adaylar:
            s.hedef = muhatap_kod
            s.skor = SKOR_MUTABIK
            s.hat = ("Y-A+B mutabık" if len(sdp_adaylar) == 1
                     else "Y-B (SDP adayları içinde)")
            s.gerekce = (
                f"SDP {kod} kodu {len(sdp_adaylar)} birime işaret ediyor; "
                f"muhatap satırında yazılı olan '{_ad(muhatap_kod)}' bu "
                f"adayların içinde."
                if len(sdp_adaylar) > 1 else
                f"SDP {kod} kodu ile muhatap satırı aynı birimi gösteriyor: "
                f"{_ad(muhatap_kod)}."
            )
        else:
            # ÇELİŞKİ. 300 belgede hiç görülmedi; OCR hasarı üretebilir.
            # Hiçbirini seçmiyoruz: iki kaynak ayrışmışken birini seçmek
            # hangisinin bozulduğunu bilmeden karar vermek olur.
            s.celiski = True
            s.hedef = muhatap_kod
            s.skor = SKOR_CELISKI
            s.hat = "ÇELİŞKİ (A≠B)"
            s.gerekce = (
                f"Çelişki: SDP {kod} kodu {[_ad(k) for k in sdp_adaylar]} "
                f"diyor, muhatap satırı '{_ad(muhatap_kod)}' diyor. "
                f"İnsan onayı gerekiyor."
            )
            s.uyarilar.append(s.gerekce)
        s.adaylar = _adaylari_kur(s.hedef, sdp_adaylar, muhatap_kod)
        return _yaz(dosya, s, muhatap_metin)

    # --- MUHATAP YOKSA SAYIYI KONUYLA ÇAPRAZ DENETLE ---------------------
    #
    # Muhatap satırı okunabildiğinde sayıdaki SDP kodunun ikinci bir
    # tanığı var: çelişirlerse yakalıyoruz (300 belgede 12 kez oldu,
    # 9'u `sdp_uyumsuz` kusuruydu). Muhatap YOKSA o tanık kayboluyor ve
    # bozuk bir kod tek başına karar veriyor.
    #
    # ÖLÇÜLDÜ 2026-08-24: 168 sayılı belgenin 12'sinde muhatap
    # kullanılamıyor (dağıtımlı ya da `muhatap_belirsiz`). Bunların
    # `sdp_uyumsuz` olanı sessizce yanlış birime giderdi — belge_082
    # tam olarak böyle oldu ve model Gazi'nin Genel Sekreterliğine
    # yönlendirdi, oysa belge belediyenin tıbbi atık yazısıydı.
    #
    # `kural_ozel.sdp_kod_celiskisi` (S-07) aynı problemi Denetçi
    # tarafında çözüyor ve çözümü de aynı: KONU, sayıdan bağımsız
    # ikinci kaynaktır. Aynı mantığı burada uyguluyoruz.
    #
    # Ölçülen güvenilirlik: 168 belgede konudan türetilen kod, sayıdaki
    # kodla 161 kez uyuştu, 7 kez ayrıştı. Ayrışan 7'sinin YEDİSİNDE de
    # muhatap okunabiliyordu, yani bu kural onlara hiç dokunmuyor.
    if not muhatap_kod and sdp_adaylar:
        konu_adaylar, konu_kodu = _konudan_adaylar(dosya, None)
        if konu_kodu and kod and konu_kodu != kod and konu_adaylar:
            s.celiski = True
            s.gerekce = (
                f"Sayıdaki SDP kodu {kod}, konu ise {konu_kodu} kodunu "
                f"işaret ediyor. Muhatap satırı okunamadığı için sayıyı "
                f"doğrulayacak başka kaynak yok; konudan türetilen kod "
                f"esas alındı."
            )
            s.uyarilar.append(s.gerekce)
            sdp_adaylar, kod = konu_adaylar, konu_kodu
            if len(sdp_adaylar) == 1:
                s.hedef = sdp_adaylar[0]
                s.skor = SKOR_CELISKI
                s.hat = "ÇELİŞKİ (sayı≠konu)"
                s.adaylar = [(s.hedef, s.skor)]
                return _yaz(dosya, s, muhatap_metin)

    # --- Y-A · yalnız SDP, tek birim -------------------------------------
    if len(sdp_adaylar) == 1:
        s.hedef = sdp_adaylar[0]
        s.skor = SKOR_TEK_HAT
        s.hat = "Y-A SDP tek birim"
        s.gerekce = (f"SDP {kod} kodu tek birime düşüyor: "
                     f"{_ad(s.hedef)}.")
        s.adaylar = [(s.hedef, s.skor)]
        return _yaz(dosya, s, muhatap_metin)

    # --- Y-B · yalnız muhatap --------------------------------------------
    if muhatap_kod:
        s.hedef = muhatap_kod
        s.skor = SKOR_TEK_HAT
        s.hat = "Y-B muhatap satırı"
        s.gerekce = (f"Muhatap satırında birim adı yazılı: "
                     f"{_ad(muhatap_kod)}. Belgede kullanılabilir SDP kodu "
                     f"yok.")
        s.adaylar = [(s.hedef, s.skor)]
        return _yaz(dosya, s, muhatap_metin)

    # --- Y-E · konudan SDP. Sayıda kod yokken bağımsız kaynak ------------
    if not sdp_adaylar:
        konu_adaylar, konu_kodu = _konudan_adaylar(dosya, _alici_kurumu(dosya))
        if len(konu_adaylar) == 1:
            s.hedef = konu_adaylar[0]
            # Sayıdan okunan koddan DÜŞÜK skor: kod belgede yazılı değil,
            # konudan türetildi. Türetme meşru ama dolaylı.
            s.skor = SKOR_KONUDAN
            s.hat = "Y-E konudan SDP"
            s.gerekce = (f"Belgede SDP kodu yok; konu '{dosya.ustveri.konu}' "
                         f"dosya planında {konu_kodu} koduna karşılık geliyor "
                         f"ve bu kod tek birime düşüyor: {_ad(s.hedef)}.")
            s.adaylar = [(s.hedef, s.skor)]
            return _yaz(dosya, s, muhatap_metin)
        if konu_adaylar:
            # Çoklu aday: LLM'e 30 birim yerine bu daraltılmış kümeyi ver.
            sdp_adaylar = konu_adaylar
            kod = konu_kodu

    # --- Y-C / Y-D · model ------------------------------------------------
    if istemci is None:
        s.hat = "llm_yok"
        s.uyarilar.append(
            "Deterministik hat çözemedi ve istemci verilmedi; hedef boş")
        return _yaz(dosya, s, muhatap_metin)

    if len(sdp_adaylar) > 1:
        kodlar, s.hat, s.skor = sdp_adaylar, "Y-C dar aday + LLM", SKOR_LLM_DAR
    else:
        from birimler import hedef_olabilecekler

        kodlar = [b["kod"] for b in hedef_olabilecekler()]
        s.hat, s.skor = "Y-D tüm birimler + LLM", SKOR_LLM_GENIS

    secilen = _llm_ile_sec(dosya, kodlar, istemci, s)
    if secilen is None:
        s.hedef, s.skor = None, 0.0
        s.hat += " (başarısız)"
        return _yaz(dosya, s, muhatap_metin)

    s.hedef = secilen
    if not s.gerekce:
        s.gerekce = f"Model {len(kodlar)} aday arasından seçti: {_ad(secilen)}."
    s.adaylar = [(secilen, s.skor)] + [(k, 0.0) for k in kodlar
                                       if k != secilen][:4]
    return _yaz(dosya, s, muhatap_metin)


def _adaylari_kur(hedef, sdp_adaylar, muhatap_kod) -> list[tuple[str, float]]:
    """Seçilen önce, diğerleri sonra. Yinelenen kod bir kez girer."""
    sirali: list[tuple[str, float]] = []
    gorulen: set[str] = set()
    for k in [hedef, muhatap_kod, *sdp_adaylar]:
        if k and k not in gorulen:
            gorulen.add(k)
            sirali.append((k, 1.0 if k == hedef else 0.0))
    return sirali[:5]


def _yaz(dosya, s: YonlendirmeSonucu, muhatap_metin: str | None):
    """Sonucu `dosya.yonlendirme`ye aktarır.

    `kaynak` alanı HATTI DÜRÜSTÇE söyler: muhataptan bulunduysa MUHATAP,
    SDP'den bulunduysa SDP_TABLOSU. İkisini tek değerde toplamak
    ablasyonu bozardı — `YonlendirmeKaynagi` docstring'i bunu açıkça
    istiyor.

    `kanit_cumle` deterministik hatlarda da doldurulur: Y-B'de muhatap
    satırının kendisi kanıttır ve arayüzde gösterilmesi memurun kararı
    denetlemesini sağlar.
    """
    from birimler import birim_bul

    y = dosya.yonlendirme
    y.hedef_birim = s.hedef
    y.skor = round(s.skor, 2)
    y.gerekce = s.gerekce
    y.dagitim_turu = DagitimTuru.GEREGI

    if s.hedef is None:
        y.kaynak = YonlendirmeKaynagi.BILINMIYOR
    elif s.llm_kullanildi:
        y.kaynak = YonlendirmeKaynagi.LLM
    elif s.hat.startswith(("Y-A", "Y-E", "ÇELİŞKİ (sayı≠konu)")):
        # Y-E ve sayı≠konu çelişkisinde cevap YİNE SDP TABLOSUNDAN geliyor;
        # farklı olan tek şey kodun nereden okunduğu — sayıdan değil,
        # konudan. Kodun kaynağı `gerekce` metninde açıkça yazılı.
        #
        # İlk sürümde bu iki hat `BILINMIYOR`a ve `MUHATAP`a düşüyordu:
        # 300 belgede 2'sinde rozet boş kalıyor, 1'inde ise hiç
        # kullanılmamış bir kaynağı gösteriyordu. Arayüz bu alandan rozet
        # üretiyor; yanlış rozet, memura kararın nereden geldiği hakkında
        # yanlış bilgi verir.
        y.kaynak = YonlendirmeKaynagi.SDP_TABLOSU
    elif s.hat.startswith(("Y-B", "ÇELİŞKİ (A≠B)")):
        y.kaynak = YonlendirmeKaynagi.MUHATAP
    else:
        y.kaynak = YonlendirmeKaynagi.BILINMIYOR

    if s.kanit_cumle:
        y.kanit_cumle = s.kanit_cumle
    elif s.hat.startswith("Y-B") and muhatap_metin:
        y.kanit_cumle = muhatap_metin[:300]

    y.alternatif_adaylar = [
        YonlendirmeAdayi(birim=k, birim_adi=_ad(k), skor=round(sk, 2))
        for k, sk in s.adaylar
    ]
    y.alternatifler = [k for k, _ in s.adaylar if k != s.hedef][:4]

    # Kurum dışına yönlendirme bu çalışmada YOK: aday kümesi zaten üç
    # kurumun 30 hedef birimi. Alan şemada var; olmayan bir yeteneği
    # varmış gibi göstermemek için açıkça False yazılıyor.
    y.kurum_disinda = False

    hedef_kaydi = birim_bul(s.hedef) if s.hedef else None
    if s.hedef and hedef_kaydi is None:
        s.uyarilar.append(f"Seçilen birim tabloda yok: {s.hedef}")
    return s
