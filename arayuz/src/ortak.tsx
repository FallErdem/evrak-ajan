import { useState } from "react"
import type {
  Durum,
  EksikKatman,
  EksikOnem,
  Motor,
} from "./tipler"

export const API = "http://localhost:8000"

// ---------------------------------------------------------------------------
// Rol taşıyan fetch sarmalayıcısı
// ---------------------------------------------------------------------------
//
// Sözleşme 1.5: GET isteklerinde rol X-Rol / X-Birim başlıklarında taşınır.
// Süzme ve maskeleme sunucuda yapılır, arayüz yalnızca kim olduğunu bildirir.
// Oturum modül düzeyinde tutulur; App rol değiştirdiğinde günceller.

let _rol = "kayit_memuru"
let _birim: string | null = null

export function oturumuAyarla(rol: string, birimKodu: string | null) {
  _rol = rol
  _birim = birimKodu
}

function basliklar(ek?: HeadersInit): HeadersInit {
  const h: Record<string, string> = { "X-Rol": _rol }
  if (_birim) h["X-Birim"] = _birim
  return { ...h, ...(ek as Record<string, string> | undefined) }
}

/** Hata gövdesi FastAPI biçiminde: {"detail": "..."} */
async function hataFirlat(r: Response): Promise<never> {
  let mesaj = `Sunucu ${r.status}`
  try {
    const g = await r.json()
    if (g?.detail) mesaj = String(g.detail)
  } catch {
    /* gövde okunamadı */
  }
  throw new Error(mesaj)
}

export async function getir<T>(yol: string): Promise<T> {
  const r = await fetch(API + yol, { headers: basliklar() })
  if (!r.ok) return hataFirlat(r)
  return (await r.json()) as T
}

export async function gonder<T>(yol: string, govde: unknown): Promise<T> {
  const r = await fetch(API + yol, {
    method: "POST",
    headers: basliklar({ "Content-Type": "application/json" }),
    body: JSON.stringify(govde),
  })
  if (!r.ok) return hataFirlat(r)
  return (await r.json()) as T
}

export async function dosyaGonder<T>(yol: string, dosya: File): Promise<T> {
  const fd = new FormData()
  fd.append("dosya", dosya)
  const r = await fetch(API + yol, { method: "POST", headers: basliklar(), body: fd })
  if (!r.ok) return hataFirlat(r)
  return (await r.json()) as T
}

/** SSE adresi — EventSource başlık taşıyamaz, akış zaten role bağlı değil. */
export const akisAdresi = (evrakId: string) => `${API}/api/evrak/${evrakId}/akis`

// ---------------------------------------------------------------------------
// Biçimleyiciler
// ---------------------------------------------------------------------------

export const ms = (n: number) => `${n.toLocaleString("tr-TR")} ms`

export const sn = (n: number) =>
  `${(n / 1000).toLocaleString("tr-TR", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })} sn`

export const guvenYaz = (g: number) => g.toFixed(2).replace(".", ",")

export const yuzde = (x: number) => `%${Math.round(x * 100)}`

export const saat = (ts: number) =>
  new Date(ts * 1000).toLocaleTimeString("tr-TR", { hour12: false })

/** ISO "2026-09-17" → "17.09.2026". Sunucu daima ISO gönderir. */
export function tarihGoster(iso: string | null): string {
  if (!iso) return "—"
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("tr-TR")
}

/** ISO tarihe kaç gün kaldığı. Geçmişse negatif. */
export function kalanGun(iso: string): number | null {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  return Math.ceil((d.getTime() - Date.now()) / 86400000)
}

/** Bekleme süresi: "43 sn", "14 dk", "5 sa 2 dk", "2 gün". */
export function bekleme(saniye: number): string {
  if (saniye < 60) return `${saniye} sn`
  const dk = Math.floor(saniye / 60)
  if (dk < 60) return `${dk} dk`
  const sa = Math.floor(dk / 60)
  if (sa < 24) return dk % 60 ? `${sa} sa ${dk % 60} dk` : `${sa} sa`
  return `${Math.floor(sa / 24)} gün`
}

/** Uzun görev alanı metnini listede kırpar; tamamı title olarak verilir. */
export function kirp(metin: string, sinir = 120): string {
  return metin.length <= sinir ? metin : metin.slice(0, sinir).trimEnd() + "…"
}

// ---------------------------------------------------------------------------
// Etiketler
// ---------------------------------------------------------------------------

export const DURUM_ETIKET: Record<string, string> = {
  ALINDI: "Alındı",
  ISLENIYOR: "İşleniyor",
  INSAN_ONAYI_BEKLIYOR: "İnsan onayı bekliyor",
  EKSIK_BILGI_BEKLIYOR: "Eksik bilgi bekliyor",
  OTOMATIK_ONAYLANDI: "Otomatik onaylandı",
  ONAYLANDI: "Onaylandı",
  REDDEDILDI: "Reddedildi",
  HATA: "Hata",
}

/**
 * `veri_yapisi.GelenTur`in on dört değeri artı sahte sunucunun kısa adları.
 * İkisi de tutuluyor: sahte sunucu çevrimdışı demo yedeği olarak duruyor ve
 * onun sözcükleri (`dilekce`, `resmi_yazi`) gerçek şemadakilerden farklı.
 * Eksik anahtarda çağıran ham değere düşüyor, boş göstermiyor.
 */
export const BELGE_TURU_ETIKET: Record<string, string> = {
  // veri_yapisi.GelenTur
  ust_yazi: "Üst yazı",
  cevap_yazisi: "Cevap yazısı",
  bilgilendirme_yazisi: "Bilgilendirme yazısı",
  talep_yazisi: "Talep yazısı",
  tekit_yazisi: "Tekit yazısı",
  olur_yazisi: "Olur yazısı",
  duyuru: "Duyuru",
  genelge: "Genelge",
  vatandas_dilekcesi: "Vatandaş dilekçesi",
  bilgi_edinme_basvurusu: "Bilgi edinme başvurusu",
  sikayet: "Şikâyet",
  itiraz: "İtiraz",
  gorus_talebi: "Görüş talebi",
  bilinmiyor: "Bilinmiyor",
  // sahte sunucunun kısa adları
  dilekce: "Dilekçe",
  resmi_yazi: "Resmî yazı",
  basvuru: "Başvuru",
}

/** `veri_yapisi.UretilecekTur`un yedi değeri artı sahte sunucunun kısaları. */
export const KARAR_TURU_ETIKET: Record<string, string> = {
  ust_yazi: "Üst yazı",
  cevap_yazisi: "Cevap yazısı",
  bilgilendirme_yazisi: "Bilgilendirme yazısı",
  olur_yazisi: "Olur yazısı",
  tekit_yazisi: "Tekit yazısı",
  eksik_bilgi_talebi: "Eksik bilgi talebi",
  taslak_gerekmez: "Taslak gerekmez",
  // sahte sunucunun kısa adları
  bilgilendirme: "Bilgilendirme metni",
  olur: "Olur",
  tekit: "Tekit",
}

/** `hata` düzeyi "kritik eksik" sayılır (sözleşme 5.6.5). */
export const ONEM_ETIKET: Record<EksikOnem, string> = {
  hata: "Kritik",
  uyari: "Uyarı",
  bilgi: "Bilgi",
}

export const KATMAN_ETIKET: Record<EksikKatman, string> = {
  sema: "Şema",
  kural: "Kural",
  mevzuat: "Mevzuat",
  cikarim: "Çıkarım",
}

export const MOTOR_ETIKET: Record<Motor, string> = {
  arac: "ARAÇ",
  kural: "KURAL",
  llm: "LLM",
  karma: "KARMA",
}

export const MOTOR_ADI: Record<Motor, string> = {
  arac: "Araç (Docling / OCR)",
  kural: "Kural motoru",
  llm: "Dil modeli",
  karma: "Karma (kural + model)",
}

export const YONTEM_ETIKET: Record<string, string> = {
  regex: "Regex",
  sozluk: "Sözlük",
  kural: "Kural",
  llm: "LLM",
  ocr: "OCR",
  hesaplama: "Hesap",
  insan: "İnsan",
  varsayilan: "Varsayılan",
}

export const GIRDI_TIPI_ETIKET: Record<string, string> = {
  metin_katmanli: "Metin katmanlı",
  taranmis: "Taranmış",
  duz_metin: "Düz metin",
}

/** Karar alınabilir durumlar. */
export const ACIK_DURUMLAR: Durum[] = ["INSAN_ONAYI_BEKLIYOR", "EKSIK_BILGI_BEKLIYOR"]
export const SONUCLANMIS_DURUMLAR: Durum[] = [
  "ONAYLANDI",
  "REDDEDILDI",
  "OTOMATIK_ONAYLANDI",
]

// ---------------------------------------------------------------------------
// Rozetler
// ---------------------------------------------------------------------------

const DURUM_RENGI: Record<string, string> = {
  ISLENIYOR: "border-havale text-havale bg-havale-soluk",
  INSAN_ONAYI_BEKLIYOR: "border-kase text-kase bg-kase-soluk",
  EKSIK_BILGI_BEKLIYOR: "border-havale text-havale bg-havale-soluk",
  OTOMATIK_ONAYLANDI: "border-muhur text-muhur bg-muhur-soluk",
  ONAYLANDI: "border-muhur text-muhur bg-muhur-soluk",
  REDDEDILDI: "border-karbon text-karbon bg-transparent",
  HATA: "border-kase text-kase bg-kase-soluk",
  ALINDI: "border-tel-koyu text-karbon bg-transparent",
}

export function DurumRozeti({ durum }: { durum: string }) {
  return (
    <span
      className={
        "inline-block font-veri text-[9px] tracking-[0.1em] uppercase px-1.5 py-0.5 rounded-xs border " +
        (DURUM_RENGI[durum] ?? "border-tel-koyu text-karbon")
      }
    >
      {DURUM_ETIKET[durum] ?? durum}
    </span>
  )
}

export function MotorRozeti({ motor }: { motor: Motor }) {
  // Deterministik motorlar öne çıkar: "her şeyi modele sormadık" iddiasının rozeti.
  const belirgin = motor === "kural" || motor === "arac"
  return (
    <span
      className={
        "font-veri text-[9px] tracking-[0.12em] px-1.5 py-px rounded-xs " +
        (motor === "kural"
          ? "bg-muhur text-yaprak"
          : motor === "arac"
            ? "border border-muhur text-muhur"
            : "border border-tel-koyu text-karbon") +
        (belirgin ? "" : "")
      }
    >
      {MOTOR_ETIKET[motor]}
    </span>
  )
}

export function OnemRozeti({ onem }: { onem: EksikOnem }) {
  const renk =
    onem === "hata"
      ? "border-kase text-kase bg-kase-soluk"
      : onem === "uyari"
        ? "border-havale text-havale bg-havale-soluk"
        : "border-tel-koyu text-karbon"
  return (
    <span
      className={
        "font-veri text-[9px] tracking-[0.1em] uppercase px-1.5 py-px rounded-xs border " +
        renk
      }
    >
      {ONEM_ETIKET[onem] ?? onem}
    </span>
  )
}

/** Kişisel veri kilidi. */
export function KilitRozeti() {
  return (
    <span
      title="Kişisel veri · maskeli"
      className="font-veri text-[9px] tracking-[0.1em] uppercase px-1 py-px rounded-xs border border-havale text-havale"
    >
      KVKK
    </span>
  )
}

/**
 * Güven çubuğu — skoru eşikle birlikte gösterir.
 * Çıplak "0,71" anlamsız; "eşiğin altında" anlamlı.
 */
export function GuvenCubugu({
  skor,
  esik,
  genislik = 120,
}: {
  skor: number
  esik: number
  genislik?: number
}) {
  const gecti = skor >= esik
  return (
    <div className="flex items-center gap-2">
      <div
        className="relative h-1.5 rounded-xs bg-tel"
        style={{ width: genislik }}
        role="img"
        aria-label={`Güven ${guvenYaz(skor)}, eşik ${guvenYaz(esik)}`}
      >
        <div
          className={"absolute inset-y-0 left-0 rounded-xs " + (gecti ? "bg-muhur" : "bg-kase")}
          style={{ width: `${Math.min(skor, 1) * 100}%` }}
        />
        <div
          className="absolute -top-1 -bottom-1 w-px bg-murekkep"
          style={{ left: `${Math.min(esik, 1) * 100}%` }}
          title={`eşik ${guvenYaz(esik)}`}
        />
      </div>
      <span
        className={"font-veri text-[11px] tabular-nums " + (gecti ? "text-muhur" : "text-kase")}
      >
        {guvenYaz(skor)}
      </span>
    </div>
  )
}

export function BolumBasligi({
  children,
  sag,
}: {
  children: React.ReactNode
  sag?: React.ReactNode
}) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <h3 className="font-veri text-[9px] tracking-[0.14em] uppercase text-karbon">
        {children}
      </h3>
      {sag}
    </div>
  )
}

/**
 * Katlanabilir bölüm — `BolumBasligi`nin tıklanabilir hâli.
 *
 * Onay künyesi sekiz bölümle çok kalabalıktı; memur karar verirken hepsine
 * aynı anda bakmıyor. Bölümler kapatılabilir oldu, ama karar için gereken
 * dördü (neden onaya düştü · künye · üretilen yazı · eylemler) katlanmıyor.
 *
 * `ozet` kapalıyken başlığın yanında görünür: bölümü açmadan içinde ne
 * olduğu bilinsin, tek tek açıp kapatmak gerekmesin.
 */
export function Katlanir({
  baslik,
  sag,
  ozet,
  acikBaslangic = false,
  className = "",
  govdeSinifi = "px-5 pb-4",
  children,
}: {
  baslik: React.ReactNode
  sag?: React.ReactNode
  ozet?: React.ReactNode
  acikBaslangic?: boolean
  className?: string
  govdeSinifi?: string
  children: React.ReactNode
}) {
  const [acik, setAcik] = useState(acikBaslangic)

  return (
    <div className={className}>
      <button
        type="button"
        onClick={() => setAcik((v) => !v)}
        aria-expanded={acik}
        className="w-full px-5 py-3.5 flex items-baseline gap-3 text-left transition-colors
                   hover:bg-kagit/70
                   focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-murekkep"
      >
        <span
          aria-hidden
          className="font-veri text-[11px] leading-none text-karbon w-2.5 shrink-0"
        >
          {acik ? "−" : "+"}
        </span>
        <h3 className="font-veri text-[9px] tracking-[0.14em] uppercase text-karbon shrink-0">
          {baslik}
        </h3>
        {!acik && ozet && (
          <span className="min-w-0 truncate font-govde text-[12.5px] text-karbon">{ozet}</span>
        )}
        <span className="ml-auto shrink-0">{sag}</span>
      </button>
      {acik && <div className={govdeSinifi}>{children}</div>}
    </div>
  )
}
