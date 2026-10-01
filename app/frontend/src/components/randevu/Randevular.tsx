import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CalendarDays, ChevronLeft, ChevronRight, List, Loader2, Mail, MapPin, Phone, Video, X } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { KART, METIN_ALANI, Rozet, Yukleniyor, zamanYaz } from '@/components/randevu/ortak';
import { hataMetni, type RandevuApi, type RandevuKaydi, type Sayfa } from '@/lib/randevu';
import { bugun, gunAdiYaz, haftaGunleri, isoGun, tzFarki } from '@/lib/randevuOrtak';

/** Faz 5R — randevular: yaklaşan / geçmiş / iptal listesi ve basit hafta görünümü. */

type Donem = 'yaklasan' | 'gecmis' | 'iptal';
type Gorunum = 'liste' | 'hafta';

/** Pazartesi (YYYY-AA-GG) + n gün. */
function gunEkle(gun: string, n: number): string {
  const [y, a, g] = gun.split('-').map(Number);
  const d = new Date(Date.UTC(y, a - 1, g + n, 12));
  return isoGun(d.getUTCFullYear(), d.getUTCMonth() + 1, d.getUTCDate());
}

function haftaBasi(gun: string): string {
  const [y, a, g] = gun.split('-').map(Number);
  const d = new Date(Date.UTC(y, a - 1, g, 12));
  return gunEkle(gun, -((d.getUTCDay() + 6) % 7));
}

/** Saat dilimindeki yerel gün başlangıcı → UTC ISO (yaklaşık; ±1 saat pay için bir gün genişletilir). */
function yerelGunUtc(gun: string): string {
  return `${gun}T00:00:00Z`;
}

function yerelGun(iso: string, tz: string): string {
  try {
    return new Intl.DateTimeFormat('en-CA', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(iso)).slice(0, 10);
  } catch {
    return iso.slice(0, 10);
  }
}

const KONUM_IKONU = { jitsi: Video, baglanti: Video, telefon: Phone, yuz_yuze: MapPin } as const;

export default function Randevular({ api, sayfa }: { api: RandevuApi; sayfa: Sayfa }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const tz = sayfa.saat_dilimi;
  const [gorunum, setGorunum] = useState<Gorunum>('liste');
  const [donem, setDonem] = useState<Donem>('yaklasan');
  const [hafta, setHafta] = useState(() => haftaBasi(bugun(tz)));
  const [kayitlar, setKayitlar] = useState<RandevuKaydi[] | null>(null);
  const [toplam, setToplam] = useState(0);
  const [saklama, setSaklama] = useState(sayfa.saklama_gun);
  const [secili, setSecili] = useState<RandevuKaydi | null>(null);
  const [neden, setNeden] = useState('');
  const [isleniyor, setIsleniyor] = useState(false);

  const yukle = useCallback(async () => {
    setKayitlar(null);
    try {
      const y =
        gorunum === 'hafta'
          ? await api.randevular(sayfa.id, { bas: yerelGunUtc(gunEkle(hafta, -1)), bit: yerelGunUtc(gunEkle(hafta, 8)) })
          : await api.randevular(sayfa.id, { donem });
      setKayitlar(y.items);
      setToplam(y.toplam);
      setSaklama(y.saklama_gun);
    } catch (e) {
      toast.error(hataMetni(t, e));
      setKayitlar([]);
    }
  }, [api, sayfa.id, gorunum, donem, hafta, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  // Ayrıntı penceresi Esc ile kapanır.
  useEffect(() => {
    if (!secili) return;
    const tus = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSecili(null);
    };
    window.addEventListener('keydown', tus);
    return () => window.removeEventListener('keydown', tus);
  }, [secili]);

  const gunler = useMemo(() => Array.from({ length: 7 }, (_, i) => gunEkle(hafta, i)), [hafta]);
  const gunAdlari = haftaGunleri(dil);
  const simdi = Date.now();

  const iptal = async () => {
    if (!secili) return;
    if (!window.confirm(t('randevu.liste2.iptalOnay'))) return;
    setIsleniyor(true);
    try {
      const r = await api.iptal(sayfa.id, secili.id, neden.trim());
      setSecili(r);
      setNeden('');
      toast.success(t('randevu.liste2.iptalEdildi'));
      void yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setIsleniyor(false);
    }
  };

  const katilim = async (k: RandevuKaydi['katilim']) => {
    if (!secili) return;
    setIsleniyor(true);
    try {
      const r = await api.katilim(sayfa.id, secili.id, k);
      setSecili(r);
      void yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setIsleniyor(false);
    }
  };

  const satir = (r: RandevuKaydi, kisa = false) => {
    const Ikon = (r.konum_turu && KONUM_IKONU[r.konum_turu]) || Video;
    return (
      <button
        type="button"
        onClick={() => {
          setSecili(r);
          setNeden('');
        }}
        className={`flex w-full items-start gap-3 rounded-xl border border-white/10 bg-black/20 text-start transition-colors hover:border-purple-400/40 ${kisa ? 'p-2' : 'p-3'} ${r.durum === 'iptal' ? 'opacity-60' : ''}`}
        data-randevu={r.uid}
        data-testid="randevu-kaydi"
      >
        <span className="mt-1 h-8 w-1.5 flex-none rounded-full" style={{ background: r.tur_renk }} aria-hidden="true" />
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-semibold tabular-nums">
            {kisa ? zamanYaz(r.baslangic, tz, dil, { timeStyle: 'short' }) : zamanYaz(r.baslangic, tz, dil, { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
          </span>
          <span className="block truncate text-sm">{r.anonim ? t('randevu.liste2.anonim') : r.ad}</span>
          {!kisa && (
            <span className="mt-1 flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
              <Rozet>
                <Ikon className="h-3 w-3" aria-hidden="true" />
                {r.tur_adi}
              </Rozet>
              <Rozet>{r.kisi_adi}</Rozet>
              {r.durum === 'iptal' && <Rozet renk="border-red-400/30 bg-red-500/10 text-red-200">{t('randevu.liste2.iptal')}</Rozet>}
              {r.katilim !== 'bilinmiyor' && (
                <Rozet renk={r.katilim === 'geldi' ? 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200' : 'border-amber-400/30 bg-amber-500/10 text-amber-200'}>
                  {t(`randevu.katilim.${r.katilim}`)}
                </Rozet>
              )}
              {r.onceki_baslangic && <Rozet>{t('randevu.liste2.yenidenPlanlandi')}</Rozet>}
            </span>
          )}
        </span>
      </button>
    );
  };

  return (
    <div className={`${KART} p-4 sm:p-6`} data-testid="randevu-randevular">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="flex rounded-lg border border-white/10 p-0.5" role="group" aria-label={t('randevu.liste2.gorunum')}>
          {(['liste', 'hafta'] as Gorunum[]).map((g) => (
            <button
              key={g}
              type="button"
              onClick={() => setGorunum(g)}
              aria-pressed={gorunum === g}
              className={`flex items-center gap-1 rounded-md px-2.5 py-1 text-sm ${gorunum === g ? 'bg-purple-500/25 text-white' : 'text-muted-foreground'}`}
              data-randevu-gorunum={g}
            >
              {g === 'liste' ? <List className="h-4 w-4" aria-hidden="true" /> : <CalendarDays className="h-4 w-4" aria-hidden="true" />}
              {t(`randevu.liste2.${g}`)}
            </button>
          ))}
        </div>
        {gorunum === 'liste' ? (
          <div className="flex gap-1">
            {(['yaklasan', 'gecmis', 'iptal'] as Donem[]).map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => setDonem(d)}
                aria-pressed={donem === d}
                className={`rounded-md px-2.5 py-1 text-sm ${donem === d ? 'bg-white/10 text-white' : 'text-muted-foreground hover:text-white'}`}
                data-randevu-donem={d}
              >
                {t(`randevu.liste2.${d}`)}
              </button>
            ))}
          </div>
        ) : (
          <div className="flex items-center gap-1">
            <Button size="icon" variant="ghost" className="h-8 w-8" aria-label={t('randevu.liste2.onceki')} onClick={() => setHafta((h) => gunEkle(h, -7))}>
              <ChevronLeft className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
            </Button>
            <span className="min-w-[10rem] text-center text-sm">
              {gunAdiYaz(hafta, dil, { day: 'numeric', month: 'short' })} – {gunAdiYaz(gunEkle(hafta, 6), dil, { day: 'numeric', month: 'short', year: 'numeric' })}
            </span>
            <Button size="icon" variant="ghost" className="h-8 w-8" aria-label={t('randevu.liste2.sonraki')} onClick={() => setHafta((h) => gunEkle(h, 7))}>
              <ChevronRight className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setHafta(haftaBasi(bugun(tz)))}>
              {t('randevu.liste2.buHafta')}
            </Button>
          </div>
        )}
        <span className="ms-auto text-xs text-muted-foreground">
          {t('randevu.liste2.saatDilimi', { tz: `${tz} (${tzFarki(tz, dil)})` })}
        </span>
      </div>

      {kayitlar === null ? (
        <Yukleniyor />
      ) : gorunum === 'liste' ? (
        kayitlar.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground" data-testid="randevu-liste-bos">
            {t(`randevu.liste2.bos.${donem}`)}
          </p>
        ) : (
          <>
            <ul className="grid gap-2 md:grid-cols-2">
              {kayitlar.map((r) => (
                <li key={r.id}>{satir(r)}</li>
              ))}
            </ul>
            {toplam > kayitlar.length && <p className="mt-2 text-xs text-muted-foreground">{t('randevu.liste2.dahaFazla', { sayi: toplam - kayitlar.length })}</p>}
          </>
        )
      ) : (
        <div className="grid gap-2 md:grid-cols-7" data-testid="randevu-hafta">
          {gunler.map((g, i) => {
            const gunun = kayitlar.filter((r) => yerelGun(r.baslangic, tz) === g);
            const bugunMu = g === bugun(tz);
            return (
              <div key={g} className={`min-h-[6rem] rounded-xl border p-2 ${bugunMu ? 'border-purple-400/50 bg-purple-500/10' : 'border-white/10 bg-black/20'}`}>
                <div className="mb-1 flex items-baseline justify-between text-xs">
                  <span className="font-semibold">{gunAdlari[i]}</span>
                  <span className="text-muted-foreground">{Number(g.slice(8))}</span>
                </div>
                <ul className="space-y-1">
                  {gunun.map((r) => (
                    <li key={r.id}>{satir(r, true)}</li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      )}
      <p className="mt-4 text-xs text-muted-foreground">{t('randevu.liste2.saklama', { gun: saklama })}</p>

      {secili && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 sm:items-center sm:p-4" role="dialog" aria-modal="true" aria-labelledby="randevu-ayrinti-baslik" onClick={() => setSecili(null)}>
          <div className="max-h-[92vh] w-full overflow-y-auto rounded-t-2xl border border-white/10 bg-zinc-950 p-5 sm:max-w-lg sm:rounded-2xl" onClick={(e) => e.stopPropagation()} data-testid="randevu-ayrinti">
            <div className="mb-3 flex items-start gap-2">
              <span className="mt-1 h-3 w-3 flex-none rounded-full" style={{ background: secili.tur_renk }} aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <h4 id="randevu-ayrinti-baslik" className="text-lg font-semibold">
                  {secili.tur_adi}
                </h4>
                <p className="text-sm text-muted-foreground">
                  {zamanYaz(secili.baslangic, tz, dil, { dateStyle: 'full', timeStyle: 'short' })} – {zamanYaz(secili.bitis, tz, dil, { timeStyle: 'short' })}
                </p>
                {secili.ziyaretci_tz && secili.ziyaretci_tz !== tz && (
                  <p className="text-xs text-muted-foreground">
                    {t('randevu.liste2.ziyaretciSaati', { saat: zamanYaz(secili.baslangic, secili.ziyaretci_tz, dil, { timeStyle: 'short' }), tz: secili.ziyaretci_tz })}
                  </p>
                )}
              </div>
              <Button size="icon" variant="ghost" className="h-8 w-8" aria-label={t('randevu.kapat')} onClick={() => setSecili(null)} data-testid="randevu-ayrinti-kapat">
                <X className="h-4 w-4" aria-hidden="true" />
              </Button>
            </div>
            <dl className="grid grid-cols-[7rem_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-sm">
              <dt className="text-muted-foreground">{t('randevu.liste2.kisi')}</dt>
              <dd>{secili.anonim ? t('randevu.liste2.anonim') : secili.ad}</dd>
              {secili.eposta && (
                <>
                  <dt className="text-muted-foreground">{t('randevu.liste2.eposta')}</dt>
                  <dd className="truncate" dir="ltr">
                    <a href={`mailto:${secili.eposta}`} className="inline-flex items-center gap-1 text-purple-200 hover:underline">
                      <Mail className="h-3.5 w-3.5" aria-hidden="true" />
                      {secili.eposta}
                    </a>
                  </dd>
                </>
              )}
              {secili.telefon && (
                <>
                  <dt className="text-muted-foreground">{t('randevu.liste2.telefon')}</dt>
                  <dd dir="ltr">
                    <a href={`tel:${secili.telefon}`} className="text-purple-200 hover:underline">
                      {secili.telefon}
                    </a>
                  </dd>
                </>
              )}
              <dt className="text-muted-foreground">{t('randevu.liste2.ekipten')}</dt>
              <dd>{secili.kisi_adi}</dd>
              {secili.konum && (
                <>
                  <dt className="text-muted-foreground">{t('randevu.liste2.konum')}</dt>
                  <dd className="break-words">
                    {/^https:\/\//.test(secili.konum) ? (
                      <a href={secili.konum} target="_blank" rel="noopener noreferrer" className="text-purple-200 hover:underline" dir="ltr">
                        {secili.konum}
                      </a>
                    ) : (
                      secili.konum
                    )}
                  </dd>
                </>
              )}
              {secili.yanitlar.map((y) => (
                <div key={y.id} className="contents">
                  <dt className="text-muted-foreground">{y.soru}</dt>
                  <dd className="whitespace-pre-wrap break-words">{y.yanit === true ? '✓' : String(y.yanit)}</dd>
                </div>
              ))}
              {secili.durum === 'iptal' && (
                <>
                  <dt className="text-muted-foreground">{t('randevu.liste2.durum')}</dt>
                  <dd>
                    {t(`randevu.liste2.iptalEden.${secili.iptal_eden || 'sahip'}`)}
                    {secili.iptal_nedeni ? ` — ${secili.iptal_nedeni}` : ''}
                  </dd>
                </>
              )}
            </dl>
            {secili.durum === 'onayli' && new Date(secili.baslangic).getTime() <= simdi && (
              <div className="mt-4">
                <p className="mb-2 text-sm font-medium">{t('randevu.liste2.katilimSoru')}</p>
                <div className="flex flex-wrap gap-2">
                  {(['geldi', 'gelmedi', 'bilinmiyor'] as const).map((k) => (
                    <Button key={k} size="sm" variant={secili.katilim === k ? 'default' : 'outline'} className={secili.katilim === k ? '' : '!bg-transparent border-white/20'} disabled={isleniyor} onClick={() => void katilim(k)} data-katilim={k}>
                      {t(`randevu.katilim.${k}`)}
                    </Button>
                  ))}
                </div>
              </div>
            )}
            {secili.durum === 'onayli' && new Date(secili.bitis).getTime() > simdi && (
              <div className="mt-4 rounded-xl border border-red-500/30 bg-red-500/5 p-3">
                <label className="block text-sm">
                  <span className="mb-1 block font-medium">{t('randevu.liste2.iptalNedeni')}</span>
                  <textarea className={METIN_ALANI} value={neden} onChange={(e) => setNeden(e.target.value)} maxLength={500} />
                </label>
                <p className="mt-1 text-xs text-muted-foreground">{t('randevu.liste2.iptalIpucu')}</p>
                <Button variant="outline" className="mt-2 gap-1.5 border-red-400/40 !bg-transparent text-red-200" disabled={isleniyor} onClick={() => void iptal()} data-testid="randevu-sahip-iptal">
                  {isleniyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
                  {t('randevu.liste2.iptalEt')}
                </Button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
