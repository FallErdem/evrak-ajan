#!/usr/bin/env python3
"""kural_listesi.md  ->  veri/kurallar.json

Depo kokunden ELLE calistirilan bir betiktir. src/ altina konmaz, hicbir
modul bunu ice aktarmaz. Kural motoru yalnizca uretilen JSON'u okur.

    python araclar/kural_donustur.py

Neyi yapar:
  1  kural_listesi.md tablosunu BORU GUVENLI ayristirir (7 kuralin regex'i
     '|' iceriyor; naif bolme 104 yerine 97 kural verir ve ME-02 kaybolur)
  2  'Nasil' sutunundan denetim turunu cikarir (8 tur)
  3  Regex'lerin CIFT KACISINI tek kaciga indirir ('\\\\s' -> '\\s')
  4  veri/kural_ekleri.json'daki insan kararlarini (yol/hedef/kapsam) bindirir
  5  Her seyi dogrular; TEK BIR DOGRULAMA DUSERSE JSON YAZILMAZ, cikis 1

Yarim cikti uretip devam etmek yok. Sessiz kirilma bu projede en pahali
hata turu (IM-01 yolu aylarca kirikti ve motor hicbir sey bulmadi).
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "src"))

from veri_yapisi import ALAN_YOLLARI, KATEGORILER, GelenTur  # noqa: E402

# kural_listesi.md deponun neresinde durdugu net degil; sirayla aranir.
# Bulunamazsa komut satirindan verilebilir:
#     python araclar/kural_donustur.py yol/kural_listesi.md
ARAMA_YERLERI = (
    KOK / "kural_listesi.md",
    KOK / "belgeler" / "kural_listesi.md",
    KOK / "veri" / "kural_listesi.md",
    KOK / "docs" / "kural_listesi.md",
    KOK / "belgeler" / "kurallar" / "kural_listesi.md",
)

EKLER = KOK / "veri" / "kural_ekleri.json"
CIKTI = KOK / "veri" / "kurallar.json"

SURUM = "1.0.0"


def kaynak_bul(argv: list[str]) -> Path | None:
    """Komut satiri once, sonra bilinen konumlar, sonra derin arama."""
    if len(argv) > 1:
        elle = Path(argv[1]).expanduser().resolve()
        return elle if elle.exists() else None

    for y in ARAMA_YERLERI:
        if y.exists():
            return y

    # Son care: depo agacinda ara (.git, .venv, node_modules disinda)
    atla = {".git", ".venv", "venv", "node_modules", "__pycache__", "site-packages"}
    for y in KOK.rglob("kural_listesi.md"):
        if not (set(y.parts) & atla):
            return y
    return None

# -----------------------------------------------------------------------------
# 1. Boru guvenli satir ayristirma
# -----------------------------------------------------------------------------

# Satirin IKI UCUNDAN capa atilir; ortasi serbest birakilir. Regex icindeki
# '|' karakteri yalnizca ortada bulunabilir, o yuzden uclar guvenli.
_SATIR = re.compile(
    r"^\|\s*\*\*(?P<id>[A-ZÇĞİÖŞÜ]{1,3}-\d{2})\*\*\s*\|"      # | **S-01** |
    r"(?P<orta>.*)"                                            # ne denetliyor | nasil
    r"\|\s*(?P<agirlik>hata|uyari|bilgi)\s*\|"                 # | hata |
    r"(?P<dayanak>[^|]*)\|\s*$"                                # | Y 11/1 |
)

# 'Nasil' sutununun baslangic isaretleri. Orta blok bunlarin ILKINDE ikiye
# bolunur; solda aciklama, sagda yontem kalir.
_YONTEM_BASI = re.compile(
    r"\|\s*(?=özel fonksiyon|bulunmalı:|bulunmamalı:|sözlük araması|`)"
)

DENETIM_TURLERI = (
    "bos_olmamali",
    "bos_liste_olmamali",
    "regex_bulunmali",
    "regex_bulunmamali",
    "alan_esitligi",
    "izinli_kume",
    "sozluk",
    "dogru_olmali",
    "ozel_fonksiyon",
)


def _denetim_turu(nasil: str) -> str:
    n = nasil.lower()
    if n.startswith("özel fonksiyon"):
        return "ozel_fonksiyon"
    if n.startswith("bulunmalı"):
        return "regex_bulunmali"
    if n.startswith("bulunmamalı"):
        return "regex_bulunmamali"
    if "boş liste olmamalı" in n:
        return "bos_liste_olmamali"
    if "boş olmamalı" in n:
        return "bos_olmamali"
    if "izinli küme" in n or "∈" in n:
        return "izinli_kume"
    if "sözlük araması" in n:
        return "sozluk"
    if "=" in n:
        return "alan_esitligi"
    raise ValueError(f"Denetim turu cozulemedi: {nasil!r}")


def _desen_cikar(nasil: str) -> str | None:
    """Ters tirnak icindeki regex'i alir. Kacis DONUSTURULMEZ.

    2026-08-22, olculdu: kural_listesi.md'deki desenler TEK kacisli ve
    dogrudan derlenebilir durumda. B-01 ham bayt dizisi:

        ' ^ \\ s * T \\ . C \\ . \\ s * $ '     ters egik cizgi adedi: 4

    Yani '\\s' bir kacis dizisi, iki ayri karakter degil.

    Onceki bir taslakta burada `d.replace("\\\\", "\\")` vardi. Yanlisti ve
    S-04'u BOZUYORDU: o kuralin deseni `[/\\\\_,;]` ve icindeki cift ters
    egik cizgi KASITLI - karakter kumesine ters egik cizginin kendisini
    koyuyor. Donusum onu kumeden silerdi. Kural yine derlenir, yine calisir,
    ama ters egik cizgi tasiyan sayilari artik yakalamazdi.

    Ders: bir donusum uygulamadan once, donusturulecek seyin gercekten
    orada oldugunu ham bayt duzeyinde dogrula.
    """
    ic = re.findall(r"`([^`]+)`", nasil)
    if not ic:
        return None
    d = ic[0].strip()
    if len(d) >= 2 and d[0] == d[-1] == "'":
        d = d[1:-1]
    return d


def _yontem_adi(nasil: str) -> str | None:
    """Ozel fonksiyon kurallarinda fonksiyon adini alir."""
    m = re.search(r"özel fonksiyon\s+`([^`]+)`", nasil)
    return m.group(1) if m else None


def markdown_oku(yol: Path) -> list[dict]:
    ham = yol.read_text(encoding="utf-8")
    kurallar: list[dict] = []
    for satir_no, satir in enumerate(ham.split("\n"), start=1):
        m = _SATIR.match(satir)
        if m is None:
            continue
        orta = m.group("orta")
        bol = _YONTEM_BASI.search(orta)
        if bol is None:
            raise ValueError(
                f"satir {satir_no}: '{m.group('id')}' yontem sutunu bulunamadi"
            )
        aciklama = orta[: bol.start()].strip()
        nasil = orta[bol.end():].strip()
        denetim = _denetim_turu(nasil)
        # desen YALNIZCA regex kurallarinda anlamlidir. Diger turlerde ters
        # tirnak icinde alan yolu ya da fonksiyon adi duruyor; onlari desen
        # diye kaydetmek okuyani yaniltir ve motorun yanlis islevi
        # cagirmasina zemin hazirlar.
        desen = (
            _desen_cikar(nasil)
            if denetim in ("regex_bulunmali", "regex_bulunmamali")
            else None
        )
        kurallar.append(
            {
                "id": m.group("id"),
                "kategori": m.group("id").split("-")[0],
                "baslik": aciklama,
                "baslik_kesik": aciklama.endswith("…"),
                "denetim": denetim,
                "desen": desen,
                "yontem_adi": _yontem_adi(nasil),
                "agirlik": m.group("agirlik"),
                "dayanak": m.group("dayanak").strip(),
                "_nasil_ham": nasil,
                "_satir": satir_no,
            }
        )
    return kurallar


# -----------------------------------------------------------------------------
# 2. Insan kararlarinin bindirilmesi
# -----------------------------------------------------------------------------

BINDIRILEBILIR = (
    "yol", "denetim", "yontem_adi", "liste_alani", "yol_bolum",
    "karsi_yol", "hedef", "kapsam", "uygulanir", "not",
    "talep_edilebilir", "soru",
)


def bindir(kurallar: list[dict], ekler: dict) -> list[dict]:
    tablo = ekler["kurallar"]
    bilinen = {k["id"] for k in kurallar}
    fazla = set(tablo) - bilinen
    if fazla:
        raise ValueError(
            f"kural_ekleri.json'da kural_listesi.md'de olmayan kimlik(ler): "
            f"{sorted(fazla)}"
        )

    for k in kurallar:
        ek = tablo.get(k["id"], {})
        for alan in BINDIRILEBILIR:
            if alan in ek:
                k[alan] = ek[alan]

        # Varsayilanlar — bindirmeden SONRA, bindirmeyi ezmemeleri icin.
        k.setdefault("yol", None)
        k.setdefault("liste_alani", None)
        k.setdefault("yol_bolum", None)
        k.setdefault("karsi_yol", None)
        k.setdefault("hedef", ["gelen"])
        k.setdefault("kapsam", None)
        k.setdefault("not", None)
        k.setdefault("talep_edilebilir", False)
        k.setdefault("soru", None)
        if "uygulanir" not in k:
            # Ozel fonksiyonlar Asama D; jenerikler ekler dosyasindan gelir.
            k["uygulanir"] = False
            if k["denetim"] == "ozel_fonksiyon":
                k["not"] = (
                    "Asama D: ozel fonksiyon yazilmadi. "
                    "Motor kurali atlar ve atladigini raporlar."
                )
    return kurallar


# -----------------------------------------------------------------------------
# 3. Dogrulama — hepsi gecmezse JSON YAZILMAZ
# -----------------------------------------------------------------------------

GECERLI_TURLER = {str(t) for t in GelenTur}


def _yol_listesi(k: dict) -> list[str]:
    """Bir kuralin denetlenecek butun yollarini duz liste olarak verir."""
    y = k["yol"]
    if y is None:
        return []
    if isinstance(y, str):
        return [y]
    if isinstance(y, dict):
        return list(y.values())
    raise ValueError(f"{k['id']}: yol ne dize ne sozluk: {y!r}")


def dogrula(kurallar: list[dict]) -> list[str]:
    hatalar: list[str] = []
    ekle = hatalar.append

    if len(kurallar) != 104:
        ekle(f"Kural sayisi 104 degil: {len(kurallar)}")

    kimlikler = [k["id"] for k in kurallar]
    for kid in set(kimlikler):
        if kimlikler.count(kid) > 1:
            ekle(f"{kid}: kimlik {kimlikler.count(kid)} kez geciyor")

    for k in kurallar:
        kid = k["id"]

        if k["denetim"] not in DENETIM_TURLERI:
            ekle(f"{kid}: bilinmeyen denetim turu {k['denetim']!r}")

        if not k["dayanak"]:
            ekle(f"{kid}: dayanak bos")

        # soru, karsi tarafa gidecek cumledir. Istenemeyecek bir eksik icin
        # soru yazmak, arayuzde gosterilemeyecek metin uretmek demektir.
        if k.get("soru") and not k.get("talep_edilebilir"):
            ekle(f"{kid}: soru yazilmis ama talep_edilebilir=false")
        if k.get("talep_edilebilir") and not k.get("soru"):
            ekle(f"{kid}: talep_edilebilir=true ama soru yazilmamis")

        if not k["baslik"]:
            ekle(f"{kid}: baslik bos")

        hedef = k["hedef"]
        if not isinstance(hedef, list) or not hedef:
            ekle(f"{kid}: hedef liste degil ya da bos: {hedef!r}")
        elif set(hedef) - {"gelen", "giden"}:
            ekle(f"{kid}: hedefte tanimsiz deger: {hedef!r}")

        kapsam = k["kapsam"]
        if kapsam is not None and kapsam not in KATEGORILER and kapsam not in GECERLI_TURLER:
            ekle(f"{kid}: kapsam ne kategori ne tur adi: {kapsam!r}")

        # -- yalnizca uygulanacak kurallarda gecerli --
        if not k["uygulanir"]:
            if not k["not"]:
                ekle(f"{kid}: uygulanir=false ama gerekce (not) yazilmamis")
            continue

        if k["denetim"] == "ozel_fonksiyon":
            if not k["yontem_adi"]:
                ekle(f"{kid}: ozel fonksiyon ama yontem adi yok")
            continue

        yollar = _yol_listesi(k)
        if not yollar:
            ekle(f"{kid}: uygulanacak jenerik kural ama yol yok")
        for y in yollar:
            if y not in ALAN_YOLLARI:
                ekle(f"{kid}: yol ALAN_YOLLARI'nda YOK -> {y!r}")
        if k["karsi_yol"] and k["karsi_yol"] not in ALAN_YOLLARI:
            ekle(f"{kid}: karsi_yol ALAN_YOLLARI'nda YOK -> {k['karsi_yol']!r}")

        # Sozluk yol, hedefteki her sey icin anahtar tasimali
        if isinstance(k["yol"], dict):
            eksik = set(hedef) - set(k["yol"])
            if eksik:
                ekle(f"{kid}: yol sozlugunde {sorted(eksik)} anahtari yok")

        if k["denetim"] in ("regex_bulunmali", "regex_bulunmamali"):
            if not k["desen"]:
                ekle(f"{kid}: regex kurali ama desen yok")
            else:
                try:
                    re.compile(k["desen"])
                except re.error as e:
                    ekle(f"{kid}: desen derlenmiyor ({e}) -> {k['desen']!r}")
                # NOT: "cift kacis kalmis mi" diye bir denetim YOK. S-04'un
                # deseni `[/\\_,;]` ve oradaki cift ters egik cizgi kasitli.
                # Derlenebilirlik + duman testi yeterli guvence.

        if k["denetim"] == "alan_esitligi" and not k["karsi_yol"]:
            ekle(f"{kid}: alan_esitligi ama karsi_yol yok")

    return hatalar


# -----------------------------------------------------------------------------
# 4. Duman testi — desenler GERCEK metinde calisiyor mu
# -----------------------------------------------------------------------------

DUMAN = (
    # (kural, denenecek metin, eslesmeli mi)
    ("B-01", "T.C.", True),
    ("B-01", "IC.", False),
    ("ME-02", "...ilan edilmesi hususunda gereğini rica ederim.", True),
    ("ME-02", "...bilgilerinize sunulur.", False),
    ("ME-15", "toplam 1500.00 TL ödenmiştir", True),
    ("ME-15", "toplam 1.500,00 TL ödenmiştir", False),
    ("ME-18", "kurumumuz, ve müdürlüğümüz tarafından", True),
    ("ME-18", "kurumumuz ve müdürlüğümüz tarafından", False),
    ("G-04", "ACİL", True),
    ("G-04", "Ivedik Caddesi No: 25", False),
    ("S-04", "E-24304062\\807.01", True),
    ("S-04", "E-24304062-807.01-57692713", False),
    ("S-05", "Sayı: 2026/103", True),
    ("S-05", "E-24304062-807.01-57692713", False),
)


def duman_testi(kurallar: list[dict]) -> list[str]:
    """Desenin BEKLENEN metinde eslesip beklenmeyende eslesmedigini kanitlar.

    Cift kacis duzeltmesi calismazsa B-01 'T.C.' metninde eslesmez ve bu
    test duser. Derlenebilirlik yetmez: '\\\\s' de derlenir ama hicbir sey
    bulmaz.
    """
    hatalar: list[str] = []
    sozluk = {k["id"]: k for k in kurallar}
    for kid, metin, beklenen in DUMAN:
        k = sozluk.get(kid)
        if k is None or not k["desen"]:
            hatalar.append(f"duman: {kid} bulunamadi ya da deseni yok")
            continue
        # B-01'in deseni satir capali; cok satirli metinde MULTILINE gerekir.
        bayrak = re.MULTILINE if k["desen"].startswith("^") else 0
        bulundu = re.search(k["desen"], metin, bayrak) is not None
        if bulundu is not beklenen:
            hatalar.append(
                f"duman: {kid} deseni {metin!r} metninde "
                f"{'eslesmeliydi' if beklenen else 'eslesmemeliydi'}"
            )
    return hatalar


# -----------------------------------------------------------------------------
# 5. Ana akis
# -----------------------------------------------------------------------------

def _ozet(kurallar: list[dict]) -> None:
    from collections import Counter

    uyg = [k for k in kurallar if k["uygulanir"]]
    atl = [k for k in kurallar if not k["uygulanir"]]

    print(f"\n  toplam kural       {len(kurallar)}")
    print(f"  uygulanir          {len(uyg)}")
    print(f"  atlanan            {len(atl)}")
    print(f"  basligi kesik      {sum(1 for k in kurallar if k['baslik_kesik'])}")

    print("\n  DENETIM TURU (uygulanan)")
    for tur, adet in Counter(k["denetim"] for k in uyg).most_common():
        print(f"    {tur:22} {adet}")

    print("\n  HEDEF (uygulanan)")
    for h, adet in Counter(",".join(k["hedef"]) for k in uyg).most_common():
        print(f"    {h:22} {adet}")

    print("\n  AGIRLIK (uygulanan)")
    for a, adet in Counter(k["agirlik"] for k in uyg).most_common():
        print(f"    {a:22} {adet}")

    jenerik_atlanan = [k for k in atl if k["denetim"] != "ozel_fonksiyon"]
    if jenerik_atlanan:
        print("\n  ATLANAN JENERIK KURALLAR (gerekceli)")
        for k in jenerik_atlanan:
            print(f"    {k['id']:7} {k['not'][:96]}")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    print("kural_donustur - kural_listesi.md -> veri/kurallar.json\n")

    kaynak = kaynak_bul(argv)
    if kaynak is None:
        print("HATA: kural_listesi.md bulunamadi.\n")
        print("  Su konumlara bakildi:")
        for y in ARAMA_YERLERI:
            print(f"    {y}")
        print(f"    ve {KOK} agacinda derin arama yapildi.\n")
        print("  Cozum: dosyanin yolunu komut satirindan verin, ornek:")
        print("    python araclar/kural_donustur.py belgeler/kural_listesi.md")
        return 1

    if not EKLER.exists():
        print(f"HATA: {EKLER} bulunamadi.")
        print("  kural_ekleri.json dosyasini veri/ klasorune koyun.")
        return 1

    print(f"  kaynak : {kaynak}")
    print(f"  ekler  : {EKLER}\n")

    try:
        kurallar = markdown_oku(kaynak)
        ekler = json.loads(EKLER.read_text(encoding="utf-8"))
        kurallar = bindir(kurallar, ekler)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"HATA: {e}")
        return 1

    hatalar = dogrula(kurallar) + duman_testi(kurallar)
    if hatalar:
        print(f"DOGRULAMA DUSTU - {len(hatalar)} sorun. JSON YAZILMADI.\n")
        for h in hatalar:
            print(f"  {h}")
        return 1

    # Ic alanlar temizlenir; JSON motorun okuyacagi sey.
    for k in kurallar:
        k.pop("_nasil_ham", None)
        k.pop("_satir", None)

    govde = {
        "_ust": {
            "surum": SURUM,
            "uretim_tarihi": date.today().isoformat(),
            "kaynak": kaynak.name,
            "kaynak_sha256": hashlib.sha256(kaynak.read_bytes()).hexdigest(),
            "ekler": EKLER.name,
            "ekler_surum": ekler.get("_surum"),
            "toplam": len(kurallar),
            "uygulanir": sum(1 for k in kurallar if k["uygulanir"]),
            "_uyari": (
                "ELLE DUZENLENMEZ. Kaynak kural_listesi.md + "
                "veri/kural_ekleri.json. Degisiklik icin onlari duzenleyip "
                "python araclar/kural_donustur.py calistirin."
            ),
        },
        "kurallar": kurallar,
    }

    CIKTI.parent.mkdir(parents=True, exist_ok=True)
    CIKTI.write_text(
        json.dumps(govde, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"DOGRULAMA GECTI - {CIKTI} yazildi.")
    _ozet(kurallar)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
