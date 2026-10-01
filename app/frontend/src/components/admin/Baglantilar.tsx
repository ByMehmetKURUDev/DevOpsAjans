import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Copy,
  Facebook,
  Link2,
  Loader2,
  LogIn,
  RefreshCw,
  Save,
  Store,
  Unplug,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  durumGetir,
  googleBaslat,
  googleBul,
  googleEsitle,
  googleKaldir,
  googleKaynaklari,
  googleSecimKaydet,
  hataMetni,
  type BaglantiDurumListesi,
  type GoogleKaynaklari,
  type KaynakKisa,
  type Secimler,
} from '@/lib/baglantilar';
import { tarihBicimle } from '@/lib/siteBakim';

/**
 * Yönetici › Bağlantılar (Faz 3B).
 *
 * Google kartı: kurulum durumu (eksik ortam değişkeninin yalnız ADI), "Google
 * ile bağlan", bağlı hesap, üç seçim (GA4 mülkü / Search Console sitesi /
 * YouTube kanalı), "Şimdi eşitle", son eşitleme ve hata, "Bağlantıyı kaldır".
 * Google Business Profile ve Meta için "yakında" kartları.
 *
 * Google'dan dönüşte adres `?sekme=baglantilar&sonuc=<kod>`: sonuç bir kez
 * gösterilir ve adresten silinir (yenileyince tekrar çıkmasın).
 */

const SECIM_ALANI: Record<KaynakKisa, keyof Secimler> = { ga4: 'ga4_mulk', sc: 'sc_site', yt: 'yt_kanal' };
const KAYNAKLAR: KaynakKisa[] = ['ga4', 'sc', 'yt'];
const BASARILI_SONUC = 'baglandi';

function sonucuOku(): string | null {
  try {
    const sonuc = new URLSearchParams(window.location.search).get('sonuc');
    return sonuc ? sonuc.replace(/[^a-z_]/g, '').slice(0, 40) || null : null;
  } catch {
    return null;
  }
}

/** `sonuc` adresten silinir (sayfa yenilenince mesaj tekrar çıkmasın); `sekme` kalır. */
function sonucuAdrestenSil() {
  try {
    const params = new URLSearchParams(window.location.search);
    if (!params.has('sonuc')) return;
    params.delete('sonuc');
    const kalan = params.toString();
    window.history.replaceState(window.history.state, '', `${window.location.pathname}${kalan ? `?${kalan}` : ''}`);
  } catch {
    /* tarayıcı dışı */
  }
}

export default function Baglantilar() {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [durum, setDurum] = useState<BaglantiDurumListesi | null>(null);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [yuklemeHatasi, setYuklemeHatasi] = useState('');
  const [sonuc] = useState<string | null>(() => sonucuOku());
  const [kaynaklar, setKaynaklar] = useState<GoogleKaynaklari | null>(null);
  const [kaynakYukleniyor, setKaynakYukleniyor] = useState(false);
  const [taslak, setTaslak] = useState<Secimler>({ ga4_mulk: null, sc_site: null, yt_kanal: null });
  const [islem, setIslem] = useState<'' | 'baglan' | 'kaydet' | 'esitle' | 'kaldir'>('');

  const google = googleBul(durum);

  const yukle = useCallback(async () => {
    try {
      const d = await durumGetir();
      setDurum(d);
      setYuklemeHatasi('');
      const g = googleBul(d);
      if (g) setTaslak(g.secimler);
    } catch (e) {
      setYuklemeHatasi(hataMetni(t, e));
    } finally {
      setYukleniyor(false);
    }
  }, [t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  useEffect(() => {
    sonucuAdrestenSil();
  }, []);

  const bagli = google?.durum === 'bagli';
  useEffect(() => {
    if (!bagli) {
      setKaynaklar(null);
      return;
    }
    let iptal = false;
    setKaynakYukleniyor(true);
    googleKaynaklari()
      .then((k) => {
        if (iptal) return;
        setKaynaklar(k);
        // Tek seçenek varsa ve henüz seçilmemişse taslağa koy (kaydetmek yine yöneticide).
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
    () => !!google && (Object.keys(SECIM_ALANI) as KaynakKisa[]).some((k) => (taslak[SECIM_ALANI[k]] || null) !== (google.secimler[SECIM_ALANI[k]] || null)),
    [google, taslak]
  );

  const baglan = async () => {
    setIslem('baglan');
    try {
      const { adres } = await googleBaslat();
      window.location.assign(adres);
    } catch (e) {
      toast.error(hataMetni(t, e));
      setIslem('');
    }
  };

  const kaydet = async () => {
    setIslem('kaydet');
    try {
      await googleSecimKaydet(taslak);
      toast.success(t('baglantilar.google.secimKaydedildi'));
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setIslem('');
    }
  };

  const esitle = async () => {
    setIslem('esitle');
    try {
      const s = await googleEsitle();
      setDurum(s.durum);
      if (Object.keys(s.hatalar || {}).length) toast.warning(t('baglantilar.google.kismenEsitlendi'));
      else toast.success(t('baglantilar.google.esitlendi', { sayi: s.yazilan }));
    } catch (e) {
      toast.error(hataMetni(t, e));
      await yukle();
    } finally {
      setIslem('');
    }
  };

  const kaldir = async () => {
    if (!window.confirm(t('baglantilar.google.kaldirOnay'))) return;
    setIslem('kaldir');
    try {
      const s = await googleKaldir();
      if (s.iptal_edildi) toast.success(t('baglantilar.google.kaldirildi'));
      else toast.warning(t('baglantilar.google.iptalEdilemedi'));
      await yukle();
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

  if (yukleniyor) {
    return (
      <div className="flex items-center justify-center py-20 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" />
      </div>
    );
  }

  const hatalar = google ? Object.entries(google.son_hata || {}) : [];
  const beklemeDk = google ? Math.ceil((google.elle_bekleme_sn || 0) / 60) : 0;
  const secimVar = google ? Object.values(google.secimler).some(Boolean) : false;

  return (
    <div className="space-y-6" data-testid="baglantilar">
      <div>
        <h2 className="flex items-center gap-2 text-xl font-semibold">
          <Link2 className="h-5 w-5" />
          {t('baglantilar.baslik')}
        </h2>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t('baglantilar.aciklama')}</p>
      </div>

      {sonuc && (
        <div
          data-testid="baglanti-sonuc"
          data-sonuc={sonuc}
          className={`flex items-start gap-2 rounded-xl border p-4 text-sm ${
            sonuc === BASARILI_SONUC
              ? 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200'
              : 'border-amber-500/30 bg-amber-500/10 text-amber-100'
          }`}
        >
          {sonuc === BASARILI_SONUC ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" /> : <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />}
          <span>{t(`baglantilar.sonuc.${sonuc}`, { defaultValue: t('baglantilar.sonuc.google_hatasi') })}</span>
        </div>
      )}

      {yuklemeHatasi && (
        <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">{yuklemeHatasi}</div>
      )}

      {durum?.test_modu && (
        <p className="inline-flex rounded-full border border-cyan-400/30 bg-cyan-500/10 px-3 py-1 text-xs text-cyan-200" data-testid="test-modu">
          {t('baglantilar.testModu')}
        </p>
      )}

      {google && (
        <section
          className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6"
          data-testid="google-karti"
          data-durum={google.durum}
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="text-lg font-semibold">{t('baglantilar.google.ad')}</h3>
              <p className="text-xs text-muted-foreground">{t('baglantilar.google.altBaslik')}</p>
            </div>
            <span
              className={`rounded-full px-3 py-1 text-xs font-medium ${
                google.durum === 'bagli'
                  ? 'bg-emerald-500/15 text-emerald-300'
                  : google.durum === 'yeniden_baglan'
                    ? 'bg-red-500/15 text-red-300'
                    : 'bg-white/10 text-muted-foreground'
              }`}
              data-testid="google-durum"
            >
              {t(`baglantilar.google.durum.${google.durum}`)}
            </span>
          </div>

          {google.durum === 'kurulmadi' && (
            <div className="mt-4 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm" data-testid="google-kurulum">
              <p className="font-medium text-amber-100">{t('baglantilar.google.kurulumBaslik')}</p>
              <p className="mt-1 text-amber-200/90">{t('baglantilar.google.kurulumAciklama')}</p>
              {google.kurulum.eksik.length > 0 && (
                <p className="mt-2">
                  {t('baglantilar.google.eksik')}:{' '}
                  {google.kurulum.eksik.map((ad) => (
                    <code key={ad} className="mr-2 rounded bg-black/30 px-1.5 py-0.5 text-xs" data-eksik={ad}>
                      {ad}
                    </code>
                  ))}
                </p>
              )}
              {google.kurulum.gecersiz.length > 0 && (
                <p className="mt-2">
                  {t('baglantilar.google.gecersiz')}:{' '}
                  {google.kurulum.gecersiz.map((ad) => (
                    <code key={ad} className="mr-2 rounded bg-black/30 px-1.5 py-0.5 text-xs">
                      {ad}
                    </code>
                  ))}
                </p>
              )}
              <p className="mt-2 text-xs text-amber-200/80">{t('baglantilar.google.rehber')}</p>
            </div>
          )}

          {(google.durum === 'kurulmadi' || google.durum === 'bagli_degil') && durum && (
            <div className="mt-4 text-xs text-muted-foreground">
              <p>{t('baglantilar.google.yonlendirme')}</p>
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <code className="break-all rounded bg-black/30 px-2 py-1" data-testid="yonlendirme-adresi">
                  {durum.yonlendirme_adresi}
                </code>
                <button
                  type="button"
                  onClick={() => void kopyala(durum.yonlendirme_adresi)}
                  className="inline-flex items-center gap-1 text-purple-300 hover:text-pink-300"
                >
                  <Copy className="h-3.5 w-3.5" />
                  {t('baglantilar.google.kopyala')}
                </button>
              </div>
            </div>
          )}

          {google.durum === 'bagli_degil' && (
            <div className="mt-5 space-y-3">
              <p className="text-sm text-muted-foreground">{t('baglantilar.google.baglanAciklama')}</p>
              <Button onClick={() => void baglan()} disabled={islem !== ''} data-testid="google-baglan">
                {islem === 'baglan' ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <LogIn className="mr-2 h-4 w-4" />}
                {t('baglantilar.google.baglan')}
              </Button>
            </div>
          )}

          {google.durum === 'yeniden_baglan' && (
            <div className="mt-4 space-y-3 rounded-xl border border-red-400/30 bg-red-500/10 p-4 text-sm" data-testid="google-yeniden">
              <p className="text-red-200">{t('baglantilar.google.yenidenAciklama')}</p>
              <Button onClick={() => void baglan()} disabled={islem !== ''} data-testid="google-yeniden-baglan">
                {islem === 'baglan' ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
                {t('baglantilar.google.yenidenBaglan')}
              </Button>
            </div>
          )}

          {(google.durum === 'bagli' || google.durum === 'yeniden_baglan') && (
            <dl className="mt-4 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-xs text-muted-foreground">{t('baglantilar.google.hesap')}</dt>
                <dd data-testid="google-hesap">{google.harici_email || '—'}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">{t('baglantilar.google.baglanmaTarihi')}</dt>
                <dd>{tarihBicimle(google.baglanti_tarihi, dil, true)}</dd>
              </div>
            </dl>
          )}

          {google.durum === 'bagli' && (
            <div className="mt-6 space-y-4">
              <h4 className="text-sm font-semibold">{t('baglantilar.google.secimBaslik')}</h4>
              {kaynakYukleniyor && (
                <p className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  {t('baglantilar.google.kaynaklarYukleniyor')}
                </p>
              )}
              <div className="grid gap-4 md:grid-cols-3">
                {KAYNAKLAR.map((kisa) => {
                  const alan = SECIM_ALANI[kisa];
                  const secenekler = kaynaklar?.[kisa] ?? [];
                  const secili = taslak[alan] || '';
                  const kaynakHatasi = kaynaklar?.hatalar?.[kisa];
                  // Kayıtlı seçim listede yoksa da görünsün (ör. erişim kalktı).
                  const tumu = secili && !secenekler.some((s) => s.kimlik === secili) ? [{ kimlik: secili, ad: secili }, ...secenekler] : secenekler;
                  return (
                    <label key={kisa} className="block text-sm">
                      <span className="mb-1 block text-xs text-muted-foreground">{t(`baglantilar.google.${kisa}`)}</span>
                      <select
                        data-testid={`secim-${kisa}`}
                        value={secili}
                        disabled={!google.kapsamlar[kisa] || islem !== ''}
                        onChange={(e) => setTaslak((o) => ({ ...o, [alan]: e.target.value || null }))}
                        className="w-full rounded-lg border border-white/15 bg-background px-3 py-2 text-sm"
                      >
                        <option value="">{t('baglantilar.google.secilmedi')}</option>
                        {tumu.map((s) => (
                          <option key={s.kimlik} value={s.kimlik}>
                            {s.ad}
                          </option>
                        ))}
                      </select>
                      {!google.kapsamlar[kisa] && (
                        <span className="mt-1 block text-xs text-amber-300">{t('baglantilar.google.kapsamYok')}</span>
                      )}
                      {kaynakHatasi && google.kapsamlar[kisa] && (
                        <span className="mt-1 block text-xs text-amber-300" data-kaynak-hatasi={kaynakHatasi}>
                          {t(`baglantilar.hata.${kaynakHatasi}`, { defaultValue: t('baglantilar.hata.genel') })}
                        </span>
                      )}
                    </label>
                  );
                })}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button size="sm" variant="outline" className="!bg-transparent border-white/20" onClick={() => void kaydet()} disabled={!degisti || islem !== ''} data-testid="secim-kaydet">
                  {islem === 'kaydet' ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                  {t('baglantilar.google.secimKaydet')}
                </Button>
                <Button size="sm" onClick={() => void esitle()} disabled={!secimVar || degisti || beklemeDk > 0 || islem !== ''} data-testid="google-esitle">
                  {islem === 'esitle' ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
                  {islem === 'esitle' ? t('baglantilar.google.esitleniyor') : t('baglantilar.google.esitle')}
                </Button>
                {beklemeDk > 0 && (
                  <span className="text-xs text-muted-foreground" data-testid="esitle-bekle">
                    {t('baglantilar.google.bekle', { sayi: beklemeDk })}
                  </span>
                )}
                {!secimVar && <span className="text-xs text-muted-foreground">{t('baglantilar.google.onceSecin')}</span>}
              </div>
            </div>
          )}

          {(google.durum === 'bagli' || google.durum === 'yeniden_baglan') && (
            <div className="mt-6 space-y-2 border-t border-white/10 pt-4 text-xs">
              <p className="flex items-center gap-1.5 text-muted-foreground" data-testid="son-esitleme">
                <Clock className="h-3.5 w-3.5" />
                {t('baglantilar.google.sonEsitleme')}:{' '}
                {google.son_esitleme ? tarihBicimle(google.son_esitleme, dil, true) : t('baglantilar.google.hic')}
              </p>
              {hatalar.length > 0 && (
                <ul className="space-y-1" data-testid="google-hata">
                  {hatalar.map(([kaynak, kod]) => (
                    <li key={kaynak} className="flex items-start gap-1.5 text-amber-300" data-hata-kodu={kod}>
                      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                      <span>
                        {t(`baglantilar.kaynak.${kaynak}`, { defaultValue: kaynak })}:{' '}
                        {t(`baglantilar.hata.${kod}`, { defaultValue: t('baglantilar.hata.genel') })}
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
                  data-testid="google-kaldir"
                >
                  {islem === 'kaldir' ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Unplug className="mr-2 h-4 w-4" />}
                  {t('baglantilar.google.kaldir')}
                </Button>
              </div>
            </div>
          )}
        </section>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {[
          { anahtar: 'google_business', ikon: Store },
          { anahtar: 'meta', ikon: Facebook },
        ].map(({ anahtar, ikon: Ikon }) => (
          <section
            key={anahtar}
            className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6 opacity-80"
            data-testid={`yakinda-${anahtar}`}
          >
            <div className="flex items-start justify-between gap-3">
              <h3 className="flex items-center gap-2 font-semibold">
                <Ikon className="h-4 w-4" />
                {t(`baglantilar.yakinda.${anahtar}.ad`)}
              </h3>
              <span className="rounded-full bg-white/10 px-3 py-1 text-xs text-muted-foreground">{t('baglantilar.yakinda.rozet')}</span>
            </div>
            <p className="mt-2 text-sm text-muted-foreground">{t(`baglantilar.yakinda.${anahtar}.aciklama`)}</p>
            {anahtar === 'google_business' && (
              <p className="mt-2 text-xs text-amber-300" data-testid="gbp-not">
                {t('baglantilar.yakinda.google_business.not')}
              </p>
            )}
          </section>
        ))}
      </div>
    </div>
  );
}
