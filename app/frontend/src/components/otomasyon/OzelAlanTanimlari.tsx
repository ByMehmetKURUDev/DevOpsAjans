import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Loader2, Pencil, Plus, Save, Trash2, X } from 'lucide-react';

import { ozelAlanApi, ozelHataMetni, type OzelAlan, type OzelAlanGirdisi, type OzelTur, type OzelVarlik } from '@/lib/otomasyon';
import { ALAN, ANA_DUGME, Etiket, IKINCIL_DUGME, KART, ROZET, SECIM } from './ortak';

const VARLIKLAR: OzelVarlik[] = ['crm_aday', 'proje', 'hesap', 'destek'];
const TURLER: OzelTur[] = ['metin', 'sayi', 'tarih', 'secim', 'coklu_secim', 'evet_hayir', 'url'];
const GORUNUR_OLABILIR: OzelVarlik[] = ['proje', 'destek'];

interface Taslak {
  ad: string;
  tur: OzelTur;
  secenekler: string;
  zorunlu: boolean;
  musteriye_gorunur: boolean;
  aktif: boolean;
  sira: string;
}

const BOS: Taslak = { ad: '', tur: 'metin', secenekler: '', zorunlu: false, musteriye_gorunur: false, aktif: true, sira: '' };

/**
 * Faz 4W — özel alan tanımları (yalnız ajans): CRM adayı, proje, müşteri hesabı, destek
 * talebi. Anahtar ve varlık oluşturulduktan sonra değişmez (kural koşulları ve yer
 * tutucular anahtara bağlı). Silinen alan çöp kutusuna gider; değerleri kalır.
 */
export default function OzelAlanTanimlari({ onDegisti }: { onDegisti?: () => void }) {
  const { t } = useTranslation();
  const [varlik, setVarlik] = useState<OzelVarlik>('crm_aday');
  const [liste, setListe] = useState<OzelAlan[] | null>(null);
  const [duzenlenen, setDuzenlenen] = useState<OzelAlan | 'yeni' | null>(null);
  const [taslak, setTaslak] = useState<Taslak>(BOS);
  const [mesgul, setMesgul] = useState(false);

  const yukle = useCallback(async () => {
    try {
      setListe((await ozelAlanApi.liste(varlik)).items);
    } catch (e) {
      toast.error(ozelHataMetni(t, e));
      setListe([]);
    }
  }, [varlik, t]);

  useEffect(() => {
    setListe(null);
    setDuzenlenen(null);
    void yukle();
  }, [yukle]);

  const ac = (a: OzelAlan | 'yeni') => {
    setDuzenlenen(a);
    setTaslak(
      a === 'yeni'
        ? BOS
        : {
            ad: a.ad,
            tur: a.tur,
            secenekler: a.secenekler.join('\n'),
            zorunlu: a.zorunlu,
            musteriye_gorunur: a.musteriye_gorunur,
            aktif: a.aktif,
            sira: String(a.sira),
          }
    );
  };

  const kaydet = async () => {
    setMesgul(true);
    try {
      const g: OzelAlanGirdisi = {
        ad: taslak.ad,
        tur: taslak.tur,
        zorunlu: taslak.zorunlu,
        aktif: taslak.aktif,
        musteriye_gorunur: GORUNUR_OLABILIR.includes(varlik) && taslak.musteriye_gorunur,
      };
      if (taslak.tur === 'secim' || taslak.tur === 'coklu_secim') {
        g.secenekler = taslak.secenekler.split(/\n|,/).map((s) => s.trim()).filter(Boolean);
      }
      if (taslak.sira.trim()) g.sira = Number(taslak.sira);
      if (duzenlenen === 'yeni') await ozelAlanApi.olustur({ ...g, varlik });
      else if (duzenlenen) await ozelAlanApi.guncelle(duzenlenen.id, g);
      toast.success(t('ozelAlanlar.kaydedildi'));
      setDuzenlenen(null);
      await yukle();
      onDegisti?.();
    } catch (e) {
      toast.error(ozelHataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  const sil = async (a: OzelAlan) => {
    if (!window.confirm(t('ozelAlanlar.silOnay', { ad: a.ad }))) return;
    try {
      await ozelAlanApi.sil(a.id);
      toast.success(t('ozelAlanlar.silindi'));
      await yukle();
      onDegisti?.();
    } catch (e) {
      toast.error(ozelHataMetni(t, e));
    }
  };

  return (
    <div className="space-y-4" data-testid="oto-ozel-alanlar">
      <p className="max-w-3xl text-sm text-muted-foreground">{t('ozelAlanlar.tanimAciklama')}</p>
      <div className="flex flex-wrap gap-2" role="tablist" aria-label={t('ozelAlanlar.varlik')}>
        {VARLIKLAR.map((v) => (
          <button
            key={v}
            type="button"
            role="tab"
            aria-selected={varlik === v}
            onClick={() => setVarlik(v)}
            data-ozel-varlik={v}
            className={`rounded-full border px-3 py-1 text-xs ${
              varlik === v ? 'border-purple-400/60 bg-purple-500/20 text-white' : 'border-white/10 text-muted-foreground hover:text-white'
            }`}
          >
            {t(`ozelAlanlar.varliklar.${v}`)}
          </button>
        ))}
      </div>

      {duzenlenen && (
        <form
          className={`${KART} grid gap-3 p-4 sm:grid-cols-2`}
          onSubmit={(e) => {
            e.preventDefault();
            void kaydet();
          }}
          data-testid="ozel-alan-form"
        >
          <div className="flex items-center justify-between sm:col-span-2">
            <h3 className="font-semibold">{duzenlenen === 'yeni' ? t('ozelAlanlar.yeni') : t('ozelAlanlar.duzenle')}</h3>
            <button type="button" className="rounded p-1 hover:bg-white/10" onClick={() => setDuzenlenen(null)} aria-label={t('ozelAlanlar.kapat')}>
              <X className="h-4 w-4" />
            </button>
          </div>
          <Etiket ad={t('ozelAlanlar.ad')}>
            <input className={ALAN} required maxLength={80} value={taslak.ad} onChange={(e) => setTaslak((x) => ({ ...x, ad: e.target.value }))} data-testid="ozel-alan-ad" />
          </Etiket>
          <Etiket ad={t('ozelAlanlar.tur')}>
            <select className={SECIM} value={taslak.tur} onChange={(e) => setTaslak((x) => ({ ...x, tur: e.target.value as OzelTur }))} data-testid="ozel-alan-tur">
              {TURLER.map((tur) => (
                <option key={tur} value={tur}>
                  {t(`ozelAlanlar.turler.${tur}`)}
                </option>
              ))}
            </select>
          </Etiket>
          {(taslak.tur === 'secim' || taslak.tur === 'coklu_secim') && (
            <Etiket ad={t('ozelAlanlar.secenekler')} ipucu={t('ozelAlanlar.seceneklerIpucu')} tam>
              <textarea className={ALAN} rows={3} value={taslak.secenekler} onChange={(e) => setTaslak((x) => ({ ...x, secenekler: e.target.value }))} data-testid="ozel-alan-secenekler" />
            </Etiket>
          )}
          <Etiket ad={t('ozelAlanlar.sira')}>
            <input className={ALAN} type="number" min={0} value={taslak.sira} onChange={(e) => setTaslak((x) => ({ ...x, sira: e.target.value }))} />
          </Etiket>
          <div className="flex flex-col gap-2 text-sm sm:col-span-2">
            <label className="inline-flex items-center gap-2">
              <input type="checkbox" className="h-4 w-4 accent-purple-500" checked={taslak.zorunlu} onChange={(e) => setTaslak((x) => ({ ...x, zorunlu: e.target.checked }))} />
              {t('ozelAlanlar.zorunlu')}
            </label>
            {GORUNUR_OLABILIR.includes(varlik) && (
              <label className="inline-flex items-center gap-2">
                <input
                  type="checkbox"
                  className="h-4 w-4 accent-purple-500"
                  checked={taslak.musteriye_gorunur}
                  onChange={(e) => setTaslak((x) => ({ ...x, musteriye_gorunur: e.target.checked }))}
                  data-testid="ozel-alan-gorunur"
                />
                {t('ozelAlanlar.musteriyeGorunur')}
              </label>
            )}
            <label className="inline-flex items-center gap-2">
              <input type="checkbox" className="h-4 w-4 accent-purple-500" checked={taslak.aktif} onChange={(e) => setTaslak((x) => ({ ...x, aktif: e.target.checked }))} />
              {t('ozelAlanlar.aktif')}
            </label>
          </div>
          <div className="flex justify-end gap-2 sm:col-span-2">
            <button type="button" className={IKINCIL_DUGME} onClick={() => setDuzenlenen(null)}>
              {t('ozelAlanlar.vazgec')}
            </button>
            <button type="submit" className={ANA_DUGME} disabled={mesgul || !taslak.ad.trim()} data-testid="ozel-alan-kaydet">
              {mesgul ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" aria-hidden="true" />}
              {t('ozelAlanlar.kaydet')}
            </button>
          </div>
        </form>
      )}

      {!duzenlenen && (
        <button type="button" className={ANA_DUGME} onClick={() => ac('yeni')} data-testid="ozel-alan-yeni">
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('ozelAlanlar.yeni')}
        </button>
      )}

      {liste === null ? (
        <div className="flex justify-center py-6 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" aria-label={t('ozelAlanlar.yukleniyor')} />
        </div>
      ) : liste.length === 0 ? (
        <p className={`${KART} p-6 text-center text-sm text-muted-foreground`}>{t('ozelAlanlar.bos')}</p>
      ) : (
        <ul className="space-y-2">
          {liste.map((a) => (
            <li key={a.id} className={`${KART} flex flex-wrap items-center justify-between gap-3 p-3`} data-ozel-alan={a.anahtar}>
              <div className="min-w-0">
                <p className="break-words font-medium">
                  {a.ad} {!a.aktif && <span className="text-xs text-muted-foreground">({t('ozelAlanlar.pasif')})</span>}
                </p>
                <p className="mt-0.5 flex flex-wrap gap-1.5 text-[11px] text-muted-foreground">
                  <code dir="ltr" className="rounded bg-black/40 px-1">
                    {a.anahtar}
                  </code>
                  <span className={`${ROZET} border-white/15`}>{t(`ozelAlanlar.turler.${a.tur}`)}</span>
                  {a.zorunlu && <span className={`${ROZET} border-amber-400/30 text-amber-200`}>{t('ozelAlanlar.zorunlu')}</span>}
                  {a.musteriye_gorunur && <span className={`${ROZET} border-emerald-400/30 text-emerald-200`}>{t('ozelAlanlar.gorunurRozet')}</span>}
                  {a.secenekler.length > 0 && <span>{a.secenekler.join(' · ')}</span>}
                </p>
              </div>
              <div className="flex gap-2">
                <button type="button" className={`${IKINCIL_DUGME} px-2`} onClick={() => ac(a)} aria-label={t('ozelAlanlar.duzenle')}>
                  <Pencil className="h-4 w-4" />
                </button>
                <button type="button" className={`${IKINCIL_DUGME} px-2 text-red-200`} onClick={() => void sil(a)} aria-label={t('ozelAlanlar.sil')}>
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
