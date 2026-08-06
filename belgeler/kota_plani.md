# Kota Planı — Geliştirme Seti (300 belge)

**Parça 2 / ADIM 4.1**

Bu belge, üretilecek 300 belgenin dağılımını tanımlar. ADIM 4.2'de üreteç bu
planı `veri/kota.json` olarak okuyacak ve **kotayı tutarak** üretecek —
rastgele seçim yapmayacak.

---

## Neden kota, neden rastgele değil

Rastgele dağıtım şuna yol açar:

```
sayi_eksik      :  3 belge   <- olcumez
tarih_eksik     : 19 belge
tarama_bozuk    :  2 belge   <- olcumez
```

Üç örnekle "sistem bu kusuru %67 yakalıyor" denemez. Üreteç her boyutta kaç
belge üreteceğini önceden bilir ve sayar; hedefe ulaşınca o kombinasyonu
kapatır.

---

## 1 · Alıcı kurum

Belgeler sisteme **gelen** evraktır. Alıcı, üç kurumdan biridir.

| Kurum | Belge | Oran | Gerekçe |
|---|---|---|---|
| Yenimahalle Belediyesi | 120 | %40 | 14 müdürlük, 15 vatandaş yaprağı — en yoğun vatandaş trafiği |
| Ankara İl MEM | 100 | %33 | 6 birim, üstten gelen genelge trafiği yoğun |
| Gazi Üniversitesi | 80 | %27 | 7 birim, 12 vatandaş yaprağı |

---

## 2 · Gönderen tipi — kapanış yönünü bu belirler

Gelen belgede kapanış, **gönderenin alıcıya göre konumuna** bağlıdır.
Kılavuz 13.1: rica yalnızca aşağı doğru.

| Gönderen | Belge | Kapanış | Örnek |
|---|---|---|---|
| Gerçek kişi (vatandaş) | 108 | arz | Vatandaş → Belediye, imar durum belgesi talebi |
| Özel hukuk tüzel kişi | 24 | arz | Yapı denetim firması → Belediye |
| **Üst makam** | **72** | **rica** | MEB → İl MEM genelgesi |
| Aynı düzey | 60 | arz | Gazi → İl MEM, protokol yazısı |
| Alt makam | 36 | arz | İlçe MEM → İl MEM, rapor |

**Kapanış dağılımı:** arz 228 (%76) · rica 60 (%20) · **arz/rica 12 (%4)**

Karma kapanış, üst makamın hem üst hem ast makamlara **dağıtımlı** gönderdiği
yazılardan gelir (`DAĞITIM YERLERİNE`). 72 üst makam belgesinin 12'si böyle.

### Gönderen tipinin kurumlara dağılımı

| Gönderen | Belediye | İl MEM | Üniversite | Toplam |
|---|---|---|---|---|
| Vatandaş | 44 | 34 | 30 | 108 |
| Özel tüzel kişi | 14 | 8 | 2 | 24 |
| **Üst makam** | **32** | **26** | **14** | **72** |
| Aynı düzey | 18 | 20 | 22 | 60 |
| Alt makam | 12 | 12 | 12 | 36 |
| **Toplam** | **120** | **100** | **80** | **300** |

**Üst makam belgeleri neden eşit dağıtılmadı.** Her kurumun kaç ayrı üst makam
kaynağı olduğu farklı:

| Alıcı | Üst makam kaynağı | Belge/kaynak |
|---|---|---|
| Belediye | 6 (Valilik, Kaymakamlık, ABB, 2 Bakanlık, kurum içi) | ~5 |
| İl MEM | 3 (MEB, Valilik, kurum içi) | ~9 |
| Üniversite | **2** (YÖK, kurum içi) | ~7 |

Eşit dağıtsaydık üniversiteye 19 rica belgesi düşerdi ve hepsi YÖK ile
Rektörlükten gelirdi. Sistem o zaman *"üst makam → rica"* kuralını değil,
*"YÖK → rica"* eşleşmesini ezberleyebilirdi. Kaynak çeşitliliği fazla olan
belediyeye ağırlık vermek bu riski azaltıyor.

Bu dağılım gerçekçi de: belediyeler bakanlık ve büyükşehirden yoğun genelge
alır, üniversiteler özerkliği gereği daha az üst yazışma alır.

**Özel tüzel kişi dağılımı** aynı mantıkla: yapı denetim firmaları, müteahhitler
ve işletmeler ağırlıkla belediyeye yazar; üniversiteye nadiren.

### Rica neden yeterli oranda

Sistem "hep arz de" derse **%76 doğruluk** alır. Gerçek bir sistem %95 civarı
alır. Aradaki 19 puanlık fark, ezber ile öğrenmeyi ayırmaya yeter.

Rica oranını yapay olarak %50'ye çıkarmak gerçekçiliği bozardı — kamu
kurumlarına gelen evrakın çoğu gerçekten alttan veya yandan gelir.

### Üst makam kaynakları

| Alıcı | Üst makamlar |
|---|---|
| Belediye | Ankara Valiliği · Yenimahalle Kaymakamlığı · Ankara Büyükşehir Bld. · İçişleri Bak. · Çevre ve Şehircilik Bak. · Belediye Başkanlığı (kurum içi) |
| Üniversite | YÖK · Rektörlük (kurum içi) |
| İl MEM | Millî Eğitim Bakanlığı · Ankara Valiliği · İl MEM (şubelere, kurum içi) |

---

## 3 · Belge türü

### Vatandaş / özel kişi belgeleri — 132

| Tür | Belge | Not |
|---|---|---|
| Dilekçe (talep) | 66 | En yaygın; belge/hizmet talebi |
| Şikâyet | 33 | Duygusal ton, resmî kalıp |
| Bilgi edinme başvurusu | 22 | 4982 sayılı Kanun atfı |
| İtiraz | 11 | Olumsuz karara itiraz |

**Yapısal fark:** Dilekçede başlık bloğu, sayı satırı ve konu satırı **yoktur.**
Belge doğrudan muhatap makamla başlar. Üreteç bunları resmî yazıyla aynı
şablondan basmamalıdır.

### Kurum yazıları — 168

| Tür | Belge | Tipik gönderen |
|---|---|---|
| Bilgilendirme / duyuru | 42 | Üst makam (genelge, talimat) |
| Talep yazısı | 38 | Aynı düzey, alt makam |
| Cevap yazısı | 34 | Her yön (ilgi zorunlu) |
| Görüş talebi | 20 | Aynı düzey |
| Üst yazı (ek gönderimi) | 18 | Her yön (ek zorunlu) |
| Tekit yazısı | 10 | Üst makam (ilgi zorunlu) |
| Olur yazısı | 6 | Kurum içi |

> Bu türler `veri_yapisi.py` içindeki `GelenTur` enum değerlerine
> eşlenecektir. Eşleme 4.2'de yapılacak; enum'da karşılığı olmayan tür
> varsa ya en yakınına eşlenir ya da enum genişletilir (ADIM 10 dondurma
> öncesi).

---

## 4 · İlgi ve ek

| Alan | Var | Yok |
|---|---|---|
| İlgi | 120 (%40) | 180 |
| Ek | 90 (%30) | 210 |

**Zorunluluklar:**
- Cevap yazısı (34) ve tekit yazısı (10) → ilgi **her zaman** var
- Üst yazı (18) → ek **her zaman** var
- Dilekçe (66) → ilgi yok, ek %25 (tapu, kimlik fotokopisi vb.)

---

## 5 · PDF biçimi

T-01 kararı gereği:

| Biçim | Belge | Not |
|---|---|---|
| Metin katmanlı (dijital doğumlu) | 250 | Docling doğrudan metin çıkarır |
| Taranmış görüntü | 50 | OCR gerekir |

Taranmış 50 belgenin 10'u ayrıca `tarama_bozuk` kusuru taşır (eğri, gürültülü).
Kalan 40'ı temiz taramadır — OCR'ın normal işini de ölçebilmek için.

---

## 6 · Kusur dağılımı

| Durum | Belge |
|---|---|
| Kusursuz | 180 (%60) |
| Tek kusurlu | 120 (%40) |

Geliştirme setinde **çoklu kusur yoktur.** Sebebi ölçüm netliği: bir belgede iki
kusur varsa, sistem birini yakalayıp diğerini kaçırdığında hangi kusurun
tespit oranına ne yazacağımız belirsizleşir. Çoklu kusur zorlayıcı setin
(50 belge) işidir.

### 11 kusur profili

| # | Kusur | Belge | Ne yapılıyor | Ön koşul |
|---|---|---|---|---|
| 1 | `sayi_eksik` | 12 | Sayı satırı boşaltılır | kurum yazısı |
| 2 | `tarih_eksik` | 12 | Tarih silinir | — |
| 3 | `konu_eksik` | 10 | Konu satırı silinir | kurum yazısı |
| 4 | `imza_eksik` | 10 | İmza bloğu silinir | — |
| 5 | `muhatap_belirsiz` | 10 | Muhatap `İLGİLİ MAKAMA` yapılır | — |
| 6 | `ilgi_kopuk` | 12 | İlgi satırı var, metinde atıf yok | **ilgi_var** |
| 7 | `ek_beyani_yanlis` | 10 | `Ek: 2` yazar, 1 ek vardır | **ek_var** |
| 8 | `sdp_uyumsuz` | 12 | Sayıdaki SDP kodu konuyla ilgisiz | kurum yazısı |
| 9 | `tarih_tutarsiz` | 12 | İlgi tarihi belge tarihinden **sonra** | **ilgi_var** |
| 10 | `kapanis_yanlis` | 10 | ALT'a arz, ÜST'e rica yazılır | kurum yazısı |
| 11 | `tarama_bozuk` | 10 | Eğri, gürültülü, düşük çözünürlük | **taranmış** |
| | **Toplam** | **120** | | |

### Ön koşul kontrolü

| Kusur | Gerekli | Mevcut | Durum |
|---|---|---|---|
| 6 + 9 | ilgi_var | 120 | 24 ≤ 120 ✓ |
| 7 | ek_var | 90 | 10 ≤ 90 ✓ |
| 11 | taranmış | 50 | 10 ≤ 50 ✓ |
| 1, 3, 8, 10 | kurum yazısı | 168 | 44 ≤ 168 ✓ |

Üreteç bu ön koşulları **enjeksiyon öncesi** kontrol etmeli. Ön koşulu
sağlamayan bir belgeye kusur enjekte edilirse etiket yalan söyler:
`ilgi_kopuk` kusuru olan ama ilgisi olmayan bir belge anlamsızdır.

### Kusur × kurum çaprazı

**Her kusur türü, üç kurumun her birinde en az 3 belge.**

Neden: bir kusur tek kurumda toplanırsa, tespit başarısızlığında sebebin kusur
mu kurum mu olduğunu ayıramayız. 12'lik kusurlar 4-4-4, 10'luklar 4-3-3 dağılır.

---

## 7 · Çeşitlilik kısıtları

Şartname 6.5 çeşitliliği ödüllendiriyor. Üreteç şunları da tutmalı:

| Kısıt | Değer | Gerekçe |
|---|---|---|
| SDP kodu başına belge | en az 1, en çok 6 | 72 atanmış yaprak kod |
| Birim başına belge | en az 3 | 30 alıcı birim (kurum + müdürlük/şube) |
| Aynı örnek konu tekrarı | en çok 3 | 345 konu başlığı mevcut |
| Kişi adı tekrarı | en çok 3 | ~150 kurgusal ad havuzu |
| Belge tarihi aralığı | 01.01.2026 – 31.05.2026 | 5 aya yayılır |
| Aynı gün belge sayısı | en çok 6 | tarih kümelenmesini önler |

### Fizibilite — plan üretilebilir mi

Kısıtlar veriye karşı sınandı:

| Kurum | Hedef | Alıcı birim | Yaprak SDP kodu | Tavan (kod×6) | Durum |
|---|---|---|---|---|---|
| Belediye | 120 | 15 | 39 | 234 | rahat |
| İl MEM | 100 | 7 | **22** | 132 | **en dar** |
| Üniversite | 80 | 8 | 29 | 174 | rahat |

**İl MEM en sıkışık nokta:** 100 belge 22 yaprak koda dağılacak, kod başına
ortalama 4,5. Tavan 6 olduğu için üreteç dengeli dağıtmak zorunda; birkaç kodu
6'ya doldurup diğerlerini boş bırakırsa kota tutmaz. Üreteç en az kullanılan
kodu tercih eden bir seçim yapmalı.

Vatandaş belgeleri de kontrol edildi:

| Kurum | Vatandaş belgesi | Vatandaş yoğun birim | Vatandaş yaprak kodu | Tavan |
|---|---|---|---|---|
| Belediye | 44 | 11 | 24 | 144 |
| İl MEM | 34 | 6 | 16 | 96 |
| Üniversite | 30 | 6 | 18 | 108 |

Üçünde de tavan hedefin en az iki katı. Sıkışma yok.

### Başlık bloğu varyantı

Gazi Üniversitesi başlığı iki biçimde de gerçek kullanımda görülüyor:

```
T.C. / GAZİ ÜNİVERSİTESİ REKTÖRLÜĞÜ / {birim}     %60
T.C. / GAZİ ÜNİVERSİTESİ / {birim}                %40
```

İkisini de üretiyoruz. Sebep: sistem **ikisini de tanımalı.** Tek biçimle
üretirsek, jüri diğerini verdiğinde sistem şaşırır.

### İmza gerçekçiliği

19 gerçek belgenin gözlemi: imzalayan çoğu zaman birimin başı **değil.**

| Biçim | Oran | Örnek |
|---|---|---|
| Birimin başı | %60 | `Müdür`, `Dekan`, `Daire Başkanı` |
| Vekâleten (`a.`) | %30 | `Müdür a. / Şube Müdürü`, `Bakan a. / Genel Müdür V.` |
| Yardımcı | %10 | `Dekan Yardımcısı`, `Müdür Yardımcısı` |

**Dikkat — K 13.1:** Belge `a.` ile imzalandığında kapanış, yetkiyi **devreden**
makamın hiyerarşik durumuna göre seçilir. `Müdür a.` ile imzalanan bir yazıda
hiyerarşi şube müdürüne göre değil, müdüre göre hesaplanır.

---

## 8 · Diğer iki set

Bu plan geliştirme seti içindir. Diğer ikisi ADIM 7'de üretilecek.

| Set | Belge | Kusursuz | Kusurlu | Amaç |
|---|---|---|---|---|
| Geliştirme | 300 | 180 | 120 (tek) | Günlük geliştirme, istem ayarı |
| Altın | 100 | 60 | 40 (tek) | Final ölçüm — geliştirme sırasında BAKILMAZ |
| Zorlayıcı | 50 | 0 | 50 (çoklu) | Tavan testi, güven kalibrasyonu |

### Kusur başına toplam örnek

```
Gelistirme :  ~11
Altin      :   ~4
Zorlayici  :   ~9   (coklu kusur, belge basina 2-3)
------------------
Toplam     :  ~24
```

24 örnekle bir tespit oranı ölçülebilir. 11 ile ölçülemez: 9/11 = %82 ama
gerçek oran %52-%96 arasında herhangi bir yerde olabilir.

### Altın set neden ayrı üretilecek

Geliştirme setine 40 kez bakıp istemi ona göre ayarlarsanız, o setteki skor
şişer — sisteme değil, o 300 belgeye özel çözüm üretmiş olursunuz. Altın set
bunu yakalar:

```
Gelistirme setinde  : %89   <- 40 tur ayarlandi
Altin sette         : %71   <- ilk kez goruyor
```

Aradaki fark aşırı uyumdur ve jüri önünde altın sete yakın sonuç alırsınız.
Bu yüzden altın set **farklı bir modelle** üretilir; aynı üretecin desenlerini
taşımasın.

---

## 9 · Tekrarlanabilirlik

Üreteç bir **tohum (seed)** alacak. Aynı tohum + aynı plan = aynı 300 belge.

Sebebi: Parça 10 yeniden üretilebilirlik iddia edecek (şartname madde 8).
Tohum kaydedilmezse "biz bu sonuçları şu veriyle aldık" denemez.

Tohum `kota.json` içinde ve her belgenin etiketinde saklanacak.

---

## 10 · Özet — üretecin tutacağı sayılar

```
TOPLAM 300

kurum        belediye 120 | il_mem 100 | universite 80
gonderen     vatandas 108 | ozel 24 | ust 72 | ayni 60 | alt 36
kapanis      arz 228 | rica 60 | karma 12
tur          dilekce 66 | sikayet 33 | bilgi_edinme 22 | itiraz 11
             bilgilendirme 42 | talep 38 | cevap 34 | gorus 20
             ust_yazi 18 | tekit 10 | olur 6
ilgi         var 120 | yok 180
ek           var 90 | yok 210
pdf          metin_katmanli 250 | taranmis 50
kusur        yok 180 | var 120  (11 profil, her biri 10-12)
```
