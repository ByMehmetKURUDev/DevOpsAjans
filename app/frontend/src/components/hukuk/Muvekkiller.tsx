import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Building2, Copy, Link2, Loader2, Plus, RefreshCw, Search, Trash2, User, XCircle } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Alan, CatismaListesi, GIRDI, KART, METIN_ALANI, Not, Rozet, SECIM, Yukleniyor, kopyala } from '@/components/hukuk/ortak';
import { gunYaz, hataMetni, type Catisma, type HukukApi, type Meta, type Muvekkil } from '@/lib/hukuk';

type Form = Pick<Muvekkil, 'tur' | 'ad' | 'yetkili' | 'vergi_no' | 'eposta' | 'telefon' | 'adres' | 'notlar'> & {
  kaynak?: 'randevu';
  kaynak_id?: number;
};
const BOS: Form = { tur: 'kisi', ad: '', yetkili: '', vergi_no: '', eposta: '', telefon: '', adres: '', notlar: '' };

/** Faz 6H — müvekkiller: liste, kişi/şirket formu, canlı çıkar çatışması kontrolü, portal bağlantısı. */
export default function Muvekkiller({ api, meta, onDosyaAc }: { api: HukukApi; meta: Meta; onDosyaAc: (id: number) => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [liste, setListe] = useState<Muvekkil[] | null>(null);
  const [q, setQ] = useState('');
  const [secili, setSecili] = useState<Muvekkil | null>(null);
  const [yeni, setYeni] = useState(false);
  const [form, setForm] = useState<Form>(BOS);
  const [catisma, setCatisma] = useState<Catisma[] | null>(null);
  const [kaydediliyor, setKaydediliyor] = useState(false);
  const [randevular, setRandevular] = useState<{ id: number; ad: string; eposta: string; telefon: string; baslangic: string | null }[]>([]);
  const zamanlayici = useRef<number | null>(null);

  const yukle = useCallback(async () => {
    try {
      setListe((await api.muvekkiller(q.trim() || undefined)).items);
    } catch (e) {
      toast.error(hataMetni(t, e));
      setListe([]);
    }
  }, [api, q, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  useEffect(() => {
    api
      .randevuKayitlari()
      .then((r) => setRandevular(r.items))
      .catch(() => setRandevular([]));
  }, [api]);

  const ac = async (m: Muvekkil) => {
    setYeni(false);
    setCatisma(null);
    try {
      const tam = await api.muvekkil(m.id);
      setSecili(tam);
      setForm({ tur: tam.tur, ad: tam.ad, yetkili: tam.yetkili, vergi_no: tam.vergi_no, eposta: tam.eposta, telefon: tam.telefon, adres: tam.adres, notlar: tam.notlar });
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const yeniAc = () => {
    setSecili(null);
    setYeni(true);
    setForm(BOS);
    setCatisma(null);
  };

  // Ad / vergi no değişince (yazmayı bitirince) çatışma kontrolü — engellemez, yalnız uyarır.
  const kontrolEt = useCallback(
    (f: Form) => {
      if (zamanlayici.current) window.clearTimeout(zamanlayici.current);
      if (!f.ad.trim() && !f.vergi_no.trim()) {
        setCatisma(null);
        return;
      }
      zamanlayici.current = window.setTimeout(() => {
        api
          .catisma({ ad: f.ad, vergi_no: f.vergi_no || undefined, rol: 'muvekkil', haric_muvekkil_id: secili?.id })
          .then((r) => setCatisma(r.items))
          .catch(() => setCatisma(null));
      }, 450);
    },
    [api, secili?.id]
  );

  const alan = <K extends keyof Form>(k: K, v: Form[K]) => {
    const yeniForm = { ...form, [k]: v };
    setForm(yeniForm);
    if (k === 'ad' || k === 'vergi_no') kontrolEt(yeniForm);
  };

  const kaydet = async () => {
    if (!form.ad.trim()) {
      toast.error(t('hukuk.ortak.zorunlu'));
      return;
    }
    setKaydediliyor(true);
    try {
      const g = { ...form };
      const r = secili ? await api.muvekkilKaydet(secili.id, g) : await api.muvekkilEkle(g);
      toast.success(t('hukuk.ortak.kaydedildi'));
      if (r.catisma.length) setCatisma(r.catisma);
      setYeni(false);
      await yukle();
      await ac(r.muvekkil);
      if (r.catisma.length) setCatisma(r.catisma);
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setKaydediliyor(false);
    }
  };

  const sil = async () => {
    if (!secili || !window.confirm(t('hukuk.ortak.onaySil'))) return;
    try {
      await api.muvekkilSil(secili.id);
      toast.success(t('hukuk.ortak.silindi', { gun: meta.silinenler_gun }));
      setSecili(null);
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const portal = async (islem: 'olustur' | 'iptal') => {
    if (!secili) return;
    try {
      if (islem === 'olustur') {
        const r = await api.portalOlustur(secili.id);
        setSecili({ ...secili, ...r.muvekkil, dosyalar: secili.dosyalar });
        toast.success(t('hukuk.muvekkil.portal.olusturuldu'));
      } else {
        await api.portalIptal(secili.id);
        setSecili({ ...secili, portal_acik: false, portal_baglantisi: null });
        toast.success(t('hukuk.muvekkil.portal.iptalEdildi'));
      }
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const formAcik = yeni || secili !== null;

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)]" data-testid="hukuk-muvekkiller">
      <div className={`${KART} p-4`}>
        <div className="mb-3 flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute start-2 top-2.5 h-4 w-4 text-muted-foreground" aria-hidden="true" />
            <input className={`${GIRDI} ps-8`} value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('hukuk.ortak.ara')} aria-label={t('hukuk.ortak.ara')} />
          </div>
          <Button size="sm" onClick={yeniAc} className="gap-1" data-testid="hukuk-muvekkil-yeni">
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('hukuk.muvekkil.yeni')}
          </Button>
        </div>
        {liste === null ? (
          <Yukleniyor />
        ) : liste.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">{t('hukuk.muvekkil.bos')}</p>
        ) : (
          <ul className="space-y-1" data-testid="hukuk-muvekkil-liste">
            {liste.map((m) => (
              <li key={m.id}>
                <button
                  type="button"
                  onClick={() => void ac(m)}
                  className={`flex w-full items-center gap-2 rounded-lg px-2 py-2 text-start text-sm hover:bg-white/[0.05] ${secili?.id === m.id ? 'bg-white/[0.07]' : ''}`}
                  data-muvekkil-id={m.id}
                >
                  {m.tur === 'sirket' ? <Building2 className="h-4 w-4 text-muted-foreground" aria-hidden="true" /> : <User className="h-4 w-4 text-muted-foreground" aria-hidden="true" />}
                  <span className="min-w-0 flex-1 truncate">{m.ad}</span>
                  {!!m.okunmamis && <Rozet renk="border-amber-400/40 bg-amber-500/15 text-amber-200">{t('hukuk.muvekkil.okunmamis', { sayi: m.okunmamis })}</Rozet>}
                  <span className="text-[11px] text-muted-foreground">{t('hukuk.muvekkil.dosyaSayisi', { sayi: m.dosya_sayisi || 0 })}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="space-y-4">
        {!formAcik ? (
          <div className={`${KART} p-6 text-sm text-muted-foreground`}>{t('hukuk.muvekkil.secin')}</div>
        ) : (
          <div className={`${KART} space-y-3 p-4 sm:p-6`} data-testid="hukuk-muvekkil-form">
            <h3 className="text-base font-semibold">{secili ? secili.ad : t('hukuk.muvekkil.yeni')}</h3>
            {yeni && randevular.length > 0 && (
              <Alan etiket={t('hukuk.muvekkil.randevudan')}>
                <select
                  className={SECIM}
                  defaultValue=""
                  onChange={(e) => {
                    const r = randevular.find((x) => String(x.id) === e.target.value);
                    if (!r) return;
                    const f: Form = { ...form, ad: r.ad, eposta: r.eposta, telefon: r.telefon, kaynak: 'randevu', kaynak_id: r.id };
                    setForm(f);
                    kontrolEt(f);
                  }}
                >
                  <option value="">{t('hukuk.muvekkil.randevuSec')}</option>
                  {randevular.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.ad || r.eposta} · {gunYaz(r.baslangic, dil)}
                    </option>
                  ))}
                </select>
              </Alan>
            )}
            <div className="grid gap-3 sm:grid-cols-2">
              <Alan etiket={t('hukuk.muvekkil.turEtiket')}>
                <select className={SECIM} value={form.tur} onChange={(e) => alan('tur', e.target.value as Form['tur'])} data-testid="hukuk-muvekkil-tur">
                  {meta.muvekkil_turleri.map((x) => (
                    <option key={x} value={x}>
                      {t(`hukuk.muvekkil.tur.${x}`)}
                    </option>
                  ))}
                </select>
              </Alan>
              <Alan etiket={form.tur === 'sirket' ? t('hukuk.muvekkil.adSirket') : t('hukuk.muvekkil.ad')}>
                <input className={GIRDI} value={form.ad} maxLength={200} onChange={(e) => alan('ad', e.target.value)} data-testid="hukuk-muvekkil-ad" />
              </Alan>
              {form.tur === 'sirket' && (
                <Alan etiket={t('hukuk.muvekkil.yetkili')}>
                  <input className={GIRDI} value={form.yetkili} maxLength={160} onChange={(e) => alan('yetkili', e.target.value)} />
                </Alan>
              )}
              <Alan etiket={t('hukuk.muvekkil.vergiNo')} ipucu={t('hukuk.muvekkil.vergiNoIpucu')}>
                <input className={GIRDI} value={form.vergi_no} maxLength={24} dir="ltr" onChange={(e) => alan('vergi_no', e.target.value)} data-testid="hukuk-muvekkil-vergi" />
              </Alan>
              <Alan etiket={t('hukuk.muvekkil.eposta')}>
                <input className={GIRDI} type="email" dir="ltr" value={form.eposta} onChange={(e) => alan('eposta', e.target.value)} />
              </Alan>
              <Alan etiket={t('hukuk.muvekkil.telefon')}>
                <input className={GIRDI} type="tel" dir="ltr" value={form.telefon} onChange={(e) => alan('telefon', e.target.value)} />
              </Alan>
            </div>
            <Alan etiket={t('hukuk.muvekkil.adres')}>
              <textarea className={METIN_ALANI} value={form.adres} maxLength={1000} onChange={(e) => alan('adres', e.target.value)} />
            </Alan>
            <Alan etiket={t('hukuk.muvekkil.notlar')}>
              <textarea className={METIN_ALANI} value={form.notlar} maxLength={20000} onChange={(e) => alan('notlar', e.target.value)} />
            </Alan>
            <CatismaListesi items={catisma} />
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => void kaydet()} disabled={kaydediliyor} className="gap-1.5" data-testid="hukuk-muvekkil-kaydet">
                {kaydediliyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
                {t('hukuk.ortak.kaydet')}
              </Button>
              <Button
                variant="ghost"
                onClick={() => {
                  setYeni(false);
                  setSecili(null);
                }}
              >
                {t('hukuk.ortak.vazgec')}
              </Button>
              {secili && (
                <Button variant="ghost" className="ms-auto gap-1 text-red-300" onClick={() => void sil()}>
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                  {t('hukuk.ortak.sil')}
                </Button>
              )}
            </div>
          </div>
        )}

        {secili && (
          <div className={`${KART} space-y-3 p-4 sm:p-6`} data-testid="hukuk-portal">
            <h3 className="flex items-center gap-2 text-base font-semibold">
              <Link2 className="h-4 w-4" aria-hidden="true" />
              {t('hukuk.muvekkil.portal.baslik')}
            </h3>
            <p className="text-xs text-muted-foreground">{t('hukuk.muvekkil.portal.aciklama')}</p>
            {secili.portal_acik && secili.portal_baglantisi ? (
              <div className="flex min-w-0 items-center gap-1 rounded-lg border border-white/10 bg-black/30 p-2">
                <a href={secili.portal_baglantisi} target="_blank" rel="noopener noreferrer" className="min-w-0 flex-1 truncate font-mono text-xs text-blue-200" dir="ltr" data-testid="hukuk-portal-baglanti">
                  {secili.portal_baglantisi}
                </a>
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-7 w-7"
                  aria-label={t('hukuk.ortak.kopyala')}
                  onClick={() => void kopyala(secili.portal_baglantisi || '', t('hukuk.ortak.kopyalandi'), t('hukuk.ortak.kopyalanamadi'))}
                >
                  <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                </Button>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">{t('hukuk.muvekkil.portal.kapali')}</p>
            )}
            {secili.portal_son_at && <p className="text-xs text-muted-foreground">{t('hukuk.muvekkil.portal.sonGiris', { zaman: gunYaz(secili.portal_son_at, dil) })}</p>}
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" className="gap-1 !bg-transparent" onClick={() => void portal('olustur')} data-testid="hukuk-portal-olustur">
                <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                {secili.portal_acik ? t('hukuk.muvekkil.portal.yenile') : t('hukuk.muvekkil.portal.olustur')}
              </Button>
              {secili.portal_acik && (
                <Button size="sm" variant="ghost" className="gap-1 text-red-300" onClick={() => void portal('iptal')} data-testid="hukuk-portal-iptal">
                  <XCircle className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('hukuk.muvekkil.portal.iptal')}
                </Button>
              )}
            </div>
            <Not>{t('hukuk.dosya.portal.gizlilik')}</Not>
          </div>
        )}

        {secili && (
          <div className={`${KART} p-4 sm:p-6`}>
            <h3 className="mb-2 text-base font-semibold">{t('hukuk.alt.dosyalar')}</h3>
            {(secili.dosyalar || []).length === 0 ? (
              <p className="text-sm text-muted-foreground">{t('hukuk.dosya.bos')}</p>
            ) : (
              <ul className="space-y-1">
                {(secili.dosyalar || []).map((d) => (
                  <li key={d.id}>
                    <button type="button" className="w-full truncate rounded-lg px-2 py-1.5 text-start text-sm hover:bg-white/[0.05]" onClick={() => onDosyaAc(d.id)}>
                      {d.baslik} · <span className="text-xs text-muted-foreground">{t(`hukuk.dosya.durum.${d.durum}`)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
