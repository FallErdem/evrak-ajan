#!/usr/bin/env python3
"""ADIM 4.4a — şartnameleri PARTİLERE böler, sohbete yapıştırılacak istem üretir.

    sartnameler/sartname_NNN.txt  x300
                     |
              parti_01.txt ... parti_15.txt   (her biri 20 belge)
                     |
        [SİZ: kopyala -> öbür sohbete yapıştır -> cevabı kopyala]
                     |
              cevaplar/cevap_01.txt
                     |
         parti_ayristir.py  ->  govdeler/govde_NNN.txt

NEDEN PARTİ
Tek tek üretim 300 çağrı demek; talimatın 1750 tokeni 300 kez gidiyor.
Partide talimat bir kez gidiyor, 20 şartname arkasına ekleniyor.

NEDEN SOHBET, API DEĞİL
Sohbet arayüzü ücretsiz. 300 belgelik API üretimi ~360 TL tutuyordu.
Bedeli: 15 tur kopyala-yapıştır.

TOPLU ÜRETİMİN RİSKİ
Model bir cevapta 20 metin yazarken KENDİ ÖNCEKİ METİNLERİNİ görüyor ve
onlara benzetiyor. ADIM 1'de her belgeden sonra /clear yaptığımızın
sebebi buydu. Üç önlem:
  1. Parti içi karışıklık — etiketler zaten karışık sırada üretildi,
     sıra bozulmadan dilimleniyor
  2. İsteme açık madde — "her belgeyi bağımsız yaz"
  3. Her 4 partide yeni sohbet — 15. partide model 280 belge görmüş olur

KULLANIM

    python parti_hazirla.py                 # 15 parti dosyasi yaz
    python parti_hazirla.py --boyut 10      # 30 parti, daha kucuk
    python parti_hazirla.py --parti 1       # yalnizca 1. partiyi ekrana bas
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

BURASI = Path(__file__).resolve().parent
DEPO_KOKU = BURASI.parent.parent
sys.path.insert(0, str(DEPO_KOKU))

from src.sartname_render import etiket_yukle, sartname_uret  # noqa: E402

ETIKETLER = BURASI / "etiketler"
ISTEMLER = BURASI / "istemler"
HEDEF = BURASI / "partiler"

PARTI_BASLIK = """Bir kamu kurumunda resmî yazışma metinlerini kaleme alan görevlisin.
Aşağıda {n} AYRI BELGE için şartname var. Her biri için SADECE METİN
GÖVDESİNİ yaz.

ÇIKTI BİÇİMİ — BUNA BİREBİR UY:
Her belgeyi şu ayraçla başlat, başka hiçbir şey yazma:

### BELGE <numara>
(metin gövdesi)

### BELGE <numara>
(metin gövdesi)

Ayraç satırı tam olarak "### BELGE" + üç haneli numara biçiminde
olacak. Numaraları aşağıdaki şartnamelerde yazdığı gibi kullan, kendin
numaralandırma. Belgeler arasına açıklama, başlık, yorum ekleme.
İlk ayraçtan önce hiçbir şey yazma.

HER BELGEYİ BAĞIMSIZ YAZ:
Önceki belgelerde kullandığın cümle kalıplarını tekrarlama. Her
belgenin ilk cümlesi farklı kurulsun. Aynı sözcük dizisini iki
belgede kullanma — bu bir veri setidir ve çeşitlilik ölçülecektir.

{talimat}
"""

PARTI_SON = """
════════════════════════════════════════════════════════════════
Yukarıdaki {n} belgenin gövdesini yaz. Her birini "### BELGE NNN"
ayracıyla başlat. Şartnamelerin sırasını koru.
════════════════════════════════════════════════════════════════
"""


def main() -> int:
    a = argparse.ArgumentParser(description="ADIM 4.4a parti hazirlama")
    a.add_argument("--boyut", type=int, default=20, help="parti basina belge")
    a.add_argument("--parti", type=int, help="yalnizca bu partiyi ekrana bas")
    a.add_argument("--temizle", action="store_true", help="eski partileri sil")
    ns = a.parse_args()

    talimat_yolu = max(ISTEMLER.glob("talimat_v*.txt"),
                       key=lambda p: int(p.stem.split("_v")[-1]))
    talimat = talimat_yolu.read_text(encoding="utf-8").strip()

    yollar = sorted(ETIKETLER.glob("etiket_*.json"))
    if not yollar:
        raise SystemExit(f"HATA: {ETIKETLER} icinde etiket yok.")

    # Etiketler zaten karışık sırada üretildi (kurum, tür, yazar tipi
    # karışık). Sırayı bozmadan dilimlemek parti içi çeşitliliği korur.
    partiler = [yollar[i:i + ns.boyut] for i in range(0, len(yollar), ns.boyut)]

    print(f"Talimat : {talimat_yolu.name}")
    print(f"Etiket  : {len(yollar)} adet")
    print(f"Parti   : {len(partiler)} x {ns.boyut}")

    if ns.temizle and HEDEF.exists():
        shutil.rmtree(HEDEF)
    HEDEF.mkdir(parents=True, exist_ok=True)

    boyutlar = []
    for i, grup in enumerate(partiler, start=1):
        etiketler = [etiket_yukle(y) for y in grup]
        numaralar = [e["belge_no"] for e in etiketler]

        govde = []
        for e in etiketler:
            govde.append(f"### BELGE {e['belge_no']}\n\n{sartname_uret(e)}")

        metin = (
            PARTI_BASLIK.format(n=len(grup), talimat=talimat)
            + "\n\n" + ("\n\n" + "─" * 64 + "\n\n").join(govde)
            + PARTI_SON.format(n=len(grup))
        )
        boyutlar.append(len(metin))

        if ns.parti and ns.parti == i:
            print("\n" + metin)
            return 0
        if not ns.parti:
            (HEDEF / f"parti_{i:02d}.txt").write_text(metin, encoding="utf-8")
            # Beklenen numaralar AYRI dosyada. Parti metninden regex ile
            # çıkarmak, başlıktaki biçim örneğini de yakalıyordu.
            (HEDEF / f"parti_{i:02d}.numaralar").write_text(
                "\n".join(numaralar) + "\n", encoding="utf-8")

    if ns.parti:
        raise SystemExit(f"HATA: {ns.parti}. parti yok (1-{len(partiler)})")

    ort = sum(boyutlar) / len(boyutlar)
    print(f"\n{len(partiler)} parti yazildi -> {HEDEF}")
    print(f"  boyut      : {min(boyutlar):,}-{max(boyutlar):,} karakter")
    print(f"  kaba token : ~{ort / 3:,.0f} / parti")
    print(f"\nSIRADAKI ADIM")
    print(f"  1. partiler/parti_01.txt dosyasini ac, TAMAMINI kopyala")
    print(f"  2. Obur sohbete yapistir")
    print(f"  3. Cevabin TAMAMINI kopyala -> cevaplar/cevap_01.txt")
    print(f"  4. python parti_ayristir.py 01")
    print(f"  5. 15 kez tekrarla. HER 4 PARTIDE YENI SOHBET AC.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
