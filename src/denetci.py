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

    def __init__(self, kural_dosyasi: Path | str | None = None) -> None:
        self.motor = KuralMotoru(kural_dosyasi)
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

        return EksikAlan(
            alan=bulgu.alan or bulgu.kural_id,
            aciklama=aciklama,
            onem=bulgu.onem,
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

        return DenetimSonucu(
            eksikler=eksikler, mevzuat=mevzuat, motor=motor_sonucu
        )
