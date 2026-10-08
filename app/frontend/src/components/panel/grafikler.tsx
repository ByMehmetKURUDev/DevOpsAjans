import { useEffect, useId, useRef, useState, type RefObject } from 'react';
import './grafikler.css';

/**
 * Panel "Genel bakış" ekranlarının ortak hafif SVG grafikleri (yeni paket yok; recharts'tan çok daha küçük).
 * Faz 11A'da yönetici Genel bakışı için yazıldı (`components/admin/genelBakis`); Faz 11B'de müşteri Genel
 * bakışı da kullandığı için buraya taşındı (yöneticinin çizimi değişmedi: aynı kod, aynı sınıflar —
 * grafik kuralları `grafikler.css`'te).
 *
 * Kıvılcım (sparkline), iki serili alan grafiği (saatlik — yönetici; günlük + plan — `SeriGrafik`, müşteri),
 * dilimli halka ve tek değerli ilerleme halkası. Eğriler Catmull-Rom → kübik Bezier ile yumuşatılır; ışıma
 * bir `feGaussianBlur` kopyası. Bütün grafikler `aria-hidden` — sayıların kendisi kartta metin olarak var
 * (ekran okuyucu ve renk körlüğü için).
 */

export interface Nokta {
  x: number;
  y: number;
}

/** Kapsayıcının genişliği (ResizeObserver; yoksa ilk ölçü). */
export function useGenislik(ref: RefObject<HTMLElement>, ilk = 200): number {
  const [gen, setGen] = useState(ilk);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const olc = () => setGen(Math.max(40, Math.round(el.getBoundingClientRect().width)));
    olc();
    if (typeof ResizeObserver === 'undefined') return;
    const g = new ResizeObserver(olc);
    g.observe(el);
    return () => g.disconnect();
  }, [ref]);
  return gen;
}

/** Noktalardan yumuşak yol (`d`). */
export function yumusakYol(n: Nokta[]): string {
  if (!n.length) return '';
  let d = `M${n[0].x.toFixed(1)},${n[0].y.toFixed(1)}`;
  for (let i = 0; i < n.length - 1; i++) {
    const p0 = n[i - 1] ?? n[i];
    const p1 = n[i];
    const p2 = n[i + 1];
    const p3 = n[i + 2] ?? p2;
    // Denetim noktaları iki uç noktanın y aralığına sıkıştırılır: eğri sıfırın altına ya da tepenin
    // üstüne taşmasın (sayım verisinde "eksi" çukur görünmesin).
    const alt = Math.min(p1.y, p2.y);
    const ust = Math.max(p1.y, p2.y);
    const sinirla = (v: number) => Math.min(ust, Math.max(alt, v));
    const c1x = p1.x + (p2.x - p0.x) / 6;
    const c1y = sinirla(p1.y + (p2.y - p0.y) / 6);
    const c2x = p2.x - (p3.x - p1.x) / 6;
    const c2y = sinirla(p2.y - (p3.y - p1.y) / 6);
    d += ` C${c1x.toFixed(1)},${c1y.toFixed(1)} ${c2x.toFixed(1)},${c2y.toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`;
  }
  return d;
}

function olcekle(degerler: number[], gen: number, yuk: number, pay: number, ymin?: number, ymax?: number): Nokta[] {
  const enAz = ymin ?? Math.min(...degerler);
  const enCok = ymax ?? Math.max(...degerler);
  const aralik = enCok - enAz;
  return degerler.map((v, i) => {
    const x = pay + ((gen - 2 * pay) * i) / Math.max(1, degerler.length - 1);
    // Düz seri: hepsi 0 ise tabanda, değilse ortada.
    const oran = aralik ? (v - enAz) / aralik : enCok === 0 ? 0 : 0.5;
    return { x, y: pay + (yuk - 2 * pay) * (1 - oran) };
  });
}

function kimlik(ham: string): string {
  return ham.replace(/[^a-zA-Z0-9_-]/g, '');
}

export function Kivilcim({ degerler, renk, yukseklik = 44 }: { degerler: number[]; renk: string; yukseklik?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const gen = useGenislik(ref, 180);
  const id = kimlik(useId());
  const h = yukseklik;
  const n = degerler.length >= 2 ? olcekle(degerler, gen, h, 3) : [];
  const yol = yumusakYol(n);
  const son = n[n.length - 1];
  return (
    <div ref={ref} className="gb-kivilcim" style={{ height: h }}>
      {n.length > 1 && (
        <svg width={gen} height={h} viewBox={`0 0 ${gen} ${h}`} aria-hidden="true" focusable="false" overflow="visible">
          <defs>
            <linearGradient id={`${id}d`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor={renk} stopOpacity="0.42" />
              <stop offset="1" stopColor={renk} stopOpacity="0" />
            </linearGradient>
            <filter id={`${id}f`} x="-20%" y="-60%" width="140%" height="220%">
              <feGaussianBlur stdDeviation="2.2" />
            </filter>
          </defs>
          <path d={`${yol} L${son.x.toFixed(1)},${h} L${n[0].x.toFixed(1)},${h} Z`} fill={`url(#${id}d)`} />
          <path d={yol} fill="none" stroke={renk} strokeWidth="3" opacity="0.5" filter={`url(#${id}f)`} />
          <path d={yol} fill="none" stroke={renk} strokeWidth="1.8" strokeLinecap="round" />
          <circle cx={son.x} cy={son.y} r="3" fill={renk} className="gb-isik-nokta" style={{ color: renk }} />
        </svg>
      )}
    </div>
  );
}

/** Güzel üst sınır ve adım (0'dan başlayan eksen). */
function eksen(enCok: number): { ust: number; adim: number } {
  if (enCok <= 4) return { ust: 4, adim: 1 };
  const kaba = enCok / 4;
  const us = Math.pow(10, Math.floor(Math.log10(kaba)));
  const adim = [1, 2, 2.5, 5, 10].map((k) => k * us).find((a) => a >= kaba) ?? 10 * us;
  return { ust: Math.ceil(enCok / adim) * adim, adim };
}

export function AlanGrafik({
  bugun,
  dun,
  renk1,
  renk2,
  yukseklik = 210,
  etiket,
}: {
  bugun: (number | null)[];
  dun: number[];
  renk1: string;
  renk2: string;
  yukseklik?: number;
  etiket: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const gen = useGenislik(ref, 460);
  const id = kimlik(useId());
  const sol = 30;
  const alt = 20;
  const ust = 8;
  const gw = Math.max(20, gen - sol - 10);
  const gh = yukseklik - alt - ust;
  const bugunDolu = bugun.filter((v): v is number => v !== null);
  const { ust: ymax, adim } = eksen(Math.max(1, ...dun, ...bugunDolu));
  const xi = (i: number) => sol + (gw * i) / 23;
  const yi = (v: number) => ust + gh * (1 - v / ymax);
  const noktalar = (seri: number[]) => seri.map((v, i) => ({ x: xi(i), y: yi(v) }));
  const dunN = noktalar(dun);
  const bugunN = noktalar(bugunDolu);
  const cizgiler = [];
  for (let v = 0; v <= ymax + 1e-9; v += adim) cizgiler.push(v);
  return (
    <div ref={ref} className="gb-alan" role="img" aria-label={etiket}>
      <svg width={gen} height={yukseklik} viewBox={`0 0 ${gen} ${yukseklik}`} aria-hidden="true" focusable="false">
        <defs>
          <linearGradient id={`${id}d`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor={renk1} stopOpacity="0.42" />
            <stop offset="1" stopColor={renk1} stopOpacity="0" />
          </linearGradient>
          <filter id={`${id}f`}>
            <feGaussianBlur stdDeviation="3" />
          </filter>
        </defs>
        {cizgiler.map((v) => (
          <g key={v}>
            <line x1={sol} x2={sol + gw} y1={yi(v)} y2={yi(v)} className="gb-izgara-cizgi" />
            <text x={sol - 8} y={yi(v) + 3.5} textAnchor="end" className="gb-eksen-yazi">
              {Number.isInteger(v) ? v : v.toFixed(1)}
            </text>
          </g>
        ))}
        {[0, 4, 8, 12, 16, 20].map((s) => (
          <text key={s} x={xi(s)} y={yukseklik - 4} textAnchor="middle" className="gb-eksen-yazi">
            {String(s).padStart(2, '0')}
          </text>
        ))}
        {dunN.length > 1 && (
          <path d={yumusakYol(dunN)} fill="none" stroke={renk2} strokeWidth="2" strokeDasharray="4 5" opacity="0.75" />
        )}
        {bugunN.length > 1 && (
          <>
            <path
              d={`${yumusakYol(bugunN)} L${bugunN[bugunN.length - 1].x.toFixed(1)},${ust + gh} L${bugunN[0].x.toFixed(1)},${ust + gh} Z`}
              fill={`url(#${id}d)`}
            />
            <path d={yumusakYol(bugunN)} fill="none" stroke={renk1} strokeWidth="4" opacity="0.5" filter={`url(#${id}f)`} />
            <path d={yumusakYol(bugunN)} fill="none" stroke={renk1} strokeWidth="2" strokeLinecap="round" />
          </>
        )}
        {bugunN.length > 0 && (
          <circle
            cx={bugunN[bugunN.length - 1].x}
            cy={bugunN[bugunN.length - 1].y}
            r="4"
            fill="#fff"
            stroke={renk1}
            strokeWidth="2"
            className="gb-isik-nokta"
            style={{ color: renk1 }}
          />
        )}
      </svg>
    </div>
  );
}

export const HALKA_RENKLERI = ['#38d1ff', '#2ef596', '#b266ff', '#ff7a2f', '#ffc542', '#3b82f6', '#ff4fd8'];

export function Halka({
  dilimler,
  boyut = 150,
  kalinlik = 16,
  ust,
  alt,
}: {
  dilimler: { deger: number; renk: string }[];
  boyut?: number;
  kalinlik?: number;
  ust: string;
  alt: string;
}) {
  const r = (boyut - kalinlik) / 2 - 4;
  const cevre = 2 * Math.PI * r;
  const toplam = dilimler.reduce((a, d) => a + d.deger, 0);
  let bas = 0;
  const m = boyut / 2;
  return (
    <svg width={boyut} height={boyut} viewBox={`0 0 ${boyut} ${boyut}`} className="gb-halka" aria-hidden="true" focusable="false">
      <circle cx={m} cy={m} r={r} fill="none" stroke="rgb(120 150 255 / 0.09)" strokeWidth={kalinlik} />
      {toplam > 0 &&
        dilimler.map((d, i) => {
          const uz = (cevre * d.deger) / toplam;
          const bosluk = dilimler.length > 1 ? 3 : 0;
          const parca = (
            <circle
              key={i}
              cx={m}
              cy={m}
              r={r}
              fill="none"
              stroke={d.renk}
              strokeWidth={kalinlik}
              strokeDasharray={`${Math.max(uz - bosluk, 0.01).toFixed(1)} ${cevre.toFixed(1)}`}
              strokeDashoffset={(-bas).toFixed(1)}
              transform={`rotate(-90 ${m} ${m})`}
              className="gb-halka-dilim"
              style={{ color: d.renk }}
            />
          );
          bas += uz;
          return parca;
        })}
      <text x={m} y={m + 6} textAnchor="middle" className="gb-halka-ust">
        {ust}
      </text>
      <text x={m} y={m + boyut * 0.16} textAnchor="middle" className="gb-halka-alt">
        {alt}
      </text>
    </svg>
  );
}

/**
 * Faz 11B — günlük seri + plan çizgisi (müşteri "Kalan iş"): gerçek seri dolgulu ve ışıyan, plan kesik çizgi.
 * `plan` içinde `null` olan günler (plan başlamadan önce) çizilmez. x ekseninde `isaret` kadar etiket.
 * Zaman ekseni dilden bağımsız soldan sağa (Arapçada da) — sayı ekseni gibi.
 */
export function SeriGrafik({
  gercek,
  plan,
  etiketler,
  renk1,
  renk2,
  yukseklik = 190,
  etiket,
  isaret = 5,
}: {
  gercek: number[];
  plan?: (number | null)[] | null;
  etiketler: string[];
  renk1: string;
  renk2: string;
  yukseklik?: number;
  etiket: string;
  isaret?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const gen = useGenislik(ref, 460);
  const id = kimlik(useId());
  const sol = 30;
  const alt = 20;
  const ust = 8;
  const n = gercek.length;
  const gw = Math.max(20, gen - sol - 12);
  const gh = yukseklik - alt - ust;
  const planDolu = (plan || []).filter((v): v is number => v !== null && Number.isFinite(v));
  const { ust: ymax, adim } = eksen(Math.max(1, ...gercek, ...planDolu));
  const xi = (i: number) => sol + (gw * i) / Math.max(1, n - 1);
  const yi = (v: number) => ust + gh * (1 - v / ymax);
  const gN = gercek.map((v, i) => ({ x: xi(i), y: yi(v) }));
  const pN = (plan || []).flatMap((v, i) => (v === null || !Number.isFinite(v) ? [] : [{ x: xi(i), y: yi(v) }]));
  const cizgiler: number[] = [];
  for (let v = 0; v <= ymax + 1e-9; v += adim) cizgiler.push(v);
  const sayi = Math.min(isaret, n);
  const isaretler = sayi > 1 ? Array.from({ length: sayi }, (_, k) => Math.round((k * (n - 1)) / (sayi - 1))) : [0];
  // Plan çizgisi doğrusal: yumuşatma gerekmiyor (düz kesik çizgi).
  const planYolu = pN.map((p, i) => `${i ? 'L' : 'M'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
  const son = gN[gN.length - 1];
  return (
    <div ref={ref} className="gb-alan" role="img" aria-label={etiket}>
      <svg width={gen} height={yukseklik} viewBox={`0 0 ${gen} ${yukseklik}`} aria-hidden="true" focusable="false" direction="ltr">
        <defs>
          <linearGradient id={`${id}d`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor={renk1} stopOpacity="0.42" />
            <stop offset="1" stopColor={renk1} stopOpacity="0" />
          </linearGradient>
          <filter id={`${id}f`}>
            <feGaussianBlur stdDeviation="3" />
          </filter>
        </defs>
        {cizgiler.map((v) => (
          <g key={v}>
            <line x1={sol} x2={sol + gw} y1={yi(v)} y2={yi(v)} className="gb-izgara-cizgi" />
            <text x={sol - 8} y={yi(v) + 3.5} textAnchor="end" className="gb-eksen-yazi">
              {Number.isInteger(v) ? v : v.toFixed(1)}
            </text>
          </g>
        ))}
        {isaretler.map((i, k) => (
          <text
            key={`${i}-${k}`}
            x={xi(i)}
            y={yukseklik - 4}
            textAnchor={k === 0 ? 'start' : k === isaretler.length - 1 ? 'end' : 'middle'}
            className="gb-eksen-yazi"
          >
            {etiketler[i] ?? ''}
          </text>
        ))}
        {pN.length > 1 && <path d={planYolu} fill="none" stroke={renk2} strokeWidth="2" strokeDasharray="5 6" opacity="0.8" data-plan-cizgisi="" />}
        {gN.length > 1 && (
          <>
            <path d={`${yumusakYol(gN)} L${son.x.toFixed(1)},${ust + gh} L${gN[0].x.toFixed(1)},${ust + gh} Z`} fill={`url(#${id}d)`} />
            <path d={yumusakYol(gN)} fill="none" stroke={renk1} strokeWidth="4" opacity="0.5" filter={`url(#${id}f)`} />
            <path d={yumusakYol(gN)} fill="none" stroke={renk1} strokeWidth="2" strokeLinecap="round" data-gercek-cizgisi="" />
          </>
        )}
        {son && <circle cx={son.x} cy={son.y} r="4" fill="#fff" stroke={renk1} strokeWidth="2" className="gb-isik-nokta" style={{ color: renk1 }} />}
      </svg>
    </div>
  );
}

/** Faz 11B — tek değerli ilerleme halkası (degrade yay + ışıma; ortada yüzde, altında ad). */
export function IlerlemeHalkasi({
  oran,
  boyut = 104,
  kalinlik = 8,
  renk1,
  renk2,
  ust,
  alt,
}: {
  oran: number | null;
  boyut?: number;
  kalinlik?: number;
  renk1: string;
  renk2: string;
  ust: string;
  alt?: string;
}) {
  const id = kimlik(useId());
  const r = boyut / 2 - kalinlik - 1;
  const cevre = 2 * Math.PI * r;
  const m = boyut / 2;
  const o = oran === null ? 0 : Math.max(0, Math.min(1, oran));
  return (
    <svg width={boyut} height={boyut} viewBox={`0 0 ${boyut} ${boyut}`} className="gb-halka" aria-hidden="true" focusable="false" direction="ltr">
      <defs>
        <linearGradient id={`${id}g`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={renk1} />
          <stop offset="1" stopColor={renk2} />
        </linearGradient>
      </defs>
      <circle cx={m} cy={m} r={r} fill="none" stroke="rgb(255 255 255 / 0.08)" strokeWidth={kalinlik} />
      {o > 0 && (
        <circle
          cx={m}
          cy={m}
          r={r}
          fill="none"
          stroke={`url(#${id}g)`}
          strokeWidth={kalinlik}
          strokeLinecap="round"
          strokeDasharray={`${Math.max(cevre * o, 0.01).toFixed(1)} ${cevre.toFixed(1)}`}
          transform={`rotate(-90 ${m} ${m})`}
          className="gb-halka-dilim"
          style={{ color: renk1 }}
        />
      )}
      <text x={m} y={m + (alt ? 2 : 6)} textAnchor="middle" className="gb-halka-ust gb-halka-ust-kucuk">
        {ust}
      </text>
      {alt && (
        <text x={m} y={m + boyut * 0.2} textAnchor="middle" className="gb-halka-alt">
          {alt.length > 14 ? `${alt.slice(0, 13)}…` : alt}
        </text>
      )}
    </svg>
  );
}
