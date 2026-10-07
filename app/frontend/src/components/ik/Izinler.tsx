import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, Download, Loader2, Plus, RotateCcw, X, XCircle } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Alan, Anahtar, Bos, DIS_DUGME, GIRDI, KART, METIN_ALANI, Pencere, Rozet, SECIM, Uyarilar, YasalNot, Yukleniyor } from '@/components/ik/ortak';
import { dar, DURUM_RENGI, IZIN_TURLERI, TUR_RENGI, YASAL_TURLER, aralikYaz, gunYaz, hataMetni, sayiYaz, type IkApi, type Izin, type IzinTuru, type Meta, type Personel, type Uyari } from '@/lib/ik';

type Ayrinti = Awaited<ReturnType<IkApi['izin']>>;

function IzinAyrintisi({ api, meta, id, onKapat, onDegisti }: { api: IkApi; meta: Meta; id: number; onKapat: () => void; onDegisti: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [veri, setVeri] = useState<Ayrinti | null>(null);
  const [not, setNot] = useState('');
  const [mesgul, setMesgul] = useState(false);
  const salt = meta.salt_okunur;

  const yukle = useCallback(async () => {
    try {
      setVeri(await api.izin(id));
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  }, [api, id, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const islem = async (f: () => Promise<unknown>, basari: string) => {
    setMesgul(true);
    try {
      await f();
      toast.success(basari);
      onDegisti();
      onKapat();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  const i = veri?.izin;
  return (
    <Pencere baslik={t('ik.izin.ayrinti')} onKapat={onKapat} testid="ik-izin-ayrinti">
      {!veri || !i ? (
        <Yukleniyor />
      ) : (
        <div className="space-y-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-base font-semibold">{veri.personel.ad}</span>
            <Rozet renk={DURUM_RENGI[i.durum]}>{t(`ik.durum.${i.durum}`)}</Rozet>
            {i.kaynak === 'portal' && <Rozet>{t('ik.izin.portaldan')}</Rozet>}
          </div>
          <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
            <div>
              <dt className="text-muted-foreground">{t('ik.izin.tur')}</dt>
              <dd className="font-medium">{t(`ik.tur.${i.tur}`)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">{t('ik.izin.tarih')}</dt>
              <dd className="font-medium">{aralikYaz(i.baslangic, i.bitis, dil)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">{t('ik.izin.isGunu')}</dt>
              <dd className="font-medium">{sayiYaz(i.gun, dil)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">{t('ik.izin.takvimGunu')}</dt>
              <dd className="font-medium">{i.takvim_gunu}</dd>
            </div>
            {i.tur === 'yillik' && veri.personel.bakiye && (
              <div className="col-span-2">
                <dt className="text-muted-foreground">{t('ik.bakiye.kalan')}</dt>
                <dd className="font-medium">
                  {sayiYaz(veri.personel.bakiye.kalan, dil)} · {t('ik.bakiye.bekleyen')}: {sayiYaz(veri.personel.bakiye.bekleyen, dil)}
                </dd>
              </div>
            )}
            {i.aciklama && (
              <div className="col-span-2">
                <dt className="text-muted-foreground">{t('ik.izin.aciklama')}</dt>
                <dd>{i.aciklama}</dd>
              </div>
            )}
            {i.karar_notu && (
              <div className="col-span-2">
                <dt className="text-muted-foreground">{t('ik.izin.kararNotu')}</dt>
                <dd>{i.karar_notu}</dd>
              </div>
            )}
            {i.karar_at && (
              <div className="col-span-2 text-muted-foreground">
                {t('ik.izin.kararVeren', { kisi: i.karar_veren || '—', tarih: gunYaz(i.karar_at, dil) })}
              </div>
            )}
          </dl>
          {i.tur === 'rapor' && <p className="text-xs text-muted-foreground">{t('ik.izin.raporNotu')}</p>}
          <Uyarilar uyarilar={veri.uyarilar} dil={dil} />
          {veri.ayni_tarihte.length > 0 && (
            <div className="rounded-lg border border-white/10 bg-black/20 p-2 text-xs">
              <p className="mb-1 font-medium">{t('ik.izin.ayniTarihte')}</p>
              <ul className="space-y-0.5 text-muted-foreground">
                {veri.ayni_tarihte.map((x, k) => (
                  <li key={k}>
                    {x.ad} — {aralikYaz(x.baslangic, x.bitis, dil)}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {!salt && (
            <div className="space-y-2 border-t border-white/10 pt-3">
              {i.durum === 'beklemede' && (
                <>
                  <Alan etiket={t('ik.izin.not')}>
                    <textarea className={METIN_ALANI} value={not} onChange={(e) => setNot(e.target.value)} maxLength={500} data-testid="ik-karar-not" />
                  </Alan>
                  <div className="flex flex-wrap justify-end gap-2">
                    <Button variant="outline" className={`${DIS_DUGME} text-rose-200`} disabled={mesgul} onClick={() => void islem(() => api.karar(i.id, 'ret', not), t('ik.izin.reddedildi'))} data-testid="ik-karar-ret">
                      <X className="h-4 w-4" aria-hidden="true" />
                      {t('ik.izin.reddet')}
                    </Button>
                    <Button disabled={mesgul} onClick={() => void islem(() => api.karar(i.id, 'onay', not), t('ik.izin.onaylandi'))} data-testid="ik-karar-onay">
                      {mesgul ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Check className="h-4 w-4" aria-hidden="true" />}
                      {t('ik.izin.onayla')}
                    </Button>
                  </div>
                </>
              )}
              <div className="flex flex-wrap justify-end gap-2">
                {(i.durum === 'beklemede' || i.durum === 'onaylandi') && (
                  <Button variant="outline" size="sm" className={DIS_DUGME} disabled={mesgul} onClick={() => window.confirm(t('ik.izin.iptalOnay')) && void islem(() => api.iptal(i.id), t('ik.izin.iptalEdildi'))}>
                    <XCircle className="h-3.5 w-3.5" aria-hidden="true" />
                    {t('ik.izin.iptal')}
                  </Button>
                )}
                {i.durum !== 'beklemede' && (
                  <Button variant="outline" size="sm" className={DIS_DUGME} disabled={mesgul} onClick={() => void islem(() => api.geriAl(i.id), t('ik.izin.geriAlindi'))} data-testid="ik-geri-al">
                    <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                    {t('ik.izin.geriAl')}
                  </Button>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </Pencere>
  );
}

function YeniIzin({ api, meta, personel, onKapat, onEklendi }: { api: IkApi; meta: Meta; personel: Personel[]; onKapat: () => void; onEklendi: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [pid, setPid] = useState<string>(personel[0] ? String(personel[0].id) : '');
  const [tur, setTur] = useState<IzinTuru>('yillik');
  const [bas, setBas] = useState(meta.bugun);
  const [bit, setBit] = useState(meta.bugun);
  const [yarim, setYarim] = useState(false);
  const [aciklama, setAciklama] = useState('');
  const [onayli, setOnayli] = useState(false);
  const [bildir, setBildir] = useState(true);
  const [onizleme, setOnizleme] = useState<{ gun: number; takvim_gunu: number } | null>(null);
  const [mesgul, setMesgul] = useState(false);
  const [uyarilar, setUyarilar] = useState<Uyari[] | null>(null);

  useEffect(() => {
    if (!bas || !bit || bit < bas) {
      setOnizleme(null);
      return;
    }
    let iptal = false;
    api
      .gunHesapla(bas, bit, yarim && bas === bit)
      .then((r) => !iptal && setOnizleme(r))
      .catch(() => !iptal && setOnizleme(null));
    return () => {
      iptal = true;
    };
  }, [api, bas, bit, yarim]);

  const kaydet = async () => {
    if (!pid) return;
    setMesgul(true);
    try {
      const r = await api.izinEkle({
        personel_id: Number(pid),
        tur,
        baslangic: bas,
        bitis: bit,
        yarim_gun: yarim && bas === bit,
        aciklama: tur === 'rapor' ? undefined : aciklama,
        onayli,
        bildir: onayli && bildir,
      });
      toast.success(onayli ? t('ik.izin.eklendiOnayli') : t('ik.izin.eklendi'));
      onEklendi();
      if (r.uyarilar.length) setUyarilar(r.uyarilar);
      else onKapat();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  const yasal = YASAL_TURLER.includes(tur) ? meta.ayarlar.yasal_gunler[tur] : null;
  return (
    <Pencere baslik={t('ik.izin.yeni')} onKapat={onKapat} testid="ik-izin-formu">
      {uyarilar ? (
        <div className="space-y-3">
          <p className="text-sm">{t('ik.izin.uyariliKaydedildi')}</p>
          <Uyarilar uyarilar={uyarilar} dil={dil} />
          <div className="flex justify-end">
            <Button onClick={onKapat}>{t('ik.tamam')}</Button>
          </div>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          <Alan etiket={t('ik.izin.personel')} className="sm:col-span-2">
            <select className={SECIM} value={pid} onChange={(e) => setPid(e.target.value)} data-testid="ik-izin-personel">
              {personel.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.ad}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('ik.izin.tur')} className="sm:col-span-2">
            <select className={SECIM} value={tur} onChange={(e) => setTur(e.target.value as IzinTuru)} data-testid="ik-izin-tur">
              {IZIN_TURLERI.map((x) => (
                <option key={x} value={x}>
                  {t(`ik.tur.${x}`)}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('ik.izin.baslangic')}>
            <input
              className={GIRDI}
              type="date"
              value={bas}
              onChange={(e) => {
                setBas(e.target.value);
                if (bit < e.target.value) setBit(e.target.value);
              }}
              data-testid="ik-izin-bas"
            />
          </Alan>
          <Alan etiket={t('ik.izin.bitis')}>
            <input className={GIRDI} type="date" value={bit} min={bas} onChange={(e) => setBit(e.target.value)} data-testid="ik-izin-bit" />
          </Alan>
          {bas === bit && (
            <div className="sm:col-span-2">
              <Anahtar acik={yarim} onDegis={setYarim} etiket={t('ik.izin.yarimGun')} />
            </div>
          )}
          <p className="text-xs text-purple-100 sm:col-span-2" data-testid="ik-izin-onizleme">
            {onizleme ? t('ik.izin.onizleme', { gun: sayiYaz(onizleme.gun, dil), takvim: onizleme.takvim_gunu }) : '—'}
            {yasal != null && <> · {t(tur === 'dogum' ? 'ik.izin.yasalTakvim' : 'ik.izin.yasalIsGunu', { sayi: yasal })}</>}
          </p>
          {tur === 'rapor' ? (
            <p className="text-xs text-muted-foreground sm:col-span-2">{t('ik.izin.raporNotu')}</p>
          ) : (
            <Alan etiket={t('ik.izin.aciklama')} className="sm:col-span-2">
              <textarea className={METIN_ALANI} value={aciklama} onChange={(e) => setAciklama(e.target.value)} maxLength={500} />
            </Alan>
          )}
          <div className="space-y-2 sm:col-span-2">
            <Anahtar acik={onayli} onDegis={setOnayli} etiket={t('ik.izin.onayliEkle')} testid="ik-izin-onayli" />
            {onayli && <Anahtar acik={bildir} onDegis={setBildir} etiket={t('ik.izin.personeleBildir')} />}
          </div>
          <div className="flex justify-end gap-2 sm:col-span-2">
            <Button variant="outline" className={DIS_DUGME} onClick={onKapat}>
              {t('ik.vazgec')}
            </Button>
            <Button onClick={() => void kaydet()} disabled={mesgul || !pid || !bas || bit < bas} data-testid="ik-izin-kaydet">
              {mesgul && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
              {t('ik.kaydet')}
            </Button>
          </div>
        </div>
      )}
    </Pencere>
  );
}

const DURUM_SUZGECLERI = ['beklemede', 'onaylandi', 'reddedildi', 'iptal', 'hepsi'] as const;

export default function IzinlerBolumu({ api, meta, onMeta }: { api: IkApi; meta: Meta; onMeta: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [durum, setDurum] = useState<string>(meta.bekleyen_izin > 0 ? 'beklemede' : 'hepsi');
  const [tur, setTur] = useState('');
  const [liste, setListe] = useState<Izin[] | null>(null);
  const [personel, setPersonel] = useState<Personel[]>([]);
  const [secili, setSecili] = useState<number | null>(null);
  const [yeni, setYeni] = useState(false);
  const salt = meta.salt_okunur;

  const yukle = useCallback(async () => {
    try {
      setListe((await api.izinler({ durum: durum === 'hepsi' ? undefined : durum, tur: tur || undefined })).items);
    } catch (e) {
      toast.error(hataMetni(t, e));
      setListe([]);
    }
  }, [api, durum, tur, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  useEffect(() => {
    api
      .personelListesi({ durum: 'aktif' })
      .then((r) => setPersonel(r.items))
      .catch(() => setPersonel([]));
  }, [api]);

  const kapat = useCallback(() => setSecili(null), []);
  const degisti = useCallback(() => {
    onMeta();
    void yukle();
  }, [onMeta, yukle]);
  const yeniKapat = useCallback(() => setYeni(false), []);

  return (
    <div className="space-y-4">
      <div className={`${KART} flex flex-wrap items-center gap-2 p-3`}>
        <div className="flex flex-wrap gap-1" role="group" aria-label={t('ik.izin.durumSuzgeci')}>
          {DURUM_SUZGECLERI.map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => setDurum(d)}
              aria-pressed={durum === d}
              className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                durum === d ? 'border-purple-400/50 bg-purple-500/20 text-white' : 'border-white/10 text-muted-foreground hover:text-white'
              }`}
              data-ik-durum={d}
            >
              {d === 'hepsi' ? t('ik.hepsi') : t(`ik.durum.${d}`)}
            </button>
          ))}
        </div>
        <select className={dar(SECIM, 'w-auto')} value={tur} onChange={(e) => setTur(e.target.value)} aria-label={t('ik.izin.tur')}>
          <option value="">{t('ik.izin.tumTurler')}</option>
          {IZIN_TURLERI.map((x) => (
            <option key={x} value={x}>
              {t(`ik.tur.${x}`)}
            </option>
          ))}
        </select>
        <div className="ms-auto flex flex-wrap gap-2">
          <Button variant="outline" className={DIS_DUGME} onClick={() => void api.izinCsv().catch((e) => toast.error(hataMetni(t, e)))}>
            <Download className="h-4 w-4" aria-hidden="true" />
            CSV
          </Button>
          {!salt && (
            <Button onClick={() => setYeni(true)} disabled={!personel.length} className="gap-1.5" data-testid="ik-izin-yeni">
              <Plus className="h-4 w-4" aria-hidden="true" />
              {t('ik.izin.yeni')}
            </Button>
          )}
        </div>
      </div>
      <div className={`${KART} p-3 sm:p-4`}>
        {liste === null ? (
          <Yukleniyor />
        ) : liste.length === 0 ? (
          <Bos>{t('ik.izin.bos')}</Bos>
        ) : (
          <ul className="space-y-2" data-testid="ik-izin-liste">
            {liste.map((i) => (
              <li key={i.id}>
                <button
                  type="button"
                  onClick={() => setSecili(i.id)}
                  className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-white/10 bg-black/20 p-3 text-start text-sm transition-colors hover:border-purple-400/40"
                  data-testid="ik-izin-ac"
                  data-izin-id={i.id}
                  data-durum={i.durum}
                >
                  <span className="h-8 w-1.5 flex-none rounded-full" style={{ background: TUR_RENGI[i.tur] }} aria-hidden="true" />
                  <span className="min-w-[8rem] flex-1">
                    <span className="block font-medium">{i.personel_ad || '—'}</span>
                    <span className="block text-xs text-muted-foreground">
                      {t(`ik.tur.${i.tur}`)} · {aralikYaz(i.baslangic, i.bitis, dil)}
                    </span>
                  </span>
                  <span className="text-xs text-muted-foreground">{t('ik.izin.gunSayisi', { sayi: sayiYaz(i.gun, dil) })}</span>
                  {i.kaynak === 'portal' && <Rozet>{t('ik.izin.portaldan')}</Rozet>}
                  <Rozet renk={DURUM_RENGI[i.durum]}>{t(`ik.durum.${i.durum}`)}</Rozet>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <YasalNot />
      {secili !== null && <IzinAyrintisi api={api} meta={meta} id={secili} onKapat={kapat} onDegisti={degisti} />}
      {yeni && <YeniIzin api={api} meta={meta} personel={personel} onKapat={yeniKapat} onEklendi={degisti} />}
    </div>
  );
}
