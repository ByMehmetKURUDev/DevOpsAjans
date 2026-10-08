import { useTranslation } from 'react-i18next';
import { CheckCircle2, CircleAlert, ImageOff } from 'lucide-react';

import type { AracSonucu } from '@/lib/seoAraclari';

/**
 * Araca özel ayrıntı görünümleri (Faz 4S). Hepsi `sonuc.veri`'yi DÜZ METİN
 * olarak çiziyor: hedef sitenin başlığı, açıklaması, robots.txt'si, JSON-LD'si
 * React metni olarak kaçışlanıyor — HTML olarak işlenen hiçbir şey yok.
 * Paylaşım görseli yalnız https ise `<img>` (CSP img-src https:), `no-referrer`.
 */

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Veri = Record<string, any>;

const KUTU = 'cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-5';
const PRE = 'max-h-96 overflow-auto whitespace-pre-wrap break-all rounded-xl border border-white/10 bg-black/40 p-4 text-xs leading-relaxed text-muted-foreground';

export function PuanHalkasi({ puan, etiket, boyut = 112 }: { puan: number; etiket?: string; boyut?: number }) {
  const r = 44;
  const cevre = 2 * Math.PI * r;
  const renk = puan >= 85 ? '#34d399' : puan >= 55 ? '#fbbf24' : '#f87171';
  return (
    <div className="relative shrink-0 self-center" style={{ width: boyut, height: boyut }} data-puan={puan}>
      <svg viewBox="0 0 100 100" width={boyut} height={boyut} aria-hidden="true" className="-rotate-90">
        <circle cx="50" cy="50" r={r} fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="8" />
        <circle
          cx="50"
          cy="50"
          r={r}
          fill="none"
          stroke={renk}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={cevre}
          strokeDashoffset={cevre * (1 - Math.max(0, Math.min(100, puan)) / 100)}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-bold">{puan}</span>
        {etiket && <span className="text-sm font-semibold text-muted-foreground">{etiket}</span>}
      </div>
    </div>
  );
}

function DurumRozeti({ kod }: { kod: number | null | undefined }) {
  const n = Number(kod || 0);
  const renk =
    n >= 200 && n < 300
      ? 'border-emerald-400/30 bg-emerald-500/10 text-emerald-300'
      : n >= 300 && n < 400
        ? 'border-amber-400/30 bg-amber-500/10 text-amber-300'
        : n >= 400
          ? 'border-red-500/30 bg-red-500/10 text-red-300'
          : 'border-white/15 bg-white/[0.04] text-muted-foreground';
  return <span className={`inline-block min-w-[3rem] rounded-md border px-1.5 py-0.5 text-center font-mono text-[11px] font-semibold ${renk}`}>{n || '—'}</span>;
}

function Satir({ ad, children }: { ad: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 border-b border-white/5 py-2 text-sm last:border-0 sm:grid-cols-[11rem_1fr]">
      <dt className="text-muted-foreground">{ad}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  );
}

function bos(deger: unknown): string {
  return deger === null || deger === undefined || deger === '' ? '—' : String(deger);
}

// --------------------------------------------------------------------------
function MetaAyrinti({ v, sonuc }: { v: Veri; sonuc: AracSonucu }) {
  const { t } = useTranslation();
  const k = 'seoAracSonuc.veri.meta';
  let kirinti = sonuc.son_url;
  try {
    const u = new URL(sonuc.son_url);
    kirinti = `${u.hostname}${u.pathname === '/' ? '' : u.pathname.replace(/\//g, ' › ')}`;
  } catch {
    /* adres değilse olduğu gibi */
  }
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className={KUTU} data-serp>
        <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t(`${k}.serp`)}</p>
        <div className="rounded-xl bg-white p-4 text-left" dir="ltr">
          <p className="truncate text-xs text-[#202124]">{kirinti}</p>
          <p className="mt-1 line-clamp-1 text-lg leading-snug text-[#1a0dab]">{v.baslik || sonuc.son_url}</p>
          <p className="mt-1 line-clamp-2 text-sm leading-snug text-[#4d5156]">{v.aciklama || '—'}</p>
        </div>
      </div>
      <dl className={KUTU}>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t(`${k}.etiketler`)}</p>
        <Satir ad={t(`${k}.baslik`)}>
          {bos(v.baslik)} <span className="text-xs text-muted-foreground">({t(`${k}.karakter`, { sayi: v.baslik_karakter ?? 0 })})</span>
        </Satir>
        <Satir ad={t(`${k}.aciklama`)}>
          {bos(v.aciklama)} <span className="text-xs text-muted-foreground">({t(`${k}.karakter`, { sayi: v.aciklama_karakter ?? 0 })})</span>
        </Satir>
        <Satir ad={t(`${k}.canonical`)}>
          <span dir="ltr" className="break-all">{(v.canonical ?? []).join(', ') || '—'}</span>
        </Satir>
        <Satir ad={t(`${k}.robots`)}>{[v.robots, v.x_robots && `X-Robots-Tag: ${v.x_robots}`].filter(Boolean).join(' · ') || '—'}</Satir>
        <Satir ad={t(`${k}.viewport`)}>{bos(v.viewport)}</Satir>
        <Satir ad={t(`${k}.lang`)}>{bos(v.lang)}</Satir>
      </dl>
      {(v.hreflang ?? []).length > 0 && (
        <div className={`${KUTU} lg:col-span-2`}>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t(`${k}.hreflang`)}</p>
          <ul className="space-y-1 text-sm" dir="ltr">
            {(v.hreflang as { dil: string; adres: string }[]).map((h, i) => (
              <li key={i} className="flex gap-3">
                <code className="w-16 shrink-0 text-purple-300">{h.dil}</code>
                <span className="min-w-0 break-all text-muted-foreground">{h.adres}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------
function OgAyrinti({ v }: { v: Veri }) {
  const { t } = useTranslation();
  const k = 'seoAracSonuc.veri.og';
  const on = v.onizleme ?? {};
  const g = v.gorsel ?? null;
  const tablo = (baslik: string, nesne: Record<string, string> | undefined) => (
    <dl className={KUTU}>
      <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{baslik}</p>
      {Object.entries(nesne ?? {}).length === 0 ? (
        <p className="text-sm text-muted-foreground">—</p>
      ) : (
        Object.entries(nesne ?? {}).map(([ad, deger]) => (
          <Satir key={ad} ad={ad}>
            <span dir="auto">{deger}</span>
          </Satir>
        ))
      )}
    </dl>
  );
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className={KUTU} data-og-onizleme>
        <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t(`${k}.onizleme`)}</p>
        <div className="overflow-hidden rounded-xl border border-white/10 bg-black/40">
          {on.gorsel ? (
            <img src={on.gorsel} alt="" referrerPolicy="no-referrer" loading="lazy" className="aspect-[1.91/1] w-full object-cover" />
          ) : (
            <div className="flex aspect-[1.91/1] w-full flex-col items-center justify-center gap-2 px-6 text-center text-xs text-muted-foreground" data-og-gorsel-yok>
              <ImageOff className="h-6 w-6" aria-hidden="true" />
              {g ? t(`${k}.gorselGizli`) : t(`${k}.gorselYok`)}
            </div>
          )}
          <div className="space-y-1 border-t border-white/10 p-4" dir="auto">
            <p className="truncate text-[11px] uppercase tracking-wider text-muted-foreground">{on.alan || '—'}</p>
            <p className="line-clamp-2 font-semibold">{on.baslik || '—'}</p>
            <p className="line-clamp-2 text-sm text-muted-foreground">{on.aciklama || '—'}</p>
          </div>
        </div>
      </div>
      <div className="space-y-4">
        {g && (
          <dl className={KUTU} data-og-gorsel>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t(`${k}.gorsel`)}</p>
            <Satir ad="URL">
              <span dir="ltr" className="break-all">{g.url}</span>
            </Satir>
            <Satir ad="HTTP">{g.hata ? g.hata : <DurumRozeti kod={g.durum} />}</Satir>
            <Satir ad={t(`${k}.tur`)}>{bos(g.tur)}</Satir>
            <Satir ad={t(`${k}.boyut`)}>{g.genislik && g.yukseklik ? `${g.genislik}×${g.yukseklik}` : '—'}</Satir>
            <Satir ad={t(`${k}.dosya`)}>{g.boyut_bayt ? t(`${k}.kb`, { sayi: Math.round(g.boyut_bayt / 1024) }) : '—'}</Satir>
          </dl>
        )}
        {tablo(t(`${k}.ogEtiketleri`), v.og)}
        {tablo(t(`${k}.twitterEtiketleri`), v.twitter)}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------
function SchemaAyrinti({ v }: { v: Veri }) {
  const { t } = useTranslation();
  const k = 'seoAracSonuc.veri.schema';
  const ogeler = (v.ogeler ?? []) as { tur: string; ad: string; ic_ice: boolean; bilinen: boolean; eksik_zorunlu: string[]; eksik_onerilen: string[]; alanlar: string[] }[];
  const bloklar = (v.bloklar ?? []) as { sira: number; gecerli: boolean; hata?: { satir: number; sutun: number; mesaj: string }; turler?: string[]; metin: string }[];
  return (
    <div className="space-y-4">
      {ogeler.length > 0 && (
        <div className={KUTU}>
          <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t(`${k}.ogeler`)}</p>
          <ul className="space-y-3">
            {ogeler.map((o, i) => (
              <li key={i} className={`rounded-xl border border-white/10 p-3 ${o.ic_ice ? 'ms-4' : ''}`} data-schema-oge={o.tur}>
                <p className="flex flex-wrap items-center gap-2 text-sm font-semibold">
                  {o.eksik_zorunlu.length ? (
                    <CircleAlert className="h-4 w-4 text-red-300" aria-hidden="true" />
                  ) : (
                    <CheckCircle2 className="h-4 w-4 text-emerald-300" aria-hidden="true" />
                  )}
                  <code className="text-purple-300">{o.tur}</code>
                  {o.ad && <span className="min-w-0 truncate font-normal text-muted-foreground" dir="auto">{o.ad}</span>}
                  {o.ic_ice && <span className="rounded border border-white/10 px-1.5 text-[10px] text-muted-foreground">{t(`${k}.icIce`)}</span>}
                  {!o.bilinen && <span className="text-[11px] font-normal text-muted-foreground">({t(`${k}.kuralYok`)})</span>}
                </p>
                {o.eksik_zorunlu.length > 0 && (
                  <p className="mt-1 text-xs text-red-300">
                    {t(`${k}.eksikZorunlu`)}: <span dir="ltr">{o.eksik_zorunlu.join(', ')}</span>
                  </p>
                )}
                {o.eksik_onerilen.length > 0 && (
                  <p className="mt-1 text-xs text-amber-300">
                    {t(`${k}.eksikOnerilen`)}: <span dir="ltr">{o.eksik_onerilen.join(', ')}</span>
                  </p>
                )}
                {o.bilinen && !o.eksik_zorunlu.length && !o.eksik_onerilen.length && <p className="mt-1 text-xs text-emerald-300">{t(`${k}.tamam`)}</p>}
                {o.alanlar.length > 0 && (
                  <p className="mt-1 break-words text-[11px] text-muted-foreground" dir="ltr">
                    {o.alanlar.join(' · ')}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      {bloklar.length > 0 && (
        <div className={KUTU}>
          <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t(`${k}.bloklar`)}</p>
          <div className="space-y-3">
            {bloklar.map((b) => (
              <details key={b.sira} className="rounded-xl border border-white/10 p-3" data-schema-blok={b.sira}>
                <summary className="cursor-pointer text-sm">
                  <span className="font-semibold">{t(`${k}.blok`, { sayi: b.sira })}</span>{' '}
                  {b.gecerli ? (
                    <span className="text-emerald-300">· {t(`${k}.gecerli`)}{b.turler?.length ? ` · ${b.turler.join(', ')}` : ''}</span>
                  ) : (
                    <span className="text-red-300">· {t(`${k}.hatali`, { satir: b.hata?.satir, sutun: b.hata?.sutun })}</span>
                  )}
                  <span className="ms-2 text-xs text-purple-300">{t(`${k}.kod`)}</span>
                </summary>
                <pre className={`${PRE} mt-3`} dir="ltr">
                  {b.metin}
                </pre>
              </details>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------
function RobotsAyrinti({ v }: { v: Veri }) {
  const { t } = useTranslation();
  const k = 'seoAracSonuc.veri.robots';
  const sonuc = v.sonuc ?? {};
  const belirsiz = !v.durum || v.durum >= 500;
  const izinli = Boolean(sonuc.izinli) && !belirsiz;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className={`${KUTU} ${belirsiz ? '' : izinli ? 'border-emerald-400/30' : 'border-red-500/30'}`} data-robots-karar={belirsiz ? 'belirsiz' : izinli ? 'izinli' : 'engelli'}>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t(`${k}.karar`)}</p>
        <p className={`text-2xl font-bold ${belirsiz ? 'text-amber-300' : izinli ? 'text-emerald-300' : 'text-red-300'}`}>
          {t(`${k}.${belirsiz ? 'belirsiz' : izinli ? 'izinli' : 'engelli'}`)}
        </p>
        <dl className="mt-3">
          <Satir ad={t(`${k}.yol`)}>
            <code dir="ltr" className="break-all">{v.yol}</code>
          </Satir>
          <Satir ad={t(`${k}.ajan`)}>
            <code dir="ltr">{v.ajan}</code>
          </Satir>
          <Satir ad={t(`${k}.kural`)}>
            {sonuc.kural ? (
              <code dir="ltr" className="break-all">
                {sonuc.kural.alan === 'allow' ? 'Allow' : 'Disallow'}: {sonuc.kural.deger} ({t(`${k}.satir`, { sayi: sonuc.kural.satir })})
              </code>
            ) : (
              <span className="text-muted-foreground">{t(`${k}.kuralYok`)}</span>
            )}
          </Satir>
          <Satir ad={t(`${k}.grup`)}>
            <code dir="ltr">{(sonuc.grup_ajanlari ?? []).join(', ') || '—'}</code>
          </Satir>
        </dl>
      </div>
      <div className="space-y-4">
        {(v.gruplar ?? []).length > 0 && (
          <div className={KUTU}>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t(`${k}.gruplar`)}</p>
            <ul className="space-y-1 text-sm" dir="ltr">
              {(v.gruplar as { ajanlar: string[]; kural_sayisi: number; satir: number }[]).map((g, i) => (
                <li key={i} className="flex flex-wrap justify-between gap-2">
                  <code className="min-w-0 break-all text-purple-300">{g.ajanlar.join(', ')}</code>
                  <span className="text-xs text-muted-foreground">
                    {t(`${k}.kuralSayisi`, { sayi: g.kural_sayisi })} · {t(`${k}.satir`, { sayi: g.satir })}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {(v.sitemapler ?? []).length > 0 && (
          <div className={KUTU}>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t(`${k}.sitemapler`)}</p>
            <ul className="space-y-1 text-sm" dir="ltr">
              {(v.sitemapler as string[]).map((s) => (
                <li key={s} className="break-all text-muted-foreground">{s}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
      {v.metin && (
        <div className={`${KUTU} lg:col-span-2`}>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t(`${k}.icerik`)}</p>
          <pre className={PRE} dir="ltr" data-robots-metni>
            {v.metin}
          </pre>
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------
function SitemapAyrinti({ v }: { v: Veri }) {
  const { t } = useTranslation();
  const k = 'seoAracSonuc.veri.sitemap';
  const kutucuk = (ad: string, deger: React.ReactNode) => (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-3">
      <p className="text-[11px] uppercase tracking-wider text-muted-foreground">{ad}</p>
      <p className="mt-1 text-lg font-semibold">{deger}</p>
    </div>
  );
  const liste = (baslik: string, ogeler: string[] | undefined) =>
    ogeler && ogeler.length > 0 ? (
      <div className={KUTU}>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{baslik}</p>
        <ul className="space-y-1 text-xs text-muted-foreground" dir="ltr">
          {ogeler.map((o, i) => (
            <li key={i} className="break-all">{o}</li>
          ))}
        </ul>
      </div>
    ) : null;
  return (
    <div className="space-y-4">
      <div className={KUTU}>
        <dl>
          <Satir ad={t(`${k}.adres`)}>
            <span dir="ltr" className="break-all">{v.sitemap_url}</span>
          </Satir>
          {v.kaynak && <Satir ad={t(`${k}.kaynak`)}>{t(`${k}.kaynaklar.${v.kaynak}`, { defaultValue: v.kaynak })}</Satir>}
          {v.tur && <Satir ad={t(`${k}.tur`)}>{t(`${k}.turler.${v.tur}`, { defaultValue: v.tur })}</Satir>}
        </dl>
        {v.tur && (
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
            {kutucuk(t(`${k}.adresSayisi`), v.alt_adres_sayisi ?? v.adres_sayisi ?? 0)}
            {kutucuk(t(`${k}.lastmodOrani`), `%${v.lastmod_orani ?? 0}`)}
            {kutucuk(t(`${k}.boyut`), v.boyut_bayt ? `${Math.max(1, Math.round(v.boyut_bayt / 1024))} KB${v.sikistirilmis ? ' · gzip' : ''}` : '—')}
          </div>
        )}
      </div>
      {(v.ornekler ?? []).length > 0 && (
        <div className={KUTU} data-sitemap-orneklem>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t(`${k}.ornekler`)}</p>
          <ul className="space-y-1.5 text-xs" dir="ltr">
            {(v.ornekler as { url: string; durum: number; hata?: string | null }[]).map((o, i) => (
              <li key={i} className="flex items-start gap-2">
                <DurumRozeti kod={o.durum} />
                <span className="min-w-0 break-all text-muted-foreground">
                  {o.url}
                  {o.hata === 'adres_yasak' ? ` (${t(`${k}.reddedildi`)})` : ''}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {liste(t(`${k}.hataliAdresler`), v.hatali_adresler)}
      {liste(t(`${k}.baskaSite`), v.baska_site_adresleri)}
      {liste(t(`${k}.altlar`), v.alt_sitemapler)}
      {v.incelenen_alt && (
        <p className="text-xs text-muted-foreground">
          {t(`${k}.incelenenAlt`)}: <span dir="ltr" className="break-all">{v.incelenen_alt}</span>
        </p>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------
function YonlendirmeAyrinti({ v }: { v: Veri }) {
  const { t } = useTranslation();
  const k = 'seoAracSonuc.veri.yonlendirme';
  const zincirler = (v.zincirler ?? []) as {
    etiket: string;
    baslangic: string;
    adimlar: { url: string; durum: number }[];
    son_url: string;
    son_durum: number;
    hata: string | null;
  }[];
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {zincirler.map((z) => (
        <div key={z.etiket} className={KUTU} data-zincir={z.etiket}>
          <p className="mb-3 flex flex-wrap items-center justify-between gap-2 text-sm font-semibold">
            <span>{t(`${k}.etiket.${z.etiket}`, { defaultValue: z.etiket })}</span>
            <span className="text-xs font-normal text-muted-foreground">{t(`${k}.adim`, { sayi: Math.max(0, z.adimlar.length - 1) })}</span>
          </p>
          <ol className="space-y-1.5 text-xs" dir="ltr">
            {z.adimlar.map((a, i) => (
              <li key={i} className="flex items-start gap-2">
                <DurumRozeti kod={a.durum} />
                <span className="min-w-0 break-all text-muted-foreground">{a.url}</span>
              </li>
            ))}
            {z.hata && (
              <li className="flex items-start gap-2 text-red-300">
                <CircleAlert className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span className="min-w-0 break-all" dir="auto">
                  {t(`${k}.erisilemedi`, { kod: z.hata })} — {z.son_url}
                </span>
              </li>
            )}
          </ol>
        </div>
      ))}
    </div>
  );
}

// --------------------------------------------------------------------------
function GuvenlikAyrinti({ v }: { v: Veri }) {
  const { t } = useTranslation();
  const k = 'seoAracSonuc.veri.guvenlik';
  const satirlar = (v.basliklar ?? []) as { ad: string; deger: string; durum: string }[];
  const renk: Record<string, string> = { iyi: 'text-emerald-300', uyari: 'text-amber-300', hata: 'text-red-300', yok: 'text-red-300', bilgi: 'text-sky-300' };
  return (
    <div className={KUTU}>
      <div className="mb-4 flex flex-wrap items-center gap-4">
        <PuanHalkasi puan={v.puan ?? 0} etiket={v.harf} boyut={96} />
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t(`${k}.puan`)}</p>
          <p className="text-3xl font-bold" data-guvenlik-notu={v.harf}>
            {v.puan ?? 0}/100 · {v.harf}
          </p>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-muted-foreground">
            <tr className="border-b border-white/10">
              <th className="py-2 pe-3 font-medium">{t(`${k}.baslik`)}</th>
              <th className="py-2 pe-3 font-medium">{t(`${k}.deger`)}</th>
              <th className="py-2 font-medium">{t(`${k}.durum`)}</th>
            </tr>
          </thead>
          <tbody>
            {satirlar.map((s) => (
              <tr key={s.ad} className="border-b border-white/5 align-top">
                <td className="py-2 pe-3 font-mono" dir="ltr">{s.ad}</td>
                <td className="max-w-[28rem] break-all py-2 pe-3 font-mono text-muted-foreground" dir="ltr">
                  {s.deger || '—'}
                </td>
                <td className={`whitespace-nowrap py-2 font-semibold ${renk[s.durum] ?? ''}`}>
                  {s.durum === 'yok' ? t(`${k}.eksik`) : t(`seoAracSonuc.seviye.${s.durum}`, { defaultValue: s.durum })}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------
function SslAyrinti({ v }: { v: Veri }) {
  const { t, i18n } = useTranslation();
  const k = 'seoAracSonuc.veri.ssl';
  const s = v.sertifika ?? null;
  const tarih = (d?: string) => {
    if (!d) return '—';
    const an = new Date(d);
    return Number.isNaN(an.getTime()) ? d : an.toLocaleDateString(i18n.language, { year: 'numeric', month: 'long', day: 'numeric' });
  };
  const ad = (o?: { cn?: string; o?: string }) => [o?.cn, o?.o].filter(Boolean).join(' · ') || '—';
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <dl className={KUTU}>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t(`${k}.sertifika`)}</p>
        <Satir ad={t(`${k}.konu`)}>{ad(s?.konu)}</Satir>
        <Satir ad={t(`${k}.yayinci`)}>{ad(s?.yayinci)}</Satir>
        <Satir ad={t(`${k}.baslangic`)}>{tarih(s?.baslangic)}</Satir>
        <Satir ad={t(`${k}.bitis`)}>{tarih(s?.bitis)}</Satir>
        <Satir ad={t(`${k}.kalan`)}>{v.kalan_gun ?? '—'}</Satir>
        <Satir ad={t(`${k}.anahtar`)}>{bos(s?.anahtar)}</Satir>
        <Satir ad={t(`${k}.imza`)}>{bos(s?.imza)}</Satir>
        <Satir ad={t(`${k}.seri`)}>
          <span className="break-all font-mono text-xs">{bos(s?.seri)}</span>
        </Satir>
      </dl>
      <div className="space-y-4">
        <dl className={KUTU}>
          <Satir ad={t(`${k}.tls`)}>{bos(v.tls_surumu)}</Satir>
          <Satir ad={t(`${k}.sifre`)}>
            <span className="break-all font-mono text-xs">{bos(v.sifre)}</span>
          </Satir>
          <Satir ad={t(`${k}.dogrulandi`)}>
            <span className={v.dogrulandi ? 'text-emerald-300' : 'text-red-300'}>{t(`${k}.${v.dogrulandi ? 'dogrulandi' : 'dogrulanmadi'}`)}</span>
          </Satir>
          {s?.aia && (
            <Satir ad={t(`${k}.aia`)}>
              <span dir="ltr" className="break-all text-xs">{s.aia}</span>
            </Satir>
          )}
        </dl>
        {(s?.san ?? []).length > 0 && (
          <div className={KUTU}>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t(`${k}.san`)}</p>
            <p className="break-words font-mono text-xs text-muted-foreground" dir="ltr">
              {(s.san as string[]).join(', ')}
            </p>
          </div>
        )}
        {(v.zincir ?? []).length > 0 && (
          <div className={KUTU}>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t(`${k}.zincir`)}</p>
            <ol className="space-y-1 text-xs text-muted-foreground">
              {(v.zincir as { konu: { cn?: string; o?: string }; yayinci: { cn?: string; o?: string }; bitis: string }[]).map((z, i) => (
                <li key={i} style={{ paddingInlineStart: `${i * 12}px` }}>
                  {ad(z.konu)} ← {ad(z.yayinci)} · {tarih(z.bitis)}
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------
function BaslikAyrinti({ v }: { v: Veri }) {
  const { t } = useTranslation();
  const k = 'seoAracSonuc.veri.basliklar';
  const basliklar = (v.basliklar ?? []) as { seviye: number; metin: string }[];
  const sayilar = (v.seviye_sayilari ?? {}) as Record<string, number>;
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className={`${KUTU} lg:col-span-2`} data-baslik-agaci>
        <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t(`${k}.agac`)}</p>
        {basliklar.length === 0 ? (
          <p className="text-sm text-muted-foreground">—</p>
        ) : (
          <ul className="max-h-[28rem] space-y-1 overflow-auto text-sm">
            {basliklar.map((b, i) => (
              <li key={i} className="flex items-start gap-2" style={{ paddingInlineStart: `${(b.seviye - 1) * 14}px` }}>
                <code className={`shrink-0 rounded px-1 text-[10px] font-semibold ${b.seviye === 1 ? 'bg-purple-500/25 text-purple-200' : 'bg-white/10 text-muted-foreground'}`}>
                  H{b.seviye}
                </code>
                <span className={`min-w-0 break-words ${b.metin ? '' : 'italic text-red-300'}`} dir="auto">
                  {b.metin || t(`${k}.bos`)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className={KUTU} data-seviye-sayilari>
        <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t(`${k}.seviyeler`)}</p>
        <div className="grid grid-cols-3 gap-2 text-center">
          {[1, 2, 3, 4, 5, 6].map((sv) => (
            <div key={sv} className="rounded-xl border border-white/10 bg-white/[0.02] p-2">
              <p className="text-lg font-semibold">{sayilar[`h${sv}`] ?? 0}</p>
              <p className="text-[11px] text-muted-foreground">H{sv}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------
type KelimeSatiri = { kelime: string; sayi: number; yuzde: number };

function KelimeAyrinti({ v }: { v: Veri }) {
  const { t } = useTranslation();
  const k = 'seoAracSonuc.veri.kelime';
  const enSik = (v.en_sik ?? []) as KelimeSatiri[];
  const ikililer = (v.ikililer ?? []) as KelimeSatiri[];
  const ucluler = (v.ucluler ?? []) as KelimeSatiri[];
  const hedef = v.hedef as { kelime: string; sayi: number; yuzde: number; title: boolean; h1: boolean; aciklama: boolean; url: boolean } | null;
  const tablo = (baslik: string, satirlar: KelimeSatiri[], ad: string) => {
    const enBuyuk = satirlar[0]?.sayi || 1;
    return (
      <div className={KUTU} data-kelime-tablosu={ad}>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{baslik}</p>
        <table className="w-full text-start text-xs">
          <thead className="text-muted-foreground">
            <tr className="border-b border-white/10">
              <th className="py-1.5 pe-3 text-start font-medium">{t(`${k}.kelime`)}</th>
              <th className="py-1.5 pe-3 text-start font-medium">{t(`${k}.adet`)}</th>
              <th className="py-1.5 text-start font-medium">{t(`${k}.yuzde`)}</th>
            </tr>
          </thead>
          <tbody>
            {satirlar.map((s) => (
              <tr key={s.kelime} className="border-b border-white/5" data-kelime={s.kelime}>
                <td className="py-1.5 pe-3" dir="auto">
                  <span className="relative block">
                    <span
                      className="absolute inset-y-0 start-0 rounded bg-purple-500/15"
                      style={{ width: `${Math.round((s.sayi / enBuyuk) * 100)}%` }}
                      aria-hidden="true"
                    />
                    <span className="relative break-words ps-1">{s.kelime}</span>
                  </span>
                </td>
                <td className="py-1.5 pe-3">{s.sayi}</td>
                <td className="py-1.5">%{s.yuzde}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };
  const konumlar: [string, boolean][] = hedef
    ? [
        ['konumTitle', hedef.title],
        ['konumH1', hedef.h1],
        ['konumAciklama', hedef.aciklama],
        ['konumUrl', hedef.url],
      ]
    : [];
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="space-y-4">
        {hedef && (
          <div className={`${KUTU} border-purple-500/30`} data-hedef-kelime>
            <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t(`${k}.hedef`)}</p>
            <p className="break-words text-lg font-semibold" dir="auto">
              {hedef.kelime}
            </p>
            <p className="text-sm text-muted-foreground">{t(`${k}.hedefOzet`, { sayi: hedef.sayi, yuzde: hedef.yuzde })}</p>
            <ul className="mt-3 grid grid-cols-2 gap-2 text-sm">
              {konumlar.map(([ad, var_]) => (
                <li key={ad} className="flex items-center gap-1.5" data-hedef-konum={ad} data-var={var_ ? '1' : '0'}>
                  {var_ ? (
                    <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-300" aria-hidden="true" />
                  ) : (
                    <CircleAlert className="h-4 w-4 shrink-0 text-amber-300" aria-hidden="true" />
                  )}
                  <span className="min-w-0">
                    {t(`${k}.${ad}`)}: {t(`${k}.${var_ ? 'var' : 'yok'}`)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
        <div className={KUTU}>
          <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t(`${k}.kelimeler`)}</p>
          <div className="grid grid-cols-3 gap-3 text-center">
            {(['toplam_kelime', 'anlamli_kelime', 'benzersiz'] as const).map((alan, i) => (
              <div key={alan} className="rounded-xl border border-white/10 bg-white/[0.02] p-3">
                <p className="text-lg font-semibold">{v[alan] ?? 0}</p>
                <p className="text-[11px] text-muted-foreground">{t(`${k}.${['toplam', 'anlamli', 'benzersiz'][i]}`)}</p>
              </div>
            ))}
          </div>
          <p className="mt-3 text-[11px] text-muted-foreground">
            {t(`${k}.dil`)}: {v.dil || '—'} · {t(`${k}.durakNotu`)}
          </p>
        </div>
        {ucluler.length > 0 && tablo(t(`${k}.ucluler`), ucluler, 'uclu')}
      </div>
      <div className="space-y-4">
        {enSik.length > 0 && tablo(t(`${k}.enSik`), enSik, 'tekli')}
        {ikililer.length > 0 && tablo(t(`${k}.ikililer`), ikililer, 'ikili')}
      </div>
    </div>
  );
}

export function AracAyrintisi({ sonuc, anahtar }: { sonuc: AracSonucu; anahtar: string }) {
  const v = sonuc.veri ?? {};
  switch (anahtar) {
    case 'meta':
      return <MetaAyrinti v={v} sonuc={sonuc} />;
    case 'og':
      return <OgAyrinti v={v} />;
    case 'schema':
      return <SchemaAyrinti v={v} />;
    case 'robots':
      return <RobotsAyrinti v={v} />;
    case 'sitemap':
      return <SitemapAyrinti v={v} />;
    case 'yonlendirme':
      return <YonlendirmeAyrinti v={v} />;
    case 'guvenlik':
      return <GuvenlikAyrinti v={v} />;
    case 'ssl':
      return <SslAyrinti v={v} />;
    case 'basliklar':
      return <BaslikAyrinti v={v} />;
    case 'kelime':
      return <KelimeAyrinti v={v} />;
    default:
      return null;
  }
}
