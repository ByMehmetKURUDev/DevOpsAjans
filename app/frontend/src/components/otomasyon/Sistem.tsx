import { Suspense, useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useLocation } from 'react-router-dom';
import { toast } from 'sonner';
import {
  AlertTriangle,
  BellRing,
  CalendarClock,
  ExternalLink,
  Eye,
  FileCheck2,
  FolderKanban,
  Handshake,
  LifeBuoy,
  Loader2,
  Mail,
  Webhook,
} from 'lucide-react';

import { ekliLazy } from '@/i18n/ekliLazy';
import {
  hataMetni,
  sistemApi,
  type HaftalikOzet,
  type HaftalikOzetDurumu,
  type OzetBolumu,
  type OzetSatiri,
} from '@/lib/otomasyon';
import { IKINCIL_DUGME, KART } from './ortak';

// Zamanlı işler kartı Site Ayarları'ndan buraya taşındı (Faz 7O); metinleri `siteBakim` ek paketinde.
const ZamanliGorevler = ekliLazy('siteBakim', () => import('./ZamanliGorevler'));

/**
 * Faz 7O — Yönetici › Otomasyon › "Sistem": sistemin kendiliğinden yaptıkları, tek yerde.
 *
 * 1. Haftalık özet kartı: açık/kapalı (bildirim matrisindeki yönetici × "Haftalık özet" × e-posta
 *    hücresi — tek kaynak), son gönderim, bu hafta, sonraki gönderim, "Önizle".
 * 2. Yerleşik akışlar (zamanlı iş olmayanlar): her biri bir cümle + ilgili bölümü açan "Ayarla".
 * 3. Zamanlı işler (her iş bir cümleyle) + "Şimdi çalıştır".
 *
 * Müşteri panelinde yok (`Otomasyon` bileşeni yalnız yönetici modunda gösteriyor).
 */
export default function Sistem() {
  const { t } = useTranslation();
  // "Şimdi çalıştır" haftalık özeti de gönderebilir: kart durumu yeniden okunsun.
  const [turSurumu, setTurSurumu] = useState(0);
  return (
    <div className="min-w-0 space-y-6" data-testid="oto-sistem">
      <div>
        <h3 className="text-lg font-semibold">{t('otomasyon.sistem.baslik')}</h3>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t('otomasyon.sistem.aciklama')}</p>
      </div>
      <HaftalikOzetKarti surum={turSurumu} />
      <YerlesikAkislar />
      <Suspense
        fallback={
          <div className="flex justify-center py-6 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" aria-label={t('otomasyon.yukleniyor')} />
          </div>
        }
      >
        <ZamanliGorevler onCalisti={() => setTurSurumu((x) => x + 1)} />
      </Suspense>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Yerleşik akışlar
// ---------------------------------------------------------------------------
const AKISLAR: { anahtar: string; arama: string; ikon: typeof Mail }[] = [
  { anahtar: 'talepCrm', arama: '?sekme=crm', ikon: Handshake },
  { anahtar: 'teklifKabul', arama: '?sekme=teklifler', ikon: FileCheck2 },
  { anahtar: 'destekKurallari', arama: '?sekme=tickets&bolum=kurallar', ikon: LifeBuoy },
  { anahtar: 'projeAsama', arama: '?sekme=projects', ikon: FolderKanban },
  { anahtar: 'bildirimler', arama: '?sekme=notify', ikon: BellRing },
  { anahtar: 'webhook', arama: '?sekme=api', ikon: Webhook },
];

function YerlesikAkislar() {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  return (
    <section className={`${KART} p-5`} data-testid="oto-yerlesik">
      <h4 className="font-semibold">{t('otomasyon.sistem.akis.baslik')}</h4>
      <p className="mt-1 text-xs text-muted-foreground">{t('otomasyon.sistem.akis.aciklama')}</p>
      <ul className="mt-3 divide-y divide-white/5">
        {AKISLAR.map(({ anahtar, arama, ikon: Ikon }) => (
          <li key={anahtar} className="flex flex-wrap items-start gap-x-3 gap-y-2 py-3" data-oto-akis={anahtar}>
            <Ikon className="mt-0.5 h-4 w-4 shrink-0 text-purple-300" aria-hidden="true" />
            <div className="min-w-0 flex-1 basis-56">
              <p className="text-sm font-medium">{t(`otomasyon.sistem.akis.${anahtar}.ad`)}</p>
              <p className="mt-0.5 text-xs text-muted-foreground">{t(`otomasyon.sistem.akis.${anahtar}.aciklama`)}</p>
            </div>
            <Link
              to={{ pathname, search: arama }}
              className={`${IKINCIL_DUGME} ms-7 px-2.5 py-1.5 text-xs sm:ms-0`}
              data-oto-akis-ayarla={anahtar}
            >
              {t('otomasyon.sistem.akis.ayarla')}
              <ExternalLink className="h-3.5 w-3.5 rtl:-scale-x-100" aria-hidden="true" />
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Haftalık özet
// ---------------------------------------------------------------------------
function tarihSaat(iso: string | null | undefined, dil: string): string {
  if (!iso) return '—';
  const an = new Date(iso);
  if (Number.isNaN(an.getTime())) return '—';
  try {
    return an.toLocaleString(dil, { weekday: 'short', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
  } catch {
    return an.toISOString().slice(0, 16).replace('T', ' ');
  }
}

function para(tutar: number, birim: string | null, dil: string): string {
  try {
    return new Intl.NumberFormat(dil, { style: 'currency', currency: (birim || 'TRY').toUpperCase() }).format(tutar);
  } catch {
    return `${tutar.toFixed(2)} ${birim || ''}`.trim();
  }
}

function HaftalikOzetKarti({ surum }: { surum: number }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [durum, setDurum] = useState<HaftalikOzetDurumu | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [onizleme, setOnizleme] = useState<HaftalikOzet | null>(null);
  const [mesgul, setMesgul] = useState<'onizle' | 'ayar' | null>(null);

  const yukle = useCallback(async () => {
    try {
      setDurum(await sistemApi.ozetDurumu());
      setHata(null);
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  }, [t]);

  useEffect(() => {
    void yukle();
  }, [yukle, surum]);

  const onizle = async () => {
    setMesgul('onizle');
    try {
      setOnizleme(await sistemApi.ozetOnizle());
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(null);
    }
  };

  const ayarla = async (acik: boolean) => {
    setMesgul('ayar');
    try {
      setDurum(await sistemApi.ozetAyarla(acik));
      toast.success(acik ? t('otomasyon.sistem.ozet.acildi') : t('otomasyon.sistem.ozet.kapandi'));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(null);
    }
  };

  const acik = !!durum?.acik;
  return (
    <section className={`${KART} p-5`} data-testid="oto-haftalik-ozet">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1 basis-60">
          <h4 className="flex items-center gap-2 font-semibold">
            <CalendarClock className="h-4 w-4 text-purple-300" aria-hidden="true" />
            {t('otomasyon.sistem.ozet.baslik')}
          </h4>
          <p className="mt-1 text-xs text-muted-foreground">{t('otomasyon.sistem.ozet.aciklama')}</p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={acik}
          disabled={!durum || mesgul !== null}
          onClick={() => void ayarla(!acik)}
          data-testid="oto-ozet-anahtar"
          className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400 disabled:opacity-50"
        >
          <span
            className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors ${
              acik ? 'bg-emerald-500/80' : 'bg-white/15'
            }`}
            aria-hidden="true"
          >
            <span
              className={`inline-block h-4 w-4 rounded-full bg-white shadow transition-transform ${
                acik ? 'translate-x-[18px] rtl:-translate-x-[18px]' : 'translate-x-0.5 rtl:-translate-x-0.5'
              }`}
            />
          </span>
          {acik ? t('otomasyon.sistem.ozet.acik') : t('otomasyon.sistem.ozet.kapali')}
        </button>
      </div>

      {hata && (
        <p className="mt-3 rounded-xl border border-red-400/30 bg-red-500/10 p-3 text-sm text-red-200" role="alert">
          {hata}
        </p>
      )}
      {!durum && !hata ? (
        <Loader2 className="mt-4 h-4 w-4 animate-spin text-muted-foreground" aria-label={t('otomasyon.yukleniyor')} />
      ) : durum ? (
        <>
          <dl className="mt-3 grid gap-x-6 gap-y-1 text-xs sm:grid-cols-[max-content_1fr]" data-testid="oto-ozet-durum">
            <dt className="text-muted-foreground">{t('otomasyon.sistem.ozet.sonGonderim')}</dt>
            <dd>{durum.son_gonderim ? tarihSaat(durum.son_gonderim, dil) : t('otomasyon.sistem.ozet.hicGonderilmedi')}</dd>
            <dt className="text-muted-foreground">{t('otomasyon.sistem.ozet.buHafta')}</dt>
            <dd data-bu-hafta={durum.bu_hafta}>{t(`otomasyon.sistem.ozet.durum.${durum.bu_hafta}`)}</dd>
            <dt className="text-muted-foreground">{t('otomasyon.sistem.ozet.sonraki')}</dt>
            <dd>
              {!acik
                ? t('otomasyon.sistem.ozet.kapaliyken')
                : durum.sonraki
                  ? tarihSaat(durum.sonraki, dil)
                  : t('otomasyon.sistem.ozet.ilkTurda')}
            </dd>
            <dt className="text-muted-foreground">{t('otomasyon.sistem.ozet.alicilar')}</dt>
            <dd>{t('otomasyon.sistem.ozet.aliciSayisi', { sayi: durum.alici_sayisi })}</dd>
          </dl>
          {durum.eposta_kanali !== 'hazir' && (
            <p className="mt-3 flex items-start gap-2 rounded-xl border border-amber-400/30 bg-amber-500/10 p-3 text-xs text-amber-100">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              {t('otomasyon.sistem.ozet.epostaYok')}
            </p>
          )}
          <p className="mt-3 text-[11px] text-muted-foreground">{t('otomasyon.sistem.ozet.tekKaynak')}</p>
        </>
      ) : null}

      <div className="mt-4 flex flex-wrap gap-2">
        <button type="button" className={IKINCIL_DUGME} onClick={() => void onizle()} disabled={mesgul !== null}
          data-testid="oto-ozet-onizle">
          {mesgul === 'onizle' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eye className="h-4 w-4" aria-hidden="true" />}
          {t('otomasyon.sistem.ozet.onizle')}
        </button>
      </div>

      {onizleme && <OzetOnizleme ozet={onizleme} />}
    </section>
  );
}

function OzetOnizleme({ ozet }: { ozet: HaftalikOzet }) {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const dolu = ozet.bolumler.filter((b) => b.sayi > 0);
  return (
    <div className="mt-4 space-y-3 border-t border-white/10 pt-4" data-testid="oto-ozet-onizleme">
      <p className="text-xs text-muted-foreground">{t('otomasyon.sistem.ozet.onizlemeNotu')}</p>
      {ozet.bos ? (
        <p className="rounded-xl border border-emerald-400/30 bg-emerald-500/10 p-3 text-sm text-emerald-100" data-testid="oto-ozet-bos">
          {t('otomasyon.sistem.ozet.bos')}
        </p>
      ) : (
        dolu.map((b) => (
          <article key={b.anahtar} className="rounded-xl border border-white/10 bg-black/20 p-3" data-ozet-bolum={b.anahtar}>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h5 className="text-sm font-semibold">
                {t(`otomasyon.sistem.ozet.bolum.${b.anahtar}`)}: <span className="text-purple-200">{b.sayi}</span>
              </h5>
              <Link to={{ pathname, search: `?sekme=${b.sekme}` }} className="text-xs text-purple-300 hover:underline"
                data-ozet-ac={b.sekme}>
                {t('otomasyon.sistem.ozet.panelde')}
              </Link>
            </div>
            <BolumEki bolum={b} />
            <ul className="mt-2 space-y-1 text-xs">
              {b.ornekler.map((s, i) => (
                <li key={i} className="min-w-0 break-words text-slate-200">
                  <OzetSatirMetni satir={s} />
                </li>
              ))}
              {b.sayi > b.ornekler.length && (
                <li className="text-muted-foreground">{t('otomasyon.sistem.ozet.dahaFazla', { sayi: b.sayi - b.ornekler.length })}</li>
              )}
            </ul>
          </article>
        ))
      )}
    </div>
  );
}

function BolumEki({ bolum }: { bolum: OzetBolumu }) {
  const { t, i18n } = useTranslation();
  const ek = bolum.ek || {};
  let metin = '';
  if (bolum.anahtar === 'faturalar' && ek.toplamlar?.length) {
    metin = t('otomasyon.sistem.ozet.ek.toplam', { tutar: ek.toplamlar.map((x) => para(x.tutar, x.para_birimi, i18n.language)).join(' · ') });
  } else if (bolum.anahtar === 'destek' && ek.sla_asildi) {
    metin = t('otomasyon.sistem.ozet.ek.sla', { sayi: ek.sla_asildi });
  } else if (bolum.anahtar === 'crm') {
    metin = t('otomasyon.sistem.ozet.ek.crm', { adim: ek.sonraki_adim ?? 0, hareketsiz: ek.hareketsiz ?? 0 });
  } else if (bolum.anahtar === 'belgeler' && ek.geciken) {
    metin = t('otomasyon.sistem.ozet.ek.geciken', { sayi: ek.geciken });
  } else if (bolum.anahtar === 'muhasebe') {
    metin = t('otomasyon.sistem.ozet.ek.muhasebe', { butce: ek.butce ?? 0, alacak: ek.alacak ?? 0 });
  } else if (bolum.anahtar === 'ortaklik' && (ek.basvuru || ek.talep)) {
    metin = t('otomasyon.sistem.ozet.ek.ortaklik', { basvuru: ek.basvuru ?? 0, talep: ek.talep ?? 0 });
  }
  return metin ? <p className="mt-0.5 text-xs text-muted-foreground">{metin}</p> : null;
}

const YENILEME_TURLERI = new Set(['alan', 'ssl', 'hosting']);

function OzetSatirMetni({ satir }: { satir: OzetSatiri }) {
  const { t, i18n } = useTranslation();
  const gun = satir.gun ?? 0;
  let durum = '';
  if (satir.tur && YENILEME_TURLERI.has(satir.tur)) {
    durum = `${t(`otomasyon.sistem.ozet.tur.${satir.tur}`)}: ${
      gun >= 0 ? t('otomasyon.sistem.ozet.satir.kaldi', { sayi: gun }) : t('otomasyon.sistem.ozet.satir.doldu', { sayi: -gun })
    }`;
  } else if (satir.tur === 'bekliyor') {
    durum = satir.gun === null ? t('otomasyon.sistem.ozet.satir.bekliyor') : t('otomasyon.sistem.ozet.satir.son_tarihe', { sayi: gun });
  } else if (satir.tur) {
    // Gün 0 ise varsa "_bugun" metni ("0 gündür açık" yerine "bugün açıldı").
    const bugun = `otomasyon.sistem.ozet.satir.${satir.tur}_bugun`;
    durum = !gun && i18n.exists(bugun) ? t(bugun) : t(`otomasyon.sistem.ozet.satir.${satir.tur}`, { sayi: gun, defaultValue: '' });
  }
  const parcalar = [satir.ad, satir.ayrinti, satir.tutar !== null ? para(satir.tutar, satir.para_birimi, i18n.language) : null, durum]
    .filter(Boolean)
    .join(' · ');
  return <bdi>{parcalar}</bdi>;
}
