import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { AlertTriangle, ArrowDown, ArrowUp, Loader2, Plus, Send, Sparkles, X } from 'lucide-react';

import { Alan, DUGME_ANA, DUGME_IKINCIL, GIRDI, KART, METIN, SECIM, Zaman } from '@/components/toplantilar/ortak';
import {
  cakismaDenetle,
  guncelle,
  hataKodu,
  istanbulGirdisi,
  jitsiUret,
  olustur,
  YER_TURLERI,
  type Ayrinti,
  type Cakisma,
  type Katilimci,
  type Meta,
  type Talep,
  type YerTuru,
} from '@/lib/toplantilar';

interface Props {
  meta: Meta;
  mevcut?: Ayrinti | null;
  talep?: Talep | null;
  onKaydedildi: (t: Ayrinti) => void;
  onVazgec: () => void;
}

const SURELER = [15, 30, 45, 60, 90, 120, 180];

/** Faz 6T — toplantı oluştur / düzenle. Saat Europe/Istanbul girilir (sunucu UTC saklar). */
export default function ToplantiFormu({ meta, mevcut, talep, onKaydedildi, onVazgec }: Props) {
  const { t } = useTranslation();
  const ilkAralik = talep?.araliklar?.[0];
  const [baslik, setBaslik] = useState(mevcut?.baslik ?? talep?.konu ?? '');
  const [gundem, setGundem] = useState<string[]>(mevcut?.gundem?.length ? mevcut.gundem : talep?.not ? [talep.not.slice(0, 300)] : ['']);
  const [baslangic, setBaslangic] = useState(istanbulGirdisi(mevcut?.baslangic ?? ilkAralik?.bas ?? null));
  const ilkSure = (() => {
    if (mevcut) return mevcut.sure_dk;
    if (ilkAralik) {
      const dk = Math.round((new Date(ilkAralik.bit).getTime() - new Date(ilkAralik.bas).getTime()) / 60000);
      return Math.min(60, Math.max(15, dk || 60));
    }
    return 60;
  })();
  const [sure, setSure] = useState<number>(ilkSure);
  const [yerTuru, setYerTuru] = useState<YerTuru>(mevcut?.yer_turu ?? 'cevrimici');
  const [baglanti, setBaglanti] = useState(mevcut?.baglanti ?? '');
  const [adres, setAdres] = useState(mevcut?.adres ?? '');
  const [telefon, setTelefon] = useState(mevcut?.telefon ?? '');
  const [hesap, setHesap] = useState(mevcut?.hesap_email ?? talep?.hesap_email ?? '');
  const [projeId, setProjeId] = useState<string>(mevcut?.proje_id ? String(mevcut.proje_id) : '');
  const [adayId, setAdayId] = useState<string>(mevcut?.crm_aday_id ? String(mevcut.crm_aday_id) : '');
  const [ekip, setEkip] = useState<string[]>((mevcut?.katilimcilar ?? []).filter((k) => k.tur === 'ekip').map((k) => k.eposta || ''));
  const [dislar, setDislar] = useState<{ eposta: string; ad?: string | null }[]>(() => {
    const d = (mevcut?.katilimcilar ?? []).filter((k) => k.tur === 'dis').map((k) => ({ eposta: k.eposta || '', ad: k.ad }));
    if (!mevcut && talep?.kisi_email) d.push({ eposta: talep.kisi_email, ad: talep.hesap_adi ?? null });
    return d;
  });
  const [yeniDis, setYeniDis] = useState('');
  const [cakismalar, setCakismalar] = useState<Cakisma[]>(mevcut?.cakismalar ?? []);
  const [kayit, setKayit] = useState<'' | 'kaydet' | 'davet'>('');
  const [hata, setHata] = useState<string | null>(null);

  const projeler = useMemo(() => meta.projeler.filter((p) => !hesap || p.hesap_email === hesap.toLowerCase()), [meta.projeler, hesap]);

  // Seçilen proje başka müşterinin ise temizle (sunucu da reddeder).
  useEffect(() => {
    if (projeId && !projeler.some((p) => String(p.id) === projeId)) setProjeId('');
  }, [projeler, projeId]);

  // Canlı çakışma uyarısı (yalnız ekip üyeleri; engel değil).
  const sayac = useRef(0);
  useEffect(() => {
    if (!baslangic || !ekip.length) {
      setCakismalar([]);
      return;
    }
    const no = ++sayac.current;
    const zaman = window.setTimeout(() => {
      cakismaDenetle({ baslangic, saat_dilimi: meta.saat_dilimi, sure_dk: sure, ekip, haric_id: mevcut?.id })
        .then((g) => no === sayac.current && setCakismalar(g.cakismalar))
        .catch(() => undefined);
    }, 400);
    return () => window.clearTimeout(zaman);
  }, [baslangic, sure, ekip, mevcut?.id, meta.saat_dilimi]);

  const ekipAdi = (e: string) => meta.ekip.find((x) => x.email === e)?.ad || e;

  function disEkle(e?: string) {
    const deger = (e ?? yeniDis).trim().toLowerCase();
    if (!deger || !/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(deger)) {
      setHata(t('toplantilar.hata.katilimci_gecersiz'));
      return;
    }
    setHata(null);
    if (!dislar.some((d) => d.eposta === deger) && !ekip.includes(deger)) setDislar((d) => [...d, { eposta: deger }]);
    if (!e) setYeniDis('');
  }

  function tasi(i: number, yon: -1 | 1) {
    setGundem((g) => {
      const j = i + yon;
      if (j < 0 || j >= g.length) return g;
      const y = [...g];
      [y[i], y[j]] = [y[j], y[i]];
      return y;
    });
  }

  async function kaydet(davet: boolean) {
    setHata(null);
    if (!baslik.trim()) {
      setHata(t('toplantilar.hata.baslik_gecersiz'));
      return;
    }
    if (!baslangic) {
      setHata(t('toplantilar.hata.baslangic_gecersiz'));
      return;
    }
    const katilimcilar: Katilimci[] = [
      ...ekip.map((e) => ({ eposta: e, tur: 'ekip' as const })),
      ...dislar.map((d) => ({ eposta: d.eposta, ad: d.ad ?? null, tur: 'dis' as const })),
    ];
    const govde: Record<string, unknown> = {
      baslik: baslik.trim(),
      gundem: gundem.map((g) => g.trim()).filter(Boolean),
      baslangic,
      saat_dilimi: meta.saat_dilimi,
      sure_dk: sure,
      yer_turu: yerTuru,
      baglanti: yerTuru === 'cevrimici' ? baglanti.trim() || null : null,
      adres: yerTuru === 'yuz_yuze' ? adres.trim() || null : null,
      telefon: yerTuru === 'telefon' ? telefon.trim() || null : null,
      hesap_email: hesap.trim().toLowerCase() || null,
      proje_id: projeId ? Number(projeId) : null,
      crm_aday_id: adayId ? Number(adayId) : null,
      katilimcilar,
    };
    if (!mevcut && talep) govde.talep_id = talep.id;
    if (!mevcut && davet) govde.davet_gonder = true;
    setKayit(davet ? 'davet' : 'kaydet');
    try {
      const sonuc = mevcut ? await guncelle(mevcut.id, govde) : await olustur(govde);
      toast.success(
        sonuc.davet?.gonderilen ? t('toplantilar.ayrinti.davetGitti', { sayi: sonuc.davet.gonderilen }) : t('toplantilar.form.kaydedildi')
      );
      if (sonuc.cakismalar?.length) toast.warning(t('toplantilar.form.cakismaBaslik'));
      onKaydedildi(sonuc);
    } catch (h) {
      setHata(t(`toplantilar.hata.${hataKodu(h)}`, { defaultValue: t('toplantilar.hata.genel') }));
    } finally {
      setKayit('');
    }
  }

  return (
    <section className={`${KART} p-4 sm:p-6`} aria-labelledby="toplanti-form-baslik" data-testid="toplanti-formu">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 id="toplanti-form-baslik" className="text-lg font-semibold">
            {mevcut ? t('toplantilar.form.duzenleBaslik') : t('toplantilar.form.yeniBaslik')}
          </h3>
          {talep && !mevcut && (
            <p className="mt-1 text-sm text-muted-foreground" data-talepten>
              {t('toplantilar.form.talepten', { konu: talep.konu })}
            </p>
          )}
        </div>
        <button type="button" onClick={onVazgec} className={DUGME_IKINCIL} aria-label={t('toplantilar.form.vazgec')}>
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>

      {talep && talep.araliklar.length > 0 && !mevcut && (
        <div className="mb-4 rounded-xl border border-purple-400/30 bg-purple-500/10 p-3 text-sm">
          <p className="mb-1 font-medium text-purple-100">{t('toplantilar.talep.araliklar')}</p>
          <ul className="space-y-1">
            {talep.araliklar.map((a, i) => (
              <li key={i} className="flex flex-wrap items-center gap-2">
                <Zaman iso={a.bas} className="text-white/90" />
                <span className="text-muted-foreground">→</span>
                <Zaman iso={a.bit} className="text-white/90" />
                <button type="button" className="text-xs text-purple-200 underline-offset-2 hover:underline" onClick={() => setBaslangic(istanbulGirdisi(a.bas))}>
                  {t('toplantilar.form.buSaat')}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <Alan etiket={t('toplantilar.form.baslik')} className="md:col-span-2">
          <input className={GIRDI} value={baslik} maxLength={200} onChange={(e) => setBaslik(e.target.value)} data-alan="baslik" />
        </Alan>
        <Alan etiket={t('toplantilar.form.baslangic')} ipucu={t('toplantilar.form.baslangicIpucu')}>
          <input type="datetime-local" className={GIRDI} value={baslangic} onChange={(e) => setBaslangic(e.target.value)} data-alan="baslangic" dir="ltr" />
        </Alan>
        <Alan etiket={t('toplantilar.form.sure')}>
          <select className={SECIM} value={sure} onChange={(e) => setSure(Number(e.target.value))} data-alan="sure">
            {[...new Set([...SURELER, sure])].sort((a, b) => a - b).map((s) => (
              <option key={s} value={s}>
                {t('toplantilar.zaman.dk', { sayi: s })}
              </option>
            ))}
          </select>
        </Alan>

        <fieldset className="md:col-span-2">
          <legend className="mb-1 text-sm font-medium text-white/90">{t('toplantilar.form.yerTuru')}</legend>
          <div className="flex flex-wrap gap-2" role="radiogroup">
            {YER_TURLERI.map((y) => (
              <button
                key={y}
                type="button"
                role="radio"
                aria-checked={yerTuru === y}
                onClick={() => setYerTuru(y)}
                className={`min-h-[36px] rounded-lg border px-3 py-1.5 text-sm ${yerTuru === y ? 'border-purple-400/70 bg-purple-500/20 text-white' : 'border-white/15 text-muted-foreground hover:text-white'}`}
                data-yer={y}
              >
                {t(`toplantilar.yer.${y}`)}
              </button>
            ))}
          </div>
        </fieldset>

        {yerTuru === 'cevrimici' && (
          <Alan etiket={t('toplantilar.form.baglanti')} ipucu={t('toplantilar.form.jitsiIpucu')} className="md:col-span-2">
            <div className="flex min-w-0 flex-col gap-2 sm:flex-row">
              <input className={GIRDI} value={baglanti} onChange={(e) => setBaglanti(e.target.value)} placeholder="https://" dir="ltr" data-alan="baglanti" />
              <button type="button" className={`${DUGME_IKINCIL} flex-none justify-center`} onClick={() => setBaglanti(jitsiUret())} data-jitsi>
                <Sparkles className="h-4 w-4" aria-hidden="true" />
                {t('toplantilar.form.jitsi')}
              </button>
            </div>
          </Alan>
        )}
        {yerTuru === 'yuz_yuze' && (
          <Alan etiket={t('toplantilar.form.adres')} className="md:col-span-2">
            <input className={GIRDI} value={adres} maxLength={300} onChange={(e) => setAdres(e.target.value)} data-alan="adres" />
          </Alan>
        )}
        {yerTuru === 'telefon' && (
          <Alan etiket={t('toplantilar.form.telefon')} className="md:col-span-2">
            <input className={GIRDI} value={telefon} maxLength={60} onChange={(e) => setTelefon(e.target.value)} dir="ltr" data-alan="telefon" />
          </Alan>
        )}

        <Alan etiket={t('toplantilar.form.musteri')}>
          <select className={SECIM} value={hesap} onChange={(e) => setHesap(e.target.value)} data-alan="hesap">
            <option value="">{t('toplantilar.form.musteriYok')}</option>
            {hesap && !meta.musteriler.some((m) => m.eposta === hesap) && <option value={hesap}>{hesap}</option>}
            {meta.musteriler.map((m) => (
              <option key={m.eposta} value={m.eposta}>
                {m.ad ? `${m.ad} — ${m.eposta}` : m.eposta}
              </option>
            ))}
          </select>
        </Alan>
        <Alan etiket={t('toplantilar.form.proje')}>
          <select className={SECIM} value={projeId} onChange={(e) => setProjeId(e.target.value)} data-alan="proje">
            <option value="">{t('toplantilar.form.projeYok')}</option>
            {projeler.map((p) => (
              <option key={p.id} value={p.id}>
                {p.baslik}
              </option>
            ))}
          </select>
        </Alan>
        <Alan etiket={t('toplantilar.form.aday')} className="md:col-span-2">
          <select className={SECIM} value={adayId} onChange={(e) => setAdayId(e.target.value)} data-alan="aday">
            <option value="">{t('toplantilar.form.adayYok')}</option>
            {meta.adaylar.map((a) => (
              <option key={a.id} value={a.id}>
                {[a.ad, a.firma, a.email].filter(Boolean).join(' — ')}
              </option>
            ))}
          </select>
        </Alan>
      </div>

      <fieldset className="mt-5">
        <legend className="mb-2 text-sm font-medium text-white/90">{t('toplantilar.form.gundem')}</legend>
        <ol className="space-y-2">
          {gundem.map((g, i) => (
            <li key={i} className="flex min-w-0 items-center gap-2">
              <span className="w-6 flex-none text-end text-xs text-muted-foreground">{i + 1}.</span>
              <input
                className={GIRDI}
                value={g}
                maxLength={300}
                aria-label={t('toplantilar.form.gundemMadde', { sayi: i + 1 })}
                onChange={(e) => setGundem((x) => x.map((y, j) => (j === i ? e.target.value : y)))}
                data-gundem={i}
              />
              <button type="button" className={DUGME_IKINCIL} onClick={() => tasi(i, -1)} disabled={i === 0} aria-label={t('toplantilar.form.yukari')}>
                <ArrowUp className="h-4 w-4" aria-hidden="true" />
              </button>
              <button type="button" className={DUGME_IKINCIL} onClick={() => tasi(i, 1)} disabled={i === gundem.length - 1} aria-label={t('toplantilar.form.asagi')}>
                <ArrowDown className="h-4 w-4" aria-hidden="true" />
              </button>
              <button type="button" className={DUGME_IKINCIL} onClick={() => setGundem((x) => x.filter((_, j) => j !== i))} aria-label={t('toplantilar.form.kaldir')}>
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </li>
          ))}
        </ol>
        <button type="button" className={`${DUGME_IKINCIL} mt-2`} onClick={() => setGundem((g) => [...g, ''])} disabled={gundem.length >= meta.sinirlar.gundem}>
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('toplantilar.form.gundemEkle')}
        </button>
      </fieldset>

      <fieldset className="mt-5">
        <legend className="mb-2 text-sm font-medium text-white/90">{t('toplantilar.form.katilimcilar')}</legend>
        <p className="mb-1 text-xs uppercase tracking-wider text-muted-foreground">{t('toplantilar.form.ekip')}</p>
        {meta.ekip.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('toplantilar.form.ekipYok')}</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {meta.ekip.map((e) => {
              const secili = ekip.includes(e.email);
              return (
                <button
                  key={e.email}
                  type="button"
                  aria-pressed={secili}
                  onClick={() => setEkip((x) => (secili ? x.filter((y) => y !== e.email) : [...x, e.email]))}
                  className={`min-h-[36px] rounded-full border px-3 py-1 text-sm ${secili ? 'border-purple-400/70 bg-purple-500/20 text-white' : 'border-white/15 text-muted-foreground hover:text-white'}`}
                  data-ekip={e.email}
                >
                  {e.ad}
                </button>
              );
            })}
          </div>
        )}
        <p className="mb-1 mt-3 text-xs uppercase tracking-wider text-muted-foreground">{t('toplantilar.form.dis')}</p>
        <div className="flex flex-wrap gap-2">
          {dislar.map((d) => (
            <span key={d.eposta} className="inline-flex max-w-full items-center gap-1 rounded-full border border-white/15 bg-black/30 px-3 py-1 text-sm" data-dis={d.eposta}>
              <span className="min-w-0 break-all" dir="ltr">{d.ad ? `${d.ad} <${d.eposta}>` : d.eposta}</span>
              <button type="button" onClick={() => setDislar((x) => x.filter((y) => y.eposta !== d.eposta))} aria-label={t('toplantilar.form.kaldir')}>
                <X className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            </span>
          ))}
        </div>
        <div className="mt-2 flex min-w-0 flex-col gap-2 sm:flex-row">
          <input
            className={GIRDI}
            type="email"
            value={yeniDis}
            placeholder="ornek@firma.com"
            dir="ltr"
            onChange={(e) => setYeniDis(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                disEkle();
              }
            }}
            aria-label={t('toplantilar.form.disEposta')}
            data-alan="dis"
          />
          <button type="button" className={`${DUGME_IKINCIL} flex-none justify-center`} onClick={() => disEkle()} data-dis-ekle>
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('toplantilar.form.disEkle')}
          </button>
          {hesap && !dislar.some((d) => d.eposta === hesap) && (
            <button type="button" className={`${DUGME_IKINCIL} flex-none justify-center`} onClick={() => disEkle(hesap)} data-musteriyi-ekle>
              <Plus className="h-4 w-4" aria-hidden="true" />
              {t('toplantilar.form.musteriyiEkle')}
            </button>
          )}
        </div>
      </fieldset>

      {cakismalar.length > 0 && (
        <div className="mt-4 rounded-xl border border-amber-400/40 bg-amber-500/10 p-3 text-sm text-amber-100" role="status" data-cakisma>
          <p className="mb-1 flex items-center gap-1.5 font-medium">
            <AlertTriangle className="h-4 w-4" aria-hidden="true" />
            {t('toplantilar.form.cakismaBaslik')}
          </p>
          <ul className="space-y-0.5">
            {cakismalar.map((c) => (
              <li key={`${c.eposta}-${c.toplanti_id}`}>
                {ekipAdi(c.eposta)}: {c.baslik} — <Zaman iso={c.baslangic} />
              </li>
            ))}
          </ul>
        </div>
      )}

      {hata && (
        <p className="mt-4 rounded-lg border border-red-400/40 bg-red-500/10 px-3 py-2 text-sm text-red-200" role="alert" data-form-hata>
          {hata}
        </p>
      )}

      <div className="mt-5 flex flex-wrap gap-2">
        <button type="button" className={DUGME_ANA} onClick={() => void kaydet(false)} disabled={!!kayit} data-kaydet>
          {kayit === 'kaydet' && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
          {t('toplantilar.form.kaydet')}
        </button>
        {!mevcut && (
          <button type="button" className={DUGME_IKINCIL} onClick={() => void kaydet(true)} disabled={!!kayit || !(ekip.length + dislar.length)} data-kaydet-davet>
            {kayit === 'davet' ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Send className="h-4 w-4" aria-hidden="true" />}
            {t('toplantilar.form.kaydetDavet')}
          </button>
        )}
        <button type="button" className={DUGME_IKINCIL} onClick={onVazgec}>
          {t('toplantilar.form.vazgec')}
        </button>
      </div>
    </section>
  );
}
