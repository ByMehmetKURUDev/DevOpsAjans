import { Fragment, type ReactNode } from 'react';

import { parcala } from '@/components/mesajlar/BaglantiliMetin';

/**
 * Asistan yanıtındaki markdown'ın KÜÇÜK ve GÜVENLİ çizicisi.
 *
 * GÜVENLİK: HTML hiçbir zaman çizilmiyor — `dangerouslySetInnerHTML` yok,
 * markdown kütüphanesi yok (ham HTML'i geçirenler var). Metin satır satır
 * okunup React öğelerine çevriliyor; `<script>` ekranda yazı olarak görünür.
 * Bağlantı yalnız `http://` / `https://` adresinden kuruluyor (`parcala`),
 * `rel="noopener noreferrer nofollow"` + yeni sekme.
 *
 * Desteklenen: paragraf (satır sonları korunur), başlık (#… → kalın satır),
 * madde ve numaralı liste, alıntı (>), yatay çizgi (---), kod bloğu (```),
 * tablo satırları (| … |, eş aralıklı blok olarak), satır içi **kalın**,
 * *eğik*, `kod` ve [metin](https://…) bağlantısı. Gerisi düz metin.
 */

type Blok =
  | { tur: 'paragraf'; satirlar: string[] }
  | { tur: 'baslik'; metin: string }
  | { tur: 'liste'; sirali: boolean; baslangic: number; maddeler: string[] }
  | { tur: 'alinti'; satirlar: string[] }
  | { tur: 'kod'; metin: string }
  | { tur: 'cizgi' };

const MADDE = /^\s*[-*+•]\s+(.*)$/;
const SIRALI = /^\s*(\d{1,3})[.)]\s+(.*)$/;
const BASLIK = /^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$/;
const CIZGI = /^\s{0,3}([-*_])(\s*\1){2,}\s*$/;
const CIT = /^\s{0,3}(```|~~~)/;
const TABLO = /^\s*\|.*\|\s*$/;

export function bloklaraAyir(metin: string): Blok[] {
  const satirlar = (metin || '').replace(/\r\n?/g, '\n').split('\n');
  const bloklar: Blok[] = [];
  let i = 0;
  while (i < satirlar.length) {
    const satir = satirlar[i];
    const cit = satir.match(CIT);
    if (cit) {
      const kod: string[] = [];
      i += 1;
      while (i < satirlar.length && !satirlar[i].trim().startsWith(cit[1])) kod.push(satirlar[i++]);
      i += 1; // kapanış çiti (yoksa metnin sonu)
      bloklar.push({ tur: 'kod', metin: kod.join('\n') });
      continue;
    }
    if (!satir.trim()) {
      i += 1;
      continue;
    }
    if (TABLO.test(satir)) {
      const tablo: string[] = [];
      while (i < satirlar.length && TABLO.test(satirlar[i])) tablo.push(satirlar[i++].trim());
      bloklar.push({ tur: 'kod', metin: tablo.join('\n') });
      continue;
    }
    if (CIZGI.test(satir)) {
      bloklar.push({ tur: 'cizgi' });
      i += 1;
      continue;
    }
    const baslik = satir.match(BASLIK);
    if (baslik) {
      bloklar.push({ tur: 'baslik', metin: baslik[1] });
      i += 1;
      continue;
    }
    if (MADDE.test(satir) || SIRALI.test(satir)) {
      const sirali = !MADDE.test(satir);
      const ilk = satir.match(SIRALI);
      const maddeler: string[] = [];
      while (i < satirlar.length) {
        const s = satirlar[i];
        const m = sirali ? s.match(SIRALI) : s.match(MADDE);
        if (m) {
          maddeler.push(sirali ? m[2] : m[1]);
        } else if (s.trim() && /^\s{2,}\S/.test(s) && maddeler.length) {
          // Girintili devam satırı: önceki maddeye eklenir.
          maddeler[maddeler.length - 1] += `\n${s.trim()}`;
        } else {
          break;
        }
        i += 1;
      }
      bloklar.push({ tur: 'liste', sirali, baslangic: ilk ? Number(ilk[1]) : 1, maddeler });
      continue;
    }
    if (/^\s*>/.test(satir)) {
      const alinti: string[] = [];
      while (i < satirlar.length && /^\s*>/.test(satirlar[i])) alinti.push(satirlar[i++].replace(/^\s*>\s?/, ''));
      bloklar.push({ tur: 'alinti', satirlar: alinti });
      continue;
    }
    const paragraf: string[] = [];
    while (
      i < satirlar.length &&
      satirlar[i].trim() &&
      !CIT.test(satirlar[i]) &&
      !BASLIK.test(satirlar[i]) &&
      !MADDE.test(satirlar[i]) &&
      !SIRALI.test(satirlar[i]) &&
      !TABLO.test(satirlar[i]) &&
      !/^\s*>/.test(satirlar[i])
    ) {
      paragraf.push(satirlar[i++]);
    }
    if (!paragraf.length) {
      // Hiçbir kurala uymayan tek satır (savunma): düz paragraf.
      paragraf.push(satirlar[i++]);
    }
    bloklar.push({ tur: 'paragraf', satirlar: paragraf });
  }
  return bloklar;
}

const BAGLANTI_SINIFI = 'underline decoration-dotted underline-offset-2 break-all hover:opacity-80';

function guvenliAdres(adres: string): string | null {
  try {
    const u = new URL(adres);
    return u.protocol === 'http:' || u.protocol === 'https:' ? u.toString() : null;
  } catch {
    return null;
  }
}

/** Düz metin + çıplak http(s) adresleri bağlantı. */
function adresli(metin: string, anahtar: string): ReactNode[] {
  return parcala(metin).map((p, i) =>
    p.tur === 'baglanti' ? (
      <a key={`${anahtar}-${i}`} href={p.deger} target="_blank" rel="noopener noreferrer nofollow" className={BAGLANTI_SINIFI}>
        {p.deger}
      </a>
    ) : (
      <Fragment key={`${anahtar}-${i}`}>{p.deger}</Fragment>
    )
  );
}

// Sıra önemli: kod → bağlantı → kalın → eğik.
const SATIR_ICI = /(`[^`\n]+`)|(\[[^\]\n]{1,300}\]\((https?:\/\/[^\s)]+)\))|(\*\*[^*\n]+\*\*|__[^_\n]+__)|(\*[^*\s][^*\n]*\*)/g;

export function satirIci(metin: string, anahtar = 's'): ReactNode[] {
  const sonuc: ReactNode[] = [];
  let son = 0;
  let n = 0;
  for (const m of metin.matchAll(SATIR_ICI)) {
    const bas = m.index ?? 0;
    if (bas > son) sonuc.push(...adresli(metin.slice(son, bas), `${anahtar}-${n++}`));
    const k = `${anahtar}-${n++}`;
    if (m[1]) {
      sonuc.push(
        <code key={k} className="rounded bg-white/10 px-1 py-0.5 font-mono text-[0.85em]" dir="ltr">
          {m[1].slice(1, -1)}
        </code>
      );
    } else if (m[2]) {
      const adres = guvenliAdres(m[3]);
      const yazi = m[2].slice(1, m[2].indexOf(']('));
      sonuc.push(
        adres ? (
          <a key={k} href={adres} target="_blank" rel="noopener noreferrer nofollow" className={BAGLANTI_SINIFI}>
            {yazi}
          </a>
        ) : (
          <Fragment key={k}>{m[2]}</Fragment>
        )
      );
    } else if (m[4]) {
      sonuc.push(
        <strong key={k} className="font-semibold text-foreground">
          {satirIci(m[4].slice(2, -2), k)}
        </strong>
      );
    } else if (m[5]) {
      sonuc.push(<em key={k}>{satirIci(m[5].slice(1, -1), k)}</em>);
    }
    son = bas + m[0].length;
  }
  if (son < metin.length) sonuc.push(...adresli(metin.slice(son), `${anahtar}-${n++}`));
  return sonuc;
}

function satirli(satirlar: string[], anahtar: string): ReactNode[] {
  return satirlar.flatMap((s, i) => [
    ...(i ? [<br key={`${anahtar}-br-${i}`} />] : []),
    <Fragment key={`${anahtar}-${i}`}>{satirIci(s, `${anahtar}-${i}`)}</Fragment>,
  ]);
}

export default function GuvenliMarkdown({ metin, className = '' }: { metin: string; className?: string }) {
  const bloklar = bloklaraAyir(metin);
  return (
    <div className={`space-y-2 break-words leading-relaxed ${className}`} dir="auto" data-guvenli-md>
      {bloklar.map((b, i) => {
        const k = `b${i}`;
        switch (b.tur) {
          case 'baslik':
            return (
              <p key={k} className="pt-1 font-semibold text-foreground">
                {satirIci(b.metin, k)}
              </p>
            );
          case 'liste': {
            const ogeler = b.maddeler.map((m, j) => (
              <li key={`${k}-${j}`}>{satirli(m.split('\n'), `${k}-${j}`)}</li>
            ));
            return b.sirali ? (
              <ol key={k} start={b.baslangic} className="list-decimal space-y-1 ps-5">
                {ogeler}
              </ol>
            ) : (
              <ul key={k} className="list-disc space-y-1 ps-5">
                {ogeler}
              </ul>
            );
          }
          case 'alinti':
            return (
              <blockquote key={k} className="border-s-2 border-white/20 ps-3 text-muted-foreground">
                {satirli(b.satirlar, k)}
              </blockquote>
            );
          case 'kod':
            return (
              <pre
                key={k}
                className="overflow-x-auto whitespace-pre rounded-lg border border-white/10 bg-black/30 p-3 font-mono text-xs"
                dir="ltr"
                data-md-kod
              >
                <code>{b.metin}</code>
              </pre>
            );
          case 'cizgi':
            return <hr key={k} className="border-white/10" />;
          default:
            return <p key={k}>{satirli(b.satirlar, k)}</p>;
        }
      })}
    </div>
  );
}
