# ADIM 1 — Üretim risk testi

**Cevaplamaya çalıştığı soru:** Seçtiğimiz model resmî Türkçe *yazabiliyor* mu?

Parça 1'de modelin metni **anladığı** ölçülmüştü. Yazmak ayrı bir yetenek;
ölçülmezse 450 belgenin tamamı çöp çıkabilir ve bu Parça 4'te fark edilir.

---

## Kurulum

### 1. API anahtarı

```
.gizli/api_anahtari.txt      ← anahtarı buraya tek satır olarak yapıştırın
```

Bu klasör `.gitignore` ile korunuyor. Şartname madde 7 depoyu herkese açık
yapmayı zorunlu kılıyor — koda giren bir anahtar herkese açık olur.

Yerel Ollama kullanıyorsanız anahtar gerekmez; `yapilandirma.json` içinde
`"anahtar_dosyasi": null` yapın.

### 2. Yapılandırma

`yapilandirma.json` içinde iki satır belirleyicidir:

```json
"base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
"model":    "gemini-3.6-flash"
```

Sağlayıcı değiştirmek için yalnızca bu ikisi değişir:

| Nereye | base_url |
|---|---|
| Ollama (yerel) | `http://localhost:11434/v1` |
| Gemini | `https://generativelanguage.googleapis.com/v1beta/openai/` |
| Colab (vLLM + tünel) | `https://xxxx.ngrok-free.app/v1` |
| RunPod | `https://xxxx.runpod.net/v1` |

Kod hiç değişmez (K-21).

---

## Kullanım

```bash
cd deneyler/adim1

python kosum.py --kuru --hepsi        # istemleri kur ve göster, GÖNDERME
python kosum.py --belge 01            # tek belge
python kosum.py --hepsi               # eksik olanların hepsini üret
python kosum.py --belge 01 --yeniden  # mevcut çıktının üzerine yaz
python kosum.py --hepsi --bekleme 5   # çağrılar arası 5 sn (hız sınırı için)
python kosum.py --hepsi --azami-token 20000   # bütçe sınırı
```

**İlk iş `--kuru` ile başlamak olmalı.** Hiç ağa çıkmaz, tek kuruş harcamaz,
istemin doğru birleştiğini gösterir.

---

## İlk gerçek koşu — maliyet ölçümü

Bütün maliyet kararının dayanağı bu:

```bash
python kosum.py --belge 01
```

Ekranda şuna benzer bir satır çıkar:

```
belge_01  girdi 1847 | çıktı 96 | düşünme 412 | toplam 2355  |  3.4 sn
```

**`düşünme` sütunu kritik.** Kimi K3 testinde ekranda ~100 token görünmüş
ama faturaya ~6000 token yansımıştı; aradaki fark görünmeyen düşünme
tokenleriydi ve maliyeti 20 kat şişirmişti.

Bu sayı yüksekse `yapilandirma.json` içindeki `_reasoning_effort` satırının
başındaki alt tireyi kaldırın (`"reasoning_effort": "low"`) ve kaliteyi
yeniden kontrol edin.

Gerçek para karşılığı için sağlayıcının fatura sayfasına bakın — betik token
sayar, fiyat bilmez.

---

## Klasör düzeni

```
istemler/
  talimat_v3.txt        SABİT talimat bloğu (bütün belgelerde aynı)
  sartname_NN.txt       belgeye özel şartname + son kontrol listesi
ciktilar/
  MODEL_ADI/
    belge_NN.txt        üretilen metin gövdesi
kayit/
  kosum.jsonl           belge başına token, süre, hata kaydı
```

### Talimat neden ayrı dosyada

- Talimattaki bir hata **tek dosyada** düzeltilir, 450 belgede değil
- Dosya adındaki sürüm numarası kayda düşer; "belge 47 neden bozuk?"
  sorusunun cevabı hangi talimatla üretildiğine bakılarak verilir
- ADIM 4'te şartnameler üreteçten gelecek, talimat dosya olarak kalacak

### Son kontrol listesi neden şartnamede

Listenin 5. maddesi belgeye özeldir (`"arz ederim." mi` / `"rica ederim." mi`).
Talimata koyulamaz.

---

## Bilinmesi gerekenler

**Betik çıktıyı denetlemez.** Kural kontrolü 1.2'deki mini linter'ın işi.
Üretim ve denetim ayrı katmanlar; karıştırılırsa ikisi de ayrı ayrı test
edilemez.

**Tekrar çalıştırmak güvenlidir.** Çıktı dosyası varsa o belge atlanır.
450 belgelik koşu 380'de çökerse ilk 380 için ikinci kez ödeme yapılmaz.

**Bir belge hata verirse koşu durmaz.** Hata kayda yazılır, sonrakine geçilir.
Eksikler sonradan aynı komutla tamamlanır.

**Bütçe sınırı bir belge kadar aşılabilir.** Bir çağrının maliyeti ancak
yapıldıktan sonra bilinir; sınır belirlerken bir belgelik pay bırakın.

---

## Değerlendirme (1.4)

Her belge için üç soru — üçü de "evet" ise o belge geçti. Eşik: 10'da 7.

1. **Kip** — metin baştan sona resmî kurumsal kipte mi?
2. **Görev** — şartname yerine getirilmiş mi, *ve* şartnamede olmayan bir
   bilgi uydurulmamış mı?
3. **Doğallık** — gerçek bir kurumun evrakında görsen yadırgar mıydın?

İkiniz **ayrı ayrı** puanlayın, sonra karşılaştırın. Anlaşamadığınız belgeyi
**hayır** sayın. 10 belgede 4'ten fazla anlaşmazlık çıkarsa sorun sonuçta
değil, soru tanımlarındadır.
