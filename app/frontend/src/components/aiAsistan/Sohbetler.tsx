import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { EyeOff, Loader2, Trash2, UserRound } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import GuvenliMarkdown from '@/components/asistanlar/GuvenliMarkdown';
import { KART, Rozet, SECIM, Yukleniyor, tarihYaz } from '@/components/aiAsistan/ortak';
import { hataMetni, type Asistan, type AsistanApi, type AsistanMod, type SohbetMesaji, type SohbetOzeti } from '@/lib/aiAsistan';

/**
 * Faz 5A — sohbet kayıtları: liste (süzgeç: hepsi / insana devredilen / bilinmeyen soru içeren /
 * önizleme), döküm, anonimleştirme (iletişim bilgisi + IP özeti silinir, mesajlarda e-posta ve
 * telefon maskelenir) ve silme. Saklama süresi dolan sohbetler liste açılırken silinir.
 */

type Ayrinti = SohbetOzeti & { mesajlar: SohbetMesaji[] };

export default function Sohbetler({ api, asistan, mod }: { api: AsistanApi; asistan: Asistan; mod: AsistanMod }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [durum, setDurum] = useState('hepsi');
  const [sayfa, setSayfa] = useState(1);
  const [veri, setVeri] = useState<{ items: SohbetOzeti[]; toplam: number; sayfa_boyu: number; saklama_gun: number } | null>(null);
  const [secili, setSecili] = useState<Ayrinti | null>(null);
  const [yukleniyor, setYukleniyor] = useState(false);

  const yukle = useCallback(async () => {
    try {
      setVeri(await api.sohbetler(asistan.id, durum, sayfa));
    } catch (e) {
      toast.error(hataMetni(t, e));
      setVeri({ items: [], toplam: 0, sayfa_boyu: 50, saklama_gun: asistan.saklama_gun });
    }
  }, [api, asistan.id, asistan.saklama_gun, durum, sayfa, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const ac = async (s: SohbetOzeti) => {
    setYukleniyor(true);
    try {
      setSecili(await api.sohbet(asistan.id, s.id));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setYukleniyor(false);
    }
  };

  const anonimlestir = async () => {
    if (!secili || !window.confirm(t('aiAsistan.sohbet.anonimOnay'))) return;
    try {
      await api.anonimlestir(asistan.id, secili.id);
      setSecili(await api.sohbet(asistan.id, secili.id));
      await yukle();
      toast.success(t('aiAsistan.sohbet.anonimlestirildi'));
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const sil = async () => {
    if (!secili || !window.confirm(t('aiAsistan.sohbet.silOnay'))) return;
    try {
      await api.sohbetSil(asistan.id, secili.id);
      setSecili(null);
      await yukle();
      toast.success(t('aiAsistan.sohbet.silindi'));
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  if (!veri) return <Yukleniyor />;
  const sayfaSayisi = Math.max(1, Math.ceil(veri.toplam / veri.sayfa_boyu));
  const talepBaglantisi = mod === 'yonetici' ? '/admin?sekme=tickets' : '/client?sekme=tickets';

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <select
            className={`${SECIM} w-auto`}
            value={durum}
            onChange={(e) => {
              setDurum(e.target.value);
              setSayfa(1);
            }}
            aria-label={t('aiAsistan.sohbet.suzgec')}
            data-testid="ai-sohbet-suzgec"
          >
            {['hepsi', 'devredildi', 'bilinmeyen', 'onizleme'].map((d) => (
              <option key={d} value={d}>
                {t(`aiAsistan.sohbet.durumlar.${d}`)}
              </option>
            ))}
          </select>
          <span className="text-xs text-muted-foreground">{t('aiAsistan.sohbet.saklama', { sayi: veri.saklama_gun })}</span>
        </div>
        {veri.items.length === 0 ? (
          <p className="text-sm text-muted-foreground" data-testid="ai-sohbet-bos">
            {t('aiAsistan.sohbet.bos')}
          </p>
        ) : (
          <ul className="space-y-2" data-testid="ai-sohbet-listesi">
            {veri.items.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  onClick={() => void ac(s)}
                  className={`${KART} w-full p-3 text-start transition-colors hover:bg-white/[0.06] ${secili?.id === s.id ? 'ring-1 ring-purple-400' : ''}`}
                  data-sohbet-id={s.id}
                  data-durum={s.durum}
                >
                  <p className="line-clamp-2 text-sm">{s.ilk_mesaj || t('aiAsistan.sohbet.ilkMesajYok')}</p>
                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
                    <span>{tarihYaz(s.son_mesaj_at, dil)}</span>
                    <span>· {t('aiAsistan.sohbet.mesajSayisi', { sayi: s.mesaj_sayisi })}</span>
                    {s.durum === 'devredildi' && (
                      <Rozet renk="border-amber-400/30 bg-amber-500/10 text-amber-200">
                        <UserRound className="h-3 w-3" aria-hidden="true" />
                        {t('aiAsistan.sohbet.devredildi')}
                      </Rozet>
                    )}
                    {s.bilinmeyen_sayisi > 0 && <Rozet>{t('aiAsistan.sohbet.bilinmeyen', { sayi: s.bilinmeyen_sayisi })}</Rozet>}
                    <Rozet>{t(`aiAsistan.sohbet.kaynak.${s.kaynak}`)}</Rozet>
                    {s.koken && <span dir="ltr">{s.koken}</span>}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
        {sayfaSayisi > 1 && (
          <div className="flex items-center gap-2 text-sm">
            <Button type="button" variant="ghost" size="sm" disabled={sayfa <= 1} onClick={() => setSayfa(sayfa - 1)}>
              ‹
            </Button>
            <span>
              {sayfa} / {sayfaSayisi}
            </span>
            <Button type="button" variant="ghost" size="sm" disabled={sayfa >= sayfaSayisi} onClick={() => setSayfa(sayfa + 1)}>
              ›
            </Button>
          </div>
        )}
      </div>

      <div>
        {yukleniyor && <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" aria-hidden="true" />}
        {!yukleniyor && !secili && <p className="text-sm text-muted-foreground">{t('aiAsistan.sohbet.sec')}</p>}
        {!yukleniyor && secili && (
          <div className={`${KART} space-y-4 p-4`} data-testid="ai-sohbet-dokum" data-sohbet-id={secili.id}>
            {secili.devir && (
              <div className="rounded-xl border border-amber-400/30 bg-amber-500/10 p-3 text-sm" data-testid="ai-sohbet-devir">
                <p className="font-semibold text-amber-100">{t('aiAsistan.sohbet.devirBaslik')}</p>
                {secili.anonim ? (
                  <p className="text-xs text-amber-100/80">{t('aiAsistan.sohbet.anonim')}</p>
                ) : (
                  <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
                    <dt className="text-muted-foreground">{t('aiAsistan.sohbet.ad')}</dt>
                    <dd>{secili.devir.ad || '—'}</dd>
                    <dt className="text-muted-foreground">{t('aiAsistan.sohbet.eposta')}</dt>
                    <dd dir="ltr">{secili.devir.eposta || '—'}</dd>
                    <dt className="text-muted-foreground">{t('aiAsistan.sohbet.telefon')}</dt>
                    <dd dir="ltr">{secili.devir.telefon || '—'}</dd>
                    {secili.devir.not && (
                      <>
                        <dt className="text-muted-foreground">{t('aiAsistan.sohbet.not')}</dt>
                        <dd className="whitespace-pre-wrap">{secili.devir.not}</dd>
                      </>
                    )}
                  </dl>
                )}
                {secili.devir.talep_id && (
                  <a href={talepBaglantisi} className="mt-2 inline-block text-xs text-purple-200 underline" data-testid="ai-sohbet-talep">
                    {t('aiAsistan.sohbet.talep', { no: secili.devir.talep_id })}
                  </a>
                )}
                {secili.devir.aday_id && <p className="mt-2 text-xs text-purple-200">{t('aiAsistan.sohbet.aday', { no: secili.devir.aday_id })}</p>}
              </div>
            )}
            <ol className="space-y-2">
              {secili.mesajlar.map((m) => (
                <li key={m.id} className={`flex ${m.rol === 'kullanici' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[90%] rounded-2xl px-3 py-2 text-sm ${m.rol === 'kullanici' ? 'bg-purple-500/20' : 'border border-white/10 bg-white/[0.04]'}`}>
                    {m.rol === 'kullanici' ? <p className="whitespace-pre-wrap break-words">{m.metin}</p> : <GuvenliMarkdown metin={m.metin} />}
                    <div className="mt-1 flex flex-wrap gap-1.5 text-[10.5px] text-muted-foreground">
                      <span>{tarihYaz(m.zaman, dil)}</span>
                      {m.bilinmiyor && <span className="text-amber-200">· {t('aiAsistan.sohbet.bilmedi')}</span>}
                      {m.kaynaklar.map((k) => (
                        <span key={`${k.no}-${k.kaynak_id}`}>
                          · [{k.no}] {k.baslik}
                        </span>
                      ))}
                    </div>
                  </div>
                </li>
              ))}
            </ol>
            <div className="flex flex-wrap gap-2 border-t border-white/10 pt-3">
              {!secili.anonim && (
                <Button type="button" variant="outline" size="sm" className="gap-1.5 !bg-transparent" onClick={() => void anonimlestir()} data-testid="ai-sohbet-anonimlestir">
                  <EyeOff className="h-4 w-4" aria-hidden="true" />
                  {t('aiAsistan.sohbet.anonimlestir')}
                </Button>
              )}
              <Button type="button" variant="ghost" size="sm" className="gap-1.5 text-red-300" onClick={() => void sil()} data-testid="ai-sohbet-sil">
                <Trash2 className="h-4 w-4" aria-hidden="true" />
                {t('aiAsistan.sil')}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
