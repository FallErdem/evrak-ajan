#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_veri_yapisi.py — src/veri_yapisi.py için kapsamlı testler

İki şekilde çalışır:
    python testler/test_veri_yapisi.py     (bağımlılık gerekmez)
    pytest testler/test_veri_yapisi.py     (pytest kuruluysa)

veri_yapisi.py'nin içindeki _kendi_testi() hızlı bir sağlık kontrolüdür;
bu dosya ise kenar durumlarını, uç değerleri ve gerileme senaryolarını
kapsar. Parça 2'de yapı dondurulacağı için bu testler sözleşmenin kendisi
hâline gelir: bir alan adı veya davranış değişirse burası kırmızıya döner.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from veri_yapisi import (  # noqa: E402
    ALAN_YOLLARI, AJANLAR, BEYAN_YONTEMLERI, ESIK_INSAN_ONAYI,
    ESIK_OTOMATIK_ONAY, KATEGORILER, KISISEL_VERI_TIPLERI, SURUM,
    YASAKLI_IVEDILIK, YONTEM_ONCELIGI,
    AltBilgi, BaslikBlogu, CiktiYazi, DagitimSatiri, DagitimTuru, Dosya, Ek,
    EksikAlan, GelenKayit, GelenTur, GizlilikDerecesi, GirdiTipi,
    HiyerarsiYonu, Icerik, Ilgi, Imza, Ivedilik, IzKaydi, Kanit,
    KanitYontemi, Karar, KaynakBilgisi, Konum, LinterBulgusu, LinterRaporu,
    MevzuatOnerisi, MuhatapTuru, Onem, SdpKodu, Siniflandirma, Taraf,
    Teskilat, UretilecekTur, Ustveri, Varlik, VarlikTipi, Yonlendirme,
    beyan_mi, bilinen_ajan_mi, daha_guvenilir, en_zayif_halka,
    gizlilik_seviyesi, kapsama_girer_mi, kisisel_veri_mi, sayi_bolumleri,
    yontem_onceligi, zayif_alanlar,
)

TUM_MODELLER = [
    AltBilgi, BaslikBlogu, CiktiYazi, DagitimSatiri, Dosya, Ek, EksikAlan,
    GelenKayit, Icerik, Ilgi, Imza, IzKaydi, Kanit, Karar, KaynakBilgisi,
    Konum, LinterBulgusu, LinterRaporu, MevzuatOnerisi, SdpKodu,
    Siniflandirma, Taraf, Ustveri, Varlik, Yonlendirme,
]


def _reddediyor_mu(fn) -> bool:
    """fn çağrısı hata veriyor mu."""
    try:
        fn()
        return False
    except Exception:
        return True


# =============================================================================
# 1. SÖZLÜK
# =============================================================================


def test_her_belge_turu_bir_kategoride():
    kapsanan = set().union(*KATEGORILER.values())
    eksik = set(GelenTur) - kapsanan - {GelenTur.BILINMIYOR}
    assert not eksik, f"kategorisiz tür: {eksik}"


def test_kategoriler_ortusmuyor():
    kurum = KATEGORILER["kurum_yazisi"]
    kisi = KATEGORILER["kisi_belgesi"]
    assert not (kurum & kisi), "bir tür iki kategoride birden"


def test_sartname_642_turleri_uretilebilir_listesinde():
    for t in ("ust_yazi", "cevap_yazisi", "bilgilendirme_yazisi"):
        assert t in set(UretilecekTur), f"şartname 6.4.2'nin türü eksik: {t}"


def test_bilinmiyor_secenegi_var():
    # Emin olmadığında tahmin eden sistem sessizce yanlış karar üretir.
    assert GelenTur.BILINMIYOR in set(GelenTur)


def test_kapsama_girer_mi():
    assert kapsama_girer_mi(GelenTur.TEKIT_YAZISI, "kurum_yazisi")
    assert not kapsama_girer_mi(GelenTur.VATANDAS_DILEKCESI, "kurum_yazisi")
    assert kapsama_girer_mi(GelenTur.VATANDAS_DILEKCESI, "kisi_belgesi")
    # doğrudan tür adı da kapsam olarak kullanılabilir (rules.yaml böyle yapıyor)
    assert kapsama_girer_mi(GelenTur.TEKIT_YAZISI, "tekit_yazisi")
    # metin girdi de kabul edilir
    assert kapsama_girer_mi("tekit_yazisi", "kurum_yazisi")
    # kenar durumlar çökmez
    assert not kapsama_girer_mi(None, "kurum_yazisi")
    assert not kapsama_girer_mi(GelenTur.UST_YAZI, "olmayan_kapsam")


def test_gizlilik_sirasi_artan():
    assert (gizlilik_seviyesi(None)
            < gizlilik_seviyesi(GizlilikDerecesi.HIZMETE_OZEL)
            < gizlilik_seviyesi(GizlilikDerecesi.GIZLI)
            < gizlilik_seviyesi(GizlilikDerecesi.COK_GIZLI))


def test_kaldirilan_ozel_derecesi_yok():
    # 2022'de yürürlükten kalktı (G-02)
    assert "Özel" not in {str(g) for g in GizlilikDerecesi}


def test_taninmayan_gizlilik_derecesi_hata_veriyor():
    # GERİLEME TESTİ. Sessizce 0 dönerse EK-05 denetimi gürültülü girdide
    # sessizce geçer; Çok Gizli bir ek fark edilmeden ilerler.
    assert gizlilik_seviyesi(None) == 0
    assert gizlilik_seviyesi("") == 0
    for kotu in ("Cok Gizli", "gizli", "Özel", "ÇOK GİZLİ", "uyduruk"):
        assert _reddediyor_mu(lambda k=kotu: gizlilik_seviyesi(k)), \
            f"{kotu!r} sessizce kabul edildi"


def test_yasakli_ivedilik_izinli_kumede_degil():
    izinli = {str(i).upper() for i in Ivedilik}
    assert not ({i.upper() for i in YASAKLI_IVEDILIK} & izinli)


def test_her_yonteme_oncelik_atanmis():
    # Bu test bir hatayı yakaladı: OCR ve VARSAYILAN hiçbir kümede değildi,
    # kümesiz kalan yöntem "kesin" sayılıyordu.
    assert set(KanitYontemi) == set(YONTEM_ONCELIGI)


def test_oncelik_siralamasi_mantikli():
    assert yontem_onceligi(KanitYontemi.INSAN) == max(YONTEM_ONCELIGI.values())
    assert yontem_onceligi(KanitYontemi.VARSAYILAN) == min(YONTEM_ONCELIGI.values())
    assert yontem_onceligi(KanitYontemi.REGEX) > yontem_onceligi(KanitYontemi.LLM)
    assert yontem_onceligi(KanitYontemi.OCR) > yontem_onceligi(KanitYontemi.LLM)
    assert yontem_onceligi("uyduruk_yontem") == 0


def test_kisisel_veri_tipleri():
    assert kisisel_veri_mi(VarlikTipi.TCKN)
    assert kisisel_veri_mi("tckn")
    assert not kisisel_veri_mi(VarlikTipi.KURUM_ADI)
    for t in (VarlikTipi.KISI_ADI, VarlikTipi.IBAN, VarlikTipi.TELEFON,
              VarlikTipi.EPOSTA, VarlikTipi.ADRES):
        assert t in KISISEL_VERI_TIPLERI


def test_beyan_yontemi_yalnizca_llm():
    assert beyan_mi(KanitYontemi.LLM)
    assert not beyan_mi(KanitYontemi.REGEX)
    assert BEYAN_YONTEMLERI == frozenset({KanitYontemi.LLM})


def test_esikler_tutarli():
    assert 0.0 < ESIK_INSAN_ONAYI < ESIK_OTOMATIK_ONAY <= 1.0


def test_ajan_listesi():
    assert bilinen_ajan_mi("a3_siniflandirma")
    assert not bilinen_ajan_mi("olmayan_ajan")
    assert len(AJANLAR) == len(set(AJANLAR)), "ajan kimliği tekrar ediyor"


# =============================================================================
# 2. KANIT VE GÜVEN
# =============================================================================


def test_gecerli_guven_korunuyor():
    for v in (0.0, 0.5, 1.0, 1e-300, 0.9999999999):
        k = Kanit(yontem=KanitYontemi.LLM, ureten="t", guven=v)
        assert k.guven_gecerliydi
        assert k.guven == v


def test_aralik_disi_guven_sifira_cekiliyor():
    # Risk testinde gerçekten gelen değerler: 703.487, 90.0, 1.75
    # Bunları en yakın sınıra yuvarlamak, sözleşme dışı bir cevabı azami
    # güven hâline getirip otomatik onaydan geçirirdi.
    for v in (703.487, 90.0, 1.75, -0.2, 1.0000000001,
              float("inf"), float("-inf"), float("nan")):
        k = Kanit(yontem=KanitYontemi.LLM, ureten="t", guven=v)
        assert k.guven == 0.0, f"{v} sıfıra çekilmedi"
        assert not k.guven_gecerliydi
        assert k.guven_ham is not None, f"{v} ham hâli kaybedildi"


def test_sayi_olmayan_guven_reddediliyor():
    for v in (True, False, "yüksek", "0.5", None, [], {}):
        k = Kanit(yontem=KanitYontemi.LLM, ureten="t", guven=v)
        assert k.guven == 0.0
        assert not k.guven_gecerliydi


def test_guven_verilmezse_sifir_ve_otomatik_gecmez():
    k = Kanit(yontem=KanitYontemi.LLM, ureten="t")
    assert k.guven == 0.0
    assert not k.otomatik_gecebilir_mi


def test_otomatik_gecebilme_esigi():
    assert Kanit(yontem=KanitYontemi.REGEX, ureten="t",
                 guven=ESIK_OTOMATIK_ONAY).otomatik_gecebilir_mi
    assert not Kanit(yontem=KanitYontemi.REGEX, ureten="t",
                     guven=ESIK_OTOMATIK_ONAY - 0.01).otomatik_gecebilir_mi
    # geçersiz güven, yüksek görünse bile geçemez
    assert not Kanit(yontem=KanitYontemi.LLM, ureten="t",
                     guven=703.487).otomatik_gecebilir_mi


def test_kanit_degistirilemez():
    k = Kanit(yontem=KanitYontemi.REGEX, ureten="t", guven=0.9)
    assert _reddediyor_mu(lambda: setattr(k, "guven", 1.0))
    assert _reddediyor_mu(lambda: setattr(k, "ureten", "baskasi"))


def test_alinti_uzunluk_siniri():
    assert len(Kanit(yontem=KanitYontemi.LLM, ureten="t", alinti="a" * 300).alinti) == 300
    assert _reddediyor_mu(
        lambda: Kanit(yontem=KanitYontemi.LLM, ureten="t", alinti="a" * 301))


def test_kanit_zamani_tz_farkindali():
    assert Kanit(yontem=KanitYontemi.LLM, ureten="t").zaman.tzinfo is not None


def test_konum_dogrulamasi():
    assert Konum(sayfa=1, baslangic=5, bitis=5).bitis == 5   # eşit aralık serbest
    assert _reddediyor_mu(lambda: Konum(sayfa=1, baslangic=9, bitis=5))
    assert _reddediyor_mu(lambda: Konum(sayfa=0))
    assert _reddediyor_mu(lambda: Konum(sayfa=1, baslangic=-1))
    assert _reddediyor_mu(lambda: setattr(Konum(sayfa=1), "sayfa", 2))


def test_yontem_guvenden_once_gelir():
    regex = Kanit(yontem=KanitYontemi.REGEX, ureten="a2", guven=0.70)
    llm = Kanit(yontem=KanitYontemi.LLM, ureten="a3", guven=0.99)
    insan = Kanit(yontem=KanitYontemi.INSAN, ureten="kullanici", guven=0.30)
    varsayilan = Kanit(yontem=KanitYontemi.VARSAYILAN, ureten="sistem", guven=0.99)

    assert not daha_guvenilir(llm, regex), "model regex'i ezdi"
    assert daha_guvenilir(regex, llm)
    assert daha_guvenilir(insan, regex), "insan düzeltmesi geçersiz kaldı"
    assert not daha_guvenilir(regex, insan)
    # GERİLEME: varsayılan kümesiz kaldığında LLM'i ezebiliyordu
    assert not daha_guvenilir(varsayilan, llm)


def test_esit_oncelikte_guven_belirleyici():
    a = Kanit(yontem=KanitYontemi.LLM, ureten="t", guven=0.8)
    b = Kanit(yontem=KanitYontemi.LLM, ureten="t", guven=0.6)
    assert daha_guvenilir(a, b)
    assert not daha_guvenilir(b, a)
    assert not daha_guvenilir(a, a), "eşit güven yer değiştirmeye yol açmamalı"


def test_gecersiz_guvenli_kanit_gecerliyi_ezemez():
    gecersiz = Kanit(yontem=KanitYontemi.LLM, ureten="t", guven=703.0)
    gecerli = Kanit(yontem=KanitYontemi.LLM, ureten="t", guven=0.0)
    assert not daha_guvenilir(gecersiz, gecerli)


def test_en_zayif_halka_ortalama_degil():
    # Dokuzu 0.95, biri 0.10 olan bir belgenin ortalaması 0.86 çıkar ve
    # otomatik onaydan geçer. En düşük alınırsa insana gider.
    kanitlar = [Kanit(yontem=KanitYontemi.LLM, ureten="t", guven=0.95)
                for _ in range(9)]
    kanitlar.append(Kanit(yontem=KanitYontemi.LLM, ureten="t", guven=0.10))
    assert en_zayif_halka(kanitlar) == 0.10
    assert en_zayif_halka({}) == 0.0
    assert en_zayif_halka([]) == 0.0


def test_zayif_alanlar_siralaniyor():
    harita = {
        "ustveri.sayi": Kanit(yontem=KanitYontemi.REGEX, ureten="t", guven=0.95),
        "ustveri.konu": Kanit(yontem=KanitYontemi.LLM, ureten="t", guven=0.40),
        "icerik.ozet": Kanit(yontem=KanitYontemi.LLM, ureten="t", guven=0.20),
    }
    sonuc = zayif_alanlar(harita)
    assert [y for y, _ in sonuc] == ["icerik.ozet", "ustveri.konu"]


def test_gecersiz_guvenli_alan_zayif_sayilir():
    harita = {"ustveri.konu": Kanit(yontem=KanitYontemi.LLM, ureten="t", guven=703.0)}
    assert zayif_alanlar(harita)


# =============================================================================
# 3. BELGE ALANLARI
# =============================================================================


def test_sayi_ayristirma():
    b = sayi_bolumleri("E-71368504-010.06.01-4471829")
    assert (b.surec, b.detsis, b.sdp, b.kayit_no) == \
        ("E", "71368504", "010.06.01", "4471829")
    assert sayi_bolumleri("  E-71368504-010.06.01-4471829  ").sdp == "010.06.01"
    assert sayi_bolumleri("Z-123456-010-1").sdp == "010"
    assert sayi_bolumleri("O-1234567890-010.06.01.02-99").sdp == "010.06.01.02"


def test_sayi_ayristirma_reddedilenler():
    # 2020 öncesi biçim: süreç harfi kayıt numarasının önünde
    assert sayi_bolumleri("96321565-774.09.03-E.79291") is None
    assert sayi_bolumleri("E/68103562/823.02/138739") is None
    assert sayi_bolumleri("e-71368504-010.06.01-4471829") is None  # küçük harf
    assert sayi_bolumleri("E-12345-010-1") is None                 # DETSİS kısa
    assert sayi_bolumleri("E-71368504-010.06.01-4471829-EK") is None
    assert sayi_bolumleri(None) is None
    assert sayi_bolumleri("") is None


def test_ek_gizliligi_ust_yaziyi_asamaz():
    # EK-05. Ekler düz metin listesi olsaydı bu kural denetlenemezdi.
    u = Ustveri(gizlilik_derecesi=GizlilikDerecesi.HIZMETE_OZEL,
                ekler=[Ek(aciklama="Rapor",
                          gizlilik_derecesi=GizlilikDerecesi.GIZLI)])
    assert u.azami_ek_gizliligi > gizlilik_seviyesi(u.gizlilik_derecesi)
    assert Ustveri().azami_ek_gizliligi == 0
    karisik = Ustveri(ekler=[Ek(aciklama="a"),
                             Ek(aciklama="b",
                                gizlilik_derecesi=GizlilikDerecesi.GIZLI)])
    assert karisik.azami_ek_gizliligi == 2


def test_dagitimli_tespiti():
    assert Ustveri(muhatap=Taraf(tur=MuhatapTuru.DAGITIM_YERLERI)).dagitimli_mi
    assert Ustveri(dagitim=[DagitimSatiri(hedef="81 İl Valiliğine")]).dagitimli_mi
    assert not Ustveri().dagitimli_mi


def test_mevzuata_aykiri_ibare_kaydediliyor():
    # Belge reddedilmiyor; kusuru raporlanabilsin diye ham hâli saklanıyor.
    u = Ustveri(ivedilik_ham="ACİL", gizlilik_ham="Özel")
    assert u.ivedilik is None and u.ivedilik_ham == "ACİL"
    assert not u.ivedilik_gecerli_mi
    assert not u.gizlilik_gecerli_mi
    assert Ustveri(ivedilik=Ivedilik.ACELE).ivedilik_gecerli_mi
    assert Ustveri().ivedilik_gecerli_mi          # ibare yoksa ihlal de yok
    assert Ustveri().gizlilik_gecerli_mi


def test_gecersiz_enum_degerleri_reddediliyor():
    assert _reddediyor_mu(lambda: Ustveri(ivedilik="ACİL"))
    assert _reddediyor_mu(lambda: Ustveri(gizlilik_derecesi="Özel"))
    assert _reddediyor_mu(lambda: Ek(sira=0))
    assert _reddediyor_mu(lambda: Ustveri(konu="k" * 251))


def test_kisisel_veri_isareti_zorlaniyor():
    # Ajan unutursa veya yanlışlıkla False derse tip kazanır.
    v = Varlik(tip=VarlikTipi.TCKN, deger="10000000140", kisisel_veri=False)
    assert v.kisisel_veri
    assert not Varlik(tip=VarlikTipi.KURUM_ADI, deger="YÖK").kisisel_veri


def test_sayfa_sayisi():
    assert KaynakBilgisi().sayfa_sayisi == 1
    assert KaynakBilgisi(sayfalar=["a", "b", "c"]).sayfa_sayisi == 3


def test_linter_yalnizca_hata_dusurur():
    r = LinterRaporu(bulgular=[
        LinterBulgusu(kural_id="S-01", baslik="Sayı zorunlu", onem=Onem.HATA),
        LinterBulgusu(kural_id="I-05", baslik="Sıra yanlış", onem=Onem.UYARI),
        LinterBulgusu(kural_id="G-01", baslik="Bilgi", onem=Onem.BILGI),
    ])
    assert not r.gecti_mi
    assert len(r.hatalar) == 1 and len(r.uyarilar) == 1
    assert LinterRaporu().gecti_mi
    assert LinterRaporu(bulgular=[
        LinterBulgusu(kural_id="X", baslik="y", onem=Onem.UYARI)]).gecti_mi


def test_icerik_ozetleri():
    i = Icerik(varliklar=[Varlik(tip=VarlikTipi.TCKN, deger="1"),
                          Varlik(tip=VarlikTipi.KURUM_ADI, deger="YÖK")],
               eksik_alanlar=[EksikAlan(alan="a", aciklama="x", onem=Onem.HATA),
                              EksikAlan(alan="b", aciklama="y", onem=Onem.UYARI)])
    assert len(i.kisisel_veriler) == 1
    assert len(i.kritik_eksikler) == 1


# =============================================================================
# 4. DOSYA
# =============================================================================


def test_bos_dosya_olusturulabiliyor():
    d = Dosya()
    assert d.evrak_id and len(d.evrak_id) == 12
    assert d.surum == SURUM
    assert d.olusturma_zamani.tzinfo is not None


def test_deger_al():
    d = Dosya(metin="deneme", ustveri=Ustveri(muhatap=Taraf(birim="Şube")))
    assert d.deger_al("metin") == "deneme"
    assert d.deger_al("ustveri.muhatap.birim") == "Şube"
    assert d.deger_al("yok.boyle.bir.sey") is None
    assert d.deger_al("yok", varsayilan="X") == "X"
    assert d.deger_al("") is None


def test_deger_al_sozluk_gecisi():
    d = Dosya(metin="x")
    d.kanit_ekle("metin", Kanit(yontem=KanitYontemi.OCR, ureten="a1_okuma", guven=0.9))
    assert d.deger_al("kanit.metin.yontem") == KanitYontemi.OCR


def test_alan_yollarinin_tamami_yapida_var():
    # ALAN_YOLLARI ile sınıf alanları arasındaki sözleşme.
    d = Dosya()
    cozulmeyen = []
    for yol in sorted(ALAN_YOLLARI):
        dugum = d
        for parca in yol.split("."):
            if not hasattr(dugum, parca):
                cozulmeyen.append(yol)
                break
            dugum = getattr(dugum, parca)
            if dugum is None:
                break
    assert not cozulmeyen, f"yapıda karşılığı olmayan yol: {cozulmeyen}"


def test_bos_dosyada_kanitsiz_alan_yok():
    # GERİLEME TESTİ. Boş Taraf(), Imza() ve GelenTur.BILINMIYOR "dolu"
    # sayıldığında boş bir Dosya'da bile 4 alan raporlanıyordu ve fonksiyon
    # teste bağlanamıyordu.
    assert Dosya().kanitsiz_alanlar() == []


def test_kanitsiz_alan_tespiti():
    d = Dosya()
    d.ustveri.konu = "Sıfır Atık"
    assert d.kanitsiz_alanlar() == ["ustveri.konu"]
    d.kanit_ekle("ustveri.konu",
                 Kanit(yontem=KanitYontemi.REGEX, ureten="a2", guven=0.9))
    assert d.kanitsiz_alanlar() == []


def test_alan_dolu_mu_ontanimliyi_saymiyor():
    d = Dosya()
    assert not d.alan_dolu_mu("siniflandirma.belge_turu")   # BILINMIYOR
    assert not d.alan_dolu_mu("ustveri.muhatap")            # boş Taraf()
    assert not d.alan_dolu_mu("ustveri.ekler")              # boş liste
    d.siniflandirma.belge_turu = GelenTur.UST_YAZI
    assert d.alan_dolu_mu("siniflandirma.belge_turu")


def test_kanit_ekle_tanimsiz_yolu_reddediyor():
    d = Dosya()
    # 'sayı' Türkçe ı ile — sessizce kabul edilseydi kanıt hiç bulunamazdı
    assert _reddediyor_mu(lambda: d.kanit_ekle(
        "ustveri.sayı", Kanit(yontem=KanitYontemi.REGEX, ureten="t")))
    assert _reddediyor_mu(lambda: d.kanit_ekle(
        "uydurma.yol", Kanit(yontem=KanitYontemi.REGEX, ureten="t")))


def test_kanit_ekle_onceligi_koruyor():
    d = Dosya(ustveri=Ustveri(sayi="E-71368504-010.06.01-4471829"))
    regex = Kanit(yontem=KanitYontemi.REGEX, ureten="a2", guven=0.70)
    llm = Kanit(yontem=KanitYontemi.LLM, ureten="a3", guven=0.99)
    insan = Kanit(yontem=KanitYontemi.INSAN, ureten="kullanici", guven=0.30)

    assert d.kanit_ekle("ustveri.sayi", regex)
    assert d.kanit_ekle("ustveri.sayi", llm) is False
    assert d.kanit["ustveri.sayi"].yontem == KanitYontemi.REGEX
    assert d.kanit_ekle("ustveri.sayi", insan)
    assert d.kanit_ekle("ustveri.sayi", llm, zorla=True)
    assert d.kanit["ustveri.sayi"].yontem == KanitYontemi.LLM


def test_gecersiz_kanit_anahtari_yakalaniyor():
    # GERİLEME TESTİ. kanit_ekle yolu denetliyor ama sözlüğe doğrudan
    # yazmak denetimi atlıyordu ve JSON turunda da fark edilmiyordu.
    d = Dosya()
    d.kanit["uydurma.yol"] = Kanit(yontem=KanitYontemi.REGEX, ureten="t")
    assert d.gecersiz_kanit_anahtarlari() == ["uydurma.yol"]
    assert _reddediyor_mu(lambda: Dosya.model_validate_json(d.model_dump_json()))


def test_toplam_guven_karara_yaziliyor():
    d = Dosya()
    d.kanit_ekle("ustveri.sayi",
                 Kanit(yontem=KanitYontemi.REGEX, ureten="t", guven=0.95))
    d.kanit_ekle("icerik.ozet",
                 Kanit(yontem=KanitYontemi.LLM, ureten="t", guven=0.35))
    assert abs(d.toplam_guven_hesapla() - 0.35) < 1e-9
    assert abs(d.karar.toplam_guven - 0.35) < 1e-9


def test_toplam_sure_ve_ozet():
    d = Dosya()
    d.iz = [IzKaydi(ajan="a1_okuma", sure_ms=1200),
            IzKaydi(ajan="a3_siniflandirma", sure_ms=2450)]
    assert d.toplam_sure_ms == 3650
    assert d.evrak_id in d.ozet_satiri()


def test_fazladan_alan_her_modelde_reddediliyor():
    for M in TUM_MODELLER:
        assert _reddediyor_mu(lambda M=M: M(uydurma_alan=1)), \
            f"{M.__name__} fazladan alan kabul ediyor"


def test_ic_ice_atama_dogrulaniyor():
    d = Dosya()
    assert _reddediyor_mu(lambda: setattr(d.ustveri, "ivedilik", "ACİL"))


# =============================================================================
# 5. SERİLEŞTİRME
# =============================================================================


def _tam_dosya() -> Dosya:
    """Bütün blokları doldurulmuş gerçekçi bir belge."""
    d = Dosya()
    d.gelen_kayit = GelenKayit(kayit_sayisi="2026/4471",
                               kayit_tarihi=date(2026, 5, 14),
                               havale_edilen_birimler=["Çevre Yönetimi Şb. Md."])
    d.kaynak = KaynakBilgisi(dosya="B01.pdf", girdi_tipi=GirdiTipi.PDF_TARAMA,
                             sayfalar=["s1", "s2"], ham_metin="tam metin",
                             ocr_motoru="PaddleOCR-VL", ocr_guven=0.93)
    d.baslik = BaslikBlogu(tc_var=True, idare_adi="ÇEVRE ... BAKANLIĞI",
                           birim_adi="Yerel Yönetimler Genel Müdürlüğü",
                           teskilat=Teskilat.MERKEZ, detsis_no="71368504")
    d.ustveri = Ustveri(
        sayi="E-71368504-010.06.01-4471829", tarih=date(2026, 5, 12),
        tarih_metin="12.05.2026", konu="Sıfır Atık Uygulama Rehberi",
        gonderen=Taraf(ham="ÇEVRE...", tur=MuhatapTuru.KAMU_IDARESI),
        muhatap=Taraf(ham="DAĞITIM YERLERİNE", tur=MuhatapTuru.DAGITIM_YERLERI),
        ilgi=[Ilgi(sira="a", tarih=date(2026, 3, 27), sayi="E-71368504-010.06.01-4318774")],
        ekler=[Ek(sira=1, aciklama="Uygulama Rehberi", sayfa_sayisi=24)],
        dagitim=[DagitimSatiri(hedef="81 İl Valiliğine", sira=1)],
        ivedilik=Ivedilik.GUNLUDUR, miat=date(2026, 7, 1),
        imza=Imza(ad="Yasemin ALTINDAĞ", unvan="Genel Müdür", yetki_devri="Bakan a."))
    d.metin = "İlgi yazı ile görüş ve önerileri talep edilen..."
    d.altbilgi = AltBilgi(adres="Mustafa Kemal Mah.", telefon="(0312) 000 00 00",
                          dogrulama_metni="5070 sayılı Kanun", dogrulama_kodu="ABC123")
    d.siniflandirma = Siniflandirma(
        belge_turu=GelenTur.UST_YAZI,
        sdp=SdpKodu(kod="010.06.01", ana_grup="010", saklama_suresi="10 yıl",
                    kaynak_sayidan_mi=True),
        gerekce="Eki var, dağıtımlı")
    d.icerik = Icerik(talep="Rehberin iletilmesi", ozet="Rehber güncellendi.",
                      varliklar=[Varlik(tip=VarlikTipi.TELEFON,
                                        deger="(0312) 000 00 00")])
    d.mevzuat = [MevzuatOnerisi(mevzuat_adi="Resmî Yazışma Yönetmeliği",
                                madde="11/1", benzerlik=0.88, dogrulandi=True)]
    d.cikti_yazi = CiktiYazi(tur=UretilecekTur.CEVAP_YAZISI, konu="Rehber Hk.",
                             metin="Bilgilerinizi rica ederim.",
                             hiyerarsi_yonu=HiyerarsiYonu.ALT)
    d.yonlendirme = Yonlendirme(hedef_birim="Çevre Yönetimi Şb. Md.",
                                dagitim_turu=DagitimTuru.GEREGI)
    d.karar = Karar(insan_onayi_gerekli=True, sebepler=["belge türü güveni düşük"])
    d.iz = [IzKaydi(ajan="a3_siniflandirma", model="qwen3.5:9b", sure_ms=2450)]
    return d


def test_json_tam_sadakat():
    d = _tam_dosya()
    geri = Dosya.model_validate_json(d.model_dump_json())
    assert geri.model_dump() == d.model_dump(), "JSON turunda veri kaybı"


def test_json_tipleri_koruyor():
    geri = Dosya.model_validate_json(_tam_dosya().model_dump_json())
    assert isinstance(geri.ustveri.tarih, date)
    assert geri.ustveri.tarih == date(2026, 5, 12)
    assert isinstance(geri.siniflandirma.belge_turu, GelenTur)
    assert geri.olusturma_zamani.tzinfo is not None


def test_turkce_karakterler_kacislanmiyor():
    j = _tam_dosya().model_dump_json()
    assert "Sıfır Atık" in j
    assert "DAĞITIM YERLERİNE" in j
    assert "\\u" not in j, "Türkçe karakterler kaçışlanmış"


def test_json_semasi_uretiliyor():
    sema = Dosya.json_semasi()
    assert isinstance(sema, dict) and "properties" in sema
    for blok in ("gelen_kayit", "kaynak", "baslik", "ustveri", "metin",
                 "altbilgi", "siniflandirma", "icerik", "mevzuat",
                 "cikti_yazi", "yonlendirme", "karar", "iz", "kanit"):
        assert blok in sema["properties"], f"şemada eksik blok: {blok}"
    assert isinstance(json.dumps(sema), str)


def test_tam_dosyada_kanitsiz_alanlar_makul():
    # Kanıt hiç eklenmediğinde doldurulan alanların tamamı raporlanmalı.
    d = _tam_dosya()
    eksik = d.kanitsiz_alanlar()
    assert eksik, "hiç kanıt yokken boş liste döndü"
    assert "ustveri.sayi" in eksik and "siniflandirma.belge_turu" in eksik


# =============================================================================
# ÇALIŞTIRICI
# =============================================================================


def main() -> int:
    for akis in (sys.stdout, sys.stderr):
        try:
            akis.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    testler = [(ad, fn) for ad, fn in sorted(globals().items())
               if ad.startswith("test_") and callable(fn)]
    basarisiz = []
    for ad, fn in testler:
        try:
            fn()
            print(f"  ✓ {ad}")
        except AssertionError as e:
            basarisiz.append((ad, str(e) or "assert başarısız"))
            print(f"  ✗ {ad} — {e}")
        except Exception as e:
            basarisiz.append((ad, f"{type(e).__name__}: {e}"))
            print(f"  ✗ {ad} — {type(e).__name__}: {e}")

    print(f"\n{len(testler) - len(basarisiz)}/{len(testler)} test geçti.")
    if basarisiz:
        print("\nBaşarısız olanlar:")
        for ad, sebep in basarisiz:
            print(f"  {ad}: {sebep}")
    return 0 if not basarisiz else 1


if __name__ == "__main__":
    sys.exit(main())
