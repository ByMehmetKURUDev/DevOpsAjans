import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CalendarDays, CalendarRange, ClipboardList, Eye, Settings2, Users, UsersRound } from 'lucide-react';

import { AltDugme, KART, SECIM, Yukleniyor } from '@/components/ik/ortak';
import { hataMetni, ikApi, type HesapOzeti, type IkMod, type Meta } from '@/lib/ik';

const PersonelBolumu = lazy(() => import('@/components/ik/Personel'));
const IzinlerBolumu = lazy(() => import('@/components/ik/Izinler'));
const TakvimBolumu = lazy(() => import('@/components/ik/Takvim'));
const VardiyaBolumu = lazy(() => import('@/components/ik/Vardiya'));
const AyarlarBolumu = lazy(() => import('@/components/ik/Ayarlar'));

type Bolum = 'personel' | 'izinler' | 'takvim' | 'vardiya' | 'ayarlar';
const BOLUMLER: { anahtar: Bolum; ikon: typeof Users }[] = [
  { anahtar: 'personel', ikon: Users },
  { anahtar: 'izinler', ikon: ClipboardList },
  { anahtar: 'takvim', ikon: CalendarDays },
  { anahtar: 'vardiya', ikon: CalendarRange },
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
 * Faz 6I — "İnsan kaynakları" sekmesi: personel, izin, izin takvimi, vardiya, ayarlar (menüde TEK sekme;
 * bölümler burada alt gezinme). Müşteri panelinde (`mod="musteri"`) etkin hesabın personeli; yönetici
 * panelinde (`mod="yonetici"`) ajansın KENDİ personeli tam yönetim, müşteri hesabı seçilince salt okunur
 * destek görünümü. Bordro / maaş / SGK / puantaj yok.
 */
export default function Ik({ mod }: { mod: IkMod }) {
  const { t } = useTranslation();
  const [hesap, setHesap] = useState('');
  const [hesaplar, setHesaplar] = useState<HesapOzeti[] | null>(null);
  const api = useMemo(() => ikApi(mod, hesap || undefined), [mod, hesap]);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [bolum, setBolum] = useState<Bolum>(() => {
    const b = adresParametresi('bolum') as Bolum | null;
    return b && BOLUMLER.some((x) => x.anahtar === b) ? b : 'personel';
  });

  useEffect(() => {
    if (mod !== 'yonetici') return;
    ikApi('yonetici')
      .hesaplar()
      .then((r) => setHesaplar(r.items))
      .catch(() => setHesaplar([]));
  }, [mod]);

  const yukle = useCallback(async () => {
    setHata(null);
    try {
      setMeta(await api.meta());
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  }, [api, t]);

  useEffect(() => {
    setMeta(null);
    void yukle();
  }, [yukle]);

  const saltOkunur = !!meta?.salt_okunur;
  return (
    <section aria-labelledby="ik-baslik" data-testid="ik-sekmesi" data-mod={mod}>
      <div className="mb-5">
        <h2 className="flex items-center gap-2 text-2xl font-bold" id="ik-baslik">
          <UsersRound className="h-6 w-6 text-purple-300" aria-hidden="true" />
          {t('ik.baslik')}
        </h2>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{mod === 'yonetici' ? t('ik.aciklamaYonetici') : t('ik.aciklama')}</p>
      </div>
      {mod === 'yonetici' && (
        <div className={`${KART} mb-4 flex flex-wrap items-center gap-2 p-3`}>
          <label className="flex min-w-[16rem] flex-1 items-center gap-2 text-sm">
            <span className="flex-none text-muted-foreground">{t('ik.yonetici.kapsam')}</span>
            <select className={SECIM} value={hesap} onChange={(e) => setHesap(e.target.value)} data-testid="ik-yonetici-hesap">
              <option value="">{t('ik.yonetici.ajans')}</option>
              {(hesaplar || []).map((h) => (
                <option key={h.hesap_email} value={h.hesap_email}>
                  {h.firma_adi ? `${h.firma_adi} — ` : ''}
                  {h.hesap_email} ({t('ik.yonetici.sayilar', { personel: h.personel, bekleyen: h.bekleyen_izin })})
                </option>
              ))}
            </select>
          </label>
          {saltOkunur && (
            <span className="inline-flex items-center gap-1 rounded-full border border-amber-400/30 bg-amber-500/10 px-2 py-0.5 text-xs text-amber-200" data-testid="ik-salt-okunur">
              <Eye className="h-3.5 w-3.5" aria-hidden="true" />
              {t('ik.yonetici.saltOkunur')}
            </span>
          )}
        </div>
      )}
      {hata && (
        <p className="mb-3 text-sm text-red-300" role="alert">
          {hata}
        </p>
      )}
      {!meta ? (
        !hata && <Yukleniyor />
      ) : (
        <>
          <div className="mb-4 flex gap-1 overflow-x-auto pb-1" role="tablist" aria-label={t('ik.baslik')}>
            {BOLUMLER.map(({ anahtar, ikon: Ikon }) => (
              <AltDugme key={anahtar} secili={bolum === anahtar} onClick={() => setBolum(anahtar)} testid={anahtar}>
                <Ikon className="h-4 w-4" aria-hidden="true" />
                {t(`ik.bolum.${anahtar}`)}
                {anahtar === 'izinler' && meta.bekleyen_izin > 0 && (
                  <span className="rounded-full bg-amber-500/80 px-1.5 text-[10px] font-semibold text-zinc-950" data-testid="ik-bekleyen-rozet">
                    {meta.bekleyen_izin}
                  </span>
                )}
              </AltDugme>
            ))}
          </div>
          <Suspense fallback={<Yukleniyor />}>
            {bolum === 'personel' ? (
              <PersonelBolumu api={api} meta={meta} onMeta={yukle} />
            ) : bolum === 'izinler' ? (
              <IzinlerBolumu api={api} meta={meta} onMeta={yukle} />
            ) : bolum === 'takvim' ? (
              <TakvimBolumu api={api} meta={meta} />
            ) : bolum === 'vardiya' ? (
              <VardiyaBolumu api={api} meta={meta} />
            ) : (
              <AyarlarBolumu api={api} meta={meta} onMeta={yukle} />
            )}
          </Suspense>
        </>
      )}
    </section>
  );
}
