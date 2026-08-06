"""Varlık havuzu — belgelerdeki somut bilgileri üreten kurgusal değerler.

NE ÜRETİR
Kişi adı, adres, ada/parsel, tarih, tutar, süre gibi belgenin içini dolduran
değerler. Hepsi kurgusal ama biçimsel olarak gerçeğe uygun.

NEDEN KURGUSAL
Şartname gerçek kişi verisi kullanılmasını istemiyor. Kurumlar gerçek (izin
verildi), kişiler ve olaylar kurgusal.

NEDEN ŞABLON, LLM DEĞİL
Bu değerleri LLM'e ürettirmek maliyeti iki katına çıkarır ve tekrarlanabilirliği
bozar. Çeşitlilik asıl olarak üst katmandan geliyor: 115 SDP kodu × 3 örnek konu
× 30 birim × 11 belge türü. Somut sayıların çeşitliliği ikincil.

Yetersiz çıkarsa LLM'e geçmek tek fonksiyon değişikliğidir; çağıran kod aynı
kalır.

TEKRARLANABİLİRLİK
Tüm üretim `random.Random(tohum)` üzerinden. Aynı tohum, aynı çıktı.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta

# =============================================================================
# KİŞİ ADLARI
# =============================================================================
# Yaygın Türkçe ad ve soyadların çaprazı. 40 x 40 = 1600 kombinasyon;
# 300 belgede tekrar riski düşük. Gerçek bir kişiye denk gelme ihtimali
# kaçınılmaz ama kombinasyon rastgele olduğu için kasıtlı değil.

_ADLAR_ERKEK = """
Ahmet Mehmet Mustafa Ali Hüseyin Hasan İbrahim Osman Yusuf Murat
Ömer Kemal Salih Ramazan Şaban Fatih Serkan Emre Burak Onur
""".split()

_ADLAR_KADIN = """
Ayşe Fatma Emine Hatice Zeynep Elif Meryem Şerife Sultan Havva
Merve Esra Büşra Selin Derya Gamze Pınar Sevgi Nurten Aslı
""".split()

_SOYADLAR = """
Yılmaz Kaya Demir Şahin Çelik Yıldız Yıldırım Öztürk Aydın Özdemir
Arslan Doğan Kılıç Aslan Çetin Kara Koç Kurt Özkan Şimşek
Polat Korkmaz Çakır Erdoğan Yavuz Bulut Güneş Aksoy Bozkurt Turan
Sarı Aktaş Ateş Duman Karaca Uçar Güler Keskin Tekin Avcı
""".split()

# =============================================================================
# YER BİLGİLERİ
# =============================================================================
# Yenimahalle'nin gerçek mahalleleri (kamuya açık idari bilgi).
_MAHALLELER = """
Demetevler Batıkent Karşıyaka Yeşilevler Şentepe Ragıpbey Gayret
Emniyet Ostim Ergazi Çiğdemtepe Turgut Özal İvedik Yakacık
Susuz Kaletepe Barıştepe Aşağı Yahyalar Yukarı Yahyalar Serhat
""".split("\n")[0].split() if False else [
    "Demetevler", "Batıkent", "Karşıyaka", "Yeşilevler", "Şentepe",
    "Ragıpbey", "Gayret", "Emniyet", "Ostim", "Ergazi",
    "Çiğdemtepe", "İvedik", "Yakacık", "Susuz", "Kaletepe",
    "Barıştepe", "Serhat", "Pamuklar", "Uğur Mumcu", "Beştepe",
]

# Kurgusal sokak adları — gerçek bir sokakla çakışsa bile belge kurgusal.
_SOKAK_ONEKLERI = [
    "Çınar", "Zeytin", "Lale", "Menekşe", "Papatya", "Manolya", "Ihlamur",
    "Akasya", "Kestane", "Ceviz", "Erguvan", "Yasemin", "Nergis", "Sümbül",
]
_SOKAK_TURU = ["Sokak", "Sokağı", "Caddesi"]

# =============================================================================
# BELGE İÇİ DEĞERLER
# =============================================================================

_TESLIM_SARTLARI = [
    "kimlik ibrazı ile şahsen veya vekâletname ile",
    "kimlik belgesi ibraz edilerek şahsen",
    "noter onaylı vekâletname ile veya bizzat",
]

_GECERLILIK_SURELERI = [
    "düzenlendiği tarihten itibaren bir yıl",
    "düzenlendiği tarihten itibaren altı ay",
    "düzenlendiği tarihten itibaren iki yıl",
]

_BILDIRIM_YOLLARI = [
    "elektronik posta ile",
    "posta yoluyla adresime",
    "e-Devlet üzerinden",
    "Kurumunuz kayıt bürosundan elden",
]

_SIKAYET_SURELERI = [
    "yaklaşık üç haftadır", "yaklaşık iki aydır", "bir aydan uzun süredir",
    "geçtiğimiz aydan bu yana", "yaklaşık kırk gündür",
]

_ONCEKI_BASVURU = [
    "durum daha önce telefonla bildirilmiş, sonuç alınamamıştır",
    "konu hakkında daha önce çağrı merkezine başvuru yapılmıştır",
    "aynı husus geçen ay yazılı olarak da iletilmiştir",
]

_DONEMLER = [
    "bahar dönemi", "güz dönemi", "içinde bulunulan öğretim yılı",
    "2026 yılı ilk altı ayı", "önümüzdeki eğitim öğretim dönemi",
]

_GEREKCELER = [
    "hizmetlerin aksamadan yürütülmesi",
    "iş ve işlemlerin zamanında tamamlanması",
    "vatandaş memnuniyetinin artırılması",
    "mevzuatın öngördüğü sürelere uyulması",
    "kaynakların etkin kullanılması",
]


# =============================================================================
# HAVUZ
# =============================================================================


@dataclass
class Kisi:
    ad: str
    soyad: str
    cinsiyet: str

    @property
    def tam_ad(self) -> str:
        """Resmî yazıda soyadı büyük harfle yazılır."""
        return f"{self.ad} {self.soyad.upper()}"


class VarlikHavuzu:
    """Kurgusal değer üreticisi.

    Tekrar sınırı tutar: aynı kişi adı en çok N belgede geçer. Sınır dolunca
    o adı havuzdan çıkarır. Çeşitlilik ölçümü (ADIM 8) buna bakacak.
    """

    def __init__(self, tohum: int, kisi_azami_tekrar: int = 3) -> None:
        self.rnd = random.Random(tohum)
        self.kisi_azami_tekrar = kisi_azami_tekrar
        self._kisi_sayaci: dict[str, int] = {}
        self._kullanilan_ada_parsel: set[tuple[int, int]] = set()

    # -- kişi ----------------------------------------------------------------

    def kisi(self) -> Kisi:
        """Tekrar sınırını aşmayan bir kişi üretir."""
        for _ in range(200):
            if self.rnd.random() < 0.5:
                ad, cins = self.rnd.choice(_ADLAR_ERKEK), "e"
            else:
                ad, cins = self.rnd.choice(_ADLAR_KADIN), "k"
            soyad = self.rnd.choice(_SOYADLAR)
            anahtar = f"{ad} {soyad}"
            if self._kisi_sayaci.get(anahtar, 0) < self.kisi_azami_tekrar:
                self._kisi_sayaci[anahtar] = self._kisi_sayaci.get(anahtar, 0) + 1
                return Kisi(ad, soyad, cins)
        # 1600 kombinasyonda 200 denemede yer bulunamaması pratikte imkânsız;
        # yine de sessizce yanlış veri üretmektense hata verilir.
        raise RuntimeError("Kişi havuzu doldu — tekrar sınırını yükseltin.")

    # -- yer -----------------------------------------------------------------

    def mahalle(self) -> str:
        return self.rnd.choice(_MAHALLELER)

    def adres(self) -> str:
        return (
            f"{self.mahalle()} Mahallesi "
            f"{self.rnd.choice(_SOKAK_ONEKLERI)} {self.rnd.choice(_SOKAK_TURU)} "
            f"No: {self.rnd.randint(1, 120)}/{self.rnd.randint(1, 24)} "
            f"Yenimahalle/ANKARA"
        )

    def ada_parsel(self) -> tuple[int, int]:
        """Benzersiz ada/parsel çifti.

        Aynı taşınmaz iki farklı belgede geçerse, iki belge arasında olmayan
        bir ilişki varmış gibi görünür ve tutarlılık ölçümünü bozar.
        """
        for _ in range(500):
            cift = (self.rnd.randint(10000, 99999), self.rnd.randint(1, 45))
            if cift not in self._kullanilan_ada_parsel:
                self._kullanilan_ada_parsel.add(cift)
                return cift
        raise RuntimeError("Ada/parsel havuzu doldu.")

    # -- metinsel değerler ---------------------------------------------------

    def teslim_sarti(self) -> str:
        return self.rnd.choice(_TESLIM_SARTLARI)

    def gecerlilik(self) -> str:
        return self.rnd.choice(_GECERLILIK_SURELERI)

    def bildirim_yolu(self) -> str:
        return self.rnd.choice(_BILDIRIM_YOLLARI)

    def sikayet_suresi(self) -> str:
        return self.rnd.choice(_SIKAYET_SURELERI)

    def onceki_basvuru(self) -> str:
        return self.rnd.choice(_ONCEKI_BASVURU)

    def donem(self) -> str:
        return self.rnd.choice(_DONEMLER)

    def gerekce(self) -> str:
        return self.rnd.choice(_GEREKCELER)

    def kisi_sayisi(self) -> int:
        """Liste/kadro gibi yerlerde geçen sayı."""
        return self.rnd.choice([12, 18, 24, 35, 47, 68, 94, 112, 142, 186])

    def sayfa_sayisi(self) -> int:
        return self.rnd.choice([1, 1, 2, 2, 3, 4, 6])

    # -- tarih ---------------------------------------------------------------

    def is_gunu(self, baslangic: date, bitis: date) -> date:
        """Hafta içi bir tarih üretir.

        Resmî yazılar hafta sonu üretilmez. Hafta sonuna düşen tarihler
        veri setini gerçek dışı yapar ve gözlemci bunu fark eder.
        """
        gun_sayisi = (bitis - baslangic).days
        for _ in range(100):
            t = baslangic + timedelta(days=self.rnd.randint(0, gun_sayisi))
            if t.weekday() < 5:
                return t
        return baslangic

    def onceki_is_gunu(self, tarih: date, en_az: int = 3, en_cok: int = 45) -> date:
        """Verilen tarihten önce bir iş günü — ilgi yazısının tarihi için.

        İlgi tarihi belgeden ÖNCE olmalı. Sonra olursa `tarih_tutarsiz`
        kusuru olur; o kusur ADIM 4.5'te bilerek enjekte edilir, burada
        kazara üretilmez.
        """
        for _ in range(100):
            t = tarih - timedelta(days=self.rnd.randint(en_az, en_cok))
            if t.weekday() < 5:
                return t
        return tarih - timedelta(days=7)

    # -- yardımcı ------------------------------------------------------------

    def sec(self, dizi):
        return self.rnd.choice(list(dizi))

    def olasilik(self, p: float) -> bool:
        return self.rnd.random() < p

    def karistir(self, dizi: list) -> list:
        d = list(dizi)
        self.rnd.shuffle(d)
        return d

    @property
    def istatistik(self) -> dict:
        return {
            "farkli_kisi": len(self._kisi_sayaci),
            "azami_kisi_tekrari": max(self._kisi_sayaci.values(), default=0),
            "ada_parsel": len(self._kullanilan_ada_parsel),
        }
