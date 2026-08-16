"""Kimlik ve iletişim numarası üreteci.

    ALGORİTMAYA UYAR, GERÇEĞE ÇAKIŞMA OLASILIĞI ASGARİYE İNDİRİLİR.

NEDEN AYRI MODÜL
`varlik_havuzu.py`'ye eklenseydi rastgele seçim sırası kayar ve 300
etiketin tamamı değişirdi — üretilmiş gövdeler geçersiz olurdu. Bu bir
kez yaşandı (120 belge yeniden üretilmek zorunda kalındı).

Bu modül BELGE NUMARASINDAN türetir; rastgele sayı üreteci kullanmaz.
Aynı belge her zaman aynı numarayı alır, sıra kaymaz.

NEDEN ALGORİTMAYA UYMASI GEREKİYOR
Sistem ileride "T.C. kimlik numarası geçerli mi" diye kontrol edebilir.
Rastgele 11 hane koyarsak o kontrol her belgede hata verir ve gerçek
bir kusurla ayırt edilemez.

KAYNAK DOĞRULAMASI
İlk sürümde bu dosyadaki kod ve telefon aralıkları HAFIZADAN yazılmış,
doğrulanmamıştı. Üç telefon kodu (537, 540, 547) gerçekte Turkcell ve
Vodafone'a tahsisliydi — tam kaçınmak istediğimiz durum. Aşağıdaki
değerler BTK ve NVİ kaynaklarından teyit edildi; dayanaklar yorumlarda.
"""

from __future__ import annotations

# =============================================================================
# T.C. KİMLİK NUMARASI
# =============================================================================
# ALGORİTMA (11 hane):
#   1. hane sıfır olamaz
#   10. hane = ((1+3+5+7+9. haneler) * 7 - (2+4+6+8. haneler)) mod 10
#   11. hane = (ilk 10 hanenin toplamı) mod 10
#
# ÇAKIŞMA RİSKİ — DÜRÜST DEĞERLENDİRME
#
# Türkiye'de "test için ayrılmış" resmî bir TCKN aralığı YOKTUR. Bu
# yüzden algoritmaya uyan hiçbir numara için "kesinlikle kimseye ait
# değil" denemez.
#
# İlk sürümde "9 ile başlayanlar hiç tahsis edilmedi" yazmıştım. Bu
# DOĞRULANMAMIŞ bir varsayımdı ve tehlikeliydi:
#
#   YKN (Yabancı Kimlik Numarası) 11 hanelidir, TCKN ile AYNI kontrol
#   hanesi algoritmasını kullanır ve 99 İLE BAŞLAYAN BLOKTA tahsis
#   edilir. Tohum 99 üretirse gerçek bir yabancı kimlik numarasına
#   denk gelebilirdi.
#
# ALINAN ÖNLEMLER:
#   1. 99 bloğu HARİÇ tutulur (YKN'ye tahsisli — belgelenmiş)
#   2. İlk hane 9: MERNİS tahsisi 10000000146'dan (Atatürk) başlayarak
#      ilçe/cilt/aile sırasına göre yapılmıştır; havuzun üst ucu alt
#      ucundan seyrektir. Garanti değil, olasılık düşürücüdür.
#   3. Numara KURGUSAL ad ve KURGUSAL adresle eşleşir. Tek başına bir
#      numara kimseyi tanımlamaz.
#
# TEKNİK RAPORDA BELİRTİLECEK: numaralar sentetiktir, gerçek kişilerle
# eşleşme iddiası veya garantisi yoktur.

_TCKN_ONEK = 9


def tckn_uret(tohum: int) -> str:
    """Algoritmaya uyan sentetik T.C. kimlik numarası.

    İlk hane 9, ikinci hane 9 DEĞİL (99 bloğu YKN'ye tahsislidir).
    """
    n = (tohum * 2654435761) % 100000000      # Knuth çarpanı, dağılım için

    ikinci = n % 9          # 0-8 arası: 9 asla çıkmaz
    n //= 10
    govde = [_TCKN_ONEK, ikinci]
    for _ in range(7):
        govde.append(n % 10)
        n //= 10

    tek = sum(govde[0::2])      # 1, 3, 5, 7, 9. haneler
    cift = sum(govde[1::2])     # 2, 4, 6, 8. haneler
    govde.append(((tek * 7) - cift) % 10)
    govde.append(sum(govde) % 10)
    return "".join(str(h) for h in govde)


def tckn_gecerli_mi(no: str) -> bool:
    """Doğrulama — üretilen numaraların algoritmaya uyduğunu sınamak için."""
    if len(no) != 11 or not no.isdigit() or no[0] == "0":
        return False
    h = [int(c) for c in no]
    tek, cift = sum(h[0:9:2]), sum(h[1:8:2])
    return (h[9] == ((tek * 7) - cift) % 10
            and h[10] == sum(h[:10]) % 10)


def ykn_blogunda_mi(no: str) -> bool:
    """99 ile başlıyor mu — YKN bloğuna düşmüş olur."""
    return no.startswith("99")


# =============================================================================
# CEP TELEFONU
# =============================================================================
# KAYNAK: BTK Genel Numaralandırma Planı (btk.gov.tr, 20 Ocak 2026)
#
# TAHSİSLİ mobil kodlar:
#   50X (X: 1,5,6,7)      TT Mobil          -> 501, 505, 506, 507
#   510, 516, 561         SMŞH
#   512                   Türk Telekomünikasyon (çağrı hizmeti)
#   53X (X: 0-9)          Turkcell          -> 530-539 TAMAMI
#   54X (X: 0-9)          Vodafone          -> 540-549 TAMAMI
#   55X (X: 1,2,3,4,5,9)  TT Mobil          -> 551-555, 559
#   57X (X: 0-5)          M2M               -> 570-575
#   592                   Globalstar (GMPCS)
#   594                   TCDD (GSM-R)
#
# İLK SÜRÜMDE ÜÇ HATA VARDI: 537, 540 ve 547 "boş" sanılmıştı. Oysa
# 53X'in TAMAMI Turkcell'e, 54X'in TAMAMI Vodafone'a tahsisli. Bu
# numaralar gerçek abonelere ait olabilirdi.
#
# Aşağıdakiler KISMEN tahsisli aralıklardaki BOŞLUKLARDIR — BTK bu
# kodları bilinçli olarak dışarıda bırakmış. Hiç adı geçmeyen aralıklar
# (52X, 58X) yerine bunlar tercih edildi: adı geçmeyen bir aralık
# ileride tahsis edilebilir, boşluk ise kasıtlıdır.

_TAHSIS_EDILMEMIS_KODLAR = [
    "500", "502", "503", "504", "508", "509",   # 50X boşlukları
    "550", "556", "557", "558",                 # 55X boşlukları
]


def telefon_uret(tohum: int) -> str:
    """05 ile başlayan, tahsis edilmemiş kodlu cep telefonu numarası."""
    kod = _TAHSIS_EDILMEMIS_KODLAR[tohum % len(_TAHSIS_EDILMEMIS_KODLAR)]
    n = (tohum * 1103515245 + 12345) % 10000000
    return f"0{kod} {n // 10000:03d} {(n // 100) % 100:02d} {n % 100:02d}"


def telefon_tahsisli_mi(numara: str) -> bool:
    """Numaranın tahsisli bir koda ait olup olmadığını sınar.

    Doğrulama içindir: ürettiğimiz numaraların hiçbiri True dönmemeli.
    """
    kod = numara.replace(" ", "")[1:4]
    if not kod.isdigit():
        return False
    k = int(kod)
    return (k in (501, 505, 506, 507, 510, 512, 516, 561, 592, 594)
            or 530 <= k <= 539          # Turkcell
            or 540 <= k <= 549          # Vodafone
            or k in (551, 552, 553, 554, 555, 559)
            or 570 <= k <= 575)         # M2M


# =============================================================================
# UYGULAMA
# =============================================================================


def kisi_bilgileri_ekle(e: dict) -> dict:
    """Etikete kimlik ve telefon ekler (gerçek kişi ve öğrenci için).

    Etiketi DEĞİŞTİRMEZ, kopyasını döndürür — üreteç çıktısı bozulmaz.
    Belge numarasından türetildiği için tekrarlanabilir.
    """
    g = e.get("gonderen", {})
    if g.get("tip") not in ("gercek_kisi", "ogrenci"):
        return e

    tohum = int(e["belge_no"])
    g = dict(g)
    g.setdefault("tckn", tckn_uret(tohum))
    g.setdefault("telefon", telefon_uret(tohum + 7919))   # farklı tohum
    yeni = dict(e)
    yeni["gonderen"] = g
    return yeni
