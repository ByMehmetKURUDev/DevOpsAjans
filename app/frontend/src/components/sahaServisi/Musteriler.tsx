import { lazy, Suspense, useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, History, Loader2, MapPin, Plus, Search, Trash2, Wrench } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { DILLER, hataMetni, tarihSaat, type Cihaz, type IsOzeti, type Musteri, type SahaApi } from '@/lib/sahaServisi';
import { Alan, Bos, DurumRozeti, GIRDI, KART, Rozet, SECIM, Yukleniyor } from './ortak';

const IsFormu = lazy(() => import('./IsFormu'));

const BOS_MUSTERI = { ad: '', tur: 'bireysel', firma: '', eposta: '', telefon: '', dil: 'tr', adres: '', ilce: '', il: '' };
const BOS_CIHAZ = { tur: '', marka: '', model: '', seri_no: '', kurulum_tarihi: '', garanti_bitis: '', son_bakim: '', bakim_periyot_ay: '', lokasyon_id: '' };

/** Faz 6S — servis müşterileri: adresler (lokasyonlar), cihaz/varlık kaydı ve cihaz geçmişi. */
export default function Musteriler({ api, onAc, saltOkunur }: { api: SahaApi; onAc: (id: number) => void; saltOkunur: boolean }) {
  const { t } = useTranslation();
  const [liste, setListe] = useState<Musteri[] | null>(null);
  const [ara, setAra] = useState('');
  const [secili, setSecili] = useState<number | null>(null);
  const [yeni, setYeni] = useState(false);
  const [form, setForm] = useState(BOS_MUSTERI);
  const [mesgul, setMesgul] = useState(false);

  const yukle = useCallback(async () => {
    try {
      setListe((await api.musteriler(ara.trim() || undefined)).items);
    } catch (e) {
      toast.error(hataMetni(t, e));
      setListe([]);
    }
  }, [api, ara, t]);

  useEffect(() => {
    const z = window.setTimeout(() => void yukle(), ara ? 300 : 0);
    return () => window.clearTimeout(z);
  }, [yukle, ara]);

  const ekle = async () => {
    if (!form.ad.trim()) {
      toast.error(t('sahaServisi.hata.zorunlu'));
      return;
    }
    setMesgul(true);
    try {
      const m = await api.musteriEkle({
        ad: form.ad,
        tur: form.tur,
        firma: form.firma,
        eposta: form.eposta,
        telefon: form.telefon,
        dil: form.dil,
        ...(form.adres.trim() ? { lokasyon: { ad: t('sahaServisi.musteri.varsayilanAdres'), adres: form.adres, ilce: form.ilce, il: form.il } } : {}),
      });
      setForm(BOS_MUSTERI);
      setYeni(false);
      toast.success(t('sahaServisi.musteri.eklendi'));
      await yukle();
      setSecili(m.id);
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  if (secili !== null) return <MusteriAyrinti api={api} id={secili} onGeri={() => { setSecili(null); void yukle(); }} onAc={onAc} saltOkunur={saltOkunur} />;

  return (
    <div className="space-y-4" data-testid="saha-musteriler">
      <div className={`${KART} flex flex-wrap items-center gap-2 p-3`}>
        <label className="relative min-w-[12rem] flex-1">
          <span className="sr-only">{t('sahaServisi.ara')}</span>
          <Search className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
          <input className={`${GIRDI} ps-9`} value={ara} onChange={(e) => setAra(e.target.value)} placeholder={t('sahaServisi.musteri.ara')} />
        </label>
        {!saltOkunur && (
          <Button className="gap-1.5" onClick={() => setYeni((x) => !x)} data-testid="saha-musteri-yeni">
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('sahaServisi.musteri.yeni')}
          </Button>
        )}
      </div>
      {yeni && (
        <div className={`${KART} grid gap-3 p-4 sm:grid-cols-2`} data-testid="saha-musteri-formu">
          <Alan etiket={t('sahaServisi.musteri.ad')}>
            <input className={GIRDI} value={form.ad} maxLength={160} onChange={(e) => setForm({ ...form, ad: e.target.value })} data-testid="saha-musteri-ad" />
          </Alan>
          <Alan etiket={t('sahaServisi.musteri.tur')}>
            <select className={SECIM} value={form.tur} onChange={(e) => setForm({ ...form, tur: e.target.value })}>
              <option value="bireysel">{t('sahaServisi.musteri.bireysel')}</option>
              <option value="kurumsal">{t('sahaServisi.musteri.kurumsal')}</option>
            </select>
          </Alan>
          {form.tur === 'kurumsal' && (
            <Alan etiket={t('sahaServisi.musteri.firma')}>
              <input className={GIRDI} value={form.firma} maxLength={160} onChange={(e) => setForm({ ...form, firma: e.target.value })} />
            </Alan>
          )}
          <Alan etiket={t('sahaServisi.musteri.eposta')} ipucu={t('sahaServisi.musteri.epostaIpucu')}>
            <input type="email" className={GIRDI} value={form.eposta} maxLength={254} onChange={(e) => setForm({ ...form, eposta: e.target.value })} dir="ltr" data-testid="saha-musteri-eposta" />
          </Alan>
          <Alan etiket={t('sahaServisi.musteri.telefon')}>
            <input type="tel" className={GIRDI} value={form.telefon} maxLength={24} onChange={(e) => setForm({ ...form, telefon: e.target.value })} dir="ltr" data-testid="saha-musteri-telefon" />
          </Alan>
          <Alan etiket={t('sahaServisi.musteri.dil')}>
            <select className={SECIM} value={form.dil} onChange={(e) => setForm({ ...form, dil: e.target.value })}>
              {DILLER.map((d) => (
                <option key={d} value={d}>
                  {t(`sahaServisi.dil.${d}`)}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('sahaServisi.lokasyon.adres')} className="sm:col-span-2">
            <input className={GIRDI} value={form.adres} maxLength={500} onChange={(e) => setForm({ ...form, adres: e.target.value })} data-testid="saha-musteri-adres" />
          </Alan>
          <Alan etiket={t('sahaServisi.lokasyon.ilce')}>
            <input className={GIRDI} value={form.ilce} maxLength={80} onChange={(e) => setForm({ ...form, ilce: e.target.value })} />
          </Alan>
          <Alan etiket={t('sahaServisi.lokasyon.il')}>
            <input className={GIRDI} value={form.il} maxLength={80} onChange={(e) => setForm({ ...form, il: e.target.value })} />
          </Alan>
          <div className="flex gap-2 sm:col-span-2">
            <Button className="gap-1.5" onClick={() => void ekle()} disabled={mesgul} data-testid="saha-musteri-kaydet">
              {mesgul && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
              {t('sahaServisi.kaydet')}
            </Button>
            <Button variant="outline" className="!bg-transparent border-white/20" onClick={() => setYeni(false)}>
              {t('sahaServisi.vazgec')}
            </Button>
          </div>
        </div>
      )}
      {liste === null ? (
        <Yukleniyor />
      ) : liste.length === 0 ? (
        <div className={KART}>
          <Bos>{t('sahaServisi.musteri.bos')}</Bos>
        </div>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" data-testid="saha-musteri-liste">
          {liste.map((m) => (
            <li key={m.id}>
              <button type="button" onClick={() => setSecili(m.id)} className={`${KART} flex h-full w-full flex-col items-start gap-1 p-4 text-start hover:border-purple-400/40`} data-testid="saha-musteri-karti">
                <span className="font-medium">{m.ad}</span>
                {m.firma && <span className="text-xs text-muted-foreground">{m.firma}</span>}
                <span className="text-xs text-muted-foreground" dir="ltr">
                  {[m.telefon, m.eposta].filter(Boolean).join(' · ')}
                </span>
                <span className="mt-1 flex flex-wrap gap-1">
                  <Rozet>{t('sahaServisi.musteri.adresSayisi', { sayi: m.lokasyonlar?.length || 0 })}</Rozet>
                  <Rozet>{t('sahaServisi.musteri.cihazSayisi', { sayi: m.cihazlar?.length || 0 })}</Rozet>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function MusteriAyrinti({ api, id, onGeri, onAc, saltOkunur }: { api: SahaApi; id: number; onGeri: () => void; onAc: (id: number) => void; saltOkunur: boolean }) {
  const { t, i18n } = useTranslation();
  const [m, setM] = useState<Musteri | null>(null);
  const [lok, setLok] = useState({ ad: '', adres: '', ilce: '', il: '', notlar: '' });
  const [cihaz, setCihaz] = useState(BOS_CIHAZ);
  const [cihazAcik, setCihazAcik] = useState(false);
  const [lokAcik, setLokAcik] = useState(false);
  const [gecmis, setGecmis] = useState<{ id: number; isler: IsOzeti[] } | null>(null);
  const [yeniIs, setYeniIs] = useState<{ cihaz?: number } | null>(null);

  const yukle = useCallback(async () => {
    try {
      setM(await api.musteri(id));
    } catch (e) {
      toast.error(hataMetni(t, e));
      onGeri();
    }
  }, [api, id, onGeri, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  if (!m) return <Yukleniyor />;

  const lokasyonEkle = async () => {
    try {
      await api.lokasyonEkle(m.id, lok);
      setLok({ ad: '', adres: '', ilce: '', il: '', notlar: '' });
      setLokAcik(false);
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const cihazEkle = async () => {
    try {
      await api.cihazEkle(m.id, {
        ...cihaz,
        bakim_periyot_ay: cihaz.bakim_periyot_ay || null,
        lokasyon_id: cihaz.lokasyon_id || null,
      });
      setCihaz(BOS_CIHAZ);
      setCihazAcik(false);
      toast.success(t('sahaServisi.cihaz.eklendi'));
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const gecmisAc = async (c: Cihaz) => {
    if (gecmis?.id === c.id) {
      setGecmis(null);
      return;
    }
    try {
      const g = await api.cihazGecmisi(c.id);
      setGecmis({ id: c.id, isler: g.isler });
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const sil = async () => {
    if (!window.confirm(t('sahaServisi.musteri.silOnay'))) return;
    try {
      await api.musteriSil(m.id);
      toast.success(t('sahaServisi.silindi'));
      onGeri();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const bugun = new Date().toISOString().slice(0, 10);
  return (
    <div className="space-y-4" data-testid="saha-musteri-ayrinti">
      <div className={`${KART} flex flex-wrap items-start gap-3 p-4`}>
        <Button size="icon" variant="ghost" onClick={onGeri} aria-label={t('sahaServisi.geri')}>
          <ArrowLeft className="h-5 w-5 rtl:rotate-180" aria-hidden="true" />
        </Button>
        <div className="min-w-0 flex-1">
          <h3 className="text-lg font-semibold">{m.ad}</h3>
          <p className="text-sm text-muted-foreground" dir="ltr">
            {[m.telefon, m.eposta].filter(Boolean).join(' · ') || '—'}
          </p>
          <p className="text-xs text-muted-foreground">
            {t(`sahaServisi.musteri.${m.tur}`)} · {t(`sahaServisi.dil.${m.dil}`)}
          </p>
        </div>
        {!saltOkunur && (
          <div className="flex flex-wrap gap-2">
            <Button className="gap-1.5" onClick={() => setYeniIs({})} data-testid="saha-musteri-is-ac">
              <Plus className="h-4 w-4" aria-hidden="true" />
              {t('sahaServisi.isler.yeni')}
            </Button>
            <Button size="icon" variant="ghost" onClick={() => void sil()} aria-label={t('sahaServisi.sil')}>
              <Trash2 className="h-4 w-4" aria-hidden="true" />
            </Button>
          </div>
        )}
      </div>

      <section className={`${KART} p-4`}>
        <div className="mb-2 flex items-center justify-between">
          <h4 className="font-semibold">{t('sahaServisi.lokasyon.baslik')}</h4>
          {!saltOkunur && (
            <Button size="sm" variant="ghost" className="gap-1" onClick={() => setLokAcik((x) => !x)}>
              <Plus className="h-4 w-4" aria-hidden="true" />
              {t('sahaServisi.ekle')}
            </Button>
          )}
        </div>
        <ul className="space-y-2 text-sm">
          {(m.lokasyonlar || []).map((l) => (
            <li key={l.id} className="flex items-start gap-2">
              <MapPin className="mt-0.5 h-4 w-4 flex-none text-purple-300" aria-hidden="true" />
              <span className="min-w-0 flex-1">
                <span className="font-medium">{l.ad}</span> — {l.tam_adres || '—'}
                {l.notlar && <span className="block text-xs text-amber-200/90">{l.notlar}</span>}
              </span>
              {l.harita && (
                <a href={l.harita} target="_blank" rel="noopener noreferrer" className="text-xs text-purple-200 hover:underline">
                  {t('sahaServisi.ayrinti.haritadaAc')}
                </a>
              )}
            </li>
          ))}
        </ul>
        {lokAcik && (
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            <Alan etiket={t('sahaServisi.lokasyon.ad')}>
              <input className={GIRDI} value={lok.ad} maxLength={120} onChange={(e) => setLok({ ...lok, ad: e.target.value })} />
            </Alan>
            <Alan etiket={t('sahaServisi.lokasyon.adres')}>
              <input className={GIRDI} value={lok.adres} maxLength={500} onChange={(e) => setLok({ ...lok, adres: e.target.value })} />
            </Alan>
            <Alan etiket={t('sahaServisi.lokasyon.ilce')}>
              <input className={GIRDI} value={lok.ilce} maxLength={80} onChange={(e) => setLok({ ...lok, ilce: e.target.value })} />
            </Alan>
            <Alan etiket={t('sahaServisi.lokasyon.il')}>
              <input className={GIRDI} value={lok.il} maxLength={80} onChange={(e) => setLok({ ...lok, il: e.target.value })} />
            </Alan>
            <Alan etiket={t('sahaServisi.lokasyon.notlar')} className="sm:col-span-2">
              <input className={GIRDI} value={lok.notlar} maxLength={1000} onChange={(e) => setLok({ ...lok, notlar: e.target.value })} placeholder={t('sahaServisi.lokasyon.notOrnek')} />
            </Alan>
            <Button className="w-fit" onClick={() => void lokasyonEkle()}>
              {t('sahaServisi.kaydet')}
            </Button>
          </div>
        )}
      </section>

      <section className={`${KART} p-4`} data-testid="saha-cihazlar">
        <div className="mb-2 flex items-center justify-between">
          <h4 className="font-semibold">{t('sahaServisi.cihaz.baslik')}</h4>
          {!saltOkunur && (
            <Button size="sm" variant="ghost" className="gap-1" onClick={() => setCihazAcik((x) => !x)} data-testid="saha-cihaz-ekle-ac">
              <Plus className="h-4 w-4" aria-hidden="true" />
              {t('sahaServisi.ekle')}
            </Button>
          )}
        </div>
        {(m.cihazlar || []).length === 0 && !cihazAcik && <p className="text-sm text-muted-foreground">{t('sahaServisi.cihaz.bos')}</p>}
        <ul className="divide-y divide-white/5 text-sm">
          {(m.cihazlar || []).map((c) => (
            <li key={c.id} className="py-2" data-testid="saha-cihaz">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{c.tur}</span>
                <span className="text-muted-foreground">{[c.marka, c.model].filter(Boolean).join(' ')}</span>
                {c.seri_no && (
                  <span className="font-mono text-xs text-muted-foreground" dir="ltr">
                    {c.seri_no}
                  </span>
                )}
                {!c.aktif && <Rozet>{t('sahaServisi.pasif')}</Rozet>}
                {c.garantide && <Rozet renk="border-emerald-400/30 bg-emerald-500/10 text-emerald-200">{t('sahaServisi.cihaz.garantide')}</Rozet>}
                {c.bakim_vadesi && (
                  <Rozet renk={c.bakim_vadesi <= bugun ? 'border-red-400/40 bg-red-500/15 text-red-200' : 'border-white/10 bg-white/[0.05] text-muted-foreground'}>
                    {t('sahaServisi.cihaz.vade', { tarih: c.bakim_vadesi })}
                  </Rozet>
                )}
                <span className="ms-auto flex gap-1">
                  <Button size="sm" variant="ghost" className="gap-1" onClick={() => void gecmisAc(c)}>
                    <History className="h-4 w-4" aria-hidden="true" />
                    {t('sahaServisi.cihaz.gecmis')}
                  </Button>
                  {!saltOkunur && c.bakim_periyot_ay && (
                    <Button size="sm" variant="ghost" className="gap-1" onClick={() => setYeniIs({ cihaz: c.id })}>
                      <Wrench className="h-4 w-4" aria-hidden="true" />
                      {t('sahaServisi.cihaz.bakimIsi')}
                    </Button>
                  )}
                </span>
              </div>
              {gecmis?.id === c.id && (
                <ul className="mt-2 space-y-1 rounded-lg bg-black/20 p-2 text-xs">
                  {gecmis.isler.length === 0 ? (
                    <li className="text-muted-foreground">{t('sahaServisi.cihaz.gecmisBos')}</li>
                  ) : (
                    gecmis.isler.map((x) => (
                      <li key={x.id}>
                        <button type="button" className="flex w-full flex-wrap items-center gap-2 text-start hover:underline" onClick={() => onAc(x.id)}>
                          <span className="font-mono" dir="ltr">
                            {x.no}
                          </span>
                          <DurumRozeti durum={x.durum} />
                          <span>{t(`sahaServisi.tur.${x.tur}`)}</span>
                          <span className="text-muted-foreground">{tarihSaat(x.bitir_at || x.plan_bas, i18n.language)}</span>
                        </button>
                      </li>
                    ))
                  )}
                </ul>
              )}
            </li>
          ))}
        </ul>
        {cihazAcik && (
          <div className="mt-3 grid gap-2 sm:grid-cols-3" data-testid="saha-cihaz-formu">
            <Alan etiket={t('sahaServisi.cihaz.tur')}>
              <input className={GIRDI} value={cihaz.tur} maxLength={60} placeholder={t('sahaServisi.cihaz.turOrnek')} onChange={(e) => setCihaz({ ...cihaz, tur: e.target.value })} data-testid="saha-cihaz-tur" />
            </Alan>
            <Alan etiket={t('sahaServisi.cihaz.marka')}>
              <input className={GIRDI} value={cihaz.marka} maxLength={80} onChange={(e) => setCihaz({ ...cihaz, marka: e.target.value })} data-testid="saha-cihaz-marka" />
            </Alan>
            <Alan etiket={t('sahaServisi.cihaz.model')}>
              <input className={GIRDI} value={cihaz.model} maxLength={80} onChange={(e) => setCihaz({ ...cihaz, model: e.target.value })} />
            </Alan>
            <Alan etiket={t('sahaServisi.cihaz.seriNo')}>
              <input className={GIRDI} value={cihaz.seri_no} maxLength={80} onChange={(e) => setCihaz({ ...cihaz, seri_no: e.target.value })} dir="ltr" data-testid="saha-cihaz-seri" />
            </Alan>
            <Alan etiket={t('sahaServisi.cihaz.kurulum')}>
              <input type="date" className={GIRDI} value={cihaz.kurulum_tarihi} onChange={(e) => setCihaz({ ...cihaz, kurulum_tarihi: e.target.value })} />
            </Alan>
            <Alan etiket={t('sahaServisi.cihaz.garanti')}>
              <input type="date" className={GIRDI} value={cihaz.garanti_bitis} onChange={(e) => setCihaz({ ...cihaz, garanti_bitis: e.target.value })} />
            </Alan>
            <Alan etiket={t('sahaServisi.cihaz.sonBakim')}>
              <input type="date" className={GIRDI} value={cihaz.son_bakim} onChange={(e) => setCihaz({ ...cihaz, son_bakim: e.target.value })} />
            </Alan>
            <Alan etiket={t('sahaServisi.cihaz.periyot')}>
              <input type="number" min={1} max={120} className={GIRDI} value={cihaz.bakim_periyot_ay} onChange={(e) => setCihaz({ ...cihaz, bakim_periyot_ay: e.target.value })} dir="ltr" data-testid="saha-cihaz-periyot" />
            </Alan>
            {(m.lokasyonlar || []).length > 0 && (
              <Alan etiket={t('sahaServisi.lokasyon.ad')}>
                <select className={SECIM} value={cihaz.lokasyon_id} onChange={(e) => setCihaz({ ...cihaz, lokasyon_id: e.target.value })}>
                  <option value="">—</option>
                  {m.lokasyonlar!.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.ad}
                    </option>
                  ))}
                </select>
              </Alan>
            )}
            <div className="sm:col-span-3">
              <Button onClick={() => void cihazEkle()} disabled={!cihaz.tur.trim()} data-testid="saha-cihaz-kaydet">
                {t('sahaServisi.kaydet')}
              </Button>
            </div>
          </div>
        )}
      </section>

      <section className={`${KART} p-4`}>
        <h4 className="mb-2 font-semibold">{t('sahaServisi.musteri.isler')}</h4>
        {(m.isler || []).length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('sahaServisi.isler.bos')}</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {m.isler!.map((x) => (
              <li key={x.id}>
                <button type="button" className="flex w-full flex-wrap items-center gap-2 rounded-lg px-2 py-1.5 text-start hover:bg-white/[0.04]" onClick={() => onAc(x.id)}>
                  <span className="font-mono text-xs text-muted-foreground" dir="ltr">
                    {x.no}
                  </span>
                  <span className="min-w-0 flex-1 truncate">{x.baslik}</span>
                  <DurumRozeti durum={x.durum} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
      {yeniIs && (
        <Suspense fallback={null}>
          <IsFormu
            api={api}
            musteriId={m.id}
            cihazId={yeniIs.cihaz}
            onKapat={() => setYeniIs(null)}
            onKaydedildi={(d) => {
              setYeniIs(null);
              onAc(d.id);
            }}
          />
        </Suspense>
      )}
    </div>
  );
}
