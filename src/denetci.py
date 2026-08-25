"""Denetçi — AJAN 1. Gelen evrakta ne eksik olduğunu bulur.

src/ altında duran, İÇE AKTARILAN modüldür.

    from denetci import Denetci
    denetci = Denetci()
    sonuc = denetci.calistir(dosya)      # dosya.icerik.eksik_alanlar dolar

ÜÇ KATMAN — DEVIR_2026-08-21-aksam.md §4.2
------------------------------------------
    Katman 1  şema kontrolü    zorunlu alan boş mu        deterministik
    Katman 2  kural motoru     kurallar.json              araç      <- BU DOSYA
    Katman 3  kural dışı       LLM, belirsizlik           model

Şu an YALNIZCA KATMAN 2 bağlıdır. Katman 1 ve 3 aynı sınıfa eklenecek;
`EksikAlan.katman` alanı hangisinden geldiğini taşıdığı için ölçüm
karışmaz.

NEDEN BU DOSYA GEREKLİ — motor tek başına yetmiyor
--------------------------------------------------
Kural motoru `LinterBulgusu` üretir. Arayüz `EksikAlan` bekler
(`api_sozlesmesi.md` §5.6.5, `Icerik.eksik_alanlar`). İkisi farklı
sınıflardır ve aralarındaki çeviri yapılmazsa motorun bütün bulguları —
19 kural, 5 kusur türü — ekrana hiç ulaşmaz.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from kural_motoru import KuralMotoru, MotorSonucu
from denetci_araclar import (
    KATEGORILER,
    arac_calistir,
    belgede_cumle_ara,
    tum_arac_semasi,
)
from veri_yapisi import (
    Dosya,
    EksikAlan,
    EksikKatman,
    MevzuatOnerisi,
    Onem,
    kapsama_girer_mi,
)

# `aciklama` şemada 300 karakterle sınırlı (veri_yapisi.EksikAlan).
ACIKLAMA_SINIRI = 300

# =============================================================================
# GELEN TARAFTA BLOKE ETMEYEN KURALLAR
# =============================================================================
#
# Ayrım şu: bulgu gelen belgeyi İŞLENEMEZ mi kılıyor, yoksa yalnızca o
# belgenin kendi kusurunu mu bildiriyor?
#
#   T-01  tarih yok        -> cevabın "ilgi"si tarih ister      HATA kalır
#   IM-01 imza yok         -> imzasız belge hukuken geçersiz    HATA kalır
#   M-01  muhatap belirsiz -> bize mi geldiği bilinmiyor        HATA kalır
#
#   I-09  gelen belgenin ilgi atfı kopuk
#   ME-02 gelen belgenin kapanışı yanlış (arz/rica)
#
# Son ikisi BİZİM ÇIKTIMIZI ETKİLEMİYOR. Bizim ilgimiz gelen belgenin
# sayı/tarihini kullanıyor, onun kendi ilgi satırını değil; bizim
# kapanışımızı `yazar.yonu_belirle` kendi hiyerarşi hesabıyla kuruyor.
# Gönderen "rica" yerine "arz" yazmışsa bu ONUN kusuru — bizim cevabımızı
# üretmeye engel değil ve memuru meşgul etmesi için sebep yok.
#
# ÖNEMİ KURAL DOSYASINDA DEĞİL BURADA DÜŞÜRÜYORUZ
# -----------------------------------------------
# `kural_ekleri.json`da `onem` alanını global değiştirmek ME-02'yi GİDEN
# tarafta da susturur ve Yazar'ın üslup döngüsünü tetikleyen kurallardan
# birini öldürür (30 belgede 1 kez tetikliyor). Denetçi motoru yalnızca
# `hedef="gelen"` ile koşturuyor, Yazar `hedef="giden"` ile ayrı çağırıyor;
# düşürmeyi buraya koymak yapı gereği hedefe özgü oluyor.
#
# KATMAN 3'TE KARŞILIĞI VAR VE DÜŞÜRÜLMEDİ
# -----------------------------------------
# `denetci_araclar.KATEGORILER["kapanis_yonu_yanlis"]` aynı kusuru bir
# katman yukarıdan, `onem: "hata"` olarak bildiriyor. Katman 3 şu an
# varsayılan olarak KAPALI (`Denetci(istemci=None)`), bu yüzden çakışma
# bugün yaşanmıyor. Katman 3 açılırsa aşağıdaki düşürme etkisiz kalır ve
# aynı belge yine bloke olur — o kategori de uyarıya çekilmelidir.
#
# DEĞİŞİKLİKTEN SONRA ZORUNLU: `python araclar\guven_kapisi_dogrula.py`
# (bedava, LLM yok). SIZAN HATA 0 KALMALI.
GELEN_BLOKE_ETMEYEN: frozenset[str] = frozenset({"I-09", "ME-02"})

# ReAct döngüsünün tur sınırı. Model en fazla 3 araç çağırıp 4. turda
# sonuç bildirebilir. Sınırsız döngü hem krediyi yakar hem sonsuza gider;
# Yazar'ın üslup döngüsü de aynı gerekçeyle 2 turla sınırlı.
AZAMI_TUR = 4

# Modele gösterilecek gövde uzunluğu. Belgelerin tamamı tek sayfa
# (kota.json), bu sınır pratikte hiç devreye girmiyor ama uzun bir belge
# gelirse istemi şişirmesin.
GOVDE_SINIRI = 4000

# =============================================================================
# Mevzuat — dayanak kısaltmalarının karşılığı
# =============================================================================
#
# KAYNAK: belgeler/kural_listesi.md, "Dayanak sütunu" başlığı. Birebir:
#
#     Y = Resmî Yazışmalarda Uygulanacak Usul ve Esaslar Hakkında Yönetmelik
#         (10.06.2020 tarihli ve 31151 sayılı RG) — 60 kural
#     K = Aynı Yönetmeliğin Kılavuzu (Cumhurbaşkanlığı) — 44 kural
#
# Bu adlar HAFIZADAN YAZILMADI, kural listesinin kendi açıklamasından
# alındı. Resmî bir ad ya da tarih değiştirilecekse kaynağa bakılmalıdır.
MEVZUAT_ADLARI: dict[str, str] = {
    "Y": "Resmî Yazışmalarda Uygulanacak Usul ve Esaslar Hakkında Yönetmelik",
    "K": "Resmî Yazışmalarda Uygulanacak Usul ve Esaslar Hakkında "
         "Yönetmeliğin Kılavuzu",
}

# "Y 17/1" · "K 13.6.9.2" · "Y 16/12-a" biçimlerinin tamamını karşılar.
# ÖLÇÜLDÜ 2026-08-23: 104 kuralın 104'ünde eşleşiyor, ayrıştırılamayan yok.
_DAYANAK = re.compile(r"^(Y|K)\s+(\S.*)$")


def dayanak_coz(dayanak: str | None) -> tuple[str, str] | None:
    """'Y 17/1' -> (mevzuat adı, '17/1'). Çözülemezse None.

    Çözülemeyen dayanak SESSİZCE bir ada eşlenmez. Yanlış mevzuat adı
    göstermek, hiç göstermemekten kötüdür: okuyan memur ona güvenip işlem
    yapar.
    """
    if not dayanak:
        return None
    m = _DAYANAK.match(dayanak.strip())
    if not m:
        return None
    ad = MEVZUAT_ADLARI.get(m.group(1))
    if not ad:
        return None
    return ad, m.group(2)


@dataclass
class DenetimSonucu:
    """Denetçi'nin çıktısı.

    `eksikler` doğrudan `dosya.icerik.eksik_alanlar`a yazılır; `motor`
    ölçüm ve tanı için saklanır (kaç kural denetlendi, kaç tanesi neden
    atlandı).
    """

    eksikler: list[EksikAlan] = field(default_factory=list)
    mevzuat: list[MevzuatOnerisi] = field(default_factory=list)
    motor: MotorSonucu | None = None
    # Katman 3 çalıştıysa ajan döngüsünün adım adım izi. Sunumda ve
    # ölçümde gösterilir; boşsa Katman 3 hiç koşmamıştır.
    ajan_izi: list[str] = field(default_factory=list)
    ajan_elenen: list[str] = field(default_factory=list)

    @property
    def hata_sayisi(self) -> int:
        return sum(1 for e in self.eksikler if e.onem == Onem.HATA)

    @property
    def gosterilecek_mevzuat(self) -> list[MevzuatOnerisi]:
        """`dogrulandi=false` olan öneri arayüzde gösterilmez — sözleşme §5.6.5."""
        return [m for m in self.mevzuat if m.dogrulandi]

    @property
    def talep_edilebilir_sayisi(self) -> int:
        """Şartname 6.4.2 (5): karşı taraftan istenebilecek eksik sayısı."""
        return sum(1 for e in self.eksikler if e.talep_edilebilir)

    @property
    def ozet(self) -> str:
        r = self.motor.rapor if self.motor else None
        return (
            f"{len(self.eksikler)} eksik ({self.hata_sayisi} hata), "
            f"{len(self.gosterilecek_mevzuat)}/{len(self.mevzuat)} mevzuat önerisi, "
            f"{r.denetlenen_kural_sayisi if r else 0} kural denetlendi, "
            f"{r.atlanan_kural_sayisi if r else 0} atlandı"
        )


class Denetci:
    """AJAN 1 — eksiklik tespiti."""

    def __init__(
        self,
        kural_dosyasi: Path | str | None = None,
        istemci=None,
    ) -> None:
        """`istemci` verilmezse Katman 3 KOŞMAZ.

        Varsayılan olarak kapalı olmasının sebebi: Katman 1 ve 2 tamamen
        deterministik ve ölçülmüş durumda. LLM çağrısı krediyi harcar ve
        ölçüm betiklerinin çoğu ona ihtiyaç duymaz. Katman 3 açıkça
        istendiğinde devreye girer.
        """
        self.motor = KuralMotoru(kural_dosyasi)
        self.istemci = istemci
        # Kural kayıtlarına kimlikten erişim: EksikAlan'ın `talep_edilebilir`
        # ve `soru` alanları kuralın kendisinde yazılı. Motorda gizli eşleme
        # YOK — çeviri kuralın içinde duruyor ve okuyan görüyor.
        self._kural = {k["id"]: k for k in self.motor.tum_kurallar}

    # -- çeviri ---------------------------------------------------------------

    def _eksige_cevir(self, bulgu) -> EksikAlan:
        """LinterBulgusu -> EksikAlan.

        `aciklama` sistemin kendine notudur: kuralın ne dediği, artı varsa
        belgeden alınan kanıt. `soru` ise karşı tarafa gidecek cümledir ve
        BURADA ÜRETİLMEZ — kuralın kaydından okunur. İkisini karıştırmak,
        vatandaşa yönetmelik maddesi okutmak olur.
        """
        kural = self._kural.get(bulgu.kural_id, {})

        aciklama = bulgu.baslik or bulgu.kural_id
        if bulgu.alinti:
            aciklama = f"{aciklama} ({bulgu.alinti})"
        if len(aciklama) > ACIKLAMA_SINIRI:
            aciklama = aciklama[: ACIKLAMA_SINIRI - 1].rstrip() + "…"

        onem = bulgu.onem
        if bulgu.kural_id in GELEN_BLOKE_ETMEYEN and onem == Onem.HATA:
            onem = Onem.UYARI

        return EksikAlan(
            alan=bulgu.alan or bulgu.kural_id,
            aciklama=aciklama,
            onem=onem,
            kural_id=bulgu.kural_id,
            dayanak=bulgu.dayanak,
            talep_edilebilir=bool(kural.get("talep_edilebilir")),
            # Bu bulgu kural motorundan geldi. Katman 1 (şema) ve Katman 3
            # (LLM) kendi değerlerini yazacak; böylece Parça 6'da "hangi
            # katman ne kadar iş görüyor" ölçülebilir kalır.
            katman=EksikKatman.KURAL,
            soru=kural.get("soru"),
        )

    # -- mevzuat --------------------------------------------------------------

    def _mevzuat_uret(self, bulgular, dosya: Dosya) -> list[MevzuatOnerisi]:
        """İhlal edilen kuralların dayanaklarından mevzuat önerisi üretir.

        KATMAN 1 — DEVIR_EK_mevzuat_ve_taslak.md §9.1
        ---------------------------------------------
        Kuralın kendi `dayanak` alanı zaten mevzuat atfıdır; aranmaz,
        kuralla birlikte gelir. Bu katman UYDURMA YAPAMAZ: atıf
        `kural_listesi.md`'de yazılıdır, model üretmez.

        KATMAN 3 — doğrulama, §9.3
        --------------------------
        Getirilen madde bu belgeye UYGULANIR MI. `kapsama_girer_mi()` ile
        belge türüne bakılır; geçemeyen öneri `dogrulandi=false` olur ve
        arayüzde gösterilmez (`api_sozlesmesi.md` §5.6.5).

        DÜRÜSTLÜK NOTU — RAPORA GİRECEK
        -------------------------------
        Kural kaynaklı önerilerde bu doğrulama YAPISI GEREĞİ geçer: motor
        kuralı koşturmadan önce aynı kapsam denetimini zaten yapıyor
        (kural_motoru.calistir, adım 2), dolayısıyla kapsam dışı bir kural
        hiç bulgu üretmez ve buraya hiç ulaşmaz. Mekanizma gerçek ve
        çalışır durumdadır; ancak eleme gücü asıl olarak belge türüne göre
        SABİT EŞLEME TABLOSUNDAN gelen önerilerde ortaya çıkardı. O tablo
        bu çalışmada kurulmamıştır — madde numaraları birincil mevzuat
        metninden doğrulanamadığı için (§9.2). Eksik satır zararsız,
        yanlış madde numarası zararlıdır.

        Aynı dayanağa birden çok kural bağlanabilir (ör. S-01, S-02 ve
        S-07'nin üçü de Y 11/1). Tek kayıt üretilir; ilk ihlal eden kuralın
        kimliği taşınır.
        """
        belge_turu = dosya.deger_al("siniflandirma.belge_turu")
        oneriler: dict[tuple[str, str], MevzuatOnerisi] = {}

        for bulgu in bulgular:
            cozum = dayanak_coz(bulgu.dayanak)
            if cozum is None:
                # Çözülemeyen dayanak atlanır, uydurulmaz. Dönüştürücü
                # 104/104 dayanağın çözüldüğünü doğruluyor; buraya düşmek
                # kural listesinin biçiminin değiştiği anlamına gelir.
                continue
            mevzuat_adi, madde = cozum
            anahtar = (mevzuat_adi, madde)
            if anahtar in oneriler:
                continue

            kapsam = (self._kural.get(bulgu.kural_id) or {}).get("kapsam")
            dogrulandi = (
                True if not kapsam else kapsama_girer_mi(belge_turu, kapsam)
            )

            oneriler[anahtar] = MevzuatOnerisi(
                mevzuat_adi=mevzuat_adi,
                madde=madde,
                alinti=None,          # mevzuat metni elimizde yok; uydurulmaz
                benzerlik=None,       # getirme yok, kuraldan geliyor
                dogrulandi=dogrulandi,
                kural_id=bulgu.kural_id,
            )
        return list(oneriler.values())

    # -- Katman 3: ajan döngüsü ----------------------------------------------

    def _istem(self, dosya: Dosya) -> list[dict]:
        """Sistem ve kullanıcı mesajlarını kurar.

        Belge türü ve kategori listesi İSTEME konur, modelin hafızasına
        değil. Parça 3'te ölçülen ders: istem ile şema farklı ad
        kullanırsa sınıflar sessizce kaybolur. Buradaki kategori adları
        `KATEGORILER` sözlüğünden üretiliyor, elle yazılmıyor.
        """
        satirlar = [
            f"- {ad}: {bilgi['modele']}"
            for ad, bilgi in KATEGORILER.items()
        ]
        sistem = (
            "Sen Türk kamu kurumlarında resmî yazışmaları inceleyen bir "
            "denetçisin. Görevin, KURAL MOTORUNUN YAKALAYAMADIĞI bir eksik "
            "olup olmadığını bulmak.\n\n"
            "Seçebileceğin kategoriler yalnızca şunlar:\n"
            + "\n".join(satirlar)
            + "\n\nÇALIŞMA BİÇİMİN:\n"
            "1. Önce kural_bulgulari aracını çağır, motorun ne bulduğunu gör. "
            "Onları TEKRAR ETME.\n"
            "2. Bir eksik olduğunu düşünüyorsan İDDİA ETMEDEN ÖNCE doğrula: "
            "alan_oku ile alanın gerçekten boş olduğunu, belgede_cumle_ara ile "
            "kanıtının belgede geçtiğini kontrol et.\n"
            "3. Araç sana HATA döndürürse iddian yanlıştır. Vazgeç ya da başka "
            "bir kanıt bul.\n"
            "4. İncelemeni bitirdiğinde sonuc_bildir'i çağır.\n\n"
            f"TUR SINIRI: en fazla {AZAMI_TUR} turun var ve her tur bir "
            "mesajdır. İlk turlarda araştır, EN GEÇ SON TURDA sonuc_bildir'i "
            "çağır. Sınırsız araştırma yok — bir noktada karar vermek "
            "zorundasın. Kanıtın doğrulandıysa bekleme, hemen bildir.\n\n"
            "Emin olmadığın bir eksiği İDDİA ETME. Var olmayan bir eksiği "
            "göstermek, bulunamayan bir eksikten daha zararlıdır."
        )

        tur = dosya.deger_al("siniflandirma.belge_turu") or "bilinmiyor"
        govde = (dosya.metin or "").strip()[:GOVDE_SINIRI]
        kullanici = (
            f"Belge türü: {tur}\n"
            f"Belge tarihi: {dosya.deger_al('ustveri.tarih')}\n"
            f"Konu: {dosya.deger_al('ustveri.konu')}\n\n"
            f"GÖVDE:\n{govde or '(gövde okunamadı)'}\n\n"
            "Bu belgeyi incele."
        )
        return [
            {"role": "system", "content": sistem},
            {"role": "user", "content": kullanici},
        ]

    def _katman3(self, dosya: Dosya) -> tuple[list[EksikAlan], list[str], list[str]]:
        """ReAct döngüsü: model karar verir, araç çağırır, gözlemi görür.

        Döner: (eksikler, iz, elenenler)

        DÖNGÜ NEDEN AJAN
        ----------------
        Katman 2'de direksiyon bizim kodumuzda: kuralı biz seçeriz, biz
        koştururuz. Burada model belgeyi okur, bir eksik olduğuna kanaat
        getirir, ve iddiasını doğrulamak için HANGİ ARACI ne zaman
        çağıracağına kendi karar verir. Aracın döndürdüğü gözlemi görüp
        yanıldığını anlarsa iddiasından vazgeçebilir.

        ELEME — modelin dediği doğrudan kabul edilmez
        --------------------------------------------
        Döngü bittikten sonra iddia üç kapıdan geçer:
            1. kategori tanımlı mı        (enum zaten zorluyor, yine de bakılır)
            2. alıntı belgede geçiyor mu  (uydurma buradan elenir)
            3. eksik_yok mu               (bulgu üretilmez)
        Geçemeyen iddia gösterilmez.
        """
        if self.istemci is None:
            return [], [], []

        mesajlar = self._istem(dosya)
        araclar = tum_arac_semasi()
        iz: list[str] = []
        elenen: list[str] = []
        iddia: dict | None = None

        for tur_no in range(1, AZAMI_TUR + 1):
            son_tur = tur_no == AZAMI_TUR

            # SON TURDA KARAR ZORLANIR
            # ------------------------
            # ÖLÇÜLDÜ 2026-08-23, belge_081: model 4 tur boyunca 8 araç
            # çağırdı ve hiç sonuç bildirmedi — araştırmaya devam etti,
            # karar vermedi. Sınırsız araştırma hem krediyi yakar hem
            # bulguyu hiç üretmez.
            #
            # İLK DENEME BAŞARISIZ OLDU: belirli bir fonksiyonu zorlamak
            # (tool_choice={"type":"function","function":{"name":...}})
            # modeli boş cevap verdirdi (content=None, tool_calls yok,
            # finish_reason=stop). Bu biçim her sağlayıcı/model çiftinde
            # desteklenmiyor.
            #
            # Bunun yerine tool_choice="required" kullanılıyor: model bir
            # araç çağırmak ZORUNDA ama hangisi olduğu serbest. Hangi aracı
            # çağırması gerektiği uyarı mesajında yazılı. Model yine de
            # araştırma aracı çağırırsa döngü sonuçsuz biter — bu da
            # kaydedilir, uydurulmaz.
            ek = None
            if son_tur:
                mesajlar.append({
                    "role": "user",
                    "content": (
                        "Son turdasın. Araştırmayı bitir ve şimdi "
                        "sonuc_bildir aracını çağır. Doğrulanmış bir kanıtın "
                        "yoksa kategori olarak 'eksik_yok' seç."
                    ),
                })
                ek = {"tool_choice": "required"}

            try:
                cevap = self.istemci.arac_cagir(mesajlar, araclar, ek=ek)
            except Exception as hata:  # noqa: BLE001
                # Model boş cevap verdi ya da sağlayıcı hata döndürdü.
                # DÖNGÜ ÇÖKMEZ: buraya kadarki iz korunur, bulgu üretilmez.
                # Sessizce bulgu uydurmaktansa hiç bulgu vermemek doğrudur.
                iz.append(f"tur {tur_no}: LLM HATASI -> {str(hata)[:110]}")
                if son_tur and ek is not None:
                    # Zorlama yüzünden olabilir; bir kez de zorlamasız dene.
                    try:
                        cevap = self.istemci.arac_cagir(mesajlar, araclar)
                        iz.append(f"tur {tur_no}: zorlamasiz yeniden denendi")
                    except Exception as hata2:  # noqa: BLE001
                        iz.append(f"tur {tur_no}: yeniden deneme de düştü -> "
                                  f"{str(hata2)[:80]}")
                        break
                else:
                    break
            mesajlar.append(cevap.ham_mesaj)

            if not cevap.arac_cagirdi_mi:
                # Model araç çağırmadan düz metin döndürdü. Sonuç bildirmesi
                # gerekiyordu; iddia yok sayılır. Uydurmaya çevirmiyoruz.
                iz.append(f"tur {tur_no}: model düz metin döndürdü, sonuç yok")
                break

            bitti = False
            for cagri in cevap.arac_cagrilari:
                if cagri.ad == "sonuc_bildir":
                    iddia = cagri.argumanlar
                    iz.append(
                        f"tur {tur_no}: SONUÇ -> {iddia.get('kategori')} "
                        f"({iddia.get('gerekce', '')[:70]})"
                    )
                    bitti = True
                    continue

                gozlem = arac_calistir(cagri.ad, cagri.argumanlar, dosya)
                iz.append(
                    f"tur {tur_no}: {cagri.ad}({str(cagri.argumanlar)[:60]}) "
                    f"-> {gozlem[:80]}"
                )
                mesajlar.append(
                    {
                        "role": "tool",
                        "tool_call_id": cagri.cagri_id,
                        "content": gozlem,
                    }
                )
            if bitti:
                break
        else:
            iz.append(f"tur sınırı ({AZAMI_TUR}) doldu, sonuç bildirilmedi")

        if not iddia:
            return [], iz, elenen

        # -- ELEME --
        kategori = (iddia.get("kategori") or "").strip()
        alinti = (iddia.get("alinti") or "").strip()
        gerekce = (iddia.get("gerekce") or "").strip()

        if kategori not in KATEGORILER:
            elenen.append(f"{kategori}: tanımsız kategori")
            return [], iz, elenen
        if kategori == "eksik_yok":
            return [], iz, elenen

        dogrulama = belgede_cumle_ara(dosya, alinti=alinti)
        if not dogrulama.startswith("BULUNDU"):
            elenen.append(f"{kategori}: alıntı doğrulanamadı — {dogrulama[:90]}")
            iz.append(f"ELENDİ: {kategori}, alıntı belgede yok")
            return [], iz, elenen

        bilgi = KATEGORILER[kategori]
        aciklama = bilgi["aciklama"]
        if gerekce:
            aciklama = f"{aciklama} ({gerekce})"
        if len(aciklama) > ACIKLAMA_SINIRI:
            aciklama = aciklama[: ACIKLAMA_SINIRI - 1].rstrip() + "…"

        return (
            [
                EksikAlan(
                    alan=bilgi["alan"] or "metin",
                    aciklama=aciklama,
                    onem=Onem(bilgi["onem"]),
                    kural_id=None,          # Katman 3'ün kuralı yok
                    dayanak=None,           # mevzuat atfı Katman 1'in işi
                    talep_edilebilir=False,
                    katman=EksikKatman.CIKARIM,
                    soru=None,
                )
            ],
            iz,
            elenen,
        )

    # -- çalıştırma -----------------------------------------------------------

    def calistir(self, dosya: Dosya, yaz: bool = True) -> DenetimSonucu:
        """Katman 2'yi koşturur ve bulguları EksikAlan'a çevirir.

        yaz=True ise sonuç `dosya.icerik.eksik_alanlar`a YAZILIR. Boru
        hattında istenen davranış budur; ölçüm betikleri yaz=False ile
        çağırıp belgeyi değiştirmeden inceleyebilir.
        """
        motor_sonucu = self.motor.calistir(dosya, hedef="gelen")
        eksikler = [self._eksige_cevir(b) for b in motor_sonucu.rapor.bulgular]
        mevzuat = self._mevzuat_uret(motor_sonucu.rapor.bulgular, dosya)

        if yaz:
            # Aynı kuralı iki kez yazmamak için: bu çağrının ürettiği
            # kural kimlikleri varsa önce temizlenir. Denetçi iki kez
            # çağrılırsa liste şişmemeli.
            yeni = {e.kural_id for e in eksikler if e.kural_id}
            dosya.icerik.eksik_alanlar = [
                e for e in dosya.icerik.eksik_alanlar
                if not (e.katman == EksikKatman.KURAL and e.kural_id in yeni)
            ] + eksikler

            # Mevzuat listesinde de tekrar olmamalı. Kural kaynaklı olanlar
            # (kural_id dolu) bu çağrının ürettikleriyle değiştirilir;
            # başka kaynaktan gelmiş öneriler korunur.
            yeni_kurallar = {m.kural_id for m in mevzuat if m.kural_id}
            dosya.mevzuat = [
                m for m in dosya.mevzuat
                if not (m.kural_id and m.kural_id in yeni_kurallar)
            ] + mevzuat

        # KATMAN 3 — Katman 2'den SONRA koşar. Sebep: `kural_bulgulari`
        # aracı `dosya.icerik.eksik_alanlar`ı okuyor; model motorun ne
        # bulduğunu görebilsin ve tekrar etmesin.
        cikarim, iz, elenen = self._katman3(dosya)
        if cikarim and yaz:
            dosya.icerik.eksik_alanlar = [
                e for e in dosya.icerik.eksik_alanlar
                if e.katman != EksikKatman.CIKARIM
            ] + cikarim

        return DenetimSonucu(
            eksikler=eksikler + cikarim,
            mevzuat=mevzuat,
            motor=motor_sonucu,
            ajan_izi=iz,
            ajan_elenen=elenen,
        )
