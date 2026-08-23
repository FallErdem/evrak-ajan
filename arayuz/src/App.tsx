import { useEffect, useMemo, useState } from "react"
import AkisEkrani from "./AkisEkrani"
import IstatistikEkrani from "./IstatistikEkrani"
import { useAkis } from "./useAkis"
import KuyrukEkrani from "./KuyrukEkrani"
import { ROLLER, ROL_HARITASI, type Birim, type Oturum, type RolKodu } from "./roller"
import { getir, oturumuAyarla } from "./ortak"

type Ekran = "akis" | "kuyruk" | "istatistik"

const EKRANLAR: { kod: Ekran; ad: string; yetkiGerekli?: boolean }[] = [
  { kod: "akis", ad: "Akış İzleme" },
  { kod: "kuyruk", ad: "Onay Kuyruğu" },
  // İstatistik yalnızca yöneticide; roller.ts'teki yetki matrisiyle uyumlu.
  { kod: "istatistik", ad: "İstatistik ve Denetim", yetkiGerekli: true },
]

const VARSAYILAN_BIRIM = "ortaogretim_sb"

/**
 * Arayüzün beklediği sunucu sürümü. sahte_sunucu.py içindeki SURUM ile aynı olmalı.
 * Uyuşmazsa ekranın üstünde uyarı çıkar — eski sunucuyla saatlerce hata aramayalım.
 */
const BEKLENEN_SURUM = "2026-08-18-h"

type SurumDurumu =
  | { hal: "kontrol" }
  | { hal: "uygun" }
  | { hal: "eski"; bulunan: string }
  | { hal: "ulasilamiyor" }

function SurumUyarisi({ durum }: { durum: SurumDurumu }) {
  if (durum.hal === "uygun" || durum.hal === "kontrol") return null

  return (
    <div className="border-b border-kase bg-kase-soluk">
      <div className="mx-auto max-w-[1400px] px-6 py-2.5 flex items-start gap-3">
        <span className="font-veri text-[9px] tracking-[0.12em] uppercase text-kase border border-kase rounded-xs px-1.5 py-px shrink-0 mt-0.5">
          {durum.hal === "eski" ? "sunucu eski" : "sunucu yok"}
        </span>
        <p className="font-govde text-[13.5px] text-kase leading-relaxed">
          {durum.hal === "eski" ? (
            <>
              Çalışan <code className="font-veri text-[12px]">sahte_sunucu.py</code> sürümü{" "}
              <strong className="font-semibold">{durum.bulunan}</strong>, arayüz{" "}
              <strong className="font-semibold">{BEKLENEN_SURUM}</strong> bekliyor. Yeni dosyayı{" "}
              <code className="font-veri text-[12px]">ui\</code> klasörüne kopyalayıp uvicorn'u
              yeniden başlatın; aksi hâlde bazı işlemler "bilinmeyen işlem" hatası verir.
            </>
          ) : (
            <>
              Sunucuya ulaşılamıyor. <code className="font-veri text-[12px]">uvicorn
              sahte_sunucu:app --reload --port 8000</code> çalışıyor mu?
            </>
          )}
        </p>
      </div>
    </div>
  )
}

export default function App() {
  const [ekran, setEkran] = useState<Ekran>("akis")
  const [rolKodu, setRolKodu] = useState<RolKodu>("birim_sorumlusu")
  const [birimKodu, setBirimKodu] = useState<string>(VARSAYILAN_BIRIM)
  const [birimler, setBirimler] = useState<Birim[]>([])
  // Akış durumu kabukta tutulur: kuyruktan bir evrağın koşusu açılabilsin ve
  // sekme değişince kaybolmasın diye.
  const akis = useAkis()
  const [surum, setSurum] = useState<SurumDurumu>({ hal: "kontrol" })

  useEffect(() => {
    getir<Birim[]>("/api/birimler")
      .then(setBirimler)
      .catch(() => setBirimler([]))

    getir<{ surum?: string }>("/api/surum")
      .then((v) =>
        setSurum(
          v.surum === BEKLENEN_SURUM
            ? { hal: "uygun" }
            : { hal: "eski", bulunan: v.surum ?? "bilinmiyor" },
        ),
      )
      .catch(() => {
        getir("/api/evrak")
          .then(() => setSurum({ hal: "eski", bulunan: "sürüm damgası yok" }))
          .catch(() => setSurum({ hal: "ulasilamiyor" }))
      })
  }, [])

  const rol = ROL_HARITASI[rolKodu]

  // Yetkisi olmayan bir role geçilirse istatistik ekranında takılı kalmasın.
  useEffect(() => {
    if (ekran === "istatistik" && !rol.yetkiler.istatistikGorur) setEkran("kuyruk")
  }, [ekran, rol])

  const oturum: Oturum = useMemo(
    () => ({ rol, birimKodu: rol.birimeBagli ? birimKodu : null }),
    [rol, birimKodu],
  )

  // X-Rol / X-Birim başlıkları: süzme ve maskeleme sunucuda buna göre yapılır.
  // Render sırasında ayarlanır ki alt bileşenlerin ilk isteği doğru rolle gitsin.
  oturumuAyarla(oturum.rol.kod, oturum.birimKodu)

  const birimAdi = birimler.find((b) => b.kod === birimKodu)?.ad

  return (
    <div className="min-h-screen bg-kagit">
      <SurumUyarisi durum={surum} />
      <header className="border-b border-tel-koyu bg-yaprak">
        <div className="mx-auto max-w-[1400px] px-6 pt-4 flex items-start gap-6">
          <div className="min-w-0">
            <p className="font-veri text-[9px] tracking-[0.18em] uppercase text-karbon">
              Kamu evrak ve yazışma süreçleri · çok ajanlı destek sistemi
            </p>
            <h1 className="mt-1 font-display font-bold text-[22px] tracking-[-0.02em]">
              Evrak Akış İzleme
            </h1>
          </div>

          {/* ---- rol seçici ---- */}
          <div className="ml-auto flex items-end gap-3 shrink-0">
            <label className="flex flex-col gap-1">
              <span className="font-veri text-[9px] tracking-[0.12em] uppercase text-karbon">
                Oturum
              </span>
              <select
                value={rolKodu}
                onChange={(e) => setRolKodu(e.target.value as RolKodu)}
                className="font-display text-[13px] px-3 py-1.5 rounded-sm border border-tel-koyu bg-kagit
                           focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-murekkep"
              >
                {ROLLER.map((r) => (
                  <option key={r.kod} value={r.kod}>
                    {r.ad}
                  </option>
                ))}
              </select>
            </label>

            {rol.birimeBagli && (
              <label className="flex flex-col gap-1">
                <span className="font-veri text-[9px] tracking-[0.12em] uppercase text-karbon">
                  Birim
                </span>
                <select
                  value={birimKodu}
                  onChange={(e) => setBirimKodu(e.target.value)}
                  className="font-display text-[13px] px-3 py-1.5 rounded-sm border border-tel-koyu bg-kagit max-w-[260px]
                             focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-murekkep"
                >
                  {[...new Set(birimler.map((b) => b.kurum))].map((kurum) => (
                    <optgroup key={kurum} label={kurum}>
                      {birimler
                        .filter((b) => b.kurum === kurum && b.hedef_olabilir)
                        .map((b) => (
                          <option key={b.kod} value={b.kod}>
                            {b.seviye === 0 ? b.ad : `— ${b.ad}`}
                          </option>
                        ))}
                    </optgroup>
                  ))}
                </select>
              </label>
            )}
          </div>
        </div>

        {/* ---- kimlik satırı ---- */}
        <div className="mx-auto max-w-[1400px] px-6 pt-2 flex items-center gap-3">
          <span className="font-veri text-[10px] text-murekkep-orta">
            {rol.ad}
            {rol.birimeBagli && birimAdi && ` · ${birimAdi}`}
          </span>
          {!rol.yetkiler.onaylayabilir && (
            <span className="font-veri text-[9px] tracking-[0.1em] uppercase text-karbon border border-tel-koyu rounded-xs px-1.5 py-px">
              onay yetkisi yok
            </span>
          )}
          <span className="font-veri text-[10px] text-karbon ml-auto hidden md:inline">
            {rol.aciklama}
          </span>
        </div>

        {/* ---- sekmeler ---- */}
        <nav className="mx-auto max-w-[1400px] px-6 mt-3 flex gap-6" aria-label="Ekranlar">
          {EKRANLAR.filter((e) => !e.yetkiGerekli || rol.yetkiler.istatistikGorur).map((e) => {
            const etkin = ekran === e.kod
            return (
              <button
                key={e.kod}
                type="button"
                onClick={() => setEkran(e.kod)}
                aria-current={etkin ? "page" : undefined}
                className={
                  "relative font-display text-[13px] pb-2.5 transition-colors " +
                  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-murekkep " +
                  (etkin
                    ? "font-semibold text-murekkep"
                    : "text-karbon hover:text-murekkep-orta")
                }
              >
                {e.ad}
                {etkin && (
                  <span
                    aria-hidden
                    className="absolute left-0 right-0 -bottom-px h-[2px] bg-kase"
                  />
                )}
              </button>
            )
          })}
        </nav>
      </header>

      {/*
        İki ekran da bağlı kalır, etkin olmayan gizlenir.
        Sökersek akış ekranının durumu ve SSE bağlantısı yok olur; sekmeden
        dönünce koşu sıfırlanmış görünür. Gizleyerek arka planda devam eder.
      */}
      <div className={ekran === "akis" ? "" : "hidden"}>
        <AkisEkrani akis={akis} />
      </div>
      <div className={ekran === "kuyruk" ? "" : "hidden"}>
        <KuyrukEkrani
          oturum={oturum}
          onAkisiGor={(id, ad) => {
            akis.izle(id, ad)
            setEkran("akis")
          }}
        />
      </div>
      {rol.yetkiler.istatistikGorur && (
        <div className={ekran === "istatistik" ? "" : "hidden"}>
          <IstatistikEkrani />
        </div>
      )}
    </div>
  )
}
