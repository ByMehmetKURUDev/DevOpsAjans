import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { ChevronDown, ChevronRight, Filter, Loader2, RefreshCw, RotateCcw, Save, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { goreliZaman, tamZaman } from '@/lib/denetim';
import {
  copAyrintisi,
  copHataMetni,
  copGeriAl,
  copKaliciSil,
  copListesi,
  copSaklamaAyari,
  type CopSatiri,
} from '@/lib/copKutusu';

/**
 * Yönetici paneli › Çöp kutusu.
 *
 * Silinen proje, görev, dosya, destek talebi, fatura, blog yazısı… saklama
 * süresi (varsayılan 30 gün) boyunca burada. "Geri al" kaydı aynı
 * numarasıyla yerine koyar; birlikte silinen bağlı kayıtlar (görevin kontrol
 * listesi gibi) da döner. "Kalıcı sil" geri alınamaz (dosyada içerik de gider).
 */

const ADET = 50;
const SECIM_SINIFI =
  'mt-1 h-10 w-full rounded-md border border-white/10 bg-white/5 px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-purple-500/40';

function Deger({ deger }: { deger: unknown }) {
  if (deger === null || deger === undefined || deger === '') return <span className="text-muted-foreground">—</span>;
  const metin = typeof deger === 'object' ? JSON.stringify(deger) : String(deger);
  return <span className="break-all">{metin.length > 300 ? `${metin.slice(0, 299)}…` : metin}</span>;
}

function Ayrinti({ id }: { id: number }) {
  const { t } = useTranslation();
  const [veri, setVeri] = useState<Record<string, unknown> | null>(null);
  const [hata, setHata] = useState(false);
  useEffect(() => {
    let iptal = false;
    copAyrintisi(id)
      .then((g) => !iptal && setVeri(g.veri ?? {}))
      .catch(() => !iptal && setHata(true));
    return () => {
      iptal = true;
    };
  }, [id]);
  if (hata) return <p className="text-xs text-red-300">{t('copKutusu.hata')}</p>;
  if (!veri)
    return (
      <div className="flex py-2 text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
      </div>
    );
  return (
    <dl className="grid gap-x-4 gap-y-1 text-xs sm:grid-cols-[minmax(8rem,auto)_1fr]">
      {Object.entries(veri).map(([alan, deger]) => (
        <div key={alan} className="contents">
          <dt className="font-mono text-[11px] text-muted-foreground">{alan}</dt>
          <dd className="text-foreground/85">
            <Deger deger={deger} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

export default function CopKutusu() {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [satirlar, setSatirlar] = useState<CopSatiri[]>([]);
  const [toplam, setToplam] = useState(0);
  const [sayfa, setSayfa] = useState(1);
  const [tablolar, setTablolar] = useState<string[]>([]);
  const [saklamaGun, setSaklamaGun] = useState(30);
  const [gunGirdisi, setGunGirdisi] = useState('30');
  const [yukleniyor, setYukleniyor] = useState(true);
  const [hata, setHata] = useState(false);
  const [tablo, setTablo] = useState('');
  const [arama, setArama] = useState('');
  const [filtre, setFiltre] = useState<{ tablo: string; q: string }>({ tablo: '', q: '' });
  const [acik, setAcik] = useState<number | null>(null);
  const [calisan, setCalisan] = useState<string | null>(null);

  const tabloAdi = (ad: string) => t(`copKutusu.tablo.${ad}`, { defaultValue: ad });
  const rolAdi = (rol?: string | null) => t(`copKutusu.rol.${rol || 'sistem'}`, { defaultValue: rol || '' });

  const yukle = useCallback(
    async (hangiSayfa = 1) => {
      setYukleniyor(true);
      setHata(false);
      try {
        const g = await copListesi(filtre, hangiSayfa, ADET);
        setSatirlar((onceki) => (hangiSayfa === 1 ? g.items : [...onceki, ...g.items]));
        setToplam(g.toplam);
        setSayfa(hangiSayfa);
        setTablolar(g.tablolar);
        setSaklamaGun(g.saklama_gun);
        setGunGirdisi(String(g.saklama_gun));
      } catch {
        setHata(true);
      } finally {
        setYukleniyor(false);
      }
    },
    [filtre]
  );

  useEffect(() => {
    void yukle(1);
  }, [yukle]);

  const filtrele = (e: FormEvent) => {
    e.preventDefault();
    setFiltre({ tablo, q: arama.trim() });
  };

  const geriAl = async (s: CopSatiri) => {
    if (!window.confirm(t('copKutusu.geriAlOnay', { kayit: s.etiket || `#${s.kayit_id}` }))) return;
    setCalisan(`geri-${s.id}`);
    try {
      await copGeriAl(s.id);
      toast.success(t('copKutusu.geriAlindi'));
      await yukle(1);
    } catch (h) {
      toast.error(copHataMetni(t, h));
    } finally {
      setCalisan(null);
    }
  };

  const kaliciSil = async (s: CopSatiri) => {
    if (!window.confirm(t('copKutusu.kaliciSilOnay', { kayit: s.etiket || `#${s.kayit_id}` }))) return;
    setCalisan(`sil-${s.id}`);
    try {
      await copKaliciSil(s.id);
      toast.success(t('copKutusu.kaliciSilindi'));
      await yukle(1);
    } catch (h) {
      toast.error(copHataMetni(t, h));
    } finally {
      setCalisan(null);
    }
  };

  const saklamaKaydet = async (e: FormEvent) => {
    e.preventDefault();
    const gun = Math.round(Number(gunGirdisi));
    if (!Number.isFinite(gun) || gun < 1 || gun > 365) {
      toast.error(t('copKutusu.saklama.gecersiz'));
      return;
    }
    setCalisan('ayar');
    try {
      const g = await copSaklamaAyari(gun);
      setSaklamaGun(g.saklama_gun);
      toast.success(t('copKutusu.saklama.kaydedildi', { gun: g.saklama_gun }));
    } catch (h) {
      toast.error(copHataMetni(t, h));
    } finally {
      setCalisan(null);
    }
  };

  return (
    <div className="space-y-6" data-testid="cop-kutusu">
      <div className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="flex items-center gap-2 text-xl font-semibold">
              <Trash2 className="h-5 w-5 text-purple-400" aria-hidden="true" />
              {t('copKutusu.baslik')}
            </h2>
            <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
              {t('copKutusu.aciklama', { gun: saklamaGun })}
            </p>
          </div>
          <Button variant="outline" size="icon" onClick={() => void yukle(1)} aria-label={t('copKutusu.yenile')}>
            <RefreshCw className={`h-4 w-4 ${yukleniyor ? 'animate-spin' : ''}`} aria-hidden="true" />
          </Button>
        </div>

        <div className="mt-5 flex flex-wrap items-end justify-between gap-4">
          <form onSubmit={filtrele} className="flex flex-1 flex-wrap items-end gap-3">
            <label className="w-48 text-xs text-muted-foreground">
              {t('copKutusu.filtre.tablo')}
              <select
                value={tablo}
                onChange={(e) => setTablo(e.target.value)}
                className={SECIM_SINIFI}
                data-testid="cop-tablo"
              >
                <option value="">{t('copKutusu.filtre.hepsi')}</option>
                {tablolar.map((ad) => (
                  <option key={ad} value={ad}>
                    {tabloAdi(ad)}
                  </option>
                ))}
              </select>
            </label>
            <label className="min-w-[12rem] flex-1 text-xs text-muted-foreground">
              {t('copKutusu.filtre.ara')}
              <Input
                value={arama}
                onChange={(e) => setArama(e.target.value)}
                placeholder={t('copKutusu.filtre.araOrnek')}
                className="mt-1 bg-white/5 border-white/10"
                data-testid="cop-ara"
              />
            </label>
            <Button type="submit" variant="outline" className="h-10" data-testid="cop-filtrele">
              <Filter className="mr-2 h-4 w-4" aria-hidden="true" />
              {t('copKutusu.filtre.uygula')}
            </Button>
          </form>
          <form onSubmit={saklamaKaydet} className="flex items-end gap-2">
            <label className="w-36 text-xs text-muted-foreground">
              {t('copKutusu.saklama.etiket')}
              <Input
                type="number"
                min={1}
                max={365}
                value={gunGirdisi}
                onChange={(e) => setGunGirdisi(e.target.value)}
                className="mt-1 bg-white/5 border-white/10"
              />
            </label>
            <Button type="submit" variant="outline" size="icon" className="h-10 w-10" disabled={calisan === 'ayar'} aria-label={t('copKutusu.saklama.kaydet')}>
              <Save className="h-4 w-4" aria-hidden="true" />
            </Button>
          </form>
        </div>
      </div>

      <div className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-2 sm:p-4">
        {yukleniyor && satirlar.length === 0 ? (
          <div className="flex justify-center py-10 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
          </div>
        ) : hata ? (
          <p className="p-4 text-sm text-red-300">{t('copKutusu.hata')}</p>
        ) : satirlar.length === 0 ? (
          <p className="p-4 text-sm text-muted-foreground" data-testid="cop-bos">
            {t('copKutusu.bos')}
          </p>
        ) : (
          <ul className="divide-y divide-white/5">
            {satirlar.map((s) => (
              <li key={s.id} className="p-3" data-testid={`cop-satir-${s.id}`} data-tablo={s.tablo} data-kayit={s.kayit_id ?? ''}>
                <div className="flex flex-wrap items-start gap-3">
                  <button
                    type="button"
                    onClick={() => setAcik(acik === s.id ? null : s.id)}
                    className="mt-0.5 text-muted-foreground hover:text-foreground"
                    aria-expanded={acik === s.id}
                    aria-label={acik === s.id ? t('copKutusu.ayrintiGizle') : t('copKutusu.ayrinti')}
                  >
                    {acik === s.id ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                  </button>
                  <div className="min-w-0 flex-1">
                    <p className="flex flex-wrap items-center gap-2 text-sm">
                      <span className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[11px] text-foreground/80">
                        {tabloAdi(s.tablo)}
                      </span>
                      <span className="break-all font-medium">{s.etiket || `#${s.kayit_id}`}</span>
                      {s.kayit_id && <span className="text-xs text-muted-foreground">#{s.kayit_id}</span>}
                      {s.bagli_sayisi > 0 && (
                        <span className="rounded-full border border-purple-400/30 bg-purple-500/10 px-2 py-0.5 text-[11px] text-purple-200">
                          {t('copKutusu.bagli', { sayi: s.bagli_sayisi })}
                        </span>
                      )}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      <span title={tamZaman(s.silinme, dil)}>{goreliZaman(s.silinme, dil)}</span>
                      {' · '}
                      {t('copKutusu.silen', { kisi: s.silen_email ? `${s.silen_email} (${rolAdi(s.silen_rol)})` : rolAdi(s.silen_rol) })}
                      {s.sahip_email && (
                        <>
                          {' · '}
                          {t('copKutusu.sahip', { eposta: s.sahip_email })}
                        </>
                      )}
                    </p>
                    {s.kalici_silinme && (
                      <p className="mt-0.5 text-[11px] text-muted-foreground/80">
                        {t('copKutusu.kaliciSilinme', { zaman: tamZaman(s.kalici_silinme, dil) })}
                      </p>
                    )}
                  </div>
                  <div className="flex shrink-0 gap-2">
                    <Button
                      size="sm"
                      className="bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0"
                      disabled={calisan !== null}
                      onClick={() => void geriAl(s)}
                      data-testid={`cop-geri-al-${s.id}`}
                    >
                      {calisan === `geri-${s.id}` ? (
                        <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                      ) : (
                        <RotateCcw className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
                      )}
                      {t('copKutusu.geriAl')}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="border-red-400/30 text-red-300 hover:bg-red-500/10"
                      disabled={calisan !== null}
                      onClick={() => void kaliciSil(s)}
                      data-testid={`cop-sil-${s.id}`}
                    >
                      <Trash2 className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
                      {t('copKutusu.kaliciSil')}
                    </Button>
                  </div>
                </div>
                {acik === s.id && (
                  <div className="mt-3 rounded-xl border border-white/10 bg-black/10 p-3">
                    <Ayrinti id={s.id} />
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
        {satirlar.length > 0 && (
          <div className="flex flex-wrap items-center justify-between gap-2 px-3 pt-3 text-xs text-muted-foreground">
            <span>{t('copKutusu.gosterilen', { sayi: satirlar.length, toplam })}</span>
            {satirlar.length < toplam && (
              <Button variant="outline" size="sm" disabled={yukleniyor} onClick={() => void yukle(sayfa + 1)}>
                {t('copKutusu.dahaFazla')}
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
