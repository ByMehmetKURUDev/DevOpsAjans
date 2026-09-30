import { memo, useEffect, useMemo, useState, type ComponentType } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  Building2,
  Check,
  ChevronDown,
  Coins,
  GraduationCap,
  HeartHandshake,
  Loader2,
  Rocket,
  ShoppingCart,
  User,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import FiyatTeklifModal from '@/components/FiyatTeklifModal';
import {
  fiyatlandirmaApi,
  type AiPmTier,
  type FiyatHesaplaSonucu,
  type FiyatPeriyodu,
  type FiyatTeklifIstegi,
  type PricingAddon,
  type PricingProfile,
  type PricingScale,
  type PricingService,
} from '@/api/fiyatlandirma';
import { KREDI_PAKETLERI } from '@/lib/krediPaketleri';

/**
 * Fiyatlandırma v6.
 *
 * v5'ten farkı (30 Eylül 2026, onaylı önizleme):
 * - Paketler / Hizmetler / Karşılaştırma / AI vs PM sekmeleri kalktı. Yerine
 *   bütün kartlara birden uygulanan **profil seçimi** geldi, altında
 *   **ödeme şekli**: Kullandıkça Öde · Aylık · Yıllık ("Tek seferlik" adı
 *   Kullandıkça Öde oldu; kartta paketin aylık karşılığı kaç kredi olduğu yazar).
 * - "Eklentiler" artık **Modüller**. AI vs PM paketleri de modüllerin içinde:
 *   kartta tek bir seviye seçilir, tutarı kartın toplamına eklenir.
 * - **Karşılaştırma** kartın içinde, Modüllerin altında, Teklif Al'ın üstünde.
 * - **Satın Al** Teklif Al'ın altında: fatura + ödeme bağlantısı açıp ödeme
 *   sayfasına götürür (`POST /fiyat-satin-al`). Kullandıkça Öde'de kredi
 *   bloğuna götürür; oradaki "Kredi Al" seçilen kredi paketini satın aldırır.
 * - 80 hizmetlik katalog kartların altında açılır "Tüm hizmetler" listesi.
 *
 * Fiyat HER ZAMAN `/fiyat-hesapla`'dan geliyor — burada elle çarpım
 * yapılmıyor (bkz. `core/fiyat_hesaplama.py`'nin "tek doğru kaynak" notu).
 */

const PERIYOTLAR: { kod: FiyatPeriyodu; etiketKey: string; etiketDefault: string }[] = [
  { kod: 'kullandikca_ode', etiketKey: 'fiyatV5.periyotKullandikca', etiketDefault: 'Kullandıkça Öde' },
  { kod: 'aylik', etiketKey: 'fiyatV5.periyotAylik', etiketDefault: 'Aylık' },
  { kod: 'yillik', etiketKey: 'fiyatV5.periyotYillik', etiketDefault: 'Yıllık (−16%)' },
];

const PROFIL_IKONLARI: Record<string, ComponentType<{ className?: string }>> = {
  kurumsal: Building2,
  startup: Rocket,
  stk: HeartHandshake,
  bireysel: User,
  egitim: GraduationCap,
};

const KARSILASTIRMA_SATIRLARI: { anahtar: string; etiketKey: string; etiketDefault: string }[] = [
  { anahtar: 'hosting', etiketKey: 'fiyatV5.karsHosting', etiketDefault: 'Hosting' },
  { anahtar: 'sla', etiketKey: 'fiyatV5.karsSla', etiketDefault: 'SLA' },
  { anahtar: 'panel', etiketKey: 'fiyatV5.karsPanel', etiketDefault: 'Panel' },
  { anahtar: 'devops', etiketKey: 'fiyatV5.karsDevops', etiketDefault: 'DevOps' },
  { anahtar: 'mulkiyet', etiketKey: 'fiyatV5.karsMulkiyet', etiketDefault: 'Mülkiyet' },
  { anahtar: 'ads', etiketKey: 'fiyatV5.karsAds', etiketDefault: 'Reklam Yönetimi' },
  { anahtar: 'seo', etiketKey: 'fiyatV5.karsSeo', etiketDefault: 'SEO' },
];

type Secim = Omit<FiyatTeklifIstegi, 'musteri_eposta' | 'musteri_adi'>;
type Eylem = (secim: Secim, konu: string, fiyatMetni: string) => void;

/**
 * Katalog alanını seçili dilde döndürür. Çeviri veritabanında `ceviriler`
 * sütununda; o dilde alan yoksa Türkçe değer gösterilir.
 */
function yerel<T extends { ceviriler?: Record<string, Record<string, unknown>> | null }, K extends keyof T>(
  kayit: T,
  alan: K,
  dil: string,
): T[K] {
  if (dil === 'tr') return kayit[alan];
  const deger = kayit.ceviriler?.[dil]?.[alan as string];
  return deger === undefined || deger === null || deger === '' ? kayit[alan] : (deger as T[K]);
}

/** i18next dil kodunu (ör. "en-US") iki harfe indirger. */
function dilKodu(dil: string | undefined): string {
  return (dil || 'tr').slice(0, 2);
}

function paraFormatla(n: number): string {
  return `$${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
}

/** Profil çarpanını ziyaretçinin anladığı dile çevirir: 1 → "1x", 0.85 → "%15 indirim". */
function profilOrani(carpan: number, t: (k: string, d: string) => string): string {
  if (carpan >= 1) return '1x';
  return `%${Math.round((1 - carpan) * 100)} ${t('fiyatV5.indirim', 'indirim')}`;
}

/** Kart içinde açılır kapanır blok (Modüller, Karşılaştırma). */
function AcilirBlok({
  baslik,
  acik,
  degistir,
  children,
}: {
  baslik: string;
  acik: boolean;
  degistir: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="mt-4 rounded-xl border border-white/10">
      <button
        type="button"
        onClick={degistir}
        aria-expanded={acik}
        className="flex w-full items-center justify-between px-3 py-2 text-xs font-medium text-muted-foreground hover:text-white"
      >
        <span>{baslik}</span>
        <ChevronDown className={`h-3.5 w-3.5 transition-transform ${acik ? 'rotate-180' : ''}`} aria-hidden="true" />
      </button>
      {acik && <div className="px-3 pb-3">{children}</div>}
    </div>
  );
}

/** Tek bir ölçek (ALFA/BETA/...) kartı: üstte seçilen profil + ödeme şekliyle canlı fiyat. */
function OlcekKarti({
  scale,
  profileKod,
  profilEtiket,
  period,
  carpan,
  addons,
  aiPmTiers,
  onTeklifAl,
  onSatinAl,
  onKrediHesapla,
}: {
  scale: PricingScale;
  /** Seçili profilin çarpanı (modül fiyatları kartta bununla gösterilir). */
  carpan: number;
  profileKod: string;
  profilEtiket: string;
  period: FiyatPeriyodu;
  addons: PricingAddon[];
  aiPmTiers: AiPmTier[];
  onTeklifAl: Eylem;
  onSatinAl: Eylem;
  onKrediHesapla: (kredi: number) => void;
}) {
  const { t, i18n } = useTranslation();
  const dil = dilKodu(i18n.resolvedLanguage || i18n.language);
  const [seciliEklentiler, setSeciliEklentiler] = useState<string[]>([]);
  const [aiPm, setAiPm] = useState('');
  const [modullerAcik, setModullerAcik] = useState(false);
  const [karsAcik, setKarsAcik] = useState(false);
  const [sonuc, setSonuc] = useState<FiyatHesaplaSonucu | null>(null);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [hata, setHata] = useState(false);

  useEffect(() => {
    let iptal = false;
    setYukleniyor(true);
    setHata(false);
    fiyatlandirmaApi
      .hesapla({ scale: scale.kod, profile: profileKod, period, addons: seciliEklentiler, aiPm })
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
  }, [scale.kod, profileKod, period, seciliEklentiler.join(','), aiPm]);

  const eklentiToggle = (ad: string) => {
    setSeciliEklentiler((prev) => (prev.includes(ad) ? prev.filter((x) => x !== ad) : [...prev, ad]));
  };

  const periyot = PERIYOTLAR.find((p) => p.kod === period);
  const periyotEtiket = t(periyot?.etiketKey ?? '', periyot?.etiketDefault ?? period);
  const kullandikca = period === 'kullandikca_ode';
  const yillik = period === 'yillik';
  // Modül ve AI vs PM fiyatları aylık; yıllıkta sunucuyla aynı kural (× 12, %16 indirim).
  /**
   * Modül / AI vs PM satırındaki fiyat. Aylık ve Kullandıkça Öde'de aylık;
   * yıllıkta aylık karşılığı + yıllık toplam (× 12, %16 indirim) — kartın
   * toplamıyla aynı kural (core/fiyat_hesaplama.py).
   */
  const satirFiyati = (aylik: number) => {
    const ayEki = t('fiyatV5.ayKisa', 'ay');
    if (!yillik) return `+${paraFormatla(aylik)}/${ayEki}`;
    const yillikToplam = Math.round(aylik * 12 * 0.84);
    return `+${paraFormatla(Math.round(yillikToplam / 12))}/${ayEki} · ${t('fiyatV5.yillikToplam', 'yıllık')} ${paraFormatla(yillikToplam)}`;
  };
  const modulSayisi = seciliEklentiler.length + (aiPm ? 1 : 0);
  const secim: Secim = {
    scale: scale.kod,
    profile: profileKod,
    period,
    addon_ids: seciliEklentiler,
    ...(aiPm ? { ai_pm_tier_kod: aiPm } : {}),
  };
  const konu = `${yerel(scale, 'ad', dil)} / ${profilEtiket} / ${periyotEtiket}`;
  const fiyatMetni = sonuc
    ? kullandikca
      ? `${sonuc.kredi ?? '—'} ${t('fiyatV5.kredi', 'Kredi')} · ${paraFormatla(sonuc.toplam)}`
      : paraFormatla(sonuc.toplam)
    : '';

  return (
    <div
      data-olcek={scale.kod}
      className={`cam-kart relative flex h-full flex-col rounded-2xl p-6 transition-all duration-300 ${
        scale.populer ? 'cam-one glass border-purple-500/50 ring-1 ring-purple-500/40' : 'glass hover:border-purple-500/30'
      }`}
    >
      {scale.populer && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-gradient-to-r from-purple-600 to-pink-600 px-3 py-1 text-[10px] font-semibold uppercase tracking-widest text-white">
          {t('ui.popular', 'Popüler')}
        </div>
      )}

      <p className="text-[11px] font-semibold uppercase tracking-[0.25em] text-pink-300">{yerel(scale, 'alt_baslik', dil)}</p>
      <h3 className="mt-1 text-xl font-bold">{yerel(scale, 'ad', dil)}</h3>
      <p className="mt-1 text-xs text-muted-foreground">{yerel(scale, 'calisan_araligi', dil)}</p>
      <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{yerel(scale, 'aciklama', dil)}</p>

      {/* Canlı fiyat */}
      <div className="cam-fiyat mt-4 min-h-[4.25rem]">
        {yukleniyor && !sonuc ? (
          <div className="flex items-center gap-2 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            <span className="text-sm">{t('fiyatV5.hesaplaniyor', 'Fiyat hesaplanıyor…')}</span>
          </div>
        ) : hata ? (
          <p className="text-sm text-red-400">{t('fiyatV5.hesaplamaHatasi', 'Fiyat şu an hesaplanamadı.')}</p>
        ) : sonuc ? (
          kullandikca ? (
            <>
              <p className="text-3xl font-bold gradient-text">
                {sonuc.kredi} {t('fiyatV5.kredi', 'Kredi')}
              </p>
              <p className="text-xs text-muted-foreground">
                {t('fiyatV5.krediKarsiligi', 'aylık karşılığı')} · {paraFormatla(sonuc.toplam)} ·{' '}
                {t('fiyatV5.krediTanimKisa', '1 Kredi = 1 Saat Senior')}
              </p>
            </>
          ) : (
            <>
              <p className="text-3xl font-bold gradient-text">{paraFormatla(sonuc.toplam)}</p>
              <p className="text-xs text-muted-foreground">
                {periyotEtiket}
                {modulSayisi > 0 ? ` · ${t('fiyatV5.modulDahil', 'modüller dahil')}` : ''}
              </p>
            </>
          )
        ) : null}
      </div>

      {/* Özellik listesi */}
      <ul className="mt-4 space-y-1.5">
        {(yerel(scale, 'ozellikler', dil) ?? []).map((oz) => (
          <li key={oz} className="flex items-start gap-2 text-xs text-muted-foreground">
            <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400" aria-hidden="true" />
            <span>{oz}</span>
          </li>
        ))}
      </ul>

      <div className="mt-auto">
        {/* Modüller: ölçeğin eklentileri + AI vs PM (tek seçim) */}
        {(addons.length > 0 || aiPmTiers.length > 0) && (
          <AcilirBlok
            baslik={`${t('fiyatV5.moduller', 'Modüller')} (${modulSayisi})`}
            acik={modullerAcik}
            degistir={() => setModullerAcik((v) => !v)}
          >
            <div className="space-y-1">
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
                    {yerel(a, 'ad', dil)}
                  </span>
                  <span className="shrink-0 text-end text-muted-foreground">{satirFiyati(a.baz_fiyat_usd * carpan)}</span>
                </label>
              ))}
            </div>
            {aiPmTiers.length > 0 && (
              <fieldset className="mt-3 border-t border-white/10 pt-3">
                <legend className="px-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-pink-300">
                  {t('fiyatV5.sekmeAivsPm', 'AI vs PM')}
                </legend>
                <div className="space-y-1">
                  {[{ kod: '', ad: t('fiyatV5.aiPmYok', 'Yok'), fiyat_aylik_usd: 0 } as Pick<AiPmTier, 'kod' | 'ad' | 'fiyat_aylik_usd'>, ...aiPmTiers].map(
                    (tier) => (
                      <label
                        key={tier.kod || 'yok'}
                        className="flex cursor-pointer items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-xs hover:bg-white/5"
                      >
                        <span className="flex items-center gap-2">
                          <input
                            type="radio"
                            name={`ai-pm-${scale.kod}`}
                            checked={aiPm === tier.kod}
                            onChange={() => setAiPm(tier.kod)}
                            className="h-3.5 w-3.5 accent-purple-500"
                          />
                          {tier.kod ? yerel(tier as AiPmTier, 'ad', dil) : tier.ad}
                        </span>
                        {tier.kod && (
                          <span className="shrink-0 text-end text-muted-foreground">{satirFiyati(tier.fiyat_aylik_usd)}</span>
                        )}
                      </label>
                    ),
                  )}
                </div>
              </fieldset>
            )}
          </AcilirBlok>
        )}

        {/* Karşılaştırma: Modüllerin altında, Teklif Al'ın üstünde */}
        {scale.karsilastirma && (
          <AcilirBlok
            baslik={t('fiyatV5.sekmeKarsilastirma', 'Karşılaştırma')}
            acik={karsAcik}
            degistir={() => setKarsAcik((v) => !v)}
          >
            <dl className="space-y-1.5 text-xs">
              {KARSILASTIRMA_SATIRLARI.map((satir) => (
                <div key={satir.anahtar} className="flex justify-between gap-3">
                  <dt className="text-muted-foreground">{t(satir.etiketKey, satir.etiketDefault)}</dt>
                  <dd className="text-end text-white/90">
                    {(yerel(scale, 'karsilastirma', dil) as Record<string, string> | null)?.[satir.anahtar] ??
                      scale.karsilastirma?.[satir.anahtar] ??
                      '—'}
                  </dd>
                </div>
              ))}
            </dl>
          </AcilirBlok>
        )}

        <div className="mt-5 space-y-2">
          <Button
            disabled={yukleniyor || !sonuc}
            onClick={() => sonuc && onTeklifAl(secim, konu, fiyatMetni)}
            className="h-11 w-full gap-2 !bg-transparent border border-white/25 hover:border-white/50"
            variant="outline"
          >
            {t('fiyatV5.teklifAl', 'Teklif Al')}
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Button>
          <Button
            disabled={yukleniyor || !sonuc}
            onClick={() =>
              sonuc && (kullandikca ? onKrediHesapla(sonuc.kredi ?? 1) : onSatinAl(secim, konu, fiyatMetni))
            }
            className="h-11 w-full gap-2 rounded-md border-0 bg-emerald-500 font-semibold text-black hover:bg-emerald-400"
          >
            {kullandikca ? <Coins className="h-4 w-4" aria-hidden="true" /> : <ShoppingCart className="h-4 w-4" aria-hidden="true" />}
            {kullandikca ? t('fiyatV5.krediSatinAl', 'Kredi satın al') : t('fiyatV5.satinAl', 'Satın Al')}
          </Button>
          <p className="text-center text-[10px] leading-snug text-muted-foreground">
            {kullandikca
              ? t('fiyatV5.satinAlNotKredi', 'Gereken krediyi aşağıdaki kredi paketlerinden alırsınız.')
              : period === 'yillik'
                ? t('fiyatV5.satinAlNotYillik', 'Yıllık ödeme · 12 ay, %16 indirimli.')
                : t('fiyatV5.satinAlNotAylik', 'Aylık abonelik · ilk ay şimdi ödenir.')}
          </p>
        </div>
      </div>
    </div>
  );
}

function TumHizmetler({ services }: { services: PricingService[] }) {
  const { t, i18n } = useTranslation();
  const dil = dilKodu(i18n.resolvedLanguage || i18n.language);
  const [acik, setAcik] = useState(false);
  const kategoriler = useMemo(() => {
    const map = new Map<string, PricingService[]>();
    for (const s of services) {
      const kategori = yerel(s, 'kategori', dil);
      if (!map.has(kategori)) map.set(kategori, []);
      map.get(kategori)!.push(s);
    }
    return Array.from(map.entries());
  }, [services, dil]);

  if (services.length === 0) return null;
  return (
    <div className="mt-10 rounded-2xl border border-white/10 bg-white/[0.02]">
      <button
        type="button"
        onClick={() => setAcik((v) => !v)}
        aria-expanded={acik}
        className="flex w-full items-center justify-between gap-3 px-5 py-4 text-start"
      >
        <span>
          <span className="block text-sm font-semibold text-white">
            {t('fiyatV5.tumHizmetler', 'Tüm hizmetler')} ({services.length})
          </span>
          <span className="block text-xs text-muted-foreground">
            {t('fiyatV5.tumHizmetlerAciklama', 'À la carte hizmet kataloğu. Teklif için paket kartlarını ya da kredileri kullanın.')}
          </span>
        </span>
        <ChevronDown className={`h-4 w-4 shrink-0 transition-transform ${acik ? 'rotate-180' : ''}`} aria-hidden="true" />
      </button>
      {acik && (
        <div className="space-y-8 border-t border-white/10 px-5 py-6">
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
                      <p className="truncate text-sm font-medium">{yerel(s, 'ad', dil)}</p>
                      {s.not_metni && <p className="mt-0.5 text-[11px] text-muted-foreground">{yerel(s, 'not_metni', dil)}</p>}
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
      )}
    </div>
  );
}

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

function KullandikcaOdeBlok({
  ihtiyac,
  setIhtiyac,
  onKrediAl,
}: {
  ihtiyac: number;
  setIhtiyac: (n: number) => void;
  onKrediAl: (kredi: number, konu: string, fiyatMetni: string) => void;
}) {
  const { t, i18n } = useTranslation();

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
                className={`cam-kart rounded-2xl border bg-white/[0.03] p-4 transition-colors ${
                  secili ? 'cam-secili border-emerald-500 ring-1 ring-emerald-500/30' : 'border-white/10'
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
                      {t('ui.popular', 'Popüler').toLocaleUpperCase(i18n.language === 'tr' ? 'tr-TR' : i18n.language)}
                    </span>
                  )}
                </div>
                <div className="cam-parla mt-2 text-lg font-bold text-white">{paraFormatla(p.fiyat)}</div>
                <div className="text-[11px] text-muted-foreground">
                  {saat} {t('fiyatV5.saat', 'saat')} • {saatlikFormatla(p.fiyat / saat)}/{t('fiyatV5.saat', 'saat')}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div>
        <div className="cam-kart cam-gok rounded-2xl border border-white/10 bg-white/[0.03] p-5">
          <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
            {t('fiyatV5.onerilen', 'Önerilen')}
          </div>
          <div className="mt-2 text-xl font-semibold text-white">
            {oneri.saat} {t('fiyatV5.saat', 'saat')}
            {oneri.ozel ? ` ${t('fiyatV5.icinOzel', 'için özel')}` : ''}
          </div>
          <div className="cam-parla mt-4 text-3xl font-extrabold text-white">
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
          {oneri.paket ? (
            <Button
              onClick={() =>
                oneri.paket &&
                onKrediAl(
                  oneri.paket.kredi,
                  `${oneri.paket.kredi} ${t('fiyatV5.kredi', 'Kredi')}${
                    oneri.paket.bonus ? ` +${oneri.paket.bonus} ${t('fiyatV5.bonus', 'bonus')}` : ''
                  } · ${oneri.saat} ${t('fiyatV5.saat', 'saat')}`,
                  paraFormatla(oneri.fiyat),
                )
              }
              className="mt-6 h-11 w-full gap-2 rounded-full bg-emerald-500 font-semibold text-black hover:bg-emerald-400"
            >
              <Coins className="h-4 w-4" aria-hidden="true" />
              {t('fiyatV5.krediAl', 'Kredi Al')} — {paraFormatla(oneri.fiyat)}
            </Button>
          ) : (
            <Button asChild className="mt-6 h-11 w-full gap-2 rounded-full bg-emerald-500 font-semibold text-black hover:bg-emerald-400">
              <Link to="/contact">
                {t('fiyatV5.ozelTeklif', 'Özel teklif iste')}
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

function PricingPlans({ className = '' }: { className?: string }) {
  const { t, i18n } = useTranslation();
  const dil = dilKodu(i18n.resolvedLanguage || i18n.language);

  const [scales, setScales] = useState<PricingScale[]>([]);
  const [profiles, setProfiles] = useState<PricingProfile[]>([]);
  const [services, setServices] = useState<PricingService[]>([]);
  const [addons, setAddons] = useState<PricingAddon[]>([]);
  const [aiPmTiers, setAiPmTiers] = useState<AiPmTier[]>([]);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [hata, setHata] = useState(false);

  const [profileKod, setProfileKod] = useState('kurumsal');
  const [period, setPeriod] = useState<FiyatPeriyodu>('aylik');
  const [ihtiyac, setIhtiyac] = useState(IHTIYAC_VARSAYILAN);

  const [pencere, setPencere] = useState<{
    secim: Secim;
    konu: string;
    fiyatMetni: string;
    mod: 'teklif' | 'satinAl';
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
      .then(([s, p, sv, a, tr]) => {
        if (iptal) return;
        const siraliProfiller = [...p].sort((x, y) => x.sira - y.sira);
        setScales([...s].sort((x, y) => x.sira - y.sira));
        setProfiles(siraliProfiller);
        setServices(sv);
        setAddons(a);
        setAiPmTiers([...tr].sort((x, y) => x.sira - y.sira));
        if (!siraliProfiller.some((x) => x.kod === 'kurumsal') && siraliProfiller[0]) {
          setProfileKod(siraliProfiller[0].kod);
        }
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

  const seciliProfil = profiles.find((p) => p.kod === profileKod);
  const profilEtiket = seciliProfil ? yerel(seciliProfil, 'ad', dil) : profileKod;
  const carpan = Number(seciliProfil?.carpan ?? 1);

  const krediHesapla = (kredi: number) => {
    setIhtiyac(Math.min(Math.max(kredi, IHTIYAC_MIN), IHTIYAC_MAX));
    document.getElementById('kullandikca-ode')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const secimDugmesi =
    'transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-purple-400';

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
              'fiyatV6.girisAciklama',
              'Profilinizi ve ödeme şeklinizi seçin, dört ölçeğin fiyatı anında güncellensin. Modülleri ekleyin, teklif alın ya da hemen satın alın.',
            )}
          </p>
        </div>

        {/* Profil — sekmelerin yerinde, bütün kartlara birden uygulanır */}
        {profiles.length > 0 && (
          <div className="mb-6">
            <p className="mb-3 text-center text-[11px] font-semibold uppercase tracking-[0.25em] text-muted-foreground">
              {t('fiyatV5.profil', 'Profil')}
            </p>
            <div className="mx-auto grid max-w-4xl grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5" role="group" aria-label={t('fiyatV5.profil', 'Profil')}>
              {profiles.map((p) => {
                const Ikon = PROFIL_IKONLARI[p.kod] ?? User;
                const secili = profileKod === p.kod;
                return (
                  <button
                    key={p.kod}
                    type="button"
                    onClick={() => setProfileKod(p.kod)}
                    aria-pressed={secili}
                    title={yerel(p, 'etiket', dil) ?? undefined}
                    className={`${secimDugmesi} flex items-center gap-3 rounded-xl border px-3 py-2.5 text-start ${
                      secili
                        ? 'border-emerald-400/70 bg-emerald-500/10 text-white'
                        : 'border-white/10 bg-white/[0.02] text-muted-foreground hover:border-white/25 hover:text-white'
                    }`}
                  >
                    <span
                      className={`flex h-9 w-9 flex-none items-center justify-center rounded-lg ${
                        secili ? 'bg-emerald-500 text-black' : 'bg-white/5 text-white/80'
                      }`}
                    >
                      <Ikon className="h-4 w-4" aria-hidden="true" />
                    </span>
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-semibold">{yerel(p, 'ad', dil)}</span>
                      <span className={`block text-[11px] ${secili ? 'text-emerald-300' : 'text-muted-foreground'}`}>
                        {profilOrani(Number(p.carpan), t)}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Ödeme şekli — profilin altında */}
        <div className="mb-12 flex flex-col items-center gap-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.25em] text-muted-foreground">
            {t('fiyatV5.odemeSekli', 'Ödeme şekli')}
          </p>
          <div
            className="inline-flex flex-wrap items-center justify-center gap-1 rounded-xl border border-white/10 bg-white/[0.03] p-1"
            role="group"
            aria-label={t('fiyatV5.odemeSekli', 'Ödeme şekli')}
          >
            {PERIYOTLAR.map((per) => (
              <button
                key={per.kod}
                type="button"
                onClick={() => setPeriod(per.kod)}
                aria-pressed={period === per.kod}
                className={`${secimDugmesi} rounded-lg px-4 py-2 text-sm font-semibold ${
                  period === per.kod
                    ? 'bg-gradient-to-r from-purple-600 to-pink-600 text-white'
                    : 'text-muted-foreground hover:text-white'
                }`}
              >
                {t(per.etiketKey, per.etiketDefault)}
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
            <div className="cam-dongu cam-numarali grid items-stretch gap-6 md:grid-cols-2 xl:grid-cols-4">
              {scales.map((s) => (
                <OlcekKarti
                  key={s.id}
                  scale={s}
                  profileKod={profileKod}
                  profilEtiket={profilEtiket}
                  period={period}
                  carpan={carpan}
                  addons={addons.filter((a) => a.scale_kod === s.kod).sort((x, y) => x.sira - y.sira)}
                  aiPmTiers={aiPmTiers}
                  onTeklifAl={(secim, konu, fiyatMetni) => setPencere({ secim, konu, fiyatMetni, mod: 'teklif' })}
                  onSatinAl={(secim, konu, fiyatMetni) => setPencere({ secim, konu, fiyatMetni, mod: 'satinAl' })}
                  onKrediHesapla={krediHesapla}
                />
              ))}
            </div>
            <TumHizmetler services={services} />
          </>
        )}

        <KullandikcaOdeBlok
          ihtiyac={ihtiyac}
          setIhtiyac={setIhtiyac}
          onKrediAl={(kredi, konu, fiyatMetni) =>
            setPencere({ secim: { kredi_paketi: kredi }, konu, fiyatMetni, mod: 'satinAl' })
          }
        />
      </div>

      <FiyatTeklifModal
        acik={pencere !== null}
        kapat={() => setPencere(null)}
        konu={pencere?.konu ?? ''}
        fiyatMetni={pencere?.fiyatMetni ?? ''}
        secim={pencere?.secim ?? {}}
        mod={pencere?.mod ?? 'teklif'}
      />
    </section>
  );
}

export default memo(PricingPlans);
