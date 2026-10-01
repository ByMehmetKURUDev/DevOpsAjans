import { useCallback, useEffect, useState } from 'react';
import { Loader2, RefreshCw, ShieldQuestion, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { goreliZaman, tamZaman } from '@/lib/denetim';
import { cspRaporlari, cspRaporlariniTemizle, type CspRaporu } from '@/lib/guvenlik';

/**
 * Yönetici paneli › Güvenlik › CSP ihlal raporları (Faz 4G).
 *
 * Sitenin İçerik Güvenliği Politikası zorunlu modda. Tarayıcılar politikaya
 * takılan her kaynağı `/api/v1/csp-rapor`'a bildiriyor; son 500 farklı ihlal
 * burada (aynı ihlal bir saat içinde tekrarlanırsa sayaç artıyor). Liste boşsa
 * site sorunsuz çalışıyor demektir; yeni bir analitik/reklam alan adı ya da
 * değişen bir satır içi betik burada görünür. Kişisel veri saklanmıyor.
 */
export default function CspRaporlari() {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [satirlar, setSatirlar] = useState<CspRaporu[]>([]);
  const [toplam, setToplam] = useState(0);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [hata, setHata] = useState(false);
  const [siliniyor, setSiliniyor] = useState(false);

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    setHata(false);
    try {
      const g = await cspRaporlari(100);
      setSatirlar(g.items);
      setToplam(g.toplam);
    } catch {
      setHata(true);
    } finally {
      setYukleniyor(false);
    }
  }, []);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const temizle = async () => {
    if (!window.confirm(t('guvenlik.csp.temizleOnay'))) return;
    setSiliniyor(true);
    try {
      await cspRaporlariniTemizle();
      toast.success(t('guvenlik.csp.temizlendi'));
      await yukle();
    } catch {
      toast.error(t('guvenlik.csp.hata'));
    } finally {
      setSiliniyor(false);
    }
  };

  return (
    <section className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6" aria-labelledby="csp-raporlari-baslik" data-testid="csp-raporlari">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 id="csp-raporlari-baslik" className="flex items-center gap-2 font-semibold">
            <ShieldQuestion className="h-5 w-5 text-purple-400" aria-hidden="true" />
            {t('guvenlik.csp.baslik')}
          </h3>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t('guvenlik.csp.aciklama')}</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="icon" onClick={() => void yukle()} aria-label={t('guvenlik.yenile')}>
            <RefreshCw className={`h-4 w-4 ${yukleniyor ? 'animate-spin' : ''}`} aria-hidden="true" />
          </Button>
          {satirlar.length > 0 && (
            <Button variant="outline" size="sm" className="h-10 gap-1" disabled={siliniyor} onClick={() => void temizle()} data-testid="csp-temizle">
              {siliniyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Trash2 className="h-4 w-4" aria-hidden="true" />}
              {t('guvenlik.csp.temizle')}
            </Button>
          )}
        </div>
      </div>

      <div className="mt-4">
        {yukleniyor && satirlar.length === 0 ? (
          <div className="flex justify-center py-6 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
          </div>
        ) : hata ? (
          <p className="text-sm text-red-300">{t('guvenlik.csp.hata')}</p>
        ) : satirlar.length === 0 ? (
          <p className="rounded-xl border border-dashed border-white/10 p-4 text-center text-sm text-muted-foreground" data-testid="csp-bos">
            {t('guvenlik.csp.bos')}
          </p>
        ) : (
          <>
            <ul className="space-y-2" data-testid="csp-liste">
              {satirlar.map((r) => (
                <li key={r.id} className="rounded-xl border border-white/10 px-3 py-2 text-sm" data-csp-yonerge={r.yonerge}>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded bg-red-500/15 px-1.5 py-0.5 font-mono text-[11px] text-red-200">{r.yonerge}</span>
                    <span className="min-w-0 flex-1 break-all font-mono text-xs" dir="ltr">
                      {r.engellenen || '—'}
                    </span>
                    {r.sayi > 1 && <span className="text-[11px] text-muted-foreground">×{r.sayi}</span>}
                    <span className="rounded-full border border-white/15 px-2 py-0.5 text-[11px] text-muted-foreground">
                      {r.mod === 'report' ? t('guvenlik.csp.modRapor') : t('guvenlik.csp.modEngel')}
                    </span>
                  </div>
                  <p className="mt-1 break-all text-[11px] text-muted-foreground" dir="ltr">
                    {r.belge}
                    {r.kaynak_dosya ? ` · ${r.kaynak_dosya}${r.satir ? `:${r.satir}` : ''}` : ''}
                    {r.ornek ? ` · “${r.ornek}”` : ''}
                  </p>
                  <p className="text-[11px] text-muted-foreground" title={tamZaman(r.son_at, dil)}>
                    {t('guvenlik.csp.son', { zaman: goreliZaman(r.son_at, dil) })}
                  </p>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-muted-foreground">{t('guvenlik.csp.gosterilen', { sayi: satirlar.length, toplam })}</p>
          </>
        )}
      </div>
    </section>
  );
}
