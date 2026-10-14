import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { AlertTriangle, Clock, Copy, Facebook, Loader2, LogIn, RefreshCw, Save, Unplug } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  hataMetni,
  metaBaslat,
  metaEsitle,
  metaKaldir,
  metaKaynaklari,
  metaSecimKaydet,
  type BaglantiDurumListesi,
  type MetaBaglantisi,
  type MetaKaynak,
  type MetaKaynaklari,
  type MetaSecimler,
} from '@/lib/baglantilar';
import { tarihBicimle } from '@/lib/siteBakim';

/**
 * Parti 13 — Bağlantılar › Meta kartı (Facebook sayfası + Instagram profesyonel hesabı).
 *
 * Google kartıyla aynı düzen: kurulum (eksik ortam değişkeninin yalnız ADI),
 * "Meta ile bağlan", bağlı Facebook kullanıcısı, iki seçim, "Şimdi eşitle",
 * son eşitleme ve hata, "Bağlantıyı kaldır". Ortak metinler `baglantilar.google.*`
 * altında (genel ifadeler), Meta'ya özgü olanlar `baglantilar.meta.*`.
 */

const SECIM_ALANI: Record<MetaKaynak, keyof MetaSecimler> = {
  fb: 'fb_sayfa',
  ig: 'ig_hesap',
};
const KAYNAKLAR: MetaKaynak[] = ['fb', 'ig'];

export default function MetaKarti({
  meta,
  yenile,
  setDurum,
}: {
  meta: MetaBaglantisi;
  yenile: () => Promise<void>;
  setDurum: (d: BaglantiDurumListesi) => void;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [kaynaklar, setKaynaklar] = useState<MetaKaynaklari | null>(null);
  const [kaynakYukleniyor, setKaynakYukleniyor] = useState(false);
  const [taslak, setTaslak] = useState<MetaSecimler>(meta.secimler);
  const [islem, setIslem] = useState<'' | 'baglan' | 'kaydet' | 'esitle' | 'kaldir'>('');

  useEffect(() => {
    setTaslak(meta.secimler);
  }, [meta.secimler]);

  const bagli = meta.durum === 'bagli';
  useEffect(() => {
    if (!bagli) {
      setKaynaklar(null);
      return;
    }
    let iptal = false;
    setKaynakYukleniyor(true);
    metaKaynaklari()
      .then((k) => {
        if (iptal) return;
        setKaynaklar(k);
        setTaslak((onceki) => {
          const yeni = { ...onceki };
          for (const kisa of KAYNAKLAR) {
            const alan = SECIM_ALANI[kisa];
            if (!yeni[alan] && k[kisa].length === 1) yeni[alan] = k[kisa][0].kimlik;
          }
          return yeni;
        });
      })
      .catch((e) => {
        if (!iptal) toast.error(hataMetni(t, e));
      })
      .finally(() => {
        if (!iptal) setKaynakYukleniyor(false);
      });
    return () => {
      iptal = true;
    };
  }, [bagli, t]);

  const degisti = useMemo(
    () => KAYNAKLAR.some((k) => (taslak[SECIM_ALANI[k]] || null) !== (meta.secimler[SECIM_ALANI[k]] || null)),
    [meta.secimler, taslak],
  );

  const baglan = async () => {
    setIslem('baglan');
    try {
      const { adres } = await metaBaslat();
      window.location.assign(adres);
    } catch (e) {
      toast.error(hataMetni(t, e));
      setIslem('');
    }
  };

  const kaydet = async () => {
    setIslem('kaydet');
    try {
      await metaSecimKaydet(taslak);
      toast.success(t('baglantilar.google.secimKaydedildi'));
      await yenile();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setIslem('');
    }
  };

  const esitle = async () => {
    setIslem('esitle');
    try {
      const s = await metaEsitle();
      setDurum(s.durum);
      if (Object.keys(s.hatalar || {}).length) toast.warning(t('baglantilar.google.kismenEsitlendi'));
      else toast.success(t('baglantilar.google.esitlendi', { sayi: s.yazilan }));
    } catch (e) {
      toast.error(hataMetni(t, e));
      await yenile();
    } finally {
      setIslem('');
    }
  };

  const kaldir = async () => {
    if (!window.confirm(t('baglantilar.meta.kaldirOnay'))) return;
    setIslem('kaldir');
    try {
      const s = await metaKaldir();
      if (s.iptal_edildi) toast.success(t('baglantilar.meta.kaldirildi'));
      else toast.warning(t('baglantilar.meta.iptalEdilemedi'));
      await yenile();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setIslem('');
    }
  };

  const kopyala = async (metin: string) => {
    try {
      await navigator.clipboard.writeText(metin);
      toast.success(t('baglantilar.google.kopyalandi'));
    } catch {
      /* pano kapalı: adres zaten ekranda */
    }
  };

  const hatalar = Object.entries(meta.son_hata || {});
  const beklemeDk = Math.ceil((meta.elle_bekleme_sn || 0) / 60);
  const secimVar = Object.values(meta.secimler).some(Boolean);

  return (
    <section className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6" data-testid="meta-karti" data-durum={meta.durum}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-lg font-semibold">
            <Facebook className="h-4 w-4" />
            {t('baglantilar.meta.ad')}
          </h3>
          <p className="text-xs text-muted-foreground">{t('baglantilar.meta.altBaslik')}</p>
        </div>
        <span
          className={`rounded-full px-3 py-1 text-xs font-medium ${
            meta.durum === 'bagli'
              ? 'bg-emerald-500/15 text-emerald-300'
              : meta.durum === 'yeniden_baglan'
                ? 'bg-red-500/15 text-red-300'
                : 'bg-white/10 text-muted-foreground'
          }`}
          data-testid="meta-durum"
        >
          {t(`baglantilar.google.durum.${meta.durum}`)}
        </span>
      </div>

      {meta.durum === 'kurulmadi' && (
        <div className="mt-4 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm" data-testid="meta-kurulum">
          <p className="font-medium text-amber-100">{t('baglantilar.google.kurulumBaslik')}</p>
          <p className="mt-1 text-amber-200/90">{t('baglantilar.google.kurulumAciklama')}</p>
          {meta.kurulum.eksik.length > 0 && (
            <p className="mt-2">
              {t('baglantilar.google.eksik')}:{' '}
              {meta.kurulum.eksik.map((ad) => (
                <code key={ad} className="mr-2 break-all rounded bg-black/30 px-1.5 py-0.5 text-xs" data-eksik={ad}>
                  {ad}
                </code>
              ))}
            </p>
          )}
          {meta.kurulum.gecersiz.length > 0 && (
            <p className="mt-2">
              {t('baglantilar.google.gecersiz')}:{' '}
              {meta.kurulum.gecersiz.map((ad) => (
                <code key={ad} className="mr-2 break-all rounded bg-black/30 px-1.5 py-0.5 text-xs">
                  {ad}
                </code>
              ))}
            </p>
          )}
          <p className="mt-2 text-xs text-amber-200/80">{t('baglantilar.meta.rehber')}</p>
        </div>
      )}

      {(meta.durum === 'kurulmadi' || meta.durum === 'bagli_degil') && (
        <div className="mt-4 text-xs text-muted-foreground">
          <p>{t('baglantilar.meta.yonlendirme')}</p>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <code className="break-all rounded bg-black/30 px-2 py-1" data-testid="meta-yonlendirme-adresi">
              {meta.yonlendirme_adresi}
            </code>
            <button
              type="button"
              onClick={() => void kopyala(meta.yonlendirme_adresi)}
              className="inline-flex items-center gap-1 text-purple-300 hover:text-pink-300"
            >
              <Copy className="h-3.5 w-3.5" />
              {t('baglantilar.google.kopyala')}
            </button>
          </div>
        </div>
      )}

      {meta.durum === 'bagli_degil' && (
        <div className="mt-5 space-y-3">
          <p className="text-sm text-muted-foreground">{t('baglantilar.meta.baglanAciklama')}</p>
          <Button onClick={() => void baglan()} disabled={islem !== ''} data-testid="meta-baglan">
            {islem === 'baglan' ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <LogIn className="mr-2 h-4 w-4" />}
            {t('baglantilar.meta.baglan')}
          </Button>
        </div>
      )}

      {meta.durum === 'yeniden_baglan' && (
        <div className="mt-4 space-y-3 rounded-xl border border-red-400/30 bg-red-500/10 p-4 text-sm" data-testid="meta-yeniden">
          <p className="text-red-200">{t('baglantilar.meta.yenidenAciklama')}</p>
          <Button onClick={() => void baglan()} disabled={islem !== ''} data-testid="meta-yeniden-baglan">
            {islem === 'baglan' ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
            {t('baglantilar.google.yenidenBaglan')}
          </Button>
        </div>
      )}

      {(meta.durum === 'bagli' || meta.durum === 'yeniden_baglan') && (
        <dl className="mt-4 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs text-muted-foreground">{t('baglantilar.meta.hesap')}</dt>
            <dd data-testid="meta-hesap">{meta.harici_ad || '—'}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">{t('baglantilar.google.baglanmaTarihi')}</dt>
            <dd>{tarihBicimle(meta.baglanti_tarihi, dil, true)}</dd>
          </div>
        </dl>
      )}

      {meta.durum === 'bagli' && (
        <div className="mt-6 space-y-4">
          <h4 className="text-sm font-semibold">{t('baglantilar.google.secimBaslik')}</h4>
          {kaynakYukleniyor && (
            <p className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              {t('baglantilar.meta.kaynaklarYukleniyor')}
            </p>
          )}
          <div className="grid gap-4 md:grid-cols-2">
            {KAYNAKLAR.map((kisa) => {
              const alan = SECIM_ALANI[kisa];
              const secenekler = kaynaklar?.[kisa] ?? [];
              const secili = taslak[alan] || '';
              const kaynakHatasi = kaynaklar?.hatalar?.[kisa];
              const tumu = secili && !secenekler.some((s) => s.kimlik === secili) ? [{ kimlik: secili, ad: secili }, ...secenekler] : secenekler;
              return (
                <label key={kisa} className="block text-sm">
                  <span className="mb-1 block text-xs text-muted-foreground">{t(`baglantilar.meta.${kisa}`)}</span>
                  <select
                    data-testid={`meta-secim-${kisa}`}
                    value={secili}
                    disabled={!meta.kapsamlar[kisa] || islem !== ''}
                    onChange={(e) =>
                      setTaslak((o) => ({
                        ...o,
                        [alan]: e.target.value || null,
                      }))
                    }
                    className="w-full rounded-lg border border-white/15 bg-background px-3 py-2 text-sm"
                  >
                    <option value="">{t('baglantilar.google.secilmedi')}</option>
                    {tumu.map((s) => (
                      <option key={s.kimlik} value={s.kimlik}>
                        {s.ad}
                      </option>
                    ))}
                  </select>
                  {!meta.kapsamlar[kisa] && <span className="mt-1 block text-xs text-amber-300">{t('baglantilar.google.kapsamYok')}</span>}
                  {kisa === 'ig' && kaynaklar && secenekler.length === 0 && meta.kapsamlar.ig && (
                    <span className="mt-1 block text-xs text-muted-foreground" data-testid="meta-ig-yok">
                      {t('baglantilar.meta.igYok')}
                    </span>
                  )}
                  {kaynakHatasi && meta.kapsamlar[kisa] && (
                    <span className="mt-1 block text-xs text-amber-300" data-kaynak-hatasi={kaynakHatasi}>
                      {t(`baglantilar.hata.${kaynakHatasi}`, {
                        defaultValue: t('baglantilar.hata.genel'),
                      })}
                    </span>
                  )}
                </label>
              );
            })}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              className="!bg-transparent border-white/20"
              onClick={() => void kaydet()}
              disabled={!degisti || islem !== ''}
              data-testid="meta-secim-kaydet"
            >
              {islem === 'kaydet' ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
              {t('baglantilar.google.secimKaydet')}
            </Button>
            <Button
              size="sm"
              onClick={() => void esitle()}
              disabled={!secimVar || degisti || beklemeDk > 0 || islem !== ''}
              data-testid="meta-esitle"
            >
              {islem === 'esitle' ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
              {islem === 'esitle' ? t('baglantilar.google.esitleniyor') : t('baglantilar.google.esitle')}
            </Button>
            {beklemeDk > 0 && <span className="text-xs text-muted-foreground">{t('baglantilar.google.bekle', { sayi: beklemeDk })}</span>}
            {!secimVar && <span className="text-xs text-muted-foreground">{t('baglantilar.google.onceSecin')}</span>}
          </div>
        </div>
      )}

      {(meta.durum === 'bagli' || meta.durum === 'yeniden_baglan') && (
        <div className="mt-6 space-y-2 border-t border-white/10 pt-4 text-xs">
          <p className="flex items-center gap-1.5 text-muted-foreground" data-testid="meta-son-esitleme">
            <Clock className="h-3.5 w-3.5" />
            {t('baglantilar.google.sonEsitleme')}: {meta.son_esitleme ? tarihBicimle(meta.son_esitleme, dil, true) : t('baglantilar.google.hic')}
          </p>
          {hatalar.length > 0 && (
            <ul className="space-y-1" data-testid="meta-hata">
              {hatalar.map(([kaynak, kod]) => (
                <li key={kaynak} className="flex items-start gap-1.5 text-amber-300" data-hata-kodu={kod}>
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  <span>
                    {t(`baglantilar.kaynak.${kaynak}`, {
                      defaultValue: kaynak,
                    })}
                    :{' '}
                    {t(`baglantilar.hata.${kod}`, {
                      defaultValue: t('baglantilar.hata.genel'),
                    })}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <div className="pt-2">
            <Button
              size="sm"
              variant="outline"
              className="!bg-transparent border-red-400/40 text-red-300"
              onClick={() => void kaldir()}
              disabled={islem !== ''}
              data-testid="meta-kaldir"
            >
              {islem === 'kaldir' ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Unplug className="mr-2 h-4 w-4" />}
              {t('baglantilar.google.kaldir')}
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
