import { useEffect, useMemo, useState } from "react"
import type { DugumTablosu, DugumTanimi } from "./tipler"
import { getir } from "./ortak"

// Düğüm tablosu arayüzde sabit tutulmaz; /api/dugumler'den gelir (sözleşme 2.5).
// Parça 4'te adım sayısı değişirse arayüz sürümü gerekmez.

/** Bir bileşen çerçevesi: aynı `bilesen` değerini taşıyan ardışık adımlar. */
export type BilesenKusagi = {
  bilesen: number
  bilesen_adi: string
  ajan: string | null
  /** Aynı `satir` = yan yana çizilir, eş zamanlı koşar. */
  satirlar: DugumTanimi[][]
}

/** Adımları bileşen → satır olarak gruplar. Eşleme tablosu tutulmaz, veriden türer. */
export function kusaklariKur(dugumler: DugumTanimi[]): BilesenKusagi[] {
  const kusaklar: BilesenKusagi[] = []
  for (const d of [...dugumler].sort((a, b) => a.no - b.no)) {
    let kusak = kusaklar.at(-1)
    if (!kusak || kusak.bilesen !== d.bilesen) {
      kusak = {
        bilesen: d.bilesen,
        bilesen_adi: d.bilesen_adi,
        ajan: d.ajan,
        satirlar: [],
      }
      kusaklar.push(kusak)
    }
    const sonSatir = kusak.satirlar.at(-1)
    if (sonSatir && sonSatir[0].satir === d.satir) sonSatir.push(d)
    else kusak.satirlar.push([d])
  }
  return kusaklar
}

export function useDugumler() {
  const [tablo, setTablo] = useState<DugumTablosu | null>(null)
  const [hata, setHata] = useState<string | null>(null)

  useEffect(() => {
    getir<DugumTablosu>("/api/dugumler")
      .then(setTablo)
      .catch((e) => setHata(e instanceof Error ? e.message : "Düğüm tablosu alınamadı"))
  }, [])

  const dugumler = useMemo(() => tablo?.dugumler ?? [], [tablo])
  const harita = useMemo(
    () => Object.fromEntries(dugumler.map((d) => [d.no, d])) as Record<number, DugumTanimi>,
    [dugumler],
  )
  const kusaklar = useMemo(() => kusaklariKur(dugumler), [dugumler])

  return {
    dugumler,
    harita,
    kusaklar,
    paralelGruplar: tablo?.paralel_gruplar ?? [],
    hazir: tablo !== null,
    hata,
  }
}
