import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CheckCircle2, Circle, Download, Eye, EyeOff, Link2, Loader2, Paperclip, Plus, Trash2, Upload } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Alan, Anahtar, GIRDI, KART, Not, OLAY_RENGI, Rozet, SECIM, Yukleniyor } from '@/components/hukuk/ortak';
import {
  boyutYaz,
  gunYaz,
  hataMetni,
  paraYaz,
  type Dosya,
  type Ek,
  type HukukApi,
  type Masraf,
  type MasrafToplami,
  type Meta,
  type Olay,
  type Zaman,
} from '@/lib/hukuk';

/** Faz 6H — dosyanın alt kayıtları: takvim olayları, saat, masraf (+ makbuz, PDF döküm), belgeler (+ portal paylaşımı). */

export function sureYaz(t: (k: string, o?: Record<string, unknown>) => string, dk: number): string {
  const sa = Math.floor(dk / 60);
  const kalan = dk % 60;
  if (sa && kalan) return `${sa} ${t('hukuk.zaman.saat')} ${kalan} ${t('hukuk.zaman.dk')}`;
  if (sa) return `${sa} ${t('hukuk.zaman.saat')}`;
  return `${kalan} ${t('hukuk.zaman.dk')}`;
}

export function kalanYaz(t: (k: string, o?: Record<string, unknown>) => string, o: Pick<Olay, 'kalan_gun' | 'tamamlandi'>): string {
  if (o.tamamlandi) return t('hukuk.olay.tamamlandi');
  if (o.kalan_gun === 0) return t('hukuk.olay.bugun');
  if (o.kalan_gun < 0) return t('hukuk.olay.gecti');
  return t('hukuk.olay.kalan', { sayi: o.kalan_gun });
}

// ---------------------------------------------------------------------------------------------- Olaylar
export function OlayFormu({ api, meta, dosyaId, onEklendi, varsayilanTarih }: { api: HukukApi; meta: Meta; dosyaId: number | null; onEklendi: (o: Olay) => void; varsayilanTarih?: string }) {
  const { t } = useTranslation();
  const [tur, setTur] = useState('durusma');
  const [baslik, setBaslik] = useState('');
  const [tarih, setTarih] = useState(varsayilanTarih || meta.bugun);
  const [saat, setSaat] = useState('');
  const [yer, setYer] = useState('');
  const [sorumlu, setSorumlu] = useState('');
  const [kayit, setKayit] = useState(false);

  const ekle = async () => {
    setKayit(true);
    try {
      const o = await api.olayEkle({ dosya_id: dosyaId, tur, baslik, tarih, saat: saat || null, yer, sorumlu_email: sorumlu || null });
      toast.success(t('hukuk.ortak.kaydedildi'));
      setBaslik('');
      setSaat('');
      setYer('');
      onEklendi(o);
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setKayit(false);
    }
  };

  return (
    <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-6 lg:items-end" data-testid="hukuk-olay-formu">
      <Alan etiket={t('hukuk.olay.alan.tur')}>
        <select className={SECIM} value={tur} onChange={(e) => setTur(e.target.value)} data-testid="hukuk-olay-tur">
          {meta.olay_turleri.map((x) => (
            <option key={x} value={x}>
              {t(`hukuk.olay.tur.${x}`)}
            </option>
          ))}
        </select>
      </Alan>
      <Alan etiket={t('hukuk.olay.alan.baslik')}>
        <input className={GIRDI} value={baslik} maxLength={200} onChange={(e) => setBaslik(e.target.value)} data-testid="hukuk-olay-baslik" />
      </Alan>
      <Alan etiket={t('hukuk.olay.alan.tarih')}>
        <input className={GIRDI} type="date" value={tarih} onChange={(e) => setTarih(e.target.value)} data-testid="hukuk-olay-tarih" />
      </Alan>
      <Alan etiket={t('hukuk.olay.alan.saat')}>
        <input className={GIRDI} type="time" value={saat} onChange={(e) => setSaat(e.target.value)} data-testid="hukuk-olay-saat" />
      </Alan>
      <Alan etiket={t('hukuk.olay.alan.yer')}>
        <input className={GIRDI} value={yer} maxLength={200} onChange={(e) => setYer(e.target.value)} />
      </Alan>
      <Alan etiket={t('hukuk.olay.alan.sorumlu')}>
        <select className={SECIM} value={sorumlu} onChange={(e) => setSorumlu(e.target.value)}>
          <option value="">—</option>
          {meta.ekip.map((k) => (
            <option key={k.eposta} value={k.eposta}>
              {k.eposta}
            </option>
          ))}
        </select>
      </Alan>
      <Button onClick={() => void ekle()} disabled={kayit || !tarih} className="gap-1 lg:col-span-6 lg:justify-self-start" data-testid="hukuk-olay-ekle">
        {kayit ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />}
        {t('hukuk.olay.yeni')}
      </Button>
    </div>
  );
}

export function OlaySatiri({ o, onDegisti, api, dil }: { o: Olay; onDegisti: () => void; api: HukukApi; dil: string }) {
  const { t } = useTranslation();
  const degistir = async (g: Record<string, unknown>) => {
    try {
      await api.olayKaydet(o.id, g);
      onDegisti();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };
  const sil = async () => {
    if (!window.confirm(t('hukuk.ortak.onaySil'))) return;
    try {
      await api.olaySil(o.id);
      onDegisti();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };
  return (
    <li className={`flex flex-wrap items-center gap-2 rounded-lg border border-white/10 bg-black/20 p-2 text-sm ${o.tamamlandi ? 'opacity-60' : ''}`} data-olay-id={o.id}>
      <button type="button" onClick={() => void degistir({ tamamlandi: !o.tamamlandi })} aria-label={o.tamamlandi ? t('hukuk.olay.geriAl') : t('hukuk.olay.tamamla')}>
        {o.tamamlandi ? <CheckCircle2 className="h-4 w-4 text-emerald-300" aria-hidden="true" /> : <Circle className="h-4 w-4 text-muted-foreground" aria-hidden="true" />}
      </button>
      <Rozet renk={OLAY_RENGI[o.tur]}>{t(`hukuk.olay.tur.${o.tur}`)}</Rozet>
      <span className="font-medium">{gunYaz(o.tarih, dil)}{o.saat ? ` ${o.saat}` : ''}</span>
      {o.baslik && <span className="min-w-0 truncate">{o.baslik}</span>}
      {o.dosya_baslik && <span className="min-w-0 truncate text-xs text-muted-foreground">{o.dosya_baslik}</span>}
      {o.yer && <span className="text-xs text-muted-foreground">{o.yer}</span>}
      <span className={`ms-auto text-xs ${!o.tamamlandi && o.kalan_gun <= 3 && o.kalan_gun >= 0 ? 'text-rose-300' : 'text-muted-foreground'}`}>{kalanYaz(t, o)}</span>
      <Button size="icon" variant="ghost" className="h-7 w-7" aria-label={t('hukuk.ortak.sil')} onClick={() => void sil()}>
        <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
      </Button>
    </li>
  );
}

export function OlaylarPaneli({ api, meta, dosya }: { api: HukukApi; meta: Meta; dosya: Dosya }) {
  const { t, i18n } = useTranslation();
  const [liste, setListe] = useState<Olay[] | null>(null);
  const yukle = useCallback(async () => {
    try {
      setListe((await api.olaylar({ dosya_id: dosya.id })).items);
    } catch (e) {
      toast.error(hataMetni(t, e));
      setListe([]);
    }
  }, [api, dosya.id, t]);
  useEffect(() => {
    void yukle();
  }, [yukle]);
  return (
    <div className={`${KART} space-y-4 p-4 sm:p-6`} data-testid="hukuk-dosya-olaylar">
      <OlayFormu api={api} meta={meta} dosyaId={dosya.id} onEklendi={() => void yukle()} />
      {liste === null ? (
        <Yukleniyor />
      ) : liste.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('hukuk.olay.bos')}</p>
      ) : (
        <ul className="space-y-1.5" data-testid="hukuk-olay-liste">
          {liste.map((o) => (
            <OlaySatiri key={o.id} o={o} api={api} dil={i18n.language || 'tr'} onDegisti={() => void yukle()} />
          ))}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------- Zaman
export function ZamanPaneli({ api, dosya }: { api: HukukApi; dosya: Dosya }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [veri, setVeri] = useState<{ items: Zaman[]; toplam_dk: number; faturalanabilir_dk: number } | null>(null);
  const [tarih, setTarih] = useState(new Date().toISOString().slice(0, 10));
  const [saat, setSaat] = useState('');
  const [dk, setDk] = useState('');
  const [aciklama, setAciklama] = useState('');
  const [fat, setFat] = useState(true);
  const yukle = useCallback(async () => {
    try {
      setVeri(await api.zaman(dosya.id));
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  }, [api, dosya.id, t]);
  useEffect(() => {
    void yukle();
  }, [yukle]);
  const ekle = async () => {
    const sure = (Number(saat) || 0) * 60 + (Number(dk) || 0);
    if (sure <= 0) {
      toast.error(t('hukuk.ortak.zorunlu'));
      return;
    }
    try {
      await api.zamanEkle(dosya.id, { tarih, sure_dk: sure, aciklama, faturalanabilir: fat });
      setSaat('');
      setDk('');
      setAciklama('');
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };
  return (
    <div className={`${KART} space-y-4 p-4 sm:p-6`} data-testid="hukuk-dosya-zaman">
      <div className="grid gap-2 sm:grid-cols-[150px_80px_80px_minmax(0,1fr)] sm:items-end">
        <Alan etiket={t('hukuk.zaman.tarih')}>
          <input className={GIRDI} type="date" value={tarih} onChange={(e) => setTarih(e.target.value)} />
        </Alan>
        <Alan etiket={t('hukuk.zaman.saatEtiket')}>
          <input className={GIRDI} type="number" min={0} max={24} value={saat} onChange={(e) => setSaat(e.target.value)} data-testid="hukuk-zaman-saat" />
        </Alan>
        <Alan etiket={t('hukuk.zaman.dkEtiket')}>
          <input className={GIRDI} type="number" min={0} max={59} value={dk} onChange={(e) => setDk(e.target.value)} data-testid="hukuk-zaman-dk" />
        </Alan>
        <Alan etiket={t('hukuk.zaman.aciklama')}>
          <input className={GIRDI} value={aciklama} maxLength={500} onChange={(e) => setAciklama(e.target.value)} data-testid="hukuk-zaman-aciklama" />
        </Alan>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Anahtar acik={fat} onDegis={setFat} etiket={t('hukuk.zaman.faturalanabilir')} />
        <Button size="sm" className="gap-1" onClick={() => void ekle()} data-testid="hukuk-zaman-ekle">
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('hukuk.zaman.ekle')}
        </Button>
      </div>
      {!veri ? (
        <Yukleniyor />
      ) : veri.items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('hukuk.zaman.bos')}</p>
      ) : (
        <>
          <ul className="space-y-1" data-testid="hukuk-zaman-liste">
            {veri.items.map((z) => (
              <li key={z.id} className="flex flex-wrap items-center gap-2 border-b border-white/5 py-1.5 text-sm">
                <span className="w-28 text-xs text-muted-foreground">{gunYaz(z.tarih, dil)}</span>
                <span className="font-medium">{sureYaz(t, z.sure_dk)}</span>
                <span className="min-w-0 flex-1 truncate">{z.aciklama}</span>
                {z.faturalanabilir && <Rozet>{t('hukuk.zaman.faturalanabilir')}</Rozet>}
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-7 w-7"
                  aria-label={t('hukuk.ortak.sil')}
                  onClick={async () => {
                    await api.zamanSil(dosya.id, z.id).catch((e) => toast.error(hataMetni(t, e)));
                    await yukle();
                  }}
                >
                  <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                </Button>
              </li>
            ))}
          </ul>
          <p className="text-sm" data-testid="hukuk-zaman-toplam">
            {t('hukuk.zaman.toplam', { sure: sureYaz(t, veri.toplam_dk), fat: sureYaz(t, veri.faturalanabilir_dk) })}
          </p>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------- Masraf
export function MasrafPaneli({ api, meta, dosya }: { api: HukukApi; meta: Meta; dosya: Dosya }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [veri, setVeri] = useState<{ items: Masraf[]; toplamlar: MasrafToplami[] } | null>(null);
  const [tur, setTur] = useState('harc');
  const [tutar, setTutar] = useState('');
  const [para, setPara] = useState('TRY');
  const [tarih, setTarih] = useState(meta.bugun);
  const [aciklama, setAciklama] = useState('');
  const [avans, setAvans] = useState(false);
  const [indiriliyor, setIndiriliyor] = useState(false);
  const makbuzGirdi = useRef<HTMLInputElement>(null);
  const [makbuzHedef, setMakbuzHedef] = useState<number | null>(null);

  const yukle = useCallback(async () => {
    try {
      setVeri(await api.masraflar(dosya.id));
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  }, [api, dosya.id, t]);
  useEffect(() => {
    void yukle();
  }, [yukle]);

  const ekle = async () => {
    try {
      await api.masrafEkle(dosya.id, { tur, tutar, para_birimi: para, tarih, aciklama, avanstan: avans });
      setTutar('');
      setAciklama('');
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const pdf = async () => {
    setIndiriliyor(true);
    try {
      await api.dokumIndir(dosya.id, dil.slice(0, 2), `dokum-${dosya.dosya_no || dosya.id}.pdf`);
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setIndiriliyor(false);
    }
  };

  return (
    <div className={`${KART} space-y-4 p-4 sm:p-6`} data-testid="hukuk-dosya-masraf">
      <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-[150px_140px_100px_150px_minmax(0,1fr)] lg:items-end">
        <Alan etiket={t('hukuk.masraf.turEtiket')}>
          <select className={SECIM} value={tur} onChange={(e) => setTur(e.target.value)} data-testid="hukuk-masraf-tur">
            {meta.masraf_turleri.map((x) => (
              <option key={x} value={x}>
                {t(`hukuk.masraf.tur.${x}`)}
              </option>
            ))}
          </select>
        </Alan>
        <Alan etiket={t('hukuk.masraf.tutar')}>
          <input className={GIRDI} inputMode="decimal" value={tutar} onChange={(e) => setTutar(e.target.value)} placeholder="1.250,50" data-testid="hukuk-masraf-tutar" />
        </Alan>
        <Alan etiket={t('hukuk.masraf.para')}>
          <select className={SECIM} value={para} onChange={(e) => setPara(e.target.value)}>
            {meta.para_birimleri.map((x) => (
              <option key={x} value={x}>
                {x}
              </option>
            ))}
          </select>
        </Alan>
        <Alan etiket={t('hukuk.masraf.tarih')}>
          <input className={GIRDI} type="date" value={tarih} onChange={(e) => setTarih(e.target.value)} />
        </Alan>
        <Alan etiket={t('hukuk.masraf.aciklama')}>
          <input className={GIRDI} value={aciklama} maxLength={300} onChange={(e) => setAciklama(e.target.value)} data-testid="hukuk-masraf-aciklama" />
        </Alan>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Anahtar acik={avans} onDegis={setAvans} etiket={t('hukuk.masraf.avanstan')} />
        <Button size="sm" className="gap-1" onClick={() => void ekle()} disabled={!tutar.trim()} data-testid="hukuk-masraf-ekle">
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('hukuk.masraf.ekle')}
        </Button>
        <Button size="sm" variant="outline" className="ms-auto gap-1 !bg-transparent" onClick={() => void pdf()} disabled={indiriliyor} data-testid="hukuk-dokum-pdf">
          {indiriliyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Download className="h-4 w-4" aria-hidden="true" />}
          {t('hukuk.masraf.pdf')}
        </Button>
      </div>
      <input
        ref={makbuzGirdi}
        type="file"
        className="hidden"
        accept=".pdf,.jpg,.jpeg,.png,.webp"
        onChange={async (e) => {
          const f = e.target.files?.[0];
          e.target.value = '';
          if (!f || makbuzHedef === null) return;
          try {
            await api.makbuzYukle(dosya.id, makbuzHedef, f);
            toast.success(t('hukuk.masraf.makbuzVar'));
            await yukle();
          } catch (err) {
            toast.error(hataMetni(t, err));
          }
        }}
      />
      {!veri ? (
        <Yukleniyor />
      ) : veri.items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('hukuk.masraf.bos')}</p>
      ) : (
        <>
          <ul className="space-y-1" data-testid="hukuk-masraf-liste">
            {veri.items.map((x) => (
              <li key={x.id} className="flex flex-wrap items-center gap-2 border-b border-white/5 py-1.5 text-sm">
                <span className="w-28 text-xs text-muted-foreground">{gunYaz(x.tarih, dil)}</span>
                <Rozet>{t(`hukuk.masraf.tur.${x.tur}`)}</Rozet>
                <span className="min-w-0 flex-1 truncate">{x.aciklama}</span>
                {x.avanstan && <Rozet renk="border-sky-400/40 bg-sky-500/15 text-sky-100">{t('hukuk.masraf.avanstan')}</Rozet>}
                <span className="font-medium tabular-nums">{paraYaz(x.tutar_kurus, x.para_birimi, dil)}</span>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 gap-1 px-2 text-xs"
                  onClick={() => {
                    setMakbuzHedef(x.id);
                    makbuzGirdi.current?.click();
                  }}
                >
                  <Paperclip className="h-3.5 w-3.5" aria-hidden="true" />
                  {x.makbuz_ek_id ? t('hukuk.masraf.makbuz') : t('hukuk.masraf.makbuzYukle')}
                </Button>
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-7 w-7"
                  aria-label={t('hukuk.ortak.sil')}
                  onClick={async () => {
                    await api.masrafSil(dosya.id, x.id).catch((e) => toast.error(hataMetni(t, e)));
                    await yukle();
                  }}
                >
                  <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                </Button>
              </li>
            ))}
          </ul>
          <div className="text-sm" data-testid="hukuk-masraf-toplam">
            {veri.toplamlar.map((tp) => (
              <p key={tp.para_birimi}>
                {t('hukuk.masraf.toplam', { tutar: paraYaz(tp.toplam_kurus, tp.para_birimi, dil) })}
                {tp.avans_kurus > 0 && <span className="text-muted-foreground"> · {t('hukuk.masraf.avansToplam', { tutar: paraYaz(tp.avans_kurus, tp.para_birimi, dil) })}</span>}
              </p>
            ))}
          </div>
        </>
      )}
      <Not>{t('hukuk.masraf.tahsilatYok')}</Not>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------- Belgeler
export function BelgelerPaneli({ api, meta, dosya }: { api: HukukApi; meta: Meta; dosya: Dosya }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [liste, setListe] = useState<Ek[] | null>(null);
  const [gorunur, setGorunur] = useState(false);
  const [yukleniyor, setYukleniyor] = useState(false);
  const [belgeler, setBelgeler] = useState<{ id: number; baslik: string }[] | null>(null);
  const girdi = useRef<HTMLInputElement>(null);

  const yukle = useCallback(async () => {
    try {
      setListe((await api.ekler(dosya.id)).items);
    } catch (e) {
      toast.error(hataMetni(t, e));
      setListe([]);
    }
  }, [api, dosya.id, t]);
  useEffect(() => {
    void yukle();
    api
      .belgelerim()
      .then((r) => setBelgeler(r.items))
      .catch(() => setBelgeler([]));
  }, [api, yukle]);

  const dosyaSec = async (f: File | undefined) => {
    if (!f) return;
    setYukleniyor(true);
    try {
      await api.ekYukle(dosya.id, f, gorunur);
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setYukleniyor(false);
    }
  };

  return (
    <div className={`${KART} space-y-4 p-4 sm:p-6`} data-testid="hukuk-dosya-belgeler">
      <div className="flex flex-wrap items-center gap-3">
        <input ref={girdi} type="file" className="hidden" onChange={(e) => void dosyaSec(e.target.files?.[0]).finally(() => (e.target.value = ''))} data-testid="hukuk-ek-girdi" />
        <Button size="sm" className="gap-1" onClick={() => girdi.current?.click()} disabled={yukleniyor}>
          {yukleniyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Upload className="h-4 w-4" aria-hidden="true" />}
          {t('hukuk.belge.yukle')}
        </Button>
        <Anahtar acik={gorunur} onDegis={setGorunur} etiket={t('hukuk.belge.gorunurYukle')} testid="hukuk-ek-gorunur" />
        <span className="text-xs text-muted-foreground">{t('hukuk.belge.boyutIpucu', { mb: meta.dosya_en_cok_mb })}</span>
      </div>
      {belgeler && belgeler.length > 0 && (
        <Alan etiket={t('hukuk.belge.baglanti')}>
          <select
            className={SECIM}
            defaultValue=""
            onChange={async (e) => {
              const id = Number(e.target.value);
              e.target.value = '';
              if (!id) return;
              try {
                await api.ekBaglanti(dosya.id, id);
                await yukle();
              } catch (err) {
                toast.error(hataMetni(t, err));
              }
            }}
          >
            <option value="">{t('hukuk.belge.baglantiSec')}</option>
            {belgeler.map((b) => (
              <option key={b.id} value={b.id}>
                {b.baslik}
              </option>
            ))}
          </select>
        </Alan>
      )}
      {liste === null ? (
        <Yukleniyor />
      ) : liste.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('hukuk.belge.bos')}</p>
      ) : (
        <ul className="space-y-1" data-testid="hukuk-ek-liste">
          {liste.map((e) => (
            <li key={e.id} className="flex flex-wrap items-center gap-2 border-b border-white/5 py-1.5 text-sm" data-ek-id={e.id}>
              {e.tip === 'baglanti' ? <Link2 className="h-4 w-4 text-muted-foreground" aria-hidden="true" /> : <Paperclip className="h-4 w-4 text-muted-foreground" aria-hidden="true" />}
              <span className="min-w-0 flex-1 truncate">{e.ad}</span>
              {e.tip === 'baglanti' && <Rozet>{t('hukuk.belge.baglantiRozet')}</Rozet>}
              {e.tip === 'makbuz' && <Rozet>{t('hukuk.belge.makbuzRozet')}</Rozet>}
              {e.tip !== 'baglanti' && <span className="text-xs text-muted-foreground">{boyutYaz(e.boyut)} · {gunYaz(e.created_at, dil)}</span>}
              {e.tip !== 'baglanti' && (
                <button
                  type="button"
                  className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] ${e.muvekkile_gorunur ? 'border-emerald-400/40 bg-emerald-500/15 text-emerald-200' : 'border-white/10 text-muted-foreground'}`}
                  onClick={async () => {
                    try {
                      await api.ekKaydet(dosya.id, e.id, { muvekkile_gorunur: !e.muvekkile_gorunur });
                      await yukle();
                    } catch (err) {
                      toast.error(hataMetni(t, err));
                    }
                  }}
                  data-testid="hukuk-ek-gorunurluk"
                >
                  {e.muvekkile_gorunur ? <Eye className="h-3 w-3" aria-hidden="true" /> : <EyeOff className="h-3 w-3" aria-hidden="true" />}
                  {e.muvekkile_gorunur ? t('hukuk.belge.gorunur') : t('hukuk.belge.gizli')}
                </button>
              )}
              {e.tip !== 'baglanti' && (
                <Button size="icon" variant="ghost" className="h-7 w-7" aria-label={t('hukuk.ortak.indir')} onClick={() => void api.ekIndir(dosya.id, e).catch((err) => toast.error(hataMetni(t, err)))}>
                  <Download className="h-3.5 w-3.5" aria-hidden="true" />
                </Button>
              )}
              <Button
                size="icon"
                variant="ghost"
                className="h-7 w-7"
                aria-label={t('hukuk.ortak.sil')}
                onClick={async () => {
                  if (!window.confirm(t('hukuk.ortak.onaySil'))) return;
                  await api.ekSil(dosya.id, e.id).catch((err) => toast.error(hataMetni(t, err)));
                  await yukle();
                }}
              >
                <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
              </Button>
            </li>
          ))}
        </ul>
      )}
      {belgeler !== null && belgeler.length === 0 && <p className="text-xs text-muted-foreground">{t('hukuk.belge.baglantiYok')}</p>}
    </div>
  );
}
