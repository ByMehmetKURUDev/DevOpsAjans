import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import {
  AlertCircle,
  ArrowDown,
  ArrowLeft,
  Check,
  CheckCheck,
  Download,
  Loader2,
  Paperclip,
  Pencil,
  RotateCcw,
  Send,
  Trash2,
  X,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import type { TFunction } from 'i18next';

import { Button } from '@/components/ui/button';
import { useYoklama } from '@/hooks/useYoklama';
import {
  MesajHatasi,
  adresiIndir,
  ekIndirmeAdresi,
  ekYukle,
  mesajDuzenle,
  mesajGonder,
  mesajSil,
  mesajlariGetir,
  okunduIsaretle,
  type Ek,
  type Mesaj,
  type Taraf,
} from '@/lib/mesajlar';
import BaglantiliMetin from './BaglantiliMetin';

/** Sohbet açıkken yoklama aralığı (4–5 sn). */
export const SOHBET_ARALIGI = 4500;
const EK_SINIRI = 5;
const METIN_SINIRI = 5000;

/** Sunucunun hata kodunu seçili dilde metne çevirir. */
export function hataMetni(t: TFunction, e: unknown): string {
  if (e instanceof MesajHatasi) {
    return t(`mesajlar.hata.${e.kod}`, { ...e.ek, defaultValue: t('mesajlar.hata.genel') }) as string;
  }
  return t('mesajlar.hata.genel');
}

function gizliMi(): boolean {
  try {
    return document.visibilityState === 'hidden';
  } catch {
    return false;
  }
}

function birlestir(eski: Mesaj[], yeni: Mesaj[]): Mesaj[] {
  const harita = new Map<number, Mesaj>();
  for (const m of eski) harita.set(m.id, m);
  for (const m of yeni) harita.set(m.id, m);
  return [...harita.values()].sort((a, b) => a.id - b.id);
}

function ayniGun(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

interface Bekleyen {
  gecici: string;
  metin: string;
  ekler: Ek[];
  durum: 'gonderiliyor' | 'hata';
  hata?: string;
}

interface Props {
  taraf: Taraf;
  konusmaId: number;
  baslik: ReactNode;
  altBaslik?: ReactNode;
  /** Mobilde listeye dönüş (tek sütun). */
  onGeri?: () => void;
  /** Gönderme / okundu / silme sonrası (liste ve rozet tazelensin). */
  onDegisti?: () => void;
  ustAraclar?: ReactNode;
  /** Yönetici: mesaj altı araçlar (talep / görev). */
  mesajAraclari?: (m: Mesaj) => ReactNode;
  /** Yönetici: yazma kutusunun üstü (hazır cevap). `ekle` metni kutuya ekler. */
  yazmaAraclari?: (ekle: (metin: string) => void) => ReactNode;
}

/**
 * Bir konuşmanın mesaj akışı + yazma kutusu. Hem müşteri hem yönetici
 * panelinde aynı bileşen: iki taraf da aynı akışı görsün.
 *
 * * İlk açılışta son 50 mesaj; yukarı kaydırınca eskiler (`once=`).
 * * `useYoklama` ile 4,5 sn'de bir `sonra=<son id>` — yalnız yeniler. Eski bir
 *   mesaj düzenlenir/silinirse konuşmanın `degisiklik` sayacı artıyor; o zaman
 *   son pencere yeniden çekiliyor.
 * * Görünür sekmede yeni mesaj gelince "okundu" işaretleniyor.
 * * Gönderim iyimser: balon hemen görünür (gönderiliyor), hata olursa
 *   "yeniden dene / kaldır".
 * * Metin DÜZ METİN; bağlantılar `BaglantiliMetin` ile (yalnız http/https).
 */
export default function SohbetAkisi({
  taraf,
  konusmaId,
  baslik,
  altBaslik,
  onGeri,
  onDegisti,
  ustAraclar,
  mesajAraclari,
  yazmaAraclari,
}: Props) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';

  const [mesajlar, setMesajlar] = useState<Mesaj[]>([]);
  const [bekleyenler, setBekleyenler] = useState<Bekleyen[]>([]);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [yuklemeHatasi, setYuklemeHatasi] = useState<string | null>(null);
  const [yenidenDene, setYenidenDene] = useState(0);
  const [dahaEski, setDahaEski] = useState(false);
  const [eskiYukleniyor, setEskiYukleniyor] = useState(false);
  const [karsiOkunan, setKarsiOkunan] = useState(0);
  const [yeniVar, setYeniVar] = useState(false);
  const [taslak, setTaslak] = useState('');
  const [ekler, setEkler] = useState<Ek[]>([]);
  const [ekYukleniyor, setEkYukleniyor] = useState(0);
  const [duzenlenen, setDuzenlenen] = useState<{ id: number; metin: string } | null>(null);
  const [simdi, setSimdi] = useState(() => Date.now());

  const akisRef = useRef<HTMLDivElement>(null);
  const metinRef = useRef<HTMLTextAreaElement>(null);
  const dosyaRef = useRef<HTMLInputElement>(null);
  const mesajlarRef = useRef<Mesaj[]>([]);
  const sonIdRef = useRef(0);
  const degisiklikRef = useRef<number | null>(null);
  const okudugumRef = useRef(0);
  const alttaRef = useRef(true);
  const altaKaydirRef = useRef(false);
  const korumaRef = useRef<{ yukseklik: number; ust: number } | null>(null);
  const onDegistiRef = useRef(onDegisti);
  onDegistiRef.current = onDegisti;

  const mesajlariAyarla = useCallback((uret: (eski: Mesaj[]) => Mesaj[]) => {
    setMesajlar((eski) => {
      const yeni = uret(eski);
      mesajlarRef.current = yeni;
      return yeni;
    });
  }, []);

  /** Görünür sekmede, karşı taraftan okunmamış mesaj varsa okundu işaretle. */
  const okunduGuncelle = useCallback(
    async (liste: Mesaj[]) => {
      if (gizliMi() || !liste.length) return;
      const son = liste[liste.length - 1].id;
      if (son <= okudugumRef.current) return;
      const onceki = okudugumRef.current;
      const okunacak = liste.some((m) => m.id > onceki && m.yazan_rol !== taraf);
      okudugumRef.current = son;
      if (!okunacak) return;
      try {
        const y = await okunduIsaretle(taraf, konusmaId, son);
        okudugumRef.current = Math.max(okudugumRef.current, y.okudugum);
        onDegistiRef.current?.();
      } catch {
        // Bir sonraki turda yeniden denensin.
        okudugumRef.current = onceki;
      }
    },
    [taraf, konusmaId]
  );

  // --- İlk yükleme -----------------------------------------------------------
  useEffect(() => {
    let iptal = false;
    setYukleniyor(true);
    setYuklemeHatasi(null);
    setMesajlar([]);
    mesajlarRef.current = [];
    setBekleyenler([]);
    setYeniVar(false);
    sonIdRef.current = 0;
    degisiklikRef.current = null;
    okudugumRef.current = 0;
    mesajlariGetir(taraf, konusmaId)
      .then((s) => {
        if (iptal) return;
        mesajlarRef.current = s.mesajlar;
        setMesajlar(s.mesajlar);
        setDahaEski(!!s.daha_eski);
        setKarsiOkunan(s.karsi_okunan || 0);
        sonIdRef.current = s.mesajlar.reduce((en, m) => Math.max(en, m.id), 0);
        degisiklikRef.current = s.konusma.degisiklik;
        okudugumRef.current = s.okudugum || 0;
        altaKaydirRef.current = true;
        void okunduGuncelle(s.mesajlar);
      })
      .catch((e) => {
        if (!iptal) setYuklemeHatasi(hataMetni(t, e));
      })
      .finally(() => {
        if (!iptal) setYukleniyor(false);
      });
    return () => {
      iptal = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taraf, konusmaId, yenidenDene]);

  // --- Yoklama (yalnız yeniler) ----------------------------------------------
  const yokla = useCallback(async () => {
    const s = await mesajlariGetir(taraf, konusmaId, { sonra: sonIdRef.current });
    setKarsiOkunan((eski) => Math.max(eski, s.karsi_okunan || 0));
    let gelen = s.mesajlar;
    if (degisiklikRef.current !== null && s.konusma.degisiklik !== degisiklikRef.current) {
      // Eski bir mesaj düzenlendi/silindi: yüklü pencereyi yeniden çek.
      const adet = Math.min(200, Math.max(50, mesajlarRef.current.length));
      const pencere = await mesajlariGetir(taraf, konusmaId, { adet });
      gelen = birlestir(gelen, pencere.mesajlar);
    }
    degisiklikRef.current = s.konusma.degisiklik;
    if (s.mesajlar.length) {
      sonIdRef.current = Math.max(sonIdRef.current, ...s.mesajlar.map((m) => m.id));
      if (alttaRef.current) altaKaydirRef.current = true;
      else if (s.mesajlar.some((m) => m.yazan_rol !== taraf)) setYeniVar(true);
    }
    if (gelen.length) {
      const birlesik = birlestir(mesajlarRef.current, gelen);
      mesajlariAyarla(() => birlesik);
      if (s.mesajlar.some((m) => m.yazan_rol !== taraf)) onDegistiRef.current?.();
    }
    await okunduGuncelle(mesajlarRef.current);
  }, [taraf, konusmaId, mesajlariAyarla, okunduGuncelle]);

  useYoklama(yokla, {
    aralik: SOHBET_ARALIGI,
    etkin: !yukleniyor && !yuklemeHatasi,
    hemen: false,
    anahtar: konusmaId,
  });

  // Düzenleme süresi düğmeleri zamanla kaybolsun.
  useEffect(() => {
    const z = window.setInterval(() => setSimdi(Date.now()), 30000);
    return () => window.clearInterval(z);
  }, []);

  // --- Kaydırma --------------------------------------------------------------
  useLayoutEffect(() => {
    const el = akisRef.current;
    if (!el) return;
    if (korumaRef.current) {
      const { yukseklik, ust } = korumaRef.current;
      el.scrollTop = el.scrollHeight - yukseklik + ust;
      korumaRef.current = null;
      return;
    }
    if (altaKaydirRef.current) {
      el.scrollTop = el.scrollHeight;
      altaKaydirRef.current = false;
      alttaRef.current = true;
      setYeniVar(false);
    }
  }, [mesajlar, bekleyenler, yukleniyor]);

  const eskileriYukle = useCallback(async () => {
    const ilk = mesajlarRef.current[0];
    if (!ilk || eskiYukleniyor) return;
    setEskiYukleniyor(true);
    try {
      const s = await mesajlariGetir(taraf, konusmaId, { once: ilk.id, adet: 50 });
      const el = akisRef.current;
      if (el) korumaRef.current = { yukseklik: el.scrollHeight, ust: el.scrollTop };
      mesajlariAyarla((eski) => birlestir(s.mesajlar, eski));
      setDahaEski(!!s.daha_eski);
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setEskiYukleniyor(false);
    }
  }, [taraf, konusmaId, eskiYukleniyor, mesajlariAyarla, t]);

  const kaydirildi = () => {
    const el = akisRef.current;
    if (!el) return;
    alttaRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    if (alttaRef.current) setYeniVar(false);
    if (el.scrollTop < 60 && dahaEski && !eskiYukleniyor) void eskileriYukle();
  };

  const altaIn = () => {
    const el = akisRef.current;
    if (el) el.scrollTop = el.scrollHeight;
    alttaRef.current = true;
    setYeniVar(false);
  };

  // --- Gönderme --------------------------------------------------------------
  const gonder = async (tekrar?: Bekleyen) => {
    const metin = tekrar ? tekrar.metin : taslak.trim();
    const ekListesi = tekrar ? tekrar.ekler : ekler;
    if ((!metin && !ekListesi.length) || (!tekrar && ekYukleniyor > 0)) return;
    if (metin.length > METIN_SINIRI) {
      toast.error(t('mesajlar.hata.metin_uzun', { sinir: METIN_SINIRI }));
      return;
    }
    const gecici = tekrar?.gecici ?? `g-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    if (tekrar) {
      setBekleyenler((l) => l.map((b) => (b.gecici === gecici ? { ...b, durum: 'gonderiliyor', hata: undefined } : b)));
    } else {
      setBekleyenler((l) => [...l, { gecici, metin, ekler: ekListesi, durum: 'gonderiliyor' }]);
      setTaslak('');
      setEkler([]);
      if (metinRef.current) metinRef.current.style.height = '';
    }
    altaKaydirRef.current = true;
    try {
      const m = await mesajGonder(taraf, konusmaId, { metin, ekler: ekListesi.map((e) => e.id) });
      setBekleyenler((l) => l.filter((b) => b.gecici !== gecici));
      okudugumRef.current = Math.max(okudugumRef.current, m.id);
      altaKaydirRef.current = true;
      // Kendi mesajımızı hemen ekle; `sonIdRef` ilerlemiyor ki arada gelen
      // karşı taraf mesajı yoklamada kaçmasın (tekrarları birleştirme ayıklıyor).
      mesajlariAyarla((eski) => birlestir(eski, [m]));
      onDegistiRef.current?.();
    } catch (e) {
      setBekleyenler((l) => l.map((b) => (b.gecici === gecici ? { ...b, durum: 'hata', hata: hataMetni(t, e) } : b)));
    }
  };

  const ekle = useCallback((metin: string) => {
    setTaslak((eski) => (eski.trim() ? `${eski.replace(/\s+$/, '')}\n${metin}` : metin));
    window.setTimeout(() => metinRef.current?.focus(), 0);
  }, []);

  const dosyaSecildi = async (liste: FileList | null) => {
    if (!liste?.length) return;
    const bos = EK_SINIRI - ekler.length;
    if (bos <= 0) {
      toast.error(t('mesajlar.hata.cok_ek', { sinir: EK_SINIRI }));
      return;
    }
    const secilen = Array.from(liste).slice(0, bos);
    if (dosyaRef.current) dosyaRef.current.value = '';
    for (const d of secilen) {
      setEkYukleniyor((n) => n + 1);
      try {
        const ek = await ekYukle(taraf, konusmaId, d);
        setEkler((l) => (l.length >= EK_SINIRI ? l : [...l, ek]));
      } catch (e) {
        toast.error(`${d.name}: ${hataMetni(t, e)}`);
      } finally {
        setEkYukleniyor((n) => n - 1);
      }
    }
  };

  const indir = async (m: Mesaj, ek: Ek) => {
    try {
      const y = await ekIndirmeAdresi(taraf, m.id, ek.id);
      adresiIndir(y.adres);
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const duzenlemeyiKaydet = async () => {
    if (!duzenlenen) return;
    try {
      const m = await mesajDuzenle(taraf, duzenlenen.id, duzenlenen.metin);
      mesajlariAyarla((eski) => birlestir(eski, [m]));
      setDuzenlenen(null);
      onDegistiRef.current?.();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const sil = async (m: Mesaj) => {
    if (!window.confirm(t('mesajlar.silOnay'))) return;
    try {
      const y = await mesajSil(taraf, m.id);
      mesajlariAyarla((eski) => birlestir(eski, [y]));
      onDegistiRef.current?.();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  // --- Biçim -----------------------------------------------------------------
  const saat = (iso?: string | null) => {
    if (!iso) return '';
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? '' : d.toLocaleTimeString(dil, { hour: '2-digit', minute: '2-digit' });
  };
  const gunEtiketi = (d: Date) => {
    const bugun = new Date();
    const dun = new Date();
    dun.setDate(bugun.getDate() - 1);
    if (ayniGun(d, bugun)) return t('mesajlar.bugun');
    if (ayniGun(d, dun)) return t('mesajlar.dun');
    return d.toLocaleDateString(dil, {
      day: 'numeric',
      month: 'long',
      ...(d.getFullYear() !== bugun.getFullYear() ? { year: 'numeric' } : {}),
    });
  };
  const yazanAdi = (m: Mesaj) => {
    if (m.benim) return t('mesajlar.siz');
    if (m.yazan_rol === 'admin') return m.yazan_ad || t('mesajlar.ajans');
    // Müşteri tarafında kim yazdı (ekipte birden çok kişi olabilir): ad · e-posta.
    if (m.yazan_ad && m.yazan_email && m.yazan_ad !== m.yazan_email) return `${m.yazan_ad} · ${m.yazan_email}`;
    return m.yazan_ad || m.yazan_email || '';
  };

  const satirlar: ReactNode[] = [];
  let oncekiGun: Date | null = null;
  for (const m of mesajlar) {
    const d = m.created_at ? new Date(m.created_at) : null;
    if (d && !Number.isNaN(d.getTime()) && (!oncekiGun || !ayniGun(oncekiGun, d))) {
      oncekiGun = d;
      satirlar.push(
        <div key={`gun-${m.id}`} className="my-3 flex items-center gap-3 text-[11px] text-muted-foreground" data-gun-ayirici>
          <span className="h-px flex-1 bg-white/10" />
          <span>{gunEtiketi(d)}</span>
          <span className="h-px flex-1 bg-white/10" />
        </div>
      );
    }
    const kendiTarafim = m.yazan_rol === taraf;
    const okundu = kendiTarafim && m.id <= karsiOkunan;
    const duzenlenebilir = m.benim && !m.silindi && !!m.duzenleme_bitis && new Date(m.duzenleme_bitis).getTime() > simdi;
    const duzenleniyor = duzenlenen?.id === m.id;
    satirlar.push(
      <div
        key={m.id}
        className={`group flex ${kendiTarafim ? 'justify-end' : 'justify-start'}`}
        data-mesaj={m.id}
        data-taraf={m.yazan_rol}
        data-benim={m.benim ? 'evet' : undefined}
      >
        <div
          className={`max-w-[88%] sm:max-w-[75%] rounded-2xl px-3.5 py-2 text-sm shadow-sm ${
            kendiTarafim
              ? 'rounded-ee-md bg-gradient-to-br from-purple-600/85 to-pink-600/75 text-white'
              : 'rounded-es-md border border-white/10 bg-white/[0.06]'
          }`}
        >
          {!m.benim && (
            <p className={`mb-0.5 text-[11px] font-semibold ${kendiTarafim ? 'text-white/80' : 'text-purple-300'}`} dir="auto">
              {yazanAdi(m)}
            </p>
          )}
          {m.silindi ? (
            <p className="italic opacity-70" data-silindi>
              {t('mesajlar.silindi')}
            </p>
          ) : duzenleniyor ? (
            <div className="space-y-2">
              <textarea
                value={duzenlenen.metin}
                onChange={(e) => setDuzenlenen({ id: m.id, metin: e.target.value })}
                maxLength={METIN_SINIRI}
                rows={3}
                dir="auto"
                className="w-64 max-w-full rounded-lg border border-white/20 bg-black/40 px-2 py-1.5 text-sm text-white"
                data-testid="mesaj-duzenle-metin"
              />
              <div className="flex justify-end gap-2">
                <button type="button" className="text-xs underline" onClick={() => setDuzenlenen(null)}>
                  {t('mesajlar.vazgec')}
                </button>
                <button type="button" className="text-xs font-semibold underline" onClick={() => void duzenlemeyiKaydet()} data-testid="mesaj-duzenle-kaydet">
                  {t('mesajlar.kaydet')}
                </button>
              </div>
            </div>
          ) : (
            m.metin && (
              <p className="whitespace-pre-wrap break-words leading-relaxed" dir="auto" data-mesaj-metni>
                <BaglantiliMetin metin={m.metin} />
              </p>
            )
          )}
          {!m.silindi && m.ekler.length > 0 && (
            <ul className="mt-1.5 space-y-1">
              {m.ekler.map((ek) => (
                <li key={ek.id}>
                  <button
                    type="button"
                    onClick={() => void indir(m, ek)}
                    className={`inline-flex max-w-full items-center gap-1.5 rounded-lg px-2 py-1 text-xs ${
                      kendiTarafim ? 'bg-white/15 hover:bg-white/25' : 'bg-white/[0.06] hover:bg-white/10'
                    }`}
                    aria-label={t('mesajlar.ekIndir', { ad: ek.ad })}
                    data-ek={ek.id}
                  >
                    <Download className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                    <span className="truncate" dir="auto">
                      {ek.ad}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className={`mt-1 flex items-center justify-end gap-1.5 text-[10px] ${kendiTarafim ? 'text-white/75' : 'text-muted-foreground'}`}>
            {m.duzenlendi_at && !m.silindi && <span>({t('mesajlar.duzenlendi')})</span>}
            <time dateTime={m.created_at || undefined}>{saat(m.created_at)}</time>
            {kendiTarafim && !m.silindi && (
              <span className="inline-flex items-center" data-okundu={okundu ? 'evet' : 'hayir'} title={okundu ? t('mesajlar.okundu') : t('mesajlar.gonderildi')}>
                {okundu ? <CheckCheck className="h-3.5 w-3.5" aria-hidden="true" /> : <Check className="h-3.5 w-3.5" aria-hidden="true" />}
                <span className="sr-only">{okundu ? t('mesajlar.okundu') : t('mesajlar.gonderildi')}</span>
              </span>
            )}
          </div>
          {duzenlenebilir && !duzenleniyor && (
            <div className="mt-1 flex justify-end gap-3 text-[11px] text-white/80">
              <button type="button" className="inline-flex items-center gap-1 hover:underline" onClick={() => setDuzenlenen({ id: m.id, metin: m.metin })} data-testid="mesaj-duzenle">
                <Pencil className="h-3 w-3" aria-hidden="true" /> {t('mesajlar.duzenle')}
              </button>
              <button type="button" className="inline-flex items-center gap-1 hover:underline" onClick={() => void sil(m)} data-testid="mesaj-sil">
                <Trash2 className="h-3 w-3" aria-hidden="true" /> {t('mesajlar.sil')}
              </button>
            </div>
          )}
          {!m.silindi && mesajAraclari?.(m)}
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col" data-sohbet={konusmaId}>
      <div className="flex items-center gap-2 border-b border-white/10 px-3 py-2.5">
        {onGeri && (
          <button
            type="button"
            onClick={onGeri}
            className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg hover:bg-white/10 md:hidden"
            aria-label={t('mesajlar.geri')}
            data-testid="mesaj-geri"
          >
            <ArrowLeft className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
          </button>
        )}
        <div className="min-w-0 flex-1">
          <p className="truncate font-semibold" dir="auto">
            {baslik}
          </p>
          {altBaslik && (
            <p className="truncate text-xs text-muted-foreground" dir="auto">
              {altBaslik}
            </p>
          )}
        </div>
        {ustAraclar}
      </div>

      <div className="relative min-h-0 flex-1">
        <div
          ref={akisRef}
          onScroll={kaydirildi}
          className="h-full space-y-1.5 overflow-y-auto px-3 py-3"
          role="log"
          aria-live="polite"
          aria-label={t('mesajlar.mesajAkisi')}
          data-mesaj-akisi
        >
          {yukleniyor ? (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              <Loader2 className="me-2 h-4 w-4 animate-spin" aria-hidden="true" /> {t('mesajlar.yukleniyor')}
            </div>
          ) : yuklemeHatasi ? (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-sm text-muted-foreground">
              <p>{yuklemeHatasi}</p>
              <Button size="sm" variant="outline" className="!bg-transparent border-white/20" onClick={() => setYenidenDene((n) => n + 1)}>
                <RotateCcw className="me-1.5 h-3.5 w-3.5" aria-hidden="true" /> {t('mesajlar.yenidenDene')}
              </Button>
            </div>
          ) : (
            <>
              {eskiYukleniyor ? (
                <p className="py-2 text-center text-xs text-muted-foreground">
                  <Loader2 className="me-1 inline h-3 w-3 animate-spin" aria-hidden="true" />
                  {t('mesajlar.eskiYukleniyor')}
                </p>
              ) : (
                mesajlar.length > 0 &&
                !dahaEski && <p className="py-2 text-center text-[11px] text-muted-foreground/70">{t('mesajlar.eskiYok')}</p>
              )}
              {mesajlar.length === 0 && bekleyenler.length === 0 && (
                <p className="py-10 text-center text-sm text-muted-foreground" data-mesaj-yok>
                  {t('mesajlar.mesajYok')}
                </p>
              )}
              {satirlar}
              {bekleyenler.map((b) => (
                <div key={b.gecici} className="flex justify-end" data-testid="mesaj-bekleyen" data-durum={b.durum}>
                  <div
                    className={`max-w-[88%] sm:max-w-[75%] rounded-2xl rounded-ee-md px-3.5 py-2 text-sm text-white ${
                      b.durum === 'hata' ? 'bg-red-900/60 border border-red-400/40' : 'bg-gradient-to-br from-purple-600/50 to-pink-600/40'
                    }`}
                  >
                    {b.metin && (
                      <p className="whitespace-pre-wrap break-words" dir="auto">
                        <BaglantiliMetin metin={b.metin} />
                      </p>
                    )}
                    {b.ekler.map((ek) => (
                      <p key={ek.id} className="truncate text-xs opacity-80" dir="auto">
                        📎 {ek.ad}
                      </p>
                    ))}
                    {b.durum === 'gonderiliyor' ? (
                      <p className="mt-1 flex items-center justify-end gap-1 text-[10px] text-white/75">
                        <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" /> {t('mesajlar.gonderiliyor')}
                      </p>
                    ) : (
                      <div className="mt-1 space-y-1 text-[11px]">
                        <p className="flex items-center gap-1 text-red-200">
                          <AlertCircle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                          {t('mesajlar.gonderilemedi')}
                          {b.hata ? ` — ${b.hata}` : ''}
                        </p>
                        <div className="flex justify-end gap-3">
                          <button type="button" className="underline" onClick={() => setBekleyenler((l) => l.filter((x) => x.gecici !== b.gecici))}>
                            {t('mesajlar.kaldir')}
                          </button>
                          <button type="button" className="font-semibold underline" onClick={() => void gonder(b)} data-testid="mesaj-yeniden-dene">
                            {t('mesajlar.yenidenDene')}
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </>
          )}
        </div>
        {yeniVar && (
          <button
            type="button"
            onClick={altaIn}
            className="absolute bottom-3 start-1/2 -translate-x-1/2 rtl:translate-x-1/2 inline-flex items-center gap-1 rounded-full bg-purple-600 px-3 py-1 text-xs font-medium text-white shadow-lg"
            data-testid="mesaj-yeni-var"
          >
            <ArrowDown className="h-3.5 w-3.5" aria-hidden="true" /> {t('mesajlar.yeniMesajlar')}
          </button>
        )}
      </div>

      <div className="border-t border-white/10 p-3">
        {yazmaAraclari?.(ekle)}
        {(ekler.length > 0 || ekYukleniyor > 0) && (
          <ul className="mb-2 flex flex-wrap gap-2" data-ekler>
            {ekler.map((ek) => (
              <li key={ek.id} className="inline-flex max-w-[14rem] items-center gap-1 rounded-lg border border-white/10 bg-white/[0.05] px-2 py-1 text-xs">
                <Paperclip className="h-3 w-3 shrink-0" aria-hidden="true" />
                <span className="truncate" dir="auto">
                  {ek.ad}
                </span>
                <button
                  type="button"
                  onClick={() => setEkler((l) => l.filter((x) => x.id !== ek.id))}
                  aria-label={t('mesajlar.ekKaldir', { ad: ek.ad })}
                  className="rounded p-0.5 hover:bg-white/10"
                >
                  <X className="h-3 w-3" aria-hidden="true" />
                </button>
              </li>
            ))}
            {ekYukleniyor > 0 && (
              <li className="inline-flex items-center gap-1 px-2 py-1 text-xs text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" /> {t('mesajlar.ekYukleniyor')}
              </li>
            )}
          </ul>
        )}
        <div className="flex items-end gap-2">
          <button
            type="button"
            onClick={() => dosyaRef.current?.click()}
            disabled={ekler.length >= EK_SINIRI}
            className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-white/10 text-muted-foreground hover:bg-white/10 hover:text-foreground disabled:opacity-40"
            aria-label={t('mesajlar.ekEkle')}
            title={t('mesajlar.ekEkle')}
            data-testid="mesaj-ek-ekle"
          >
            <Paperclip className="h-4 w-4" aria-hidden="true" />
          </button>
          <input
            ref={dosyaRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => void dosyaSecildi(e.target.files)}
            data-testid="mesaj-dosya"
          />
          <textarea
            ref={metinRef}
            value={taslak}
            onChange={(e) => {
              setTaslak(e.target.value);
              e.target.style.height = 'auto';
              e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                void gonder();
              }
            }}
            rows={1}
            maxLength={METIN_SINIRI}
            dir="auto"
            placeholder={t('mesajlar.yaz')}
            aria-label={t('mesajlar.yaz')}
            className="max-h-40 min-h-[44px] flex-1 resize-none rounded-xl border border-white/10 bg-black/30 px-3 py-2.5 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-purple-500"
            data-testid="mesaj-metin"
          />
          <Button
            type="button"
            onClick={() => void gonder()}
            disabled={(!taslak.trim() && ekler.length === 0) || ekYukleniyor > 0}
            className="h-11 w-11 shrink-0 bg-gradient-to-r from-purple-600 to-pink-600 p-0 text-white border-0"
            aria-label={t('mesajlar.gonder')}
            title={t('mesajlar.gonder')}
            data-testid="mesaj-gonder"
          >
            <Send className="h-4 w-4 rtl:-scale-x-100" aria-hidden="true" />
          </Button>
        </div>
        <p className="mt-1.5 hidden text-[11px] text-muted-foreground sm:block">{t('mesajlar.ipucu')}</p>
      </div>
    </div>
  );
}
