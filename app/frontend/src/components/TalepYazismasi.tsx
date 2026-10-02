import { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { Loader2, Paperclip, Send } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { getAPIBaseURL } from '@/lib/config';
import { ekIndirmeAdresi, mesajGonder, yazismayiGetir, type TalepMesaji } from '@/lib/talepler';
import { ekliLazy } from '@/i18n/ekliLazy';

// Faz 2C: ajans tarafında hazır cevap seçicisi — ayrı parça, müşteri paneline inmez.
const HazirCevapSecici = ekliLazy('yardim', () => import('@/components/HazirCevapSecici'));
// Faz 4W: talebin özel alanları — ayrı parça (tanım yoksa hiçbir şey çizmez).
const OzelAlanlarBolumu = ekliLazy('ozelAlanlar', () => import('@/components/OzelAlanlarBolumu'));

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

  // Faz 2F: e-postayla gelen ek — imzalı, 15 dakikalık adresle indirilir.
  async function ekiIndir(ekId: number) {
    try {
      const yol = await ekIndirmeAdresi(ticketId, ekId);
      const a = document.createElement('a');
      a.href = `${getAPIBaseURL()}${yol}`;
      a.rel = 'noopener';
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (e) {
      console.error(e);
      toast.error(t('talep.yuklenemedi'));
    }
  }

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
      <Suspense fallback={null}>
        <OzelAlanlarBolumu varlik="destek" kimlik={ticketId} mod={bizKimiz === 'ajans' ? 'yonetici' : 'musteri'} />
      </Suspense>
      <div className="max-h-80 space-y-2 overflow-y-auto pr-1">
        {mesajlar.map((m) => {
          // Kuralın otomatik cevabı ajans tarafında görünür.
          const taraf = m.yazan === 'otomatik' ? 'ajans' : m.yazan;
          const bizimMi = taraf === bizKimiz;
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
                  {m.yazan === 'otomatik'
                    ? t('talep.otomatikYanit')
                    : m.yazan === 'ajans'
                      ? t('talep.ajans')
                      : m.yazan_ad || t('talep.musteri')}
                  {m.created_at ? ` • ${saat(m.created_at)}` : ''}
                </p>
                <p className="whitespace-pre-wrap break-words">{m.mesaj}</p>
                {m.ekler && m.ekler.length > 0 ? (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {m.ekler.map((ek) => (
                      <button
                        key={ek.id}
                        type="button"
                        onClick={() => void ekiIndir(ek.id)}
                        aria-label={t('talep.ekIndir', { ad: ek.ad })}
                        title={t('talep.ekIndir', { ad: ek.ad })}
                        className="inline-flex max-w-full items-center gap-1 rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 text-[11px] text-muted-foreground hover:border-white/30 hover:text-foreground"
                      >
                        <Paperclip className="h-3 w-3 shrink-0" aria-hidden="true" />
                        <span className="truncate">{ek.ad}</span>
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            </div>
          );
        })}
        <div ref={sonRef} />
      </div>

      {bizKimiz === 'ajans' ? (
        <Suspense fallback={null}>
          <HazirCevapSecici
            ticketId={ticketId}
            onEkle={(metin) => setTaslak((eski) => (eski.trim() ? `${eski.trimEnd()}\n\n${metin}` : metin))}
          />
        </Suspense>
      ) : null}

      <div className="flex items-end gap-2">
        <Textarea
          value={taslak}
          onChange={(e) => setTaslak(e.target.value)}
          rows={2}
          placeholder={t('talep.yaz')}
          className="min-h-0 flex-1 text-sm"
          data-testid={`talep-yanit-${ticketId}`}
        />
        <Button
          size="sm"
          className="gap-2"
          disabled={gonderiliyor || !taslak.trim()}
          onClick={() => void gonder()}
          data-testid={`talep-gonder-${ticketId}`}
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
