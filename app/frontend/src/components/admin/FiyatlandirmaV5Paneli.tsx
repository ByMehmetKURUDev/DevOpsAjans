import { useCallback, useEffect, useMemo, useState } from 'react';
import { Loader2, Pencil, Plus, RefreshCw, Trash2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { fiyatlandirmaAdminApi, type FiyatV5Satir } from '@/api/fiyatlandirmaAdmin';

/**
 * Fiyatlandırma v5 admin sekmesi.
 *
 * Diğer admin alt panelleri gibi (bkz. `MusteriRaporlari`, `OdemePaneli`)
 * kendi verisini kendisi çekiyor, `AdminPanel.tsx`'in açılış toplu isteğine
 * eklenmiyor.
 *
 * 6 tablo tek bileşende: her biri için ayrı ~300 satırlık form yazmak
 * yerine (bu dosyanın diğerlerinden farkı) alan listesi veriye göre
 * tanımlanıyor, form o listeden üretiliyor. `pricing_inquiries` ("Teklif
 * Al" ile gelen talepler) düzenlenmiyor, yalnızca görüntülenip
 * silinebiliyor — kayıt zaten `/fiyat-teklif`'ten otomatik oluşuyor.
 */

type AlanTipi = 'text' | 'textarea' | 'number' | 'boolean' | 'json';

interface AlanTanimi {
  key: string;
  label: string;
  tip: AlanTipi;
  zorunlu?: boolean;
}

interface TabloTanimi {
  tablo: string;
  baslik: string;
  alanlar: AlanTanimi[];
  /** true ise yalnızca görüntüleme + silme; düzenleme formu gösterilmiyor. */
  saltOkunur?: boolean;
}

const TABLOLAR: TabloTanimi[] = [
  {
    tablo: 'pricing_scales',
    baslik: 'Ölçekler (ALFA/BETA/OMEGA/SIGMA)',
    alanlar: [
      { key: 'kod', label: 'Kod', tip: 'text', zorunlu: true },
      { key: 'sira', label: 'Sıra', tip: 'number', zorunlu: true },
      { key: 'ad', label: 'Ad', tip: 'text', zorunlu: true },
      { key: 'alt_baslik', label: 'Alt başlık', tip: 'text', zorunlu: true },
      { key: 'calisan_araligi', label: 'Çalışan aralığı', tip: 'text', zorunlu: true },
      { key: 'aciklama', label: 'Açıklama', tip: 'textarea', zorunlu: true },
      { key: 'baz_aylik_fiyat_usd', label: 'Baz aylık fiyat (USD)', tip: 'number', zorunlu: true },
      { key: 'ozellikler', label: 'Özellikler (JSON dizi)', tip: 'json' },
      { key: 'eklenti_limiti', label: 'Eklenti limiti', tip: 'text' },
      { key: 'revizyon_saat', label: 'Revizyon saati', tip: 'text' },
      { key: 'populer', label: 'Popüler rozeti', tip: 'boolean' },
      { key: 'karsilastirma', label: 'Karşılaştırma (JSON obje)', tip: 'json' },
    ],
  },
  {
    tablo: 'pricing_profiles',
    baslik: 'Profiller (kurumsal/startup/stk/bireysel/eğitim)',
    alanlar: [
      { key: 'kod', label: 'Kod', tip: 'text', zorunlu: true },
      { key: 'ad', label: 'Ad', tip: 'text', zorunlu: true },
      { key: 'carpan', label: 'Çarpan', tip: 'number', zorunlu: true },
      { key: 'etiket', label: 'Etiket', tip: 'text' },
      { key: 'sira', label: 'Sıra', tip: 'number', zorunlu: true },
    ],
  },
  {
    tablo: 'pricing_services',
    baslik: 'À la carte hizmetler',
    alanlar: [
      { key: 'kategori', label: 'Kategori', tip: 'text', zorunlu: true },
      { key: 'ad', label: 'Ad', tip: 'text', zorunlu: true },
      { key: 'baz_fiyat_usd', label: 'Baz fiyat (USD)', tip: 'number', zorunlu: true },
      { key: 'tek_seferlik', label: 'Tek seferlik', tip: 'boolean' },
      { key: 'not_metni', label: 'Not', tip: 'text' },
      { key: 'yeni', label: 'Yeni rozeti', tip: 'boolean' },
    ],
  },
  {
    tablo: 'pricing_addons',
    baslik: 'Ölçek eklentileri',
    alanlar: [
      { key: 'scale_kod', label: 'Ölçek kodu (ALFA/BETA/OMEGA/SIGMA)', tip: 'text', zorunlu: true },
      { key: 'ad', label: 'Ad', tip: 'text', zorunlu: true },
      { key: 'baz_fiyat_usd', label: 'Baz fiyat (USD)', tip: 'number', zorunlu: true },
      { key: 'birim', label: 'Birim', tip: 'text' },
      { key: 'sira', label: 'Sıra', tip: 'number', zorunlu: true },
    ],
  },
  {
    tablo: 'ai_pm_tiers',
    baslik: 'AI vs PM katmanları',
    alanlar: [
      { key: 'kod', label: 'Kod', tip: 'text', zorunlu: true },
      { key: 'ad', label: 'Ad', tip: 'text', zorunlu: true },
      { key: 'fiyat_aylik_usd', label: 'Aylık fiyat (USD)', tip: 'number', zorunlu: true },
      { key: 'rozet', label: 'Rozet', tip: 'text' },
      { key: 'ozellikler', label: 'Özellikler (JSON dizi)', tip: 'json' },
      { key: 'sira', label: 'Sıra', tip: 'number', zorunlu: true },
    ],
  },
  {
    tablo: 'pricing_inquiries',
    baslik: 'Teklif talepleri (leads)',
    saltOkunur: true,
    alanlar: [
      { key: 'scale_kod', label: 'Ölçek', tip: 'text' },
      { key: 'profile_kod', label: 'Profil', tip: 'text' },
      { key: 'ai_pm_tier_kod', label: 'AI/PM katmanı', tip: 'text' },
      { key: 'period', label: 'Periyot', tip: 'text' },
      { key: 'hesaplanan_tutar', label: 'Tutar (USD)', tip: 'number' },
      { key: 'musteri_adi', label: 'Müşteri', tip: 'text' },
      { key: 'musteri_eposta', label: 'E-posta', tip: 'text' },
      { key: 'kaynak', label: 'Kaynak', tip: 'text' },
      { key: 'invoice_id', label: 'Fatura ID', tip: 'number' },
    ],
  },
];

function bosForm(tanim: TabloTanimi): Record<string, string> {
  const form: Record<string, string> = {};
  for (const a of tanim.alanlar) {
    if (a.tip === 'boolean') continue; // checkbox ayrı state'te
    form[a.key] = '';
  }
  return form;
}

function satirdanForm(satir: FiyatV5Satir, tanim: TabloTanimi): { form: Record<string, string>; bool: Record<string, boolean> } {
  const form: Record<string, string> = {};
  const bool: Record<string, boolean> = {};
  for (const a of tanim.alanlar) {
    const deger = satir[a.key];
    if (a.tip === 'boolean') {
      bool[a.key] = Boolean(deger);
    } else if (a.tip === 'json') {
      form[a.key] = deger != null ? JSON.stringify(deger, null, 2) : '';
    } else {
      form[a.key] = deger != null ? String(deger) : '';
    }
  }
  return { form, bool };
}

export default function FiyatlandirmaV5Paneli() {
  const { t } = useTranslation();
  const [aktifTablo, setAktifTablo] = useState(TABLOLAR[0].tablo);
  const tanim = useMemo(() => TABLOLAR.find((x) => x.tablo === aktifTablo)!, [aktifTablo]);

  const [satirlar, setSatirlar] = useState<FiyatV5Satir[]>([]);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [duzenlenen, setDuzenlenen] = useState<FiyatV5Satir | 'yeni' | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [boolAlanlar, setBoolAlanlar] = useState<Record<string, boolean>>({});
  const [kaydediliyor, setKaydediliyor] = useState(false);
  const [silinen, setSilinen] = useState<number | null>(null);

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    try {
      const veri = await fiyatlandirmaAdminApi.list(aktifTablo);
      setSatirlar(veri);
    } catch (e) {
      toast.error((e as Error)?.message || t('fiyatV5Admin.yuklenemedi', 'Liste yüklenemedi.'));
    } finally {
      setYukleniyor(false);
    }
  }, [aktifTablo, t]);

  useEffect(() => {
    setDuzenlenen(null);
    void yukle();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aktifTablo]);

  const duzenlemeyeBasla = (satir: FiyatV5Satir | 'yeni') => {
    if (satir === 'yeni') {
      setForm(bosForm(tanim));
      setBoolAlanlar({});
    } else {
      const { form: f, bool } = satirdanForm(satir, tanim);
      setForm(f);
      setBoolAlanlar(bool);
    }
    setDuzenlenen(satir);
  };

  const kaydet = async () => {
    const payload: Record<string, unknown> = {};
    for (const a of tanim.alanlar) {
      if (a.tip === 'boolean') {
        payload[a.key] = boolAlanlar[a.key] ?? false;
        continue;
      }
      const ham = form[a.key] ?? '';
      if (a.tip === 'number') {
        if (ham.trim() === '') {
          if (a.zorunlu) {
            toast.error(t('fiyatV5Admin.alanGerekli', '"{{alan}}" alanı gerekli.', { alan: a.label }));
            return;
          }
          continue;
        }
        const sayi = Number(ham);
        if (Number.isNaN(sayi)) {
          toast.error(t('fiyatV5Admin.gecersizSayi', '"{{alan}}" geçerli bir sayı olmalı.', { alan: a.label }));
          return;
        }
        payload[a.key] = sayi;
      } else if (a.tip === 'json') {
        if (ham.trim() === '') {
          payload[a.key] = null;
          continue;
        }
        try {
          payload[a.key] = JSON.parse(ham);
        } catch {
          toast.error(t('fiyatV5Admin.gecersizJson', '"{{alan}}" geçerli bir JSON olmalı.', { alan: a.label }));
          return;
        }
      } else {
        if (a.zorunlu && !ham.trim()) {
          toast.error(t('fiyatV5Admin.alanGerekli', '"{{alan}}" alanı gerekli.', { alan: a.label }));
          return;
        }
        payload[a.key] = ham;
      }
    }

    setKaydediliyor(true);
    try {
      if (duzenlenen === 'yeni') {
        await fiyatlandirmaAdminApi.create(aktifTablo, payload);
        toast.success(t('fiyatV5Admin.eklendi', 'Kayıt eklendi.'));
      } else if (duzenlenen) {
        await fiyatlandirmaAdminApi.update(aktifTablo, duzenlenen.id, payload);
        toast.success(t('fiyatV5Admin.guncellendi', 'Kayıt güncellendi.'));
      }
      setDuzenlenen(null);
      await yukle();
    } catch (e) {
      toast.error((e as Error)?.message || t('fiyatV5Admin.kaydedilemedi', 'Kaydedilemedi.'));
    } finally {
      setKaydediliyor(false);
    }
  };

  const sil = async (id: number) => {
    if (!window.confirm(t('fiyatV5Admin.silOnay', 'Bu kayıt silinsin mi?'))) return;
    setSilinen(id);
    try {
      await fiyatlandirmaAdminApi.remove(aktifTablo, id);
      toast.success(t('fiyatV5Admin.silindi', 'Kayıt silindi.'));
      await yukle();
    } catch (e) {
      toast.error((e as Error)?.message || t('fiyatV5Admin.silinemedi', 'Silinemedi.'));
    } finally {
      setSilinen(null);
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-1.5">
          {TABLOLAR.map((x) => (
            <button
              key={x.tablo}
              type="button"
              onClick={() => setAktifTablo(x.tablo)}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
                aktifTablo === x.tablo
                  ? 'bg-gradient-to-r from-purple-600 to-pink-600 text-white'
                  : 'border border-white/10 text-muted-foreground hover:text-white'
              }`}
            >
              {x.baslik}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" className="gap-2" onClick={() => void yukle()}>
            <RefreshCw className={`h-4 w-4 ${yukleniyor ? 'animate-spin' : ''}`} aria-hidden="true" />
            {t('odeme.yenile', 'Yenile')}
          </Button>
          {!tanim.saltOkunur && (
            <Button size="sm" className="gap-2" onClick={() => duzenlemeyeBasla('yeni')}>
              <Plus className="h-4 w-4" aria-hidden="true" />
              {t('fiyatV5Admin.yeniEkle', 'Yeni ekle')}
            </Button>
          )}
        </div>
      </div>

      {duzenlenen && (
        <div className="rounded-xl glass p-4">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-sm font-semibold">
              {duzenlenen === 'yeni'
                ? t('fiyatV5Admin.yeniKayit', 'Yeni kayıt — {{tablo}}', { tablo: tanim.baslik })
                : t('fiyatV5Admin.kayitDuzenle', 'Kayıt düzenle — {{tablo}}', { tablo: tanim.baslik })}
            </p>
            <button
              type="button"
              onClick={() => setDuzenlenen(null)}
              className="text-muted-foreground hover:text-foreground"
              aria-label={t('genel.kapat', 'Kapat')}
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {tanim.alanlar.map((a) => (
              <div key={a.key} className={a.tip === 'json' || a.tip === 'textarea' ? 'sm:col-span-2' : ''}>
                <Label className="mb-1 block text-xs text-muted-foreground">
                  {a.label}
                  {a.zorunlu ? ' *' : ''}
                </Label>
                {a.tip === 'boolean' ? (
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={boolAlanlar[a.key] ?? false}
                      onChange={(o) => setBoolAlanlar((p) => ({ ...p, [a.key]: o.target.checked }))}
                      className="h-4 w-4 rounded border-white/30 bg-transparent accent-purple-500"
                    />
                    {a.label}
                  </label>
                ) : a.tip === 'textarea' || a.tip === 'json' ? (
                  <textarea
                    value={form[a.key] ?? ''}
                    onChange={(o) => setForm((p) => ({ ...p, [a.key]: o.target.value }))}
                    rows={a.tip === 'json' ? 5 : 3}
                    className="w-full resize-y rounded-lg border border-white/10 bg-black/40 px-3 py-2 font-mono text-xs text-white focus:border-primary focus:outline-none"
                  />
                ) : (
                  <Input
                    type={a.tip === 'number' ? 'number' : 'text'}
                    value={form[a.key] ?? ''}
                    onChange={(o) => setForm((p) => ({ ...p, [a.key]: o.target.value }))}
                  />
                )}
              </div>
            ))}
          </div>
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="outline" onClick={() => setDuzenlenen(null)}>
              {t('genel.iptal', 'İptal')}
            </Button>
            <Button onClick={() => void kaydet()} disabled={kaydediliyor} className="gap-2">
              {kaydediliyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}
              {t('genel.kaydet', 'Kaydet')}
            </Button>
          </div>
        </div>
      )}

      {yukleniyor ? (
        <div className="flex justify-center py-8">
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" aria-hidden="true" />
        </div>
      ) : satirlar.length === 0 ? (
        <div className="rounded-xl glass p-8 text-center text-sm text-muted-foreground">
          {t('fiyatV5Admin.bosListe', 'Kayıt yok.')}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl glass">
          <table className="w-full min-w-[720px] border-collapse text-sm">
            <thead>
              <tr>
                {tanim.alanlar
                  .filter((a) => a.tip !== 'json' && a.tip !== 'textarea')
                  .map((a) => (
                    <th
                      key={a.key}
                      className="border-b border-white/10 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground"
                    >
                      {a.label}
                    </th>
                  ))}
                <th className="border-b border-white/10 px-3 py-2 text-right text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {t('fiyatV5Admin.islemler', 'İşlemler')}
                </th>
              </tr>
            </thead>
            <tbody>
              {satirlar.map((satir) => (
                <tr key={satir.id} className="border-b border-white/5 hover:bg-white/[0.02]">
                  {tanim.alanlar
                    .filter((a) => a.tip !== 'json' && a.tip !== 'textarea')
                    .map((a) => (
                      <td key={a.key} className="px-3 py-2">
                        {a.tip === 'boolean' ? (satir[a.key] ? '✓' : '—') : String(satir[a.key] ?? '—')}
                      </td>
                    ))}
                  <td className="px-3 py-2 text-right">
                    <div className="flex justify-end gap-1">
                      {!tanim.saltOkunur && (
                        <button
                          type="button"
                          onClick={() => duzenlemeyeBasla(satir)}
                          className="rounded-lg p-1.5 text-muted-foreground hover:bg-white/10 hover:text-white"
                          aria-label={t('genel.duzenle', 'Düzenle')}
                        >
                          <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => void sil(satir.id)}
                        disabled={silinen === satir.id}
                        className="rounded-lg p-1.5 text-muted-foreground hover:bg-red-500/10 hover:text-red-300"
                        aria-label={t('genel.sil', 'Sil')}
                      >
                        {silinen === satir.id ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                        ) : (
                          <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                        )}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
