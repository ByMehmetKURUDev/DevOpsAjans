import { useState } from 'react';
import { Check, Copy, MailCheck, ShieldAlert, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import type { OlusturYaniti } from '@/lib/imzaliIslem';

/**
 * Yeni üretilen imzalı bağlantıyı bir kez gösterir (kopyala düğmesiyle).
 *
 * Sunucu jetonun yalnız özetini tutuyor; bu kutu kapanınca bağlantı bir
 * daha gösterilemiyor. Uyarı bu yüzden kutunun içinde, göze batacak yerde.
 */
export default function BaglantiKutusu({ yanit, onKapat }: { yanit: OlusturYaniti; onKapat: () => void }) {
  const { t } = useTranslation();
  const [kopyalandi, setKopyalandi] = useState(false);

  const kopyala = async () => {
    try {
      await navigator.clipboard.writeText(yanit.baglanti);
      setKopyalandi(true);
      setTimeout(() => setKopyalandi(false), 2000);
    } catch {
      // Pano izni yoksa metin seçili kalsın; elle kopyalanır.
      const alan = document.getElementById(`islem-baglanti-${yanit.islem.id}`) as HTMLInputElement | null;
      alan?.select();
    }
  };

  return (
    <div
      className="cam-kart rounded-2xl border border-emerald-400/30 bg-emerald-500/[0.06] p-5"
      role="status"
      data-testid="islem-baglanti-kutusu"
    >
      <div className="flex items-start justify-between gap-3">
        <p className="font-semibold">{t('islem.yonetim.baglantiHazir')}</p>
        <button
          type="button"
          onClick={onKapat}
          className="rounded-md p-1 text-muted-foreground hover:text-foreground"
          aria-label={t('islem.kapat')}
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
      <p className="mt-1 break-words text-sm text-muted-foreground">
        {yanit.islem.baslik} · {yanit.islem.alici_eposta}
      </p>
      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        <input
          id={`islem-baglanti-${yanit.islem.id}`}
          readOnly
          value={yanit.baglanti}
          onFocus={(e) => e.currentTarget.select()}
          className="h-10 min-w-0 flex-1 rounded-md border border-white/10 bg-black/30 px-3 font-mono text-xs"
          data-testid="islem-baglanti"
        />
        <Button type="button" onClick={() => void kopyala()} className="gap-2" data-testid="islem-kopyala">
          {kopyalandi ? <Check className="h-4 w-4" aria-hidden="true" /> : <Copy className="h-4 w-4" aria-hidden="true" />}
          {kopyalandi ? t('islem.yonetim.kopyalandi') : t('islem.yonetim.kopyala')}
        </Button>
      </div>
      <p className="mt-3 flex items-start gap-2 text-xs text-amber-300">
        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        {t('islem.yonetim.birKezUyari')}
      </p>
      {yanit.eposta_gonderildi && (
        <p className="mt-2 flex items-center gap-2 text-xs text-emerald-300">
          <MailCheck className="h-4 w-4 shrink-0" aria-hidden="true" />
          {t('islem.yonetim.epostaGitti', { eposta: yanit.islem.alici_eposta })}
        </p>
      )}
    </div>
  );
}
