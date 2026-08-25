"""Güven Kapısı — Düğüm 12. Bu belge insana sorulmadan geçebilir mi.

Akış diyagramı: "otomatik mi, insana mı · eşik altındaysa veya kritik eksik
varsa insan onayına düşer · her karar işlem günlüğüne yazılır."

BEŞ GİRDİ, HEPSİ **VE** İLE BAĞLI
=================================
Biri bile kırmızıysa belge insana düşer. Hiçbiri tek başına yeterli değil.

    1  yönlendirme skoru        eşiğin altındaysa
    2  üslup döngüsü pes etti   taslak Yönetmeliğe uydurulamadı
    3  kimlik belirsiz          yazıyı hangi birimin imzalayacağı şüpheli
    4  kritik eksik             gelen evrakta hata düzeyinde eksik var
    5  çelişki                  iki bağımsız kaynak farklı birim gösteriyor

NEDEN TEK BİR SKOR DEĞİL
------------------------
Yönlendirme skoru 1,00 olan bir belgede taslak bozuk olabilir; taslağı
kusursuz bir belgenin hedefi belirsiz olabilir. Tek sayıya indirmek bu
ikisini birbirine karıştırır. `toplam_guven` yine de yazılıyor ama
BİLEŞENLERİN EN DÜŞÜĞÜ olarak — zincir en zayıf halkası kadar sağlamdır
ve bu yorumlanabilir bir sayı.

EŞİK 0,85 — ÖLÇÜMLE SEÇİLDİ, TAHMİNLE DEĞİL
===========================================
Yönlendirici skorları kesikli: 1,00 · 0,90 · 0,80 · 0,70 · 0,45 · 0,40.
Yani 0,95 ile 0,91 aynı şeyi yapar, ikisi de yalnızca 1,00'i geçirir.

ÖLÇÜLDÜ 2026-08-24, 300 belge (yonlendirici_dogrula, LLM açık):

    bant          doğru  yanlış
    1,00            125       0
    0,90-0,99       145       0
    0,70-0,89         5       1
    0,40-0,69        21       3

    eşik 0,85 -> 270 belge otomatik, içlerinde yanlış yönlendirme: 0
    eşik 0,95 -> 125 belge otomatik, içlerinde yanlış yönlendirme: 0

0,90-0,99 bandında 145 belgenin 145'i doğru. Eşiği 0,95'e çıkarmak doğru
yönlendirilmiş 145 belgeyi sebepsiz yere memurun önüne koyardı — bu
projede "yanlış alarm en tehlikeli hata türü" ilkesinin memur zamanına
uygulanmış hâli. Eşik 0,85'te kalıyor.

KURAL ÇAKIŞMASI OTOMATİK ONAYI ENGELLEMEZ
=========================================
`cikti_yazi.linter_raporu` kural motorunun TÜM bulgularını taşıyor,
Yazar'ın düzeltemediği çakışmalar dâhil. ME-02, muhatabı gerçek kişi olan
taslağın kapanışını ihlal sayıyor ama kapanış Y 16/12-e gereği DOĞRU
(bkz. yazar.CAKISAN_KURALLAR). Bu bulgular otomatik onayı engellememeli:
40 belgede 14'ü böyleydi ve hepsinde taslak doğruydu.

`yazar_sonucu` verilirse çakışmalar oradan okunuyor. Verilmezse rapordan
`yazar.CAKISAN_KURALLAR` süzgeciyle ayıklanıyor — süzgeç tek yerde.

NE YAZILMIYOR
=============
`insan_karari`, `karar_veren_rol`, `karar_zamani`, `karar_gerekcesi`
ALANLARINA DOKUNULMUYOR. Onlar "insan ne dedi" sorusunun cevabı ve
arayüz doldurur. Kapı yalnızca "insana sorulmalı mı" sorusunu cevaplıyor;
`Karar` docstring'i bu ayrımı açıkça istiyor.

Kuyruk da bir alan değil, bir sorgudur:
    durum == INSAN_ONAYI_BEKLIYOR  AND  insan_karari == YOK
"""

from __future__ import annotations

from dataclasses import dataclass, field

from veri_yapisi import EvrakDurumu, Karar, Onem

VARSAYILAN_ESIK = 0.85

# Kritik sayılan eksik düzeyi. UYARI ve BILGI düzeyi otomatik onayı
# engellemiyor — `Onem` docstring'i: "yalnızca bu düzeyde bulgu belgeyi
# geçersiz kılar" diyen düzey HATA.
KRITIK_ONEM = Onem.HATA


@dataclass
class KapiSonucu:
    """Kararın ayrıntısı. `Karar` şeması yalnızca sonucu tutuyor; hangi
    bileşenin ne verdiği ölçümde lazım ve şemaya alan eklemeden burada
    taşınıyor."""

    otomatik: bool = False
    toplam_guven: float = 0.0
    esik: float = VARSAYILAN_ESIK
    sebepler: list[str] = field(default_factory=list)
    bilesenler: dict[str, float] = field(default_factory=dict)
    engelleyen: list[str] = field(default_factory=list)

    @property
    def ozet(self) -> str:
        if self.otomatik:
            return f"otomatik onay · güven {self.toplam_guven:.2f}"
        return (f"insan onayı · güven {self.toplam_guven:.2f} · "
                f"engel: {', '.join(self.engelleyen) or '?'}")


def _cakisan_kural_kimlikleri(yon) -> set[str]:
    """Bu yönde Yazar'ın düzeltemeyeceği kural kimlikleri."""
    from yazar import CAKISAN_KURALLAR

    return set(CAKISAN_KURALLAR.get(yon, ()))


def _linter_engelleri(dosya, yazar_sonucu) -> list[str]:
    """Taslakta çözülmemiş kural ihlali kaldı mı.

    `yazar_sonucu` varsa döngünün kendi kaydı kullanılıyor — en doğru
    kaynak, çünkü çakışmaları zaten ayıklamış durumda.

    Yoksa `linter_raporu`ndan okunuyor ve çakışan kurallar `yazar`
    modülündeki süzgeçle ayıklanıyor. Süzgeci burada YENİDEN TANIMLAMAK
    iki listenin zamanla ayrışmasına yol açardı; ME-02 düzeltildiğinde
    orayı boşaltmak yetsin.
    """
    if yazar_sonucu is not None:
        if yazar_sonucu.pes_edildi:
            kalan = [getattr(b, "kural_id", "?")
                     for b in (yazar_sonucu.son_bulgular or [])]
            return [f"Üslup döngüsü {len(kalan)} ihlali düzeltemedi: "
                    f"{', '.join(kalan) or '?'}"]
        return []

    rapor = getattr(dosya.cikti_yazi, "linter_raporu", None)
    bulgular = getattr(rapor, "bulgular", None) or []
    if not bulgular:
        return []
    yon = getattr(dosya.cikti_yazi, "hiyerarsi_yonu", None)
    cakisan = _cakisan_kural_kimlikleri(yon)
    kalan = [b for b in bulgular
             if str(getattr(b, "onem", "")).lower() == KRITIK_ONEM.value
             and getattr(b, "kural_id", None) not in cakisan]
    if not kalan:
        return []
    return [f"Taslakta çözülmemiş kural ihlali: "
            f"{', '.join(getattr(b, 'kural_id', '?') for b in kalan)}"]


def _kritik_eksikler(dosya) -> list[str]:
    """Gelen evrakta hata düzeyinde eksik var mı.

    Denetçi'nin `icerik.eksik_alanlar` listesinden okunuyor. `giderildi`
    olanlar sayılmıyor: cevabı gelmiş bir eksik artık engel değil.
    """
    alanlar = getattr(getattr(dosya, "icerik", None), "eksik_alanlar", None) or []
    kritik = [e for e in alanlar
              if getattr(e, "onem", None) == KRITIK_ONEM
              and not getattr(e, "giderildi", False)]
    if not kritik:
        return []
    adlar = ", ".join(sorted({(e.kural_id or e.alan or "?") for e in kritik}))
    return [f"Gelen evrakta {len(kritik)} kritik eksik: {adlar}"]


def _kimlik_engeli(yazar_sonucu) -> list[str]:
    """Yazıyı hangi birimin imzalayacağı şüpheliyse otomatik onay olmaz.

    Yanlış birim adına imzalanmış bir yazı, yanlış yönlendirilmiş bir
    yazıdan daha kötüdür: karşı taraf onu meşru sayar ve işlem yapar.
    """
    if yazar_sonucu is None or yazar_sonucu.iskelet is None:
        return []
    kimlik = yazar_sonucu.iskelet.kimlik
    if kimlik.belirsiz:
        return [kimlik.sebep or "Taslağı yazan birim belirsiz"]
    return []


def degerlendir(dosya, yazar_sonucu=None, yonlendirme_sonucu=None,
                esik: float = VARSAYILAN_ESIK) -> KapiSonucu:
    """Beş girdiyi birleştirir, `dosya.karar` ve `dosya.durum`u yazar.

    `yazar_sonucu` ve `yonlendirme_sonucu` verilmezse elden geldiğince
    `Dosya`dan okunuyor. Verilmeleri yeğdir: döngünün ve yönlendirmenin
    kendi kayıtları şemaya sığmayan ayrıntıyı taşıyor.
    """
    s = KapiSonucu(esik=esik)

    # -- 1 · yönlendirme skoru --------------------------------------------
    y = getattr(dosya, "yonlendirme", None)
    hedef = getattr(y, "hedef_birim", None)
    skor = float(getattr(y, "skor", 0.0) or 0.0)
    s.bilesenler["yonlendirme"] = skor
    if not hedef:
        s.engelleyen.append("yonlendirme")
        s.sebepler.append("Hedef birim belirlenemedi")
    elif skor < esik:
        s.engelleyen.append("yonlendirme")
        s.sebepler.append(
            f"Yönlendirme güveni {skor:.2f}, eşik {esik:.2f} — altında")

    # -- 2 · üslup döngüsü -------------------------------------------------
    linter = _linter_engelleri(dosya, yazar_sonucu)
    s.bilesenler["taslak"] = 0.0 if linter else 1.0
    if linter:
        s.engelleyen.append("taslak")
        s.sebepler.extend(linter)

    # -- 3 · kimlik --------------------------------------------------------
    kimlik = _kimlik_engeli(yazar_sonucu)
    s.bilesenler["kimlik"] = 0.0 if kimlik else 1.0
    if kimlik:
        s.engelleyen.append("kimlik")
        s.sebepler.extend(kimlik)

    # -- 4 · kritik eksik --------------------------------------------------
    eksik = _kritik_eksikler(dosya)
    s.bilesenler["eksik"] = 0.0 if eksik else 1.0
    if eksik:
        s.engelleyen.append("eksik")
        s.sebepler.extend(eksik)

    # -- 5 · çelişki -------------------------------------------------------
    celiski = bool(getattr(yonlendirme_sonucu, "celiski", False))
    if not celiski and yonlendirme_sonucu is None:
        # Sonuç nesnesi yoksa gerekçeden okunuyor. Yönlendirici çelişkiyi
        # gerekçeye AÇIKÇA yazıyor; başka yerde iz bırakmıyor.
        celiski = "Çelişki" in (getattr(y, "gerekce", None) or "")
    s.bilesenler["celiski"] = 0.0 if celiski else 1.0
    if celiski:
        s.engelleyen.append("celiski")
        s.sebepler.append(
            "İki bağımsız kaynak farklı birim gösteriyor; hangisinin "
            "bozulduğu belirlenemedi")

    # -- birleştirme -------------------------------------------------------
    # Zincir en zayıf halkası kadar sağlam. Ortalama almak, tek bir
    # bileşenin sıfır olduğu belgeyi yüksek skorlu gösterirdi.
    s.toplam_guven = min(s.bilesenler.values()) if s.bilesenler else 0.0
    s.otomatik = not s.engelleyen

    _yaz(dosya, s)
    return s


def _yaz(dosya, s: KapiSonucu) -> None:
    """Sonucu `dosya.karar` ve `dosya.durum`a aktarır.

    `insan_karari` ve karar meta alanlarına DOKUNULMUYOR — onlar arayüzün.

    `EKSIK_BILGI_BEKLIYOR` durumu da burada YAZILMIYOR. Eksik bilgi
    talebini karşı tarafa göndermek İNSANIN kararı: akış diyagramında
    "kullanıcıya eksik bilgi soruları iletilir" satırı İNSAN ONAYI
    kutusunun altında duruyor. Memur "Eksik bilgi iste" düğmesine
    bastığında durumu arayüz değiştirir.
    """
    mevcut = dosya.karar
    dosya.karar = Karar(
        otomatik_onay=s.otomatik,
        insan_onayi_gerekli=not s.otomatik,
        sebepler=s.sebepler[:20],
        toplam_guven=round(max(0.0, min(1.0, s.toplam_guven)), 2),
        toplam_sure_ms=getattr(mevcut, "toplam_sure_ms", 0.0),
        esik=s.esik,
        # İnsan zaten karar vermişse EZİLMİYOR: kapı yeniden koşarsa
        # memurun kararını silmek, iz kaydını yok etmek olur.
        insan_karari=getattr(mevcut, "insan_karari", None) or Karar().insan_karari,
        karar_veren_rol=getattr(mevcut, "karar_veren_rol", None),
        karar_zamani=getattr(mevcut, "karar_zamani", None),
        karar_gerekcesi=getattr(mevcut, "karar_gerekcesi", None),
    )
    dosya.durum = (EvrakDurumu.OTOMATIK_ONAYLANDI if s.otomatik
                   else EvrakDurumu.INSAN_ONAYI_BEKLIYOR)
