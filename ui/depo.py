"""Kalıcılık ve evrak kayıt defteri.

İKİ AYRI DEPO, İKİ AYRI GEREKÇE
==============================

`EvrakDeposu`  — koşu sonuçları, JSON dosyası.
    `Dosya` pydantic olduğu için `model_dump(mode="json")` ile yazılıp
    `model_validate` ile geri okunuyor. Şema `extra="forbid"` olduğundan
    bozuk kayıt sessizce geçmiyor, yüklemede yakalanıyor.

`Defter`       — gelen/giden kayıt defteri, SQLite.
    JSON DEĞİL, çünkü burada SAYAÇ var. İki onay aynı anda gelirse
    "en büyük sıra no + 1" iki kez aynı sayıyı üretir ve defterde
    çift numara oluşur. SQLite'ın `BEGIN IMMEDIATE` işlemi bunu
    tek satırda çözüyor; JSON dosyasıyla aynısını yazmak kilit
    yönetimi demek olurdu.

SAYI BİÇİMİ BURADA DEĞİL
========================
`src/defter.py` docstring'i gerekçesini yazıyor: biçimi `giden_sayi_kur`
üretiyor ve `veri_yapisi.sayi_bolumleri()` ile kapalı devre sınanıyor.
Bu modül yalnızca SAYACI tutuyor ve satırı saklıyor. Biçim iki yerde
tutulursa zamanla ayrışır ve ürettiğimiz belgeyi kendi ayrıştırıcımız
okuyamaz hâle gelir.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import threading
import time
from datetime import date, datetime
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
if str(KOK / "src") not in sys.path:
    sys.path.insert(0, str(KOK / "src"))

from veri_yapisi import Dosya  # noqa: E402

BURASI = Path(__file__).resolve().parent
EVRAK_DOSYASI = BURASI / "evraklar_gercek.json"
DEFTER_DOSYASI = BURASI / "defter.db"

# Sarmalayıcıda saklanan, `Dosya` şemasına girmeyen alanlar.
SARMAL_ALANLAR = (
    "calisma_id", "dosya_adi", "yuklenme_ts", "toplam_ms", "linter_tur",
    "gunluk", "sevk", "defter_kaydi", "hatalar", "uyarilar", "atlanan",
    "llm_cagrisi",
)


def _json_uyumlu(deger):
    """`defter_satiri()` tarih ve enum döndürüyor; SQLite metin istiyor."""
    if deger is None:
        return None
    if isinstance(deger, (date, datetime)):
        return deger.isoformat()
    if isinstance(deger, (int, float, str)):
        return deger
    return str(deger)


# =============================================================================
# Evrak deposu
# =============================================================================


class EvrakDeposu:
    """Bellekte sözlük, diskte JSON. Sunucu yeniden başlarsa kayıp yok."""

    def __init__(self, yol: Path = EVRAK_DOSYASI) -> None:
        self.yol = yol
        self.kayitlar: dict[str, dict] = {}
        self._kilit = threading.Lock()

    # -- disk --------------------------------------------------------------
    def yukle(self) -> int:
        if not self.yol.exists():
            return 0
        try:
            ham = json.loads(self.yol.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return 0

        for evrak_id, k in (ham or {}).items():
            try:
                dosya = Dosya.model_validate(k["dosya"])
            except Exception:  # noqa: BLE001
                # Şema değiştiyse eski kayıt okunamaz. SESSİZ ATLAMIYORUZ —
                # atlanan kayıt sayısı çağırana dönüyor ve sunucu yazıyor.
                continue
            # Yarım kalmış koşu diskte "işleniyor" görünür; sunucu düştüğünde
            # o iş parçacığı ölmüştür ve bir daha dönmeyecektir.
            if str(dosya.durum) in ("ALINDI", "ISLENIYOR"):
                dosya.durum = "HATA"  # type: ignore[assignment]
            self.kayitlar[evrak_id] = {**{a: k.get(a) for a in SARMAL_ALANLAR},
                                       "dosya": dosya}
        return len(self.kayitlar)

    def kaydet(self) -> None:
        with self._kilit:
            ham = {
                evrak_id: {**{a: k.get(a) for a in SARMAL_ALANLAR},
                           "dosya": k["dosya"].model_dump(mode="json")}
                for evrak_id, k in self.kayitlar.items()
            }
        gecici = self.yol.with_suffix(".tmp")
        gecici.write_text(json.dumps(ham, ensure_ascii=False), encoding="utf-8")
        gecici.replace(self.yol)  # yarım dosya bırakmamak için

    # -- erişim ------------------------------------------------------------
    def ekle(self, kayit: dict) -> None:
        self.kayitlar[kayit["dosya"].evrak_id] = kayit

    def al(self, evrak_id: str) -> dict | None:
        return self.kayitlar.get(evrak_id)

    def hepsi(self) -> list[dict]:
        return sorted(self.kayitlar.values(),
                      key=lambda k: -(k.get("yuklenme_ts") or 0))

    def temizle(self) -> None:
        self.kayitlar.clear()


# =============================================================================
# Evrak kayıt defteri
# =============================================================================


class Defter:
    """Gelen ve giden defteri. Sayaç KURUM BAŞINA, 1'den başlar.

    NEDEN KURUM, NEDEN BİRİM DEĞİL
    ------------------------------
    Gerçekte evrak kayıt defteri kurumun defteridir; birimler o deftere
    yazar. `src/defter.py:139` da bunu söylüyor (İrem'in 2026-08-24
    kararı) ve iki taraf ayrışmasın diye burada da öyle.

    Satırda `birim` sütunu YİNE VAR ama sayaç anahtarı değil: hangi
    birimin işlediği görünsün, numara kurum genelinde tek dizi olsun.
    Yani Ankara İl MEM'in giden defterinde 1, 2, 3... diye tek bir sıra
    akar; 3 numaralı yazıyı Özel Öğretim Şubesi, 4'ü Ortaöğretim yazmış
    olabilir.

    BİLİNEN SONUÇ: `giden_sayi_kur` sayının ikinci bölümüne BİRİMİN
    DETSİS'ini yazıyor, kurumunkini değil. Sayaç kurum genelinde tek
    dizi olduğu için aynı DETSİS'li iki yazı arasında numara atlamaları
    görünür (E-91571118-...-3 ile E-91571118-...-7 gibi). Bu, kurum
    defteri tutan gerçek kurumlarda da böyledir; atlama başka bir
    birimin araya giren kaydıdır.
    """

    def __init__(self, yol: Path = DEFTER_DOSYASI) -> None:
        self.yol = yol
        self._kilit = threading.Lock()
        self._kur()

    def _baglan(self) -> sqlite3.Connection:
        # `isolation_level=None` -> işlemleri elle yönetiyoruz; sayaç
        # artırma ile satır yazma tek `BEGIN IMMEDIATE` içinde olmalı.
        baglanti = sqlite3.connect(self.yol, timeout=10.0, isolation_level=None)
        baglanti.row_factory = sqlite3.Row
        return baglanti

    def _kur(self) -> None:
        with self._baglan() as b:
            b.executescript("""
                CREATE TABLE IF NOT EXISTS defter (
                  yon        TEXT    NOT NULL,
                  kurum      TEXT    NOT NULL,   -- sayacın anahtarı
                  birim      TEXT,               -- kaydı işleyen birim
                  sira_no    INTEGER NOT NULL,
                  evrak_id   TEXT    NOT NULL,
                  sayi       TEXT,
                  tarih      TEXT,
                  konu       TEXT,
                  muhatap    TEXT,
                  belge_turu TEXT,
                  durum      TEXT,
                  ts         REAL    NOT NULL,
                  PRIMARY KEY (yon, kurum, sira_no)
                );
                -- Aynı evrak aynı kurumun aynı defterine iki kez yazılamaz.
                -- Memur "kaydet"e iki kez basarsa ikinci numara verilmemeli;
                -- defterde boşluk kalır ve boşluk denetimde soru olur.
                CREATE UNIQUE INDEX IF NOT EXISTS defter_tekil
                  ON defter (yon, kurum, evrak_id);
            """)

    # -- yazma -------------------------------------------------------------
    def yaz(self, yon: str, kurum: str, birim: str | None,
            evrak_id: str, satir: dict) -> dict:
        """Sıra numarası verir ve satırı yazar. Zaten varsa mevcudu döndürür.

        Sayaç artırma ile satır yazma TEK İŞLEMDE. Ayrı olsaydı eş zamanlı
        iki onay aynı numarayı alırdı.
        """
        with self._kilit, self._baglan() as b:
            b.execute("BEGIN IMMEDIATE")
            try:
                mevcut = b.execute(
                    "SELECT * FROM defter WHERE yon=? AND kurum=? AND evrak_id=?",
                    (yon, kurum, evrak_id)).fetchone()
                if mevcut is not None:
                    b.execute("COMMIT")
                    return dict(mevcut)

                sira_no = b.execute(
                    "SELECT COALESCE(MAX(sira_no), 0) + 1 FROM defter "
                    "WHERE yon=? AND kurum=?", (yon, kurum)).fetchone()[0]

                kayit = {
                    "yon": yon, "kurum": kurum, "birim": birim,
                    "sira_no": int(sira_no), "evrak_id": evrak_id,
                    "sayi": _json_uyumlu(satir.get("sayi")),
                    "tarih": _json_uyumlu(satir.get("tarih")),
                    "konu": _json_uyumlu(satir.get("konu")),
                    "muhatap": _json_uyumlu(satir.get("muhatap")),
                    "belge_turu": _json_uyumlu(satir.get("belge_turu")),
                    "durum": _json_uyumlu(satir.get("durum")),
                    "ts": time.time(),
                }
                b.execute(
                    "INSERT INTO defter (yon, kurum, birim, sira_no, evrak_id, "
                    "sayi, tarih, konu, muhatap, belge_turu, durum, ts) "
                    "VALUES (:yon, :kurum, :birim, :sira_no, :evrak_id, :sayi, "
                    ":tarih, :konu, :muhatap, :belge_turu, :durum, :ts)", kayit)
                b.execute("COMMIT")
                return kayit
            except Exception:
                b.execute("ROLLBACK")
                raise

    def sayiyi_isle(self, yon: str, kurum: str, evrak_id: str, sayi: str) -> None:
        """Satır yazıldıktan sonra resmî sayıyı ekler.

        Sayı ancak sıra numarası kesinleşince kurulabiliyor (`giden_sayi_kur`
        onu girdi alıyor), numara da ancak satır yazılınca kesinleşiyor.
        Bu yüzden iki adım: önce `yaz()`, sonra bu.
        """
        with self._kilit, self._baglan() as b:
            b.execute("UPDATE defter SET sayi=? WHERE yon=? AND kurum=? AND evrak_id=?",
                      (sayi, yon, kurum, evrak_id))

    def durumu_guncelle(self, evrak_id: str, durum: str) -> None:
        with self._kilit, self._baglan() as b:
            b.execute("UPDATE defter SET durum=? WHERE evrak_id=?", (durum, evrak_id))

    # -- okuma -------------------------------------------------------------
    def satirlar(self, yon: str | None = None, kurum: str | None = None,
                 q: str | None = None) -> list[dict]:
        kosul, parametre = [], []
        if yon:
            kosul.append("yon = ?")
            parametre.append(yon)
        if kurum:
            kosul.append("kurum = ?")
            parametre.append(kurum)
        if q:
            kosul.append("(IFNULL(konu,'') LIKE ? OR IFNULL(sayi,'') LIKE ? "
                         "OR IFNULL(muhatap,'') LIKE ?)")
            parametre += [f"%{q}%"] * 3
        nerede = (" WHERE " + " AND ".join(kosul)) if kosul else ""
        with self._baglan() as b:
            return [dict(r) for r in b.execute(
                f"SELECT * FROM defter{nerede} ORDER BY kurum, yon, sira_no",
                parametre).fetchall()]

    def ozet(self) -> list[dict]:
        with self._baglan() as b:
            return [dict(r) for r in b.execute(
                "SELECT yon, kurum, COUNT(*) AS adet, MAX(sira_no) AS son_no "
                "FROM defter GROUP BY yon, kurum ORDER BY kurum, yon").fetchall()]

    def temizle(self) -> None:
        with self._kilit, self._baglan() as b:
            b.execute("DELETE FROM defter")
