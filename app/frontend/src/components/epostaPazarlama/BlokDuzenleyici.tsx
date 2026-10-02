import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ArrowDown,
  ArrowUp,
  Columns2,
  Eye,
  Heading,
  Image as ImageIcon,
  Loader2,
  Minus,
  MousePointerClick,
  MoveVertical,
  Smartphone,
  Monitor,
  Sparkles,
  Trash2,
  Type,
} from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Alan, DIS_DUGME, GIRDI, KART, METIN_ALANI, SECIM } from '@/components/epostaPazarlama/ortak';
import { hataMetni, type Blok, type BlokTuru, type Onizleme, type PazarlamaApi } from '@/lib/epostaPazarlama';
import { SABLONLAR, sablonBloklari, yeniBlok, yerTutucuOrnekleri, type SablonAdi } from '@/lib/epostaSablonlari';

const EKLENEBILIR: { tur: BlokTuru; ikon: typeof Type }[] = [
  { tur: 'baslik', ikon: Heading },
  { tur: 'metin', ikon: Type },
  { tur: 'gorsel', ikon: ImageIcon },
  { tur: 'dugme', ikon: MousePointerClick },
  { tur: 'ayirici', ikon: Minus },
  { tur: 'bosluk', ikon: MoveVertical },
  { tur: 'iki_sutun', ikon: Columns2 },
  { tur: 'logo', ikon: Sparkles },
];
const SUTUN_EKLENEBILIR: BlokTuru[] = ['baslik', 'metin', 'gorsel', 'dugme'];

/**
 * Faz 5M — blok tabanlı basit e-posta düzenleyici (yeni npm paketi yok). Çıktı sunucuda
 * e-posta uyumlu tablo HTML + düz metne dönüşüyor; önizleme sunucunun ürettiği HTML'i
 * kum havuzundaki (betiksiz) çerçevede gösteriyor — panelde gördüğünüz, gidenin aynısı.
 */
export default function BlokDuzenleyici({
  api,
  bloklar,
  onDegis,
  konu,
  onizlemeMetni,
  dil,
  gonderenAdi,
  testid = 'ep-blok-duzenleyici',
}: {
  api: PazarlamaApi;
  bloklar: Blok[];
  onDegis: (b: Blok[]) => void;
  konu: string;
  onizlemeMetni?: string;
  dil: string;
  gonderenAdi?: string;
  testid?: string;
}) {
  const { t } = useTranslation();
  const [onizleme, setOnizleme] = useState<Onizleme | null>(null);
  const [dar, setDar] = useState(true);
  const [metinSurumu, setMetinSurumu] = useState(false);
  const [mesgul, setMesgul] = useState(false);

  const degis = (i: number, b: Blok) => onDegis(bloklar.map((x, j) => (j === i ? b : x)));
  const tasi = (i: number, yon: -1 | 1) => {
    const j = i + yon;
    if (j < 0 || j >= bloklar.length) return;
    const yeni = [...bloklar];
    [yeni[i], yeni[j]] = [yeni[j], yeni[i]];
    onDegis(yeni);
  };
  const sablonSec = (ad: SablonAdi) => {
    if (bloklar.length && !window.confirm(t('epostaPazarlama.blok.sablonOnay'))) return;
    onDegis(sablonBloklari(ad, t));
  };
  const onizle = async () => {
    setMesgul(true);
    try {
      setOnizleme(await api.onizleme({ bloklar, konu, onizleme_metni: onizlemeMetni, dil, gonderen_adi: gonderenAdi }));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  return (
    <div className="space-y-3" data-testid={testid}>
      <div className={`${KART} p-3`}>
        <p className="mb-2 text-xs font-medium text-muted-foreground">{t('epostaPazarlama.blok.sablonlar')}</p>
        <div className="flex flex-wrap gap-1.5" data-testid="ep-sablonlar">
          {SABLONLAR.map((s) => (
            <Button key={s} size="sm" variant="outline" className={`${DIS_DUGME} h-8 text-xs`} onClick={() => sablonSec(s)} data-sablon={s}>
              {t(`epostaPazarlama.sablon.${s}.ad`)}
            </Button>
          ))}
        </div>
      </div>

      <ol className="space-y-2">
        {bloklar.map((b, i) => (
          <li key={i} className={`${KART} p-3`} data-blok={b.tur} data-blok-sira={i}>
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-xs font-semibold uppercase tracking-wide text-purple-200">{t(`epostaPazarlama.blok.tur.${b.tur}`)}</span>
              <span className="flex gap-0.5">
                <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => tasi(i, -1)} disabled={i === 0} aria-label={t('epostaPazarlama.blok.yukari')}>
                  <ArrowUp className="h-3.5 w-3.5" aria-hidden="true" />
                </Button>
                <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => tasi(i, 1)} disabled={i === bloklar.length - 1} aria-label={t('epostaPazarlama.blok.asagi')}>
                  <ArrowDown className="h-3.5 w-3.5" aria-hidden="true" />
                </Button>
                <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => onDegis(bloklar.filter((_, j) => j !== i))} aria-label={t('epostaPazarlama.genel.sil')}>
                  <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                </Button>
              </span>
            </div>
            <BlokAlanlari api={api} blok={b} onDegis={(x) => degis(i, x)} />
          </li>
        ))}
      </ol>

      <div className="flex flex-wrap gap-1.5" data-testid="ep-blok-ekle">
        {EKLENEBILIR.map(({ tur, ikon: Ikon }) => (
          <Button key={tur} size="sm" variant="outline" className={`${DIS_DUGME} h-8 text-xs`} onClick={() => onDegis([...bloklar, yeniBlok(tur, t)])} data-blok-ekle={tur}>
            <Ikon className="h-3.5 w-3.5" aria-hidden="true" /> {t(`epostaPazarlama.blok.tur.${tur}`)}
          </Button>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">{t('epostaPazarlama.blok.yerTutucuIpucu', yerTutucuOrnekleri(t))}</p>

      <div className={`${KART} p-3`}>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" onClick={() => void onizle()} disabled={mesgul || !bloklar.length} className="gap-1.5" data-testid="ep-onizle">
            {mesgul ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}
            {t('epostaPazarlama.genel.onizleme')}
          </Button>
          {onizleme && (
            <>
              <Button size="sm" variant="ghost" className="gap-1" onClick={() => setDar(!dar)} aria-pressed={dar}>
                {dar ? <Smartphone className="h-4 w-4" aria-hidden="true" /> : <Monitor className="h-4 w-4" aria-hidden="true" />}
                {dar ? t('epostaPazarlama.blok.mobil') : t('epostaPazarlama.blok.masaustu')}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setMetinSurumu(!metinSurumu)} aria-pressed={metinSurumu}>
                {metinSurumu ? t('epostaPazarlama.blok.html') : t('epostaPazarlama.blok.duzMetin')}
              </Button>
            </>
          )}
        </div>
        {onizleme && (
          <div className="mt-3 space-y-2" data-testid="ep-onizleme">
            <p className="truncate text-xs text-muted-foreground">
              <strong className="text-white/80">{onizleme.gonderen}</strong> · {onizleme.konu}
            </p>
            {metinSurumu ? (
              <pre className="max-h-[480px] overflow-auto whitespace-pre-wrap rounded-lg bg-black/40 p-3 text-xs" data-testid="ep-onizleme-metin">
                {onizleme.metin}
              </pre>
            ) : (
              <div className="overflow-x-auto">
                <iframe
                  title={t('epostaPazarlama.genel.onizleme')}
                  sandbox=""
                  srcDoc={onizleme.html}
                  className="mx-auto block h-[560px] rounded-lg border border-white/10 bg-white"
                  style={{ width: dar ? 360 : 640, maxWidth: '100%' }}
                  data-testid="ep-onizleme-cerceve"
                />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function BlokAlanlari({ api, blok, onDegis, sutun = false }: { api: PazarlamaApi; blok: Blok; onDegis: (b: Blok) => void; sutun?: boolean }) {
  const { t } = useTranslation();
  const [yukleniyor, setYukleniyor] = useState(false);
  const hiza = (deger: string | undefined) => (
    <select className={SECIM} value={deger || 'sol'} onChange={(e) => onDegis({ ...blok, hiza: e.target.value } as Blok)} aria-label={t('epostaPazarlama.blok.hiza')}>
      {(['sol', 'orta', 'sag'] as const).map((h) => (
        <option key={h} value={h}>
          {t(`epostaPazarlama.blok.hizalar.${h}`)}
        </option>
      ))}
    </select>
  );
  switch (blok.tur) {
    case 'logo':
      return <p className="text-xs text-muted-foreground">{t('epostaPazarlama.blok.logoIpucu')}</p>;
    case 'ayirici':
      return null;
    case 'bosluk':
      return (
        <input
          type="range"
          min={8}
          max={64}
          value={blok.yukseklik ?? 24}
          onChange={(e) => onDegis({ ...blok, yukseklik: Number(e.target.value) })}
          className="w-full accent-purple-500"
          aria-label={t('epostaPazarlama.blok.yukseklik')}
        />
      );
    case 'baslik':
      return (
        <div className="grid gap-2 sm:grid-cols-[1fr_auto_auto]">
          <input className={GIRDI} value={blok.metin} onChange={(e) => onDegis({ ...blok, metin: e.target.value })} aria-label={t('epostaPazarlama.blok.tur.baslik')} data-testid="ep-blok-metin" />
          <select className={SECIM} value={blok.seviye ?? 1} onChange={(e) => onDegis({ ...blok, seviye: Number(e.target.value) as 1 | 2 })} aria-label={t('epostaPazarlama.blok.seviye')}>
            <option value={1}>H1</option>
            <option value={2}>H2</option>
          </select>
          {hiza(blok.hiza)}
        </div>
      );
    case 'metin':
      return (
        <div className="space-y-2">
          <textarea className={METIN_ALANI} value={blok.metin} onChange={(e) => onDegis({ ...blok, metin: e.target.value })} aria-label={t('epostaPazarlama.blok.tur.metin')} data-testid="ep-blok-metin" />
          {!sutun && <div className="max-w-[12rem]">{hiza(blok.hiza)}</div>}
          <p className="text-[11px] text-muted-foreground">{t('epostaPazarlama.blok.metinIpucu')}</p>
        </div>
      );
    case 'dugme':
      return (
        <div className="grid gap-2 sm:grid-cols-2">
          <Alan etiket={t('epostaPazarlama.blok.dugmeMetni')}>
            <input className={GIRDI} value={blok.metin} onChange={(e) => onDegis({ ...blok, metin: e.target.value })} data-testid="ep-blok-dugme-metin" />
          </Alan>
          <Alan etiket={t('epostaPazarlama.blok.adres')}>
            <input className={GIRDI} value={blok.url} onChange={(e) => onDegis({ ...blok, url: e.target.value })} placeholder="https://" data-testid="ep-blok-dugme-url" />
          </Alan>
          {!sutun && <div className="max-w-[12rem]">{hiza(blok.hiza)}</div>}
        </div>
      );
    case 'gorsel':
      return (
        <div className="grid gap-2 sm:grid-cols-2">
          <Alan etiket={t('epostaPazarlama.blok.gorselAdresi')}>
            <input className={GIRDI} value={blok.url} onChange={(e) => onDegis({ ...blok, url: e.target.value })} placeholder="https://" />
          </Alan>
          <Alan etiket={t('epostaPazarlama.blok.gorselYukle')}>
            <span className="flex items-center gap-2">
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp,image/gif"
                className="block w-full min-w-0 text-xs text-muted-foreground file:me-2 file:rounded-md file:border-0 file:bg-white/10 file:px-2 file:py-1.5 file:text-white"
                onChange={async (e) => {
                  const f = e.target.files?.[0];
                  if (!f) return;
                  setYukleniyor(true);
                  try {
                    const g = await api.gorselYukle(f);
                    onDegis({ ...blok, url: g.url });
                  } catch (h) {
                    toast.error(hataMetni(t, h));
                  } finally {
                    setYukleniyor(false);
                  }
                }}
              />
              {yukleniyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            </span>
          </Alan>
          <Alan etiket={t('epostaPazarlama.blok.alt')}>
            <input className={GIRDI} value={blok.alt ?? ''} onChange={(e) => onDegis({ ...blok, alt: e.target.value })} />
          </Alan>
          <Alan etiket={t('epostaPazarlama.blok.gorselBaglanti')}>
            <input className={GIRDI} value={blok.baglanti ?? ''} onChange={(e) => onDegis({ ...blok, baglanti: e.target.value || undefined })} placeholder="https://" />
          </Alan>
          {!sutun && (
            <Alan etiket={t('epostaPazarlama.blok.genislik')}>
              <input
                type="range"
                min={10}
                max={100}
                value={blok.genislik ?? 100}
                onChange={(e) => onDegis({ ...blok, genislik: Number(e.target.value) })}
                className="w-full accent-purple-500"
              />
            </Alan>
          )}
        </div>
      );
    case 'iki_sutun':
      return (
        <div className="grid gap-3 sm:grid-cols-2">
          {(['sol', 'sag'] as const).map((taraf) => (
            <div key={taraf} className="space-y-2 rounded-lg border border-white/10 p-2">
              <p className="text-[11px] font-semibold text-muted-foreground">{t(`epostaPazarlama.blok.${taraf}Sutun`)}</p>
              {blok[taraf].map((ic, j) => (
                <div key={j} className="space-y-1 rounded-md bg-white/[0.02] p-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] text-purple-200">{t(`epostaPazarlama.blok.tur.${ic.tur}`)}</span>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-6 w-6 p-0"
                      onClick={() => onDegis({ ...blok, [taraf]: blok[taraf].filter((_, k) => k !== j) })}
                      aria-label={t('epostaPazarlama.genel.sil')}
                    >
                      <Trash2 className="h-3 w-3" aria-hidden="true" />
                    </Button>
                  </div>
                  <BlokAlanlari api={api} blok={ic} sutun onDegis={(x) => onDegis({ ...blok, [taraf]: blok[taraf].map((y, k) => (k === j ? x : y)) })} />
                </div>
              ))}
              {blok[taraf].length < 4 && (
                <div className="flex flex-wrap gap-1">
                  {SUTUN_EKLENEBILIR.map((tur) => (
                    <Button
                      key={tur}
                      size="sm"
                      variant="ghost"
                      className="h-7 px-2 text-[11px]"
                      onClick={() => onDegis({ ...blok, [taraf]: [...blok[taraf], yeniBlok(tur, t)] })}
                    >
                      + {t(`epostaPazarlama.blok.tur.${tur}`)}
                    </Button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      );
    default:
      return null;
  }
}
