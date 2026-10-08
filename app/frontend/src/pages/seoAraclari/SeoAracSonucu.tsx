import { useMemo, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowRight, CheckCircle2, CircleAlert, Gauge, Info, Loader2, Mail, TriangleAlert } from 'lucide-react';

import AydinlatmaSatiri from '@/components/AydinlatmaSatiri';
import { Button } from '@/components/ui/button';
import { AracHatasi, SEVIYE_SIRASI, sonucuEpostala, type AracSonucu, type Bulgu, type Seviye } from '@/lib/seoAraclari';
import { localizedPath } from '../../../prerender/site.js';
import type { AracTanimi } from './ortak';
import { AracAyrintisi, PuanHalkasi } from './SonucGorunumleri';

/**
 * Bir aracın sonucu (Faz 4S): kontrol kartları ("Neden önemli? / Nasıl düzeltilir?"),
 * araca özel ayrıntı, "Sitenin tam analizini al" (Site Analizi, adres dolu) ve isteğe bağlı
 * "Sonucu e-postayla gönder".
 *
 * Bu bileşen ve metinleri (`seoAracSonuc`, `aydinlatma`) yalnız ilk sonuçta iniyor.
 * Hedef sitenin metinleri yalnız düz metin olarak basılıyor (React kaçışlıyor).
 */

const GIRDI =
  'w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2.5 text-sm text-white placeholder:text-muted-foreground focus:border-primary focus:outline-none';

const RENK: Record<Seviye, string> = {
  hata: 'text-red-300',
  uyari: 'text-amber-300',
  bilgi: 'text-sky-300',
  iyi: 'text-emerald-300',
};
const KENAR: Record<Seviye, string> = {
  hata: 'border-red-500/30',
  uyari: 'border-amber-400/30',
  bilgi: 'border-white/10',
  iyi: 'border-white/10',
};

export function SeviyeIkonu({ seviye, className = 'h-4 w-4' }: { seviye: Seviye; className?: string }) {
  const Ikon = seviye === 'hata' ? CircleAlert : seviye === 'uyari' ? TriangleAlert : seviye === 'bilgi' ? Info : CheckCircle2;
  return <Ikon className={`${className} shrink-0 ${RENK[seviye]}`} aria-hidden="true" />;
}

/** Bulgu cümlesi: `deger` sözlükse alanları da yerleşiyor ({{yol}}, {{ajan}}…). */
export function bulguMetni(t: (k: string, o?: Record<string, unknown>) => string, b: Bulgu): string {
  const ek = b.deger && typeof b.deger === 'object' ? (b.deger as Record<string, unknown>) : {};
  const deger = b.deger !== null && b.deger !== undefined && typeof b.deger !== 'object' ? b.deger : '';
  return t(`seoAracSonuc.bulgu.${b.kod}`, { ...ek, deger, defaultValue: b.kod });
}

function enKotu(bulgular: Bulgu[]): Seviye {
  for (const s of SEVIYE_SIRASI) if (bulgular.some((b) => b.seviye === s)) return s;
  return 'iyi';
}

function KontrolKarti({ kontrol, bulgular }: { kontrol: string; bulgular: Bulgu[] }) {
  const { t } = useTranslation();
  const seviye = enKotu(bulgular);
  const sorunlu = seviye === 'hata' || seviye === 'uyari';
  const k = `seoAracSonuc.kontrol.${kontrol}`;
  const aciklama = (
    <div className="mt-4 grid gap-4 text-sm leading-relaxed sm:grid-cols-2">
      <div>
        <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t('seoAracSonuc.nedenOnemli')}</p>
        <p className="text-muted-foreground">{t(`${k}.neden`)}</p>
      </div>
      <div>
        <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t('seoAracSonuc.nasilDuzeltilir')}</p>
        <p className="text-muted-foreground">{t(`${k}.duzelt`)}</p>
      </div>
    </div>
  );
  return (
    <section className={`cam-kart rounded-2xl border ${KENAR[seviye]} bg-white/[0.03] p-5`} data-kontrol={kontrol} data-seviye={seviye}>
      <h3 className="flex items-center gap-2 text-base font-semibold">
        <SeviyeIkonu seviye={seviye} className="h-5 w-5" />
        <span className="min-w-0">{t(`${k}.ad`)}</span>
        <span className={`ms-auto rounded-full border border-white/10 px-2 py-0.5 text-[11px] font-semibold ${RENK[seviye]}`}>
          {t(`seoAracSonuc.seviye.${seviye}`)}
        </span>
      </h3>
      <ul className="mt-3 space-y-2">
        {bulgular.map((b, i) => (
          <li key={`${b.kod}-${i}`} className="flex gap-2 text-sm" data-bulgu={b.kod}>
            <SeviyeIkonu seviye={b.seviye} className="mt-0.5 h-4 w-4" />
            <span className="min-w-0 break-words">{bulguMetni(t, b)}</span>
          </li>
        ))}
      </ul>
      {sorunlu ? (
        aciklama
      ) : (
        <details className="mt-3">
          <summary className="cursor-pointer text-xs font-semibold text-purple-300">{t('seoAracSonuc.nedenOnemli')}</summary>
          {aciklama}
        </details>
      )}
    </section>
  );
}

function siteKoku(adres: string): string {
  try {
    const u = new URL(adres);
    return `${u.protocol}//${u.host}/`;
  } catch {
    return adres;
  }
}

function alanAdi(adres: string): string {
  try {
    return new URL(adres).hostname;
  } catch {
    return adres;
  }
}

/**
 * "Sitenin tam analizini al" → mevcut Site Analiz Raporu sayfası, adres dolu.
 * Uygulama içi geçişte analiz kendiliğinden başlar (router state); aracın adı analize
 * yazılır (yönetici özeti). Yeni sekmede açılırsa `?url=` yalnız alanı doldurur.
 */
function TamAnalizCagrisi({ sonuc, arac, dil }: { sonuc: AracSonucu; arac: AracTanimi; dil: string }) {
  const { t } = useTranslation();
  const kok = siteKoku(sonuc.son_url || sonuc.url);
  const hedef = `${localizedPath(dil, 'siteAnalysis')}?${new URLSearchParams({ url: kok, arac: arac.slug }).toString()}`;
  return (
    <section
      className="cam-kart cam-mor flex flex-col gap-5 rounded-3xl border border-purple-500/30 bg-purple-500/10 p-6 sm:flex-row sm:items-center md:p-8"
      data-tam-analiz
    >
      <Gauge className="h-10 w-10 shrink-0 text-purple-300" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <h2 className="text-xl font-bold md:text-2xl">{t('seoAraclari.tamAnaliz.baslik')}</h2>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          {t('seoAraclari.tamAnaliz.metin', { alan: alanAdi(kok) })}
        </p>
      </div>
      <Button asChild className="h-11 shrink-0 border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white">
        <Link to={hedef} state={{ url: kok, arac: arac.slug, otomatik: true }} data-tam-analiz-dugmesi>
          {t('seoAraclari.tamAnaliz.dugme')}
          <ArrowRight className="ms-1 h-4 w-4 rtl:rotate-180" aria-hidden="true" />
        </Link>
      </Button>
    </section>
  );
}

/**
 * "Sonucu e-postayla gönder" (isteğe bağlı). Yalnız sunucuda e-posta kanalı varsa görünür
 * (`sonuc.eposta.acik`). Pazarlama izni AYRI, isteğe bağlı, varsayılan işaretsiz kutu (yalnız
 * site ayarı açıkken); gönder düğmesinin altında aydınlatma satırı. Ziyaretçi CRM'e aday olarak
 * yazılır (Gelen kutusuna düşmez). `web_sitesi` bal küpü: ekranda yok, botlar doldurur.
 */
function EpostaFormu({ sonuc, arac, dil }: { sonuc: AracSonucu; arac: AracTanimi; dil: string }) {
  const { t } = useTranslation();
  const [eposta, setEposta] = useState('');
  const [ad, setAd] = useState('');
  const [izin, setIzin] = useState(false);
  const [balKupu, setBalKupu] = useState('');
  const [durum, setDurum] = useState<'bos' | 'gonderiliyor' | 'tamam'>('bos');
  const [hata, setHata] = useState<string | null>(null);
  const secenek = sonuc.eposta;
  if (!secenek?.acik || !secenek.jeton) return null;
  const jeton = secenek.jeton;

  const gonder = async (olay: FormEvent) => {
    olay.preventDefault();
    if (durum !== 'bos') return;
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(eposta.trim())) {
      setHata('eposta_gecersiz');
      return;
    }
    setHata(null);
    setDurum('gonderiliyor');
    try {
      await sonucuEpostala(arac.slug, {
        jeton,
        eposta: eposta.trim(),
        ad: ad.trim() || undefined,
        pazarlama_izni: Boolean(secenek.pazarlama_izni_sor && izin),
        dil,
        ...(balKupu ? { web_sitesi: balKupu } : {}),
      });
      setDurum('tamam');
    } catch (h) {
      setHata(h instanceof AracHatasi ? h.kod : 'genel');
      setDurum('bos');
    }
  };

  return (
    <section className="cam-kart rounded-3xl border border-white/10 bg-white/[0.03] p-6 md:p-8" aria-labelledby="sonuc-eposta-baslik" data-sonuc-eposta>
      {durum === 'tamam' ? (
        <div className="py-2 text-center" role="status" data-sonuc-eposta-tamam>
          <CheckCircle2 className="mx-auto mb-3 h-10 w-10 text-emerald-400" aria-hidden="true" />
          <p id="sonuc-eposta-baslik" className="text-lg font-semibold">
            {t('seoAraclari.eposta.basarili')}
          </p>
          <p className="mx-auto mt-2 max-w-lg text-sm text-muted-foreground">{t('seoAraclari.eposta.basariliMetin')}</p>
        </div>
      ) : (
        <form onSubmit={gonder} className="grid gap-6 lg:grid-cols-2" noValidate>
          <div className="min-w-0">
            <h2 id="sonuc-eposta-baslik" className="flex items-center gap-2 text-xl font-bold">
              <Mail className="h-5 w-5 shrink-0 text-purple-300" aria-hidden="true" />
              {t('seoAraclari.eposta.baslik')}
            </h2>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{t('seoAraclari.eposta.aciklama')}</p>
          </div>
          <div className="min-w-0 space-y-3">
            <input
              value={ad}
              onChange={(o) => setAd(o.target.value)}
              placeholder={t('seoAraclari.eposta.ad')}
              aria-label={t('seoAraclari.eposta.ad')}
              autoComplete="name"
              maxLength={120}
              disabled={durum === 'gonderiliyor'}
              className={GIRDI}
            />
            <input
              type="email"
              value={eposta}
              onChange={(o) => setEposta(o.target.value)}
              placeholder={t('seoAraclari.eposta.eposta')}
              aria-label={t('seoAraclari.eposta.eposta')}
              autoComplete="email"
              maxLength={254}
              dir="ltr"
              required
              disabled={durum === 'gonderiliyor'}
              className={GIRDI}
              data-sonuc-eposta-adres
            />
            {/* Bal küpü: ekran okuyucudan ve klavyeden de gizli. */}
            <input
              type="text"
              name="web_sitesi"
              value={balKupu}
              onChange={(o) => setBalKupu(o.target.value)}
              tabIndex={-1}
              autoComplete="off"
              aria-hidden="true"
              className="absolute -start-[10000px] h-px w-px overflow-hidden opacity-0"
            />
            {secenek.pazarlama_izni_sor && (
              <label className="flex cursor-pointer items-start gap-2 text-xs leading-relaxed text-muted-foreground">
                <input
                  type="checkbox"
                  checked={izin}
                  onChange={(o) => setIzin(o.target.checked)}
                  className="mt-0.5 h-4 w-4 flex-none accent-emerald-500"
                  data-pazarlama-izni
                />
                <span>
                  {t('seoAraclari.eposta.pazarlama')} <span className="opacity-70">({t('seoAraclari.eposta.istegeBagli')})</span>
                </span>
              </label>
            )}
            {hata && (
              <p role="alert" className="text-sm text-red-300" data-sonuc-eposta-hata={hata}>
                {t(`seoAraclari.hata.${hata}`, { defaultValue: t('seoAraclari.hata.genel') })}
              </p>
            )}
            <Button type="submit" disabled={durum === 'gonderiliyor'} className="h-11 w-full gap-2" data-sonuc-eposta-gonder>
              {durum === 'gonderiliyor' ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Mail className="h-4 w-4" aria-hidden="true" />}
              {t(durum === 'gonderiliyor' ? 'seoAraclari.eposta.gonderiliyor' : 'seoAraclari.eposta.gonder')}
            </Button>
            <AydinlatmaSatiri />
          </div>
        </form>
      )}
    </section>
  );
}

export default function SeoAracSonucu({
  sonuc,
  arac,
  dil,
}: {
  sonuc: AracSonucu;
  arac: AracTanimi;
  dil: string;
  girilen?: string;
}) {
  const { t } = useTranslation();
  const gruplar = useMemo(() => {
    const sira: string[] = [];
    const harita: Record<string, Bulgu[]> = {};
    for (const b of sonuc.bulgular) {
      if (!harita[b.kontrol]) {
        harita[b.kontrol] = [];
        sira.push(b.kontrol);
      }
      harita[b.kontrol].push(b);
    }
    // Sorunlu kontroller önce: aynı seviyede motorun sırası korunur.
    return sira
      .map((k) => ({ kontrol: k, bulgular: harita[k], seviye: enKotu(harita[k]) }))
      .sort((a, b) => SEVIYE_SIRASI.indexOf(a.seviye) - SEVIYE_SIRASI.indexOf(b.seviye));
  }, [sonuc]);

  return (
    <div className="space-y-8" data-arac-sonuc={sonuc.arac}>
      <div className="cam-kart cam-gok flex flex-col gap-6 rounded-3xl border border-white/10 bg-white/[0.03] p-6 sm:flex-row sm:items-center md:p-8">
        {sonuc.puan !== null && sonuc.puan !== undefined && (
          <PuanHalkasi puan={sonuc.puan} etiket={sonuc.veri?.harf ? String(sonuc.veri.harf) : undefined} />
        )}
        <div className="min-w-0 flex-1">
          <h2 className="text-2xl font-bold">{t('seoAracSonuc.baslik')}</h2>
          <dl className="mt-3 grid gap-1 text-sm">
            <div className="flex flex-wrap gap-x-2">
              <dt className="text-muted-foreground">{t('seoAracSonuc.kontrolEdilen')}:</dt>
              <dd className="min-w-0 break-all" dir="ltr" data-sonuc-url>
                {sonuc.url}
              </dd>
            </div>
            {sonuc.son_url && sonuc.son_url !== sonuc.url && (
              <div className="flex flex-wrap gap-x-2">
                <dt className="text-muted-foreground">{t('seoAracSonuc.sonAdres')}:</dt>
                <dd className="min-w-0 break-all" dir="ltr">
                  {sonuc.son_url}
                </dd>
              </div>
            )}
            {sonuc.durum !== null && sonuc.durum !== undefined && (
              <div className="flex flex-wrap gap-x-2">
                <dt className="text-muted-foreground">{t('seoAracSonuc.durum')}:</dt>
                <dd>{sonuc.durum}</dd>
              </div>
            )}
          </dl>
          <p className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-sm" data-sonuc-ozet>
            {SEVIYE_SIRASI.map((s) => (
              <span key={s} className={`inline-flex items-center gap-1 ${RENK[s]}`}>
                <SeviyeIkonu seviye={s} />
                {sonuc.ozet?.[s] ?? 0} {t(`seoAracSonuc.seviye.${s}`)}
              </span>
            ))}
          </p>
        </div>
      </div>

      <section>
        <h2 className="mb-4 text-xl font-bold">{t('seoAracSonuc.kontroller')}</h2>
        <div className="grid gap-4 lg:grid-cols-2">
          {gruplar.map((g) => (
            <KontrolKarti key={g.kontrol} kontrol={g.kontrol} bulgular={g.bulgular} />
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-4 text-xl font-bold">{t('seoAracSonuc.ayrintilar')}</h2>
        <AracAyrintisi sonuc={sonuc} anahtar={arac.anahtar} />
      </section>

      <TamAnalizCagrisi sonuc={sonuc} arac={arac} dil={dil} />
      <EpostaFormu sonuc={sonuc} arac={arac} dil={dil} />
    </div>
  );
}
