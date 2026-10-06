import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Copy, ExternalLink, KeyRound, Loader2, QrCode, RefreshCw, ScanLine } from 'lucide-react';
import { toast } from 'sonner';

import { Alan, DIS_DUGME, KART, Rozet, SECIM, Yukleniyor, kopyala } from '@/components/randevu/ortak';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { hataMetni, type Etkinlik, type EtkinlikApi, type EtkinlikMod, type Istatistik } from '@/lib/etkinlik';
import { OkutmaHatasi, panelIstemcisi, saatYaz, tarihYaz, type OkutmaSonucu } from '@/lib/etkinlikOrtak';

/**
 * Faz 6E — kapı: canlı giriş sayacı (10 sn'de bir basit yoklama; sekme görünmüyorsa durur),
 * son okutmalar, elle kod denetimi, tam ekran okutucuyu açma ve görevli bağlantısı
 * (girişsiz, yalnız okutma, süreli; yenilenince eskiler geçersiz).
 *
 * Kamera panelde kapalı (Permissions-Policy camera=()); okutucu `/etkinlik/okut/<id>` adresinde
 * ayrı sayfa olarak açılıyor, orada izin veriliyor.
 */

const YOKLAMA_MS = 10_000;

export const SONUC_RENGI: Record<OkutmaSonucu, string> = {
  gecerli: 'border-emerald-400/40 bg-emerald-500/15 text-emerald-200',
  zaten_girdi: 'border-amber-400/40 bg-amber-500/15 text-amber-200',
  gecersiz: 'border-red-400/40 bg-red-500/15 text-red-200',
  iptal: 'border-red-400/40 bg-red-500/15 text-red-200',
  farkli_etkinlik: 'border-red-400/40 bg-red-500/15 text-red-200',
  odeme_bekliyor: 'border-amber-400/40 bg-amber-500/15 text-amber-200',
  etkinlik_iptal: 'border-red-400/40 bg-red-500/15 text-red-200',
};

export default function Kapi({ api, etkinlik, mod }: { api: EtkinlikApi; etkinlik: Etkinlik; mod: EtkinlikMod }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const tz = etkinlik.saat_dilimi;
  const [ist, setIst] = useState<Istatistik | null>(null);
  const [guncel, setGuncel] = useState<string | null>(null);
  const [gorevli, setGorevli] = useState<{ adres: string; son: string } | null>(null);
  const [sure, setSure] = useState('');
  const [mesgul, setMesgul] = useState(false);
  const [kod, setKod] = useState('');
  const [sonuc, setSonuc] = useState<{ sonuc: OkutmaSonucu; ad: string | null; tur: string | null; giris: string | null } | null>(null);
  const istemci = useRef(panelIstemcisi(etkinlik.id, mod === 'yonetici'));

  const yukle = useCallback(async () => {
    try {
      setIst(await api.istatistik(etkinlik.id));
      setGuncel(new Date().toISOString());
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  }, [api, etkinlik.id, t]);

  useEffect(() => {
    void yukle();
    const z = window.setInterval(() => {
      if (document.visibilityState === 'visible') void yukle();
    }, YOKLAMA_MS);
    return () => window.clearInterval(z);
  }, [yukle]);

  const gorevliAl = async (yenile: boolean) => {
    if (yenile && !window.confirm(t('etkinlik.kapi.gorevliYenileOnay'))) return;
    setMesgul(true);
    try {
      const saat = sure ? Number(sure) : null;
      setGorevli(yenile || saat ? await api.gorevliYeni(etkinlik.id, { saat, yenile }) : await api.gorevli(etkinlik.id));
      if (yenile) toast.success(t('etkinlik.kapi.gorevliYenilendi'));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  const denetle = async () => {
    const k = kod.trim();
    if (!k) return;
    setMesgul(true);
    try {
      const y = await istemci.current.okut(k);
      setSonuc({ sonuc: y.sonuc, ad: y.bilet?.ad ?? null, tur: y.bilet?.tur ?? null, giris: y.bilet?.giris_at ?? null });
      setKod('');
      void yukle();
    } catch (e) {
      toast.error(e instanceof OkutmaHatasi ? t(`etkinlik.hata.${e.kod}`, { defaultValue: t('etkinlik.hata.genel') }) : t('etkinlik.hata.genel'));
    } finally {
      setMesgul(false);
    }
  };

  if (!ist) return <Yukleniyor />;
  const oran = ist.toplam ? Math.round((ist.giren / ist.toplam) * 100) : 0;
  const okutAdresi = `/etkinlik/okut/${etkinlik.id}?mod=${mod}`;

  return (
    <div className="space-y-4" data-testid="etkinlik-kapi">
      <div className={`${KART} p-4 sm:p-6`}>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-semibold">{t('etkinlik.kapi.baslik')}</h3>
          <span className="text-xs text-muted-foreground">{guncel ? t('etkinlik.kapi.guncellendi', { saat: saatYaz(guncel, tz, dil) }) : ''}</span>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {[
            ['giren', ist.giren],
            ['toplam', ist.toplam],
            ['kalan', ist.kalan],
            ['kapasite', ist.kapasite ?? '∞'],
          ].map(([ad, deger]) => (
            <div key={ad as string} className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
              <div className="text-xs text-muted-foreground">{t(`etkinlik.kapi.${ad}`)}</div>
              <div className="text-2xl font-bold tabular-nums" data-testid={`etkinlik-sayac-${ad}`}>
                {deger}
              </div>
            </div>
          ))}
        </div>
        <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/10" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={oran} aria-label={t('etkinlik.kapi.giren')}>
          <div className="h-full bg-emerald-400 transition-all" style={{ width: `${oran}%` }} />
        </div>
        {ist.turler.length > 1 && (
          <ul className="mt-3 grid gap-1 text-sm sm:grid-cols-2">
            {ist.turler.map((x) => (
              <li key={x.id} className="flex justify-between gap-2 rounded-lg bg-white/[0.03] px-3 py-1.5">
                <span className="truncate">{x.ad}</span>
                <span className="tabular-nums text-muted-foreground">
                  {x.giren} / {x.toplam}
                </span>
              </li>
            ))}
          </ul>
        )}
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          {ist.bekleyen_odeme > 0 && <Rozet>{t('etkinlik.kapi.bekleyenOdeme', { sayi: ist.bekleyen_odeme })}</Rozet>}
          {(ist.bekleme.bekliyor || 0) > 0 && <Rozet>{t('etkinlik.kapi.bekleme', { sayi: ist.bekleme.bekliyor })}</Rozet>}
        </div>
      </div>

      <div className={`${KART} p-4 sm:p-6`}>
        <h3 className="mb-1 font-semibold">{t('etkinlik.kapi.okutBaslik')}</h3>
        <p className="mb-3 text-sm text-muted-foreground">{t('etkinlik.kapi.okutAciklama')}</p>
        <div className="flex flex-wrap gap-2">
          <a href={okutAdresi} target="_blank" rel="noopener" className="inline-flex items-center gap-1.5 rounded-md bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-500" data-testid="etkinlik-okut-ac">
            <ScanLine className="h-4 w-4" aria-hidden="true" />
            {t('etkinlik.kapi.okutAc')}
          </a>
        </div>
        <div className="mt-4 flex flex-wrap items-end gap-2">
          <Alan etiket={t('etkinlik.kapi.elle')} ipucu={t('etkinlik.kapi.elleIpucu')} className="min-w-[12rem] flex-1">
            <Input
              value={kod}
              onChange={(e) => setKod(e.target.value.toUpperCase())}
              onKeyDown={(e) => {
                if (e.key === 'Enter') void denetle();
              }}
              autoCapitalize="characters"
              autoComplete="off"
              spellCheck={false}
              data-testid="etkinlik-kapi-kod"
            />
          </Alan>
          <Button onClick={() => void denetle()} disabled={mesgul || !kod.trim()} className="gap-1.5" data-testid="etkinlik-kapi-denetle">
            {mesgul ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <QrCode className="h-4 w-4" aria-hidden="true" />}
            {t('etkinlik.kapi.denetle')}
          </Button>
        </div>
        {sonuc && (
          <div className={`mt-3 rounded-xl border p-3 ${SONUC_RENGI[sonuc.sonuc]}`} role="status" data-testid="etkinlik-kapi-sonuc" data-sonuc={sonuc.sonuc}>
            <div className="font-semibold">{t(`etkinlik.kapi.sonuc.${sonuc.sonuc}`)}</div>
            {(sonuc.ad || sonuc.tur) && <div className="text-sm">{[sonuc.ad, sonuc.tur].filter(Boolean).join(' · ')}</div>}
            {sonuc.sonuc === 'zaten_girdi' && sonuc.giris && <div className="text-sm">{t('etkinlik.kapi.girisSaati', { saat: saatYaz(sonuc.giris, tz, dil) })}</div>}
          </div>
        )}
      </div>

      <div className={`${KART} p-4 sm:p-6`} data-testid="etkinlik-gorevli">
        <h3 className="mb-1 flex items-center gap-2 font-semibold">
          <KeyRound className="h-4 w-4" aria-hidden="true" />
          {t('etkinlik.kapi.gorevli')}
        </h3>
        <p className="mb-3 text-sm text-muted-foreground">{t('etkinlik.kapi.gorevliAciklama')}</p>
        <div className="flex flex-wrap items-end gap-2">
          <Alan etiket={t('etkinlik.kapi.gorevliSure')} className="w-48">
            <select className={SECIM} value={sure} onChange={(e) => setSure(e.target.value)} data-testid="etkinlik-gorevli-sure">
              <option value="">{t('etkinlik.kapi.varsayilanSure')}</option>
              {[2, 6, 12, 24, 72].map((s) => (
                <option key={s} value={s}>
                  {t('etkinlik.kapi.saat', { sayi: s })}
                </option>
              ))}
            </select>
          </Alan>
          <Button onClick={() => void gorevliAl(false)} disabled={mesgul} className="gap-1.5" data-testid="etkinlik-gorevli-olustur">
            <KeyRound className="h-4 w-4" aria-hidden="true" />
            {t('etkinlik.kapi.gorevliOlustur')}
          </Button>
          <Button variant="outline" className={DIS_DUGME} onClick={() => void gorevliAl(true)} disabled={mesgul} data-testid="etkinlik-gorevli-yenile">
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            {t('etkinlik.kapi.gorevliYenile')}
          </Button>
        </div>
        {gorevli && (
          <div className="mt-3 space-y-2 rounded-xl border border-white/10 bg-white/[0.03] p-3">
            <div className="flex items-center gap-2">
              <code className="min-w-0 flex-1 truncate text-xs" data-testid="etkinlik-gorevli-baglantisi">
                {gorevli.adres}
              </code>
              <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => void kopyala(gorevli.adres, t('etkinlik.kopyalandi'), t('etkinlik.kopyalanamadi'))} aria-label={t('etkinlik.kopyala')}>
                <Copy className="h-4 w-4" aria-hidden="true" />
              </Button>
              <a href={gorevli.adres} target="_blank" rel="noopener" className="inline-flex h-9 items-center rounded-md border border-white/20 px-2" aria-label={t('etkinlik.ac')}>
                <ExternalLink className="h-4 w-4" aria-hidden="true" />
              </a>
            </div>
            <div className="text-xs text-muted-foreground">{t('etkinlik.kapi.gorevliSon', { tarih: `${tarihYaz(gorevli.son, tz, dil, { dateStyle: 'medium' })} ${saatYaz(gorevli.son, tz, dil)}` })}</div>
          </div>
        )}
      </div>

      <div className={`${KART} p-4 sm:p-6`}>
        <h3 className="mb-2 font-semibold">{t('etkinlik.kapi.sonOkutmalar')}</h3>
        {ist.son_okutmalar.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('etkinlik.kapi.bos')}</p>
        ) : (
          <ul className="space-y-1 text-sm" data-testid="etkinlik-son-okutmalar">
            {ist.son_okutmalar.map((o, i) => (
              <li key={`${o.zaman}-${i}`} className="flex flex-wrap items-center gap-2 rounded-lg bg-white/[0.03] px-3 py-1.5">
                <span className="tabular-nums text-muted-foreground">{saatYaz(o.zaman, tz, dil)}</span>
                <Rozet renk={SONUC_RENGI[o.sonuc as OkutmaSonucu] || undefined}>{t(`etkinlik.kapi.sonuc.${o.sonuc}`, { defaultValue: o.sonuc })}</Rozet>
                {o.kod && <code className="text-xs">{o.kod}</code>}
                {o.tur && <span className="text-muted-foreground">{o.tur}</span>}
                <span className="ms-auto text-xs text-muted-foreground">
                  {t(`etkinlik.kapi.kaynak.${o.kaynak}`, { defaultValue: o.kaynak })}
                  {o.cevrimdisi ? ` · ${t('etkinlik.kapi.cevrimdisi')}` : ''}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
