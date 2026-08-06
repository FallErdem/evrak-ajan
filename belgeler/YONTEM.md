# sdp_kodlari.csv — Nasıl Üretildi

TEKNOFEST 2026 Yapay Zekâ Dil Ajanları Yarışması, 1. Senaryo.
Türk kamu kurumlarının resmî yazışmalarını işleyen sistem için sentetik belge üretiminde
kullanılacak Standart Dosya Planı (SDP) kod havuzu.

Bu belge, çıktının **nasıl** üretildiğini ve **neden bu şekilde** üretildiğini anlatır.
Amaç: aynı işi başka biri tekrarlayabilsin, genişletebilsin ve hatalarını yakalayabilsin.

---

## 1. Çıktı

`sdp_kodlari.csv` — 115 satır, UTF-8 (BOM'suz), LF satır sonu, virgül ayraç,
virgül içeren alanlar çift tırnaklı.

10 sütun: `kod, ana_grup, seviye, ust_kod, ad, saklama_suresi, kapsam, kurum_tipi,
vatandas_konusu, ornek_konular`

| Grup | Satır | Kod aralığı |
|---|---|---|
| Ortak | 40 | 000-099, 600-999 |
| Belediye | 27 | 100-599 |
| Üniversite | 23 | 100-599 |
| İl Millî Eğitim Müdürlüğü | 25 | 100-599 |

`vatandas_konusu=evet`: 51 satır (%44). Seviye dağılımı: 55 / 49 / 11.

---

## 2. SDP'nin gerçek yapısı (doğrulanmış)

Belge sayısının ikinci bölümü SDP kodudur:

```
E-71368504-010.06.01-4471829
  │        │          │
  │        │          └─ kayıt numarası
  │        └─ SDP kodu
  └─ DETSİS numarası
```

Plan **üç bloktan** oluşur:

| Aralık | İçerik | Kim yayımlar |
|---|---|---|
| 000-099 | Genel İşler | Devlet Arşivleri Başkanlığı — **tüm kurumlarda aynı** |
| 100-599 | Kurumsal Alan (ana hizmet) | Her kurum grubu kendi planını yayımlar — **kuruma özel** |
| 600-999 | Ortak alanlar | Devlet Arşivleri Başkanlığı — **tüm kurumlarda aynı** |

**Yaygın bir yanılgı:** "600-799 Danışma-Denetim / 800-999 Yardımcı Hizmetler" ayrımı
**V.3'e (2012-2023) aittir.** V.4'te 600-999 tek ortak bloktur ve alt bölümleri şöyledir:

```
600-619 Araştırma ve Planlama      800-819 İdari ve Sosyal
620-639 Basın ve Halkla İlişkiler   820-839 Tanıtım ve Yayın
640-659 Hukuk                       840-869 Mali
660-679 Teftiş/Denetim              870-899 Özel Kalem ve Protokol
700-719 Bilgi Sistemleri            900-929 Personel
720-739 Dış İlişkiler               930-949 Satınalma ve Satış
740-749 Avrupa Birliği              950-969 Güvenlik / Afet / Sivil Savunma
750-769 Emlak ve Yapım
770-799 Eğitim
```

**970-999 aralığı V.4'te boştur.** Plan 000'dan 969'a kadar gider.

---

## 3. Kaynak zinciri

Nihai sürümde kullanılan **tek kaynak türü resmî `.xls` dosyalarıdır**:

| Dosya | Sayfa | Kayıt | Yürürlük dayanağı |
|---|---|---|---|
| `SSDP__2024_V_4___1_.xls` | `V.4_(2024)` | 718 | DAB 23.10.2023 / E-72424901-805.01.01-86936, **2.1.2024**'ten itibaren |
| `Belediye_SSDP.xls` | `Belediyeler` | 392 | Başbakanlık 09.01.2018 / 63788445-... |
| `YÖK_SSDP.xls` | `YÖK` | 468 | Başbakanlık 24.11.2017 / 63788445-... |
| `29105813_mebsaklamasurelistandartdosyaplani__1_.xls` | `MEB SDP 100-599- 2024` | 388 | MEB Destek Hizmetleri GM, **2024** |

Hepsi `devletarsivleri.gov.tr` "Standart Dosya Planı / Saklama Planları" sayfasından ve
`dhgm.meb.gov.tr` mevzuat sayfasından indirilebilir.

### Neden ikincil kaynak yetmedi

İlk turda bu dosyalara doğrudan erişilemedi (site bot koruması / robots.txt / binary
`.xls`). Onun yerine üniversite ve belediye sitelerinin yayımladığı PDF kopyalar kullanıldı.
Bu yaklaşımın **üç somut zararı çıktı**, hepsi resmî dosyalar gelince ortaya döküldü:

1. **PDF metin çıkarımı hiyerarşiyi kaybediyor.** `641.04 İdari Davalar` mı yoksa
   `641.03.04` mü olduğu PDF metninden ayırt edilemedi; girinti bilgisi kayboluyor.
   Resmî `.xls`'te her seviye ayrı sütunda olduğu için belirsizlik yok — `641.04` doğru.
2. **PDF kopyalar eski.** MEB için bulunan PDF 2018 dönemine aitti ve **saklama süresi
   sütunu hiç yoktu**; 23 satırın `saklama_suresi` alanı boş kalmıştı.
3. **Elle transkripsiyon hatası.** `115.02.11` için PDF'ten `B` okunmuştu; resmî dosyada
   bu alan **boş** (çünkü kodun kendi süresi yok, alt kodları var).

**Kural:** SDP gibi hiyerarşik + normatif verilerde ikincil kaynak yalnızca keşif içindir.
Nihai veri mutlaka kurumun kendi yayımladığı makine-okunur dosyadan üretilir.

---

## 4. `.xls` dosyalarını okuma yöntemi

Dört dosya da eski BIFF formatında (`D0 CF 11 E0` imzası) — `openpyxl` okumaz,
`xlrd` gerekir (`pip install xlrd`).

### Sütun düzeni

```
Ana Dosya | 1. Alt Konu | 2. Alt Konu | 3. Alt Konu | Ad | Saklama Süresi | Tasfiye Kodu | [Açıklama]
```

Ortak plan (V.4) 8 sütunlu ve **`DOSYA KODU AÇIKLAMASI` sütunu var** — kullanım
kısıtları burada (bkz. §7). Kurumsal planlar 7 sütunlu, açıklama sütunu yok.

### İki farklı yazım biçimi — dikkat

Ortak plan her satırda ana dosya kodunu **tekrar eder**:
```
010 | 06 |    |    | Genelgeler       -> 010.06
```

Kurumsal planlar ana dosyayı **yalnızca bir kez yazar**, sonraki satırlarda boş bırakır:
```
105 |    |    |    | Meclis İşleri    -> 105
    | 04 |    |    | Meclis Kararları -> 105.04     <- 105'i taşımak gerekir
    | 06 |    |    | Meclis Komis.    -> 105.06
    |    | 01 |    | Toplantılar      -> 105.06.01
```

Bu yüzden parser **carry-forward** çalışır: dolu olan en soldaki sütun yeni seviyeyi
belirler, o seviye güncellenir, **altındaki tüm seviyeler sıfırlanır**, kod birleştirilir.

### Normalleştirme (uygulanan tek dönüşüm)

- Excel bazı hücreleri sayı olarak saklamış: `100.0` → `100`, `1.0` → `1`, `99.0` → `99`
- Ana dosya 3 haneye, alt konular 2 haneye sıfırla doldurulur: `1` → `01`
- Adlardaki `\n` boşluğa çevrilir
- YÖK planında `Denklik İşleri*` gibi **dipnot yıldızları** ad'ın parçası değildir, atılır

Bunlar dışında hiçbir kod veya ad değiştirilmedi. Kaynakta olmayan hiçbir kod uydurulmadı.

Parser sonucu: 4 dosyada **0 biçim hatası, 0 tekrar eden kod**. Bu, carry-forward
mantığının doğru çalıştığının kanıtıdır (yanlış olsaydı çakışan kodlar üretirdi).

---

## 5. Hangi kodların seçildiği

Dört dosyadaki **1966 resmî kayıttan** (718 ortak + 392 belediye + 468 üniversite + 388 MEB) 115'i seçildi. Ölçüt: **gerçek evrak trafiğinin büyük kısmını
oluşturan kodlar**, nadir olanlar değil. Vatandaş dilekçesi yazılabilen kodlara ağırlık
verildi (üretilecek belgelerin ~%40'ı dilekçe olacak).

**Kapanış kuralı:** bir kod seçildiyse, tüm üst kodları da satır olarak eklenir.
`115.02.01` seçildiyse `115.02` ve `115` de dosyada olmak zorundadır. Bu, hiyerarşinin
CSV içinde kendi kendine tutarlı olmasını sağlar.

### Türetilen alanlar — elle yazılmaz

`ana_grup`, `seviye`, `ust_kod` **koddan hesaplanır**:

```
ana_grup = kod[:3]
seviye   = kod.split(".") uzunluğu
ust_kod  = son parça atılmış hâli (seviye 1 ise boş)
```

Elle yazılırsa er geç tutarsızlaşır. Üretim betiği bunları her seferinde yeniden hesaplar.

### `ad` ve `saklama_suresi` de elle yazılmaz

Nihai sürümde bu iki alan **üretim anında resmî dosyalardan çekilir**. Betikte yalnızca
kod listesi ve insan kararı gerektiren alanlar (`vatandas_konusu`, `ornek_konular`) elle
tutulur. Bu ilkeye geçildiğinde 11 alan otomatik düzeldi — 10'u MEB'in eksik saklama
süresi, 1'i yanlış transkripsiyon.

### `ornek_konular`

Her kod için o kod altında gerçekten yazılabilecek 3 belge konusu, `|` ile ayrılmış.
Resmî yazının `Konu:` satırına yazılacak türden — **cümle değil, konu başlığı**:

```
İmar Durum Belgesi Talebi|Parsel İmar Durumu Hk.|İmar Durumu Bilgi Talebi
```

Bu sütun kaynakta yoktur; kurumsal yazışma pratiğinden yazılmıştır. Veri setinin en
yumuşak kısmı budur — kodlar doğrulanabilir, konu başlıkları doğrulanamaz.

---

## 6. Kod çakışması — bilinmesi zorunlu

**100-599 aralığında aynı sayı farklı kurumda farklı anlama gelir.**

| Kod | Belediye | Üniversite | MEB |
|---|---|---|---|
| `105` | Meclis İşleri | Ders Programları | Okul/Kurum Açma |
| `220` | Su ve Kanalizasyon | — | Devam-Devamsızlık |
| `135` | Cenaze Hizmetleri | — | Eğitim Kurumlarında Açılan Kurslar |
| `140` | Hayvan Sağlığı ve Veterinerlik | — | Taşımalı Eğitim **(MEB tercih edildi)** |
| `165` | Zabıta İş ve İşlemleri | — | Eğitime Yardımcı Dernek ve Kurumlar |

Brifingdeki "aynı kod iki kez geçmesin" kuralı bu yüzden 100-599'da **doğal olarak
tutturulamaz**. Kural korundu; çakışan kodlarda bir kurum tercih edilip diğeri listeden
çıkarıldı. Örnekler:

- `105` belediyede kaldı (Meclis İşleri); MEB tarafı `198 Eğitimle İlgili Defter, Dosya,
  Çizelge ve Belgeler` ile telafi edildi.
- `140` **MEB'e verildi** (Taşımalı Eğitim); belediyenin `140 Hayvan Sağlığı ve
  Veterinerlik` zinciri çıkarıldı, yerine `175 Ölçü Aletleri` ve `180.03 İtfaiye Uygunluk
  Raporları` eklendi.
- `210` MEB'de kaldı (Nakil ve Geçişler); bu yüzden belediyenin `210.05.03 Servis Aracı`
  kodu **alınamadı**. Okul servisi konusu ortak `802 Ulaşım ve Servis İşleri` üzerinden
  karşılanıyor. Servis aracı tahsis belgesi gerekiyorsa tekillik kuralı gevşetilmeli.

**Sonuç:** kodu asla tek başına anahtar yapma. Her yerde `(kod, kurum_tipi)` çifti taşı.
Tekillik kuralını bu çift üzerinden tanımlarsan liste taviz vermeden genişletilebilir —
üç kurumun tam havuzu (1248 kayıt) parse edilmiş durumda.

---

## 7. Belge üretirken uyulacak kullanım kısıtları

Bunlar V.4'ün `DOSYA KODU AÇIKLAMASI` sütunundan ve genel açıklamalarından çıkarıldı.
Uyulmazsa **biçimsel olarak geçersiz belge sayısı** üretilir.

**1. `020` ve `030.01-030.99` birincil kod olamaz.**
> "020 kodu ancak ikinci dosya kodu olarak kullanılabilir."
> "…030.01-030.99 kodları ancak ikinci dosya kodu olarak kullanılabilir."

Yani `E-71368504-020-4471829` geçersizdir. Bir Olur'da birinci kod işi ifade eden koddur.
Bu kodlar listeden çıkarıldı.

**2. Bölüm genelini belirten kodlar kullanılmaz.**
> "Plan'da bölüm genelini belirten kodlar kullanılmamalıdır (Örnek: 000- Genel İşler,
> 600- Araştırma ve Planlama İşleri, 640- Hukuk İşleri vb.)"

`000, 100, 300, 600, 620, 640, 660, 700, 720, 740, 750, 770, 800, 820, 840, 870, 900,
930, 950` — hiçbiri listede yok.

**3. `99 Diğer` kodları kontrollü kullanılır.** Sentetik veride hiç kullanılmadı.

**4. `saklama_suresi` boşsa o kod bir grup düğümüdür.**
Denetimde doğrulandı: `saklama_suresi` boş olan **47 satırın 47'sinde de** resmî planda
alt kod var; boş olup yaprak olan **tek satır yok**. Yani bu alan boşsa, o kodun altında
daha spesifik bir kod vardır ve belge kodu olarak tercihen alt kod seçilmelidir.

Ters durum her zaman geçerli değil: 19 satırda hem saklama süresi hem alt kod var
(YÖK ve MEB planlarında üst kod süreyi taşır, alt kodlar devralır — ör. `302.10 Belge
İşlemleri, 10` altında `01 Öğrenci Belgesi`, `04 Transkriptler`).

**5. `vatandas_konusu=evet` satırlarının 17'si grup düğümüdür.**
Dilekçe üretirken bunlar yerine alt kodlarını seçmek daha gerçekçi olur:
`115.02.11, 155.01, 102.03, 301.06, 302.01, 302.03, 302.08, 302.10, 302.11, 302.14,
302.15, 309, 310, 160.01, 160.02, 245.04, 250`

---

## 8. Doğrulama harness'ı

Her üretimden sonra çalıştırılan otomatik kontroller. Altı grup:

**A — Dosya seviyesi**
BOM yok · UTF-8 çözülüyor · CR yok · dosya newline ile bitiyor · Unicode NFC ·
Türkçe karakterler bozulmamış (`çğıöşüÇİÖŞÜ`) · mojibake taraması (`Ã`, `Â`, `U+FFFD`) ·
başlık satırı birebir beklenen 10 sütun

**B — Sütun kuralları**
`kod` regex `^\d{3}(\.\d{2}){0,3}$` · kod tekilliği · `ana_grup == kod[:3]` ·
`seviye == nokta sayısı + 1` · `ust_kod` türetimi doğru · **her `ust_kod` dosyada ayrı
satır** · seviye 1 ⟺ `ust_kod` boş · `ad` ≤ 200 karakter, boş değil, kırpılmış ·
`kapsam ∈ {ortak, kuruma_ozel}` · `vatandas_konusu ∈ {evet, hayir}` ·
`kurum_tipi` sözlüğe uyuyor · `kapsam=ortak ⟺ kurum_tipi=hepsi` ·
`ornek_konular` tam 3 parça, boş değil, cümle değil

**C — Resmî kaynak eşleşmesi**
Her kod ilgili resmî `.xls`'te var mı · `ad` birebir aynı mı · `saklama_suresi` aynı mı

**D — Hiyerarşi bütünlüğü**
Her `ust_kod` yalnızca CSV'de değil, **resmî planda da** gerçek bir kod mu

**E — Kullanım kısıtları**
Bölüm başlığı kodu yok · `020` yok · `030.x` yok · `.99` yok

**F — Dağılım bantları**
Toplam 80-120 · ortak 30-40 · belediye 20-30 · üniversite 15-25 · il MEM 15-25

**Son çalıştırma: 115/115 satır, 0 hata.**

---

## 8b. Okul binası, yatırım ve taşımalı eğitim nerede

Sık sorulan bir konu: **MEB'in kurumsal alanında (100-599) okul binası, inşaat, arsa
veya yatırım kodu yoktur.** MEB planının 100-199 bloğu tamamen eğitim-öğretim
faaliyetlerine ayrılmıştır. Bina ve yatırım işleri **ortak blokta** yürür:

| Konu | Kod | Blok |
|---|---|---|
| Yatırım programı, ödenek | `602.07 Yatırım Programı` | ortak |
| Okul projesi, zemin etüdü | `755.01 Etüd-Proje ve Fizibilite` | ortak |
| İnşaat süreci, süre uzatımı | `755.03 Uygulama` | ortak |
| İhale | `755.02 İhale` | ortak |
| Okul arsası tahsisi/devri | `756.01 Tahsis, Devir ve Takas` | ortak |
| Okul binası onarımı | `807.01 Bina ve Tesisler` | ortak |
| Kamulaştırma | `752.01 Kamulaştırma` | ortak |

MEB'in kurumsal alanında bina konusuna en yakın kod `105.04 Pansiyon Açma/Kapatma/
Kapasite Belirleme İşlemleri`'dir; o da idari bir işlem, yapım işi değil. `105` belediye
ile çakıştığı için alınmadı.

**Taşımalı eğitim** MEB'de tek koddur: `140 Taşımalı Eğitim` (10, D), alt kodu yoktur.

**Öğretmenlik uygulaması / uygulama öğrencisi** yazışmasının iki ucu iki farklı koddur:
üniversite tarafı ortak `773 Staj İşleri`, İl MEM tarafı `355.02 Eğitim Fakülteleri İle
İlişkiler`. Aynı yazışmanın gönderen ve alıcı kodları aynı olmak zorunda değildir —
her kurum kendi planına göre kodlar.

**Okul servisi araçlarının ruhsatı belediyededir** (`210.04.01.03 Servis Araçları`,
`210.05.03 Servis Aracı`), MEB'de değil. Bu kodlar `210` çakışması nedeniyle listede yok;
kurumun kendi servis hizmeti için ortak `802 Ulaşım ve Servis İşleri` kullanılıyor.

---

## 8c. Senaryoya göre yapılan kod eklemeleri ve çıkarmaları

Kod havuzu, üç kurumun gerçek yetki alanına göre budandı. Yapılan işlemler ve gerekçeleri:

| İşlem | Kod | Gerekçe |
|---|---|---|
| çıkarıldı | `220`, `220.01`, `220.01.01` Su ve Kanalizasyon / Abonelik | Ankara'da su ve kanalizasyon ASKİ'ye (Büyükşehir bağlı kuruluşu) aittir; ilçe belediyesi abonelik işlemi yapmaz |
| çıkarıldı | `754` İmar İşleri (ortak) | Belediye `115.x` kullanır; üniversite ve il MEM imar yazışması yapmaz |
| çıkarıldı | `040` Faaliyet Raporları | `801`'e yer açmak için; planlama-raporlama `602.04` ve `602.07` ile karşılanıyor |
| eklendi | `841.01` Bütçe Çalışmaları | `841` grup düğümüydü, bütçe yazışması için yaprak kod gerekiyordu |
| eklendi | `801` Taşıt ve İş Makineleri İşleri | Makine İkmal Bakım ve Onarım Müdürlüğü'nün ana hizmet kodu |

`180.03 İtfaiye Uygunluk Raporları` **çıkarılmadı**: Ankara'da itfaiye Büyükşehir'dedir, ama ilçe
belediyesi işyeri ruhsatı verirken bu raporu arar ve ABB İtfaiye Dairesi'ne yazar. Yani hizmet
olarak değil, **yazışma konusu olarak** vardır.

---

## 8d. Gerçek yazı örneklerinden çıkan bulgular

On bir gerçek resmî yazı incelendi (Gazi Üniversitesi, TRT, İŞKUR, MEB merkez ve taşra, özel okul).
Ayrıntılı kalıplar `belge_sablonu.json` dosyasındadır. Öne çıkan dört bulgu:

**1. Üniversitede DETSİS numarası alt birim düzeyindedir.** Aynı Teknoloji Fakültesi Dekanlığı'ndan
çıkan iki yazının sayısı farklı numarayla başlıyor: `E-67934452` (Öğrenci İşleri Birimi) ve
`E-70989351` (Tanıtım ve Yayın Birimi). Belge sayısı dekanlığın değil, parantezdeki birimin.

**2. Başlık bloğu 4 satır olabiliyor.** `T.C. / GAZİ ÜNİVERSİTESİ REKTÖRLÜĞÜ / Teknoloji Fakültesi
Dekanlığı / (Öğrenci İşleri Birimi)`. Üniversitede ikinci satır **REKTÖRLÜĞÜ ibaresiyle** yazılıyor.

**3. İmzalayan çoğu zaman birimin başı değildir.** Gözlenen kalıplar: `Müdür a. / Şube Müdürü`,
`Bakan a. / Ortaöğretim Genel Müdür V.`, `Dekan Yardımcısı`. `birimler.csv`'deki `imza_unvani`
alanı en üst yetkiliyi gösterir; üretilen belgelerin bir kısmı vekâleten imza kalıbı kullanmalıdır.

**4. `020` kodu gerçek yazışmada BİRİNCİL kod olarak kullanılıyor.** SSDP V.4'ün açıklama sütunu
"020 kodu ancak ikinci dosya kodu olarak kullanılabilir" der ve bu yüzden `020` havuzdan
çıkarılmıştı. Ancak MEB Talim ve Terbiye Kurulu Başkanlığı'nın 25.12.2024 tarihli olur yazısının
sayısı `E-75292403-**020**-119194271`. **Norm ile uygulama çelişiyor.** Havuza geri eklenmedi
(normatif kaynağa uyum korundu); makam oluru belgesi üretilecekse tek satırlık ekleme yeterlidir.

---

## 9. Bilinen sınırlar

**Kurumsal planların tarihi.** Ortak alan 2024 sürümü. MEB kurumsal alanı da 2024.
Ama **belediye planı 2018, YÖK planı 2017** tarihli. Devlet Arşivleri sitesinde güncel
olarak yayımlandıkları için yürürlükteler; ancak dilleri eski — YÖK planında hâlâ
"Sokrates/Erasmus", "Yrd. Doç.", "Leonardo Da Vinci" geçiyor. **`ad` alanındaki bu eski
terimleri belge metnine olduğu gibi taşırsan anakronik görünür.** Bugün üretilmiş gibi
duran bir yazıda "Yrd. Doç. Temsilcisi" ifadesi tutarsızlık sinyali verir.

**`ornek_konular` kısmen kalibre edildi.** Gerçek yazıların Konu satırlarıyla karşılaştırıldı:
kurumlar arası duyurularda düz isim tamlaması baskın ("Mezuniyet töreni", "Ulusal Staj Programı",
"ÇEDES Yıl Sonu Kültür Şenlikleri"), talep yazılarında "...Talebi" kalıbı doğru. Mevcut dağılım:
%33 "...Talebi", %29 düz isim tamlaması, %18 "...Hk.". Gerçek örneklerin tamamı duyuru niteliğinde
olduğu için dilekçe ve talep kalıbı hâlâ doğrulanmamıştır.

**`ornek_konular` tam doğrulanamaz.** Kodlar ve adlar resmî kaynaktan gelir; konu başlıkları
kurumsal yazışma pratiğinden yazılmıştır. Hata payı buradadır.

**Kapsam kısıtı.** 1966 resmî kayıttan 115'i seçildi. Nadir ama meşru kodlar dışarıda
kaldı; üretilen belgeler bu 116 kodun dağılımını yansıtacaktır, gerçek evrak trafiğinin
tam dağılımını değil.

**İl Özel İdaresi ayrımı yok.** Belediye planının resmî adı "Belediyeler **ve İl Özel
İdareleri**" SSDP'dir. Yalnızca ilçe belediyesi senaryosu hedeflendiği için özel idareye
özgü kodlar (`145 Tarımsal Hizmetler`, `195 Ekonomik Hizmet İşleri` gibi) alınmadı.

---

## 10. Brifingdeki hata

Brifingde örnek olarak `754.01 İmar Durumu` verilmişti. **Bu kod yok.**

V.4'te `754 İmar İşleri` tek satırdır, alt kodu yoktur (saklama `B`, tasfiye `D`).
Vatandaşın imar durum belgesi talebi **belediyede `115.02.01 İmar Durumu (Belgesi)`**
koduna girer.

Bu, §3'teki kuralın somut örneği: elde resmî dosya olmadan kod uydurulursa veri seti
sessizce geçersizleşir.

---

## 11. Yeniden üretme

```
1. Dört .xls dosyasını indir (§3'teki kaynaklar)
2. pip install xlrd
3. Ortak planı parse et      -> official.json   (kod, ad, saklama, tasfiye)
   4 seviye sütunu her satırda dolu; carry-forward gerekmez
4. Üç kurumsal planı parse et -> kurumsal.json  (kurum_tipi -> {kod: ...})
   carry-forward zorunlu (§4)
5. Kod listesini + vatandas_konusu + ornek_konular'ı elle tut
6. ana_grup / seviye / ust_kod'u koddan hesapla
7. ad / saklama_suresi'ni json'lardan çek — elle yazma
8. csv.writer, QUOTE_MINIMAL, lineterminator="\n", encoding="utf-8"
9. §8 harness'ını çalıştır; 0 hata görmeden teslim etme
```

Genişletmek istersen: `kurumsal.json` içinde üç kurumun **tam** kod havuzu var
(392 + 468 + 388). Yeni kod eklerken tek yapman gereken kodu listeye yazmak — ad ve
saklama süresi otomatik gelir, üst kodlar harness'ta kontrol edilir.
