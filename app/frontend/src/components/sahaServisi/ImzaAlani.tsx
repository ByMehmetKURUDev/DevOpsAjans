import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Eraser } from 'lucide-react';

/**
 * Faz 6S — yerinde müşteri imzası: tuval (canvas) üzerine parmak/kalem/fare ile çizim → PNG.
 * Saydam zemin + koyu çizgi (PDF'te beyaz kâğıtta okunur). Sayfa kaymasın diye `touch-action: none`.
 * Satır içi betik yok; dış kütüphane yok (Pointer Events).
 */
export default function ImzaAlani({ onDegis, devreDisi }: { onDegis: (png: string | null) => void; devreDisi?: boolean }) {
  const { t } = useTranslation();
  const tuval = useRef<HTMLCanvasElement | null>(null);
  const ciziyor = useRef(false);
  const son = useRef<{ x: number; y: number } | null>(null);
  const [bos, setBos] = useState(true);

  const hazirla = useCallback(() => {
    const c = tuval.current;
    if (!c) return;
    const oran = Math.min(window.devicePixelRatio || 1, 2);
    const { width, height } = c.getBoundingClientRect();
    c.width = Math.max(1, Math.round(width * oran));
    c.height = Math.max(1, Math.round(height * oran));
    const ctx = c.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(oran, 0, 0, oran, 0, 0);
    ctx.lineWidth = 2.6;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.strokeStyle = '#111827';
    setBos(true);
    onDegis(null);
  }, [onDegis]);

  useEffect(() => {
    hazirla();
    // Yalnız ilk çizimde boyutlandır (döndürmede çizim silinmesin diye yeniden kurulmuyor).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const nokta = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  };

  const basla = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (devreDisi) return;
    e.preventDefault();
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      /* yoksay */
    }
    ciziyor.current = true;
    son.current = nokta(e);
    const ctx = e.currentTarget.getContext('2d');
    if (ctx && son.current) {
      ctx.beginPath();
      ctx.arc(son.current.x, son.current.y, 1.2, 0, Math.PI * 2);
      ctx.fillStyle = '#111827';
      ctx.fill();
    }
  };

  const ciz = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!ciziyor.current || devreDisi) return;
    e.preventDefault();
    const ctx = e.currentTarget.getContext('2d');
    const p = nokta(e);
    if (ctx && son.current) {
      ctx.beginPath();
      ctx.moveTo(son.current.x, son.current.y);
      ctx.lineTo(p.x, p.y);
      ctx.stroke();
    }
    son.current = p;
    if (bos) setBos(false);
  };

  const bitir = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!ciziyor.current) return;
    ciziyor.current = false;
    son.current = null;
    try {
      onDegis(e.currentTarget.toDataURL('image/png'));
      setBos(false);
    } catch {
      onDegis(null);
    }
  };

  return (
    <div className="space-y-2">
      <div className="relative overflow-hidden rounded-xl border border-white/15 bg-white">
        <canvas
          ref={tuval}
          className="block h-44 w-full cursor-crosshair touch-none sm:h-52"
          style={{ touchAction: 'none' }}
          onPointerDown={basla}
          onPointerMove={ciz}
          onPointerUp={bitir}
          onPointerCancel={bitir}
          onPointerLeave={(e) => ciziyor.current && bitir(e)}
          aria-label={t('sahaServisi.imza.tuval')}
          role="img"
          data-testid="saha-imza-tuval"
        />
        {bos && (
          <span className="pointer-events-none absolute inset-x-0 bottom-3 text-center text-xs text-zinc-400" aria-hidden="true">
            {t('sahaServisi.imza.buraya')}
          </span>
        )}
        <span className="pointer-events-none absolute inset-x-6 bottom-8 border-b border-dashed border-zinc-300" aria-hidden="true" />
      </div>
      <button
        type="button"
        onClick={hazirla}
        disabled={devreDisi}
        className="inline-flex min-h-[40px] items-center gap-1.5 rounded-lg px-3 text-sm text-muted-foreground hover:bg-white/[0.06] hover:text-white"
        data-testid="saha-imza-temizle"
      >
        <Eraser className="h-4 w-4" aria-hidden="true" />
        {t('sahaServisi.imza.temizle')}
      </button>
    </div>
  );
}
