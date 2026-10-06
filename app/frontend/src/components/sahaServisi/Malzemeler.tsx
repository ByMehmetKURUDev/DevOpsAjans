import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, Plus, Save, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { hataMetni, paraYaz, type Malzeme, type SahaApi } from '@/lib/sahaServisi';
import { BIRIM_SECENEKLERI, Bos, GIRDI, KART, Rozet, SECIM, Yukleniyor } from './ortak';

const BOS = { ad: '', kod: '', birim: 'adet', birim_fiyat: '', stok: '', kritik_stok: '' };

/** Faz 6S — malzeme/parça kataloğu + basit stok (iş emrinde kullanılınca düşer). Tam envanter ileride. */
export default function Malzemeler({ api, saltOkunur, paraBirimi }: { api: SahaApi; saltOkunur: boolean; paraBirimi: string }) {
  const { t, i18n } = useTranslation();
  const [liste, setListe] = useState<Malzeme[] | null>(null);
  const [form, setForm] = useState(BOS);
  const [duzen, setDuzen] = useState<Record<number, { stok: string; birim_fiyat: string }>>({});

  const yukle = useCallback(async () => {
    try {
      setListe((await api.malzemeler()).items);
    } catch (e) {
      toast.error(hataMetni(t, e));
      setListe([]);
    }
  }, [api, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const ekle = async () => {
    try {
      await api.malzemeEkle({
        ad: form.ad,
        kod: form.kod,
        birim: form.birim,
        birim_fiyat: form.birim_fiyat.replace(',', '.'),
        stok: form.stok === '' ? null : form.stok.replace(',', '.'),
        kritik_stok: form.kritik_stok === '' ? null : form.kritik_stok.replace(',', '.'),
      });
      setForm(BOS);
      toast.success(t('sahaServisi.malzeme.eklendi'));
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const guncelle = async (m: Malzeme) => {
    const d = duzen[m.id];
    if (!d) return;
    try {
      await api.malzemeGuncelle(m.id, { stok: d.stok === '' ? null : d.stok.replace(',', '.'), birim_fiyat: d.birim_fiyat.replace(',', '.') });
      setDuzen((x) => {
        const y = { ...x };
        delete y[m.id];
        return y;
      });
      await yukle();
      toast.success(t('sahaServisi.kaydedildi'));
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const sil = async (m: Malzeme) => {
    if (!window.confirm(t('sahaServisi.malzeme.silOnay', { ad: m.ad }))) return;
    try {
      await api.malzemeSil(m.id);
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  return (
    <div className="space-y-4" data-testid="saha-malzeme-katalog">
      {!saltOkunur && (
        <div className={`${KART} grid gap-2 p-4 sm:grid-cols-6 sm:items-end`}>
          <label className="text-sm sm:col-span-2">
            <span className="mb-1 block font-medium">{t('sahaServisi.malzeme.ad')}</span>
            <input className={GIRDI} value={form.ad} maxLength={160} onChange={(e) => setForm({ ...form, ad: e.target.value })} data-testid="saha-malzeme-ad" />
          </label>
          <label className="text-sm">
            <span className="mb-1 block font-medium">{t('sahaServisi.malzeme.birim')}</span>
            <select className={SECIM} value={form.birim} onChange={(e) => setForm({ ...form, birim: e.target.value })}>
              {BIRIM_SECENEKLERI.map((b) => (
                <option key={b} value={b}>
                  {t(`sahaServisi.birim.${b}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block font-medium">{t('sahaServisi.malzeme.birimFiyat')}</span>
            <input className={GIRDI} inputMode="decimal" value={form.birim_fiyat} onChange={(e) => setForm({ ...form, birim_fiyat: e.target.value })} dir="ltr" data-testid="saha-malzeme-fiyat" />
          </label>
          <label className="text-sm">
            <span className="mb-1 block font-medium">{t('sahaServisi.malzeme.stok')}</span>
            <input className={GIRDI} inputMode="decimal" value={form.stok} onChange={(e) => setForm({ ...form, stok: e.target.value })} dir="ltr" placeholder={t('sahaServisi.malzeme.stokIzlenmez')} data-testid="saha-malzeme-stok" />
          </label>
          <Button className="gap-1" onClick={() => void ekle()} disabled={!form.ad.trim()} data-testid="saha-malzeme-kaydet">
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('sahaServisi.ekle')}
          </Button>
        </div>
      )}
      {liste === null ? (
        <Yukleniyor />
      ) : liste.length === 0 ? (
        <div className={KART}>
          <Bos>{t('sahaServisi.malzeme.katalogBos')}</Bos>
        </div>
      ) : (
        <div className={`${KART} overflow-x-auto`}>
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="text-start text-xs text-muted-foreground">
                <th className="px-4 py-2 text-start font-medium">{t('sahaServisi.malzeme.ad')}</th>
                <th className="px-2 py-2 text-start font-medium">{t('sahaServisi.malzeme.birim')}</th>
                <th className="px-2 py-2 text-end font-medium">{t('sahaServisi.malzeme.birimFiyat')}</th>
                <th className="px-2 py-2 text-end font-medium">{t('sahaServisi.malzeme.stok')}</th>
                <th className="px-2 py-2" />
              </tr>
            </thead>
            <tbody>
              {liste.map((m) => {
                const d = duzen[m.id];
                return (
                  <tr key={m.id} className="border-t border-white/5" data-testid="saha-malzeme-satiri">
                    <td className="px-4 py-2">
                      <span className="font-medium">{m.ad}</span>
                      {m.kod && <span className="ms-2 font-mono text-xs text-muted-foreground">{m.kod}</span>}
                      {!m.aktif && <Rozet>{t('sahaServisi.pasif')}</Rozet>}
                    </td>
                    <td className="px-2 py-2">{t(`sahaServisi.birim.${m.birim}`, { defaultValue: m.birim })}</td>
                    <td className="px-2 py-2 text-end tabular-nums">
                      {d ? (
                        <input className={`${GIRDI} h-8 w-24`} value={d.birim_fiyat} onChange={(e) => setDuzen({ ...duzen, [m.id]: { ...d, birim_fiyat: e.target.value } })} dir="ltr" />
                      ) : (
                        paraYaz(m.birim_fiyat, paraBirimi, i18n.language)
                      )}
                    </td>
                    <td className="px-2 py-2 text-end tabular-nums" data-testid="saha-malzeme-stok-deger">
                      {d ? (
                        <input className={`${GIRDI} h-8 w-20`} value={d.stok} onChange={(e) => setDuzen({ ...duzen, [m.id]: { ...d, stok: e.target.value } })} dir="ltr" />
                      ) : m.stok == null ? (
                        <span className="text-muted-foreground">—</span>
                      ) : (
                        <span className={m.kritik ? 'text-amber-200' : ''}>
                          {m.kritik && <AlertTriangle className="me-1 inline h-3.5 w-3.5" aria-label={t('sahaServisi.malzeme.kritik')} />}
                          {m.stok}
                        </span>
                      )}
                    </td>
                    <td className="px-2 py-2 text-end">
                      {!saltOkunur &&
                        (d ? (
                          <Button size="sm" className="gap-1" onClick={() => void guncelle(m)}>
                            <Save className="h-3.5 w-3.5" aria-hidden="true" />
                            {t('sahaServisi.kaydet')}
                          </Button>
                        ) : (
                          <span className="inline-flex gap-1">
                            <Button size="sm" variant="ghost" onClick={() => setDuzen({ ...duzen, [m.id]: { stok: m.stok == null ? '' : String(m.stok), birim_fiyat: String(m.birim_fiyat / 100) } })}>
                              {t('sahaServisi.duzenle')}
                            </Button>
                            <Button size="icon" variant="ghost" className="h-8 w-8" onClick={() => void sil(m)} aria-label={t('sahaServisi.sil')}>
                              <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                            </Button>
                          </span>
                        ))}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
