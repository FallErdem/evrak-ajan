import { useState } from "react"
import type { Taslak, UslupBulgusu } from "./tipler"
import { BolumBasligi, KARAR_TURU_ETIKET } from "./ortak"

// Resmî Yazışmalarda Uygulanacak Usul ve Esaslar Hakkında Yönetmelik düzeni:
// başlık ortada, sayı solda / tarih sağda, konu altında, muhatap, metin, imza sağ altta.
//
// SAYI, TARİH ve İMZALAYANIN ADI daima null gelir ve düzenlenemez — EBYS'de
// kayıt ve imza anında atanır (sözleşme 5.6.6). Boş bırakmak yerine ne olacağını
// yazıyoruz; jüri "burada ne olacağını biliyoruz, henüz atanmadı" mesajını alsın.

const ATANACAK = "EBYS kayıt anında atanacak"
const IMZA_ATANACAK = "İmza anında atanacak"

function muhatapOrtali(muhatap: string): boolean {
  const harfler = muhatap.replace(/[^A-Za-zÇĞİÖŞÜçğıöşü]/g, "")
  return harfler.length > 0 && harfler === harfler.toLocaleUpperCase("tr-TR")
}

function KenarNotu({ bulgu }: { bulgu: UslupBulgusu }) {
  const hata = bulgu.duzey === "hata"
  return (
    <li className="relative pl-3">
      <span
        aria-hidden
        className={"absolute left-0 top-1 bottom-1 w-px " + (hata ? "bg-kase" : "bg-havale")}
      />
      <div className="flex items-baseline gap-1.5 flex-wrap">
        <span
          className={"font-veri text-[10px] tracking-[0.06em] " + (hata ? "text-kase" : "text-havale")}
        >
          {bulgu.kural_no}
        </span>
        {bulgu.cozuldu && (
          <span className="font-veri text-[8.5px] tracking-[0.1em] uppercase text-muhur">
            giderildi
          </span>
        )}
      </div>
      <p
        className={
          "mt-0.5 font-govde text-[12.5px] leading-snug " +
          (bulgu.cozuldu ? "text-karbon line-through decoration-tel-koyu" : "text-murekkep-orta")
        }
      >
        {bulgu.mesaj}
      </p>
      <p className="mt-0.5 font-veri text-[9.5px] text-karbon leading-snug">{bulgu.mevzuat}</p>
    </li>
  )
}

export default function ResmiYazi({
  taslak,
  bulgular,
  linterTuru,
  kararTuru,
  baslik = "Onaylanacak yazı",
  kenarGoster = true,
  katlanabilir = false,
  acikBaslangic = true,
  duzenleniyor = false,
  govde,
  konu,
  muhatap,
  yaziBasligi,
  onGovdeDegisti,
  onKonuDegisti,
  onMuhatapDegisti,
  onBaslikDegisti,
}: {
  taslak: Taslak
  bulgular?: UslupBulgusu[]
  linterTuru?: number | null
  kararTuru?: string
  baslik?: string
  kenarGoster?: boolean
  /** Başlık şeridi tıklanınca yazı katlanır. Künyeyi sadeleştirmek için. */
  katlanabilir?: boolean
  acikBaslangic?: boolean
  duzenleniyor?: boolean
  govde: string
  konu?: string
  muhatap?: string
  yaziBasligi?: string
  onGovdeDegisti?: (v: string) => void
  onKonuDegisti?: (v: string) => void
  onMuhatapDegisti?: (v: string) => void
  onBaslikDegisti?: (v: string) => void
}) {
  const [acik, setAcik] = useState(acikBaslangic)
  // Düzenleme açıkken katlanmaz: yazdığı metni göremeyen kullanıcı kalmasın.
  const gorunur = !katlanabilir || acik || duzenleniyor

  const bulgu = bulgular ?? []
  const gosterKonu = konu ?? taslak.konu
  const gosterMuhatap = muhatap ?? taslak.muhatap
  const gosterBaslik = yaziBasligi ?? taslak.baslik
  const baslikSatirlari = gosterBaslik.split("\n").filter(Boolean)
  const paragraflar = govde.split(/\n{2,}/).filter((p) => p.trim())
  const ortali = muhatapOrtali(gosterMuhatap)

  const duzStil =
    "w-full bg-kagit border border-havale rounded-sm px-2 py-1 " +
    "focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-havale"

  return (
    <div className="border border-tel rounded-sm bg-kagit overflow-hidden">
      <div
        className={
          "px-5 py-3 bg-yaprak " + (gorunur ? "border-b border-tel" : "")
        }
        {...(katlanabilir && !duzenleniyor
          ? {
              role: "button" as const,
              tabIndex: 0,
              "aria-expanded": acik,
              onClick: () => setAcik((v) => !v),
              onKeyDown: (e: React.KeyboardEvent) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault()
                  setAcik((v) => !v)
                }
              },
              className:
                "px-5 py-3 bg-yaprak cursor-pointer transition-colors hover:bg-kagit/70 " +
                "focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-murekkep " +
                (gorunur ? "border-b border-tel" : ""),
            }
          : {})}
      >
        <BolumBasligi
          sag={
            <div className="flex items-center gap-2">
              {kararTuru && (
                <span className="font-veri text-[9px] tracking-[0.1em] uppercase text-karbon border border-tel-koyu rounded-xs px-1.5 py-px">
                  {KARAR_TURU_ETIKET[kararTuru] ?? kararTuru}
                </span>
              )}
              {linterTuru != null && (
                <span
                  className={
                    "font-veri text-[9px] tracking-[0.1em] uppercase rounded-xs px-1.5 py-px border " +
                    (linterTuru > 1
                      ? "text-havale border-havale bg-havale-soluk"
                      : "text-muhur border-muhur bg-muhur-soluk")
                  }
                >
                  {linterTuru > 1 ? `${linterTuru}. turda geçti` : "ilk turda geçti"}
                </span>
              )}
            </div>
          }
        >
          {katlanabilir && !duzenleniyor && (
            <span aria-hidden className="mr-2 text-karbon">
              {acik ? "−" : "+"}
            </span>
          )}
          {baslik}
        </BolumBasligi>
      </div>

      <div
        className={
          (gorunur ? "" : "hidden ") +
          (kenarGoster ? "grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_200px]" : "grid grid-cols-1")
        }
      >
        {/* ---------------- kâğıt ---------------- */}
        <article
          className="bg-yaprak px-8 sm:px-12 py-10 min-w-0 overflow-hidden font-govde text-[14.5px] leading-[1.75] text-murekkep"
          aria-label="Resmî yazı"
        >
          {/* kurum başlığı */}
          <header className="text-center">
            {duzenleniyor && onBaslikDegisti ? (
              <textarea
                value={gosterBaslik}
                onChange={(e) => onBaslikDegisti(e.target.value)}
                rows={3}
                aria-label="Kurum başlığı"
                className={duzStil + " resize-none text-center font-display font-bold text-[13px] tracking-[0.06em]"}
              />
            ) : (
              baslikSatirlari.map((s, i) => (
                <p
                  key={i}
                  className={
                    i === 0
                      ? "font-display text-[12px] tracking-[0.3em]"
                      : i === 1
                        ? "font-display font-bold text-[13.5px] tracking-[0.06em] uppercase mt-0.5"
                        : "font-display text-[12.5px] mt-0.5"
                  }
                >
                  {s}
                </p>
              ))
            )}
          </header>

          {/* sayı · tarih · konu */}
          <div className="mt-8 font-veri text-[11.5px] leading-relaxed">
            <div className="flex items-baseline gap-3">
              <span className="w-12 shrink-0">Sayı</span>
              <span className="shrink-0">:</span>
              <span className="text-karbon italic">{ATANACAK}</span>
              <span className="ml-auto shrink-0 text-karbon italic">{ATANACAK}</span>
            </div>
            <div className="flex items-baseline gap-3 mt-1">
              <span className="w-12 shrink-0">Konu</span>
              <span className="shrink-0">:</span>
              {duzenleniyor && onKonuDegisti ? (
                <input
                  value={gosterKonu}
                  onChange={(e) => onKonuDegisti(e.target.value)}
                  aria-label="Yazı konusu"
                  className={duzStil + " font-veri text-[11.5px] flex-1 min-w-0"}
                />
              ) : (
                <span>{gosterKonu}</span>
              )}
            </div>
          </div>

          {/* muhatap */}
          {duzenleniyor && onMuhatapDegisti ? (
            <div className="mt-9">
              <textarea
                value={gosterMuhatap}
                onChange={(e) => onMuhatapDegisti(e.target.value)}
                rows={2}
                aria-label="Muhatap"
                className={
                  duzStil +
                  " resize-none font-display font-semibold text-[13.5px] tracking-[0.04em] " +
                  (ortali ? "text-center" : "")
                }
              />
            </div>
          ) : (
            <p
              className={
                "mt-9 font-display font-semibold text-[13.5px] tracking-[0.04em] whitespace-pre-line " +
                (ortali ? "text-center" : "")
              }
            >
              {gosterMuhatap}
            </p>
          )}

          {/* gövde */}
          <div className="mt-7">
            {duzenleniyor && onGovdeDegisti ? (
              <textarea
                value={govde}
                onChange={(e) => onGovdeDegisti(e.target.value)}
                rows={Math.max(8, govde.split("\n").length + 2)}
                aria-label="Yazı gövdesi"
                className={duzStil + " resize-y font-govde text-[14.5px] leading-[1.75]"}
              />
            ) : (
              paragraflar.map((p, i) => (
                <p key={i} className="indent-10 mb-4 last:mb-0 text-justify">
                  {p.trim()}
                </p>
              ))
            )}
          </div>

          {/* imza */}
          <footer className="mt-12 flex justify-end">
            <div className="text-center min-w-[220px]">
              <p className="font-display text-[12px] text-karbon italic">{IMZA_ATANACAK}</p>
              <p className="font-display font-semibold text-[13px] mt-0.5">
                {taslak.imza_unvan}
              </p>
            </div>
          </footer>

          {duzenleniyor && (
            <p className="mt-6 font-veri text-[9.5px] text-havale leading-snug">
              Sayı, tarih ve imzalayanın adı EBYS'de kayıt ve imza anında atanır;
              taslak aşamasında bilinmez ve düzenlenemez. Başlık, konu, muhatap ve
              gövde düzenlenebilir.
            </p>
          )}
        </article>

        {/* ---------------- kenar notları ---------------- */}
        {kenarGoster && (
          <aside
            className="border-t xl:border-t-0 xl:border-l border-tel px-4 py-5 bg-kagit"
            aria-label="Üslup denetimi bulguları"
          >
            <p className="font-veri text-[9px] tracking-[0.14em] uppercase text-karbon">
              Üslup denetimi
            </p>
            <p className="mt-1 font-veri text-[9.5px] text-karbon leading-snug">
              40 kural · deterministik · model yok
            </p>

            {bulgu.length === 0 ? (
              <p className="mt-4 font-govde text-[12.5px] text-muhur leading-snug">
                Bulgu yok. Taslak kuralların tamamını ilk turda geçti.
              </p>
            ) : (
              <ul className="mt-4 flex flex-col gap-4">
                {bulgu.map((b) => (
                  <KenarNotu key={b.kural_no} bulgu={b} />
                ))}
              </ul>
            )}
          </aside>
        )}
      </div>
    </div>
  )
}
