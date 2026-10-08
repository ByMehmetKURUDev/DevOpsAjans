import { useCallback, useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { toast } from 'sonner';
import {
  ArrowRight,
  CalendarClock,
  Check,
  CircleCheck,
  CircleDot,
  FileSignature,
  FileText,
  FolderKanban,
  LifeBuoy,
  Loader2,
  MessageSquare,
  PenTool,
  Receipt,
  ReceiptText,
  Target,
  UserCog,
  Wallet,
  type LucideIcon,
} from 'lucide-react';
import { IlerlemeHalkasi, SeriGrafik } from '@/components/panel/grafikler';
import { useStageLabels } from '@/lib/projectEvents';
import { islemlerimKarar } from '@/lib/imzaliIslem';
import { onaylarimKarar } from '@/lib/icerikOnay';
import { belgeApi } from '@/lib/belgeler';
import { faturamiBakiyedenOde, istekAnahtari } from '@/lib/cuzdan';
import { faturamOdemeBaglantisi } from '@/lib/faturaIslemleri';
import { mIcs } from '@/lib/toplantilar';
import {
  bellektekiOzet,
  musteriOzetiGetir,
  ozetiUnut,
  type AcikFatura,
  type DestekTalebi,
  type Ekip,
  type Hedef,
  type KalanIs,
  type MusteriOzeti,
  type OnayBekleyen,
  type OnayOgesi,
  type ProjeIlerleme,
  type Toplanti,
} from '@/lib/musteriOzeti';
import './musteriGenelBakis.css';

/**
 * Faz 11B — müşteri paneli "Genel bakış" (Panel v2, önizleme 5).
 *
 * Tek istek (`GET /api/v1/musteri-ozeti`, kısa bellek). Izgara: karşılama şeridi; proje ilerlemesi (halkalar),
 * kalan iş (gerçek alan + plan kesik çizgi), ekibiniz; onayınızı bekleyen (geniş), yaklaşan toplantı + bakiyem,
 * ortak hedef + faturalar ve destek. `null` / boş kalemin kartı ÇİZİLMEZ; kalan kartlar satırı ağırlıklarına
 * göre paylaşır (boşluk kalmaz). Hiç veri yoksa yalnız "Hoş geldiniz" + ilk adımlar kartı.
 *
 * Eylemler YALNIZ mevcut uçları çağırır: teslim onayı / fiyat teklifi `POST /islemlerim/{id}`, içerik onayı
 * `POST /icerik-onaylarim/{id}`, belge "okudum" `POST /belgelerim/{id}/okundu`, bakiyeden öde
 * `POST /cuzdanim/faturalar/{id}/ode`, ödeme sayfası `POST /faturalarim/{id}/odeme-baglantisi`, takvim
 * `GET /toplantilarim/{id}/ics`. Biçimli teklif ve sözleşme kararı ek bilgi istediği için (ad, imza) "İncele"
 * Faturalar sekmesindeki kendi akışına götürür.
 *
 * Renk tek başına bilgi taşımaz (durumlar yazıyla da); halkalarda metin karşılığı; grafikler `role="img"` +
 * özet etiketi; kart başlıkları başlık öğesi; `prefers-reduced-motion` ışıma animasyonunu kapatır.
 */

const RENK = {
  mor: '#a855f7',
  pembe: '#ff4fd8',
  mavi: '#60a5fa',
  yesil: '#2ef596',
  sari: '#fde68a',
  turuncu: '#fb923c',
  indigo: '#6366f1',
  camgobegi: '#38d1ff',
} as const;

const HALKA_RENKLERI: [string, string][] = [
  [RENK.mor, RENK.pembe],
  [RENK.mavi, RENK.mor],
  [RENK.pembe, RENK.turuncu],
];

const AVATAR_RENKLERI: [string, string][] = [
  ['#f9a8d4', RENK.mor],
  ['#93c5fd', RENK.indigo],
  [RENK.yesil, RENK.camgobegi],
  [RENK.sari, RENK.turuncu],
];

const SAAT_DILIMI = 'Europe/Istanbul';

interface Props {
  /** Etkin hesap (bellek anahtarı). */
  hesap: string;
  /** Görünen bölümler (bağlantılar yalnız bunlara). */
  bolumler: string[];
  /** Mesajlar sekmesi açık mı ("Ekibe yaz" oraya; değilse Destek). */
  mesajSekmesi: boolean;
  onBolumeGit: (sekme: string, hedef?: string) => void;
  onTalepAc: (id: number) => void;
  /** Bir karar/ödeme sonrası panelin kendi verisi (projeler, faturalar) tazelensin. */
  onDegisti?: () => void;
  /** Toplantısı ve talebi olmayan hesapta "Toplantı iste" kartı (Faz 6T bileşeni). */
  toplantiIste?: ReactNode;
}

// ---------------------------------------------------------------- biçim yardımcıları
function yuzdeYaz(n: number, dil: string): string {
  try {
    return new Intl.NumberFormat(dil, { style: 'percent', maximumFractionDigits: 0 }).format(n / 100);
  } catch {
    return `%${Math.round(n)}`;
  }
}

function sayiYaz(n: number, dil: string, kesir = 0): string {
  return new Intl.NumberFormat(dil, { maximumFractionDigits: kesir }).format(n);
}

function paraYaz(tutar: number, birim: string, dil: string): string {
  try {
    return new Intl.NumberFormat(dil, {
      style: 'currency',
      currency: birim || 'TRY',
      maximumFractionDigits: Number.isInteger(tutar) ? 0 : 2,
    }).format(tutar);
  } catch {
    return `${tutar} ${birim}`;
  }
}

/** 'YYYY-MM-DD' → yerel tarih (saat dilimi kaymasın diye öğlen). */
function gunTarihi(iso: string): Date {
  const [y, a, g] = iso.slice(0, 10).split('-').map(Number);
  return new Date(Date.UTC(y, (a || 1) - 1, g || 1, 12));
}

function tarihYaz(iso: string | null | undefined, dil: string, ay: 'long' | 'short' = 'long'): string {
  if (!iso) return '';
  try {
    return gunTarihi(iso).toLocaleDateString(dil, { day: 'numeric', month: ay, timeZone: 'UTC' });
  } catch {
    return iso.slice(0, 10);
  }
}

/** İstanbul takvim günü (YYYY-MM-DD). */
function istanbulGunu(an: Date): string {
  return an.toLocaleDateString('en-CA', { timeZone: SAAT_DILIMI });
}

/** "bugün", "dün", "3 gün önce" (dile göre). */
function goreliGun(iso: string | null | undefined, dil: string): string {
  if (!iso) return '';
  const fark = Math.round((gunTarihi(istanbulGunu(new Date(iso))).getTime() - gunTarihi(istanbulGunu(new Date())).getTime()) / 86_400_000);
  try {
    return new Intl.RelativeTimeFormat(dil, { numeric: 'auto' }).format(fark, 'day');
  } catch {
    return iso.slice(0, 10);
  }
}

function saatYaz(iso: string, dil: string): string {
  return new Date(iso).toLocaleTimeString(dil, { hour: '2-digit', minute: '2-digit', timeZone: SAAT_DILIMI });
}

/** Toplantı zamanı: "yarın 14:00–14:45" / "12 Ekim 14:00–14:45". */
function toplantiZamani(t: Toplanti, dil: string): string {
  if (!t.baslangic) return '';
  const bas = new Date(t.baslangic);
  const fark = Math.round((gunTarihi(istanbulGunu(bas)).getTime() - gunTarihi(istanbulGunu(new Date())).getTime()) / 86_400_000);
  let gun: string;
  if (Math.abs(fark) <= 1) {
    gun = new Intl.RelativeTimeFormat(dil, { numeric: 'auto' }).format(fark, 'day');
    gun = gun.charAt(0).toLocaleUpperCase(dil) + gun.slice(1);
  } else {
    gun = bas.toLocaleDateString(dil, { weekday: 'short', day: 'numeric', month: 'long', timeZone: SAAT_DILIMI });
  }
  const bitis = t.bitis ? `–${saatYaz(t.bitis, dil)}` : '';
  return `${gun} ${saatYaz(t.baslangic, dil)}${bitis}`;
}

/** Ağırlıklarla 12 sütunu paylaştırır (en büyük kalan yöntemi; toplam her zaman 12). */
function dagit(agirliklar: number[]): number[] {
  if (!agirliklar.length) return [];
  const toplam = agirliklar.reduce((a, b) => a + b, 0);
  const ham = agirliklar.map((a) => (a * 12) / toplam);
  const tam = ham.map((h) => Math.max(1, Math.floor(h)));
  let kalan = 12 - tam.reduce((a, b) => a + b, 0);
  const sira = ham.map((h, i) => ({ i, kesir: h - Math.floor(h) })).sort((a, b) => b.kesir - a.kesir);
  for (let k = 0; kalan > 0 && k < sira.length; k++, kalan--) tam[sira[k].i] += 1;
  return tam;
}

// ---------------------------------------------------------------- küçük parçalar
function Kart({
  sinif,
  baslik,
  ikon: Ikon,
  ikonRengi,
  sag,
  alt,
  children,
  span,
  ...ek
}: {
  sinif: string;
  baslik: ReactNode;
  ikon?: LucideIcon;
  ikonRengi?: string;
  sag?: ReactNode;
  alt?: ReactNode;
  children: ReactNode;
  span?: number;
} & Record<`data-${string}`, string | undefined>) {
  return (
    <article className={`mgb-kart ${sinif}`} style={span ? ({ '--mgb-span': span } as CSSProperties) : undefined} {...ek}>
      <header className="mgb-kart-ust">
        {Ikon && <Ikon className="mgb-kart-ikon" style={{ color: ikonRengi }} aria-hidden="true" />}
        <div className="mgb-kart-baslik-kutu">
          <h2 className="mgb-kart-baslik">{baslik}</h2>
          {alt && <p className="mgb-kart-alt">{alt}</p>}
        </div>
        {sag}
      </header>
      {children}
    </article>
  );
}

function Hap({ renk, children, ...ek }: { renk: string; children: ReactNode } & Record<`data-${string}`, string | undefined>) {
  return (
    <span className="mgb-hap" style={{ '--mgb-renk': renk } as CSSProperties} {...ek}>
      {children}
    </span>
  );
}

function Avatar({ harf, sira, boyut = 'buyuk', isik = true }: { harf: string; sira: number; boyut?: 'buyuk' | 'kucuk'; isik?: boolean }) {
  const [r1, r2] = AVATAR_RENKLERI[sira % AVATAR_RENKLERI.length];
  return (
    <span
      className={`mgb-avatar mgb-avatar-${boyut}${isik ? ' mgb-avatar-isik' : ''}`}
      style={{ background: `linear-gradient(135deg, ${r1}, ${r2})`, '--mgb-renk': r2 } as CSSProperties}
      aria-hidden="true"
    >
      {harf}
    </span>
  );
}

// ---------------------------------------------------------------- Karşılama
function Kahraman({
  ozet,
  dil,
  t,
  onIncele,
  onYaz,
}: {
  ozet: MusteriOzeti;
  dil: string;
  t: TFunction;
  onIncele: () => void;
  onYaz: () => void;
}) {
  const k = ozet.karsilama;
  const proje = k?.proje ?? null;
  const parcalar: ReactNode[] = [];
  if (k?.siradaki) {
    parcalar.push(
      <span key="s">
        {t('musteriOzeti.karsilama.siradaki')} <b>{k.siradaki.baslik}</b>
        {k.siradaki.tarih ? ` · ${tarihYaz(k.siradaki.tarih, dil)}` : ''}
      </span>,
    );
  }
  if (k?.onay_sayisi) parcalar.push(<span key="o">{t('musteriOzeti.karsilama.onayBekleyen', { sayi: k.onay_sayisi })}</span>);
  return (
    <section className="mgb-kahraman" aria-labelledby="mgb-baslik" data-mgb-kart="karsilama">
      <svg className="mgb-kahraman-dalga" viewBox="0 0 1380 170" preserveAspectRatio="none" aria-hidden="true" focusable="false">
        <path d="M0,150 C300,90 500,170 760,120 S1150,60 1380,110" className="mgb-dalga-1" />
        <path d="M0,160 C320,110 560,180 800,135 S1180,80 1380,125" className="mgb-dalga-2" />
      </svg>
      <div className="mgb-kahraman-metin">
        <p className="mgb-merhaba">{k?.hitap ? t('musteriOzeti.karsilama.merhabaAd', { ad: k.hitap }) : t('musteriOzeti.karsilama.merhaba')}</p>
        <h1 id="mgb-baslik" className="mgb-kahraman-baslik">
          {proje && proje.yuzde !== null ? (
            <>
              {proje.baslik} <span className="mgb-parlak mgb-mono">{yuzdeYaz(proje.yuzde, dil)}</span> {t('musteriOzeti.karsilama.hazir')}
            </>
          ) : proje ? (
            t('musteriOzeti.karsilama.devamEdiyor', { proje: proje.baslik })
          ) : (
            t('musteriOzeti.karsilama.panel')
          )}
        </h1>
        {parcalar.length > 0 && (
          <p className="mgb-kahraman-alt">
            {parcalar.map((p, i) => (
              <span key={i}>
                {i > 0 && ' · '}
                {p}
              </span>
            ))}
          </p>
        )}
      </div>
      <div className="mgb-kahraman-dugmeler">
        <button type="button" className="mgb-dugme mgb-dugme-pembe" onClick={onIncele} data-mgb-teslimler>
          {t('musteriOzeti.karsilama.teslimler')}
          <ArrowRight className="mgb-yon" aria-hidden="true" />
        </button>
        <button type="button" className="mgb-dugme mgb-dugme-cizgi" onClick={onYaz} data-mgb-ekibe-yaz>
          <MessageSquare aria-hidden="true" />
          {t('musteriOzeti.karsilama.ekibeYaz')}
        </button>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- Proje ilerlemesi
function IlerlemeKart({ v, dil, t, span }: { v: ProjeIlerleme; dil: string; t: TFunction; span?: number }) {
  const alt =
    v.tur === 'proje'
      ? t('musteriOzeti.ilerleme.etkinProjeler', { sayi: v.kalem_sayisi })
      : `${v.proje?.baslik ?? ''} · ${t(v.tur === 'grup' ? 'musteriOzeti.ilerleme.isKalemi' : 'musteriOzeti.ilerleme.kilometre', { sayi: v.kalem_sayisi })}`;
  return (
    <Kart sinif="mgb-ilerleme" baslik={t('musteriOzeti.ilerleme.baslik')} alt={alt} span={span} data-mgb-kart="ilerleme">
      <ul className="mgb-halkalar">
        {v.halkalar.map((h, i) => {
          const [r1, r2] = HALKA_RENKLERI[i % HALKA_RENKLERI.length];
          const deger = h.yuzde === null ? '—' : yuzdeYaz(h.yuzde, dil);
          const etiket =
            h.tamam !== null && h.toplam !== null
              ? t('musteriOzeti.ilerleme.halkaEtiketi', { ad: h.ad, deger, tamam: h.tamam, toplam: h.toplam })
              : t('musteriOzeti.ilerleme.halkaEtiketiKisa', { ad: h.ad, deger });
          return (
            <li key={h.id} className="mgb-halka-oge" role="img" aria-label={etiket} data-halka={h.yuzde ?? ''}>
              <IlerlemeHalkasi oran={h.yuzde === null ? null : h.yuzde / 100} renk1={r1} renk2={r2} ust={deger} alt={h.ad} boyut={100} />
            </li>
          );
        })}
      </ul>
      {(v.son_teslim || v.siradaki) && (
        <div className="mgb-teslimler">
          {v.son_teslim && (
            <p className="mgb-teslim">
              <span className="mgb-teslim-etiket">
                <Check className="mgb-yesil" aria-hidden="true" /> {t('musteriOzeti.ilerleme.sonTeslim')}
              </span>
              <b>
                {v.son_teslim.baslik}
                {v.son_teslim.tarih ? ` · ${tarihYaz(v.son_teslim.tarih, dil)}` : ''}
              </b>
            </p>
          )}
          {v.siradaki && (
            <p className="mgb-teslim">
              <span className="mgb-teslim-etiket">
                <CircleDot className="mgb-sari" aria-hidden="true" /> {t('musteriOzeti.ilerleme.siradaki')}
              </span>
              <b>
                {v.siradaki.baslik}
                {v.siradaki.tarih ? ` · ${tarihYaz(v.siradaki.tarih, dil)}` : ''}
              </b>
            </p>
          )}
        </div>
      )}
    </Kart>
  );
}

// ---------------------------------------------------------------- Kalan iş
function KalanIsKart({ v, dil, t, span }: { v: KalanIs; dil: string; t: TFunction; span?: number }) {
  const fark = v.plan_farki_gun;
  const durum =
    fark === null || v.plan === null
      ? null
      : fark > 0
        ? t('musteriOzeti.kalan.onde', { sayi: fark })
        : fark < 0
          ? t('musteriOzeti.kalan.geride', { sayi: Math.abs(fark) })
          : t('musteriOzeti.kalan.planda');
  const etiketler = v.gunler.map((g, i) => (i === 0 ? tarihYaz(g, dil, 'short') : String(gunTarihi(g).getUTCDate())));
  const ozetEtiketi = t('musteriOzeti.kalan.grafikEtiketi', {
    sayi: v.kalan,
    bas: tarihYaz(v.gunler[0], dil),
    son: tarihYaz(v.gunler[v.gunler.length - 1], dil),
    ilk: v.gercek[0],
  });
  return (
    <Kart
      sinif="mgb-kalan"
      baslik={t('musteriOzeti.kalan.baslik')}
      span={span}
      data-mgb-kart="kalan"
      sag={
        <div className="mgb-lejant" aria-hidden="true">
          <span>
            <i style={{ background: RENK.pembe }} /> {t('musteriOzeti.kalan.gercek')}
          </span>
          {v.plan && (
            <span>
              <i style={{ background: RENK.mavi }} /> {t('musteriOzeti.kalan.plan')}
            </span>
          )}
        </div>
      }
    >
      <p className="mgb-kalan-ozet">
        <span className="mgb-buyuk mgb-mono" data-kalan={v.kalan}>
          {sayiYaz(v.kalan, dil)}
        </span>
        <span className="mgb-soluk">
          {t('musteriOzeti.kalan.gorev', { sayi: v.kalan })}
          {durum ? ` · ${durum}` : ''}
        </span>
      </p>
      <SeriGrafik gercek={v.gercek} plan={v.plan} etiketler={etiketler} renk1={RENK.pembe} renk2={RENK.mavi} etiket={ozetEtiketi} yukseklik={176} />
    </Kart>
  );
}

// ---------------------------------------------------------------- Ekip
function EkipKart({ v, dil, t, span, onYaz }: { v: Ekip; dil: string; t: TFunction; span?: number; onYaz: () => void }) {
  const rol = (k: Ekip['kisiler'][number]) =>
    k.hizmet ? t(`musteriOzeti.ekip.hizmet.${k.hizmet}`, { defaultValue: t('musteriOzeti.ekip.rol.calisan') }) : t(`musteriOzeti.ekip.rol.${k.rol}`);
  return (
    <Kart sinif="mgb-ekip" baslik={t('musteriOzeti.ekip.baslik')} span={span} data-mgb-kart="ekip">
      <ul className="mgb-ekip-liste">
        {v.kisiler.map((k, i) => (
          <li key={`${k.bas_harf}-${i}`} className="mgb-ekip-kisi">
            <Avatar harf={k.bas_harf} sira={i} />
            <b dir="auto">{k.ad}</b>
            <span className="mgb-soluk">{rol(k)}</span>
          </li>
        ))}
      </ul>
      <button type="button" className="mgb-dugme mgb-dugme-cizgi mgb-tam" onClick={onYaz} data-mgb-mesaj>
        <MessageSquare aria-hidden="true" />
        {t('musteriOzeti.ekip.mesajGonder')}
        {v.ort_yanit_dk !== null && (
          <span className="mgb-soluk-acik">
            {' · '}
            {v.ort_yanit_dk < 60
              ? t('musteriOzeti.ekip.ortYanitDk', { sayi: v.ort_yanit_dk })
              : t('musteriOzeti.ekip.ortYanitSa', { sayi: sayiYaz(v.ort_yanit_dk / 60, dil, 1) })}
          </span>
        )}
      </button>
    </Kart>
  );
}

// ---------------------------------------------------------------- Onay bekleyenler
type Bekleyen = { oge: OnayOgesi; eylem: 'onay' | 'kabul' | 'revizyon' | 'red' } | null;

const ONAY_IKONU: Record<string, LucideIcon> = {
  teslimat: FolderKanban,
  teklif_kabul: ReceiptText,
  icerik: PenTool,
  teklif: ReceiptText,
  sozlesme: FileSignature,
  belge: FileText,
};

function OnayKart({
  v,
  dil,
  t,
  span,
  kartRef,
  onKarar,
  onIncele,
  onTumu,
}: {
  v: OnayBekleyen;
  dil: string;
  t: TFunction;
  span?: number;
  kartRef: React.RefObject<HTMLElement>;
  onKarar: (oge: OnayOgesi, sonuc: 'onay' | 'revizyon' | 'kabul' | 'red' | 'okundu', not?: string) => Promise<boolean>;
  onIncele: (oge: OnayOgesi) => void;
  onTumu: () => void;
}) {
  const stageLabel = useStageLabels();
  const [bekleyen, setBekleyen] = useState<Bekleyen>(null);
  const [not, setNot] = useState('');
  const [mesgul, setMesgul] = useState<number | null>(null);

  const anahtar = (o: OnayOgesi) => `${o.tur}-${o.id}`;
  const altBilgi = (o: OnayOgesi): string => {
    const parca: string[] = [t(`musteriOzeti.onay.tur.${o.tur}`)];
    if (o.tur === 'teslimat' && o.asama) parca.push(stageLabel(o.asama));
    if (o.tur === 'icerik') {
      if (o.gorsel) parca.push(t('musteriOzeti.onay.gorsel', { sayi: o.gorsel }));
      if (o.kelime) parca.push(t('musteriOzeti.onay.kelime', { sayi: o.kelime, deger: sayiYaz(o.kelime, dil) }));
    }
    if ((o.tur === 'teklif' || o.tur === 'teklif_kabul') && o.tutar != null) parca.push(paraYaz(o.tutar, o.para_birimi || 'TRY', dil));
    if (o.tur === 'belge' && o.surum && o.surum > 1) parca.push(t('musteriOzeti.onay.surum', { sayi: o.surum }));
    if (o.tarih) parca.push(goreliGun(o.tarih, dil));
    return parca.join(' · ');
  };

  const gonder = async (o: OnayOgesi, sonuc: 'onay' | 'revizyon' | 'kabul' | 'red' | 'okundu', metin?: string) => {
    setMesgul(o.id);
    const tamam = await onKarar(o, sonuc, metin);
    setMesgul(null);
    if (tamam) {
      setBekleyen(null);
      setNot('');
    }
  };

  const r = v.revizyon;
  const revizyonYazisi = !r
    ? null
    : r.asildi || (r.kalan !== null && r.kalan <= 0)
      ? t('musteriOzeti.onay.revizyonBitti')
      : r.kalan !== null
        ? t('musteriOzeti.onay.revizyonKalan', { sure: sayiYaz(r.kalan, dil, 1) })
        : null;

  return (
    <Kart
      sinif="mgb-onay"
      baslik={t('musteriOzeti.onay.baslik')}
      span={span}
      data-mgb-kart="onay"
      sag={
        v.toplam > v.ogeler.length ? (
          <button type="button" className="mgb-bag" onClick={onTumu}>
            {t('musteriOzeti.onay.tumu', { sayi: v.toplam })}
          </button>
        ) : (
          <Hap renk={RENK.sari}>{sayiYaz(v.toplam, dil)}</Hap>
        )
      }
    >
      <div ref={kartRef as React.RefObject<HTMLDivElement>} className="mgb-onay-capa" tabIndex={-1} />
      <ul className="mgb-onay-liste">
        {v.ogeler.map((o) => {
          const Ikon = ONAY_IKONU[o.tur] ?? CircleCheck;
          const acik = bekleyen && anahtar(bekleyen.oge) === anahtar(o) ? bekleyen.eylem : null;
          const kilitli = mesgul === o.id;
          const notGerekli = acik === 'revizyon';
          return (
            <li key={anahtar(o)} className="mgb-onay-oge" data-onay-oge={o.tur} data-onay-id={o.id}>
              <div className="mgb-onay-ust">
                <Ikon className="mgb-onay-ikon" aria-hidden="true" />
                <div className="mgb-onay-metin">
                  <h3 className="mgb-onay-baslik">{o.baslik}</h3>
                  <p className="mgb-soluk mgb-kucuk">{altBilgi(o)}</p>
                  {o.tur === 'teslimat' && o.not && <p className="mgb-onay-not">“{o.not}”</p>}
                </div>
                <Hap renk={RENK.sari}>{t(o.tur === 'sozlesme' ? 'musteriOzeti.onay.imzaBekliyor' : o.tur === 'belge' ? 'musteriOzeti.onay.okumaBekliyor' : 'musteriOzeti.onay.onayBekliyor')}</Hap>
              </div>

              {acik === 'revizyon' || acik === 'red' ? (
                <form
                  className="mgb-onay-form"
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (notGerekli && !not.trim()) return;
                    void gonder(o, acik, not.trim() || undefined);
                  }}
                >
                  <label className="mgb-kucuk mgb-soluk" htmlFor={`mgb-not-${anahtar(o)}`}>
                    {t(acik === 'revizyon' ? 'musteriOzeti.onay.revizyonNotu' : 'musteriOzeti.onay.redNotu')}
                  </label>
                  <textarea
                    id={`mgb-not-${anahtar(o)}`}
                    className="mgb-girdi"
                    rows={2}
                    maxLength={1000}
                    value={not}
                    required={notGerekli}
                    onChange={(e) => setNot(e.target.value)}
                    data-mgb-not
                  />
                  <div className="mgb-dugmeler">
                    <button type="submit" className="mgb-dugme mgb-dugme-mor" disabled={kilitli || (notGerekli && !not.trim())} data-mgb-gonder>
                      {kilitli && <Loader2 className="mgb-don" aria-hidden="true" />}
                      {t(acik === 'revizyon' ? 'musteriOzeti.onay.revizyonGonder' : 'musteriOzeti.onay.reddet')}
                    </button>
                    <button type="button" className="mgb-dugme mgb-dugme-cizgi" onClick={() => setBekleyen(null)}>
                      {t('musteriOzeti.vazgec')}
                    </button>
                  </div>
                </form>
              ) : acik === 'onay' || acik === 'kabul' ? (
                <div className="mgb-onay-form" role="group" aria-label={t('musteriOzeti.onay.eminMisiniz')}>
                  <p className="mgb-kucuk">{t(acik === 'onay' ? 'musteriOzeti.onay.onayEmin' : 'musteriOzeti.onay.kabulEmin')}</p>
                  <div className="mgb-dugmeler">
                    <button type="button" className="mgb-dugme mgb-dugme-yesil" disabled={kilitli} onClick={() => void gonder(o, acik)} data-mgb-evet>
                      {kilitli ? <Loader2 className="mgb-don" aria-hidden="true" /> : <Check aria-hidden="true" />}
                      {t(acik === 'onay' ? 'musteriOzeti.onay.evetOnayla' : 'musteriOzeti.onay.evetKabul')}
                    </button>
                    <button type="button" className="mgb-dugme mgb-dugme-cizgi" onClick={() => setBekleyen(null)}>
                      {t('musteriOzeti.vazgec')}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="mgb-onay-alt">
                  <div className="mgb-dugmeler">
                    {o.eylemler.includes('onay') && (
                      <button type="button" className="mgb-dugme mgb-dugme-yesil" onClick={() => setBekleyen({ oge: o, eylem: 'onay' })} data-mgb-onayla>
                        <Check aria-hidden="true" />
                        {t('musteriOzeti.onay.onayla')}
                      </button>
                    )}
                    {o.eylemler.includes('revizyon') && (
                      <button type="button" className="mgb-dugme mgb-dugme-cizgi" onClick={() => { setNot(''); setBekleyen({ oge: o, eylem: 'revizyon' }); }} data-mgb-revizyon>
                        {t('musteriOzeti.onay.revizyonIste')}
                      </button>
                    )}
                    {o.eylemler.includes('kabul') && (
                      <button type="button" className="mgb-dugme mgb-dugme-yesil" onClick={() => setBekleyen({ oge: o, eylem: 'kabul' })} data-mgb-kabul>
                        <Check aria-hidden="true" />
                        {t('musteriOzeti.onay.kabulEt')}
                      </button>
                    )}
                    {o.eylemler.includes('red') && (
                      <button type="button" className="mgb-dugme mgb-dugme-cizgi" onClick={() => { setNot(''); setBekleyen({ oge: o, eylem: 'red' }); }} data-mgb-red>
                        {t('musteriOzeti.onay.reddet')}
                      </button>
                    )}
                    {o.eylemler.includes('okundu') && (
                      <button type="button" className="mgb-dugme mgb-dugme-yesil" disabled={kilitli} onClick={() => void gonder(o, 'okundu')} data-mgb-okundu>
                        {kilitli ? <Loader2 className="mgb-don" aria-hidden="true" /> : <Check aria-hidden="true" />}
                        {t('musteriOzeti.onay.okudum')}
                      </button>
                    )}
                    {o.eylemler.includes('incele') && (
                      <button type="button" className="mgb-dugme mgb-dugme-mor" onClick={() => onIncele(o)} data-mgb-incele>
                        {t(o.tur === 'sozlesme' ? 'musteriOzeti.onay.imzala' : 'musteriOzeti.onay.incele')}
                        <ArrowRight className="mgb-yon" aria-hidden="true" />
                      </button>
                    )}
                  </div>
                  {revizyonYazisi && (o.tur === 'teslimat' || o.tur === 'icerik') && <span className="mgb-soluk mgb-kucuk">{revizyonYazisi}</span>}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </Kart>
  );
}

// ---------------------------------------------------------------- Toplantı
function ToplantiKart({ v, dil, t, ayrinti }: { v: Toplanti; dil: string; t: TFunction; ayrinti?: () => void }) {
  const [iniyor, setIniyor] = useState(false);
  const yer = t(`musteriOzeti.toplanti.yer.${v.yer_turu}`, { defaultValue: '' });
  const yanit = v.katilimci_miyim && v.yanitim ? t(`musteriOzeti.toplanti.yanit.${v.yanitim}`) : null;
  return (
    <Kart sinif="mgb-toplanti" baslik={t('musteriOzeti.toplanti.baslik')} ikon={CalendarClock} ikonRengi={RENK.mavi} data-mgb-kart="toplanti">
      <h3 className="mgb-toplanti-baslik">{v.baslik}</h3>
      <p className="mgb-toplanti-zaman">
        {toplantiZamani(v, dil)}
        {yer ? ` · ${yer}` : ''}
      </p>
      <div className="mgb-katilimcilar">
        <span className="mgb-avatar-yigin" aria-hidden="true">
          {v.katilimcilar.map((k, i) => (
            <Avatar key={i} harf={k.bas_harf} sira={i} boyut="kucuk" isik={false} />
          ))}
        </span>
        <span className="mgb-kucuk">
          {t('musteriOzeti.toplanti.katilimci', { sayi: v.katilimci_sayisi })}
          {yanit ? ` · ${yanit}` : ''}
        </span>
      </div>
      <div className="mgb-dugmeler">
        {v.katil_baglantisi && (
          <a className="mgb-dugme mgb-dugme-mavi" href={v.katil_baglantisi} target="_blank" rel="noopener noreferrer" data-mgb-katil>
            {t('musteriOzeti.toplanti.katil')}
          </a>
        )}
        <button
          type="button"
          className="mgb-dugme mgb-dugme-cizgi-mavi"
          disabled={iniyor}
          onClick={() => {
            setIniyor(true);
            mIcs(v.id)
              .catch(() => toast.error(t('musteriOzeti.hata.genel')))
              .finally(() => setIniyor(false));
          }}
          data-mgb-ics
        >
          {t('musteriOzeti.toplanti.takvimeEkle')}
        </button>
        {ayrinti && (
          <button type="button" className="mgb-bag" onClick={ayrinti}>
            {t('musteriOzeti.toplanti.ayrinti')}
          </button>
        )}
      </div>
      {!v.katil_baglantisi && v.katil_yakinda && <p className="mgb-kucuk mgb-soluk">{t('musteriOzeti.toplanti.katilYakinda')}</p>}
    </Kart>
  );
}

// ---------------------------------------------------------------- Bakiye
function BakiyeKart({ v, dil, t, onYukle, onHareketler }: { v: NonNullable<MusteriOzeti['bakiye']>; dil: string; t: TFunction; onYukle: () => void; onHareketler: () => void }) {
  const [ilk, ...diger] = v.bakiyeler;
  return (
    <Kart sinif="mgb-bakiye" baslik={t('musteriOzeti.bakiye.baslik')} ikon={Wallet} ikonRengi={RENK.yesil} data-mgb-kart="bakiye">
      <p className="mgb-bakiye-tutar mgb-mono" data-mgb-bakiye={ilk ? ilk.bakiye : 0}>
        {ilk ? paraYaz(ilk.bakiye, ilk.para_birimi, dil) : paraYaz(0, 'TRY', dil)}
      </p>
      {diger.length > 0 && <p className="mgb-kucuk mgb-mono">{diger.map((b) => paraYaz(b.bakiye, b.para_birimi, dil)).join(' · ')}</p>}
      <p className="mgb-kucuk mgb-bakiye-not">
        {v.otomatik_odeme ? t('musteriOzeti.bakiye.otomatikAcik') : t('musteriOzeti.bakiye.otomatikKapali')}
        {v.bekleyen_yukleme > 0 && ` · ${t('musteriOzeti.bakiye.bekleyen', { sayi: v.bekleyen_yukleme })}`}
      </p>
      <div className="mgb-dugmeler">
        <button type="button" className="mgb-dugme mgb-dugme-yesil" onClick={onYukle} data-mgb-bakiye-yukle>
          {t('musteriOzeti.bakiye.yukle')}
        </button>
        <button type="button" className="mgb-dugme mgb-dugme-cizgi-yesil" onClick={onHareketler}>
          {t('musteriOzeti.bakiye.hareketler')}
        </button>
      </div>
    </Kart>
  );
}

// ---------------------------------------------------------------- Hedef
function HedefKart({ v, dil, t }: { v: Hedef; dil: string; t: TFunction }) {
  const durumRengi: Record<string, string> = { tamam: RENK.yesil, yolunda: RENK.yesil, riskli: RENK.sari, geride: RENK.turuncu };
  const KR_RENKLERI = [RENK.mor, RENK.pembe, RENK.yesil];
  const d = v.donem;
  const donem = d.ad
    ? d.ad
    : `${gunTarihi(d.baslangic).toLocaleDateString(dil, { month: 'long', timeZone: 'UTC' })}–${gunTarihi(d.bitis).toLocaleDateString(dil, { month: 'long', year: 'numeric', timeZone: 'UTC' })}`;
  const ajans = v.kaynak === 'ajans';
  return (
    <Kart
      sinif="mgb-hedef"
      baslik={ajans ? t('hedefKarti.baslik') : t('musteriOzeti.hedef.kendiBaslik')}
      ikon={Target}
      ikonRengi={RENK.pembe}
      sag={v.durum ? <Hap renk={durumRengi[v.durum] ?? RENK.mor}>{t(`hedefKarti.durum.${v.durum}`)}</Hap> : undefined}
      data-mgb-kart="hedef"
      data-testid={ajans ? 'okr-paylasilan' : undefined}
    >
      <h3 className="mgb-hedef-baslik">{v.baslik}</h3>
      <p className="mgb-kucuk mgb-soluk">
        {donem} · {t('musteriOzeti.hedef.beklenen', { deger: yuzdeYaz(v.beklenen * 100, dil) })}
        {v.ilerleme !== null && ` · ${t('musteriOzeti.hedef.gerceklesen', { deger: yuzdeYaz(v.ilerleme * 100, dil) })}`}
      </p>
      <ul className="mgb-krler">
        {v.krler.map((k, i) => {
          const oran = Math.max(0, Math.min(1, k.ilerleme));
          const renk = KR_RENKLERI[i % KR_RENKLERI.length];
          return (
            <li key={k.id} className="mgb-kr">
              <div className="mgb-kr-ust">
                <span>{k.baslik}</span>
                <b className="mgb-mono">{yuzdeYaz(oran * 100, dil)}</b>
              </div>
              <div
                className="mgb-kr-cubuk"
                role="progressbar"
                aria-label={k.baslik}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={Math.round(oran * 100)}
              >
                <span style={{ width: `${oran * 100}%`, '--mgb-renk': renk } as CSSProperties} />
              </div>
            </li>
          );
        })}
      </ul>
      {v.kr_sayisi > v.krler.length && <p className="mgb-kucuk mgb-soluk">{t('musteriOzeti.hedef.dahaFazla', { sayi: v.kr_sayisi - v.krler.length })}</p>}
    </Kart>
  );
}

// ---------------------------------------------------------------- Faturalar ve destek
function FaturaDestekKart({
  faturalar,
  destek,
  dil,
  t,
  onOde,
  onTalepAc,
  onFaturalar,
}: {
  faturalar: AcikFatura[];
  destek: DestekTalebi[];
  dil: string;
  t: TFunction;
  onOde: (f: AcikFatura) => Promise<boolean>;
  onTalepAc: (id: number) => void;
  onFaturalar: () => void;
}) {
  const [onayla, setOnayla] = useState<number | null>(null);
  const [mesgul, setMesgul] = useState<number | null>(null);
  const odemeSayfasi = async (f: AcikFatura) => {
    setMesgul(f.id);
    try {
      const adres = f.odeme_adresi || (await faturamOdemeBaglantisi(f.id)).adres;
      if (adres.startsWith('/')) window.location.assign(adres);
      else onFaturalar();
    } catch {
      onFaturalar();
    } finally {
      setMesgul(null);
    }
  };
  return (
    <Kart sinif="mgb-fatura-destek" baslik={t('musteriOzeti.faturaDestek.baslik')} data-mgb-kart="fatura-destek">
      <ul className="mgb-satirlar">
        {faturalar.map((f) => (
          <li key={`f-${f.id}`} className="mgb-satir" data-mgb-fatura={f.id}>
            <Receipt className="mgb-satir-ikon mgb-sari" aria-hidden="true" />
            <div className="mgb-satir-metin">
              <b>
                <span className="mgb-mono">{f.kod}</span> · <span className="mgb-mono">{paraYaz(f.kalan, f.para_birimi, dil)}</span>
              </b>
              <span className={`mgb-kucuk ${f.gecikmis ? 'mgb-kirmizi' : 'mgb-soluk'}`}>
                {f.vade ? t(f.gecikmis ? 'musteriOzeti.faturaDestek.gecikti' : 'musteriOzeti.faturaDestek.vade', { tarih: tarihYaz(f.vade, dil) }) : t('musteriOzeti.faturaDestek.acik')}
              </span>
            </div>
            {onayla === f.id ? (
              <div className="mgb-satir-onay" role="group" aria-label={t('musteriOzeti.faturaDestek.odeEmin', { tutar: paraYaz(f.kalan, f.para_birimi, dil) })}>
                <span className="mgb-kucuk">{t('musteriOzeti.faturaDestek.odeEmin', { tutar: paraYaz(f.kalan, f.para_birimi, dil) })}</span>
                <button
                  type="button"
                  className="mgb-dugme mgb-dugme-mor mgb-kucuk-dugme"
                  disabled={mesgul === f.id}
                  onClick={async () => {
                    setMesgul(f.id);
                    const ok = await onOde(f);
                    setMesgul(null);
                    if (ok) setOnayla(null);
                  }}
                  data-mgb-ode-evet
                >
                  {mesgul === f.id && <Loader2 className="mgb-don" aria-hidden="true" />}
                  {t('musteriOzeti.faturaDestek.ode')}
                </button>
                <button type="button" className="mgb-dugme mgb-dugme-cizgi mgb-kucuk-dugme" onClick={() => setOnayla(null)}>
                  {t('musteriOzeti.vazgec')}
                </button>
              </div>
            ) : f.bakiyeden ? (
              <button type="button" className="mgb-dugme mgb-dugme-mor mgb-kucuk-dugme" onClick={() => setOnayla(f.id)} data-mgb-bakiyeden-ode>
                {t('musteriOzeti.faturaDestek.bakiyedenOde')}
              </button>
            ) : (
              <button type="button" className="mgb-dugme mgb-dugme-cizgi mgb-kucuk-dugme" disabled={mesgul === f.id} onClick={() => void odemeSayfasi(f)} data-mgb-ode>
                {mesgul === f.id && <Loader2 className="mgb-don" aria-hidden="true" />}
                {t('musteriOzeti.faturaDestek.odemeYap')}
              </button>
            )}
          </li>
        ))}
        {destek.map((d) => (
          <li key={`d-${d.id}`} className="mgb-satir" data-mgb-talep={d.id}>
            <LifeBuoy className="mgb-satir-ikon mgb-mavi" aria-hidden="true" />
            <div className="mgb-satir-metin">
              <b>
                <span className="mgb-mono">{d.kod}</span> · {d.baslik}
              </b>
              <span className="mgb-kucuk mgb-soluk">
                {d.yanit_bekliyor ? t('musteriOzeti.faturaDestek.siziBekliyor') : t('musteriOzeti.faturaDestek.acikTalep')}
              </span>
            </div>
            <button type="button" className={`mgb-hap-dugme ${d.yanit_bekliyor ? 'mgb-hap-mavi' : ''}`} onClick={() => onTalepAc(d.id)}>
              {d.yanit_bekliyor ? t('musteriOzeti.faturaDestek.yanitVerin') : t('musteriOzeti.faturaDestek.ac')}
            </button>
          </li>
        ))}
      </ul>
    </Kart>
  );
}

// ---------------------------------------------------------------- Hoş geldiniz (veri yok)
function HosGeldin({
  hitap,
  t,
  bolumler,
  mesajSekmesi,
  onBolumeGit,
  toplantiIste,
}: {
  hitap: string | null;
  t: TFunction;
  bolumler: string[];
  mesajSekmesi: boolean;
  onBolumeGit: (s: string) => void;
  toplantiIste?: ReactNode;
}) {
  const adimlar: { sekme: string; ikon: LucideIcon; anahtar: string }[] = [
    { sekme: 'projects', ikon: FolderKanban, anahtar: 'projeler' },
    { sekme: 'tickets', ikon: LifeBuoy, anahtar: 'talep' },
    ...(mesajSekmesi ? [{ sekme: 'mesajlar', ikon: MessageSquare, anahtar: 'mesaj' }] : []),
    { sekme: 'invoices', ikon: Receipt, anahtar: 'faturalar' },
    { sekme: 'profile', ikon: UserCog, anahtar: 'profil' },
  ].filter((a) => bolumler.includes(a.sekme));
  return (
    <section className="mgb-hos-geldin" aria-labelledby="mgb-baslik" data-mgb-kart="hos-geldin" data-testid="mgb-hos-geldin">
      <svg className="mgb-kahraman-dalga" viewBox="0 0 1380 170" preserveAspectRatio="none" aria-hidden="true" focusable="false">
        <path d="M0,150 C300,90 500,170 760,120 S1150,60 1380,110" className="mgb-dalga-1" />
      </svg>
      <p className="mgb-merhaba">{hitap ? t('musteriOzeti.karsilama.merhabaAd', { ad: hitap }) : t('musteriOzeti.karsilama.merhaba')}</p>
      <h1 id="mgb-baslik" className="mgb-kahraman-baslik">
        {t('musteriOzeti.hosGeldin.baslik')}
      </h1>
      <p className="mgb-hos-geldin-metin">{t('musteriOzeti.hosGeldin.metin')}</p>
      <h2 className="mgb-hos-geldin-alt">{t('musteriOzeti.hosGeldin.ilkAdimlar')}</h2>
      <ul className="mgb-adimlar">
        {adimlar.map((a) => (
          <li key={a.sekme}>
            <button type="button" className="mgb-adim" onClick={() => onBolumeGit(a.sekme)} data-mgb-adim={a.sekme}>
              <a.ikon aria-hidden="true" />
              <span>
                <b>{t(`musteriOzeti.hosGeldin.adim.${a.anahtar}.baslik`)}</b>
                <span className="mgb-kucuk mgb-soluk">{t(`musteriOzeti.hosGeldin.adim.${a.anahtar}.metin`)}</span>
              </span>
              <ArrowRight className="mgb-yon" aria-hidden="true" />
            </button>
          </li>
        ))}
      </ul>
      {toplantiIste && <div className="mgb-toplanti-iste">{toplantiIste}</div>}
    </section>
  );
}

// ---------------------------------------------------------------- Ana bileşen
export default function MusteriGenelBakis({ hesap, bolumler, mesajSekmesi, onBolumeGit, onTalepAc, onDegisti, toplantiIste }: Props) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [ozet, setOzet] = useState<MusteriOzeti | null>(() => bellektekiOzet(hesap));
  const [hata, setHata] = useState(false);
  const onayRef = useRef<HTMLElement>(null);

  const yukle = useCallback(async () => {
    try {
      setOzet(await musteriOzetiGetir(hesap));
      setHata(false);
    } catch {
      setHata(true);
    }
  }, [hesap]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const tazele = useCallback(() => {
    ozetiUnut();
    void yukle();
    onDegisti?.();
  }, [yukle, onDegisti]);

  const git = (sekme: string, hedef?: string) => {
    if (bolumler.includes(sekme)) onBolumeGit(sekme, hedef);
  };
  const ekibeYaz = () => git(mesajSekmesi ? 'mesajlar' : 'tickets');

  const hataGoster = (h: unknown) => {
    const durum = (h as { durum?: number })?.durum ?? 0;
    if (durum === 404 || durum === 409 || durum === 410) {
      toast.error(t('musteriOzeti.hata.artikBeklemiyor'));
      tazele();
    } else {
      toast.error(t('musteriOzeti.hata.genel'));
    }
  };

  const karar = async (o: OnayOgesi, sonuc: 'onay' | 'revizyon' | 'kabul' | 'red' | 'okundu', not?: string): Promise<boolean> => {
    try {
      if (o.tur === 'icerik') await onaylarimKarar(o.id, sonuc as 'onay' | 'revizyon', not);
      else if (o.tur === 'belge') await belgeApi('musteri').okundu(o.id);
      else await islemlerimKarar(o.id, sonuc as 'onay' | 'revizyon' | 'kabul' | 'red', not);
    } catch (h) {
      hataGoster(h);
      return false;
    }
    toast.success(t(`musteriOzeti.onay.basarili.${sonuc}`));
    // Öğe hemen listeden düşsün; sayılar sunucudan tazelenir.
    setOzet((x) =>
      x && x.onayBekleyen
        ? {
            ...x,
            onayBekleyen: { ...x.onayBekleyen, toplam: x.onayBekleyen.toplam - 1, ogeler: x.onayBekleyen.ogeler.filter((y) => !(y.tur === o.tur && y.id === o.id)) },
            karsilama: x.karsilama ? { ...x.karsilama, onay_sayisi: Math.max(0, (x.karsilama.onay_sayisi ?? 1) - 1) } : x.karsilama,
          }
        : x,
    );
    tazele();
    return true;
  };

  const bakiyedenOde = async (f: AcikFatura): Promise<boolean> => {
    try {
      await faturamiBakiyedenOde(f.id, null, istekAnahtari());
    } catch (h) {
      hataGoster(h);
      return false;
    }
    toast.success(t('musteriOzeti.faturaDestek.odendi', { kod: f.kod }));
    setOzet((x) => (x && x.faturalar ? { ...x, faturalar: { acik_sayisi: x.faturalar.acik_sayisi - 1, ogeler: x.faturalar.ogeler.filter((y) => y.id !== f.id) } } : x));
    tazele();
    return true;
  };

  if (!ozet) {
    return (
      <section className="mgb mgb-durum" aria-busy={!hata} data-musteri-genel-bakis="">
        {hata ? (
          <div className="mgb-kart mgb-hata">
            <p>{t('musteriOzeti.hata.yuklenemedi')}</p>
            <button type="button" className="mgb-dugme mgb-dugme-cizgi" onClick={() => void yukle()}>
              {t('musteriOzeti.yenidenDene')}
            </button>
          </div>
        ) : (
          <p className="mgb-yukleniyor">
            <Loader2 className="mgb-don" aria-hidden="true" /> {t('musteriOzeti.yukleniyor')}
          </p>
        )}
      </section>
    );
  }

  const k = ozet.karsilama;
  const ilerleme = ozet.projeIlerleme && ozet.projeIlerleme.halkalar.length ? ozet.projeIlerleme : null;
  const kalan = ozet.kalanIs;
  const ekip = ozet.ekip && ozet.ekip.kisiler.length ? ozet.ekip : null;
  const onay = ozet.onayBekleyen && ozet.onayBekleyen.ogeler.length ? ozet.onayBekleyen : null;
  const faturalar = ozet.faturalar?.ogeler ?? [];
  const destek = ozet.destek?.ogeler ?? [];
  const faturaDestek = faturalar.length > 0 || destek.length > 0;
  const toplantiVar = !!ozet.toplanti;
  const ortaSutun = toplantiVar || !!ozet.bakiye || !!toplantiIste;
  const sagSutun = !!ozet.hedef || faturaDestek;
  const veriVar = !!(k?.proje || ilerleme || kalan || ekip || onay || toplantiVar || ozet.hedef || ozet.bakiye || faturaDestek);

  if (!veriVar) {
    return (
      <section className="mgb" aria-label={t('musteriOzeti.bolgeEtiketi')} data-musteri-genel-bakis="" data-bos="">
        <HosGeldin hitap={k?.hitap ?? null} t={t} bolumler={bolumler} mesajSekmesi={mesajSekmesi} onBolumeGit={git} toplantiIste={toplantiIste} />
      </section>
    );
  }

  const satir1 = [ilerleme && 4, kalan && 5, ekip && 3].filter(Boolean) as number[];
  const s1 = dagit(satir1);
  let i1 = 0;
  const satir2 = [onay && 5, ortaSutun && 3, sagSutun && 4].filter(Boolean) as number[];
  const s2 = dagit(satir2);
  let i2 = 0;
  const sutunStili = (span: number) => ({ '--mgb-span': span }) as CSSProperties;

  return (
    <section className="mgb" aria-label={t('musteriOzeti.bolgeEtiketi')} data-musteri-genel-bakis="">
      <div className="mgb-izgara">
        <Kahraman
          ozet={ozet}
          dil={dil}
          t={t}
          onIncele={() => {
            if (onay && onayRef.current) {
              onayRef.current.closest('.mgb-kart')?.scrollIntoView({ block: 'center', behavior: 'auto' });
              onayRef.current.focus({ preventScroll: true });
            } else git('projects');
          }}
          onYaz={ekibeYaz}
        />
        {ilerleme && <IlerlemeKart v={ilerleme} dil={dil} t={t} span={s1[i1++]} />}
        {kalan && <KalanIsKart v={kalan} dil={dil} t={t} span={s1[i1++]} />}
        {ekip && <EkipKart v={ekip} dil={dil} t={t} span={s1[i1++]} onYaz={ekibeYaz} />}
        {onay && (
          <OnayKart
            v={onay}
            dil={dil}
            t={t}
            span={s2[i2++]}
            kartRef={onayRef}
            onKarar={karar}
            onIncele={(o) => git('invoices', o.tur === 'sozlesme' ? `[data-testid=sozlesmem-${o.id}]` : `[data-testid=teklifim-${o.id}]`)}
            onTumu={() => git('projects')}
          />
        )}
        {ortaSutun && (
          <div className="mgb-sutun" style={sutunStili(s2[i2++])}>
            {ozet.toplanti ? (
              <ToplantiKart v={ozet.toplanti} dil={dil} t={t} ayrinti={bolumler.includes('toplantilar') ? () => git('toplantilar') : undefined} />
            ) : (
              toplantiIste && <div className="mgb-toplanti-iste">{toplantiIste}</div>
            )}
            {ozet.bakiye && (
              <BakiyeKart
                v={ozet.bakiye}
                dil={dil}
                t={t}
                onYukle={() => git('invoices', '[data-testid=bakiyem]')}
                onHareketler={() => git('invoices', '[data-testid=bakiyem]')}
              />
            )}
          </div>
        )}
        {sagSutun && (
          <div className="mgb-sutun" style={sutunStili(s2[i2++])}>
            {ozet.hedef && <HedefKart v={ozet.hedef} dil={dil} t={t} />}
            {faturaDestek && (
              <FaturaDestekKart
                faturalar={faturalar}
                destek={destek}
                dil={dil}
                t={t}
                onOde={bakiyedenOde}
                onTalepAc={onTalepAc}
                onFaturalar={() => git('invoices')}
              />
            )}
          </div>
        )}
      </div>
    </section>
  );
}
