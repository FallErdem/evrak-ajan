"""Belge türü taksonomisi — etiket adları ile şema adları arasındaki köprü.

NEDEN AYRI MODÜL
----------------
Belge türü iki ayrı sözlükte adlandırılmış:

    veri/kota.json + etiketler   ->  dilekce, bilgi_edinme, bilgilendirme
    src/veri_yapisi.py GelenTur  ->  vatandas_dilekcesi, bilgi_edinme_basvurusu,
                                     bilgilendirme_yazisi

Aynı üç şey, farklı üç ad. Kalan sekiz ad birebir aynı.

Eşleme üç yerde birden gerekiyor: Anlama (şema enum'unu üretirken),
ayristirici_dogrula.py (cevap anahtarını okurken), Parça 6 değerlendirmesi.
Üç kopya tutulursa zamanla ayrışırlar; tek kaynak burası.

NEDEN ADLAR HİZALANMADI
-----------------------
Seçenek C (enum'u kota.json adlarına çevirmek) reddedildi. Gerekçe:
`rules.yaml` 104 kural taşıyor ve `kapsama_girer_mi()` üzerinden belge
türü adlarına bakıyor. Yeniden adlandırma o kuralları SESSİZCE kırardı —
hata Parça 4'te, Denetçi yazılırken, sebebi belirsiz biçimde çıkardı.

Parça 2'nin donma kuralı da aynı yöne işaret ediyor: alan silinmez,
eklenir. Yeniden adlandırma silme sayılır.

1.2.0'DA NE EKLENDİ
-------------------
`itiraz` (11 belge) ve `gorus_talebi` (20 belge) veri setinde vardı ama
şemada yoktu. Anlama'nın şeması bu enum'dan üretildiği için o 31 belgede
doğru cevap fiziksel olarak verilemiyordu.

Kategori atamaları ÖLÇÜLDÜ, atanmadı:
    gorus_talebi   20/20 kurumdan, hepsinin sayısı var  -> kurum_yazisi
    itiraz         8 gerçek kişi, 2 şirket, 1 öğrenci   -> kisi_belgesi
"""

from __future__ import annotations

from veri_yapisi import GelenTur

# -----------------------------------------------------------------------------
# Ad eşlemesi
# -----------------------------------------------------------------------------

# etiket / kota.json adı  ->  GelenTur değeri
ETIKETTEN_SEMAYA: dict[str, str] = {
    "dilekce": GelenTur.VATANDAS_DILEKCESI.value,
    "bilgi_edinme": GelenTur.BILGI_EDINME_BASVURUSU.value,
    "bilgilendirme": GelenTur.BILGILENDIRME_YAZISI.value,
    # Kalan sekiz ad birebir aynı; yine de açıkça yazılıyor ki tabloya
    # bakan biri "eksik mi kaldı" diye düşünmesin.
    "sikayet": GelenTur.SIKAYET.value,
    "itiraz": GelenTur.ITIRAZ.value,
    "gorus_talebi": GelenTur.GORUS_TALEBI.value,
    "talep_yazisi": GelenTur.TALEP_YAZISI.value,
    "cevap_yazisi": GelenTur.CEVAP_YAZISI.value,
    "ust_yazi": GelenTur.UST_YAZI.value,
    "tekit_yazisi": GelenTur.TEKIT_YAZISI.value,
    "olur_yazisi": GelenTur.OLUR_YAZISI.value,
}

SEMADAN_ETIKETE: dict[str, str] = {v: k for k, v in ETIKETTEN_SEMAYA.items()}

# Şemada var ama veri setinde HİÇ geçmeyen türler.
#
# Anlama'nın aday listesine konmamalılar: modele hiç görmeyeceği bir seçenek
# sunmak yanlış cevap üretme riskini boşuna artırır. Şemadan da silinmiyorlar
# (donma kuralı) — sahada kullanılıyorlar, ileride veri gelebilir.
VERIDE_OLMAYAN = frozenset({
    GelenTur.DUYURU.value,
    GelenTur.GENELGE.value,
})


def etiketten(ad: str | None) -> str | None:
    """Cevap anahtarındaki türü şema değerine çevirir.

    Tanınmayan ad None döner — sessizce bir değere eşlenmez, çünkü sessiz
    eşleme ölçümü bozar ve fark edilmez.
    """
    if not ad:
        return None
    return ETIKETTEN_SEMAYA.get(ad.strip())


def semadan(deger: str | None) -> str | None:
    """Şema değerini cevap anahtarındaki ada çevirir."""
    if not deger:
        return None
    return SEMADAN_ETIKETE.get(deger.strip())


def eslesir_mi(bulunan: str | None, etiket_turu: str | None) -> bool:
    """Modelin verdiği tür, cevap anahtarındaki türle aynı mı.

    İki tarafı da şema değerine çevirip karşılaştırır; böylece hangi
    sözlükte konuşulduğu önemli olmaz.
    """
    if not bulunan or not etiket_turu:
        return False
    beklenen = etiketten(etiket_turu)
    karsilik = ETIKETTEN_SEMAYA.get(bulunan.strip(), bulunan.strip())
    return beklenen is not None and karsilik == beklenen


def dogrula() -> list[str]:
    """Tablo ile şema tutarlı mı. Boş liste = temiz."""
    sorunlar: list[str] = []
    semadaki = {t.value for t in GelenTur}

    for etiket_adi, sema_degeri in ETIKETTEN_SEMAYA.items():
        if sema_degeri not in semadaki:
            sorunlar.append(f"{etiket_adi} -> {sema_degeri}: şemada yok")

    kapsanan = set(ETIKETTEN_SEMAYA.values())
    beklenen_disarida = VERIDE_OLMAYAN | {GelenTur.BILINMIYOR.value}
    kapsanmayan = semadaki - kapsanan - beklenen_disarida
    if kapsanmayan:
        sorunlar.append(f"şemada olup tabloda olmayan: {sorted(kapsanmayan)}")

    if len(SEMADAN_ETIKETE) != len(ETIKETTEN_SEMAYA):
        sorunlar.append("iki ad aynı şema değerine eşleniyor")

    return sorunlar


if __name__ == "__main__":
    sorunlar = dogrula()
    print(f"{len(ETIKETTEN_SEMAYA)} tür eşlemesi, "
          f"{len(VERIDE_OLMAYAN)} tür veri setinde yok")
    for s in sorunlar:
        print(f"  ✗ {s}")
    print("  ✓ tutarlı" if not sorunlar else "\nSORUN VAR")
    raise SystemExit(1 if sorunlar else 0)
