import { useCallback, useEffect, useState, type ReactElement } from 'react';
import { Link, useParams } from 'react-router-dom';
import { AlertCircle, Ban, CheckCircle2, Clock, FileDown, FileSignature, Home, Loader2, Scale } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import GuvenliMarkdown from '@/components/asistanlar/GuvenliMarkdown';
import ImzaTuvali from '@/components/belge/ImzaTuvali';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { BelgeHatasi, tarihBicimle } from '@/lib/belge';
import { getAPIBaseURL } from '@/lib/config';
import { acikSozlesme, acikSozlesmeImza, acikSozlesmePdf, sozlesmeDurumRengi, type Sozlesme } from '@/lib/sozlesmeler';

/**
 * Girişsiz sözleşme imza sayfası: `/sozlesme/<jeton>` (Faz 3T).
 *
 * Metni gösterir; "okudum ve kabul ediyorum" + ad soyad (+ isteğe bağlı
 * çizim) ile basit elektronik imza. İmza isteği gösterilen metnin SHA-256
 * özetini taşıyor; metin bu arada değiştiyse sunucu reddediyor. Sözleşme
 * gövdesi çevrilmiyor (kendi dilinde, soldan sağa); arayüz yedi dilde.
 * Prerender yok, noindex, Referer yok. Metinler `sozlesme` ek paketinde.
 */
export default function SozlesmeSayfasi() {
  const { jeton } = useParams<{ jeton: string }>();
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [s, setS] = useState<Sozlesme | null>(null);
  const [hata, setHata] = useState<BelgeHatasi | null>(null);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [onay, setOnay] = useState(false);
  const [ad, setAd] = useState('');
  const [png, setPng] = useState<string | null>(null);
  const [gonderiyor, setGonderiyor] = useState(false);
  const [imzaHatasi, setImzaHatasi] = useState<string | null>(null);
  const [yeniImza, setYeniImza] = useState(false);

  useEffect(() => {
    const robots = document.createElement('meta');
    robots.name = 'robots';
    robots.content = 'noindex, nofollow';
    const referans = document.createElement('meta');
    referans.name = 'referrer';
    referans.content = 'no-referrer';
    document.head.append(robots, referans);
    return () => {
      robots.remove();
      referans.remove();
    };
  }, []);

  const yukle = useCallback(async () => {
    if (!jeton) return;
    setYukleniyor(true);
    try {
      setS(await acikSozlesme(jeton));
      setHata(null);
    } catch (h) {
      setHata(h instanceof BelgeHatasi ? h : new BelgeHatasi(0, 'genel'));
    } finally {
      setYukleniyor(false);
    }
  }, [jeton]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const imzala = async () => {
    if (!jeton || !s) return;
    setGonderiyor(true);
    setImzaHatasi(null);
    try {
      setS(await acikSozlesmeImza(jeton, { ad_soyad: ad, onay, metin_ozeti: s.metin_ozeti, imza_png: png }));
      setYeniImza(true);
    } catch (h) {
      const kod = h instanceof BelgeHatasi ? h.kod : 'genel';
      setImzaHatasi(t(`sozlesme.hata.${kod}`, { defaultValue: t('sozlesme.hata.genel') }));
      if (h instanceof BelgeHatasi && (h.durum === 409 || h.durum === 410)) void yukle();
    } finally {
      setGonderiyor(false);
    }
  };

  let icerik: ReactElement;
  if (yukleniyor) {
    icerik = (
      <div className="flex min-h-[40vh] items-center justify-center text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" aria-hidden="true" />
      </div>
    );
  } else if (hata || !s) {
    icerik = (
      <div className="cam-kart mx-auto max-w-xl rounded-3xl border border-white/10 bg-white/[0.03] p-6 text-center sm:p-8" data-testid="sozlesme-hata">
        <AlertCircle className="mx-auto mb-3 h-10 w-10 text-red-300" aria-hidden="true" />
        <h1 className="text-xl font-semibold">{hata?.durum === 404 ? t('sozlesme.sayfa.bulunamadiBaslik') : t('sozlesme.hata.genel')}</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {hata?.durum === 404 ? t('sozlesme.sayfa.bulunamadiMetin') : t(`sozlesme.hata.${hata?.kod || 'genel'}`, { defaultValue: t('sozlesme.hata.genel') })}
        </p>
        <Button asChild variant="outline" className="mt-6 !bg-transparent">
          <Link to="/"><Home className="me-2 h-4 w-4" aria-hidden="true" />{t('sozlesme.anaSayfa')}</Link>
        </Button>
      </div>
    );
  } else {
    const pdfAdresi = `${getAPIBaseURL()}${acikSozlesmePdf(jeton!)}`;
    icerik = (
      <article className="mx-auto max-w-3xl space-y-6" data-testid="sozlesme-karti">
        <header className="cam-kart rounded-3xl border border-white/10 bg-white/[0.03] p-6 sm:p-8">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-sm text-muted-foreground">{s.no} · v{s.surum}</span>
            <span className={`rounded-full border px-2 py-0.5 text-xs ${sozlesmeDurumRengi(s.durum)}`} data-testid="sozlesme-durum">
              {t(`sozlesme.durum.${s.durum}`, { defaultValue: s.durum })}
            </span>
          </div>
          <p className="mt-3 text-xs uppercase tracking-widest text-purple-300">{t('sozlesme.sayfa.ust')}</p>
          <h1 className="mt-1 break-words text-2xl font-bold sm:text-3xl" dir="ltr" lang={s.dil}>{s.baslik}</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {s.taraf_ad ? `${s.taraf_ad} · ` : ''}{s.alici}
            {s.baslangic ? ` · ${t('sozlesme.sayfa.baslangic', { tarih: tarihBicimle(s.baslangic, dil) })}` : ''}
            {s.bitis ? ` · ${t('sozlesme.sayfa.bitis', { tarih: tarihBicimle(s.bitis, dil) })}` : ''}
          </p>
        </header>

        <section className="cam-kart rounded-3xl border border-white/10 bg-white/[0.03] p-5 sm:p-8" dir="ltr" lang={s.dil} data-testid="sozlesme-metni">
          <GuvenliMarkdown metin={s.govde} />
        </section>

        <section className="cam-kart space-y-4 rounded-3xl border border-white/10 bg-white/[0.03] p-5 sm:p-8">
          {s.durum === 'imzalandi' ? (
            <div className="space-y-2" data-testid="sozlesme-imzalandi">
              <p className="flex items-center gap-2 font-semibold text-emerald-300">
                <CheckCircle2 className="h-5 w-5" aria-hidden="true" />
                {yeniImza ? t('sozlesme.imza.basarili') : t('sozlesme.sayfa.zatenImzali')}
              </p>
              <p className="text-sm">{t('sozlesme.imzalayanBilgi', { ad: s.imza_ad, tarih: tarihBicimle(s.imza_at, dil, true) })}</p>
              <p className="break-all text-xs text-muted-foreground">
                {t('sozlesme.sayfa.dogrulama')}: <span className="font-mono">{s.imza_metin_ozeti}</span>
              </p>
            </div>
          ) : s.imzalanabilir ? (
            <div className="grid gap-4" data-testid="sozlesme-imza-formu">
              <h2 className="flex items-center gap-2 text-lg font-semibold">
                <FileSignature className="h-5 w-5 text-purple-300" aria-hidden="true" />{t('sozlesme.imza.baslik')}
              </h2>
              <label className="flex items-start gap-2 text-sm">
                <input type="checkbox" name="onay" checked={onay} onChange={(e) => setOnay(e.target.checked)} className="mt-0.5 h-4 w-4 accent-purple-500"
                  data-testid="sozlesme-onay" />
                {t('sozlesme.imza.onayKutusu')}
              </label>
              <div className="grid gap-1">
                <label htmlFor="sozlesme-ad" className="text-sm font-medium">{t('sozlesme.imza.adSoyad')}</label>
                <Input id="sozlesme-ad" name="ad_soyad" value={ad} maxLength={120} autoComplete="name" onChange={(e) => setAd(e.target.value)} />
              </div>
              <div className="grid gap-1">
                <span className="text-sm font-medium">{t('sozlesme.imza.cizim')}</span>
                <span className="text-xs text-muted-foreground">{t('sozlesme.imza.cizimIstegeBagli')}</span>
                <ImzaTuvali onChange={setPng} />
              </div>
              {imzaHatasi && <p className="text-sm text-red-300" role="alert">{imzaHatasi}</p>}
              <Button disabled={gonderiyor || !onay || ad.trim().length < 2} onClick={() => void imzala()} className="gap-2"
                data-testid="sozlesme-imzala">
                {gonderiyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <FileSignature className="h-4 w-4" aria-hidden="true" />}
                {t('sozlesme.imza.imzala')}
              </Button>
              <p className="text-xs text-muted-foreground">{t('sozlesme.imza.kayitBilgisi')}</p>
            </div>
          ) : s.durum === 'iptal' || s.baglanti_durumu === 'iptal' ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground" data-testid="sozlesme-iptal">
              <Ban className="h-5 w-5" aria-hidden="true" />{t('sozlesme.sayfa.iptal')}
            </p>
          ) : (
            <p className="flex items-center gap-2 text-sm text-amber-300" data-testid="sozlesme-suresi-doldu">
              <Clock className="h-5 w-5" aria-hidden="true" />{t('sozlesme.sayfa.suresiDoldu')}
            </p>
          )}
          <Button asChild variant="outline" className="gap-2 !bg-transparent">
            <a href={pdfAdresi} rel="noreferrer noopener" data-testid="sozlesme-pdf">
              <FileDown className="h-4 w-4" aria-hidden="true" />{t('sozlesme.pdfIndir')}
            </a>
          </Button>
          <p className="flex items-start gap-2 rounded-xl border border-amber-500/20 bg-amber-500/10 p-3 text-xs text-amber-100" data-testid="sozlesme-hukuki-not">
            <Scale className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />{t('sozlesme.hukukiNot')}
          </p>
        </section>
      </article>
    );
  }

  return (
    <div className="pb-20 pt-28 sm:pt-32" data-testid="sozlesme-sayfasi">
      <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">{icerik}</div>
    </div>
  );
}
