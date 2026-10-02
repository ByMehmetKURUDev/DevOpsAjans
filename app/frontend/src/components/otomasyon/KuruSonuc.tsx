import { useTranslation } from 'react-i18next';
import { CheckCircle2, FlaskConical, X, XCircle } from 'lucide-react';

import { alanAdi, anahtarAdi, type KuruSonuc, type OtoMeta } from '@/lib/otomasyon';
import { DurumRozeti, OzetSatirlari } from './ortak';

/**
 * Kuru çalıştırma ("Test et") sonucu: koşulların tek tek sonucu ve her eylemin ne
 * YAPACAĞI (alıcı, konu, gövde…). Hiçbir eylem yapılmadı — sunucu bunu garanti ediyor.
 */
export default function KuruSonucGorunumu({
  sonuc,
  meta,
  tetik,
  onKapat,
}: {
  sonuc: KuruSonuc;
  meta: OtoMeta | null;
  tetik: string;
  onKapat?: () => void;
}) {
  const { t } = useTranslation();
  const sema = meta?.olaylar.find((o) => o.anahtar === tetik)?.sema ?? [];
  return (
    <div className="rounded-xl border border-sky-400/30 bg-sky-500/[0.06] p-3 text-sm" data-testid="oto-kuru-sonuc" role="status">
      <div className="mb-2 flex items-start justify-between gap-2">
        <p className="flex items-center gap-1.5 font-medium text-sky-100">
          <FlaskConical className="h-4 w-4" aria-hidden="true" />
          {t('otomasyon.test.baslik')}
          <span className="text-xs font-normal text-muted-foreground">({t(`otomasyon.test.kaynak.${sonuc.kaynak}`)})</span>
        </p>
        {onKapat && (
          <button type="button" className="rounded p-1 hover:bg-white/10" onClick={onKapat} aria-label={t('otomasyon.kapat')}>
            <X className="h-4 w-4" />
          </button>
        )}
      </div>
      <p className="mb-2 text-xs text-muted-foreground">{t('otomasyon.test.aciklama')}</p>
      <p className="flex items-center gap-1.5" data-testid="oto-kuru-kosul" data-sonuc={sonuc.kosul_sonucu ? 'dogru' : 'yanlis'}>
        {sonuc.kosul_sonucu ? (
          <CheckCircle2 className="h-4 w-4 text-emerald-300" aria-hidden="true" />
        ) : (
          <XCircle className="h-4 w-4 text-amber-300" aria-hidden="true" />
        )}
        {sonuc.kosul_sonucu ? t('otomasyon.test.kosulTuttu') : t('otomasyon.test.kosulTutmadi')}
      </p>
      {sonuc.kosul_ayrinti.length > 0 && (
        <ul className="mt-1 space-y-0.5 ps-6 text-xs text-muted-foreground">
          {sonuc.kosul_ayrinti.map((k, i) => (
            <li key={i}>
              {k.sonuc ? '✓' : '✗'} {alanAdi(t, sema.find((a) => a.yol === k.alan), k.alan)} {t(`otomasyon.islec.${k.islec}`)}{' '}
              {k.deger ?? ''} <span className="opacity-70">({t('otomasyon.test.gercek')}: {k.gercek === null || k.gercek === undefined ? '—' : String(k.gercek)})</span>
            </li>
          ))}
        </ul>
      )}
      <ol className="mt-3 space-y-2">
        {sonuc.eylemler.map((e) => (
          <li key={e.sira} className="rounded-lg border border-white/10 bg-black/20 p-2" data-oto-kuru-eylem={e.tur} data-durum={e.durum}>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-medium">
                {e.sira + 1}. {t(`otomasyon.eylem.${e.tur}`)}
              </span>
              <DurumRozeti durum={e.durum} metin={t(`otomasyon.durum.${e.durum}`)} />
              {e.neden && <span className="text-[11px] text-muted-foreground">{t(`otomasyon.neden.${anahtarAdi(e.neden)}`, { defaultValue: e.neden })}</span>}
            </div>
            <OzetSatirlari ozet={e.ozet} />
          </li>
        ))}
      </ol>
      {sonuc.bilinmeyen_degiskenler.length > 0 && (
        <p className="mt-2 text-xs text-amber-200">
          {t('otomasyon.test.bilinmeyen')}: {sonuc.bilinmeyen_degiskenler.map((d) => `{{${d}}}`).join(', ')}
        </p>
      )}
    </div>
  );
}
