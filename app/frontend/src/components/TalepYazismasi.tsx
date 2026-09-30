import { useCallback, useEffect, useRef, useState } from 'react';
import { Loader2, Send } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { mesajGonder, yazismayiGetir, type TalepMesaji } from '@/lib/talepler';

/**
 * Bir talebin altındaki yazışma. Hem müşteri panelinde hem yönetim
 * panelinde aynı bileşen kullanılıyor: iki taraf da aynı akışı
 * görsün, biri diğerinde olmayan bir mesaj göstermesin.
 *
 * `bizKimiz` yalnızca hizalama ve etiket için; mesajın kime ait
 * yazıldığını sunucu belirliyor.
 */

interface Props {
  ticketId: number;
  bizKimiz: 'musteri' | 'ajans';
}

function saat(deger?: string | null): string {
  if (!deger) return '';
  const t = new Date(deger);
  if (Number.isNaN(t.getTime())) return '';
  return t.toLocaleString('tr-TR', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function TalepYazismasi({ ticketId, bizKimiz }: Props) {
  const { t } = useTranslation();
  const [mesajlar, setMesajlar] = useState<TalepMesaji[]>([]);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [hata, setHata] = useState(false);
  const [taslak, setTaslak] = useState('');
  const [gonderiliyor, setGonderiliyor] = useState(false);
  const sonRef = useRef<HTMLDivElement>(null);

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    try {
      const yazisma = await yazismayiGetir(ticketId);
      setMesajlar(yazisma.mesajlar);
      setHata(false);
    } catch (e) {
      console.error(e);
      setHata(true);
    } finally {
      setYukleniyor(false);
    }
  }, [ticketId]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  useEffect(() => {
    // Yeni mesaj gelince sona kaydır; ilk açılışta da en alttan başla
    // ki son konuşulan görünsün.
    sonRef.current?.scrollIntoView({ block: 'nearest' });
  }, [mesajlar.length]);

  async function gonder() {
    const metin = taslak.trim();
    if (!metin) return;
    setGonderiliyor(true);
    try {
      const yeni = await mesajGonder(ticketId, metin);
      setMesajlar((eski) => [...eski, yeni]);
      setTaslak('');
    } catch (e) {
      console.error(e);
      toast.error(t('talep.gonderilemedi'));
    } finally {
      setGonderiliyor(false);
    }
  }

  if (yukleniyor) {
    return (
      <div className="flex items-center justify-center py-6">
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" aria-hidden="true" />
      </div>
    );
  }

  if (hata) {
    return <p className="py-4 text-sm text-muted-foreground">{t('talep.yuklenemedi')}</p>;
  }

  return (
    <div className="mt-3 space-y-3">
      <div className="max-h-80 space-y-2 overflow-y-auto pr-1">
        {mesajlar.map((m) => {
          const bizimMi = m.yazan === bizKimiz;
          return (
            <div
              key={`${m.id}-${m.created_at || ''}`}
              className={`flex ${bizimMi ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[85%] rounded-xl px-3 py-2 text-sm ${
                  bizimMi
                    ? 'bg-primary/15 text-foreground'
                    : 'border border-white/10 bg-white/[0.04] text-foreground'
                }`}
              >
                <p className="mb-1 text-[10px] uppercase tracking-wider text-muted-foreground">
                  {m.yazan === 'ajans' ? t('talep.ajans') : m.yazan_ad || t('talep.musteri')}
                  {m.created_at ? ` • ${saat(m.created_at)}` : ''}
                </p>
                <p className="whitespace-pre-wrap break-words">{m.mesaj}</p>
              </div>
            </div>
          );
        })}
        <div ref={sonRef} />
      </div>

      <div className="flex items-end gap-2">
        <Textarea
          value={taslak}
          onChange={(e) => setTaslak(e.target.value)}
          rows={2}
          placeholder={t('talep.yaz')}
          className="min-h-0 flex-1 text-sm"
        />
        <Button
          size="sm"
          className="gap-2"
          disabled={gonderiliyor || !taslak.trim()}
          onClick={() => void gonder()}
        >
          {gonderiliyor ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
          {t('talep.gonder')}
        </Button>
      </div>
    </div>
  );
}
