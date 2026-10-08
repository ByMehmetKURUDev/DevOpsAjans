import { useState, type CSSProperties, type FormEvent, type ReactNode } from 'react';
import {
  BookOpen,
  Briefcase,
  CalendarDays,
  Camera,
  Clock,
  Download,
  Dribbble,
  Facebook,
  FileText,
  Gift,
  Github,
  Globe,
  Heart,
  Instagram,
  Link as LinkIcon,
  Linkedin,
  Loader2,
  Mail,
  MapPin,
  Megaphone,
  MessageCircle,
  Music,
  Palette,
  Phone,
  Pin,
  QrCode,
  Send,
  Share2,
  ShoppingBag,
  Star,
  Ticket,
  Twitch,
  Twitter,
  UserPlus,
  Video,
  Youtube,
  AtSign,
  type LucideIcon,
} from 'lucide-react';

import { BAL_KUPU, apiAdresi, temaStili, type AcikKart, type Cevirmen } from '@/lib/kartvizitAcik';

import './kartvizit.css';

/**
 * Faz 4K — dijital kartvizitin kendisi. Herkese açık `/kart/<slug>` sayfası ve
 * paneldeki canlı telefon önizlemesi AYNI bileşeni çiziyor (önizlemede
 * etkileşim kapalı).
 *
 * Mobil öncelikli tek sütun (en çok 28rem). Tema `--kv-*` değişkenleriyle
 * (`temaStili`); yüzeyler her şablonda okunur kontrastta. Görseller boyutlu
 * (width/height → yerleşim kaymaz), galeri tembel yükleniyor. Marka ikonu
 * lucide'da olan platformlar kendi ikonuyla, olmayanlar sade genel ikonla
 * (marka logosu çizilmiyor).
 */

const SOSYAL_IKON: Record<string, LucideIcon> = {
  linkedin: Linkedin,
  instagram: Instagram,
  x: Twitter,
  facebook: Facebook,
  youtube: Youtube,
  github: Github,
  dribbble: Dribbble,
  twitch: Twitch,
  // lucide'da marka ikonu olmayanlar: sade genel ikon.
  tiktok: Music,
  spotify: Music,
  behance: Palette,
  pinterest: Pin,
  telegram: Send,
  threads: AtSign,
  medium: BookOpen,
  snapchat: Camera,
  discord: MessageCircle,
  web: Globe,
};
/** Platformun görünen adı (özel ad; çevrilmiyor). */
export const PLATFORM_ADI: Record<string, string> = {
  linkedin: 'LinkedIn',
  instagram: 'Instagram',
  x: 'X',
  facebook: 'Facebook',
  youtube: 'YouTube',
  tiktok: 'TikTok',
  github: 'GitHub',
  behance: 'Behance',
  dribbble: 'Dribbble',
  pinterest: 'Pinterest',
  telegram: 'Telegram',
  threads: 'Threads',
  medium: 'Medium',
  twitch: 'Twitch',
  snapchat: 'Snapchat',
  spotify: 'Spotify',
  discord: 'Discord',
  web: 'Web',
};
export const BAGLANTI_IKON: Record<string, LucideIcon> = {
  link: LinkIcon,
  globe: Globe,
  shop: ShoppingBag,
  calendar: CalendarDays,
  video: Video,
  music: Music,
  file: FileText,
  mail: Mail,
  phone: Phone,
  map: MapPin,
  star: Star,
  gift: Gift,
  book: BookOpen,
  briefcase: Briefcase,
  heart: Heart,
  camera: Camera,
  message: MessageCircle,
  download: Download,
  ticket: Ticket,
  megaphone: Megaphone,
};

export interface FormVerisi {
  ad: string;
  eposta: string;
  telefon: string;
  mesaj: string;
  web_sitesi: string;
}

export type FormSonucu = 'tamam' | 'hata' | 'cok_hizli' | 'iletisim';

const YUZEY = 'kv-yuzey';
const YUZEY_STILI = { borderRadius: 'var(--kv-yaricap)' } as const;

function harici(url: string) {
  return /^https?:/i.test(url) ? { target: '_blank', rel: 'noopener noreferrer' } : {};
}

export default function KartGorunumu({
  kart,
  m,
  onizleme = false,
  jeton,
  onTik,
  onPaylas,
  onQr,
  onGonder,
  ust,
  stil,
  rozet = true,
}: {
  kart: AcikKart;
  m: Cevirmen;
  onizleme?: boolean;
  jeton?: string | null;
  onTik?: (hedef: string) => void;
  onPaylas?: () => void;
  onQr?: () => void;
  onGonder?: (veri: FormVerisi) => Promise<FormSonucu>;
  ust?: ReactNode;
  /** Faz 4L: tema stilinin üstüne eklenen stil (marka zemini, yazı tipi, `--marka-*`). */
  stil?: CSSProperties;
  /** Faz 4L: "mehmetkuru.dev ile hazırlandı" (yönetici marka modülünde gizleyebilir). */
  rozet?: boolean;
}) {
  const bio = kart.duzen === 'bio_link';
  const yon = kart.dil === 'ar' ? 'rtl' : 'ltr';
  const tik = (hedef: string) => () => {
    if (!onizleme) onTik?.(hedef);
  };
  const vcard = apiAdresi(kart.vcard_adresi) + (jeton ? `?j=${encodeURIComponent(jeton)}` : '');
  const altBaslik = [kart.unvan, kart.sirket].filter(Boolean).join(' · ');
  const ilkTel = kart.telefonlar[0];

  const hizli: { anahtar: string; href: string; ikon: LucideIcon; etiket: string }[] = [];
  if (ilkTel) hizli.push({ anahtar: 'tel:0', href: ilkTel.tel, ikon: Phone, etiket: m('ara') });
  if (kart.whatsapp_url) hizli.push({ anahtar: 'wa', href: kart.whatsapp_url, ikon: MessageCircle, etiket: m('whatsapp') });
  if (kart.eposta) hizli.push({ anahtar: 'eposta', href: `mailto:${kart.eposta}`, ikon: Mail, etiket: m('eposta') });
  if (kart.webler[0]) hizli.push({ anahtar: 'web:0', href: kart.webler[0].url, ikon: Globe, etiket: m('web') });
  if (kart.harita_url) hizli.push({ anahtar: 'harita', href: kart.harita_url, ikon: MapPin, etiket: m('harita') });

  const profil = (
    <div className={`kv-yuzey relative overflow-hidden px-5 pb-5 text-center`} style={YUZEY_STILI}>
      {kart.kapak ? (
        <img
          src={apiAdresi(kart.kapak.url)}
          alt={m('kapak')}
          width={kart.kapak.genislik}
          height={kart.kapak.yukseklik}
          className="kv-kapak"
          decoding="async"
          fetchPriority="high"
        />
      ) : (
        <div className="kv-kapak-zemin" aria-hidden="true" />
      )}
      <div className="kv-avatar-kap">
        {kart.foto ? (
          <img
            src={apiAdresi(kart.foto.url)}
            alt={m('profilFotografi', { ad: kart.ad_soyad })}
            width={96}
            height={96}
            className="kv-avatar"
            decoding="async"
            fetchPriority="high"
          />
        ) : (
          <div
            className="kv-avatar flex items-center justify-center text-3xl font-bold"
            style={{ background: 'var(--kv-vurgu)', color: 'var(--kv-vurgu-metin)' }}
            aria-hidden="true"
          >
            {(kart.ad_soyad || '?').trim().charAt(0).toUpperCase()}
          </div>
        )}
        {kart.logo && (
          <img
            src={apiAdresi(kart.logo.url)}
            alt={m('logo', { ad: kart.sirket || kart.ad_soyad })}
            width={40}
            height={40}
            className="kv-rozet"
            decoding="async"
          />
        )}
      </div>
      <h1 className="mt-3 break-words text-2xl font-bold leading-tight kv-baslik" data-testid="kart-ad">
        {kart.ad_soyad}
      </h1>
      {altBaslik && <p className="mt-1 text-sm kv-soluk">{altBaslik}</p>}
      {kart.tanitim && <p className="mt-3 whitespace-pre-line text-sm leading-relaxed">{kart.tanitim}</p>}
      {bio && kart.sosyal.length > 0 && <SosyalSatiri kart={kart} tik={tik} />}
    </div>
  );

  const eylemler = (
    <div className="kv-eylemler">
      <a
        href={onizleme ? undefined : vcard}
        onClick={onizleme ? (e) => e.preventDefault() : undefined}
        className="kv-dugme-ana shadow-sm"
        data-testid="kart-rehber"
        download={onizleme ? undefined : `${kart.slug}.vcf`}
      >
        <UserPlus className="h-4 w-4" aria-hidden="true" />
        {m('rehbereKaydet')}
      </a>
      <button
        type="button"
        onClick={() => !onizleme && onPaylas?.()}
        className="kv-yuzey kv-kare-dugme"
        aria-label={m('paylas')}
        title={m('paylas')}
        data-testid="kart-paylas"
      >
        <Share2 className="h-5 w-5" aria-hidden="true" />
      </button>
      <button
        type="button"
        onClick={() => !onizleme && onQr?.()}
        className="kv-yuzey kv-kare-dugme"
        aria-label={m('qr')}
        title={m('qr')}
        data-testid="kart-qr"
      >
        <QrCode className="h-5 w-5" aria-hidden="true" />
      </button>
    </div>
  );

  const baglantilar = kart.baglantilar.length > 0 && (
    <nav aria-label={m('baglantilar')} className="space-y-2.5" data-testid="kart-baglantilar">
      {kart.baglantilar.map((b, i) => {
        const Ikon = BAGLANTI_IKON[b.simge] || LinkIcon;
        return (
          <a
            key={b.id || i}
            href={onizleme ? undefined : b.url}
            onClick={tik(`l:${b.id}`)}
            {...harici(b.url)}
            className="kv-yuzey kv-baglanti"
          >
            <span className="kv-ikon-zemin flex h-8 w-8 shrink-0 items-center justify-center rounded-full">
              <Ikon className="h-4 w-4" aria-hidden="true" />
            </span>
            <span className="min-w-0 flex-1 break-words text-start">{b.baslik}</span>
          </a>
        );
      })}
    </nav>
  );

  const iletisim = (kart.telefonlar.length > 0 || kart.eposta || kart.webler.length > 0 || kart.adres) && (
    <section className={`kv-yuzey p-4`} style={YUZEY_STILI} aria-labelledby="kv-iletisim">
      <h2 id="kv-iletisim" className="mb-2 text-xs font-semibold uppercase tracking-wide kv-soluk kv-baslik">
        {m('iletisim')}
      </h2>
      <ul className="kv-bolucu text-sm">
        {kart.telefonlar.map((t, i) => (
          <SatirBag key={`t${i}`} href={t.tel} ikon={Phone} ust={t.etiket || m('telefon')} metin={t.numara} onClick={tik(`tel:${i}`)} onizleme={onizleme} ltr />
        ))}
        {kart.eposta && <SatirBag href={`mailto:${kart.eposta}`} ikon={Mail} ust={m('eposta')} metin={kart.eposta} onClick={tik('eposta')} onizleme={onizleme} ltr />}
        {kart.webler.map((w, i) => (
          <SatirBag key={`w${i}`} href={w.url} ikon={Globe} ust={w.etiket || m('web')} metin={w.url.replace(/^https?:\/\/(www\.)?/, '')} onClick={tik(`web:${i}`)} onizleme={onizleme} ltr />
        ))}
        {kart.adres && (
          <SatirBag href={kart.harita_url} ikon={MapPin} ust={m('adres')} metin={kart.adres} onClick={tik('harita')} onizleme={onizleme} />
        )}
      </ul>
    </section>
  );

  const sosyal = !bio && kart.sosyal.length > 0 && (
    <section className={`kv-yuzey p-4`} style={YUZEY_STILI} aria-labelledby="kv-sosyal">
      <h2 id="kv-sosyal" className="mb-3 text-xs font-semibold uppercase tracking-wide kv-soluk kv-baslik">
        {m('sosyal')}
      </h2>
      <SosyalSatiri kart={kart} tik={tik} />
    </section>
  );

  const hizmetler = kart.hizmetler.length > 0 && (
    <section className={`kv-yuzey p-4`} style={YUZEY_STILI} aria-labelledby="kv-hizmet">
      <h2 id="kv-hizmet" className="mb-2 text-xs font-semibold uppercase tracking-wide kv-soluk kv-baslik">
        {m('hizmetler')}
      </h2>
      <ul className="space-y-3">
        {kart.hizmetler.map((h, i) => (
          <li key={i} className="flex gap-3">
            <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full" style={{ background: 'var(--kv-vurgu)' }} aria-hidden="true" />
            <div className="min-w-0">
              <p className="text-sm font-semibold">{h.baslik}</p>
              {h.aciklama && <p className="whitespace-pre-line text-sm kv-soluk">{h.aciklama}</p>}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );

  const saatler = kart.calisma_saatleri?.goster && (
    <section className={`kv-yuzey p-4`} style={YUZEY_STILI} aria-labelledby="kv-saat">
      <h2 id="kv-saat" className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide kv-soluk kv-baslik">
        <Clock className="h-3.5 w-3.5" aria-hidden="true" />
        {m('calismaSaatleri')}
      </h2>
      <dl className="kv-saatler">
        {kart.calisma_saatleri.gunler.map((g) => (
          <div key={g.gun} className="contents">
            <dt>{m(`gun.${g.gun}`)}</dt>
            <dd className="text-end tabular-nums kv-soluk" dir="ltr">
              {g.acik ? `${g.acilis} – ${g.kapanis}` : m('kapali')}
            </dd>
          </div>
        ))}
      </dl>
      {kart.calisma_saatleri.not && <p className="mt-2 text-xs kv-soluk">{kart.calisma_saatleri.not}</p>}
    </section>
  );

  const galeri = kart.galeri.length > 0 && (
    <section aria-labelledby="kv-galeri">
      <h2 id="kv-galeri" className="mb-2 px-1 text-xs font-semibold uppercase tracking-wide kv-soluk kv-baslik">
        {m('galeri')}
      </h2>
      <div className="grid grid-cols-2 gap-2">
        {kart.galeri.map((g, i) => (
          <a key={g.id} href={onizleme ? undefined : apiAdresi(g.url)} {...harici('https:')} onClick={tik('galeri')}>
            <img
              src={apiAdresi(g.url)}
              alt={m('galeriGorseli', { sira: i + 1 })}
              width={g.genislik}
              height={g.yukseklik}
              loading="lazy"
              decoding="async"
              className="aspect-square w-full object-cover"
              style={{ borderRadius: 'calc(var(--kv-yaricap) * 0.6)' }}
            />
          </a>
        ))}
      </div>
    </section>
  );

  const form = kart.form.acik && <IletisimFormu kart={kart} m={m} onizleme={onizleme} onGonder={onGonder} />;

  return (
    <div lang={kart.dil} dir={yon} className="w-full" style={{ ...temaStili(kart.tema, kart.dil), ...stil }} data-testid="kart-gorunumu" data-duzen={kart.duzen}>
      <div className="mx-auto w-full max-w-md space-y-3 px-4 pb-10 pt-6">
        {ust}
        {profil}
        {bio ? (
          <>
            {baglantilar}
            {eylemler}
            {iletisim}
          </>
        ) : (
          <>
            {eylemler}
            {hizli.length > 0 && (
              <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${Math.min(hizli.length, 5)}, minmax(0, 1fr))` }}>
                {hizli.map((h) => (
                  <a
                    key={h.anahtar}
                    href={onizleme ? undefined : h.href}
                    onClick={tik(h.anahtar)}
                    {...harici(h.href)}
                    className="kv-yuzey kv-hizli"
                  >
                    <h.ikon className="kv-vurgu-metin h-5 w-5" aria-hidden="true" />
                    <span className="max-w-full truncate">{h.etiket}</span>
                  </a>
                ))}
              </div>
            )}
            {iletisim}
            {baglantilar}
          </>
        )}
        {sosyal}
        {hizmetler}
        {saatler}
        {galeri}
        {form}
        {rozet && (
          <p className="pt-2 text-center text-[11px] kv-soluk" data-testid="marka-rozet">
            <a href="https://mehmetkuru.dev/" className="hover:underline" target="_blank" rel="noopener">
              {m('altBilgi')}
            </a>
          </p>
        )}
      </div>
    </div>
  );
}

function SosyalSatiri({ kart, tik }: { kart: AcikKart; tik: (h: string) => () => void }) {
  return (
    <ul className="mt-4 flex flex-wrap justify-center gap-2" data-testid="kart-sosyal">
      {kart.sosyal.map((s) => {
        const Ikon = SOSYAL_IKON[s.platform] || Globe;
        return (
          <li key={s.platform + s.url}>
            <a
              href={s.url}
              onClick={tik(`s:${s.platform}`)}
              target="_blank"
              rel="noopener noreferrer me"
              aria-label={PLATFORM_ADI[s.platform] || s.platform}
              title={PLATFORM_ADI[s.platform] || s.platform}
              className="kv-ikon-zemin flex h-11 w-11 items-center justify-center rounded-full"
            >
              <Ikon className="h-5 w-5" aria-hidden="true" />
            </a>
          </li>
        );
      })}
    </ul>
  );
}

function SatirBag({
  href,
  ikon: Ikon,
  ust,
  metin,
  onClick,
  onizleme,
  ltr,
}: {
  href: string;
  ikon: LucideIcon;
  ust: string;
  metin: string;
  onClick: () => void;
  onizleme: boolean;
  ltr?: boolean;
}) {
  return (
    <li>
      <a href={onizleme ? undefined : href} onClick={onClick} {...harici(href)} className="flex items-center gap-3 py-2.5">
        <Ikon className="kv-vurgu-metin h-4 w-4 shrink-0" aria-hidden="true" />
        <span className="min-w-0 flex-1 text-start">
          <span className="block text-[11px] kv-soluk">{ust}</span>
          {/* Telefon / e-posta / adres soldan sağa okunur ama sağdan sola kartta satır başına (sağa) hizalanır. */}
          <span className="block whitespace-pre-line break-words">{ltr ? <bdi dir="ltr">{metin}</bdi> : metin}</span>
        </span>
      </a>
    </li>
  );
}

function IletisimFormu({
  kart,
  m,
  onizleme,
  onGonder,
}: {
  kart: AcikKart;
  m: Cevirmen;
  onizleme: boolean;
  onGonder?: (veri: FormVerisi) => Promise<FormSonucu>;
}) {
  const [v, setV] = useState<FormVerisi>({ ad: '', eposta: '', telefon: '', mesaj: '', web_sitesi: '' });
  const [durum, setDurum] = useState<'bos' | 'gonderiliyor' | FormSonucu>('bos');
  const alan = 'kv-girdi';

  const gonder = async (e: FormEvent) => {
    e.preventDefault();
    if (onizleme || !onGonder) return;
    if (!v.eposta.trim() && !v.telefon.trim()) {
      setDurum('iletisim');
      return;
    }
    setDurum('gonderiliyor');
    setDurum(await onGonder(v));
  };

  if (durum === 'tamam') {
    return (
      <div className={`kv-yuzey p-5 text-center text-sm font-medium`} style={YUZEY_STILI} role="status" data-testid="kart-form-tamam">
        {m('form.tesekkur')}
      </div>
    );
  }
  return (
    <form onSubmit={gonder} className={`kv-yuzey space-y-2.5 p-4`} style={YUZEY_STILI} aria-labelledby="kv-form" data-testid="kart-form" noValidate>
      <h2 id="kv-form" className="text-base font-semibold kv-baslik">
        {m('form.baslik')}
      </h2>
      <p className="text-xs kv-soluk">{m('form.aciklama')}</p>
      <label className="block">
        <span className="sr-only">{m('form.ad')}</span>
        <input className={alan} required maxLength={120} autoComplete="name" placeholder={m('form.ad')} value={v.ad}
          onChange={(e) => setV({ ...v, ad: e.target.value })} name="ad" />
      </label>
      <div className="grid gap-2.5 sm:grid-cols-2">
        <label className="block">
          <span className="sr-only">{m('form.eposta')}</span>
          <input className={alan} type="email" maxLength={254} autoComplete="email" placeholder={m('form.eposta')} value={v.eposta}
            onChange={(e) => setV({ ...v, eposta: e.target.value })} name="eposta" dir="ltr" />
        </label>
        <label className="block">
          <span className="sr-only">{m('form.telefon')}</span>
          <input className={alan} type="tel" maxLength={40} autoComplete="tel" placeholder={m('form.telefon')} value={v.telefon}
            onChange={(e) => setV({ ...v, telefon: e.target.value })} name="telefon" dir="ltr" />
        </label>
      </div>
      <label className="block">
        <span className="sr-only">{m('form.mesaj')}</span>
        <textarea className={alan} maxLength={2000} placeholder={m('form.mesaj')} value={v.mesaj}
          onChange={(e) => setV({ ...v, mesaj: e.target.value })} name="mesaj" />
      </label>
      {/* Bal küpü: insan görmez, bot doldurur (sunucu sessizce yok sayar). Sayfanın dışına itilmiyor:
          sağdan sola (ar) düzende negatif konum yatay kaydırma açıyordu. */}
      <div aria-hidden="true" style={BAL_KUPU}>
        <label>
          {m('form.tuzak')}
          <input tabIndex={-1} autoComplete="off" name="web_sitesi" value={v.web_sitesi} onChange={(e) => setV({ ...v, web_sitesi: e.target.value })} />
        </label>
      </div>
      {(durum === 'hata' || durum === 'cok_hizli' || durum === 'iletisim') && (
        <p className="text-xs font-medium text-red-500" role="alert">
          {m(durum === 'iletisim' ? 'form.iletisimGerekli' : durum === 'cok_hizli' ? 'form.cokHizli' : 'form.hata')}
        </p>
      )}
      <button
        type="submit"
        disabled={durum === 'gonderiliyor' || onizleme}
        className="kv-dugme-ana w-full"
        data-testid="kart-form-gonder"
      >
        {durum === 'gonderiliyor' ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Send className="rtl-flip h-4 w-4" aria-hidden="true" />}
        {durum === 'gonderiliyor' ? m('form.gonderiliyor') : m('form.gonder')}
      </button>
      <p className="text-center text-[11px] leading-relaxed kv-soluk" data-aydinlatma>
        {m('form.aydinlatma')}{' '}
        <a href={kart.form.aydinlatma_adresi} target="_blank" rel="noopener" className="underline underline-offset-2">
          {m('form.gizlilik')}
        </a>
      </p>
    </form>
  );
}
