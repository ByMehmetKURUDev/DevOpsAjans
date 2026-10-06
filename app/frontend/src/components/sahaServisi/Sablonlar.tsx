import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowDown, ArrowUp, ClipboardList, Loader2, Plus, Save, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { hataMetni, IS_TURLERI, MADDE_TURLERI, type IsTuru, type Madde, type MaddeTuru, type SahaApi, type Sablon } from '@/lib/sahaServisi';
import { Alan, Anahtar, Bos, GIRDI, KART, Rozet, SECIM, Yukleniyor } from './ortak';

/**
 * Faz 6S — kontrol listesi şablonları: maddeler (evet/hayır, metin, sayı, ölçüm + birim, fotoğraf),
 * zorunluluk, iş türüne göre varsayılan şablon. Hazır üç şablon (Klima bakımı, Ofis temizliği,
 * Kombi bakımı) hesabın ilk açılışında eklenir; düzenlenebilir.
 */
export default function Sablonlar({ api, saltOkunur }: { api: SahaApi; saltOkunur: boolean }) {
  const { t } = useTranslation();
  const [liste, setListe] = useState<Sablon[] | null>(null);
  const [secili, setSecili] = useState<Sablon | null>(null);
  const [mesgul, setMesgul] = useState(false);

  const yukle = useCallback(async () => {
    try {
      const l = (await api.sablonlar()).items;
      setListe(l);
      return l;
    } catch (e) {
      toast.error(hataMetni(t, e));
      setListe([]);
      return [];
    }
  }, [api, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const kaydet = async () => {
    if (!secili) return;
    setMesgul(true);
    try {
      const govde = { ad: secili.ad, is_turu: secili.is_turu, maddeler: secili.maddeler, aktif: secili.aktif };
      const s = secili.id ? await api.sablonGuncelle(secili.id, govde) : await api.sablonEkle(govde);
      toast.success(t('sahaServisi.kaydedildi'));
      await yukle();
      setSecili(s);
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  const sil = async () => {
    if (!secili?.id || !window.confirm(t('sahaServisi.sablon.silOnay'))) return;
    try {
      await api.sablonSil(secili.id);
      setSecili(null);
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const maddeDegis = (i: number, m: Partial<Madde>) =>
    setSecili((s) => (s ? { ...s, maddeler: s.maddeler.map((x, j) => (j === i ? { ...x, ...m } : x)) } : s));
  const tasi = (i: number, yon: -1 | 1) =>
    setSecili((s) => {
      if (!s) return s;
      const m = [...s.maddeler];
      const j = i + yon;
      if (j < 0 || j >= m.length) return s;
      [m[i], m[j]] = [m[j], m[i]];
      return { ...s, maddeler: m };
    });

  return (
    <div className="grid gap-4 lg:grid-cols-[18rem_minmax(0,1fr)]" data-testid="saha-sablonlar">
      <div className={`${KART} p-3`}>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-semibold">{t('sahaServisi.sablon.baslik')}</h3>
          {!saltOkunur && (
            <Button size="sm" variant="ghost" className="gap-1" onClick={() => setSecili({ id: 0, ad: '', is_turu: null, maddeler: [], aktif: true, hazir: null })} data-testid="saha-sablon-yeni">
              <Plus className="h-4 w-4" aria-hidden="true" />
              {t('sahaServisi.yeni')}
            </Button>
          )}
        </div>
        {liste === null ? (
          <Yukleniyor />
        ) : liste.length === 0 ? (
          <Bos>{t('sahaServisi.sablon.bos')}</Bos>
        ) : (
          <ul className="space-y-1">
            {liste.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  onClick={() => setSecili(s)}
                  className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-start text-sm ${secili?.id === s.id ? 'bg-purple-500/20' : 'hover:bg-white/[0.04]'}`}
                  data-testid="saha-sablon"
                >
                  <ClipboardList className="h-4 w-4 flex-none text-purple-300" aria-hidden="true" />
                  <span className="min-w-0 flex-1 truncate">{s.ad}</span>
                  {s.is_turu && <Rozet>{t(`sahaServisi.tur.${s.is_turu}`)}</Rozet>}
                  {!s.aktif && <Rozet>{t('sahaServisi.pasif')}</Rozet>}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className={`${KART} p-4`}>
        {!secili ? (
          <Bos>{t('sahaServisi.sablon.sec')}</Bos>
        ) : (
          <div className="space-y-3" data-testid="saha-sablon-duzenleyici">
            <div className="grid gap-3 sm:grid-cols-2">
              <Alan etiket={t('sahaServisi.sablon.ad')}>
                <input className={GIRDI} disabled={saltOkunur} value={secili.ad} maxLength={120} onChange={(e) => setSecili({ ...secili, ad: e.target.value })} data-testid="saha-sablon-ad" />
              </Alan>
              <Alan etiket={t('sahaServisi.sablon.varsayilanTur')} ipucu={t('sahaServisi.sablon.varsayilanIpucu')}>
                <select className={SECIM} disabled={saltOkunur} value={secili.is_turu || ''} onChange={(e) => setSecili({ ...secili, is_turu: (e.target.value || null) as IsTuru | null })}>
                  <option value="">—</option>
                  {IS_TURLERI.map((x) => (
                    <option key={x} value={x}>
                      {t(`sahaServisi.tur.${x}`)}
                    </option>
                  ))}
                </select>
              </Alan>
            </div>
            <Anahtar acik={secili.aktif} devreDisi={saltOkunur} onDegis={(v) => setSecili({ ...secili, aktif: v })} etiket={t('sahaServisi.aktif')} />
            <ol className="space-y-2">
              {secili.maddeler.map((m, i) => (
                <li key={m.id || i} className="grid gap-2 rounded-xl border border-white/10 bg-black/20 p-3 sm:grid-cols-[minmax(0,1fr)_10rem_6rem_auto]" data-testid="saha-sablon-madde">
                  <input className={GIRDI} disabled={saltOkunur} value={m.metin} maxLength={200} onChange={(e) => maddeDegis(i, { metin: e.target.value })} aria-label={t('sahaServisi.sablon.madde')} placeholder={t('sahaServisi.sablon.madde')} />
                  <select className={SECIM} disabled={saltOkunur} value={m.tur} onChange={(e) => maddeDegis(i, { tur: e.target.value as MaddeTuru })} aria-label={t('sahaServisi.sablon.maddeTuru')}>
                    {MADDE_TURLERI.map((x) => (
                      <option key={x} value={x}>
                        {t(`sahaServisi.maddeTuru.${x}`)}
                      </option>
                    ))}
                  </select>
                  {m.tur === 'olcum' ? (
                    <input className={GIRDI} disabled={saltOkunur} value={m.birim || ''} maxLength={12} onChange={(e) => maddeDegis(i, { birim: e.target.value })} placeholder={t('sahaServisi.sablon.birim')} aria-label={t('sahaServisi.sablon.birim')} />
                  ) : (
                    <span className="hidden sm:block" />
                  )}
                  <div className="flex items-center gap-1">
                    <label className="flex items-center gap-1 text-xs">
                      <input type="checkbox" className="h-4 w-4 accent-purple-500" disabled={saltOkunur} checked={m.zorunlu} onChange={(e) => maddeDegis(i, { zorunlu: e.target.checked })} />
                      {t('sahaServisi.kontrol.zorunlu')}
                    </label>
                    {!saltOkunur && (
                      <>
                        <Button size="icon" variant="ghost" className="h-8 w-8" onClick={() => tasi(i, -1)} aria-label={t('sahaServisi.yukari')}>
                          <ArrowUp className="h-3.5 w-3.5" aria-hidden="true" />
                        </Button>
                        <Button size="icon" variant="ghost" className="h-8 w-8" onClick={() => tasi(i, 1)} aria-label={t('sahaServisi.asagi')}>
                          <ArrowDown className="h-3.5 w-3.5" aria-hidden="true" />
                        </Button>
                        <Button size="icon" variant="ghost" className="h-8 w-8" onClick={() => setSecili({ ...secili, maddeler: secili.maddeler.filter((_, j) => j !== i) })} aria-label={t('sahaServisi.sil')}>
                          <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                        </Button>
                      </>
                    )}
                  </div>
                </li>
              ))}
            </ol>
            {!saltOkunur && (
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  className="gap-1 !bg-transparent border-white/20"
                  onClick={() => setSecili({ ...secili, maddeler: [...secili.maddeler, { id: `m${Date.now().toString(36)}`, metin: '', tur: 'evet_hayir', zorunlu: false }] })}
                  data-testid="saha-sablon-madde-ekle"
                >
                  <Plus className="h-4 w-4" aria-hidden="true" />
                  {t('sahaServisi.sablon.maddeEkle')}
                </Button>
                <Button className="gap-1" onClick={() => void kaydet()} disabled={mesgul || !secili.ad.trim()} data-testid="saha-sablon-kaydet">
                  {mesgul ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Save className="h-4 w-4" aria-hidden="true" />}
                  {t('sahaServisi.kaydet')}
                </Button>
                {secili.id > 0 && (
                  <Button variant="ghost" className="gap-1 text-rose-200" onClick={() => void sil()}>
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                    {t('sahaServisi.sil')}
                  </Button>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
