import { useCallback, useEffect, useState } from "react"
import type { DefterSatiri } from "./tipler"
import { getir } from "./ortak"

// Evrak kayıt defteri — gelen ve giden.
//
// Sıra numarası SUNUCUDA veriliyor ve birim başına 1'den artıyor. Arayüz
// numara üretmiyor, saymıyor, sıralamıyor: satırlar sunucudan zaten
// `sira_no` sırasında geliyor. İki taraf da sayarsa listeler ayrışır.
//
// Süzme de sunucuda: birim sorumlusu kendi defterinden başkasını göremiyor,
// `X-Birim` başlığı bunu belirliyor (ortak.tsx'teki oturum sarmalayıcısı).

const YENILEME_MS = 5000

export function useDefter(yon: "gelen" | "giden" | null, rolAnahtari: string) {
  const [satirlar, setSatirlar] = useState<DefterSatiri[]>([])
  const [ilkYukleme, setIlkYukleme] = useState(true)
  const [hata, setHata] = useState<string | null>(null)

  const cek = useCallback(async () => {
    if (!yon) return
    try {
      setSatirlar(await getir<DefterSatiri[]>(`/api/defter?yon=${yon}`))
      setHata(null)
    } catch (e) {
      // Sahte sunucuda /api/defter yok. Bunu hata olarak değil, "bu sunucu
      // defteri desteklemiyor" olarak gösteriyoruz; çevrimdışı yedekte
      // kırmızı bir bant çıkmasın.
      setSatirlar([])
      setHata(e instanceof Error ? e.message : "Defter alınamadı")
    } finally {
      setIlkYukleme(false)
    }
  }, [yon])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void cek()
  }, [cek, rolAnahtari])

  useEffect(() => {
    if (!yon) return
    const z = setInterval(() => void cek(), YENILEME_MS)
    return () => clearInterval(z)
  }, [cek, yon])

  return { satirlar, ilkYukleme, hata, yenile: cek }
}
