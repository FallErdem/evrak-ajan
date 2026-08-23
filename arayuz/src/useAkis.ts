import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import type { DugumKaydi, Durum, KutuDurumu, Olay } from "./tipler"
import { akisAdresi, dosyaGonder } from "./ortak"

// SSE tek gerçek kaynak değil: bitmiş koşu detaydan da çizilebilir.
// Bağlanan istemci önce anlik_goruntu alır (sözleşme 6.1), sonra canlı akar.
// Olay tamponlama ve yeniden oynatma yoktur.

export function useAkis() {
  const [kayitlar, setKayitlar] = useState<DugumKaydi[]>([])
  const [duraklayan, setDuraklayan] = useState<Set<number>>(new Set())
  const [olaylar, setOlaylar] = useState<Olay[]>([])
  const [durum, setDurum] = useState<Durum | null>(null)
  const [toplamMs, setToplamMs] = useState<number | null>(null)
  const [evrakId, setEvrakId] = useState<string | null>(null)
  const [dosyaAdi, setDosyaAdi] = useState<string | null>(null)
  const [yukleniyor, setYukleniyor] = useState(false)
  const [hata, setHata] = useState<string | null>(null)

  // Paralel koşan adımların her biri kendi sayacını taşır (sözleşme 6.5).
  const [baslangiclar, setBaslangiclar] = useState<Record<number, number>>({})
  const [aktifSureler, setAktifSureler] = useState<Record<number, number>>({})

  const esRef = useRef<EventSource | null>(null)

  // ---- canlı sayaçlar ----------------------------------------------------
  useEffect(() => {
    if (Object.keys(baslangiclar).length === 0) {
      setAktifSureler({})
      return
    }
    const guncelle = () => {
      const simdi = Date.now()
      setAktifSureler(
        Object.fromEntries(
          Object.entries(baslangiclar).map(([no, bas]) => [Number(no), simdi - bas]),
        ),
      )
    }
    guncelle()
    const z = setInterval(guncelle, 100)
    return () => clearInterval(z)
  }, [baslangiclar])

  useEffect(() => () => esRef.current?.close(), [])

  const sayacAc = useCallback((no: number) => {
    setBaslangiclar((b) => ({ ...b, [no]: Date.now() }))
  }, [])

  const sayacKapat = useCallback((no: number) => {
    setBaslangiclar((b) => {
      if (!(no in b)) return b
      const yeni = { ...b }
      delete yeni[no]
      return yeni
    })
  }, [])

  /** Kaydı ekler veya günceller. Her tur ayrı kayıttır (sözleşme 5.6.2). */
  const kayitYaz = useCallback((no: number, turNo: number, alanlar: Partial<DugumKaydi>) => {
    setKayitlar((eski) => {
      const i = eski.findIndex((k) => k.no === no && k.tur_no === turNo)
      if (i >= 0) {
        const yeni = [...eski]
        yeni[i] = { ...yeni[i], ...alanlar }
        return yeni
      }
      return [
        ...eski,
        {
          no,
          ad: "",
          tur_no: turNo,
          durum: "calisiyor",
          sure_ms: null,
          guven: null,
          gerekce: null,
          cikti: null,
          ...alanlar,
        },
      ]
    })
  }, [])

  // ---- olay işleme -------------------------------------------------------
  const olayIsle = useCallback(
    (o: Olay) => {
      setOlaylar((eski) => [...eski, o])

      switch (o.tur) {
        case "anlik_goruntu": {
          const gelen = o.dugum_kayitlari ?? []
          setKayitlar(gelen)
          setDurum(o.durum ?? null)
          setDuraklayan(new Set())
          if (o.canli === false) setToplamMs(o.toplam_ms ?? null)
          const simdi = Date.now()
          setBaslangiclar(
            Object.fromEntries(
              gelen.filter((k) => k.durum === "calisiyor").map((k) => [k.no, simdi]),
            ),
          )
          break
        }

        case "dugum_basladi": {
          const no = o.dugum!
          kayitYaz(no, o.tur_no ?? 1, { ad: o.dugum_adi ?? "", durum: "calisiyor" })
          setDuraklayan((d) => {
            if (!d.has(no)) return d
            const y = new Set(d)
            y.delete(no)
            return y
          })
          sayacAc(no)
          break
        }

        case "dugum_tekrar": {
          const no = o.dugum!
          kayitYaz(no, o.tur_no ?? 2, { ad: o.dugum_adi ?? "", durum: "calisiyor" })
          sayacAc(no)
          break
        }

        case "dugum_bitti": {
          const no = o.dugum!
          kayitYaz(no, o.tur_no ?? 1, {
            ad: o.dugum_adi ?? "",
            durum: "tamam",
            sure_ms: o.sure_ms ?? null,
            guven: o.guven ?? null,
            gerekce: o.gerekce ?? null,
            cikti: o.cikti ?? null,
          })
          sayacKapat(no)
          break
        }

        case "dugum_duraklatildi": {
          // Üslup denetleyici ihlal buldu, taslağı geri gönderdi; kendisi bekliyor.
          const no = o.dugum!
          kayitYaz(no, o.tur_no ?? 1, {
            ad: o.dugum_adi ?? "",
            durum: "tamam",
            sure_ms: o.sure_ms ?? null,
            gerekce: o.gerekce ?? null,
          })
          setDuraklayan((d) => new Set(d).add(no))
          sayacKapat(no)
          break
        }

        case "hata": {
          const no = o.dugum
          if (no) {
            kayitYaz(no, o.tur_no ?? 1, { durum: "hata", gerekce: o.hata ?? null })
            sayacKapat(no)
          }
          setHata(o.hata ?? "Koşu hatası")
          break
        }

        case "durum_degisti":
          setDurum(o.durum ?? null)
          break

        case "akis_bitti":
          setDurum(o.durum ?? null)
          setToplamMs(o.toplam_ms ?? null)
          setBaslangiclar({})
          esRef.current?.close()
          esRef.current = null
          break
      }
    },
    [kayitYaz, sayacAc, sayacKapat],
  )

  // ---- bağlan ------------------------------------------------------------
  const baglan = useCallback(
    (id: string) => {
      esRef.current?.close()
      const es = new EventSource(akisAdresi(id))
      esRef.current = es
      es.onmessage = (e) => {
        try {
          olayIsle(JSON.parse(e.data) as Olay)
        } catch {
          /* bozuk satırı yut */
        }
      }
      es.onerror = () => {
        if (es.readyState === EventSource.CLOSED) return
        setHata("Akış bağlantısı koptu")
        es.close()
      }
    },
    [olayIsle],
  )

  const sifirla = useCallback(() => {
    esRef.current?.close()
    esRef.current = null
    setKayitlar([])
    setDuraklayan(new Set())
    setOlaylar([])
    setDurum(null)
    setToplamMs(null)
    setHata(null)
    setBaslangiclar({})
    setAktifSureler({})
  }, [])

  /** Var olan bir evrağın akışını izler; yükleme yapmaz. */
  const izle = useCallback(
    (id: string, ad?: string) => {
      sifirla()
      setEvrakId(id)
      setDosyaAdi(ad ?? null)
      baglan(id)
    },
    [baglan, sifirla],
  )

  const yukle = useCallback(
    async (dosya: File) => {
      sifirla()
      setYukleniyor(true)
      try {
        const veri = await dosyaGonder<{ evrak_id: string; durum: Durum }>(
          "/api/evrak",
          dosya,
        )
        setEvrakId(veri.evrak_id)
        setDosyaAdi(dosya.name)
        setDurum(veri.durum)
        baglan(veri.evrak_id)
      } catch (e) {
        setHata(
          e instanceof Error
            ? `${e.message} — sunucu 8000 portunda çalışıyor mu?`
            : "Yükleme başarısız",
        )
      } finally {
        setYukleniyor(false)
      }
    },
    [baglan, sifirla],
  )

  // ---- türetilenler ------------------------------------------------------
  const kutuDurumlari = useMemo(() => {
    const d: Record<number, KutuDurumu> = {}
    for (const k of kayitlar) {
      const mevcut = d[k.no]
      // Son tur belirleyicidir; çalışan bir tur varsa o kazanır.
      if (k.durum === "calisiyor" || mevcut === undefined || mevcut === "tamam") {
        d[k.no] = k.durum
      }
    }
    for (const no of duraklayan) {
      if (d[no] !== "calisiyor") d[no] = "duraklatildi"
    }
    return d
  }, [kayitlar, duraklayan])

  const sureler = useMemo(() => {
    const s: Record<number, number> = {}
    for (const k of kayitlar) s[k.no] = (s[k.no] ?? 0) + (k.sure_ms ?? 0)
    return s
  }, [kayitlar])

  const turSayilari = useMemo(() => {
    const t: Record<number, number> = {}
    for (const k of kayitlar) t[k.no] = Math.max(t[k.no] ?? 1, k.tur_no)
    return t
  }, [kayitlar])

  /** Bir adımın son turunun kaydı — yan panel bunu gösterir. */
  const sonKayit = useCallback(
    (no: number): DugumKaydi | null => {
      const kendi = kayitlar.filter((k) => k.no === no)
      if (kendi.length === 0) return null
      return kendi.reduce((a, b) => (b.tur_no >= a.tur_no ? b : a))
    },
    [kayitlar],
  )

  const bitenSayisi = useMemo(
    () => Object.values(kutuDurumlari).filter((d) => d === "tamam").length,
    [kutuDurumlari],
  )

  return {
    yukle,
    izle,
    sifirla,
    yukleniyor,
    evrakId,
    dosyaAdi,
    kayitlar,
    kutuDurumlari,
    sureler,
    turSayilari,
    aktifSureler,
    sonKayit,
    bitenSayisi,
    olaylar,
    durum,
    toplamMs,
    hata,
  }
}
