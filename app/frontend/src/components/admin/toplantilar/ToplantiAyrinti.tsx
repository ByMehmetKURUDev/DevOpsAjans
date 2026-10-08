import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import {
  ArrowLeft,
  Ban,
  CalendarClock,
  CalendarPlus,
  CheckCircle2,
  FileDown,
  ListTodo,
  Loader2,
  Pencil,
  Plus,
  Send,
  Share2,
  Trash2,
} from 'lucide-react';

import {
  Alan,
  DUGME_ANA,
  DUGME_IKINCIL,
  DUGME_TEHLIKE,
  DurumRozeti,
  GIRDI,
  KART,
  METIN,
  Rozet,
  SECIM,
  Yer,
  YanitRozeti,
  Zaman,
} from '@/components/toplantilar/ortak';
import { PDF_DILLERI } from '@/lib/belge';
import {
  aksiyonEkle,
  aksiyonGuncelle,
  aksiyonSil,
  ayrinti as ayrintiGetir,
  davetGonder,
  ertele,
  goreveDonustur,
  hataKodu,
  icsAl,
  iptalEt,
  istanbulGirdisi,
  mdAl,
  paylas,
  pdfAl,
  sil,
  tutanakYaz,
  yapildi,
  type Ayrinti,
  type Meta,
} from '@/lib/toplantilar';

interface Props {
  id: number;
  meta: Meta;
  onGeri: () => void;
  onDuzenle: (t: Ayrinti) => void;
  onDegisti: () => void;
}

/** Faz 6T — toplantı ayrıntısı: katılımcı yanıtları, davet/ertele/iptal/yapıldı, tutanak, aksiyonlar, PDF/MD/ICS. */
export default function ToplantiAyrinti({ id, meta, onGeri, onDuzenle, onDegisti }: Props) {
  const { t, i18n } = useTranslation();
  const [v, setV] = useState<Ayrinti | null>(null);
  const [hata, setHata] = useState(false);
  const [calisan, setCalisan] = useState<string | null>(null);
  const [notlar, setNotlar] = useState('');
  const [kararlar, setKararlar] = useState('');
  const [erteleAcik, setErteleAcik] = useState(false);
  const [yeniTarih, setYeniTarih] = useState('');
  const [iptalAcik, setIptalAcik] = useState(false);
  const [neden, setNeden] = useState('');
  const [pdfDili, setPdfDili] = useState<string>(PDF_DILLERI.includes(i18n.language as never) ? i18n.language : 'tr');
  const [yeniAksiyon, setYeniAksiyon] = useState({ metin: '', sorumlu: 'ekip:', son_tarih: '' });

  const yukle = useCallback(async () => {
    try {
      const g = await ayrintiGetir(id);
      setV(g);
      setNotlar(g.notlar || '');
      setKararlar((g.kararlar || []).join('\n'));
      setHata(false);
    } catch {
      setHata(true);
    }
  }, [id]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const mesaj = (h: unknown) => t(`toplantilar.hata.${hataKodu(h)}`, { defaultValue: t('toplantilar.hata.genel') });

  async function calistir(anahtar: string, is: () => Promise<Ayrinti | void>, basari?: (s: Ayrinti | void) => string) {
    setCalisan(anahtar);
    try {
      const s = await is();
      if (s && 'id' in s) {
        setV(s);
        setNotlar(s.notlar || '');
        setKararlar((s.kararlar || []).join('\n'));
      } else await yukle();
      if (basari) toast.success(basari(s));
      onDegisti();
    } catch (h) {
      toast.error(mesaj(h));
    } finally {
      setCalisan(null);
    }
  }

  if (hata) {
    return (
      <div className={`${KART} p-6 text-sm text-red-200`}>
        {t('toplantilar.hata.genel')}
        <button type="button" className={`${DUGME_IKINCIL} ms-3`} onClick={onGeri}>
          {t('toplantilar.ayrinti.listeyeDon')}
        </button>
      </div>
    );
  }
  if (!v) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" />
      </div>
    );
  }

  const acik = v.durum !== 'iptal';
  const ekipAdi = (e: string | null) => (e ? meta.ekip.find((x) => x.email === e)?.ad || e : t('toplantilar.aksiyon.ekip'));

  return (
    <div className="space-y-4" data-testid="toplanti-ayrinti" data-toplanti-id={v.id}>
      <button type="button" className={DUGME_IKINCIL} onClick={onGeri}>
        <ArrowLeft className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
        {t('toplantilar.ayrinti.listeyeDon')}
      </button>

      <section className={`${KART} p-4 sm:p-6`}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="break-words text-xl font-semibold" data-toplanti-baslik>
              {v.baslik}
            </h3>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <DurumRozeti durum={v.durum} />
              {v.guncelleme_bekliyor && <Rozet tur="uyari">{t('toplantilar.rozet.guncelleme')}</Rozet>}
              {!v.davet_gonderildi_at && acik && <Rozet tur="bekliyor">{t('toplantilar.rozet.davetYok')}</Rozet>}
              {v.notlar_paylasildi && <Rozet tur="bilgi">{t('toplantilar.rozet.paylasildi')}</Rozet>}
            </div>
          </div>
        </div>
        <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
          <div className="min-w-0">
            <dt className="text-xs uppercase tracking-wider text-muted-foreground">{t('toplantilar.form.baslangic')}</dt>
            <dd>
              <Zaman iso={v.baslangic} /> · {t('toplantilar.zaman.dk', { sayi: v.sure_dk })}
            </dd>
          </div>
          <div className="min-w-0">
            <dt className="text-xs uppercase tracking-wider text-muted-foreground">{t('toplantilar.form.yerTuru')}</dt>
            <dd>
              <Yer yer_turu={v.yer_turu} baglanti={v.baglanti} adres={v.adres} telefon={v.telefon} />
            </dd>
          </div>
          {v.hesap_email && (
            <div className="min-w-0">
              <dt className="text-xs uppercase tracking-wider text-muted-foreground">{t('toplantilar.form.musteri')}</dt>
              <dd className="break-all">{v.hesap_adi ? `${v.hesap_adi} — ${v.hesap_email}` : v.hesap_email}</dd>
            </div>
          )}
          {v.proje && (
            <div className="min-w-0">
              <dt className="text-xs uppercase tracking-wider text-muted-foreground">{t('toplantilar.form.proje')}</dt>
              <dd>{v.proje.baslik}</dd>
            </div>
          )}
          {v.aday && (
            <div className="min-w-0">
              <dt className="text-xs uppercase tracking-wider text-muted-foreground">{t('toplantilar.form.aday')}</dt>
              <dd>{[v.aday.ad, v.aday.firma].filter(Boolean).join(' — ')}</dd>
            </div>
          )}
          {v.durum === 'iptal' && v.iptal_nedeni && (
            <div className="min-w-0 sm:col-span-2">
              <dt className="text-xs uppercase tracking-wider text-muted-foreground">{t('toplantilar.ayrinti.iptalNedeni')}</dt>
              <dd className="whitespace-pre-line break-words">{v.iptal_nedeni}</dd>
            </div>
          )}
        </dl>

        {v.guncelleme_bekliyor && (
          <p className="mt-3 rounded-lg border border-amber-400/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">{t('toplantilar.ayrinti.guncellemeUyari')}</p>
        )}
        {!!v.cakismalar?.length && (
          <p className="mt-3 rounded-lg border border-amber-400/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-100" data-cakisma>
            {t('toplantilar.form.cakismaBaslik')}: {v.cakismalar.map((c) => `${ekipAdi(c.eposta)} — ${c.baslik}`).join('; ')}
          </p>
        )}

        <div className="mt-4 flex flex-wrap gap-2">
          {acik && (
            <button type="button" className={DUGME_IKINCIL} onClick={() => onDuzenle(v)} data-eylem="duzenle">
              <Pencil className="h-4 w-4" aria-hidden="true" />
              {t('toplantilar.ayrinti.duzenle')}
            </button>
          )}
          {acik && v.durum !== 'yapildi' && (
            <button
              type="button"
              className={DUGME_ANA}
              disabled={!!calisan || !v.katilimcilar.length}
              onClick={() =>
                void calistir('davet', () => davetGonder(v.id), (s) => t('toplantilar.ayrinti.davetGitti', { sayi: (s as Ayrinti)?.davet?.gonderilen ?? 0 }))
              }
              data-eylem="davet"
            >
              {calisan === 'davet' ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Send className="h-4 w-4" aria-hidden="true" />}
              {v.guncelleme_bekliyor ? t('toplantilar.ayrinti.guncellemeGonder') : t('toplantilar.ayrinti.davetGonder')}
            </button>
          )}
          {acik && v.durum !== 'yapildi' && (
            <button type="button" className={DUGME_IKINCIL} onClick={() => { setErteleAcik((x) => !x); setYeniTarih(istanbulGirdisi(v.baslangic)); }} data-eylem="ertele">
              <CalendarClock className="h-4 w-4" aria-hidden="true" />
              {t('toplantilar.ayrinti.ertele')}
            </button>
          )}
          {acik && v.durum !== 'yapildi' && v.kategori !== 'yaklasan' && (
            <button type="button" className={DUGME_IKINCIL} disabled={!!calisan} onClick={() => void calistir('yapildi', () => yapildi(v.id))} data-eylem="yapildi">
              <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
              {t('toplantilar.ayrinti.yapildi')}
            </button>
          )}
          <button type="button" className={DUGME_IKINCIL} onClick={() => void icsAl(v.id).catch((h) => toast.error(mesaj(h)))} data-eylem="ics">
            <CalendarPlus className="h-4 w-4" aria-hidden="true" />
            {t('toplantilar.ayrinti.ics')}
          </button>
          {acik && v.durum !== 'yapildi' && (
            <button type="button" className={DUGME_TEHLIKE} onClick={() => setIptalAcik((x) => !x)} data-eylem="iptal">
              <Ban className="h-4 w-4" aria-hidden="true" />
              {t('toplantilar.ayrinti.iptal')}
            </button>
          )}
          <button
            type="button"
            className={DUGME_TEHLIKE}
            disabled={!!calisan}
            onClick={() => {
              if (!window.confirm(t('toplantilar.ayrinti.silOnay'))) return;
              setCalisan('sil');
              sil(v.id)
                .then(() => {
                  toast.success(t('toplantilar.ayrinti.silindi'));
                  onDegisti();
                  onGeri();
                })
                .catch((h) => toast.error(mesaj(h)))
                .finally(() => setCalisan(null));
            }}
            data-eylem="sil"
          >
            <Trash2 className="h-4 w-4" aria-hidden="true" />
            {t('toplantilar.ayrinti.sil')}
          </button>
        </div>

        {erteleAcik && (
          <div className="mt-3 flex min-w-0 flex-col gap-2 rounded-xl border border-white/10 bg-black/20 p-3 sm:flex-row sm:items-end">
            <Alan etiket={t('toplantilar.ayrinti.erteleYeni')} ipucu={t('toplantilar.form.baslangicIpucu')} className="flex-1">
              <input type="datetime-local" className={GIRDI} value={yeniTarih} onChange={(e) => setYeniTarih(e.target.value)} dir="ltr" data-ertele-tarih />
            </Alan>
            <button
              type="button"
              className={DUGME_ANA}
              disabled={!yeniTarih || !!calisan}
              onClick={() =>
                void calistir('ertele', async () => {
                  const s = await ertele(v.id, { baslangic: yeniTarih, saat_dilimi: meta.saat_dilimi });
                  setErteleAcik(false);
                  return s;
                }, () => t('toplantilar.ayrinti.ertelendi'))
              }
              data-ertele-kaydet
            >
              {t('toplantilar.ayrinti.erteleGonder')}
            </button>
          </div>
        )}
        {iptalAcik && (
          <div className="mt-3 rounded-xl border border-red-400/30 bg-red-500/5 p-3">
            <Alan etiket={t('toplantilar.ayrinti.iptalNeden')}>
              <textarea className={METIN} value={neden} maxLength={1000} onChange={(e) => setNeden(e.target.value)} data-iptal-neden />
            </Alan>
            <button
              type="button"
              className={`${DUGME_TEHLIKE} mt-2`}
              disabled={!neden.trim() || !!calisan}
              onClick={() =>
                void calistir('iptal', async () => {
                  const s = await iptalEt(v.id, neden.trim());
                  setIptalAcik(false);
                  return s;
                }, () => t('toplantilar.ayrinti.iptalEdildi'))
              }
              data-iptal-onay
            >
              {t('toplantilar.ayrinti.iptalOnay')}
            </button>
          </div>
        )}
      </section>

      <section className={`${KART} p-4 sm:p-6`} aria-labelledby="toplanti-katilimcilar">
        <h4 id="toplanti-katilimcilar" className="mb-3 font-semibold">
          {t('toplantilar.ayrinti.katilimcilar')} ({v.katilimcilar.length})
        </h4>
        {v.katilimcilar.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('toplantilar.ayrinti.katilimciYok')}</p>
        ) : (
          <ul className="divide-y divide-white/5">
            {v.katilimcilar.map((k) => (
              <li key={k.eposta} className="flex flex-wrap items-start justify-between gap-2 py-2 text-sm" data-katilimci={k.eposta}>
                <div className="min-w-0">
                  <p className="break-all">
                    <span className="font-medium">{k.ad || k.eposta}</span>
                    {k.ad && <span className="ms-1 text-muted-foreground" dir="ltr">{`<${k.eposta}>`}</span>}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {t(`toplantilar.katilimciTuru.${k.tur}`)} ·{' '}
                    {k.davet_at ? (
                      <>
                        {t('toplantilar.ayrinti.davetEdildi')} <Zaman iso={k.davet_at} />
                      </>
                    ) : (
                      t('toplantilar.ayrinti.davetEdilmedi')
                    )}
                  </p>
                  {k.yanit_notu && <p className="mt-1 whitespace-pre-line break-words text-xs text-white/80" data-yanit-notu>“{k.yanit_notu}”</p>}
                </div>
                <YanitRozeti yanit={k.yanit || 'bekliyor'} />
              </li>
            ))}
          </ul>
        )}
        {v.gundem.length > 0 && (
          <>
            <h4 className="mb-2 mt-4 font-semibold">{t('toplantilar.form.gundem')}</h4>
            <ol className="list-decimal space-y-1 ps-6 text-sm">
              {v.gundem.map((g, i) => (
                <li key={i} className="break-words">{g}</li>
              ))}
            </ol>
          </>
        )}
      </section>

      <section className={`${KART} p-4 sm:p-6`} aria-labelledby="toplanti-tutanak" data-testid="toplanti-tutanak">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h4 id="toplanti-tutanak" className="font-semibold">
            {t('toplantilar.tutanak.baslik')}
          </h4>
          <label className="inline-flex cursor-pointer items-center gap-2 text-sm" data-paylas>
            <input
              type="checkbox"
              className="h-4 w-4 accent-purple-500"
              checked={v.notlar_paylasildi}
              disabled={!v.hesap_email || !!calisan}
              onChange={(e) =>
                void calistir('paylas', () => paylas(v.id, e.target.checked), (s) =>
                  (s as Ayrinti)?.notlar_paylasildi ? t('toplantilar.tutanak.paylasildi') : t('toplantilar.tutanak.paylasimKaldirildi')
                )
              }
            />
            <Share2 className="h-4 w-4 text-purple-300" aria-hidden="true" />
            {t('toplantilar.tutanak.paylas')}
          </label>
        </div>
        <p className="mb-3 text-xs text-muted-foreground">{v.hesap_email ? t('toplantilar.tutanak.paylasIpucu') : t('toplantilar.hata.musteri_yok')}</p>
        <div className="grid gap-4 lg:grid-cols-2">
          <Alan etiket={t('toplantilar.tutanak.notlar')} ipucu={t('toplantilar.tutanak.notlarIpucu')}>
            <textarea className={`${METIN} min-h-[180px]`} value={notlar} onChange={(e) => setNotlar(e.target.value)} data-notlar />
          </Alan>
          <div className="min-w-0">
            <span className="mb-1 block text-sm font-medium text-white/90">{t('toplantilar.tutanak.onizleme')}</span>
            {/* Sunucu güvenli HTML'i (services/guvenli_html.py: izinli etiketler, javascript: yok). */}
            <div
              className="prose prose-invert max-w-none break-words rounded-md border border-white/10 bg-black/20 p-3 text-sm"
              data-notlar-onizleme
              dangerouslySetInnerHTML={{ __html: v.notlar_html || `<p>${t('toplantilar.tutanak.bos')}</p>` }}
            />
          </div>
        </div>
        <Alan etiket={t('toplantilar.tutanak.kararlar')} ipucu={t('toplantilar.tutanak.kararlarIpucu')} className="mt-4">
          <textarea className={METIN} value={kararlar} onChange={(e) => setKararlar(e.target.value)} data-kararlar />
        </Alan>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            className={DUGME_ANA}
            disabled={!!calisan}
            onClick={() =>
              void calistir('tutanak', () => tutanakYaz(v.id, { notlar, kararlar: kararlar.split('\n').map((x) => x.trim()).filter(Boolean) }), () =>
                t('toplantilar.tutanak.kaydedildi')
              )
            }
            data-tutanak-kaydet
          >
            {calisan === 'tutanak' && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {t('toplantilar.tutanak.kaydet')}
          </button>
          <select className={`${SECIM} w-auto`} value={pdfDili} onChange={(e) => setPdfDili(e.target.value)} aria-label={t('toplantilar.tutanak.dil')}>
            {PDF_DILLERI.map((d) => (
              <option key={d} value={d}>
                {d.toUpperCase()}
              </option>
            ))}
          </select>
          <button type="button" className={DUGME_IKINCIL} onClick={() => void pdfAl(v.id, pdfDili).catch((h) => toast.error(mesaj(h)))} data-pdf>
            <FileDown className="h-4 w-4" aria-hidden="true" />
            {t('toplantilar.tutanak.pdf')}
          </button>
          <button type="button" className={DUGME_IKINCIL} onClick={() => void mdAl(v.id, pdfDili).catch((h) => toast.error(mesaj(h)))} data-md>
            <FileDown className="h-4 w-4" aria-hidden="true" />
            {t('toplantilar.tutanak.md')}
          </button>
        </div>
      </section>

      <section className={`${KART} p-4 sm:p-6`} aria-labelledby="toplanti-aksiyonlar" data-testid="toplanti-aksiyonlar">
        <h4 id="toplanti-aksiyonlar" className="mb-3 font-semibold">
          {t('toplantilar.aksiyon.baslik')}
        </h4>
        {v.aksiyonlar.length === 0 && <p className="text-sm text-muted-foreground">{t('toplantilar.aksiyon.yok')}</p>}
        <ul className="divide-y divide-white/5">
          {v.aksiyonlar.map((a) => (
            <li key={a.id} className="flex flex-wrap items-start gap-3 py-2 text-sm" data-aksiyon={a.id}>
              <input
                type="checkbox"
                className="mt-1 h-4 w-4 accent-purple-500"
                checked={a.durum === 'tamamlandi'}
                aria-label={t('toplantilar.aksiyon.tamam')}
                onChange={(e) => void calistir('aksiyon', async () => void (await aksiyonGuncelle(a.id, { durum: e.target.checked ? 'tamamlandi' : 'acik' })))}
              />
              <div className="min-w-0 flex-1 basis-40">
                <p className={`break-words ${a.durum === 'tamamlandi' ? 'text-muted-foreground line-through' : ''}`}>{a.metin}</p>
                <p className="text-xs text-muted-foreground">
                  {a.sorumlu_tur === 'musteri'
                    ? `${t('toplantilar.aksiyon.musteri')}${a.sorumlu_eposta ? ` (${a.sorumlu_eposta})` : ''}`
                    : ekipAdi(a.sorumlu_eposta)}
                  {a.son_tarih && ` · ${t('toplantilar.aksiyon.sonTarih')}: ${new Date(`${a.son_tarih}T00:00:00Z`).toLocaleDateString(i18n.language === 'ar' ? 'ar-u-nu-latn' : i18n.language, { timeZone: 'UTC' })}`}
                </p>
              </div>
              {a.gorev_id ? (
                <Rozet tur="bilgi">{t('toplantilar.aksiyon.gorevOldu', { id: a.gorev_id })}</Rozet>
              ) : (
                <button
                  type="button"
                  className={DUGME_IKINCIL}
                  disabled={!v.proje_id || !!calisan}
                  title={!v.proje_id ? t('toplantilar.aksiyon.projeYok') : undefined}
                  onClick={() => void calistir('gorev', async () => void (await goreveDonustur(a.id)), () => t('toplantilar.aksiyon.gorevAcildi'))}
                  data-goreve-donustur={a.id}
                >
                  <ListTodo className="h-4 w-4" aria-hidden="true" />
                  {t('toplantilar.aksiyon.gorev')}
                </button>
              )}
              <button
                type="button"
                className={DUGME_IKINCIL}
                aria-label={t('toplantilar.aksiyon.sil')}
                disabled={!!calisan}
                onClick={() => void calistir('aksiyonSil', async () => void (await aksiyonSil(a.id)))}
              >
                <Trash2 className="h-4 w-4" aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
        {!v.proje_id && v.aksiyonlar.length > 0 && <p className="mt-2 text-xs text-muted-foreground">{t('toplantilar.aksiyon.projeYok')}</p>}
        <div className="mt-3 grid gap-2 rounded-xl border border-white/10 bg-black/20 p-3 md:grid-cols-[1fr_200px_160px_auto]">
          <input
            className={GIRDI}
            value={yeniAksiyon.metin}
            maxLength={500}
            placeholder={t('toplantilar.aksiyon.metin')}
            aria-label={t('toplantilar.aksiyon.metin')}
            onChange={(e) => setYeniAksiyon((x) => ({ ...x, metin: e.target.value }))}
            data-aksiyon-metin
          />
          <select
            className={SECIM}
            value={yeniAksiyon.sorumlu}
            aria-label={t('toplantilar.aksiyon.sorumlu')}
            onChange={(e) => setYeniAksiyon((x) => ({ ...x, sorumlu: e.target.value }))}
            data-aksiyon-sorumlu
          >
            <option value="ekip:">{t('toplantilar.aksiyon.ekip')}</option>
            {meta.ekip.map((e) => (
              <option key={e.email} value={`ekip:${e.email}`}>
                {e.ad}
              </option>
            ))}
            {v.hesap_email && <option value="musteri:">{t('toplantilar.aksiyon.musteri')}</option>}
          </select>
          <input
            type="date"
            className={GIRDI}
            value={yeniAksiyon.son_tarih}
            aria-label={t('toplantilar.aksiyon.sonTarih')}
            onChange={(e) => setYeniAksiyon((x) => ({ ...x, son_tarih: e.target.value }))}
            dir="ltr"
          />
          <button
            type="button"
            className={DUGME_ANA}
            disabled={!yeniAksiyon.metin.trim() || !!calisan}
            onClick={() =>
              void calistir('aksiyonEkle', async () => {
                const [tur, eposta] = yeniAksiyon.sorumlu.split(':');
                await aksiyonEkle(v.id, { metin: yeniAksiyon.metin.trim(), sorumlu_tur: tur, sorumlu_eposta: eposta || null, son_tarih: yeniAksiyon.son_tarih || null });
                setYeniAksiyon({ metin: '', sorumlu: 'ekip:', son_tarih: '' });
              })
            }
            data-aksiyon-ekle
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('toplantilar.aksiyon.ekle')}
          </button>
        </div>
      </section>
    </div>
  );
}
