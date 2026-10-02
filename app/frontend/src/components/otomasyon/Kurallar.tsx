import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { FlaskConical, History, Loader2, Pencil, Plus, Trash2, Zap } from 'lucide-react';

import KuruSonucGorunumu from '@/components/otomasyon/KuruSonuc';
import { anahtarAdi, hataMetni, tarihYaz, type Kural, type KuruSonuc, type OtoMeta, type OtomasyonApi } from '@/lib/otomasyon';
import { ANA_DUGME, DurumRozeti, IKINCIL_DUGME, KART } from './ortak';

interface Props {
  api: OtomasyonApi;
  meta: OtoMeta | null;
  onDuzenle: (k: Kural) => void;
  onYeni: () => void;
  onGunluk: (kuralId: number) => void;
  onDegisti: () => void;
}

/** Kural listesi: aç/kapa, düzenle, kuru çalıştır ("Test et"), günlük, sil. */
export default function Kurallar({ api, meta, onDuzenle, onYeni, onGunluk, onDegisti }: Props) {
  const { t, i18n } = useTranslation();
  const [liste, setListe] = useState<Kural[] | null>(null);
  const [mesgul, setMesgul] = useState<number | null>(null);
  const [test, setTest] = useState<{ id: number; sonuc: KuruSonuc } | null>(null);

  const yukle = useCallback(async () => {
    try {
      setListe(await api.kurallar());
    } catch (e) {
      toast.error(hataMetni(t, e));
      setListe([]);
    }
  }, [api, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const aktifDegistir = async (k: Kural) => {
    setMesgul(k.id);
    try {
      await api.guncelle(k.id, { aktif: !k.aktif });
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(null);
    }
  };

  const sil = async (k: Kural) => {
    if (!window.confirm(t('otomasyon.kural.silOnay', { ad: k.ad }))) return;
    setMesgul(k.id);
    try {
      await api.sil(k.id);
      toast.success(t('otomasyon.kural.silindi'));
      await yukle();
      onDegisti();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(null);
    }
  };

  const testEt = async (k: Kural) => {
    setMesgul(k.id);
    try {
      setTest({ id: k.id, sonuc: await api.kayitliTest(k.id) });
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(null);
    }
  };

  const sinir = meta?.sinirlar;
  const dolu = !!sinir && sinir.kural_sayisi >= sinir.kural;

  return (
    <div className="space-y-4" data-testid="oto-kurallar">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          {sinir ? t('otomasyon.kural.sayac', { sayi: sinir.kural_sayisi, sinir: sinir.kural }) : ' '}
        </p>
        <button type="button" className={ANA_DUGME} onClick={onYeni} disabled={!meta || dolu} data-testid="oto-yeni-kural">
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('otomasyon.kural.yeni')}
        </button>
      </div>

      {liste === null ? (
        <div className="flex justify-center py-10 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" aria-label={t('otomasyon.yukleniyor')} />
        </div>
      ) : liste.length === 0 ? (
        <div className={`${KART} p-8 text-center text-sm text-muted-foreground`} data-testid="oto-kural-bos">
          <Zap className="mx-auto mb-2 h-6 w-6 text-purple-300" aria-hidden="true" />
          {t('otomasyon.kural.bos')}
        </div>
      ) : (
        <ul className="space-y-3">
          {liste.map((k) => (
            <li key={k.id} className={`${KART} p-4`} data-oto-kural={k.id}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <h3 className="break-words font-semibold" data-testid="oto-kural-ad">
                    {k.ad}
                  </h3>
                  <p className="mt-1 text-xs text-muted-foreground">
                    <span className="text-purple-200">{t(`otomasyon.olay.${anahtarAdi(k.tetik)}`)}</span>
                    {' → '}
                    {k.eylemler.map((e) => t(`otomasyon.eylem.${e.tur}`)).join(' · ')}
                  </p>
                  {k.aciklama && <p className="mt-1 break-words text-xs text-muted-foreground">{k.aciklama}</p>}
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    {t('otomasyon.kural.calisma', { sayi: k.calisma_sayisi })}
                    {k.son_calisma_at ? ` · ${t('otomasyon.kural.son', { zaman: tarihYaz(k.son_calisma_at, i18n.language) })}` : ''}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <DurumRozeti durum={k.aktif ? 'aktif' : 'pasif'} metin={k.aktif ? t('otomasyon.kural.aktif') : t('otomasyon.kural.pasif')} />
                  <label className="inline-flex cursor-pointer items-center gap-1.5 text-xs">
                    <input
                      type="checkbox"
                      className="h-4 w-4 accent-purple-500"
                      checked={k.aktif}
                      disabled={mesgul === k.id}
                      onChange={() => void aktifDegistir(k)}
                      data-testid="oto-kural-aktif"
                    />
                    {t('otomasyon.kural.acikKapali')}
                  </label>
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <button type="button" className={IKINCIL_DUGME} onClick={() => onDuzenle(k)} data-testid="oto-kural-duzenle">
                  <Pencil className="h-4 w-4" aria-hidden="true" />
                  {t('otomasyon.kural.duzenle')}
                </button>
                <button type="button" className={IKINCIL_DUGME} onClick={() => void testEt(k)} disabled={mesgul === k.id} data-testid="oto-kural-test">
                  {mesgul === k.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <FlaskConical className="h-4 w-4" aria-hidden="true" />}
                  {t('otomasyon.kural.test')}
                </button>
                <button type="button" className={IKINCIL_DUGME} onClick={() => onGunluk(k.id)} data-testid="oto-kural-gunluk">
                  <History className="h-4 w-4" aria-hidden="true" />
                  {t('otomasyon.kural.gunluk')}
                </button>
                <button
                  type="button"
                  className={`${IKINCIL_DUGME} text-red-200 hover:text-red-100`}
                  onClick={() => void sil(k)}
                  disabled={mesgul === k.id}
                  aria-label={t('otomasyon.kural.sil')}
                  data-testid="oto-kural-sil"
                >
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                  <span className="sr-only sm:not-sr-only">{t('otomasyon.kural.sil')}</span>
                </button>
              </div>
              {test?.id === k.id && (
                <div className="mt-3">
                  <KuruSonucGorunumu sonuc={test.sonuc} meta={meta} tetik={k.tetik} onKapat={() => setTest(null)} />
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
