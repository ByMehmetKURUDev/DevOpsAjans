import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { BarChart3, Boxes, Eye, Package, ScanBarcode, Settings2, ShoppingCart } from 'lucide-react';

import { hataMetni, stokApi, type Meta, type StokMod } from '@/lib/stokPos';
import { KART, SECIM, Yukleniyor } from '@/components/stokPos/ortak';

const Kasa = lazy(() => import('@/components/stokPos/Kasa'));
const Urunler = lazy(() => import('@/components/stokPos/Urunler'));
const Stok = lazy(() => import('@/components/stokPos/Stok'));
const Raporlar = lazy(() => import('@/components/stokPos/Raporlar'));
const Ayarlar = lazy(() => import('@/components/stokPos/Ayarlar'));

type Bolum = 'kasa' | 'urunler' | 'stok' | 'raporlar' | 'ayarlar';
const BOLUMLER: { anahtar: Bolum; ikon: typeof Package }[] = [
  { anahtar: 'kasa', ikon: ShoppingCart },
  { anahtar: 'urunler', ikon: Package },
  { anahtar: 'stok', ikon: Boxes },
  { anahtar: 'raporlar', ikon: BarChart3 },
  { anahtar: 'ayarlar', ikon: Settings2 },
];

function adresParametresi(ad: string): string | null {
  try {
    return new URLSearchParams(window.location.search).get(ad);
  } catch {
    return null;
  }
}

/**
 * Faz 6P — "Stok ve POS" sekmesi. Müşteri panelinde (`mod="musteri"`): işletmenin kendi işi — `stok` izni
 * olana Kasa, Ürünler, Stok, Raporlar, Ayarlar; yalnız `kasa` izni olana sadece Kasa (satış ekranı).
 * Yönetici panelinde (`mod="yonetici"`) hesap seçerek SALT OKUNUR destek görünümü (Ürünler, Stok, Raporlar).
 */
export default function StokPos({ mod }: { mod: StokMod }) {
  const { t } = useTranslation();
  const [hesap, setHesap] = useState('');
  const [hesaplar, setHesaplar] = useState<{ hesap_email: string; firma_adi: string | null; urun: number; satis: number }[] | null>(null);
  const api = useMemo(() => stokApi(mod, hesap || undefined), [mod, hesap]);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [bolum, setBolum] = useState<Bolum>(() => (adresParametresi('bolum') as Bolum) || (mod === 'yonetici' ? 'urunler' : 'kasa'));
  // Faz 6Q: kasa ekranının çevrimdışı kuyruğundaki satış sayısı — kasadan çıkarken uyarı (kuyruk cihazda kalır ama
  // kasa ekranı kapalıyken gönderilmez).
  const [kuyrukSayisi, setKuyrukSayisi] = useState(0);
  const bolumSec = (b: Bolum) => {
    if (bolum === 'kasa' && b !== 'kasa' && kuyrukSayisi > 0 && !window.confirm(t('stokPos.kuyruk.ayrilOnay', { sayi: kuyrukSayisi }))) return;
    setBolum(b);
  };

  useEffect(() => {
    if (mod !== 'yonetici') return;
    stokApi('yonetici')
      .hesaplar()
      .then((r) => setHesaplar(r.items))
      .catch((e) => setHata(hataMetni(t, e)));
  }, [mod, t]);

  const yukle = useCallback(async () => {
    if (mod === 'yonetici' && !hesap) return;
    setHata(null);
    try {
      setMeta(await api.meta());
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  }, [api, hesap, mod, t]);

  useEffect(() => {
    setMeta(null);
    void yukle();
  }, [yukle]);

  const gorunen = useMemo<Bolum[]>(() => {
    if (!meta) return [];
    if (meta.yetki.ajans) return ['urunler', 'stok', 'raporlar'];
    if (!meta.yetki.stok) return ['kasa'];
    return BOLUMLER.map((b) => b.anahtar);
  }, [meta]);

  useEffect(() => {
    if (meta && !gorunen.includes(bolum)) setBolum(gorunen[0]);
  }, [meta, gorunen, bolum]);

  const saltOkunur = !!meta?.salt_okunur;
  return (
    <section aria-labelledby="stok-baslik" data-testid="stok-sekmesi" data-mod={mod}>
      <div className="mb-5">
        <h2 className="flex items-center gap-2 text-2xl font-bold" id="stok-baslik">
          <ScanBarcode className="h-6 w-6 text-purple-300" aria-hidden="true" />
          {t('stokPos.baslik')}
        </h2>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
          {mod === 'yonetici' ? t('stokPos.aciklamaYonetici') : meta && !meta.yetki.stok ? t('stokPos.aciklamaKasiyer') : t('stokPos.aciklama')}
        </p>
      </div>
      {mod === 'yonetici' && (
        <div className={`${KART} mb-4 flex flex-wrap items-center gap-2 p-3`}>
          <label className="flex min-w-[16rem] flex-1 items-center gap-2 text-sm">
            <span className="text-muted-foreground">{t('stokPos.yonetici.hesap')}</span>
            <select className={SECIM} value={hesap} onChange={(e) => setHesap(e.target.value)} data-testid="stok-yonetici-hesap">
              <option value="">{t('stokPos.secin')}</option>
              {(hesaplar || []).map((h) => (
                <option key={h.hesap_email} value={h.hesap_email}>
                  {h.firma_adi ? `${h.firma_adi} — ` : ''}
                  {h.hesap_email} ({t('stokPos.yonetici.sayilar', { urun: h.urun, satis: h.satis })})
                </option>
              ))}
            </select>
          </label>
          <span className="inline-flex items-center gap-1 rounded-full border border-amber-400/30 bg-amber-500/10 px-2 py-0.5 text-xs text-amber-200">
            <Eye className="h-3.5 w-3.5" aria-hidden="true" />
            {t('stokPos.yonetici.saltOkunur')}
          </span>
        </div>
      )}
      {hata && (
        <p className="mb-3 text-sm text-red-300" role="alert">
          {hata}
        </p>
      )}
      {mod === 'yonetici' && !hesap ? (
        <p className="py-10 text-center text-sm text-muted-foreground">{t('stokPos.yonetici.sec')}</p>
      ) : !meta ? (
        !hata && <Yukleniyor />
      ) : (
        <>
          {gorunen.length > 1 && (
            <div className="mb-4 flex gap-1 overflow-x-auto pb-1" role="tablist" aria-label={t('stokPos.baslik')}>
              {BOLUMLER.filter((b) => gorunen.includes(b.anahtar)).map(({ anahtar, ikon: Ikon }) => (
                <button
                  key={anahtar}
                  type="button"
                  role="tab"
                  aria-selected={bolum === anahtar}
                  onClick={() => bolumSec(anahtar)}
                  className={`flex min-h-[40px] flex-none items-center gap-1.5 rounded-lg px-3 py-2 text-sm transition-colors ${
                    bolum === anahtar ? 'bg-purple-500/20 text-white' : 'text-muted-foreground hover:bg-white/[0.05] hover:text-white'
                  }`}
                  data-stok-bolum={anahtar}
                >
                  <Ikon className="h-4 w-4" aria-hidden="true" />
                  {t(`stokPos.bolum.${anahtar}`)}
                  {anahtar === 'urunler' && meta.sayilar.kritik > 0 && (
                    <span className="rounded-full bg-amber-500/80 px-1.5 text-[10px] font-semibold text-zinc-950" data-testid="stok-kritik-rozet">
                      {meta.sayilar.kritik}
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}
          <Suspense fallback={<Yukleniyor />}>
            {bolum === 'kasa' ? (
              <Kasa api={api} meta={meta} onMeta={yukle} onKuyruk={setKuyrukSayisi} />
            ) : bolum === 'urunler' ? (
              <Urunler api={api} meta={meta} saltOkunur={saltOkunur} onMeta={yukle} baslangicKritik={adresParametresi('kritik') === '1'} />
            ) : bolum === 'stok' ? (
              <Stok api={api} meta={meta} saltOkunur={saltOkunur} onMeta={yukle} />
            ) : bolum === 'raporlar' ? (
              <Raporlar api={api} meta={meta} />
            ) : (
              <Ayarlar api={api} meta={meta} onMeta={yukle} />
            )}
          </Suspense>
        </>
      )}
    </section>
  );
}
