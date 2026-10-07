import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Download, Loader2, Lock, X } from 'lucide-react';
import { toast } from 'sonner';

import KartGorunumu, { type FormSonucu, type FormVerisi } from '@/components/kartvizit/KartGorunumu';
import '@/components/kartvizit/kartvizit.css';
import { MarkaBasligi, rozetGorunur } from '@/components/marka/MarkaParcalari';
import {
  AcikHata,
  apiAdresi,
  cevirmen,
  isaretGonder,
  kartGetir,
  kartMesaj,
  kartParola,
  markaliTema,
  metinleriYukle,
  SABLONLAR,
  temaStili,
  yaziTipiYukle,
  type AcikKart,
  type AcikTema,
  type Cevirmen,
} from '@/lib/kartvizitAcik';
import type { AcikMarka } from '@/lib/marka';

/**
 * Faz 4K — herkese açık dijital kartvizit: `/kart/<slug>` (ve değişmez kodla
 * `/kart/<kod>` — QR; adres çubuğu okunaklı slug'a çevriliyor).
 *
 * Site düzeni (üst menü/alt bilgi) yok: tek sütun, mobil öncelikli, kartın kendi
 * dili ve teması. Prerender edilmiyor; paylaşım önizlemesini (og:*) Pages
 * Function yazıyor (`functions/kart/[slug].js`). Varsayılan noindex; kart
 * sahibi "arama motorlarında görünsün" dediyse robots etiketi eklenmiyor.
 *
 * Parolalı kart: doğru parolayla 2 saatlik imzalı jeton (oturum deposunda);
 * vCard / QR / form / olay istekleri onu taşıyor.
 *
 * Faz 4L — marka teması: kartın kendi teması varsayılandaysa hesabın markası (zemin, ana
 * renk, köşe, yazı tipi; kartta logo yoksa marka logosu) uygulanıyor; kartın özel teması
 * varsa o öncelikli (`marka.sayfa_ozel`). Yüklenirken zemin Pages Function'ın sunucuda
 * yazdığı `--marka-ilk-zemin` (ilk boyama ile aynı renk — sıçrama yok).
 */

type Durum = 'yukleniyor' | 'aktif' | 'kilitli' | 'yok' | 'pasif' | 'hata';

function jetonOku(slug: string): string | null {
  try {
    return sessionStorage.getItem(`kart-jeton:${slug}`);
  } catch {
    return null;
  }
}
function jetonYaz(slug: string, jeton: string | null): void {
  try {
    if (jeton) sessionStorage.setItem(`kart-jeton:${slug}`, jeton);
    else sessionStorage.removeItem(`kart-jeton:${slug}`);
  } catch {
    /* depolama yok */
  }
}

const VARSAYILAN_TEMA: AcikTema = { sablon: 'gece', renk: '#a855f7', yazi_tipi: 'jakarta', kose: 'yumusak' };

export default function KartSayfasi() {
  const { slug = '' } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const { i18n } = useTranslation();
  const [durum, setDurum] = useState<Durum>('yukleniyor');
  const [kart, setKart] = useState<AcikKart | null>(null);
  const [kilit, setKilit] = useState<{ dil: string; tema: AcikTema; slug: string; marka?: AcikMarka } | null>(null);
  const [jeton, setJeton] = useState<string | null>(() => jetonOku(slug));
  const [m, setM] = useState<Cevirmen>(() => cevirmen(null));
  const [qrAcik, setQrAcik] = useState(false);
  const [deneme, setDeneme] = useState(0);
  const dil = kart?.dil || kilit?.dil || (i18n.language || 'tr');
  const adres = kart?.slug || kilit?.slug || slug;

  useEffect(() => {
    let iptal = false;
    yaziTipiYukle(dil);
    void metinleriYukle(dil).then((s) => {
      if (!iptal) setM(() => cevirmen(s));
    });
    return () => {
      iptal = true;
    };
  }, [dil]);

  useEffect(() => {
    let iptal = false;
    setDurum('yukleniyor');
    const j = jetonOku(slug);
    kartGetir(slug, j)
      .then((y) => {
        if (iptal) return;
        if (y.durum === 'yonlendir') {
          navigate(`/kart/${encodeURIComponent(y.yonlendir)}`, { replace: true });
          return;
        }
        if (y.durum === 'kilitli') {
          if (j) jetonYaz(slug, null);
          setJeton(null);
          setKilit({ dil: y.dil, tema: y.tema, slug: y.slug, marka: y.marka });
          setDurum('kilitli');
          return;
        }
        setKart(y);
        setDurum('aktif');
        // Değişmez kodla (QR) açıldıysa adres çubuğunda okunaklı adres dursun (yeniden yükleme yok).
        if (y.slug && y.slug !== slug) {
          window.history.replaceState(window.history.state, '', `/kart/${encodeURIComponent(y.slug)}${window.location.search}`);
          if (j) jetonYaz(y.slug, j);
        }
      })
      .catch((e: unknown) => {
        if (iptal) return;
        const d = e instanceof AcikHata ? e.durum : 0;
        setDurum(d === 404 ? 'yok' : d === 410 ? 'pasif' : 'hata');
      });
    return () => {
      iptal = true;
    };
  }, [slug, navigate, deneme]);

  // Belge başlığı ve robots: varsayılan noindex (kart sahibi izin verdiyse kalkıyor).
  const index = durum === 'aktif' && !!kart?.index;
  useEffect(() => {
    if (index) return;
    const etiket = document.createElement('meta');
    etiket.name = 'robots';
    etiket.content = 'noindex, nofollow';
    document.head.appendChild(etiket);
    return () => etiket.remove();
  }, [index]);
  useEffect(() => {
    const onceki = document.title;
    if (kart) document.title = [kart.ad_soyad, [kart.unvan, kart.sirket].filter(Boolean).join(' · ')].filter(Boolean).join(' — ');
    else if (durum === 'kilitli') document.title = m('kilit.baslik') || onceki;
    return () => {
      document.title = onceki;
    };
  }, [kart, durum, m]);

  const olay = useCallback(
    (veri: Record<string, unknown>) => isaretGonder(`/api/v1/kart/${encodeURIComponent(adres)}/olay`, { ...veri, j: jeton }),
    [adres, jeton]
  );

  const paylas = async () => {
    if (!kart) return;
    olay({ tur: 'paylas' });
    const metin = [kart.unvan, kart.sirket].filter(Boolean).join(' · ');
    if (typeof navigator.share === 'function') {
      try {
        await navigator.share({ title: kart.ad_soyad, text: metin || kart.ad_soyad, url: kart.kart_adresi });
      } catch {
        /* vazgeçildi */
      }
      return;
    }
    try {
      await navigator.clipboard.writeText(kart.kart_adresi);
      toast.success(m('baglantiKopyalandi'));
    } catch {
      toast.error(m('kopyalanamadi'));
    }
  };

  const gonder = async (v: FormVerisi): Promise<FormSonucu> => {
    if (!kart) return 'hata';
    try {
      await kartMesaj(kart.slug, { ...v, form_jetonu: kart.form.jeton, j: jeton });
      return 'tamam';
    } catch (e) {
      if (e instanceof AcikHata) {
        if (e.durum === 429) return 'cok_hizli';
        if (e.kod === 'iletisim_gerekli') return 'iletisim';
      }
      return 'hata';
    }
  };

  if (durum === 'aktif' && kart) {
    const mt = markaliTema(kart.tema, kart.marka, kart.dil);
    const gorunen = mt.ek ? { ...kart, tema: mt.tema } : kart;
    return (
      <main className="min-h-screen" style={{ ...temaStili(gorunen.tema, kart.dil), ...mt.ek }} data-marka-uygulandi={mt.ek ? '1' : '0'}>
        <KartGorunumu
          kart={gorunen}
          m={m}
          jeton={jeton}
          stil={mt.ek}
          rozet={rozetGorunur(kart.marka)}
          ust={mt.ek && !kart.logo ? <MarkaBasligi marka={kart.marka} className="justify-center" /> : undefined}
          onTik={(hedef) => olay({ tur: 'tik', hedef })}
          onPaylas={() => void paylas()}
          onQr={() => setQrAcik(true)}
          onGonder={gonder}
        />
        {qrAcik && <QrPenceresi kart={gorunen} m={m} jeton={jeton} onKapat={() => setQrAcik(false)} />}
      </main>
    );
  }

  if (durum === 'kilitli' && kilit) {
    return (
      <ParolaEkrani
        tema={kilit.tema}
        marka={kilit.marka}
        dil={kilit.dil}
        m={m}
        onAc={async (parola) => {
          const y = await kartParola(kilit.slug, parola);
          if (y.jeton) jetonYaz(kilit.slug, y.jeton);
          setJeton(y.jeton);
          setKart(y.kart);
          setDurum('aktif');
        }}
      />
    );
  }

  const stil = temaStili(VARSAYILAN_TEMA, dil);
  if (durum === 'yukleniyor') {
    // Faz 4L: sunucunun ilk boyama zemini (kartın/markanın rengi) varsa onunla — sıçrama yok.
    const ilk = { ...stil, background: `var(--marka-ilk-zemin, ${SABLONLAR.gece.zemin})`, color: 'var(--marka-ilk-metin, #f4f0fb)' };
    return (
      <main className="flex min-h-screen items-center justify-center" style={ilk} aria-busy="true">
        <Loader2 className="h-7 w-7 animate-spin opacity-70" aria-hidden="true" />
      </main>
    );
  }
  const anahtar = durum === 'yok' ? 'yok' : durum === 'pasif' ? 'pasif' : 'hata';
  return (
    <main className="flex min-h-screen items-center justify-center px-4" style={stil} lang={dil} dir={dil === 'ar' ? 'rtl' : 'ltr'}>
      <div className="kv-yuzey kv-durum-kart" data-testid={`kart-durum-${anahtar}`}>
        <h1 className="text-lg font-semibold kv-baslik">{m(`${anahtar}.baslik`)}</h1>
        <p className="mt-2 text-sm kv-soluk">{m(`${anahtar}.aciklama`)}</p>
        {durum === 'hata' && (
          <button type="button" onClick={() => setDeneme((x) => x + 1)} className="kv-dugme-ana mx-auto mt-4">
            {m('hata.yenile')}
          </button>
        )}
      </div>
    </main>
  );
}

function ParolaEkrani({
  tema,
  marka,
  dil,
  m,
  onAc,
}: {
  tema: AcikTema;
  marka?: AcikMarka;
  dil: string;
  m: Cevirmen;
  onAc: (parola: string) => Promise<void>;
}) {
  const mt = markaliTema(tema, marka, dil);
  const [parola, setParola] = useState('');
  const [hata, setHata] = useState<string | null>(null);
  const [mesgul, setMesgul] = useState(false);
  const gonder = async (e: FormEvent) => {
    e.preventDefault();
    if (!parola) return;
    setMesgul(true);
    setHata(null);
    try {
      await onAc(parola);
    } catch (h) {
      setHata(h instanceof AcikHata && h.durum === 429 ? m('kilit.cokDeneme') : m('kilit.yanlis'));
    } finally {
      setMesgul(false);
    }
  };
  return (
    <main className="flex min-h-screen items-center justify-center px-4" style={{ ...temaStili(mt.tema, dil), ...mt.ek }} lang={dil} dir={dil === 'ar' ? 'rtl' : 'ltr'}>
      <form
        onSubmit={gonder}
        className="kv-yuzey kv-durum-kart space-y-3"
        data-testid="kart-kilit"
      >
        <div className="kv-ikon-zemin mx-auto flex h-12 w-12 items-center justify-center rounded-full" aria-hidden="true">
          <Lock className="h-5 w-5" />
        </div>
        <h1 className="text-lg font-semibold kv-baslik">{m('kilit.baslik')}</h1>
        <p className="text-sm kv-soluk">{m('kilit.aciklama')}</p>
        <label className="block text-start">
          <span className="sr-only">{m('kilit.parola')}</span>
          <input
            type="password"
            autoComplete="current-password"
            value={parola}
            onChange={(e) => setParola(e.target.value)}
            placeholder={m('kilit.parola')}
            className="kv-girdi"
            data-testid="kart-parola"
            maxLength={128}
          />
        </label>
        {hata && (
          <p className="text-sm font-medium text-red-500" role="alert">
            {hata}
          </p>
        )}
        <button
          type="submit"
          disabled={mesgul || !parola}
          className="kv-dugme-ana w-full"
          data-testid="kart-parola-ac"
        >
          {mesgul && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
          {m('kilit.ac')}
        </button>
      </form>
    </main>
  );
}

function QrPenceresi({ kart, m, jeton, onKapat }: { kart: AcikKart; m: Cevirmen; jeton: string | null; onKapat: () => void }) {
  const kapat = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    kapat.current?.focus();
    const tus = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onKapat();
    };
    window.addEventListener('keydown', tus);
    return () => window.removeEventListener('keydown', tus);
  }, [onKapat]);
  const adres = apiAdresi(kart.qr_adresi) + (jeton ? `?j=${encodeURIComponent(jeton)}` : '');
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="kv-qr-baslik"
      onClick={onKapat}
      style={temaStili(kart.tema, kart.dil)}
      lang={kart.dil}
      dir={kart.dil === 'ar' ? 'rtl' : 'ltr'}
    >
      <div
        className="kv-cerceve w-full max-w-xs p-5 text-center shadow-2xl"
        style={{ borderRadius: 'var(--kv-yaricap)', background: '#ffffff', color: '#0f172a' }}
        onClick={(e) => e.stopPropagation()}
        data-testid="kart-qr-pencere"
      >
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 id="kv-qr-baslik" className="text-base font-semibold kv-baslik">
            {m('qrBaslik')}
          </h2>
          <button ref={kapat} type="button" onClick={onKapat} className="kv-kapat flex h-9 w-9 items-center justify-center rounded-full" aria-label={m('kapat')}>
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>
        <img src={adres} alt={m('qrBaslik')} width={240} height={240} className="kv-qr-img mx-auto" />
        <p className="kv-qr-not mt-2 text-xs">{m('qrAciklama')}</p>
        <a
          href={adres}
          download={`kartvizit-${kart.slug}-qr.png`}
          className="kv-dugme-ana mt-3"
          data-testid="kart-qr-indir"
        >
          <Download className="h-4 w-4" aria-hidden="true" />
          {m('qrIndir')}
        </a>
      </div>
    </div>
  );
}
