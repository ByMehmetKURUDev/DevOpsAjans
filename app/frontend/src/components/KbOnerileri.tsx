import { useEffect, useState } from 'react';
import { Lightbulb } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { MakaleGorunumu } from '@/components/DestekYardim';
import { makaleGetir, makaleOnerisi, type Makale, type MakaleOzeti } from '@/lib/destek';

/**
 * Talep açarken "Bu makaleler yardımcı olabilir" (Faz 2C).
 *
 * Konu yazıldıkça (400 ms bekleyerek) bilgi bankasından en çok 3 öneri.
 * Makale aynı yerde açılıyor; müşteri formdan ayrılmıyor.
 */
export default function KbOnerileri({ konu }: { konu: string }) {
  const { t, i18n } = useTranslation();
  const [oneriler, setOneriler] = useState<MakaleOzeti[]>([]);
  const [okunan, setOkunan] = useState<Makale | null>(null);

  useEffect(() => {
    const metin = konu.trim();
    if (metin.length < 3) {
      setOneriler([]);
      return;
    }
    let iptal = false;
    const zamanlayici = window.setTimeout(() => {
      makaleOnerisi(metin, i18n.language)
        .then((s) => {
          if (!iptal) setOneriler(s);
        })
        .catch(() => {
          if (!iptal) setOneriler([]);
        });
    }, 400);
    return () => {
      iptal = true;
      window.clearTimeout(zamanlayici);
    };
  }, [konu, i18n.language]);

  if (okunan) {
    return (
      <div className="rounded-xl border border-purple-400/30 bg-purple-500/10 p-4">
        <MakaleGorunumu makale={okunan} geri={() => setOkunan(null)} />
      </div>
    );
  }

  if (oneriler.length === 0) return null;

  return (
    <div className="rounded-xl border border-amber-400/30 bg-amber-500/10 p-3" data-testid="kb-oneriler" aria-live="polite">
      <p className="flex items-center gap-2 text-sm font-medium text-amber-100">
        <Lightbulb className="h-4 w-4" aria-hidden="true" /> {t('yardim.kb.oneriBaslik')}
      </p>
      <ul className="mt-2 space-y-1">
        {oneriler.map((m) => (
          <li key={m.id}>
            <button
              type="button"
              className="text-left text-sm text-amber-50 underline decoration-amber-300/40 underline-offset-4 hover:decoration-amber-200"
              onClick={() => {
                makaleGetir(m.id, i18n.language)
                  .then(setOkunan)
                  .catch(() => setOkunan(null));
              }}
              data-testid={`kb-oneri-${m.id}`}
            >
              {m.baslik}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
