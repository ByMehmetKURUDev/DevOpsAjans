import { useState } from 'react';
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  ExternalLink,
  Info,
  Link2Off,
  Loader2,
  XCircle,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { taramayiCalistir, type Seviye, type TaramaRaporu } from '@/lib/siteTaramasi';

/**
 * Ajan tabanlı tarama paneli.
 *
 * PageSpeed tek sayfanın hızını, Search Console Google'ın gördüğünü
 * söylüyor. Bu ise sitenin kendi içindeki eksikleri söylüyor: başlığı
 * olmayan sayfa, iki H1, 404 veren menü bağlantısı. Hepsi her yayından
 * sonra elle bakılacak şeyler; bakılmadığı için de fark edilmiyor.
 *
 * Tarama onlarca istek demek ve arka uç ücretsiz katmanda uyuyor olabilir;
 * ilk istek sunucuyu uyandırırken uzun sürüyor. O yüzden düğme çalışırken
 * kilitli ve beklemenin sebebi yazıyor.
 */

const SEVIYE_SIRASI: Seviye[] = ['hata', 'uyari', 'bilgi'];

const SEVIYE_BICIMI: Record<Seviye, { renk: string; Ikon: typeof AlertTriangle }> = {
  hata: { renk: 'text-red-300', Ikon: XCircle },
  uyari: { renk: 'text-amber-300', Ikon: AlertTriangle },
  bilgi: { renk: 'text-sky-300', Ikon: Info },
};

function kisaYol(tam: string, site: string): string {
  const yol = tam.startsWith(site) ? tam.slice(site.length) : tam;
  return yol || '/';
}

export default function SiteTaramasi() {
  const { t } = useTranslation();
  const [calisiyor, setCalisiyor] = useState(false);
  const [rapor, setRapor] = useState<TaramaRaporu | null>(null);

  const basla = async () => {
    setCalisiyor(true);
    try {
      const sonuc = await taramayiCalistir();
      setRapor(sonuc);
      const hata = sonuc.ozet.hata || 0;
      if (hata > 0) toast.warning(t('siteTarama.bitti', { count: hata }));
      else toast.success(t('siteTarama.temiz'));
    } catch {
      toast.error(t('siteTarama.hata'));
    } finally {
      setCalisiyor(false);
    }
  };

  const sorunlu = rapor ? rapor.sayfalar.filter((s) => s.bulgular.length > 0) : [];
  const temizSayisi = rapor ? rapor.sayfalar.length - sorunlu.length : 0;

  return (
    <div className="glass rounded-2xl p-5">
      <div className="mb-1 flex items-center gap-2">
        <Bot className="h-4 w-4 text-purple-300" />
        <h3 className="text-sm font-semibold">{t('siteTarama.baslik')}</h3>
      </div>
      <p className="mb-4 text-xs text-muted-foreground">{t('siteTarama.aciklama')}</p>

      <Button
        onClick={basla}
        disabled={calisiyor}
        className="h-11 border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white"
      >
        {calisiyor ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            {t('siteTarama.calisiyor')}
          </>
        ) : (
          t('siteTarama.basla')
        )}
      </Button>

      {calisiyor && (
        <p className="mt-2 text-xs text-muted-foreground">{t('siteTarama.bekleyin')}</p>
      )}

      {rapor && (
        <div className="mt-5 space-y-4">
          <div className="flex flex-wrap gap-2 text-xs">
            <span className="rounded-full bg-white/5 px-3 py-1">
              {t('siteTarama.ozetSayfa', { count: rapor.sayfa_sayisi })}
            </span>
            <span className="rounded-full bg-white/5 px-3 py-1">
              {t('siteTarama.ozetBaglanti', { count: rapor.baglanti_sayisi })}
            </span>
            <span className="rounded-full bg-red-500/10 px-3 py-1 text-red-300">
              {t('siteTarama.ozetHata', { count: rapor.ozet.hata || 0 })}
            </span>
            <span className="rounded-full bg-amber-500/10 px-3 py-1 text-amber-300">
              {t('siteTarama.ozetUyari', { count: rapor.ozet.uyari || 0 })}
            </span>
            <span className="rounded-full bg-white/5 px-3 py-1 text-muted-foreground">
              {t('siteTarama.ozetSure', { sn: (rapor.sure_ms / 1000).toFixed(1) })}
            </span>
          </div>

          {rapor.notlar.map((n) => (
            <p key={n} className="text-xs text-muted-foreground">
              {n}
            </p>
          ))}

          {rapor.kirik_baglantilar.length > 0 && (
            <div className="rounded-xl border border-red-400/30 bg-red-500/[0.06] p-4">
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-red-200">
                <Link2Off className="h-4 w-4" />
                {t('siteTarama.kirik', { count: rapor.kirik_baglantilar.length })}
              </div>
              <ul className="space-y-2">
                {rapor.kirik_baglantilar.map((k) => (
                  <li key={k.url} className="text-xs">
                    <span className="font-mono break-all">{kisaYol(k.url, rapor.site)}</span>
                    <span className="ml-2 text-red-300">
                      {k.durum === 0 ? t('siteTarama.ulasilamadi') : k.durum}
                    </span>
                    {k.kaynaklar.length > 0 && (
                      <span className="block text-muted-foreground">
                        {t('siteTarama.gectigiYer')}{' '}
                        {k.kaynaklar.map((s) => kisaYol(s, rapor.site)).join(', ')}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {sorunlu.length === 0 && rapor.kirik_baglantilar.length === 0 ? (
            <div className="flex items-center gap-2 rounded-xl border border-emerald-400/30 bg-emerald-500/[0.06] p-4 text-sm text-emerald-200">
              <CheckCircle2 className="h-4 w-4" />
              {t('siteTarama.temiz')}
            </div>
          ) : (
            <div className="space-y-2">
              {sorunlu.map((s) => (
                <div
                  key={s.url}
                  className="rounded-xl border border-white/10 bg-white/[0.03] p-3"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <a
                      href={s.url}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center gap-1 font-mono text-xs font-semibold break-all hover:text-purple-300"
                    >
                      {kisaYol(s.url, rapor.site)}
                      <ExternalLink className="h-3 w-3 flex-none" aria-hidden="true" />
                    </a>
                    <span className="text-[11px] text-muted-foreground">
                      {s.durum || '—'} · {s.sure_ms} ms · {Math.round(s.boyut / 1024)} KB
                    </span>
                  </div>
                  <ul className="mt-2 space-y-1">
                    {[...s.bulgular]
                      .sort(
                        (a, b) =>
                          SEVIYE_SIRASI.indexOf(a.seviye) - SEVIYE_SIRASI.indexOf(b.seviye),
                      )
                      .map((b, i) => {
                        const bicim = SEVIYE_BICIMI[b.seviye] || SEVIYE_BICIMI.bilgi;
                        const Ikon = bicim.Ikon;
                        return (
                          <li
                            key={`${b.kod}-${i}`}
                            className="flex items-start gap-2 text-xs leading-snug"
                          >
                            <Ikon
                              className={`mt-0.5 h-3.5 w-3.5 flex-none ${bicim.renk}`}
                              aria-hidden="true"
                            />
                            <span>{b.mesaj}</span>
                          </li>
                        );
                      })}
                  </ul>
                </div>
              ))}
              {temizSayisi > 0 && (
                <p className="text-xs text-muted-foreground">
                  {t('siteTarama.temizSayisi', { count: temizSayisi })}
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
