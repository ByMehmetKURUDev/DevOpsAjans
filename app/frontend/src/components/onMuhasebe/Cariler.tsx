import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Download, FileDown, Link2, Loader2, Pencil, Plus, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Alan, Anahtar, Bos, DIS_DUGME, GIRDI, HataSatiri, KART, KovaTablosu, METIN_ALANI, Pencere, Rozet, SECIM, Tutar, Yukleniyor } from '@/components/onMuhasebe/ortak';
import {
  bugun,
  gunYaz,
  hataMetni,
  kurusMetni,
  para,
  type BaglantiAdayi,
  type BolumProps,
  type Cari,
  type CariAyrinti,
  type CariTuru,
  type Ekstre,
} from '@/lib/onMuhasebe';

/** Faz 6M — cari hesaplar: müşteri/tedarikçi kartı, bakiye, ekstre (devreden bakiye; PDF + CSV), yaşlandırma. */
export default function Cariler({ api, meta, yenile, surum }: BolumProps) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const salt = meta.salt_okunur;
  const [ara, setAra] = useState('');
  const [tur, setTur] = useState('');
  const [arsiv, setArsiv] = useState(false);
  const [veri, setVeri] = useState<{ items: Cari[]; toplamlar: { para_birimi: string; alacak: number; borc: number }[] } | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [form, setForm] = useState<Cari | 'yeni' | null>(null);
  const [acik, setAcik] = useState<number | null>(null);

  const yukle = useCallback(async () => {
    setHata(null);
    try {
      setVeri(await api.cariler({ ara: ara || undefined, tur: tur || undefined, arsiv }));
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  }, [api, ara, tur, arsiv, t]);

  useEffect(() => {
    const z = window.setTimeout(() => void yukle(), 250);
    return () => window.clearTimeout(z);
  }, [yukle, surum]);

  return (
    <div className="space-y-3" data-testid="mh-cariler">
      <div className="flex flex-wrap items-center gap-2">
        {!salt && (
          <Button type="button" size="sm" className="gap-1.5" onClick={() => setForm('yeni')} data-testid="mh-cari-yeni">
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('onMuhasebe.cari.yeni')}
          </Button>
        )}
        <input className={`${GIRDI} max-w-xs`} placeholder={t('onMuhasebe.ortak.ara')} value={ara} onChange={(e) => setAra(e.target.value)} />
        <select className={`${SECIM} max-w-[12rem]`} value={tur} onChange={(e) => setTur(e.target.value)} aria-label={t('onMuhasebe.ortak.tur')}>
          <option value="">{t('onMuhasebe.cari.tumTurler')}</option>
          {meta.sabitler.cari_turleri.map((x) => (
            <option key={x} value={x}>
              {t(`onMuhasebe.cariTuru.${x}`)}
            </option>
          ))}
        </select>
        <Anahtar acik={arsiv} onDegis={setArsiv} etiket={t('onMuhasebe.cari.arsivGoster')} />
      </div>
      {veri && veri.toplamlar.length > 0 && (
        <div className="flex flex-wrap gap-2 text-sm">
          {veri.toplamlar.map((x) => (
            <span key={x.para_birimi} className={`${KART} flex flex-wrap gap-3 px-3 py-2`}>
              <span>
                {t('onMuhasebe.cari.toplamAlacak')}: <b className="text-emerald-300">{para(x.alacak, x.para_birimi, dil)}</b>
              </span>
              <span>
                {t('onMuhasebe.cari.toplamBorc')}: <b className="text-rose-300">{para(x.borc, x.para_birimi, dil)}</b>
              </span>
            </span>
          ))}
        </div>
      )}
      <HataSatiri hata={hata} />
      {!veri ? (
        <Yukleniyor />
      ) : !veri.items.length ? (
        <Bos>{t('onMuhasebe.cari.bos')}</Bos>
      ) : (
        <ul className={`${KART} divide-y divide-white/5`} data-testid="mh-cari-liste">
          {veri.items.map((c) => (
            <li key={c.id}>
              <button type="button" className="flex w-full items-center justify-between gap-3 px-3 py-2.5 text-start text-sm hover:bg-white/[0.04]" onClick={() => setAcik(c.id)} data-testid="mh-cari-ac">
                <span className="min-w-0">
                  <span className="block truncate font-medium">{c.ad}</span>
                  <span className="flex flex-wrap gap-1 text-xs text-muted-foreground">
                    {t(`onMuhasebe.cariTuru.${c.tur}`)}
                    {c.bagli_tur && (
                      <Rozet>
                        <Link2 className="h-3 w-3" aria-hidden="true" />
                        {t(`onMuhasebe.cari.baglantiTur.${c.bagli_tur}`)}
                      </Rozet>
                    )}
                    {c.arsiv && <Rozet>{t('onMuhasebe.hesap.arsivde')}</Rozet>}
                  </span>
                </span>
                <span className="text-end">
                  <Tutar deger={c.bakiye} metin={para(Math.abs(c.bakiye), c.para_birimi, dil)} />
                  <span className="block text-[11px] text-muted-foreground">
                    {c.bakiye > 0 ? t('onMuhasebe.cari.bakiyeAlacak') : c.bakiye < 0 ? t('onMuhasebe.cari.bakiyeBorc') : t('onMuhasebe.cari.bakiyeSifir')}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {acik !== null && (
        <CariPenceresi
          api={api}
          id={acik}
          salt={salt}
          onKapat={() => setAcik(null)}
          onDuzenle={(c) => {
            setAcik(null);
            setForm(c);
          }}
          onSilindi={() => {
            setAcik(null);
            yenile();
          }}
        />
      )}
      {form && (
        <CariFormu
          api={api}
          meta={meta}
          cari={form === 'yeni' ? null : form}
          onKaydet={() => {
            setForm(null);
            yenile();
          }}
          onKapat={() => setForm(null)}
        />
      )}
    </div>
  );
}

function CariPenceresi({
  api,
  id,
  salt,
  onKapat,
  onDuzenle,
  onSilindi,
}: {
  api: BolumProps['api'];
  id: number;
  salt: boolean;
  onKapat: () => void;
  onDuzenle: (c: Cari) => void;
  onSilindi: () => void;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [c, setC] = useState<CariAyrinti | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [bas, setBas] = useState(`${bugun().slice(0, 4)}-01-01`);
  const [bit, setBit] = useState(bugun());
  const [ekstre, setEkstre] = useState<Ekstre | null>(null);

  useEffect(() => {
    api
      .cari(id)
      .then(setC)
      .catch((e) => setHata(hataMetni(t, e)));
  }, [api, id, t]);

  useEffect(() => {
    if (!bas || !bit) return;
    api
      .ekstre(id, bas, bit)
      .then(setEkstre)
      .catch((e) => setHata(hataMetni(t, e)));
  }, [api, id, bas, bit, t]);

  const sil = async () => {
    if (!c || !window.confirm(t('onMuhasebe.cari.silOnay', { ad: c.ad }))) return;
    try {
      await api.cariSil(c.id);
      onSilindi();
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  };

  const pb = c?.para_birimi || 'TRY';
  return (
    <Pencere baslik={c?.ad || t('onMuhasebe.ortak.cari')} onKapat={onKapat} genis testid="mh-cari-ayrinti">
      {!c ? (
        hata ? <HataSatiri hata={hata} /> : <Yukleniyor />
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="text-sm text-muted-foreground">
              <p>
                {t(`onMuhasebe.cariTuru.${c.tur}`)} · {c.para_birimi}
                {c.vergi_no ? ` · ${c.vergi_dairesi ? `${c.vergi_dairesi} / ` : ''}${c.vergi_no}` : ''}
              </p>
              {(c.eposta || c.telefon) && <p>{[c.eposta, c.telefon].filter(Boolean).join(' · ')}</p>}
              {c.bagli && (
                <p className="flex items-center gap-1">
                  <Link2 className="h-3.5 w-3.5" aria-hidden="true" />
                  {t(`onMuhasebe.cari.baglantiTur.${c.bagli.tur}`)}: {c.bagli.ad || c.bagli.id}
                </p>
              )}
            </div>
            <div className="text-end">
              <p className="text-xs text-muted-foreground">{t('onMuhasebe.ortak.bakiye')}</p>
              <p className="text-2xl font-semibold" data-testid="mh-cari-bakiye">
                <Tutar deger={c.bakiye} metin={para(Math.abs(c.bakiye), pb, dil)} />
              </p>
              <p className="text-xs text-muted-foreground">
                {c.bakiye > 0 ? t('onMuhasebe.cari.bakiyeAlacak') : c.bakiye < 0 ? t('onMuhasebe.cari.bakiyeBorc') : t('onMuhasebe.cari.bakiyeSifir')}
              </p>
            </div>
          </div>
          {c.yaslandirma_alacak.acik > 0 && <KovaTablosu y={c.yaslandirma_alacak} pb={pb} baslik={t('onMuhasebe.cari.yaslandirmaAlacak')} />}
          {c.yaslandirma_borc.acik > 0 && <KovaTablosu y={c.yaslandirma_borc} pb={pb} baslik={t('onMuhasebe.cari.yaslandirmaBorc')} />}
          <div className="space-y-2" data-testid="mh-ekstre">
            <div className="flex flex-wrap items-end gap-2">
              <h4 className="me-auto text-sm font-semibold">{t('onMuhasebe.cari.ekstre')}</h4>
              <input type="date" className={`${GIRDI} max-w-[10rem]`} value={bas} onChange={(e) => setBas(e.target.value)} aria-label={t('onMuhasebe.ortak.bas')} data-testid="mh-ekstre-bas" />
              <input type="date" className={`${GIRDI} max-w-[10rem]`} value={bit} onChange={(e) => setBit(e.target.value)} aria-label={t('onMuhasebe.ortak.bit')} data-testid="mh-ekstre-bit" />
              <Button type="button" size="sm" variant="outline" className={DIS_DUGME} onClick={() => void api.ekstrePdf(c.id, bas, bit, dil).catch((e) => setHata(hataMetni(t, e)))} data-testid="mh-ekstre-pdf">
                <FileDown className="h-4 w-4" aria-hidden="true" />
                PDF
              </Button>
              <Button type="button" size="sm" variant="outline" className={DIS_DUGME} onClick={() => void api.ekstreCsv(c.id, bas, bit).catch((e) => setHata(hataMetni(t, e)))} data-testid="mh-ekstre-csv">
                <Download className="h-4 w-4" aria-hidden="true" />
                CSV
              </Button>
            </div>
            {ekstre && (
              <div className="overflow-x-auto rounded-xl border border-white/10">
                <table className="min-w-full text-xs">
                  <thead className="bg-white/[0.04] text-muted-foreground">
                    <tr>
                      <th className="px-2 py-1.5 text-start font-medium">{t('onMuhasebe.ortak.tarih')}</th>
                      <th className="px-2 py-1.5 text-start font-medium">{t('onMuhasebe.ortak.aciklama')}</th>
                      <th className="px-2 py-1.5 text-end font-medium">{t('onMuhasebe.cari.borc')}</th>
                      <th className="px-2 py-1.5 text-end font-medium">{t('onMuhasebe.cari.alacak')}</th>
                      <th className="px-2 py-1.5 text-end font-medium">{t('onMuhasebe.ortak.bakiye')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr className="border-t border-white/5 italic">
                      <td className="px-2 py-1">{gunYaz(ekstre.bas, dil)}</td>
                      <td className="px-2 py-1" colSpan={3}>
                        {t('onMuhasebe.cari.ekstreDevreden')}
                      </td>
                      <td className="px-2 py-1 text-end tabular-nums" data-testid="mh-ekstre-devreden">
                        {para(ekstre.devreden, pb, dil)}
                      </td>
                    </tr>
                    {ekstre.satirlar.map((s, i) => (
                      <tr key={`${s.id}-${i}`} className="border-t border-white/5" data-testid="mh-ekstre-satir">
                        <td className="whitespace-nowrap px-2 py-1">{gunYaz(s.tarih, dil)}</td>
                        <td className="px-2 py-1">
                          {s.tur === 'acilis' ? t('onMuhasebe.cari.acilisSatiri') : s.aciklama || t(`onMuhasebe.tur.${s.tur}`)}
                          {s.ters ? ` (${t('onMuhasebe.hareket.ters')})` : ''}
                          {s.vade ? <span className="text-muted-foreground"> · {t('onMuhasebe.ortak.vade')}: {gunYaz(s.vade, dil)}</span> : null}
                        </td>
                        <td className="px-2 py-1 text-end tabular-nums">{s.borc ? para(s.borc, pb, dil) : ''}</td>
                        <td className="px-2 py-1 text-end tabular-nums">{s.alacak ? para(s.alacak, pb, dil) : ''}</td>
                        <td className="px-2 py-1 text-end tabular-nums">{para(s.bakiye, pb, dil)}</td>
                      </tr>
                    ))}
                    <tr className="border-t border-white/10 font-semibold">
                      <td className="px-2 py-1">{gunYaz(ekstre.bit, dil)}</td>
                      <td className="px-2 py-1">{t('onMuhasebe.cari.ekstreKapanis')}</td>
                      <td className="px-2 py-1 text-end tabular-nums">{para(ekstre.toplam_borc, pb, dil)}</td>
                      <td className="px-2 py-1 text-end tabular-nums">{para(ekstre.toplam_alacak, pb, dil)}</td>
                      <td className="px-2 py-1 text-end tabular-nums" data-testid="mh-ekstre-kapanis">
                        {para(ekstre.kapanis, pb, dil)}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            )}
          </div>
          <HataSatiri hata={hata} />
          {!salt && (
            <div className="flex flex-wrap justify-end gap-2">
              <Button type="button" variant="outline" className={`${DIS_DUGME} text-rose-200`} onClick={() => void sil()}>
                <Trash2 className="h-4 w-4" aria-hidden="true" />
                {t('onMuhasebe.ortak.sil')}
              </Button>
              <Button type="button" className="gap-1.5" onClick={() => onDuzenle(c)}>
                <Pencil className="h-4 w-4" aria-hidden="true" />
                {t('onMuhasebe.ortak.duzenle')}
              </Button>
            </div>
          )}
        </div>
      )}
    </Pencere>
  );
}

function CariFormu({
  api,
  meta,
  cari,
  onKaydet,
  onKapat,
}: {
  api: BolumProps['api'];
  meta: BolumProps['meta'];
  cari: Cari | null;
  onKaydet: () => void;
  onKapat: () => void;
}) {
  const { t } = useTranslation();
  const [tam, setTam] = useState<Cari | null>(cari);
  const [g, setG] = useState<Record<string, string>>({});
  const [tur, setTur] = useState<CariTuru>(cari?.tur ?? 'musteri');
  const [pb, setPb] = useState(cari?.para_birimi ?? meta.ayarlar.para_birimi ?? 'TRY');
  const [arsiv, setArsiv] = useState(cari?.arsiv ?? false);
  const [bagli, setBagli] = useState<BaglantiAdayi | null>(cari?.bagli_tur && cari.bagli_id ? { tur: cari.bagli_tur, id: cari.bagli_id, ad: null, ayrinti: null } : null);
  const [aranan, setAranan] = useState('');
  const [adaylar, setAdaylar] = useState<BaglantiAdayi[]>([]);
  const [hata, setHata] = useState<string | null>(null);
  const [kaydediliyor, setKaydediliyor] = useState(false);

  useEffect(() => {
    if (!cari) return;
    api
      .cari(cari.id)
      .then((c) => {
        setTam(c);
        setG({
          ad: c.ad,
          vergi_dairesi: c.vergi_dairesi || '',
          vergi_no: c.vergi_no || '',
          eposta: c.eposta || '',
          telefon: c.telefon || '',
          adres: c.adres || '',
          notlar: c.notlar || '',
          acilis_bakiyesi: kurusMetni(c.acilis_bakiyesi ?? 0),
          acilis_tarihi: c.acilis_tarihi || '',
        });
        if (c.bagli) setBagli(c.bagli);
      })
      .catch((e) => setHata(hataMetni(t, e)));
  }, [api, cari, t]);

  useEffect(() => {
    if (aranan.trim().length < 2) {
      setAdaylar([]);
      return;
    }
    const z = window.setTimeout(() => {
      api
        .baglantiAdaylari(aranan)
        .then((r) => setAdaylar(r.items))
        .catch(() => setAdaylar([]));
    }, 300);
    return () => window.clearTimeout(z);
  }, [api, aranan]);

  const alan = (ad: string) => ({ value: g[ad] ?? '', onChange: (e: { target: { value: string } }) => setG((x) => ({ ...x, [ad]: e.target.value })) });

  const kaydet = async () => {
    setHata(null);
    setKaydediliyor(true);
    const govde: Record<string, unknown> = { ...g, tur, para_birimi: pb, bagli_tur: bagli?.tur ?? null, bagli_id: bagli?.id ?? null };
    if (cari) govde.arsiv = arsiv;
    try {
      if (cari) await api.cariGuncelle(cari.id, govde);
      else await api.cariEkle(govde);
      onKaydet();
    } catch (e) {
      setHata(hataMetni(t, e));
    } finally {
      setKaydediliyor(false);
    }
  };

  if (cari && !tam) return null;
  return (
    <Pencere baslik={cari ? t('onMuhasebe.cari.duzenle') : t('onMuhasebe.cari.yeni')} onKapat={onKapat} genis testid="mh-cari-formu">
      <div className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <Alan etiket={t('onMuhasebe.cari.ad')}>
            <input className={GIRDI} maxLength={160} {...alan('ad')} data-testid="mh-cari-ad" />
          </Alan>
          <Alan etiket={t('onMuhasebe.ortak.tur')}>
            <select className={SECIM} value={tur} onChange={(e) => setTur(e.target.value as CariTuru)} data-testid="mh-cari-tur">
              {meta.sabitler.cari_turleri.map((x) => (
                <option key={x} value={x}>
                  {t(`onMuhasebe.cariTuru.${x}`)}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('onMuhasebe.cari.vergiDairesi')}>
            <input className={GIRDI} maxLength={80} {...alan('vergi_dairesi')} />
          </Alan>
          <Alan etiket={t('onMuhasebe.cari.vergiNo')}>
            <input className={GIRDI} inputMode="numeric" maxLength={11} {...alan('vergi_no')} />
          </Alan>
          <Alan etiket={t('onMuhasebe.cari.eposta')}>
            <input className={GIRDI} type="email" maxLength={254} {...alan('eposta')} />
          </Alan>
          <Alan etiket={t('onMuhasebe.cari.telefon')}>
            <input className={GIRDI} type="tel" maxLength={32} {...alan('telefon')} />
          </Alan>
          <Alan etiket={t('onMuhasebe.ortak.paraBirimi')}>
            <select className={SECIM} value={pb} onChange={(e) => setPb(e.target.value)}>
              {meta.sabitler.para_birimleri.map((x) => (
                <option key={x} value={x}>
                  {x}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('onMuhasebe.cari.acilis')} ipucu={t('onMuhasebe.cari.acilisIpucu')}>
            <input className={GIRDI} inputMode="decimal" placeholder="0,00" {...alan('acilis_bakiyesi')} data-testid="mh-cari-acilis" />
          </Alan>
          <Alan etiket={t('onMuhasebe.cari.adres')} className="sm:col-span-2">
            <textarea className={METIN_ALANI} maxLength={500} {...alan('adres')} />
          </Alan>
          <Alan etiket={t('onMuhasebe.cari.notlar')} className="sm:col-span-2">
            <textarea className={METIN_ALANI} maxLength={1000} {...alan('notlar')} />
          </Alan>
        </div>
        {meta.sabitler.bagli_turler.length > 0 && (
          <div className="space-y-1.5">
            <p className="text-sm font-medium">{t('onMuhasebe.cari.baglanti')}</p>
            {bagli ? (
              <p className="flex items-center gap-2 text-sm">
                <Link2 className="h-4 w-4 text-purple-300" aria-hidden="true" />
                {t(`onMuhasebe.cari.baglantiTur.${bagli.tur}`)}: {bagli.ad || bagli.id}
                <button type="button" className="text-xs text-muted-foreground underline" onClick={() => setBagli(null)}>
                  {t('onMuhasebe.ortak.kaldir')}
                </button>
              </p>
            ) : (
              <>
                <input className={GIRDI} placeholder={t('onMuhasebe.cari.baglantiAra')} value={aranan} onChange={(e) => setAranan(e.target.value)} data-testid="mh-cari-baglanti-ara" />
                {adaylar.length > 0 && (
                  <ul className="max-h-40 overflow-y-auto rounded-md border border-white/10 text-sm">
                    {adaylar.map((a) => (
                      <li key={`${a.tur}-${a.id}`}>
                        <button
                          type="button"
                          className="w-full px-3 py-1.5 text-start hover:bg-white/[0.05]"
                          onClick={() => {
                            setBagli(a);
                            if (!g.ad) setG((x) => ({ ...x, ad: a.ad || '' }));
                          }}
                        >
                          {a.ad} <span className="text-xs text-muted-foreground">· {t(`onMuhasebe.cari.baglantiTur.${a.tur}`)}{a.ayrinti ? ` · ${a.ayrinti}` : ''}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                {aranan.trim().length >= 2 && !adaylar.length && <p className="text-xs text-muted-foreground">{t('onMuhasebe.cari.baglantiYok')}</p>}
              </>
            )}
          </div>
        )}
        {cari && <Anahtar acik={arsiv} onDegis={setArsiv} etiket={t('onMuhasebe.hesap.arsiveAl')} />}
        <HataSatiri hata={hata} />
        <div className="flex flex-wrap justify-end gap-2">
          <Button type="button" variant="outline" className={DIS_DUGME} onClick={onKapat}>
            {t('onMuhasebe.ortak.iptal')}
          </Button>
          <Button type="button" onClick={() => void kaydet()} disabled={kaydediliyor || !(g.ad || '').trim()} data-testid="mh-cari-kaydet">
            {kaydediliyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {t('onMuhasebe.ortak.kaydet')}
          </Button>
        </div>
      </div>
    </Pencere>
  );
}
