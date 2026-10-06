import { useEffect, useState } from 'react';
import { CheckCircle2, Copy, Download, ExternalLink, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Cekmece, DIS_DUGME, DurumRozeti, KanalIkonu, SayacRozeti, Yukleniyor } from '@/components/icerikStudyosu/ortak';
import { planlananYaz } from '@/lib/icerikOnay';
import { hataMetni, panoyaKopyala, type Gonderi, type Paket, type StudyoApi } from '@/lib/icerikStudyosu';

/**
 * Faz 5I — "Paylaşıma hazır" paketi: kanal başına son metin (bağlantı + etiketler eklenmiş),
 * panoya kopyala, ilk yorum, görsel boyut önerisi, görselleri ZIP indir ve paylaştıktan sonra
 * "Yayınlandı" işareti. Doğrudan yayın YOK (platform API'leri bağlı değil) — metni kanalın
 * kendi uygulamasına yapıştırırsınız.
 */

const KANAL_ADRESI: Record<string, string> = {
  instagram: 'https://www.instagram.com/',
  facebook: 'https://www.facebook.com/',
  linkedin: 'https://www.linkedin.com/feed/?shareActive=true',
  x: 'https://x.com/compose/post',
  tiktok: 'https://www.tiktok.com/upload',
  youtube_shorts: 'https://studio.youtube.com/',
  google_isletme: 'https://business.google.com/',
  pinterest: 'https://www.pinterest.com/pin-builder/',
};

export default function PaylasimPaketi({
  api,
  gonderiId,
  yazilabilir = true,
  onKapat,
  onDegisti,
}: {
  api: StudyoApi;
  gonderiId: number;
  yazilabilir?: boolean;
  onKapat: () => void;
  onDegisti: (g: Gonderi) => void;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [paket, setPaket] = useState<Paket | null>(null);
  const [calisiyor, setCalisiyor] = useState<string | null>(null);

  useEffect(() => {
    api.paket(gonderiId).then(setPaket).catch((e) => toast.error(hataMetni(t, e)));
  }, [api, gonderiId, t]);

  const kopyala = async (metin: string) => toast[(await panoyaKopyala(metin)) ? 'success' : 'error'](t('icerikStudyosu.kopyalandi'));

  const zip = async () => {
    setCalisiyor('zip');
    try {
      await api.zipIndir(gonderiId);
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setCalisiyor(null);
    }
  };

  const yayinlandi = async () => {
    setCalisiyor('yayin');
    try {
      const g = await api.durum(gonderiId, 'yayinlandi');
      setPaket((p) => (p ? { ...p, durum: g.durum } : p));
      toast.success(t('icerikStudyosu.paket.yayinlandi'));
      onDegisti(g);
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setCalisiyor(null);
    }
  };

  return (
    <Cekmece baslik={t('icerikStudyosu.paket.baslik')} onKapat={onKapat} testid="is-paket" genis>
      {!paket ? (
        <Yukleniyor />
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-medium">{paket.baslik}</span>
            <DurumRozeti durum={paket.durum} />
            <span className="text-xs text-muted-foreground">{planlananYaz(paket, dil)}</span>
          </div>
          <p className="text-xs text-muted-foreground">{t('icerikStudyosu.paket.aciklama')}</p>
          {paket.kanallar.map((k) => (
            <article key={k.kanal} className="rounded-xl border border-white/10 p-3" data-paket-kanal={k.kanal}>
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <KanalIkonu kanal={k.kanal} className="h-4 w-4" />
                <span className="text-sm font-medium">{t(`icerikOnay.kanal.${k.kanal}`)}</span>
                <SayacRozeti olcum={k.olcum} dil={dil} />
                <span className="ms-auto flex flex-wrap gap-1">
                  <Button type="button" size="sm" variant="outline" className={DIS_DUGME} onClick={() => kopyala(k.metin)} data-testid={`paket-kopyala-${k.kanal}`}>
                    <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                    {t('icerikStudyosu.paket.metniKopyala')}
                  </Button>
                  {KANAL_ADRESI[k.kanal] && (
                    <Button asChild type="button" size="sm" variant="outline" className={DIS_DUGME}>
                      <a href={KANAL_ADRESI[k.kanal]} target="_blank" rel="noopener noreferrer">
                        <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                        {t('icerikStudyosu.paket.uygulamadaAc')}
                      </a>
                    </Button>
                  )}
                </span>
              </div>
              <pre className="max-h-56 overflow-y-auto whitespace-pre-wrap break-words rounded-lg bg-black/30 p-2 font-sans text-sm" dir="auto">{k.metin || '—'}</pre>
              <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
                {k.baglanti && !k.metin.includes(k.baglanti) && (
                  <button type="button" className="inline-flex items-center gap-1 rounded bg-white/5 px-1.5 py-0.5 text-sky-200" onClick={() => kopyala(k.baglanti!)} dir="ltr">
                    <Copy className="h-3 w-3" aria-hidden="true" /> {t('icerikStudyosu.paket.baglanti')}: {k.baglanti.replace(/^https?:\/\//, '').slice(0, 40)}
                  </button>
                )}
                {k.ilk_yorum && (
                  <button type="button" className="inline-flex items-center gap-1 rounded bg-white/5 px-1.5 py-0.5" onClick={() => kopyala(k.ilk_yorum!)}>
                    <Copy className="h-3 w-3" aria-hidden="true" /> {t('icerikStudyosu.paket.ilkYorum')}
                  </button>
                )}
                {k.gorsel_onerisi.length > 0 && <span>{t('icerikStudyosu.paket.boyut')}: {k.gorsel_onerisi.map((o) => `${o.boyut} (${o.oran})`).join(' · ')}</span>}
              </div>
            </article>
          ))}
          {paket.gorseller.length > 0 && (
            <div>
              <div className="mb-2 flex items-center gap-2">
                <span className="text-sm font-medium">{t('icerikOnay.gorseller')}</span>
                <Button type="button" size="sm" variant="outline" className={DIS_DUGME + ' ms-auto'} onClick={zip} disabled={!!calisiyor} data-testid="paket-zip">
                  {calisiyor === 'zip' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" aria-hidden="true" />}
                  {t('icerikStudyosu.paket.zip')}
                </Button>
              </div>
              <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
                {paket.gorseller.map((r) => (
                  <img key={r.anahtar} src={r.url} alt={r.ad || ''} className="aspect-square w-full rounded-lg border border-white/10 object-cover" loading="lazy" />
                ))}
              </div>
            </div>
          )}
          {paket.durum === 'onaylandi' && yazilabilir && (
            <Button type="button" onClick={yayinlandi} disabled={!!calisiyor} className="w-full gap-1.5 sm:w-auto" data-testid="paket-yayinlandi">
              {calisiyor === 'yayin' ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" aria-hidden="true" />}
              {t('icerikStudyosu.paket.yayinlandiIsaretle')}
            </Button>
          )}
        </div>
      )}
    </Cekmece>
  );
}
