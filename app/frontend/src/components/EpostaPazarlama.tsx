import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, BarChart3, Layers, ListChecks, Mail, Send, Settings2, ShieldCheck, Users, Workflow } from 'lucide-react';

import { Yukleniyor } from '@/components/epostaPazarlama/ortak';
import { hataMetni, pazarlamaApi, type Meta, type PazarlamaMod } from '@/lib/epostaPazarlama';

const Ozet = lazy(() => import('@/components/epostaPazarlama/Ozet'));
const Kisiler = lazy(() => import('@/components/epostaPazarlama/Kisiler'));
const Listeler = lazy(() => import('@/components/epostaPazarlama/Listeler'));
const Segmentler = lazy(() => import('@/components/epostaPazarlama/Segmentler'));
const Kampanyalar = lazy(() => import('@/components/epostaPazarlama/Kampanyalar'));
const Diziler = lazy(() => import('@/components/epostaPazarlama/Diziler'));
const Ayarlar = lazy(() => import('@/components/epostaPazarlama/Ayarlar'));

/**
 * Faz 5M — "E-posta pazarlama" sekmesi. Yönetici panelinde (`mod="yonetici"`: ajansın
 * kendi listeleri + müşteri hesaplarının gönderim sağlığı) ve müşteri panelinde
 * (`mod="musteri"`: etkin hesap) aynı bileşen.
 *
 * Alt sekmeler: özet, kişiler (izin kaydı, CSV, bastırma), listeler ve abonelik formları,
 * segmentler, kampanyalar (blok düzenleyici, test, zamanlama, A/B, rapor), damla dizileri,
 * ayarlar (gönderen kimliği, takip, İYS bilgisi).
 */

type AltSekme = 'ozet' | 'kisiler' | 'listeler' | 'segmentler' | 'kampanyalar' | 'diziler' | 'ayarlar';
const ALT_SEKMELER: { anahtar: AltSekme; ikon: typeof Layers }[] = [
  { anahtar: 'ozet', ikon: BarChart3 },
  { anahtar: 'kampanyalar', ikon: Send },
  { anahtar: 'kisiler', ikon: Users },
  { anahtar: 'listeler', ikon: ListChecks },
  { anahtar: 'segmentler', ikon: Layers },
  { anahtar: 'diziler', ikon: Workflow },
  { anahtar: 'ayarlar', ikon: Settings2 },
];

export default function EpostaPazarlama({ mod }: { mod: PazarlamaMod }) {
  const { t } = useTranslation();
  const api = useMemo(() => pazarlamaApi(mod), [mod]);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [alt, setAlt] = useState<AltSekme>(() => {
    try {
      const s = new URLSearchParams(window.location.search).get('alt') as AltSekme | null;
      return s && ALT_SEKMELER.some((x) => x.anahtar === s) ? s : 'ozet';
    } catch {
      return 'ozet';
    }
  });

  const metaYukle = useCallback(async () => {
    try {
      setMeta(await api.meta());
      setHata(null);
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  }, [api, t]);

  useEffect(() => {
    void metaYukle();
  }, [metaYukle]);

  const uyarilar: { anahtar: string; metin: string }[] = [];
  if (meta) {
    if (!meta.resend_kurulu) uyarilar.push({ anahtar: 'resend', metin: t('epostaPazarlama.uyari.resendYok') });
    if (meta.kimlik.eksik.length)
      uyarilar.push({
        anahtar: 'kimlik',
        metin: meta.yonetici ? t('epostaPazarlama.uyari.kimlikEksik') : t('epostaPazarlama.uyari.kimlikEksikMusteri'),
      });
    if (meta.sahte_mod) uyarilar.push({ anahtar: 'sahte', metin: t('epostaPazarlama.uyari.sahteMod') });
  }

  return (
    <section data-testid="eposta-pazarlama" data-mod={mod} className="min-w-0">
      <div className="mb-5">
        <h2 className="flex items-center gap-2 text-2xl font-bold" id="eposta-pazarlama-baslik">
          <Mail className="h-6 w-6 text-purple-300" aria-hidden="true" />
          {t('epostaPazarlama.baslik')}
        </h2>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t('epostaPazarlama.aciklama')}</p>
      </div>

      {hata && (
        <p className="mb-4 rounded-xl border border-rose-400/30 bg-rose-400/10 px-4 py-3 text-sm text-rose-200" role="alert">
          {hata}
        </p>
      )}
      {uyarilar.map((u) => (
        <p
          key={u.anahtar}
          className="mb-3 flex items-start gap-2 rounded-xl border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-100"
          data-testid={`ep-uyari-${u.anahtar}`}
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{u.metin}</span>
        </p>
      ))}

      <div className="-mx-1 mb-5 flex gap-1 overflow-x-auto pb-1" role="tablist" aria-label={t('epostaPazarlama.baslik')}>
        {ALT_SEKMELER.map(({ anahtar, ikon: Ikon }) => (
          <button
            key={anahtar}
            type="button"
            role="tab"
            aria-selected={alt === anahtar}
            onClick={() => setAlt(anahtar)}
            data-ep-alt={anahtar}
            className={`flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-2 text-sm transition-colors ${
              alt === anahtar ? 'bg-purple-500/20 text-white ring-1 ring-purple-400/40' : 'text-muted-foreground hover:bg-white/5 hover:text-white'
            }`}
          >
            <Ikon className="h-4 w-4" aria-hidden="true" />
            {t(`epostaPazarlama.alt.${anahtar}`)}
          </button>
        ))}
      </div>

      {!meta && !hata ? (
        <Yukleniyor />
      ) : meta ? (
        <Suspense fallback={<Yukleniyor />}>
          {alt === 'ozet' && <Ozet api={api} meta={meta} gecis={(s) => setAlt(s as AltSekme)} />}
          {alt === 'kisiler' && <Kisiler api={api} meta={meta} />}
          {alt === 'listeler' && <Listeler api={api} meta={meta} />}
          {alt === 'segmentler' && <Segmentler api={api} meta={meta} />}
          {alt === 'kampanyalar' && <Kampanyalar api={api} meta={meta} />}
          {alt === 'diziler' && <Diziler api={api} meta={meta} />}
          {alt === 'ayarlar' && <Ayarlar api={api} meta={meta} yenile={metaYukle} />}
        </Suspense>
      ) : null}

      <p className="mt-6 flex items-start gap-2 text-xs text-muted-foreground">
        <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <span>{t('epostaPazarlama.yasalNot')}</span>
      </p>
    </section>
  );
}
