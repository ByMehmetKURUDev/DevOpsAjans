import { useCallback, useEffect, useRef, useState } from 'react';
import type { TFunction } from 'i18next';
import { AlertTriangle, Camera, CameraOff, CheckCircle2, CloudOff, Loader2, Send, XCircle } from 'lucide-react';

import {
  KUYRUK_EN_COK,
  OkutmaHatasi,
  kuyrukOku,
  kuyrukYaz,
  saatYaz,
  tarihYaz,
  type KuyrukOgesi,
  type OkutmaIstemcisi,
  type OkutmaSonucu,
  type Sayac,
} from '@/lib/etkinlikOrtak';

/**
 * Faz 6E — kapı okutucu (görevli bağlantısı ve panel okutucusu aynı bileşen).
 *
 * * Kamera: tarayıcıda `BarcodeDetector` (QR) varsa arka kamera; yoksa yalnız elle kod girişi.
 *   Ek kütüphane yok (bilinçli: QR çözücü paketi eklenmedi). iOS Safari / masaüstü Firefox'ta
 *   `BarcodeDetector` yok → elle giriş.
 * * Sonuç büyük ve renkli: geçerli / zaten girdi (saat) / geçersiz / iptal / farklı etkinlik /
 *   ödeme bekliyor / etkinlik iptal.
 * * Çevrimdışı: ağ hatasında okutma yerel kuyruğa (en çok 50); bağlantı gelince sırayla gönderilir.
 *   Çift giriş sunucuda koşullu UPDATE ile engelli — kuyruktan gelen ikinci okutma "zaten girdi" olur.
 * * Sayaç 10 sn'de bir yoklanır (sekme görünürken).
 */

type Durum = 'yukleniyor' | 'hazir' | 'gecersiz' | 'suresi' | 'pasif' | 'yetki' | 'hata';
type Gosterilen = OkutmaSonucu | 'kuyrukta';

interface SonucKaydi {
  sonuc: Gosterilen;
  kod: string;
  ad: string | null;
  tur: string | null;
  giris: string | null;
  zaman: string;
  cevrimdisi: boolean;
}

const RENK: Record<Gosterilen, string> = {
  gecerli: 'bg-emerald-600 text-white',
  zaten_girdi: 'bg-amber-500 text-zinc-950',
  odeme_bekliyor: 'bg-amber-500 text-zinc-950',
  kuyrukta: 'bg-sky-600 text-white',
  gecersiz: 'bg-red-600 text-white',
  iptal: 'bg-red-600 text-white',
  farkli_etkinlik: 'bg-red-600 text-white',
  etkinlik_iptal: 'bg-red-600 text-white',
};

const YOKLAMA_MS = 10_000;
const AYNI_KOD_MS = 2500;

interface BarkodAlgilayici {
  detect(kaynak: HTMLVideoElement): Promise<{ rawValue: string }[]>;
}
type BarkodSinifi = { new (s: { formats: string[] }): BarkodAlgilayici; getSupportedFormats?: () => Promise<string[]> };

function barkodSinifi(): BarkodSinifi | null {
  const w = window as unknown as { BarcodeDetector?: BarkodSinifi };
  return typeof w.BarcodeDetector === 'function' && !!navigator.mediaDevices?.getUserMedia ? w.BarcodeDetector : null;
}

/**
 * `onek`: metin anahtarlarının ek paketi (varsayılan `etkinlikSayfa`). Faz 6K eğitim yoklaması aynı okutucuyu
 * `egitimSayfa` paketiyle kullanıyor (aynı `okut.*` anahtarları; öğrenci kodu / yoklama metinleri).
 */
export default function Okutucu({ istemci, t, dil, panelAdresi, onBaslik, onek = 'etkinlikSayfa' }: { istemci: OkutmaIstemcisi; t: TFunction; dil: string; panelAdresi?: string; onBaslik?: (b: string) => void; onek?: string }) {
  const [durum, setDurum] = useState<Durum>('yukleniyor');
  const [ozet, setOzet] = useState<{ baslik: string; baslangic: string; bitis: string; saat_dilimi: string } | null>(null);
  const [sayac, setSayac] = useState<Sayac | null>(null);
  const [kod, setKod] = useState('');
  const [sonuc, setSonuc] = useState<SonucKaydi | null>(null);
  const [gecmis, setGecmis] = useState<SonucKaydi[]>([]);
  const [kuyruk, setKuyruk] = useState<KuyrukOgesi[]>(() => kuyrukOku(istemci.anahtar));
  const [mesgul, setMesgul] = useState(false);
  const [kamera, setKamera] = useState<'kapali' | 'aciliyor' | 'acik' | 'izin_yok'>('kapali');
  const [kameraDestek, setKameraDestek] = useState(false);
  const video = useRef<HTMLVideoElement | null>(null);
  const akis = useRef<MediaStream | null>(null);
  const sonKod = useRef<{ kod: string; an: number }>({ kod: '', an: 0 });
  const calisiyor = useRef(false);
  const gonderiliyor = useRef(false);
  const tz = ozet?.saat_dilimi || 'Europe/Istanbul';

  // ---------------------------------------------------------------- açılış
  useEffect(() => {
    let iptal = false;
    istemci
      .ozet()
      .then((o) => {
        if (iptal) return;
        setOzet(o);
        setSayac(o.sayac);
        setDurum('hazir');
        onBaslik?.(o.baslik);
      })
      .catch((e) => {
        if (iptal) return;
        const h = e instanceof OkutmaHatasi ? e : new OkutmaHatasi(0, 'ag');
        setDurum(h.durum === 404 ? 'gecersiz' : h.durum === 410 ? (h.kod === 'etkinlik_pasif' ? 'pasif' : 'suresi') : h.durum === 401 || h.durum === 403 ? 'yetki' : 'hata');
      });
    const S = barkodSinifi();
    if (S) {
      if (typeof S.getSupportedFormats === 'function') {
        S.getSupportedFormats()
          .then((f) => !iptal && setKameraDestek(f.includes('qr_code')))
          .catch(() => undefined);
      } else setKameraDestek(true);
    }
    return () => {
      iptal = true;
    };
  }, [istemci, onBaslik]);

  // ---------------------------------------------------------------- sayaç yoklama
  useEffect(() => {
    if (durum !== 'hazir') return;
    const z = window.setInterval(() => {
      if (document.visibilityState !== 'visible') return;
      istemci
        .sayac()
        .then(setSayac)
        .catch(() => undefined);
    }, YOKLAMA_MS);
    return () => window.clearInterval(z);
  }, [durum, istemci]);

  const kaydet = useCallback((k: SonucKaydi, goster = true) => {
    if (goster) setSonuc(k);
    setGecmis((g) => [k, ...g].slice(0, 12));
    try {
      navigator.vibrate?.(k.sonuc === 'gecerli' ? 80 : [60, 60, 160]);
    } catch {
      /* titreşim yok */
    }
  }, []);

  const kuyrugaEkle = useCallback(
    (k: string, zaman: string) => {
      const yeni = [...kuyrukOku(istemci.anahtar), { kod: k, zaman }].slice(-KUYRUK_EN_COK);
      kuyrukYaz(istemci.anahtar, yeni);
      setKuyruk(yeni);
    },
    [istemci.anahtar]
  );

  // ---------------------------------------------------------------- kuyruğu gönder
  const kuyruguGonder = useCallback(async () => {
    if (gonderiliyor.current) return;
    let liste = kuyrukOku(istemci.anahtar);
    if (!liste.length) return;
    gonderiliyor.current = true;
    try {
      while (liste.length) {
        const oge = liste[0];
        try {
          const y = await istemci.okut(oge.kod, true, oge.zaman);
          setSayac(y.sayac);
          kaydet({ sonuc: y.sonuc, kod: y.bilet?.kod || oge.kod, ad: y.bilet?.ad ?? null, tur: y.bilet?.tur ?? null, giris: y.bilet?.giris_at ?? null, zaman: oge.zaman, cevrimdisi: true }, false);
        } catch (e) {
          // Ağ yoksa ya da hız sınırı: dur, sonra yeniden dene. Başka hata (bozuk kod): öğeyi düşür.
          if (!(e instanceof OkutmaHatasi) || e.durum === 0 || e.durum === 429 || e.durum >= 500) break;
        }
        liste = liste.slice(1);
        kuyrukYaz(istemci.anahtar, liste);
        setKuyruk(liste);
      }
    } finally {
      gonderiliyor.current = false;
    }
  }, [istemci, kaydet]);

  useEffect(() => {
    if (durum !== 'hazir') return;
    const cevrimici = () => void kuyruguGonder();
    window.addEventListener('online', cevrimici);
    const z = window.setInterval(() => {
      if (navigator.onLine !== false) void kuyruguGonder();
    }, 15_000);
    void kuyruguGonder();
    return () => {
      window.removeEventListener('online', cevrimici);
      window.clearInterval(z);
    };
  }, [durum, kuyruguGonder]);

  // ---------------------------------------------------------------- okut
  const okut = useCallback(
    async (ham: string) => {
      const deger = ham.trim();
      if (!deger || calisiyor.current) return;
      calisiyor.current = true;
      setMesgul(true);
      const zaman = new Date().toISOString();
      try {
        const y = await istemci.okut(deger, false, zaman);
        setSayac(y.sayac);
        kaydet({ sonuc: y.sonuc, kod: y.bilet?.kod || deger.slice(0, 24), ad: y.bilet?.ad ?? null, tur: y.bilet?.tur ?? null, giris: y.bilet?.giris_at ?? null, zaman: y.zaman || zaman, cevrimdisi: false });
        setKod('');
      } catch (e) {
        if (e instanceof OkutmaHatasi && e.durum === 0) {
          kuyrugaEkle(deger, zaman);
          kaydet({ sonuc: 'kuyrukta', kod: deger.slice(0, 24), ad: null, tur: null, giris: null, zaman, cevrimdisi: true });
          setKod('');
        } else if (e instanceof OkutmaHatasi && (e.durum === 404 || e.durum === 410)) {
          setDurum(e.durum === 404 ? 'gecersiz' : 'suresi');
        } else if (e instanceof OkutmaHatasi && (e.durum === 401 || e.durum === 403)) {
          setDurum('yetki');
        } else {
          kaydet({ sonuc: 'gecersiz', kod: deger.slice(0, 24), ad: null, tur: null, giris: null, zaman, cevrimdisi: false });
        }
      } finally {
        calisiyor.current = false;
        setMesgul(false);
      }
    },
    [istemci, kaydet, kuyrugaEkle]
  );

  // ---------------------------------------------------------------- kamera
  const kameraKapat = useCallback(() => {
    akis.current?.getTracks().forEach((x) => x.stop());
    akis.current = null;
    if (video.current) video.current.srcObject = null;
    setKamera((k) => (k === 'izin_yok' ? k : 'kapali'));
  }, []);

  useEffect(() => () => kameraKapat(), [kameraKapat]);

  const kameraAc = async () => {
    const S = barkodSinifi();
    if (!S) return;
    setKamera('aciliyor');
    try {
      const a = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false });
      akis.current = a;
      if (video.current) {
        video.current.srcObject = a;
        await video.current.play().catch(() => undefined);
      }
      setKamera('acik');
      const algilayici = new S({ formats: ['qr_code'] });
      const dongu = async () => {
        if (!akis.current) return;
        try {
          if (video.current && video.current.readyState >= 2 && !calisiyor.current) {
            const bulunan = await algilayici.detect(video.current);
            const deger = bulunan[0]?.rawValue;
            const an = Date.now();
            if (deger && !(deger === sonKod.current.kod && an - sonKod.current.an < AYNI_KOD_MS)) {
              sonKod.current = { kod: deger, an };
              await okut(deger);
            }
          }
        } catch {
          /* tek kare hatası */
        }
        if (akis.current) window.setTimeout(() => void dongu(), 250);
      };
      void dongu();
    } catch {
      akis.current = null;
      setKamera('izin_yok');
    }
  };

  // ---------------------------------------------------------------- görünüm
  if (durum === 'yukleniyor') {
    return (
      <div className="flex min-h-[60vh] items-center justify-center" data-testid="etkinlik-okutucu-yukleniyor">
        <Loader2 className="h-8 w-8 animate-spin text-zinc-400" aria-label={t(`${onek}.yukleniyor`)} />
      </div>
    );
  }
  if (durum !== 'hazir') {
    const metin =
      durum === 'gecersiz' ? 'okut.gecersizBaglanti' : durum === 'suresi' ? 'okut.suresiDoldu' : durum === 'pasif' ? 'okut.pasif' : durum === 'yetki' ? 'okut.yetki' : 'okut.hata';
    return (
      <div className="mx-auto max-w-md px-4 py-16 text-center" data-testid="etkinlik-okutucu-hata" data-durum={durum}>
        <AlertTriangle className="mx-auto mb-3 h-10 w-10 text-amber-400" aria-hidden="true" />
        <p className="text-lg">{t(`${onek}.${metin}`)}</p>
        {durum === 'yetki' && panelAdresi && (
          <a href={panelAdresi} className="mt-4 inline-block rounded-lg bg-white/10 px-4 py-2 text-sm hover:bg-white/20">
            {t(`${onek}.okut.panelGiris`)}
          </a>
        )}
      </div>
    );
  }

  const ikon = (s: Gosterilen) =>
    s === 'gecerli' ? <CheckCircle2 className="h-12 w-12" aria-hidden="true" /> : s === 'kuyrukta' ? <CloudOff className="h-12 w-12" aria-hidden="true" /> : s === 'zaten_girdi' || s === 'odeme_bekliyor' ? <AlertTriangle className="h-12 w-12" aria-hidden="true" /> : <XCircle className="h-12 w-12" aria-hidden="true" />;

  return (
    <div className="mx-auto w-full max-w-lg px-3 py-4 sm:py-6" data-testid="etkinlik-okutucu">
      <header className="mb-3">
        <h1 className="text-lg font-semibold leading-tight" data-testid="etkinlik-okutucu-baslik">
          {ozet?.baslik}
        </h1>
        {ozet && (
          <p className="text-sm text-zinc-400">
            {tarihYaz(ozet.baslangic, tz, dil, { dateStyle: 'medium' })} · <span dir="ltr">{saatYaz(ozet.baslangic, tz, dil)}</span>
          </p>
        )}
      </header>

      {sayac && (
        <div className="mb-3 flex items-center justify-between rounded-2xl bg-white/5 px-4 py-3" aria-live="polite">
          <span className="text-sm text-zinc-300">{t(`${onek}.okut.girenler`)}</span>
          <span className="text-2xl font-bold tabular-nums" data-testid="etkinlik-okutucu-sayac">
            {sayac.giren} / {sayac.toplam}
          </span>
        </div>
      )}

      <div
        className={`mb-3 flex min-h-[8.5rem] flex-col items-center justify-center gap-1 rounded-2xl px-4 py-5 text-center ${sonuc ? RENK[sonuc.sonuc] : 'bg-white/5 text-zinc-400'}`}
        role="status"
        aria-live="assertive"
        data-testid="etkinlik-okut-sonuc"
        data-sonuc={sonuc?.sonuc || ''}
      >
        {sonuc ? (
          <>
            {ikon(sonuc.sonuc)}
            <div className="text-2xl font-extrabold uppercase tracking-wide sm:text-3xl">{t(`${onek}.okut.sonuc.${sonuc.sonuc}`)}</div>
            {sonuc.sonuc === 'zaten_girdi' && sonuc.giris && <div className="text-base font-semibold">{t(`${onek}.okut.girisSaati`, { saat: saatYaz(sonuc.giris, tz, dil) })}</div>}
            {(sonuc.ad || sonuc.tur) && <div className="text-base">{[sonuc.ad, sonuc.tur].filter(Boolean).join(' · ')}</div>}
            <code className="text-xs opacity-80">{sonuc.kod}</code>
          </>
        ) : (
          <p className="text-sm">{t(`${onek}.okut.bekliyor`)}</p>
        )}
      </div>

      {kameraDestek ? (
        <div className="mb-3">
          <video ref={video} className={`aspect-square w-full rounded-2xl bg-black object-cover ${kamera === 'acik' ? '' : 'hidden'}`} muted playsInline aria-label={t(`${onek}.okut.kamera`)} />
          {kamera === 'acik' ? (
            <button type="button" onClick={kameraKapat} className="mt-2 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-white/10 px-4 py-3 text-sm font-medium hover:bg-white/20">
              <CameraOff className="h-5 w-5" aria-hidden="true" />
              {t(`${onek}.okut.kameraKapat`)}
            </button>
          ) : (
            <button
              type="button"
              onClick={() => void kameraAc()}
              disabled={kamera === 'aciliyor'}
              className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-purple-600 px-4 py-3 text-base font-semibold text-white hover:bg-purple-500 disabled:opacity-60"
              data-testid="etkinlik-kamera-ac"
            >
              {kamera === 'aciliyor' ? <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" /> : <Camera className="h-5 w-5" aria-hidden="true" />}
              {t(`${onek}.okut.kameraAc`)}
            </button>
          )}
          {kamera === 'izin_yok' && <p className="mt-2 text-sm text-amber-300">{t(`${onek}.okut.kameraIzin`)}</p>}
        </div>
      ) : (
        <p className="mb-3 rounded-xl bg-white/5 px-3 py-2 text-sm text-zinc-300" data-testid="etkinlik-kamera-yok">
          {t(`${onek}.okut.kameraYok`)}
        </p>
      )}

      <form
        className="mb-4 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void okut(kod);
        }}
      >
        <label className="sr-only" htmlFor="etkinlik-okut-kod">
          {t(`${onek}.okut.kod`)}
        </label>
        <input
          id="etkinlik-okut-kod"
          value={kod}
          onChange={(e) => setKod(e.target.value.toUpperCase())}
          placeholder={t(`${onek}.okut.kodIpucu`)}
          autoCapitalize="characters"
          autoComplete="off"
          spellCheck={false}
          inputMode="text"
          maxLength={120}
          dir="ltr"
          className="min-w-0 flex-1 rounded-xl border border-white/15 bg-white/5 px-3 py-3 font-mono text-lg tracking-widest text-white placeholder:text-sm placeholder:tracking-normal placeholder:text-zinc-500"
          data-testid="etkinlik-okut-kod"
        />
        <button type="submit" disabled={mesgul || !kod.trim()} className="inline-flex items-center gap-1.5 rounded-xl bg-white px-4 py-3 font-semibold text-zinc-900 disabled:opacity-50" data-testid="etkinlik-okut-gonder">
          {mesgul ? <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" /> : <Send className="h-5 w-5 rtl:rotate-180" aria-hidden="true" />}
          {t(`${onek}.okut.denetle`)}
        </button>
      </form>

      {kuyruk.length > 0 && (
        <div className="mb-4 flex items-center justify-between gap-2 rounded-xl border border-sky-400/40 bg-sky-500/10 px-3 py-2 text-sm" data-testid="etkinlik-okut-kuyruk">
          <span className="inline-flex items-center gap-1.5">
            <CloudOff className="h-4 w-4" aria-hidden="true" />
            {t(`${onek}.okut.kuyruk`, { sayi: kuyruk.length })}
          </span>
          <button type="button" onClick={() => void kuyruguGonder()} className="rounded-lg bg-white/10 px-3 py-1 hover:bg-white/20">
            {t(`${onek}.okut.kuyrukGonder`)}
          </button>
        </div>
      )}

      <section>
        <h2 className="mb-2 text-sm font-semibold text-zinc-300">{t(`${onek}.okut.sonOkutmalar`)}</h2>
        {gecmis.length === 0 ? (
          <p className="text-sm text-zinc-500">{t(`${onek}.okut.bos`)}</p>
        ) : (
          <ul className="space-y-1 text-sm" data-testid="etkinlik-okut-gecmis">
            {gecmis.map((g, i) => (
              <li key={`${g.zaman}-${i}`} className="flex items-center gap-2 rounded-lg bg-white/5 px-3 py-1.5">
                <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${RENK[g.sonuc].split(' ')[0]}`} aria-hidden="true" />
                <span className="tabular-nums text-zinc-400" dir="ltr">
                  {saatYaz(g.zaman, tz, dil)}
                </span>
                <span className="truncate">{t(`${onek}.okut.sonuc.${g.sonuc}`)}</span>
                <span className="ms-auto truncate text-zinc-400">{g.ad || g.kod}</span>
                {g.cevrimdisi && <CloudOff className="h-3.5 w-3.5 shrink-0 text-sky-300" aria-label={t(`${onek}.okut.cevrimdisi`)} />}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
