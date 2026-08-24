"""Özetleyici — boru hattının 5. adımı. Belgeyi tek cümlelik talep ve kısa
özete indirir.

src/ altında duran, İÇE AKTARILAN modüldür.

    from ozetleyici import Ozetleyici
    ozetleyici = Ozetleyici(istemci)
    sonuc = ozetleyici.calistir(dosya)    # dosya.icerik.talep ve .ozet dolar

AJAN DEĞİL, LLM ÇAĞRISIDIR
--------------------------
Karar vermiyor, araç kullanmıyor, döngüye girmiyor. Bir kez çağrılır ve
biter. Sistemdeki iki ajan Denetçi ve Yazar'dır; bu ayrım raporda ve
sunumda korunmalıdır — LLM kullanmak ajan olmak değildir.

NEDEN ÇIKTI DOĞRULANIYOR
------------------------
Özet, memurun BELGEYİ OKUMAK YERİNE okuyacağı metindir. Model oraya
belgede olmayan bir tarih ya da tutar koyarsa memur ona güvenip işlem
yapar ve kimse fark etmez — karşılaştıracağı bir cevap anahtarı yoktur.

    belgede    "idari para cezasına yönelik itirazım ... reddedilmiştir"
    model yazsa "5.000 TL cezaya 09.03.2026 tarihinde itiraz edilmiş"

İkincisi daha bilgilendirici görünür ama o tutar ve tarih belgede yoktur.
`sayisal_dogrula()` bunu yakalar: özetteki her sayı ve tarih gövdede
aranır, bulunamayanlar işaretlenir.

SINIR — RAPORA GİRECEK
----------------------
Doğrulama SAYISAL uydurmayı yakalar, anlamsal çarpıtmayı yakalamaz:

    belgede  "talep reddedilmiştir"
    özette   "talep kabul edilmiştir"     <- hiç sayı yok, denetim geçer

Bunu yakalamak için ya cevap anahtarı ya ikinci bir model gerekir; bu
çalışmada ikisi de yok. Özetleme kalitesi (akıcılık, kapsayıcılık)
ölçülmemiştir.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from metin import katla
from veri_yapisi import Dosya

# İKİ AYRI SINIR VAR
# ------------------
# ŞEMA sınırı modelden istediğimiz uzunluk; ŞEMA sınırı `veri_yapisi.Icerik`
# sınırından DAR olabilir, geniş olamaz.
#
#     Icerik.talep   azami  500      <- Pydantic'in kabul ettiği tavan
#     Icerik.ozet    azami 1500
#
# ÖLÇÜLDÜ 2026-08-23, belge_030: şema sınırı 500/1500 iken model 150
# karakter talep ve 329 karakter özet üretti. Gövde 530 karakterdi, yani
# sıkıştırma neredeyse yoktu. Sınırlar daraltıldı.
#
# Kırpma ZORUNLU: Pydantic sınırı bir karakter aşan metni ValidationError
# ile reddediyor ve alan sessizce boş kalıyor. Parça 3'te aynı hata sekiz
# belgeyi kaybettirmişti.
TALEP_SINIRI = 200          # şemaya konan sınır  (Icerik tavanı 500)
OZET_SINIRI = 450           # şemaya konan sınır  (Icerik tavanı 1500)

# Modele gösterilecek gövde. Veri setinin tamamı tek sayfa; bu sınır
# pratikte devreye girmiyor ama uzun bir belge istemi şişirmesin.
GOVDE_SINIRI = 4000

SISTEM_ISTEMI = (
    "Sen Türk kamu kurumlarında gelen evrakı özetleyen bir memursun. "
    "Görevin, belgeyi okuyacak olan görevlinin belgenin tamamını okumadan "
    "ne yapması gerektiğini anlamasını sağlamak.\n\n"
    "KURALLAR:\n"
    "1. YALNIZCA belgede yazanı özetle. Çıkarım yapma, yorum ekleme.\n"
    "2. Belgede geçmeyen hiçbir SAYI, TARİH, TUTAR veya İSİM yazma. "
    "Emin değilsen o ayrıntıyı hiç yazma.\n"
    "3. Resmî ve yalın bir dil kullan. 'Sanırım', 'muhtemelen' gibi "
    "ifadeler kullanma.\n"
    "4. Talep TEK CÜMLE, en fazla 20 kelime. Belgenin ne İSTEDİĞİNİ "
    "söylesin.\n"
    "5. Özet EN FAZLA İKİ CÜMLE: kim, ne istiyor, hangi gerekçeyle.\n"
    "6. Belgenin kendi SAYISINI ve TARİHİNİ özete yazma; bu alanlar "
    "arayüzde zaten ayrıca gösteriliyor ve tekrar etmek özeti gereksiz "
    "uzatır. İlgi tutulan bir yazıya atıf gerekiyorsa 'ilgi yazı' de, "
    "numarasını ve tarihini yazma.\n"
    "7. Kısa yaz. Özet, belgeyi okumaya alternatif değil; görevlinin ne "
    "yapması gerektiğini bir bakışta anlamasını sağlayan not."
)


def sema() -> dict:
    """response_format şeması.

    `anlama.py` deseni birebir izleniyor: strict=True ve
    additionalProperties=False. Ölçüldü (Parça 3): sağlayıcı yalnızca bu
    biçimde şemayı güvenilir biçimde zorluyor.

    maxLength değerleri `veri_yapisi.Icerik` ile aynı; modelden şemanın
    kabul etmeyeceği uzunlukta metin istenmiyor.
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "belge_ozeti",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "talep": {
                        "type": "string",
                        "maxLength": TALEP_SINIRI,
                        "description": (
                            "Belge ne istiyor? TEK CÜMLE, en fazla 20 "
                            "kelime. Sayı ve tarih yazma. "
                            "Örnek: 'Yurtdışı denklik başvurusunun "
                            "sonuçlandırılması.'"
                        ),
                    },
                    "ozet": {
                        "type": "string",
                        "maxLength": OZET_SINIRI,
                        "description": (
                            "EN FAZLA İKİ CÜMLE: kim, ne istiyor, hangi "
                            "gerekçeyle. Belgenin sayısını ve tarihini "
                            "yazma. Belgede geçmeyen ayrıntı yazma."
                        ),
                    },
                },
                "required": ["talep", "ozet"],
                "additionalProperties": False,
            },
        },
    }


# =============================================================================
# Sayısal doğrulama
# =============================================================================

# Özette geçen sayısal ifadeler. Tarih, tutar, kod, adet — hepsi rakam
# içerir ve hepsi belgede DOĞRULANABİLİR olmalıdır.
_SAYISAL = re.compile(r"\d[\d.,/:-]*\d|\d")

# Doğrulamadan muaf tutulanlar: metnin kendi sıra numaraları ve tek
# haneli sayılar. Tek hane ("üç birim" yerine "3 birim") uydurma sinyali
# değil, dil tercihidir ve gövdede yazıyla geçiyor olabilir.
MUAF_UZUNLUK = 1


@dataclass
class OzetSonucu:
    """Özetleyici çıktısı."""

    talep: str | None = None
    ozet: str | None = None
    uyarilar: list[str] = field(default_factory=list)
    # Sayısal doğrulama izi — ölçümde ve raporda kullanılır.
    bulunan_sayilar: list[str] = field(default_factory=list)
    dogrulanmayan: list[str] = field(default_factory=list)
    sure_ms: float = 0.0
    token: int = 0
    model: str | None = None

    @property
    def basarili(self) -> bool:
        return bool(self.talep and self.ozet)

    @property
    def ozet_temiz_mi(self) -> bool:
        """Özette belgede bulunmayan sayısal değer var mı."""
        return not self.dogrulanmayan


def sayisal_dogrula(ozet_metni: str, kaynak: str) -> tuple[list[str], list[str]]:
    """Özetteki sayısal değerleri kaynakta arar.

    Döner: (bulunan_tum_sayilar, dogrulanmayanlar)

    İKİ AŞAMALI KARŞILAŞTIRMA
    -------------------------
    1. HAM (katlanmış) alt dize araması. "2026" ifadesi kaynaktaki
       "05.03.2026" içinde geçtiği için kabul edilir — özet yalnızca yılı
       yazmış olabilir ve bu uydurma değildir.
    2. Bulunamazsa, noktalama düşürülüp kaynağın SAYI BELİRTEÇLERİYLE
       TEK TEK karşılaştırılır. Model tarihi "09/03/2026" yazarken belge
       "09.03.2026" yazmış olabilir; biçim farkı uydurma sanılmamalı.

    NEDEN BELİRTEÇ BAZLI, TOPLU DEĞİL
    ---------------------------------
    İlk sürüm kaynağın BÜTÜN rakamlarını tek dizeye birleştirip alt dize
    arıyordu. ÖLÇÜLDÜ 2026-08-23, sınır aşan sahte eşleşme üretiyordu:

        kaynakta  "1.250,00"  ->  "125000"
        özette    "5.000"     ->  "5000"
        "5000" in "125000"    ->  TRUE    <- uydurma tutar DOĞRULANMIŞ sayıldı

    Uydurma bir değer, alakasız bir sayının ortasında tesadüfen bulunuyor.
    Artık kaynağın her sayısı ayrı bir belirteç ve karşılaştırma TAM
    EŞLEŞME. Böyle bir doğrulayıcı, yakalayamadığı şeyi sessizce
    "doğrulandı" diye geçmez.
    """
    if not ozet_metni or not kaynak:
        return [], []

    k = katla(kaynak)
    kaynak_belirtecleri = {
        re.sub(r"\D", "", t) for t in _SAYISAL.findall(kaynak)
    }
    kaynak_belirtecleri.discard("")

    bulunan: list[str] = []
    dogrulanmayan: list[str] = []
    for eslesme in _SAYISAL.finditer(ozet_metni):
        sayi = eslesme.group(0)
        sade = re.sub(r"\D", "", sayi)
        if len(sade) <= MUAF_UZUNLUK:
            continue
        bulunan.append(sayi)
        if katla(sayi) in k:                 # 1. ham eşleşme
            continue
        if sade in kaynak_belirtecleri:      # 2. biçimden bağımsız tam eşleşme
            continue
        dogrulanmayan.append(sayi)
    return bulunan, dogrulanmayan


# =============================================================================
# Özetleyici
# =============================================================================


class Ozetleyici:
    """Boru hattının 5. adımı. Tek LLM çağrısı."""

    def __init__(self, istemci) -> None:
        self.istemci = istemci

    def istem_kur(self, dosya: Dosya) -> str:
        """Modele gidecek metin.

        GÖVDE VERİLİYOR, HAM METİN DEĞİL. Ham metin imza bloğunu, ek
        satırını, doğrulama kodunu ve altbilgiyi taşır; bunlar özete
        sızarsa memur kurumun telefonunu vatandaşın telefonu sanır.
        Aynı gerekçeyle `dipnot.py` ayrımı yapılmıştı.

        Üstveri alanları AYRICA veriliyor: gövde "İlgi'de kayıtlı yazı"
        diyor ama hangi yazı olduğu ilgi satırındadır.
        """
        tur = dosya.deger_al("siniflandirma.belge_turu") or "bilinmiyor"
        muhatap = dosya.deger_al("ustveri.muhatap.idare") or ""
        ilgiler = getattr(dosya.ustveri, "ilgi", None) or []
        ilgi_metni = "; ".join(
            str(getattr(i, "ham", "")) for i in ilgiler if getattr(i, "ham", None)
        )
        govde = (dosya.metin or "").strip()[:GOVDE_SINIRI]

        satirlar = [
            f"Belge türü: {tur}",
            f"Tarih: {dosya.deger_al('ustveri.tarih')}",
            f"Konu: {dosya.deger_al('ustveri.konu')}",
        ]
        if muhatap:
            satirlar.append(f"Muhatap: {muhatap}")
        if ilgi_metni:
            satirlar.append(f"İlgi: {ilgi_metni}")
        satirlar.append("")
        satirlar.append("GÖVDE:")
        satirlar.append(govde or "(gövde okunamadı)")
        satirlar.append("")
        satirlar.append("Bu belgenin talebini ve özetini çıkar.")
        return "\n".join(satirlar)

    def calistir(self, dosya: Dosya, yaz: bool = True) -> OzetSonucu:
        """Tek çağrı yapar, çıktıyı doğrular, dosyaya yazar.

        DOĞRULAMA GEÇMEZSE ALAN YİNE YAZILIR
        ------------------------------------
        Uydurma sayı bulunması özeti çöpe atmayı gerektirmez; özetin
        geri kalanı kullanışlı olabilir. Ama `dogrulanmayan` listesi
        sonuçta taşınır ve ölçümde raporlanır. Arayüz istenirse o özeti
        "doğrulanmadı" rozetiyle gösterebilir.

        Sessizce kabul etmiyoruz, sessizce atmıyoruz — işaretliyoruz.
        """
        sonuc = OzetSonucu()
        govde = (dosya.metin or "").strip()
        if not govde:
            sonuc.uyarilar.append("Gövde boş, özet üretilmedi")
            return sonuc

        try:
            cevap = self.istemci.metin_uret(
                istem=self.istem_kur(dosya),
                sistem_istemi=SISTEM_ISTEMI,
                ek={"response_format": sema()},
            )
        except Exception as e:  # noqa: BLE001
            sonuc.uyarilar.append(f"LLM çağrısı başarısız: {type(e).__name__}: {e}")
            return sonuc

        sonuc.sure_ms = getattr(cevap, "sure_ms", 0.0)
        sonuc.token = getattr(getattr(cevap, "token", None), "toplam", 0)
        sonuc.model = getattr(cevap, "model", None)

        if getattr(cevap, "kesildi_mi", False):
            # Yarım JSON ayrıştırılamaz; ayrıştırılsa bile eksik metin
            # sessizce özet diye kabul edilmiş olur.
            sonuc.uyarilar.append("Model çıktısı token sınırında kesildi")
            return sonuc

        try:
            veri = json.loads(cevap.metin)
        except (json.JSONDecodeError, TypeError) as e:
            sonuc.uyarilar.append(f"Model çıktısı JSON değil: {e}")
            return sonuc

        talep = (veri.get("talep") or "").strip() or None
        ozet = (veri.get("ozet") or "").strip() or None

        # Şema sınırlarını aşan metin Pydantic'te ValidationError atar ve
        # alan sessizce boş kalır. Burada kırpılıp uyarı bırakılıyor.
        if talep and len(talep) > TALEP_SINIRI:
            talep = talep[: TALEP_SINIRI - 1].rstrip() + "…"
            sonuc.uyarilar.append("talep sınırı aştı, kırpıldı")
        if ozet and len(ozet) > OZET_SINIRI:
            ozet = ozet[: OZET_SINIRI - 1].rstrip() + "…"
            sonuc.uyarilar.append("ozet sınırı aştı, kırpıldı")

        sonuc.talep, sonuc.ozet = talep, ozet

        # Sayısal doğrulama: talep ve özetin ikisi birden denetlenir.
        # Kaynak gövde + üstveri: tarih ve sayı gövdede değil üstveride.
        kaynak = "\n".join(
            str(x) for x in (
                govde,
                dosya.deger_al("ustveri.sayi"),
                dosya.deger_al("ustveri.tarih"),
                dosya.deger_al("ustveri.konu"),
                *[getattr(i, "ham", "") for i in (getattr(dosya.ustveri, "ilgi", None) or [])],
            ) if x
        )
        bulunan, dogrulanmayan = sayisal_dogrula(
            " ".join(x for x in (talep, ozet) if x), kaynak
        )
        sonuc.bulunan_sayilar = bulunan
        sonuc.dogrulanmayan = dogrulanmayan
        if dogrulanmayan:
            sonuc.uyarilar.append(
                "Özette belgede bulunmayan sayısal değer(ler): "
                + ", ".join(dogrulanmayan)
            )

        if yaz:
            dosya.icerik.talep = talep
            dosya.icerik.ozet = ozet
        return sonuc
