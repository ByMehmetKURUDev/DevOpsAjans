import { useCallback, useEffect, useRef, useState } from 'react';
import { Eraser } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';

/**
 * İsteğe bağlı el çizimi imza (fare / parmak / kalem). Saydam zeminli PNG
 * olarak dışarı veriliyor (`data:image/png;base64,…`); sunucu Pillow ile
 * yeniden kodluyor ve boş tuvali imza saymıyor.
 *
 * `touch-action: none`: mobilde çizerken sayfa kaymasın. Çizgi rengi her
 * zaman koyu (kâğıt PDF'e basılıyor); tuval zemini açık.
 * Metinler `sozlesme` ek paketinde.
 */
const GENISLIK = 600;
const YUKSEKLIK = 200;

export default function ImzaTuvali({ onChange }: { onChange: (png: string | null) => void }) {
  const { t } = useTranslation();
  const tuval = useRef<HTMLCanvasElement | null>(null);
  const ciziyor = useRef(false);
  const son = useRef<{ x: number; y: number } | null>(null);
  const [dolu, setDolu] = useState(false);
  const doluRef = useRef(false);

  useEffect(() => {
    const c = tuval.current;
    if (!c) return;
    const ctx = c.getContext('2d');
    if (!ctx) return;
    ctx.lineWidth = 3;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.strokeStyle = '#1a0b2e';
  }, []);

  const nokta = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const c = tuval.current!;
    const r = c.getBoundingClientRect();
    return { x: ((e.clientX - r.left) / r.width) * GENISLIK, y: ((e.clientY - r.top) / r.height) * YUKSEKLIK };
  };

  const basla = (e: React.PointerEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    ciziyor.current = true;
    son.current = nokta(e);
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      /* eski tarayıcı */
    }
  };

  const ciz = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!ciziyor.current) return;
    const ctx = tuval.current?.getContext('2d');
    const p = nokta(e);
    if (!ctx || !son.current) return;
    ctx.beginPath();
    ctx.moveTo(son.current.x, son.current.y);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
    son.current = p;
    if (!doluRef.current) {
      doluRef.current = true;
      setDolu(true);
    }
  };

  const bitir = useCallback(() => {
    if (!ciziyor.current) return;
    ciziyor.current = false;
    son.current = null;
    const c = tuval.current;
    if (c && doluRef.current) onChange(c.toDataURL('image/png'));
  }, [onChange]);

  const temizle = () => {
    const c = tuval.current;
    c?.getContext('2d')?.clearRect(0, 0, GENISLIK, YUKSEKLIK);
    doluRef.current = false;
    setDolu(false);
    onChange(null);
  };

  return (
    <div className="space-y-2" data-testid="imza-tuvali">
      <canvas
        ref={tuval}
        width={GENISLIK}
        height={YUKSEKLIK}
        role="img"
        aria-label={t('sozlesme.imza.tuvalEtiketi')}
        className="block h-auto w-full rounded-xl border border-dashed border-white/25 bg-white"
        style={{ touchAction: 'none', aspectRatio: `${GENISLIK} / ${YUKSEKLIK}`, maxWidth: GENISLIK, cursor: 'crosshair' }}
        onPointerDown={basla}
        onPointerMove={ciz}
        onPointerUp={bitir}
        onPointerLeave={bitir}
        onPointerCancel={bitir}
      />
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
        <span>{dolu ? t('sozlesme.imza.cizildi') : t('sozlesme.imza.tuvalIpucu')}</span>
        <Button type="button" size="sm" variant="ghost" className="gap-1" onClick={temizle} disabled={!dolu}
          data-testid="imza-temizle">
          <Eraser className="h-3.5 w-3.5" aria-hidden="true" />
          {t('sozlesme.imza.temizle')}
        </Button>
      </div>
    </div>
  );
}
