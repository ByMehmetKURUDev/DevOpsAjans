import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, ArrowLeft, Check, ExternalLink, ImagePlus, Loader2, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  STATIK_TURLER,
  TURLER,
  dosyaOku,
  hataMetni,
  svgAdresi,
  utmOnizleme,
  QrUcHatasi,
  type Alanlar,
  type Onizleme,
  type QrApi,
  type QrGirdisi,
  type QrKaydi,
  type QrMeta,
  type QrMod,
  type QrTuru,
  type Tasarim,
} from '@/lib/dinamikQr';

import { KART, SECIM, TUR_IKONLARI } from './ortak';

/**
 * Faz 4Q — oluştur / düzenle sihirbazı: 1) tür → 2) içerik → 3) tasarım ve ayarlar.
 *
 * Önizleme sunucudan SVG olarak geliyor (350 ms gecikmeli, son istek kazanır)
 * ve `<img>` ile çiziliyor. Dinamik türlerde QR içeriği alanlara bağlı değil
 * (`/q/<kod>`): hedef sonradan değişse de basılı QR aynı kalır. Kısa link
 * (yalnız URL) tasarım adımını atlar.
 */

type AlanTipi = 'text' | 'url' | 'tel' | 'email' | 'textarea' | 'datetime' | 'checkbox' | 'password' | 'select';
interface AlanTanimi {
  ad: string;
  tip?: AlanTipi;
  zorunlu?: boolean;
  genis?: boolean;
  yer?: string;
  secenekler?: string[];
}

const SAAT_DILIMLERI = [
  'Europe/Istanbul',
  'UTC',
  'Europe/London',
  'Europe/Berlin',
  'Europe/Moscow',
  'Asia/Dubai',
  'Asia/Kolkata',
  'Asia/Shanghai',
  'America/New_York',
];

const ALAN_TANIMLARI: Record<QrTuru, AlanTanimi[]> = {
  url: [{ ad: 'url', tip: 'url', zorunlu: true, genis: true, yer: 'https://ornek.com/kampanya' }],
  google_yorum: [{ ad: 'place_id', zorunlu: true, genis: true, yer: 'ChIJN1t_tDeuEmsRUsoyG83frY4' }],
  whatsapp: [
    { ad: 'numara', tip: 'tel', zorunlu: true, yer: '+905551112233' },
    { ad: 'mesaj', tip: 'textarea', genis: true },
  ],
  telefon: [{ ad: 'numara', tip: 'tel', zorunlu: true, yer: '+905551112233' }],
  eposta: [
    { ad: 'eposta', tip: 'email', zorunlu: true, yer: 'bilgi@ornek.com' },
    { ad: 'konu' },
    { ad: 'govde', tip: 'textarea', genis: true },
  ],
  sms: [
    { ad: 'numara', tip: 'tel', zorunlu: true, yer: '+905551112233' },
    { ad: 'mesaj', tip: 'textarea', genis: true },
  ],
  konum: [],
  vcard: [
    { ad: 'ad' },
    { ad: 'soyad' },
    { ad: 'kurum' },
    { ad: 'unvan' },
    { ad: 'telefon_cep', tip: 'tel', yer: '+905551112233' },
    { ad: 'telefon_is', tip: 'tel' },
    { ad: 'eposta', tip: 'email' },
    { ad: 'web', tip: 'url', yer: 'https://ornek.com' },
    { ad: 'adres_sokak', genis: true },
    { ad: 'adres_sehir' },
    { ad: 'adres_posta_kodu' },
    { ad: 'adres_ulke' },
    { ad: 'not', tip: 'textarea', genis: true },
  ],
  etkinlik: [
    { ad: 'baslik', zorunlu: true, genis: true },
    { ad: 'tum_gun', tip: 'checkbox', genis: true },
    { ad: 'baslangic', tip: 'datetime', zorunlu: true },
    { ad: 'bitis', tip: 'datetime' },
    { ad: 'saat_dilimi', tip: 'select', secenekler: SAAT_DILIMLERI },
    { ad: 'konum' },
    { ad: 'aciklama', tip: 'textarea', genis: true },
  ],
  uygulama: [
    { ad: 'ios', tip: 'url', genis: true, yer: 'https://apps.apple.com/…' },
    { ad: 'android', tip: 'url', genis: true, yer: 'https://play.google.com/store/apps/details?id=…' },
    { ad: 'diger', tip: 'url', genis: true, yer: 'https://ornek.com' },
  ],
  wifi: [
    { ad: 'ssid', zorunlu: true },
    { ad: 'sifre', tip: 'password' },
    { ad: 'guvenlik', tip: 'select', secenekler: ['WPA', 'WEP', 'nopass'] },
    { ad: 'gizli', tip: 'checkbox' },
  ],
  metin: [{ ad: 'metin', tip: 'textarea', zorunlu: true, genis: true }],
};

const UTM_ALANLARI = ['utm_source', 'utm_medium', 'utm_campaign'];
const ADIM3_ALANLARI = new Set(['tasarim', 'on_renk', 'arka_renk', 'kenar', 'boyut', 'hata_duzeltme', 'logo', 'takma_ad', 'bitis', 'tarama_limiti', 'hesap_email', 'kisa_link']);
const PLACE_ID_BULUCU = 'https://developers.google.com/maps/documentation/javascript/examples/places-placeid-finder';

/** Onaltılık renk kutusu: yazarken yerel metin, geçerli (#RRGGBB) olunca tasarıma yazılır. */
function RenkGirdisi({ id, deger, onDegis }: { id: string; deger: string; onDegis: (v: string) => void }) {
  const [metin, setMetin] = useState(deger);
  useEffect(() => setMetin(deger), [deger]);
  return (
    <Input
      id={id}
      data-testid={id}
      dir="ltr"
      value={metin}
      maxLength={7}
      onChange={(e) => {
        const v = e.target.value.trim();
        if (!/^#?[0-9a-fA-F]{0,6}$/.test(v)) return;
        const duz = v.startsWith('#') ? v : `#${v}`;
        setMetin(duz);
        if (duz.length === 7) onDegis(duz.toLowerCase());
      }}
      onBlur={() => setMetin(deger)}
    />
  );
}

/** ISO (UTC) → `datetime-local` değeri (yerel saat). */
function yerelDeger(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

export default function Sihirbaz({
  api,
  mod,
  meta,
  kayit,
  kisaBaslangic,
  onKapat,
  onKaydedildi,
}: {
  api: QrApi;
  mod: QrMod;
  meta: QrMeta | null;
  kayit: QrKaydi | null;
  kisaBaslangic?: boolean;
  onKapat: () => void;
  onKaydedildi: (k: QrKaydi) => void;
}) {
  const { t } = useTranslation();
  const varsayilanTasarim: Tasarim = meta?.tasarim ?? {
    on_renk: '#000000',
    arka_renk: '#ffffff',
    kenar: 4,
    boyut: 512,
    hata_duzeltme: 'M',
  };
  const [adim, setAdim] = useState<1 | 2 | 3>(kayit || kisaBaslangic ? 2 : 1);
  const [tur, setTur] = useState<QrTuru | null>(kayit?.tur ?? (kisaBaslangic ? 'url' : null));
  const [kisa, setKisa] = useState<boolean>(kayit?.kisa_link ?? !!kisaBaslangic);
  const [ad, setAd] = useState(kayit?.ad ?? '');
  const [alanlar, setAlanlar] = useState<Alanlar>(() => ({ ...(kayit?.alanlar ?? {}) }));
  const [konumModu, setKonumModu] = useState<'koordinat' | 'adres'>(
    kayit?.tur === 'konum' && !kayit.alanlar.enlem ? 'adres' : 'koordinat'
  );
  const [tasarim, setTasarim] = useState<Tasarim>({ ...varsayilanTasarim, ...(kayit?.tasarim ?? {}) });
  const [logo, setLogo] = useState<string | null>(null);
  const [logoKaldir, setLogoKaldir] = useState(false);
  const [takmaAd, setTakmaAd] = useState(kayit?.takma_ad ?? '');
  const [aktif, setAktif] = useState(kayit?.aktif ?? true);
  const [bitis, setBitis] = useState(yerelDeger(kayit?.bitis ?? null));
  const [limit, setLimit] = useState(kayit?.tarama_limiti ? String(kayit.tarama_limiti) : '');
  const [hesapEmail, setHesapEmail] = useState('');
  const [onizleme, setOnizleme] = useState<Onizleme | null>(null);
  const [onizlemeHatasi, setOnizlemeHatasi] = useState<string | null>(null);
  const [onizlemeYukleniyor, setOnizlemeYukleniyor] = useState(false);
  const [kaydediliyor, setKaydediliyor] = useState(false);
  const [alanHatasi, setAlanHatasi] = useState<{ alan: string; metin: string } | null>(null);
  const istekSirasi = useRef(0);
  const logoGirdisi = useRef<HTMLInputElement | null>(null);

  const statik = !!tur && STATIK_TURLER.includes(tur);
  const mevcutLogo = !!kayit?.logo_var && !logoKaldir && !logo;
  const logoVar = !!logo || mevcutLogo;

  const alan = (adi: string) => alanlar[adi] ?? '';
  const alanYaz = (adi: string, deger: string | boolean) => {
    setAlanlar((a) => ({ ...a, [adi]: deger }));
    if (alanHatasi?.alan === adi) setAlanHatasi(null);
  };

  /** Yalnız bu türün alanları (konumda seçili mod). */
  const temizAlanlar = (): Alanlar => {
    if (!tur) return {};
    if (tur === 'konum') {
      return konumModu === 'koordinat'
        ? { enlem: String(alan('enlem')), boylam: String(alan('boylam')) }
        : { adres: String(alan('adres')) };
    }
    const adlar = ALAN_TANIMLARI[tur].map((x) => x.ad).concat(tur === 'url' ? UTM_ALANLARI : []);
    const sonuc: Alanlar = {};
    for (const a of adlar) if (alanlar[a] !== undefined) sonuc[a] = alanlar[a];
    if (tur === 'etkinlik' && !sonuc.saat_dilimi) sonuc.saat_dilimi = 'Europe/Istanbul';
    return sonuc;
  };

  // Canlı önizleme: tür, tasarım, logo (statik türde alanlar da) değişince.
  const onizlemeAnahtari = JSON.stringify({
    tur,
    tasarim,
    logo: logo ? logo.length : 0,
    logoKaldir,
    alanlar: statik ? temizAlanlar() : null,
  });
  useEffect(() => {
    if (!tur || kisa || adim < 2) return;
    const sira = ++istekSirasi.current;
    setOnizlemeYukleniyor(true);
    const zaman = window.setTimeout(async () => {
      const govde: QrGirdisi = { tur, tasarim };
      if (kayit) govde.qr_id = kayit.id;
      if (logo) govde.logo = logo;
      if (logoKaldir) govde.logo_kaldir = true;
      if (statik) govde.alanlar = temizAlanlar();
      try {
        const o = await api.onizleme(govde);
        if (sira !== istekSirasi.current) return;
        setOnizleme(o);
        setOnizlemeHatasi(null);
      } catch (e) {
        if (sira !== istekSirasi.current) return;
        setOnizlemeHatasi(hataMetni(t, e));
      } finally {
        if (sira === istekSirasi.current) setOnizlemeYukleniyor(false);
      }
    }, 350);
    return () => window.clearTimeout(zaman);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onizlemeAnahtari, adim, kisa, api]);

  const turSec = (yeni: QrTuru, kisaLink = false) => {
    setTur(yeni);
    setKisa(kisaLink);
    setAlanHatasi(null);
    if (yeni === 'wifi' && !alanlar.guvenlik) setAlanlar((a) => ({ ...a, guvenlik: 'WPA' }));
    if (yeni === 'etkinlik' && !alanlar.saat_dilimi) setAlanlar((a) => ({ ...a, saat_dilimi: 'Europe/Istanbul' }));
    setAdim(2);
  };

  const logoSec = async (dosya: File | undefined) => {
    if (!dosya) return;
    const sinir = (meta?.logo_en_cok_kb ?? 512) * 1024;
    if (!/^image\/(png|jpeg)$/.test(dosya.type)) {
      toast.error(t('dinamikQr.hata.logo_turu'));
      return;
    }
    if (dosya.size > sinir) {
      toast.error(t('dinamikQr.hata.logo_buyuk', { en_cok_kb: meta?.logo_en_cok_kb ?? 512 }));
      return;
    }
    try {
      setLogo(await dosyaOku(dosya));
      setLogoKaldir(false);
    } catch {
      toast.error(t('dinamikQr.hata.logo_gecersiz'));
    }
  };

  const ileri = () => {
    if (adim === 2) {
      if (!ad.trim()) {
        setAlanHatasi({ alan: 'ad', metin: t('dinamikQr.hata.zorunlu') });
        return;
      }
      setAdim(3);
    }
  };

  const kaydet = async () => {
    if (!tur) return;
    if (!ad.trim()) {
      setAdim(2);
      setAlanHatasi({ alan: 'ad', metin: t('dinamikQr.hata.zorunlu') });
      return;
    }
    const govde: QrGirdisi = {
      ad: ad.trim(),
      tur,
      alanlar: temizAlanlar(),
      kisa_link: kisa,
      takma_ad: statik ? null : takmaAd.trim() || null,
      aktif,
      bitis: bitis ? new Date(bitis).toISOString() : null,
      tarama_limiti: limit.trim() ? Number(limit) : null,
    };
    if (!kisa) govde.tasarim = tasarim;
    if (logo && !kisa) govde.logo = logo;
    if (logoKaldir) govde.logo_kaldir = true;
    if (mod === 'yonetici' && !kayit && hesapEmail.trim()) govde.hesap_email = hesapEmail.trim();
    setKaydediliyor(true);
    setAlanHatasi(null);
    try {
      const k = kayit ? await api.guncelle(kayit.id, govde) : await api.olustur(govde);
      toast.success(t(kayit ? 'dinamikQr.sihirbaz.guncellendi' : 'dinamikQr.sihirbaz.olusturuldu'));
      onKaydedildi(k);
    } catch (e) {
      const metin = hataMetni(t, e);
      if (e instanceof QrUcHatasi && e.alan) {
        setAlanHatasi({ alan: e.alan, metin });
        setAdim(ADIM3_ALANLARI.has(e.alan) ? 3 : 2);
      }
      toast.error(metin);
    } finally {
      setKaydediliyor(false);
    }
  };

  const hataNotu = (adi: string) =>
    alanHatasi?.alan === adi ? (
      <span className="mt-1 block text-xs text-red-300" role="alert" data-qr-alan-hatasi={adi}>
        {alanHatasi.metin}
      </span>
    ) : null;

  const alanCiz = (d: AlanTanimi) => {
    const id = `qr-alan-${d.ad}`;
    const etiket = (
      <span className="mb-1 block text-xs text-muted-foreground">
        {t(`dinamikQr.alan.${d.ad}`)}
        {d.zorunlu && <span className="text-purple-300"> *</span>}
      </span>
    );
    const hatali = alanHatasi?.alan === d.ad;
    const ortak = {
      id,
      'data-testid': id,
      'aria-invalid': hatali || undefined,
      className: hatali ? 'border-red-400/60' : undefined,
    };
    if (d.tip === 'checkbox') {
      return (
        <label key={d.ad} className={`flex items-center gap-2 text-sm ${d.genis ? 'sm:col-span-2' : ''}`}>
          <input
            type="checkbox"
            {...ortak}
            className="h-4 w-4 accent-purple-500"
            checked={!!alanlar[d.ad]}
            onChange={(e) => alanYaz(d.ad, e.target.checked)}
          />
          {t(`dinamikQr.alan.${d.ad}`)}
        </label>
      );
    }
    let girdi;
    if (d.tip === 'textarea') {
      girdi = (
        <Textarea {...ortak} rows={3} value={String(alan(d.ad))} onChange={(e) => alanYaz(d.ad, e.target.value)} />
      );
    } else if (d.tip === 'select') {
      girdi = (
        <select {...ortak} className={SECIM} value={String(alan(d.ad))} onChange={(e) => alanYaz(d.ad, e.target.value)}>
          {(d.secenekler ?? []).map((s) => (
            <option key={s} value={s}>
              {d.ad === 'guvenlik' ? t(`dinamikQr.guvenlik.${s}`) : s}
            </option>
          ))}
        </select>
      );
    } else {
      const tumGun = tur === 'etkinlik' && !!alanlar.tum_gun;
      const tip = d.tip === 'datetime' ? (tumGun ? 'date' : 'datetime-local') : d.tip ?? 'text';
      let deger = String(alan(d.ad));
      if (d.tip === 'datetime') deger = tumGun ? deger.slice(0, 10) : deger.length === 10 ? `${deger}T09:00` : deger;
      girdi = (
        <Input
          {...ortak}
          type={tip}
          dir={['url', 'tel', 'email', 'password'].includes(tip) ? 'ltr' : undefined}
          placeholder={d.yer}
          autoComplete={d.tip === 'password' ? 'new-password' : 'off'}
          value={deger}
          onChange={(e) => alanYaz(d.ad, e.target.value)}
        />
      );
    }
    return (
      <label key={d.ad} htmlFor={id} className={`block ${d.genis ? 'sm:col-span-2' : ''}`}>
        {etiket}
        {girdi}
        {hataNotu(d.ad)}
      </label>
    );
  };

  const turKartlari = useMemo(
    () => [...TURLER.map((x) => ({ tur: x as QrTuru, kisa: false })), { tur: 'url' as QrTuru, kisa: true }],
    []
  );

  const adimlar = [1, 2, 3];
  const baslik = kayit ? t('dinamikQr.sihirbaz.duzenleBaslik') : t('dinamikQr.sihirbaz.yeniBaslik');

  return (
    <div className={`${KART} p-4 sm:p-6`} data-testid="qr-sihirbaz">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={onKapat} className="gap-1 px-2" data-testid="qr-sihirbaz-kapat">
            <ArrowLeft className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
            {t('dinamikQr.sihirbaz.iptal')}
          </Button>
          <h3 className="text-lg font-semibold">{baslik}</h3>
        </div>
        <ol className="flex items-center gap-1 text-xs" aria-label={t('dinamikQr.sihirbaz.adimlar')}>
          {adimlar.map((n) => {
            const erisilebilir = n === 1 ? !kayit : !!tur;
            return (
              <li key={n}>
                <button
                  type="button"
                  disabled={!erisilebilir}
                  onClick={() => erisilebilir && setAdim(n as 1 | 2 | 3)}
                  aria-current={adim === n ? 'step' : undefined}
                  className={`rounded-full border px-3 py-1 transition-colors ${
                    adim === n
                      ? 'border-purple-400/60 bg-purple-500/20 text-white'
                      : 'border-white/10 text-muted-foreground hover:border-white/25 disabled:opacity-40'
                  }`}
                  data-qr-adim={n}
                >
                  {n}. {t(`dinamikQr.sihirbaz.adim${n}${n === 3 && kisa ? 'Kisa' : ''}`)}
                </button>
              </li>
            );
          })}
        </ol>
      </div>

      {adim === 1 && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4" role="list">
          {turKartlari.map(({ tur: x, kisa: k }) => {
            const anahtar = k ? 'kisa_link' : x;
            const Ikon = TUR_IKONLARI[anahtar];
            return (
              <button
                key={anahtar}
                type="button"
                role="listitem"
                onClick={() => turSec(x, k)}
                className="group flex flex-col items-start gap-1.5 rounded-xl border border-white/10 bg-white/[0.03] p-3 text-start transition-colors hover:border-purple-400/40 hover:bg-white/[0.05]"
                data-testid={`qr-tur-${anahtar}`}
              >
                <span className="flex items-center gap-2 text-sm font-semibold">
                  <span className="flex h-7 w-7 flex-none items-center justify-center rounded-lg bg-purple-500/15">
                    <Ikon className="h-4 w-4 text-purple-300" aria-hidden="true" />
                  </span>
                  {t(`dinamikQr.tur.${anahtar}`)}
                </span>
                <span className="text-xs leading-relaxed text-muted-foreground">{t(`dinamikQr.turAciklama.${anahtar}`)}</span>
              </button>
            );
          })}
        </div>
      )}

      {adim >= 2 && tur && (
        <div className={`grid gap-6 ${kisa ? '' : 'lg:grid-cols-[minmax(0,1fr)_300px]'}`}>
          <div className="min-w-0 space-y-5">
            {adim === 2 && (
              <>
                <label htmlFor="qr-ad" className="block">
                  <span className="mb-1 block text-xs text-muted-foreground">
                    {t('dinamikQr.sihirbaz.ad')} <span className="text-purple-300">*</span>
                  </span>
                  <Input
                    id="qr-ad"
                    data-testid="qr-ad"
                    value={ad}
                    maxLength={120}
                    placeholder={t('dinamikQr.sihirbaz.adYer')}
                    onChange={(e) => {
                      setAd(e.target.value);
                      if (alanHatasi?.alan === 'ad') setAlanHatasi(null);
                    }}
                  />
                  {hataNotu('ad')}
                </label>

                <div className="rounded-xl border border-white/10 bg-black/20 p-3 text-xs leading-relaxed text-muted-foreground">
                  {kisa
                    ? t('dinamikQr.sihirbaz.kisaLinkBilgi')
                    : statik
                      ? t('dinamikQr.sihirbaz.statikBilgi')
                      : t('dinamikQr.sihirbaz.dinamikBilgi')}
                </div>

                {tur === 'google_yorum' && (
                  <div className="rounded-xl border border-purple-400/20 bg-purple-500/[0.06] p-3 text-xs leading-relaxed" data-testid="qr-place-yardim">
                    <p className="mb-1 font-semibold text-white">{t('dinamikQr.ipucu.placeBaslik')}</p>
                    <p className="text-muted-foreground">{t('dinamikQr.ipucu.placeMetin')}</p>
                    <a
                      href={PLACE_ID_BULUCU}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-2 inline-flex items-center gap-1 font-medium text-purple-300 hover:underline"
                    >
                      {t('dinamikQr.ipucu.placeBulucu')}
                      <ExternalLink className="h-3 w-3" aria-hidden="true" />
                    </a>
                  </div>
                )}

                {tur === 'konum' ? (
                  <div className="space-y-3">
                    <div className="flex gap-2" role="radiogroup" aria-label={t('dinamikQr.konumModu.baslik')}>
                      {(['koordinat', 'adres'] as const).map((m) => (
                        <button
                          key={m}
                          type="button"
                          role="radio"
                          aria-checked={konumModu === m}
                          onClick={() => setKonumModu(m)}
                          className={`rounded-full border px-3 py-1 text-xs ${
                            konumModu === m ? 'border-purple-400/60 bg-purple-500/20 text-white' : 'border-white/10 text-muted-foreground'
                          }`}
                        >
                          {t(`dinamikQr.konumModu.${m}`)}
                        </button>
                      ))}
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2">
                      {konumModu === 'koordinat'
                        ? [alanCiz({ ad: 'enlem', zorunlu: true, yer: '41.0082' }), alanCiz({ ad: 'boylam', zorunlu: true, yer: '28.9784' })]
                        : alanCiz({ ad: 'adres', zorunlu: true, genis: true })}
                    </div>
                  </div>
                ) : (
                  <div className="grid gap-3 sm:grid-cols-2">{ALAN_TANIMLARI[tur].map(alanCiz)}</div>
                )}

                {['whatsapp', 'telefon', 'sms'].includes(tur) && (
                  <p className="text-xs text-muted-foreground">{t('dinamikQr.ipucu.numara')}</p>
                )}
                {tur === 'uygulama' && <p className="text-xs text-muted-foreground">{t('dinamikQr.ipucu.uygulama')}</p>}
                {tur === 'vcard' && <p className="text-xs text-muted-foreground">{t('dinamikQr.ipucu.vcard')}</p>}
                {tur === 'wifi' && <p className="text-xs text-muted-foreground">{t('dinamikQr.ipucu.wifi')}</p>}

                {tur === 'url' && (
                  <details className="rounded-xl border border-white/10 p-3" open={UTM_ALANLARI.some((u) => !!alanlar[u])}>
                    <summary className="cursor-pointer text-sm font-medium">{t('dinamikQr.utm.baslik')}</summary>
                    <p className="mt-2 text-xs text-muted-foreground">{t('dinamikQr.utm.aciklama')}</p>
                    <div className="mt-3 grid gap-3 sm:grid-cols-3">
                      {UTM_ALANLARI.map((u) => alanCiz({ ad: u, yer: u === 'utm_source' ? 'qr' : u === 'utm_medium' ? 'afis' : 'bahar-2026' }))}
                    </div>
                    {String(alan('url')).trim() && (
                      <p className="mt-3 break-all text-xs text-muted-foreground" dir="ltr" data-testid="qr-utm-sonuc">
                        <span className="text-white">{t('dinamikQr.utm.sonuc')}:</span> {utmOnizleme(String(alan('url')), alanlar)}
                      </p>
                    )}
                  </details>
                )}
              </>
            )}

            {adim === 3 && (
              <>
                {!kisa && (
                  <section className="space-y-4" aria-labelledby="qr-tasarim-baslik">
                    <h4 id="qr-tasarim-baslik" className="text-sm font-semibold">
                      {t('dinamikQr.tasarim.baslik')}
                    </h4>
                    <div className="grid gap-3 sm:grid-cols-2">
                      {(['on_renk', 'arka_renk'] as const).map((r) => (
                        <label key={r} className="block" htmlFor={`qr-${r}`}>
                          <span className="mb-1 block text-xs text-muted-foreground">{t(`dinamikQr.tasarim.${r}`)}</span>
                          <span className="flex items-center gap-2">
                            <input
                              type="color"
                              aria-label={t(`dinamikQr.tasarim.${r}`)}
                              value={tasarim[r]}
                              onChange={(e) => setTasarim((x) => ({ ...x, [r]: e.target.value }))}
                              className="h-10 w-12 flex-none cursor-pointer rounded-md border border-white/10 bg-transparent"
                            />
                            <RenkGirdisi
                              id={`qr-${r}`}
                              deger={tasarim[r]}
                              onDegis={(v) => setTasarim((x) => ({ ...x, [r]: v }))}
                            />
                          </span>
                        </label>
                      ))}
                      <label className="block" htmlFor="qr-kenar">
                        <span className="mb-1 block text-xs text-muted-foreground">
                          {t('dinamikQr.tasarim.kenar')}: {tasarim.kenar}
                        </span>
                        <input
                          id="qr-kenar"
                          type="range"
                          min={0}
                          max={10}
                          value={tasarim.kenar}
                          onChange={(e) => setTasarim((x) => ({ ...x, kenar: Number(e.target.value) }))}
                          className="w-full accent-purple-500"
                        />
                      </label>
                      <label className="block" htmlFor="qr-boyut">
                        <span className="mb-1 block text-xs text-muted-foreground">{t('dinamikQr.tasarim.boyut')}</span>
                        <select
                          id="qr-boyut"
                          className={SECIM}
                          value={tasarim.boyut}
                          onChange={(e) => setTasarim((x) => ({ ...x, boyut: Number(e.target.value) }))}
                        >
                          {[256, 512, 1024, 2048].map((b) => (
                            <option key={b} value={b}>
                              {b} × {b} px
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="block sm:col-span-2" htmlFor="qr-hata-duzeltme">
                        <span className="mb-1 block text-xs text-muted-foreground">{t('dinamikQr.tasarim.hataDuzeltme')}</span>
                        <select
                          id="qr-hata-duzeltme"
                          className={SECIM}
                          disabled={logoVar}
                          value={logoVar ? 'H' : tasarim.hata_duzeltme}
                          onChange={(e) => setTasarim((x) => ({ ...x, hata_duzeltme: e.target.value as Tasarim['hata_duzeltme'] }))}
                        >
                          {(['L', 'M', 'Q', 'H'] as const).map((h) => (
                            <option key={h} value={h}>
                              {t(`dinamikQr.tasarim.hd.${h}`)}
                            </option>
                          ))}
                        </select>
                        {logoVar && <span className="mt-1 block text-xs text-muted-foreground">{t('dinamikQr.tasarim.logoH')}</span>}
                      </label>
                    </div>

                    <div className="rounded-xl border border-white/10 p-3">
                      <p className="mb-2 text-xs text-muted-foreground">
                        {t('dinamikQr.tasarim.logoBilgi', { kb: meta?.logo_en_cok_kb ?? 512 })}
                      </p>
                      <div className="flex flex-wrap items-center gap-2">
                        <input
                          ref={logoGirdisi}
                          type="file"
                          accept="image/png,image/jpeg"
                          className="sr-only"
                          data-testid="qr-logo-dosya"
                          onChange={(e) => {
                            void logoSec(e.target.files?.[0]);
                            e.target.value = '';
                          }}
                        />
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="gap-1.5 !bg-transparent border-white/20"
                          onClick={() => logoGirdisi.current?.click()}
                        >
                          <ImagePlus className="h-4 w-4" aria-hidden="true" />
                          {logoVar ? t('dinamikQr.tasarim.logoDegistir') : t('dinamikQr.tasarim.logoSec')}
                        </Button>
                        {logoVar && (
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="gap-1.5 text-red-300"
                            onClick={() => {
                              setLogo(null);
                              if (kayit?.logo_var) setLogoKaldir(true);
                            }}
                            data-testid="qr-logo-kaldir"
                          >
                            <Trash2 className="h-4 w-4" aria-hidden="true" />
                            {t('dinamikQr.tasarim.logoKaldir')}
                          </Button>
                        )}
                        {logo && <img src={logo} alt="" className="h-9 w-9 rounded border border-white/10 object-contain" />}
                      </div>
                    </div>
                  </section>
                )}

                <section className="space-y-3" aria-labelledby="qr-ayar-baslik">
                  <h4 id="qr-ayar-baslik" className="text-sm font-semibold">
                    {t('dinamikQr.ayarlar.baslik')}
                  </h4>
                  {!statik && (
                    <label htmlFor="qr-takma-ad" className="block">
                      <span className="mb-1 block text-xs text-muted-foreground">{t('dinamikQr.ayarlar.takmaAd')}</span>
                      <span className="flex items-stretch overflow-hidden rounded-md border border-white/10" dir="ltr">
                        <span className="flex items-center bg-white/[0.04] px-2 text-xs text-muted-foreground">
                          {(meta?.kisa_adres_tabani ?? '/q/').replace(/^https?:\/\//, '')}
                        </span>
                        <input
                          id="qr-takma-ad"
                          data-testid="qr-takma-ad"
                          value={takmaAd}
                          maxLength={40}
                          placeholder={t('dinamikQr.ayarlar.takmaAdYer')}
                          onChange={(e) => {
                            setTakmaAd(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''));
                            if (alanHatasi?.alan === 'takma_ad') setAlanHatasi(null);
                          }}
                          className="h-10 min-w-0 flex-1 bg-background px-2 text-sm focus-visible:outline-none"
                        />
                      </span>
                      <span className="mt-1 block text-xs text-muted-foreground">{t('dinamikQr.ayarlar.takmaAdBilgi')}</span>
                      {hataNotu('takma_ad')}
                    </label>
                  )}
                  {!statik && (
                    <div className="grid gap-3 sm:grid-cols-2">
                      <label htmlFor="qr-bitis" className="block">
                        <span className="mb-1 block text-xs text-muted-foreground">{t('dinamikQr.ayarlar.bitis')}</span>
                        <Input id="qr-bitis" type="datetime-local" value={bitis} onChange={(e) => setBitis(e.target.value)} />
                        {hataNotu('bitis')}
                      </label>
                      <label htmlFor="qr-limit" className="block">
                        <span className="mb-1 block text-xs text-muted-foreground">{t('dinamikQr.ayarlar.taramaLimiti')}</span>
                        <Input
                          id="qr-limit"
                          type="number"
                          min={1}
                          inputMode="numeric"
                          value={limit}
                          placeholder={t('dinamikQr.ayarlar.sinirsiz')}
                          onChange={(e) => setLimit(e.target.value.replace(/[^0-9]/g, ''))}
                        />
                        {hataNotu('tarama_limiti')}
                      </label>
                    </div>
                  )}
                  {!statik && (
                    <label className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        className="h-4 w-4 accent-purple-500"
                        checked={aktif}
                        onChange={(e) => setAktif(e.target.checked)}
                        data-testid="qr-aktif"
                      />
                      {t('dinamikQr.ayarlar.aktif')}
                    </label>
                  )}
                  {mod === 'yonetici' && !kayit && (
                    <label htmlFor="qr-hesap" className="block">
                      <span className="mb-1 block text-xs text-muted-foreground">{t('dinamikQr.ayarlar.hesap')}</span>
                      <Input
                        id="qr-hesap"
                        type="email"
                        dir="ltr"
                        value={hesapEmail}
                        placeholder="musteri@ornek.com"
                        onChange={(e) => setHesapEmail(e.target.value)}
                      />
                      <span className="mt-1 block text-xs text-muted-foreground">{t('dinamikQr.ayarlar.hesapBilgi')}</span>
                      {hataNotu('hesap_email')}
                    </label>
                  )}
                  {statik && <p className="text-xs text-muted-foreground">{t('dinamikQr.ayarlar.statikNot')}</p>}
                </section>
              </>
            )}

            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-white/10 pt-4">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setAdim(adim === 3 ? 2 : 1)}
                disabled={adim === 2 && !!kayit}
              >
                {t('dinamikQr.sihirbaz.geri')}
              </Button>
              <div className="flex gap-2">
                {adim === 2 && (
                  <Button type="button" variant="outline" className="!bg-transparent border-white/20" onClick={ileri} data-testid="qr-ileri">
                    {t('dinamikQr.sihirbaz.ileri')}
                  </Button>
                )}
                <Button type="button" onClick={kaydet} disabled={kaydediliyor} className="gap-1.5" data-testid="qr-kaydet">
                  {kaydediliyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Check className="h-4 w-4" aria-hidden="true" />}
                  {kaydediliyor ? t('dinamikQr.sihirbaz.kaydediliyor') : t('dinamikQr.sihirbaz.kaydet')}
                </Button>
              </div>
            </div>
          </div>

          {!kisa && (
            <aside className="space-y-3 lg:sticky lg:top-4 lg:self-start" aria-label={t('dinamikQr.sihirbaz.onizleme')}>
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>{t('dinamikQr.sihirbaz.onizleme')}</span>
                {onizlemeYukleniyor && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />}
              </div>
              <div className="flex aspect-square w-full max-w-[300px] items-center justify-center overflow-hidden rounded-xl border border-white/10 bg-white/[0.02] p-2">
                {onizleme && !onizlemeHatasi ? (
                  <img
                    src={svgAdresi(onizleme.svg)}
                    alt={t('dinamikQr.sihirbaz.onizlemeAlt', { ad: ad || t(`dinamikQr.tur.${tur}`) })}
                    className="h-full w-full object-contain"
                    data-testid="qr-onizleme-img"
                  />
                ) : (
                  <span className="px-4 text-center text-xs text-muted-foreground" data-testid="qr-onizleme-bos">
                    {onizlemeHatasi ?? t('dinamikQr.yukleniyor')}
                  </span>
                )}
              </div>
              {onizleme && !onizlemeHatasi && (
                <p className="text-[11px] text-muted-foreground">
                  {t('dinamikQr.sihirbaz.onizlemeOzet', { surum: onizleme.surum, hd: onizleme.hata_duzeltme })}
                </p>
              )}
              {onizleme?.uyarilar.map((u) => (
                <p
                  key={u}
                  className="flex items-start gap-1.5 rounded-lg border border-amber-400/30 bg-amber-500/10 p-2 text-xs text-amber-100"
                  data-qr-uyari={u}
                >
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-none" aria-hidden="true" />
                  {t(`dinamikQr.tasarim.uyari.${u}`, { oran: onizleme.kontrast })}
                </p>
              ))}
            </aside>
          )}
        </div>
      )}
    </div>
  );
}
