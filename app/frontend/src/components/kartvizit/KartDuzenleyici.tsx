import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  Check,
  ChevronLeft,
  ChevronRight,
  Eye,
  GripVertical,
  ImagePlus,
  Loader2,
  Pencil,
  Plus,
  Save,
  Trash2,
  X,
} from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { KART, SECIM } from '@/components/dinamikQr/ortak';
import KartGorunumu, { PLATFORM_ADI } from '@/components/kartvizit/KartGorunumu';
import { apiAdresi, cevirmen, metinleriYukle, SABLONLAR, yaziTipiYukle, type AcikKart, type Cevirmen } from '@/lib/kartvizitAcik';
import {
  BOS_SAATLER,
  bosIcerik,
  hataMetni,
  slugOner,
  type Duzen,
  type Gorsel,
  type Icerik,
  type KartApi,
  type KartKaydi,
  type KartMeta,
  type PanelMod,
  type SlugDurumu,
  type Tema,
} from '@/lib/kartvizit';

/**
 * Faz 4K — kart düzenleyici: solda form, sağda canlı telefon önizlemesi
 * (herkese açık sayfayla AYNI bileşen, kartın kendi dilinde). Mobilde
 * "Düzenle / Önizleme" sekmeleri. Görseller kart bir kez kaydedildikten sonra
 * yüklenebiliyor (sunucuda WebP'ye çevriliyor). Bio link bağlantıları
 * sürükle-bırak ya da yukarı/aşağı düğmeleriyle sıralanıyor.
 */

const VARSAYILAN_META: Pick<KartMeta, 'sablonlar' | 'sablon_renkleri' | 'yazi_tipleri' | 'koseler' | 'platformlar' | 'simgeler' | 'gunler' | 'telefon_tipleri' | 'diller' | 'en_cok'> = {
  sablonlar: ['gece', 'beyaz', 'kurumsal', 'canli', 'doga'],
  sablon_renkleri: { gece: '#a855f7', beyaz: '#2563eb', kurumsal: '#1e3a8a', canli: '#ec4899', doga: '#15803d' },
  yazi_tipleri: ['jakarta', 'mono', 'sistem'],
  koseler: ['keskin', 'yumusak', 'yuvarlak'],
  platformlar: Object.keys(PLATFORM_ADI),
  simgeler: ['link', 'globe', 'shop', 'calendar', 'video', 'music', 'file', 'mail', 'phone', 'map', 'star', 'gift', 'book', 'briefcase', 'heart', 'camera', 'message', 'download', 'ticket', 'megaphone'],
  gunler: ['pzt', 'sal', 'car', 'per', 'cum', 'cmt', 'paz'],
  telefon_tipleri: ['cep', 'is', 'ev', 'faks'],
  diller: ['tr', 'en', 'de', 'ru', 'zh', 'hi', 'ar'],
  en_cok: { telefon: 5, web: 5, sosyal: 12, baglanti: 30, hizmet: 20, galeri: 8 },
};
const DIL_ADI: Record<string, string> = { tr: 'Türkçe', en: 'English', de: 'Deutsch', ru: 'Русский', zh: '中文', hi: 'हिन्दी', ar: 'العربية' };

function icerikHazirla(k: KartKaydi | null, gunler: string[]): Icerik {
  const bos = bosIcerik(gunler);
  if (!k) return bos;
  const i = k.icerik || bos;
  const saatler = i.calisma_saatleri?.gunler?.length ? i.calisma_saatleri : BOS_SAATLER(gunler);
  return { ...bos, ...i, calisma_saatleri: { ...BOS_SAATLER(gunler), ...saatler } };
}

function telAdresi(numara: string): string {
  let s = (numara || '').replace(/[^\d+]/g, '');
  s = s.startsWith('+') ? `+${s.replace(/\+/g, '')}` : s.replace(/\+/g, '');
  if (s.startsWith('00')) s = `+${s.slice(2)}`;
  return `tel:${s}`;
}

function webAdresi(url: string): string {
  const u = (url || '').trim();
  return /^[a-z][a-z0-9+.-]*:/i.test(u) ? u : `https://${u.replace(/^\/+/, '')}`;
}

export default function KartDuzenleyici({
  api,
  mod,
  meta,
  kayit,
  onKapat,
  onKaydedildi,
}: {
  api: KartApi;
  mod: PanelMod;
  meta: KartMeta | null;
  kayit: KartKaydi | null;
  onKapat: () => void;
  onKaydedildi: (k: KartKaydi) => void;
}) {
  const { t } = useTranslation();
  const M = { ...VARSAYILAN_META, ...(meta || {}) };
  const [kart, setKart] = useState<KartKaydi | null>(kayit);
  const [icerik, setIcerik] = useState<Icerik>(() => icerikHazirla(kayit, M.gunler));
  const [tema, setTema] = useState<Tema>(() => kayit?.tema || { sablon: 'gece', renk: '#a855f7', yazi_tipi: 'jakarta', kose: 'yumusak' });
  const [duzen, setDuzen] = useState<Duzen>(kayit?.duzen || 'kartvizit');
  const [dil, setDil] = useState(kayit?.dil || 'tr');
  const [slug, setSlug] = useState(kayit?.slug || '');
  const [slugElle, setSlugElle] = useState(!!kayit);
  const [slugDurumu, setSlugDurumu] = useState<SlugDurumu | null>(null);
  const [aktif, setAktif] = useState(kayit?.aktif ?? true);
  const [formAcik, setFormAcik] = useState(kayit?.form_acik ?? true);
  const [indexAcik, setIndexAcik] = useState(kayit?.index_acik ?? false);
  const [sifre, setSifre] = useState('');
  const [sifreKaldir, setSifreKaldir] = useState(false);
  const [hesapEmail, setHesapEmail] = useState('');
  const [kaydediliyor, setKaydediliyor] = useState(false);
  const [hata, setHata] = useState<string | null>(null);
  const [mobilSekme, setMobilSekme] = useState<'duzenle' | 'onizleme'>('duzenle');
  const [m, setM] = useState<Cevirmen>(() => cevirmen(null));
  const [gorselYukleniyor, setGorselYukleniyor] = useState<string | null>(null);

  useEffect(() => {
    setKart(kayit);
  }, [kayit]);

  useEffect(() => {
    let iptal = false;
    yaziTipiYukle(dil);
    void metinleriYukle(dil).then((s) => !iptal && setM(() => cevirmen(s)));
    return () => {
      iptal = true;
    };
  }, [dil]);

  // Yeni kartta slug addan önerilir (elle değiştirilene kadar).
  useEffect(() => {
    if (!slugElle) setSlug(slugOner(icerik.ad_soyad));
  }, [icerik.ad_soyad, slugElle]);

  useEffect(() => {
    if (!slug || slug === kart?.slug) {
      setSlugDurumu(null);
      return;
    }
    const z = window.setTimeout(() => {
      api
        .slugUygun(slug, kart?.id, icerik.ad_soyad)
        .then(setSlugDurumu)
        .catch(() => setSlugDurumu(null));
    }, 400);
    return () => window.clearTimeout(z);
  }, [slug, kart?.id, kart?.slug, api, icerik.ad_soyad]);

  const ic = <K extends keyof Icerik>(ad: K, deger: Icerik[K]) => setIcerik((x) => ({ ...x, [ad]: deger }));

  const onizleme: AcikKart = useMemo(
    () => ({
      durum: 'aktif',
      slug: slug || 'ornek',
      kod: kart?.kod || '',
      duzen,
      dil,
      tema,
      ad_soyad: icerik.ad_soyad || t('kartvizit.duzenle.ornekAd'),
      unvan: icerik.unvan,
      sirket: icerik.sirket,
      tanitim: icerik.tanitim,
      adres: icerik.adres,
      harita_url: icerik.harita_url || (icerik.adres ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(icerik.adres)}` : ''),
      telefonlar: icerik.telefonlar.filter((x) => x.numara.trim()).map((x) => ({ ...x, tel: telAdresi(x.numara) })),
      eposta: icerik.eposta,
      webler: icerik.webler.filter((w) => w.url.trim()).map((w) => ({ ...w, url: webAdresi(w.url) })),
      whatsapp_url: icerik.whatsapp ? `https://wa.me/${icerik.whatsapp.replace(/\D/g, '')}` : '',
      sosyal: icerik.sosyal.filter((s) => s.url.trim()).map((s) => ({ platform: s.platform, url: webAdresi(s.url) })),
      baglantilar: icerik.baglantilar.filter((b) => b.baslik.trim()),
      hizmetler: icerik.hizmetler.filter((h) => h.baslik.trim()),
      calisma_saatleri: icerik.calisma_saatleri.goster ? icerik.calisma_saatleri : null,
      foto: kart?.foto ?? null,
      logo: kart?.logo ?? null,
      kapak: kart?.kapak ?? null,
      galeri: kart?.galeri ?? [],
      form: { acik: formAcik, jeton: null, aydinlatma_adresi: '#' },
      kart_adresi: kart?.kart_adresi || '',
      index: indexAcik,
      vcard_adresi: '',
      qr_adresi: '',
    }),
    [slug, kart, duzen, dil, tema, icerik, formAcik, indexAcik, t]
  );

  const kaydet = async () => {
    setHata(null);
    if (!icerik.ad_soyad.trim()) {
      setHata(t('kartvizit.duzenle.adGerekli'));
      return;
    }
    setKaydediliyor(true);
    const govde: Record<string, unknown> = {
      icerik,
      tema,
      duzen,
      dil,
      aktif,
      form_acik: formAcik,
      index_acik: indexAcik,
      ...(slug ? { slug } : {}),
      ...(sifre ? { sifre } : {}),
      ...(sifreKaldir ? { sifre_kaldir: true } : {}),
      ...(mod === 'yonetici' && !kart && hesapEmail.trim() ? { hesap_email: hesapEmail.trim() } : {}),
    };
    try {
      const k = kart ? await api.guncelle(kart.id, govde) : await api.olustur(govde);
      setKart(k);
      setIcerik(icerikHazirla(k, M.gunler));
      setSlug(k.slug);
      setSlugElle(true);
      setSifre('');
      setSifreKaldir(false);
      toast.success(t(kart ? 'kartvizit.duzenle.kaydedildi' : 'kartvizit.duzenle.olusturuldu'));
      onKaydedildi(k);
    } catch (e) {
      setHata(hataMetni(t, e));
    } finally {
      setKaydediliyor(false);
    }
  };

  const gorselYukle = async (tur: string, dosya: File | undefined) => {
    if (!kart || !dosya) return;
    setGorselYukleniyor(tur);
    try {
      const k = await api.gorselYukle(kart.id, tur, dosya);
      setKart(k);
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setGorselYukleniyor(null);
    }
  };
  const gorselKaldir = async (g: Gorsel) => {
    if (!kart) return;
    try {
      setKart(await api.gorselKaldir(kart.id, g.id));
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };
  const galeriTasi = async (i: number, yon: -1 | 1) => {
    if (!kart) return;
    const idler = kart.galeri.map((g) => g.id);
    const j = i + yon;
    if (j < 0 || j >= idler.length) return;
    [idler[i], idler[j]] = [idler[j], idler[i]];
    try {
      setKart(await api.galeriSira(kart.id, idler));
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const form = (
    <div className="space-y-4">
      <Bolum baslik={t('kartvizit.duzenle.temel')}>
        <Alan etiket={t('kartvizit.alan.ad_soyad')} zorunlu>
          <Input value={icerik.ad_soyad} onChange={(e) => ic('ad_soyad', e.target.value)} maxLength={100} data-testid="kd-ad" />
        </Alan>
        <div className="grid gap-3 sm:grid-cols-2">
          <Alan etiket={t('kartvizit.alan.unvan')}>
            <Input value={icerik.unvan} onChange={(e) => ic('unvan', e.target.value)} maxLength={100} data-testid="kd-unvan" />
          </Alan>
          <Alan etiket={t('kartvizit.alan.sirket')}>
            <Input value={icerik.sirket} onChange={(e) => ic('sirket', e.target.value)} maxLength={120} data-testid="kd-sirket" />
          </Alan>
        </div>
        <Alan etiket={t('kartvizit.alan.tanitim')} ipucu={t('kartvizit.duzenle.tanitimIpucu')}>
          <Textarea value={icerik.tanitim} onChange={(e) => ic('tanitim', e.target.value)} maxLength={600} rows={3} data-testid="kd-tanitim" />
        </Alan>
        <div className="grid gap-3 sm:grid-cols-2">
          <Alan etiket={t('kartvizit.alan.duzen')} grup>
            <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label={t('kartvizit.alan.duzen')}>
              {(['kartvizit', 'bio_link'] as Duzen[]).map((d) => (
                <button
                  key={d}
                  type="button"
                  role="radio"
                  aria-checked={duzen === d}
                  onClick={() => setDuzen(d)}
                  className={`rounded-lg border px-2 py-2 text-xs ${duzen === d ? 'border-purple-400 bg-purple-500/15 text-white' : 'border-white/10 text-muted-foreground'}`}
                  data-testid={`kd-duzen-${d}`}
                >
                  {t(`kartvizit.duzen.${d}`)}
                </button>
              ))}
            </div>
          </Alan>
          <Alan etiket={t('kartvizit.alan.dil')} ipucu={t('kartvizit.duzenle.dilIpucu')}>
            <select className={SECIM} value={dil} onChange={(e) => setDil(e.target.value)} data-testid="kd-dil">
              {M.diller.map((d) => (
                <option key={d} value={d}>
                  {DIL_ADI[d] || d}
                </option>
              ))}
            </select>
          </Alan>
        </div>
        <Alan grup etiket={t('kartvizit.alan.slug')} ipucu={kart ? t('kartvizit.duzenle.slugIpucu', { gun: meta?.eski_slug_gun ?? 30 }) : undefined}>
          <div className="flex items-stretch overflow-hidden rounded-md border border-white/10 bg-black/40 kv-slug" dir="ltr">
            <span className="flex items-center whitespace-nowrap px-2 text-xs text-muted-foreground">/kart/</span>
            <input
              className="min-w-0 flex-1 bg-transparent px-1 py-2 text-sm text-white outline-none"
              value={slug}
              onChange={(e) => {
                setSlugElle(true);
                setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '').slice(0, 50));
              }}
              aria-label={t('kartvizit.alan.slug')}
              data-testid="kd-slug"
            />
          </div>
          {slugDurumu && (
            <p className={`mt-1 flex flex-wrap items-center gap-1 text-xs ${slugDurumu.uygun ? 'text-emerald-300' : 'text-amber-300'}`} role="status">
              {slugDurumu.uygun ? <Check className="h-3 w-3" aria-hidden="true" /> : null}
              {slugDurumu.uygun ? t('kartvizit.duzenle.slugUygun') : t(`kartvizit.hata.${slugDurumu.kod}`, { defaultValue: t('kartvizit.hata.genel') })}
              {!slugDurumu.uygun && slugDurumu.oneri && (
                <button type="button" className="underline" onClick={() => setSlug(slugDurumu.oneri)}>
                  {t('kartvizit.duzenle.oneriKullan', { oneri: slugDurumu.oneri })}
                </button>
              )}
            </p>
          )}
        </Alan>
      </Bolum>

      <Bolum baslik={t('kartvizit.duzenle.gorunum')}>
        <Alan etiket={t('kartvizit.alan.sablon')} grup>
          <div className="kv-sablonlar" role="radiogroup" aria-label={t('kartvizit.alan.sablon')}>
            {M.sablonlar.map((s) => (
              <button
                key={s}
                type="button"
                role="radio"
                aria-checked={tema.sablon === s}
                onClick={() => setTema({ ...tema, sablon: s, renk: M.sablon_renkleri[s] || tema.renk })}
                className={`flex flex-col items-center gap-1 rounded-lg border p-1.5 text-[10px] ${tema.sablon === s ? 'border-purple-400 text-white' : 'border-white/10 text-muted-foreground'}`}
                data-testid={`kd-sablon-${s}`}
              >
                <span
                  className="kv-sablon-ornek"
                  style={{ background: (SABLONLAR[s]?.zemin || '#000').replace(/var\(--kv-vurgu\)/g, M.sablon_renkleri[s] || '#888') }}
                  aria-hidden="true"
                />
                <span className="truncate">{t(`kartvizit.sablon.${s}`)}</span>
              </button>
            ))}
          </div>
        </Alan>
        <div className="grid gap-3 sm:grid-cols-3">
          <Alan etiket={t('kartvizit.alan.renk')} grup>
            <div className="flex items-center gap-2">
              <input
                type="color"
                value={tema.renk}
                onChange={(e) => setTema({ ...tema, renk: e.target.value })}
                className="h-10 w-12 cursor-pointer rounded border border-white/10 bg-transparent"
                aria-label={t('kartvizit.alan.renk')}
                data-testid="kd-renk"
              />
              <span className="font-mono text-xs text-muted-foreground" dir="ltr">
                {tema.renk}
              </span>
            </div>
          </Alan>
          <Alan etiket={t('kartvizit.alan.yazi_tipi')}>
            <select className={SECIM} value={tema.yazi_tipi} onChange={(e) => setTema({ ...tema, yazi_tipi: e.target.value })}>
              {M.yazi_tipleri.map((y) => (
                <option key={y} value={y}>
                  {t(`kartvizit.yaziTipi.${y}`)}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('kartvizit.alan.kose')}>
            <select className={SECIM} value={tema.kose} onChange={(e) => setTema({ ...tema, kose: e.target.value })}>
              {M.koseler.map((k) => (
                <option key={k} value={k}>
                  {t(`kartvizit.kose.${k}`)}
                </option>
              ))}
            </select>
          </Alan>
        </div>
      </Bolum>

      <Bolum baslik={t('kartvizit.duzenle.gorseller')}>
        {!kart ? (
          <p className="text-xs text-muted-foreground">{t('kartvizit.duzenle.gorselOnceKaydet')}</p>
        ) : (
          <>
            <p className="text-xs text-muted-foreground">{t('kartvizit.duzenle.gorselIpucu', { mb: meta?.gorsel_en_cok_mb ?? 5 })}</p>
            <div className="grid gap-3 sm:grid-cols-3">
              {(['foto', 'logo', 'kapak'] as const).map((tur) => (
                <GorselAlani
                  key={tur}
                  etiket={t(`kartvizit.gorsel.${tur}`)}
                  gorsel={kart[tur]}
                  yukleniyor={gorselYukleniyor === tur}
                  onSec={(d) => void gorselYukle(tur, d)}
                  onKaldir={(g) => void gorselKaldir(g)}
                  testId={`kd-gorsel-${tur}`}
                  t={t}
                />
              ))}
            </div>
            <div>
              <p className="mb-2 text-xs font-medium">
                {t('kartvizit.gorsel.galeri')} ({kart.galeri.length}/{M.en_cok.galeri})
              </p>
              <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
                {kart.galeri.map((g, i) => (
                  <div key={g.id} className="relative overflow-hidden rounded-lg border border-white/10">
                    <img src={apiAdresi(g.url)} alt="" width={g.genislik} height={g.yukseklik} className="aspect-square w-full object-cover" loading="lazy" />
                    <div className="absolute inset-x-0 bottom-0 flex justify-between bg-black/60 p-0.5">
                      <button type="button" className="p-1 disabled:opacity-30" disabled={i === 0} onClick={() => void galeriTasi(i, -1)} aria-label={t('kartvizit.duzenle.sola')}>
                        <ChevronLeft className="h-3.5 w-3.5 rtl:-scale-x-100" aria-hidden="true" />
                      </button>
                      <button type="button" className="p-1 text-red-300" onClick={() => void gorselKaldir(g)} aria-label={t('kartvizit.duzenle.kaldir')}>
                        <X className="h-3.5 w-3.5" aria-hidden="true" />
                      </button>
                      <button
                        type="button"
                        className="p-1 disabled:opacity-30"
                        disabled={i === kart.galeri.length - 1}
                        onClick={() => void galeriTasi(i, 1)}
                        aria-label={t('kartvizit.duzenle.saga')}
                      >
                        <ChevronRight className="h-3.5 w-3.5 rtl:-scale-x-100" aria-hidden="true" />
                      </button>
                    </div>
                  </div>
                ))}
                {kart.galeri.length < M.en_cok.galeri && (
                  <DosyaDugmesi onSec={(d) => void gorselYukle('galeri', d)} yukleniyor={gorselYukleniyor === 'galeri'} etiket={t('kartvizit.duzenle.galeriEkle')} testId="kd-galeri-ekle" kare />
                )}
              </div>
            </div>
          </>
        )}
      </Bolum>

      <Bolum baslik={t('kartvizit.duzenle.iletisim')}>
        <ListeAlani
          baslik={t('kartvizit.alan.telefonlar')}
          testId="telefonlar"
          ogeler={icerik.telefonlar}
          enCok={M.en_cok.telefon}
          yeni={() => ({ etiket: '', numara: '', tip: 'cep' })}
          degisti={(x) => ic('telefonlar', x)}
          t={t}
          satir={(o, d) => (
            <div className="kv-satir kv-satir-tel">
              <Input value={o.etiket} onChange={(e) => d({ ...o, etiket: e.target.value })} placeholder={t('kartvizit.alan.etiket')} maxLength={30} aria-label={t('kartvizit.alan.etiket')} />
              <Input value={o.numara} onChange={(e) => d({ ...o, numara: e.target.value })} placeholder="+90 555 111 22 33" maxLength={32} dir="ltr" inputMode="tel" aria-label={t('kartvizit.alan.numara')} data-testid="kd-telefon" />
              <select className={SECIM} value={o.tip} onChange={(e) => d({ ...o, tip: e.target.value })} aria-label={t('kartvizit.alan.tip')}>
                {M.telefon_tipleri.map((x) => (
                  <option key={x} value={x}>
                    {t(`kartvizit.telefonTipi.${x}`)}
                  </option>
                ))}
              </select>
            </div>
          )}
        />
        <div className="grid gap-3 sm:grid-cols-2">
          <Alan etiket={t('kartvizit.alan.eposta')}>
            <Input type="email" value={icerik.eposta} onChange={(e) => ic('eposta', e.target.value)} maxLength={254} dir="ltr" data-testid="kd-eposta" />
          </Alan>
          <Alan etiket={t('kartvizit.alan.whatsapp')} ipucu={t('kartvizit.duzenle.whatsappIpucu')}>
            <Input value={icerik.whatsapp} onChange={(e) => ic('whatsapp', e.target.value)} placeholder="+905551112233" maxLength={32} dir="ltr" inputMode="tel" data-testid="kd-whatsapp" />
          </Alan>
        </div>
        <ListeAlani
          baslik={t('kartvizit.alan.webler')}
          testId="webler"
          ogeler={icerik.webler}
          enCok={M.en_cok.web}
          yeni={() => ({ etiket: '', url: '' })}
          degisti={(x) => ic('webler', x)}
          t={t}
          satir={(o, d) => (
            <div className="kv-satir kv-satir-web">
              <Input value={o.etiket} onChange={(e) => d({ ...o, etiket: e.target.value })} placeholder={t('kartvizit.alan.etiket')} maxLength={30} aria-label={t('kartvizit.alan.etiket')} />
              <Input value={o.url} onChange={(e) => d({ ...o, url: e.target.value })} placeholder="ornek.com" maxLength={500} dir="ltr" aria-label={t('kartvizit.alan.url')} />
            </div>
          )}
        />
        <Alan etiket={t('kartvizit.alan.adres')}>
          <Textarea value={icerik.adres} onChange={(e) => ic('adres', e.target.value)} maxLength={300} rows={2} />
        </Alan>
        <Alan etiket={t('kartvizit.alan.harita_url')} ipucu={t('kartvizit.duzenle.haritaIpucu')}>
          <Input value={icerik.harita_url} onChange={(e) => ic('harita_url', e.target.value)} maxLength={500} dir="ltr" placeholder="https://maps.app.goo.gl/…" />
        </Alan>
      </Bolum>

      <Bolum baslik={t('kartvizit.duzenle.sosyal')}>
        <ListeAlani
          baslik={t('kartvizit.alan.sosyal')}
          testId="sosyal"
          ogeler={icerik.sosyal}
          enCok={M.en_cok.sosyal}
          yeni={() => ({ platform: 'linkedin', url: '' })}
          degisti={(x) => ic('sosyal', x)}
          t={t}
          ipucu={t('kartvizit.duzenle.sosyalIpucu')}
          satir={(o, d) => (
            <div className="kv-satir kv-satir-sosyal">
              <select className={SECIM} value={o.platform} onChange={(e) => d({ ...o, platform: e.target.value })} aria-label={t('kartvizit.alan.platform')}>
                {M.platformlar.map((p) => (
                  <option key={p} value={p}>
                    {PLATFORM_ADI[p] || p}
                  </option>
                ))}
              </select>
              <Input value={o.url} onChange={(e) => d({ ...o, url: e.target.value })} placeholder="@kullanici / https://…" maxLength={500} dir="ltr" aria-label={t('kartvizit.alan.url')} data-testid="kd-sosyal-url" />
            </div>
          )}
        />
      </Bolum>

      <Bolum baslik={t('kartvizit.duzenle.baglantilar')} aciklama={duzen === 'bio_link' ? t('kartvizit.duzenle.baglantilarBio') : t('kartvizit.duzenle.baglantilarKart')}>
        <ListeAlani
          baslik={t('kartvizit.alan.baglantilar')}
          testId="baglantilar"
          ogeler={icerik.baglantilar}
          enCok={M.en_cok.baglanti}
          yeni={() => ({ baslik: '', url: '', simge: 'link' })}
          degisti={(x) => ic('baglantilar', x)}
          t={t}
          siralanir
          satir={(o, d) => (
            <div className="kv-satir kv-satir-bag">
              <Input value={o.baslik} onChange={(e) => d({ ...o, baslik: e.target.value })} placeholder={t('kartvizit.alan.baslik')} maxLength={80} aria-label={t('kartvizit.alan.baslik')} data-testid="kd-bag-baslik" />
              <Input value={o.url} onChange={(e) => d({ ...o, url: e.target.value })} placeholder="https://…" maxLength={500} dir="ltr" aria-label={t('kartvizit.alan.url')} data-testid="kd-bag-url" />
              <select className={SECIM} value={o.simge} onChange={(e) => d({ ...o, simge: e.target.value })} aria-label={t('kartvizit.alan.simge')}>
                {M.simgeler.map((s) => (
                  <option key={s} value={s}>
                    {t(`kartvizit.simge.${s}`)}
                  </option>
                ))}
              </select>
            </div>
          )}
        />
      </Bolum>

      <Bolum baslik={t('kartvizit.duzenle.hizmetler')}>
        <ListeAlani
          baslik={t('kartvizit.alan.hizmetler')}
          testId="hizmetler"
          ogeler={icerik.hizmetler}
          enCok={M.en_cok.hizmet}
          yeni={() => ({ baslik: '', aciklama: '' })}
          degisti={(x) => ic('hizmetler', x)}
          t={t}
          siralanir
          satir={(o, d) => (
            <div className="grid flex-1 gap-2">
              <Input value={o.baslik} onChange={(e) => d({ ...o, baslik: e.target.value })} placeholder={t('kartvizit.alan.baslik')} maxLength={80} aria-label={t('kartvizit.alan.baslik')} />
              <Textarea value={o.aciklama} onChange={(e) => d({ ...o, aciklama: e.target.value })} placeholder={t('kartvizit.alan.aciklama')} maxLength={300} rows={2} aria-label={t('kartvizit.alan.aciklama')} />
            </div>
          )}
        />
      </Bolum>

      <Bolum baslik={t('kartvizit.duzenle.saatler')}>
        <Anahtar
          etiket={t('kartvizit.duzenle.saatlerGoster')}
          deger={icerik.calisma_saatleri.goster}
          degisti={(v) => ic('calisma_saatleri', { ...icerik.calisma_saatleri, goster: v })}
        />
        {icerik.calisma_saatleri.goster && (
          <div className="space-y-1.5">
            {icerik.calisma_saatleri.gunler.map((g, i) => {
              const d = (yeni: typeof g) => {
                const gunler = [...icerik.calisma_saatleri.gunler];
                gunler[i] = yeni;
                ic('calisma_saatleri', { ...icerik.calisma_saatleri, gunler });
              };
              return (
                <div key={g.gun} className="kv-satir-saat">
                  <span>{m(`gun.${g.gun}`) || g.gun}</span>
                  <input type="checkbox" checked={g.acik} onChange={(e) => d({ ...g, acik: e.target.checked, acilis: g.acilis || '09:00', kapanis: g.kapanis || '18:00' })} aria-label={t('kartvizit.duzenle.acik')} className="h-4 w-4 accent-purple-500" />
                  <Input type="time" value={g.acik ? g.acilis : ''} disabled={!g.acik} onChange={(e) => d({ ...g, acilis: e.target.value })} aria-label={t('kartvizit.duzenle.acilis')} dir="ltr" />
                  <Input type="time" value={g.acik ? g.kapanis : ''} disabled={!g.acik} onChange={(e) => d({ ...g, kapanis: e.target.value })} aria-label={t('kartvizit.duzenle.kapanis')} dir="ltr" />
                </div>
              );
            })}
            <Input
              value={icerik.calisma_saatleri.not}
              onChange={(e) => ic('calisma_saatleri', { ...icerik.calisma_saatleri, not: e.target.value })}
              placeholder={t('kartvizit.duzenle.saatNotu')}
              maxLength={120}
              aria-label={t('kartvizit.duzenle.saatNotu')}
            />
          </div>
        )}
      </Bolum>

      <Bolum baslik={t('kartvizit.duzenle.ayarlar')}>
        <Anahtar etiket={t('kartvizit.duzenle.aktif')} deger={aktif} degisti={setAktif} testId="kd-aktif" />
        <Anahtar etiket={t('kartvizit.duzenle.formAcik')} aciklama={t('kartvizit.duzenle.formAcikAciklama')} deger={formAcik} degisti={setFormAcik} />
        <Anahtar etiket={t('kartvizit.duzenle.index')} aciklama={t('kartvizit.duzenle.indexAciklama')} deger={indexAcik} degisti={setIndexAcik} testId="kd-index" />
        <Alan grup etiket={t('kartvizit.alan.sifre')} ipucu={kart?.sifreli ? t('kartvizit.duzenle.sifreVar') : t('kartvizit.duzenle.sifreIpucu')}>
          <div className="flex flex-wrap items-center gap-2">
            <Input
              type="password"
              value={sifre}
              onChange={(e) => {
                setSifre(e.target.value);
                setSifreKaldir(false);
              }}
              autoComplete="new-password"
              maxLength={128}
              className="max-w-xs"
              placeholder={kart?.sifreli ? '••••••••' : ''}
              aria-label={t('kartvizit.alan.sifre')}
              data-testid="kd-sifre"
            />
            {kart?.sifreli && (
              <label className="flex items-center gap-1.5 text-xs">
                <input type="checkbox" checked={sifreKaldir} onChange={(e) => setSifreKaldir(e.target.checked)} className="accent-purple-500" />
                {t('kartvizit.duzenle.sifreKaldir')}
              </label>
            )}
          </div>
        </Alan>
        {mod === 'yonetici' && !kart && (
          <Alan etiket={t('kartvizit.alan.hesap_email')} ipucu={t('kartvizit.duzenle.hesapIpucu')}>
            <Input type="email" value={hesapEmail} onChange={(e) => setHesapEmail(e.target.value)} dir="ltr" maxLength={254} data-testid="kd-hesap" />
          </Alan>
        )}
      </Bolum>
    </div>
  );

  return (
    <div data-testid="kart-duzenleyici">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" className="gap-1.5" onClick={onKapat}>
          <ArrowLeft className="h-4 w-4 rtl:-scale-x-100" aria-hidden="true" />
          {t('kartvizit.duzenle.listeyeDon')}
        </Button>
        <h3 className="text-lg font-semibold">{kart ? t('kartvizit.duzenle.duzenleBaslik') : t('kartvizit.duzenle.yeniBaslik')}</h3>
        {kart && (
          <a href={kart.kart_adresi} target="_blank" rel="noopener" className="ms-auto text-sm text-purple-300 hover:underline" dir="ltr">
            /kart/{kart.slug}
          </a>
        )}
      </div>
      <div className="mb-3 grid grid-cols-2 gap-1 rounded-lg border border-white/10 p-1 lg:hidden" role="tablist">
        {(['duzenle', 'onizleme'] as const).map((s) => (
          <button
            key={s}
            type="button"
            role="tab"
            aria-selected={mobilSekme === s}
            onClick={() => setMobilSekme(s)}
            className={`flex items-center justify-center gap-1.5 rounded-md py-2 text-sm ${mobilSekme === s ? 'bg-purple-500/20 text-white' : 'text-muted-foreground'}`}
            data-testid={`kd-mobil-${s}`}
          >
            {s === 'duzenle' ? <Pencil className="h-4 w-4" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}
            {t(`kartvizit.duzenle.${s}`)}
          </button>
        ))}
      </div>
      <div className="kv-duzen-izgara">
        <div className={mobilSekme === 'duzenle' ? 'block' : 'hidden lg:block'}>
          {form}
          <div className="kv-kaydet-cubugu">
            <Button onClick={() => void kaydet()} disabled={kaydediliyor} className="gap-1.5" data-testid="kd-kaydet">
              {kaydediliyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Save className="h-4 w-4" aria-hidden="true" />}
              {kart ? t('kartvizit.duzenle.kaydet') : t('kartvizit.duzenle.olustur')}
            </Button>
            <Button variant="ghost" onClick={onKapat}>
              {t('kartvizit.duzenle.vazgec')}
            </Button>
            {hata && (
              <p className="w-full text-sm text-red-300" role="alert" data-testid="kd-hata">
                {hata}
              </p>
            )}
          </div>
        </div>
        <div className={mobilSekme === 'onizleme' ? 'block' : 'hidden lg:block'}>
          <div className="lg:sticky lg:top-4">
            <p className="mb-2 text-center text-xs text-muted-foreground">{t('kartvizit.duzenle.canliOnizleme')}</p>
            <div
              className="kv-telefon"
              data-testid="kd-onizleme"
              aria-label={t('kartvizit.duzenle.canliOnizleme')}
            >
              <KartGorunumu kart={onizleme} m={m} onizleme />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Bolum({ baslik, aciklama, children }: { baslik: string; aciklama?: string; children: ReactNode }) {
  return (
    <section className={`${KART} space-y-3 p-4`}>
      <div>
        <h4 className="text-sm font-semibold">{baslik}</h4>
        {aciklama && <p className="mt-0.5 text-xs text-muted-foreground">{aciklama}</p>}
      </div>
      {children}
    </section>
  );
}

/** Etiketli alan. `grup`: içinde birden çok denetim var (etiket `<label>` değil, başlık). */
function Alan({ etiket, ipucu, zorunlu, grup, children }: { etiket: string; ipucu?: string; zorunlu?: boolean; grup?: boolean; children: ReactNode }) {
  const Kap = grup ? 'div' : 'label';
  return (
    <Kap className="block">
      <span className="mb-1 block text-xs font-medium text-muted-foreground">
        {etiket}
        {zorunlu && <span className="text-red-300"> *</span>}
      </span>
      {children}
      {ipucu && <span className="mt-1 block text-[11px] text-muted-foreground">{ipucu}</span>}
    </Kap>
  );
}

function Anahtar({ etiket, aciklama, deger, degisti, testId }: { etiket: string; aciklama?: string; deger: boolean; degisti: (v: boolean) => void; testId?: string }) {
  return (
    <label className="flex cursor-pointer items-start gap-3">
      <input type="checkbox" checked={deger} onChange={(e) => degisti(e.target.checked)} className="mt-0.5 h-4 w-4 accent-purple-500" data-testid={testId} />
      <span>
        <span className="block text-sm">{etiket}</span>
        {aciklama && <span className="block text-xs text-muted-foreground">{aciklama}</span>}
      </span>
    </label>
  );
}

function ListeAlani<T>({
  baslik,
  ogeler,
  enCok,
  yeni,
  degisti,
  satir,
  siralanir,
  ipucu,
  testId,
  t,
}: {
  baslik: string;
  testId: string;
  ogeler: T[];
  enCok: number;
  yeni: () => T;
  degisti: (x: T[]) => void;
  satir: (o: T, d: (y: T) => void) => ReactNode;
  siralanir?: boolean;
  ipucu?: string;
  t: (k: string, o?: Record<string, unknown>) => string;
}) {
  const [surukle, setSurukle] = useState<number | null>(null);
  const tasi = (i: number, j: number) => {
    if (j < 0 || j >= ogeler.length || i === j) return;
    const y = [...ogeler];
    const [o] = y.splice(i, 1);
    y.splice(j, 0, o);
    degisti(y);
  };
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-muted-foreground">
          {baslik} ({ogeler.length}/{enCok})
        </span>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-8 gap-1 !bg-transparent border-white/20 text-xs"
          disabled={ogeler.length >= enCok}
          onClick={() => degisti([...ogeler, yeni()])}
          data-testid={`kd-ekle-${testId}`}
        >
          <Plus className="h-3.5 w-3.5" aria-hidden="true" />
          {t('kartvizit.duzenle.ekle')}
        </Button>
      </div>
      {ipucu && <p className="mb-1.5 text-[11px] text-muted-foreground">{ipucu}</p>}
      <ul className="space-y-2">
        {ogeler.map((o, i) => (
          <li
            key={i}
            className={`flex items-start gap-1.5 rounded-lg border border-white/10 bg-black/20 p-2 ${surukle === i ? 'opacity-50' : ''}`}
            draggable={siralanir}
            onDragStart={() => setSurukle(i)}
            onDragOver={(e) => siralanir && e.preventDefault()}
            onDrop={() => {
              if (surukle !== null) tasi(surukle, i);
              setSurukle(null);
            }}
            onDragEnd={() => setSurukle(null)}
          >
            {siralanir && (
              <div className="flex flex-col items-center">
                <GripVertical className="mt-1 hidden h-4 w-4 cursor-grab text-muted-foreground sm:block" aria-hidden="true" />
                <button type="button" className="p-1 disabled:opacity-30" disabled={i === 0} onClick={() => tasi(i, i - 1)} aria-label={t('kartvizit.duzenle.yukari')}>
                  <ArrowUp className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
                <button type="button" className="p-1 disabled:opacity-30" disabled={i === ogeler.length - 1} onClick={() => tasi(i, i + 1)} aria-label={t('kartvizit.duzenle.asagi')}>
                  <ArrowDown className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              </div>
            )}
            {satir(o, (y) => {
              const z = [...ogeler];
              z[i] = y;
              degisti(z);
            })}
            <button
              type="button"
              className="mt-1 shrink-0 rounded p-1.5 text-red-300 hover:bg-red-500/10"
              onClick={() => degisti(ogeler.filter((_, j) => j !== i))}
              aria-label={t('kartvizit.duzenle.kaldir')}
            >
              <Trash2 className="h-4 w-4" aria-hidden="true" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function DosyaDugmesi({ onSec, yukleniyor, etiket, testId, kare }: { onSec: (d: File | undefined) => void; yukleniyor: boolean; etiket: string; testId?: string; kare?: boolean }) {
  const girdi = useRef<HTMLInputElement>(null);
  return (
    <>
      <button
        type="button"
        onClick={() => girdi.current?.click()}
        disabled={yukleniyor}
        className={`flex items-center justify-center gap-1.5 rounded-lg border border-dashed border-white/20 text-xs text-muted-foreground hover:border-purple-400 hover:text-white ${kare ? 'aspect-square flex-col' : 'h-10 px-3'}`}
        data-testid={testId}
      >
        {yukleniyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <ImagePlus className="h-4 w-4" aria-hidden="true" />}
        {etiket}
      </button>
      <input
        ref={girdi}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className="hidden"
        onChange={(e) => {
          onSec(e.target.files?.[0]);
          e.target.value = '';
        }}
        data-testid={testId ? `${testId}-dosya` : undefined}
      />
    </>
  );
}

function GorselAlani({
  etiket,
  gorsel,
  yukleniyor,
  onSec,
  onKaldir,
  testId,
  t,
}: {
  etiket: string;
  gorsel: Gorsel | null;
  yukleniyor: boolean;
  onSec: (d: File | undefined) => void;
  onKaldir: (g: Gorsel) => void;
  testId: string;
  t: (k: string) => string;
}) {
  return (
    <div className="rounded-lg border border-white/10 bg-black/20 p-2">
      <p className="mb-1.5 text-xs font-medium">{etiket}</p>
      {gorsel ? (
        <div className="space-y-1.5">
          <img src={apiAdresi(gorsel.url)} alt="" width={gorsel.genislik} height={gorsel.yukseklik} className="kv-gorsel-onizleme" data-testid={`${testId}-onizleme`} />
          <div className="flex gap-1">
            <DosyaDugmesi onSec={onSec} yukleniyor={yukleniyor} etiket={t('kartvizit.duzenle.degistir')} testId={testId} />
            <button type="button" className="rounded p-2 text-red-300 hover:bg-red-500/10" onClick={() => onKaldir(gorsel)} aria-label={t('kartvizit.duzenle.kaldir')}>
              <Trash2 className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        </div>
      ) : (
        <DosyaDugmesi onSec={onSec} yukleniyor={yukleniyor} etiket={t('kartvizit.duzenle.yukle')} testId={testId} />
      )}
    </div>
  );
}
