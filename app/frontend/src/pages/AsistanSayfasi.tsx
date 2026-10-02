import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import i18n from 'i18next';
import type { TFunction } from 'i18next';
import { Bot, Loader2 } from 'lucide-react';

import SohbetPenceresi from '@/components/aiAsistan/SohbetPenceresi';
import { AcikHata, acikIstek, asistanPaketiYukle, dilSec, type AcikYapilandirma, type AsistanDili } from '@/lib/asistanOrtak';

/**
 * Faz 5A — herkese açık AI asistan sayfası.
 *
 *   /asistan/<anahtar>             paylaşılabilir tam sayfa (asistanın "tam sayfa" ayarı açıksa)
 *   /asistan/<anahtar>?gomulu=1    gömülü pencere (public/asistan-widget.js çerçevesi)
 *
 * Site düzeninin (Layout) DIŞINDA, lazy; prerender yok, site haritasında yok, her zaman
 * noindex. Gömülü modda Pages Function (`functions/asistan/[[yol]].js`) yalnız asistanın
 * izinli alan adlarına `frame-ancestors` veriyor; burada da üst sayfanın kökeni bulunup
 * (postMessage el sıkışması → ancestorOrigins → referrer) sunucuya bildiriliyor, sunucu
 * izinli listeye göre reddediyor. Yükseklik ve kapama üst sayfaya postMessage ile.
 */

type Durum = 'yukleniyor' | 'hazir' | 'yok' | 'pasif' | 'izinsiz' | 'hata';

function sorgu(ad: string): string | null {
  try {
    return new URLSearchParams(window.location.search).get(ad);
  } catch {
    return null;
  }
}

function ustKokenTahmini(): string | null {
  try {
    const ao = (window.location as Location & { ancestorOrigins?: DOMStringList }).ancestorOrigins;
    if (ao && ao.length) return ao[0];
  } catch {
    /* yok */
  }
  try {
    if (document.referrer) return new URL(document.referrer).origin;
  } catch {
    /* yok */
  }
  return null;
}

function ustSayfayaGonder(veri: Record<string, unknown>): void {
  try {
    if (window.parent !== window) window.parent.postMessage({ tur: 'mk-asistan', ...veri }, '*');
  } catch {
    /* üst sayfa yok */
  }
}

/** Gömülü modda üst sayfanın gerçek kökeni: widget `merhaba` iletisiyle yanıt verir (en çok 600 ms beklenir). */
function elSikis(): Promise<string | null> {
  return new Promise((coz) => {
    if (window.parent === window) return coz(null);
    let bitti = false;
    const dinle = (e: MessageEvent) => {
      if (e.source !== window.parent || !e.data || typeof e.data !== 'object' || e.data.tur !== 'mk-asistan' || e.data.olay !== 'merhaba') return;
      bitti = true;
      window.removeEventListener('message', dinle);
      coz(e.origin && e.origin !== 'null' ? e.origin : null);
    };
    window.addEventListener('message', dinle);
    ustSayfayaGonder({ olay: 'hazir' });
    window.setTimeout(() => {
      if (bitti) return;
      window.removeEventListener('message', dinle);
      coz(null);
    }, 600);
  });
}

export default function AsistanSayfasi() {
  const { anahtar = '' } = useParams<{ anahtar: string }>();
  const gomulu = useMemo(() => sorgu('gomulu') === '1', []);
  const [durum, setDurum] = useState<Durum>('yukleniyor');
  const [yap, setYap] = useState<AcikYapilandirma | null>(null);
  const [dil, setDil] = useState<AsistanDili>('tr');
  const [t, setT] = useState<TFunction | null>(null);
  const [kaynak, setKaynak] = useState<string | null>(null);

  useEffect(() => {
    let iptal = false;
    (async () => {
      const koken = gomulu ? (await elSikis()) || ustKokenTahmini() : null;
      if (iptal) return;
      setKaynak(koken);
      const p = new URLSearchParams();
      const istenen = sorgu('dil');
      if (istenen) p.set('dil', istenen);
      if (gomulu) {
        p.set('gomulu', '1');
        if (koken) p.set('kaynak', koken);
      }
      let yeni: Durum = 'hazir';
      let veri: AcikYapilandirma | null = null;
      try {
        veri = await acikIstek<AcikYapilandirma>(`/api/v1/asistan/${encodeURIComponent(anahtar)}?${p.toString()}`);
      } catch (e) {
        const h = e instanceof AcikHata ? e : new AcikHata(0, 'ag');
        yeni = h.durum === 404 ? 'yok' : h.durum === 410 ? 'pasif' : h.durum === 403 ? 'izinsiz' : 'hata';
      }
      const secilen = dilSec(istenen, veri?.ui_dil, typeof navigator !== 'undefined' ? navigator.language : null);
      await asistanPaketiYukle(secilen).catch(() => undefined);
      if (iptal) return;
      setYap(veri);
      setDil(secilen);
      setT(() => i18n.getFixedT(secilen));
      setDurum(yeni);
    })();
    return () => {
      iptal = true;
    };
  }, [anahtar, gomulu]);

  // Belge dili/yönü, başlık, robots (her zaman noindex); gömülüde zemin saydam.
  useEffect(() => {
    const kok = document.documentElement;
    const eski = { lang: kok.lang, dir: kok.dir, bg: document.body.style.background, baslik: document.title };
    kok.lang = dil;
    kok.dir = dil === 'ar' ? 'rtl' : 'ltr';
    document.body.style.background = gomulu ? 'transparent' : '#eef0f4';
    let etiket = document.head.querySelector<HTMLMetaElement>('meta[name="robots"]');
    if (!etiket) {
      etiket = document.createElement('meta');
      etiket.name = 'robots';
      document.head.appendChild(etiket);
    }
    etiket.content = 'noindex, nofollow';
    return () => {
      kok.lang = eski.lang;
      kok.dir = eski.dir;
      document.body.style.background = eski.bg;
      document.title = eski.baslik;
    };
  }, [dil, gomulu]);
  useEffect(() => {
    if (yap?.ad) document.title = yap.ad;
  }, [yap]);

  const yukseklik = useCallback((px: number) => ustSayfayaGonder({ olay: 'yukseklik', deger: px }), []);
  const kapat = useCallback(() => ustSayfayaGonder({ olay: 'kapat' }), []);

  if (!t || durum === 'yukleniyor') {
    return (
      <div className="flex min-h-[60vh] items-center justify-center text-zinc-500" data-testid="asistan-yukleniyor">
        <Loader2 className="h-6 w-6 animate-spin" aria-hidden="true" />
      </div>
    );
  }

  if (durum !== 'hazir' || !yap) {
    const anahtarlar: Record<Exclude<Durum, 'yukleniyor' | 'hazir'>, string> = {
      yok: 'asistanSayfa.durum.yok',
      pasif: 'asistanSayfa.durum.pasif',
      izinsiz: 'asistanSayfa.durum.izinsiz',
      hata: 'asistanSayfa.durum.hata',
    };
    return (
      <div className={`flex ${gomulu ? 'h-[100dvh]' : 'min-h-screen'} items-center justify-center bg-white p-6 text-center text-zinc-700`} dir={dil === 'ar' ? 'rtl' : 'ltr'} data-testid="asistan-durum" data-durum={durum}>
        <div className="max-w-sm space-y-3">
          <Bot className="mx-auto h-8 w-8 text-zinc-400" aria-hidden="true" />
          <p className="text-sm">{t(anahtarlar[durum as keyof typeof anahtarlar] || 'asistanSayfa.durum.hata')}</p>
          {gomulu && (
            <button type="button" onClick={kapat} className="rounded-full border border-zinc-300 px-3 py-1 text-xs">
              {t('asistanSayfa.kapat')}
            </button>
          )}
        </div>
      </div>
    );
  }

  if (gomulu) {
    return (
      <div className="h-[100dvh]" data-testid="asistan-sayfasi" data-gomulu="1">
        <SohbetPenceresi t={t} dil={dil} yap={yap} gomulu kaynak={kaynak} onKapat={kapat} onYukseklik={yukseklik} depoAnahtari={`mk-asistan:${yap.anahtar}`} />
      </div>
    );
  }

  return (
    <div className="flex min-h-[100dvh] items-stretch justify-center sm:items-center sm:p-6" data-testid="asistan-sayfasi" data-gomulu="0">
      <div className="flex h-[100dvh] w-full max-w-xl flex-col overflow-hidden bg-white shadow-xl sm:h-[min(760px,92dvh)] sm:rounded-3xl">
        <SohbetPenceresi t={t} dil={dil} yap={yap} depoAnahtari={`mk-asistan:${yap.anahtar}`} />
      </div>
    </div>
  );
}
