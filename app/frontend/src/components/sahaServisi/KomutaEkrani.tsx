import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { Activity, AlertTriangle, Box, CheckCircle2, Clock, Expand, MapPin, Navigation, Phone, Shrink, X } from 'lucide-react';

import OsmHarita from '@/components/harita/OsmHarita';
import { bugunIso, gunYaz, hataMetni, saatYaz, type IsOzeti, type Komuta, type SahaApi } from '@/lib/sahaServisi';
import { DURUM_HEX, TEKNISYEN_DURUM_HEX, isaretler, rotalar } from './harita';

import './komutaEkrani.css';

/**
 * Faz 11E — Komuta ekranı (TV / duvar modu). Sevk panosundan açılan tam ekran katman: en acil iş, günün
 * sayıları, iş türleri, gerçek harita (iş noktaları + teknisyen ziyaret sırası), teknisyen kartları ve canlı akış.
 * 30 sn'de bir yenilenir; saat her saniye. İsteğe bağlı "3B" görünüm katmanları hafif eğimle dizer (tercih
 * yerel saklanır; "hareketi azalt" açıksa varsayılan düz). Esc kapatır. Teknisyenin canlı konumu YOK:
 * haritadaki noktalar işlerin adresleri.
 */

const UC_B_ANAHTARI = 'mk_komuta_3b';

function ucBOku(): boolean {
  try {
    const v = window.localStorage.getItem(UC_B_ANAHTARI);
    if (v != null) return v === '1';
  } catch {
    /* depo kapalı */
  }
  return !(typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);
}

function basHarfler(ad: string): string {
  return ad
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toLocaleUpperCase('tr'))
    .join('');
}

function yolTarifi(adres: string | null): string | null {
  return adres ? `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(adres)}` : null;
}

export default function KomutaEkrani({ api, firma, onKapat, onAc }: { api: SahaApi; firma?: string | null; onKapat: () => void; onAc: (id: number) => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [veri, setVeri] = useState<Komuta | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [simdi, setSimdi] = useState(() => new Date());
  const [ucB, setUcB] = useState(ucBOku);
  const [tamEkran, setTamEkran] = useState(false);
  const [secili, setSecili] = useState<number | null>(null);
  const kokRef = useRef<HTMLDivElement>(null);
  const kapatRef = useRef<HTMLButtonElement>(null);

  const [firmaAdi, setFirmaAdi] = useState<string | null>(firma ?? null);
  useEffect(() => {
    if (firma !== undefined) return;
    let iptal = false;
    api
      .ayarlar()
      .then((a) => {
        if (!iptal) setFirmaAdi(a.firma_adi || null);
      })
      .catch(() => undefined);
    return () => {
      iptal = true;
    };
  }, [api, firma]);

  const yukle = useCallback(async () => {
    try {
      setVeri(await api.komuta(bugunIso()));
      setHata(null);
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  }, [api, t]);

  useEffect(() => {
    void yukle();
    const v = window.setInterval(() => {
      if (document.visibilityState === 'visible') void yukle();
    }, 30_000);
    const s = window.setInterval(() => setSimdi(new Date()), 1000);
    return () => {
      window.clearInterval(v);
      window.clearInterval(s);
    };
  }, [yukle]);

  // Esc kapatır; açılınca odak katmana, sayfa kaydırması kilitli.
  useEffect(() => {
    const onceki = document.activeElement as HTMLElement | null;
    kapatRef.current?.focus();
    const tus = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !document.fullscreenElement) onKapat();
    };
    const tam = () => setTamEkran(!!document.fullscreenElement);
    document.addEventListener('keydown', tus);
    document.addEventListener('fullscreenchange', tam);
    const tasma = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', tus);
      document.removeEventListener('fullscreenchange', tam);
      document.body.style.overflow = tasma;
      if (document.fullscreenElement) void document.exitFullscreen?.().catch(() => undefined);
      onceki?.focus?.();
    };
  }, [onKapat]);

  const ucBDegistir = () => {
    setUcB((v) => {
      try {
        window.localStorage.setItem(UC_B_ANAHTARI, v ? '0' : '1');
      } catch {
        /* yalnız hatırlanmaz */
      }
      return !v;
    });
  };

  const tamEkranDegistir = () => {
    if (document.fullscreenElement) void document.exitFullscreen?.().catch(() => undefined);
    else void kokRef.current?.requestFullscreen?.().catch(() => undefined);
  };

  const isler = useMemo(() => new Map((veri?.isler || []).map((x) => [x.id, x])), [veri]);
  const renkler = useMemo(() => new Map((veri?.teknisyenler || []).map((x) => [x.id, x.renk])), [veri]);
  const etiketle = useCallback((x: IsOzeti) => `${x.plan_bas ? saatYaz(x.plan_bas, dil) : ''} · ${x.baslik}`, [dil]);
  const pinler = useMemo(() => (veri ? isaretler(veri.isler, etiketle) : []), [veri, etiketle]);
  const cizgiler = useMemo(() => (veri ? rotalar(veri.isler, renkler) : []), [veri, renkler]);

  const acil = veri?.acil != null ? isler.get(veri.acil) ?? null : null;
  const s = veri?.sayilar;
  const yuzde = s && s.toplam ? Math.round((s.tamamlanan / s.toplam) * 100) : 0;
  const turToplam = veri ? Object.values(veri.turler).reduce((a, b) => a + (b || 0), 0) : 0;

  const dakikaFarki = (iso: string | null) => (iso ? Math.round((new Date(iso).getTime() - simdi.getTime()) / 60000) : null);
  const fark = acil ? dakikaFarki(acil.plan_bas) : null;

  // Katman <body> altına: panel kabuğundaki dönüşümlü/kapsamlı ataların içinde `fixed` kaymasın.
  return createPortal(
    <div
      ref={kokRef}
      className="kmt"
      data-3b={ucB ? 'acik' : 'kapali'}
      role="dialog"
      aria-modal="true"
      aria-labelledby="kmt-baslik"
      data-testid="saha-komuta"
    >
      <header className="kmt-ust">
        <span className="kmt-canli">
          <span className="kmt-canli-nokta" aria-hidden="true" />
          {t('sahaServisi.komuta.canli')}
        </span>
        <div className="min-w-0">
          <h2 id="kmt-baslik" className="kmt-baslik">
            {t('sahaServisi.komuta.baslik')}
            {firmaAdi ? <span className="kmt-firma"> · {firmaAdi}</span> : null}
          </h2>
          <p className="kmt-tarih">{veri ? gunYaz(veri.gun, dil, true) : ''}</p>
        </div>
        <p className="kmt-saat" dir="ltr" aria-live="off">
          {simdi.toLocaleTimeString(dil === 'ar' ? 'ar-EG' : dil, { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, timeZone: 'Europe/Istanbul' })}
        </p>
        <div className="kmt-dugmeler">
          <button type="button" className="kmt-dugme" aria-pressed={ucB} onClick={ucBDegistir} data-testid="saha-komuta-3b">
            <Box className="h-4 w-4" aria-hidden="true" />
            {t('sahaServisi.komuta.ucB')}
          </button>
          <button type="button" className="kmt-dugme" onClick={tamEkranDegistir} aria-pressed={tamEkran}>
            {tamEkran ? <Shrink className="h-4 w-4" aria-hidden="true" /> : <Expand className="h-4 w-4" aria-hidden="true" />}
            {t(tamEkran ? 'sahaServisi.komuta.tamEkrandanCik' : 'sahaServisi.komuta.tamEkran')}
          </button>
          <button ref={kapatRef} type="button" className="kmt-dugme kmt-kapat" onClick={onKapat} aria-label={t('sahaServisi.kapat')} data-testid="saha-komuta-kapat">
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </header>

      {hata && (
        <p className="kmt-hata" role="alert">
          {hata}
        </p>
      )}

      {!veri || !s ? (
        <div className="kmt-yukleniyor" aria-busy="true">
          {t('sahaServisi.komuta.yukleniyor')}
        </div>
      ) : (
        <div className="kmt-sahne">
          <div className="kmt-izgara">
            {/* Sol: acil, sayılar, türler */}
            <section className="kmt-sol" aria-label={t('sahaServisi.komuta.ozet')}>
              {acil ? (
                <article className={`kmt-panel kmt-acil ${acil.oncelik === 'acil' ? '' : 'kmt-acil-gec'}`} data-testid="saha-komuta-acil">
                  <p className="kmt-acil-rozet">
                    <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
                    {acil.oncelik === 'acil' ? t('sahaServisi.komuta.acil') : t('sahaServisi.komuta.geciken')}
                    <span className="kmt-mono">{acil.no}</span>
                  </p>
                  <h3 className="kmt-acil-baslik">{acil.baslik}</h3>
                  <p className="kmt-acil-alt">
                    {acil.musteri_ad}
                    {acil.adres ? ` · ${acil.adres}` : ''}
                  </p>
                  <div className="kmt-acil-alt-satir">
                    <span className="kmt-acil-sayac" data-testid="saha-komuta-acil-sayac">
                      <Clock className="h-4 w-4" aria-hidden="true" />
                      {acil.durum === 'iste' && acil.basla_at
                        ? t('sahaServisi.komuta.istedir', { dk: Math.max(0, -(dakikaFarki(acil.basla_at) ?? 0)) })
                        : acil.durum === 'yolda' && acil.yolda_at
                          ? t('sahaServisi.komuta.yoldadir', { dk: Math.max(0, -(dakikaFarki(acil.yolda_at) ?? 0)) })
                          : fark == null
                            ? t('sahaServisi.planYok')
                            : fark >= 0
                              ? t('sahaServisi.komuta.planaKalan', { dk: fark })
                              : t('sahaServisi.komuta.gecikme', { dk: -fark })}
                    </span>
                    <span className="kmt-acil-ekip">{acil.teknisyenler.map((x) => x.ad).join(', ') || t('sahaServisi.komuta.atanmamis')}</span>
                  </div>
                  <button
                    type="button"
                    className="kmt-acil-dugme"
                    onClick={() => {
                      onKapat();
                      onAc(acil.id);
                    }}
                  >
                    {t('sahaServisi.komuta.ayrinti')}
                  </button>
                </article>
              ) : (
                <article className="kmt-panel kmt-sakin" data-testid="saha-komuta-acil-yok">
                  <CheckCircle2 className="h-6 w-6 text-emerald-300" aria-hidden="true" />
                  <p>{t('sahaServisi.komuta.acilYok')}</p>
                </article>
              )}

              <div className="kmt-sayilar">
                {(
                  [
                    ['toplam', s.toplam, '#e2f3ff'],
                    ['tamamlanan', s.tamamlanan, '#34d399'],
                    ['yolda', s.yolda, '#fbbf24'],
                    ['iste', s.iste, '#fb923c'],
                    ['bekleyen', s.bekleyen, '#a78bfa'],
                    ['geciken', s.geciken, s.geciken ? '#f87171' : '#94a3b8'],
                  ] as const
                ).map(([a, n, renk]) => (
                  <div key={a} className="kmt-panel kmt-sayi" style={{ ['--kmt-renk' as string]: renk }} data-testid={`saha-komuta-sayi-${a}`}>
                    <p className="kmt-etiket">{t(`sahaServisi.harita.sayi.${a}`)}</p>
                    <p className="kmt-deger kmt-mono">{n}</p>
                    {a === 'tamamlanan' && (
                      <span className="kmt-cubuk" aria-hidden="true">
                        <span style={{ width: `${yuzde}%` }} />
                      </span>
                    )}
                  </div>
                ))}
              </div>

              <div className="kmt-panel">
                <p className="kmt-etiket">{t('sahaServisi.komuta.turler')}</p>
                <ul className="kmt-turler">
                  {Object.entries(veri.turler)
                    .sort((a, b) => (b[1] || 0) - (a[1] || 0))
                    .map(([tur, n]) => (
                      <li key={tur}>
                        <span>{t(`sahaServisi.tur.${tur}`)}</span>
                        <span className="kmt-tur-cubuk" aria-hidden="true">
                          <span style={{ width: `${turToplam ? Math.round(((n || 0) / turToplam) * 100) : 0}%` }} />
                        </span>
                        <span className="kmt-mono">{n}</span>
                      </li>
                    ))}
                  {turToplam === 0 && <li className="kmt-bos">{t('sahaServisi.harita.isYok')}</li>}
                </ul>
              </div>
            </section>

            {/* Orta: harita */}
            <section className="kmt-orta kmt-panel kmt-harita-panel" aria-label={t('sahaServisi.harita.haritaEtiket')}>
              <div className="kmt-harita-bas">
                <p className="kmt-etiket">
                  <MapPin className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('sahaServisi.komuta.harita')}
                </p>
                <p className="kmt-harita-not">
                  {s.konumsuz > 0 ? t('sahaServisi.harita.konumsuzKisa', { sayi: s.konumsuz }) : t('sahaServisi.komuta.haritaNot')}
                </p>
              </div>
              <OsmHarita
                isaretler={pinler}
                cizgiler={cizgiler}
                secili={secili}
                onSec={(id) => setSecili(Number(id))}
                sigdirAnahtari={`${veri.gun}-${pinler.length}`}
                className="kmt-harita"
                etiket={t('sahaServisi.harita.haritaEtiket')}
                testid="saha-komuta-harita"
              />
            </section>

            {/* Sağ: teknisyenler + canlı akış */}
            <section className="kmt-sag" aria-label={t('sahaServisi.komuta.ekip')}>
              <div className="kmt-panel kmt-ekip">
                <p className="kmt-etiket">{t('sahaServisi.komuta.ekip')}</p>
                {veri.teknisyenler.length === 0 && <p className="kmt-bos">{t('sahaServisi.pano.teknisyenYok')}</p>}
                <ul>
                  {veri.teknisyenler.map((x) => {
                    const aktif = x.aktif_is != null ? isler.get(x.aktif_is) : undefined;
                    const sonraki = x.siradaki_is != null ? isler.get(x.siradaki_is) : undefined;
                    const hedef = aktif || sonraki;
                    const yol = yolTarifi(hedef?.adres ?? null);
                    return (
                      <li key={x.id} className="kmt-tek" data-testid={`saha-komuta-teknisyen-${x.id}`} data-durum={x.durum}>
                        <span className="kmt-avatar" style={{ ['--kmt-renk' as string]: x.renk }} aria-hidden="true">
                          {basHarfler(x.ad)}
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="kmt-tek-ust">
                            <span className="kmt-tek-ad">{x.ad}</span>
                            <span className="kmt-durum" style={{ ['--kmt-renk' as string]: TEKNISYEN_DURUM_HEX[x.durum] }}>
                              {t(`sahaServisi.komuta.teknisyenDurum.${x.durum}`)}
                            </span>
                          </p>
                          {aktif && (
                            <p className="kmt-tek-is">
                              <span className="kmt-nokta" style={{ background: DURUM_HEX[aktif.durum] }} aria-hidden="true" />
                              {aktif.baslik} · {aktif.musteri_ad}
                            </p>
                          )}
                          {sonraki && (
                            <p className="kmt-tek-sonraki">
                              {t('sahaServisi.komuta.siradaki')}{' '}
                              <span className="kmt-mono" dir="ltr">
                                {sonraki.plan_bas ? saatYaz(sonraki.plan_bas, dil) : '—'}
                              </span>{' '}
                              · {sonraki.baslik}
                            </p>
                          )}
                          <div className="kmt-tek-alt">
                            <span className="kmt-cubuk" aria-hidden="true">
                              <span style={{ width: `${x.toplam ? Math.round((x.tamamlanan / x.toplam) * 100) : 0}%`, background: x.renk }} />
                            </span>
                            <span className="kmt-mono kmt-tek-sayi">
                              {x.tamamlanan}/{x.toplam}
                            </span>
                            {x.telefon && (
                              <a className="kmt-ikon-dugme" href={`tel:${x.telefon.replace(/[^\d+]/g, '')}`} aria-label={t('sahaServisi.komuta.ara', { ad: x.ad })} title={t('sahaServisi.komuta.ara', { ad: x.ad })}>
                                <Phone className="h-3.5 w-3.5" aria-hidden="true" />
                              </a>
                            )}
                            {yol && (
                              <a className="kmt-ikon-dugme" href={yol} target="_blank" rel="noopener noreferrer" aria-label={t('sahaServisi.komuta.yolTarifi')} title={t('sahaServisi.komuta.yolTarifi')}>
                                <Navigation className="h-3.5 w-3.5" aria-hidden="true" />
                              </a>
                            )}
                          </div>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </div>

              <div className="kmt-panel kmt-akis">
                <p className="kmt-etiket">
                  <Activity className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('sahaServisi.komuta.akis')}
                </p>
                {veri.akis.length === 0 ? (
                  <p className="kmt-bos">{t('sahaServisi.komuta.akisYok')}</p>
                ) : (
                  <ol data-testid="saha-komuta-akis">
                    {veri.akis.slice(0, 12).map((a, i) => (
                      <li key={`${a.is_id}-${a.zaman}-${i}`}>
                        <span className="kmt-mono kmt-akis-saat" dir="ltr">
                          {saatYaz(a.zaman, dil)}
                        </span>
                        <span className="kmt-nokta" style={{ background: DURUM_HEX[a.yeni] }} aria-hidden="true" />
                        <span className="min-w-0 flex-1">
                          <span className="kmt-akis-ust">
                            <span className="kmt-mono">{a.no}</span> {a.eski ? `${t(`sahaServisi.durum.${a.eski}`)} → ` : ''}
                            <strong>{a.eski ? t(`sahaServisi.durum.${a.yeni}`) : t('sahaServisi.komuta.yeniIs')}</strong>
                          </span>
                          <span className="kmt-akis-alt">
                            {a.baslik}
                            {a.kisi ? ` · ${a.kisi}` : ''}
                          </span>
                        </span>
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            </section>
          </div>
        </div>
      )}
    </div>,
    document.body
  );
}
