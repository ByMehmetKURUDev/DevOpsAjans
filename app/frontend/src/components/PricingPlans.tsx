import { memo, useEffect, useMemo, useState } from 'react';
import { ArrowRight, Check, ChevronDown, Coins, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import FiyatTeklifModal from '@/components/FiyatTeklifModal';
import {
  fiyatlandirmaApi,
  type AiPmTier,
  type FiyatHesaplaSonucu,
  type FiyatPeriyodu,
  type PricingAddon,
  type PricingProfile,
  type PricingScale,
  type PricingService,
} from '@/api/fiyatlandirma';

/**
 * Fiyatlandırma v5.
 *
 * Eski 5 sabit kartlı `PricingPlans`'ın yerini alıyor. Artık her şey admin
 * panelinden yönetilen 5 tablodan geliyor (bkz. `routers/pricing_entities.py`,
 * `dependencies/entity_guard.py`): 4 ölçek (ALFA/BETA/OMEGA/SIGMA) × 5 profil
 * × à la carte 80 hizmet + ölçek başına eklentiler, ayrı sabit fiyatlı
 * "AI vs PM" 4 katman.
 *
 * Fiyat HER ZAMAN `/fiyat-hesapla`'dan geliyor — burada elle çarpım
 * yapılmıyor (bkz. `core/fiyat_hesaplama.py`'nin "tek doğru kaynak" notu).
 * "Teklif Al" aynı seçimi `/fiyat-teklif`'e gönderip gerçek fatura +
 * `pricing_inquiries` kaydı oluşturuyor.
 *
 * "Kullandıkça Öde" bloğu bilerek işlevsiz: bu faz yalnızca görünürlük
 * istiyor, ödeme akışı ayrı bir iş.
 */

const PERIYOTLAR: { kod: FiyatPeriyodu; etiketKey: string; etiketDefault: string }[] = [
  { kod: 'aylik', etiketKey: 'fiyatV5.periyotAylik', etiketDefault: 'Aylık' },
  { kod: 'yillik', etiketKey: 'fiyatV5.periyotYillik', etiketDefault: 'Yıllık (−16%)' },
  { kod: 'tek_seferlik', etiketKey: 'fiyatV5.periyotTekSeferlik', etiketDefault: 'Tek seferlik' },
];

const KARSILASTIRMA_SATIRLARI: { anahtar: string; etiketKey: string; etiketDefault: string }[] = [
  { anahtar: 'hosting', etiketKey: 'fiyatV5.karsHosting', etiketDefault: 'Hosting' },
  { anahtar: 'sla', etiketKey: 'fiyatV5.karsSla', etiketDefault: 'SLA' },
  { anahtar: 'panel', etiketKey: 'fiyatV5.karsPanel', etiketDefault: 'Panel' },
  { anahtar: 'devops', etiketKey: 'fiyatV5.karsDevops', etiketDefault: 'DevOps' },
  { anahtar: 'mulkiyet', etiketKey: 'fiyatV5.karsMulkiyet', etiketDefault: 'Mülkiyet' },
  { anahtar: 'ads', etiketKey: 'fiyatV5.karsAds', etiketDefault: 'Reklam Yönetimi' },
  { anahtar: 'seo', etiketKey: 'fiyatV5.karsSeo', etiketDefault: 'SEO' },
];

type SekmeKey = 'paketler' | 'hizmetler' | 'karsilastirma' | 'aivspm';

function paraFormatla(n: number): string {
  return `$${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
}

/** Tek bir ölçek (ALFA/BETA/...) kartı: profil + periyot + eklenti seçimiyle canlı fiyat. */
function OlcekKarti({
  scale,
  profiles,
  addons,
  onTeklifAl,
}: {
  scale: PricingScale;
  profiles: PricingProfile[];
  addons: PricingAddon[];
  onTeklifAl: (args: { scale: string; profile: string; period: FiyatPeriyodu; addon_ids: string[] }, konu: string, fiyatMetni: string) => void;
}) {
  const { t } = useTranslation();
  const [profileKod, setProfileKod] = useState(
    profiles.find((p) => p.kod === 'kurumsal')?.kod ?? profiles[0]?.kod ?? 'kurumsal',
  );
  const [period, setPeriod] = useState<FiyatPeriyodu>('aylik');
  const [seciliEklentiler, setSeciliEklentiler] = useState<string[]>([]);
  const [eklentilerAcik, setEklentilerAcik] = useState(false);
  const [sonuc, setSonuc] = useState<FiyatHesaplaSonucu | null>(null);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [hata, setHata] = useState(false);

  useEffect(() => {
    let iptal = false;
    setYukleniyor(true);
    setHata(false);
    fiyatlandirmaApi
      .hesapla({ scale: scale.kod, profile: profileKod, period, addons: seciliEklentiler })
      .then((r) => {
        if (!iptal) setSonuc(r);
      })
      .catch(() => {
        if (!iptal) setHata(true);
      })
      .finally(() => {
        if (!iptal) setYukleniyor(false);
      });
    return () => {
      iptal = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scale.kod, profileKod, period, seciliEklentiler.join(',')]);

  const eklentiToggle = (ad: string) => {
    setSeciliEklentiler((prev) => (prev.includes(ad) ? prev.filter((x) => x !== ad) : [...prev, ad]));
  };

  const profilEtiket = profiles.find((p) => p.kod === profileKod)?.ad ?? profileKod;
  const periyotEtiket = t(
    PERIYOTLAR.find((p) => p.kod === period)?.etiketKey ?? '',
    PERIYOTLAR.find((p) => p.kod === period)?.etiketDefault ?? period,
  );

  return (
    <div
      className={`relative flex h-full flex-col rounded-2xl p-6 transition-all duration-300 ${
        scale.populer ? 'glass border-purple-500/50 ring-1 ring-purple-500/40' : 'glass hover:border-purple-500/30'
      }`}
    >
      {scale.populer && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-gradient-to-r from-purple-600 to-pink-600 px-3 py-1 text-[10px] font-semibold uppercase tracking-widest text-white">
          {t('ui.popular', 'Popüler')}
        </div>
      )}

      <p className="text-[11px] font-semibold uppercase tracking-[0.25em] text-pink-300">{scale.alt_baslik}</p>
      <h3 className="mt-1 text-xl font-bold">{scale.ad}</h3>
      <p className="mt-1 text-xs text-muted-foreground">{scale.calisan_araligi}</p>
      <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{scale.aciklama}</p>

      {/* Profil pilleri */}
      <div className="mt-5 flex flex-wrap gap-1.5">
        {profiles.map((p) => (
          <button
            key={p.kod}
            type="button"
            onClick={() => setProfileKod(p.kod)}
            className={`rounded-full px-2.5 py-1 text-[11px] font-medium transition-colors ${
              profileKod === p.kod
                ? 'bg-gradient-to-r from-purple-600 to-pink-600 text-white'
                : 'border border-white/15 text-muted-foreground hover:border-white/30 hover:text-white'
            }`}
            title={p.etiket ?? undefined}
          >
            {p.ad}
          </button>
        ))}
      </div>

      {/* Periyot pilleri */}
      <div className="mt-2 flex flex-wrap gap-1.5">
        {PERIYOTLAR.map((per) => (
          <button
            key={per.kod}
            type="button"
            onClick={() => setPeriod(per.kod)}
            className={`rounded-full px-2.5 py-1 text-[11px] font-medium transition-colors ${
              period === per.kod
                ? 'bg-white/15 text-white'
                : 'border border-white/10 text-muted-foreground hover:border-white/25 hover:text-white'
            }`}
          >
            {t(per.etiketKey, per.etiketDefault)}
          </button>
        ))}
      </div>

      {/* Canlı fiyat */}
      <div className="mt-4 min-h-[3.5rem]">
        {yukleniyor ? (
          <div className="flex items-center gap-2 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            <span className="text-sm">{t('fiyatV5.hesaplaniyor', 'Fiyat hesaplanıyor…')}</span>
          </div>
        ) : hata ? (
          <p className="text-sm text-red-400">{t('fiyatV5.hesaplamaHatasi', 'Fiyat şu an hesaplanamadı.')}</p>
        ) : sonuc ? (
          <>
            <p className="text-3xl font-bold gradient-text">{paraFormatla(sonuc.toplam)}</p>
            <p className="text-xs text-muted-foreground">
              {periyotEtiket}
              {sonuc.eklentiler_toplami > 0
                ? ` · ${t('fiyatV5.eklentiDahil', 'eklentiler dahil')}`
                : ''}
            </p>
            {sonuc.formul_notu === 'varsayilan_aylik_x3' && (
              <p className="mt-1 text-[10px] text-amber-300/80">
                {t('fiyatV5.tekSeferlikNot', '* Tek seferlik fiyat varsayılan formülle (aylık × 3) hesaplandı.')}
              </p>
            )}
          </>
        ) : null}
      </div>

      {/* Özellik listesi */}
      <ul className="mt-4 space-y-1.5">
        {(scale.ozellikler ?? []).map((oz) => (
          <li key={oz} className="flex items-start gap-2 text-xs text-muted-foreground">
            <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400" aria-hidden="true" />
            <span>{oz}</span>
          </li>
        ))}
      </ul>

      {/* Eklenti akordeonu */}
      {addons.length > 0 && (
        <div className="mt-4 rounded-xl border border-white/10">
          <button
            type="button"
            onClick={() => setEklentilerAcik((v) => !v)}
            className="flex w-full items-center justify-between px-3 py-2 text-xs font-medium text-muted-foreground hover:text-white"
          >
            <span>
              {t('fiyatV5.eklentiler', 'Eklentiler')} ({seciliEklentiler.length}/{addons.length})
            </span>
            <ChevronDown
              className={`h-3.5 w-3.5 transition-transform ${eklentilerAcik ? 'rotate-180' : ''}`}
              aria-hidden="true"
            />
          </button>
          {eklentilerAcik && (
            <div className="space-y-1 px-3 pb-3">
              {addons.map((a) => (
                <label
                  key={a.id}
                  className="flex cursor-pointer items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-xs hover:bg-white/5"
                >
                  <span className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={seciliEklentiler.includes(a.ad)}
                      onChange={() => eklentiToggle(a.ad)}
                      className="h-3.5 w-3.5 rounded border-white/30 bg-transparent accent-purple-500"
                    />
                    {a.ad}
                  </span>
                  <span className="text-muted-foreground">+{paraFormatla(a.baz_fiyat_usd)}</span>
                </label>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="mt-5">
        <Button
          disabled={yukleniyor || !sonuc}
          onClick={() =>
            sonuc &&
            onTeklifAl(
              { scale: scale.kod, profile: profileKod, period, addon_ids: seciliEklentiler },
              `${scale.ad} / ${profilEtiket} / ${periyotEtiket}`,
              paraFormatla(sonuc.toplam),
            )
          }
          className={`h-11 w-full gap-2 ${
            scale.populer
              ? 'border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white hover:from-purple-500 hover:to-pink-500'
              : '!bg-transparent border border-white/25 hover:border-white/50'
          }`}
          variant={scale.populer ? 'default' : 'outline'}
        >
          {t('fiyatV5.teklifAl', 'Teklif Al')}
          <ArrowRight className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
    </div>
  );
}

function HizmetlerSekmesi({ services }: { services: PricingService[] }) {
  const { t } = useTranslation();
  const kategoriler = useMemo(() => {
    const map = new Map<string, PricingService[]>();
    for (const s of services) {
      if (!map.has(s.kategori)) map.set(s.kategori, []);
      map.get(s.kategori)!.push(s);
    }
    return Array.from(map.entries());
  }, [services]);

  return (
    <div className="space-y-8">
      <p className="text-center text-sm text-muted-foreground">
        {t(
          'fiyatV5.hizmetlerAciklama',
          'À la carte hizmet kataloğu — vitrin amaçlı. Teklif almak için yukarıdaki paket kartlarını kullanın.',
        )}
      </p>
      {kategoriler.map(([kategori, list]) => (
        <div key={kategori}>
          <h4 className="mb-3 text-xs font-semibold uppercase tracking-[0.2em] text-pink-300">{kategori}</h4>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {list.map((s) => (
              <div
                key={s.id}
                className="flex items-start justify-between gap-3 rounded-xl border border-white/10 bg-white/[0.02] px-3 py-2.5"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{s.ad}</p>
                  {s.not_metni && <p className="mt-0.5 text-[11px] text-muted-foreground">{s.not_metni}</p>}
                  <div className="mt-1 flex gap-1">
                    {s.yeni && (
                      <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[9px] font-bold text-emerald-300">
                        {t('fiyatV5.yeni', 'YENİ')}
                      </span>
                    )}
                    {s.tek_seferlik && (
                      <span className="rounded-full bg-white/10 px-2 py-0.5 text-[9px] font-bold text-muted-foreground">
                        {t('fiyatV5.tekSeferlik', 'TEK SEFERLİK')}
                      </span>
                    )}
                  </div>
                </div>
                <p className="shrink-0 text-sm font-bold text-white/90">{paraFormatla(s.baz_fiyat_usd)}</p>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function KarsilastirmaSekmesi({ scales }: { scales: PricingScale[] }) {
  const { t } = useTranslation();
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-collapse text-sm">
        <thead>
          <tr>
            <th className="border-b border-white/10 px-3 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {t('fiyatV5.karsOzellik', 'Özellik')}
            </th>
            {scales.map((s) => (
              <th
                key={s.id}
                className="border-b border-white/10 px-3 py-3 text-left text-xs font-semibold uppercase tracking-wider text-white"
              >
                {s.ad}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {KARSILASTIRMA_SATIRLARI.map((satir) => (
            <tr key={satir.anahtar} className="border-b border-white/5">
              <td className="px-3 py-2.5 text-muted-foreground">{t(satir.etiketKey, satir.etiketDefault)}</td>
              {scales.map((s) => (
                <td key={s.id} className="px-3 py-2.5">
                  {s.karsilastirma?.[satir.anahtar] ?? '—'}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AiVsPmSekmesi({
  tiers,
  onTeklifAl,
}: {
  tiers: AiPmTier[];
  onTeklifAl: (args: { ai_pm_tier_kod: string }, konu: string, fiyatMetni: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
      {tiers.map((tier) => (
        <div
          key={tier.id}
          className={`relative flex h-full flex-col rounded-2xl p-6 transition-all duration-300 ${
            tier.kod === 'kombin_ai_pm' ? 'glass border-purple-500/50 ring-1 ring-purple-500/40' : 'glass'
          }`}
        >
          {tier.rozet && (
            <div className="absolute -top-3 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-gradient-to-r from-purple-600 to-pink-600 px-3 py-1 text-[10px] font-semibold uppercase tracking-widest text-white">
              {tier.rozet}
            </div>
          )}
          <h3 className="mt-2 text-lg font-bold">{tier.ad}</h3>
          <p className="mt-3 text-3xl font-bold gradient-text">{paraFormatla(tier.fiyat_aylik_usd)}</p>
          <p className="text-xs text-muted-foreground">{t('packages.perMonth', 'ay başına')}</p>

          <ul className="mt-5 flex-1 space-y-1.5">
            {(tier.ozellikler ?? []).map((oz) => (
              <li key={oz} className="flex items-start gap-2 text-xs text-muted-foreground">
                <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400" aria-hidden="true" />
                <span>{oz}</span>
              </li>
            ))}
          </ul>

          <div className="mt-5">
            <Button
              onClick={() => onTeklifAl({ ai_pm_tier_kod: tier.kod }, tier.ad, paraFormatla(tier.fiyat_aylik_usd))}
              className="h-11 w-full gap-2 border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white hover:from-purple-500 hover:to-pink-500"
            >
              {t('fiyatV5.teklifAl', 'Teklif Al')}
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Button>
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * Kullandıkça Öde kredi paketleri — onaylı mockup'taki (v5) değerler birebir.
 * 1 Kredi = 1 Saat Senior, 12 ay geçerli. Satın alma bu fazda bağlı değil:
 * "Kredi Al" devre dışı ve "Yakında" etiketli (bkz. v5 spec).
 */
const KREDI_PAKETLERI: { kredi: number; bonus: number; fiyat: number; populer?: boolean }[] = [
  { kredi: 10, bonus: 0, fiyat: 1000 },
  { kredi: 25, bonus: 2, fiyat: 2250, populer: true },
  { kredi: 50, bonus: 5, fiyat: 4000 },
  { kredi: 100, bonus: 15, fiyat: 7000 },
];
const PAYG_SAATLIK_USD = 120;
const IHTIYAC_MIN = 1;
const IHTIYAC_MAX = 120;
const IHTIYAC_VARSAYILAN = 28;

function ihtiyacSeviyesi(saat: number): { key: string; varsayilan: string } {
  if (saat <= 10) return { key: 'fiyatV5.seviyeKucuk', varsayilan: 'Küçük' };
  if (saat <= 30) return { key: 'fiyatV5.seviyeOrta', varsayilan: 'Orta' };
  if (saat <= 60) return { key: 'fiyatV5.seviyeBuyuk', varsayilan: 'Büyük' };
  return { key: 'fiyatV5.seviyeOlcek', varsayilan: 'Ölçek' };
}

function saatlikFormatla(n: number): string {
  return `$${n.toLocaleString('en-US', { maximumFractionDigits: 3 })}`;
}

function KullandikcaOdeBlok() {
  const { t } = useTranslation();
  const [ihtiyac, setIhtiyac] = useState(IHTIYAC_VARSAYILAN);

  // İhtiyacı karşılayan en küçük paket; hiçbiri yetmiyorsa en büyük paket +
  // aşan saatler PAYG fiyatından ("… saat için özel").
  const oneri = useMemo(() => {
    const paket = KREDI_PAKETLERI.find((p) => p.kredi + p.bonus >= ihtiyac);
    if (paket) return { paket, saat: paket.kredi + paket.bonus, fiyat: paket.fiyat, ozel: false };
    const enBuyuk = KREDI_PAKETLERI[KREDI_PAKETLERI.length - 1];
    const enBuyukSaat = enBuyuk.kredi + enBuyuk.bonus;
    return {
      paket: null,
      saat: ihtiyac,
      fiyat: enBuyuk.fiyat + (ihtiyac - enBuyukSaat) * PAYG_SAATLIK_USD,
      ozel: true,
    };
  }, [ihtiyac]);

  const seviye = ihtiyacSeviyesi(ihtiyac);

  return (
    <div
      id="kullandikca-ode"
      className="mt-16 grid grid-cols-1 gap-8 rounded-3xl border border-white/10 bg-white/[0.02] p-6 md:p-8 lg:grid-cols-2"
    >
      <div>
        <div className="flex flex-wrap gap-2">
          <span className="rounded-full border border-white/10 bg-white/[0.03] px-2.5 py-1 text-[10px] uppercase tracking-widest text-muted-foreground">
            {t('fiyatV5.saatBankasiYeni', 'Saat Bankası → Yeni')}
          </span>
          <span className="rounded-full bg-emerald-500 px-2.5 py-1 text-[10px] font-bold uppercase tracking-widest text-black">
            {t('fiyatV5.kullandikcaOdeBaslik', 'Kullandıkça Öde')}
          </span>
          <span className="rounded-full border border-indigo-800 bg-indigo-950 px-2.5 py-1 text-[10px] uppercase tracking-widest text-indigo-300">
            {t('fiyatV5.besProfil', '5 Profil')}
          </span>
        </div>

        <h3 className="mt-4 text-2xl font-bold tracking-tight md:text-3xl">
          {t('fiyatV5.kullandikcaOdeKredileri', 'Kullandıkça Öde Kredileri')}
        </h3>
        <p className="mt-2 max-w-[52ch] text-sm leading-relaxed text-muted-foreground">
          {t('fiyatV5.krediAciklama1', 'AI kredisi değil.')}{' '}
          <span className="font-medium text-white">{t('fiyatV5.krediTanim', '1 Kredi = 1 Saat Senior.')}</span>{' '}
          {t('fiyatV5.krediAciklama2', '12 ay geçerli, 80 hizmet için.')}
        </p>

        <div className="mt-6">
          <div className="flex items-center justify-between">
            <label htmlFor="kredi-ihtiyac" className="text-xs text-muted-foreground">
              {t('fiyatV5.ihtiyac', 'İhtiyaç')}: {ihtiyac} {t('fiyatV5.saat', 'saat')}
            </label>
            <span className="rounded-full border border-white/10 bg-white/[0.03] px-2 py-1 font-mono text-[11px] text-muted-foreground">
              {t(seviye.key, seviye.varsayilan)}
            </span>
          </div>
          <input
            id="kredi-ihtiyac"
            type="range"
            min={IHTIYAC_MIN}
            max={IHTIYAC_MAX}
            value={ihtiyac}
            onChange={(e) => setIhtiyac(Number(e.target.value))}
            className="mt-3 w-full accent-emerald-500"
          />
        </div>

        <div className="mt-6 grid grid-cols-2 gap-3">
          {KREDI_PAKETLERI.map((p) => {
            const saat = p.kredi + p.bonus;
            const secili = oneri.paket === p;
            return (
              <div
                key={p.kredi}
                className={`rounded-2xl border bg-white/[0.03] p-4 transition-colors ${
                  secili ? 'border-emerald-500 ring-1 ring-emerald-500/30' : 'border-white/10'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="text-xs font-semibold text-white">
                    {p.kredi} {t('fiyatV5.kredi', 'Kredi')}
                    {p.bonus > 0 && (
                      <span className="text-emerald-400">
                        {' '}+{p.bonus} {t('fiyatV5.bonus', 'bonus')}
                      </span>
                    )}
                  </div>
                  {p.populer && (
                    <span className="rounded-full bg-emerald-500 px-2 py-0.5 text-[9px] font-bold text-black">
                      {t('ui.popular', 'Popüler').toLocaleUpperCase('tr-TR')}
                    </span>
                  )}
                </div>
                <div className="mt-2 text-lg font-bold text-white">{paraFormatla(p.fiyat)}</div>
                <div className="text-[11px] text-muted-foreground">
                  {saat} {t('fiyatV5.saat', 'saat')} • {saatlikFormatla(p.fiyat / saat)}/{t('fiyatV5.saat', 'saat')}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div>
        <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
          <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
            {t('fiyatV5.onerilen', 'Önerilen')}
          </div>
          <div className="mt-2 text-xl font-semibold text-white">
            {oneri.saat} {t('fiyatV5.saat', 'saat')}
            {oneri.ozel ? ` ${t('fiyatV5.icinOzel', 'için özel')}` : ''}
          </div>
          <div className="mt-4 text-3xl font-extrabold text-white">
            <span className="text-emerald-400">$</span>
            {oneri.fiyat.toLocaleString('en-US', { maximumFractionDigits: 0 })}
          </div>
          <div className="mt-4 space-y-2 text-xs text-muted-foreground">
            <div className="flex justify-between">
              <span>PAYG</span>
              <span className="font-mono text-white">
                ${PAYG_SAATLIK_USD}/{t('fiyatV5.saat', 'saat')}
              </span>
            </div>
            <div className="flex justify-between">
              <span>{t('fiyatV5.gecerlilik', 'Geçerlilik')}</span>
              <span className="text-white">{t('fiyatV5.onIkiAy', '12 ay')}</span>
            </div>
            <div className="flex justify-between">
              <span>{t('fiyatV5.tanim', 'Tanım')}</span>
              <span className="text-white">{t('fiyatV5.krediTanimKisa', '1 Kredi = 1 Saat Senior')}</span>
            </div>
          </div>
          <Button
            disabled
            className="mt-6 h-11 w-full gap-2 rounded-full bg-emerald-500 font-semibold text-black opacity-70 hover:bg-emerald-500"
          >
            <Coins className="h-4 w-4" aria-hidden="true" />
            {t('fiyatV5.krediAl', 'Kredi Al')} — {paraFormatla(oneri.fiyat)}
            <span className="ms-1 rounded-full bg-black/15 px-2 py-0.5 text-[10px] font-semibold">
              {t('fiyatV5.yakinda', 'Yakında')}
            </span>
          </Button>
        </div>
      </div>
    </div>
  );
}

function PricingPlans({ className = '' }: { className?: string }) {
  const { t } = useTranslation();
  const [sekme, setSekme] = useState<SekmeKey>('paketler');

  const [scales, setScales] = useState<PricingScale[]>([]);
  const [profiles, setProfiles] = useState<PricingProfile[]>([]);
  const [services, setServices] = useState<PricingService[]>([]);
  const [addons, setAddons] = useState<PricingAddon[]>([]);
  const [aiPmTiers, setAiPmTiers] = useState<AiPmTier[]>([]);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [hata, setHata] = useState(false);

  const [teklif, setTeklif] = useState<{
    secim: { scale?: string; profile?: string; period?: FiyatPeriyodu; addon_ids?: string[]; ai_pm_tier_kod?: string };
    konu: string;
    fiyatMetni: string;
  } | null>(null);

  useEffect(() => {
    let iptal = false;
    Promise.all([
      fiyatlandirmaApi.scales(),
      fiyatlandirmaApi.profiles(),
      fiyatlandirmaApi.services(),
      fiyatlandirmaApi.addons(),
      fiyatlandirmaApi.aiPmTiers(),
    ])
      .then(([s, p, sv, a, t]) => {
        if (iptal) return;
        setScales([...s].sort((x, y) => x.sira - y.sira));
        setProfiles([...p].sort((x, y) => x.sira - y.sira));
        setServices(sv);
        setAddons(a);
        setAiPmTiers([...t].sort((x, y) => x.sira - y.sira));
      })
      .catch(() => {
        if (!iptal) setHata(true);
      })
      .finally(() => {
        if (!iptal) setYukleniyor(false);
      });
    return () => {
      iptal = true;
    };
  }, []);

  const sekmeler: { key: SekmeKey; labelKey: string; labelDefault: string }[] = [
    { key: 'paketler', labelKey: 'fiyatV5.sekmePaketler', labelDefault: 'Paketler' },
    { key: 'hizmetler', labelKey: 'fiyatV5.sekmeHizmetler', labelDefault: 'Hizmetler' },
    { key: 'karsilastirma', labelKey: 'fiyatV5.sekmeKarsilastirma', labelDefault: 'Karşılaştırma' },
    { key: 'aivspm', labelKey: 'fiyatV5.sekmeAivsPm', labelDefault: 'AI vs PM' },
  ];

  const tab =
    'rounded-lg px-4 py-2 text-sm font-semibold transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-purple-400';

  return (
    <section className={`py-24 border-t border-white/10 ${className}`}>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-10">
          <p className="text-xs uppercase tracking-[0.3em] text-pink-300 mb-4">{t('packages.sectionTag', 'Paketler')}</p>
          <h2 className="text-4xl md:text-5xl font-bold mb-4">
            {t('packages.title', 'Paketinizi')} <span className="gradient-text">{t('packages.titleHighlight', 'seçin')}</span>.
          </h2>
          <p className="text-muted-foreground max-w-2xl mx-auto">
            {t(
              'fiyatV5.girisAciklama',
              'Ölçeğinizi ve profilinizi seçin, fiyat anında hesaplansın. À la carte hizmetleri gezin, AI vs PM sürekli desteğini karşılaştırın.',
            )}
          </p>
        </div>

        {/* Sekme çubuğu */}
        <div className="mb-12 flex justify-center">
          <div
            className="inline-flex flex-wrap items-center justify-center gap-1 rounded-xl border border-white/10 bg-white/[0.03] p-1"
            role="tablist"
          >
            {sekmeler.map((s) => (
              <button
                key={s.key}
                type="button"
                role="tab"
                aria-selected={sekme === s.key}
                onClick={() => setSekme(s.key)}
                className={`${tab} ${
                  sekme === s.key
                    ? 'bg-gradient-to-r from-purple-600 to-pink-600 text-white'
                    : 'text-muted-foreground hover:text-white'
                }`}
              >
                {t(s.labelKey, s.labelDefault)}
              </button>
            ))}
          </div>
        </div>

        {yukleniyor ? (
          <div className="flex justify-center py-16">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" aria-hidden="true" />
          </div>
        ) : hata ? (
          <p className="py-16 text-center text-sm text-red-400">
            {t('fiyatV5.katalogHatasi', 'Fiyat kataloğu yüklenemedi, lütfen sayfayı yenileyin.')}
          </p>
        ) : (
          <>
            {sekme === 'paketler' && (
              <div className="grid items-stretch gap-6 md:grid-cols-2 xl:grid-cols-4">
                {scales.map((s) => (
                  <OlcekKarti
                    key={s.id}
                    scale={s}
                    profiles={profiles}
                    addons={addons.filter((a) => a.scale_kod === s.kod).sort((x, y) => x.sira - y.sira)}
                    onTeklifAl={(secim, konu, fiyatMetni) => setTeklif({ secim, konu, fiyatMetni })}
                  />
                ))}
              </div>
            )}
            {sekme === 'hizmetler' && <HizmetlerSekmesi services={services} />}
            {sekme === 'karsilastirma' && <KarsilastirmaSekmesi scales={scales} />}
            {sekme === 'aivspm' && (
              <AiVsPmSekmesi
                tiers={aiPmTiers}
                onTeklifAl={(secim, konu, fiyatMetni) => setTeklif({ secim, konu, fiyatMetni })}
              />
            )}
          </>
        )}

        <KullandikcaOdeBlok />
      </div>

      <FiyatTeklifModal
        acik={teklif !== null}
        kapat={() => setTeklif(null)}
        konu={teklif?.konu ?? ''}
        fiyatMetni={teklif?.fiyatMetni ?? ''}
        secim={teklif?.secim ?? {}}
      />
    </section>
  );
}

export default memo(PricingPlans);
