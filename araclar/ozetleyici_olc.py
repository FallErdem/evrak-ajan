#!/usr/bin/env python3
"""Ozetleyici'yi TUR CESITLILIGINE gore secilmis bir kumede olcer.

Depo kokunden ELLE calistirilir. LLM CAGRISI YAPAR.

    python araclar/ozetleyici_olc.py              her turden 1 belge
    python araclar/ozetleyici_olc.py 2            her turden 2 belge

MALIYET: belge basina 1 cagri, ~600 token. Her turden 1 belge ~11 cagri.
Katman 3'un yaninda cok ucuz (orada belge basina 3-4 cagri vardi).

NEDEN TUR CESITLILIGI, RASTGELE DEGIL
-------------------------------------
Ozetleyici'nin istemi tek ve butun belge turlerinde ayni. Risk, bir tur
ailesinde calisip digerinde bozulmasi:

    kurum yazisi   talep + SONUC var      "sonucu yaz" ise yarar
    dilekce/itiraz talep var, SONUC YOK   sonuc uydurma riski

Rastgele orneklem 11 turun bazilarini hic getirmeyebilir. Bu yuzden her
turden en az bir belge secilir.

OLCULEN DORT SEY
----------------
1  UZUNLUK        talep ve ozet sema sinirini asiyor mu (kirpma tetikleniyor mu)
2  SAYISAL UYDURMA ozette gecen sayilar kaynakta var mi
3  YASAGA UYUM    istem "belgenin sayisini ve tarihini yazma" diyor;
                  uyuluyor mu? Ustveri sayisi/tarihi ozete sizmis mi
4  BASARISIZLIK   JSON hatasi, token kesilmesi, ag hatasi

Ucuncusu OLCULMEMIS bir varsayimdi: yasak istemde yazili ama uyuldugu
gosterilmedi. Sema enum'u zorlayabiliyor, serbest metni zorlayamiyor.

DURUSTLUK NOTU - RAPORA GIRECEK
-------------------------------
Ozetleme KALITESI (akicilik, kapsayicilik, anlamsal sadakat) bu olcumde
DEGERLENDIRILMIYOR. Cevap anahtari yok. Olculen sey bicim uyumu ve
sayisal uydurmadir; anlamsal carpitma (belgede "reddedilmistir" derken
ozette "kabul edilmistir" demek) yakalanamaz.
"""

from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "src"))
sys.path.insert(0, str(KOK / "araclar"))

from ayristirici import ayristir                                      # noqa: E402
from katman3_dene import yapilandirma_bul                             # noqa: E402
from kural_motoru_dogrula import dosya_kur, etiket_klasoru, klasor_bul  # noqa: E402
from llm_istemci import istemci_olustur                               # noqa: E402
from okuyucu import oku                                               # noqa: E402
from ozetleyici import OZET_SINIRI, TALEP_SINIRI, Ozetleyici          # noqa: E402

VARSAYILAN_YAPILANDIRMA = "yapilandirma.qwen.json"


def _sar(metin: str, genislik: int) -> list[str]:
    """Metni satirlara boler. Konsol ve dosya okunabilir kalsin diye."""
    import textwrap
    if not metin:
        return ["(bos)"]
    return textwrap.wrap(" ".join(metin.split()), width=genislik) or ["(bos)"]


def _sar(metin: str, genislik: int) -> list[str]:
    """Uzun metni okunabilir satirlara boler. Kelime ortasindan kesmez."""
    if not metin:
        return ["(bos)"]
    satirlar: list[str] = []
    su_an = ""
    for kelime in metin.split():
        if su_an and len(su_an) + len(kelime) + 1 > genislik:
            satirlar.append(su_an)
            su_an = kelime
        else:
            su_an = f"{su_an} {kelime}".strip()
    if su_an:
        satirlar.append(su_an)
    return satirlar


def ornek_sec(etiket_klasor: Path, tur_basina: int) -> list[Path]:
    """Her belge turunden `tur_basina` belge secer.

    Kusursuz belgeler ONCE gelir: kusurlu belgede etiket ile belge kasten
    celisiyor olabilir ve ozetin kaynagi BELGEDIR. Kusursuz belge yoksa
    kusurlu da alinir; secim numaraya gore sirali, yani tekrarlanabilir.
    """
    turlere: dict[str, list[tuple[int, Path]]] = {}
    for yol in sorted(etiket_klasor.glob("etiket_*.json")):
        try:
            e = json.loads(yol.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if e.get("pdf_bicimi") != "metin_katmanli":
            continue
        tur = e.get("belge_turu") or "bilinmiyor"
        oncelik = 0 if e.get("kusur") is None else 1
        turlere.setdefault(tur, []).append((oncelik, yol))

    secilen: list[Path] = []
    for tur in sorted(turlere):
        sirali = [y for _o, y in sorted(turlere[tur], key=lambda x: (x[0], x[1].name))]
        secilen.extend(sirali[:tur_basina])
    return secilen


def yasak_ihlali(metin: str, dosya) -> list[str]:
    """Ozette belgenin KENDI sayisi ya da tarihi geciyor mu.

    Istem bunlari yasakliyor cunku arayuz o alanlari ayrica gosteriyor ve
    tekrar etmek ozeti gereksiz uzatiyor (olculdu: yasaksiz surumde ozet
    329 karakter, yasakli surumde 200).

    Tarih iki bicimde de aranir: '2026-04-14' (ISO) ve '14.04.2026'
    (belgede yazan bicim). Yalnizca birine bakmak ihlali kacirir.
    """
    if not metin:
        return []
    ihlaller: list[str] = []

    sayi = dosya.deger_al("ustveri.sayi")
    if sayi and str(sayi) in metin:
        ihlaller.append(f"sayi: {sayi}")

    tarih = dosya.deger_al("ustveri.tarih")
    if tarih:
        bicimler = {str(tarih)}
        try:
            bicimler.add(tarih.strftime("%d.%m.%Y"))
            bicimler.add(tarih.strftime("%d/%m/%Y"))
        except AttributeError:
            pass
        for b in bicimler:
            if b and b in metin:
                ihlaller.append(f"tarih: {b}")
                break
    return ihlaller


def main(argv: list[str]) -> int:
    tur_basina = next((int(a) for a in argv if a.isdigit()), 1)
    yap_adi = next((a for a in argv if a.endswith(".json")), VARSAYILAN_YAPILANDIRMA)

    yap = yapilandirma_bul(yap_adi)
    if yap is None:
        print(f"HATA: {yap_adi} bulunamadi.")
        return 1

    pdf_klasoru = klasor_bul()
    ek_klasoru = etiket_klasoru(pdf_klasoru)
    secilen = ornek_sec(ek_klasoru, tur_basina)
    if not secilen:
        print("HATA: orneklem bos.")
        return 1

    istemci = istemci_olustur(yap)
    ozetleyici = Ozetleyici(istemci)

    cikti = KOK / "ozetleyici_olc_sonuc.txt"
    with cikti.open("w", encoding="utf-8") as f:
        def yaz(s: str = "") -> None:
            print(s)
            f.write(s + "\n")

        yaz("OZETLEYICI OLCUMU - TUR CESITLILIGI")
        yaz("=" * 72)
        yaz(f"  yapilandirma  : {yap}")
        yaz(f"  orneklem      : {len(secilen)} belge, tur basina {tur_basina}")
        yaz(f"  sema sinirlari: talep {TALEP_SINIRI} · ozet {OZET_SINIRI}")
        yaz("")

        basarili = 0
        basarisiz: list[str] = []
        talep_uzunluk: list[int] = []
        ozet_uzunluk: list[int] = []
        kirpilan: list[str] = []
        sayi_tasiyan: list[str] = []
        uydurma: list[str] = []
        yasak: list[str] = []
        tur_dagilimi: Counter = Counter()
        # Gozle kontrol icin: her belgenin govdesi ve uretilen ozet.
        # Sayilar bicim uyumunu olcuyor ama anlamsal sadakati OLCEMIYOR;
        # o yalnizca okunarak degerlendirilebilir. Bu yuzden girdi ve cikti
        # birlikte kaydediliyor.
        dokum: list[dict] = []
        t0 = time.perf_counter()

        for i, ey in enumerate(secilen, 1):
            no = ey.stem.replace("etiket_", "")
            pdf = pdf_klasoru / f"belge_{no}.pdf"
            if not pdf.exists():
                continue
            e = json.loads(ey.read_text(encoding="utf-8"))
            tur = e.get("belge_turu") or "?"

            r = oku(str(pdf))
            if r.hata or not r.ayrilmis:
                basarisiz.append(f"{no} ({tur}): okuma -> {r.hata}")
                continue
            a = ayristir(r.ayrilmis.govde_satirlari,
                         dipnot_var=r.ayrilmis.dipnot_bulundu)
            d = dosya_kur(r, a, e)

            sonuc = ozetleyici.calistir(d)
            tur_dagilimi[tur] += 1

            if not sonuc.basarili:
                basarisiz.append(
                    f"{no} ({tur}): {sonuc.uyarilar[0] if sonuc.uyarilar else 'bos cikti'}"
                )
                print(f"  ... {i}/{len(secilen)}  belge_{no} {tur} -> BASARISIZ",
                      file=sys.stderr)
                continue

            basarili += 1
            talep_uzunluk.append(len(sonuc.talep))
            ozet_uzunluk.append(len(sonuc.ozet))
            if any("kırpıldı" in u for u in sonuc.uyarilar):
                kirpilan.append(f"{no} ({tur})")
            if sonuc.bulunan_sayilar:
                sayi_tasiyan.append(f"{no}:{','.join(sonuc.bulunan_sayilar[:3])}")
            if sonuc.dogrulanmayan:
                uydurma.append(f"{no} ({tur}): {', '.join(sonuc.dogrulanmayan)}")

            ihlal = yasak_ihlali(
                " ".join(x for x in (sonuc.talep, sonuc.ozet) if x), d
            )
            if ihlal:
                yasak.append(f"{no} ({tur}): {'; '.join(ihlal)}")

            dokum.append({
                "no": no,
                "tur": tur,
                "kusur": e.get("kusur"),
                "govde": (d.metin or "").strip(),
                "talep": sonuc.talep,
                "ozet": sonuc.ozet,
                "sayilar": sonuc.bulunan_sayilar,
                "dogrulanmayan": sonuc.dogrulanmayan,
                "ihlal": ihlal,
            })

            print(f"  ... {i}/{len(secilen)}  belge_{no} {tur} -> "
                  f"talep {len(sonuc.talep)} ozet {len(sonuc.ozet)}", file=sys.stderr)

        sure = time.perf_counter() - t0
        toplam = basarili + len(basarisiz)

        yaz("SONUC")
        yaz("-" * 72)
        yaz(f"  denenen belge         {toplam}")
        yaz(f"  basarili              {basarili}")
        yaz(f"  basarisiz             {len(basarisiz)}")
        for x in basarisiz:
            yaz(f"    {x[:105]}")
        yaz("")

        yaz("OLCUM 1 - UZUNLUK")
        yaz("-" * 72)
        if talep_uzunluk:
            yaz(f"  talep  en kisa {min(talep_uzunluk):4}  ortalama "
                f"{sum(talep_uzunluk)//len(talep_uzunluk):4}  en uzun "
                f"{max(talep_uzunluk):4}   (sinir {TALEP_SINIRI})")
            yaz(f"  ozet   en kisa {min(ozet_uzunluk):4}  ortalama "
                f"{sum(ozet_uzunluk)//len(ozet_uzunluk):4}  en uzun "
                f"{max(ozet_uzunluk):4}   (sinir {OZET_SINIRI})")
        yaz(f"  kirpilan              {len(kirpilan)}"
            + (f"  ({', '.join(kirpilan)})" if kirpilan else ""))
        yaz("")

        yaz("OLCUM 2 - SAYISAL UYDURMA")
        yaz("-" * 72)
        yaz(f"  ozetinde sayi gecen belge   {len(sayi_tasiyan)}/{basarili}")
        for x in sayi_tasiyan[:10]:
            yaz(f"    {x[:100]}")
        yaz(f"  UYDURMA sayi bulunan belge  {len(uydurma)}")
        for x in uydurma[:10]:
            yaz(f"    {x[:105]}")
        if not uydurma:
            yaz("    yok - ozetlerde kaynakta bulunmayan sayisal deger cikmadi")
        yaz("")

        yaz("OLCUM 3 - SAYI/TARIH YASAGINA UYUM")
        yaz("-" * 72)
        yaz(f"  yasagi ihlal eden belge     {len(yasak)}/{basarili}")
        for x in yasak[:12]:
            yaz(f"    {x[:105]}")
        if not yasak:
            yaz("    yok - hicbir ozette belgenin kendi sayisi/tarihi gecmiyor")
        yaz("")

        yaz("TUR DAGILIMI")
        yaz("-" * 72)
        for tur, adet in sorted(tur_dagilimi.items()):
            yaz(f"  {tur:24} {adet}")
        yaz("")

        yaz("DOKUM - GIRDI VE CIKTI")
        yaz("=" * 72)
        yaz("Asagidaki karsilastirma OLCULEN bir sey degil. Ozetleme kalitesi")
        yaz("(anlamsal sadakat, kapsayicilik) cevap anahtari olmadan sayiyla")
        yaz("olculemez; gozle okunmak icin veriliyor.")
        yaz("")
        for k in dokum:
            baslik = f"belge_{k['no']}  [{k['tur']}]"
            if k["kusur"]:
                baslik += f"  kusur={k['kusur']}"
            yaz(baslik)
            yaz(f"  GOVDE ({len(k['govde'])} karakter):")
            for parca in _sar(k["govde"], 66):
                yaz(f"    {parca}")
            yaz(f"  TALEP ({len(k['talep'] or '')}):")
            for parca in _sar(k["talep"] or "", 66):
                yaz(f"    {parca}")
            yaz(f"  OZET  ({len(k['ozet'] or '')}):")
            for parca in _sar(k["ozet"] or "", 66):
                yaz(f"    {parca}")
            if k["sayilar"]:
                ek = (f"DOGRULANMAYAN: {', '.join(k['dogrulanmayan'])}"
                      if k["dogrulanmayan"] else "hepsi dogrulandi")
                yaz(f"  sayilar: {', '.join(k['sayilar'])}   ({ek})")
            if k["ihlal"]:
                yaz(f"  YASAK IHLALI: {'; '.join(k['ihlal'])}")
            yaz("")

        yaz("MALIYET")
        yaz("-" * 72)
        yaz(f"  cagri sayisi          {getattr(istemci, 'cagri_sayisi', '?')}")
        yaz(f"  girdi token           {getattr(istemci, 'toplam_girdi', '?')}")
        yaz(f"  cikti token           {getattr(istemci, 'toplam_genel', '?')}")
        yaz(f"  sure                  {sure:.0f} sn")
        yaz("")
        yaz("NOT: Ozetleme KALITESI bu olcumde degerlendirilmiyor - cevap")
        yaz("anahtari yok. Olculen sey bicim uyumu ve sayisal uydurmadir.")
        yaz("")
        yaz(f"sonuc dosyasi: {cikti}")

    return 0 if not basarisiz else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
