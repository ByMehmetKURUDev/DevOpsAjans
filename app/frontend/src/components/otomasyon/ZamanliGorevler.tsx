import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, Clock, KeyRound, Loader2, Play, Timer } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { tarihBicimle, zamanliCalistir, zamanliDurum, type ZamanliDurum } from '@/lib/siteBakim';

/**
 * "Zamanlı görevler" kartı (Faz 2A). Faz 7O'dan beri Yönetici › Otomasyon › Sistem altında (Site
 * Ayarları'ndan taşındı); metinleri `siteBakim` ek paketinde.
 *
 * Ücretsiz sunucuda zamanlayıcı yok; GitHub Actions her 10 dakikada
 * `/api/v1/zamanli/calistir` ucunu çağırıyor. Bu kart her görevin ne yaptığını
 * (tek cümle), son çalışmasını, süresini, özetini ve (varsa) hatasını gösteriyor;
 * "Şimdi çalıştır" 5 dakika kuralını ve görev sıklıklarını atlıyor (haftalık özet
 * kendi takvimine uyar: aynı hafta ikinci kez gitmez).
 */
export default function ZamanliGorevler({ onCalisti }: { onCalisti?: () => void } = {}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [durum, setDurum] = useState<ZamanliDurum | null>(null);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [calisiyor, setCalisiyor] = useState(false);

  const yukle = useCallback(async () => {
    try {
      setDurum(await zamanliDurum());
    } catch {
      setDurum(null);
    } finally {
      setYukleniyor(false);
    }
  }, []);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const calistir = async () => {
    setCalisiyor(true);
    try {
      const d = await zamanliCalistir();
      setDurum(d);
      if (d.atlandi) toast.message(t('siteBakim.zamanli.atlandi'));
      else toast.success(t('siteBakim.zamanli.calisti'));
      onCalisti?.();
    } catch {
      toast.error(t('siteBakim.hata.genel'));
    } finally {
      setCalisiyor(false);
    }
  };

  const siklik = (dk: number, plan?: string | null) => {
    if (plan) return t(`siteBakim.zamanli.plan.${plan}`, { defaultValue: t('siteBakim.zamanli.haftalik') });
    if (!dk) return t('siteBakim.zamanli.herTur');
    // Sunucudaki pencere kaymaya pay bırakıyor (20 sa ≈ günlük, 6 gün 20 sa ≈ haftalık).
    if (dk >= 1200 && dk < 2880) return t('siteBakim.zamanli.gunluk');
    if (dk >= 9000 && dk <= 10080) return t('siteBakim.zamanli.haftalik');
    if (dk >= 1440) return t('siteBakim.zamanli.gun', { sayi: Math.round(dk / 1440) });
    if (dk >= 60) return t('siteBakim.zamanli.saat', { sayi: Math.round(dk / 60) });
    return t('siteBakim.zamanli.dk', { sayi: dk });
  };

  const ozetMetni = (sonuc: Record<string, unknown> | null) =>
    sonuc
      ? Object.entries(sonuc)
          .filter(([, v]) => typeof v === 'number' || typeof v === 'string')
          .map(([k, v]) => `${k}: ${v}`)
          .join(' · ')
      : '';

  return (
    <div className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-5" data-testid="zamanli-karti">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="flex items-center gap-2 font-semibold">
            <Timer className="h-4 w-4" />
            {t('siteBakim.zamanli.baslik')}
          </h3>
          <p className="mt-1 text-xs text-muted-foreground">{t('siteBakim.zamanli.aciklama')}</p>
        </div>
        <Button size="sm" onClick={() => void calistir()} disabled={calisiyor} data-testid="zamanli-calistir">
          {calisiyor ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
          {t('siteBakim.zamanli.calistir')}
        </Button>
      </div>

      {yukleniyor ? (
        <Loader2 className="mt-4 h-4 w-4 animate-spin text-muted-foreground" />
      ) : !durum ? (
        <p className="mt-4 text-sm text-muted-foreground">{t('siteBakim.hata.yuklenemedi')}</p>
      ) : (
        <>
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <Clock className="h-3.5 w-3.5" />
              {t('siteBakim.zamanli.sonCalisma')}:{' '}
              {durum.genel.son_calisma ? tarihBicimle(durum.genel.son_calisma, dil, true) : t('siteBakim.zamanli.hic')}
            </span>
            {durum.genel.calisiyor && <span className="text-amber-300">{t('siteBakim.zamanli.calisiyor')}</span>}
            <span className="inline-flex items-center gap-1">
              <KeyRound className="h-3.5 w-3.5" />
              {durum.anahtar_tanimli ? t('siteBakim.zamanli.anahtarVar') : t('siteBakim.zamanli.anahtarYok')}
            </span>
          </div>
          <ul className="mt-3 divide-y divide-white/5">
            {durum.gorevler.map((g) => (
              <li key={g.gorev} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-xs" data-testid={`zamanli-${g.gorev}`}>
                {g.hata ? (
                  <AlertTriangle className="h-4 w-4 shrink-0 text-red-400" aria-label={t('siteBakim.zamanli.hatali')} />
                ) : g.son_calisma ? (
                  <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" aria-label={t('siteBakim.zamanli.basarili')} />
                ) : (
                  <Clock className="h-4 w-4 shrink-0 text-muted-foreground" />
                )}
                <span className="min-w-0 flex-1 basis-40 font-medium">
                  {t(`siteBakim.zamanli.gorev.${g.gorev}`, { defaultValue: g.gorev })}
                </span>
                <span className="text-muted-foreground">
                  {t('siteBakim.zamanli.siklik')}: {siklik(g.siklik_dk, g.plan)}
                </span>
                <span className="text-muted-foreground">
                  {g.son_calisma ? tarihBicimle(g.son_calisma, dil, true) : t('siteBakim.zamanli.hic')}
                </span>
                {g.sure_ms !== null && <span className="text-muted-foreground">{g.sure_ms} ms</span>}
                {/* Faz 7O: sade dilde "bu iş ne yapar" (teknik olmayan kullanıcı için). */}
                <span className="w-full ps-7 text-[11px] leading-snug text-slate-300" data-zamanli-ne={g.gorev}>
                  {t(`siteBakim.zamanli.ne.${g.gorev}`, { defaultValue: '' })}
                </span>
                {ozetMetni(g.sonuc) && (
                  <span className="w-full break-words font-mono text-[11px] text-muted-foreground">{ozetMetni(g.sonuc)}</span>
                )}
                {g.hata && <span className="w-full break-words text-[11px] text-red-300">{g.hata}</span>}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
