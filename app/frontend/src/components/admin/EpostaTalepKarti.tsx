import { useCallback, useEffect, useState } from 'react';
import { CheckCircle2, Copy, Inbox, Loader2, RefreshCw, Save, XCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  EpostaHatasi,
  epostaAyarlari,
  epostaAyarlariKaydet,
  gelenEpostalar,
  type EpostaAyarlari,
  type GelenEposta,
} from '@/lib/destekEposta';

/**
 * Yönetici › Destek › Ayarlar › "E-postadan talep" (Faz 2F).
 *
 * Kurulum durumu (anahtarlar tanımlı mı — DEĞERLERİ gösterilmez), webhook
 * adresleri (kopyala), gelen destek adresi (`destek_gelen_adres`, gizli
 * değil) ve sorun ayıklamak için son gelen e-postalar.
 */

const KART = 'cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6';
const DURUM_RENK: Record<string, string> = {
  islendi: 'bg-emerald-500/15 text-emerald-300',
  yoksayildi: 'bg-white/10 text-muted-foreground',
  hata: 'bg-red-500/15 text-red-300',
  isleniyor: 'bg-sky-500/15 text-sky-300',
};

function Durum({ tanimli, etiket }: { tanimli: boolean; etiket: string }) {
  const { t } = useTranslation();
  return (
    <li className="flex items-center justify-between gap-3 py-1.5 text-sm">
      <span>{etiket}</span>
      <span className={`flex items-center gap-1 text-xs ${tanimli ? 'text-emerald-300' : 'text-amber-300'}`}>
        {tanimli ? <CheckCircle2 className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}
        {tanimli ? t('destekKurallari.eposta.tanimli') : t('destekKurallari.eposta.tanimsiz')}
      </span>
    </li>
  );
}

export default function EpostaTalepKarti() {
  const { t, i18n } = useTranslation();
  const [ayar, setAyar] = useState<EpostaAyarlari | null>(null);
  const [adres, setAdres] = useState('');
  const [kaydediliyor, setKaydediliyor] = useState(false);
  const [gelenler, setGelenler] = useState<GelenEposta[] | null>(null);

  const hata = useCallback(
    (h: unknown) => {
      const kod = h instanceof EpostaHatasi ? h.kod : 'genel';
      toast.error(t(`destekKurallari.hata.${kod}`, { defaultValue: t('destekKurallari.hata.genel') }));
    },
    [t]
  );

  const gelenleriYukle = useCallback(() => {
    setGelenler(null);
    gelenEpostalar()
      .then((g) => setGelenler(g.slice(0, 50)))
      .catch((h) => {
        setGelenler([]);
        hata(h);
      });
  }, [hata]);

  useEffect(() => {
    epostaAyarlari()
      .then((a) => {
        setAyar(a);
        setAdres(a.gelen_adres);
      })
      .catch(hata);
    gelenleriYukle();
  }, [hata, gelenleriYukle]);

  const kaydet = async () => {
    setKaydediliyor(true);
    try {
      const a = await epostaAyarlariKaydet(adres.trim());
      setAyar(a);
      setAdres(a.gelen_adres);
      toast.success(t('destekKurallari.eposta.kaydedildi'));
    } catch (h) {
      hata(h);
    } finally {
      setKaydediliyor(false);
    }
  };

  const kopyala = (metin: string) => {
    void navigator.clipboard?.writeText(metin).then(
      () => toast.success(t('destekKurallari.eposta.kopyalandi')),
      () => toast.error(t('destekKurallari.hata.genel'))
    );
  };

  const zaman = (d: string | null) => {
    if (!d) return '—';
    const x = new Date(d);
    return Number.isNaN(x.getTime())
      ? '—'
      : x.toLocaleString(i18n.language, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
  };

  return (
    <section className={`${KART} lg:col-span-2`} data-testid="eposta-talep-karti">
      <h3 className="flex items-center gap-2 font-semibold">
        <Inbox className="h-4 w-4 text-sky-300" aria-hidden="true" /> {t('destekKurallari.eposta.baslik')}
      </h3>
      <p className="mt-1 text-sm text-muted-foreground">{t('destekKurallari.eposta.aciklama')}</p>

      {!ayar ? (
        <div className="flex justify-center py-8">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <div className="mt-4 grid gap-6 lg:grid-cols-2">
          <div className="space-y-4">
            <ul className="divide-y divide-white/5 rounded-xl border border-white/10 px-3" aria-label={t('destekKurallari.eposta.durum')}>
              <Durum tanimli={ayar.resend_imza_tanimli} etiket={t('destekKurallari.eposta.resendImza')} />
              <Durum tanimli={ayar.resend_api_tanimli} etiket={t('destekKurallari.eposta.resendApi')} />
              <Durum tanimli={Boolean(ayar.gelen_adres)} etiket={t('destekKurallari.eposta.gelenAdres')} />
              <Durum tanimli={ayar.genel_anahtar_tanimli} etiket={t('destekKurallari.eposta.genelAnahtar')} />
            </ul>
            {(
              [
                ['resend', ayar.webhook.resend, 'destekKurallari.eposta.webhookResend'],
                ['genel', ayar.webhook.genel, 'destekKurallari.eposta.webhookGenel'],
              ] as const
            ).map(([k, adr, etiket]) => (
              <div key={k}>
                <p className="mb-1 text-xs text-muted-foreground">{t(etiket)}</p>
                <div className="flex gap-2">
                  <code className="flex-1 truncate rounded-md border border-white/10 bg-black/30 px-2 py-1.5 text-xs" dir="ltr">
                    {adr}
                  </code>
                  <Button size="sm" variant="ghost" onClick={() => kopyala(adr)} aria-label={t('destekKurallari.eposta.kopyala')}>
                    <Copy className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))}
            <label className="block text-xs text-muted-foreground">
              {t('destekKurallari.eposta.gelenAdres')}
              <div className="mt-1 flex gap-2">
                <Input
                  value={adres}
                  onChange={(e) => setAdres(e.target.value)}
                  placeholder="destek@destek.mehmetkuru.dev"
                  className="bg-white/5"
                  dir="ltr"
                  data-testid="gelen-adres"
                />
                <Button onClick={() => void kaydet()} disabled={kaydediliyor} className="gap-2" data-testid="gelen-adres-kaydet">
                  {kaydediliyor ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                  {t('destekKurallari.kaydet')}
                </Button>
              </div>
              <span className="mt-1 block">{t('destekKurallari.eposta.gelenAdresIpucu')}</span>
            </label>
            <p className="text-xs text-muted-foreground">
              {t('destekKurallari.eposta.sinirlar', {
                saatlik: ayar.sinirlar.saatlik,
                mb: ayar.sinirlar.ek_mb,
                adet: ayar.sinirlar.ek_sayisi,
              })}
            </p>
            <p className="text-xs text-muted-foreground">{t('destekKurallari.eposta.kurulumNotu')}</p>
          </div>

          <div>
            <div className="mb-2 flex items-center justify-between gap-2">
              <p className="text-sm font-medium">{t('destekKurallari.eposta.sonGelenler')}</p>
              <Button size="sm" variant="ghost" className="gap-1 text-xs" onClick={gelenleriYukle}>
                <RefreshCw className="h-3.5 w-3.5" /> {t('destekKurallari.eposta.yenile')}
              </Button>
            </div>
            {gelenler === null ? (
              <div className="flex justify-center py-6">
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              </div>
            ) : gelenler.length === 0 ? (
              <p className="text-sm text-muted-foreground" data-testid="gelen-bos">
                {t('destekKurallari.eposta.yok')}
              </p>
            ) : (
              <ul className="max-h-96 divide-y divide-white/5 overflow-y-auto rounded-xl border border-white/10" data-testid="gelen-liste">
                {gelenler.map((g) => (
                  <li key={g.id} className="px-3 py-2 text-sm">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`rounded-full px-2 py-0.5 text-[10px] uppercase tracking-widest ${DURUM_RENK[g.durum] || ''}`}>
                        {t(`destekKurallari.eposta.durumlar.${g.durum}`, { defaultValue: g.durum })}
                      </span>
                      <span className="min-w-0 flex-1 truncate" dir="ltr">
                        {g.gonderen || '—'}
                      </span>
                      <span className="text-xs text-muted-foreground">{zaman(g.created_at)}</span>
                    </div>
                    <p className="mt-0.5 truncate text-xs">{g.konu || '—'}</p>
                    <p className="text-xs text-muted-foreground">
                      {g.neden ? t(`destekKurallari.eposta.nedenler.${g.neden}`, { defaultValue: g.neden }) : ''}
                      {g.talep_id ? ` · ${t('destekKurallari.eposta.talep', { id: g.talep_id })}` : ''}
                      {g.ek_sayisi ? ` · ${t('destekKurallari.eposta.ekSayisi', { adet: g.ek_sayisi })}` : ''}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
