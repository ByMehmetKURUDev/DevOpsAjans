import { useCallback, useEffect, useState } from 'react';
import { BookOpen, Eye, Loader2, Pencil, Plus, Save, Trash2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  DestekHatasi,
  makaleEkle,
  makaleGuncelle,
  makaleOnizle,
  makaleSil,
  yonetimMakaleleri,
  type MakaleGirdisi,
  type YonetimMakalesi,
} from '@/lib/destek';

/**
 * Yönetici paneli › Bilgi bankası (Faz 2C).
 *
 * Makale: kategori, başlık, markdown içerik (Türkçe ana metin) + 6 dilde
 * çeviri, taslak/yayında. Önizleme sunucuda (markdown → güvenli HTML) —
 * müşterinin göreceği HTML'in aynısı.
 */

const KART = 'cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6';
const DILLER = ['tr', 'en', 'de', 'ru', 'zh', 'hi', 'ar'] as const;
type Dil = (typeof DILLER)[number];

const BOS: MakaleGirdisi = { kategori: '', baslik: '', icerik: '', ceviriler: {}, durum: 'taslak' };

export default function BilgiBankasiYonetimi() {
  const { t } = useTranslation();
  const [liste, setListe] = useState<YonetimMakalesi[]>([]);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [duzenlenen, setDuzenlenen] = useState<{ id: number | null; veri: MakaleGirdisi } | null>(null);
  const [dil, setDil] = useState<Dil>('tr');
  const [onizleme, setOnizleme] = useState<string | null>(null);
  const [kaydediliyor, setKaydediliyor] = useState(false);

  const hata = useCallback(
    (h: unknown) => toast.error(t(`yardim.hata.${h instanceof DestekHatasi ? h.kod : 'genel'}`, { defaultValue: t('yardim.hata.genel') })),
    [t]
  );

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    try {
      setListe(await yonetimMakaleleri());
    } catch (h) {
      hata(h);
    } finally {
      setYukleniyor(false);
    }
  }, [hata]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const alan = (ad: 'baslik' | 'icerik'): string => {
    if (!duzenlenen) return '';
    if (dil === 'tr') return duzenlenen.veri[ad];
    return duzenlenen.veri.ceviriler[dil]?.[ad] ?? '';
  };

  const alanYaz = (ad: 'baslik' | 'icerik', deger: string) => {
    if (!duzenlenen) return;
    if (dil === 'tr') {
      setDuzenlenen({ ...duzenlenen, veri: { ...duzenlenen.veri, [ad]: deger } });
      return;
    }
    const onceki = duzenlenen.veri.ceviriler[dil] ?? { baslik: '', icerik: '' };
    setDuzenlenen({
      ...duzenlenen,
      veri: { ...duzenlenen.veri, ceviriler: { ...duzenlenen.veri.ceviriler, [dil]: { ...onceki, [ad]: deger } } },
    });
  };

  const kaydet = async () => {
    if (!duzenlenen || !duzenlenen.veri.baslik.trim()) {
      toast.error(t('yardim.kb.baslikGerekli'));
      return;
    }
    setKaydediliyor(true);
    try {
      if (duzenlenen.id) await makaleGuncelle(duzenlenen.id, duzenlenen.veri);
      else await makaleEkle(duzenlenen.veri);
      toast.success(t('yardim.kb.kaydedildi'));
      setDuzenlenen(null);
      setOnizleme(null);
      await yukle();
    } catch (h) {
      hata(h);
    } finally {
      setKaydediliyor(false);
    }
  };

  const onizle = async () => {
    try {
      setOnizleme((await makaleOnizle(alan('icerik'))).html);
    } catch (h) {
      hata(h);
    }
  };

  return (
    <div className="space-y-6" data-testid="bilgi-bankasi-yonetimi">
      <div className={KART}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-xl font-semibold">
              <BookOpen className="h-5 w-5 text-purple-300" aria-hidden="true" /> {t('yardim.kb.yonetimBaslik')}
            </h2>
            <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{t('yardim.kb.yonetimAciklama')}</p>
          </div>
          <Button
            className="gap-2"
            onClick={() => {
              setDuzenlenen({ id: null, veri: { ...BOS, ceviriler: {} } });
              setDil('tr');
              setOnizleme(null);
            }}
            data-testid="kb-yeni"
          >
            <Plus className="h-4 w-4" /> {t('yardim.kb.yeni')}
          </Button>
        </div>
      </div>

      {duzenlenen && (
        <div className={KART} data-testid="kb-duzenleyici">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-semibold">{duzenlenen.id ? t('yardim.kb.duzenle') : t('yardim.kb.yeni')}</h3>
            <Button size="sm" variant="ghost" onClick={() => setDuzenlenen(null)} aria-label={t('yardim.vazgec')}>
              <X className="h-4 w-4" />
            </Button>
          </div>
          <div className="grid gap-3 md:grid-cols-[1fr_180px]">
            <Input
              value={duzenlenen.veri.kategori ?? ''}
              onChange={(e) => setDuzenlenen({ ...duzenlenen, veri: { ...duzenlenen.veri, kategori: e.target.value } })}
              placeholder={t('yardim.kb.kategori')}
              aria-label={t('yardim.kb.kategori')}
              className="bg-white/5"
              data-testid="kb-kategori"
            />
            <select
              value={duzenlenen.veri.durum}
              onChange={(e) =>
                setDuzenlenen({ ...duzenlenen, veri: { ...duzenlenen.veri, durum: e.target.value as 'taslak' | 'yayinda' } })
              }
              className="h-10 rounded-md border border-white/10 bg-white/5 px-3 text-sm"
              aria-label={t('yardim.kb.durum')}
              data-testid="kb-durum"
            >
              <option value="taslak">{t('yardim.kb.taslak')}</option>
              <option value="yayinda">{t('yardim.kb.yayinda')}</option>
            </select>
          </div>
          <div className="mt-4 flex flex-wrap gap-1" role="tablist" aria-label={t('yardim.kb.dil')}>
            {DILLER.map((d) => {
              const dolu = d === 'tr' ? !!duzenlenen.veri.baslik : !!duzenlenen.veri.ceviriler[d]?.baslik;
              return (
                <button
                  key={d}
                  type="button"
                  role="tab"
                  aria-selected={dil === d}
                  onClick={() => {
                    setDil(d);
                    setOnizleme(null);
                  }}
                  className={`rounded-md px-3 py-1 text-xs uppercase ${
                    dil === d ? 'bg-purple-500/25 text-white' : 'text-muted-foreground hover:bg-white/5'
                  }`}
                >
                  {d}
                  {dolu ? ' ✓' : ''}
                </button>
              );
            })}
          </div>
          <div className="mt-3 space-y-3">
            <Input
              value={alan('baslik')}
              onChange={(e) => alanYaz('baslik', e.target.value)}
              placeholder={t('yardim.kb.makaleBasligi')}
              aria-label={t('yardim.kb.makaleBasligi')}
              className="bg-white/5"
              dir={dil === 'ar' ? 'rtl' : undefined}
              data-testid="kb-baslik"
            />
            <Textarea
              value={alan('icerik')}
              onChange={(e) => alanYaz('icerik', e.target.value)}
              placeholder={t('yardim.kb.icerikYer')}
              rows={10}
              className="bg-white/5 font-mono text-sm"
              dir={dil === 'ar' ? 'rtl' : undefined}
              data-testid="kb-icerik"
            />
            {dil !== 'tr' && <p className="text-xs text-muted-foreground">{t('yardim.kb.ceviriIpucu')}</p>}
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => void kaydet()} disabled={kaydediliyor} className="gap-2" data-testid="kb-kaydet">
                {kaydediliyor ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                {t('yardim.kaydet')}
              </Button>
              <Button variant="outline" className="gap-2 !bg-transparent" onClick={() => void onizle()}>
                <Eye className="h-4 w-4" /> {t('yardim.kb.onizle')}
              </Button>
            </div>
            {onizleme !== null && (
              <div
                className="prose prose-invert text-sm max-w-none rounded-xl border border-white/10 bg-white/[0.02] p-4 text-sm leading-relaxed"
                dir={dil === 'ar' ? 'rtl' : undefined}
                // Sunucu izinli etiket listesiyle temizledi (services/guvenli_html.py).
                dangerouslySetInnerHTML={{ __html: onizleme }}
              />
            )}
          </div>
        </div>
      )}

      <div className={KART}>
        {yukleniyor ? (
          <div className="flex justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : liste.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('yardim.kb.bos')}</p>
        ) : (
          <ul className="divide-y divide-white/5">
            {liste.map((m) => (
              <li key={m.id} className="flex flex-wrap items-center gap-3 py-3 text-sm" data-testid={`kb-makale-${m.id}`}>
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{m.baslik}</p>
                  <p className="text-xs text-muted-foreground">
                    {m.kategori || t('yardim.kb.kategorisiz')} · {t('yardim.kb.goruntulenme', { sayi: m.goruntulenme })} ·{' '}
                    {t('yardim.kb.ceviriSayisi', { sayi: Object.keys(m.ceviriler).length })}
                  </p>
                </div>
                <span
                  className={`rounded-full px-2 py-0.5 text-[11px] ${
                    m.durum === 'yayinda' ? 'bg-emerald-500/15 text-emerald-200' : 'bg-white/10 text-muted-foreground'
                  }`}
                >
                  {t(`yardim.kb.${m.durum}`)}
                </span>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setDuzenlenen({
                      id: m.id,
                      veri: { kategori: m.kategori ?? '', baslik: m.baslik, icerik: m.icerik, ceviriler: { ...m.ceviriler }, durum: m.durum },
                    });
                    setDil('tr');
                    setOnizleme(null);
                  }}
                  aria-label={t('yardim.duzenle')}
                >
                  <Pencil className="h-4 w-4" />
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-destructive hover:text-destructive"
                  onClick={() => {
                    if (!window.confirm(t('yardim.kb.silOnay'))) return;
                    void makaleSil(m.id).then(yukle).catch(hata);
                  }}
                  aria-label={t('yardim.sil')}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
