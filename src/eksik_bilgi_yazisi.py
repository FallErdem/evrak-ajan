"""Eksik bilgi talep yazısı — deterministik şablon, model çağırmaz.

NEDEN MODEL YOK
===============
Bu yazının değişen tek üç parçası var: muhatap, ilgi satırı ve memurun
seçtiği eksik maddeler. Giriş ve kapanış her belgede aynı. Sabit bir
metni modele yazdırmak, deterministik olarak bilinen bir şeyi üretime
devretmek olurdu — `yazar._talep_kur` docstring'inin "sorular
uydurulmuyor" kuralının aynısı, bir katman yukarıda.

Yan faydası: bu yazı için LLM çağrısı harcanmıyor ve iki koşu arasında
metin oynamıyor.

TASLAKTAN TAMAMEN AYRI NESNE — 2026-08-26'da düzeltilen hata
============================================================
`_talep_kur` eskiden `yazi=dosya.cikti_yazi` diyordu ve pydantic bunu
KOPYALAMIYOR, referansla tutuyordu. Sonucu:

    1  Arayüzde "eksik tamamlama yazısı" diye asıl cevap taslağı
       gösteriliyordu — alakasız görünmesinin sebebi buydu.
    2  Memur talep yazısını düzenlediğinde asıl taslak da değişiyordu;
       tek düzenlemeyle iki belge birden bozuluyordu.

Bu modül HER ZAMAN yeni bir `CiktiYazi` döndürüyor ve `dosya`ya hiçbir
şey yazmıyor. Çağıran ne yapacağına kendi karar veriyor.

KAPANIŞ İKİ YERDE HESAPLANMIYOR
===============================
`yazar.KAPANIS` sözlüğü kullanılıyor. Kendi kapanış tablomuzu kursaydık
ME-02 zamanla iki metinden birini yanlış bulurdu; Y 16/12-e tartışması
(gerçek kişi muhataplı yazılar) tek yerde çözülmüş durumda ve orada
kalmalı.
"""

from __future__ import annotations

from veri_yapisi import CiktiYazi, UretilecekTur

# Sabit parçalar. Değişen üç şey dışında her belgede birebir aynı metin.
#
# GİRİŞ CÜMLESİ PARÇALI KURULUYOR — gerekçesi ölçüldü, belge_178
# ------------------------------------------------------------
# Tek bir kalıba iki yedek birden dolarsa cümle bozuluyordu:
# "Başvurusu alınan ilgili tarafından yapılan tarafımıza ulaşan
# başvurunuz…". Eksik bilgi talebi gönderilen belgeler doğası gereği
# eksik: 178'de hem gönderen hem konu boş. Bilinmeyen parça cümleden
# ÇIKARILIYOR, yedek metinle DOLDURULMUYOR.
GIRIS_TAM = "{ozne} tarafından yapılan {konu} başvurunuz Müdürlüğümüzce incelenmiştir."
GIRIS_OZNESIZ = "Tarafımıza ulaşan {konu} başvurunuz Müdürlüğümüzce incelenmiştir."
GIRIS_KONUSUZ = "{ozne} tarafından yapılan başvurunuz Müdürlüğümüzce incelenmiştir."
GIRIS_YALIN = "Tarafımıza ulaşan başvurunuz Müdürlüğümüzce incelenmiştir."

# Muhatap çözülemediğinde yazıya konan işaret. Boş bırakmıyoruz: memur
# farkına varmadan gönderirse yazı muhatapsız çıkar. Taslaktaki
# "EBYS kayıt anında atanacak" ile aynı ilke — eksik olan görünür kalır.
MUHATAP_YOK = "(Muhatap belirlenemedi — düzenleyerek yazınız)"

GECIS = (
    "Başvurunuzun sonuçlandırılabilmesi için aşağıda belirtilen bilgi ve "
    "belgelere ihtiyaç duyulmaktadır:"
)
KAPANIS_PARAGRAFI = (
    "Söz konusu eksikliklerin tamamlanarak Müdürlüğümüze iletilmesi hâlinde "
    "başvurunuz işleme alınacaktır."
)


def _ozne(dosya) -> str | None:
    """Başvuruyu yapan tarafın cümle içinde kullanılacak yalın adı.

    Bulunamazsa None — uydurulmuyor. İmzası olmayan bir dilekçede
    gönderen gerçekten bilinmiyor ve bu, belgenin insan onayına
    düşmesinin sebebidir; yazıda da öyle görünmeli.
    """
    g = getattr(dosya.ustveri, "gonderen", None)
    for alan in ("ad", "birim", "idare", "ham"):
        deger = getattr(g, alan, None)
        if deger and str(deger).strip():
            return str(deger).strip()
    return None


def _ilgi_satiri(dosya) -> str | None:
    """Gelen belgenin tarih ve sayısı. İkisi de yoksa satır hiç yazılmaz.

    Vatandaş dilekçelerinin sayısı yok (300 belgenin 108'i böyle); olmayan
    bir sayıyı "—" diye yazmak resmî yazıda kusurdur.
    """
    u = dosya.ustveri
    tarih = u.tarih.strftime("%d/%m/%Y") if u.tarih else (u.tarih_metin or None)
    sayi = (u.sayi or "").strip() or None
    if tarih and sayi:
        return f"İlgi : {tarih} tarihli ve {sayi} sayılı başvurunuz."
    if tarih:
        return f"İlgi : {tarih} tarihli başvurunuz."
    if sayi:
        return f"İlgi : {sayi} sayılı başvurunuz."
    return None


def _konu_ifadesi(dosya) -> str | None:
    konu = (dosya.ustveri.konu or "").strip()
    return f"“{konu}” konulu" if konu else None


def _giris(dosya) -> str:
    """Bilinen parçalara göre giriş cümlesi. Eksik parça cümleden düşer."""
    ozne, konu = _ozne(dosya), _konu_ifadesi(dosya)
    if ozne and konu:
        return GIRIS_TAM.format(ozne=ozne, konu=konu)
    if konu:
        return GIRIS_OZNESIZ.format(konu=konu)
    if ozne:
        return GIRIS_KONUSUZ.format(ozne=ozne)
    return GIRIS_YALIN


def govde_kur(dosya, sorular: list[str]) -> str:
    """Yazının gövdesi. Maddeler memurun seçtikleri, sırası korunuyor."""
    from yazar import KAPANIS

    paragraflar: list[str] = []

    ilgi = _ilgi_satiri(dosya)
    if ilgi:
        paragraflar.append(ilgi)

    paragraflar.append(_giris(dosya))
    paragraflar.append(GECIS)

    # Maddeler tek paragrafta, satır satır. Numaralandırma memurun seçim
    # sırasını izliyor; kural kimliği YAZILMIYOR — vatandaşa "IM-01"
    # göstermek ona yönetmelik okutmak olur.
    paragraflar.append("\n".join(
        f"{i}) {soru.strip()}" for i, soru in enumerate(sorular, 1)))

    paragraflar.append(KAPANIS_PARAGRAFI)

    kapanis = KAPANIS.get(dosya.cikti_yazi.hiyerarsi_yonu)
    if not kapanis:
        # Yön belirlenemediyse Yazar'ın varsayılanı ne ise o. Kendi
        # varsayılanımızı koymak iki metni ayrıştırırdı.
        from veri_yapisi import HiyerarsiYonu

        kapanis = KAPANIS[HiyerarsiYonu.BILINMIYOR]
    paragraflar.append(kapanis)

    return "\n\n".join(paragraflar)


def kur(dosya, sorular: list[str]) -> CiktiYazi:
    """Eksik bilgi talep yazısını üretir. `dosya`ya HİÇBİR ŞEY YAZMAZ.

    Başlık, muhatap ve imza unvanı asıl taslaktan okunuyor — ikisi de
    aynı birim adına, aynı muhataba yazılıyor. Kopyalanıyor, paylaşılmıyor:
    bu nesne üzerinde yapılan düzenleme asıl taslağa dokunmuyor.
    """
    c = dosya.cikti_yazi
    return CiktiYazi(
        tur=UretilecekTur.EKSIK_BILGI_TALEBI,
        tur_gerekcesi="Gelen evrakta karşı taraftan istenebilir eksik bulundu.",
        sablon="eksik_bilgi_talebi",
        konu="Eksik Bilgi Talebi",
        metin=govde_kur(dosya, sorular),
        muhatap=(c.muhatap or "").strip() or MUHATAP_YOK,
        baslik=c.baslik,
        imza_unvan=c.imza_unvan,
        hiyerarsi_yonu=c.hiyerarsi_yonu,
    )
