import { lazy, Suspense, useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowLeftRight, Download, FileDown, FileUp, Paperclip, Pencil, Plus, Trash2, Upload } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { HareketFormu, VirmanFormu } from '@/components/onMuhasebe/Form';
import { Bos, DIS_DUGME, GIRDI, HataSatiri, KART, Not, Pencere, Rozet, SECIM, Tutar, Yukleniyor } from '@/components/onMuhasebe/ortak';
import {
  gunYaz,
  hataMetni,
  kategoriAdi,
  para,
  TUR_RENGI,
  type BolumProps,
  type Hareket,
  type HareketSuzgeci,
  type Toplam,
} from '@/lib/onMuhasebe';

const IceAktar = lazy(() => import('@/components/onMuhasebe/IceAktar'));

const ADET = 50;

function etki(h: Hareket): number {
  if (h.tur === 'gelir' || h.tur === 'tahsilat') return h.tutar;
  if (h.tur === 'gider' || h.tur === 'odeme') return -h.tutar;
  return 0;
}

/** Faz 6M — hareketler: süzgeç, liste (toplamlar), yeni/düzenle, virman, ayrıntı + belge ekleri, CSV/PDF, CSV içe aktarma. */
export default function Hareketler({ api, meta, yenile, surum }: BolumProps) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const salt = meta.salt_okunur;
  const [suzgec, setSuzgec] = useState<HareketSuzgeci>({});
  const [ara, setAra] = useState('');
  const [items, setItems] = useState<Hareket[] | null>(null);
  const [toplam, setToplam] = useState(0);
  const [toplamlar, setToplamlar] = useState<Toplam[]>([]);
  const [sayfa, setSayfa] = useState(1);
  const [hata, setHata] = useState<string | null>(null);
  const [form, setForm] = useState<'yeni' | 'virman' | 'ice' | null>(null);
  const [duzenlenen, setDuzenlenen] = useState<Hareket | null>(null);
  const [ayrinti, setAyrinti] = useState<Hareket | null>(null);

  const yukle = useCallback(
    async (s = 1) => {
      setHata(null);
      try {
        const r = await api.hareketler({ ...suzgec, sayfa: s, adet: ADET });
        setItems((once) => (s === 1 || !once ? r.items : [...once, ...r.items]));
        setToplam(r.toplam);
        setToplamlar(r.toplamlar);
        setSayfa(s);
      } catch (e) {
        setHata(hataMetni(t, e));
      }
    },
    [api, suzgec, t]
  );

  useEffect(() => {
    void yukle(1);
  }, [yukle, surum]);

  // Arama kutusu: yazmayı bitirince süzgece geçer.
  useEffect(() => {
    const z = window.setTimeout(() => setSuzgec((s) => (s.ara === (ara || undefined) ? s : { ...s, ara: ara || undefined })), 350);
    return () => window.clearTimeout(z);
  }, [ara]);

  const ayrintiAc = async (h: Hareket) => {
    try {
      setAyrinti(await api.hareket(h.id));
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  };

  const kaydedildi = () => {
    setForm(null);
    setDuzenlenen(null);
    setAyrinti(null);
    yenile();
  };

  const set = (alan: keyof HareketSuzgeci, deger: string) =>
    setSuzgec((s) => ({ ...s, [alan]: deger === '' ? undefined : ['hesap_id', 'kategori_id'].includes(alan) ? Number(deger) : deger }));

  return (
    <div className="space-y-3" data-testid="mh-hareketler">
      <div className="flex flex-wrap items-center gap-2">
        {!salt && (
          <>
            <Button type="button" size="sm" className="gap-1.5" onClick={() => setForm('yeni')} disabled={!meta.hesaplar.length} data-testid="mh-hareket-yeni">
              <Plus className="h-4 w-4" aria-hidden="true" />
              {t('onMuhasebe.hareket.yeni')}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className={DIS_DUGME}
              onClick={() => setForm('virman')}
              disabled={meta.hesaplar.filter((h) => !h.arsiv).length < 2}
              data-testid="mh-virman-ac"
            >
              <ArrowLeftRight className="h-4 w-4" aria-hidden="true" />
              {t('onMuhasebe.hesap.virman')}
            </Button>
            <Button type="button" size="sm" variant="outline" className={DIS_DUGME} onClick={() => setForm('ice')} disabled={!meta.hesaplar.length} data-testid="mh-ice-aktar-ac">
              <FileUp className="h-4 w-4" aria-hidden="true" />
              {t('onMuhasebe.iceAktar.baslik')}
            </Button>
          </>
        )}
        <span className="flex-1" />
        <Button type="button" size="sm" variant="outline" className={DIS_DUGME} onClick={() => void api.hareketCsv(suzgec).catch((e) => setHata(hataMetni(t, e)))} data-testid="mh-hareket-csv">
          <Download className="h-4 w-4" aria-hidden="true" />
          CSV
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className={DIS_DUGME}
          onClick={() => void api.hareketPdf({ ...suzgec, dil }).catch((e) => setHata(hataMetni(t, e)))}
          data-testid="mh-hareket-pdf"
        >
          <FileDown className="h-4 w-4" aria-hidden="true" />
          PDF
        </Button>
      </div>
      <div className={`${KART} grid gap-2 p-3 sm:grid-cols-3 lg:grid-cols-6`}>
        <input type="date" className={GIRDI} aria-label={t('onMuhasebe.ortak.bas')} value={suzgec.bas ?? ''} onChange={(e) => set('bas', e.target.value)} />
        <input type="date" className={GIRDI} aria-label={t('onMuhasebe.ortak.bit')} value={suzgec.bit ?? ''} onChange={(e) => set('bit', e.target.value)} />
        <select className={SECIM} aria-label={t('onMuhasebe.ortak.tur')} value={suzgec.tur ?? ''} onChange={(e) => set('tur', e.target.value)} data-testid="mh-suzgec-tur">
          <option value="">{t('onMuhasebe.hareket.suzgec.tumTurler')}</option>
          {meta.sabitler.hareket_turleri.map((x) => (
            <option key={x} value={x}>
              {t(`onMuhasebe.tur.${x}`)}
            </option>
          ))}
        </select>
        <select className={SECIM} aria-label={t('onMuhasebe.ortak.hesap')} value={suzgec.hesap_id ?? ''} onChange={(e) => set('hesap_id', e.target.value)}>
          <option value="">{t('onMuhasebe.hareket.suzgec.tumHesaplar')}</option>
          {meta.hesaplar.map((h) => (
            <option key={h.id} value={h.id}>
              {h.ad}
            </option>
          ))}
        </select>
        <select className={SECIM} aria-label={t('onMuhasebe.ortak.kategori')} value={suzgec.kategori_id ?? ''} onChange={(e) => set('kategori_id', e.target.value)}>
          <option value="">{t('onMuhasebe.hareket.suzgec.tumKategoriler')}</option>
          {meta.kategoriler.map((k) => (
            <option key={k.id} value={k.id}>
              {t(`onMuhasebe.tur.${k.tur}`)} · {kategoriAdi(t, k)}
            </option>
          ))}
        </select>
        <input className={GIRDI} placeholder={t('onMuhasebe.hareket.suzgec.ara')} value={ara} onChange={(e) => setAra(e.target.value)} data-testid="mh-suzgec-ara" />
      </div>
      <HataSatiri hata={hata} />
      {toplamlar.length > 0 && (
        <div className="flex flex-wrap gap-2 text-xs" data-testid="mh-hareket-toplamlar">
          {toplamlar.map((x) => (
            <span key={x.para_birimi} className={`${KART} flex flex-wrap gap-3 px-3 py-2`}>
              <span>
                {t('onMuhasebe.ortak.gelir')}: <b className="text-emerald-300">{para(x.gelir, x.para_birimi, dil)}</b>
              </span>
              <span>
                {t('onMuhasebe.ortak.gider')}: <b className="text-rose-300">{para(x.gider, x.para_birimi, dil)}</b>
              </span>
              <span>
                {t('onMuhasebe.ortak.net')}: <b>{para(x.net, x.para_birimi, dil)}</b>
              </span>
            </span>
          ))}
        </div>
      )}
      {!items ? (
        <Yukleniyor />
      ) : !items.length ? (
        <Bos>{t('onMuhasebe.hareket.bos')}</Bos>
      ) : (
        <div className={`${KART} overflow-hidden`}>
          <ul className="divide-y divide-white/5" data-testid="mh-hareket-liste">
            {items.map((h) => (
              <li key={h.id}>
                <button
                  type="button"
                  onClick={() => void ayrintiAc(h)}
                  className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2.5 text-start text-sm hover:bg-white/[0.04]"
                  data-testid="mh-hareket-ac"
                  data-tur={h.tur}
                >
                  <span className="w-24 flex-none text-xs text-muted-foreground">{gunYaz(h.tarih, dil)}</span>
                  <Rozet renk={TUR_RENGI[h.tur]}>{t(`onMuhasebe.tur.${h.tur}`)}</Rozet>
                  {h.ters && <Rozet renk="border-zinc-400/30 bg-zinc-500/10 text-zinc-300">{t('onMuhasebe.hareket.ters')}</Rozet>}
                  {h.otomatik && !h.ters && <Rozet>{t(`onMuhasebe.kaynak.${h.kaynak}`)}</Rozet>}
                  <span className="min-w-0 flex-1 basis-40">
                    <span className="block truncate">{h.aciklama || (h.tur === 'virman' ? `${h.hesap} → ${h.hedef_hesap}` : h.cari || '—')}</span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {[h.kategori ? kategoriAdi(t, h.kategori) : null, h.tur !== 'virman' ? h.hesap || t('onMuhasebe.hareket.vadeli') : null, h.cari]
                        .filter(Boolean)
                        .join(' · ')}
                    </span>
                  </span>
                  {h.ek_sayisi > 0 && <Paperclip className="h-3.5 w-3.5 text-muted-foreground" aria-label={t('onMuhasebe.hareket.ekler')} />}
                  <Tutar deger={etki(h)} metin={para(h.tutar, h.para_birimi, dil)} notr={h.tur === 'virman'} />
                </button>
              </li>
            ))}
          </ul>
          {items.length < toplam && (
            <div className="border-t border-white/5 p-2 text-center">
              <Button type="button" variant="ghost" size="sm" onClick={() => void yukle(sayfa + 1)}>
                {t('onMuhasebe.hareket.dahaFazla', { gosterilen: items.length, toplam })}
              </Button>
            </div>
          )}
        </div>
      )}
      {ayrinti && (
        <Ayrinti
          h={ayrinti}
          salt={salt}
          api={api}
          onKapat={() => setAyrinti(null)}
          onDuzenle={() => {
            setDuzenlenen(ayrinti);
            setAyrinti(null);
          }}
          onDegisti={kaydedildi}
          onEkDegisti={() => void ayrintiAc(ayrinti)}
        />
      )}
      {duzenlenen && <HareketFormu api={api} meta={meta} hareket={duzenlenen} onKaydet={kaydedildi} onKapat={() => setDuzenlenen(null)} />}
      {form === 'yeni' && <HareketFormu api={api} meta={meta} onKaydet={kaydedildi} onKapat={() => setForm(null)} />}
      {form === 'virman' && <VirmanFormu api={api} meta={meta} onKaydet={kaydedildi} onKapat={() => setForm(null)} />}
      {form === 'ice' && (
        <Suspense fallback={null}>
          <IceAktar api={api} meta={meta} onBitti={kaydedildi} onKapat={() => setForm(null)} />
        </Suspense>
      )}
    </div>
  );
}

function Ayrinti({
  h,
  salt,
  api,
  onKapat,
  onDuzenle,
  onDegisti,
  onEkDegisti,
}: {
  h: Hareket;
  salt: boolean;
  api: BolumProps['api'];
  onKapat: () => void;
  onDuzenle: () => void;
  onDegisti: () => void;
  onEkDegisti: () => void;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [hata, setHata] = useState<string | null>(null);
  const [yukleniyor, setYukleniyor] = useState(false);
  const dosya = useRef<HTMLInputElement | null>(null);
  const satir = (ad: string, deger: ReactNode) =>
    deger === null || deger === undefined || deger === '' ? null : (
      <div className="flex justify-between gap-3 border-b border-white/5 py-1.5 text-sm">
        <span className="text-muted-foreground">{ad}</span>
        <span className="text-end">{deger}</span>
      </div>
    );

  const sil = async () => {
    if (!window.confirm(t('onMuhasebe.hareket.silOnay'))) return;
    try {
      await api.hareketSil(h.id);
      onDegisti();
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  };

  const ekYukle = async (f: File | undefined) => {
    if (!f) return;
    setYukleniyor(true);
    setHata(null);
    try {
      await api.ekYukle(h.id, f);
      onEkDegisti();
    } catch (e) {
      setHata(hataMetni(t, e));
    } finally {
      setYukleniyor(false);
      if (dosya.current) dosya.current.value = '';
    }
  };

  return (
    <Pencere baslik={`${t(`onMuhasebe.tur.${h.tur}`)} · ${gunYaz(h.tarih, dil)}`} onKapat={onKapat} testid="mh-hareket-ayrinti">
      <div className="space-y-3">
        {h.otomatik && <Not>{t('onMuhasebe.hareket.otomatikNot', { kaynak: t(`onMuhasebe.kaynak.${h.kaynak}`) })}</Not>}
        {h.ters && <Not>{t('onMuhasebe.hareket.tersNot')}</Not>}
        <div>
          {satir(t('onMuhasebe.ortak.tutar'), para(h.tutar, h.para_birimi, dil))}
          {h.tur !== 'virman' && h.kdv_tutari !== 0 && satir(t('onMuhasebe.ortak.kdvTutari'), `${para(h.kdv_tutari, h.para_birimi, dil)}${h.kdv_orani !== null ? ` (%${h.kdv_orani})` : ''}`)}
          {satir(t('onMuhasebe.ortak.kategori'), h.kategori ? kategoriAdi(t, h.kategori) : null)}
          {satir(h.tur === 'virman' ? t('onMuhasebe.hareket.kaynakHesap') : t('onMuhasebe.ortak.hesap'), h.hesap || (h.tur === 'gelir' || h.tur === 'gider' ? t('onMuhasebe.hareket.vadeli') : null))}
          {h.tur === 'virman' && satir(t('onMuhasebe.hareket.hedefHesap'), h.hedef_hesap)}
          {h.hedef_tutar !== null && satir(t('onMuhasebe.hareket.hedefTutar'), para(h.hedef_tutar, h.hedef_para_birimi || h.para_birimi, dil))}
          {satir(t('onMuhasebe.ortak.cari'), h.cari)}
          {satir(t('onMuhasebe.ortak.vade'), h.vade_tarihi ? gunYaz(h.vade_tarihi, dil) : null)}
          {satir(t('onMuhasebe.ortak.aciklama'), h.aciklama)}
          {satir(t('onMuhasebe.ortak.belgeNo'), h.belge_no)}
          {satir(t('onMuhasebe.ortak.etiketler'), h.etiketler.join(', '))}
          {satir(t('onMuhasebe.ortak.kaynak'), t(`onMuhasebe.kaynak.${h.kaynak}`))}
        </div>
        <div>
          <h4 className="mb-1 text-sm font-semibold">{t('onMuhasebe.hareket.ekler')}</h4>
          {(h.ekler || []).length ? (
            <ul className="space-y-1" data-testid="mh-ekler">
              {(h.ekler || []).map((e) => (
                <li key={e.id} className="flex items-center justify-between gap-2 text-sm">
                  <button type="button" className="truncate underline" onClick={() => void api.ekIndir(e.id, e.ad).catch((x) => setHata(hataMetni(t, x)))}>
                    {e.ad}
                  </button>
                  {!salt && (
                    <button
                      type="button"
                      className="rounded p-1 text-muted-foreground hover:bg-white/10 hover:text-white"
                      aria-label={t('onMuhasebe.ortak.sil')}
                      onClick={() =>
                        void api
                          .ekSil(e.id)
                          .then(onEkDegisti)
                          .catch((x) => setHata(hataMetni(t, x)))
                      }
                    >
                      <Trash2 className="h-4 w-4" aria-hidden="true" />
                    </button>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-muted-foreground">{t('onMuhasebe.hareket.ekYok')}</p>
          )}
          {!salt && (
            <label className="mt-2 inline-flex cursor-pointer items-center gap-1.5 text-xs text-purple-200 underline">
              <Upload className="h-3.5 w-3.5" aria-hidden="true" />
              {yukleniyor ? t('onMuhasebe.ortak.yukleniyor') : t('onMuhasebe.hareket.ekYukle')}
              <input ref={dosya} type="file" className="sr-only" onChange={(e) => void ekYukle(e.target.files?.[0])} data-testid="mh-ek-dosya" />
            </label>
          )}
        </div>
        <HataSatiri hata={hata} />
        {!salt && h.duzenlenebilir && (
          <div className="flex flex-wrap justify-end gap-2">
            <Button type="button" variant="outline" className={`${DIS_DUGME} text-rose-200`} onClick={() => void sil()} data-testid="mh-hareket-sil">
              <Trash2 className="h-4 w-4" aria-hidden="true" />
              {t('onMuhasebe.ortak.sil')}
            </Button>
            {h.tur !== 'virman' && (
              <Button type="button" onClick={onDuzenle} className="gap-1.5" data-testid="mh-hareket-duzenle">
                <Pencil className="h-4 w-4" aria-hidden="true" />
                {t('onMuhasebe.ortak.duzenle')}
              </Button>
            )}
          </div>
        )}
      </div>
    </Pencere>
  );
}

