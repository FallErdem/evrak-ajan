# Evrak Ajanı

Kamu evrak ve yazışma süreçleri için çok ajanlı destek sistemi.
**TEKNOFEST Yapay Zekâ Dil Ajanları Yarışması · Senaryo 1**.

Evrak Ajanı, sisteme verilen bir PDF belgesini okur, alanlarına ayırır ve türünü belirler. Mevzuata göre eksiklerini tespit eder, özetini çıkarır, ilgili birime yönlendirir ve cevap yazısının taslağını üretir. Taslak, 40 kurallık bir üslup denetiminden geçer. Sistem nihai olarak şu soruya cevap verir: **"Bu belge insana sorulmadan geçebilir mi?"**. Cevap hayır ise, belge reddedilme veya eksiklik gerekçeleriyle birlikte memurun onay kuyruğuna düşer.

---

## İçindekiler

- [Mimari ve Akış](#mimari)
- [Temel Bileşenler](#temel)
- [Performans ve Ölçümler](#performans)
- [Kurulum ve Çalıştırma](#kurulum)
- [Bilinen Sınırlar](#sinirlar)
- [Veri Seti ve Lisans](#veri)

---
<a id="mimari"></a>
## Mimari ve Akış

Sistem mimarisi; özerkliğin gerektiği yerlerde ajanların, mümkün olan yerlerde deterministik araçların kullanılması prensibine dayanır. Toplamda **sekiz bileşen, iki ajan, dört tek atışlık model çağrısı ve iki deterministik araç** bulunmaktadır.

Aşağıda sistemin genel akış şeması yer almaktadır:

<img width="4620" height="8192" alt="Image" src="https://github.com/user-attachments/assets/b865e980-d4b8-46c6-a102-1c075b673f1c" />

> **Mimari Notu:** Yukarıdaki akış şeması kavramsal olarak 12 adımı gösterse de, sistem entegrasyonu aşamasında bileşenler optimize edilerek **8 ana bileşene** indirilmiştir (Örn: Sınıflandırıcı ve Bilgi Çıkarıcı tek bir *Anlama* modülünde birleşmiştir).
> 
> 

---
<a id="temel"></a>
## Temel Bileşenler

| # | Bileşen | Tür | Görevi |
| --- | --- | --- | --- |
| 1 | **Okuyucu** | Araç | PDF belgesini okur, metin katmanı yoksa OCR uygular.|
| 2 | **Ayrıştırıcı** | Melez | Sayı, tarih, konu, muhatap, imza ve diğer alanları ayrıştırır.|
| 3 | **Anlama** | LLM | Tek çağrıda belge türünü, SDP kodunu ve talepleri belirler.|
| 4 | **Denetçi** | **AJAN 1** | Eksik bilgileri ve mevzuat dayanağını araç döngüsü (ReAct) ile tespit eder.|
| 5 | **Özetleyici** | LLM | En fazla 1500 karakterlik, sayısal doğrulamalı kısa ve öz özet çıkarır.|
| 6 | **Yönlendirici** | Melez | Evrağın 3 kurum ve 35 birim arasından hangisine gideceğini (çoğunlukla LLM kullanmadan) bulur.|
| 7 | **Yazar** | **AJAN 2** | Kimlik ve yön belirler, taslak üretir ve üslup döngüsü ile (linter) metni düzeltir.|
| 8 | **Güven Kapısı** | Araç | Tüm girdileri kontrol eder, otomatik onay veya insan onayı kararı verir.|

---
<a id="performans"></a>
## Performans ve Ölçümler

Tüm metrikler 300 belgelik veri seti üzerinden, gerçek LLM çağrılarıyla elde edilmiştir. Ölçülmeyen hiçbir veri rapora dahil edilmemiştir.

* **Sınıflandırma Doğruluğu:** %96,7 (30 belge üzerinde).


* **Yönlendirme Başarımı:** %98,7 (300 belgede yalnızca 15 model çağrısıyla).


* **Eksik Bilgi Tespiti:** 21 aktif kural ile 153 kusursuz belgede **0 yanlış alarm**.


* **Yazı Şablonu Kalitesi:** İlk turda %83,3 oranında tamamen temiz taslak; kalanlarda üslup döngüsü başarıyla düzeltme yaptı (**0 pes etme**).


* **Güven Kapısı (Otomatik Onay):** %71,7 oranında otonom işlem başarısı.


* **Sızan Hata Oranı:** **0** (Otomatik onaylanan hiçbir belgede yanlış yönlendirme yapılmamıştır).


* **Hız ve Maliyet:** Belge başına ortanca işlem süresi 23,8 saniye olup, belge başına ortalama 2,2 LLM çağrısı yapılmaktadır.



---
<a id="kurulum"></a>
## Kurulum ve Çalıştırma

Arayüz (UI) ve arka uç (backend) tamamen birleştirilmiştir ve tek bir boru hattı üzerinden (`boru_hatti.isle()`) entegre çalışmaktadır.

### Gereksinimler

* Python 3.13


* Node 20+ (Arayüz için)


* OpenAI uyumlu bir API anahtarı (örn. OpenRouter)



### Başlangıç Adımları

**1. Çevreyi Hazırlayın**

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows için
pip install -r requirements.txt
pip install fastapi uvicorn python-multipart

```

**2. API Anahtarını Ekleyin**
API anahtarınızı `.gizli/api_anahtari.openrouter.txt` dosyası içine yerleştirin. Anahtar bulunamazsa sistem LLM'siz kipte (sadece deterministik kural motoruyla) açılır.

**3. Sunucuları Başlatın (İki ayrı terminalde)**

```bash
# Terminal 1: Backend (Gerçek Sunucu)
cd ui
uvicorn gercek_sunucu:app --port 8000

# Terminal 2: Frontend (Arayüz)
cd arayuz
npm install
npm run dev

```

Uygulamaya `http://localhost:5173` adresinden erişebilirsiniz. Backend ise `http://localhost:8000` portunda çalışacaktır.

---
<a id="sinirlar"></a>
## Bilinen Sınırlar


* **Kural Kapsamı:** Mevcut kural motoru 21 maddeyi kapsar. Dış mevzuat ve dış veri tabanı doğrulaması gerektirmeyen, doğrudan belge üzerinden kusur tespiti yapılabilen tüm kurallar işlenmiştir.


* **Çok Sayfalı Belgeler:** Veri setinin tamamı tek sayfadan oluştuğu için çok sayfalı belgeler şu an için kapsam dışıdır.


* **Sentetik Veri:** Eğitim/test setindeki kimlik numaraları vb. bilgiler tamamen sentetiktir.



---
<a id="veri"></a>
## Veri Seti ve Lisans

* **Modeller:** Qwen 3.8 27B (OpenRouter üzerinden, Apache 2.0 lisanslı) başta olmak üzere açık ağırlıklı modeller tercih edilmiştir. Model ağırlıkları şartname gereği depoya yüklenmemiştir.


* **Veri Seti:** 300 adet sentetik evrak kullanılmış olup gerçek kişi veya kurum verisi içermemektedir.


* **Lisans:** Bu projenin kodları Apache License 2.0 ile lisanslanmıştır.
