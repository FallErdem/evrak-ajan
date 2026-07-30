# Risk testi belge kümesi

PARÇA 1 / ADIM 3'ün girdisi. Altı belge, beş temiz bir bozuk.

## Köken ve lisans

**Tamamı sentetiktir.** Hiçbir gerçek evraktan kopyalanmamış, hiçbir gerçek
yazışmanın metni kullanılmamıştır.

- **Kurum adları** gerçek kamu tüzel kişilerine aittir. Gerçekçilik ve standart
  dosya planı kodlarının anlamlı olması için böyle bırakıldı. Kurum adı kişisel
  veri değildir ve kamuya açıktır.
- **Kişi adları** kurgudur. Hiçbiri gerçek bir kamu görevlisine ait değildir.
- **Sayı numaraları** kurgudur, yalnızca biçim olarak geçerlidir.
- **İletişim bilgileri** yer tutucudur: telefonlar `000 00 00` kalıbında,
  e-posta alanı RFC 2606 ile ayrılmış `example.com`.
- **B04'teki T.C. Kimlik Numarası** (`10000000140`) sağlama toplamı kasıtlı
  olarak geçersiz olacak şekilde üretilmiştir; hiçbir gerçek kimlik numarasıyla
  çakışamaz.

Şartname dayanağı: **6.5** — *"kurgu evrak örnekleri ve yapay olarak
oluşturulmuş resmî yazışma taslakları"*. Madde **14** (KVKK) açısından kümede
gerçek kişiye ait hiçbir veri bulunmamaktadır.

## Biçim notu — önemli

Sayı alanları `rules.yaml` S-02'deki **2020 sonrası** biçimde yazılmıştır:

```
E-71368504-010.06.01-4471829
│ │        │          └─ kayıt numarası
│ │        └─ standart dosya planı kodu
│ └─ DETSİS numarası
└─ hazırlanma süreci (E / Z / O)
```

İnternette bulunan kamuya açık örneklerin çoğu 2020 öncesindendir ve süreç
harfi kayıt numarasının önünde durur (`96321565-774.09.03-E.79291`). O örnekleri
referans alırken bu farka dikkat edin — eski biçimi veri kümesine taşımak,
linter'ın kendi verinizi hatalı işaretlemesine yol açar.

## Belgeler

| Dosya | Tür | Ayırt edici özellik | Kural referansı |
|---|---|---|---|
| `B01_ust_yazi.txt` | üst yazı | ilgi + ek + dağıtım | S-02, M-11, ME-07 |
| `B02_cevap_yazisi.txt` | cevap yazısı | bir talebe cevap, alt→üst "Arz ederim" | S-02, ME-07 |
| `B03_bilgilendirme_yazisi.txt` | bilgilendirme | "işlem yapılmasına gerek bulunmamakta", Gereği/Bilgi ayrımı | S-02, M-11, ME-07 |
| `B04_vatandas_dilekcesi.txt` | vatandaş dilekçesi | başlık/sayı/konu yok, beş KVKK alanı | S-01 notu, ME-05 |
| `B05_duyuru.txt` | duyuru | GÜNLÜDÜR + son tarih | S-02, G-03, G-05, M-11 |
| `B06_bozuk_belirsiz.txt` | bilinmiyor | bozuk diakritik, kesilmiş sayfa, tablo kalıntısı | — |

`cevap_anahtari.json` her belge için türü, Test B'nin kavram gruplarını,
üstveri alanlarını ve varsa kişisel veri alanlarını tutar.

### Alternatif kabul edilen cevaplar

B03 ve B05'in sınırı doğası gereği bulanıktır — bir yönetmelik değişikliği
bildirimi hem bilgilendirme hem duyuru sayılabilir. Cevap anahtarında bunlar
`alternatif_kabul` alanıyla işaretlidir ve puanlamada doğru sayılır. Tam isabet
oranı raporda ayrıca gösterilir.

## Sonraki parçalarda ne olacak

- **Parça 2:** bu altı belge, sentetik üretecin biçim referansı olur. 300+
  belge oradan gelecek; bu küme elde kalır ve regresyon testi olarak kullanılır.
- **Parça 3:** B04 maskeleme katmanının, B06 OCR normalizasyonunun ilk testi.
- **Parça 10:** ablasyon tablolarında sabit karşılaştırma kümesi.

## Kamuya açık gerçek örnekler

Gerçeklik kontrolü için toplanan kamuya açık yazılar **bu depoya
konmamalıdır**: gerçek kişi adları, telefon ve e-posta bilgileri içerirler
(madde 14) ve şartname 6.5'in ilk cümlesi gerçek kamu verisi kullanılmayacağını
söyler. Referans olarak depo dışında tutun, biçim karşılaştırması için
kullanın, teslim edilen veri kümesine dahil etmeyin.
