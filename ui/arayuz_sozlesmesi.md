# Arayüz Sözleşmesi

Backend ile frontend arasındaki anlaşma. Bu dosya donduktan sonra iki taraf birbirini
beklemeden çalışabilir.

**Kural:** Frontend yalnızca bu sözleşmeye güvenir. Backend'in içi nasıl çalışırsa çalışsın,
dışarıya bu şekilde konuşur.

---

## 1. Backend'den istenen tek şey

Pipeline'ın içine dokunmuyoruz. Her ajanın **başında ve sonunda** bir fonksiyon çağrılıyor:

```python
from arayuz.olay import yayinla

def siniflandirici(evrak, calisma_id):
    yayinla(calisma_id, "dugum_basladi", dugum=3, dugum_adi="siniflandirici")
    t0 = time.perf_counter()

    sonuc = ...  # mevcut kod, hiç değişmiyor

    yayinla(calisma_id, "dugum_bitti", dugum=3, dugum_adi="siniflandirici",
            sure_ms=int((time.perf_counter() - t0) * 1000),
            cikti=sonuc.model_dump(),
            guven=sonuc.guven,
            gerekce=sonuc.gerekce)
    return sonuc
```

`yayinla` bir kuyruğa yazar, o kadar. Pipeline'ı bloke etmez, hata fırlatmaz.
Toplam ek iş: 12 ajan × 2 satır.

---

## 2. Düğüm numaraları

Akış diyagramıyla birebir. Frontend bu numaralara göre kutu çiziyor, değişmemeli.

| No | `dugum_adi` | Ajan | Tip |
|---|---|---|---|
| 1 | `okuyucu` | — | Docling |
| 2 | `ayristirici` | — | Kural + LLM |
| 3 | `siniflandirici` | — | Regex + LLM |
| 4 | `bilgi_cikarici` | — | LLM |
| 5 | `eksik_bilgi` | Ajan 1 | Kural motoru + LLM |
| 6 | `mevzuat_danismani` | Ajan 1 | Arama + LLM |
| 7 | `ozetleyici` | — | LLM |
| 8 | `karar_verici` | Ajan 2 | LLM |
| 9 | `taslak` | Ajan 2 | Şablon + LLM |
| 10 | `uslup_denetleyici` | Ajan 2 | Kural motoru (LLM yok) |
| 11 | `yonlendirici` | — | Arama + LLM |
| 12 | `guven_kapisi` | — | Deterministik |

---

## 3. Durumlar

Evrak her an tam olarak bir durumda:

```
ALINDI → ISLENIYOR → INSAN_ONAYI_BEKLIYOR → ONAYLANDI
                   ↘ OTOMATIK_ONAYLANDI      REDDEDILDI
                   ↘ HATA                    EKSIK_BILGI_BEKLIYOR
```

`ISLENIYOR` durumundayken `aktif_dugum` alanı hangi düğümde olunduğunu söyler.

**Önemli:** `INSAN_ONAYI_BEKLIYOR` durumunda süreç gerçekten durur ve saatler sonra devam
edebilir. Bu yüzden pipeline tek bir fonksiyon çağrısı olamaz — durum SQLite'a yazılır,
insan karar verince kaldığı yerden devam eder.

---

## 4. Olay biçimi (SSE)

Sunucu `text/event-stream` yayınlar. Her satır bir JSON:

```json
{
  "tur": "dugum_bitti",
  "calisma_id": "c_8f3a",
  "evrak_id": "e_120",
  "dugum": 3,
  "dugum_adi": "siniflandirici",
  "ts": 1755432101.482,
  "sure_ms": 1420,
  "guven": 0.87,
  "gerekce": "Sayının üçüncü bölümünde 010.06.01 kodu okundu.",
  "cikti": { "belge_turu": "resmi_yazi", "sdp_kodu": "010.06.01" }
}
```

Olay türleri:

| `tur` | Ne zaman | Zorunlu alanlar |
|---|---|---|
| `akis_basladi` | Evrak alındı | `evrak_id`, `calisma_id` |
| `dugum_basladi` | Ajan başladı | `dugum`, `dugum_adi` |
| `dugum_bitti` | Ajan bitti | `dugum`, `sure_ms`, `cikti` |
| `dugum_hata` | Ajan patladı | `dugum`, `hata` |
| `dugum_tekrar` | Üslup denetleyici taslağı geri gönderdi (9↔10) | `dugum`, `tur_no` |
| `durum_degisti` | Durum geçişi | `durum` |
| `akis_bitti` | Bitti | `durum`, `toplam_ms` |

Frontend bu olayları biriktirir; ekranı olay akışından kurar. Sayfa yenilenirse
`GET /api/evrak/{id}` ile tam durum çekilir, akış oradan devam eder.

---

## 5. Uç noktalar

| Metot | Yol | Ne yapar |
|---|---|---|
| `POST` | `/api/evrak` | multipart dosya → `{evrak_id, calisma_id}` |
| `GET` | `/api/evrak` | Liste (özet alanlar) |
| `GET` | `/api/evrak/{id}` | Tam durum (aşağıdaki şema) |
| `GET` | `/api/evrak/{id}/akis` | SSE olay akışı |
| `GET` | `/api/evrak/{id}/sayfa/{n}` | PNG sayfa görüntüsü |
| `POST` | `/api/evrak/{id}/karar` | İnsan kararı |
| `GET` | `/api/istatistik` | Pano rakamları |

### POST /api/evrak/{id}/karar

```json
{
  "rol": "birim_sorumlusu",
  "aksiyon": "onayla | duzenle_onayla | reddet | birim_degistir | eksik_bilgi_iste",
  "gerekce": "zorunlu — reddet ve birim_degistir için",
  "taslak_govde": "duzenle_onayla ise yeni gövde metni",
  "yeni_birim": "birim_degistir ise hedef birim kodu"
}
```

`birim_degistir` ve `duzenle_onayla` çağrıları **düzeltme kaydı** olarak saklanır.
Bu kayıtlar Parça 10'da "insan düzeltme oranı" metriğini verir — yani sistemin kendi
hata payını ölçmesini sağlar. Raporda bir satır, jüri karşısında bir cümle.

---

## 6. Evrak şeması

`GET /api/evrak/{id}` çıktısı. Alan adları `src/veri_yapisi.py` ile aynı kalmalı.

```json
{
  "evrak_id": "e_120",
  "calisma_id": "c_8f3a",
  "dosya_adi": "dilekce_ornek_03.pdf",
  "yuklenme_ts": 1755432100.0,
  "durum": "INSAN_ONAYI_BEKLIYOR",
  "aktif_dugum": null,
  "sayfa_sayisi": 2,

  "ustveri": {
    "sayi":     { "deger": "E-71368504-010.06.01-4471829", "guven": 1.0,  "yontem": "regex", "kanit": {"sayfa": 1, "kutu": [72, 118, 340, 134]} },
    "tarih":    { "deger": "2026-08-11", "guven": 0.96, "yontem": "regex", "kanit": {"sayfa": 1, "kutu": [612, 118, 720, 134]} },
    "konu":     { "deger": "İmar durumu talebi", "guven": 0.88, "yontem": "llm", "kanit": {"sayfa": 1, "kutu": [72, 190, 480, 206]} },
    "muhatap":  { "deger": "Çevre ve Şehircilik İl Müdürlüğü", "guven": 0.91, "yontem": "llm", "kanit": {"sayfa": 1, "kutu": [72, 158, 430, 174]} },
    "ilgi":     { "deger": null, "guven": 0.0, "yontem": null, "kanit": null },
    "imza":     { "deger": "Ahmet Y. — Şube Müdürü", "guven": 0.84, "yontem": "llm", "kanit": {"sayfa": 2, "kutu": [480, 620, 720, 660]} }
  },

  "belge_turu": { "deger": "dilekce", "guven": 0.82, "gerekce": "Sayı alanı yok, gerçek kişi imzası var." },
  "sdp":        { "kod": "010.06.01", "ad": "İmar planı işlemleri", "kaynak_sayidan_mi": true },

  "varliklar": [
    { "tur": "kisi",  "deger": "Ahmet Y.",        "guven": 0.93, "pii": true,  "kanit": {"sayfa": 1, "kutu": [72, 300, 210, 316]} },
    { "tur": "ada",   "deger": "1024/7",          "guven": 0.88, "pii": false, "kanit": {"sayfa": 1, "kutu": [230, 340, 320, 356]} },
    { "tur": "tarih", "deger": "2026-07-30",      "guven": 0.95, "pii": false, "kanit": {"sayfa": 1, "kutu": [400, 340, 500, 356]} }
  ],

  "talep": "Ada/parsel için imar durum belgesi düzenlenmesi.",

  "eksikler": [
    { "alan": "tapu_belgesi", "onem": "kritik", "katman": "mevzuat", "dayanak": "İmar Yönetmeliği m.12",
      "soru": "Söz konusu taşınmaza ait tapu belgesinin bir örneğini iletebilir misiniz?",
      "karsi_taraftan_istenebilir": true },
    { "alan": "iletisim_telefon", "onem": "dusuk", "katman": "sema", "dayanak": "Zorunlu alan",
      "soru": "Size ulaşabileceğimiz bir telefon numarası paylaşır mısınız?",
      "karsi_taraftan_istenebilir": true }
  ],

  "mevzuat": [
    { "madde": "3194 sayılı İmar Kanunu m.8", "baslik": "Planların hazırlanması",
      "alinti": "Halihazır haritalar üzerine...", "gerekce": "Talep imar durumuna ilişkin.",
      "dogrulandi": true }
  ],

  "ozet": "Ahmet Y., 1024 ada 7 parsel için imar durum belgesi talep etmektedir. Tapu belgesi eklenmemiştir.",

  "karar": { "uretilecek_tur": "cevap_yazisi", "gerekce": "Vatandaş talebi, doğrudan cevap gerektiriyor.", "taslak_gerekli": true },

  "taslak": {
    "baslik": "T.C. ... BELEDİYE BAŞKANLIĞI",
    "sayi": "E-12345678-010.06.01-2026/441",
    "tarih": "2026-08-17",
    "muhatap": "Sayın Ahmet Y.",
    "govde": "İlgi dilekçenizde ...",
    "imza": "İmar ve Şehircilik Müdürü"
  },

  "uslup_bulgulari": [
    { "kural_no": "U-14", "duzey": "uyari", "mesaj": "Kapanış ibaresi eksik.", "mevzuat": "Yönetmelik m.21", "tur_no": 1, "cozuldu": true }
  ],
  "linter_tur_sayisi": 2,

  "yonlendirme": {
    "birim": "IMAR_SEHIRCILIK",
    "birim_adi": "İmar ve Şehircilik Müdürlüğü",
    "skor": 0.91,
    "geregi_bilgi": "geregi",
    "gerekce": "Talep imar durum belgesine ilişkin; bu birimin görev alanında.",
    "kanit_cumle": "1024 ada 7 parsel için imar durum belgesi talep ediyorum.",
    "alternatifler": [
      { "birim": "EMLAK_ISTIMLAK", "birim_adi": "Emlak ve İstimlak Müdürlüğü", "skor": 0.34 },
      { "birim": "FEN_ISLERI",     "birim_adi": "Fen İşleri Müdürlüğü",        "skor": 0.11 }
    ]
  },

  "guven_kapisi": { "mod": "INSAN", "skor": 0.82, "esik": 0.85,
                    "sebep": "Kritik eksik bilgi var: tapu_belgesi" },

  "sureler": { "1": 2100, "2": 1340, "3": 1420, "4": 2800, "5": 3100,
               "6": 2400, "7": 1900, "8": 1100, "9": 4200, "10": 340,
               "11": 1600, "12": 40 },
  "toplam_ms": 22340,

  "gunluk": [
    { "ts": 1755432101.4, "aktor": "sistem", "olay": "Sınıflandırma: dilekçe (0.82)" },
    { "ts": 1755432124.0, "aktor": "sistem", "olay": "Güven kapısı: insan onayına düştü" }
  ]
}
```

### Alanlar hakkında notlar

- **`kanit.kutu`** → `[x1, y1, x2, y2]`, PNG sayfa görüntüsünün piksel koordinatı.
  Docling'in sınır kutusu farklı ölçekteyse backend dönüştürür; frontend ölçek hesabı yapmaz.
- **`yontem`** → K-13 gereği: `regex` > `sozluk` > `llm`. Arayüz bunu rozet olarak gösterir,
  "her şeyi LLM'e sormadık" iddiasının görsel kanıtı.
- **`guven`** → K-15 hatırlatması: qwen yanlış cevaplara ortalama 0.79 veriyor. Arayüz
  ham skoru göstermez, kalibre edilmiş eşiğe göre üç renk kullanır (yeşil/sarı/kırmızı).
- **Eksik alanlar** `null` gelir, anahtar hiç gelmemezlik etmez. Frontend `undefined`
  kontrolü yapmak zorunda kalmamalı.

---

## 7. İstatistik

`GET /api/istatistik`:

```json
{
  "toplam_evrak": 12,
  "otomatik_onay_orani": 0.58,
  "insan_duzeltme_orani": 0.17,
  "ortalama_sure_ms": 21400,
  "p50_sure_ms": 19800,
  "dugum_ortalama_ms": { "1": 2000, "2": 1300, "...": 0 },
  "llm_sure_orani": 0.71,
  "kural_sure_orani": 0.29,
  "linter_ilk_tur_gecme": 0.64,
  "bilinmiyor_orani": 0.08
}
```

`otomatik_onay_orani` ticarileşme anlatısının tek rakamlık özeti; sunumda bu geçecek.

---

## 8. Sahte sunucu

`sahte_sunucu.py` bu sözleşmenin tamamını gerçekliyor, ama içinde model yok —
kayıtlı bir koşuyu gerçekçi gecikmelerle oynatıyor.

İki işe yarıyor:

1. **Bugün:** Frontend backend'i beklemeden yazılır.
2. **Demo günü:** T-03'ün 4. yedek katmanı. İnternet veya GPU giderse `--kayittan`
   bayrağıyla aynı arayüz aynı sonuçları üretir. Şartname madde 8 kayıttan sunuma izin
   veriyor; bu ondan daha iyisi, çünkü arayüz canlı çalışıyor.

Gerçek backend hazır olunca frontend'de değişen tek şey `.env` içindeki adres.
