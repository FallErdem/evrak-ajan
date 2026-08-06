#!/usr/bin/env python3
"""ADIM 1 — belge gövdesi üretim koşturucusu.

Yaptığı iş basit:

    talimat_vN.txt  +  sartname_NN.txt  ->  LLM  ->  ciktilar/MODEL/belge_NN.txt

TASARIM KARARLARI

K1 — Talimat ve şartname ayrı dosyalarda.
     Talimat 10 belgede aynı, şartname her belgede farklı. Ayrı tutunca
     talimattaki bir hata tek dosyada düzeltiliyor; ayrıca kayıt dosyasına
     hangi talimat sürümünün kullanıldığı yazılıyor. Sonra "belge 47 neden
     bozuk?" diye sorulduğunda hangi talimatla üretildiği bilinir.

K4 — Tekrar çalıştırma güvenli.
     Çıktı dosyası varsa o belge atlanır. 450 belgelik koşu 380'de çökerse
     tekrar başlattığınızda kaldığı yerden devam eder; ilk 380 için ikinci
     kez ödeme yapılmaz. Zorla üretmek için --yeniden.

K5 — Token bütçesi.
     Her belgeden sonra kümülatif token yazdırılır. Sınır aşılırsa koşu
     durur. Bir hata döngüsünün faturayı sessizce şişirmesini engeller.

K6 — Hız sınırında geri çekilme (istemcide) + belge atlanabilir.
     Bir belge üç denemede de başarısız olursa koşu durmaz; hata kaydedilir,
     sonraki belgeye geçilir. Eksikler sonra tamamlanır (bkz. K4).

K9 — Bu betik çıktıyı DENETLEMEZ.
     Kural kontrolü 1.2'deki mini linter'ın işi. Üretim ve denetim ayrı
     katmanlar; karıştırılırsa ikisi de ayrı ayrı test edilemez.

KULLANIM

    python kosum.py --kuru --hepsi        # istemleri kur, GÖNDERME (bedava)
    python kosum.py --belge 01            # tek belge
    python kosum.py --hepsi               # eksik olan hepsini üret
    python kosum.py --belge 01 --yeniden  # mevcut çıktının üzerine yaz
    python kosum.py --hepsi --bekleme 5   # çağrılar arasında 5 sn bekle
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# --- depo kökünü bul, src/ dizinini içe aktarma yoluna ekle ------------------
BURASI = Path(__file__).resolve().parent
DEPO_KOKU = BURASI.parent.parent
sys.path.insert(0, str(DEPO_KOKU))

from src.llm_istemci import LLMHatasi, LLMIstemci, yapilandirma_yukle  # noqa: E402

# --- yollar ------------------------------------------------------------------
ISTEMLER = BURASI / "istemler"
CIKTILAR = BURASI / "ciktilar"
KAYIT = BURASI / "kayit"
YAPILANDIRMA = DEPO_KOKU / "yapilandirma.json"

# Türkçe metinde kabaca 3 karakter ≈ 1 token. Yalnızca --kuru modunda,
# gönderilmeden önce büyüklük fikri vermek için kullanılıyor; faturaya
# esas olan sayı her zaman sunucudan dönen gerçek değerdir.
KABA_TOKEN_BOLENI = 3


# -----------------------------------------------------------------------------
# Dosya işleri
# -----------------------------------------------------------------------------


def talimat_dosyasini_bul() -> Path:
    """En yüksek sürümlü talimat_vN.txt dosyasını seçer.

    Sürüm numarası dosya adında tutuluyor ki eski talimatlar silinmesin:
    hangi çıktının hangi talimatla üretildiği kayıttan izlenebilsin.
    """
    adaylar = sorted(
        ISTEMLER.glob("talimat_v*.txt"),
        key=lambda p: int(re.search(r"_v(\d+)", p.stem).group(1)),
    )
    if not adaylar:
        raise SystemExit(f"HATA: {ISTEMLER} içinde talimat_vN.txt bulunamadı.")
    return adaylar[-1]


def sartname_listesi(secilen: list[str] | None) -> list[tuple[str, Path]]:
    """(belge_no, dosya_yolu) çiftleri döndürür."""
    hepsi = sorted(ISTEMLER.glob("sartname_*.txt"))
    if not hepsi:
        raise SystemExit(f"HATA: {ISTEMLER} içinde sartname_NN.txt bulunamadı.")

    esle = {p.stem.split("_")[-1]: p for p in hepsi}

    if secilen is None:
        return sorted(esle.items())

    sonuc = []
    for no in secilen:
        no = no.zfill(2)
        if no not in esle:
            raise SystemExit(
                f"HATA: sartname_{no}.txt yok. Mevcut: {', '.join(sorted(esle))}"
            )
        sonuc.append((no, esle[no]))
    return sonuc


def istemi_kur(talimat: str, sartname: str) -> str:
    """Talimat bloğunu ve şartname bloğunu birleştirir.

    Şartname sona konuyor. Sebebi ölçülmüş bir davranış: uzun istemlerde
    model sondaki içeriği daha iyi tutuyor, ve asıl değişken olan kısım
    şartname. Talimat sürümü sabit kaldığı için başta durması sorun değil.
    """
    return talimat.rstrip() + "\n\n" + sartname.strip() + "\n"


# -----------------------------------------------------------------------------
# Kayıt
# -----------------------------------------------------------------------------


def kayit_ekle(kayit_dosyasi: Path, satir: dict) -> None:
    """Kayıt dosyasına bir satır ekler (JSON Lines).

    Her belge ayrı satır olduğu için koşu ortasında çökme durumunda dosya
    bozulmuyor; o ana kadarki kayıtlar okunabilir kalıyor.
    """
    kayit_dosyasi.parent.mkdir(parents=True, exist_ok=True)
    with kayit_dosyasi.open("a", encoding="utf-8") as f:
        f.write(json.dumps(satir, ensure_ascii=False) + "\n")


def simdi() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# -----------------------------------------------------------------------------
# Ana akış
# -----------------------------------------------------------------------------


def main() -> int:
    ayrist = argparse.ArgumentParser(
        description="ADIM 1 belge gövdesi üretimi",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    grup = ayrist.add_mutually_exclusive_group(required=True)
    grup.add_argument("--belge", nargs="+", metavar="NO", help="belge numarası, ör. 01 07")
    grup.add_argument("--hepsi", action="store_true", help="tüm şartnameleri koş")

    ayrist.add_argument("--yeniden", action="store_true",
                        help="mevcut çıktının üzerine yaz")
    ayrist.add_argument("--kuru", action="store_true",
                        help="istemi kur ve göster, GÖNDERME (bedava)")
    ayrist.add_argument("--bekleme", type=float, default=0.0, metavar="SN",
                        help="çağrılar arasında bekleme (hız sınırı için)")
    ayrist.add_argument("--azami-token", type=int, default=None, metavar="N",
                        help="bütçe sınırı; aşılırsa koşu durur")
    ayrist.add_argument("--yapilandirma", type=Path, default=YAPILANDIRMA,
                        help=f"yapılandırma dosyası (öntanımlı: {YAPILANDIRMA})")

    a = ayrist.parse_args()

    talimat_yolu = talimat_dosyasini_bul()
    talimat = talimat_yolu.read_text(encoding="utf-8")
    isler = sartname_listesi(None if a.hepsi else a.belge)

    print(f"Talimat  : {talimat_yolu.name}")
    print(f"Belge    : {len(isler)} adet")

    # --- kuru koşu: hiç ağa çıkmadan istemleri göster -----------------------
    if a.kuru:
        return kuru_kosu(isler, talimat)

    # --- gerçek koşu ---------------------------------------------------------
    try:
        y = yapilandirma_yukle(a.yapilandirma)
    except LLMHatasi as hata:
        print(f"\nHATA: {hata}")
        return 1

    istemci = LLMIstemci(y)
    hedef_dizin = CIKTILAR / y.model.replace("/", "_")
    hedef_dizin.mkdir(parents=True, exist_ok=True)
    kayit_dosyasi = KAYIT / "kosum.jsonl"

    print(f"Model    : {y.model}")
    print(f"Uçnokta  : {y.base_url}")
    print(f"Çıktı    : {hedef_dizin}")
    if a.azami_token:
        print(f"Bütçe    : {a.azami_token} token")
    print("-" * 68)

    uretilen = atlanan = hatali = 0

    for no, sartname_yolu in isler:
        hedef = hedef_dizin / f"belge_{no}.txt"

        if hedef.exists() and not a.yeniden:
            print(f"belge_{no}  ATLANDI (çıktı var — üzerine yazmak için --yeniden)")
            atlanan += 1
            continue

        # Bütçe çağrıdan ÖNCE kontrol edilir, dolayısıyla sınır en fazla bir
        # belge kadar aşılabilir — bir çağrının maliyeti ancak yapıldıktan
        # sonra bilinir. Sınırı belirlerken bir belgelik pay bırakın.
        if a.azami_token and istemci.toplam_token >= a.azami_token:
            print(f"\nDURDURULDU: token bütçesi doldu ({istemci.toplam_token})")
            break

        istem = istemi_kur(talimat, sartname_yolu.read_text(encoding="utf-8"))

        try:
            cevap = istemci.metin_uret(istem)
        except LLMHatasi as hata:
            print(f"belge_{no}  HATA: {hata}")
            hatali += 1
            kayit_ekle(kayit_dosyasi, {
                "zaman": simdi(), "belge": no, "model": y.model,
                "talimat": talimat_yolu.name, "hata": str(hata)[:500],
            })
            continue

        hedef.write_text(cevap.metin + "\n", encoding="utf-8")
        uretilen += 1

        uyari = "  [!] ÇIKTI KESİLDİ" if cevap.kesildi_mi else ""
        print(
            f"belge_{no}  {cevap.token}  |  {cevap.sure_ms / 1000:.1f} sn"
            f"  |  kümülatif {istemci.toplam_token}{uyari}"
        )

        kayit_ekle(kayit_dosyasi, {
            "zaman": simdi(),
            "belge": no,
            "model": cevap.model,
            "talimat": talimat_yolu.name,
            "girdi_token": cevap.token.girdi,
            "metin_token": cevap.token.gorunur_cikti,
            "dusunme_token": cevap.token.dusunme,
            "faturalanan_cikti": cevap.token.faturalanan_cikti,
            "toplam_token": cevap.token.toplam,
            "dusunme_ciktiya_dahil": cevap.token.dusunme_ciktiya_dahil,
            "usage_ham": cevap.token.ham,
            "sure_ms": round(cevap.sure_ms, 1),
            "deneme": cevap.deneme_sayisi,
            "bitis_sebebi": cevap.bitis_sebebi,
            "karakter": len(cevap.metin),
            "hata": None,
        })

        if a.bekleme > 0 and (no, sartname_yolu) != isler[-1]:
            time.sleep(a.bekleme)

    # --- özet ----------------------------------------------------------------
    print("-" * 68)
    print(f"Üretilen {uretilen} | atlanan {atlanan} | hatalı {hatali}")
    print(f"Token    : {istemci.ozet()}")
    print(f"Kayıt    : {kayit_dosyasi}")

    if istemci.cagri_sayisi:
        n = istemci.cagri_sayisi
        girdi_ort = istemci.toplam_girdi / n
        cikti_ort = istemci.toplam_faturalanan_cikti / n

        # Girdi ve cikti AYRI gosteriliyor: cikti tokeni girdiden birkac kat
        # pahali. Tek bir "toplam token" sayisiyla maliyet hesaplanamaz.
        print(
            f"\nBelge başına ortalama:"
            f"\n  girdi            {girdi_ort:>8,.0f} token"
            f"\n  faturalanan çıktı {cikti_ort:>7,.0f} token  (düşünme dahil)"
            f"\n\n450 belge için:"
            f"\n  girdi            {girdi_ort * 450:>8,.0f} token"
            f"\n  faturalanan çıktı {cikti_ort * 450:>7,.0f} token"
            f"\n\nMaliyet = (girdi × girdi_fiyatı) + (faturalanan çıktı × çıktı fiyatı)."
            f"\nFiyatlar sağlayıcının fiyat sayfasında, 1 milyon token başına."
        )
        if istemci.toplam_dusunme > istemci.toplam_metin * 3:
            print(
                f"\n[!] Düşünme tokenleri metnin {istemci.toplam_dusunme / max(1, istemci.toplam_metin):.0f}"
                f" katı. Maliyetin büyük kısmı buradan geliyor."
                f"\n    yapilandirma.json içine \"reasoning_effort\": \"low\" eklemeyi deneyin."
            )

    return 1 if hatali else 0


def kuru_kosu(isler: list[tuple[str, Path]], talimat: str) -> int:
    """Ağa çıkmadan istemleri kurar ve büyüklüklerini gösterir.

    Amacı üç yönlü: istemin gerçekten doğru birleştiğini görmek, dosya
    adlandırmasında hata olup olmadığını anlamak, ve tek kuruş harcamadan
    büyüklük fikri edinmek.
    """
    print("KURU KOŞU — hiçbir istek gönderilmiyor\n")
    toplam = 0

    for no, yol in isler:
        istem = istemi_kur(talimat, yol.read_text(encoding="utf-8"))
        kaba = len(istem) // KABA_TOKEN_BOLENI
        toplam += kaba
        print(f"belge_{no}  {len(istem):>6} karakter  ~{kaba:>5} token  ({yol.name})")

    print(f"\nToplam ~{toplam} token (kaba tahmin, yalnızca girdi).")
    print("Bir istemi tam görmek için:")
    print(f"  python -c \"import kosum,pathlib;"
          f"print(kosum.istemi_kur(kosum.talimat_dosyasini_bul().read_text('utf-8'),"
          f"(kosum.ISTEMLER/'sartname_01.txt').read_text('utf-8')))\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
