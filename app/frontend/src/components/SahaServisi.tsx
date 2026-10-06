import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { BarChart3, ClipboardList, Eye, LayoutGrid, ListChecks, Package, Settings2, Smartphone, Users, Wrench } from 'lucide-react';

import { hataMetni, sahaApi, type Meta, type Riza, type SahaMod } from '@/lib/sahaServisi';
import { KART, SECIM, Yukleniyor } from '@/components/sahaServisi/ortak';

const Pano = lazy(() => import('@/components/sahaServisi/Pano'));
const IsEmirleri = lazy(() => import('@/components/sahaServisi/IsEmirleri'));
const IsAyrintisi = lazy(() => import('@/components/sahaServisi/IsAyrintisi'));
const Islerim = lazy(() => import('@/components/sahaServisi/Islerim'));
const Musteriler = lazy(() => import('@/components/sahaServisi/Musteriler'));
const Sablonlar = lazy(() => import('@/components/sahaServisi/Sablonlar'));
const Malzemeler = lazy(() => import('@/components/sahaServisi/Malzemeler'));
const Raporlar = lazy(() => import('@/components/sahaServisi/Raporlar'));
const Ayarlar = lazy(() => import('@/components/sahaServisi/Ayarlar'));

type Bolum = 'pano' | 'isler' | 'islerim' | 'musteriler' | 'sablonlar' | 'malzemeler' | 'raporlar' | 'ayarlar';
const BOLUMLER: { anahtar: Bolum; ikon: typeof Wrench }[] = [
  { anahtar: 'pano', ikon: LayoutGrid },
  { anahtar: 'isler', ikon: ClipboardList },
  { anahtar: 'islerim', ikon: Smartphone },
  { anahtar: 'musteriler', ikon: Users },
  { anahtar: 'sablonlar', ikon: ListChecks },
  { anahtar: 'malzemeler', ikon: Package },
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
 * Faz 6S — "Saha servisi" sekmesi. Müşteri panelinde (`mod="musteri"`): servis firmasının kendi işi —
 * yönetim izni (`saha_yonetim`) olana Pano, İş emirleri, Müşteriler/Cihazlar, Şablonlar, Malzemeler,
 * Raporlar, Ayarlar; teknisyene (`saha_teknisyen`) sadeleştirilmiş "İşlerim". Yönetici panelinde
 * (`mod="yonetici"`) aynı ekranlar hesap seçerek SALT OKUNUR (destek amaçlı).
 */
export default function SahaServisi({ mod }: { mod: SahaMod }) {
  const { t } = useTranslation();
  const [hesap, setHesap] = useState('');
  const [hesaplar, setHesaplar] = useState<{ hesap_email: string; firma_adi: string | null; is_emri: number }[] | null>(null);
  const api = useMemo(() => sahaApi(mod, hesap || undefined), [mod, hesap]);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [bolum, setBolum] = useState<Bolum>(() => (adresParametresi('bolum') as Bolum) || 'pano');
  const [acikIs, setAcikIs] = useState<number | null>(() => Number(adresParametresi('is')) || null);
  const [riza, setRiza] = useState<Riza | null>(null);

  useEffect(() => {
    if (mod !== 'yonetici') return;
    sahaApi('yonetici')
      .hesaplar()
      .then((r) => setHesaplar(r.items))
      .catch((e) => setHata(hataMetni(t, e)));
  }, [mod, t]);

  const yukle = useCallback(async () => {
    if (mod === 'yonetici' && !hesap) return;
    setHata(null);
    try {
      const m = await api.meta();
      setMeta(m);
      if (m.teknisyen) api.rizam().then(setRiza).catch(() => undefined);
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  }, [api, hesap, mod, t]);

  useEffect(() => {
    setMeta(null);
    void yukle();
  }, [yukle]);

  const gorunen = useMemo(() => {
    if (!meta) return [] as Bolum[];
    if (!meta.yonetim) return ['islerim'] as Bolum[];
    return BOLUMLER.map((b) => b.anahtar).filter((b) => b !== 'islerim' || meta.teknisyen);
  }, [meta]);

  useEffect(() => {
    if (meta && !gorunen.includes(bolum)) setBolum(gorunen[0]);
  }, [meta, gorunen, bolum]);

  const ust = (
    <div className="mb-5">
      <h2 className="flex items-center gap-2 text-2xl font-bold" id="saha-baslik">
        <Wrench className="h-6 w-6 text-purple-300" aria-hidden="true" />
        {t('sahaServisi.baslik')}
      </h2>
      <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
        {mod === 'yonetici' ? t('sahaServisi.aciklamaYonetici') : meta && !meta.yonetim ? t('sahaServisi.aciklamaTeknisyen') : t('sahaServisi.aciklama')}
      </p>
    </div>
  );

  const yonetimMi = !!meta?.yonetim;
  const saltOkunur = !!meta?.salt_okunur;
  return (
    <section aria-labelledby="saha-baslik" data-testid="saha-sekmesi" data-mod={mod}>
      {ust}
      {mod === 'yonetici' && (
        <div className={`${KART} mb-4 flex flex-wrap items-center gap-2 p-3`}>
          <label className="flex min-w-[16rem] flex-1 items-center gap-2 text-sm">
            <span className="text-muted-foreground">{t('sahaServisi.yonetici.hesap')}</span>
            <select className={SECIM} value={hesap} onChange={(e) => setHesap(e.target.value)} data-testid="saha-yonetici-hesap">
              <option value="">{t('sahaServisi.secin')}</option>
              {(hesaplar || []).map((h) => (
                <option key={h.hesap_email} value={h.hesap_email}>
                  {h.firma_adi ? `${h.firma_adi} — ` : ''}
                  {h.hesap_email} ({h.is_emri})
                </option>
              ))}
            </select>
          </label>
          <span className="inline-flex items-center gap-1 rounded-full border border-amber-400/30 bg-amber-500/10 px-2 py-0.5 text-xs text-amber-200">
            <Eye className="h-3.5 w-3.5" aria-hidden="true" />
            {t('sahaServisi.yonetici.saltOkunur')}
          </span>
        </div>
      )}
      {hata && (
        <p className="mb-3 text-sm text-red-300" role="alert">
          {hata}
        </p>
      )}
      {mod === 'yonetici' && !hesap ? (
        <p className="py-10 text-center text-sm text-muted-foreground">{t('sahaServisi.yonetici.sec')}</p>
      ) : !meta ? (
        !hata && <Yukleniyor />
      ) : (
        <>
          {yonetimMi && acikIs === null && (
            <div className="mb-4 flex gap-1 overflow-x-auto pb-1" role="tablist" aria-label={t('sahaServisi.baslik')}>
              {BOLUMLER.filter((b) => gorunen.includes(b.anahtar)).map(({ anahtar, ikon: Ikon }) => (
                <button
                  key={anahtar}
                  type="button"
                  role="tab"
                  aria-selected={bolum === anahtar}
                  onClick={() => setBolum(anahtar)}
                  className={`flex min-h-[40px] flex-none items-center gap-1.5 rounded-lg px-3 py-2 text-sm transition-colors ${
                    bolum === anahtar ? 'bg-purple-500/20 text-white' : 'text-muted-foreground hover:bg-white/[0.05] hover:text-white'
                  }`}
                  data-saha-bolum={anahtar}
                >
                  <Ikon className="h-4 w-4" aria-hidden="true" />
                  {t(`sahaServisi.bolum.${anahtar}`)}
                </button>
              ))}
            </div>
          )}
          <Suspense fallback={<Yukleniyor />}>
            {yonetimMi && acikIs !== null && bolum !== 'islerim' ? (
              <IsAyrintisi api={api} meta={meta} isId={acikIs} riza={riza} onGeri={() => setAcikIs(null)} />
            ) : bolum === 'islerim' || !yonetimMi ? (
              <Islerim api={api} meta={meta} baslangicIs={!yonetimMi ? acikIs : null} />
            ) : bolum === 'pano' ? (
              <Pano api={api} onAc={setAcikIs} saltOkunur={saltOkunur} />
            ) : bolum === 'isler' ? (
              <IsEmirleri api={api} onAc={setAcikIs} saltOkunur={saltOkunur} />
            ) : bolum === 'musteriler' ? (
              <Musteriler api={api} onAc={setAcikIs} saltOkunur={saltOkunur} />
            ) : bolum === 'sablonlar' ? (
              <Sablonlar api={api} saltOkunur={saltOkunur} />
            ) : bolum === 'malzemeler' ? (
              <Malzemeler api={api} saltOkunur={saltOkunur} paraBirimi={meta.ayarlar.para_birimi} />
            ) : bolum === 'raporlar' ? (
              <Raporlar api={api} onAc={setAcikIs} saltOkunur={saltOkunur} />
            ) : (
              <Ayarlar api={api} saltOkunur={saltOkunur} />
            )}
          </Suspense>
        </>
      )}
    </section>
  );
}
