import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, Send } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { KART, METIN_ALANI, Not, Rozet, Yukleniyor } from '@/components/hukuk/ortak';
import { hataMetni, type HukukApi, type Mesaj } from '@/lib/hukuk';

/**
 * Faz 6H — müvekkil portalından gelen mesajlar (ajansın gelen kutusuna DÜŞMEZ) ve büronun yanıtı (müvekkil
 * kendi bağlantısında görür; e-posta gönderilmez).
 */
export default function Mesajlar({ api, onOkundu }: { api: HukukApi; onOkundu: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [liste, setListe] = useState<Mesaj[] | null>(null);
  const [secili, setSecili] = useState<number | null>(null);
  const [metin, setMetin] = useState('');
  const [gonderiliyor, setGonderiliyor] = useState(false);

  const yukle = useCallback(async () => {
    try {
      setListe((await api.mesajlar()).items);
    } catch (e) {
      toast.error(hataMetni(t, e));
      setListe([]);
    }
  }, [api, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const gruplar = useMemo(() => {
    const m = new Map<number, { ad: string; mesajlar: Mesaj[]; okunmamis: number; son: string }>();
    for (const x of liste || []) {
      const g = m.get(x.muvekkil_id) || { ad: x.muvekkil_ad || `#${x.muvekkil_id}`, mesajlar: [], okunmamis: 0, son: '' };
      g.mesajlar.push(x);
      if (x.yon === 'muvekkil' && !x.okundu) g.okunmamis += 1;
      g.son = x.created_at || g.son;
      m.set(x.muvekkil_id, g);
    }
    return [...m.entries()].sort((a, b) => (b[1].son > a[1].son ? 1 : -1));
  }, [liste]);

  const ac = async (id: number) => {
    setSecili(id);
    const g = gruplar.find(([k]) => k === id)?.[1];
    if (g && g.okunmamis) {
      try {
        await api.okundu(id);
        await yukle();
        onOkundu();
      } catch {
        /* okundu işareti gecikebilir */
      }
    }
  };

  const gonder = async () => {
    if (secili === null || !metin.trim()) return;
    setGonderiliyor(true);
    try {
      await api.mesajYaz({ muvekkil_id: secili, metin: metin.trim() });
      setMetin('');
      toast.success(t('hukuk.mesaj.gonderildi'));
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setGonderiliyor(false);
    }
  };

  const zaman = (iso: string | null) => {
    if (!iso) return '';
    try {
      return new Intl.DateTimeFormat(dil, { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Europe/Istanbul' }).format(new Date(iso));
    } catch {
      return iso;
    }
  };

  const konusma = gruplar.find(([k]) => k === secili)?.[1];
  return (
    <div className="space-y-4" data-testid="hukuk-mesajlar">
      <Not>{t('hukuk.mesaj.aciklama')}</Not>
      {liste === null ? (
        <Yukleniyor />
      ) : gruplar.length === 0 ? (
        <div className={`${KART} p-6 text-center text-sm text-muted-foreground`}>{t('hukuk.mesaj.bos')}</div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,280px)_minmax(0,1fr)]">
          <ul className={`${KART} space-y-1 p-3`} data-testid="hukuk-mesaj-gruplar">
            {gruplar.map(([id, g]) => (
              <li key={id}>
                <button
                  type="button"
                  onClick={() => void ac(id)}
                  className={`flex w-full items-center gap-2 rounded-lg px-2 py-2 text-start text-sm hover:bg-white/[0.05] ${secili === id ? 'bg-white/[0.07]' : ''}`}
                  data-muvekkil-id={id}
                >
                  <span className="min-w-0 flex-1 truncate">{g.ad}</span>
                  {g.okunmamis > 0 && <Rozet renk="border-amber-400/40 bg-amber-500/15 text-amber-200">{t('hukuk.mesaj.yeniMesaj')} {g.okunmamis}</Rozet>}
                </button>
              </li>
            ))}
          </ul>
          <div className={`${KART} flex min-h-[320px] flex-col p-4`}>
            {!konusma ? (
              <p className="m-auto text-sm text-muted-foreground">{t('hukuk.mesaj.secin')}</p>
            ) : (
              <>
                <ul className="flex-1 space-y-2 overflow-y-auto" data-testid="hukuk-mesaj-akis">
                  {konusma.mesajlar.map((m) => (
                    <li key={m.id} className={`max-w-[85%] rounded-xl px-3 py-2 text-sm ${m.yon === 'buro' ? 'ms-auto bg-blue-500/20' : 'bg-white/[0.06]'}`} data-yon={m.yon}>
                      <p className="mb-0.5 text-[10px] text-muted-foreground">
                        {m.yon === 'buro' ? t('hukuk.mesaj.burodan') : t('hukuk.mesaj.muvekkilden')} · {zaman(m.created_at)}
                      </p>
                      <p className="whitespace-pre-wrap break-words">{m.metin}</p>
                    </li>
                  ))}
                </ul>
                <div className="mt-3 flex items-end gap-2">
                  <textarea className={`${METIN_ALANI} min-h-[64px]`} value={metin} maxLength={4000} onChange={(e) => setMetin(e.target.value)} placeholder={t('hukuk.mesaj.yanit')} aria-label={t('hukuk.mesaj.yanit')} data-testid="hukuk-mesaj-yanit" />
                  <Button onClick={() => void gonder()} disabled={gonderiliyor || !metin.trim()} className="gap-1" data-testid="hukuk-mesaj-gonder">
                    {gonderiliyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Send className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />}
                    {t('hukuk.mesaj.gonder')}
                  </Button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
