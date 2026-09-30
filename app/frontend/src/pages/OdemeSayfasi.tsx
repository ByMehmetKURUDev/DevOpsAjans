import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { AlertCircle, CheckCircle2, Copy, CreditCard, Home, Loader2, ShieldCheck } from 'lucide-react';
import {
  acikOdemeGetir,
  paraBicimle,
  shopierBaglantisiIste,
  type AcikOdeme,
} from '@/lib/odemeler';

/**
 * Müşterinin gördüğü ödeme sayfası: `/ode/<jeton>`
 *
 * Panelde "Ödeme bağlantısı" düğmesine basılınca üretilen adres buraya
 * düşüyor. Sayfa oturum istemiyor — bağlantı e-postayla, WhatsApp'la
 * elden ele gidebilir. Bu yüzden arka uç yalnızca ödemek için gereken
 * alanları döndürüyor: tutar, para birimi, açıklama, fatura numarası,
 * son tarih. Müşterinin adı ve e-postası dönmüyor.
 *
 * Kart tahsilatı henüz bağlı değil. `saglayici_hazir` yanlışken sayfa
 * "kartla öde" düğmesi göstermiyor; bunun yerine havale bilgilerini ve
 * dekont gönderme yönergesini gösteriyor. Var olmayan bir düğme
 * koymaktansa müşteriye ne yapacağını açıkça söylemek daha doğru:
 * çalışmayan bir ödeme düğmesi, ödemeyi tamamen kaybettiriyor.
 */

const DURUM_RENGI: Record<string, string> = {
  odendi: 'border-emerald-400/40 bg-emerald-500/10 text-emerald-300',
  bekliyor: 'border-orange-400/40 bg-orange-500/10 text-orange-300',
  basarisiz: 'border-red-400/40 bg-red-500/10 text-red-300',
  iade: 'border-purple-400/40 bg-purple-500/10 text-purple-300',
  iptal: 'border-white/15 bg-white/5 text-muted-foreground',
};

function tarihBicimle(deger?: string | null): string | null {
  if (!deger) return null;
  const t = new Date(deger);
  if (Number.isNaN(t.getTime())) return null;
  return t.toLocaleDateString('tr-TR', { day: '2-digit', month: 'long', year: 'numeric' });
}

export default function OdemeSayfasi() {
  const { jeton } = useParams<{ jeton: string }>();
  const { t } = useTranslation();
  const [kayit, setKayit] = useState<AcikOdeme | null>(null);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [hata, setHata] = useState<string | null>(null);
  const [kopyalandi, setKopyalandi] = useState(false);
  const [gidiyor, setGidiyor] = useState(false);
  const [bekleniyor, setBekleniyor] = useState(false);
  const [kartHatasi, setKartHatasi] = useState<string | null>(null);

  const kartaGit = useCallback(async () => {
    if (!jeton) return;
    setGidiyor(true);
    setKartHatasi(null);
    try {
      const adres = await shopierBaglantisiIste(jeton);
      // Shopier YENİ SEKMEDE açılıyor, bu sayfa arkada kalıyor.
      //
      // Sebebi: Shopier'in yeni API'sinde ödeme sonrası dönüş adresi
      // verilemiyor — ürün oluştururken böyle bir alan yok. Aynı
      // sekmede gitseydik müşteri ödemeyi bitirince Shopier'in kendi
      // sayfasında kalır, faturasının kapandığını hiç görmezdi.
      //
      // Bu sayfa arkada açık kalıp durumu yoklamaya başlıyor; ödeme
      // düşünce kendiliğinden "Ödendi"ye dönüyor. Dönüş adresini
      // taklit etmek yerine ihtiyacı doğrudan karşılıyor.
      window.open(adres, '_blank', 'noopener');
      setBekleniyor(true);
    } catch {
      setKartHatasi(t('odeme.sayfa.kartHatasi'));
    } finally {
      setGidiyor(false);
    }
  }, [jeton, t]);

  // Shopier sekmesi açıkken durumu yokluyoruz. Ödeme webhook ile
  // düşüyor; birkaç saniye sürebiliyor, bu yüzden 4 saniyede bir
  // soruluyor ve ödendiğinde yoklama kendiliğinden duruyor.
  useEffect(() => {
    if (!bekleniyor || !jeton) return;
    if (kayit?.durum === 'odendi') return;

    const zamanlayici = window.setInterval(() => {
      void acikOdemeGetir(jeton)
        .then((guncel) => {
          setKayit(guncel);
          if (guncel.durum === 'odendi') setBekleniyor(false);
        })
        .catch(() => {
          /* geçici ağ hatası: bir sonraki turda yine denenecek */
        });
    }, 4000);

    return () => window.clearInterval(zamanlayici);
  }, [bekleniyor, jeton, kayit?.durum]);

  // Bu adres arama sonuçlarında çıkmamalı: her jeton tek bir faturaya
  // ait. Prerender listesine girmiyor, burada da çalışma anında
  // noindex veriliyor — bağlantı bir yerde paylaşılırsa diye.
  useEffect(() => {
    const etiket = document.createElement('meta');
    etiket.name = 'robots';
    etiket.content = 'noindex, nofollow';
    document.head.appendChild(etiket);
    return () => {
      etiket.remove();
    };
  }, []);

  useEffect(() => {
    let iptal = false;
    if (!jeton) {
      setHata(t('odeme.sayfa.bulunamadi'));
      setYukleniyor(false);
      return;
    }
    setYukleniyor(true);
    acikOdemeGetir(jeton)
      .then((v) => {
        if (!iptal) {
          setKayit(v);
          setHata(null);
        }
      })
      .catch(() => {
        if (!iptal) setHata(t('odeme.sayfa.bulunamadi'));
      })
      .finally(() => {
        if (!iptal) setYukleniyor(false);
      });
    return () => {
      iptal = true;
    };
  }, [jeton, t]);

  const referansiKopyala = useCallback(async () => {
    const referans = kayit?.invoice_no || kayit?.jeton || '';
    if (!referans) return;
    try {
      await navigator.clipboard.writeText(referans);
      setKopyalandi(true);
      setTimeout(() => setKopyalandi(false), 1600);
    } catch {
      /* pano izni yoksa müşteri elle yazabiliyor, sessiz geçiyoruz */
    }
  }, [kayit]);

  if (yukleniyor) {
    return (
      <section className="min-h-[70vh] flex items-center justify-center px-4">
        <Loader2 className="h-6 w-6 animate-spin text-primary" aria-hidden="true" />
        <span className="sr-only">{t('odeme.sayfa.yukleniyor')}</span>
      </section>
    );
  }

  if (hata || !kayit) {
    return (
      <section className="min-h-[70vh] flex items-center justify-center px-4 py-20">
        <div className="max-w-md w-full text-center">
          <AlertCircle className="mx-auto h-10 w-10 text-orange-300" aria-hidden="true" />
          <h1 className="mt-5 text-2xl font-bold text-white">{t('odeme.sayfa.bulunamadi')}</h1>
          <p className="mt-3 text-sm text-muted-foreground">{t('odeme.sayfa.bulunamadiAciklama')}</p>
          <Link
            to="/"
            className="mt-7 inline-flex items-center justify-center gap-2 rounded-xl border border-white/15 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:border-primary/50"
          >
            <Home className="h-4 w-4" aria-hidden="true" />
            {t('odeme.sayfa.anaSayfa')}
          </Link>
        </div>
      </section>
    );
  }

  const durum = kayit.durum || 'bekliyor';
  const odendi = durum === 'odendi';
  const kapali = durum === 'iptal';
  const sonTarih = tarihBicimle(kayit.son_tarih);
  const referans = kayit.invoice_no || kayit.jeton;

  return (
    <section className="min-h-[70vh] px-4 py-14 sm:py-20">
      <div className="mx-auto w-full max-w-lg">
        <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-6 backdrop-blur-xl sm:p-8">
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs uppercase tracking-[0.25em] text-muted-foreground">
              {t('odeme.sayfa.baslik')}
            </p>
            <span
              className={`rounded-full border px-3 py-1 text-[11px] font-semibold ${
                DURUM_RENGI[durum] || DURUM_RENGI.bekliyor
              }`}
            >
              {t(`odeme.durum.${durum}`)}
            </span>
          </div>

          <p className="mt-6 text-4xl font-bold text-white sm:text-5xl">
            {paraBicimle(kayit.tutar, kayit.para_birimi)}
          </p>

          {kayit.aciklama ? (
            <p className="mt-3 text-sm text-muted-foreground">{kayit.aciklama}</p>
          ) : null}

          <dl className="mt-6 space-y-2.5 border-t border-white/10 pt-5 text-sm">
            {kayit.invoice_no ? (
              <div className="flex items-center justify-between gap-4">
                <dt className="text-muted-foreground">{t('odeme.sayfa.faturaNo')}</dt>
                <dd className="font-mono text-white">{kayit.invoice_no}</dd>
              </div>
            ) : null}
            {sonTarih ? (
              <div className="flex items-center justify-between gap-4">
                <dt className="text-muted-foreground">{t('odeme.sayfa.sonTarih')}</dt>
                <dd className="text-white">{sonTarih}</dd>
              </div>
            ) : null}
          </dl>

          {odendi ? (
            <div className="mt-7 flex items-start gap-3 rounded-xl border border-emerald-400/30 bg-emerald-500/10 p-4">
              <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-300" aria-hidden="true" />
              <p className="text-sm text-emerald-100">{t('odeme.sayfa.odendiMesaj')}</p>
            </div>
          ) : kapali ? (
            <div className="mt-7 flex items-start gap-3 rounded-xl border border-white/15 bg-white/[0.04] p-4">
              <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground" aria-hidden="true" />
              <p className="text-sm text-muted-foreground">{t('odeme.sayfa.iptalMesaj')}</p>
            </div>
          ) : kayit.saglayici_hazir ? (
            <div className="mt-7 space-y-3">
              <p className="text-sm text-muted-foreground">{t('odeme.sayfa.kartAciklama')}</p>
              {kartHatasi ? <p className="text-sm text-red-300">{kartHatasi}</p> : null}
              <button
                type="button"
                onClick={() => void kartaGit()}
                disabled={gidiyor}
                className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-6 py-3 text-sm font-semibold text-black transition-opacity disabled:opacity-60"
              >
                {gidiyor ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <CreditCard className="h-4 w-4" aria-hidden="true" />
                )}
                {gidiyor
                  ? t('odeme.sayfa.yonlendiriliyor')
                  : bekleniyor
                    ? t('odeme.sayfa.tekrarAc')
                    : t('odeme.sayfa.kartlaOde')}
              </button>
              {bekleniyor ? (
                <div className="flex items-start gap-2 rounded-lg border border-primary/25 bg-primary/[0.06] p-3">
                  <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-primary" aria-hidden="true" />
                  <p className="text-xs leading-relaxed text-muted-foreground">
                    {t('odeme.sayfa.bekleniyor')}
                  </p>
                </div>
              ) : null}
              <p className="text-xs leading-relaxed text-muted-foreground">
                {t('odeme.sayfa.hemenAlNotu')}
              </p>
              <p className="text-xs leading-relaxed text-muted-foreground">
                {t('odeme.sayfa.kartNotu')}
              </p>
            </div>
          ) : (
            <div className="mt-7 rounded-xl border border-white/10 bg-white/[0.04] p-4">
              <p className="text-sm font-semibold text-white">{t('odeme.sayfa.havaleBaslik')}</p>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                {t('odeme.sayfa.havaleAciklama')}
              </p>
              <div className="mt-4 flex items-center justify-between gap-3 rounded-lg border border-dashed border-primary/30 bg-primary/[0.05] px-3 py-2">
                <div className="min-w-0">
                  <p className="text-[11px] uppercase tracking-wider text-muted-foreground">
                    {t('odeme.sayfa.aciklamaAlani')}
                  </p>
                  <code className="block truncate font-mono text-sm text-primary">{referans}</code>
                </div>
                <button
                  type="button"
                  onClick={() => void referansiKopyala()}
                  className="inline-flex shrink-0 items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium text-white/80 transition-colors hover:bg-white/10"
                >
                  {kopyalandi ? (
                    <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                  ) : (
                    <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                  )}
                  {kopyalandi ? t('odeme.kopyalandi') : t('odeme.kopyala')}
                </button>
              </div>
              <a
                href="/contact"
                className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-xl border border-primary/40 px-5 py-2.5 text-sm font-semibold text-primary transition-colors hover:bg-primary/10"
              >
                {t('odeme.sayfa.iletisim')}
              </a>
            </div>
          )}

          <p className="mt-6 flex items-center justify-center gap-2 text-[11px] text-muted-foreground">
            <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
            {t('odeme.sayfa.guvenlikNotu')}
          </p>
        </div>
      </div>
    </section>
  );
}
