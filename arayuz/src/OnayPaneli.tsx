import { useMemo, useState } from "react"
import type { Birim, EksikBilgiTalebi, Evrak, KararGovdesi, KararYaniti } from "./tipler"
import type { Oturum } from "./roller"
import ResmiYazi from "./ResmiYazi"
import {
  ACIK_DURUMLAR,
  BolumBasligi,
  DURUM_ETIKET,
  OnemRozeti,
  SONUCLANMIS_DURUMLAR,
  kirp,
  tarihGoster,
} from "./ortak"

type Eylem = "reddet" | "birim_degistir" | "eksik_bilgi_iste" | "geri_al" | null

function Dugme({
  children,
  onClick,
  birincil,
  tehlike,
  etkin = true,
  yukleniyor,
}: {
  children: React.ReactNode
  onClick: () => void
  birincil?: boolean
  tehlike?: boolean
  etkin?: boolean
  yukleniyor?: boolean
}) {
  const stil = birincil
    ? "bg-murekkep text-yaprak border-murekkep hover:bg-murekkep-orta"
    : tehlike
      ? "border-kase text-kase hover:bg-kase-soluk"
      : "border-tel-koyu text-murekkep hover:border-murekkep"
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!etkin || yukleniyor}
      className={
        "font-display font-semibold text-[12.5px] px-3.5 py-2 rounded-sm border transition-colors " +
        "disabled:opacity-40 disabled:cursor-not-allowed " +
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-murekkep " +
        stil
      }
    >
      {children}
    </button>
  )
}

function GerekceKutusu({
  deger,
  onDegisti,
  etiket,
  ipucu,
}: {
  deger: string
  onDegisti: (v: string) => void
  etiket: string
  ipucu: string
}) {
  return (
    <label className="block">
      <span className="font-veri text-[9px] tracking-[0.12em] uppercase text-karbon">
        {etiket} <span className="text-kase">· zorunlu</span>
      </span>
      <textarea
        value={deger}
        onChange={(e) => onDegisti(e.target.value)}
        rows={3}
        placeholder={ipucu}
        className="mt-1.5 w-full resize-y bg-yaprak border border-tel-koyu rounded-sm px-3 py-2
                   font-govde text-[14px] leading-relaxed placeholder:text-karbon
                   focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-murekkep"
      />
    </label>
  )
}

/** 35 birim, üç kurum, üç kademe. Arama görev alanında da eşleşir. */
function BirimSecici({
  birimler,
  mevcutKod,
  secili,
  onSecildi,
}: {
  birimler: Birim[]
  mevcutKod: string | null
  secili: string | null
  onSecildi: (kod: string) => void
}) {
  const [arama, setArama] = useState("")

  const gruplar = useMemo(() => {
    const q = arama.trim().toLocaleLowerCase("tr-TR")
    const uygun = birimler.filter((b) => {
      if (!b.hedef_olabilir || b.kod === mevcutKod) return false
      if (!q) return true
      return (
        b.ad.toLocaleLowerCase("tr-TR").includes(q) ||
        b.gorev_alani.toLocaleLowerCase("tr-TR").includes(q) ||
        b.kurum.toLocaleLowerCase("tr-TR").includes(q) ||
        b.sdp_kodlari.some((k) => k.startsWith(q))
      )
    })
    const harita = new Map<string, Birim[]>()
    for (const b of uygun) {
      const liste = harita.get(b.kurum) ?? []
      liste.push(b)
      harita.set(b.kurum, liste)
    }
    // Kurum satırı (seviye 0) başa gelir; kendisi de hedeftir.
    // Arama yokken vatandaş yoğunluğu yüksek birimler öne alınır.
    const agirlik = { yuksek: 0, orta: 1, dusuk: 2 } as const
    for (const liste of harita.values()) {
      liste.sort((a, b) => {
        if (a.seviye !== b.seviye) return a.seviye - b.seviye
        if (q) return 0
        return agirlik[a.vatandas_yogunlugu] - agirlik[b.vatandas_yogunlugu]
      })
    }
    return [...harita.entries()]
  }, [birimler, arama, mevcutKod])

  const toplam = gruplar.reduce((n, [, l]) => n + l.length, 0)

  return (
    <div>
      <label className="block">
        <span className="font-veri text-[9px] tracking-[0.12em] uppercase text-karbon">
          Hedef birim <span className="text-kase">· zorunlu</span>
        </span>
        <input
          type="search"
          value={arama}
          onChange={(e) => setArama(e.target.value)}
          placeholder="Birim adı, görev alanı veya SDP kodu — örn. nakil, denklik, 210.01"
          className="mt-1.5 w-full bg-yaprak border border-tel-koyu rounded-sm px-3 py-2
                     font-display text-[13px] placeholder:text-karbon
                     focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-murekkep"
        />
      </label>

      <p className="mt-1.5 font-veri text-[9px] text-karbon">
        {toplam} birim · yalnızca hedef olabilenler
      </p>

      <div className="mt-2 border border-tel rounded-sm max-h-72 overflow-y-auto bg-yaprak">
        {toplam === 0 && (
          <p className="px-3 py-3 font-govde text-[13px] text-karbon">Eşleşen birim yok.</p>
        )}
        {gruplar.map(([kurum, liste]) => (
          <div key={kurum}>
            <p className="sticky top-0 px-3 py-1.5 bg-kagit border-y border-tel font-veri text-[9px] tracking-[0.12em] uppercase text-karbon">
              {kurum}
            </p>
            <ul className="divide-y divide-tel">
              {liste.map((b) => {
                const etkin = secili === b.kod
                return (
                  <li key={b.kod}>
                    <button
                      type="button"
                      onClick={() => onSecildi(b.kod)}
                      aria-pressed={etkin}
                      title={b.gorev_alani}
                      className={
                        "w-full text-left px-3 py-2 transition-colors " +
                        "focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-murekkep " +
                        (etkin ? "bg-murekkep text-yaprak" : "hover:bg-kagit")
                      }
                      style={{ paddingLeft: 12 + (b.seviye === 0 ? 0 : 12) }}
                    >
                      <div className="flex items-baseline gap-2">
                        <span className="font-display font-semibold text-[13px]">{b.ad}</span>
                        {b.seviye === 0 && (
                          <span
                            className={
                              "font-veri text-[8.5px] tracking-[0.1em] uppercase shrink-0 " +
                              (etkin ? "text-yaprak/70" : "text-karbon")
                            }
                          >
                            kurum
                          </span>
                        )}
                        {b.vatandas_yogunlugu === "yuksek" && (
                          <span
                            title="Vatandaş başvurusu yoğun"
                            className={
                              "ml-auto font-veri text-[8.5px] tracking-[0.1em] uppercase shrink-0 " +
                              (etkin ? "text-yaprak/70" : "text-havale")
                            }
                          >
                            yoğun
                          </span>
                        )}
                      </div>
                      <p
                        className={
                          "mt-0.5 font-veri text-[10px] leading-snug " +
                          (etkin ? "text-yaprak/80" : "text-karbon")
                        }
                      >
                        {kirp(b.gorev_alani, 110)}
                      </p>
                    </button>
                  </li>
                )
              })}
            </ul>
          </div>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------

export default function OnayPaneli({
  detay,
  oturum,
  birimler,
  duzenleniyor,
  duzenlenen,
  onDuzenlemeBaslat,
  onDuzenlemeIptal,
  kararVer,
  eksikBilgiOnizle,
}: {
  detay: Evrak
  oturum: Oturum
  birimler: Birim[]
  duzenleniyor: boolean
  duzenlenen: { baslik: string; konu: string; muhatap: string; govde: string }
  onDuzenlemeBaslat: () => void
  onDuzenlemeIptal: () => void
  kararVer: (govde: KararGovdesi) => Promise<KararYaniti>
  eksikBilgiOnizle: (sorular: string[]) => Promise<EksikBilgiTalebi>
}) {
  const [eylem, setEylem] = useState<Eylem>(null)
  const [gerekce, setGerekce] = useState("")
  const [yeniBirim, setYeniBirim] = useState<string | null>(null)
  const [secilenSorular, setSecilenSorular] = useState<string[]>(() =>
    (detay.eksikler ?? [])
      .filter((x) => x.karsi_taraftan_istenebilir && !x.giderildi)
      .map((x) => x.soru),
  )
  const [onizleme, setOnizleme] = useState<EksikBilgiTalebi | null>(null)
  const [onizlemeDuzen, setOnizlemeDuzen] = useState(false)
  const [onizlemeYazi, setOnizlemeYazi] = useState<Record<string, string>>({})
  const [gonderiliyor, setGonderiliyor] = useState(false)
  const [mesaj, setMesaj] = useState<{ tur: "ok" | "hata"; metin: string } | null>(null)

  const yetkili = oturum.rol.yetkiler.onaylayabilir
  const acik = ACIK_DURUMLAR.includes(detay.durum)

  // "Deftere kaydet" yalnızca evrak bir birimde duruyor ve o birimin gelen
  // defterine henüz yazılmamışsa görünür. `sevk` alanını sahte sunucu hiç
  // göndermiyor; orada düğme çıkmaz ve bu doğru — sahte sunucuda defter yok.
  const deftereYazilabilir = !!detay.sevk && !detay.sevk.kaydedildi

  const sifirla = () => {
    setEylem(null)
    setGerekce("")
    setYeniBirim(null)
    setOnizleme(null)
    setOnizlemeDuzen(false)
    setOnizlemeYazi({})
  }

  const gonder = async (govde: KararGovdesi) => {
    setGonderiliyor(true)
    setMesaj(null)
    try {
      const sonuc = await kararVer(govde)
      sifirla()
      onDuzenlemeIptal()
      let metin: string
      switch (govde.aksiyon) {
        case "deftere_kaydet":
          metin =
            "Evrak gelen defterine kaydedildi. Defter sekmesinden sıra numarasıyla açılabilir."
          break
        case "taslak_kaydet":
          metin =
            "Değişiklik kaydedildi. Evrak hâlâ onayınızı bekliyor — hazır olduğunuzda “Onayla” deyin."
          break
        case "birim_degistir":
          metin = `Yönlendirme değiştirildi. Düzeltme kaydedildi — yönlendirme başarımı ölçümüne işlendi.`
          break
        case "karari_geri_al":
          metin = "Karar geri alındı. Geri alma işlem günlüğüne yazıldı."
          break
        case "eksik_bilgi_iste":
          metin = "Tamamlama yazısı gönderildi. Evrak, cevap gelene kadar bekliyor."
          break
        default:
          metin = `${DURUM_ETIKET[sonuc.durum] ?? sonuc.durum}.`
      }
      setMesaj({ tur: "ok", metin })
    } catch (e) {
      setMesaj({ tur: "hata", metin: e instanceof Error ? e.message : "İşlem başarısız." })
    } finally {
      setGonderiliyor(false)
    }
  }

  const onizlemeHazirla = async () => {
    setGonderiliyor(true)
    setMesaj(null)
    try {
      const t = await eksikBilgiOnizle(secilenSorular)
      setOnizleme(t)
      setOnizlemeDuzen(false)
      setOnizlemeYazi({
        baslik: t.yazi.baslik,
        konu: t.yazi.konu,
        muhatap: t.yazi.muhatap,
        govde: t.yazi.govde,
      })
    } catch (e) {
      setMesaj({ tur: "hata", metin: e instanceof Error ? e.message : "Yazı üretilemedi." })
    } finally {
      setGonderiliyor(false)
    }
  }

  const Bildirim = () =>
    mesaj ? (
      <p
        role="status"
        className={
          "mx-5 mb-5 rounded-sm border px-4 py-2.5 font-govde text-[13.5px] leading-relaxed " +
          (mesaj.tur === "ok"
            ? "border-muhur bg-muhur-soluk text-muhur"
            : "border-kase bg-kase-soluk text-kase")
        }
      >
        {mesaj.metin}
      </p>
    ) : null

  // ---- sonuçlanmış evrak -------------------------------------------------
  if (!acik) {
    const geriAlinabilir =
      oturum.rol.kod === "yonetici" && SONUCLANMIS_DURUMLAR.includes(detay.durum)

    return (
      <div className="border border-tel rounded-sm bg-yaprak overflow-hidden">
        <div className="px-5 py-3 border-b border-tel">
          <BolumBasligi>Eylemler</BolumBasligi>
        </div>
        <div className="px-5 py-4">
          <p className="font-govde text-[14px] text-murekkep-orta leading-relaxed">
            Bu evrak sonuçlanmış: {DURUM_ETIKET[detay.durum] ?? detay.durum}.
            {detay.duzeltmeler.length > 0 &&
              " Süreçte insan düzeltmesi yapılmış; işlem günlüğünde görünür."}
          </p>

          {deftereYazilabilir && (
            <div className="mt-4">
              <Dugme
                etkin={yetkili}
                yukleniyor={gonderiliyor}
                onClick={() =>
                  void gonder({ aksiyon: "deftere_kaydet", rol: oturum.rol.kod })
                }
              >
                Deftere kaydet
              </Dugme>
              <p className="mt-2 font-veri text-[10px] text-karbon leading-relaxed">
                Evrak biriminize ulaştı ama gelen defterine yazılmadı. Kaydetmek
                sıra numarası verir ve işi kapatır.
              </p>
            </div>
          )}

          {geriAlinabilir ? (
            eylem === "geri_al" ? (
              <div className="mt-4">
                <GerekceKutusu
                  etiket="Geri alma gerekçesi"
                  ipucu="Kararın neden geri alındığını yazın. Bu kayıt denetim izinde kalır."
                  deger={gerekce}
                  onDegisti={setGerekce}
                />
                <p className="mt-2 font-veri text-[10px] text-karbon leading-relaxed">
                  Karar silinmez; geri alma ayrı bir olay olarak işlem günlüğüne yazılır.
                </p>
                <div className="mt-3 flex gap-2">
                  <Dugme
                    tehlike
                    etkin={gerekce.trim().length > 0}
                    yukleniyor={gonderiliyor}
                    onClick={() =>
                      void gonder({ aksiyon: "karari_geri_al", rol: oturum.rol.kod, gerekce })
                    }
                  >
                    Kararı geri al
                  </Dugme>
                  <Dugme onClick={sifirla}>Vazgeç</Dugme>
                </div>
              </div>
            ) : (
              <div className="mt-4">
                <Dugme onClick={() => setEylem("geri_al")}>Kararı geri al</Dugme>
              </div>
            )
          ) : (
            <p className="mt-3 font-veri text-[10px] text-karbon leading-relaxed">
              Kararı yalnızca Kurum Yöneticisi geri alabilir.
            </p>
          )}
        </div>
        <Bildirim />
      </div>
    )
  }

  return (
    <div className="border border-tel rounded-sm bg-yaprak overflow-hidden">
      <div className="px-5 py-3 border-b border-tel">
        <BolumBasligi
          sag={
            !yetkili ? (
              <span className="font-veri text-[9px] tracking-[0.1em] uppercase text-kase border border-kase rounded-xs px-1.5 py-px">
                yetki yok
              </span>
            ) : undefined
          }
        >
          Eylemler
        </BolumBasligi>
      </div>

      {!yetkili && (
        <p className="px-5 pt-4 font-govde text-[13.5px] text-murekkep-orta leading-relaxed">
          <strong className="font-semibold">{oturum.rol.ad}</strong> rolünün onay yetkisi yok.
          Düğmeler görünür ama çalışmaz; onay Birim Sorumlusu veya Kurum Yöneticisindedir.
        </p>
      )}

      <div className="px-5 py-4 flex flex-wrap gap-2">
        {duzenleniyor ? (
          <>
            <Dugme
              birincil
              etkin={yetkili && duzenlenen.govde.trim().length > 0}
              yukleniyor={gonderiliyor}
              onClick={() =>
                void gonder({
                  aksiyon: "taslak_kaydet",
                  rol: oturum.rol.kod,
                  taslak_baslik: duzenlenen.baslik,
                  taslak_konu: duzenlenen.konu,
                  taslak_muhatap: duzenlenen.muhatap,
                  taslak_govde: duzenlenen.govde,
                })
              }
            >
              Değişikliği kaydet
            </Dugme>
            <Dugme onClick={onDuzenlemeIptal}>Vazgeç</Dugme>
            <p className="w-full mt-1 font-veri text-[10px] text-karbon leading-relaxed">
              Kaydetmek onaylamaz. Yazıyı gözden geçirdikten sonra ayrıca “Onayla” demeniz
              gerekir.
            </p>
          </>
        ) : (
          <>
            <Dugme
              birincil
              etkin={yetkili}
              yukleniyor={gonderiliyor}
              onClick={() => void gonder({ aksiyon: "onayla", rol: oturum.rol.kod })}
            >
              Onayla
            </Dugme>
            <Dugme
              etkin={yetkili}
              onClick={() => {
                sifirla()
                onDuzenlemeBaslat()
              }}
            >
              Yazıyı düzenle
            </Dugme>
            <Dugme
              etkin={yetkili}
              onClick={() => setEylem(eylem === "birim_degistir" ? null : "birim_degistir")}
            >
              Başka birime yönlendir
            </Dugme>
            {deftereYazilabilir && (
              <Dugme
                etkin={yetkili}
                yukleniyor={gonderiliyor}
                onClick={() =>
                  void gonder({ aksiyon: "deftere_kaydet", rol: oturum.rol.kod })
                }
              >
                Deftere kaydet
              </Dugme>
            )}
            <Dugme
              etkin={yetkili}
              onClick={() => setEylem(eylem === "eksik_bilgi_iste" ? null : "eksik_bilgi_iste")}
            >
              Eksik bilgi iste
            </Dugme>
            <Dugme
              tehlike
              etkin={yetkili}
              onClick={() => setEylem(eylem === "reddet" ? null : "reddet")}
            >
              Reddet
            </Dugme>
          </>
        )}
      </div>

      {eylem === "reddet" && (
        <div className="px-5 pb-5 border-t border-tel pt-4 bg-kase-soluk/30">
          <GerekceKutusu
            etiket="Red gerekçesi"
            ipucu="Evrağın neden işleme alınmadığını yazın."
            deger={gerekce}
            onDegisti={setGerekce}
          />
          <div className="mt-3 flex gap-2">
            <Dugme
              tehlike
              etkin={yetkili && gerekce.trim().length > 0}
              yukleniyor={gonderiliyor}
              onClick={() => void gonder({ aksiyon: "reddet", rol: oturum.rol.kod, gerekce })}
            >
              Reddi onayla
            </Dugme>
            <Dugme onClick={sifirla}>Vazgeç</Dugme>
          </div>
        </div>
      )}

      {eylem === "birim_degistir" && (
        <div className="px-5 pb-5 border-t border-tel pt-4 bg-kagit">
          {detay.yonlendirme && (
            <p className="mb-3 font-veri text-[10.5px] text-karbon">
              Sistem önerisi: {detay.yonlendirme.birim_adi} ·{" "}
              {detay.yonlendirme.kaynak === "sdp_tablosu"
                ? "SDP tablosundan (deterministik)"
                : "çıkarım"}
            </p>
          )}
          <BirimSecici
            birimler={birimler}
            mevcutKod={detay.yonlendirme?.birim ?? null}
            secili={yeniBirim}
            onSecildi={setYeniBirim}
          />
          <div className="mt-4">
            <GerekceKutusu
              etiket="Değişiklik gerekçesi"
              ipucu="Sistemin önerisi neden uygun değil? Bu kayıt yönlendirme başarımı ölçümünde kullanılır."
              deger={gerekce}
              onDegisti={setGerekce}
            />
          </div>
          <div className="mt-3 flex gap-2">
            <Dugme
              birincil
              etkin={yetkili && !!yeniBirim && gerekce.trim().length > 0}
              yukleniyor={gonderiliyor}
              onClick={() =>
                void gonder({
                  aksiyon: "birim_degistir",
                  rol: oturum.rol.kod,
                  yeni_birim: yeniBirim!,
                  gerekce,
                })
              }
            >
              Yönlendirmeyi değiştir
            </Dugme>
            <Dugme onClick={sifirla}>Vazgeç</Dugme>
          </div>
        </div>
      )}

      {eylem === "eksik_bilgi_iste" && (
        <div className="px-5 pb-5 border-t border-tel pt-4 bg-havale-soluk/30">
          <p className="font-veri text-[9px] tracking-[0.12em] uppercase text-karbon">
            Karşı taraftan istenecek bilgiler
          </p>

          {(detay.eksikler ?? []).length === 0 ? (
            <p className="mt-2 font-govde text-[13.5px] text-murekkep-orta">
              Bu evrakta tespit edilmiş eksik bilgi yok.
            </p>
          ) : (
            <ul className="mt-3 flex flex-col gap-2.5">
              {(detay.eksikler ?? []).map((x) => {
                const secili = secilenSorular.includes(x.soru)
                return (
                  <li key={x.alan}>
                    <label className="flex gap-3 items-start cursor-pointer">
                      <input
                        type="checkbox"
                        checked={secili}
                        disabled={!x.karsi_taraftan_istenebilir || x.giderildi}
                        onChange={(e) =>
                          setSecilenSorular((eski) =>
                            e.target.checked
                              ? [...eski, x.soru]
                              : eski.filter((s) => s !== x.soru),
                          )
                        }
                        className="mt-1 accent-murekkep w-4 h-4 shrink-0"
                      />
                      <span className="min-w-0">
                        <span className="flex items-center gap-2 flex-wrap">
                          <OnemRozeti onem={x.onem} />
                          <span className="font-govde text-[14px] leading-snug">{x.soru}</span>
                          {x.giderildi && (
                            <span className="font-veri text-[8.5px] tracking-[0.1em] uppercase text-muhur">
                              giderildi
                            </span>
                          )}
                        </span>
                        <span className="block mt-0.5 font-veri text-[10px] text-karbon">
                          {x.dayanak}
                        </span>
                      </span>
                    </label>
                  </li>
                )
              })}
            </ul>
          )}

          <div className="mt-4 flex gap-2 flex-wrap">
            <Dugme
              birincil
              etkin={yetkili && secilenSorular.length > 0}
              yukleniyor={gonderiliyor}
              onClick={() => void onizlemeHazirla()}
            >
              {onizleme
                ? "Yazıyı yeniden üret"
                : `${secilenSorular.length} soruyla yazıyı hazırla`}
            </Dugme>
            <Dugme onClick={sifirla}>Vazgeç</Dugme>
          </div>

          {!onizleme && (
            <p className="mt-2 font-veri text-[10px] text-karbon leading-relaxed">
              Yazı şablondan üretilir, gösterilir; onaylamadan gönderilmez.
            </p>
          )}

          {onizleme && (
            <div className="mt-5 border-t border-havale pt-5">
              <dl className="grid grid-cols-2 sm:grid-cols-4 gap-y-3 gap-x-4">
                {[
                  ["Kime", onizleme.muhatap_ad],
                  ["Kanal", onizleme.kanal],
                  ["Süre", `${onizleme.sure_gun} gün`],
                  ["Son tarih", tarihGoster(onizleme.son_tarih)],
                ].map(([b, d]) => (
                  <div key={b}>
                    <dt className="font-veri text-[9px] tracking-[0.12em] uppercase text-karbon">
                      {b}
                    </dt>
                    <dd className="mt-0.5 font-govde text-[13.5px] leading-snug">{d}</dd>
                  </div>
                ))}
              </dl>
              <p className="mt-3 font-veri text-[10px] text-karbon leading-relaxed">
                Dayanak: {onizleme.dayanak}
              </p>

              <div className="mt-4">
                <ResmiYazi
                  taslak={onizleme.yazi}
                  baslik={
                    onizlemeDuzen
                      ? "Gönderilecek yazı — düzenleniyor"
                      : "Gönderilecek yazı — önizleme"
                  }
                  kenarGoster={false}
                  duzenleniyor={onizlemeDuzen}
                  govde={onizlemeYazi.govde ?? onizleme.yazi.govde}
                  konu={onizlemeYazi.konu ?? onizleme.yazi.konu}
                  muhatap={onizlemeYazi.muhatap ?? onizleme.yazi.muhatap}
                  yaziBasligi={onizlemeYazi.baslik ?? onizleme.yazi.baslik}
                  onGovdeDegisti={(v) => setOnizlemeYazi((y) => ({ ...y, govde: v }))}
                  onKonuDegisti={(v) => setOnizlemeYazi((y) => ({ ...y, konu: v }))}
                  onMuhatapDegisti={(v) => setOnizlemeYazi((y) => ({ ...y, muhatap: v }))}
                  onBaslikDegisti={(v) => setOnizlemeYazi((y) => ({ ...y, baslik: v }))}
                />
              </div>

              <div className="mt-4 flex gap-2 flex-wrap items-center">
                <Dugme
                  birincil
                  etkin={yetkili}
                  yukleniyor={gonderiliyor}
                  onClick={() =>
                    void gonder({
                      aksiyon: "eksik_bilgi_iste",
                      rol: oturum.rol.kod,
                      sorular: secilenSorular,
                      yazi: onizlemeYazi,
                    })
                  }
                >
                  Yazıyı gönder
                </Dugme>
                <Dugme onClick={() => setOnizlemeDuzen((v) => !v)}>
                  {onizlemeDuzen ? "Düzenlemeyi bitir" : "Taslağı düzenle"}
                </Dugme>
                <button
                  type="button"
                  onClick={() => {
                    setOnizleme(null)
                    setOnizlemeDuzen(false)
                  }}
                  className="font-veri text-[10px] text-karbon underline underline-offset-2 hover:text-murekkep
                             focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-murekkep"
                >
                  soruları değiştir
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      <Bildirim />
    </div>
  )
}
