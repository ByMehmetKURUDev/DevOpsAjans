import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, Copy, ExternalLink, MapPin, Phone, Video } from 'lucide-react';
import { toast } from 'sonner';

import { ciftZaman, type Durum, type Yanit, type YerTuru } from '@/lib/toplantilar';

/** Faz 6T — toplantı ekranlarının (yönetici + müşteri) ortak küçük parçaları; mevcut sınıf dili (`cam-kart`). */

export const KART = 'cam-kart rounded-2xl border border-white/10 bg-white/[0.03]';
export const GIRDI =
  'h-10 w-full min-w-0 rounded-md border border-white/10 bg-black/40 px-3 text-sm text-white placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400';
export const SECIM =
  'h-10 w-full min-w-0 rounded-md border border-white/10 bg-black/40 px-2 text-sm text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400';
export const METIN =
  'min-h-[96px] w-full min-w-0 rounded-md border border-white/10 bg-black/40 px-3 py-2 text-sm text-white placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400';
export const DUGME_IKINCIL =
  'inline-flex min-h-[36px] items-center gap-1.5 rounded-lg border border-white/15 px-3 py-1.5 text-sm text-white/90 transition-colors hover:border-purple-400/60 hover:bg-white/[0.05] disabled:opacity-50';
export const DUGME_ANA =
  'inline-flex min-h-[36px] items-center gap-1.5 rounded-lg bg-gradient-to-r from-purple-600 to-pink-600 px-3 py-1.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50';
export const DUGME_TEHLIKE =
  'inline-flex min-h-[36px] items-center gap-1.5 rounded-lg border border-red-400/40 px-3 py-1.5 text-sm text-red-200 transition-colors hover:bg-red-500/10 disabled:opacity-50';

const DURUM_RENGI: Record<string, string> = {
  planlandi: 'border-sky-400/30 bg-sky-500/10 text-sky-200',
  ertelendi: 'border-amber-400/30 bg-amber-500/10 text-amber-200',
  yapildi: 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200',
  iptal: 'border-white/15 bg-white/5 text-muted-foreground',
  katilacak: 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200',
  katilamayacak: 'border-red-400/30 bg-red-500/10 text-red-200',
  belki: 'border-amber-400/30 bg-amber-500/10 text-amber-200',
  bekliyor: 'border-white/15 bg-white/5 text-muted-foreground',
  uyari: 'border-amber-400/30 bg-amber-500/10 text-amber-200',
  bilgi: 'border-purple-400/30 bg-purple-500/10 text-purple-200',
};

export function Rozet({ tur, children }: { tur: string; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] ${DURUM_RENGI[tur] ?? DURUM_RENGI.bekliyor}`}
      data-rozet={tur}
    >
      {children}
    </span>
  );
}

export function DurumRozeti({ durum }: { durum: Durum }) {
  const { t } = useTranslation();
  return <Rozet tur={durum}>{t(`toplantilar.durum.${durum}`)}</Rozet>;
}

export function YanitRozeti({ yanit }: { yanit: Yanit }) {
  const { t } = useTranslation();
  return <Rozet tur={yanit}>{t(`toplantilar.yanit.${yanit}`)}</Rozet>;
}

export function Alan({ etiket, ipucu, children, className }: { etiket: string; ipucu?: string; children: ReactNode; className?: string }) {
  return (
    <label className={`block min-w-0 text-sm ${className ?? ''}`}>
      <span className="mb-1 block font-medium text-white/90">{etiket}</span>
      {children}
      {ipucu && <span className="mt-1 block text-xs text-muted-foreground">{ipucu}</span>}
    </label>
  );
}

export function AltDugme({ secili, onClick, children, anahtar }: { secili: boolean; onClick: () => void; children: ReactNode; anahtar: string }) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={secili}
      onClick={onClick}
      className={`flex min-h-[40px] flex-none items-center gap-1.5 rounded-lg px-3 py-2 text-sm transition-colors ${
        secili ? 'bg-purple-500/20 text-white' : 'text-muted-foreground hover:bg-white/[0.05] hover:text-white'
      }`}
      data-toplanti-alt={anahtar}
    >
      {children}
    </button>
  );
}

/** İstanbul saati; tarayıcı farklı saat dilimindeyse yerel saat de. */
export function Zaman({ iso, className }: { iso: string | null | undefined; className?: string }) {
  const { t, i18n } = useTranslation();
  return (
    <span className={className} data-zaman>
      {ciftZaman(iso, i18n.language, { istanbul: t('toplantilar.zaman.istanbul'), yerel: t('toplantilar.zaman.yerel') })}
    </span>
  );
}

const YER_IKONU: Record<YerTuru, typeof Video> = { cevrimici: Video, yuz_yuze: MapPin, telefon: Phone };

/** Yer bilgisi: çevrim içi bağlantı YALNIZ metin bağlantı (yeni sekme, noopener) — iframe/betik yok. */
export function Yer({ yer_turu, baglanti, adres, telefon, katil }: {
  yer_turu: YerTuru;
  baglanti: string | null;
  adres: string | null;
  telefon: string | null;
  katil?: boolean;
}) {
  const { t } = useTranslation();
  const Ikon = YER_IKONU[yer_turu] ?? Video;
  let icerik: ReactNode = t(`toplantilar.yer.${yer_turu}`);
  if (yer_turu === 'cevrimici' && baglanti) {
    icerik = (
      <a href={baglanti} target="_blank" rel="noopener noreferrer" className="inline-flex min-w-0 items-center gap-1 break-all text-purple-200 underline-offset-2 hover:underline" data-katil-baglantisi>
        {katil ? t('toplantilar.musteri.katil') : baglanti}
        <ExternalLink className="h-3.5 w-3.5 flex-none" aria-hidden="true" />
      </a>
    );
  } else if (yer_turu === 'yuz_yuze' && adres) {
    icerik = <span className="break-words">{adres}</span>;
  } else if (yer_turu === 'telefon' && telefon) {
    icerik = (
      <a href={`tel:${telefon.replace(/[^\d+]/g, '')}`} className="text-purple-200 hover:underline" dir="ltr">
        {telefon}
      </a>
    );
  }
  return (
    <span className="inline-flex min-w-0 max-w-full items-start gap-1.5 text-sm">
      <Ikon className="mt-0.5 h-4 w-4 flex-none text-purple-300" aria-hidden="true" />
      <span className="min-w-0">{icerik}</span>
    </span>
  );
}

/** Bir kez gösterilen gizli adres + kopyala. */
export function AdresKutusu({ adres }: { adres: string }) {
  const { t } = useTranslation();
  const [kopyalandi, setKopyalandi] = useState(false);
  async function kopyala() {
    try {
      await navigator.clipboard.writeText(adres);
      setKopyalandi(true);
      toast.success(t('toplantilar.abonelik.kopyalandi'));
    } catch {
      toast.message(adres);
    }
  }
  return (
    <div className="mt-3 rounded-xl border border-emerald-400/30 bg-emerald-500/10 p-3" data-abonelik-adresi>
      <p className="mb-2 text-xs text-emerald-100">{t('toplantilar.abonelik.adresNotu')}</p>
      <div className="flex min-w-0 items-center gap-2">
        <code className="min-w-0 flex-1 select-all break-all rounded bg-black/40 px-2 py-1 text-xs text-white" dir="ltr">
          {adres}
        </code>
        <button type="button" onClick={kopyala} className={DUGME_IKINCIL} aria-label={t('toplantilar.abonelik.kopyala')}>
          {kopyalandi ? <Check className="h-4 w-4" aria-hidden="true" /> : <Copy className="h-4 w-4" aria-hidden="true" />}
          <span className="hidden sm:inline">{t('toplantilar.abonelik.kopyala')}</span>
        </button>
      </div>
    </div>
  );
}

/** Google / Apple / Outlook'a "adresle abone ol" tarifi. */
export function AbonelikTarifi() {
  const { t } = useTranslation();
  return (
    <details className="mt-3 rounded-xl border border-white/10 bg-black/20 p-3 text-sm" data-abonelik-tarifi>
      <summary className="cursor-pointer font-medium text-white/90">{t('toplantilar.abonelik.tarif.baslik')}</summary>
      <ul className="mt-2 space-y-2 text-muted-foreground">
        <li>
          <strong className="text-white/90">Google:</strong> {t('toplantilar.abonelik.tarif.google')}
        </li>
        <li>
          <strong className="text-white/90">Apple (iPhone, Mac):</strong> {t('toplantilar.abonelik.tarif.apple')}
        </li>
        <li>
          <strong className="text-white/90">Outlook:</strong> {t('toplantilar.abonelik.tarif.outlook')}
        </li>
      </ul>
      <p className="mt-2 text-xs text-muted-foreground">{t('toplantilar.abonelik.tarif.gizlilik')}</p>
    </details>
  );
}
