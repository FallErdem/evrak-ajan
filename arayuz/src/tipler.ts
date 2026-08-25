// api_sozlesmesi.md · sürüm 2026-08-18-h karşılığı.
//
// Bu dosya sözleşmeden türetilir. Sözleşme değişirse burası da değişir;
// tersi olmaz. Düğüm tablosu burada SABİT DEĞİLDİR — /api/dugumler'den gelir
// (sözleşme 2.5), çünkü Parça 4'te adım sayısı yine değişebilir.

// ---------------------------------------------------------------------------
// Sayılabilir değerler
// ---------------------------------------------------------------------------

/** Sözleşme 3.1 — sekiz durum. */
export type Durum =
  | "ALINDI"
  | "ISLENIYOR"
  | "INSAN_ONAYI_BEKLIYOR"
  | "EKSIK_BILGI_BEKLIYOR"
  | "OTOMATIK_ONAYLANDI"
  | "ONAYLANDI"
  | "REDDEDILDI"
  | "HATA"

/** Sözleşme 2.3 — dört motor. `kural` ve `arac` payı deterministik kısımdır. */
export type Motor = "arac" | "kural" | "llm" | "karma"

/** Sözleşme 5.6.3 — bir alanın nasıl çıkarıldığı. */
export type Yontem =
  | "regex"
  | "sozluk"
  | "kural"
  | "llm"
  | "ocr"
  | "hesaplama"
  | "insan"
  | "varsayilan"
  | null

/** Sözleşme 5.6.5 — eksik bilgi düzeyi. `hata` "kritik eksik" sayılır. */
export type EksikOnem = "bilgi" | "uyari" | "hata"

/** Sözleşme 5.6.5 — eksiği hangi katman yakaladı. */
export type EksikKatman = "sema" | "kural" | "mevzuat" | "cikarim"

/** Sözleşme 5.6.2 — adım kaydının durumu. */
export type AdimDurumu = "bekliyor" | "calisiyor" | "tamam" | "hata" | "atlandi"

/**
 * Ekrandaki kutu durumu. `duraklatildi` sunucudan gelmez; `dugum_duraklatildi`
 * olayından türetilir (üslup denetleyici taslağı geri gönderdi, kendisi bekliyor).
 */
export type KutuDurumu = AdimDurumu | "duraklatildi"

export type GirdiTipi = "metin_katmanli" | "taranmis" | "duz_metin"

// ---------------------------------------------------------------------------
// Düğüm tablosu — /api/dugumler
// ---------------------------------------------------------------------------

export type DugumTanimi = {
  no: number
  ad: string
  baslik: string
  aciklama: string
  motor: Motor
  /** Aynı `bilesen` değerini taşıyan ardışık adımlar tek çerçeveye alınır. */
  bilesen: number
  bilesen_adi: string
  /** Aynı `satir` = yan yana çizilir, eş zamanlı koşar. */
  satir: number
  /** Doluysa çerçeve etiketi olarak basılır. */
  ajan: string | null
}

export type DugumTablosu = {
  dugumler: DugumTanimi[]
  paralel_gruplar: number[][]
}

// ---------------------------------------------------------------------------
// Temel yapılar
// ---------------------------------------------------------------------------

/** `kutu` Parça 5'e ertelendi; şu an daima null (sözleşme 8.3). */
export type Kanit = { sayfa: number; kutu: [number, number, number, number] | null }

export type Alan = {
  deger: string | null
  /** `deger` null iken daima 0.0. */
  guven: number
  yontem: Yontem
  kanit: Kanit | null
  /** Değerin belgede birebir geçtiği metin. Geçmiyorsa null — uydurulmaz. */
  kanit_metin: string | null
}

/** Sözleşme 5.6.3 — sekiz üstveri alanı. */
export type Ustveri = {
  sayi: Alan
  tarih: Alan
  konu: Alan
  muhatap: Alan
  ilgi: Alan
  imza: Alan
  ek: Alan
  dagitim: Alan
}

export type Varlik = {
  /** /varlik/{sira}/ham çağrısı için gerekir. */
  sira: number
  tur: string
  /** Maskeliyse maskeli hâli. Ham değer ayrı uç noktadan alınır. */
  deger: string
  guven: number
  pii: boolean
  maskelendi: boolean
  kanit: Kanit | null
  kanit_metin: string | null
}

export type Eksik = {
  alan: string
  onem: EksikOnem
  katman: EksikKatman
  dayanak: string
  aciklama: string
  soru: string
  karsi_taraftan_istenebilir: boolean
  giderildi: boolean
  cevap: string | null
}

export type Mevzuat = {
  mevzuat_adi: string
  madde: string
  baslik: string
  alinti: string
  gerekce: string
  benzerlik: number
  /** false olan öneri arayüzde gösterilmez (sözleşme 5.6.5). */
  dogrulandi: boolean
}

/**
 * `sayi`, `tarih` ve `imza_ad` daima null gelir ve düzenlenemez —
 * EBYS'de kayıt ve imza anında atanır. `imza_unvan` birim tablosundan dolar.
 */
export type Taslak = {
  baslik: string
  sayi: null
  tarih: null
  konu: string
  muhatap: string
  govde: string
  imza_ad: null
  imza_unvan: string
}

export type UslupBulgusu = {
  kural_no: string
  duzey: "bilgi" | "uyari" | "hata"
  mesaj: string
  mevzuat: string
  cozuldu: boolean
}

export type BirimAdayi = { birim: string; birim_adi: string; skor: number }

export type Yonlendirme = {
  birim: string
  birim_adi: string
  skor: number
  geregi_bilgi: "geregi" | "bilgi"
  gerekce: string
  kanit_cumle: string
  /** `sdp_tablosu` = deterministik eşleşme, `llm` = çıkarım. */
  kaynak: "sdp_tablosu" | "llm"
  /** Kullanılmıyor; sözleşme 9.4 gereği kırılmasın diye duruyor. */
  alternatifler: unknown[]
  alternatif_adaylar: BirimAdayi[]
  kurum_disinda: boolean
}

export type GuvenKapisi = {
  mod: "OTOMATIK" | "INSAN"
  skor: number
  esik: number
  sebep: string
}

export type GunlukSatiri = { ts: number; aktor: string; olay: string }

/**
 * Evrağın şu an hangi birimde olduğu. Yönlendirmeden AYRI tutuluyor:
 * `yonlendirme` sistemin kararı ve yönlendirme başarımı ölçümünü besliyor,
 * `sevk` ise evrağın fiilî yeri. Onay evrağı taşırken sistemin kararını
 * yeniden yazsaydı metrik bozulurdu.
 */
export type Sevk = {
  bulundugu_birim: string | null
  gonderen_birim: string | null
  gelis_ts: number
  /** Gelen defterine yazıldı mı — "Deftere kaydet" düğmesi buna bakar. */
  kaydedildi: boolean
  /** Başka bir birimden mi geldi (yoksa doğrudan yönlendirilmiş). */
  gelen_mi: boolean
}

/**
 * Evrak kayıt defteri satırı. Sıra numarası KURUM başına 1'den artar —
 * defter kurumun defteridir, birimler ona yazar. `birim` hangi birimin
 * işlediğini söyler ve sayacın anahtarı değildir.
 */
export type DefterSatiri = {
  yon: "gelen" | "giden"
  kurum: string
  kurum_adi: string | null
  birim: string | null
  birim_adi: string | null
  sira_no: number
  evrak_id: string
  sayi: string | null
  tarih: string | null
  konu: string | null
  muhatap: string | null
  belge_turu: string | null
  durum: string | null
  ts: number
}

export type Duzeltme = {
  tur: "taslak" | "birim" | "red" | "geri_alma"
  rol: string
  ts: number
  alanlar?: string[]
  eski?: string
  yeni?: string
  gerekce?: string
}

/** Sözleşme 5.6.2 — her tur ayrı kayıttır. */
export type DugumKaydi = {
  no: number
  ad: string
  tur_no: number
  durum: AdimDurumu
  sure_ms: number | null
  guven: number | null
  gerekce: string | null
  cikti: Record<string, unknown> | null
}

// ---------------------------------------------------------------------------
// Eksik bilgi döngüsü
// ---------------------------------------------------------------------------

/**
 * Karşı taraftan eksik bilgi isteme talebi.
 *
 * `kanal`, `sure_gun` ve `son_tarih` BOŞ GELEBİLİR ve bu kasıtlı: süreyi
 * mevzuat verir, sistem uydurmuyor (`yazar._talep_kur`). Arayüz null'a
 * dayanıklı olmak zorunda — "null gün" yazdırmak boş bırakmaktan kötüdür.
 *
 * `yazi` talep gönderilene kadar null. Gönderildiğinde sunucu onu
 * `eksik_bilgi_yazisi` şablonundan kuruyor; asıl cevap taslağıyla
 * nesne paylaşmıyor.
 */
export type EksikBilgiTalebi = {
  ts: number
  muhatap_ad: string
  muhatap_turu: "gercek_kisi" | "kurum"
  kanal: string | null
  sure_gun: number | null
  /** ISO YYYY-MM-DD. Biçimlendirme arayüzün işi. */
  son_tarih: string | null
  dayanak: string
  sorular: string[]
  yazi: Taslak | null
  elle_duzenlendi: boolean
}

export type EksikBilgiCevabi = {
  ts: number
  gonderen: string
  ilgi: string
  cevaplar: { soru: string; cevap: string }[]
}

// ---------------------------------------------------------------------------
// Evrak
// ---------------------------------------------------------------------------

export type Evrak = {
  evrak_id: string
  calisma_id: string
  dosya_adi: string
  yuklenme_ts: number
  durum: Durum
  toplam_ms: number
  sayfa_sayisi: number
  karakter: number | null
  girdi_tipi: GirdiTipi | null

  dugum_kayitlari: DugumKaydi[]

  ustveri: Ustveri | null
  belge_turu: { deger: string; guven: number; gerekce: string } | null
  sdp: { kod: string; ad: string; kaynak_sayidan_mi: boolean } | null
  varliklar: Varlik[] | null
  talep: string | null
  ozet: string | null
  eksikler: Eksik[] | null
  mevzuat: Mevzuat[] | null
  karar: { uretilecek_tur: string; gerekce: string; taslak_gerekli: boolean } | null
  taslak: Taslak | null
  uslup_bulgulari: UslupBulgusu[] | null
  linter_tur_sayisi: number | null
  yonlendirme: Yonlendirme | null
  guven_kapisi: GuvenKapisi | null

  gunluk: GunlukSatiri[]
  duzeltmeler: Duzeltme[]
  eksik_bilgi_talebi: EksikBilgiTalebi | null
  eksik_bilgi_cevabi: EksikBilgiCevabi | null

  /**
   * Sözleşmeye EKLEME (2026-08-25). Sahte sunucu göndermiyor; isteğe bağlı
   * olduğu için eski sunucuyla da çalışır — alan yoksa defter ve sevk
   * bölümleri çizilmez.
   */
  sevk?: Sevk | null
  defter_kaydi?: {
    gelen: DefterSatiri | null
    giden: DefterSatiri | null
  } | null
}

/** GET /api/evrak — liste özeti. */
export type EvrakOzeti = {
  evrak_id: string
  dosya_adi: string
  durum: Durum
  yuklenme_ts: number
  bekleme_sn: number
  toplam_ms: number
  sayi: string | null
  konu: string | null
  belge_turu: string | null
  birim: string | null
  birim_adi: string | null
  guven: number | null
  esik: number | null
  sebep: string | null
  eksik_sayisi: number
  kritik_eksik_sayisi: number
  duzeltme_sayisi: number
}

// ---------------------------------------------------------------------------
// SSE olayları — sözleşme 6.2
// ---------------------------------------------------------------------------

export type OlayTuru =
  | "anlik_goruntu"
  | "durum_degisti"
  | "dugum_basladi"
  | "dugum_bitti"
  | "dugum_duraklatildi"
  | "dugum_tekrar"
  | "hata"
  | "akis_bitti"

export type Olay = {
  tur: OlayTuru
  evrak_id: string
  ts: number
  // düğüm olaylarında
  dugum?: number
  dugum_adi?: string
  bilesen?: number
  /** Her düğüm olayında gelir; döngü yaşanmayan adımda daima 1 (sözleşme 6.3). */
  tur_no?: number
  sure_ms?: number
  guven?: number | null
  gerekce?: string | null
  cikti?: Record<string, unknown> | null
  hata?: string
  // durum olaylarında
  durum?: Durum
  toplam_ms?: number
  // anlik_goruntu
  calisma_id?: string
  /** false ise koşu bitmiştir ve akış bu olaydan sonra kapanır. */
  canli?: boolean
  dugum_kayitlari?: DugumKaydi[]
}

// ---------------------------------------------------------------------------
// Birimler — /api/birimler
// ---------------------------------------------------------------------------

export type Birim = {
  kod: string
  ad: string
  /** Kök birimin adı; sunucu `ust_birim_kodu` zincirinden türetir. */
  kurum: string
  kurum_kodu: string
  ust_birim_kodu: string | null
  /** Tür etiketi: 0 kurum, 1 başkan yardımcılığı, 2 birim. Ağaç derinliği değil. */
  seviye: number
  gorev_alani: string
  sdp_kodlari: string[]
  /** Arama sonuçlarını sıralamada kullanılır. */
  vatandas_yogunlugu: "yuksek" | "orta" | "dusuk"
  imza_unvani: string
  detsis_no: string
  /** Yönlendiricinin aday kümesi. Seviye 1'in beşi false. */
  hedef_olabilir: boolean
}

// ---------------------------------------------------------------------------
// İstatistik — /api/istatistik
// ---------------------------------------------------------------------------

export type IstatistikBos = { toplam_evrak: 0; bos: true }

export type IstatistikDolu = {
  bos: false
  toplam_evrak: number
  otomatik_onay_orani: number
  insan_duzeltme_orani: number
  ortalama_sure_ms: number
  p50_sure_ms: number
  p95_sure_ms: number
  en_hizli_ms: number
  en_yavas_ms: number
  dugum_dagilimi: {
    no: number
    ad: string
    baslik: string
    motor: Motor
    ortalama_ms: number
    p95_ms: number
  }[]
  /** Paralelleştirmeseydik ne olurdu — karşılaştırma tabanı. */
  sirali_toplam_ms: number
  /** Ölçülen gerçek toplam. Paralellik uygulanıyor. */
  gerceklesen_toplam_ms: number
  motor_ms: Partial<Record<Motor, number>>
  guven_skorlari: number[]
  esik: number
  yonlendirme_isabet: number
  yonlendirme_duzeltmeleri: {
    eski: string
    yeni: string
    konu: string | null
    gerekce: string
  }[]
  yonlendirilen: number
  eksik_katman: Record<EksikKatman, number>
  eksik_onem: Record<EksikOnem, number>
  eksik_toplam: number
  eksik_giderilen: number
  /**
   * Mevzuat eleme — sözleşme 2026-08-18-h'ye EKLEME olarak gelecek.
   * Gelmezse bölüm çizilmez; bu yüzden isteğe bağlı.
   * `benzerlik` bir getirme skoru, `dogrulandi` Denetçi'nin kendi elemesi;
   * ikisi ayrı şeydir, o yüzden belge başına değil pano düzeyinde raporlanır.
   */
  mevzuat_getirilen?: number
  mevzuat_dogrulanan?: number
  mevzuat_elenen?: number
  benzerlik_dogrulanan_ort?: number
  benzerlik_elenen_ort?: number

  linter_ilk_tur_gecme: number
  linter_kurallar: {
    kural_no: string
    mesaj: string
    mevzuat: string
    duzey: string
    adet: number
  }[]
  durum_dagilimi: Record<string, number>
  belge_turu_dagilimi: Record<string, number>
  birim_dagilimi: { birim_adi: string; adet: number }[]
  bekleyen: number
  kritik_eksikli: number
  bekleme_ortalama_sn: number
}

export type Istatistik = IstatistikBos | IstatistikDolu

// ---------------------------------------------------------------------------
// Karar istekleri — sözleşme 8.1
// ---------------------------------------------------------------------------

export type Aksiyon =
  | "onayla"
  | "taslak_kaydet"
  | "reddet"
  | "birim_degistir"
  | "eksik_bilgi_iste"
  | "eksik_bilgi_cevabi"
  | "karari_geri_al"
  /** Gelen defterine kaydeder ve işi kapatır. Yalnızca gerçek sunucuda var. */
  | "deftere_kaydet"

export type KararGovdesi = {
  aksiyon: Aksiyon
  rol: string
  gerekce?: string
  /** taslak_sayi / taslak_tarih / taslak_imza_ad gönderilirse sunucu 400 döner. */
  taslak_baslik?: string
  taslak_konu?: string
  taslak_muhatap?: string
  taslak_govde?: string
  yeni_birim?: string
  sorular?: string[]
  yazi?: Partial<Taslak>
  cevaplar?: { soru: string; cevap: string }[]
}

export type KararYaniti = { durum: Durum; duzeltme_sayisi: number }

// ---------------------------------------------------------------------------
// Metin — /api/evrak/{id}/metin
// ---------------------------------------------------------------------------

export type EvrakMetni = {
  evrak_id: string
  dosya_adi: string
  sayfa_sayisi: number
  karakter: number
  girdi_tipi: GirdiTipi
  /** Metin katmanlı belgelerde null. */
  ocr_motoru: string | null
  /** Normalize edilmemiş; kanit_metin eşleşmesi bunun üzerinde yapılır. */
  metin: string
}

export type HamVarlik = {
  sira: number
  tur: string
  deger: string
  acan_rol: string
}
