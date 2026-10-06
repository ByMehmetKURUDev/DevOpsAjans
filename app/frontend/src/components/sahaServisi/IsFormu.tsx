import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, Save } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  girdidenIso,
  hataMetni,
  IS_TURLERI,
  ONCELIKLER,
  yerelGirdi,
  type IsAyrintisi,
  type IsTuru,
  type Musteri,
  type Oncelik,
  type SahaApi,
  type Sablon,
  type Teknisyen,
} from '@/lib/sahaServisi';
import { Alan, GIRDI, METIN_ALANI, Panel, SECIM } from './ortak';

/** Faz 6S — iş emri oluştur / düzenle (yönetim). Müşteri → adres → cihazlar; plan; teknisyenler; şablon. */
export default function IsFormu({
  api,
  mevcut,
  musteriId,
  cihazId,
  onKapat,
  onKaydedildi,
}: {
  api: SahaApi;
  mevcut?: IsAyrintisi;
  musteriId?: number;
  cihazId?: number;
  onKapat: () => void;
  onKaydedildi: (d: IsAyrintisi) => void;
}) {
  const { t } = useTranslation();
  const [musteriler, setMusteriler] = useState<Musteri[] | null>(null);
  const [teknisyenler, setTeknisyenler] = useState<Teknisyen[]>([]);
  const [sablonlar, setSablonlar] = useState<Sablon[]>([]);
  const [mesgul, setMesgul] = useState(false);
  const [f, setF] = useState(() => ({
    musteri_id: mevcut?.musteri_id ?? musteriId ?? 0,
    lokasyon_id: mevcut?.lokasyon_id ?? 0,
    cihazlar: mevcut?.cihazlar.map((c) => c.id) ?? (cihazId ? [cihazId] : []),
    tur: (mevcut?.tur ?? (cihazId ? 'bakim' : 'ariza')) as IsTuru,
    oncelik: (mevcut?.oncelik ?? 'normal') as Oncelik,
    baslik: mevcut?.baslik ?? '',
    aciklama: mevcut?.aciklama ?? '',
    plan: yerelGirdi(mevcut?.plan_bas),
    tahmini_dk: String(mevcut?.tahmini_dk ?? 60),
    teknisyenler: mevcut?.teknisyenler.map((x) => x.id) ?? [],
    sablon_id: mevcut ? String(mevcut.sablon_id ?? '') : 'varsayilan',
    iscilik_ucreti: mevcut ? String((mevcut.iscilik_ucreti || 0) / 100) : '',
  }));

  useEffect(() => {
    let iptal = false;
    Promise.all([api.musteriler(), api.teknisyenler(), api.sablonlar()])
      .then(([m, te, s]) => {
        if (iptal) return;
        setMusteriler(m.items);
        setTeknisyenler(te.items.filter((x) => x.aktif));
        setSablonlar(s.items.filter((x) => x.aktif));
      })
      .catch((e) => !iptal && toast.error(hataMetni(t, e)));
    return () => {
      iptal = true;
    };
  }, [api, t]);

  const musteri = useMemo(() => musteriler?.find((m) => m.id === f.musteri_id), [musteriler, f.musteri_id]);

  // Tek adresi olan müşteride adres kendiliğinden seçilsin.
  useEffect(() => {
    if (musteri && !f.lokasyon_id && musteri.lokasyonlar?.length === 1) setF((x) => ({ ...x, lokasyon_id: musteri.lokasyonlar![0].id }));
  }, [musteri, f.lokasyon_id]);

  const kaydet = async () => {
    if (!f.musteri_id || !f.baslik.trim()) {
      toast.error(t('sahaServisi.hata.zorunlu'));
      return;
    }
    setMesgul(true);
    const g: Record<string, unknown> = {
      musteri_id: f.musteri_id,
      lokasyon_id: f.lokasyon_id || null,
      cihazlar: f.cihazlar,
      tur: f.tur,
      oncelik: f.oncelik,
      baslik: f.baslik.trim(),
      aciklama: f.aciklama,
      plan_bas: girdidenIso(f.plan),
      tahmini_dk: Number(f.tahmini_dk) || 60,
      teknisyenler: f.teknisyenler,
      iscilik_ucreti: f.iscilik_ucreti.replace(',', '.'),
    };
    if (f.sablon_id !== 'varsayilan') g.sablon_id = f.sablon_id ? Number(f.sablon_id) : null;
    if (mevcut && String(mevcut.sablon_id ?? '') === f.sablon_id) delete g.sablon_id;
    try {
      const d = mevcut ? await api.isGuncelle(mevcut.id, g) : await api.isEkle(g);
      if (d.cakismalar?.length) {
        toast.warning(t('sahaServisi.pano.cakismaUyari', { no: d.cakismalar.map((c) => c.no).join(', ') }));
      }
      toast.success(mevcut ? t('sahaServisi.kaydedildi') : t('sahaServisi.isler.olusturuldu', { no: d.no }));
      onKaydedildi(d);
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  const degis = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((x) => ({ ...x, [k]: v }));

  return (
    <Panel baslik={mevcut ? t('sahaServisi.isler.duzenle', { no: mevcut.no }) : t('sahaServisi.isler.yeni')} onKapat={onKapat} testid="saha-is-formu">
      {musteriler === null ? (
        <div className="flex justify-center py-10">
          <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          <Alan etiket={t('sahaServisi.isler.musteri')} className="sm:col-span-2">
            <select
              className={SECIM}
              value={f.musteri_id || ''}
              onChange={(e) => setF((x) => ({ ...x, musteri_id: Number(e.target.value), lokasyon_id: 0, cihazlar: [] }))}
              data-testid="saha-form-musteri"
            >
              <option value="">{t('sahaServisi.secin')}</option>
              {musteriler.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.ad}
                  {m.firma ? ` — ${m.firma}` : ''}
                </option>
              ))}
            </select>
          </Alan>
          {musteri && (musteri.lokasyonlar?.length ?? 0) > 0 && (
            <Alan etiket={t('sahaServisi.isler.adres')} className="sm:col-span-2">
              <select className={SECIM} value={f.lokasyon_id || ''} onChange={(e) => degis('lokasyon_id', Number(e.target.value))} data-testid="saha-form-lokasyon">
                <option value="">—</option>
                {musteri.lokasyonlar!.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.ad}: {l.tam_adres}
                  </option>
                ))}
              </select>
            </Alan>
          )}
          {musteri && (musteri.cihazlar?.filter((c) => c.aktif).length ?? 0) > 0 && (
            <fieldset className="sm:col-span-2">
              <legend className="mb-1 text-sm font-medium text-white/90">{t('sahaServisi.isler.cihazlar')}</legend>
              <div className="flex flex-wrap gap-2">
                {musteri.cihazlar!.filter((c) => c.aktif).map((c) => (
                  <label key={c.id} className="flex min-h-[40px] cursor-pointer items-center gap-2 rounded-lg border border-white/10 bg-black/20 px-3 text-sm">
                    <input
                      type="checkbox"
                      className="h-4 w-4 accent-purple-500"
                      checked={f.cihazlar.includes(c.id)}
                      onChange={(e) => degis('cihazlar', e.target.checked ? [...f.cihazlar, c.id] : f.cihazlar.filter((x) => x !== c.id))}
                    />
                    {c.tur} {[c.marka, c.model].filter(Boolean).join(' ')}
                  </label>
                ))}
              </div>
            </fieldset>
          )}
          <Alan etiket={t('sahaServisi.isler.tur')}>
            <select className={SECIM} value={f.tur} onChange={(e) => degis('tur', e.target.value as IsTuru)} data-testid="saha-form-tur">
              {IS_TURLERI.map((x) => (
                <option key={x} value={x}>
                  {t(`sahaServisi.tur.${x}`)}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('sahaServisi.isler.oncelik')}>
            <select className={SECIM} value={f.oncelik} onChange={(e) => degis('oncelik', e.target.value as Oncelik)}>
              {ONCELIKLER.map((x) => (
                <option key={x} value={x}>
                  {t(`sahaServisi.oncelik.${x}`)}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('sahaServisi.isler.baslik')} className="sm:col-span-2">
            <input className={GIRDI} value={f.baslik} maxLength={160} onChange={(e) => degis('baslik', e.target.value)} placeholder={t('sahaServisi.isler.baslikOrnek')} data-testid="saha-form-baslik" />
          </Alan>
          <Alan etiket={t('sahaServisi.isler.aciklama')} className="sm:col-span-2">
            <textarea className={METIN_ALANI} value={f.aciklama} maxLength={4000} onChange={(e) => degis('aciklama', e.target.value)} />
          </Alan>
          <Alan etiket={t('sahaServisi.isler.plan')} ipucu={t('sahaServisi.isler.planIpucu')}>
            <input type="datetime-local" className={GIRDI} value={f.plan} onChange={(e) => degis('plan', e.target.value)} step={900} data-testid="saha-form-plan" />
          </Alan>
          <Alan etiket={t('sahaServisi.isler.tahmini')}>
            <input type="number" min={5} max={1440} step={5} className={GIRDI} value={f.tahmini_dk} onChange={(e) => degis('tahmini_dk', e.target.value)} dir="ltr" />
          </Alan>
          <fieldset className="sm:col-span-2">
            <legend className="mb-1 text-sm font-medium text-white/90">{t('sahaServisi.isler.teknisyenler')}</legend>
            {teknisyenler.length === 0 ? (
              <p className="text-xs text-muted-foreground">{t('sahaServisi.teknisyen.yok')}</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {teknisyenler.map((x) => (
                  <label key={x.id} className="flex min-h-[40px] cursor-pointer items-center gap-2 rounded-lg border border-white/10 bg-black/20 px-3 text-sm">
                    <input
                      type="checkbox"
                      className="h-4 w-4 accent-purple-500"
                      checked={f.teknisyenler.includes(x.id)}
                      onChange={(e) => degis('teknisyenler', e.target.checked ? [...f.teknisyenler, x.id] : f.teknisyenler.filter((y) => y !== x.id))}
                      data-testid="saha-form-teknisyen"
                    />
                    <span className="h-2.5 w-2.5 rounded-full" style={{ background: x.renk }} aria-hidden="true" />
                    {x.ad}
                  </label>
                ))}
              </div>
            )}
          </fieldset>
          <Alan etiket={t('sahaServisi.isler.sablon')}>
            <select className={SECIM} value={f.sablon_id} onChange={(e) => degis('sablon_id', e.target.value)} data-testid="saha-form-sablon">
              {!mevcut && <option value="varsayilan">{t('sahaServisi.isler.sablonVarsayilan')}</option>}
              <option value="">{t('sahaServisi.isler.sablonYok')}</option>
              {sablonlar.map((s) => (
                <option key={s.id} value={String(s.id)}>
                  {s.ad}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('sahaServisi.isler.iscilikUcreti')}>
            <input type="text" inputMode="decimal" className={GIRDI} value={f.iscilik_ucreti} onChange={(e) => degis('iscilik_ucreti', e.target.value)} dir="ltr" />
          </Alan>
          <div className="flex gap-2 sm:col-span-2">
            <Button className="min-h-[44px] gap-1.5" onClick={() => void kaydet()} disabled={mesgul} data-testid="saha-form-kaydet">
              {mesgul ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Save className="h-4 w-4" aria-hidden="true" />}
              {t('sahaServisi.kaydet')}
            </Button>
            <Button variant="outline" className="min-h-[44px] !bg-transparent border-white/20" onClick={onKapat}>
              {t('sahaServisi.vazgec')}
            </Button>
          </div>
        </div>
      )}
    </Panel>
  );
}
