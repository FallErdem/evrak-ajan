"""Mini linter — üretilen metin gövdesini etiketine karşı denetler.

NE YAPAR
Bir metin ile o metnin etiketini (cevap anahtarı) alır, aralarındaki
uyuşmazlıkları bulur. Yönetmelik ve Kılavuz'un metin gövdesine uygulanan
kurallarını, artı üretim sürecinin kendi kurallarını denetler.

NE YAPMAZ
Dilbilgisi ve anlam denetimi. Bunlar deterministik olarak yakalanamıyor:

    "Uygulamalı okul yönetimlerine duyurulması"   <- ek yanlış
    "Yapılan işlem, ... aykırıdır"                <- ortada işlem yok

İkisi de bütün kurallardan geçer. Bunlar için üç katmanlı savunmanın
diğer iki katmanı var: ADIM 6'da LLM denetçisi (ikinci bir çağrıyla
"bu metinde dilbilgisi hatası var mı" sorulur) ve ADIM 8'de insan
örneklemesi. Bu dosya birinci katman.

NEDEN ETİKET AYRI DOSYADA
Denetim, metni bir CEVAP ANAHTARINA karşı yapıyor. "Kapanış doğru mu"
sorusunun cevabı belgenin hiyerarşi yönüne bağlı; linter bunu metinden
tahmin edemez, bilmesi gerekir. Etiket ADIM 4'te üreteç tarafından
üretilecek; şu an elle yazılıyor ama biçim aynı kalacak.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

# =============================================================================
# BÖLÜM 1 — TÜRKÇE METİN YARDIMCILARI
# =============================================================================


def tr_kucult(metin: str) -> str:
    """Türkçeye uygun küçük harfe çevirme.

    Python'un str.lower() metodu Türkçe için yanlış çalışır:
        "İ".lower() -> "i̇"  (i + birleşen nokta, iki karakter)
        "I".lower() -> "i"   (olması gereken "ı")

    Bu düzeltilmezse "İlgi" ile "ilgi" eşleşmez ve bütün metin
    karşılaştırmaları sessizce yanlış sonuç verir.
    """
    return metin.replace("İ", "i").replace("I", "ı").lower()


def sapkasiz(metin: str) -> str:
    """Düzeltme işaretlerini kaldırır: â->a, î->i, û->u.

    Aynı kelime iki türlü yazılıyor ("vekâletname" / "vekaletname",
    "ikametgâh" / "ikametgah"). Anahtar terim aramasında ikisi de
    kabul edilmeli, yoksa doğru metinler hatalı sayılır.
    """
    esle = {"â": "a", "Â": "A", "î": "i", "Î": "I", "û": "u", "Û": "U"}
    return "".join(esle.get(k, k) for k in metin)


def normalize(metin: str) -> str:
    """Karşılaştırma için tek biçime indirger.

    Unicode normalleştirmesi de yapılıyor: aynı Türkçe harf iki farklı
    kod dizisiyle yazılabiliyor (ö = tek karakter, veya o + iki nokta).
    Metin farklı kaynaklardan geldiğinde bu fark görünmez ama eşleşmeyi
    bozar.
    """
    metin = unicodedata.normalize("NFC", metin)
    # Kesme işareti atılır: model "İlgi'de kayıtlı" yazıyor, etiket
    # "ilgide kayıtlı" diyor. İkisi aynı ifade.
    metin = metin.replace("'", "").replace("\u2019", "").replace("\u02bc", "")
    return sapkasiz(tr_kucult(metin))


def paragraflara_ayir(metin: str) -> list[str]:
    """Boş satırlara göre paragraflara böler."""
    parcalar = re.split(r"\n\s*\n", metin.strip())
    return [p.strip() for p in parcalar if p.strip()]


# Nokta ile biten ama cümleyi bitirmeyen kısaltmalar. Listede olmayan bir
# kısaltma cümle sayımını şişirir; o yüzden liste geniş tutuluyor.
_KISALTMALAR = (
    "Hk", "hk", "vb", "vs", "md", "bkz", "Sn", "Dr", "Doç", "Prof", "Yrd",
    "No", "no", "ör", "yy", "sy", "bs", "çev", "haz", "age", "vd", "Av",
    "Tel", "Fax", "Mah", "Cad", "Sok", "Apt", "Blv",
)
_YER_TUTUCU = "\x00"


def cumlelere_ayir(paragraf: str) -> list[str]:
    """Paragrafı cümlelere böler.

    Türkçede nokta üç ayrı işi görüyor ve üçü de karışıyor:
        cümle sonu   : "...tabidir. Uygulamanın..."
        kısaltma     : "İmar Durumu Hk."
        sayı ayracı  : "12.05.2026", "010.06.01", "6. sınıf"

    Yöntem: önce cümle sonu OLMAYAN noktalar geçici bir karakterle
    değiştirilir, bölme yapılır, sonra geri konur. Bölme ölçütü nokta
    değil, "nokta + boşluk + BÜYÜK HARF" — böylece "6. sınıf" bölünmez
    ama "...tabidir. Uygulamanın" bölünür.
    """
    p = paragraf

    # Rakam.Rakam kalıbı: tarih, SDP kodu, sürüm numarası
    p = re.sub(r"(?<=\d)\.(?=\d)", _YER_TUTUCU, p)

    # Bilinen kısaltmalar
    for k in _KISALTMALAR:
        p = re.sub(rf"\b{re.escape(k)}\.", k + _YER_TUTUCU, p)

    # Tek harf + nokta (baş harf: "A. Yılmaz")
    p = re.sub(r"\b([A-ZÇĞİÖŞÜ])\.", r"\1" + _YER_TUTUCU, p)

    # Bölme: cümle sonu işareti + boşluk + büyük harf veya tırnak
    parcalar = re.split(r'(?<=[.!?])\s+(?=[A-ZÇĞİÖŞÜ"„])', p)

    return [c.replace(_YER_TUTUCU, ".").strip() for c in parcalar if c.strip()]


# =============================================================================
# BÖLÜM 2 — ETİKET
# =============================================================================


@dataclass(frozen=True)
class Etiket:
    """Bir belgenin cevap anahtarı.

    ADIM 4'te üreteç bunu kendisi üretecek. Şu an elle yazılıyor ama
    alanlar aynı kalacak; linter'ın kodu değişmeyecek.
    """

    belge_no: str
    yazan_tipi: str            # kurum | vatandas
    hiyerarsi_yonu: str        # ust | ayni | alt | gercek_kisi | yok
    ilgi_var: bool
    ek_var: bool
    paragraf_cumle_sayilari: list[int]
    yasakli_adlar: list[str] = field(default_factory=list)
    anahtar_terimler: list[str] = field(default_factory=list)
    aciklama: str = ""

    @property
    def beklenen_kapanis(self) -> str:
        """Hiyerarşi yönünden kapanış türünü türetir.

        Kılavuz 13.1: rica YALNIZCA aşağı doğru. Üst ve aynı düzeydeki
        makamlara arz edilir. Gerçek kişiye "Bilgilerinize sunulur."
        Vatandaşın yazdığı belgede kapanış "arz ederim" olur (Y m.31/7
        bunu zorunlu tutmuyor ama şartnamemiz istiyor).
        """
        if self.yazan_tipi == "vatandas":
            return "arz"
        return {
            "ust": "arz",
            "ayni": "arz",
            "alt": "rica",
            "karma": "karma",
            "gercek_kisi": "sunulur",
            "kurum_disi": "rica",
        }.get(self.hiyerarsi_yonu, "arz")

    @classmethod
    def yukle(cls, yol: str | Path) -> "Etiket":
        veri = json.loads(Path(yol).read_text(encoding="utf-8"))
        veri.pop("_aciklama", None)
        return cls(**veri)


# =============================================================================
# BÖLÜM 3 — BULGU
# =============================================================================


class Onem(StrEnum):
    """Bulgunun ağırlığı.

    HATA  : belge kullanılamaz, yeniden üretilmeli
    UYARI : şüpheli ama yanlış alarm olabilir, insan bakmalı
    """

    HATA = "hata"
    UYARI = "uyari"


@dataclass(frozen=True)
class Bulgu:
    kural: str
    onem: Onem
    mesaj: str
    kanit: str | None = None

    def __str__(self) -> str:
        isaret = "✗" if self.onem is Onem.HATA else "!"
        satir = f"   {isaret} {self.kural:<14} {self.mesaj}"
        if self.kanit:
            satir += f'\n     kanıt: "{self.kanit}"'
        return satir


@dataclass
class Rapor:
    belge_no: str
    bulgular: list[Bulgu] = field(default_factory=list)

    @property
    def hatalar(self) -> list[Bulgu]:
        return [b for b in self.bulgular if b.onem is Onem.HATA]

    @property
    def uyarilar(self) -> list[Bulgu]:
        return [b for b in self.bulgular if b.onem is Onem.UYARI]

    @property
    def temiz_mi(self) -> bool:
        """Hata yoksa temiz. Uyarı temizliği bozmaz.

        ADIM 6'nın "üret -> denetle -> hatalıysa yeniden üret" döngüsü
        buna bakacak. Uyarıda yeniden üretmiyoruz; yanlış alarm olabilir
        ve her uyarıda yeniden üretmek maliyeti katlar.
        """
        return not self.hatalar


# =============================================================================
# BÖLÜM 4 — KONTROLLER
# =============================================================================

# --- kapanış -----------------------------------------------------------------

_KAPANIS_DESENLERI = {
    "arz": r"arz ederim\s*\.?\s*$",
    "rica": r"rica ederim\s*\.?\s*$",
    "karma": r"arz\s*(?:ve|/)\s*rica ederim\s*\.?\s*$",
    "sunulur": r"(?:bilgilerinize sunulur|saygılarımla|saygılarımı sunarım)\s*\.?\s*$",
}

# Y m.16/12-a ve K 13.1: kapanış fiili "arz ederim" veya "rica ederim"
# biçimindedir. Edilgen ve çoğul biçimler kullanılmaz.
_YASAK_KAPANIS = (
    "arz olunur", "rica olunur", "arz edilir", "rica edilir",
    "arz ederiz", "rica ederiz", "arz etmekteyiz", "rica etmekteyiz",
    "arz olunmaktadır", "rica olunmaktadır", "arz ve rica olunur",
)


def _kapanis_kontrol(metin: str, e: Etiket) -> list[Bulgu]:
    bulgular = []
    n = normalize(metin.strip())

    # Yasak varyantlar metnin herhangi bir yerinde olabilir
    for yasak in _YASAK_KAPANIS:
        if normalize(yasak) in n:
            bulgular.append(Bulgu(
                "ME-02", Onem.HATA,
                f"Yasak kapanış biçimi kullanılmış: '{yasak}'. "
                f"Doğrusu 'arz ederim' veya 'rica ederim'.",
                yasak,
            ))

    # "önem arz etmektedir" kapanışla karışabiliyor ama geçerli Türkçe
    if re.search(r"önem arz et", n):
        bulgular.append(Bulgu(
            "ME-02", Onem.UYARI,
            "'önem arz etmektedir' kalıbı var. Kapanış yerine geçmiş "
            "olabilir; kapanış cümlesini ayrıca kontrol edin.",
        ))

    beklenen = e.beklenen_kapanis
    desen = _KAPANIS_DESENLERI[beklenen]

    if re.search(desen, n):
        return bulgular

    # Beklenen yok — başka bir geçerli kapanış var mı?
    bulunan = [ad for ad, d in _KAPANIS_DESENLERI.items() if re.search(d, n)]
    if bulunan:
        bulgular.append(Bulgu(
            "ME-03", Onem.HATA,
            f"Kapanış yönü yanlış: '{bulunan[0]}' yazılmış, '{beklenen}' "
            f"olmalıydı (hiyerarşi yönü: {e.hiyerarsi_yonu}).",
            metin.strip().splitlines()[-1][-70:],
        ))
    else:
        bulgular.append(Bulgu(
            "ME-02", Onem.HATA,
            f"Kapanış cümlesi yok veya tanınmıyor. Beklenen: '{beklenen}'.",
            metin.strip().splitlines()[-1][-70:],
        ))
    return bulgular


# --- şahsileştirme -----------------------------------------------------------

# K 13.1: metinde şahsileştirilmiş ifade bulunmamalı (Planlıyoruz ->
# Planlanmaktadır). Tek istisna kapanış cümlesi.
#
# NEDEN İKİ AYRI YÖNTEM: Türkçede iyelik eki ile şahıs eki benzer görünüyor.
# "Müdürlüğümüz" (iyelik, SERBEST) ile "inceledik" (şahıs, YASAK) ayrımını
# ekten yapmak mümkün değil. Bu yüzden:
#   - Belirsiz olmayan ekler (-yoruz, -mekteyiz, -acağız) desenle aranıyor
#   - Belirsiz olanlar (-dık, -tik) için sabit kelime listesi kullanılıyor
# Aksi hâlde "artık", "yazımız", "Başkanlığımız" yanlış alarm verir.

_SAHIS_DESENI = re.compile(
    r"\b\w{2,}(?:ıyoruz|iyoruz|uyoruz|üyoruz|ıyorum|iyorum|uyorum|üyorum"
    r"|maktayız|mekteyiz|maktayım|mekteyim"
    r"|acağız|eceğiz|acağım|eceğim)\b"
)

# Sabit liste kaçırıyordu ("yaşadık" listede yoktu). Artık liste YEDEK;
# asıl yakalama _SAHIS_EK_DESENI ile yapılıyor.
_SAHIS_KELIMELERI = frozenset("""
ettik yaptık aldık verdik gördük bulduk sunduk gönderdik istedik
inceledik değerlendirdik belirledik hazırladık kararlaştırdık
uyguladık başlattık tamamladık düşündük bildirdik saptadık yaşadık
ettim yaptım aldım verdim gördüm buldum sundum gönderdim istedim
inceledim değerlendirdim belirledim hazırladım düşündüm bildirdim
""".split())

# Geçmiş zaman birinci çoğul/tekil eki: -dık/-dik/-duk/-dük ve -tık/-tik...
#
# TEHLİKE: Türkçede iyelik ve isim kökleri de bu harflerle bitebilir
# ("artık", "açık", "yazdık" değil "yazık"). Bu yüzden desen yalnızca
# FİİL KÖKÜ + GEÇMİŞ ZAMAN EKİ birleşimini arıyor: ekten önce en az iki
# harf ve sonrasında kelime sınırı. Yanlış alarm verenler ayrıca
# _SAHIS_ISTISNA listesinde.
_SAHIS_EK_DESENI = re.compile(
    r"\b\w{3,}(?:dık|dik|duk|dük|tık|tik|tuk|tük)\b"
)

# Bu kelimeler yukarıdaki desene uyuyor ama fiil değil.
_SAHIS_ISTISNA = frozenset("""
artık açık ilgili yazık karışık kapalı aralık sıklık yaklaşık
katılık darlık varlık birlik dirlik açıklık sağlık yatık
""".split())


def _sahsilestirme_kontrol(metin: str, e: Etiket) -> list[Bulgu]:
    # Vatandaş, öğrenci ve özel hukuk tüzel kişisi birinci şahıs yazar.
    # yazan_tipi iki değerliyken yalnızca "vatandas" atlanıyordu; üç yeni
    # değer eklenince öğrenci ve şirket yazıları yanlış alarm veriyordu.
    if e.yazan_tipi in ("vatandas", "ogrenci", "ozel_tuzel"):
        return []

    # Kapanış cümlesi ("arz ederim") istisnadır, kesip atılıyor
    govde = re.sub(
        r"(?:bilgilerini(?:zi|ze)?\s+(?:ve\s+gereğini\s+)?)?"
        r"(?:arz|rica)(?:\s*(?:ve|/)\s*rica)?\s+ederim\s*\.?\s*$",
        "", normalize(metin.strip()),
    )

    bulgular = []
    for eslesme in _SAHIS_DESENI.finditer(govde):
        bulgular.append(Bulgu(
            "K13.1", Onem.HATA,
            "Şahsileştirilmiş ifade. Genelleştirilmiş kip kullanılmalı.",
            eslesme.group(),
        ))

    for eslesme in _SAHIS_EK_DESENI.finditer(govde):
        kelime = eslesme.group()
        if kelime in _SAHIS_ISTISNA:
            continue
        bulgular.append(Bulgu(
            "K13.1", Onem.HATA,
            "Şahsileştirilmiş fiil. Edilgen biçim kullanılmalı.",
            kelime,
        ))

    # Yedek: desene uymayan biçimler için sabit liste
    for kelime in re.findall(r"\b\w+\b", govde):
        if kelime in _SAHIS_KELIMELERI and not _SAHIS_EK_DESENI.fullmatch(kelime):
            bulgular.append(Bulgu(
                "K13.1", Onem.HATA,
                "Şahsileştirilmiş fiil. Edilgen biçim kullanılmalı.",
                kelime,
            ))
    return bulgular


# --- vatandaş belgesinde kurum ağzı ------------------------------------------

_KURUM_AGZI = ("müdürlüğümüz", "başkanlığımız", "bakanlığımız",
               "kurumumuz", "rektörlüğümüz", "valiliğimiz")


def _vatandas_agzi_kontrol(metin: str, e: Etiket) -> list[Bulgu]:
    """Vatandaş dilekçesinde kurum ağzı kullanılmamalı.

    Vatandaş bir kurum değildir; "Müdürlüğümüzce" diye yazamaz. Bu hata,
    talimatın vatandaş belgeleri için geçersiz kılınmadığında ortaya
    çıkar — geçersiz kılma bloğunun çalışıp çalışmadığının ölçüsü.
    """
    if e.yazan_tipi != "vatandas":
        return []
    n = normalize(metin)
    return [
        Bulgu("VTD-01", Onem.HATA,
              f"Vatandaş belgesinde kurum ağzı: '{k}'. Yazan kişi kurum değil.",
              k)
        for k in _KURUM_AGZI if k in n
    ]


# --- yapı --------------------------------------------------------------------


def _yapi_kontrol(metin: str, e: Etiket) -> list[Bulgu]:
    bulgular = []
    paragraflar = paragraflara_ayir(metin)
    beklenen = e.paragraf_cumle_sayilari

    if len(paragraflar) != len(beklenen):
        bulgular.append(Bulgu(
            "BCM-01", Onem.HATA,
            f"Paragraf sayısı {len(paragraflar)}, beklenen {len(beklenen)}. "
            f"Paragraflar arasında boş satır olmalı.",
        ))
        return bulgular  # cümle sayımı anlamsız kalır

    for i, (p, bek) in enumerate(zip(paragraflar, beklenen), start=1):
        gercek = len(cumlelere_ayir(p))
        if gercek != bek:
            bulgular.append(Bulgu(
                "BCM-02", Onem.UYARI,
                f"{i}. paragrafta {gercek} cümle var, beklenen {bek}.",
            ))
    return bulgular


# --- metin tamlığı -----------------------------------------------------------


def _tamlik_kontrol(metin: str, e: Etiket) -> list[Bulgu]:
    """Metin yarıda kesilmiş mi.

    Gemini'nin düşünme tokenleri max_tokens bütçesinden yiyor; bütçe
    yetmeyince metin cümle ortasında kesiliyor. Ölçülen örnek:
        "...Düzenlenen belge, kimlik ibrazı ile ş"
    Bu kontrol o durumu yakalar.
    """
    kirpik = metin.strip()
    if not kirpik:
        return [Bulgu("TAM-01", Onem.HATA, "Metin boş.")]

    if not kirpik.endswith((".", "!", "?")):
        return [Bulgu(
            "TAM-01", Onem.HATA,
            "Metin noktalama işaretiyle bitmiyor — yarıda kesilmiş olabilir.",
            kirpik[-60:],
        )]

    # Nokta var ama son cümle çok kısa: "...ile ş." gibi
    son = cumlelere_ayir(paragraflara_ayir(kirpik)[-1])[-1]
    if len(son.split()) < 2:
        return [Bulgu(
            "TAM-01", Onem.UYARI,
            "Son cümle tek kelimelik — kesilme olabilir.", son,
        )]
    return []


# --- kurum adı sızıntısı ------------------------------------------------------


def _ad_sizintisi_kontrol(metin: str, e: Etiket) -> list[Bulgu]:
    """Gönderen ve muhatabın adı gövdede geçmemeli.

    Bu bilgi başlık bloğunda ve muhatap satırında zaten var; gövdede
    tekrarlanması yazıyı hem uzatır hem gerçek yazışma diline aykırıdır.
    Kurum kendinden "Müdürlüğümüz" diye söz eder.
    """
    n = normalize(metin)
    return [
        Bulgu("ATF-01", Onem.HATA,
              f"Kurum adı gövdede geçiyor: '{ad}'. "
              f"'Müdürlüğümüz' gibi bir ifade kullanılmalı.", ad)
        for ad in e.yasakli_adlar if normalize(ad) in n
    ]


# --- bilgi kapsama -----------------------------------------------------------


# Anlam tasimayan kelimeler — kapsama kontrolunde sayilmaz.
# Anlam taşımayan sözcükler — kapsama kontrolünde sayılmaz.
# NORMALIZE EDİLEREK saklanır: normalize() Türkçe harfleri korur (ç, ş, ı),
# liste ASCII yazılınca "içinde" ile "icinde" eşleşmiyordu.
_ETKISIZ = frozenset(normalize(k) for k in """
ve veya ile de da ki bu şu o bir birer her tüm bütün için gibi kadar
olan olarak üzere hakkında ilişkin dair konusunda kapsamında
edilmiştir edilmiş edilecek edilir yapılmıştır yapılmış yapılacak
olmuştur olmuş olacak olup bulunmaktadır bulunan gerekmektedir
tarihinden itibaren sonra önce hâlinde halinde
içinde içerisinde üzerine doğrultusunda gereği gereğince nedeniyle
söz konusu ayrıca yine ancak fakat ise iken kere defa
sonuçlandırılmıştır sonuçlanmıştır tamamlanmıştır karşılanmıştır
düzenlenmiştir güncellenmiştir alınmıştır görülmüştür verilmiştir
gönderilmiştir bildirilmiştir iletilmiştir hazırlanmıştır
""".split())


_ETKISIZ_KOK = frozenset(k if len(k) <= 5 else k[:5] for k in _ETKISIZ)


def _icerik_sozcukleri(metin: str) -> list[str]:
    """Anlam taşıyan sözcükler, ek atılmış hâlde.

    SABİT KESİM YANLIŞ SONUÇ VERİYORDU. 5 harfe kesince "yazı" (4 harf)
    ile "yazıda" (kesilince "yazıd") eşleşmiyordu — şartnamede "yazı"
    geçen bir bilgi, metinde "yazıda" olarak geçtiğinde bulunamıyordu.

    Çözüm: kök uzunluğu kelimeye göre. Kısa kelimelerde tamamı, uzun
    kelimelerde ilk 5 harf.
    """
    return [_kok(k) for k in re.findall(r"\w+", normalize(metin))
            if len(k) > 3 and k not in _ETKISIZ and _kok(k) not in _ETKISIZ_KOK]


def _kok(kelime: str) -> str:
    """Kaba kök: 6 harften kısa kelimeler olduğu gibi, uzunlar ilk 5 harf."""
    return kelime if len(kelime) <= 5 else kelime[:5]


def _kapsama_kontrol(metin: str, e: Etiket) -> list[Bulgu]:
    """Şartnamedeki somut bilgilerin hepsi metne girmiş mi.

    Model malzemesi bittiğinde iki şeyden birini yapıyor: uyduruyor veya
    bilgi düşürüyor. İkincisi daha sinsi — metin kusursuz görünür ama
    etiketle uyuşmaz. Ölçülen örnek: "Talep 2: konunun değerlendirilmesi"
    bir koşuda metne hiç girmemişti.
    """
    n = normalize(metin)
    metin_sozcukleri = set(_icerik_sozcukleri(metin))
    bulgular = []
    for terim in e.anahtar_terimler:
        if normalize(terim) in n:
            continue
        # TAM EŞLEŞME ARAMAK YANLIŞ ALARM ÜRETİYOR. Model bilgiyi doğru
        # aktarıyor ama kendi cümlesini kuruyor:
        #   şartname: "15.01.2026 tarihinde yürürlüğe girmiştir"
        #   metin   : "Düzenlemenin yürürlük tarihi 15.01.2026'dır"
        # Bilgi metinde VAR. Bu yüzden içerik sözcüklerinin çoğunun
        # geçmesi yeterli sayılıyor.
        sozcukler = _icerik_sozcukleri(terim)
        if not sozcukler:
            continue
        # ÖNEK EŞLEŞME: terimdeki "yazı" kökü, metindeki "yazıd" kökünü de
        # bulmalı. Tam eşitlik aranınca ek almış biçimler kaçıyordu.
        eslesen = sum(1 for k in sozcukler
                      if any(m.startswith(k) or k.startswith(m)
                             for m in metin_sozcukleri))
        if eslesen / len(sozcukler) < 0.6:
            bulgular.append(Bulgu(
                "KPS-01", Onem.HATA,
                f"Şartnamedeki bilgi metne girmemiş "
                f"({eslesen}/{len(sozcukler)} sözcük): '{terim[:44]}'", terim))
    return bulgular


# --- ek ve ilgi ---------------------------------------------------------------

# Çekimli biçimler de sayılır: "ektedir", "ekindedir", "ilişiktedir".
# Kelime sınırlı desen bunları kaçırıyordu ve "önceki başvurumun sureti
# ektedir" cümlesi ek atfı sayılmıyordu.
# Fiil biçimleri de ek atfıdır: "dilekçeme ekledim", "ekliyorum",
# "eklenmiştir". Yalnızca yer bildiren biçimler (ekte, ilişikte) aranınca
# vatandaş dilekçelerindeki doğal ifade kaçırılıyordu.
_EK_DESENI = re.compile(
    r"\b(ekte\w*|ekinde\w*|ekimizde\w*|ilişikte\w*|ilişiğinde\w*|"
    r"ek olarak|ekli\b|yazımız ekind\w*|ekled\w+|ekliyor\w*|eklenmiş\w*|"
    r"eke dâhil|eke dahil|ekinde sun\w+)")
_ILGI_DESENI = re.compile(r"\bilgi(?:'de|de|ye|nde)?\b")


def _ek_ilgi_kontrol(metin: str, e: Etiket) -> list[Bulgu]:
    bulgular = []
    n = normalize(metin)

    ek_atfi = bool(_EK_DESENI.search(n))
    if e.ek_var and not ek_atfi:
        bulgular.append(Bulgu(
            "EK-01", Onem.HATA,
            "Belgede ek var ama metinde eke atıf yok "
            "('...ekte sunulmuştur' gibi bir ifade bekleniyor).",
        ))
    elif not e.ek_var and ek_atfi:
        bulgular.append(Bulgu(
            "EK-02", Onem.HATA,
            "Belgede ek yok ama metin ekten söz ediyor. "
            "Etiket ile belge çelişiyor.",
            _EK_DESENI.search(n).group(),
        ))

    ilk_cumle = normalize(cumlelere_ayir(paragraflara_ayir(metin)[0])[0])
    ilgi_atfi = bool(_ILGI_DESENI.search(ilk_cumle))

    if e.ilgi_var and not ilgi_atfi:
        bulgular.append(Bulgu(
            "ILG-01", Onem.UYARI,
            "İlgi var ama ilk cümle ilgiye atıfla başlamıyor.",
            ilk_cumle[:70],
        ))
    elif not e.ilgi_var and _ILGI_DESENI.search(n):
        bulgular.append(Bulgu(
            "ILG-02", Onem.HATA,
            "İlgi yok ama metin ilgiden söz ediyor.",
        ))
    return bulgular


# --- yasak biçim ve artık -----------------------------------------------------

_YASAK_BICIM = (
    (r"^\s*T\.?C\.?\s*$", "Başlık bloğu (T.C.) gövdeye yazılmış"),
    (r"^\s*(Sayı|Konu|İlgi|Tarih)\s*:", "Üstveri satırı gövdeye yazılmış"),
    (r"^\s*(EK|EKİ|EKLER|DAĞITIM)\s*:", "Ek/dağıtım listesi gövdeye yazılmış"),
    (r"\*\*|^#{1,6}\s|^\s*[-*+]\s+|^\s*\d+[.)]\s+", "Biçimlendirme işareti (markdown/madde)"),
    (r"```", "Kod bloğu işareti"),
    (r"\.\.\.|…", "Üç nokta — resmî yazıda kullanılmaz. Kapanış cümlesinin "
                  "başına yapıştırılmış olabilir."),
    (r"^\s*(İşte|Aşağıda|Tabii|Elbette)\b", "Modelin açıklama cümlesi"),
    (r"!", "Ünlem işareti — resmî yazıda kullanılmaz"),
)


def _bicim_kontrol(metin: str, e: Etiket) -> list[Bulgu]:
    """Gövdeye ait olmayan şeyler yazılmış mı.

    Şablon başlığı, sayıyı, tarihi, imzayı kendisi kuruyor. Model bunları
    da yazarsa belge iki kez başlıklı olur.
    """
    bulgular = []
    for desen, mesaj in _YASAK_BICIM:
        m = re.search(desen, metin, re.MULTILINE)
        if m:
            bulgular.append(Bulgu(
                "BIC-01", Onem.HATA, mesaj, m.group().strip()[:50],
            ))
    return bulgular


# =============================================================================
# BÖLÜM 5 — ANA GİRİŞ
# =============================================================================

_KONTROLLER = (
    _tamlik_kontrol,
    _bicim_kontrol,
    _kapanis_kontrol,
    _sahsilestirme_kontrol,
    _vatandas_agzi_kontrol,
    _ad_sizintisi_kontrol,
    _kapsama_kontrol,
    _ek_ilgi_kontrol,
    _yapi_kontrol,
)


def denetle(metin: str, etiket: Etiket) -> Rapor:
    """Metni etiketine karşı denetler.

    Kontroller sırayla çalışır ve birbirini durdurmaz: bir belgede birden
    çok hata olabilir ve hepsini bir seferde görmek, teker teker
    düzeltmekten hızlıdır.
    """
    rapor = Rapor(belge_no=etiket.belge_no)
    for kontrol in _KONTROLLER:
        try:
            rapor.bulgular.extend(kontrol(metin, etiket))
        except Exception as hata:  # noqa: BLE001
            # Bir kontrolün çökmesi diğerlerini engellememeli. 450 belgelik
            # koşuda tek bir beklenmedik metin bütün denetimi durdurmasın.
            rapor.bulgular.append(Bulgu(
                "SIS-01", Onem.UYARI,
                f"{kontrol.__name__} çalışırken hata: {type(hata).__name__}: {hata}",
            ))
    return rapor
