import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Download, RefreshCw, Wifi, WifiOff, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useCevrimici, useUygulamaYukleme } from '@/lib/uygulamaKabugu';

/**
 * Faz 7M — panellerin mobil kabuğu: yükleme düğmesi, çevrimdışı şeridi ve
 * çevrimdışı iskelet. Bu dosya tembel yüklenir (`lib/uygulamaKabugu.ts`),
 * metinler ek paket `panelKabugu` › `uygulama`.
 */

const A = 'panelKabugu.uygulama';

/**
 * Panel başlığında küçük "Uygulama olarak yükle" düğmesi. Tarayıcı yüklemeyi
 * sunuyorsa onu açar; iPhone/iPad'de kısa "Ana Ekrana Ekle" tarifini gösterir.
 * Zaten uygulama olarak açıksa ya da "×" ile gizlendiyse (30 gün) hiç çizilmez.
 */
export function UygulamaYukle() {
  const { t } = useTranslation();
  const { durum, yukle, gizle } = useUygulamaYukleme();
  const [tarifAcik, setTarifAcik] = useState(false);
  // Tarif kartı düğmenin hangi yanına açılsın: başlangıç yönünde yer varsa oraya
  // (dar ekranda düğme satır başında), yoksa sona doğru (geniş ekranda başlığın ucunda).
  const kutu = useRef<HTMLDivElement>(null);
  const [basaHizali, setBasaHizali] = useState(true);
  const tarifiAcKapat = () => {
    const r = kutu.current?.getBoundingClientRect();
    if (r) {
      const yer = document.documentElement.dir === 'rtl' ? r.right : window.innerWidth - r.left;
      setBasaHizali(yer >= 272);
    }
    setTarifAcik((acik) => !acik);
  };

  useEffect(() => {
    if (!tarifAcik) return;
    const tus = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setTarifAcik(false);
    };
    window.addEventListener('keydown', tus);
    return () => window.removeEventListener('keydown', tus);
  }, [tarifAcik]);

  if (durum === 'gizli') return null;
  return (
    <div ref={kutu} className="relative inline-flex items-center gap-0.5" data-testid="uygulama-yukle" data-durum={durum}>
      <button
        type="button"
        onClick={() => (durum === 'istem' ? void yukle() : tarifiAcKapat())}
        title={t(`${A}.yukleAciklama`)}
        aria-expanded={durum === 'ios' ? tarifAcik : undefined}
        className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-white/10 hover:text-foreground"
        data-testid="uygulama-yukle-dugme"
      >
        <Download className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        {t(`${A}.yukle`)}
      </button>
      <button
        type="button"
        onClick={gizle}
        aria-label={t(`${A}.gizle`)}
        title={t(`${A}.gizle`)}
        className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-white/10 hover:text-foreground"
        data-testid="uygulama-yukle-gizle"
      >
        <X className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
      {tarifAcik && (
        <div
          role="dialog"
          aria-label={t(`${A}.iosBaslik`)}
          className={`absolute ${basaHizali ? 'start-0' : 'end-0'} top-full z-40 mt-2 w-64 rounded-2xl border border-white/10 bg-background/95 p-4 text-sm shadow-xl backdrop-blur`}
          data-testid="uygulama-yukle-ios"
        >
          <p className="mb-2 font-semibold">{t(`${A}.iosBaslik`)}</p>
          <ol className="list-decimal space-y-1 ps-5 text-muted-foreground">
            <li>{t(`${A}.iosAdim1`)}</li>
            <li>{t(`${A}.iosAdim2`)}</li>
            <li>{t(`${A}.iosAdim3`)}</li>
          </ol>
          <p className="mt-3 text-xs text-muted-foreground">{t(`${A}.iosNot`)}</p>
          <div className="mt-3 flex justify-end">
            <Button type="button" size="sm" variant="outline" onClick={() => setTarifAcik(false)}>
              {t(`${A}.tamam`)}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Bağlantı yokken ekranın altında ince uyarı şeridi; bağlantı gelince kısa
 * bir "geri geldi" notu gösterip kaybolur. `zorla`: panel çevrimdışı açıldı.
 */
export function CevrimdisiSerit({ zorla = false }: { zorla?: boolean }) {
  const { t } = useTranslation();
  const cevrimici = useCevrimici();
  const onceki = useRef(cevrimici);
  const [geriGeldi, setGeriGeldi] = useState(false);

  useEffect(() => {
    const dondu = cevrimici && !onceki.current;
    onceki.current = cevrimici;
    if (!dondu) return;
    setGeriGeldi(true);
    const zamanlayici = window.setTimeout(() => setGeriGeldi(false), 3000);
    return () => window.clearTimeout(zamanlayici);
  }, [cevrimici]);

  const cevrimdisi = zorla || !cevrimici;
  if (!cevrimdisi && !geriGeldi) return null;
  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="cevrimdisi-serit"
      data-durum={cevrimdisi ? 'cevrimdisi' : 'geri-geldi'}
      className="pointer-events-none fixed inset-x-0 bottom-0 z-[60] flex justify-center px-4"
      // iPhone'da ana ekran çubuğunun üstünde kalsın (satır içi stil: herkese açık CSS'e yeni sınıf eklemesin).
      style={{ paddingBottom: 'max(0.75rem, env(safe-area-inset-bottom))' }}
    >
      <p
        className={`pointer-events-auto inline-flex max-w-xl items-center gap-2 rounded-2xl border bg-background/95 px-4 py-2 text-xs shadow-lg backdrop-blur ${
          cevrimdisi ? 'border-amber-400/30 text-amber-100' : 'border-emerald-400/30 text-emerald-100'
        }`}
      >
        {cevrimdisi ? (
          <WifiOff className="h-4 w-4 shrink-0" aria-hidden="true" />
        ) : (
          <Wifi className="h-4 w-4 shrink-0" aria-hidden="true" />
        )}
        {cevrimdisi ? t(`${A}.cevrimdisi`) : t(`${A}.geriGeldi`)}
      </p>
    </div>
  );
}

/**
 * Panel bağlantısız açılınca (servis çalışanının sakladığı iskelet) giriş
 * ekranı yerine gösterilir: başlık, bölüm yer tutucuları, açıklama ve
 * "Yeniden dene". Bağlantı gelince panel kendiliğinden yüklenir.
 */
export function CevrimdisiIskelet({ ust, onYenidenDene }: { ust: string; onYenidenDene: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16" data-testid="panel-iskeleti">
      <div className="mb-10">
        <p className="text-xs uppercase tracking-[0.3em] text-purple-400 mb-2">{ust}</p>
        <h1 className="text-4xl md:text-5xl font-bold">
          {t('ui.controlCenter')} <span className="gradient-text">{t('ui.controlCenterHighlight')}</span>
        </h1>
      </div>
      <div className="mb-8 flex gap-2 overflow-hidden border-b border-white/10 pb-3" aria-hidden="true">
        {[24, 20, 28, 18, 22].map((g, i) => (
          <span key={i} className="h-8 shrink-0 rounded-full bg-white/5" style={{ width: `${g * 4}px` }} />
        ))}
      </div>
      <div className="cam-kart max-w-xl rounded-2xl border border-white/10 bg-white/[0.03] p-6">
        <p className="flex items-center gap-2 font-semibold">
          <WifiOff className="h-5 w-5 text-amber-300" aria-hidden="true" />
          {t(`${A}.iskeletBaslik`)}
        </p>
        <p className="mt-2 text-sm text-muted-foreground">{t(`${A}.iskeletMetin`)}</p>
        <Button type="button" size="sm" variant="outline" className="mt-4 gap-2" onClick={onYenidenDene} data-testid="panel-iskeleti-yenile">
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          {t(`${A}.yenidenDene`)}
        </Button>
      </div>
      <CevrimdisiSerit zorla />
    </div>
  );
}
