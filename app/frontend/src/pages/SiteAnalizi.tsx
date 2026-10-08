import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ArrowRight, CheckCircle2, Loader2, Mail, Search, Wrench } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import AydinlatmaSatiri from '@/components/AydinlatmaSatiri';
import { BolumKarti, PuanHalkasi } from '@/components/SiteRaporGorunumu';
import {
  BOLUM_SIRASI,
  SiteAnaliziHatasi,
  analizBaslat,
  tamRaporIste,
  type AnalizOzeti,
} from '@/lib/siteAnalizi';
import { DEFAULT_LANGUAGE, LANGUAGE_CODES, localizedPath } from '../../prerender/site.js';

/**
 * Ücretsiz Site Analiz Raporu (herkese açık, `/site-analizi`).
 *
 * Ziyaretçi alan adını yazıyor; sunucu siteyi dışarıdan inceleyip altı
 * bölümde puanlıyor. Burada yalnız ÖZET görünüyor (bölüm başına en çok 3
 * bulgu). Tam rapor e-postayla geliyor: e-posta bırakan ziyaretçi
 * `inquiries`'e aday olarak düşüyor. Faz 4G: onay kutusu yok — talep
 * aydınlatmayla işleniyor (gönder düğmesinin altındaki satır + /gizlilik).
 * Pazarlama izni AYRI, isteğe bağlı, varsayılan işaretsiz; yalnız site ayarı
 * açıksa (sunucu analiz yanıtında `pazarlama_izni_sor` ile bildiriyor).
 *
 * Analiz ~30 saniye sürebiliyor (PageSpeed ölçümü dahil); bekleme
 * sırasında bölüm iskeletleri gösteriliyor ki sayfa donmuş görünmesin.
 *
 * Faz 4S: ücretsiz SEO araçlarının "Sitenin tam analizini al" düğmesi buraya
 * adresle geliyor. Uygulama içi geçişte (router state `{url, arac, otomatik}`)
 * analiz kendiliğinden başlar; `?url=` (ör. sonuç e-postasındaki bağlantı)
 * yalnız alanı doldurur — dışarıdan verilen bir bağlantı kendi başına analiz
 * başlatmasın. `arac` analize yazılır (yönetici özetinde araçtan gelen geçiş).
 */

const GIRDI =
  'w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2.5 text-sm text-white placeholder:text-muted-foreground focus:border-primary focus:outline-none';

export default function SiteAnalizi() {
  const { t, i18n } = useTranslation();
  const dil = LANGUAGE_CODES.includes(i18n.language) ? i18n.language : DEFAULT_LANGUAGE;

  const konum = useLocation();
  const gelen = (() => {
    const durum = konum.state as { url?: unknown; arac?: unknown; otomatik?: unknown } | null;
    const sorgu = new URLSearchParams(konum.search);
    const url = typeof durum?.url === 'string' ? durum.url : sorgu.get('url') || '';
    const arac = typeof durum?.arac === 'string' ? durum.arac : sorgu.get('arac') || '';
    return { url: url.slice(0, 2000), arac: /^[a-z0-9-]{1,40}$/.test(arac) ? arac : '', otomatik: durum?.otomatik === true };
  })();
  const [adres, setAdres] = useState(gelen.url);
  const [aracKaynagi, setAracKaynagi] = useState(gelen.arac);
  const [calisiyor, setCalisiyor] = useState(false);
  const [ozet, setOzet] = useState<AnalizOzeti | null>(null);
  const [hataKodu, setHataKodu] = useState<string | null>(null);

  const [ad, setAd] = useState('');
  const [eposta, setEposta] = useState('');
  const [pazarlama, setPazarlama] = useState(false);
  const [gonderiliyor, setGonderiliyor] = useState(false);
  const [gonderildi, setGonderildi] = useState(false);
  const [formHatasi, setFormHatasi] = useState<string | null>(null);

  const hataMetni = (kod: string) => t(`siteAnalizi.hata.${kod}`, { defaultValue: t('siteAnalizi.hata.genel') });

  const baslat = async (hedef: string) => {
    if (calisiyor) return;
    if (!hedef.trim()) {
      setHataKodu('adres_gecersiz');
      return;
    }
    setCalisiyor(true);
    setHataKodu(null);
    setOzet(null);
    setGonderildi(false);
    setFormHatasi(null);
    try {
      setOzet(await analizBaslat(hedef.trim(), aracKaynagi || null));
    } catch (hata) {
      setHataKodu(hata instanceof SiteAnaliziHatasi ? hata.kod : 'genel');
    } finally {
      setCalisiyor(false);
    }
  };

  const analizEt = (olay: FormEvent) => {
    olay.preventDefault();
    void baslat(adres);
  };

  // SEO aracından uygulama içi geçiş: bir kez, kendiliğinden başlat.
  const otomatikBasladi = useRef(false);
  useEffect(() => {
    if (otomatikBasladi.current || !gelen.otomatik || !gelen.url) return;
    otomatikBasladi.current = true;
    void baslat(gelen.url);
    // Yalnız ilk açılışta; sonraki çizimler yeniden başlatmasın.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const tamRaporGonder = async (olay: FormEvent) => {
    olay.preventDefault();
    if (!ozet || gonderiliyor) return;
    setGonderiliyor(true);
    setFormHatasi(null);
    try {
      await tamRaporIste(ozet.id, {
        eposta: eposta.trim(),
        ad: ad.trim() || undefined,
        pazarlama_izni: Boolean(ozet.pazarlama_izni_sor && pazarlama),
        dil,
      });
      setGonderildi(true);
    } catch (hata) {
      setFormHatasi(hata instanceof SiteAnaliziHatasi ? hata.kod : 'genel');
    } finally {
      setGonderiliyor(false);
    }
  };

  const yeniAnaliz = () => {
    setPazarlama(false);
    setOzet(null);
    setAdres('');
    setAracKaynagi('');
    setGonderildi(false);
    setHataKodu(null);
  };

  const bolumler = ozet
    ? BOLUM_SIRASI.map((a) => ozet.bolumler.find((b) => b.anahtar === a)).filter(
        (b): b is NonNullable<typeof b> => Boolean(b),
      )
    : [];

  return (
    <div className="pt-32 pb-24">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="max-w-3xl mb-10">
          <p className="text-xs uppercase tracking-[0.3em] text-purple-300 mb-4">{t('siteAnalizi.etiket')}</p>
          <h1 className="text-4xl sm:text-5xl font-bold leading-tight mb-5">
            {t('siteAnalizi.baslik1')} <span className="gradient-text">{t('siteAnalizi.baslikVurgu')}</span>
          </h1>
          <p className="text-lg text-muted-foreground">{t('siteAnalizi.giris')}</p>
        </div>

        <form
          onSubmit={analizEt}
          className="cam-kart cam-mor rounded-2xl border border-white/10 bg-white/[0.03] p-4 sm:p-6"
          aria-label={t('siteAnalizi.adresEtiketi')}
        >
          <label htmlFor="analiz-adres" className="mb-2 block text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
            {t('siteAnalizi.adresEtiketi')}
          </label>
          <div className="flex flex-col gap-3 sm:flex-row">
            <input
              id="analiz-adres"
              value={adres}
              onChange={(o) => setAdres(o.target.value)}
              placeholder={t('siteAnalizi.adresOrnek')}
              inputMode="url"
              autoComplete="url"
              spellCheck={false}
              disabled={calisiyor}
              className={`${GIRDI} h-12 text-base`}
            />
            <Button type="submit" disabled={calisiyor} className="h-12 gap-2 px-6 sm:flex-none">
              {calisiyor ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <Search className="h-4 w-4" aria-hidden="true" />
              )}
              {calisiyor ? t('siteAnalizi.calisiyor') : t('siteAnalizi.analizEt')}
            </Button>
          </div>
          <p className="mt-3 text-xs text-muted-foreground">{t('siteAnalizi.neOlcuyor')}</p>
          {/* Faz 4S: tek konuya bakan ücretsiz SEO araçları (meta, schema, robots.txt, SSL…). */}
          <p className="mt-2 text-xs text-muted-foreground" data-seo-araclari-baglanti>
            {t('siteAnalizi.araclar.metin')}{' '}
            <Link to={localizedPath(dil, 'seoAraclari')} className="inline-flex items-center gap-1 font-semibold text-purple-300 hover:underline">
              <Wrench className="h-3 w-3" aria-hidden="true" />
              {t('siteAnalizi.araclar.dugme')}
            </Link>
          </p>
          {hataKodu && (
            <p role="alert" className="mt-3 rounded-lg border border-red-400/30 bg-red-500/10 px-3 py-2 text-sm text-red-200">
              {hataMetni(hataKodu)}
            </p>
          )}
        </form>

        {calisiyor && (
          <div className="mt-10" aria-live="polite" aria-busy="true">
            <p className="mb-5 flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              {t('siteAnalizi.bekleyin')}
            </p>
            <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
              {BOLUM_SIRASI.map((a) => (
                <div key={a} className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold">{t(`siteAnalizi.bolum.${a}`)}</span>
                    <span className="h-6 w-10 animate-pulse rounded bg-white/10" />
                  </div>
                  <div className="mt-5 space-y-3">
                    <div className="h-3 w-5/6 animate-pulse rounded bg-white/10" />
                    <div className="h-3 w-2/3 animate-pulse rounded bg-white/10" />
                    <div className="h-3 w-3/4 animate-pulse rounded bg-white/10" />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {ozet && (
          <div className="mt-10 space-y-8" aria-live="polite">
            <div className="cam-kart cam-gok flex flex-col items-center gap-6 rounded-3xl border border-white/10 bg-white/[0.03] p-6 sm:flex-row md:p-8">
              <PuanHalkasi puan={ozet.puan} boyut={144} etiket={t('siteAnalizi.genelPuan')} />
              <div className="min-w-0 flex-1 text-center sm:text-left">
                <h2 className="break-all text-2xl font-bold md:text-3xl">{ozet.alan_adi}</h2>
                <p className="mt-2 text-sm text-muted-foreground">{t('siteAnalizi.ozetNotu')}</p>
                <button
                  type="button"
                  onClick={yeniAnaliz}
                  className="mt-3 text-sm text-purple-300 underline-offset-4 hover:underline"
                >
                  {t('siteAnalizi.yeniAnaliz')}
                </button>
              </div>
            </div>

            <div className="cam-dongu grid gap-5 md:grid-cols-2 lg:grid-cols-3">
              {bolumler.map((b) => (
                <BolumKarti key={b.anahtar} bolum={b} />
              ))}
            </div>

            <section
              className="cam-kart cam-mor rounded-3xl border border-white/10 bg-white/[0.03] p-6 md:p-10"
              aria-labelledby="tam-rapor-baslik"
            >
              {gonderildi ? (
                <div className="py-6 text-center">
                  <CheckCircle2 className="mx-auto mb-3 h-10 w-10 text-emerald-400" aria-hidden="true" />
                  <p className="text-lg font-semibold">{t('siteAnalizi.tamRapor.basarili')}</p>
                  <p className="mt-2 text-sm text-muted-foreground">{t('siteAnalizi.tamRapor.basariliAciklama')}</p>
                </div>
              ) : (
                <form onSubmit={tamRaporGonder} className="grid gap-8 lg:grid-cols-2">
                  <div>
                    <h2 id="tam-rapor-baslik" className="flex items-center gap-2 text-2xl font-bold md:text-3xl">
                      <Mail className="h-6 w-6 text-purple-300" aria-hidden="true" />
                      {t('siteAnalizi.tamRapor.baslik')}
                    </h2>
                    <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                      {t('siteAnalizi.tamRapor.aciklama')}
                    </p>
                  </div>
                  <div className="space-y-3">
                    <input
                      value={ad}
                      onChange={(o) => setAd(o.target.value)}
                      placeholder={t('siteAnalizi.tamRapor.ad')}
                      autoComplete="name"
                      maxLength={120}
                      className={GIRDI}
                    />
                    <input
                      required
                      type="email"
                      value={eposta}
                      onChange={(o) => setEposta(o.target.value)}
                      placeholder={t('siteAnalizi.tamRapor.eposta')}
                      autoComplete="email"
                      className={GIRDI}
                    />
                    {ozet.pazarlama_izni_sor && (
                      <label className="flex cursor-pointer items-start gap-2 text-xs leading-relaxed text-muted-foreground">
                        <input
                          type="checkbox"
                          checked={pazarlama}
                          onChange={(o) => setPazarlama(o.target.checked)}
                          className="mt-0.5 h-4 w-4 flex-none accent-emerald-500"
                          data-pazarlama-izni
                        />
                        <span>
                          {t('siteAnalizi.tamRapor.pazarlama')}{' '}
                          <span className="opacity-70">({t('siteAnalizi.tamRapor.istegeBagli')})</span>
                        </span>
                      </label>
                    )}
                    {formHatasi && (
                      <p role="alert" className="text-sm text-red-300">
                        {hataMetni(formHatasi)}
                      </p>
                    )}
                    <Button type="submit" disabled={gonderiliyor} className="h-11 w-full gap-2">
                      {gonderiliyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}
                      {t('siteAnalizi.tamRapor.gonder')}
                    </Button>
                    <AydinlatmaSatiri />
                  </div>
                </form>
              )}
            </section>

            <section className="cam-kart rounded-3xl border border-white/10 bg-white/[0.03] p-6 text-center md:p-10">
              <h2 className="text-2xl font-bold">{t('siteAnalizi.teklif.baslik')}</h2>
              <p className="mx-auto mt-3 max-w-2xl text-sm text-muted-foreground">{t('siteAnalizi.teklif.aciklama')}</p>
              <div className="mt-6 flex flex-wrap justify-center gap-3">
                <Button asChild className="h-11 gap-2">
                  <Link to={localizedPath(dil, 'contact')}>
                    {t('siteAnalizi.teklif.teklifAl')}
                    <ArrowRight className="h-4 w-4" aria-hidden="true" />
                  </Link>
                </Button>
                <Button asChild variant="outline" className="h-11">
                  <Link to={localizedPath(dil, 'services')}>{t('siteAnalizi.teklif.hizmetler')}</Link>
                </Button>
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
