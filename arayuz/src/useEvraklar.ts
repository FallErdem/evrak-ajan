import { useCallback, useEffect, useRef, useState } from "react"
import type {
  Birim,
  EksikBilgiTalebi,
  Evrak,
  EvrakOzeti,
  HamVarlik,
  KararGovdesi,
  KararYaniti,
} from "./tipler"
import { getir, gonder } from "./ortak"

const YENILEME_MS = 5000

export function useEvraklar(rolAnahtari: string) {
  const [evraklar, setEvraklar] = useState<EvrakOzeti[]>([])
  const [birimler, setBirimler] = useState<Birim[]>([])
  const [ilkYukleme, setIlkYukleme] = useState(true)
  const [hata, setHata] = useState<string | null>(null)
  const [detay, setDetay] = useState<Evrak | null>(null)
  const seciliRef = useRef<string | null>(null)

  const listeyiCek = useCallback(async () => {
    try {
      setEvraklar(await getir<EvrakOzeti[]>("/api/evrak"))
      setHata(null)
    } catch (e) {
      setHata(
        e instanceof Error
          ? `${e.message} — sunucu 8000 portunda çalışıyor mu?`
          : "Sunucuya ulaşılamıyor",
      )
    } finally {
      setIlkYukleme(false)
    }
  }, [])

  const detayiCek = useCallback(async (evrakId: string) => {
    try {
      const veri = await getir<Evrak>(`/api/evrak/${evrakId}`)
      // Yavaş yanıt geldiğinde başka evrağa geçilmiş olabilir; eskiyi yazma.
      if (seciliRef.current === evrakId) setDetay(veri)
    } catch {
      setHata("Evrak ayrıntısı alınamadı.")
    }
  }, [])

  const sec = useCallback(
    (evrakId: string | null) => {
      seciliRef.current = evrakId
      if (evrakId) void detayiCek(evrakId)
      else setDetay(null)
    },
    [detayiCek],
  )

  const kararVer = useCallback(
    async (evrakId: string, govde: KararGovdesi) => {
      const sonuc = await gonder<KararYaniti>(`/api/evrak/${evrakId}/karar`, govde)
      await listeyiCek()
      await detayiCek(evrakId)
      return sonuc
    },
    [listeyiCek, detayiCek],
  )

  /** Yazıyı üretir ama göndermez (sözleşme 8.2). */
  const eksikBilgiOnizle = useCallback(
    (evrakId: string, sorular: string[]) =>
      gonder<EksikBilgiTalebi>(`/api/evrak/${evrakId}/eksik_bilgi_onizleme`, { sorular }),
    [],
  )

  /** Kişisel verinin maskesiz hâli. Sunucu her çağrıyı günlüğe yazar. */
  const hamVarlik = useCallback(
    async (evrakId: string, sira: number) => {
      const veri = await getir<HamVarlik>(`/api/evrak/${evrakId}/varlik/${sira}/ham`)
      await detayiCek(evrakId) // günlüğe düşen kaydı hemen göster
      return veri
    },
    [detayiCek],
  )

  // Rol değişince liste yeniden süzülür — süzme sunucuda yapılıyor.
  useEffect(() => {
    void listeyiCek()
    if (seciliRef.current) void detayiCek(seciliRef.current)
  }, [rolAnahtari, listeyiCek, detayiCek])

  useEffect(() => {
    getir<Birim[]>("/api/birimler")
      .then(setBirimler)
      .catch(() => setBirimler([]))
  }, [])

  useEffect(() => {
    const z = setInterval(() => {
      void listeyiCek()
      if (seciliRef.current) void detayiCek(seciliRef.current)
    }, YENILEME_MS)
    return () => clearInterval(z)
  }, [listeyiCek, detayiCek])

  return {
    evraklar,
    birimler,
    ilkYukleme,
    hata,
    detay,
    sec,
    kararVer,
    eksikBilgiOnizle,
    hamVarlik,
    yenile: listeyiCek,
  }
}
