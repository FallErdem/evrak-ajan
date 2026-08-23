// Roller ve yetkiler. Karar A-08.
//
// Yetkiler GİZLENMEZ, DEVRE DIŞI BIRAKILIR. Kayıt memuru onay ekranına girer,
// düğmeleri görür ama basamaz; üstünde kimde yetki olduğu yazar. Gizlersek
// jüri rol ayrımının gerçekten uygulandığını göremez.

export type RolKodu = "kayit_memuru" | "birim_sorumlusu" | "yonetici"

export type Yetkiler = {
  /** Evrak yükleyebilir mi */
  yukleyebilir: boolean
  /** Onay/red/yönlendirme kararı verebilir mi */
  onaylayabilir: boolean
  /** Kuyrukta bütün birimlerin evrakını görür mü */
  tumBirimleriGorur: boolean
  /** İstatistik panosuna erişir mi */
  istatistikGorur: boolean
}

export type RolTanimi = {
  kod: RolKodu
  ad: string
  aciklama: string
  /** Birim sorumlusu bir birime bağlıdır; diğerleri kurum genelindedir. */
  birimeBagli: boolean
  yetkiler: Yetkiler
}

export const ROLLER: RolTanimi[] = [
  {
    kod: "kayit_memuru",
    ad: "Evrak Kayıt Memuru",
    aciklama: "Evrak alır, akışı izler. Onay yetkisi yoktur.",
    birimeBagli: false,
    yetkiler: {
      yukleyebilir: true,
      onaylayabilir: false,
      tumBirimleriGorur: true,
      istatistikGorur: false,
    },
  },
  {
    kod: "birim_sorumlusu",
    ad: "Birim Sorumlusu",
    aciklama: "Kendi birimine düşen evrakları onaylar veya yönlendirir.",
    birimeBagli: true,
    yetkiler: {
      yukleyebilir: true,
      onaylayabilir: true,
      tumBirimleriGorur: false,
      istatistikGorur: false,
    },
  },
  {
    kod: "yonetici",
    ad: "Kurum Yöneticisi",
    aciklama: "Tüm evrakları görür, onaylar; istatistik ve denetim izine erişir.",
    birimeBagli: false,
    yetkiler: {
      yukleyebilir: true,
      onaylayabilir: true,
      tumBirimleriGorur: true,
      istatistikGorur: true,
    },
  },
]

export const ROL_HARITASI: Record<RolKodu, RolTanimi> = Object.fromEntries(
  ROLLER.map((r) => [r.kod, r]),
) as Record<RolKodu, RolTanimi>

/** Oturumdaki kullanıcı. */
export type Oturum = {
  rol: RolTanimi
  /** Birim sorumlusuysa bağlı olduğu birim kodu, değilse null. */
  birimKodu: string | null
}

// Birim tipi sözleşmeden gelir; burada yalnızca yeniden dışa aktarılır.
export type { Birim } from "./tipler"
