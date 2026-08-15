#!/usr/bin/env python3
"""ADIM 4.4d — dilekçeleri yeniden üretmek için parti hazırlar.

    etiketler/  ->  belge_talebi ailesindeki 66 dilekçe
                ->  partiler_dilekce/dilekce_parti_NN.txt

NEDEN YENİDEN ÜRETİM
Ölçülen sorun: model şartnamedeki "Talep" alanını CÜMLEYE GÖMÜYORDU.

    şartname : Talep: Araştırma Talebinin Reddi
    metin    : "Araştırma Talebinin Reddi konusundaki başvurumu kayıt
                bürosuna teslim ettim."

"Araştırma Talebinin Reddi" bir SDP konu başlığıdır — devletin dosya
planından gelen katalog adı. Bir vatandaş böyle yazmaz; olayı anlatır.

NEDEN ETİKET DEĞİŞMİYOR
Üretece dokunmak rastgele seçim sırasını kaydırır ve 300 etiketin
tamamı değişir; üretilmiş gövdeler geçersiz olur (bir kez yaşandı,
120 belge yeniden üretilmek zorunda kalındı).

Bu yüzden yalnızca İSTEME bir bölüm ekleniyor. Etiket, şartname ve
diğer 234 belge dokunulmadan kalıyor.

KULLANIM

    python dilekce_parti_hazirla.py            # 4 parti dosyasi yaz
    python dilekce_parti_hazirla.py --boyut 20 # parti boyu degistir
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
HEDEF = BURASI / "partiler_dilekce"

# Yalnızca bu ailedeki belgeler yeniden üretilir.
HEDEF_AILE = "belge_talebi"

PARTI_BASLIK = """Bir vatandaş adına DİLEKÇE metni yazıyorsun.
Aşağıda {n} AYRI DİLEKÇE için şartname var. Her biri için SADECE METİN
GÖVDESİNİ yaz.

ÇIKTI BİÇİMİ — BUNA BİREBİR UY:
Her belgeyi şu ayraçla başlat, başka hiçbir şey yazma:

### BELGE <numara>
(metin gövdesi)

Ayraç satırı tam olarak "### BELGE" + üç haneli numara biçiminde
olacak. Numaraları aşağıdaki şartnamelerde yazdığı gibi kullan, kendin
numaralandırma. Belgeler arasına açıklama, başlık, yorum ekleme.
İlk ayraçtan önce hiçbir şey yazma.

HER BELGEYİ BAĞIMSIZ YAZ:
Önceki belgelerde kullandığın cümle kalıplarını tekrarlama. Her
dilekçenin ilk cümlesi farklı kurulsun. Aynı sözcük dizisini iki
belgede kullanma — bu bir veri setidir ve çeşitlilik ölçülecektir.

{dilekce_kurali}

{talimat}
"""

PARTI_SON = """
════════════════════════════════════════════════════════════════
Yukarıdaki {n} dilekçenin gövdesini yaz. Her birini "### BELGE NNN"
ayracıyla başlat. Şartnamelerin sırasını koru.

UNUTMA: konu başlığını cümleye gömme — vatandaş olayı anlatır.
════════════════════════════════════════════════════════════════
"""


def main() -> int:
    a = argparse.ArgumentParser(description="ADIM 4.4d dilekce parti hazirlama")
    a.add_argument("--boyut", type=int, default=17, help="parti basina belge")
    a.add_argument("--parti", type=int, help="yalnizca bu partiyi ekrana bas")
    ns = a.parse_args()

    talimat_yolu = max(ISTEMLER.glob("talimat_v*.txt"),
                       key=lambda p: int(p.stem.split("_v")[-1]))
    talimat = talimat_yolu.read_text(encoding="utf-8").strip()

    dilekce_kurali_yolu = ISTEMLER / "dilekce_ek.txt"
    if not dilekce_kurali_yolu.exists():
        raise SystemExit(
            f"HATA: {dilekce_kurali_yolu} yok.\n"
            f"dilekce_ek.txt dosyasini istemler klasorune koyun.")
    dilekce_kurali = dilekce_kurali_yolu.read_text(encoding="utf-8").strip()

    hepsi = []
    for y in sorted(ETIKETLER.glob("etiket_*.json")):
        e = etiket_yukle(y)
        if e.get("aile") == HEDEF_AILE:
            hepsi.append(e)

    if not hepsi:
        raise SystemExit(f"HATA: {HEDEF_AILE} ailesinde belge bulunamadi.")

    partiler = [hepsi[i:i + ns.boyut] for i in range(0, len(hepsi), ns.boyut)]

    print(f"Talimat  : {talimat_yolu.name} + dilekce_ek.txt")
    print(f"Hedef    : {HEDEF_AILE} ailesi, {len(hepsi)} dilekce")
    print(f"Parti    : {len(partiler)} x {ns.boyut}")

    if HEDEF.exists() and not ns.parti:
        shutil.rmtree(HEDEF)
    if not ns.parti:
        HEDEF.mkdir(parents=True, exist_ok=True)

    boyutlar = []
    for i, grup in enumerate(partiler, start=1):
        numaralar = [e["belge_no"] for e in grup]
        govde = [f"### BELGE {e['belge_no']}\n\n{sartname_uret(e)}"
                 for e in grup]
        metin = (
            PARTI_BASLIK.format(n=len(grup), dilekce_kurali=dilekce_kurali,
                                talimat=talimat)
            + "\n\n" + ("\n\n" + "─" * 64 + "\n\n").join(govde)
            + PARTI_SON.format(n=len(grup)))
        boyutlar.append(len(metin))

        if ns.parti and ns.parti == i:
            print("\n" + metin)
            return 0
        if not ns.parti:
            (HEDEF / f"dilekce_parti_{i:02d}.txt").write_text(
                metin, encoding="utf-8")
            (HEDEF / f"dilekce_parti_{i:02d}.numaralar").write_text(
                "\n".join(numaralar) + "\n", encoding="utf-8")

    if ns.parti:
        raise SystemExit(f"HATA: {ns.parti}. parti yok (1-{len(partiler)})")

    ort = sum(boyutlar) / len(boyutlar)
    print(f"\n{len(partiler)} parti yazildi -> {HEDEF}")
    print(f"  boyut      : {min(boyutlar):,}-{max(boyutlar):,} karakter")
    print(f"  kaba token : ~{ort / 3:,.0f} / parti")
    print("\nSIRADAKI ADIM")
    print("  1. partiler_dilekce/dilekce_parti_01.txt ac, TAMAMINI kopyala")
    print("  2. YENI SOHBETE yapistir")
    print("  3. Cevabi cevaplar/dilekce_cevap_01.txt olarak kaydet")
    print("  4. python dilekce_ayristir.py 01")
    print("  5. python denetle_govde.py")
    print("\n  DIKKAT: govdeler/ icindeki dosyalarin UZERINE yazilir.")
    print("  Eski hallerini korumak isterseniz once yedek alin.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
