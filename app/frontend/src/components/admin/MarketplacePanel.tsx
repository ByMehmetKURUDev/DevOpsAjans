import { useEffect, useState } from 'react';
import { Eye, EyeOff, Loader2, Pencil, Plus, Trash2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { client } from '@/lib/sdkClient';
import {
  CEVIRI_DILLERI,
  CEVRILEBILIR_ALANLAR,
  KATEGORILER,
  kategoriEtiketi,
  type CevrilebilirAlan,
  type MarketplaceUrunu,
} from '@/lib/marketplace';

/**
 * Marketplace ürünlerinin yönetimi.
 *
 * Ayrı bir bileşen: AdminPanel zaten iki bin satır ve her yeni sekme onu
 * biraz daha okunmaz yapıyor. Burada durunca yalnızca sekme açılınca
 * indiriliyor.
 *
 * Yazma işlemleri `client.entities.marketplace_items` üzerinden gidiyor;
 * o uç yönetici yetkisi istiyor. Sitenin gösterdiği liste ayrı, herkese
 * açık uçtan geliyor ve yalnızca `published` ürünleri döndürüyor.
 */

type Taslak = Partial<MarketplaceUrunu> & { id?: number };

/** Düzenleme formundaki çeviri alanları: dil → alan → metin. */
type CeviriFormu = Record<string, Partial<Record<CevrilebilirAlan, string>>>;

/** Çeviri formunda alanların sırası ve etiket anahtarları (Türkçe formla aynı). */
const CEVIRI_ALAN_ETIKETI: Record<CevrilebilirAlan, string> = {
  title: 'marketplaceAdmin.fBaslik',
  summary: 'marketplaceAdmin.fOzet',
  features: 'marketplaceAdmin.fOzellikler',
  price_note: 'marketplaceAdmin.fFiyatNotu',
  delivery_time: 'marketplaceAdmin.fTeslim',
  badge: 'marketplaceAdmin.fRozet',
  description: 'marketplaceAdmin.fAciklama',
};
const CEVIRI_ALAN_SIRASI: CevrilebilirAlan[] = [
  'title',
  'summary',
  'features',
  'price_note',
  'delivery_time',
  'badge',
  'description',
];
const COK_SATIRLI = new Set<CevrilebilirAlan>(['summary', 'features', 'description']);

/** Kayıtlı çevirilerden form durumunu kurar (her dil, her alan). */
function ceviriFormuKur(urun: Taslak): CeviriFormu {
  const form: CeviriFormu = {};
  for (const d of CEVIRI_DILLERI) {
    form[d] = {};
    for (const a of CEVRILEBILIR_ALANLAR) form[d][a] = urun.ceviriler?.[d]?.[a] ?? '';
  }
  return form;
}

/** Formdaki dolu çeviri alanları; boş alan kaydedilmez (sitede Türkçeye düşer). */
function ceviriFormunuTopla(form: CeviriFormu): Record<string, Partial<Record<CevrilebilirAlan, string>>> {
  const sonuc: Record<string, Partial<Record<CevrilebilirAlan, string>>> = {};
  for (const d of CEVIRI_DILLERI) {
    for (const a of CEVRILEBILIR_ALANLAR) {
      const deger = (form[d]?.[a] ?? '').trim();
      if (deger) (sonuc[d] ??= {})[a] = deger;
    }
  }
  return sonuc;
}

/** Bir üründe en az bir alanı çevrilmiş dil sayısı. */
function ceviriliDilSayisi(urun: MarketplaceUrunu): number {
  return CEVIRI_DILLERI.filter((d) => Object.values(urun.ceviriler?.[d] ?? {}).some((v) => (v ?? '').trim())).length;
}

const BOS: Taslak = {
  title: '',
  slug: '',
  category: 'website',
  summary: '',
  description: '',
  features: '',
  price: '',
  currency: 'USD',
  price_note: '',
  delivery_time: '',
  image_url: '',
  demo_url: '',
  badge: '',
  published: false,
  sort_order: undefined,
};

/** Başlıktan URL'ye uygun kısa ad. Türkçe harfler karşılıklarına düşüyor. */
function slugla(metin: string): string {
  const harita: Record<string, string> = {
    ç: 'c', ğ: 'g', ı: 'i', ö: 'o', ş: 's', ü: 'u',
    Ç: 'c', Ğ: 'g', İ: 'i', Ö: 'o', Ş: 's', Ü: 'u',
  };
  return metin
    .split('')
    .map((k) => harita[k] ?? k)
    .join('')
    .toLocaleLowerCase('tr')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80);
}

export default function MarketplacePanel() {
  const { t } = useTranslation();
  const [urunler, setUrunler] = useState<MarketplaceUrunu[] | null>(null);
  const [duzenlenen, setDuzenlenen] = useState<Taslak | null>(null);
  const [kaydediliyor, setKaydediliyor] = useState(false);
  // Formda hangi dil düzenleniyor: 'tr' ana alanlar, diğerleri `ceviriler`.
  const [formDili, setFormDili] = useState<string>('tr');
  const [ceviriFormu, setCeviriFormu] = useState<CeviriFormu>({});

  const duzenlemeyeBasla = (urun: Taslak) => {
    setFormDili('tr');
    setCeviriFormu(ceviriFormuKur(urun));
    setDuzenlenen(urun);
  };

  const yukle = () => {
    void client.entities.marketplace_items
      .query({ sort: '-created_at', limit: 200 })
      .then((y: unknown) => {
        const kok = (y ?? {}) as Record<string, unknown>;
        const govde = ('data' in kok ? kok.data : kok) as { items?: MarketplaceUrunu[] };
        setUrunler(govde?.items ?? []);
      })
      .catch(() => {
        setUrunler([]);
        toast.error(t('marketplaceAdmin.listeHatasi'));
      });
  };

  useEffect(yukle, []); // eslint-disable-line react-hooks/exhaustive-deps

  const kaydet = async () => {
    if (!duzenlenen) return;
    const baslik = (duzenlenen.title || '').trim();
    if (!baslik) {
      toast.error(t('marketplaceAdmin.baslikGerekli'));
      return;
    }

    // Slug boşsa başlıktan üretiliyor; kullanıcının her ürün için ayrıca
    // slug düşünmesi gereksiz bir yük.
    const ceviriler = ceviriFormunuTopla(ceviriFormu);
    const payload = {
      ...duzenlenen,
      // Hepsi silindiyse boş sözlük gönderiliyor: kısmi güncellemede `null`
      // "değiştirme" demek, eski çeviriler yerinde kalırdı.
      ceviriler: Object.keys(ceviriler).length ? ceviriler : duzenlenen.id ? {} : null,
      title: baslik,
      slug: (duzenlenen.slug || '').trim() || slugla(baslik),
      sort_order:
        duzenlenen.sort_order === undefined || duzenlenen.sort_order === null
          ? null
          : Number(duzenlenen.sort_order),
    };
    delete (payload as { id?: number }).id;

    setKaydediliyor(true);
    try {
      if (duzenlenen.id) {
        await client.entities.marketplace_items.update({
          id: String(duzenlenen.id),
          data: payload,
        });
      } else {
        await client.entities.marketplace_items.create({ data: payload });
      }
      toast.success(t('marketplaceAdmin.kaydedildi'));
      setDuzenlenen(null);
      yukle();
    } catch (e) {
      const err = e as { message?: string };
      toast.error(err?.message || t('marketplaceAdmin.kaydetmeHatasi'));
    } finally {
      setKaydediliyor(false);
    }
  };

  const yayinDegistir = async (urun: MarketplaceUrunu) => {
    try {
      await client.entities.marketplace_items.update({
        id: String(urun.id),
        data: { published: !((urun as { published?: boolean }).published) },
      });
      yukle();
    } catch {
      toast.error(t('marketplaceAdmin.kaydetmeHatasi'));
    }
  };

  const sil = async (urun: MarketplaceUrunu) => {
    if (!confirm(t('marketplaceAdmin.silmeOnayi', { title: urun.title }))) return;
    try {
      await client.entities.marketplace_items.delete({ id: String(urun.id) });
      toast.success(t('marketplaceAdmin.silindi'));
      yukle();
    } catch {
      toast.error(t('marketplaceAdmin.silmeHatasi'));
    }
  };

  const alan = 'bg-white/5 border-white/10';
  const etiket = 'mb-2 block text-xs uppercase tracking-widest text-muted-foreground';

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">{t('marketplaceAdmin.aciklama')}</p>
        <Button
          onClick={() => duzenlemeyeBasla({ ...BOS })}
          className="bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0 h-11"
        >
          <Plus className="me-2 h-4 w-4" /> {t('marketplaceAdmin.yeni')}
        </Button>
      </div>

      {urunler === null && (
        <p className="flex items-center gap-2 py-12 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> {t('marketplaceAdmin.yukleniyor')}
        </p>
      )}

      {urunler !== null && urunler.length === 0 && (
        <p className="rounded-xl border border-white/10 bg-white/[0.03] px-6 py-10 text-center text-sm text-muted-foreground">
          {t('marketplaceAdmin.bos')}
        </p>
      )}

      {urunler !== null && urunler.length > 0 && (
        <div className="space-y-2">
          {urunler.map((urun) => {
            const yayinda = Boolean((urun as { published?: boolean }).published);
            return (
              <div
                key={urun.id}
                className="cam-kart flex flex-wrap items-center gap-3 rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold">{urun.title}</p>
                  <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                    {urun.category ? t(kategoriEtiketi(urun.category), urun.category) : '—'}
                    {urun.price ? ` · ${urun.price} ${urun.currency || ''}` : ''}
                    {urun.sort_order !== null && urun.sort_order !== undefined
                      ? ` · #${urun.sort_order}`
                      : ''}
                    {` · ${t('marketplaceCeviri.durum', 'çeviri {{sayi}}/{{toplam}}', {
                      sayi: ceviriliDilSayisi(urun),
                      toplam: CEVIRI_DILLERI.length,
                    })}`}
                  </p>
                </div>

                <span
                  className={`rounded-full px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider ${
                    yayinda
                      ? 'bg-primary/15 text-primary'
                      : 'bg-white/10 text-muted-foreground'
                  }`}
                >
                  {yayinda ? t('marketplaceAdmin.yayinda') : t('marketplaceAdmin.taslak')}
                </span>

                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => yayinDegistir(urun)}
                  aria-label={yayinda ? t('marketplaceAdmin.yayindanKaldir') : t('marketplaceAdmin.yayinla')}
                  className="!bg-transparent !hover:bg-transparent border-white/20"
                >
                  {yayinda ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => duzenlemeyeBasla({ ...urun })}
                  aria-label={t('marketplaceAdmin.duzenle')}
                  className="!bg-transparent !hover:bg-transparent border-white/20"
                >
                  <Pencil className="h-4 w-4" />
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => sil(urun)}
                  aria-label={t('marketplaceAdmin.sil')}
                  className="!bg-transparent !hover:bg-transparent border-white/20 text-red-300"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            );
          })}
        </div>
      )}

      {/* Ürün formu */}
      {duzenlenen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-background/80 p-4 backdrop-blur-sm">
          <div className="glass relative my-8 w-full max-w-2xl rounded-2xl border border-purple-500/30 p-8">
            <button
              className="absolute right-4 top-4 rounded-lg p-2 hover:bg-white/5"
              onClick={() => setDuzenlenen(null)}
              aria-label={t('marketplaceAdmin.kapat')}
            >
              <X className="h-4 w-4" />
            </button>
            <h3 className="mb-6 text-2xl font-bold">
              {duzenlenen.id ? t('marketplaceAdmin.duzenleBaslik') : t('marketplaceAdmin.yeniBaslik')}
            </h3>

            <div className="mb-5 flex flex-wrap items-center gap-1.5" role="group" aria-label={t('marketplaceCeviri.dilSecimi', 'Düzenlenen dil')}>
              {['tr', ...CEVIRI_DILLERI].map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => setFormDili(d)}
                  aria-pressed={formDili === d}
                  data-dil={d}
                  className={`rounded-md px-2.5 py-1 text-xs font-semibold uppercase ${
                    formDili === d
                      ? 'bg-primary text-background'
                      : 'border border-white/10 text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {d}
                </button>
              ))}
              {formDili !== 'tr' && (
                <span className="ms-2 text-[11px] text-muted-foreground">
                  {t('marketplaceCeviri.ipucu', 'Boş bırakılan alan sitede Türkçe görünür. Soluk yazı Türkçe değerdir.')}
                </span>
              )}
            </div>

            {formDili !== 'tr' ? (
              <div className="space-y-4" dir={formDili === 'ar' ? 'rtl' : undefined}>
                {CEVIRI_ALAN_SIRASI.map((a) => {
                  const deger = ceviriFormu[formDili]?.[a] ?? '';
                  const degistir = (yeni: string) =>
                    setCeviriFormu((onceki) => ({ ...onceki, [formDili]: { ...onceki[formDili], [a]: yeni } }));
                  return (
                    <div key={a}>
                      <Label className={etiket} htmlFor={`ceviri-${a}`}>
                        {t(CEVIRI_ALAN_ETIKETI[a])} ({formDili.toUpperCase()})
                      </Label>
                      {COK_SATIRLI.has(a) ? (
                        <Textarea
                          id={`ceviri-${a}`}
                          name={`ceviri-${a}`}
                          rows={a === 'features' ? 5 : a === 'description' ? 4 : 2}
                          className={`${alan} ${a === 'features' ? 'font-mono text-xs' : ''} placeholder:text-white/30`}
                          placeholder={duzenlenen[a] || ''}
                          value={deger}
                          onChange={(e) => degistir(e.target.value)}
                        />
                      ) : (
                        <Input
                          id={`ceviri-${a}`}
                          name={`ceviri-${a}`}
                          className={`${alan} placeholder:text-white/30`}
                          placeholder={duzenlenen[a] || ''}
                          value={deger}
                          onChange={(e) => degistir(e.target.value)}
                        />
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
            <div className="space-y-4">
              <div>
                <Label className={etiket}>{t('marketplaceAdmin.fBaslik')} *</Label>
                <Input
                  className={alan}
                  value={duzenlenen.title || ''}
                  onChange={(e) => setDuzenlenen({ ...duzenlenen, title: e.target.value })}
                />
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <Label className={etiket}>{t('marketplaceAdmin.fKategori')}</Label>
                  <select
                    value={duzenlenen.category || 'website'}
                    onChange={(e) => setDuzenlenen({ ...duzenlenen, category: e.target.value })}
                    className="h-10 w-full rounded-md border border-white/10 bg-white/5 px-3 text-sm"
                  >
                    {KATEGORILER.map((k) => (
                      <option key={k} value={k} className="bg-background">
                        {t(kategoriEtiketi(k))}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <Label className={etiket}>{t('marketplaceAdmin.fSira')}</Label>
                  <Input
                    className={alan}
                    type="number"
                    value={duzenlenen.sort_order ?? ''}
                    onChange={(e) =>
                      setDuzenlenen({
                        ...duzenlenen,
                        sort_order: e.target.value === '' ? undefined : Number(e.target.value),
                      })
                    }
                  />
                </div>
              </div>

              <div>
                <Label className={etiket}>{t('marketplaceAdmin.fOzet')}</Label>
                <Textarea
                  rows={2}
                  className={alan}
                  value={duzenlenen.summary || ''}
                  onChange={(e) => setDuzenlenen({ ...duzenlenen, summary: e.target.value })}
                />
              </div>

              <div>
                <Label className={etiket}>{t('marketplaceAdmin.fOzellikler')}</Label>
                <Textarea
                  rows={5}
                  className={`${alan} font-mono text-xs`}
                  placeholder={t('marketplaceAdmin.fOzelliklerIpucu')}
                  value={duzenlenen.features || ''}
                  onChange={(e) => setDuzenlenen({ ...duzenlenen, features: e.target.value })}
                />
              </div>

              <div className="grid gap-4 sm:grid-cols-3">
                <div>
                  <Label className={etiket}>{t('marketplaceAdmin.fFiyat')}</Label>
                  <Input
                    className={alan}
                    placeholder={t('marketplaceAdmin.fFiyatIpucu')}
                    value={duzenlenen.price || ''}
                    onChange={(e) => setDuzenlenen({ ...duzenlenen, price: e.target.value })}
                  />
                </div>
                <div>
                  <Label className={etiket}>{t('marketplaceAdmin.fParaBirimi')}</Label>
                  <select
                    value={duzenlenen.currency || 'USD'}
                    onChange={(e) => setDuzenlenen({ ...duzenlenen, currency: e.target.value })}
                    className="h-10 w-full rounded-md border border-white/10 bg-white/5 px-3 text-sm"
                  >
                    {['USD', 'EUR', 'TRY'].map((p) => (
                      <option key={p} value={p} className="bg-background">
                        {p}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <Label className={etiket}>{t('marketplaceAdmin.fFiyatNotu')}</Label>
                  <Input
                    className={alan}
                    placeholder={t('marketplaceAdmin.fFiyatNotuIpucu')}
                    value={duzenlenen.price_note || ''}
                    onChange={(e) => setDuzenlenen({ ...duzenlenen, price_note: e.target.value })}
                  />
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <Label className={etiket}>{t('marketplaceAdmin.fTeslim')}</Label>
                  <Input
                    className={alan}
                    placeholder={t('marketplaceAdmin.fTeslimIpucu')}
                    value={duzenlenen.delivery_time || ''}
                    onChange={(e) =>
                      setDuzenlenen({ ...duzenlenen, delivery_time: e.target.value })
                    }
                  />
                </div>
                <div>
                  <Label className={etiket}>{t('marketplaceAdmin.fRozet')}</Label>
                  <Input
                    className={alan}
                    placeholder={t('marketplaceAdmin.fRozetIpucu')}
                    value={duzenlenen.badge || ''}
                    onChange={(e) => setDuzenlenen({ ...duzenlenen, badge: e.target.value })}
                  />
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <Label className={etiket}>{t('marketplaceAdmin.fGorsel')}</Label>
                  <Input
                    className={alan}
                    placeholder="/assets/... veya https://..."
                    value={duzenlenen.image_url || ''}
                    onChange={(e) => setDuzenlenen({ ...duzenlenen, image_url: e.target.value })}
                  />
                </div>
                <div>
                  <Label className={etiket}>{t('marketplaceAdmin.fDemo')}</Label>
                  <Input
                    className={alan}
                    placeholder="https://..."
                    value={duzenlenen.demo_url || ''}
                    onChange={(e) => setDuzenlenen({ ...duzenlenen, demo_url: e.target.value })}
                  />
                </div>
              </div>

              <div>
                <Label className={etiket}>{t('marketplaceAdmin.fAciklama')}</Label>
                <Textarea
                  rows={4}
                  className={alan}
                  value={duzenlenen.description || ''}
                  onChange={(e) => setDuzenlenen({ ...duzenlenen, description: e.target.value })}
                />
              </div>

              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={Boolean(duzenlenen.published)}
                  onChange={(e) => setDuzenlenen({ ...duzenlenen, published: e.target.checked })}
                  className="h-4 w-4 accent-primary"
                />
                {t('marketplaceAdmin.fYayinda')}
              </label>
            </div>
            )}

            <div className="mt-6 flex gap-3">
              <Button
                onClick={kaydet}
                disabled={kaydediliyor}
                className="h-11 flex-1 border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white"
              >
                {kaydediliyor && <Loader2 className="me-2 h-4 w-4 animate-spin" />}
                {t('marketplaceAdmin.kaydet')}
              </Button>
              <Button
                variant="outline"
                onClick={() => setDuzenlenen(null)}
                className="h-11 border-white/20 !bg-transparent !hover:bg-transparent"
              >
                {t('marketplaceAdmin.vazgec')}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
