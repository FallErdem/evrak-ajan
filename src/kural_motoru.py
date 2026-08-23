"""Kural motoru — veri/kurallar.json'daki denetimleri bir belgeye uygular.

src/ altinda duran, ICE AKTARILAN bir moduldur. Elle calistirilmaz.

    from kural_motoru import KuralMotoru
    motor = KuralMotoru()                       # veri/kurallar.json okunur
    rapor = motor.calistir(dosya, hedef="gelen")

Motor IKI KEZ calisir (DEVIR_EK2 §5):

    Denetci (AJAN 1)   hedef="gelen"    gelen evrakta ne eksik
    Yazar   (AJAN 2)   hedef="giden"    urettigi taslak Yonetmelige uyuyor mu

MOTOR DEGISMEZI
---------------
Bir kuralin baktigi alan bos ise kural ATLANIR ve atlanan_kural_sayisi'na
yazilir. Tek istisna 'bos_olmamali' ve 'bos_liste_olmamali' turleridir;
onlarin isi zaten boslugu denetlemek.

Sebep: dilekcede sayi yoktur, ilgi yoktur, konu yoktur. Bu kurallar
korlemesine kosarsa 132 kisi belgesinde yanlis alarm seli olur. Yanlis
alarm bu projenin en tehlikeli hata turudur — memura olmayan bir ihlali
gostermek sisteme guveni bitirir.

"Bos" tanimi BURADA YENIDEN YAZILMAZ. veri_yapisi.Dosya.alan_dolu_mu()
cagirilir. Iki ayri bosluk tanimi zamanla ayrisir; Parca 3'te bu hatanin
uc ornegi yasandi.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kural_ozel import OZEL_FONKSIYONLAR
from veri_yapisi import (
    Dosya,
    LinterBulgusu,
    LinterRaporu,
    Onem,
    kapsama_girer_mi,
)

VARSAYILAN_KURAL_DOSYASI = Path(__file__).resolve().parent.parent / "veri" / "kurallar.json"

HEDEFLER = ("gelen", "giden")


# =============================================================================
# Atlama sebepleri — olcum icin ayri ayri sayilir
# =============================================================================


class AtlamaSebebi:
    HEDEF_DISI = "hedef_disi"        # kural bu yone uygulanmiyor
    KAPSAM_DISI = "kapsam_disi"      # belge turu kuralin kapsaminda degil
    ALAN_BOS = "alan_bos"            # motor degismezi
    YOL_YOK = "yol_yok"              # kuralda yol tanimli degil (hata sayilir)
    VERI_YOK = "veri_yok"            # ozel fonksiyon denetim icin veri bulamadi


@dataclass
class AtlamaKaydi:
    """Hangi kural neden atlandi. Arayuzde ve olcumde gorunur."""

    kural_id: str
    sebep: str
    ayrinti: str | None = None


@dataclass
class MotorSonucu:
    """calistir() ciktisi.

    LinterRaporu semada donmus ve yalnizca iki sayac tasiyor. Atlama
    ayrintisi ve uygulanmayan kural sayisi burada tasinir; sema
    degistirilmez (alan silinmez/eklenmez kurali).
    """

    rapor: LinterRaporu
    atlamalar: list[AtlamaKaydi] = field(default_factory=list)

    def atlama_ozeti(self) -> dict[str, int]:
        ozet: dict[str, int] = {}
        for a in self.atlamalar:
            ozet[a.sebep] = ozet.get(a.sebep, 0) + 1
        return ozet


# =============================================================================
# Islemeciler — 8 tane
# =============================================================================
#
# Her isleyici ayni sozlesmeyi tasiyor:
#     (deger, kural, dosya) -> (ihlal_var_mi, alinti)
#
# `deger` motor tarafindan yoldan okunmus olarak gelir. Isleyici yol
# cozumlemez; yol cozumleme tek yerde yapilir ki gizli esleme olmasin.


def _isleyici_bos_olmamali(deger, kural, dosya) -> tuple[bool, str | None]:
    """Alan doldurulmus mu. Motor degismezinin ISTISNASI: bos deger burada
    atlama sebebi degil, bulgunun ta kendisidir."""
    yol = kural["_cozulmus_yol"]
    return (not dosya.alan_dolu_mu(yol)), None


def _isleyici_bos_liste_olmamali(deger, kural, dosya) -> tuple[bool, str | None]:
    """Liste alani en az bir eleman tasiyor mu. Bu da istisnadir."""
    if deger is None:
        return True, None
    try:
        bos = len(deger) == 0
    except TypeError:
        return False, None          # liste degil; denetlenecek bir sey yok
    return bos, None


def _isleyici_regex_bulunmali(deger, kural, dosya) -> tuple[bool, str | None]:
    desen = kural["_derlenmis"]
    for parca in _metin_parcalari(deger, kural):
        m = desen.search(parca)
        if m:
            return False, None      # bulundu, ihlal yok
    return True, _kisalt(_ilk_parca(deger, kural))


def _isleyici_regex_bulunmamali(deger, kural, dosya) -> tuple[bool, str | None]:
    desen = kural["_derlenmis"]
    for parca in _metin_parcalari(deger, kural):
        m = desen.search(parca)
        if m:
            return True, _kisalt(m.group(0))
    return False, None


def _isleyici_alan_esitligi(deger, kural, dosya) -> tuple[bool, str | None]:
    """Iki alan ayni mi. Ikisi de dolu degilse motor degismezi atlar."""
    karsi = dosya.deger_al(kural["karsi_yol"])
    if deger is None or karsi is None:
        return False, None
    return (str(deger).strip() != str(karsi).strip()), _kisalt(f"{deger} != {karsi}")


def _isleyici_izinli_kume(deger, kural, dosya) -> tuple[bool, str | None]:
    """Deger izinli degerler kumesinde mi.

    Kume kuralin `izinli_kume` alanindan gelir. Bu alani tasiyan aktif kural
    su an YOK (G-01 ve G-03 uygulanir=false); isleyici gercek veriyle
    sinanmamistir.
    """
    kume = kural.get("izinli_kume")
    if not kume:
        raise KuralYapilandirmaHatasi(
            f"{kural['id']}: izinli_kume denetimi ama 'izinli_kume' alani yok"
        )
    return (str(deger) not in set(kume)), _kisalt(str(deger))


def _isleyici_sozluk(deger, kural, dosya) -> tuple[bool, str | None]:
    """Metinde sozlukteki yanlis kullanimlardan biri geciyor mu.

    Sozluk kuralin `sozluk` alanindan gelir. Bu alani tasiyan aktif kural
    su an YOK (ME-10 uygulanir=false); isleyici gercek veriyle
    sinanmamistir.
    """
    sozluk = kural.get("sozluk")
    if not sozluk:
        raise KuralYapilandirmaHatasi(
            f"{kural['id']}: sozluk denetimi ama 'sozluk' alani yok"
        )
    for parca in _metin_parcalari(deger, kural):
        for yanlis in sozluk:
            if yanlis.lower() in parca.lower():
                return True, _kisalt(yanlis)
    return False, None


def _isleyici_dogru_olmali(deger, kural, dosya) -> tuple[bool, str | None]:
    """Mantiksal alan True mu.

    B-01 icin eklendi: baslik.tc_var bir bool, uzerinde regex kosturulamaz.
    B-01 su an uygulanir=false (ayristirici baslik blogunu uretmiyor);
    isleyici gercek veriyle sinanmamistir.
    """
    return (deger is not True), None


ISLEYICILER = {
    "bos_olmamali": _isleyici_bos_olmamali,
    "bos_liste_olmamali": _isleyici_bos_liste_olmamali,
    "regex_bulunmali": _isleyici_regex_bulunmali,
    "regex_bulunmamali": _isleyici_regex_bulunmamali,
    "alan_esitligi": _isleyici_alan_esitligi,
    "izinli_kume": _isleyici_izinli_kume,
    "sozluk": _isleyici_sozluk,
    "dogru_olmali": _isleyici_dogru_olmali,
}

# Motor degismezinin ISTISNASI olan turler.
BOSLUK_DENETLEYENLER = frozenset({"bos_olmamali", "bos_liste_olmamali"})


# =============================================================================
# Yardimcilar
# =============================================================================


class KuralYapilandirmaHatasi(Exception):
    """kurallar.json bozuk ya da eksik. Sessizce yutulmaz."""


def _metin_parcalari(deger: Any, kural: dict) -> list[str]:
    """Denetlenecek metin parcalarini verir.

    liste_alani tanimliysa deger bir nesne listesidir (ornek: I-04 ->
    ustveri.ilgi, her Ilgi nesnesinin `ham` alani). O zaman her elemanin
    ilgili alani ayri bir parca olur.
    """
    liste_alani = kural.get("liste_alani")
    if liste_alani:
        if deger is None:
            return []
        parcalar = []
        for eleman in deger:
            ic = getattr(eleman, liste_alani, None)
            if ic:
                parcalar.append(str(ic))
        return parcalar
    if deger is None:
        return []
    return [str(deger)]


def _ilk_parca(deger: Any, kural: dict) -> str:
    parcalar = _metin_parcalari(deger, kural)
    return parcalar[0] if parcalar else ""


def _kisalt(metin: str | None, sinir: int = 300) -> str | None:
    if not metin:
        return None
    metin = " ".join(metin.split())
    return metin[:sinir]


def _bos_mu(deger: Any, kural: dict) -> bool:
    """Motor degismezi icin: denetlenecek bir sey var mi.

    Bilerek dar tutuldu — asil bosluk kararini Dosya.alan_dolu_mu() veriyor.
    Burada yalnizca liste/dize duzeyinde bakiliyor.
    """
    if deger is None:
        return True
    if kural.get("liste_alani"):
        return len(_metin_parcalari(deger, kural)) == 0
    if isinstance(deger, str):
        return not deger.strip()
    if isinstance(deger, (list, tuple, dict, set)):
        return len(deger) == 0
    return False


# =============================================================================
# Motor
# =============================================================================


class KuralMotoru:
    """kurallar.json'u yukler ve bir Dosya uzerinde kosturur."""

    def __init__(self, kural_dosyasi: Path | str | None = None) -> None:
        yol = Path(kural_dosyasi) if kural_dosyasi else VARSAYILAN_KURAL_DOSYASI
        if not yol.exists():
            raise KuralYapilandirmaHatasi(
                f"Kural dosyasi bulunamadi: {yol}\n"
                f"  python araclar/kural_donustur.py calistirin."
            )
        govde = json.loads(yol.read_text(encoding="utf-8"))
        self.kaynak = yol
        self.ust = govde.get("_ust", {})
        self.tum_kurallar: list[dict] = govde["kurallar"]
        self.kurallar: list[dict] = [k for k in self.tum_kurallar if k.get("uygulanir")]
        self._hazirla()

    # -- yukleme --------------------------------------------------------------

    def _hazirla(self) -> None:
        """Desenleri BIR KEZ derler ve yapilandirma hatalarini erkenden yakalar.

        Belge basina yeniden derlemek 300 belge x 18 kural = 5400 gereksiz
        derleme demek. Ayrica bozuk bir kural ilk belgede degil, yukleme
        aninda ortaya cikmali.
        """
        for k in self.kurallar:
            denetim = k.get("denetim")
            if denetim == "ozel_fonksiyon":
                ad = k.get("yontem_adi")
                fn = OZEL_FONKSIYONLAR.get(ad)
                if fn is None:
                    raise KuralYapilandirmaHatasi(
                        f"{k['id']}: uygulanir=true ama '{ad}' ozel fonksiyonu "
                        f"kural_ozel.OZEL_FONKSIYONLAR icinde yok. "
                        f"Ya fonksiyonu yazin ya kurali uygulanir=false yapin."
                    )
                k["_fonksiyon"] = fn
                continue
            if denetim not in ISLEYICILER:
                raise KuralYapilandirmaHatasi(
                    f"{k['id']}: bilinmeyen denetim turu {denetim!r}"
                )
            if denetim in ("regex_bulunmali", "regex_bulunmamali"):
                desen = k.get("desen")
                if not desen:
                    raise KuralYapilandirmaHatasi(f"{k['id']}: regex kurali ama desen yok")
                # Satir capali desenler cok satirli metinde MULTILINE ister.
                # Satir basindaki inline bayraklar '(?i)' atlanarak bakilir.
                govde = re.sub(r"^\(\?[aiLmsux]+\)", "", desen)
                bayrak = re.MULTILINE if govde.startswith("^") else 0
                k["_derlenmis"] = re.compile(desen, bayrak)

    @property
    def uygulanan_kural_sayisi(self) -> int:
        return len(self.kurallar)

    @property
    def kapsam_disi_kural_sayisi(self) -> int:
        """kurallar.json'da uygulanir=false olanlar. Raporda gorunur."""
        return len(self.tum_kurallar) - len(self.kurallar)

    # -- yol cozumleme --------------------------------------------------------

    @staticmethod
    def _yol_coz(kural: dict, hedef: str) -> str | None:
        """Kuralin bu hedefteki alan yolunu verir.

        yol ya DIZE ya SOZLUK'tur. Sozlukse anahtarlar gelen/giden. Motorda
        GIZLI ESLEME YOKTUR: ceviri kuralin icinde yazilidir, okuyan gorur.
        """
        yol = kural.get("yol")
        if yol is None:
            return None
        if isinstance(yol, str):
            return yol
        if isinstance(yol, dict):
            return yol.get(hedef)
        raise KuralYapilandirmaHatasi(
            f"{kural['id']}: yol ne dize ne sozluk: {yol!r}"
        )

    # -- kosturma -------------------------------------------------------------

    def calistir(self, dosya: Dosya, hedef: str = "gelen") -> MotorSonucu:
        if hedef not in HEDEFLER:
            raise ValueError(f"hedef 'gelen' ya da 'giden' olmali, verilen: {hedef!r}")

        rapor = LinterRaporu()
        atlamalar: list[AtlamaKaydi] = []
        belge_turu = dosya.deger_al("siniflandirma.belge_turu")

        for kural in self.kurallar:
            kid = kural["id"]

            # 1) Hedef — kural bu yone uygulaniyor mu
            if hedef not in kural.get("hedef", ["gelen"]):
                atlamalar.append(AtlamaKaydi(kid, AtlamaSebebi.HEDEF_DISI, hedef))
                continue

            # 2) Kapsam — belge turu kuralin kapsaminda mi
            kapsam = kural.get("kapsam")
            if kapsam and not kapsama_girer_mi(belge_turu, kapsam):
                atlamalar.append(
                    AtlamaKaydi(kid, AtlamaSebebi.KAPSAM_DISI, f"{belge_turu} !~ {kapsam}")
                )
                continue

            # 3) Yol cozumleme
            yol = self._yol_coz(kural, hedef)
            if yol is None:
                atlamalar.append(AtlamaKaydi(kid, AtlamaSebebi.YOL_YOK, hedef))
                continue
            kural["_cozulmus_yol"] = yol
            deger = dosya.deger_al(yol)

            # 4) MOTOR DEGISMEZI — alan bossa atla
            denetim = kural["denetim"]
            if denetim not in BOSLUK_DENETLEYENLER and _bos_mu(deger, kural):
                atlamalar.append(AtlamaKaydi(kid, AtlamaSebebi.ALAN_BOS, yol))
                continue

            # 5) Denetle
            isleyici = kural.get("_fonksiyon") or ISLEYICILER[denetim]
            cikti = isleyici(deger, kural, dosya)
            # Ozel fonksiyon None donerse: denetim icin gereken veriyi
            # bulamadi. Motor degismezinin uzantisi — atlanir, uydurulmaz.
            if cikti is None:
                atlamalar.append(
                    AtlamaKaydi(kid, AtlamaSebebi.VERI_YOK, kural.get("yontem_adi"))
                )
                continue
            ihlal, alinti = cikti
            rapor.denetlenen_kural_sayisi += 1
            if ihlal:
                rapor.bulgular.append(self._bulgu(kural, yol, alinti, dosya))

        rapor.atlanan_kural_sayisi = len(atlamalar)
        return MotorSonucu(rapor=rapor, atlamalar=atlamalar)

    # -- bulgu uretimi --------------------------------------------------------

    @staticmethod
    def _bulgu(kural: dict, yol: str, alinti: str | None, dosya: Dosya) -> LinterBulgusu:
        """Kuraldan bir LinterBulgusu kurar.

        `konum` ve yedek `alinti` ayristiricinin biraktigi kanittan gelir —
        boylece kullanici bulgunun belgede NEREDE oldugunu gorur.
        """
        kanit = dosya.kanit.get(yol) if isinstance(dosya.kanit, dict) else None
        baslik = kural.get("baslik") or kural["id"]
        if kural.get("baslik_kesik"):
            # Kaynak tabloda aciklama '…' ile kesik. Yarim cumleyi tamamlamak
            # UYDURMA olur; kesik oldugu acikca isaretlenir.
            baslik = baslik.rstrip("…").rstrip() + " […]"

        return LinterBulgusu(
            kural_id=kural["id"],
            baslik=_kisalt(baslik, 200) or kural["id"],
            onem=Onem(kural["agirlik"]),
            aciklama=None,
            dayanak=_kisalt(kural.get("dayanak"), 1000),
            alan=yol,
            alinti=alinti or (_kisalt(kanit.alinti) if kanit else None),
            konum=kanit.konum if kanit else None,
            duzeltme_onerisi=None,
        )

    # -- tani -----------------------------------------------------------------

    def ozet(self) -> str:
        from collections import Counter

        sayim = Counter(k["denetim"] for k in self.kurallar)
        satirlar = [
            f"kaynak                  {self.kaynak}",
            f"uretim                  {self.ust.get('uretim_tarihi', '?')}",
            f"uygulanan kural         {self.uygulanan_kural_sayisi}",
            f"kapsam disi kural       {self.kapsam_disi_kural_sayisi}",
            "denetim turleri:",
        ]
        for tur, adet in sayim.most_common():
            satirlar.append(f"    {tur:22} {adet}")
        kullanilmayan = sorted(set(ISLEYICILER) - set(sayim))
        if kullanilmayan:
            satirlar.append(
                "aktif kurali OLMAYAN isleyiciler (gercek veriyle sinanmadi): "
                + ", ".join(kullanilmayan)
            )
        return "\n".join(satirlar)
