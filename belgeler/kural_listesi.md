# Kural Listesi — 104 Denetim Maddesi

`rules.yaml`'daki kuralların tamamı. Kural motoru bir belgeyi alıp bu listeyi
baştan sona uygular ve ihlalleri raporlar.

## Nasıl okunur

**Nasıl** sütunu, o kuralın hangi yöntemle denetlendiğini söylüyor:

| Yöntem | Kaç kural | Ne demek |
|---|---|---|
| `regex` | 15 | Metinde desen aranıyor. Motor bir kez yazılır, hepsini işletir. |
| `boş olmamalı` | 5 | Alan dolu mu diye bakılıyor. |
| `alan eşitliği` | 3 | İki alan birbirine eşit mi. |
| `izinli küme` | 2 | Değer belirli listeden mi. |
| `boş liste olmamalı` | 1 | Liste en az bir eleman içeriyor mu. |
| `sözlük araması` | 1 | Kelime listesinde arama. |
| **özel fonksiyon** | **77** | **Her biri için ayrı Python kodu yazılacak.** |

**Ağırlık** sütunu sonucu belirliyor: `hata` düzeyinde bir bulgu belgeyi
düşürür, `uyari` ve `bilgi` düşürmez. 54 hata, 46 uyarı, 4 bilgi.

**Dayanak** sütunu:
- **Y** = Resmî Yazışmalarda Uygulanacak Usul ve Esaslar Hakkında Yönetmelik
  (10.06.2020 tarihli ve 31151 sayılı RG) — 60 kural
- **K** = Aynı Yönetmeliğin Kılavuzu (Cumhurbaşkanlığı) — 44 kural

Her bulgu bu referansla birlikte raporlanır: "K-02 · Kılavuz 12.2".

---

## Başlık bloğu — 8 kural

| Kural | Ne denetliyor | Nasıl | Ağırlık | Dayanak |
|---|---|---|---|---|
| **B-01** | Başlığın ilk satırı 'T.C.' kısaltması olmalıdır. | bulunmalı: regex `'^\s*T\.C\.\s*$'` | hata | Y 10/2 |
| **B-02** | Başlığın ikinci satırında idarenin adı tamamı büyük harflerle yazılmalıdır. | özel fonksiyon `baslik_idare_buyuk_harf` | hata | Y 10/2 |
| **B-03** | Başlığın üçüncü satırında birimin adı, kelimelerin ilk harfleri büyük diğerleri küçük olacak şekilde y… | özel fonksiyon `baslik_birim_ilk_harf` | hata | Y 10/2 |
| **B-04** | Başlıkta geçen bağlaçlar, bulunduğu satırın yazım düzeyine uymalıdır: küçük harfli yazımda 've', tamam… | özel fonksiyon `baslik_baglac_yazimi` | uyari | Y 16/8 |
| **B-05** | Başlıkta kullanılan idare ve birim adı, DETSİS'te kayıtlı ad ile aynı olmalıdır. | özel fonksiyon `baslik_detsis_esleme` | hata | Y 10/6 |
| **B-06** | Merkez teşkilatındaki birimler, bağlı bulundukları idare adıyla birlikte yazılmalıdır. | özel fonksiyon `baslik_merkez_birim_yalniz` | uyari | K 7.5 |
| **B-07** | Başlıkta, kuruluş kanununda veya Cumhurbaşkanlığı Kararnamesi'nde yer almayan alt birim adlarına yer v… | özel fonksiyon `baslik_alt_birim_fazlaligi` | uyari | K 7.5 |
| **B-08** | İl ve ilçe teşkilatı başlıklarında, bağlı olunan valilik veya kaymakamlık bilgisine yer verilmelidir. | özel fonksiyon `baslik_tasra_mulki_idare` | uyari | Y 10/3 |

## Sayı — 7 kural

| Kural | Ne denetliyor | Nasıl | Ağırlık | Dayanak |
|---|---|---|---|---|
| **S-01** | Her belgede sayı bulunmalıdır. | `ustveri.sayi` boş olmamalı | hata | Y 11/1 |
| **S-02** | Sayı; hazırlanma süreci harfi (E/Z/O), DETSİS numarası, standart dosya planı kodu ve kayıt numarasında… | bulunmalı: regex `'^[EZO]-\d{6,10}-\d{3}(\.\d{2}){0,3}-\d+$'` | hata | Y 11/1 |
| **S-03** | Sayı, belgenin hazırlanma sürecini gösteren E, Z veya O harflerinden biriyle başlamalıdır. | bulunmalı: regex `'^[EZO]-'` | hata | K 31 |
| **S-04** | Sayı bölümleri arasında yalnızca kısa çizgi (-) kullanılmalı; eğik çizgi veya başka işaret kullanılmam… | bulunmamalı: regex `'[/\\_,;]'` | hata | K 31 |
| **S-05** | Sayı alanında dört bölüm dışında herhangi bir ibare bulunmamalıdır. | bulunmamalı: regex `'(?i)(sayı|no|nr|belge|evrak|kayıt)'` | hata | K 8 |
| **S-06** | Belge kayıt numarasının başında rakam dışı bir ifade kullanılmamalıdır. | bulunmalı: regex `'-\d+$'` | uyari | K 8.1 |
| **S-07** | Sayının üçüncü bölümündeki dosya planı kodu, belgeye atanan standart dosya planı kodu ile aynı olmalıdır. | `ustveri.sayi[bolum:3]` = `siniflandirma.sdp.kod` | hata | Y 11/1 |

## Tarih — 4 kural

| Kural | Ne denetliyor | Nasıl | Ağırlık | Dayanak |
|---|---|---|---|---|
| **T-01** | Belgede tarih bulunmalıdır. | `ustveri.tarih` boş olmamalı | hata | Y 12/1 |
| **T-02** | Tarih, gün.ay.yıl biçiminde nokta ile ayrılarak veya ay adı harfle yazılarak (işaretsiz) gösterilmelidir. | özel fonksiyon `tarih_bicimi` | hata | Y 12/1 |
| **T-03** | Ay adı harfle yazıldığında yalnızca ilk harfi büyük olmalıdır. | özel fonksiyon `tarih_ay_adi_bicimi` | uyari | K 9 |
| **T-04** | Belge görüntüsündeki tarih ile üstverideki tarih aynı olmalıdır. | `kaynak.ham_metin[baslik_bloku_tarih]` = `ustveri.tarih` | hata | Y 28/3 |

## Konu — 5 kural

| Kural | Ne denetliyor | Nasıl | Ağırlık | Dayanak |
|---|---|---|---|---|
| **K-01** | Belgede konu bulunmalıdır. | `ustveri.konu` boş olmamalı | hata | Y 13/1 |
| **K-02** | Konunun sonunda herhangi bir noktalama işareti bulunmamalıdır. | bulunmamalı: regex `'[.,;:!?]\s*$'` | hata | Y 13/1 |
| **K-03** | Konuda geçen kelimelerin baş harfleri büyük yazılmalıdır. | özel fonksiyon `konu_bas_harfler` | hata | Y 13/1 |
| **K-04** | Konu alanına standart dosya planı kodunun adı aynen yazılmamalı; belge hakkında kısa ve öz bilgi veril… | özel fonksiyon `konu_sdp_kopyasi` | uyari | K 10 |
| **K-05** | Gerçek veya tüzel kişilerle ilgili yazışmalarda kişiye ait bilgi, konu alanında parantez içinde verilm… | özel fonksiyon `konu_kisi_bilgisi_parantez` | bilgi | K 10 |

## Muhatap — 12 kural

| Kural | Ne denetliyor | Nasıl | Ağırlık | Dayanak |
|---|---|---|---|---|
| **M-01** | Belgede muhatap bulunmalıdır. | özel fonksiyon `muhatap_var_mi` | hata | Y 14/1 |
| **M-02** | Muhatap bir idare veya özel hukuk tüzel kişisi ise adı büyük harflerle ve sonuna yönelme hâl eki getir… | özel fonksiyon `muhatap_idare_bicimi` | hata | Y 14/2 |
| **M-03** | Muhatap bilgisinde 'T.C.' ibaresine yer verilmemelidir. | özel fonksiyon `muhatap_tc_ibaresi` | hata | K 11.4 |
| **M-04** | Muhatap gerçek kişi ise 'Sayın' ibaresi kullanılmalı ve ilk harfi büyük diğerleri küçük yazılmalıdır. | özel fonksiyon `muhatap_sayin_bicimi` | hata | Y 14/3 |
| **M-05** | Muhatap gerçek kişi ise yönelme hâl ekine yer verilmemelidir. | özel fonksiyon `muhatap_gercek_kisi_hal_eki` | uyari | K 11.4 |
| **M-06** | Muhatap gerçek kişi ise adı ilk harfi büyük, soyadı tamamı büyük harflerle yazılmalıdır. | özel fonksiyon `muhatap_ad_soyad_bicimi` | hata | Y 14/3 |
| **M-07** | Muhatabın alt satırında parantez içinde belirtilen birim adına yönelme hâl eki getirilmemelidir. | özel fonksiyon `muhatap_parantez_hal_eki` | hata | K 11.4 |
| **M-08** | Muhatabın parantez içinde yalnızca tek bir birim adı belirtilmeli; birden fazla birim tire ile zincirl… | bulunmamalı: regex `'\s[-–]\s'` | hata | K 11.4 |
| **M-09** | Muhatap bilgisinde idareler için kısaltma kullanılmamalıdır. | özel fonksiyon `muhatap_kisaltma` | uyari | K 11.4 |
| **M-10** | İdarenin merkez teşkilatındaki birimlerine muhatap bölümünde tek başına yer verilmemeli, idare ismi de… | özel fonksiyon `muhatap_merkez_birim_yalniz` | uyari | K 11.4 |
| **M-11** | Birden fazla muhataba iletilecek dağıtımlı belgelerin muhatap bölümüne 'DAĞITIM YERLERİNE' ibaresi yaz… | özel fonksiyon `muhatap_dagitim_yerlerine` | hata | Y 14/6 |
| **M-12** | Muhatap gerçek kişi ise ad ve soyadı bilgilerinde kısaltma kullanılmamalıdır. | özel fonksiyon `kisi_adi_kisaltma` | uyari | K 11.3 |

## İlgi — 10 kural

| Kural | Ne denetliyor | Nasıl | Ağırlık | Dayanak |
|---|---|---|---|---|
| **I-01** | İlgi tutulan belgenin tarihi belirtilmelidir. | özel fonksiyon `ilgi_tarih_var` | hata | Y 15/6 |
| **I-02** | İlgi tutulan belgenin sayısı belirtilmelidir. | özel fonksiyon `ilgi_sayi_var` | hata | Y 15/6 |
| **I-03** | İlgide belirtilen sayı, dört bölümün tamamı yazılarak gösterilmelidir; yalnızca kayıt numarası yazılma… | özel fonksiyon `ilgi_sayi_tam_bicim` | hata | K 12.3 |
| **I-04** | İlgi kısmında, vatandaş başvuruları haricinde 'bila tarihli' veya 'tarihsiz' ifadesi kullanılmamalıdır. | bulunmamalı: regex `'(?i)(bila tarihli|tarihsiz)'` | hata | K 12.2 |
| **I-05** | Birden fazla ilgi bulunması durumunda belgeler, önceki tarihli olandan başlanarak sıralanmalıdır. | özel fonksiyon `ilgi_tarih_sirasi` | hata | Y 15/5 |
| **I-06** | İlgi sıralamasında Türk alfabesindeki küçük harfler, kendilerinden sonra kapama parantezi konularak ku… | özel fonksiyon `ilgi_siralama_harfleri` | hata | Y 15/5 |
| **I-07** | İlgide '… tarihli ve … sayılı …' ibaresi kullanılmalı ve ilginin sonuna nokta konulmalıdır. | özel fonksiyon `ilgi_kalip_bicimi` | hata | Y 15/7 |
| **I-08** | İlgi tutulan belge üçüncü bir idareye aitse, o idarenin adı ilgide belirtilmelidir. | özel fonksiyon `ilgi_idare_adi` | hata | Y 15/6 |
| **I-09** | İlgi tutulan belgelerden metin içinde bahsedilmeli, ilk paragrafta ilgi ile belge arasında bağ kurulma… | özel fonksiyon `metin_ilgi_atfi` | hata | K 13.2 |
| **I-10** | İlgi tutulan belge gerçek kişiden geliyorsa ilgi, \"…'ın … tarihli başvurusu/dilekçesi.\" biçiminde ya… | özel fonksiyon `ilgi_gercek_kisi_bicimi` | uyari | Y 15/9 |

## Metin — 22 kural

| Kural | Ne denetliyor | Nasıl | Ağırlık | Dayanak |
|---|---|---|---|---|
| **ME-01** | Belgede metin bölümü bulunmalıdır. | `cikti_yazi.metin` boş olmamalı | hata | Y 16/1 |
| **ME-02** | Metin, muhatabın hiyerarşik durumuna uygun arz veya rica ibaresiyle bitirilmelidir. | bulunmalı: regex `'(?i)(arz ederim|rica ederim|arz ve rica ederim|arz/rica ederim)\.?\s*$'` | hata | Y 16/12-a |
| **ME-03** | Alt makamlara 'rica ederim.', üst ve aynı düzeydeki makamlara 'arz ederim.' kullanılmalıdır. | özel fonksiyon `metin_arz_rica_hiyerarsi` | hata | Y 16/12-a |
| **ME-04** | Üst, aynı düzey ve alt makamlara birlikte dağıtımlı yapılan yazışmalar 'arz ve rica ederim.' veya 'arz… | özel fonksiyon `metin_dagitimli_arz_rica` | uyari | Y 16/12-b |
| **ME-05** | Muhatabı gerçek kişi olan yazışmalar 'Saygılarımla.', 'İyi dileklerimle.' veya 'Bilgilerinize sunulur.… | özel fonksiyon `metin_gercek_kisi_kapanis` | bilgi | Y 16/12-e |
| **ME-06** | İdarelerin kamu niteliği olmayan tüzel kişilerle yaptığı yazışmalar 'Rica ederim.' ile bitirilmelidir. | özel fonksiyon `metin_ozel_tuzel_kisi_rica` | uyari | K 13.1 |
| **ME-07** | Metindeki cümleler, son cümle hariç, -dır/-dir/-dur/-dür/-tır/-tir/-tur/-tür eklerinden uygun olanı il… | özel fonksiyon `metin_kosac` | uyari | K 13 |
| **ME-08** | Metinde şahsileştirilmiş anlatımdan kaçınılmalı, genelleştirilmiş kurumsal ifade kullanılmalıdır. | özel fonksiyon `metin_sahsilestirilmis_ifade` | uyari | K 13 |
| **ME-09** | Belge içinde zorunlu olmadıkça yabancı kelimeye yer verilmemeli, verildiğinde parantez içinde anlamı b… | özel fonksiyon `metin_yabanci_kelime` | uyari | Y 16/8 |
| **ME-10** | Metinde resmî yazışmalarda sıklıkla yanlış yazılan kelimeler kullanılmamalıdır. | sözlük araması | hata | K 13.6 (Resmî Yazışmalarda Sıklıkla Yanlış Kullanılan Kelimeler tablosu) |
| **ME-11** | Aynı cümle içinde 've' bağlacı ikiden fazla kullanılmamalıdır. | özel fonksiyon `metin_ve_baglaci_tekrari` | uyari | K 13.5.3.1 |
| **ME-12** | Metin içinde ilgiye atıf yapılırken 'İlgi'de kayıtlı' veya 'İlgi (a)'da kayıtlı' kalıbı kullanılmalıdır. | özel fonksiyon `metin_ilgi_gosterim_kalibi` | uyari | K 13.2 |
| **ME-13** | Metin içinde ekten bahsedilirken 'Ek'te yer alan' veya 'Ek-1'de belirtilen' kalıbı kullanılmalıdır. | özel fonksiyon `metin_ek_gosterim_kalibi` | uyari | K 13.3 |
| **ME-14** | Dört ve daha fazla haneli sayılar, sondan üçlü gruplara ayrılarak nokta ile yazılmalıdır. | özel fonksiyon `metin_sayi_gruplama` | uyari | Y 16/7 |
| **ME-15** | Sayılarda kesirler virgül ile ayrılmalıdır. | bulunmamalı: regex `'\d+\.\d{2}\s*(TL|₺|lira)'` | uyari | Y 16/7 |
| **ME-16** | Metin içinde harfle maddelendirme yapıldığında küçük harfler, kendilerinden sonra kapama parantezi kon… | özel fonksiyon `metin_maddeleme_bicimi` | uyari | Y 16/10 |
| **ME-17** | Metinde kısaltma kullanılacaksa ifadenin ilk geçtiği yerde açık biçimi, ardından parantez içinde kısal… | özel fonksiyon `metin_kisaltma_acilimi` | uyari | Y 16/11 |
| **ME-18** | Metin içinde ve, veya, yahut bağlaçlarından önce de sonra da virgül kullanılmamalıdır. | bulunmamalı: regex `'(,\s+(ve|veya|yahut)\b|\b(ve|veya|yahut)\s*,)'` | uyari | K 13.6.9.2 |
| **ME-19** | Şart ekinden (-sa/-se) sonra virgül kullanılmamalıdır. | bulunmamalı: regex `'\w+(sa|se|sanız|seniz|saydı|seydi)\s*,'` | uyari | K 13.6.9.2 |
| **ME-20** | Kurum, kuruluş, kurul ve iş yeri adlarına gelen ekler kesme işaretiyle ayrılmamalıdır. | özel fonksiyon `metin_kurum_kesme_isareti` | uyari | K 13.6.9.8 |
| **ME-21** | Belli bir kanun, tüzük veya yönetmelik kastedildiğinde bu sözlerin aldığı ekler kesme işaretiyle ayrıl… | özel fonksiyon `metin_mevzuat_kesme_isareti` | uyari | K 13.6.9.8 |
| **ME-22** | Metinde 4-5 satırı aşan uzun cümlelerden kaçınılmalıdır. | özel fonksiyon `metin_uzun_cumle` | uyari | K 13.5.3 |

## İmza — 9 kural

| Kural | Ne denetliyor | Nasıl | Ağırlık | Dayanak |
|---|---|---|---|---|
| **IM-01** | Belgede imzalayan makamın adı, soyadı ve unvanı bulunmalıdır. | `ustveri.imza_sahibi_unvan` boş olmamalı | hata | Y 17/1 |
| **IM-02** | Belgeyi imzalayanın adı ilk harfi büyük diğerleri küçük, soyadı ise tamamı büyük harflerle yazılmalıdır. | özel fonksiyon `imza_ad_soyad_bicimi` | hata | Y 17/2 |
| **IM-03** | Unvan, ad ve soyadın altına ilk harfleri büyük diğerleri küçük harflerle yazılmalıdır. | özel fonksiyon `imza_unvan_bicimi` | hata | Y 17/2 |
| **IM-04** | İmza alanında yetkili makamın adı ve soyadı açık yazılmalı, kısaltma kullanılmamalıdır. | özel fonksiyon `kisi_adi_kisaltma` | uyari | K 14.2 |
| **IM-05** | Elektronik ortamda imzalanan belgelerde, yetkili makamın ad ve soyad bilgilerinin üzerinde güvenli ele… | özel fonksiyon `imza_ustunde_eimza_ibaresi` | hata | Y 17/3 |
| **IM-06** | Belge imza yetkisi devredilen makam tarafından imzalandığında, yetkiyi devreden makamı gösteren 'Bakan… | özel fonksiyon `imza_yetki_devri_bicimi` | uyari | Y 17/9 |
| **IM-07** | Belge vekâleten imzalandığında, vekâlet olunan makam 'Genel Müdür V.' biçiminde ikinci satıra yazılmal… | özel fonksiyon `imza_vekalet_bicimi` | uyari | Y 17/10 |
| **IM-08** | İmza bölümünde unvan açık yazılmalı; yalnızca akademik unvanlar ile askerî rütbelerde kısaltma kullanı… | özel fonksiyon `imza_unvan_acik` | uyari | K 14.2 |
| **IM-09** | İmza alanından sonra Ek, Dağıtım ve iletişim bilgileri dışında yazı veya tablo bulunmamalıdır. | özel fonksiyon `imza_sonrasi_icerik` | uyari | K 14.7 |

## Ek — 6 kural

| Kural | Ne denetliyor | Nasıl | Ağırlık | Dayanak |
|---|---|---|---|---|
| **EK-01** | Eklerin sayfa, adet veya kişi sayısı gibi açıklayıcı ifadeleri parantez içinde belirtilmelidir. | özel fonksiyon `ek_nitelik_parantez` | hata | Y 18/2 |
| **EK-02** | Belgenin sadece bir eki varsa 'Ek:' başlığının sağında belirtilmeli, numaralandırılmamalıdır. | özel fonksiyon `ek_tek_numaralandirma` | uyari | Y 18/2 |
| **EK-03** | Belgede birden fazla ek varsa 'Ek:' başlığının altında ekler numaralandırılmalıdır. | özel fonksiyon `ek_coklu_numaralandirma` | uyari | Y 18/2 |
| **EK-04** | Metinde ekten bahsediliyorsa ek listesi boş olmamalıdır. | özel fonksiyon `ek_metin_tutarliligi` | hata | Y 18/1 |
| **EK-05** | Belge ekinin gizlilik derecesi varsa, üst yazının gizlilik derecesi ekin derecesinden aşağı olmamalıdır. | özel fonksiyon `ek_gizlilik_derecesi` | hata | K 15 |
| **EK-06** | Belge ekleri muhataba gönderilmediğinde 'Ek konulmadı' veya 'Ek-… konulmadı' ifadesi yazılmalıdır. | özel fonksiyon `ek_konulmadi_ifadesi` | bilgi | Y 18/5 |

## Dağıtım — 4 kural

| Kural | Ne denetliyor | Nasıl | Ağırlık | Dayanak |
|---|---|---|---|---|
| **D-01** | Belge birden fazla muhataba gönderiliyorsa dağıtım bölümüne yer verilmelidir. | özel fonksiyon `dagitim_bolumu_var` | hata | Y 19/1 |
| **D-02** | Belgenin gereğini yerine getirecekler 'Gereği:' kısmına, bilgi sahibi olması istenenler 'Bilgi:' kısmı… | özel fonksiyon `dagitim_geregi_bilgi` | uyari | Y 19/2 |
| **D-03** | Dağıtım listesi, Kılavuz'da belirtilen protokol sırasına göre düzenlenmelidir. | özel fonksiyon `dagitim_protokol_sirasi` | uyari | K 16.1 |
| **D-04** | Dağıtım bölümü yazı alanına sığmayacak kadar uzunsa ayrı bir sayfada 'DAĞITIM LİSTESİ' başlığı altında… | özel fonksiyon `dagitim_uzun_liste` | bilgi | Y 19/3 |

## Gizlilik ve süreli yazışma — 8 kural

| Kural | Ne denetliyor | Nasıl | Ağırlık | Dayanak |
|---|---|---|---|---|
| **G-01** | Gizlilik derecesi yalnızca 'Çok Gizli', 'Gizli' veya 'Hizmete Özel' olabilir. | `ustveri.gizlilik_derecesi` ∈ izinli küme | hata | K 22 |
| **G-02** | 'Özel' gizlilik derecesi kullanılmamalıdır; 2022'de kullanımdan kaldırılmıştır. | bulunmamalı: regex `'(?i)^özel$'` | hata | K 22 |
| **G-03** | Süreli yazışmalarda yalnızca 'ACELE' veya 'GÜNLÜDÜR' ibaresi kullanılabilir. | `ustveri.ivedilik` ∈ izinli küme | hata | Y 26/1 |
| **G-04** | ÇOK ACELE, İVEDİ, ÇOK İVEDİ, ACİL gibi ibareler kullanılmamalıdır. | bulunmamalı: regex `'(?i)\b(ÇOK ACELE|ÇOK İVEDİ|İVEDİ|ACİL)\b'` | hata | K 23 |
| **G-05** | 'GÜNLÜDÜR' ibaresi taşıyan belgelerde cevap verilmesi gereken süre veya tarih, metin içinde ve üstveri… | özel fonksiyon `ivedilik_gunludur_sure` | hata | Y 26/1 |
| **G-06** | 'ACELE' ibaresi taşıyan belgelerin içinde veya üstveri alanında süre belirtilmemelidir. | özel fonksiyon `ivedilik_acele_suresiz` | hata | K 23 |
| **G-07** | Olur belgelerinde 'ACELE' veya 'GÜNLÜDÜR' ibaresi kullanılmamalıdır. | özel fonksiyon `olur_ivedilik_yasagi` | hata | K 23 |
| **G-08** | Çok Gizli ve Gizli belgeler fiziksel ortamda, Hizmete Özel belgeler elektronik ortamda üretilmelidir. | özel fonksiyon `gizlilik_ortam_uyumu` | uyari | K 22 |

## Tekit — 2 kural

| Kural | Ne denetliyor | Nasıl | Ağırlık | Dayanak |
|---|---|---|---|---|
| **TK-01** | Tekit yazısında daha önce gönderilen belge ilgi olarak tutulmalıdır. | `ustveri.ilgi` boş liste olmamalı | hata | K 30 |
| **TK-02** | Tekit yazıları hiyerarşi yönünden alt veya aynı düzey idarelere yazılmalı; üst seviyedeki kurumlara ya… | özel fonksiyon `tekit_hiyerarsi` | uyari | K 30 |

## Genel tutarlılık — 7 kural

| Kural | Ne denetliyor | Nasıl | Ağırlık | Dayanak |
|---|---|---|---|---|
| **GN-01** | Belge görüntüsündeki konu ile üstverideki konu aynı olmalıdır. | `kaynak.ham_metin[konu]` = `ustveri.konu` | hata | Y 28/3 |
| **GN-02** | Birden fazla sayfa tutan üst yazılarda sayı, tarih, konu, muhatap ve ilgi bilgilerine sadece ilk sayfa… | özel fonksiyon `cok_sayfa_baslik_tekrari` | uyari | Y 16/5 |
| **GN-03** | Birden fazla sayfa tutan üst yazılarda imza, ek ve dağıtım bilgilerine sadece son sayfada yer verilmel… | özel fonksiyon `cok_sayfa_imza_konumu` | uyari | Y 16/5 |
| **GN-04** | Birden fazla sayfa tutan belgelerde sayfa numarası, toplam sayfa sayısının kaçıncısı olduğunu gösterec… | özel fonksiyon `sayfa_numarasi_bicimi` | uyari | Y 27/1 |
| **GN-05** | Elektronik imzalı belgelerde 'Bu belge, güvenli elektronik imza ile imzalanmıştır.' ibaresi, doğrulama… | özel fonksiyon `belge_dogrulama_bilgisi` | uyari | Y 23/1 |
| **GN-06** | Belgenin sayfa sonunda gönderen idarenin iletişim bilgileri ile bilgi alınacak kişinin bilgileri yer a… | özel fonksiyon `iletisim_bilgileri` | uyari | Y 24/1 |
| **GN-07** | İdare içi ve idare dışı görüş, bilgi ve belge talep yazıları günlü yazılmalıdır. | özel fonksiyon `talep_yazisi_gunlu` | uyari | Y 33/1 |

---

## Bu kurallar sadece yazım denetimi değil

Listeye bakınca dört farklı denetim türü olduğu görülüyor:

**Biçim.** Başlık kaç satır, tarih hangi biçimde, konu nasıl yazılır.
Word'ün yazım denetimine en çok benzeyen kısım.

**Tutarlılık.** Belge görüntüsündeki tarih ile üstverideki tarih aynı mı
(GN-01, T-04). Sayının içindeki dosya planı kodu ile atanan kod aynı mı
(S-07). Bunlar iki ayrı yeri karşılaştırıyor.

**Hiyerarşi ve hukuk.** Alt kurumdan üst kuruma yazılan yazı "arz" ile biter,
diğerleri "rica" ile (ME-02, ME-03). Tekit yazısı üst makama yazılmaz
(TK-02). Ekin gizlilik derecesi üst yazıyı aşamaz (EK-05). Bunlar yazım
değil, idare hukuku kuralları.

**Yasak.** "ACİL", "İVEDİ" gibi ibareler kullanılamaz (G-04). "Özel" gizlilik
derecesi 2022'de kaldırıldı (G-02). Kişiye özel ifadeler resmî yazıda yer
almaz (ME-08).

Üretilen bir taslağın bu 104 maddeden geçmesi, "dil bilgisi doğru" demek
değil — "mevzuata uygun" demek. Şartname 6.4.2'nin istediği de bu.
