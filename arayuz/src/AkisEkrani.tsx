import { useMemo, useRef, useState } from "react"
import type { DugumKaydi, DugumTanimi, KutuDurumu, Olay } from "./tipler"
import type { useAkis } from "./useAkis"
import { useDugumler, type BilesenKusagi } from "./useDugumler"
import {
  BolumBasligi,
  DURUM_ETIKET,
  MotorRozeti,
  guvenYaz,
  ms,
  saat,
  sn,
} from "./ortak"

// Düğüm tablosu buradan gelmiyor, /api/dugumler'den geliyor. Bileşen çerçevesi
// ve ajan etiketi de veriden türer; arayüz kendi eşleme tablosunu tutmaz.

function DugumKarti({
  dugum,
  durum,
  sure,
  turNo,
  aktifSure,
  secili,
  onSec,
}: {
  dugum: DugumTanimi
  durum: KutuDurumu | undefined
  sure?: number
  turNo?: number
  aktifSure: number | null
  secili: boolean
  onSec: () => void
}) {
  const d = durum ?? "bekliyor"
  const kenar =
    d === "calisiyor"
      ? "border-kase bg-yaprak"
      : d === "tamam"
        ? "border-tel-koyu bg-yaprak"
        : d === "duraklatildi"
          ? "border-karbon border-dashed bg-kagit"
          : d === "hata"
            ? "border-kase bg-kase-soluk"
            : "border-tel bg-transparent"

  const cubuk =
    d === "calisiyor"
      ? "bg-kase"
      : d === "tamam"
        ? "bg-muhur"
        : d === "duraklatildi"
          ? "bg-karbon"
          : d === "hata"
            ? "bg-kase"
            : "bg-tel"

  return (
    <button
      type="button"
      onClick={onSec}
      aria-pressed={secili}
      className={
        "relative w-full text-left border rounded-sm pl-4 pr-3 py-2.5 transition-colors " +
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-murekkep " +
        kenar +
        (secili ? " ring-1 ring-murekkep ring-offset-2 ring-offset-kagit" : "") +
        (d === "bekliyor" ? " opacity-55" : "")
      }
    >
      <span
        aria-hidden
        className={"absolute left-0 top-0 bottom-0 w-[3px] rounded-l-sm " + cubuk}
        style={d === "calisiyor" ? { animation: "nabiz 1.1s ease-in-out infinite" } : undefined}
      />

      <div className="flex items-baseline gap-2">
        <span className="font-veri text-[11px] text-karbon tabular-nums">
          {String(dugum.no).padStart(2, "0")}
        </span>
        <span className="font-display font-semibold text-[13px] tracking-tight leading-tight">
          {dugum.baslik}
        </span>
        <span className="ml-auto flex items-center gap-1.5">
          {turNo && turNo > 1 && (
            <span className="font-veri text-[9px] px-1 py-px rounded-xs bg-havale-soluk text-havale tracking-[0.08em]">
              {turNo}. TUR
            </span>
          )}
          <MotorRozeti motor={dugum.motor} />
        </span>
      </div>

      <p className="mt-0.5 text-[11px] leading-snug text-murekkep-orta">{dugum.aciklama}</p>

      <div className="mt-2 pt-1.5 border-t border-tel flex items-center justify-between font-veri text-[10px] tabular-nums">
        <span className={d === "calisiyor" ? "text-kase" : "text-karbon"}>
          {d === "calisiyor" && aktifSure !== null
            ? ms(aktifSure)
            : d === "duraklatildi"
              ? "bekliyor"
              : sure
                ? ms(sure)
                : "—"}
        </span>
        <span className="text-karbon">
          {d === "tamam" ? "tamam" : d === "hata" ? "hata" : ""}
        </span>
      </div>
    </button>
  )
}

/** Bileşen çerçevesi. Ajan etiketi doluysa köşeli parantezle basılır. */
function Cerceve({ kusak, children }: { kusak: BilesenKusagi; children: React.ReactNode }) {
  const tekAdim = kusak.satirlar.flat().length === 1
  // Tek adımlık bileşene çerçeve çizmiyoruz; kutu zaten bileşenin kendisi.
  if (tekAdim && !kusak.ajan) return <>{children}</>

  const etiket = kusak.ajan ?? `${kusak.bilesen} · ${kusak.bilesen_adi}`
  return (
    <div className="relative my-6 -ml-5 pl-5">
      <span aria-hidden className="absolute left-0 top-0 bottom-0 w-px bg-tel-koyu" />
      <span aria-hidden className="absolute left-0 top-0 w-2.5 h-px bg-tel-koyu" />
      <span aria-hidden className="absolute left-0 bottom-0 w-2.5 h-px bg-tel-koyu" />
      <div className="pb-3">
        <span
          className={
            "font-veri text-[9px] tracking-[0.14em] uppercase " +
            (kusak.ajan ? "text-kase" : "text-karbon")
          }
        >
          {etiket}
        </span>
      </div>
      {children}
    </div>
  )
}

function Ok() {
  return (
    <div aria-hidden className="flex justify-center py-1">
      <svg width="9" height="16" viewBox="0 0 9 16" className="text-tel-koyu">
        <path d="M4.5 0v12M0.5 9l4 5 4-5" stroke="currentColor" strokeWidth="1" fill="none" />
      </svg>
    </div>
  )
}

/** Akış bitince basılan kaşe. */
function Kase({
  durum,
  toplamMs,
  birim,
}: {
  durum: string
  toplamMs: number | null
  birim?: string
}) {
  const otomatik = durum === "OTOMATIK_ONAYLANDI"
  return (
    <div
      className="pointer-events-none select-none"
      style={{ animation: "kase-bas 520ms cubic-bezier(.2,.9,.3,1.2) both" }}
    >
      <div
        className={
          "border-2 rounded-sm px-3 py-1.5 opacity-90 " +
          (otomatik ? "text-muhur border-muhur" : "text-kase border-kase")
        }
        style={{ transform: "rotate(-4deg)" }}
      >
        <div className="font-display font-bold text-[11px] tracking-[0.1em] uppercase leading-none">
          {DURUM_ETIKET[durum] ?? durum}
        </div>
        <div className="mt-1 font-veri text-[9px] tracking-wide leading-tight opacity-80">
          {new Date().toLocaleDateString("tr-TR")} · {toplamMs ? sn(toplamMs) : "—"}
          {birim && <br />}
          {birim}
        </div>
      </div>
    </div>
  )
}

function YanPanel({
  dugum,
  kayit,
  sure,
  turNo,
  duraklamaNotu,
}: {
  dugum: DugumTanimi | null
  kayit: DugumKaydi | null
  sure?: number
  turNo?: number
  duraklamaNotu?: string | null
}) {
  if (!dugum) {
    return (
      <div className="h-full border border-tel rounded-sm p-5 bg-yaprak/50">
        <BolumBasligi>Adım ayrıntısı</BolumBasligi>
        <p className="mt-3 text-[13px] leading-relaxed text-murekkep-orta font-govde">
          Bir adıma tıklayın. Ne karar verdiği, neye dayandırdığı ve ürettiği ham çıktı
          burada görünür.
        </p>
      </div>
    )
  }

  return (
    <div className="h-full border border-tel rounded-sm bg-yaprak flex flex-col overflow-hidden">
      <div className="px-5 py-4 border-b border-tel">
        <div className="flex items-baseline gap-2">
          <span className="font-veri text-[11px] text-karbon tabular-nums">
            {String(dugum.no).padStart(2, "0")}
          </span>
          <h2 className="font-display font-bold text-[15px] tracking-tight">{dugum.baslik}</h2>
          <span className="ml-auto">
            <MotorRozeti motor={dugum.motor} />
          </span>
        </div>
        <p className="mt-1 text-[11px] text-murekkep-orta">{dugum.aciklama}</p>
        <p className="mt-1.5 font-veri text-[9px] tracking-[0.1em] uppercase text-karbon">
          Bileşen {dugum.bilesen} · {dugum.bilesen_adi}
          {dugum.ajan && ` · ${dugum.ajan}`}
        </p>
      </div>

      <dl className="grid grid-cols-3 divide-x divide-tel border-b border-tel">
        <div className="px-4 py-3">
          <dt className="font-veri text-[9px] tracking-[0.12em] uppercase text-karbon">Süre</dt>
          <dd className="mt-1 font-veri text-[13px] tabular-nums">{sure ? ms(sure) : "—"}</dd>
        </div>
        <div className="px-4 py-3">
          <dt className="font-veri text-[9px] tracking-[0.12em] uppercase text-karbon">Güven</dt>
          <dd className="mt-1 font-veri text-[13px] tabular-nums">
            {kayit?.guven != null ? guvenYaz(kayit.guven) : "—"}
          </dd>
        </div>
        <div className="px-4 py-3">
          <dt className="font-veri text-[9px] tracking-[0.12em] uppercase text-karbon">Tur</dt>
          <dd className="mt-1 font-veri text-[13px] tabular-nums">{turNo ?? 1}</dd>
        </div>
      </dl>

      <div className="flex-1 overflow-auto">
        {kayit?.gerekce && (
          <section className="px-5 py-4 border-b border-tel">
            <BolumBasligi>Gerekçe</BolumBasligi>
            <p className="mt-2 font-govde text-[14px] leading-relaxed">{kayit.gerekce}</p>
          </section>
        )}

        {duraklamaNotu && (
          <section className="px-5 py-4 border-b border-tel bg-havale-soluk/40">
            <BolumBasligi>Geri gönderme</BolumBasligi>
            <p className="mt-2 font-govde text-[14px] leading-relaxed">{duraklamaNotu}</p>
          </section>
        )}

        {kayit?.cikti && (
          <section className="px-5 py-4">
            <BolumBasligi>Ham çıktı</BolumBasligi>
            <pre className="mt-2 font-veri text-[10.5px] leading-relaxed whitespace-pre-wrap break-words text-murekkep-orta">
              {JSON.stringify(kayit.cikti, null, 2)}
            </pre>
          </section>
        )}

        {!kayit && (
          <p className="px-5 py-4 font-govde text-[13px] text-murekkep-orta">
            Bu adım henüz çalışmadı.
          </p>
        )}
      </div>
    </div>
  )
}

function Gunluk({ olaylar }: { olaylar: Olay[] }) {
  const satirlar = [...olaylar].reverse()

  const metin = (o: Olay) => {
    switch (o.tur) {
      case "anlik_goruntu":
        return `bağlanıldı · ${o.canli ? "canlı" : "geçmiş koşu"}`
      case "dugum_basladi":
        return `${o.dugum_adi} başladı${o.tur_no && o.tur_no > 1 ? ` · ${o.tur_no}. tur` : ""}`
      case "dugum_bitti":
        return `${o.dugum_adi} bitti · ${ms(o.sure_ms ?? 0)}`
      case "dugum_duraklatildi":
        return `${o.dugum_adi} durakladı · ${o.gerekce}`
      case "dugum_tekrar":
        return `${o.dugum_adi} yeniden çalışıyor · ${o.gerekce ?? ""}`
      case "hata":
        return `hata · ${o.hata}`
      case "durum_degisti":
        return `durum → ${DURUM_ETIKET[o.durum ?? ""] ?? o.durum}`
      case "akis_bitti":
        return `akış bitti · ${ms(o.toplam_ms ?? 0)}`
      default:
        return o.tur
    }
  }

  const renk = (o: Olay) =>
    o.tur === "dugum_duraklatildi"
      ? "text-havale"
      : o.tur === "hata"
        ? "text-kase"
        : o.tur === "durum_degisti" || o.tur === "akis_bitti"
          ? "text-murekkep"
          : "text-murekkep-orta"

  return (
    <div className="border border-tel rounded-sm bg-yaprak">
      <div className="px-4 py-2 border-b border-tel">
        <BolumBasligi
          sag={
            <span className="font-veri text-[9px] text-karbon tabular-nums">
              {olaylar.length} olay
            </span>
          }
        >
          İşlem günlüğü
        </BolumBasligi>
      </div>
      <ul className="px-4 py-2 font-veri text-[10.5px] leading-[1.7] max-h-72 overflow-y-auto overscroll-contain">
        {satirlar.length === 0 && <li className="text-karbon py-1">—</li>}
        {satirlar.map((o, i) => (
          <li key={olaylar.length - i} className="flex gap-3">
            <span className="text-tel-koyu tabular-nums shrink-0">{saat(o.ts)}</span>
            <span className={renk(o)}>{metin(o)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

// ---------------------------------------------------------------------------

export default function AkisEkrani({ akis }: { akis: ReturnType<typeof useAkis> }) {
  const { kusaklar, harita, hazir, hata: dugumHatasi } = useDugumler()
  const [seciliNo, setSeciliNo] = useState<number | null>(null)
  const [surukleniyor, setSurukleniyor] = useState(false)
  const dosyaRef = useRef<HTMLInputElement>(null)

  const secili = seciliNo != null ? (harita[seciliNo] ?? null) : null
  const seciliKayit = seciliNo != null ? akis.sonKayit(seciliNo) : null

  const duraklamaNotu = useMemo(() => {
    if (seciliNo == null) return null
    const o = [...akis.olaylar]
      .reverse()
      .find((x) => x.tur === "dugum_duraklatildi" && x.dugum === seciliNo)
    return o?.gerekce ?? null
  }, [akis.olaylar, seciliNo])

  const bitti = akis.durum != null && !["ALINDI", "ISLENIYOR"].includes(akis.durum)
  const adimSayisi = Object.keys(harita).length

  const dosyaSec = (f: File | undefined) => {
    if (!f) return
    setSeciliNo(null)
    void akis.yukle(f)
  }

  return (
    <div>
      {/* ---- üst şerit ---- */}
      <div className="border-b border-tel bg-yaprak">
        <div className="mx-auto max-w-[1400px] px-6 py-3 flex items-center gap-6 min-h-[62px]">
          {akis.dosyaAdi ? (
            <div className="min-w-0 flex items-center gap-4 font-veri text-[10px] text-murekkep-orta">
              <span className="text-karbon tracking-[0.12em] uppercase text-[9px]">Evrak</span>
              <span className="truncate">{akis.dosyaAdi}</span>
              {bitti && (
                <span className="shrink-0 font-veri text-[9px] tracking-[0.1em] uppercase text-karbon border border-tel-koyu rounded-xs px-1.5 py-px">
                  geçmiş koşu
                </span>
              )}
            </div>
          ) : (
            <p className="font-veri text-[10px] text-karbon tracking-[0.12em] uppercase">
              Evrak bekleniyor
            </p>
          )}

          <div className="ml-auto flex items-center gap-6">
            {akis.durum && (
              <dl className="flex items-center gap-6 font-veri text-[10px] tabular-nums">
                <div className="text-right">
                  <dt className="text-karbon tracking-[0.12em] uppercase text-[9px]">Adım</dt>
                  <dd className="text-[13px]">
                    {akis.bitenSayisi} / {adimSayisi || "—"}
                  </dd>
                </div>
                <div className="text-right">
                  <dt className="text-karbon tracking-[0.12em] uppercase text-[9px]">Süre</dt>
                  <dd className="text-[13px]">
                    {akis.toplamMs ? sn(akis.toplamMs) : akis.durum === "ISLENIYOR" ? "…" : "—"}
                  </dd>
                </div>
              </dl>
            )}

            {bitti && <Kase durum={akis.durum!} toplamMs={akis.toplamMs} />}

            <input
              ref={dosyaRef}
              type="file"
              accept=".pdf,.png,.jpg,.jpeg,.txt"
              className="sr-only"
              onChange={(e) => dosyaSec(e.target.files?.[0])}
            />
            <button
              type="button"
              onClick={() => dosyaRef.current?.click()}
              disabled={akis.yukleniyor}
              className="font-display font-semibold text-[13px] px-4 py-2 rounded-sm bg-murekkep text-yaprak
                         hover:bg-murekkep-orta disabled:opacity-50 transition-colors
                         focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-murekkep"
            >
              {akis.yukleniyor ? "Yükleniyor…" : "Evrak yükle"}
            </button>
          </div>
        </div>
      </div>

      {(akis.hata || dugumHatasi) && (
        <div className="mx-auto max-w-[1400px] px-6 pt-4">
          <p className="border border-kase bg-kase-soluk text-kase rounded-sm px-4 py-2.5 text-[13px]">
            {akis.hata ?? dugumHatasi}
          </p>
        </div>
      )}

      <main className="mx-auto max-w-[1400px] px-6 py-6">
        {akis.olaylar.length === 0 && !akis.yukleniyor ? (
          <div
            onDragOver={(e) => {
              e.preventDefault()
              setSurukleniyor(true)
            }}
            onDragLeave={() => setSurukleniyor(false)}
            onDrop={(e) => {
              e.preventDefault()
              setSurukleniyor(false)
              dosyaSec(e.dataTransfer.files?.[0])
            }}
            className={
              "rounded-sm border-2 border-dashed px-8 py-20 text-center transition-colors " +
              (surukleniyor ? "border-kase bg-kase-soluk/30" : "border-tel-koyu")
            }
          >
            <p className="font-display font-bold text-[18px] tracking-tight">
              Evrakı buraya bırakın
            </p>
            <p className="mt-2 font-govde text-[15px] text-murekkep-orta max-w-md mx-auto leading-relaxed">
              {hazir
                ? `${adimSayisi} adım, sekiz bileşen, iki ajan. Her adımda ne karar verildiği,
                   neye dayandırıldığı ve ne kadar sürdüğü burada görünür.`
                : "Adım tablosu sunucudan alınıyor…"}
            </p>
            <button
              type="button"
              onClick={() => dosyaRef.current?.click()}
              className="mt-6 font-display font-semibold text-[13px] px-4 py-2 rounded-sm border border-murekkep
                         hover:bg-murekkep hover:text-yaprak transition-colors
                         focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-murekkep"
            >
              Dosya seç
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_380px] gap-6 items-start">
            <section aria-label="Akış çizelgesi">
              {kusaklar.map((kusak, gi) => (
                <div key={kusak.bilesen}>
                  {gi > 0 && <Ok />}
                  <Cerceve kusak={kusak}>
                    {kusak.satirlar.map((satir, si) => (
                      <div key={si}>
                        {si > 0 && <Ok />}
                        <div
                          className="grid gap-3"
                          style={{
                            gridTemplateColumns: `repeat(${satir.length}, minmax(0, 1fr))`,
                          }}
                        >
                          {satir.map((d) => (
                            <DugumKarti
                              key={d.no}
                              dugum={d}
                              durum={akis.kutuDurumlari[d.no]}
                              sure={akis.sureler[d.no]}
                              turNo={akis.turSayilari[d.no]}
                              aktifSure={akis.aktifSureler[d.no] ?? null}
                              secili={seciliNo === d.no}
                              onSec={() => setSeciliNo(seciliNo === d.no ? null : d.no)}
                            />
                          ))}
                        </div>
                      </div>
                    ))}
                  </Cerceve>
                </div>
              ))}
            </section>

            <aside className="lg:sticky lg:top-6 flex flex-col gap-4">
              <div className="h-[440px]">
                <YanPanel
                  dugum={secili}
                  kayit={seciliKayit}
                  sure={seciliNo != null ? akis.sureler[seciliNo] : undefined}
                  turNo={seciliNo != null ? akis.turSayilari[seciliNo] : undefined}
                  duraklamaNotu={duraklamaNotu}
                />
              </div>
              <Gunluk olaylar={akis.olaylar} />
            </aside>
          </div>
        )}
      </main>
    </div>
  )
}
