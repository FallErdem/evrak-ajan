"""OpenAI uyumlu LLM istemcisi.

Bu dosyanın tek işi var: metin gönder, metin al, token say. Resmî yazının
ne olduğunu, kuralları, şartnameyi bilmez — sadece bir postacıdır.

NEDEN AYRI BİR DOSYA
K-21 kararı: model ve uçnokta yapılandırmadan gelir, koda gömülmez.
Aynı istemci dört yerde çalışır, yalnızca yapılandırma değişir:

    Ollama  : http://localhost:11434/v1
    Gemini  : https://generativelanguage.googleapis.com/v1beta/openai/
    Colab   : https://xxxx.ngrok-free.app/v1
    RunPod  : https://xxxx.runpod.net/v1

Bu sayede ADIM 4'ten Parça 8'e kadar bütün ajanlar aynı istemciyi
kullanabilir; model değişirse tek dosya değişir.

NEDEN DIŞ BAĞIMLILIK YOK
Yalnızca standart kütüphane kullanılıyor (urllib, json). "pip install"
gerektirmiyor. Sebebi pratik: bu betik hem yerelde hem Colab'da hem
RunPod'da çalışacak; her ortamda paket sürümü uğraşmak istemiyoruz.
"""

from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

# -----------------------------------------------------------------------------
# Sabitler
# -----------------------------------------------------------------------------

# Bu HTTP kodlarında yeniden denenir. Gerisinde denenmez:
# 400 (bozuk istek), 401 (anahtar yanlış), 403 (yetki yok), 404 (model yok)
# tekrar denemekle düzelmez; sadece zaman ve para harcar.
YENIDEN_DENENECEK_KODLAR: frozenset[int] = frozenset({408, 409, 429, 500, 502, 503, 504})

# Anahtarın yanlışlıkla ekrana veya kayda düşmesini engellemek için
# hata mesajlarında bu uzunluktan sonrası kesilir.
HATA_METNI_AZAMI = 500


# -----------------------------------------------------------------------------
# Veri kapları
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class TokenBilgisi:
    """Bir çağrının token muhasebesi.

    DÜŞÜNME TOKENLERİ İKİ FARKLI ŞEKİLDE RAPORLANIYOR — ölçülmüş durum:

    (A) OpenAI biçimi: completion_tokens düşünmeyi İÇERİR ve düşünme
        completion_tokens_details.reasoning_tokens alanında ayrıca yazar.

    (B) Google biçimi: düşünme HİÇBİR ALANDA yazmaz, yalnızca
        total_tokens'a eklenir. Ölçtüğümüz gerçek örnek:
            prompt 1726 + completion 70 = 1796  ama  total 3760
            aradaki 1964 token = görünmeyen düşünme

    Bu ayrım maliyet açısından kritik: düşünme çıktı fiyatından
    faturalanır. (B) durumunda completion_tokens'a bakarak hesap yapmak
    maliyeti 25 kat düşük gösterir.

    dusunme_ciktiya_dahil bu iki durumu ayırt eder.
    """

    girdi: int = 0
    cikti: int = 0
    dusunme: int = 0
    toplam: int = 0
    dusunme_ciktiya_dahil: bool = False
    ham: dict = field(default_factory=dict)

    @property
    def gorunur_cikti(self) -> int:
        """Kullanıcının okuduğu metnin token sayısı (düşünme hariç)."""
        if self.dusunme_ciktiya_dahil:
            return max(0, self.cikti - self.dusunme)
        return self.cikti

    @property
    def faturalanan_cikti(self) -> int:
        """Çıktı fiyatından faturalanan token — düşünme DAHİL.

        Maliyet hesabında kullanılacak sayı budur, cikti değil.
        """
        if self.dusunme_ciktiya_dahil:
            return self.cikti
        return self.cikti + self.dusunme

    def __str__(self) -> str:
        return (
            f"girdi {self.girdi} | metin {self.gorunur_cikti} | "
            f"düşünme {self.dusunme} | toplam {self.toplam}"
        )


@dataclass(frozen=True)
class Cevap:
    """Bir çağrının sonucu."""

    metin: str
    token: TokenBilgisi
    sure_ms: float
    deneme_sayisi: int
    model: str
    bitis_sebebi: str | None = None

    @property
    def kesildi_mi(self) -> bool:
        """Çıktı token sınırına takılıp yarıda kesildi mi.

        Kesilmiş metin sessizce kabul edilirse veri setine yarım cümleyle
        biten belgeler girer ve bunu ancak elle okurken fark ederiz.
        """
        return self.bitis_sebebi == "length"


class LLMHatasi(Exception):
    """İstemci kaynaklı hata. Mesajında asla API anahtarı bulunmaz."""


@dataclass(frozen=True)
class AracCagrisi:
    """Modelin çağırmaya karar verdiği tek bir araç."""

    ad: str
    argumanlar: dict
    cagri_id: str


@dataclass(frozen=True)
class AracCevabi:
    """`arac_cagir()` çıktısı.

    `Cevap` sınıfı frozen ve `anlama.py` tarafından kullanılıyor; ona alan
    eklemek yerine ayrı bir sınıf yazıldı (donma kuralı: alan silinmez,
    yeniden adlandırma silme sayılır).

    Model iki şeyden birini yapar:
      - bir ya da birkaç ARAÇ çağırır   -> arac_cagrilari dolu, metin None
      - doğrudan CEVAP verir            -> arac_cagrilari boş, metin dolu

    `ham_mesaj` modelin ürettiği asistan mesajının kendisidir. ReAct
    döngüsünde geçmişe OLDUĞU GİBİ geri konur; yeniden kurulursa
    `tool_call_id` eşleşmesi bozulur ve sağlayıcı 400 döner.
    """

    arac_cagrilari: list[AracCagrisi]
    metin: str | None
    ham_mesaj: dict
    token: TokenBilgisi
    sure_ms: float
    model: str
    bitis_sebebi: str | None = None

    @property
    def arac_cagirdi_mi(self) -> bool:
        return bool(self.arac_cagrilari)


# -----------------------------------------------------------------------------
# Yapılandırma
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Yapilandirma:
    """İstemcinin çalışma ayarları.

    Anahtar burada tutulur ama dosyadan okunur; yapılandırma dosyasının
    kendisinde anahtar YAZMAZ. Sebebi şartname madde 7: depo herkese açık
    olmak zorunda. Koda veya sürüm takibine giren bir anahtar herkese açık
    olur, birileri kullanır, faturayı siz ödersiniz.
    """

    base_url: str
    model: str
    anahtar: str = ""
    zaman_asimi_sn: int = 120
    azami_deneme: int = 3
    ilk_bekleme_sn: float = 1.0
    ek_parametreler: dict = field(default_factory=dict)

    @property
    def uc_nokta(self) -> str:
        """Tam sohbet uçnoktası.

        Google'ın adresi '/' ile biter, Ollama'nınki bitmez. Sondaki eğik
        çizgiyi normalleştirmezsek biri 404 verir ve sebebi saatlerce
        bulunamaz.
        """
        return self.base_url.rstrip("/") + "/chat/completions"


def yapilandirma_yukle(yol: str | Path) -> Yapilandirma:
    """Yapılandırma dosyasını ve ayrı duran anahtar dosyasını okur."""
    yol = Path(yol)
    if not yol.exists():
        raise LLMHatasi(
            f"Yapılandırma dosyası bulunamadı: {yol}\n"
            f"'yapilandirma.ornek.json' dosyasını kopyalayıp doldurun."
        )

    veri = json.loads(yol.read_text(encoding="utf-8"))

    for zorunlu in ("base_url", "model"):
        if not veri.get(zorunlu):
            raise LLMHatasi(f"Yapılandırmada '{zorunlu}' alanı boş veya eksik: {yol}")

    anahtar = _anahtar_oku(veri.get("anahtar_dosyasi"), yol.parent)

    return Yapilandirma(
        base_url=veri["base_url"],
        model=veri["model"],
        anahtar=anahtar,
        zaman_asimi_sn=int(veri.get("zaman_asimi_sn", 120)),
        azami_deneme=int(veri.get("azami_deneme", 3)),
        ilk_bekleme_sn=float(veri.get("ilk_bekleme_sn", 1.0)),
        ek_parametreler=veri.get("ek_parametreler") or {},
    )


def _anahtar_oku(anahtar_dosyasi: str | None, taban: Path) -> str:
    """Anahtarı dosyadan okur. Yoksa boş döner — yerel Ollama anahtar istemez."""
    if not anahtar_dosyasi:
        return ""

    yol = Path(anahtar_dosyasi)
    if not yol.is_absolute():
        yol = (taban / yol).resolve()

    if not yol.exists():
        raise LLMHatasi(
            f"Anahtar dosyası bulunamadı: {yol}\n"
            f"Dosyayı oluşturup içine API anahtarını tek satır olarak yazın."
        )

    anahtar = yol.read_text(encoding="utf-8").strip()
    if not anahtar:
        raise LLMHatasi(
            f"Anahtar dosyası boş: {yol}\n"
            f"API anahtarını aldıktan sonra bu dosyanın içine yapıştırın."
        )
    return anahtar


# -----------------------------------------------------------------------------
# İstemci
# -----------------------------------------------------------------------------


class LLMIstemci:
    """OpenAI uyumlu sohbet uçnoktasına metin ürettirir.

    Kümülatif token sayacı tutar. Bütçe denetimini koşturucu yapar; istemci
    yalnızca sayar. Böylece istemci tek çağrılık işlerde de kullanılabilir.
    """

    def __init__(self, yapilandirma: Yapilandirma) -> None:
        self.y = yapilandirma
        self.toplam_girdi = 0
        self.toplam_metin = 0
        self.toplam_dusunme = 0
        self.toplam_faturalanan_cikti = 0
        self.toplam_genel = 0
        self.cagri_sayisi = 0
        # Kendi imzalı sertifika kullanan tünellerde (ngrok vb.) gerekebilir
        # diye ayrı tutuluyor; varsayılan doğrulama açık.
        self._ssl_baglami = ssl.create_default_context()

    # -- ana giriş noktası ----------------------------------------------------

    def metin_uret(
        self,
        istem: str,
        sistem_istemi: str | None = None,
        sicaklik: float | None = None,
        ek: dict | None = None,          # <-- YENİ,
    ) -> Cevap:
        """İstemi gönderir, üretilen metni döndürür.

        sicaklik None ise istek gövdesine hiç konmaz. Bu bilerek böyle:
        Gemini 3.6 Flash'ta sıcaklık ayarı yok; olmayan bir parametreyi
        göndermek 400 hatasına yol açabilir.
        """
        govde: dict = {
            "model": self.y.model,
            "messages": self._mesajlari_kur(istem, sistem_istemi),
        }
        if sicaklik is not None:
            govde["temperature"] = sicaklik
        govde.update(self.y.ek_parametreler)
        if ek:                            # <-- YENİ
            govde.update(ek)              # çağrı, yapılandırmayı ezer

        baslangic = time.perf_counter()
        veri, deneme = self._gonder(govde)
        sure_ms = (time.perf_counter() - baslangic) * 1000

        metin = self._metni_cikar(veri)
        token = self._token_cikar(veri)
        self._sayaci_guncelle(token)

        return Cevap(
            metin=metin,
            token=token,
            sure_ms=sure_ms,
            deneme_sayisi=deneme,
            model=veri.get("model") or self.y.model,
            bitis_sebebi=self._bitis_sebebi(veri),
        )

    # -- araç çağırma (ReAct döngüsü) -----------------------------------------

    def arac_cagir(
        self,
        mesajlar: list[dict],
        araclar: list[dict],
        sicaklik: float | None = None,
        ek: dict | None = None,
    ) -> AracCevabi:
        """Modele araç tanımlarıyla birlikte mesaj geçmişini gönderir.

        `metin_uret()`'e DOKUNULMADI. Sebep: o metot `content` boş gelince
        hata fırlatıyor ve bu doğru davranış — düz metin isteyen bir çağrıda
        boş içerik sessizce geçilmemeli. Ama model araç çağırdığında
        sağlayıcı tam olarak şunu döndürür:

            message.content    = null
            message.tool_calls = [...]

        Yani araç çağıran her cevap `metin_uret()` ile istisna atardı.
        `anlama.py` mevcut metodu kullanıyor ve Parça 3'te 300 belgede
        ölçüldü; o yolu değiştirmek ölçümleri riske atar.

        `mesajlar` geçmişin TAMAMIDIR, çağıran taraf yönetir. Döngü şöyle
        ilerler:

            mesajlar = [sistem, kullanici]
            cevap = arac_cagir(mesajlar, araclar)
            mesajlar.append(cevap.ham_mesaj)              # modelin hamlesi
            mesajlar.append({"role": "tool", ...})        # aracın gözlemi
            cevap = arac_cagir(mesajlar, araclar)         # model düzeltir

        Sağlayıcı OpenAI istek/cevap biçimini kullanıyor (OpenRouter). Bu
        bir model tercihi değil, zarf biçimi; Qwen de aynı zarfla döner.
        """
        govde: dict = {
            "model": self.y.model,
            "messages": mesajlar,
            "tools": araclar,
        }
        if sicaklik is not None:
            govde["temperature"] = sicaklik
        govde.update(self.y.ek_parametreler)
        if ek:
            govde.update(ek)

        baslangic = time.perf_counter()
        veri, _deneme = self._gonder(govde)
        sure_ms = (time.perf_counter() - baslangic) * 1000

        token = self._token_cikar(veri)
        self._sayaci_guncelle(token)

        secenekler = veri.get("choices") or []
        if not secenekler:
            raise LLMHatasi(f"Cevapta 'choices' yok. Ham cevap: {str(veri)[:300]}")
        mesaj = secenekler[0].get("message") or {}

        cagrilar = [
            AracCagrisi(
                ad=(c.get("function") or {}).get("name") or "",
                argumanlar=_argumanlari_coz(c),
                cagri_id=c.get("id") or "",
            )
            for c in (mesaj.get("tool_calls") or [])
        ]
        icerik = mesaj.get("content")

        # Ne araç ne metin: sessizce boş cevap dönmek yerine açık hata.
        # Sebebi ancak burada anlaşılır; ileride bulgu yokluğu "temiz belge"
        # gibi okunur ve kimse fark etmez.
        if not cagrilar and not icerik:
            raise LLMHatasi(
                f"Model ne araç çağırdı ne metin üretti "
                f"(finish_reason={secenekler[0].get('finish_reason')}). "
                f"Ham mesaj: {str(mesaj)[:300]}"
            )

        return AracCevabi(
            arac_cagrilari=cagrilar,
            metin=icerik.strip() if isinstance(icerik, str) and icerik.strip() else None,
            ham_mesaj=mesaj,
            token=token,
            sure_ms=sure_ms,
            model=veri.get("model") or self.y.model,
            bitis_sebebi=secenekler[0].get("finish_reason"),
        )

    # -- kümülatif muhasebe ---------------------------------------------------

    @property
    def toplam_token(self) -> int:
        """Bu istemci örneğinin harcadığı toplam token.

        Sağlayıcının bildirdiği total_tokens toplanıyor, girdi+çıktı DEĞİL.
        Sebebi ölçülmüş: Google düşünme tokenlerini yalnızca total_tokens'a
        ekliyor. girdi+çıktı toplanırsa bir çağrının 3760 tokeni 1796
        görünür ve bütçe sınırı işe yaramaz hâle gelir.
        """
        return self.toplam_genel

    def ozet(self) -> str:
        return (
            f"{self.cagri_sayisi} çağrı | girdi {self.toplam_girdi} | "
            f"metin {self.toplam_metin} | düşünme {self.toplam_dusunme} | "
            f"toplam {self.toplam_genel}"
            f"\n           faturalanan çıktı (düşünme dahil): "
            f"{self.toplam_faturalanan_cikti}"
        )

    def _sayaci_guncelle(self, token: TokenBilgisi) -> None:
        self.toplam_girdi += token.girdi
        self.toplam_metin += token.gorunur_cikti
        self.toplam_dusunme += token.dusunme
        self.toplam_faturalanan_cikti += token.faturalanan_cikti
        self.toplam_genel += token.toplam
        self.cagri_sayisi += 1

    # -- HTTP -----------------------------------------------------------------

    def _gonder(self, govde: dict) -> tuple[dict, int]:
        """İsteği gönderir; geçici hatalarda üstel geri çekilmeyle tekrar dener.

        Geri çekilme: 1 sn, 2 sn, 4 sn... Sunucu Retry-After başlığı
        gönderirse ona uyulur — kendi tahminimizden daha doğrudur.
        """
        ham = json.dumps(govde, ensure_ascii=False).encode("utf-8")
        basliklar = {"Content-Type": "application/json"}
        if self.y.anahtar:
            basliklar["Authorization"] = f"Bearer {self.y.anahtar}"

        son_hata: Exception | None = None

        for deneme in range(1, self.y.azami_deneme + 1):
            istek = urllib.request.Request(
                self.y.uc_nokta, data=ham, headers=basliklar, method="POST"
            )
            try:
                with urllib.request.urlopen(
                    istek, timeout=self.y.zaman_asimi_sn, context=self._ssl_baglami
                ) as cevap:
                    return json.loads(cevap.read().decode("utf-8")), deneme

            except urllib.error.HTTPError as hata:
                govde_metni = self._hata_govdesi(hata)
                if hata.code not in YENIDEN_DENENECEK_KODLAR:
                    raise LLMHatasi(
                        f"HTTP {hata.code} — tekrar denenmedi. Sunucu: {govde_metni}"
                    ) from None
                son_hata = LLMHatasi(f"HTTP {hata.code}: {govde_metni}")
                bekleme = self._bekleme_suresi(deneme, hata)

            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as hata:
                son_hata = LLMHatasi(f"{type(hata).__name__}: {hata}")
                bekleme = self._bekleme_suresi(deneme, None)

            if deneme < self.y.azami_deneme:
                print(f"      ! {son_hata} — {bekleme:.1f} sn sonra tekrar denenecek")
                time.sleep(bekleme)

        raise LLMHatasi(
            f"{self.y.azami_deneme} denemede başarısız. Son hata: {son_hata}"
        )

    def _bekleme_suresi(self, deneme: int, hata: urllib.error.HTTPError | None) -> float:
        """Üstel geri çekilme; sunucunun Retry-After başlığı önceliklidir."""
        if hata is not None:
            basligi = hata.headers.get("Retry-After") if hata.headers else None
            if basligi:
                try:
                    return max(1.0, float(basligi))
                except ValueError:
                    pass
        return self.y.ilk_bekleme_sn * (2 ** (deneme - 1))

    @staticmethod
    def _hata_govdesi(hata: urllib.error.HTTPError) -> str:
        """Sunucunun hata açıklamasını okur, kısaltır.

        Kısaltma önemli: bazı sunucular hatada isteğin tamamını geri
        yansıtır, bu da 1800 tokenlik istemin ekrana dökülmesi demektir.
        """
        try:
            metin = hata.read().decode("utf-8", errors="replace")
        except Exception:
            metin = str(hata)
        metin = " ".join(metin.split())
        return metin[:HATA_METNI_AZAMI]

    # -- cevap ayrıştırma -----------------------------------------------------

    @staticmethod
    def _mesajlari_kur(istem: str, sistem_istemi: str | None) -> list[dict]:
        mesajlar: list[dict] = []
        if sistem_istemi:
            mesajlar.append({"role": "system", "content": sistem_istemi})
        mesajlar.append({"role": "user", "content": istem})
        return mesajlar

    @staticmethod
    def _metni_cikar(veri: dict) -> str:
        """choices[0].message.content — yoksa açık hata verir.

        Boş içerik sessizce geçilmiyor: güvenlik filtresi devreye girdiğinde
        veya model bir sebeple cevap üretmediğinde içerik None gelir. Bunu
        boş metin sayarsak veri setine boş belgeler girer ve sebebi
        anlaşılmaz.
        """
        secenekler = veri.get("choices") or []
        if not secenekler:
            raise LLMHatasi(f"Cevapta 'choices' yok. Ham cevap: {str(veri)[:300]}")

        icerik = (secenekler[0].get("message") or {}).get("content")
        if icerik is None:
            sebep = secenekler[0].get("finish_reason")
            raise LLMHatasi(
                f"Model içerik üretmedi (finish_reason={sebep}). "
                f"Güvenlik filtresi veya boş cevap olabilir."
            )
        return icerik.strip()

    @staticmethod
    def _bitis_sebebi(veri: dict) -> str | None:
        secenekler = veri.get("choices") or []
        return secenekler[0].get("finish_reason") if secenekler else None

    @staticmethod
    def _token_cikar(veri: dict) -> TokenBilgisi:
        """usage alanını okur; iki farklı raporlama biçimini de kavrar.

        ÖNCE açık bir düşünme alanı aranır (OpenAI biçimi). Bulunamazsa
        aritmetikten türetilir: total - prompt - completion sıfırdan büyükse
        aradaki fark düşünmedir (Google biçimi).

        Türetme sağlam bir yöntem: sağlayıcı düşünmeyi gizlese bile
        total_tokens'a eklemek zorunda, çünkü faturayı ona göre kesiyor.

        HAM VERİ KORUNUYOR: alan adları sağlayıcıdan sağlayıcıya değişiyor.
        Ham sözlük kayda düştüğü için beklenmedik bir biçimle karşılaşınca
        bilgi kaybolmuyor.
        """
        kullanim = veri.get("usage") or {}
        detay = kullanim.get("completion_tokens_details") or {}

        girdi = int(kullanim.get("prompt_tokens") or 0)
        cikti = int(kullanim.get("completion_tokens") or 0)
        toplam = int(kullanim.get("total_tokens") or (girdi + cikti))

        # (A) Açık alan var mı?
        dusunme = 0
        dusunme_dahil = False
        for kaynak in (detay, kullanim):
            for aday in ("reasoning_tokens", "thoughts_token_count",
                         "thinking_tokens", "reasoning_token_count"):
                deger = kaynak.get(aday)
                if isinstance(deger, int) and deger > 0:
                    dusunme, dusunme_dahil = deger, True
                    break
            if dusunme:
                break

        # (B) Yoksa toplamdan türet
        if not dusunme:
            fark = toplam - girdi - cikti
            if fark > 0:
                dusunme, dusunme_dahil = fark, False

        return TokenBilgisi(
            girdi=girdi,
            cikti=cikti,
            dusunme=dusunme,
            toplam=toplam,
            dusunme_ciktiya_dahil=dusunme_dahil,
            ham=kullanim,
        )


# -----------------------------------------------------------------------------
# Kolaylık
# -----------------------------------------------------------------------------


def _argumanlari_coz(cagri: dict) -> dict:
    """tool_calls[i].function.arguments -> dict.

    Sağlayıcılar bu alanı iki farklı biçimde döndürüyor:
      - JSON DİZESİ  '{"alinti": "..."}'   (OpenAI ve OpenRouter'ın çoğu)
      - hazır SÖZLÜK {"alinti": "..."}     (bazı sağlayıcılar)

    İkisi de karşılanıyor. Dize bozuksa istisna atılmıyor: model geçersiz
    JSON üretebilir ve bu bir MODEL HATASIDIR, istemci hatası değil.
    Döngüyü çökertmek yerine boş sözlük dönüyor; çağıran taraf aracı
    çalıştıramaz ve modele "argümanların okunamadı" diye geri bildirir.
    """
    ham = (cagri.get("function") or {}).get("arguments")
    if isinstance(ham, dict):
        return ham
    if not isinstance(ham, str) or not ham.strip():
        return {}
    try:
        cozulen = json.loads(ham)
    except (json.JSONDecodeError, ValueError):
        return {}
    return cozulen if isinstance(cozulen, dict) else {}


def istemci_olustur(yapilandirma_yolu: str | Path) -> LLMIstemci:
    """Yapılandırmayı okuyup hazır istemci döndürür."""
    return LLMIstemci(yapilandirma_yukle(yapilandirma_yolu))
