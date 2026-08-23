import { useEffect, useMemo, useState } from "react"
import type { EksikBilgiCevabi, EksikBilgiTalebi, EvrakOzeti } from "./tipler"
import type { Oturum } from "./roller"
import { useEvraklar } from "./useEvraklar"
import GelenEvrak from "./GelenEvrak"
import OnayPaneli from "./OnayPaneli"
import ResmiYazi from "./ResmiYazi"
import {
  ACIK_DURUMLAR,
  BELGE_TURU_ETIKET,
  BolumBasligi,
  DurumRozeti,
  GuvenCubugu,
  KATMAN_ETIKET,
  OnemRozeti,
  bekleme,
  guvenYaz,
  kalanGun,
  saat,
  sn,
  tarihGoster,
} from "./ortak"

type Sekme = "bekleyen" | "tumu"

function KuyrukSatiri({
  e,
  secili,
  onSec,
}: {
  e: EvrakOzeti
  secili: boolean
  onSec: () => void
}) {
  const kritik = e.kritik_eksik_sayisi > 0
  const dusukGuven = e.guven != null && e.esik != null && e.guven < e.esik
  const isaret = kritik ? "bg-kase" : dusukGuven ? "bg-havale" : "bg-tel-koyu"

  return (
    <button
      type="button"
      onClick={onSec}
      aria-pressed={secili}
      className={
        "relative w-full text-left pl-4 pr-3 py-3 border-b border-tel transition-colors " +
        "focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-murekkep " +
        (secili ? "bg-yaprak" : "hover:bg-yaprak/60")
      }
    >
      <span aria-hidden className={"absolute left-0 top-0 bottom-0 w-[3px] " + isaret} />
      <div className="flex items-baseline gap-2">
        <span className="font-veri text-[10px] text-karbon truncate">{e.sayi ?? "sayısız"}</span>
        <span className="ml-auto font-veri text-[9px] text-karbon tabular-nums shrink-0">
          {bekleme(e.bekleme_sn)}
        </span>
      </div>
      <p className="mt-1 font-govde text-[14px] leading-snug">{e.konu ?? e.dosya_adi}</p>
      <div className="mt-1.5 flex items-center gap-2 flex-wrap">
        <span className="font-veri text-[9px] tracking-[0.1em] uppercase text-karbon border border-tel-koyu rounded-xs px-1 py-px">
          {BELGE_TURU_ETIKET[e.belge_turu ?? ""] ?? e.belge_turu ?? "—"}
        </span>
        {e.kritik_eksik_sayisi > 0 && (
          <span className="font-veri text-[9px] tracking-[0.1em] uppercase text-kase bg-kase-soluk border border-kase rounded-xs px-1 py-px">
            {e.kritik_eksik_sayisi} kritik eksik
          </span>
        )}
        {e.duzeltme_sayisi > 0 && (
          <span className="font-veri text-[9px] tracking-[0.1em] uppercase text-havale border border-havale rounded-xs px-1 py-px">
            düzeltildi
          </span>
        )}
      </div>
      <div className="mt-2 flex items-center justify-between gap-3">
        <span className="font-veri text-[10px] text-murekkep-orta truncate">
          → {e.birim_adi ?? "—"}
        </span>
        {e.guven != null && e.esik != null && (
          <GuvenCubugu skor={e.guven} esik={e.esik} genislik={64} />
        )}
      </div>
    </button>
  )
}

// ---------------------------------------------------------------------------

function TalepKarti({
  talep,
  cevap,
  bekliyor,
  yetkili,
  onCevapGonder,
}: {
  talep: EksikBilgiTalebi
  cevap: EksikBilgiCevabi | null
  bekliyor: boolean
  yetkili: boolean
  onCevapGonder: (c: { soru: string; cevap: string }[]) => Promise<void>
}) {
  const [yaziAcik, setYaziAcik] = useState(false)
  const [formAcik, setFormAcik] = useState(false)
  const [girilen, setGirilen] = useState<Record<string, string>>({})
  const [gonderiliyor, setGonderiliyor] = useState(false)
  const [hataMesaji, setHataMesaji] = useState<string | null>(null)

  const dolu = talep.sorular.filter((q) => (girilen[q] ?? "").trim())
  const kalan = kalanGun(talep.son_tarih)

  const gonder = async () => {
    setGonderiliyor(true)
    setHataMesaji(null)
    try {
      await onCevapGonder(dolu.map((q) => ({ soru: q, cevap: girilen[q].trim() })))
      setFormAcik(false)
      setGirilen({})
    } catch (e) {
      setHataMesaji(e instanceof Error ? e.message : "Cevap işlenemedi.")
    } finally {
      setGonderiliyor(false)
    }
  }

  return (
    <div className="border border-havale rounded-sm bg-havale-soluk/40 overflow-hidden">
      <div className="px-5 py-4">
        <BolumBasligi
          sag={
            <span className="font-veri text-[9px] tracking-[0.1em] uppercase text-havale">
              gönderildi · {new Date(talep.ts * 1000).toLocaleDateString("tr-TR")}
              {talep.elle_duzenlendi && " · elle düzenlendi"}
              {bekliyor && kalan != null && ` · ${kalan} gün kaldı`}
            </span>
          }
        >
          Eksik bilgi talebi
        </BolumBasligi>

        <dl className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-y-3 gap-x-4">
          {[
            ["Kime", talep.muhatap_ad],
            ["Kanal", talep.kanal],
            ["Süre", `${talep.sure_gun} gün`],
            ["Son tarih", tarihGoster(talep.son_tarih)],
          ].map(([b, d]) => (
            <div key={b}>
              <dt className="font-veri text-[9px] tracking-[0.12em] uppercase text-karbon">{b}</dt>
              <dd className="mt-0.5 font-govde text-[13.5px] leading-snug">{d}</dd>
            </div>
          ))}
        </dl>

        <p className="mt-3 font-veri text-[10px] text-karbon leading-relaxed">
          Dayanak: {talep.dayanak}
        </p>

        <ol className="mt-4 flex flex-col gap-1.5">
          {talep.sorular.map((q, i) => (
            <li key={i} className="flex gap-2.5 font-govde text-[14px] leading-snug">
              <span className="font-veri text-[11px] text-havale shrink-0 pt-0.5">{i + 1}</span>
              <span>{q}</span>
            </li>
          ))}
        </ol>

        {cevap && (
          <div className="mt-4 border-t border-havale pt-4">
            <p className="font-veri text-[9px] tracking-[0.12em] uppercase text-muhur">
              Cevap alındı · {cevap.gonderen} ·{" "}
              {new Date(cevap.ts * 1000).toLocaleDateString("tr-TR")}
            </p>
            <ul className="mt-3 flex flex-col gap-2">
              {cevap.cevaplar.map((c, i) => (
                <li key={i} className="border-l-2 border-muhur pl-3">
                  <p className="font-veri text-[10px] text-karbon leading-snug">{c.soru}</p>
                  <p className="mt-0.5 font-govde text-[14px] leading-snug">{c.cevap}</p>
                </li>
              ))}
            </ul>
          </div>
        )}

        {bekliyor && !cevap && (
          <div className="mt-4 border-t border-havale pt-4">
            {!formAcik ? (
              <div className="flex items-center gap-3 flex-wrap">
                <button
                  type="button"
                  disabled={!yetkili}
                  onClick={() => setFormAcik(true)}
                  className="font-display font-semibold text-[12.5px] px-3.5 py-2 rounded-sm border border-murekkep
                             bg-murekkep text-yaprak hover:bg-murekkep-orta transition-colors
                             disabled:opacity-40 disabled:cursor-not-allowed
                             focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-murekkep"
                >
                  Cevap geldi
                </button>
                <span className="font-veri text-[10px] text-karbon leading-snug">
                  Cevap kamuda ayrı bir evraktır; ilgi ile bu evraka bağlanır ve eksiklik kapanır.
                </span>
              </div>
            ) : (
              <div>
                <p className="font-veri text-[9px] tracking-[0.12em] uppercase text-karbon">
                  Gelen cevaplar
                </p>
                <ul className="mt-3 flex flex-col gap-3">
                  {talep.sorular.map((q, i) => (
                    <li key={i}>
                      <label className="block">
                        <span className="font-govde text-[13.5px] leading-snug">{q}</span>
                        <textarea
                          value={girilen[q] ?? ""}
                          onChange={(e) => setGirilen((g) => ({ ...g, [q]: e.target.value }))}
                          rows={2}
                          placeholder="Karşı tarafın verdiği cevabı yazın"
                          className="mt-1 w-full resize-y bg-yaprak border border-tel-koyu rounded-sm px-3 py-2
                                     font-govde text-[14px] leading-relaxed placeholder:text-karbon
                                     focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-murekkep"
                        />
                      </label>
                    </li>
                  ))}
                </ul>
                <div className="mt-3 flex gap-2 flex-wrap">
                  <button
                    type="button"
                    disabled={dolu.length === 0 || gonderiliyor}
                    onClick={() => void gonder()}
                    className="font-display font-semibold text-[12.5px] px-3.5 py-2 rounded-sm border border-murekkep
                               bg-murekkep text-yaprak hover:bg-murekkep-orta transition-colors
                               disabled:opacity-40 disabled:cursor-not-allowed
                               focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-murekkep"
                  >
                    {dolu.length} cevabı işle
                  </button>
                  <button
                    type="button"
                    onClick={() => setFormAcik(false)}
                    className="font-display font-semibold text-[12.5px] px-3.5 py-2 rounded-sm border border-tel-koyu
                               hover:border-murekkep transition-colors
                               focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-murekkep"
                  >
                    Vazgeç
                  </button>
                </div>
                {hataMesaji && (
                  <p className="mt-3 border border-kase bg-kase-soluk text-kase rounded-sm px-3 py-2 font-govde text-[13px]">
                    {hataMesaji}
                  </p>
                )}
              </div>
            )}
          </div>
        )}

        <button
          type="button"
          onClick={() => setYaziAcik((v) => !v)}
          aria-expanded={yaziAcik}
          className="mt-5 font-display font-semibold text-[12.5px] px-3 py-1.5 rounded-sm border border-havale text-havale
                     hover:bg-havale-soluk transition-colors
                     focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-murekkep"
        >
          {yaziAcik ? "Tamamlama yazısını gizle" : "Gönderilen tamamlama yazısını gör"}
        </button>
      </div>

      {yaziAcik && (
        <div className="border-t border-havale">
          <ResmiYazi
            taslak={talep.yazi}
            govde={talep.yazi.govde}
            baslik="Eksik tamamlama yazısı"
            kenarGoster={false}
          />
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------

export default function KuyrukEkrani({
  oturum,
  onAkisiGor,
}: {
  oturum: Oturum
  /** Evrağın koşusunu akış ekranında açar. Geçmiş koşu detaydan yeniden çizilir. */
  onAkisiGor: (evrakId: string, dosyaAdi: string) => void
}) {
  const rolAnahtari = `${oturum.rol.kod}:${oturum.birimKodu ?? ""}`
  const { evraklar, birimler, ilkYukleme, hata, detay, sec, kararVer, eksikBilgiOnizle, hamVarlik } =
    useEvraklar(rolAnahtari)

  const [sekme, setSekme] = useState<Sekme>("bekleyen")
  const [seciliId, setSeciliId] = useState<string | null>(null)
  const [gelenAcik, setGelenAcik] = useState(false)
  const [duzenleniyor, setDuzenleniyor] = useState(false)
  const [duzenlenen, setDuzenlenen] = useState({
    baslik: "",
    konu: "",
    muhatap: "",
    govde: "",
  })

  useEffect(() => {
    setDuzenleniyor(false)
    setGelenAcik(false)
  }, [seciliId])

  const gorunur = useMemo(
    () =>
      sekme === "bekleyen"
        ? evraklar.filter((e) => ACIK_DURUMLAR.includes(e.durum))
        : evraklar,
    [evraklar, sekme],
  )

  const kritikSayisi = gorunur.filter((e) => e.kritik_eksik_sayisi > 0).length

  const secildi = (id: string) => {
    setSeciliId(id)
    sec(id)
  }

  const duzenlemeBaslat = () => {
    const t = detay?.taslak
    setDuzenlenen({
      baslik: t?.baslik ?? "",
      konu: t?.konu ?? "",
      muhatap: t?.muhatap ?? "",
      govde: t?.govde ?? "",
    })
    setDuzenleniyor(true)
  }

  const dogrulanmisMevzuat = (detay?.mevzuat ?? []).filter((m) => m.dogrulandi)

  // SDP tablosu kodların %64'ünde tek bir birimi işaret ediyor, kalanında
  // yalnızca aday kümesini daraltıyor. "Deterministik" demeden önce sayıyoruz.
  const sdpAdaySayisi = useMemo(() => {
    const kod = detay?.sdp?.kod
    if (!kod) return null
    return birimler.filter((b) => b.hedef_olabilir && b.sdp_kodlari.includes(kod)).length
  }, [detay?.sdp?.kod, birimler])

  return (
    <div className="mx-auto max-w-[1400px] px-6 py-6">
      {hata && (
        <p className="mb-4 border border-kase bg-kase-soluk text-kase rounded-sm px-4 py-2.5 text-[13px]">
          {hata}
        </p>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[340px_minmax(0,1fr)] gap-6 items-start">
        {/* ---------------- kuyruk ---------------- */}
        <section
          aria-label="Onay kuyruğu"
          className="border border-tel rounded-sm bg-kagit overflow-hidden lg:sticky lg:top-6"
        >
          <div className="px-4 py-3 border-b border-tel-koyu bg-yaprak">
            <BolumBasligi
              sag={
                <span className="font-veri text-[9px] text-karbon tabular-nums">
                  {gorunur.length} evrak{kritikSayisi > 0 && ` · ${kritikSayisi} kritik`}
                </span>
              }
            >
              {oturum.rol.yetkiler.tumBirimleriGorur ? "Tüm birimler" : "Birimime düşenler"}
            </BolumBasligi>

            <div className="mt-3 flex gap-1">
              {(["bekleyen", "tumu"] as Sekme[]).map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setSekme(s)}
                  className={
                    "font-veri text-[10px] tracking-[0.08em] uppercase px-2.5 py-1 rounded-xs border transition-colors " +
                    (sekme === s
                      ? "border-murekkep bg-murekkep text-yaprak"
                      : "border-tel-koyu text-karbon hover:border-murekkep-orta")
                  }
                >
                  {s === "bekleyen" ? "Bekleyen" : "Tümü"}
                </button>
              ))}
            </div>
          </div>

          <div className="max-h-[calc(100vh-220px)] overflow-y-auto">
            {ilkYukleme && (
              <p className="px-4 py-6 font-veri text-[11px] text-karbon">Yükleniyor…</p>
            )}
            {!ilkYukleme && gorunur.length === 0 && (
              <div className="px-4 py-10 text-center">
                <p className="font-govde text-[14px] text-murekkep-orta leading-relaxed">
                  {sekme === "bekleyen" ? "Onay bekleyen evrak yok." : "Bu görünümde evrak yok."}
                </p>
                {!oturum.rol.yetkiler.tumBirimleriGorur && (
                  <p className="mt-2 font-veri text-[10px] text-karbon">
                    Süzme sunucuda yapılıyor; yalnızca biriminize yönlendirilenler geliyor.
                  </p>
                )}
              </div>
            )}
            {gorunur.map((e) => (
              <KuyrukSatiri
                key={e.evrak_id}
                e={e}
                secili={seciliId === e.evrak_id}
                onSec={() => secildi(e.evrak_id)}
              />
            ))}
          </div>
        </section>

        {/* ---------------- künye ---------------- */}
        <section aria-label="Evrak künyesi">
          {!detay ? (
            <div className="border border-tel rounded-sm bg-yaprak/50 px-8 py-24 text-center">
              <p className="font-display font-bold text-[17px] tracking-tight">
                Soldan bir evrak seçin
              </p>
              <p className="mt-2 font-govde text-[15px] text-murekkep-orta max-w-sm mx-auto leading-relaxed">
                Evrağın neden onaya düştüğü, özeti, eksikleri, dayandığı mevzuat, üretilen
                resmî yazı ve yönlendirme önerisi burada görünür.
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              {/* neden onaya düştü */}
              {detay.guven_kapisi && (
                <div
                  className={
                    "border rounded-sm px-5 py-4 " +
                    (detay.guven_kapisi.mod === "OTOMATIK"
                      ? "border-muhur bg-muhur-soluk"
                      : "border-kase bg-kase-soluk")
                  }
                >
                  <BolumBasligi>
                    {detay.guven_kapisi.mod === "OTOMATIK"
                      ? "Otomatik onaylandı"
                      : "Neden onayınıza düştü"}
                  </BolumBasligi>
                  <p className="mt-2 font-govde text-[15px] leading-relaxed">
                    {detay.guven_kapisi.sebep}
                  </p>
                  <div className="mt-3">
                    <GuvenCubugu
                      skor={detay.guven_kapisi.skor}
                      esik={detay.guven_kapisi.esik}
                      genislik={180}
                    />
                  </div>
                </div>
              )}

              {/* künye */}
              <div className="border border-tel rounded-sm bg-yaprak overflow-hidden">
                <div className="px-5 py-4 border-b border-tel flex items-start gap-4">
                  <div className="min-w-0">
                    <p className="font-veri text-[10px] text-karbon truncate">
                      {detay.ustveri?.sayi.deger ?? "sayısız"}
                    </p>
                    <h2 className="mt-0.5 font-display font-bold text-[17px] tracking-tight">
                      {detay.ustveri?.konu.deger ?? detay.dosya_adi}
                    </h2>
                  </div>
                  <div className="ml-auto shrink-0 flex items-center gap-3">
                    <button
                      type="button"
                      onClick={() => onAkisiGor(detay.evrak_id, detay.dosya_adi)}
                      title="Bu evrağın on bir adımlık koşusunu adım adım göster"
                      className="font-display font-semibold text-[12px] px-2.5 py-1 rounded-sm border border-tel-koyu
                                 hover:border-murekkep transition-colors
                                 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-murekkep"
                    >
                      Akışı gör
                    </button>
                    <button
                      type="button"
                      onClick={() => setGelenAcik((v) => !v)}
                      aria-expanded={gelenAcik}
                      className="font-display font-semibold text-[12px] px-2.5 py-1 rounded-sm border border-tel-koyu
                                 hover:border-murekkep transition-colors
                                 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-murekkep"
                    >
                      {gelenAcik ? "Gelen evrakı gizle" : "Gelen evrakı gör"}
                    </button>
                    <DurumRozeti durum={detay.durum} />
                  </div>
                </div>

                <dl className="grid grid-cols-2 sm:grid-cols-4 divide-x divide-tel border-b border-tel">
                  {[
                    ["Belge türü", BELGE_TURU_ETIKET[detay.belge_turu?.deger ?? ""] ?? "—"],
                    [
                      "SDP",
                      detay.sdp
                        ? `${detay.sdp.kod}${detay.sdp.kaynak_sayidan_mi ? " · sayıdan" : " · tahmin"}`
                        : "—",
                    ],
                    ["Toplam süre", detay.toplam_ms ? sn(detay.toplam_ms) : "—"],
                    ["Sayfa", String(detay.sayfa_sayisi ?? "—")],
                  ].map(([b, d]) => (
                    <div key={b} className="px-4 py-3">
                      <dt className="font-veri text-[9px] tracking-[0.12em] uppercase text-karbon">
                        {b}
                      </dt>
                      <dd className="mt-1 font-veri text-[12px] tabular-nums">{d}</dd>
                    </div>
                  ))}
                </dl>

                {detay.ozet && (
                  <div className="px-5 py-4 border-b border-tel">
                    <BolumBasligi>Özet</BolumBasligi>
                    <p className="mt-2 font-govde text-[15px] leading-relaxed">{detay.ozet}</p>
                  </div>
                )}

                {detay.eksikler && detay.eksikler.length > 0 && (
                  <div className="px-5 py-4 border-b border-tel">
                    <BolumBasligi>Eksik bilgiler</BolumBasligi>
                    <ul className="mt-3 flex flex-col gap-3">
                      {detay.eksikler.map((x) => (
                        <li key={x.alan} className="flex gap-3">
                          <span className="pt-0.5 shrink-0">
                            <OnemRozeti onem={x.onem} />
                          </span>
                          <div className="min-w-0">
                            <p className="font-govde text-[14px] leading-snug">
                              {x.soru}
                              {x.giderildi && (
                                <span className="ml-2 font-veri text-[8.5px] tracking-[0.1em] uppercase text-muhur">
                                  giderildi
                                </span>
                              )}
                            </p>
                            <p className="mt-0.5 font-veri text-[10px] text-karbon">
                              {KATMAN_ETIKET[x.katman] ?? x.katman} · {x.dayanak}
                            </p>
                            {x.cevap && (
                              <p className="mt-0.5 font-govde text-[13px] text-muhur">
                                → {x.cevap}
                              </p>
                            )}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {dogrulanmisMevzuat.length > 0 && (
                  <div className="px-5 py-4">
                    <BolumBasligi
                      sag={
                        <span className="font-veri text-[9px] text-karbon">
                          yalnızca doğrulananlar
                        </span>
                      }
                    >
                      Dayanak mevzuat
                    </BolumBasligi>
                    <ul className="mt-3 flex flex-col gap-3">
                      {dogrulanmisMevzuat.map((m) => (
                        <li key={m.madde + m.mevzuat_adi} className="border-l-2 border-tel-koyu pl-3">
                          <p className="font-veri text-[11px]">
                            {m.mevzuat_adi} {m.madde}
                            <span className="ml-2 text-muhur text-[9px] tracking-[0.1em] uppercase">
                              doğrulandı
                            </span>
                          </p>
                          {m.alinti && (
                            <p className="mt-0.5 font-govde text-[13px] italic text-karbon leading-snug">
                              “{m.alinti}”
                            </p>
                          )}
                          <p className="mt-0.5 font-govde text-[13px] text-murekkep-orta leading-snug">
                            {m.gerekce}
                          </p>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              {gelenAcik && (
                <GelenEvrak
                  detay={detay}
                  hamAc={async (sira) => (await hamVarlik(detay.evrak_id, sira)).deger}
                />
              )}

              {detay.taslak && (
                <ResmiYazi
                  taslak={detay.taslak}
                  bulgular={detay.uslup_bulgulari ?? []}
                  linterTuru={detay.linter_tur_sayisi}
                  kararTuru={detay.karar?.uretilecek_tur}
                  duzenleniyor={duzenleniyor}
                  govde={duzenleniyor ? duzenlenen.govde : detay.taslak.govde}
                  konu={duzenleniyor ? duzenlenen.konu : detay.taslak.konu}
                  muhatap={duzenleniyor ? duzenlenen.muhatap : detay.taslak.muhatap}
                  yaziBasligi={duzenleniyor ? duzenlenen.baslik : detay.taslak.baslik}
                  onGovdeDegisti={(v) => setDuzenlenen((d) => ({ ...d, govde: v }))}
                  onKonuDegisti={(v) => setDuzenlenen((d) => ({ ...d, konu: v }))}
                  onMuhatapDegisti={(v) => setDuzenlenen((d) => ({ ...d, muhatap: v }))}
                  onBaslikDegisti={(v) => setDuzenlenen((d) => ({ ...d, baslik: v }))}
                />
              )}

              {detay.eksik_bilgi_talebi && (
                <TalepKarti
                  talep={detay.eksik_bilgi_talebi}
                  cevap={detay.eksik_bilgi_cevabi}
                  bekliyor={detay.durum === "EKSIK_BILGI_BEKLIYOR"}
                  yetkili={oturum.rol.yetkiler.onaylayabilir}
                  onCevapGonder={async (cevaplar) => {
                    await kararVer(detay.evrak_id, {
                      aksiyon: "eksik_bilgi_cevabi",
                      rol: oturum.rol.kod,
                      cevaplar,
                    })
                  }}
                />
              )}

              {detay.yonlendirme && (
                <div className="border border-tel rounded-sm bg-yaprak px-5 py-4">
                  <BolumBasligi
                    sag={
                      <span
                        title={
                          detay.yonlendirme.kaynak === "sdp_tablosu" && sdpAdaySayisi != null
                            ? `${detay.sdp?.kod} kodu ${sdpAdaySayisi} hedef birimin tablosunda geçiyor`
                            : undefined
                        }
                        className={
                          "font-veri text-[9px] tracking-[0.1em] uppercase px-1.5 py-px rounded-xs border " +
                          (detay.yonlendirme.kaynak === "sdp_tablosu" && sdpAdaySayisi === 1
                            ? "border-muhur text-muhur bg-muhur-soluk"
                            : detay.yonlendirme.kaynak === "sdp_tablosu"
                              ? "border-havale text-havale bg-havale-soluk"
                              : "border-tel-koyu text-karbon")
                        }
                      >
                        {detay.yonlendirme.kaynak !== "sdp_tablosu"
                          ? "çıkarım"
                          : sdpAdaySayisi === 1
                            ? "SDP tablosu · tek aday"
                            : `SDP tablosu · ${sdpAdaySayisi} aday`}
                      </span>
                    }
                  >
                    Yönlendirme önerisi
                  </BolumBasligi>
                  <div className="mt-3 flex items-baseline gap-3 flex-wrap">
                    <p className="font-display font-bold text-[15px]">
                      {detay.yonlendirme.birim_adi}
                    </p>
                    <span className="font-veri text-[11px] text-karbon tabular-nums">
                      {guvenYaz(detay.yonlendirme.skor)}
                    </span>
                    <span className="font-veri text-[9px] tracking-[0.1em] uppercase text-karbon border border-tel-koyu rounded-xs px-1 py-px">
                      {detay.yonlendirme.geregi_bilgi === "geregi" ? "gereği" : "bilgi"}
                    </span>
                  </div>
                  <p className="mt-1.5 font-govde text-[14px] leading-relaxed">
                    {detay.yonlendirme.gerekce}
                  </p>
                  <blockquote className="mt-2 border-l-2 border-tel-koyu pl-3 font-govde text-[13px] italic text-murekkep-orta">
                    {detay.yonlendirme.kanit_cumle}
                  </blockquote>

                  {detay.yonlendirme.kaynak === "sdp_tablosu" &&
                    sdpAdaySayisi != null &&
                    sdpAdaySayisi > 1 && (
                      <p className="mt-2 font-veri text-[10px] text-havale leading-relaxed">
                        {detay.sdp?.kod} kodu {sdpAdaySayisi} birimin görev tablosunda geçiyor;
                        tablo aday kümesini daraltıyor, birimi tek başına belirlemiyor.
                      </p>
                    )}

                  {detay.yonlendirme.alternatif_adaylar.length > 0 && (
                    <div className="mt-4 pt-3 border-t border-tel">
                      <p className="font-veri text-[9px] tracking-[0.12em] uppercase text-karbon">
                        Değerlendirilen diğer birimler
                      </p>
                      <ul className="mt-2 flex flex-col gap-1">
                        {detay.yonlendirme.alternatif_adaylar.map((a) => (
                          <li
                            key={a.birim}
                            className="flex items-center justify-between gap-3 font-veri text-[10.5px] text-karbon"
                          >
                            <span className="truncate">{a.birim_adi}</span>
                            <span className="tabular-nums shrink-0">{guvenYaz(a.skor)}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              <OnayPaneli
                key={detay.evrak_id + detay.durum}
                detay={detay}
                oturum={oturum}
                birimler={birimler}
                duzenleniyor={duzenleniyor}
                duzenlenen={duzenlenen}
                onDuzenlemeBaslat={duzenlemeBaslat}
                onDuzenlemeIptal={() => setDuzenleniyor(false)}
                kararVer={(govde) => kararVer(detay.evrak_id, govde)}
                eksikBilgiOnizle={(sorular) => eksikBilgiOnizle(detay.evrak_id, sorular)}
              />

              {detay.gunluk.length > 0 && (
                <div className="border border-tel rounded-sm bg-yaprak">
                  <div className="px-4 py-2 border-b border-tel">
                    <BolumBasligi>İşlem günlüğü</BolumBasligi>
                  </div>
                  <ul className="px-4 py-2 font-veri text-[10.5px] leading-[1.7] max-h-48 overflow-y-auto overscroll-contain">
                    {[...detay.gunluk].reverse().map((g, i) => (
                      <li key={i} className="flex gap-3">
                        <span className="text-tel-koyu tabular-nums shrink-0">{saat(g.ts)}</span>
                        <span
                          className={
                            "shrink-0 w-32 truncate " +
                            (g.aktor === "sistem" ? "text-karbon" : "text-havale")
                          }
                        >
                          {g.aktor}
                        </span>
                        <span className="text-murekkep-orta">{g.olay}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
