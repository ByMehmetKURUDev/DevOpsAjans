import { useMemo, useState } from 'react';
import {
  ArrowLeft,
  CheckCircle2,
  Download,
  FileDown,
  History,
  Loader2,
  Pencil,
  Pin,
  PinOff,
  Printer,
  Share2,
  Trash2,
  Undo2,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { hataMetni, tarihYaz, type BelgeApi, type BelgeAyrintisi, type Meta } from '@/lib/belgeler';

import { KART, Rozet, yazdir } from './ortak';
import StratejiIzgarasi from './StratejiIzgarasi';
import SurumGecmisi from './SurumGecmisi';

/**
 * Faz 5B — belge / strateji okuma görünümü.
 *
 * İçerik sunucunun temizlediği HTML (`html`). Yapılacak maddeleri (`li[data-satir]`) düzenleme
 * yetkisi varsa tıklamayla işaretlenir. Eylemler role göre: ajans kendi belgesinde düzenle /
 * paylaş / sabitle / sürümler / sil; müşteri ajansın paylaştığı belgede yalnız okur ve
 * "okudum, onaylıyorum" der; kendi belgesinde düzenler ve ajansla paylaşır. PDF, Markdown ve
 * yazdırma herkese açık.
 */

interface Ozellikler {
  api: BelgeApi;
  meta: Meta;
  belge: BelgeAyrintisi;
  onDuzenle: () => void;
  onDegisti: (b: BelgeAyrintisi) => void;
  onSilindi: (id: number) => void;
  onGeri: () => void;
}

export default function BelgeGoruntule({ api, meta, belge, onDuzenle, onDegisti, onSilindi, onGeri }: Ozellikler) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const yonetici = api.mod === 'yonetici';
  const duzenlenebilir = yonetici ? !belge.musteri_belgesi : belge.musteri_belgesi;
  const [calisan, setCalisan] = useState<string | null>(null);
  const [surumAcik, setSurumAcik] = useState(false);
  const sablon = useMemo(() => meta.strateji_sablonlari.find((s) => s.tur === belge.tur) || null, [meta, belge.tur]);

  const calistir = async (ad: string, is: () => Promise<void>) => {
    setCalisan(ad);
    try {
      await is();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setCalisan(null);
    }
  };

  const paylasimDegistir = () =>
    calistir('paylas', async () => {
      const yeni = belge.gorunurluk === 'paylasilan' ? 'ekip' : 'paylasilan';
      const b = await api.guncelle(belge.id, { gorunurluk: yeni });
      onDegisti(b);
      toast.success(t(yeni === 'paylasilan' ? (yonetici ? 'belgeler.durum.paylasildi' : 'belgeler.durum.ajanslaPaylasildi') : 'belgeler.durum.paylasimKalkti'));
    });

  const sabitDegistir = () =>
    calistir('sabit', async () => {
      onDegisti(await api.guncelle(belge.id, { sabit: !belge.sabit }));
    });

  const sil = () => {
    if (!window.confirm(t('belgeler.eylem.silOnay', { ad: belge.baslik }))) return;
    void calistir('sil', async () => {
      await api.sil(belge.id);
      toast.success(t('belgeler.durum.silindi'));
      onSilindi(belge.id);
    });
  };

  const okundu = () =>
    calistir('okundu', async () => {
      const b = await api.okundu(belge.id);
      onDegisti(b);
      toast.success(t('belgeler.durum.okundu', { sayi: b.okundu_surum ?? b.surum }));
    });

  const maddeTikla = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!duzenlenebilir || calisan) return;
    const li = (e.target as HTMLElement).closest('li[data-satir]') as HTMLElement | null;
    if (!li || (e.target as HTMLElement).closest('a')) return;
    const satir = Number(li.dataset.satir);
    const madde = belge.yapilacaklar?.find((y) => y.satir === satir);
    if (!madde) return;
    void calistir('madde', async () => {
      onDegisti(await api.yapilacak(belge.id, { satir, metin: madde.metin, tamam: !madde.tamam }));
    });
  };

  const alanMetni =
    belge.alan === 'ajans'
      ? t('belgeler.alan.ajans')
      : belge.alan === 'proje'
        ? t('belgeler.alan.proje', { ad: belge.proje_adi || `#${belge.proje_id}` })
        : t('belgeler.alan.musteri', { ad: belge.musteri_email || '' });
  const okunduGuncel = belge.okundu_surum !== null && belge.okundu_surum === belge.surum;

  return (
    <article className="min-w-0 space-y-4" data-testid="belge-goruntule" data-belge-id={belge.id}>
      <div className={`${KART} belge-yazdir-alani`}>
        <div className="yazdirma mb-3 flex flex-wrap items-center gap-2">
          <Button size="sm" variant="ghost" className="gap-1 px-2 lg:hidden" onClick={onGeri}>
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            {t('belgeler.eylem.geri')}
          </Button>
          {duzenlenebilir && (
            <Button size="sm" className="gap-1" onClick={onDuzenle} data-testid="belge-duzenle">
              <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
              {t('belgeler.eylem.duzenle')}
            </Button>
          )}
          {duzenlenebilir && (yonetici ? belge.alan !== 'ajans' : true) && (
            <Button size="sm" variant="outline" className="gap-1 !bg-transparent" onClick={() => void paylasimDegistir()} disabled={!!calisan} data-testid="belge-paylas">
              {calisan === 'paylas' ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : belge.gorunurluk === 'paylasilan' ? <Undo2 className="h-3.5 w-3.5" aria-hidden="true" /> : <Share2 className="h-3.5 w-3.5" aria-hidden="true" />}
              {belge.gorunurluk === 'paylasilan'
                ? t('belgeler.eylem.paylasimKaldir')
                : yonetici
                  ? t('belgeler.eylem.paylas')
                  : t('belgeler.eylem.ajanslaPaylas')}
            </Button>
          )}
          {!yonetici && !belge.musteri_belgesi && (
            <Button
              size="sm"
              variant={okunduGuncel ? 'outline' : 'default'}
              className={`gap-1 ${okunduGuncel ? '!bg-transparent' : ''}`}
              onClick={() => void okundu()}
              disabled={okunduGuncel || !!calisan}
              data-testid="belge-okundu"
            >
              <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
              {okunduGuncel ? t('belgeler.durum.okundu', { sayi: belge.okundu_surum }) : t('belgeler.eylem.okudum')}
            </Button>
          )}
          {duzenlenebilir && (
            <Button size="sm" variant="outline" className="gap-1 !bg-transparent" onClick={() => setSurumAcik(true)} data-testid="belge-surumler">
              <History className="h-3.5 w-3.5" aria-hidden="true" />
              {t('belgeler.eylem.surumler')}
            </Button>
          )}
          <Button size="sm" variant="outline" className="gap-1 !bg-transparent" onClick={() => void calistir('pdf', () => api.pdfIndir(belge, dil))} disabled={calisan === 'pdf'} data-testid="belge-pdf">
            {calisan === 'pdf' ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <FileDown className="h-3.5 w-3.5" aria-hidden="true" />}
            {t('belgeler.eylem.pdf')}
          </Button>
          <Button size="sm" variant="outline" className="gap-1 !bg-transparent" onClick={() => void calistir('md', () => api.mdIndir(belge, dil))} data-testid="belge-md">
            <Download className="h-3.5 w-3.5" aria-hidden="true" />
            {t('belgeler.eylem.md')}
          </Button>
          <Button size="sm" variant="outline" className="gap-1 !bg-transparent" onClick={yazdir} data-testid="belge-yazdir">
            <Printer className="h-3.5 w-3.5" aria-hidden="true" />
            {t('belgeler.eylem.yazdir')}
          </Button>
          {duzenlenebilir && (
            <Button size="sm" variant="ghost" className="gap-1 px-2" onClick={() => void sabitDegistir()} title={belge.sabit ? t('belgeler.eylem.sabitKaldir') : t('belgeler.eylem.sabitle')} aria-label={belge.sabit ? t('belgeler.eylem.sabitKaldir') : t('belgeler.eylem.sabitle')}>
              {belge.sabit ? <PinOff className="h-4 w-4" aria-hidden="true" /> : <Pin className="h-4 w-4" aria-hidden="true" />}
            </Button>
          )}
          {duzenlenebilir && (
            <Button size="sm" variant="ghost" className="gap-1 px-2 text-rose-300" onClick={sil} aria-label={t('belgeler.eylem.sil')} title={t('belgeler.eylem.sil')} data-testid="belge-sil">
              <Trash2 className="h-4 w-4" aria-hidden="true" />
            </Button>
          )}
        </div>

        <header className="mb-4">
          <h2 className="break-words text-2xl font-bold" data-testid="belge-baslik-goruntu">{belge.baslik}</h2>
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            {belge.strateji && <Rozet renk="fuchsia">{t(`belgeler.sablon.${belge.tur}.ad`)}</Rozet>}
            <Rozet>{alanMetni}</Rozet>
            {belge.gorunurluk === 'paylasilan' && (
              <Rozet renk="emerald" testId="belge-rozet-paylasilan">
                {belge.musteri_belgesi ? t('belgeler.rozet.ajanslaPaylasilan') : t('belgeler.rozet.paylasilan')}
              </Rozet>
            )}
            {belge.musteri_belgesi && yonetici && <Rozet renk="sky">{t('belgeler.rozet.musteriBelgesi')}</Rozet>}
            {!duzenlenebilir && <Rozet renk="amber">{t('belgeler.rozet.salt')}</Rozet>}
            {belge.sabit && <Rozet renk="sky">{t('belgeler.rozet.sabit')}</Rozet>}
            <Rozet>{t('belgeler.rozet.surum', { sayi: belge.surum })}</Rozet>
            {belge.etiketler.map((e) => (
              <Rozet key={e}>#{e}</Rozet>
            ))}
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            {belge.son_duzenleyen
              ? t('belgeler.durum.sonDuzenleyen', { kisi: belge.son_duzenleyen, zaman: tarihYaz(belge.updated_at, dil) })
              : t('belgeler.durum.guncellendi', { zaman: tarihYaz(belge.updated_at, dil) })}
            {yonetici && belge.okundu_at && (
              <span className="ml-2 text-emerald-300" data-testid="belge-okundu-bilgi">
                · {t('belgeler.durum.musteriOnayladi', { kisi: belge.okuyan || '', sayi: belge.okundu_surum ?? 1 })}
              </span>
            )}
          </p>
          {!yonetici && !belge.musteri_belgesi && belge.okundu_surum !== null && !okunduGuncel && (
            <p className="mt-1 text-xs text-amber-200">{t('belgeler.durum.okunduEski')}</p>
          )}
        </header>

        {belge.strateji ? (
          <>
            {belge.strateji_icerik?.isletme && (
              <p className="mb-3 whitespace-pre-wrap text-sm text-slate-300">
                <span className="font-medium text-white">{t('belgeler.alanlar.isletmeKisa')}: </span>
                {belge.strateji_icerik.isletme}
              </p>
            )}
            {sablon && belge.strateji_icerik && <StratejiIzgarasi sablon={sablon} icerik={belge.strateji_icerik} />}
          </>
        ) : (
          <div
            className="belge-icerik prose prose-invert max-w-none break-words"
            data-isaretlenebilir={duzenlenebilir ? 'evet' : 'hayir'}
            onClick={maddeTikla}
            // Sunucu ham HTML'i kaçışladı ve izinli etiket listesiyle temizledi (services/guvenli_html.belge_html).
            dangerouslySetInnerHTML={{ __html: belge.html || `<p>—</p>` }}
            data-testid="belge-icerik-goruntu"
          />
        )}
      </div>

      {surumAcik && (
        <SurumGecmisi
          api={api}
          belge={belge}
          sablon={sablon}
          onKapat={() => setSurumAcik(false)}
          onGeriYuklendi={(b) => {
            setSurumAcik(false);
            onDegisti(b);
          }}
        />
      )}
    </article>
  );
}
