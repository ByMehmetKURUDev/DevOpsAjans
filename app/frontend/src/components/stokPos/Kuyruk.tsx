import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, CloudUpload, Loader2, Receipt, RotateCw, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { DIS_DUGME, KART, Rozet } from '@/components/stokPos/ortak';
import { kalici, kisiOzeti, kuyrugaYaz, kuyrukListe, kuyruktanSil, type KuyrukKaydi } from '@/lib/posKuyruk';
import { hataMetni, StokHatasi, tarihSaat, type Meta, type Satis, type StokApi } from '@/lib/stokPos';

/** Bağlantı varken kuyruğun kendiliğinden yeniden denenme aralığı. */
const DENEME_ARALIGI_MS = 15_000;

export interface Kuyruk {
  /** Bu kişinin (aynı hesap + aynı kişi özeti) kuyruğu: bekleyenler ve çözüm bekleyenler. */
  kayitlar: KuyrukKaydi[];
  bekleyen: number;
  hatali: KuyrukKaydi[];
  benim: string;
  kalici: boolean;
  esitleniyor: boolean;
  ekle: (k: KuyrukKaydi) => Promise<void>;
  esitle: () => Promise<void>;
  tekrarDene: (kimlik: string, guncelFiyat?: boolean) => Promise<void>;
  iptal: (kimlik: string) => Promise<void>;
}

/**
 * Faz 6Q — kasa ekranının çevrimdışı satış kuyruğu.
 *
 * Gönderim SIRAYLA (cihazdaki sıra): bağlantı gelince (`online`), kasa ekranı açılınca ve bağlantı varken
 * aralıklarla. Göndermeden önce `/meta` taze alınır: yalnız AYNI hesabın AYNI kişisinin kayıtları gider
 * (başka biri giriş yaptıysa onun jetonuyla gönderilmez). Ağ/sunucu hatası (0, 5xx, 429, 401) kuyruğu durdurur
 * ve kayıt beklemede kalır; iş kuralı hatası (ürün silinmiş, yetersiz stok, fiyat değişmiş…) kaydı "çözüm
 * bekleyen" yapar ve sıradakine geçilir. Kuyruk boş değilken sayfadan çıkmak uyarı verir.
 */
export function useKuyruk(api: StokApi, meta: Meta, onEsitlendi: (gonderilen: Satis[], hatali: number) => void): Kuyruk {
  const [kayitlar, setKayitlar] = useState<KuyrukKaydi[]>([]);
  const [benim, setBenim] = useState('');
  const [kaliciMi, setKaliciMi] = useState(true);
  const [esitleniyor, setEsitleniyor] = useState(false);
  const kilit = useRef(false);
  const geriCagri = useRef(onEsitlendi);
  geriCagri.current = onEsitlendi;

  const yenile = useCallback(async () => {
    const oz = await kisiOzeti(meta.hesap, meta.ben);
    setBenim(oz);
    setKayitlar((await kuyrukListe(meta.hesap)).filter((k) => k.kisi_ozeti === oz));
  }, [meta.hesap, meta.ben]);

  useEffect(() => {
    void yenile();
    void kalici().then(setKaliciMi);
  }, [yenile]);

  const esitle = useCallback(async () => {
    if (kilit.current) return;
    kilit.current = true;
    setEsitleniyor(true);
    const gonderilen: Satis[] = [];
    let hatali = 0;
    try {
      const liste = (await kuyrukListe(meta.hesap)).filter((k) => k.durum === 'bekliyor');
      if (!liste.length) return;
      let taze: Meta;
      try {
        taze = await api.meta();
      } catch {
        return; // hâlâ bağlantı yok (ya da oturum düştü): kayıtlar beklemede kalır
      }
      // Yalnız AYNI hesabın AYNI kişisinin kayıtları (kişi özeti hesap + kişi e-postasından).
      const oz = await kisiOzeti(taze.hesap, taze.ben);
      for (const k of liste) {
        if (k.kisi_ozeti !== oz) continue;
        try {
          gonderilen.push(await api.satisEkle(k.govde));
          await kuyruktanSil(k.istemci_kimligi);
        } catch (e) {
          const h = e instanceof StokHatasi ? e : new StokHatasi(0, 'ag');
          if (h.durum === 0 || h.durum >= 500 || h.durum === 429 || h.durum === 401) break;
          await kuyrugaYaz({ ...k, durum: 'hata', hata: { kod: h.kod, durum: h.durum, ek: h.ek }, deneme: k.deneme + 1 });
          hatali += 1;
        }
      }
    } finally {
      kilit.current = false;
      setEsitleniyor(false);
      await yenile();
      if (gonderilen.length || hatali) geriCagri.current(gonderilen, hatali);
    }
  }, [api, meta.hesap, yenile]);

  const bekleyen = kayitlar.filter((k) => k.durum === 'bekliyor').length;

  // Bağlantı varken bekleyen kayıt kaldıysa (ör. sunucu uykudan uyanıyordu) aralıklarla yeniden dene.
  useEffect(() => {
    if (!bekleyen) return;
    const z = window.setInterval(() => {
      if (typeof navigator === 'undefined' || navigator.onLine !== false) void esitle();
    }, DENEME_ARALIGI_MS);
    return () => window.clearInterval(z);
  }, [bekleyen, esitle]);

  // Kuyruk boş değilken sayfadan çıkma uyarısı (kayıtlar cihazda kalır ama bu sekme kapanınca gönderilmez).
  useEffect(() => {
    if (!kayitlar.length) return;
    const uyar = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = '';
      return '';
    };
    window.addEventListener('beforeunload', uyar);
    return () => window.removeEventListener('beforeunload', uyar);
  }, [kayitlar.length]);

  const ekle = useCallback(
    async (k: KuyrukKaydi) => {
      await kuyrugaYaz(k);
      await yenile();
    },
    [yenile]
  );

  const tekrarDene = useCallback(
    async (kimlik: string, guncelFiyat?: boolean) => {
      const k = (await kuyrukListe(meta.hesap)).find((x) => x.istemci_kimligi === kimlik);
      if (!k) return;
      const govde: Record<string, unknown> = { ...k.govde };
      if (guncelFiyat) {
        // Kullanıcı sunucudaki güncel fiyatı kabul etti: beklenen toplam ve (eski toplama göre) alınan nakit düşer.
        delete govde.beklenen_toplam;
        const odeme = { ...((govde.odeme as Record<string, unknown>) || {}) };
        delete odeme.nakit_alinan;
        govde.odeme = odeme;
      }
      await kuyrugaYaz({ ...k, govde, durum: 'bekliyor', hata: undefined });
      await yenile();
      await esitle();
    },
    [esitle, meta.hesap, yenile]
  );

  const iptal = useCallback(
    async (kimlik: string) => {
      await kuyruktanSil(kimlik);
      await yenile();
    },
    [yenile]
  );

  return { kayitlar, bekleyen, hatali: kayitlar.filter((k) => k.durum === 'hata'), benim, kalici: kaliciMi, esitleniyor, ekle, esitle, tekrarDene, iptal };
}

/** Kuyruktaki satışlar: eşitlenmeyi bekleyenler ve "çözüm bekleyenler" (tekrar dene / iptal). */
export function KuyrukPaneli({ kuyruk, para, cevrimici, onFis }: { kuyruk: Kuyruk; para: (n: number) => string; cevrimici: boolean; onFis: (s: Satis) => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  if (!kuyruk.kayitlar.length) return null;
  return (
    <section className={`${KART} space-y-2 p-3`} aria-labelledby="pos-kuyruk-baslik" data-testid="pos-kuyruk-panel">
      <div className="flex flex-wrap items-center gap-2">
        <h3 id="pos-kuyruk-baslik" className="flex items-center gap-1.5 text-sm font-semibold">
          <CloudUpload className="h-4 w-4 text-amber-300" aria-hidden="true" />
          {t('stokPos.kuyruk.baslik', { sayi: kuyruk.kayitlar.length })}
        </h3>
        {cevrimici && kuyruk.bekleyen > 0 && (
          <Button size="sm" variant="outline" className={`${DIS_DUGME} ms-auto h-8`} disabled={kuyruk.esitleniyor} onClick={() => void kuyruk.esitle()} data-testid="pos-kuyruk-esitle">
            {kuyruk.esitleniyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <RotateCw className="h-4 w-4" aria-hidden="true" />}
            {t('stokPos.kuyruk.simdiEsitle')}
          </Button>
        )}
      </div>
      {!kuyruk.kalici && <p className="text-xs text-amber-200">{t('stokPos.kuyruk.bellekte')}</p>}
      <ul className="divide-y divide-white/5">
        {kuyruk.kayitlar.map((k) => {
          const hata = k.hata ? hataMetni(t, new StokHatasi(k.hata.durum, k.hata.kod, k.hata.ek)) : null;
          return (
            <li key={k.istemci_kimligi} className="space-y-1 py-2 text-sm" data-testid="pos-kuyruk-kaydi" data-durum={k.durum}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs">{k.no}</span>
                <span className="text-xs text-muted-foreground">{tarihSaat(k.zaman, dil)}</span>
                {k.durum === 'hata' ? (
                  <Rozet renk="border-red-400/40 bg-red-500/15 text-red-200">
                    <AlertTriangle className="h-3 w-3" aria-hidden="true" />
                    {t('stokPos.kuyruk.cozumBekleyen')}
                  </Rozet>
                ) : (
                  <Rozet renk="border-amber-400/40 bg-amber-500/15 text-amber-200">{t('stokPos.kuyruk.esitlenecek')}</Rozet>
                )}
                <span className="ms-auto font-semibold tabular-nums">{para(k.toplam)}</span>
              </div>
              {hata && (
                <p className="text-xs text-red-200" data-testid="pos-kuyruk-hata">
                  {hata}
                </p>
              )}
              <div className="flex flex-wrap justify-end gap-1">
                <Button size="sm" variant="ghost" className="h-8 gap-1 px-2" onClick={() => onFis(k.fis)}>
                  <Receipt className="h-4 w-4" aria-hidden="true" />
                  {t('stokPos.kasa.fis')}
                </Button>
                {k.durum === 'hata' && (
                  <>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-8 gap-1 px-2"
                      disabled={!cevrimici || kuyruk.esitleniyor}
                      onClick={() => void kuyruk.tekrarDene(k.istemci_kimligi, k.hata?.kod === 'toplam_degisti')}
                      data-testid="pos-kuyruk-tekrar"
                    >
                      <RotateCw className="h-4 w-4" aria-hidden="true" />
                      {k.hata?.kod === 'toplam_degisti' ? t('stokPos.kuyruk.guncelFiyatla') : t('stokPos.kuyruk.tekrarDene')}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-8 gap-1 px-2 text-red-300 hover:text-red-200"
                      onClick={() => {
                        if (window.confirm(t('stokPos.kuyruk.iptalOnay', { no: k.no }))) void kuyruk.iptal(k.istemci_kimligi);
                      }}
                      data-testid="pos-kuyruk-iptal"
                    >
                      <Trash2 className="h-4 w-4" aria-hidden="true" />
                      {t('stokPos.kuyruk.iptal')}
                    </Button>
                  </>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
