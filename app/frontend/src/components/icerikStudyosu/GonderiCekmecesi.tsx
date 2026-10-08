import { useEffect, useMemo, useRef, useState } from 'react';
import { Copy, Link2, Loader2, Package, Plus, Save, Send, Trash2, Upload, Wand2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  Alan,
  Cekmece,
  DIS_DUGME,
  DurumRozeti,
  GIRDI,
  KanalIkonu,
  METIN_ALANI,
  Rozet,
  SECIM,
  Uyarilar,
} from '@/components/icerikStudyosu/ortak';
import {
  hataMetni,
  panoyaKopyala,
  tarihSaatYaz,
  uzunluk,
  type Durum,
  type Gonderi,
  type GonderiProjesi,
  type Gorsel,
  type Marka,
  type Meta,
  type StudyoApi,
} from '@/lib/icerikStudyosu';
import type { PlanTaslagi } from '@/components/IcerikStudyosu';

/**
 * Faz 5I — Gönderi çekmecesi: oluştur / düzenle, kanal başına metin, görseller, kısa link,
 * durum geçişleri ve (yönetici + müşteri hesabı) müşteri onayına gönderme.
 * Ajansın yönettiği gönderi müşteri modunda salt okunur; onaya sunulmuş/onaylı içerik kilitli.
 */

const SAAT_DILIMLERI = ['Europe/Istanbul', 'Europe/Berlin', 'Europe/London', 'Europe/Moscow', 'Asia/Dubai', 'Asia/Kolkata',
  'Asia/Shanghai', 'America/New_York', 'America/Los_Angeles', 'UTC'];
const KILITLI: Durum[] = ['musteri_onayi', 'onaylandi', 'yayinlandi'];

interface Form {
  baslik: string;
  metin: string;
  kanallar: string[];
  kanal_metinleri: Record<string, string>;
  hashtagler: string;
  ilk_yorum: string;
  gorseller: Gorsel[];
  video_url: string;
  baglanti: string;
  kampanya: string;
  notlar: string;
  marka_id: number | null;
  proje_id: number | null;
  sorumlu_eposta: string;
  planlanan: string;
  saat_dilimi: string;
}

function formdan(g: Gonderi | null, taslak: PlanTaslagi | null, varsayilanTz: string, gun?: string | null): Form {
  return {
    baslik: g?.baslik ?? taslak?.baslik ?? '',
    metin: g?.metin ?? taslak?.metin ?? '',
    kanallar: g?.kanallar ?? taslak?.kanallar ?? ['instagram'],
    kanal_metinleri: { ...(g?.kanal_metinleri ?? {}) },
    hashtagler: g?.hashtagler ?? '',
    ilk_yorum: g?.ilk_yorum ?? '',
    gorseller: g?.gorseller ?? [],
    video_url: g?.video_url ?? '',
    baglanti: g?.baglanti ?? '',
    kampanya: g?.kampanya ?? '',
    notlar: g?.notlar ?? '',
    marka_id: g?.marka_id ?? taslak?.marka_id ?? null,
    proje_id: g?.proje_id ?? null,
    sorumlu_eposta: g?.sorumlu_eposta ?? '',
    planlanan: g?.planlanan ?? (gun ? `${gun}T10:00` : ''),
    saat_dilimi: g?.saat_dilimi ?? varsayilanTz,
  };
}

export default function GonderiCekmecesi({
  api,
  meta,
  gonderi,
  taslak,
  gun,
  kampanyalar,
  varsayilanTz,
  onKapat,
  onDegisti,
  onPaket,
}: {
  api: StudyoApi;
  meta: Meta;
  gonderi: Gonderi | null;
  taslak: PlanTaslagi | null;
  gun?: string | null;
  kampanyalar: string[];
  varsayilanTz: string;
  onKapat: () => void;
  onDegisti: (g: Gonderi | null) => void;
  onPaket: (id: number) => void;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [g, setG] = useState<Gonderi | null>(gonderi);
  const [form, setForm] = useState<Form>(() => formdan(gonderi, taslak, varsayilanTz, gun));
  const [seciliKanal, setSeciliKanal] = useState<string>(() => (gonderi?.kanallar ?? taslak?.kanallar ?? ['instagram'])[0]);
  const [markalar, setMarkalar] = useState<Marka[]>([]);
  const [projeler, setProjeler] = useState<GonderiProjesi[]>([]);
  /** Proje listesi tek bir hesabın mı (ajans içeriğinde bütün projeler gelir; öneri yalnız hesaplıda). */
  const [projeHesapli, setProjeHesapli] = useState(false);
  const [kitaplik, setKitaplik] = useState<Gorsel[] | null>(null);
  const [calisiyor, setCalisiyor] = useState<string | null>(null);
  const [retNotu, setRetNotu] = useState<string | null>(null);
  const [onayGun, setOnayGun] = useState(7);
  const [onayEposta, setOnayEposta] = useState(true);
  const [onayBaglantisi, setOnayBaglantisi] = useState<string | null>(null);
  const dosyaGirdisi = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    api.markalar().then((r) => setMarkalar(r.items)).catch(() => setMarkalar([]));
  }, [api]);

  // Faz 7K — isteğe bağlı proje: var olan gönderide gönderinin hesabının projeleri (ajans içeriği: hepsi).
  const projeHesabi = gonderi ? gonderi.hesap_email : undefined;
  useEffect(() => {
    api
      .projeler(projeHesabi)
      .then((r) => {
        setProjeler(r.items);
        setProjeHesapli(Boolean(r.hesap));
      })
      .catch(() => setProjeler([]));
  }, [api, projeHesabi]);

  // Faz 7K — hesabın TEK açık projesi varsa ve gönderiye proje bağlanmamışsa öneri (tek tıkla bağlanır).
  const acikProjeler = projeler.filter((p) => p.acik);
  const onerilenProje = projeHesapli && !form.proje_id && acikProjeler.length === 1 ? acikProjeler[0] : null;

  const durum: Durum = g?.durum ?? 'taslak';
  const saltOkunur = meta.yonetici ? false : g?.yoneten === 'ajans';
  const icerikKilitli = saltOkunur || (g ? KILITLI.includes(durum) : false);
  const zamanKilitli = saltOkunur || durum === 'yayinlandi';
  const yaz = <K extends keyof Form>(k: K, v: Form[K]) => setForm((f) => ({ ...f, [k]: v }));

  const islem = async (ad: string, is: () => Promise<void>) => {
    setCalisiyor(ad);
    try {
      await is();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setCalisiyor(null);
    }
  };

  const govde = () => {
    const d: Record<string, unknown> = {
      planlanan: form.planlanan || null,
      saat_dilimi: form.saat_dilimi,
      kampanya: form.kampanya,
      notlar: form.notlar,
      sorumlu_eposta: form.sorumlu_eposta,
      proje_id: form.proje_id,
    };
    if (!icerikKilitli) {
      Object.assign(d, {
        baslik: form.baslik,
        metin: form.metin,
        kanallar: form.kanallar,
        kanal_metinleri: Object.fromEntries(Object.entries(form.kanal_metinleri).filter(([k, v]) => form.kanallar.includes(k) && v.trim())),
        hashtagler: form.hashtagler,
        ilk_yorum: form.ilk_yorum,
        gorseller: form.gorseller.map((x) => x.anahtar),
        video_url: form.video_url,
        baglanti: form.baglanti,
        marka_id: form.marka_id,
      });
    }
    if (zamanKilitli) {
      delete d.planlanan;
      delete d.saat_dilimi;
    }
    return d;
  };

  const kaydet = () =>
    islem('kaydet', async () => {
      if (!form.baslik.trim()) {
        toast.error(t('icerikStudyosu.form.baslikGerekli'));
        return;
      }
      const yeni = g ? await api.gonderiGuncelle(g.id, govde()) : await api.gonderiEkle({ ...govde(), uretim_id: taslak?.uretim_id ?? null });
      setG(yeni);
      setForm(formdan(yeni, null, varsayilanTz));
      toast.success(t('icerikStudyosu.form.kaydedildi'));
      onDegisti(yeni);
    });

  const sil = () =>
    islem('sil', async () => {
      if (!g || !window.confirm(t('icerikStudyosu.form.silOnay', { baslik: g.baslik }))) return;
      await api.gonderiSil(g.id);
      toast.success(t('icerikStudyosu.form.silindi'));
      onDegisti(null);
      onKapat();
    });

  const durumDegistir = (yeniDurum: Durum, not?: string) =>
    islem(`durum-${yeniDurum}`, async () => {
      if (!g) return;
      const yeni = await api.durum(g.id, yeniDurum, not);
      setG(yeni);
      setRetNotu(null);
      toast.success(t('icerikStudyosu.form.durumDegisti', { durum: t(`icerikOnay.durum.${yeniDurum}`) }));
      onDegisti(yeni);
    });

  const onayaGonder = () =>
    islem('onay', async () => {
      if (!g) return;
      const y = await api.onayaGonder(g.id, { gun: onayGun, eposta_gonder: onayEposta });
      setG(y.gonderi);
      setOnayBaglantisi(y.baglanti);
      toast.success(y.eposta_gonderildi ? t('icerikStudyosu.form.onayEpostaGitti') : t('icerikStudyosu.form.onayHazir'));
      onDegisti(y.gonderi);
    });

  const kisaLink = () =>
    islem('kisa', async () => {
      if (!g) return;
      const y = await api.kisaLink(g.id);
      setG(y.gonderi);
      toast.success(t('icerikStudyosu.form.kisaLinkHazir'));
    });

  const uyarla = (kanal: string) =>
    islem(`uyarla-${kanal}`, async () => {
      const kaynak = form.kanal_metinleri[kanal]?.trim() || form.metin;
      if (!kaynak.trim()) {
        toast.error(t('icerikStudyosu.form.metinGerekli'));
        return;
      }
      const y = await api.inceAyar({ islem: 'uyarla', metin: kaynak, kanal, marka_id: form.marka_id });
      yaz('kanal_metinleri', { ...form.kanal_metinleri, [kanal]: y.uretim.varyasyonlar[0]?.metin ?? kaynak });
    });

  const gorselYukle = (dosyalar: FileList | null) =>
    islem('gorsel', async () => {
      if (!dosyalar?.length) return;
      const eklenen: Gorsel[] = [];
      for (const d of Array.from(dosyalar).slice(0, 10 - form.gorseller.length)) eklenen.push(await api.gorselYukle(d));
      yaz('gorseller', [...form.gorseller, ...eklenen]);
      if (dosyaGirdisi.current) dosyaGirdisi.current.value = '';
    });

  const kitapligiAc = () =>
    islem('kitaplik', async () => {
      setKitaplik((await api.gorseller()).items);
    });

  const kanalDegistir = (k: string) => {
    const var_ = form.kanallar.includes(k);
    const yeni = var_ ? form.kanallar.filter((x) => x !== k) : [...form.kanallar, k];
    if (!yeni.length) return;
    yaz('kanallar', yeni);
    if (!yeni.includes(seciliKanal)) setSeciliKanal(yeni[0]);
    if (!var_) setSeciliKanal(k);
  };

  const sayac = (k: string, metin: string) => {
    const sinir = meta.sinirlar[k]?.metin;
    const n = uzunluk(metin, k);
    return { n, sinir, asim: !!sinir && n > sinir };
  };
  const kanalMetni = (k: string) => form.kanal_metinleri[k]?.trim() || form.metin;
  const gecisler = useMemo(() => (g?.gecisler ?? []).filter((x) => x !== 'musteri_onayi'), [g]);
  const onayaGonderilebilir = meta.yonetici && g && g.hesap_email && g.yoneten === 'ajans' && ['taslak', 'incelemede', 'reddedildi', 'musteri_onayi'].includes(durum);

  return (
    <Cekmece baslik={g ? g.baslik : t('icerikStudyosu.form.yeni')} onKapat={onKapat} testid="is-gonderi-cekmece" genis>
      <div className="space-y-4" data-gonderi={g?.id ?? 'yeni'}>
        {g && (
          <div className="flex flex-wrap items-center gap-2">
            <DurumRozeti durum={durum} />
            {g.marka_adi && <Rozet>{g.marka_adi}</Rozet>}
            {g.hesap_email && meta.yonetici && <Rozet renk="border-fuchsia-400/30 bg-fuchsia-500/10 text-fuchsia-100">{g.hesap_email}</Rozet>}
            {g.durum_notu && (
              <span className="w-full rounded-lg border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-xs text-amber-100" data-testid="durum-notu">
                {t('icerikStudyosu.form.durumNotu')}: {g.durum_notu}
              </span>
            )}
          </div>
        )}
        {saltOkunur && <p className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-xs text-muted-foreground">{t('icerikStudyosu.form.saltOkunur')}</p>}
        {!saltOkunur && icerikKilitli && <p className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-xs text-muted-foreground">{t('icerikStudyosu.form.kilitli')}</p>}

        <Alan etiket={t('icerikStudyosu.form.baslik')} ipucu={t('icerikStudyosu.form.baslikIpucu')}>
          <input className={GIRDI} value={form.baslik} onChange={(e) => yaz('baslik', e.target.value)} disabled={icerikKilitli} maxLength={200} data-testid="is-form-baslik" />
        </Alan>

        <div>
          <span className="mb-1 block text-sm font-medium">{t('icerikStudyosu.form.kanallar')}</span>
          <div className="flex flex-wrap gap-1.5" data-testid="is-form-kanallar">
            {meta.kanallar.map((k) => {
              const sec = form.kanallar.includes(k);
              return (
                <button
                  key={k}
                  type="button"
                  disabled={icerikKilitli}
                  onClick={() => kanalDegistir(k)}
                  aria-pressed={sec}
                  data-kanal={k}
                  className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs transition-colors disabled:opacity-60 ${
                    sec ? 'border-fuchsia-400/50 bg-fuchsia-500/20 text-white' : 'border-white/10 text-muted-foreground hover:text-white'
                  }`}
                >
                  <KanalIkonu kanal={k} />
                  {t(`icerikOnay.kanal.${k}`)}
                </button>
              );
            })}
          </div>
        </div>

        <Alan etiket={t('icerikStudyosu.form.metin')} ipucu={t('icerikStudyosu.form.metinIpucu')}>
          <textarea className={METIN_ALANI + ' min-h-[140px]'} value={form.metin} onChange={(e) => yaz('metin', e.target.value)} disabled={icerikKilitli} dir="auto" data-testid="is-form-metin" />
        </Alan>
        <div className="flex flex-wrap gap-x-3 gap-y-1" data-testid="is-form-sayaclar">
          {form.kanallar.map((k) => {
            const s = sayac(k, kanalMetni(k));
            return (
              <span key={k} className={`inline-flex items-center gap-1 text-[11px] tabular-nums ${s.asim ? 'text-rose-300' : 'text-muted-foreground'}`} data-sayac={k} data-asim={s.asim ? '1' : '0'}>
                <KanalIkonu kanal={k} className="h-3 w-3" />
                {s.sinir ? `${s.n}/${s.sinir}` : s.n}
              </span>
            );
          })}
        </div>

        {/* Kanal başına metin */}
        <div className="rounded-xl border border-white/10 p-3">
          <p className="mb-2 text-sm font-medium">{t('icerikStudyosu.form.kanalMetni')}</p>
          <div className="mb-2 flex flex-wrap gap-1">
            {form.kanallar.map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => setSeciliKanal(k)}
                className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs ${seciliKanal === k ? 'bg-white/10 text-white' : 'text-muted-foreground hover:text-white'}`}
                data-kanal-sekme={k}
              >
                <KanalIkonu kanal={k} />
                {t(`icerikOnay.kanal.${k}`)}
                {form.kanal_metinleri[k]?.trim() ? ' •' : ''}
              </button>
            ))}
          </div>
          {seciliKanal && (
            <>
              <textarea
                className={METIN_ALANI}
                value={form.kanal_metinleri[seciliKanal] ?? ''}
                placeholder={t('icerikStudyosu.form.kanalMetniIpucu')}
                onChange={(e) => yaz('kanal_metinleri', { ...form.kanal_metinleri, [seciliKanal]: e.target.value })}
                disabled={icerikKilitli}
                dir="auto"
                data-testid="is-form-kanal-metni"
              />
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <Button type="button" size="sm" variant="outline" className={DIS_DUGME} disabled={icerikKilitli || !form.metin.trim()}
                  onClick={() => yaz('kanal_metinleri', { ...form.kanal_metinleri, [seciliKanal]: form.metin })}>
                  <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('icerikStudyosu.form.anaMetindenKopyala')}
                </Button>
                <Button type="button" size="sm" variant="outline" className={DIS_DUGME} disabled={icerikKilitli || !meta.ai_hazir || !!calisiyor}
                  title={!meta.ai_hazir ? t('icerikStudyosu.uyariAiKapali') : undefined}
                  onClick={() => uyarla(seciliKanal)} data-testid="is-form-uyarla">
                  {calisiyor === `uyarla-${seciliKanal}` ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Wand2 className="h-3.5 w-3.5" aria-hidden="true" />}
                  {t('icerikStudyosu.form.aiUyarla')}
                </Button>
                <span className="text-[11px] text-muted-foreground">
                  {(meta.gorsel_onerileri[seciliKanal] || []).map((o) => `${o.boyut} (${o.oran})`).join(' · ')}
                </span>
              </div>
            </>
          )}
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <Alan etiket={t('icerikStudyosu.form.hashtagler')} ipucu={t('icerikStudyosu.form.hashtaglerIpucu')}>
            <input className={GIRDI} value={form.hashtagler} onChange={(e) => yaz('hashtagler', e.target.value)} disabled={icerikKilitli} />
          </Alan>
          <Alan etiket={t('icerikStudyosu.form.marka')}>
            <select className={SECIM} value={form.marka_id ?? ''} onChange={(e) => yaz('marka_id', e.target.value ? Number(e.target.value) : null)} disabled={icerikKilitli}>
              <option value="">{t('icerikStudyosu.form.markaYok')}</option>
              {markalar.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.ad}
                </option>
              ))}
            </select>
          </Alan>
        </div>
        <Alan etiket={t('icerikStudyosu.form.ilkYorum')} ipucu={t('icerikStudyosu.form.ilkYorumIpucu')}>
          <textarea className={METIN_ALANI + ' min-h-[64px]'} value={form.ilk_yorum} onChange={(e) => yaz('ilk_yorum', e.target.value)} disabled={icerikKilitli} dir="auto" />
        </Alan>
        <div className="grid gap-3 sm:grid-cols-2">
          <Alan etiket={t('icerikStudyosu.form.baglanti')} ipucu={t('icerikStudyosu.form.baglantiIpucu')}>
            <input className={GIRDI} type="url" inputMode="url" value={form.baglanti} onChange={(e) => yaz('baglanti', e.target.value)} disabled={icerikKilitli} placeholder="https://" dir="ltr" />
          </Alan>
          <Alan etiket={t('icerikStudyosu.form.video')}>
            <input className={GIRDI} type="url" inputMode="url" value={form.video_url} onChange={(e) => yaz('video_url', e.target.value)} disabled={icerikKilitli} placeholder="https://" dir="ltr" />
          </Alan>
        </div>
        {g && g.baglanti && !saltOkunur && (
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <Button type="button" size="sm" variant="outline" className={DIS_DUGME} onClick={kisaLink} disabled={!!calisiyor} data-testid="is-form-kisa-link">
              <Link2 className="h-3.5 w-3.5" aria-hidden="true" />
              {t('icerikStudyosu.form.kisaLinkUret')}
            </Button>
            {Object.entries(g.kisa_linkler).map(([k, v]) => (
              <button key={k} type="button" className="inline-flex items-center gap-1 rounded bg-white/5 px-1.5 py-0.5" dir="ltr"
                onClick={async () => toast[(await panoyaKopyala(v.adres)) ? 'success' : 'error'](t('icerikStudyosu.kopyalandi'))}>
                <KanalIkonu kanal={k} className="h-3 w-3" /> {v.adres.replace(/^https?:\/\//, '')}
              </button>
            ))}
          </div>
        )}

        {/* Görseller */}
        <div>
          <span className="mb-1 block text-sm font-medium">{t('icerikStudyosu.form.gorseller')}</span>
          <div className="flex flex-wrap gap-2" data-testid="is-form-gorseller">
            {form.gorseller.map((r) => (
              <div key={r.anahtar} className="relative h-20 w-20 overflow-hidden rounded-lg border border-white/10">
                <img src={r.url} alt={r.ad || ''} className="h-full w-full object-cover" loading="lazy" />
                {!icerikKilitli && (
                  <button type="button" className="absolute end-1 top-1 rounded bg-black/70 p-0.5" aria-label={t('icerikStudyosu.form.gorselKaldir')}
                    onClick={() => yaz('gorseller', form.gorseller.filter((x) => x.anahtar !== r.anahtar))}>
                    <X className="h-3 w-3" />
                  </button>
                )}
              </div>
            ))}
            {!icerikKilitli && form.gorseller.length < 10 && (
              <>
                <label className="flex h-20 w-20 cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-white/20 text-[11px] text-muted-foreground hover:text-white">
                  {calisiyor === 'gorsel' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" aria-hidden="true" />}
                  {t('icerikStudyosu.form.gorselYukle')}
                  <input ref={dosyaGirdisi} type="file" accept="image/jpeg,image/png,image/webp" multiple className="sr-only" onChange={(e) => gorselYukle(e.target.files)} data-testid="is-form-gorsel-dosya" />
                </label>
                <button type="button" onClick={kitapligiAc} className="flex h-20 w-20 flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-white/20 text-[11px] text-muted-foreground hover:text-white">
                  <Plus className="h-4 w-4" aria-hidden="true" />
                  {t('icerikStudyosu.form.kitaplik')}
                </button>
              </>
            )}
          </div>
          {kitaplik && (
            <div className="mt-2 grid max-h-52 grid-cols-4 gap-2 overflow-y-auto rounded-lg border border-white/10 p-2 sm:grid-cols-6">
              {kitaplik.length === 0 && <p className="col-span-full text-xs text-muted-foreground">{t('icerikStudyosu.form.kitaplikBos')}</p>}
              {kitaplik.map((r) => (
                <button key={r.anahtar} type="button" className="overflow-hidden rounded border border-white/10 disabled:opacity-40"
                  disabled={form.gorseller.some((x) => x.anahtar === r.anahtar)}
                  onClick={() => yaz('gorseller', [...form.gorseller, r].slice(0, 10))}>
                  <img src={r.url} alt={r.ad || ''} className="aspect-square w-full object-cover" loading="lazy" />
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <Alan etiket={t('icerikStudyosu.form.planlanan')}>
            <input className={GIRDI} type="datetime-local" value={form.planlanan} onChange={(e) => yaz('planlanan', e.target.value)} disabled={zamanKilitli} data-testid="is-form-planlanan" />
          </Alan>
          <Alan etiket={t('icerikStudyosu.form.saatDilimi')}>
            <select className={SECIM} value={form.saat_dilimi} onChange={(e) => yaz('saat_dilimi', e.target.value)} disabled={zamanKilitli}>
              {[...new Set([form.saat_dilimi, varsayilanTz, ...SAAT_DILIMLERI])].map((z) => (
                <option key={z} value={z}>
                  {z}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('icerikStudyosu.form.kampanya')} ipucu={t('icerikStudyosu.form.kampanyaIpucu')}>
            <input className={GIRDI} list="is-kampanyalar" value={form.kampanya} onChange={(e) => yaz('kampanya', e.target.value)} disabled={saltOkunur} maxLength={100} />
            <datalist id="is-kampanyalar">
              {kampanyalar.map((k) => (
                <option key={k} value={k} />
              ))}
            </datalist>
          </Alan>
          <Alan etiket={t('icerikStudyosu.form.sorumlu')} ipucu={t('icerikStudyosu.form.sorumluIpucu')}>
            <input className={GIRDI} type="email" value={form.sorumlu_eposta} onChange={(e) => yaz('sorumlu_eposta', e.target.value)} disabled={saltOkunur} dir="ltr" />
          </Alan>
          <div className="min-w-0">
            <Alan etiket={t('icerikStudyosu.form.proje')} ipucu={t('icerikStudyosu.form.projeIpucu')}>
              <select className={SECIM} value={form.proje_id ?? ''} disabled={saltOkunur} data-testid="is-form-proje"
                onChange={(e) => yaz('proje_id', e.target.value ? Number(e.target.value) : null)}>
                <option value="">{t('icerikStudyosu.form.projeYok')}</option>
                {form.proje_id && !projeler.some((p) => p.id === form.proje_id) && <option value={form.proje_id}>#{form.proje_id}</option>}
                {projeler.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.baslik}
                  </option>
                ))}
              </select>
            </Alan>
            {onerilenProje && !saltOkunur && (
              <p className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-sky-200" data-testid="is-proje-onerisi">
                <span>
                  {t('icerikStudyosu.form.projeOnerisi', { proje: onerilenProje.baslik })}
                </span>
                <button
                  type="button"
                  className="rounded-full border border-sky-400/40 px-2 py-0.5 font-medium hover:bg-sky-500/10"
                  onClick={() => yaz('proje_id', onerilenProje.id)}
                >
                  {t('icerikStudyosu.form.projeBagla')}
                </button>
              </p>
            )}
          </div>
        </div>
        <Alan etiket={t('icerikStudyosu.form.notlar')}>
          <textarea className={METIN_ALANI + ' min-h-[56px]'} value={form.notlar} onChange={(e) => yaz('notlar', e.target.value)} disabled={saltOkunur} />
        </Alan>
        {g && <Uyarilar uyarilar={g.uyarilar} />}

        {/* Durum geçişleri */}
        {g && !saltOkunur && gecisler.length > 0 && (
          <div className="rounded-xl border border-white/10 p-3" data-testid="is-form-gecisler">
            <p className="mb-2 text-sm font-medium">{t('icerikStudyosu.form.durumDegistir')}</p>
            <div className="flex flex-wrap gap-2">
              {gecisler.map((d) => (
                <Button key={d} type="button" size="sm" variant="outline" className={DIS_DUGME} disabled={!!calisiyor}
                  onClick={() => (d === 'reddedildi' ? setRetNotu('') : durumDegistir(d))} data-gecis={d}>
                  {calisiyor === `durum-${d}` && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                  {t(`icerikStudyosu.gecis.${d}`, { defaultValue: t(`icerikOnay.durum.${d}`) })}
                </Button>
              ))}
            </div>
            {retNotu !== null && (
              <div className="mt-2 flex flex-col gap-2 sm:flex-row">
                <input className={GIRDI} value={retNotu} onChange={(e) => setRetNotu(e.target.value)} placeholder={t('icerikStudyosu.form.retNotu')} data-testid="is-form-ret-notu" />
                <Button type="button" size="sm" disabled={!retNotu.trim()} onClick={() => durumDegistir('reddedildi', retNotu)}>
                  {t('icerikStudyosu.gecis.reddedildi')}
                </Button>
              </div>
            )}
          </div>
        )}

        {/* Müşteri onayı (yalnız yönetici, müşteri hesabındaki ajans gönderisi) */}
        {onayaGonderilebilir && g && (
          <div className="rounded-xl border border-fuchsia-400/30 bg-fuchsia-500/5 p-3" data-testid="is-form-onay">
            <p className="mb-1 flex items-center gap-1.5 text-sm font-medium">
              <Send className="h-4 w-4 text-fuchsia-300" aria-hidden="true" />
              {durum === 'musteri_onayi' ? t('icerikStudyosu.form.onayYenile') : t('icerikStudyosu.form.onayaGonder')}
            </p>
            {g.onay && (
              <p className="mb-2 text-xs text-muted-foreground" data-testid="is-form-onay-durumu" data-onay-durum={g.onay.durum}>
                {t(`icerikStudyosu.onayDurumu.${g.onay.durum}`, { defaultValue: g.onay.durum })} · {t('icerikStudyosu.form.sonKullanma')}: {tarihSaatYaz(g.onay.son_kullanma, dil)}
              </p>
            )}
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <select className={SECIM + ' sm:w-36'} value={onayGun} onChange={(e) => setOnayGun(Number(e.target.value))} aria-label={t('icerikStudyosu.form.gecerlilik')}>
                {[3, 7, 14, 30].map((n) => (
                  <option key={n} value={n}>
                    {t('icerikStudyosu.form.gun', { sayi: n })}
                  </option>
                ))}
              </select>
              <label className="flex items-center gap-2 text-xs">
                <input type="checkbox" className="h-4 w-4 accent-fuchsia-500" checked={onayEposta} onChange={(e) => setOnayEposta(e.target.checked)} />
                {t('icerikStudyosu.form.epostaGonder')}
              </label>
              <Button type="button" size="sm" className="gap-1.5 sm:ms-auto" onClick={onayaGonder} disabled={!!calisiyor} data-testid="is-form-onaya-gonder">
                {calisiyor === 'onay' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" aria-hidden="true" />}
                {durum === 'musteri_onayi' ? t('icerikStudyosu.form.onayYenile') : t('icerikStudyosu.form.onayaGonder')}
              </Button>
            </div>
            {onayBaglantisi && (
              <div className="mt-2 flex items-center gap-2 rounded-lg bg-black/30 p-2 text-xs">
                <span className="min-w-0 flex-1 truncate" dir="ltr" data-testid="is-onay-baglantisi">{onayBaglantisi}</span>
                <Button type="button" size="sm" variant="outline" className={DIS_DUGME}
                  onClick={async () => toast[(await panoyaKopyala(onayBaglantisi)) ? 'success' : 'error'](t('icerikStudyosu.kopyalandi'))}>
                  <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('icerikStudyosu.kopyala')}
                </Button>
              </div>
            )}
            {onayBaglantisi && <p className="mt-1 text-[11px] text-muted-foreground">{t('icerikStudyosu.form.baglantiBirKez')}</p>}
          </div>
        )}

        <div className="sticky bottom-0 -mx-4 flex flex-wrap gap-2 border-t border-white/10 bg-background/95 px-4 py-3 sm:-mx-6 sm:px-6">
          {!saltOkunur && (
            <Button type="button" onClick={kaydet} disabled={!!calisiyor} className="gap-1.5" data-testid="is-form-kaydet">
              {calisiyor === 'kaydet' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" aria-hidden="true" />}
              {t('icerikStudyosu.kaydet')}
            </Button>
          )}
          {g && (
            <Button type="button" variant="outline" className={DIS_DUGME} onClick={() => onPaket(g.id)} data-testid="is-form-paket">
              <Package className="h-4 w-4" aria-hidden="true" />
              {t('icerikStudyosu.paket.ac')}
            </Button>
          )}
          {g && !saltOkunur && (
            <Button type="button" variant="outline" className={DIS_DUGME + ' text-rose-200 sm:ms-auto'} onClick={sil} disabled={!!calisiyor}>
              <Trash2 className="h-4 w-4" aria-hidden="true" />
              {t('icerikStudyosu.sil')}
            </Button>
          )}
        </div>
      </div>
    </Cekmece>
  );
}
