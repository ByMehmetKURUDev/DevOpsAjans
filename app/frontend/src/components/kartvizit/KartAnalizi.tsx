import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, BarChart3, Download, Loader2, Table2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { KART, sayiYaz } from '@/components/dinamikQr/ortak';
import { PLATFORM_ADI } from '@/components/kartvizit/KartGorunumu';
import { hataMetni, type Analiz } from '@/lib/kartvizit';

/**
 * Faz 4K — kart ya da yorum sayfası analitiği: toplamlar, son 30 gün günlük
 * görüntülenme (tek seri, tek renk; çubuğa gelince/odaklanınca ipucu, "Tablo"
 * görünümü), tıklanan öğeler ve cihaz dağılımı. Bot ve bağlantı önizlemeleri
 * sunucuda ayıklanıyor; ham IP saklanmıyor (gün bazlı tuzlu özet).
 */

export interface AnalizKaynagi {
  id: number;
  baslik: string;
  analiz: (id: number, gun?: number) => Promise<Analiz>;
  qrIndir?: (bicim: 'png' | 'svg') => Promise<void>;
}

const KART_OLAYLARI = ['goruntulenme', 'rehber', 'tik', 'form', 'paylas'] as const;
const YORUM_OLAYLARI = ['goruntulenme', 'google', 'geri_bildirim'] as const;

export function AnalizPaneli({ kaynak, tur, onGeri }: { kaynak: AnalizKaynagi; tur: 'kart' | 'yorum'; onGeri: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [a, setA] = useState<Analiz | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [tablo, setTablo] = useState(false);
  const [secili, setSecili] = useState<number | null>(null);

  useEffect(() => {
    let iptal = false;
    kaynak
      .analiz(kaynak.id, 30)
      .then((x) => !iptal && setA(x))
      .catch((e) => !iptal && setHata(hataMetni(t, e)));
    return () => {
      iptal = true;
    };
  }, [kaynak, t]);

  const olaylar = tur === 'kart' ? KART_OLAYLARI : YORUM_OLAYLARI;
  const gunYaz = (g: string) => {
    try {
      return new Intl.DateTimeFormat(dil, { day: 'numeric', month: 'short' }).format(new Date(`${g}T12:00:00Z`));
    } catch {
      return g;
    }
  };

  return (
    <div className="space-y-4" data-testid="kart-analizi">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" className="gap-1.5" onClick={onGeri}>
          <ArrowLeft className="h-4 w-4 rtl:-scale-x-100" aria-hidden="true" />
          {t('kartvizit.duzenle.listeyeDon')}
        </Button>
        <h3 className="min-w-0 truncate text-lg font-semibold">{kaynak.baslik}</h3>
        {kaynak.qrIndir && (
          <div className="ms-auto flex gap-1.5">
            {(['png', 'svg'] as const).map((b) => (
              <Button
                key={b}
                size="sm"
                variant="outline"
                className="h-9 gap-1 !bg-transparent border-white/20"
                onClick={() => void kaynak.qrIndir?.(b).catch((e) => toast.error(hataMetni(t, e)))}
              >
                <Download className="h-3.5 w-3.5" aria-hidden="true" />
                QR {b.toUpperCase()}
              </Button>
            ))}
          </div>
        )}
      </div>
      {hata && (
        <p className="text-sm text-red-300" role="alert">
          {hata}
        </p>
      )}
      {!a ? (
        !hata && (
          <div className="flex justify-center py-12 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
          </div>
        )
      ) : (
        <div className={`${KART} space-y-6 p-4 sm:p-6`}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h4 className="text-base font-semibold">{t('kartvizit.analiz.baslik')}</h4>
            <p className="text-xs text-muted-foreground">{t('kartvizit.analiz.botBilgi', { sayi: sayiYaz(a.bot, dil) })}</p>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Kutu ad={t('kartvizit.analiz.tekil')} deger={sayiYaz(a.tekil, dil)} test="tekil" />
            {olaylar.map((o) => (
              <Kutu key={o} ad={t(`kartvizit.olay.${o}`)} deger={sayiYaz(a.toplam[o] || 0, dil)} test={o} />
            ))}
            {tur === 'kart' && <Kutu ad={t('kartvizit.analiz.qrIle')} deger={sayiYaz(a.qr, dil)} test="qr" />}
          </div>

          <section aria-labelledby="kv-gunluk">
            <div className="mb-2 flex items-center justify-between gap-2">
              <h5 id="kv-gunluk" className="text-sm font-medium">
                {t('kartvizit.analiz.gunluk', { gun: a.donem.gun })}
              </h5>
              <Button size="sm" variant="ghost" className="h-8 gap-1.5 text-xs" onClick={() => setTablo((x) => !x)} aria-pressed={tablo}>
                {tablo ? <BarChart3 className="h-3.5 w-3.5" aria-hidden="true" /> : <Table2 className="h-3.5 w-3.5" aria-hidden="true" />}
                {tablo ? t('kartvizit.analiz.grafik') : t('kartvizit.analiz.tablo')}
              </Button>
            </div>
            {tablo ? (
              <div className="max-h-72 overflow-auto rounded-lg border border-white/10">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-black/60 text-muted-foreground">
                    <tr>
                      <th className="px-3 py-2 text-start font-medium">{t('kartvizit.analiz.tarih')}</th>
                      <th className="px-3 py-2 text-end font-medium">{t('kartvizit.olay.goruntulenme')}</th>
                      <th className="px-3 py-2 text-end font-medium">{t('kartvizit.analiz.tekil')}</th>
                      {olaylar.slice(1).map((o) => (
                        <th key={o} className="px-3 py-2 text-end font-medium">
                          {t(`kartvizit.olay.${o}`)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {[...a.gunluk].reverse().map((g) => (
                      <tr key={g.gun} className="border-t border-white/5">
                        <td className="px-3 py-1.5">{gunYaz(g.gun)}</td>
                        <td className="px-3 py-1.5 text-end tabular-nums">{sayiYaz(Number(g.goruntulenme) || 0, dil)}</td>
                        <td className="px-3 py-1.5 text-end tabular-nums">{sayiYaz(g.tekil, dil)}</td>
                        {olaylar.slice(1).map((o) => (
                          <td key={o} className="px-3 py-1.5 text-end tabular-nums">
                            {sayiYaz(Number(g[o]) || 0, dil)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Grafik a={a} secili={secili} setSecili={setSecili} gunYaz={gunYaz} dil={dil} />
            )}
          </section>

          <div className="grid gap-6 md:grid-cols-2">
            {tur === 'kart' && (
              <section>
                <h5 className="mb-2 text-sm font-medium">{t('kartvizit.analiz.tiklananlar')}</h5>
                {a.hedefler.length === 0 ? (
                  <p className="text-xs text-muted-foreground">{t('kartvizit.analiz.veriYok')}</p>
                ) : (
                  <ul className="space-y-1.5 text-sm" data-testid="kart-analiz-hedefler">
                    {a.hedefler.map((h) => (
                      <li key={h.hedef} className="flex items-center justify-between gap-3 rounded-lg bg-white/[0.03] px-3 py-1.5">
                        <span className="min-w-0 truncate">{hedefEtiketi(h.hedef, h.etiket, t)}</span>
                        <span className="tabular-nums text-muted-foreground">{sayiYaz(h.sayi, dil)}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            )}
            <section>
              <h5 className="mb-2 text-sm font-medium">{t('kartvizit.analiz.cihazlar')}</h5>
              {a.cihazlar.length === 0 ? (
                <p className="text-xs text-muted-foreground">{t('kartvizit.analiz.veriYok')}</p>
              ) : (
                <ul className="space-y-1.5 text-sm">
                  {a.cihazlar.map((c) => (
                    <li key={c.anahtar} className="flex items-center justify-between gap-3 rounded-lg bg-white/[0.03] px-3 py-1.5">
                      <span>{t(`kartvizit.cihaz.${c.anahtar}`, { defaultValue: c.anahtar })}</span>
                      <span className="tabular-nums text-muted-foreground">{sayiYaz(c.sayi, dil)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
          <p className="text-[11px] text-muted-foreground">{t('kartvizit.analiz.gizlilik')}</p>
        </div>
      )}
    </div>
  );
}

function hedefEtiketi(hedef: string, etiket: string | null | undefined, t: (k: string, o?: Record<string, unknown>) => string): string {
  if (hedef.startsWith('s:')) return PLATFORM_ADI[hedef.slice(2)] || hedef.slice(2);
  if (hedef.startsWith('l:')) return etiket || t('kartvizit.analiz.silinmisBaglanti');
  if (hedef.startsWith('tel:')) return `${t('kartvizit.alan.telefonlar')}: ${etiket || ''}`;
  if (hedef.startsWith('web:')) return `${t('kartvizit.alan.webler')}: ${etiket || ''}`;
  if (hedef === 'eposta') return `${t('kartvizit.alan.eposta')}: ${etiket || ''}`;
  if (hedef === 'galeri') return t('kartvizit.gorsel.galeri');
  return etiket || hedef;
}

function Kutu({ ad, deger, test }: { ad: string; deger: string; test: string }) {
  return (
    <div className="rounded-xl border border-white/10 bg-black/20 p-3" data-analiz={test}>
      <p className="text-xs text-muted-foreground">{ad}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{deger}</p>
    </div>
  );
}

function Grafik({
  a,
  secili,
  setSecili,
  gunYaz,
  dil,
}: {
  a: Analiz;
  secili: number | null;
  setSecili: (i: number | null) => void;
  gunYaz: (g: string) => string;
  dil: string;
}) {
  const { t } = useTranslation();
  const deger = (i: number) => Number(a.gunluk[i]?.goruntulenme) || 0;
  const enCok = Math.max(1, ...a.gunluk.map((_, i) => deger(i)));
  const odak = secili !== null ? a.gunluk[secili] : null;
  return (
    <div>
      <p className="mb-1 h-4 text-xs text-muted-foreground" aria-live="polite">
        {odak
          ? t('kartvizit.analiz.ipucu', { tarih: gunYaz(odak.gun), sayi: sayiYaz(Number(odak.goruntulenme) || 0, dil), tekil: sayiYaz(odak.tekil, dil) })
          : ''}
      </p>
      <div className="relative" dir="ltr">
        <span className="absolute -top-0.5 start-0 text-[10px] text-muted-foreground">{sayiYaz(enCok, dil)}</span>
        <div
          className="flex h-36 items-end gap-[2px] border-b border-white/15 pt-4"
          role="img"
          aria-label={t('kartvizit.analiz.grafikEtiket', { gun: a.donem.gun, sayi: a.donem.goruntulenme || 0 })}
          onMouseLeave={() => setSecili(null)}
          data-testid="kart-gunluk-grafik"
        >
          {a.gunluk.map((g, i) => (
            <div
              key={g.gun}
              className="group flex h-full flex-1 items-end"
              onMouseEnter={() => setSecili(i)}
              onFocus={() => setSecili(i)}
              onBlur={() => setSecili(null)}
              tabIndex={0}
              aria-label={t('kartvizit.analiz.ipucu', { tarih: gunYaz(g.gun), sayi: deger(i), tekil: g.tekil })}
            >
              <div
                className={`w-full rounded-t-[4px] transition-colors ${secili === i ? 'bg-purple-300' : 'bg-purple-400/80'}`}
                style={{ height: deger(i) ? `${Math.max(3, (deger(i) / enCok) * 100)}%` : 0 }}
              />
            </div>
          ))}
        </div>
        <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
          <span>{gunYaz(a.gunluk[0]?.gun ?? '')}</span>
          <span>{gunYaz(a.gunluk[a.gunluk.length - 1]?.gun ?? '')}</span>
        </div>
      </div>
    </div>
  );
}

export default function KartAnalizi({
  api,
  kayit,
  onGeri,
}: {
  api: { analiz: (id: number, gun?: number) => Promise<Analiz>; qrIndir: (id: number, b: 'png' | 'svg', slug: string) => Promise<void> };
  kayit: { id: number; ad_soyad: string; slug: string };
  onGeri: () => void;
}) {
  const [kaynak] = useState<AnalizKaynagi>(() => ({
    id: kayit.id,
    baslik: kayit.ad_soyad,
    analiz: api.analiz,
    qrIndir: (b) => api.qrIndir(kayit.id, b, kayit.slug),
  }));
  return <AnalizPaneli kaynak={kaynak} tur="kart" onGeri={onGeri} />;
}
