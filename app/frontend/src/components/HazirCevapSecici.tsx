import { useEffect, useState } from 'react';
import { MessageSquareText } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { hazirCevapUygula, hazirCevaplar, type HazirCevap } from '@/lib/destek';

/**
 * Yanıt kutusunun üstündeki hazır cevap seçicisi (yalnız ajans, Faz 2C).
 *
 * Seçilen cevabın {musteri_adi}, {talep_no}, {konu} değişkenleri sunucuda
 * bu talebe göre dolduruluyor; sonuç yanıt kutusuna ekleniyor (gönderilmiyor —
 * yönetici son hâlini görüp düzeltebilsin).
 */
export default function HazirCevapSecici({ ticketId, onEkle }: { ticketId: number; onEkle: (metin: string) => void }) {
  const { t } = useTranslation();
  const [liste, setListe] = useState<HazirCevap[]>([]);
  const [secim, setSecim] = useState('');

  useEffect(() => {
    hazirCevaplar()
      .then(setListe)
      .catch(() => setListe([]));
  }, []);

  if (liste.length === 0) return null;

  return (
    <label className="flex items-center gap-2 text-xs text-muted-foreground">
      <MessageSquareText className="h-4 w-4 shrink-0" aria-hidden="true" />
      <select
        value={secim}
        onChange={(e) => {
          const id = Number(e.target.value);
          setSecim('');
          if (!id) return;
          hazirCevapUygula(id, ticketId)
            .then((s) => onEkle(s.metin))
            .catch(() => toast.error(t('yardim.hazirCevap.uygulanamadi')));
        }}
        className="h-8 max-w-full rounded-md border border-white/10 bg-black/40 px-2 text-xs text-white"
        aria-label={t('yardim.hazirCevap.sec')}
        data-testid={`hazir-cevap-sec-${ticketId}`}
      >
        <option value="">{t('yardim.hazirCevap.sec')}</option>
        {liste.map((h) => (
          <option key={h.id} value={h.id}>
            {h.baslik}
          </option>
        ))}
      </select>
    </label>
  );
}
