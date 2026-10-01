import { useCallback, useEffect, useRef, useState, type ReactElement } from 'react';
import { Link, useParams } from 'react-router-dom';
import { AlertCircle, Ban, CheckCircle2, Clock, FileDown, Home, Loader2, ShieldCheck, XCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import KalemTablosu from '@/components/belge/KalemTablosu';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { BelgeHatasi, paraBicimle, pdfDili, tarihBicimle } from '@/lib/belge';
import { getAPIBaseURL } from '@/lib/config';
import { acikTeklif, acikTeklifKarar, acikTeklifPdf, teklifDurumRengi, type Teklif } from '@/lib/teklifler';

/**
 * Girişsiz teklif sayfası: `/teklif/<jeton>` (Faz 3T).
 *
 * Oturum istemiyor — jetonun kendisi yetki; prerender edilmiyor, noindex,
 * Referer gönderilmiyor (jeton dışarı sızmasın). Her açılış görüntülenme
 * sayacını bir artırıyor (sayfa veriyi yalnız bir kez çeker; karardan sonra
 * yanıtı kullanır). Kabul: ad soyad yazılarak; ret: gerekçeyle. Karar tek;
 * görüntüleme ve PDF her zaman. Metinler `teklif` ek paketinde.
 */
export default function TeklifSayfasi() {
  const { jeton } = useParams<{ jeton: string }>();
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [teklif, setTeklif] = useState<Teklif | null>(null);
  const [hata, setHata] = useState<BelgeHatasi | null>(null);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [karar, setKarar] = useState<'kabul' | 'red' | null>(null);
  const [ad, setAd] = useState('');
  const [neden, setNeden] = useState('');
  const [gonderiyor, setGonderiyor] = useState(false);
  const [kararHatasi, setKararHatasi] = useState<string | null>(null);
  const [yeniKarar, setYeniKarar] = useState<'kabul' | 'red' | null>(null);
  const cekildi = useRef(false);

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
      setTeklif(await acikTeklif(jeton));
      setHata(null);
    } catch (h) {
      setHata(h instanceof BelgeHatasi ? h : new BelgeHatasi(0, 'genel'));
    } finally {
      setYukleniyor(false);
    }
  }, [jeton]);

  useEffect(() => {
    // StrictMode'da iki kez çalışmasın: her çağrı sayacı artırıyor.
    if (cekildi.current) return;
    cekildi.current = true;
    void yukle();
  }, [yukle]);

  const gonder = async () => {
    if (!jeton || !karar) return;
    setGonderiyor(true);
    setKararHatasi(null);
    try {
      const sonuc = await acikTeklifKarar(jeton, karar === 'kabul' ? { sonuc: 'kabul', ad_soyad: ad } : { sonuc: 'red', not: neden });
      setTeklif(sonuc);
      setYeniKarar(karar);
      setKarar(null);
    } catch (h) {
      const kod = h instanceof BelgeHatasi ? h.kod : 'genel';
      setKararHatasi(t(`teklif.hata.${kod}`, { defaultValue: t('teklif.hata.genel') }));
    } finally {
      setGonderiyor(false);
    }
  };

  const ekran = (ikon: ReactElement, baslik: string, metin: string, testId: string) => (
    <div className="cam-kart mx-auto max-w-xl rounded-3xl border border-white/10 bg-white/[0.03] p-6 text-center sm:p-8" data-testid={testId}>
      <div className="mx-auto mb-3 flex justify-center">{ikon}</div>
      <h1 className="text-xl font-semibold">{baslik}</h1>
      <p className="mt-2 text-sm text-muted-foreground">{metin}</p>
      <Button asChild variant="outline" className="mt-6 !bg-transparent">
        <Link to="/"><Home className="me-2 h-4 w-4" aria-hidden="true" />{t('teklif.anaSayfa')}</Link>
      </Button>
    </div>
  );

  let icerik: ReactElement;
  if (yukleniyor) {
    icerik = (
      <div className="flex min-h-[40vh] items-center justify-center text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" aria-hidden="true" />
      </div>
    );
  } else if (hata || !teklif) {
    icerik = ekran(
      <AlertCircle className="h-10 w-10 text-red-300" aria-hidden="true" />,
      hata?.durum === 404 ? t('teklif.sayfa.bulunamadiBaslik') : t('teklif.hata.genel'),
      hata?.durum === 404 ? t('teklif.sayfa.bulunamadiMetin') : t(`teklif.hata.${hata?.kod || 'genel'}`, { defaultValue: t('teklif.hata.genel') }),
      'teklif-hata',
    );
  } else {
    const durumMesaji =
      teklif.durum === 'kabul' ? (
        <p className="flex items-center gap-2 text-sm text-emerald-300" data-testid="teklif-sonuc">
          <CheckCircle2 className="h-5 w-5 shrink-0" aria-hidden="true" />
          {yeniKarar === 'kabul' ? t('teklif.sayfa.kabulTesekkur') : ''}{' '}
          {t('teklif.kabulBilgisi', { ad: teklif.karar_ad || '—', tarih: tarihBicimle(teklif.karar_at, dil, true) })}
        </p>
      ) : teklif.durum === 'ret' ? (
        <p className="flex items-center gap-2 text-sm text-amber-300" data-testid="teklif-sonuc">
          <XCircle className="h-5 w-5 shrink-0" aria-hidden="true" />
          {yeniKarar === 'red' ? t('teklif.sayfa.retTesekkur') : t('teklif.sayfa.reddedildi')}
        </p>
      ) : teklif.durum === 'suresi_doldu' ? (
        <p className="flex items-center gap-2 text-sm text-amber-300" data-testid="teklif-sonuc">
          <Clock className="h-5 w-5 shrink-0" aria-hidden="true" />{t('teklif.sayfa.suresiDoldu')}
        </p>
      ) : teklif.durum === 'revize' || teklif.baglanti_durumu === 'iptal' ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground" data-testid="teklif-sonuc">
          <Ban className="h-5 w-5 shrink-0" aria-hidden="true" />{t('teklif.sayfa.revize')}
        </p>
      ) : null;

    icerik = (
      <article className="mx-auto max-w-3xl space-y-6" data-testid="teklif-karti">
        <header className="cam-kart rounded-3xl border border-white/10 bg-white/[0.03] p-6 sm:p-8">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-sm text-muted-foreground">{teklif.no}</span>
            <span className={`rounded-full border px-2 py-0.5 text-xs ${teklifDurumRengi(teklif.durum)}`} data-testid="teklif-durum">
              {t(`teklif.durum.${teklif.durum}`, { defaultValue: teklif.durum })}
            </span>
          </div>
          <p className="mt-3 text-xs uppercase tracking-widest text-purple-300">{t('teklif.sayfa.ust')}</p>
          <h1 className="mt-1 break-words text-2xl font-bold sm:text-3xl">{teklif.baslik}</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {teklif.musteri_ad ? `${teklif.musteri_ad} · ` : ''}{teklif.alici}
            {teklif.gecerlilik ? ` · ${t('teklif.gecerlilik', { tarih: tarihBicimle(teklif.gecerlilik, dil) })}` : ''}
          </p>
          <p className="mt-4 text-3xl font-bold tabular-nums" data-testid="teklif-toplam">
            {paraBicimle(teklif.ozet.genel_toplam, teklif.para_birimi, dil)}
          </p>
        </header>

        <section className="cam-kart rounded-3xl border border-white/10 bg-white/[0.03] p-5 sm:p-8">
          <KalemTablosu kalemler={teklif.kalemler} ozet={teklif.ozet} paraBirimi={teklif.para_birimi} />
          {teklif.notlar && <p className="mt-6 whitespace-pre-line text-sm text-muted-foreground">{teklif.notlar}</p>}
        </section>

        {teklif.sartlar && (
          <section className="cam-kart rounded-3xl border border-white/10 bg-white/[0.03] p-5 sm:p-8">
            <h2 className="mb-2 font-semibold">{t('teklif.sartlar')}</h2>
            <p className="whitespace-pre-line text-sm text-muted-foreground">{teklif.sartlar}</p>
          </section>
        )}

        <section className="cam-kart space-y-4 rounded-3xl border border-white/10 bg-white/[0.03] p-5 sm:p-8">
          {durumMesaji}
          <div className="flex flex-col flex-wrap gap-3 sm:flex-row">
            <Button asChild variant="outline" className="gap-2 !bg-transparent">
              <a href={`${getAPIBaseURL()}${acikTeklifPdf(jeton!, pdfDili(dil))}`} rel="noreferrer noopener" data-testid="teklif-pdf">
                <FileDown className="h-4 w-4" aria-hidden="true" />{t('teklif.pdfIndir')}
              </a>
            </Button>
            {teklif.karar_verilebilir && !karar && (
              <>
                <Button className="gap-2" onClick={() => setKarar('kabul')} data-testid="teklif-kabul">
                  <CheckCircle2 className="h-4 w-4" aria-hidden="true" />{t('teklif.kabulEt')}
                </Button>
                <Button variant="ghost" className="gap-2" onClick={() => setKarar('red')} data-testid="teklif-red">
                  <XCircle className="h-4 w-4" aria-hidden="true" />{t('teklif.reddet')}
                </Button>
              </>
            )}
          </div>
          {karar && (
            <div className="grid gap-3 rounded-2xl border border-white/10 p-4" data-testid="teklif-karar-formu">
              {karar === 'kabul' ? (
                <>
                  <label htmlFor="teklif-ad" className="text-sm font-medium">{t('teklif.adSoyadEtiket')}</label>
                  <Input id="teklif-ad" name="ad_soyad" value={ad} maxLength={120} autoComplete="name" onChange={(e) => setAd(e.target.value)} />
                  <p className="text-xs text-muted-foreground">{t('teklif.kabulAciklama')}</p>
                </>
              ) : (
                <>
                  <label htmlFor="teklif-neden" className="text-sm font-medium">{t('teklif.retNedeni')}</label>
                  <Textarea id="teklif-neden" name="neden" rows={3} maxLength={2000} value={neden} onChange={(e) => setNeden(e.target.value)} />
                </>
              )}
              {kararHatasi && <p className="text-sm text-red-300" role="alert">{kararHatasi}</p>}
              <div className="flex flex-col gap-2 sm:flex-row">
                <Button disabled={gonderiyor || (karar === 'kabul' ? ad.trim().length < 2 : !neden.trim())} onClick={() => void gonder()}
                  className="gap-2" data-testid="teklif-onayla">
                  {gonderiyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
                  {karar === 'kabul' ? t('teklif.kabulOnayla') : t('teklif.retOnayla')}
                </Button>
                <Button variant="ghost" onClick={() => setKarar(null)}>{t('teklif.vazgec')}</Button>
              </div>
            </div>
          )}
          <p className="flex items-start gap-2 text-xs text-muted-foreground">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />{t('teklif.sayfa.guvenlik')}
          </p>
        </section>
      </article>
    );
  }

  return (
    <div className="pb-20 pt-28 sm:pt-32" data-testid="teklif-sayfasi">
      <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">{icerik}</div>
    </div>
  );
}
