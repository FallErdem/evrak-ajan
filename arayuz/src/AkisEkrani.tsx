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

/**
 * Bir adım = bir daire. Kart yerleşiminden daireye geçildi (mentör isteği,
 * 2026-08-25): akış tek bakışta görünsün, ayrıntı yan panelde kalsın.
 *
 * Renk sözlüğü kart sürümünden BİREBİR taşındı — çalışan kırmızı yanıp söner,
 * biten yeşil, bekleyen gri. Bu üç renk demoda anlatılan şeyin kendisi.
 */
function DugumDairesi({
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

  const halka =
    d === "calisiyor"
      ? "border-kase bg-kase-soluk"
      : d === "tamam"
        ? "border-muhur bg-muhur-soluk"
        : d === "duraklatildi"
          ? "border-karbon border-dashed bg-kagit"
          : d === "hata"
            ? "border-kase bg-kase-soluk"
            : "border-tel bg-transparent"

  const yazi =
    d === "calisiyor"
      ? "text-kase"
      : d === "tamam"
        ? "text-muhur"
        : d === "hata"
          ? "text-kase"
          : "text-karbon"

  const sureMetni =
    d === "calisiyor" && aktifSure !== null
      ? ms(aktifSure)
      : d === "duraklatildi"
        ? "bekliyor"
        : sure
          ? ms(sure)
          : "—"

  return (
    <div className={"w-[92px] flex flex-col items-center " + (d === "bekliyor" ? "opacity-55" : "")}>
      <button
        type="button"
        onClick={onSec}
        aria-pressed={secili}
        title={dugum.aciklama}
        className={
          "relative w-14 h-14 rounded-full flex items-center justify-center transition-colors " +
          "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-murekkep " +
          (secili ? "ring-1 ring-murekkep ring-offset-2 ring-offset-kagit rounded-full" : "")
        }
      >
        {/*
          Halka ayrı bir katman: nabız yalnızca kenarlığı söndürsün, içindeki
          numarayı değil. Düğmenin kendisine animasyon verilseydi rakam da
          kaybolurdu.
        */}
        <span
          aria-hidden
          className={"absolute inset-0 rounded-full border-2 " + halka}
          style={d === "calisiyor" ? { animation: "nabiz 1.1s ease-in-out infinite" } : undefined}
        />
        <span className={"relative font-veri text-[15px] tabular-nums " + yazi}>
          {String(dugum.no).padStart(2, "0")}
        </span>

        {turNo && turNo > 1 && (
          <span
            title={`${turNo}. tur`}
            className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-havale text-yaprak
                       font-veri text-[9px] leading-4 text-center tabular-nums"
          >
            {turNo}
          </span>
        )}
      </button>

      <span className="mt-1.5 font-display font-semibold text-[10.5px] leading-tight tracking-tight text-center">
        {dugum.baslik}
      </span>
      <span className="mt-0.5 flex items-center gap-1">
        <MotorRozeti motor={dugum.motor} />
      </span>
      <span
        className={
          "mt-0.5 font-veri text-[9px] tabular-nums " +
          (d === "calisiyor" ? "text-kase" : "text-karbon")
        }
      >
        {sureMetni}
      </span>
    </div>
  )
}

/**
 * Ajan çerçevesi. Daireler yatay aktığı için ayraç ALTA alındı: aynı ajana
 * ait daireleri bir çizgi bağlar, etiket çizginin altında durur.
 * Ajanı olmayan bileşen çerçevesiz çizilir — çerçeve ancak özerklik varsa
 * bir şey anlatıyor.
 */
function Cerceve({ kusak, children }: { kusak: BilesenKusagi; children: React.ReactNode }) {
  if (!kusak.ajan) return <>{children}</>

  return (
    <div className="relative pb-5">
      {children}
      <span aria-hidden className="absolute left-1 right-1 bottom-3.5 h-px bg-kase/40" />
      <span aria-hidden className="absolute left-1 bottom-3.5 w-px h-1.5 bg-kase/40" />
      <span aria-hidden className="absolute right-1 bottom-3.5 w-px h-1.5 bg-kase/40" />
      <span className="absolute inset-x-0 bottom-0 text-center font-veri text-[8.5px] tracking-[0.14em] uppercase text-kase">
        {kusak.ajan}
      </span>
    </div>
  )
}

/** Daireler arası yatay ok. Dairelerin merkez hizasında durur. */
function Ok() {
  return (
    <div aria-hidden className="w-4 shrink-0 flex justify-center" style={{ paddingTop: 24 }}>
      <svg width="14" height="9" viewBox="0 0 14 9" className="text-tel-koyu">
        <path d="M0 4.5h11M8 0.5l4.5 4-4.5 4" stroke="currentColor" strokeWidth="1" fill="none" />
      </svg>
    </div>
  )
}

/** Eş zamanlı koşan iki adım arasına ok değil, paralellik işareti girer. */
function Paralel() {
  return (
    <div
      aria-hidden
      title="Eş zamanlı koşuyor"
      className="w-4 shrink-0 flex justify-center font-veri text-[13px] text-tel-koyu"
      style={{ paddingTop: 18 }}
    >
      ∥
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

/** İki adım aynı paralel grupta mı — aralarına ok değil, ∥ girer. */
function esZamanli(gruplar: number[][], a: number, b: number): boolean {
  return gruplar.some((g) => g.includes(a) && g.includes(b))
}

// ---------------------------------------------------------------------------

export default function AkisEkrani({
  akis,
  onOnayaGit,
}: {
  akis: ReturnType<typeof useAkis>
  /** Akış bitip insan onayına düştüğünde evrağı onay panelinde açar. */
  onOnayaGit?: (evrakId: string) => void
}) {
  const { kusaklar, harita, hazir, paralelGruplar, hata: dugumHatasi } = useDugumler()
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

  // Karar alınabilir durumdaysa onay paneline geçiş düğmesi çıkar.
  // Sonuçlanmış evrakta çıkmaz — onay panelinde yapacak bir şey yok.
  const onayaGider =
    !!onOnayaGit &&
    !!akis.evrakId &&
    (akis.durum === "INSAN_ONAYI_BEKLIYOR" || akis.durum === "EKSIK_BILGI_BEKLIYOR")

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
            <section
              aria-label="Akış çizelgesi"
              className="border border-tel rounded-sm bg-yaprak px-5 py-6"
            >
              {/*
                Kuşaklar yatay akar ve sığmayınca alt satıra sarar. Bir kuşak
                kendi içinde bölünmez (`flex-nowrap`) — ajan çerçevesi ortadan
                ikiye ayrılmasın diye.
              */}
              <div className="flex flex-wrap items-start gap-x-1 gap-y-7">
                {kusaklar.map((kusak, gi) => {
                  const adimlar = kusak.satirlar.flat()
                  return (
                    <div key={kusak.bilesen} className="flex items-start">
                      <Cerceve kusak={kusak}>
                        <div className="flex items-start flex-nowrap">
                          {adimlar.map((d, i) => (
                            <div key={d.no} className="flex items-start">
                              {i > 0 &&
                                (esZamanli(paralelGruplar, adimlar[i - 1].no, d.no) ? (
                                  <Paralel />
                                ) : (
                                  <Ok />
                                ))}
                              <DugumDairesi
                                dugum={d}
                                durum={akis.kutuDurumlari[d.no]}
                                sure={akis.sureler[d.no]}
                                turNo={akis.turSayilari[d.no]}
                                aktifSure={akis.aktifSureler[d.no] ?? null}
                                secili={seciliNo === d.no}
                                onSec={() => setSeciliNo(seciliNo === d.no ? null : d.no)}
                              />
                            </div>
                          ))}
                        </div>
                      </Cerceve>
                      {gi < kusaklar.length - 1 && <Ok />}
                    </div>
                  )
                })}
              </div>

              {/* ---- onaya gönder ---- */}
              {onayaGider && (
                <div className="mt-8 pt-5 border-t border-tel flex items-center gap-4 flex-wrap">
                  <button
                    type="button"
                    onClick={() => akis.evrakId && onOnayaGit?.(akis.evrakId)}
                    className="font-display font-semibold text-[13px] px-4 py-2 rounded-sm bg-murekkep text-yaprak
                               hover:bg-murekkep-orta transition-colors
                               focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-murekkep"
                  >
                    Onay paneline gönder
                  </button>
                  <p className="font-veri text-[10px] text-karbon leading-relaxed max-w-md">
                    {akis.durum === "EKSIK_BILGI_BEKLIYOR"
                      ? "Evrak eksik bilgi bekliyor; künyesi ve tamamlama yazısı onay panelinde."
                      : "Boru hattı bitti, güven kapısı insan onayı istedi. Üretilen yazı ve gerekçesi onay panelinde."}
                  </p>
                </div>
              )}
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
