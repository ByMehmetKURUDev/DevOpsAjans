import { lazy, Suspense, useCallback, useEffect, useState, type ReactNode } from 'react';
import { Copy, ExternalLink, RefreshCw, Undo2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Bos, DIS_DUGME, DurumRozeti, KanalIkonu, KART, Rozet, Yukleniyor } from '@/components/icerikStudyosu/ortak';
import { hataMetni, panoyaKopyala, tarihSaatYaz, type Gonderi, type Meta, type StudyoApi } from '@/lib/icerikStudyosu';

const IcerikOnaylari = lazy(() => import('@/components/IcerikOnaylari'));

/**
 * Faz 5I — Onaylar. Yönetici: müşteri onayı bekleyen gönderiler (bağlantı durumu, süre,
 * yenile, geri çek) ve iç incelemedekiler. Müşteri: ajansın onaya sunduğu içerikler (modül
 * kapalıyken de müşteri panelinin üstünde görünen kartla aynı) + kendi ekibinin incelemesi.
 */
export default function Onaylar({ api, meta, onAc }: { api: StudyoApi; meta: Meta; onAc: (id: number) => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [onayda, setOnayda] = useState<Gonderi[] | null>(null);
  const [incelemede, setIncelemede] = useState<Gonderi[] | null>(null);
  const [baglanti, setBaglanti] = useState<Record<number, string>>({});

  const yukle = useCallback(async () => {
    try {
      const hesap = meta.yonetici && !api.hesap ? '*' : undefined;
      const [a, b] = await Promise.all([
        meta.yonetici ? api.gonderiler({ durum: 'musteri_onayi', hesap }) : Promise.resolve({ items: [] as Gonderi[] }),
        api.gonderiler({ durum: 'incelemede', hesap }),
      ]);
      setOnayda(a.items);
      setIncelemede(b.items);
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  }, [api, meta.yonetici, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const yenile = async (g: Gonderi) => {
    try {
      const y = await api.onayaGonder(g.id, { gun: 7, eposta_gonder: false });
      setBaglanti((b) => ({ ...b, [g.id]: y.baglanti }));
      toast.success(t('icerikStudyosu.form.onayHazir'));
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const durum = async (g: Gonderi, d: 'taslak' | 'onaylandi') => {
    try {
      await api.durum(g.id, d);
      toast.success(t('icerikStudyosu.form.durumDegisti', { durum: t(`icerikOnay.durum.${d}`) }));
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const satir = (g: Gonderi, eylemler: ReactNode) => (
    <article key={g.id} className={`${KART} flex flex-col gap-2 p-3 sm:flex-row sm:items-center`} data-onay-gonderi={g.id}>
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium">{g.baslik}</p>
        <p className="mt-0.5 flex flex-wrap items-center gap-1 text-[11px] text-muted-foreground">
          {g.kanallar.map((k) => (
            <KanalIkonu key={k} kanal={k} className="h-3 w-3" />
          ))}
          <span>· {tarihSaatYaz(g.planlanan_at, dil)}</span>
          {meta.yonetici && g.hesap_email && <span>· {g.hesap_email}</span>}
          {g.onay && (
            <Rozet renk={g.onay.durum === 'bekliyor' ? 'border-sky-400/30 bg-sky-400/10 text-sky-100' : 'border-amber-400/30 bg-amber-400/10 text-amber-100'}>
              {t(`icerikStudyosu.onayDurumu.${g.onay.durum}`, { defaultValue: g.onay.durum })} · {tarihSaatYaz(g.onay.son_kullanma, dil)}
            </Rozet>
          )}
        </p>
        {baglanti[g.id] && (
          <button type="button" className="mt-1 inline-flex max-w-full items-center gap-1 truncate rounded bg-black/30 px-1.5 py-0.5 text-[11px]" dir="ltr"
            onClick={async () => toast[(await panoyaKopyala(baglanti[g.id])) ? 'success' : 'error'](t('icerikStudyosu.kopyalandi'))}>
            <Copy className="h-3 w-3 shrink-0" aria-hidden="true" /> {baglanti[g.id]}
          </button>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <DurumRozeti durum={g.durum} />
        {eylemler}
      </div>
    </article>
  );

  return (
    <div className="space-y-6" data-testid="is-onaylar">
      {!meta.yonetici && (
        <section>
          <h3 className="mb-2 text-sm font-semibold">{t('icerikOnay.baslik')}</h3>
          <Suspense fallback={<Yukleniyor />}>
            <IcerikOnaylari gomulu onDegisti={yukle} />
          </Suspense>
        </section>
      )}
      {meta.yonetici && (
        <section>
          <h3 className="mb-2 text-sm font-semibold">{t('icerikStudyosu.onaylar.musteriBekleyen')}</h3>
          {!onayda ? (
            <Yukleniyor />
          ) : onayda.length === 0 ? (
            <Bos>{t('icerikStudyosu.onaylar.bos')}</Bos>
          ) : (
            <div className="space-y-2">
              {onayda.map((g) =>
                satir(
                  g,
                  <>
                    <Button type="button" size="sm" variant="outline" className={DIS_DUGME} onClick={() => onAc(g.id)}>
                      <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                      {t('icerikStudyosu.ac')}
                    </Button>
                    <Button type="button" size="sm" variant="outline" className={DIS_DUGME} onClick={() => yenile(g)}>
                      <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                      {t('icerikStudyosu.onaylar.yenile')}
                    </Button>
                    <Button type="button" size="sm" variant="outline" className={DIS_DUGME} onClick={() => durum(g, 'taslak')}>
                      <Undo2 className="h-3.5 w-3.5" aria-hidden="true" />
                      {t('icerikStudyosu.onaylar.geriCek')}
                    </Button>
                  </>
                )
              )}
            </div>
          )}
        </section>
      )}
      <section>
        <h3 className="mb-2 text-sm font-semibold">{t('icerikStudyosu.onaylar.incelemede')}</h3>
        {!incelemede ? (
          <Yukleniyor />
        ) : incelemede.length === 0 ? (
          <Bos>{t('icerikStudyosu.onaylar.incelemeBos')}</Bos>
        ) : (
          <div className="space-y-2">
            {incelemede.map((g) =>
              satir(
                g,
                <>
                  <Button type="button" size="sm" variant="outline" className={DIS_DUGME} onClick={() => onAc(g.id)}>
                    <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                    {t('icerikStudyosu.ac')}
                  </Button>
                  {(meta.yonetici || g.yoneten === 'musteri') && (
                    <>
                      <Button type="button" size="sm" onClick={() => durum(g, 'onaylandi')} data-testid={`is-onayla-${g.id}`}>
                        {t('icerikStudyosu.gecis.onaylandi')}
                      </Button>
                      <Button type="button" size="sm" variant="outline" className={DIS_DUGME} onClick={() => durum(g, 'taslak')}>
                        {t('icerikStudyosu.gecis.taslak')}
                      </Button>
                    </>
                  )}
                </>
              )
            )}
          </div>
        )}
      </section>
    </div>
  );
}
