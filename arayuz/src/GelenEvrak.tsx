import { useEffect, useMemo, useState } from "react"
import type { Alan, Evrak, EvrakMetni, Ustveri, Varlik, Yontem } from "./tipler"
import {
  BolumBasligi,
  GIRDI_TIPI_ETIKET,
  KilitRozeti,
  YONTEM_ETIKET,
  getir,
  guvenYaz,
} from "./ortak"

// Onaycı neyi imzaladığını görüyor ama neye dayanarak üretildiğini göremiyordu.
// Bu panel gelen evrakın ham metnini gösterir ve her alanı metinde işaretler.
//
// İşaretlenemeyen alan, metinde birebir geçmeyen çıkarımdır — gizlemiyoruz.
// Maskeli kişisel verilerin kanıt metni sunucudan gelmez; aksi hâlde maskeleme
// metin üzerinden delinirdi.

const ALAN_ETIKET: Record<keyof Ustveri, string> = {
  sayi: "Sayı",
  tarih: "Tarih",
  konu: "Konu",
  muhatap: "Muhatap",
  ilgi: "İlgi",
  imza: "İmza",
  ek: "Ek",
  dagitim: "Dağıtım",
}

type Kayit = {
  etiket: string
  deger: string
  guven: number
  yontem: Yontem
  kanit: string | null
  pii: boolean
  sira?: number
  tur: "ustveri" | "varlik"
}

function isaretle(metin: string, kayitlar: Kayit[]) {
  const bulunan: { bas: number; son: number; etiket: string }[] = []
  for (const k of kayitlar) {
    if (!k.kanit) continue
    const i = metin.indexOf(k.kanit)
    if (i < 0) continue
    const yeni = { bas: i, son: i + k.kanit.length, etiket: k.etiket }
    if (!bulunan.some((b) => yeni.bas < b.son && b.bas < yeni.son)) bulunan.push(yeni)
  }
  return bulunan.sort((a, b) => a.bas - b.bas)
}

export default function GelenEvrak({
  detay,
  hamAc,
}: {
  detay: Evrak
  hamAc: (sira: number) => Promise<string>
}) {
  const [veri, setVeri] = useState<EvrakMetni | null>(null)
  const [hata, setHata] = useState<string | null>(null)
  const [vurgulu, setVurgulu] = useState<string | null>(null)
  const [acilan, setAcilan] = useState<Record<number, string>>({})

  useEffect(() => {
    let iptal = false
    setVeri(null)
    setHata(null)
    setAcilan({})
    getir<EvrakMetni>(`/api/evrak/${detay.evrak_id}/metin`)
      .then((v) => !iptal && setVeri(v))
      .catch((e) => !iptal && setHata(e instanceof Error ? e.message : "Metin alınamadı"))
    return () => {
      iptal = true
    }
  }, [detay.evrak_id])

  const kayitlar = useMemo<Kayit[]>(() => {
    const liste: Kayit[] = []
    if (detay.ustveri) {
      for (const [ad, alan] of Object.entries(detay.ustveri) as [keyof Ustveri, Alan][]) {
        if (!alan.deger) continue
        liste.push({
          etiket: ALAN_ETIKET[ad] ?? ad,
          deger: alan.deger,
          guven: alan.guven,
          yontem: alan.yontem,
          kanit: alan.kanit_metin,
          pii: false,
          tur: "ustveri",
        })
      }
    }
    for (const v of (detay.varliklar ?? []) as Varlik[]) {
      liste.push({
        etiket: v.tur,
        deger: acilan[v.sira] ?? v.deger,
        guven: v.guven,
        yontem: null,
        kanit: v.kanit_metin,
        pii: v.pii,
        sira: v.sira,
        tur: "varlik",
      })
    }
    return liste
  }, [detay, acilan])

  const parcalar = useMemo(() => {
    if (!veri) return null
    const isaretler = isaretle(veri.metin, kayitlar)
    const cikti: { metin: string; etiket?: string }[] = []
    let imlec = 0
    for (const i of isaretler) {
      if (i.bas > imlec) cikti.push({ metin: veri.metin.slice(imlec, i.bas) })
      cikti.push({ metin: veri.metin.slice(i.bas, i.son), etiket: i.etiket })
      imlec = i.son
    }
    if (imlec < veri.metin.length) cikti.push({ metin: veri.metin.slice(imlec) })
    return cikti
  }, [veri, kayitlar])

  const bulunan = veri ? isaretle(veri.metin, kayitlar).length : 0

  const acmaDene = async (sira: number) => {
    try {
      const ham = await hamAc(sira)
      setAcilan((a) => ({ ...a, [sira]: ham }))
    } catch (e) {
      setHata(e instanceof Error ? e.message : "Kişisel veri açılamadı")
    }
  }

  return (
    <div className="border border-tel rounded-sm bg-kagit overflow-hidden">
      <div className="px-5 py-3 border-b border-tel bg-yaprak">
        <BolumBasligi
          sag={
            veri ? (
              <span className="font-veri text-[9px] text-karbon tabular-nums">
                {GIRDI_TIPI_ETIKET[veri.girdi_tipi] ?? veri.girdi_tipi}
                {veri.ocr_motoru && ` · ${veri.ocr_motoru}`} ·{" "}
                {veri.karakter.toLocaleString("tr-TR")} karakter · {bulunan}/{kayitlar.length}{" "}
                alan işaretlendi
              </span>
            ) : undefined
          }
        >
          Gelen evrak
        </BolumBasligi>
      </div>

      {hata && (
        <p className="px-5 py-4 font-govde text-[13.5px] text-kase">{hata}</p>
      )}
      {!veri && !hata && (
        <p className="px-5 py-4 font-veri text-[11px] text-karbon">Metin okunuyor…</p>
      )}

      {veri && (
        <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_280px]">
          <div className="bg-yaprak px-6 sm:px-10 py-8">
            <p className="font-veri text-[9px] tracking-[0.14em] uppercase text-karbon mb-5">
              {veri.dosya_adi}
            </p>
            <pre className="font-govde text-[13.5px] leading-[1.85] whitespace-pre-wrap break-words text-murekkep">
              {parcalar?.map((p, i) =>
                p.etiket ? (
                  <mark
                    key={i}
                    onMouseEnter={() => setVurgulu(p.etiket!)}
                    onMouseLeave={() => setVurgulu(null)}
                    title={p.etiket}
                    className={
                      "rounded-xs px-0.5 -mx-0.5 transition-colors cursor-default " +
                      (vurgulu === p.etiket
                        ? "bg-havale text-yaprak"
                        : "bg-havale-soluk text-murekkep")
                    }
                  >
                    {p.metin}
                  </mark>
                ) : (
                  <span key={i}>{p.metin}</span>
                ),
              )}
            </pre>
          </div>

          <aside className="border-t xl:border-t-0 xl:border-l border-tel px-4 py-5">
            <p className="font-veri text-[9px] tracking-[0.14em] uppercase text-karbon">
              Çıkarılan alanlar
            </p>
            <p className="mt-1 font-veri text-[9.5px] text-karbon leading-snug">
              İşaretli olanlar metinde birebir geçiyor
            </p>

            {(["ustveri", "varlik"] as const).map((grup) => {
              const grupKayitlari = kayitlar.filter((k) => k.tur === grup)
              if (grupKayitlari.length === 0) return null
              return (
                <div key={grup} className="mt-4">
                  <p className="font-veri text-[8.5px] tracking-[0.14em] uppercase text-tel-koyu border-b border-tel pb-1">
                    {grup === "ustveri" ? "Üstveri alanları" : "İçerikten çıkarılan varlıklar"}
                  </p>
                  <ul className="mt-3 flex flex-col gap-3">
                    {grupKayitlari.map((k, i) => {
                      const bulundu = !!k.kanit && veri.metin.includes(k.kanit)
                      const acildi = k.sira != null && k.sira in acilan
                      return (
                        <li
                          key={i}
                          onMouseEnter={() => bulundu && setVurgulu(k.etiket)}
                          onMouseLeave={() => setVurgulu(null)}
                          className={
                            "border-l-2 pl-2.5 transition-colors " +
                            (bulundu ? "border-havale" : "border-tel-koyu")
                          }
                        >
                          <div className="flex items-baseline gap-1.5 flex-wrap">
                            <span className="font-veri text-[9px] tracking-[0.1em] uppercase text-karbon">
                              {k.etiket}
                            </span>
                            {k.yontem && (
                              <span
                                className={
                                  "font-veri text-[8.5px] tracking-[0.08em] px-1 rounded-xs " +
                                  (k.yontem === "regex"
                                    ? "bg-muhur text-yaprak"
                                    : "border border-tel-koyu text-karbon")
                                }
                              >
                                {YONTEM_ETIKET[k.yontem] ?? k.yontem}
                              </span>
                            )}
                            {k.pii && !acildi && <KilitRozeti />}
                            <span className="ml-auto font-veri text-[9.5px] text-karbon tabular-nums">
                              {guvenYaz(k.guven)}
                            </span>
                          </div>

                          <p className="mt-0.5 font-govde text-[13px] leading-snug break-words">
                            {k.deger}
                          </p>

                          {k.pii && !acildi && (
                            <button
                              type="button"
                              onClick={() => void acmaDene(k.sira!)}
                              className="mt-1 font-veri text-[9.5px] text-havale underline underline-offset-2
                                         hover:text-murekkep focus-visible:outline-2
                                         focus-visible:outline-offset-2 focus-visible:outline-murekkep"
                            >
                              maskeyi kaldır · işlem günlüğüne yazılır
                            </button>
                          )}
                          {acildi && (
                            <p className="mt-0.5 font-veri text-[9px] text-kase">
                              açıldı · günlüğe yazıldı
                            </p>
                          )}
                          {!bulundu && !k.pii && (
                            <p className="mt-0.5 font-veri text-[9px] text-karbon">
                              metinde birebir geçmiyor · çıkarım
                            </p>
                          )}
                        </li>
                      )
                    })}
                  </ul>
                </div>
              )
            })}
          </aside>
        </div>
      )}
    </div>
  )
}
