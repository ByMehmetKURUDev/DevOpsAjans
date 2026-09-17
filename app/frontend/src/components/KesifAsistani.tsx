import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, ArrowRight, Check, Compass, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';

/**
 * Proje Keşif Asistanı.
 *
 * Ziyaretçiye tek seferde uzun bir form yerine beş kısa adım soruyor, sonunda
 * verdiği cevaplara göre bir paket öneriyor ve iletişim sayfasına hazır bir
 * özetle gönderiyor.
 *
 * Öneri KURAL TABANLI, dil modeli çağırmıyor: cevaplar puanlanıyor, en yüksek
 * puanlı paket öneriliyor. Gerçek bir model bağlanacaksa `paketOner` işlevinin
 * yerine sunucu çağrısı konur; bileşenin geri kalanı değişmez.
 *
 * Adımlar arası durum bileşende tutuluyor; sayfa yenilenirse sıfırlanır.
 * Sunucuya hiçbir şey yazılmıyor — ziyaretçi son adımda kendi isteğiyle
 * iletişim formuna geçiyor.
 */

type Amac = 'website' | 'eticaret' | 'saas' | 'mobil' | 'mevcut';
type Zaman = 'acil' | 'ceyrek' | 'yarim' | 'esnek';
type Butce = 'baslangic' | 'orta' | 'genis' | 'belirsiz';
type Kapsam =
  | 'girisUyelik'
  | 'odeme'
  | 'cokDil'
  | 'yonetimPaneli'
  | 'entegrasyon'
  | 'seoReklam';

interface Cevaplar {
  amac: Amac | null;
  serbest: string;
  kapsam: Kapsam[];
  zaman: Zaman | null;
  butce: Butce | null;
}

const BOS: Cevaplar = { amac: null, serbest: '', kapsam: [], zaman: null, butce: null };

const AMAC_SECENEKLERI: Amac[] = ['website', 'eticaret', 'saas', 'mobil', 'mevcut'];
const KAPSAM_SECENEKLERI: Kapsam[] = [
  'girisUyelik',
  'odeme',
  'cokDil',
  'yonetimPaneli',
  'entegrasyon',
  'seoReklam',
];
const ZAMAN_SECENEKLERI: Zaman[] = ['acil', 'ceyrek', 'yarim', 'esnek'];
const BUTCE_SECENEKLERI: Butce[] = ['baslangic', 'orta', 'genis', 'belirsiz'];

const TOPLAM_ADIM = 5;

/** Paket anahtarları `packages.optionN` ile aynı sırada. */
type PaketNo = 1 | 2 | 3 | 4 | 5;

/**
 * Cevaplara göre paket seçer.
 *
 * Puanlama bilerek basit: her cevap bir veya iki pakete puan ekliyor, en
 * yüksek puanlı kazanıyor. Eşitlikte küçük numaralı (daha kapsamlı olmayan)
 * paket öneriliyor — ziyaretçiye olduğundan büyük bir iş satmamak için.
 */
function paketOner(c: Cevaplar): PaketNo {
  const puan: Record<PaketNo, number> = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 };

  if (c.amac === 'website') puan[2] += 2;
  if (c.amac === 'eticaret') { puan[2] += 1; puan[3] += 2; }
  if (c.amac === 'saas') { puan[4] += 1; puan[5] += 2; }
  if (c.amac === 'mobil') { puan[2] += 1; puan[5] += 1; }
  if (c.amac === 'mevcut') puan[1] += 2;

  if (c.kapsam.includes('seoReklam')) puan[3] += 2;
  if (c.kapsam.includes('odeme')) puan[3] += 1;
  if (c.kapsam.includes('girisUyelik')) puan[4] += 1;
  if (c.kapsam.includes('yonetimPaneli')) puan[4] += 1;
  if (c.kapsam.includes('entegrasyon')) { puan[4] += 1; puan[5] += 1; }
  if (c.kapsam.length >= 4) puan[5] += 2;
  if (c.kapsam.length === 0) puan[1] += 1;

  if (c.zaman === 'acil') puan[2] += 1;
  if (c.zaman === 'esnek') puan[1] += 1;

  if (c.butce === 'baslangic') puan[2] += 1;
  if (c.butce === 'genis') { puan[4] += 1; puan[5] += 1; }
  if (c.butce === 'belirsiz') puan[1] += 1;

  let kazanan: PaketNo = 1;
  ([1, 2, 3, 4, 5] as PaketNo[]).forEach((n) => {
    if (puan[n] > puan[kazanan]) kazanan = n;
  });
  return kazanan;
}

export default function KesifAsistani() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [adim, setAdim] = useState(1);
  const [cevaplar, setCevaplar] = useState<Cevaplar>(BOS);

  const onerilenPaket = useMemo(() => paketOner(cevaplar), [cevaplar]);

  /** Her adımın ilerlemek için doldurulması gereken alanı. */
  const ilerleyebilir =
    (adim === 1 && (cevaplar.amac !== null || cevaplar.serbest.trim() !== '')) ||
    adim === 2 ||
    (adim === 3 && cevaplar.zaman !== null) ||
    (adim === 4 && cevaplar.butce !== null) ||
    adim === 5;

  const kapsamDegistir = (k: Kapsam) =>
    setCevaplar((c) => ({
      ...c,
      kapsam: c.kapsam.includes(k) ? c.kapsam.filter((x) => x !== k) : [...c.kapsam, k],
    }));

  /** İletişim formuna taşınacak, insan okuyabilir özet. */
  const ozetMetni = () => {
    const satir: string[] = [t('kesif.ozetBaslik'), ''];
    if (cevaplar.amac) satir.push(`${t('kesif.s1Baslik')}: ${t(`kesif.amac.${cevaplar.amac}`)}`);
    if (cevaplar.serbest.trim()) satir.push(`${t('kesif.aciklama')}: ${cevaplar.serbest.trim()}`);
    if (cevaplar.kapsam.length)
      satir.push(
        `${t('kesif.s2Baslik')}: ${cevaplar.kapsam.map((k) => t(`kesif.kapsam.${k}`)).join(', ')}`,
      );
    if (cevaplar.zaman) satir.push(`${t('kesif.s3Baslik')}: ${t(`kesif.zaman.${cevaplar.zaman}`)}`);
    if (cevaplar.butce) satir.push(`${t('kesif.s4Baslik')}: ${t(`kesif.butce.${cevaplar.butce}`)}`);
    satir.push('', `${t('kesif.onerilen')}: ${t(`packages.option${onerilenPaket}`)}`);
    return satir.join('\n');
  };

  const secimSinifi = (secili: boolean) =>
    `min-h-[44px] w-full rounded-xl border px-4 py-3 text-left text-sm transition-colors ${
      secili
        ? 'border-primary bg-primary/10 text-foreground'
        : 'border-white/10 bg-white/[0.03] text-muted-foreground hover:border-white/25 hover:text-foreground'
    }`;

  return (
    <section id="kesif" className="alt-bolum relative py-20 md:py-28 border-t border-white/10">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid gap-12 lg:grid-cols-2 lg:items-center">
          {/* Sol: anlatım */}
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-purple-300 mb-4">
              {t('kesif.sectionTag')}
            </p>
            <h2 className="text-3xl sm:text-4xl lg:text-5xl font-bold leading-tight">
              {t('kesif.title')} <span className="gradient-text">{t('kesif.titleHighlight')}</span>
            </h2>
            <p className="mt-6 text-muted-foreground max-w-xl leading-relaxed">
              {t('kesif.desc')}
            </p>
            <ul className="mt-8 space-y-3">
              {['fayda1', 'fayda2', 'fayda3'].map((k) => (
                <li key={k} className="flex items-start gap-3 text-sm text-muted-foreground">
                  <Check className="mt-0.5 h-4 w-4 flex-none text-primary" aria-hidden="true" />
                  {t(`kesif.${k}`)}
                </li>
              ))}
            </ul>
          </div>

          {/* Sağ: sihirbaz */}
          <div className="glass rounded-2xl p-6 sm:p-8">
            <div className="flex items-start gap-3">
              <span className="flex h-10 w-10 flex-none items-center justify-center rounded-xl bg-primary/15">
                <Compass className="h-5 w-5 text-primary" aria-hidden="true" />
              </span>
              <div>
                <h3 className="font-bold">{t('kesif.kartBaslik')}</h3>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {adim > TOPLAM_ADIM - 1
                    ? t('kesif.sonAdimEtiket')
                    : t('kesif.adimEtiket', { adim, toplam: TOPLAM_ADIM })}
                </p>
              </div>
            </div>

            {/* İlerleme */}
            <div className="mt-5 mb-6 flex gap-1.5" role="presentation">
              {Array.from({ length: TOPLAM_ADIM }, (_, i) => (
                <span
                  key={i}
                  className={`h-1 flex-1 rounded-full ${
                    i < adim ? 'bg-gradient-to-r from-purple-500 to-pink-500' : 'bg-white/10'
                  }`}
                />
              ))}
            </div>

            {/* 1 — Amaç */}
            {adim === 1 && (
              <div>
                <label
                  htmlFor="kesif-serbest"
                  className="block text-sm font-medium text-foreground"
                >
                  {t('kesif.s1Baslik')}
                </label>
                <textarea
                  id="kesif-serbest"
                  rows={3}
                  value={cevaplar.serbest}
                  onChange={(e) => setCevaplar((c) => ({ ...c, serbest: e.target.value }))}
                  placeholder={t('kesif.s1Ornek')}
                  className="mt-2 w-full rounded-xl border border-white/10 bg-background/60 px-4 py-3 text-sm leading-relaxed text-foreground placeholder:text-muted-foreground/70 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                />
                <p className="mt-4 mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {t('kesif.hizliSecim')}
                </p>
                <div className="space-y-2">
                  {AMAC_SECENEKLERI.map((a) => (
                    <button
                      key={a}
                      type="button"
                      onClick={() => setCevaplar((c) => ({ ...c, amac: c.amac === a ? null : a }))}
                      aria-pressed={cevaplar.amac === a}
                      className={secimSinifi(cevaplar.amac === a)}
                    >
                      {t(`kesif.amac.${a}`)}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* 2 — Kapsam */}
            {adim === 2 && (
              <div>
                <p className="text-sm font-medium text-foreground">{t('kesif.s2Baslik')}</p>
                <p className="mt-1 text-xs text-muted-foreground">{t('kesif.s2Yardim')}</p>
                <div className="mt-4 space-y-2">
                  {KAPSAM_SECENEKLERI.map((k) => (
                    <button
                      key={k}
                      type="button"
                      onClick={() => kapsamDegistir(k)}
                      aria-pressed={cevaplar.kapsam.includes(k)}
                      className={secimSinifi(cevaplar.kapsam.includes(k))}
                    >
                      <span className="flex items-center gap-3">
                        <span
                          className={`flex h-4 w-4 flex-none items-center justify-center rounded border ${
                            cevaplar.kapsam.includes(k)
                              ? 'border-primary bg-primary'
                              : 'border-white/25'
                          }`}
                        >
                          {cevaplar.kapsam.includes(k) && (
                            <Check className="h-3 w-3 text-white" aria-hidden="true" />
                          )}
                        </span>
                        {t(`kesif.kapsam.${k}`)}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* 3 — Zaman */}
            {adim === 3 && (
              <div>
                <p className="text-sm font-medium text-foreground">{t('kesif.s3Baslik')}</p>
                <div className="mt-4 space-y-2">
                  {ZAMAN_SECENEKLERI.map((z) => (
                    <button
                      key={z}
                      type="button"
                      onClick={() => setCevaplar((c) => ({ ...c, zaman: z }))}
                      aria-pressed={cevaplar.zaman === z}
                      className={secimSinifi(cevaplar.zaman === z)}
                    >
                      {t(`kesif.zaman.${z}`)}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* 4 — Bütçe */}
            {adim === 4 && (
              <div>
                <p className="text-sm font-medium text-foreground">{t('kesif.s4Baslik')}</p>
                <p className="mt-1 text-xs text-muted-foreground">{t('kesif.s4Yardim')}</p>
                <div className="mt-4 space-y-2">
                  {BUTCE_SECENEKLERI.map((b) => (
                    <button
                      key={b}
                      type="button"
                      onClick={() => setCevaplar((c) => ({ ...c, butce: b }))}
                      aria-pressed={cevaplar.butce === b}
                      className={secimSinifi(cevaplar.butce === b)}
                    >
                      {t(`kesif.butce.${b}`)}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* 5 — Özet */}
            {adim === 5 && (
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {t('kesif.ozetEtiket')}
                </p>
                <div className="mt-3 divide-y divide-white/10 rounded-xl border border-white/10">
                  <div className="flex items-start justify-between gap-4 px-4 py-3">
                    <span className="text-xs text-muted-foreground">{t('kesif.s1Baslik')}</span>
                    <span className="text-right text-sm font-medium">
                      {cevaplar.amac ? t(`kesif.amac.${cevaplar.amac}`) : t('kesif.belirtilmedi')}
                    </span>
                  </div>
                  <div className="flex items-start justify-between gap-4 px-4 py-3">
                    <span className="text-xs text-muted-foreground">{t('kesif.s2Baslik')}</span>
                    <span className="text-right text-sm font-medium">
                      {cevaplar.kapsam.length
                        ? cevaplar.kapsam.map((k) => t(`kesif.kapsam.${k}`)).join(', ')
                        : t('kesif.belirtilmedi')}
                    </span>
                  </div>
                  <div className="flex items-start justify-between gap-4 px-4 py-3">
                    <span className="text-xs text-muted-foreground">{t('kesif.s3Baslik')}</span>
                    <span className="text-right text-sm font-medium">
                      {cevaplar.zaman ? t(`kesif.zaman.${cevaplar.zaman}`) : t('kesif.belirtilmedi')}
                    </span>
                  </div>
                  <div className="flex items-start justify-between gap-4 px-4 py-3">
                    <span className="text-xs text-muted-foreground">{t('kesif.s4Baslik')}</span>
                    <span className="text-right text-sm font-medium">
                      {cevaplar.butce ? t(`kesif.butce.${cevaplar.butce}`) : t('kesif.belirtilmedi')}
                    </span>
                  </div>
                </div>

                <div className="mt-4 rounded-xl border border-primary/40 bg-primary/10 px-4 py-4">
                  <p className="text-xs font-semibold uppercase tracking-wider text-purple-200">
                    {t('kesif.onerilen')}
                  </p>
                  <p className="mt-1 text-lg font-bold">{t(`packages.option${onerilenPaket}`)}</p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {t(`packages.option${onerilenPaket}Desc`)}
                  </p>
                </div>

                <p className="mt-3 text-xs text-muted-foreground">{t('kesif.oneriNotu')}</p>
              </div>
            )}

            {/* Gezinme */}
            <div className="mt-6 flex items-center justify-between gap-3">
              {adim > 1 ? (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setAdim((a) => a - 1)}
                  className="gap-2 text-muted-foreground hover:text-foreground"
                >
                  <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                  {t('kesif.geri')}
                </Button>
              ) : (
                <span />
              )}

              {adim < TOPLAM_ADIM ? (
                <Button
                  size="sm"
                  disabled={!ilerleyebilir}
                  onClick={() => setAdim((a) => a + 1)}
                  className="h-11 gap-2 border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white hover:from-purple-500 hover:to-pink-500 disabled:opacity-40"
                >
                  {t('kesif.devam')}
                  <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </Button>
              ) : (
                <div className="flex items-center gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setCevaplar(BOS);
                      setAdim(1);
                    }}
                    className="gap-2 text-muted-foreground hover:text-foreground"
                  >
                    <RotateCcw className="h-4 w-4" aria-hidden="true" />
                    {t('kesif.bastanBasla')}
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => navigate('/contact', { state: { kesifOzeti: ozetMetni() } })}
                    className="h-11 gap-2 border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white hover:from-purple-500 hover:to-pink-500"
                  >
                    {t('kesif.teklifIste')}
                    <ArrowRight className="h-4 w-4" aria-hidden="true" />
                  </Button>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
