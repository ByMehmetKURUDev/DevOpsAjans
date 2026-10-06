import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, Megaphone, Send, Share2, Smile } from 'lucide-react';
import { toast } from 'sonner';

import { Alan, Anahtar, KART, METIN_ALANI, SECIM } from '@/components/randevu/ortak';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { hataMetni, type Etkinlik, type EtkinlikApi } from '@/lib/etkinlik';
import { tarihYaz } from '@/lib/etkinlikOrtak';

/**
 * Faz 6E — iletişim:
 *   * Duyuru: yalnız geçerli bilet sahiplerine BİLGİLENDİRME e-postası (saat/yer değişikliği vb.).
 *     Pazarlama değil — izin aranmaz, ama reklam içeriği için kullanılmamalı (metin bunu söylüyor).
 *   * Teşekkür + anket: etkinlik bitince zamanlı görev bir kez gönderir (ya da "şimdi gönder").
 *   * E-posta pazarlamaya aktarım: yalnız kayıtta açık izin verenler (5M).
 */
export default function Iletisim({ api, etkinlik, onKaydedildi }: { api: EtkinlikApi; etkinlik: Etkinlik; onKaydedildi: (e: Etkinlik) => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [duyuru, setDuyuru] = useState({ konu: '', metin: '' });
  const [tesekkur, setTesekkur] = useState({ aktif: etkinlik.tesekkur_aktif, metin: etkinlik.tesekkur_metni || '', anket: etkinlik.anket_url || '' });
  const [paz, setPaz] = useState<{ acik: boolean; izinli: number; listeler: { id: number; ad: string }[] } | null>(null);
  const [liste, setListe] = useState('');
  const [mesgul, setMesgul] = useState<string | null>(null);
  const bitti = new Date(etkinlik.bitis).getTime() <= Date.now();

  useEffect(() => {
    api
      .pazarlama(etkinlik.id)
      .then((p) => {
        setPaz(p);
        setListe(p.listeler[0] ? String(p.listeler[0].id) : '');
      })
      .catch(() => setPaz(null));
  }, [api, etkinlik.id]);

  const calistir = async (ad: string, f: () => Promise<void>) => {
    setMesgul(ad);
    try {
      await f();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(null);
    }
  };

  const duyuruGonder = () =>
    calistir('duyuru', async () => {
      if (!duyuru.konu.trim() || !duyuru.metin.trim()) {
        toast.error(t('etkinlik.hata.zorunlu'));
        return;
      }
      if (!window.confirm(t('etkinlik.iletisim.duyuruOnay'))) return;
      const y = await api.duyuru(etkinlik.id, { konu: duyuru.konu, metin: duyuru.metin });
      toast.success(t('etkinlik.iletisim.duyuruGonderildi', { sayi: y.alici }));
      setDuyuru({ konu: '', metin: '' });
    });

  const tesekkurKaydet = () =>
    calistir('tesekkur', async () => {
      const e = await api.guncelle(etkinlik.id, { tesekkur_aktif: tesekkur.aktif, tesekkur_metni: tesekkur.metin, anket_url: tesekkur.anket });
      onKaydedildi(e);
      toast.success(t('etkinlik.ayar.kaydedildi'));
    });

  const tesekkurSimdi = () =>
    calistir('simdi', async () => {
      if (!window.confirm(t('etkinlik.iletisim.tesekkurOnay'))) return;
      await api.tesekkur(etkinlik.id);
      onKaydedildi(await api.getir(etkinlik.id));
      toast.success(t('etkinlik.iletisim.tesekkurGonderildi'));
    });

  const aktar = () =>
    calistir('aktar', async () => {
      if (!liste) return;
      const y = await api.pazarlamaAktar(etkinlik.id, Number(liste));
      toast.success(t('etkinlik.iletisim.aktarildi', { sayi: y.sayilar.aktarilan, yeni: y.sayilar.yeni }));
    });

  const Dongu = ({ ad }: { ad: string }) => (mesgul === ad ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null);

  return (
    <div className="space-y-4" data-testid="etkinlik-iletisim">
      <div className={`${KART} p-4 sm:p-6`}>
        <h3 className="mb-1 flex items-center gap-2 font-semibold">
          <Megaphone className="h-4 w-4" aria-hidden="true" />
          {t('etkinlik.iletisim.duyuru')}
        </h3>
        <p className="mb-3 text-sm text-muted-foreground">{t('etkinlik.iletisim.duyuruAciklama')}</p>
        <div className="grid gap-3">
          <Alan etiket={t('etkinlik.iletisim.konu')}>
            <Input value={duyuru.konu} maxLength={150} onChange={(e) => setDuyuru({ ...duyuru, konu: e.target.value })} data-testid="etkinlik-duyuru-konu" />
          </Alan>
          <Alan etiket={t('etkinlik.iletisim.metin')}>
            <textarea className={METIN_ALANI} rows={5} maxLength={5000} value={duyuru.metin} onChange={(e) => setDuyuru({ ...duyuru, metin: e.target.value })} data-testid="etkinlik-duyuru-metin" />
          </Alan>
          <div>
            <Button onClick={() => void duyuruGonder()} disabled={mesgul !== null} className="gap-1.5" data-testid="etkinlik-duyuru-gonder">
              <Dongu ad="duyuru" />
              <Send className="h-4 w-4" aria-hidden="true" />
              {t('etkinlik.iletisim.gonder')}
            </Button>
          </div>
        </div>
      </div>

      <div className={`${KART} p-4 sm:p-6`}>
        <h3 className="mb-1 flex items-center gap-2 font-semibold">
          <Smile className="h-4 w-4" aria-hidden="true" />
          {t('etkinlik.iletisim.tesekkur')}
        </h3>
        <p className="mb-3 text-sm text-muted-foreground">{t('etkinlik.iletisim.tesekkurAciklama')}</p>
        <div className="grid gap-3">
          <Anahtar acik={tesekkur.aktif} onDegis={(v) => setTesekkur({ ...tesekkur, aktif: v })} etiket={t('etkinlik.iletisim.tesekkurAktif')} testid="etkinlik-tesekkur-aktif" />
          <Alan etiket={t('etkinlik.iletisim.tesekkurMetni')} ipucu={t('etkinlik.iletisim.tesekkurMetniIpucu')}>
            <textarea className={METIN_ALANI} rows={4} maxLength={3000} value={tesekkur.metin} onChange={(e) => setTesekkur({ ...tesekkur, metin: e.target.value })} />
          </Alan>
          <Alan etiket={t('etkinlik.iletisim.anket')} ipucu={t('etkinlik.iletisim.anketIpucu')}>
            <Input type="url" inputMode="url" placeholder="https://" value={tesekkur.anket} onChange={(e) => setTesekkur({ ...tesekkur, anket: e.target.value })} />
          </Alan>
          {etkinlik.tesekkur_at && (
            <p className="text-sm text-emerald-300" data-testid="etkinlik-tesekkur-gitti">
              {t('etkinlik.iletisim.tesekkurGitti', { tarih: tarihYaz(etkinlik.tesekkur_at, etkinlik.saat_dilimi, dil, { dateStyle: 'medium', timeStyle: 'short' }) })}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => void tesekkurKaydet()} disabled={mesgul !== null} className="gap-1.5">
              <Dongu ad="tesekkur" />
              {t('etkinlik.kaydet')}
            </Button>
            <Button variant="outline" className="gap-1.5 !bg-transparent border-white/20" onClick={() => void tesekkurSimdi()} disabled={mesgul !== null || !bitti} title={bitti ? undefined : t('etkinlik.hata.etkinlik_bitmedi')}>
              <Dongu ad="simdi" />
              <Send className="h-4 w-4" aria-hidden="true" />
              {t('etkinlik.iletisim.simdiGonder')}
            </Button>
            {!bitti && <span className="self-center text-xs text-muted-foreground">{t('etkinlik.hata.etkinlik_bitmedi')}</span>}
          </div>
        </div>
      </div>

      <div className={`${KART} p-4 sm:p-6`}>
        <h3 className="mb-1 flex items-center gap-2 font-semibold">
          <Share2 className="h-4 w-4" aria-hidden="true" />
          {t('etkinlik.iletisim.pazarlama')}
        </h3>
        <p className="mb-3 text-sm text-muted-foreground">{t('etkinlik.iletisim.pazarlamaAciklama')}</p>
        {!paz ? null : !paz.acik ? (
          <p className="text-sm text-muted-foreground">{t('etkinlik.iletisim.pazarlamaKapali')}</p>
        ) : (
          <div className="flex flex-wrap items-end gap-2">
            <p className="w-full text-sm" data-testid="etkinlik-pazarlama-izinli">
              {t('etkinlik.iletisim.izinli', { sayi: paz.izinli })}
            </p>
            {paz.listeler.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t('etkinlik.iletisim.listeYok')}</p>
            ) : (
              <>
                <Alan etiket={t('etkinlik.iletisim.liste')} className="min-w-[12rem]">
                  <select className={SECIM} value={liste} onChange={(e) => setListe(e.target.value)}>
                    {paz.listeler.map((l) => (
                      <option key={l.id} value={l.id}>
                        {l.ad}
                      </option>
                    ))}
                  </select>
                </Alan>
                <Button onClick={() => void aktar()} disabled={mesgul !== null || !paz.izinli} className="gap-1.5">
                  <Dongu ad="aktar" />
                  {t('etkinlik.iletisim.aktar')}
                </Button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
