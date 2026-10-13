import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent, type WheelEvent } from 'react';
import { Minus, Plus, Scan } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import './osmHarita.css';

/**
 * Faz 11E — hafif OpenStreetMap haritası (harita kütüphanesi yok; ~300 satır).
 *
 * Standart OSM raster karoları (`tile.openstreetmap.org`) Web Mercator'da yerleştiriliyor; yalnız görünen
 * karolar isteniyor (önden indirme / çevrimdışı kayıt YOK — OSM karo kullanım politikası). Tarayıcı kendi
 * önbelleğini ve Referer'ını kullanıyor; site Referrer-Policy'si (strict-origin-when-cross-origin) kaynağı
 * gönderiyor. Atıf ("© OpenStreetMap katkıda bulunanlar") her zaman görünür, sağ altta.
 *
 * Etkileşim: sürükleyerek kaydırma, +/− düğmeleri, çift tıklama, Ctrl/⌘ + tekerlek (ya da dokunmatik
 * yakınlaştırma), klavye (oklar, +/−). Sayfa kaydırması haritaya takılmıyor (düz tekerlek sayfayı kaydırır).
 * İşaretler düğme (klavyeyle seçilebilir); çizgiler SVG. `onTikla` verilirse boş yere tıklamak koordinat döndürür.
 */

export interface HaritaIsareti {
  id: string | number;
  enlem: number;
  boylam: number;
  renk: string;
  etiket: string;
  /** İşaretin içinde gösterilen kısa metin (sıra numarası vb.). */
  ic?: string;
  vurgu?: boolean;
  nabiz?: boolean;
  /** Kırmızı halka (gecikmiş). */
  uyari?: boolean;
}

export interface HaritaCizgisi {
  renk: string;
  noktalar: [number, number][];
}

interface Props {
  isaretler: HaritaIsareti[];
  cizgiler?: HaritaCizgisi[];
  secili?: string | number | null;
  onSec?: (id: string | number) => void;
  onTikla?: (enlem: number, boylam: number) => void;
  /** Bu değer değişince harita işaretlere yeniden sığdırılır. */
  sigdirAnahtari?: string | number;
  varsayilanMerkez?: [number, number];
  varsayilanYakinlik?: number;
  enFazlaYakinlik?: number;
  karanlik?: boolean;
  className?: string;
  etiket?: string;
  testid?: string;
}

const KARO = 256;
const EN_AZ_Z = 2;
const EN_COK_Z = 18;
const ENLEM_SINIRI = 85.0511;

function izdusum(enlem: number, boylam: number, z: number) {
  const s = KARO * 2 ** z;
  const e = Math.max(-ENLEM_SINIRI, Math.min(ENLEM_SINIRI, enlem));
  const sin = Math.sin((e * Math.PI) / 180);
  return { x: ((boylam + 180) / 360) * s, y: (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * s };
}

function geriIzdusum(x: number, y: number, z: number) {
  const s = KARO * 2 ** z;
  const n = Math.PI - (2 * Math.PI * y) / s;
  let boylam = (x / s) * 360 - 180;
  boylam = ((((boylam + 180) % 360) + 360) % 360) - 180;
  return { enlem: (180 / Math.PI) * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n))), boylam };
}

const ISTANBUL: [number, number] = [41.0082, 28.9784];

export default function OsmHarita({
  isaretler,
  cizgiler = [],
  secili = null,
  onSec,
  onTikla,
  sigdirAnahtari,
  varsayilanMerkez = ISTANBUL,
  varsayilanYakinlik = 10,
  enFazlaYakinlik = 16,
  karanlik = true,
  className = '',
  etiket,
  testid,
}: Props) {
  const { t } = useTranslation();
  const kapRef = useRef<HTMLDivElement>(null);
  const [boyut, setBoyut] = useState({ w: 0, h: 0 });
  const [gorus, setGorus] = useState<{ enlem: number; boylam: number; z: number }>({
    enlem: varsayilanMerkez[0],
    boylam: varsayilanMerkez[1],
    z: varsayilanYakinlik,
  });

  useLayoutEffect(() => {
    const kap = kapRef.current;
    if (!kap) return;
    const olc = () => setBoyut({ w: kap.clientWidth, h: kap.clientHeight });
    olc();
    if (typeof ResizeObserver === 'undefined') return;
    const g = new ResizeObserver(olc);
    g.observe(kap);
    return () => g.disconnect();
  }, []);

  // İşaretlere sığdır (ilk boyut ölçüldüğünde ve anahtar değişince).
  const sigdir = useCallback(() => {
    if (!boyut.w || !boyut.h) return;
    const noktalar: [number, number][] = [...isaretler.map((i) => [i.enlem, i.boylam] as [number, number]), ...cizgiler.flatMap((c) => c.noktalar)];
    if (noktalar.length === 0) {
      setGorus({ enlem: varsayilanMerkez[0], boylam: varsayilanMerkez[1], z: varsayilanYakinlik });
      return;
    }
    const pay = 56;
    for (let z = enFazlaYakinlik; z >= EN_AZ_Z; z--) {
      const p = noktalar.map(([e, b]) => izdusum(e, b, z));
      const minX = Math.min(...p.map((q) => q.x));
      const maxX = Math.max(...p.map((q) => q.x));
      const minY = Math.min(...p.map((q) => q.y));
      const maxY = Math.max(...p.map((q) => q.y));
      if (maxX - minX <= boyut.w - 2 * pay && maxY - minY <= boyut.h - 2 * pay) {
        const m = geriIzdusum((minX + maxX) / 2, (minY + maxY) / 2, z);
        setGorus({ enlem: m.enlem, boylam: m.boylam, z: noktalar.length === 1 ? Math.min(z, 15) : z });
        return;
      }
    }
    setGorus((g) => ({ ...g, z: EN_AZ_Z }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [boyut.w, boyut.h, sigdirAnahtari]);

  const ilkSigdirma = useRef<string | number | undefined | null>(null);
  useEffect(() => {
    if (!boyut.w || !boyut.h) return;
    const anahtar = sigdirAnahtari ?? '';
    if (ilkSigdirma.current === anahtar) return;
    ilkSigdirma.current = anahtar;
    sigdir();
  }, [boyut.w, boyut.h, sigdirAnahtari, sigdir]);

  const merkezPx = useMemo(() => izdusum(gorus.enlem, gorus.boylam, gorus.z), [gorus]);
  const solUst = { x: merkezPx.x - boyut.w / 2, y: merkezPx.y - boyut.h / 2 };

  const karolar = useMemo(() => {
    if (!boyut.w || !boyut.h) return [];
    const n = 2 ** gorus.z;
    const x0 = Math.floor(solUst.x / KARO);
    const x1 = Math.floor((solUst.x + boyut.w) / KARO);
    const y0 = Math.max(0, Math.floor(solUst.y / KARO));
    const y1 = Math.min(n - 1, Math.floor((solUst.y + boyut.h) / KARO));
    const liste: { anahtar: string; src: string; sol: number; ust: number }[] = [];
    for (let ty = y0; ty <= y1; ty++) {
      for (let tx = x0; tx <= x1; tx++) {
        const wx = ((tx % n) + n) % n;
        liste.push({
          anahtar: `${gorus.z}/${tx}/${ty}`,
          src: `https://tile.openstreetmap.org/${gorus.z}/${wx}/${ty}.png`,
          sol: Math.round(tx * KARO - solUst.x),
          ust: Math.round(ty * KARO - solUst.y),
        });
      }
    }
    return liste;
  }, [gorus.z, solUst.x, solUst.y, boyut.w, boyut.h]);

  const ekrana = (enlem: number, boylam: number) => {
    const p = izdusum(enlem, boylam, gorus.z);
    // Dünyanın sarmalanması: merkeze en yakın kopya.
    const s = KARO * 2 ** gorus.z;
    let x = p.x - solUst.x;
    if (x < -s / 2) x += s;
    if (x > s / 2 + boyut.w) x -= s;
    return { x, y: p.y - solUst.y };
  };

  const yakinlas = (fark: number, odak?: { x: number; y: number }) => {
    setGorus((g) => {
      const z = Math.max(EN_AZ_Z, Math.min(EN_COK_Z, g.z + fark));
      if (z === g.z) return g;
      const o = odak ?? { x: boyut.w / 2, y: boyut.h / 2 };
      const m = izdusum(g.enlem, g.boylam, g.z);
      const nokta = geriIzdusum(m.x - boyut.w / 2 + o.x, m.y - boyut.h / 2 + o.y, g.z);
      const yeni = izdusum(nokta.enlem, nokta.boylam, z);
      const c = geriIzdusum(yeni.x - o.x + boyut.w / 2, yeni.y - o.y + boyut.h / 2, z);
      return { enlem: c.enlem, boylam: c.boylam, z };
    });
  };

  const kaydir = (dx: number, dy: number) => {
    setGorus((g) => {
      const m = izdusum(g.enlem, g.boylam, g.z);
      const s = KARO * 2 ** g.z;
      const y = Math.max(0, Math.min(s, m.y + dy));
      const c = geriIzdusum(m.x + dx, y, g.z);
      return { ...g, enlem: c.enlem, boylam: c.boylam };
    });
  };

  // Sürükleme ve iki parmakla yakınlaştırma
  const isaretciler = useRef(new Map<number, { x: number; y: number }>());
  const surukleme = useRef<{ x: number; y: number; hareket: number } | null>(null);
  const tutam = useRef<number | null>(null);

  const asagi = (e: PointerEvent<HTMLDivElement>) => {
    if ((e.target as HTMLElement).closest('[data-harita-dugme]')) return;
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
    isaretciler.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (isaretciler.current.size === 1) surukleme.current = { x: e.clientX, y: e.clientY, hareket: 0 };
    else if (isaretciler.current.size === 2) {
      const [a, b] = [...isaretciler.current.values()];
      tutam.current = Math.hypot(a.x - b.x, a.y - b.y);
    }
  };
  const hareket = (e: PointerEvent<HTMLDivElement>) => {
    if (!isaretciler.current.has(e.pointerId)) return;
    isaretciler.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (isaretciler.current.size === 2 && tutam.current) {
      const [a, b] = [...isaretciler.current.values()];
      const d = Math.hypot(a.x - b.x, a.y - b.y);
      if (d / tutam.current > 1.5 || d / tutam.current < 0.66) {
        yakinlas(d > tutam.current ? 1 : -1);
        tutam.current = d;
      }
      return;
    }
    const s = surukleme.current;
    if (!s) return;
    const dx = e.clientX - s.x;
    const dy = e.clientY - s.y;
    s.hareket += Math.abs(dx) + Math.abs(dy);
    s.x = e.clientX;
    s.y = e.clientY;
    if (dx || dy) kaydir(-dx, -dy);
  };
  const yukari = (e: PointerEvent<HTMLDivElement>) => {
    const s = surukleme.current;
    isaretciler.current.delete(e.pointerId);
    if (isaretciler.current.size < 2) tutam.current = null;
    if (isaretciler.current.size === 0) surukleme.current = null;
    if (s && s.hareket < 5 && onTikla && kapRef.current && !(e.target as HTMLElement).closest('[data-harita-dugme]')) {
      const r = kapRef.current.getBoundingClientRect();
      const p = geriIzdusum(solUst.x + (e.clientX - r.left), solUst.y + (e.clientY - r.top), gorus.z);
      onTikla(Number(p.enlem.toFixed(6)), Number(p.boylam.toFixed(6)));
    }
  };

  const tekerlek = (e: WheelEvent<HTMLDivElement>) => {
    if (!(e.ctrlKey || e.metaKey)) return; // düz tekerlek sayfayı kaydırsın
    e.preventDefault();
    const r = e.currentTarget.getBoundingClientRect();
    yakinlas(e.deltaY < 0 ? 1 : -1, { x: e.clientX - r.left, y: e.clientY - r.top });
  };

  const tus = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.target !== e.currentTarget) return;
    const adim = 80;
    const harita: Record<string, () => void> = {
      ArrowLeft: () => kaydir(-adim, 0),
      ArrowRight: () => kaydir(adim, 0),
      ArrowUp: () => kaydir(0, -adim),
      ArrowDown: () => kaydir(0, adim),
      '+': () => yakinlas(1),
      '=': () => yakinlas(1),
      '-': () => yakinlas(-1),
    };
    const f = harita[e.key];
    if (f) {
      e.preventDefault();
      f();
    }
  };

  return (
    <div
      ref={kapRef}
      className={`osm ${karanlik ? 'osm-karanlik' : ''} ${onTikla ? 'osm-secici' : ''} ${className}`}
      role="application"
      aria-label={etiket || t('harita.etiket')}
      aria-roledescription={t('harita.rol')}
      tabIndex={0}
      onPointerDown={asagi}
      onPointerMove={hareket}
      onPointerUp={yukari}
      onPointerCancel={yukari}
      onWheel={tekerlek}
      onDoubleClick={(e) => {
        if ((e.target as HTMLElement).closest('[data-harita-dugme]')) return;
        const r = e.currentTarget.getBoundingClientRect();
        yakinlas(1, { x: e.clientX - r.left, y: e.clientY - r.top });
      }}
      onKeyDown={tus}
      data-testid={testid}
      data-yakinlik={gorus.z}
    >
      <div className="osm-karolar" aria-hidden="true">
        {karolar.map((k) => (
          <img
            key={k.anahtar}
            src={k.src}
            alt=""
            width={KARO}
            height={KARO}
            draggable={false}
            decoding="async"
            className="osm-karo"
            style={{ transform: `translate(${k.sol}px, ${k.ust}px)` }}
          />
        ))}
      </div>
      <div className="osm-ton" aria-hidden="true" />

      {cizgiler.length > 0 && (
        <svg className="osm-cizgiler" width={boyut.w} height={boyut.h} aria-hidden="true" focusable="false">
          {cizgiler.map((c, i) => {
            const d = c.noktalar
              .map(([e, b], j) => {
                const p = ekrana(e, b);
                return `${j ? 'L' : 'M'}${p.x.toFixed(1)},${p.y.toFixed(1)}`;
              })
              .join(' ');
            return (
              <g key={i} style={{ color: c.renk }}>
                <path d={d} className="osm-cizgi-isik" />
                <path d={d} className="osm-cizgi" />
              </g>
            );
          })}
        </svg>
      )}

      {isaretler.map((i) => {
        const p = ekrana(i.enlem, i.boylam);
        if (p.x < -40 || p.y < -40 || p.x > boyut.w + 40 || p.y > boyut.h + 40) return null;
        const sec = secili != null && secili === i.id;
        return (
          <button
            key={i.id}
            type="button"
            data-harita-dugme=""
            data-harita-isaret={i.id}
            className={`osm-isaret ${sec || i.vurgu ? 'osm-isaret-secili' : ''} ${i.nabiz ? 'osm-isaret-nabiz' : ''} ${i.uyari ? 'osm-isaret-uyari' : ''}`}
            style={{ transform: `translate(${p.x.toFixed(1)}px, ${p.y.toFixed(1)}px)`, ['--osm-renk' as string]: i.renk }}
            onClick={() => onSec?.(i.id)}
            aria-pressed={onSec ? sec : undefined}
            aria-label={i.etiket}
            title={i.etiket}
          >
            <span className="osm-isaret-nokta">{i.ic}</span>
            {sec && <span className="osm-isaret-etiket">{i.etiket}</span>}
          </button>
        );
      })}

      <div className="osm-kontroller" data-harita-dugme="">
        <button type="button" onClick={() => yakinlas(1)} aria-label={t('harita.yakinlas')} title={t('harita.yakinlas')}>
          <Plus className="h-4 w-4" aria-hidden="true" />
        </button>
        <button type="button" onClick={() => yakinlas(-1)} aria-label={t('harita.uzaklas')} title={t('harita.uzaklas')}>
          <Minus className="h-4 w-4" aria-hidden="true" />
        </button>
        <button type="button" onClick={sigdir} aria-label={t('harita.sigdir')} title={t('harita.sigdir')}>
          <Scan className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>

      <p className="osm-atif" data-harita-dugme="">
        ©{' '}
        <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">
          OpenStreetMap
        </a>{' '}
        {t('harita.katkida')}
      </p>
    </div>
  );
}
