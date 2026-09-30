import { useEffect, useState } from 'react';
import { Eye, EyeOff, Loader2, Pencil, Plus, Trash2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { client } from '@/lib/sdkClient';
import { KATEGORILER, kategoriEtiketi, type MarketplaceUrunu } from '@/lib/marketplace';

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
    const payload = {
      ...duzenlenen,
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
          onClick={() => setDuzenlenen({ ...BOS })}
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
                className="flex flex-wrap items-center gap-3 rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold">{urun.title}</p>
                  <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                    {urun.category ? t(kategoriEtiketi(urun.category), urun.category) : '—'}
                    {urun.price ? ` · ${urun.price} ${urun.currency || ''}` : ''}
                    {urun.sort_order !== null && urun.sort_order !== undefined
                      ? ` · #${urun.sort_order}`
                      : ''}
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
                  onClick={() => setDuzenlenen({ ...urun })}
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
