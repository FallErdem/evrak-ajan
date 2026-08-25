"""Boru hattı — PDF'ten karara kadar tek çağrı.

    from boru_hatti import isle
    sonuc = isle("belge_048.pdf", istemci)
    sonuc.dosya.cikti_yazi.metin
    sonuc.dosya.karar.otomatik_onay

NEDEN BU MODÜL VAR — ÖLÇÜLDÜ 2026-08-24
=======================================
Bu modül yazılana kadar boru hattı YALNIZCA ölçüm betiklerinin içinde
yaşıyordu ve her betik `Dosya`yı kendi kuruyordu. Üçü de yanlış kurdu:
`d.metin = r.govde` diyerek imza bloğunu ve dipnotu gövdeye kattılar.

Bedeli: güven kapısı koşusunda 300 belgenin 300'ünde ME-02 yanlış alarm
verdi ve otomatik onay oranı %0 çıktı. Aynı hata 2026-08-23'te bir kez
daha bulunup `govde_kur` ile düzeltilmişti; ikinci kez ortaya çıkmasının
sebebi düzeltmenin bir ölçüm betiğinde kalmış olmasıydı.

Arayüz bağlandığında sırayı yeniden kuran biri aynı tuzağa düşerdi.
Artık tek çağrı var ve sıra burada yazılı.

DÜĞÜM SIRASI
============
    1  Okuyucu        PDF -> satırlar
    2  Ayrıştırıcı    satırlar -> alanlar, gövde
    3  Anlama         belge türü, SDP, talep, özet        LLM
    4  Denetçi        gelen evrakta ne eksik              LLM'siz kipte
    7  Özetleyici     kısa ve öz özet                     LLM
   11  Yönlendirici   hangi birime gider                  gerekirse LLM
    9  Yazar          taslak + üslup döngüsü              LLM
   12  Güven Kapısı   otomatik mı, insana mı              LLM yok

ÖZETLEYİCİ DENETÇİ'DEN **SONRA** — 2026-08-25'te eklendi
--------------------------------------------------------
Modül yazıldığında `ozetleyici` boru hattına hiç bağlanmamıştı; tek
başına ölçülmüş ama `isle()` onu çağırmıyordu. Şartname 6.4.1 beşinci
yeteneği ("evraka ilişkin kısa ve öz bir özet oluşturabilme") ayrıca
sayıyor ve madde 9 "tek görevin eksik olması durumunda sistem
tamamlanmış kabul edilmez" diyor.

Konumu Denetçi'den sonra: özet, belgenin ne dediğini değil NE
DURUMDA OLDUĞUNU anlatmalı ve eksik bilgi tespiti o an elde olmalı.
Anlama'nın `icerik.ozet`i yerinde kalıyor; Özetleyici üstüne yazıyor
ve farkı sayısal doğrulamadan geçirmiş olması (`dogrulanmayan`
listesi uydurma sayıları yakalıyor).

YÖNLENDİRİCİ, YAZAR'DAN **ÖNCE** KOŞUYOR — diyagramdan sapma
------------------------------------------------------------
Akış diyagramı Yönlendirici'yi (düğüm 11) Ajan 2'den SONRA koymuş.
Burada ÖNCE koşuyor ve gerekçesi ölçüm:

`yazar.kim_yaziyor` taslağı hangi birimin imzalayacağını belirlerken
önce `yonlendirme.hedef_birim`e bakıyor, yoksa muhatap satırına
düşüyor. 300 belgenin 22'sinde muhatap satırı hedefi SÖYLEMİYOR
("DAĞITIM YERLERİNE" 12, "İLGİLİ MAKAMA" 10). Yönlendirici sonra
koşarsa o 22 belgede taslak kimliksiz kalıyor ve insan onayına düşüyor.

Yönlendirici'nin taslağa bağımlılığı YOK — yalnızca gelen evrağı
okuyor (`ustveri`, `siniflandirma`, `icerik`, `metin`). Bu yüzden sırayı
değiştirmek teknik olarak serbest ve tek yönlü kazanç.

Gerçek idari akış da bu yönde: evrak gelir, kaydedilir, HAVALE EDİLİR,
sonra ilgili birim cevabı hazırlar. Diyagram güncellenmeli.

LLM'SİZ KİP
===========
`istemci=None` verilirse Anlama ve Yazar ATLANIR, Yönlendirici
deterministik hatlarla koşar. Çıktı bir taslak içermez ama sınıflandırma
dışındaki her şey ölçülebilir. Kredi harcamadan koşan bir ablasyon.

HATA YÖNETİMİ — ADIM ADIM, SESSİZ DEĞİL
=======================================
Her düğüm kendi `IzKaydi`sini bırakıyor (`dosya.iz`) — akış diyagramının
"her karar işlem günlüğüne yazılır" satırı. Bir düğüm patlarsa iz kaydına
yazılıyor ve boru hattı DEVAM EDİYOR: Anlama patladıysa Yönlendirici yine
deterministik hatlarla çalışabilir. Hangi düğümün patladığı `sonuc.hatalar`
listesinde görünür kalıyor.

Okuyucu ya da Ayrıştırıcı patlarsa devam edilmiyor — sonraki her düğümün
girdisi onlardan geliyor.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from veri_yapisi import Dosya, EvrakDurumu, IzKaydi


@dataclass
class BoruHattiSonucu:
    """Koşunun tamamının kaydı."""

    dosya: Dosya
    basarili: bool = True
    hatalar: list[str] = field(default_factory=list)
    # Alt modüllerin ürettiği uyarılar. HATA DEĞİL ama görünür kalmalı:
    # düğüm çalıştı, çıktı verdi, ama bir şey ters gitti diyor.
    uyarilar: list[str] = field(default_factory=list)
    atlanan: list[str] = field(default_factory=list)
    sure_ms: float = 0.0
    llm_cagrisi: int = 0

    # Düğümlerin kendi sonuç nesneleri. Şemaya sığmayan ayrıntıyı
    # taşıyorlar ve Güven Kapısı ile ölçüm betikleri bunları istiyor.
    okuma: object | None = None
    ayristirma: object | None = None
    anlama: object | None = None
    ozetleme: object | None = None
    yonlendirme: object | None = None
    yazar: object | None = None
    kapi: object | None = None

    @property
    def ozet(self) -> str:
        d = self.dosya
        hedef = getattr(d.yonlendirme, "hedef_birim", None) or "—"
        return (f"{d.durum} · hedef {hedef} · "
                f"güven {d.karar.toplam_guven:.2f}"
                + (f" · {len(self.hatalar)} hata" if self.hatalar else ""))


def _iz(dosya: Dosya, ajan: str, adim: int, t0: float,
        basarili: bool = True, hata: str | None = None,
        ozet: str | None = None, guven: float | None = None) -> None:
    """Düğümün izini `dosya.iz`e ekler.

    Akış diyagramı düğüm 12: "her karar işlem günlüğüne yazılır." İz
    kaydı olmadan hangi düğümün ne kadar sürdüğü ve nerede patladığı
    sonradan bilinemez.
    """
    dosya.iz.append(IzKaydi(
        ajan=ajan,
        adim_no=adim,
        basarili=basarili,
        hata=(hata[:500] if hata else None),
        sure_ms=(time.perf_counter() - t0) * 1000,
        ozet=(ozet[:300] if ozet else None),
        guven=guven,
    ))


def isle(pdf_yolu: str | Path, istemci=None, motor=None,
         denetci=None, esik: float | None = None,
         yonlendirici_once: bool = True) -> BoruHattiSonucu:
    """Bir PDF'i uçtan uca işler.

    `istemci`  LLM istemcisi. None ise Anlama ve Yazar atlanır.
    `motor`    KuralMotoru. Verilmezse kurulur — DÖNGÜDE ÇAĞIRIYORSAN VER,
               yoksa kural dosyası her belgede yeniden okunur.
    `denetci`  Denetci örneği. Verilmezse kurulmaya çalışılır.
    `esik`     Güven kapısı eşiği. None ise `guven_kapisi.VARSAYILAN_ESIK`.

    `yonlendirici_once`  ABLASYON ANAHTARI. Varsayılan True ve üretimde
        böyle kalmalı. False verilirse diyagramdaki eski sıra koşar
        (Yazar önce, Yönlendirici sonra) ve `kim_yaziyor` muhatap
        satırına düşer. Ölçüm betiği iki sırayı yan yana koşturup kararı
        rakamla göstersin diye var; ölçüm betiğinin boru hattını KENDİ
        KURMASINI istemiyoruz — o hata bir kez yapıldı ve 300 belgede
        yanlış alarm üretti.
    """
    from ayristirici import ayristir, govde_kur
    from guven_kapisi import VARSAYILAN_ESIK, degerlendir
    from okuyucu import oku
    from yonlendirici import yonlendir

    t_bas = time.perf_counter()
    d = Dosya()
    s = BoruHattiSonucu(dosya=d)
    d.durum = EvrakDurumu.ISLENIYOR
    d.kaynak.dosya = str(pdf_yolu)

    # -- 1 · Okuyucu -------------------------------------------------------
    t = time.perf_counter()
    r = oku(pdf_yolu)
    s.okuma = r
    if r.hata or not r.satirlar:
        _iz(d, "okuyucu", 1, t, basarili=False, hata=r.hata or "satır yok")
        s.basarili = False
        s.hatalar.append(f"Okuyucu: {r.hata or 'satır yok'}")
        d.durum = EvrakDurumu.HATA
        s.sure_ms = (time.perf_counter() - t_bas) * 1000
        return s
    d.kaynak.ham_metin = "\n".join(x.metin for x in r.satirlar)
    _iz(d, "okuyucu", 1, t, ozet=r.ozet)

    # -- 2 · Ayrıştırıcı ---------------------------------------------------
    t = time.perf_counter()
    try:
        a = ayristir(r.satirlar,
                     r.ayrilmis.dipnot_bulundu if r.ayrilmis else None)
    except Exception as e:  # noqa: BLE001
        _iz(d, "ayristirici", 2, t, basarili=False, hata=f"{type(e).__name__}: {e}")
        s.basarili = False
        s.hatalar.append(f"Ayrıştırıcı: {type(e).__name__}: {e}")
        d.durum = EvrakDurumu.HATA
        s.sure_ms = (time.perf_counter() - t_bas) * 1000
        return s
    s.ayristirma = a
    d.ustveri = a.ustveri
    d.kanit = dict(a.kanit)
    # GÖVDE `govde_kur` İLE KURULUYOR. `r.govde` DEĞİL — o, imza bloğunu ve
    # dipnotu da içeriyor ve ME kurallarında yanlış alarm üretiyor.
    d.metin = govde_kur(r.ayrilmis.govde_satirlari if r.ayrilmis else r.satirlar, a)
    _iz(d, "ayristirici", 2, t,
        ozet=f"aile {a.aile}, {len(a.uyarilar)} uyarı")

    # -- 3 · Anlama --------------------------------------------------------
    if istemci is None:
        s.atlanan.append("anlama (istemci yok)")
    else:
        t = time.perf_counter()
        try:
            from anlama import anla

            an = anla(r.govde, a, istemci)
            s.anlama = an
            s.llm_cagrisi += 1
            d.siniflandirma = an.siniflandirma
            d.icerik = an.icerik
            s.uyarilar.extend(f"Anlama: {u}" for u in (an.uyarilar or []))
            # `anla()` istisnayı KENDİ İÇİNDE yakalayıp uyarıya çeviriyor.
            # Sessiz kalırsak boru hattı "başarılı" der ama sınıflandırma
            # boştur. Tür bilinmiyorsa bunu HATA sayıyoruz: Denetçi'nin
            # kapsamlı kuralları türe bakıyor ve tür yoksa eksik bulamıyor.
            tur = getattr(an.siniflandirma, "belge_turu", None)
            if tur is None or str(tur) == "bilinmiyor":
                s.hatalar.append("Anlama belge türünü belirleyemedi")
            _iz(d, "anlama", 3, t, ozet=f"tür {an.siniflandirma.belge_turu}")
        except Exception as e:  # noqa: BLE001
            _iz(d, "anlama", 3, t, basarili=False, hata=f"{type(e).__name__}: {e}")
            s.hatalar.append(f"Anlama: {type(e).__name__}: {e}")

    # -- 4 · Denetçi -------------------------------------------------------
    # Anlama'dan SONRA: `kapsama_girer_mi` belge türüne bakıyor, tür
    # `bilinmiyor` kalırsa kapsamlı kurallar atlanır ve eksik bulunmaz.
    if denetci is None:
        try:
            from denetci import Denetci

            denetci = Denetci()
        except Exception as e:  # noqa: BLE001
            s.atlanan.append(f"denetci ({type(e).__name__})")
    if denetci is not None:
        t = time.perf_counter()
        try:
            denetci.calistir(d)
            _iz(d, "denetci", 4, t,
                ozet=f"{len(d.icerik.eksik_alanlar)} eksik alan")
        except Exception as e:  # noqa: BLE001
            _iz(d, "denetci", 4, t, basarili=False, hata=f"{type(e).__name__}: {e}")
            s.hatalar.append(f"Denetçi: {type(e).__name__}: {e}")

    # -- 7 · Özetleyici ----------------------------------------------------
    # Denetçi'den SONRA: özet, belgenin eksikleri bilinerek yazılmalı.
    if istemci is None:
        s.atlanan.append("ozetleyici (istemci yok)")
    else:
        t = time.perf_counter()
        try:
            from ozetleyici import Ozetleyici

            oz = Ozetleyici(istemci).calistir(d)
            s.ozetleme = oz
            s.llm_cagrisi += 1
            s.uyarilar.extend(f"Özetleyici: {u}" for u in (oz.uyarilar or []))
            # Uydurma sayı SESSİZ GEÇİLMİYOR. `sayisal_dogrula` özetteki her
            # sayısal değeri belgede arıyor; bulunmayan varsa özet yine
            # yazılıyor (geri kalanı kullanışlı) ama uyarı listesinde kalıyor.
            if oz.dogrulanmayan:
                s.uyarilar.append(
                    "Özetleyici: özette belgede geçmeyen sayısal değer(ler) var: "
                    + ", ".join(oz.dogrulanmayan[:5])
                )
            _iz(d, "ozetleyici", 7, t,
                ozet=f"{len(d.icerik.ozet or '')} karakter, "
                     f"{len(oz.dogrulanmayan)} doğrulanmayan sayı")
        except Exception as e:  # noqa: BLE001
            _iz(d, "ozetleyici", 7, t, basarili=False,
                hata=f"{type(e).__name__}: {e}")
            s.hatalar.append(f"Özetleyici: {type(e).__name__}: {e}")

    # -- 11 · Yönlendirici — VARSAYILAN OLARAK YAZAR'DAN ÖNCE -------------
    def _yonlendirici_adimi() -> None:
        t = time.perf_counter()
        try:
            yon = yonlendir(d, istemci)
            s.yonlendirme = yon
            if yon.llm_kullanildi:
                s.llm_cagrisi += 1
            s.uyarilar.extend(f"Yönlendirici: {u}" for u in (yon.uyarilar or []))
            if yon.hedef is None:
                s.hatalar.append("Yönlendirici hedef birim belirleyemedi")
            _iz(d, "yonlendirici", 11, t, ozet=yon.ozet, guven=yon.skor)
        except Exception as e:  # noqa: BLE001
            _iz(d, "yonlendirici", 11, t, basarili=False,
                hata=f"{type(e).__name__}: {e}")
            s.hatalar.append(f"Yönlendirici: {type(e).__name__}: {e}")

    # -- 9 · Yazar ---------------------------------------------------------
    def _yazar_adimi() -> None:
        nonlocal motor
        if istemci is None:
            s.atlanan.append("yazar (istemci yok)")
            return
        if motor is None:
            from kural_motoru import KuralMotoru

            motor = KuralMotoru()
        t = time.perf_counter()
        try:
            from yazar import yaz

            ys = yaz(d, istemci, motor)
            s.yazar = ys
            s.llm_cagrisi += ys.tur_sayisi
            s.uyarilar.extend(f"Yazar: {u}" for u in (ys.uyarilar or []))
            # `taslak_uret` LLM hatasını yakalayıp uyarı listesine
            # yazıyor, istisna fırlatmıyor. Metin boşsa taslak
            # ÜRETİLMEMİŞTİR ve bu sessiz geçilemez — Ş 9: "tek görevin
            # eksik olması durumunda sistem tamamlanmış kabul edilmez."
            if not (d.cikti_yazi.metin or "").strip():
                s.hatalar.append("Yazar taslak metni üretemedi")
            _iz(d, "yazar", 9, t, ozet=ys.ozet,
                basarili=bool((d.cikti_yazi.metin or "").strip()))
        except Exception as e:  # noqa: BLE001
            _iz(d, "yazar", 9, t, basarili=False, hata=f"{type(e).__name__}: {e}")
            s.hatalar.append(f"Yazar: {type(e).__name__}: {e}")

    # SIRA. Gerekçesi modül başlığında: `kim_yaziyor` önce
    # `yonlendirme.hedef_birim`e bakıyor ve 300 belgenin 22'sinde muhatap
    # satırı hedefi söylemiyor.
    if yonlendirici_once:
        _yonlendirici_adimi()
        _yazar_adimi()
    else:
        _yazar_adimi()
        _yonlendirici_adimi()

    # -- 12 · Güven Kapısı -------------------------------------------------
    t = time.perf_counter()
    try:
        kapi = degerlendir(d, yazar_sonucu=s.yazar, yonlendirme_sonucu=s.yonlendirme,
                           esik=esik if esik is not None else VARSAYILAN_ESIK)
        s.kapi = kapi
        _iz(d, "guven_kapisi", 12, t, ozet=kapi.ozet, guven=kapi.toplam_guven)
    except Exception as e:  # noqa: BLE001
        _iz(d, "guven_kapisi", 12, t, basarili=False,
            hata=f"{type(e).__name__}: {e}")
        s.hatalar.append(f"Güven kapısı: {type(e).__name__}: {e}")
        # Kapı patladıysa belge OTOMATİK GEÇMEZ. Karar verilemediğinde
        # güvenli varsayılan insana sormaktır.
        d.durum = EvrakDurumu.INSAN_ONAYI_BEKLIYOR

    s.sure_ms = (time.perf_counter() - t_bas) * 1000
    d.karar.toplam_sure_ms = s.sure_ms
    s.basarili = not s.hatalar
    return s
