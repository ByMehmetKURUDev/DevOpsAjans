import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Copy, Download, FileUp, Link2, Loader2, Mail, Plus, RefreshCw, Search, Trash2, Unlink, Upload } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Alan, Bos, DIS_DUGME, GIRDI, KART, METIN_ALANI, Pencere, Rozet, SECIM, YasalNot, Yukleniyor } from '@/components/ik/ortak';
import { dar, DURUM_RENGI, aralikYaz, gunYaz, hataMetni, sayiYaz, type IkApi, type Meta, type Personel, type PersonelAyrinti } from '@/lib/ik';

type Form = {
  ad: string;
  eposta: string;
  telefon: string;
  gorev: string;
  departman: string;
  ise_giris: string;
  durum: 'aktif' | 'ayrildi';
  ayrilis_tarihi: string;
  yas_grubu: 'genel' | 'genc' | 'ileri';
  devir_gun: string;
  devir_tarihi: string;
  yillik_gun_ozel: string;
  notlar: string;
  dil: string;
};

const BOS_FORM = (bugun: string): Form => ({
  ad: '',
  eposta: '',
  telefon: '',
  gorev: '',
  departman: '',
  ise_giris: bugun,
  durum: 'aktif',
  ayrilis_tarihi: '',
  yas_grubu: 'genel',
  devir_gun: '',
  devir_tarihi: '',
  yillik_gun_ozel: '',
  notlar: '',
  dil: 'tr',
});

function formdan(p: Personel): Form {
  return {
    ad: p.ad,
    eposta: p.eposta || '',
    telefon: p.telefon || '',
    gorev: p.gorev || '',
    departman: p.departman || '',
    ise_giris: p.ise_giris,
    durum: p.durum,
    ayrilis_tarihi: p.ayrilis_tarihi || '',
    yas_grubu: p.yas_grubu || 'genel',
    devir_gun: p.devir_gun ? String(p.devir_gun) : '',
    devir_tarihi: p.devir_tarihi || '',
    yillik_gun_ozel: p.yillik_gun_ozel ? String(p.yillik_gun_ozel) : '',
    notlar: p.notlar || '',
    dil: p.dil || 'tr',
  };
}

function govde(f: Form): Record<string, unknown> {
  return {
    ad: f.ad.trim(),
    eposta: f.eposta.trim(),
    telefon: f.telefon.trim(),
    gorev: f.gorev.trim(),
    departman: f.departman.trim(),
    ise_giris: f.ise_giris,
    durum: f.durum,
    ayrilis_tarihi: f.durum === 'ayrildi' ? f.ayrilis_tarihi || null : null,
    yas_grubu: f.yas_grubu,
    devir_gun: f.devir_gun.replace(',', '.') || 0,
    devir_tarihi: f.devir_tarihi || null,
    yillik_gun_ozel: f.yillik_gun_ozel || null,
    notlar: f.notlar,
    dil: f.dil,
  };
}

const DILLER = ['tr', 'en', 'de', 'ru', 'zh', 'hi', 'ar'];

function PersonelFormu({ form, setForm, meta }: { form: Form; setForm: (f: Form) => void; meta: Meta }) {
  const { t } = useTranslation();
  const d = (alan: keyof Form) => (e: { target: { value: string } }) => setForm({ ...form, [alan]: e.target.value });
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <Alan etiket={t('ik.personel.ad')} className="sm:col-span-2">
        <input className={GIRDI} value={form.ad} onChange={d('ad')} maxLength={120} data-testid="ik-personel-ad" />
      </Alan>
      <Alan etiket={t('ik.personel.eposta')} ipucu={t('ik.personel.epostaIpucu')}>
        <input className={GIRDI} type="email" dir="ltr" value={form.eposta} onChange={d('eposta')} data-testid="ik-personel-eposta" />
      </Alan>
      <Alan etiket={t('ik.personel.telefon')}>
        <input className={GIRDI} type="tel" dir="ltr" value={form.telefon} onChange={d('telefon')} />
      </Alan>
      <Alan etiket={t('ik.personel.gorev')}>
        <input className={GIRDI} value={form.gorev} onChange={d('gorev')} maxLength={120} data-testid="ik-personel-gorev" />
      </Alan>
      <Alan etiket={t('ik.personel.departman')}>
        <input className={GIRDI} value={form.departman} onChange={d('departman')} maxLength={120} list="ik-departmanlar" />
        <datalist id="ik-departmanlar">
          {meta.departmanlar.map((x) => (
            <option key={x} value={x} />
          ))}
        </datalist>
      </Alan>
      <Alan etiket={t('ik.personel.iseGiris')}>
        <input className={GIRDI} type="date" value={form.ise_giris} onChange={d('ise_giris')} data-testid="ik-personel-ise-giris" />
      </Alan>
      <Alan etiket={t('ik.personel.durumEtiket')}>
        <select className={SECIM} value={form.durum} onChange={d('durum')}>
          <option value="aktif">{t('ik.personel.durum.aktif')}</option>
          <option value="ayrildi">{t('ik.personel.durum.ayrildi')}</option>
        </select>
      </Alan>
      {form.durum === 'ayrildi' && (
        <Alan etiket={t('ik.personel.ayrilis')}>
          <input className={GIRDI} type="date" value={form.ayrilis_tarihi} onChange={d('ayrilis_tarihi')} />
        </Alan>
      )}
      <Alan etiket={t('ik.personel.yasGrubu')} ipucu={t('ik.personel.yasGrubuIpucu')}>
        <select className={SECIM} value={form.yas_grubu} onChange={d('yas_grubu')} data-testid="ik-personel-yas">
          <option value="genel">{t('ik.personel.yas.genel')}</option>
          <option value="genc">{t('ik.personel.yas.genc')}</option>
          <option value="ileri">{t('ik.personel.yas.ileri')}</option>
        </select>
      </Alan>
      <Alan etiket={t('ik.personel.dil')}>
        <select className={SECIM} value={form.dil} onChange={d('dil')}>
          {DILLER.map((x) => (
            <option key={x} value={x}>
              {t(`ik.dil.${x}`)}
            </option>
          ))}
        </select>
      </Alan>
      <Alan etiket={t('ik.personel.devirGun')} ipucu={t('ik.personel.devirIpucu')}>
        <input className={GIRDI} inputMode="decimal" value={form.devir_gun} onChange={d('devir_gun')} placeholder="0" data-testid="ik-personel-devir" />
      </Alan>
      <Alan etiket={t('ik.personel.devirTarihi')}>
        <input className={GIRDI} type="date" value={form.devir_tarihi} onChange={d('devir_tarihi')} />
      </Alan>
      <Alan etiket={t('ik.personel.ozelGun')} ipucu={t('ik.personel.ozelGunIpucu')}>
        <input className={GIRDI} inputMode="numeric" value={form.yillik_gun_ozel} onChange={d('yillik_gun_ozel')} />
      </Alan>
      <Alan etiket={t('ik.personel.notlar')} className="sm:col-span-2">
        <textarea className={METIN_ALANI} value={form.notlar} onChange={d('notlar')} maxLength={4000} />
      </Alan>
      <p className="text-xs text-muted-foreground sm:col-span-2">{t('ik.personel.veriAzaltma')}</p>
    </div>
  );
}

function BakiyeKarti({ p, dil }: { p: Personel; dil: string }) {
  const { t } = useTranslation();
  const b = p.bakiye;
  if (!b) return null;
  return (
    <div className="rounded-xl border border-purple-400/25 bg-purple-500/10 p-3" data-testid="ik-bakiye">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-sm text-muted-foreground">{t('ik.bakiye.kalan')}</span>
        <span className="text-2xl font-bold" data-testid="ik-bakiye-kalan">
          {sayiYaz(b.kalan, dil)} <span className="text-sm font-normal text-muted-foreground">{t('ik.gun')}</span>
        </span>
      </div>
      <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs sm:grid-cols-3">
        <div>
          <dt className="text-muted-foreground">{t('ik.bakiye.devir')}</dt>
          <dd>{sayiYaz(b.devir, dil)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">{t('ik.bakiye.kazanilan')}</dt>
          <dd>{sayiYaz(b.kazanilan, dil)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">{t('ik.bakiye.kullanilan')}</dt>
          <dd>{sayiYaz(b.kullanilan, dil)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">{t('ik.bakiye.bekleyen')}</dt>
          <dd>{sayiYaz(b.bekleyen, dil)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">{t('ik.bakiye.kidem')}</dt>
          <dd>{t('ik.bakiye.yil', { sayi: b.kidem_yil })}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">{t('ik.bakiye.sonraki')}</dt>
          <dd>{b.sonraki ? t('ik.bakiye.sonrakiMetin', { tarih: gunYaz(b.sonraki.tarih, dil), gun: b.sonraki.gun }) : '—'}</dd>
        </div>
      </dl>
    </div>
  );
}

function Ayrinti({ api, meta, id, onKapat, onDegisti }: { api: IkApi; meta: Meta; id: number; onKapat: () => void; onDegisti: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [p, setP] = useState<PersonelAyrinti | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [mesgul, setMesgul] = useState(false);
  const [adres, setAdres] = useState<string | null>(null);
  const dosyaRef = useRef<HTMLInputElement | null>(null);
  const salt = meta.salt_okunur;

  const yukle = useCallback(async () => {
    try {
      const x = await api.personel(id);
      setP(x);
      setForm(formdan(x));
    } catch (e) {
      toast.error(hataMetni(t, e));
      onKapat();
    }
  }, [api, id, onKapat, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const kaydet = async () => {
    if (!form) return;
    setMesgul(true);
    try {
      await api.personelGuncelle(id, govde(form));
      toast.success(t('ik.kaydedildi'));
      onDegisti();
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  const baglanti = async (islem: 'goster' | 'yenile' | 'iptal', gonder = false) => {
    if (islem === 'iptal' && !window.confirm(t('ik.portal.iptalOnay'))) return;
    if (islem === 'yenile' && !window.confirm(t('ik.portal.yenileOnay'))) return;
    try {
      const r = await api.baglanti(id, islem, gonder);
      setAdres(r.adres);
      if (gonder && r.gonderildi) toast.success(t('ik.portal.gonderildi'));
      else if (islem === 'iptal') toast.success(t('ik.portal.iptalEdildi'));
      else if (islem === 'yenile') toast.success(t('ik.portal.yenilendi'));
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const kopyala = async () => {
    if (!adres) return;
    try {
      await navigator.clipboard.writeText(adres);
      toast.success(t('ik.kopyalandi'));
    } catch {
      toast.error(t('ik.kopyalanamadi'));
    }
  };

  const sil = async () => {
    if (!window.confirm(t('ik.personel.silOnay'))) return;
    try {
      await api.personelSil(id);
      toast.success(t('ik.personel.silindi'));
      onDegisti();
      onKapat();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const dosyaYukle = async (f: File | undefined) => {
    if (!f) return;
    try {
      await api.dosyaEkle(id, f);
      toast.success(t('ik.dosya.yuklendi'));
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  return (
    <Pencere baslik={p?.ad || t('ik.personel.ayrinti')} onKapat={onKapat} genis testid="ik-personel-ayrinti">
      {!p || !form ? (
        <Yukleniyor />
      ) : (
        <div className="space-y-4">
          <BakiyeKarti p={p} dil={dil} />
          {!salt && (
            <div className={`${KART} space-y-2 p-3`} data-testid="ik-portal-kutusu">
              <h4 className="flex items-center gap-1.5 text-sm font-semibold">
                <Link2 className="h-4 w-4 text-purple-300" aria-hidden="true" />
                {t('ik.portal.baslik')}
              </h4>
              <p className="text-xs text-muted-foreground">{t('ik.portal.aciklama')}</p>
              {adres && (
                <div className="flex min-w-0 items-center gap-1 rounded-lg border border-white/10 bg-black/30 px-2 py-1.5">
                  <a href={adres} target="_blank" rel="noopener noreferrer" className="truncate font-mono text-xs text-purple-200 hover:underline" dir="ltr" data-testid="ik-portal-adres">
                    {adres.replace(/^https?:\/\//, '')}
                  </a>
                  <Button size="icon" variant="ghost" className="h-7 w-7 flex-none" aria-label={t('ik.kopyala')} onClick={() => void kopyala()}>
                    <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                  </Button>
                </div>
              )}
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => void baglanti('goster')} disabled={p.durum !== 'aktif'} data-testid="ik-portal-goster">
                  <Link2 className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('ik.portal.goster')}
                </Button>
                <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => void baglanti('goster', true)} disabled={!p.eposta || p.durum !== 'aktif'}>
                  <Mail className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('ik.portal.gonder')}
                </Button>
                <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => void baglanti('yenile')} disabled={p.durum !== 'aktif'}>
                  <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('ik.portal.yenile')}
                </Button>
                <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => void baglanti('iptal')}>
                  <Unlink className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('ik.portal.iptal')}
                </Button>
              </div>
              {p.portal_son_at && <p className="text-[11px] text-muted-foreground">{t('ik.portal.sonAcilis', { tarih: gunYaz(p.portal_son_at, dil) })}</p>}
            </div>
          )}
          <fieldset disabled={salt} className="space-y-3">
            <PersonelFormu form={form} setForm={setForm} meta={meta} />
          </fieldset>
          <div>
            <h4 className="mb-2 text-sm font-semibold">{t('ik.personel.izinGecmisi')}</h4>
            {p.izinler.length === 0 ? (
              <p className="text-xs text-muted-foreground">{t('ik.izin.bos')}</p>
            ) : (
              <ul className="space-y-1.5">
                {p.izinler.slice(0, 20).map((i) => (
                  <li key={i.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs">
                    <span className="font-medium">{t(`ik.tur.${i.tur}`)}</span>
                    <span className="text-muted-foreground">{aralikYaz(i.baslangic, i.bitis, dil)}</span>
                    <span className="text-muted-foreground">{t('ik.izin.gunSayisi', { sayi: sayiYaz(i.gun, dil) })}</span>
                    <Rozet renk={DURUM_RENGI[i.durum]}>{t(`ik.durum.${i.durum}`)}</Rozet>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <div className="mb-2 flex items-center justify-between gap-2">
              <h4 className="text-sm font-semibold">{t('ik.dosya.baslik')}</h4>
              {!salt && (
                <>
                  <input ref={dosyaRef} type="file" className="hidden" onChange={(e) => void dosyaYukle(e.target.files?.[0])} />
                  <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => dosyaRef.current?.click()}>
                    <FileUp className="h-3.5 w-3.5" aria-hidden="true" />
                    {t('ik.dosya.ekle')}
                  </Button>
                </>
              )}
            </div>
            {p.dosyalar.length === 0 ? (
              <p className="text-xs text-muted-foreground">{t('ik.dosya.bos')}</p>
            ) : (
              <ul className="space-y-1.5">
                {p.dosyalar.map((d) => (
                  <li key={d.id} className="flex items-center gap-2 rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs">
                    <span className="min-w-0 flex-1 truncate">{d.ad}</span>
                    <Button size="icon" variant="ghost" className="h-7 w-7" aria-label={t('ik.dosya.indir')} onClick={() => void api.dosyaIndir(d.id, d.ad).catch((e) => toast.error(hataMetni(t, e)))}>
                      <Download className="h-3.5 w-3.5" aria-hidden="true" />
                    </Button>
                    {!salt && (
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-7 w-7"
                        aria-label={t('ik.dosya.sil')}
                        onClick={() =>
                          void api
                            .dosyaSil(d.id)
                            .then(() => yukle())
                            .catch((e) => toast.error(hataMetni(t, e)))
                        }
                      >
                        <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
          {!salt && (
            <div className="flex flex-wrap justify-between gap-2 border-t border-white/10 pt-3">
              <Button variant="outline" className={`${DIS_DUGME} text-rose-200`} onClick={() => void sil()} data-testid="ik-personel-sil">
                <Trash2 className="h-4 w-4" aria-hidden="true" />
                {t('ik.personel.sil')}
              </Button>
              <Button onClick={() => void kaydet()} disabled={mesgul} data-testid="ik-personel-kaydet">
                {mesgul && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
                {t('ik.kaydet')}
              </Button>
            </div>
          )}
        </div>
      )}
    </Pencere>
  );
}

export default function PersonelBolumu({ api, meta, onMeta }: { api: IkApi; meta: Meta; onMeta: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [liste, setListe] = useState<Personel[] | null>(null);
  const [durum, setDurum] = useState('aktif');
  const [ara, setAra] = useState('');
  const [departman, setDepartman] = useState('');
  const [yeni, setYeni] = useState<Form | null>(null);
  const [secili, setSecili] = useState<number | null>(null);
  const [mesgul, setMesgul] = useState(false);
  const [csvAcik, setCsvAcik] = useState(false);
  const [csvMetni, setCsvMetni] = useState('');
  const salt = meta.salt_okunur;
  const sinirDolu = meta.personel_siniri != null && meta.aktif_personel >= meta.personel_siniri;
  const kapat = useCallback(() => setSecili(null), []);
  const yeniKapat = useCallback(() => setYeni(null), []);
  const csvKapat = useCallback(() => setCsvAcik(false), []);

  const yukle = useCallback(async () => {
    try {
      setListe((await api.personelListesi({ durum, ara: ara.trim() || undefined, departman: departman || undefined })).items);
    } catch (e) {
      toast.error(hataMetni(t, e));
      setListe([]);
    }
  }, [api, ara, departman, durum, t]);

  useEffect(() => {
    const z = window.setTimeout(() => void yukle(), ara ? 250 : 0);
    return () => window.clearTimeout(z);
  }, [yukle, ara]);

  const degisti = useCallback(() => {
    onMeta();
    void yukle();
  }, [onMeta, yukle]);

  const ekle = async () => {
    if (!yeni) return;
    if (!yeni.ad.trim()) {
      toast.error(t('ik.hata.zorunlu'));
      return;
    }
    setMesgul(true);
    try {
      await api.personelEkle(govde(yeni));
      toast.success(t('ik.personel.eklendi'));
      setYeni(null);
      onMeta();
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  const iceAktar = async (metin: string) => {
    setMesgul(true);
    try {
      const r = await api.iceAktar(metin);
      toast.success(t('ik.csv.sonuc', { eklenen: r.eklenen, guncellenen: r.guncellenen, hata: r.hata_sayisi }));
      if (r.hata_sayisi) {
        toast.warning(
          r.hatalar
            .slice(0, 5)
            .map((h) => `${t('ik.csv.satir', { sayi: h.satir })}: ${t(`ik.hata.${h.kod}`, { defaultValue: h.kod })}`)
            .join(' · ')
        );
      }
      setCsvAcik(false);
      setCsvMetni('');
      onMeta();
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className={`${KART} flex flex-wrap items-end gap-2 p-3`}>
        <label className="relative min-w-[12rem] flex-1">
          <span className="sr-only">{t('ik.ara')}</span>
          <Search className="pointer-events-none absolute start-2.5 top-3 h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <input className={`${GIRDI} ps-8`} value={ara} onChange={(e) => setAra(e.target.value)} placeholder={t('ik.personel.araIpucu')} data-testid="ik-personel-ara" />
        </label>
        <select className={dar(SECIM, 'w-auto')} value={durum} onChange={(e) => setDurum(e.target.value)} aria-label={t('ik.personel.durumEtiket')}>
          <option value="aktif">{t('ik.personel.durum.aktif')}</option>
          <option value="ayrildi">{t('ik.personel.durum.ayrildi')}</option>
          <option value="hepsi">{t('ik.hepsi')}</option>
        </select>
        {meta.departmanlar.length > 0 && (
          <select className={dar(SECIM, 'w-auto')} value={departman} onChange={(e) => setDepartman(e.target.value)} aria-label={t('ik.personel.departman')}>
            <option value="">{t('ik.personel.tumDepartmanlar')}</option>
            {meta.departmanlar.map((x) => (
              <option key={x} value={x}>
                {x}
              </option>
            ))}
          </select>
        )}
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" className={DIS_DUGME} onClick={() => void api.personelCsv().catch((e) => toast.error(hataMetni(t, e)))}>
            <Download className="h-4 w-4" aria-hidden="true" />
            {t('ik.csv.disa')}
          </Button>
          {!salt && (
            <>
              <Button variant="outline" className={DIS_DUGME} onClick={() => setCsvAcik(true)}>
                <Upload className="h-4 w-4" aria-hidden="true" />
                {t('ik.csv.ice')}
              </Button>
              <Button onClick={() => setYeni(BOS_FORM(meta.bugun))} disabled={sinirDolu} className="gap-1.5" data-testid="ik-personel-yeni">
                <Plus className="h-4 w-4" aria-hidden="true" />
                {t('ik.personel.ekle')}
              </Button>
            </>
          )}
        </div>
      </div>
      {meta.personel_siniri != null && (
        <p className="text-xs text-muted-foreground">{t('ik.personel.sinir', { sayi: meta.aktif_personel, sinir: meta.personel_siniri })}</p>
      )}
      <div className={`${KART} p-3 sm:p-4`}>
        {liste === null ? (
          <Yukleniyor />
        ) : liste.length === 0 ? (
          <Bos>{t('ik.personel.bos')}</Bos>
        ) : (
          <ul className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3" data-testid="ik-personel-liste">
            {liste.map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  onClick={() => setSecili(p.id)}
                  className="flex h-full w-full items-start gap-3 rounded-xl border border-white/10 bg-black/20 p-3 text-start transition-colors hover:border-purple-400/40 hover:bg-white/[0.04]"
                  data-testid="ik-personel-ac"
                  data-personel-id={p.id}
                >
                  <span className="flex h-10 w-10 flex-none items-center justify-center rounded-full bg-purple-500/20 text-sm font-semibold text-purple-100" aria-hidden="true">
                    {p.ad
                      .split(/\s+/)
                      .slice(0, 2)
                      .map((x) => x[0])
                      .join('')
                      .toLocaleUpperCase(dil)}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{p.ad}</span>
                    <span className="block truncate text-[11px] text-muted-foreground">{[p.gorev, p.departman].filter(Boolean).join(' · ') || '—'}</span>
                    <span className="mt-1.5 flex flex-wrap items-center gap-1">
                      <Rozet renk="border-purple-400/30 bg-purple-500/10 text-purple-100">
                        {t('ik.personel.kalanRozet', { sayi: sayiYaz(p.bakiye?.kalan ?? 0, dil) })}
                      </Rozet>
                      {!!p.bekleyen_izin && <Rozet renk={DURUM_RENGI.beklemede}>{t('ik.personel.bekleyenRozet', { sayi: p.bekleyen_izin })}</Rozet>}
                      {p.durum === 'ayrildi' && <Rozet>{t('ik.personel.durum.ayrildi')}</Rozet>}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <YasalNot />
      {yeni && (
        <Pencere baslik={t('ik.personel.ekle')} onKapat={yeniKapat} genis testid="ik-personel-formu">
          <PersonelFormu form={yeni} setForm={setYeni} meta={meta} />
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="outline" className={DIS_DUGME} onClick={() => setYeni(null)}>
              {t('ik.vazgec')}
            </Button>
            <Button onClick={() => void ekle()} disabled={mesgul} data-testid="ik-personel-kaydet-yeni">
              {mesgul && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
              {t('ik.kaydet')}
            </Button>
          </div>
        </Pencere>
      )}
      {csvAcik && (
        <Pencere baslik={t('ik.csv.ice')} onKapat={csvKapat} genis>
          <p className="mb-2 text-xs text-muted-foreground">{t('ik.csv.aciklama', { sayi: meta.en_cok_csv })}</p>
          <code className="mb-2 block overflow-x-auto rounded-lg bg-black/40 p-2 text-[11px]" dir="ltr">
            ad;eposta;telefon;gorev;departman;ise_giris;devir_gun
          </code>
          <input
            type="file"
            accept=".csv,text/csv"
            className="mb-2 block text-xs"
            onChange={async (e) => {
              const f = e.target.files?.[0];
              if (f) setCsvMetni(await f.text());
            }}
          />
          <textarea className={`${METIN_ALANI.replace('min-h-[72px]', 'min-h-[140px]')} font-mono text-xs`} dir="ltr" value={csvMetni} onChange={(e) => setCsvMetni(e.target.value)} />
          <div className="mt-3 flex justify-end">
            <Button onClick={() => void iceAktar(csvMetni)} disabled={mesgul || !csvMetni.trim()}>
              {mesgul && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
              {t('ik.csv.aktar')}
            </Button>
          </div>
        </Pencere>
      )}
      {secili !== null && <Ayrinti api={api} meta={meta} id={secili} onKapat={kapat} onDegisti={degisti} />}
    </div>
  );
}
