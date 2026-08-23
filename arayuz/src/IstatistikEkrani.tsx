import { useEffect, useMemo, useState } from "react"
import type { EksikKatman, EksikOnem, Istatistik, IstatistikDolu, Motor } from "./tipler"
import {
  BELGE_TURU_ETIKET,
  BolumBasligi,
  DURUM_ETIKET,
  KATMAN_ETIKET,
  MOTOR_ADI,
  MotorRozeti,
  ONEM_ETIKET,
  getir,
  guvenYaz,
  ms,
  sn,
  yuzde,
} from "./ortak"

// Bu ekran bir SaaS panosu değil, kurum faaliyet cetveli gibi kurgulandı:
// kâğıt zemin, ince çizgiler, tabular rakamlar. Renk yalnızca anlam taşıdığında.
//
// Her rakamın altında ne anlama geldiği yazılı — jüri "peki bu ne demek"
// diye sormadan cevabı görsün.

const tamsayi = (x: number) => Math.round(x).toLocaleString("tr-TR")

// ---------------------------------------------------------------------------
// Küçük parçalar
// ---------------------------------------------------------------------------

function Rakam({
  deger,
  etiket,
  yorum,
  vurgu,
}: {
  deger: string
  etiket: string
  yorum: string
  vurgu?: "iyi" | "dikkat" | "notr"
}) {
  const renk =
    vurgu === "iyi" ? "text-muhur" : vurgu === "dikkat" ? "text-kase" : "text-murekkep"
  return (
    <div className="px-5 py-5">
      <p className="font-veri text-[9px] tracking-[0.14em] uppercase text-karbon">{etiket}</p>
      <p
        className={
          "mt-1.5 font-display font-bold text-[34px] leading-none tracking-[-0.03em] tabular-nums " +
          renk
        }
      >
        {deger}
      </p>
      <p className="mt-2 font-govde text-[12.5px] leading-snug text-murekkep-orta">{yorum}</p>
    </div>
  )
}

function Cubuk({
  oran,
  renk = "bg-murekkep",
  yukseklik = "h-1.5",
}: {
  oran: number
  renk?: string
  yukseklik?: string
}) {
  return (
    <div className={"w-full rounded-xs bg-tel overflow-hidden " + yukseklik}>
      <div
        className={"h-full rounded-xs " + renk}
        style={{ width: `${Math.max(0, Math.min(1, oran)) * 100}%` }}
      />
    </div>
  )
}

function Kaydirac({
  etiket,
  deger,
  min,
  max,
  adim,
  birim,
  onDegisti,
}: {
  etiket: string
  deger: number
  min: number
  max: number
  adim: number
  birim: string
  onDegisti: (v: number) => void
}) {
  return (
    <label className="block">
      <span className="flex items-baseline justify-between">
        <span className="font-veri text-[9px] tracking-[0.12em] uppercase text-karbon">
          {etiket}
        </span>
        <span className="font-veri text-[13px] tabular-nums">
          {deger.toLocaleString("tr-TR")} {birim}
        </span>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={adim}
        value={deger}
        onChange={(e) => onDegisti(Number(e.target.value))}
        className="mt-2 w-full accent-kase"
      />
    </label>
  )
}

function Bolum({
  baslik,
  aciklama,
  sag,
  children,
}: {
  baslik: string
  aciklama?: string
  sag?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <section className="border border-tel rounded-sm bg-yaprak">
      <div className="px-5 py-3 border-b border-tel">
        <BolumBasligi sag={sag}>{baslik}</BolumBasligi>
        {aciklama && (
          <p className="mt-1.5 font-govde text-[13px] leading-snug text-murekkep-orta">
            {aciklama}
          </p>
        )}
      </div>
      <div className="px-5 py-4">{children}</div>
    </section>
  )
}

function Cetvel({ satirlar }: { satirlar: { ad: string; adet: number }[] }) {
  const enBuyuk = Math.max(1, ...satirlar.map((s) => s.adet))
  return (
    <ul className="flex flex-col gap-2">
      {satirlar.map((s) => (
        <li key={s.ad} className="flex items-center gap-3">
          <span className="font-govde text-[13.5px] w-44 shrink-0 truncate">{s.ad}</span>
          <span className="flex-1">
            <Cubuk oran={s.adet / enBuyuk} yukseklik="h-1" renk="bg-murekkep-orta" />
          </span>
          <span className="font-veri text-[11px] tabular-nums text-karbon w-6 text-right">
            {s.adet}
          </span>
        </li>
      ))}
    </ul>
  )
}

// ---------------------------------------------------------------------------
// Güven dağılımı + eşik simülatörü
// ---------------------------------------------------------------------------

function GuvenDagilimi({ skorlar, varsayilanEsik }: { skorlar: number[]; varsayilanEsik: number }) {
  const [esik, setEsik] = useState(varsayilanEsik)

  const kovalar = useMemo(() => {
    const sinirlar = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    return sinirlar.slice(0, -1).map((alt, i) => {
      const ust = sinirlar[i + 1]
      const adet = skorlar.filter((s) => s >= alt && (ust === 1 ? s <= ust : s < ust)).length
      return { alt, ust, adet }
    })
  }, [skorlar])

  const enBuyuk = Math.max(1, ...kovalar.map((k) => k.adet))
  const otomatik = skorlar.filter((s) => s >= esik).length
  const oran = skorlar.length ? otomatik / skorlar.length : 0

  return (
    <div>
      <div className="flex items-end gap-2 h-32">
        {kovalar.map((k) => {
          const esikUstu = k.alt >= esik
          return (
            <div key={k.alt} className="flex-1 flex flex-col items-center justify-end h-full">
              <span className="font-veri text-[10px] tabular-nums text-karbon mb-1">
                {k.adet || ""}
              </span>
              <div
                className={
                  "w-full rounded-t-xs transition-colors " +
                  (esikUstu ? "bg-muhur" : "bg-kase")
                }
                style={{ height: `${(k.adet / enBuyuk) * 100}%`, minHeight: k.adet ? 4 : 0 }}
              />
              <span className="mt-1.5 font-veri text-[9px] text-karbon tabular-nums">
                {guvenYaz(k.alt)}
              </span>
            </div>
          )
        })}
      </div>

      <div className="mt-5 pt-4 border-t border-tel">
        <Kaydirac
          etiket="Otomatik onay eşiği"
          deger={esik}
          min={0.5}
          max={0.99}
          adim={0.01}
          birim=""
          onDegisti={setEsik}
        />
        <div className="mt-4 grid grid-cols-2 gap-4">
          <div>
            <p className="font-veri text-[9px] tracking-[0.12em] uppercase text-karbon">
              Otomatik onay
            </p>
            <p className="mt-1 font-display font-bold text-[24px] tabular-nums text-muhur">
              {yuzde(oran)}
            </p>
            <p className="font-veri text-[10px] text-karbon">
              {otomatik} / {skorlar.length} evrak
            </p>
          </div>
          <div>
            <p className="font-veri text-[9px] tracking-[0.12em] uppercase text-karbon">
              İnsan onayına düşen
            </p>
            <p className="mt-1 font-display font-bold text-[24px] tabular-nums text-kase">
              {yuzde(1 - oran)}
            </p>
            <p className="font-veri text-[10px] text-karbon">
              {skorlar.length - otomatik} / {skorlar.length} evrak
            </p>
          </div>
        </div>
        <p className="mt-4 font-govde text-[13px] leading-relaxed text-murekkep-orta">
          Eşiği düşürmek otomasyonu artırır ama hatalı otomatik onay riskini de büyütür.
          Kamu kurumu bu ayarı kendi risk iştahına göre belirler; sistem eşiği dayatmaz.
          {esik !== varsayilanEsik && (
            <>
              {" "}
              Yürürlükteki eşik <strong className="font-semibold">{guvenYaz(varsayilanEsik)}</strong>;
              burada {guvenYaz(esik)} ile benzetim yapıyorsunuz.
            </>
          )}
        </p>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Kazanılan zaman
// ---------------------------------------------------------------------------

function KazanilanZaman({ ortalamaMs }: { ortalamaMs: number }) {
  const [gunlukEvrak, setGunlukEvrak] = useState(250)
  const [manuelDakika, setManuelDakika] = useState(18)
  const [insanPayi, setInsanPayi] = useState(40)

  const hesap = useMemo(() => {
    const sistemDk = ortalamaMs / 60000
    // İnsan onayına düşenler için gözden geçirme süresi: manuelin üçte biri.
    const gozdenGecirmeDk = (manuelDakika / 3) * (insanPayi / 100)
    const yeniDk = sistemDk + gozdenGecirmeDk
    const kazancDk = Math.max(0, manuelDakika - yeniDk)
    const gunlukSaat = (kazancDk * gunlukEvrak) / 60
    const yillikSaat = gunlukSaat * 250 // iş günü
    const personel = yillikSaat / 1760 // yıllık çalışma saati
    return { sistemDk, gozdenGecirmeDk, yeniDk, kazancDk, gunlukSaat, yillikSaat, personel }
  }, [gunlukEvrak, manuelDakika, insanPayi, ortalamaMs])

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[320px_minmax(0,1fr)] gap-8">
      <div className="flex flex-col gap-5">
        <Kaydirac
          etiket="Günlük gelen evrak"
          deger={gunlukEvrak}
          min={10}
          max={2000}
          adim={10}
          birim="adet"
          onDegisti={setGunlukEvrak}
        />
        <Kaydirac
          etiket="Manuel işlem süresi"
          deger={manuelDakika}
          min={5}
          max={60}
          adim={1}
          birim="dk"
          onDegisti={setManuelDakika}
        />
        <Kaydirac
          etiket="İnsan onayına düşen oran"
          deger={insanPayi}
          min={0}
          max={100}
          adim={5}
          birim="%"
          onDegisti={setInsanPayi}
        />
      </div>

      <div>
        <div className="grid grid-cols-2 sm:grid-cols-3 divide-x divide-tel border border-tel rounded-sm bg-kagit">
          {[
            ["Günde", `${tamsayi(hesap.gunlukSaat)} saat`],
            ["Yılda", `${tamsayi(hesap.yillikSaat)} saat`],
            ["Personel karşılığı", `${hesap.personel.toFixed(1)} kişi`],
          ].map(([b, d]) => (
            <div key={b} className="px-4 py-4">
              <p className="font-veri text-[9px] tracking-[0.12em] uppercase text-karbon">{b}</p>
              <p className="mt-1 font-display font-bold text-[20px] tabular-nums tracking-tight">
                {d}
              </p>
            </div>
          ))}
        </div>

        <div className="mt-4 border border-tel rounded-sm bg-kagit px-4 py-3">
          <p className="font-veri text-[9px] tracking-[0.12em] uppercase text-karbon">Hesap</p>
          <ul className="mt-2 flex flex-col gap-1 font-veri text-[11px] text-murekkep-orta tabular-nums">
            <li>Manuel süre · {manuelDakika} dk/evrak</li>
            <li>
              Sistem süresi · {hesap.sistemDk.toFixed(2)} dk + gözden geçirme{" "}
              {hesap.gozdenGecirmeDk.toFixed(2)} dk = {hesap.yeniDk.toFixed(2)} dk
            </li>
            <li>
              Evrak başına kazanç · {hesap.kazancDk.toFixed(2)} dk × {gunlukEvrak} evrak ={" "}
              {tamsayi(hesap.gunlukSaat)} saat/gün
            </li>
            <li>Yıl · 250 iş günü · personel yılı 1.760 saat</li>
          </ul>
        </div>

        <p className="mt-3 font-govde text-[13px] leading-relaxed text-murekkep-orta">
          Rakamlar varsayıma dayanır; kaydıraçlar kurumun kendi verisiyle ayarlanır. Sistem
          insanı devre dışı bırakmaz — onay kuyruğunda geçen süre hesaba dâhildir.
        </p>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------

export default function IstatistikEkrani() {
  const [veri, setVeri] = useState<Istatistik | null>(null)
  const [hata, setHata] = useState<string | null>(null)

  useEffect(() => {
    const cek = () =>
      getir<Istatistik>("/api/istatistik")
        .then((v) => {
          setVeri(v)
          setHata(null)
        })
        .catch((e) => setHata(e instanceof Error ? e.message : "Bilinmeyen hata"))
    void cek()
    const z = setInterval(cek, 5000)
    return () => clearInterval(z)
  }, [])

  // Sunucunun kendi mesajını gösteriyoruz; "sunucu güncel mi" hiçbir şey söylemiyordu.
  if (hata && !veri) {
    return (
      <div className="mx-auto max-w-[1400px] px-6 py-10">
        <div className="border border-kase bg-kase-soluk rounded-sm px-5 py-4">
          <p className="font-veri text-[9px] tracking-[0.14em] uppercase text-kase">
            İstatistik alınamadı
          </p>
          <p className="mt-2 font-govde text-[14px] text-kase leading-relaxed">{hata}</p>
          <ul className="mt-3 font-govde text-[13px] text-murekkep-orta leading-relaxed list-disc pl-5">
            <li>
              Sunucu 500 döndüyse <code className="font-veri text-[12px]">ui\evraklar.json</code>{" "}
              eski şemada olabilir; silip uvicorn'u yeniden başlatın.
            </li>
            <li>403 döndüyse istatistik yalnızca Kurum Yöneticisine açıktır.</li>
            <li>Bağlantı kurulamadıysa uvicorn 8000 portunda çalışmıyor olabilir.</li>
          </ul>
        </div>
      </div>
    )
  }

  if (!veri) {
    return (
      <p className="mx-auto max-w-[1400px] px-6 py-10 font-veri text-[11px] text-karbon">
        Hesaplanıyor…
      </p>
    )
  }

  if (veri.bos) {
    return (
      <div className="mx-auto max-w-[1400px] px-6 py-20 text-center">
        <p className="font-display font-bold text-[18px]">Henüz işlenmiş evrak yok</p>
        <p className="mt-2 font-govde text-[15px] text-murekkep-orta">
          Akış ekranından birkaç evrak yükleyin, ölçütler burada birikir.
        </p>
      </div>
    )
  }

  const v: IstatistikDolu = veri
  const enYavasDugum = Math.max(...v.dugum_dagilimi.map((d) => d.ortalama_ms))
  const motorToplam = Object.values(v.motor_ms).reduce((a, b) => a + b, 0) || 1
  const kuralPayi = (v.motor_ms.kural ?? 0) / motorToplam
  const paralelKazanc =
    v.sirali_toplam_ms > 0
      ? (v.sirali_toplam_ms - v.gerceklesen_toplam_ms) / v.sirali_toplam_ms
      : 0

  return (
    <div className="mx-auto max-w-[1400px] px-6 py-6 flex flex-col gap-5">
      {hata && (
        <p className="border border-havale bg-havale-soluk text-havale rounded-sm px-4 py-2.5 font-govde text-[13px]">
          Son yenileme başarısız: {hata} — aşağıdaki rakamlar en son alınan hâli gösteriyor.
        </p>
      )}

      {/* ---- ana rakamlar ---- */}
      <section className="border border-tel-koyu rounded-sm bg-yaprak">
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 divide-y sm:divide-y-0 sm:divide-x divide-tel">
          <Rakam
            deger={yuzde(v.otomatik_onay_orani)}
            etiket="Otomatik onay oranı"
            yorum="İnsana düşmeden tamamlanan evrak payı. Ticarileşme anlatısının tek rakamlık özeti."
            vurgu="iyi"
          />
          <Rakam
            deger={sn(v.ortalama_sure_ms)}
            etiket="Ortalama işlem süresi"
            yorum={`Uçtan uca, on iki düğüm. En hızlı ${sn(v.en_hizli_ms)}, en yavaş ${sn(v.en_yavas_ms)}.`}
          />
          <Rakam
            deger={yuzde(v.insan_duzeltme_orani)}
            etiket="İnsan düzeltme oranı"
            yorum="Onaycının sistemi düzelttiği evrak payı. Sistemin kendi hata payını ölçmesi."
            vurgu={v.insan_duzeltme_orani > 0.3 ? "dikkat" : "notr"}
          />
          <Rakam
            deger={String(v.bekleyen)}
            etiket="Onay bekleyen"
            yorum={
              v.kritik_eksikli > 0
                ? `${v.kritik_eksikli} evrakta açık kritik eksik var.`
                : "Kritik eksik bulunan evrak yok."
            }
            vurgu={v.kritik_eksikli > 0 ? "dikkat" : "notr"}
          />
        </div>
      </section>

      {/* ---- kazanılan zaman ---- */}
      <Bolum
        baslik="Kazanılan zaman"
        aciklama="Kurumun kendi rakamlarıyla oynatılabilir. Sistem süresi ölçülen gerçek değerdir; manuel süre ve hacim varsayımdır."
      >
        <KazanilanZaman ortalamaMs={v.ortalama_sure_ms} />
      </Bolum>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        {/* ---- güven dağılımı ---- */}
        <Bolum
          baslik="Güven dağılımı ve eşik benzetimi"
          aciklama="Eşiği kaydırarak otomasyon oranının nasıl değiştiğini görün."
          sag={
            <span className="font-veri text-[9px] text-karbon tabular-nums">
              yürürlükteki eşik {guvenYaz(v.esik)}
            </span>
          }
        >
          <GuvenDagilimi skorlar={v.guven_skorlari} varsayilanEsik={v.esik} />
        </Bolum>

        {/* ---- düğüm süreleri ---- */}
        <Bolum
          baslik="Düğüm süreleri"
          aciklama="Darboğaz nerede, hangi adım ne kadar sürüyor."
          sag={
            <span className="font-veri text-[9px] text-karbon tabular-nums">
              p95 {sn(v.p95_sure_ms)}
            </span>
          }
        >
          <ul className="flex flex-col gap-2">
            {v.dugum_dagilimi.map((d) => {
              const darbogaz = d.ortalama_ms === enYavasDugum
              return (
                <li key={d.no} className="flex items-center gap-3">
                  <span className="font-veri text-[10px] text-karbon tabular-nums w-5 shrink-0">
                    {String(d.no).padStart(2, "0")}
                  </span>
                  <span className="font-govde text-[13px] w-32 shrink-0 truncate">
                    {d.baslik}
                  </span>
                  <span className="shrink-0">
                    <MotorRozeti motor={d.motor} />
                  </span>
                  <span className="flex-1 min-w-0">
                    <Cubuk
                      oran={d.ortalama_ms / enYavasDugum}
                      yukseklik="h-1"
                      renk={darbogaz ? "bg-kase" : "bg-murekkep-orta"}
                    />
                  </span>
                  <span
                    className={
                      "font-veri text-[10.5px] tabular-nums w-16 text-right shrink-0 " +
                      (darbogaz ? "text-kase" : "text-karbon")
                    }
                  >
                    {ms(d.ortalama_ms)}
                  </span>
                </li>
              )
            })}
          </ul>

          <div className="mt-4 pt-3 border-t border-tel grid grid-cols-3 gap-3">
            {[
              ["Paralelleştirmeseydik", sn(v.sirali_toplam_ms)],
              ["Gerçekleşen", sn(v.gerceklesen_toplam_ms)],
              ["Kazanç", yuzde(paralelKazanc)],
            ].map(([b, d]) => (
              <div key={b}>
                <p className="font-veri text-[9px] tracking-[0.12em] uppercase text-karbon">
                  {b}
                </p>
                <p className="mt-0.5 font-veri text-[14px] tabular-nums">{d}</p>
              </div>
            ))}
          </div>
          <p className="mt-2 font-govde text-[12.5px] leading-snug text-murekkep-orta">
            Denetçi'nin iki adımı (eksiklik tespiti ve mevzuat getirme) birbirini beklemez;
            eş zamanlı koştukları için toplam süre bu kadar kısalıyor.
          </p>
        </Bolum>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        {/* ---- motor payı ---- */}
        <Bolum
          baslik="Zamanın nereye gittiği"
          aciklama="Her şeyi dil modeline sormuyoruz; kural motoru payı deterministik, tekrarlanabilir ve denetlenebilir kısımdır."
        >
          <div className="flex h-8 rounded-sm overflow-hidden border border-tel">
            {(["kural", "arac", "karma", "llm"] as Motor[]).map((m) => {
              const pay = (v.motor_ms[m] ?? 0) / motorToplam
              if (pay <= 0) return null
              const renk =
                m === "kural"
                  ? "bg-muhur"
                  : m === "arac"
                    ? "bg-karbon"
                    : m === "karma"
                      ? "bg-murekkep-orta"
                      : "bg-murekkep"
              return (
                <div
                  key={m}
                  className={renk + " flex items-center justify-center"}
                  style={{ width: `${pay * 100}%` }}
                  title={`${MOTOR_ADI[m]} ${yuzde(pay)}`}
                >
                  {pay > 0.12 && (
                    <span className="font-veri text-[9px] text-yaprak tabular-nums">
                      {yuzde(pay)}
                    </span>
                  )}
                </div>
              )
            })}
          </div>

          <ul className="mt-4 flex flex-col gap-2">
            {(["kural", "arac", "karma", "llm"] as Motor[]).map((m) => {
              const deger = v.motor_ms[m] ?? 0
              if (!deger) return null
              return (
                <li key={m} className="flex items-baseline gap-3">
                  <MotorRozeti motor={m} />
                  <span className="font-govde text-[13.5px]">{MOTOR_ADI[m]}</span>
                  <span className="ml-auto font-veri text-[11px] tabular-nums text-karbon">
                    {ms(deger)} · {yuzde(deger / motorToplam)}
                  </span>
                </li>
              )
            })}
          </ul>

          <p className="mt-4 font-govde text-[13px] leading-relaxed text-murekkep-orta">
            Üslup denetleyici ve güven kapısı hiç model çağırmaz; toplam sürenin{" "}
            {yuzde(kuralPayi)} kadarını oluşturur ve çıktısı her koşuda aynıdır.
          </p>
        </Bolum>

        {/* ---- yönlendirme başarımı ---- */}
        <Bolum
          baslik="Yönlendirme başarımı"
          aciklama="Onaycının hedef birimi değiştirdiği her durum kayda geçer; sistem kendi isabetini bu kayıtlardan ölçer."
          sag={
            <span className="font-veri text-[9px] text-karbon tabular-nums">
              {v.yonlendirilen} evrak
            </span>
          }
        >
          <div className="flex items-baseline gap-4">
            <span className="font-display font-bold text-[30px] tabular-nums tracking-tight text-muhur">
              {yuzde(v.yonlendirme_isabet)}
            </span>
            <span className="font-govde text-[13.5px] text-murekkep-orta">
              isabet · {v.yonlendirme_duzeltmeleri.length} düzeltme
            </span>
          </div>
          <div className="mt-3">
            <Cubuk oran={v.yonlendirme_isabet} renk="bg-muhur" />
          </div>

          {v.yonlendirme_duzeltmeleri.length === 0 ? (
            <p className="mt-4 font-govde text-[13px] text-murekkep-orta">
              Henüz düzeltme yok. Onaycı bir evrağı başka birime yönlendirirse burada listelenir.
            </p>
          ) : (
            <ul className="mt-4 flex flex-col gap-3">
              {v.yonlendirme_duzeltmeleri.map((d, i) => (
                <li key={i} className="border-l-2 border-havale pl-3">
                  <p className="font-govde text-[13.5px] leading-snug">
                    <span className="text-karbon line-through decoration-tel-koyu">{d.eski}</span>
                    <span className="mx-2 text-havale">→</span>
                    <span className="font-semibold">{d.yeni}</span>
                  </p>
                  {d.konu && (
                    <p className="mt-0.5 font-veri text-[10px] text-karbon truncate">{d.konu}</p>
                  )}
                  {d.gerekce && (
                    <p className="mt-0.5 font-govde text-[12.5px] italic text-murekkep-orta">
                      {d.gerekce}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Bolum>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        {/* ---- eksik bilgi ---- */}
        <Bolum
          baslik="Eksik bilgi tespiti"
          aciklama="Üç katman ayrı ayrı çalışır: zorunlu alan şeması, mevzuatın istediği belgeler, ve kural dışı belirsizlikler."
          sag={
            <span className="font-veri text-[9px] text-karbon tabular-nums">
              {v.eksik_giderilen}/{v.eksik_toplam} giderildi
            </span>
          }
        >
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {(["sema", "kural", "mevzuat", "cikarim"] as EksikKatman[]).map((k) => (
              <div key={k}>
                <p className="font-veri text-[9px] tracking-[0.12em] uppercase text-karbon">
                  {KATMAN_ETIKET[k]}
                </p>
                <p className="mt-1 font-display font-bold text-[24px] tabular-nums">
                  {v.eksik_katman[k] ?? 0}
                </p>
              </div>
            ))}
          </div>

          <div className="mt-5 pt-4 border-t border-tel">
            <p className="font-veri text-[9px] tracking-[0.12em] uppercase text-karbon">
              Önem dağılımı
            </p>
            <ul className="mt-3 flex flex-col gap-2">
              {(["hata", "uyari", "bilgi"] as EksikOnem[]).map((o) => {
                const adet = v.eksik_onem[o] ?? 0
                const renk =
                  o === "hata" ? "bg-kase" : o === "uyari" ? "bg-havale" : "bg-karbon"
                return (
                  <li key={o} className="flex items-center gap-3">
                    <span className="font-govde text-[13.5px] w-16 shrink-0">
                      {ONEM_ETIKET[o]}
                    </span>
                    <span className="flex-1">
                      <Cubuk
                        oran={adet / Math.max(1, v.eksik_toplam)}
                        yukseklik="h-1"
                        renk={renk}
                      />
                    </span>
                    <span className="font-veri text-[11px] tabular-nums text-karbon w-6 text-right">
                      {adet}
                    </span>
                  </li>
                )
              })}
            </ul>
          </div>
        </Bolum>

        {/* ---- mevzuat eleme ---- */}
        {v.mevzuat_getirilen != null && v.mevzuat_getirilen > 0 && (
          <Bolum
            baslik="Mevzuat eleme"
            aciklama="Denetçi getirdiği her maddeyi belge metninde doğrular. Doğrulayamadığını göstermez."
            sag={
              <span className="font-veri text-[9px] text-karbon tabular-nums">
                {v.mevzuat_getirilen} öneri getirildi
              </span>
            }
          >
            <div className="grid grid-cols-2 gap-6">
              <div>
                <p className="font-veri text-[9px] tracking-[0.12em] uppercase text-muhur">
                  Doğrulandı · gösterildi
                </p>
                <p className="mt-1 font-display font-bold text-[26px] tabular-nums text-muhur">
                  {v.mevzuat_dogrulanan ?? 0}
                </p>
                <p className="mt-1 font-veri text-[10px] text-karbon">
                  ortalama benzerlik {guvenYaz(v.benzerlik_dogrulanan_ort ?? 0)}
                </p>
              </div>
              <div>
                <p className="font-veri text-[9px] tracking-[0.12em] uppercase text-kase">
                  Elendi · gösterilmedi
                </p>
                <p className="mt-1 font-display font-bold text-[26px] tabular-nums text-kase">
                  {v.mevzuat_elenen ?? 0}
                </p>
                <p className="mt-1 font-veri text-[10px] text-karbon">
                  ortalama benzerlik {guvenYaz(v.benzerlik_elenen_ort ?? 0)}
                </p>
              </div>
            </div>

            <div className="mt-4">
              <Cubuk
                oran={(v.mevzuat_dogrulanan ?? 0) / Math.max(1, v.mevzuat_getirilen)}
                renk="bg-muhur"
              />
            </div>

            <p className="mt-4 font-govde text-[13px] leading-relaxed text-murekkep-orta">
              Metinsel yakınlık tek başına yetmiyor: elenen önerilerin ortalama benzerliği{" "}
              {guvenYaz(v.benzerlik_elenen_ort ?? 0)}, yani sıfır değil. Arama onları makul
              buldu, doğrulama adımı eledi. Kullanıcıya yalnızca belgede karşılığı bulunan
              maddeler gösterilir.
            </p>
          </Bolum>
        )}

        {/* ---- üslup denetimi ---- */}
        <Bolum
          baslik="Üslup denetimi"
          aciklama="Kırk kural, tamamı deterministik. Hata düzeyinde bulgu varsa taslak en fazla iki tur geri gönderilir."
          sag={
            <span className="font-veri text-[9px] text-karbon tabular-nums">
              ilk turda geçme {yuzde(v.linter_ilk_tur_gecme)}
            </span>
          }
        >
          <Cubuk oran={v.linter_ilk_tur_gecme} renk="bg-muhur" />

          {v.linter_kurallar.length === 0 ? (
            <p className="mt-4 font-govde text-[13px] text-murekkep-orta">
              Hiçbir kural ihlali kaydedilmedi.
            </p>
          ) : (
            <ul className="mt-4 flex flex-col gap-3">
              {v.linter_kurallar.slice(0, 6).map((k) => (
                <li key={k.kural_no} className="flex gap-3">
                  <span
                    className={
                      "font-veri text-[10px] shrink-0 pt-0.5 " +
                      (k.duzey === "hata" ? "text-kase" : "text-havale")
                    }
                  >
                    {k.kural_no}
                  </span>
                  <span className="min-w-0">
                    <p className="font-govde text-[13.5px] leading-snug">{k.mesaj}</p>
                    <p className="mt-0.5 font-veri text-[10px] text-karbon">{k.mevzuat}</p>
                  </span>
                  <span className="ml-auto font-veri text-[11px] tabular-nums text-karbon shrink-0">
                    {k.adet}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Bolum>
      </div>

      {/* ---- dağılımlar ---- */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        <Bolum baslik="Belge türü">
          <Cetvel
            satirlar={Object.entries(v.belge_turu_dagilimi).map(([k, v]) => ({
              ad: BELGE_TURU_ETIKET[k] ?? k,
              adet: v,
            }))}
          />
        </Bolum>

        <Bolum baslik="Durum">
          <Cetvel
            satirlar={Object.entries(v.durum_dagilimi).map(([k, v]) => ({
              ad: DURUM_ETIKET[k] ?? k,
              adet: v,
            }))}
          />
        </Bolum>

        <Bolum baslik="Hedef birim">
          <Cetvel
            satirlar={v.birim_dagilimi
              .slice(0, 6)
              .map((b) => ({ ad: b.birim_adi, adet: b.adet }))}
          />
        </Bolum>
      </div>
    </div>
  )
}
