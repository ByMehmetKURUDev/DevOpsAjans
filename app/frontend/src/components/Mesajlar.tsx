import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Loader2, MessagesSquare, Plus } from 'lucide-react';
import { useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { useYoklama } from '@/hooks/useYoklama';
import { konusmaAc, konusmalariGetir, ozetGetir, type Konusma } from '@/lib/mesajlar';
import KonusmaListesi, { konusmaAdi } from '@/components/mesajlar/KonusmaListesi';
import SohbetAkisi, { hataMetni } from '@/components/mesajlar/SohbetAkisi';

/** Sohbet açıkken liste/özet yoklaması (diğer konuşmaların okunmamışları). */
const LISTE_ARALIGI = 10000;

function urlKonusmasi(arama: string): number | null {
  try {
    const k = Number(new URLSearchParams(arama).get('konusma'));
    return Number.isInteger(k) && k > 0 ? k : null;
  } catch {
    return null;
  }
}

function genisEkran(): boolean {
  try {
    return window.matchMedia('(min-width: 768px)').matches;
  } catch {
    return true;
  }
}

interface Props {
  /** Yeni konuşmayı projeye bağlamak için (hesabın projeleri). */
  projeler?: { id: number; baslik: string }[];
  /** Sekme rozeti: toplam okunmamış. */
  onOkunmamis?: (sayi: number) => void;
}

/**
 * Faz 2G — müşteri paneli › Mesajlar. Solda konuşma listesi, sağda akış;
 * mobilde tek sütun (liste ↔ sohbet). `?konusma=<id>` (bildirim bağlantısı)
 * o konuşmayı açar.
 */
export default function Mesajlar({ projeler = [], onOkunmamis }: Props) {
  const { t } = useTranslation();
  const location = useLocation();
  const [liste, setListe] = useState<Konusma[] | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [secili, setSecili] = useState<number | null>(() => urlKonusmasi(location.search));
  const [form, setForm] = useState<{ konu: string; proje: string } | null>(null);
  const [aciliyor, setAciliyor] = useState(false);
  const imzaRef = useRef('');
  const onOkunmamisRef = useRef(onOkunmamis);
  onOkunmamisRef.current = onOkunmamis;

  const listeyiYukle = useCallback(async () => {
    const l = await konusmalariGetir('client');
    setListe(l);
    setHata(null);
    onOkunmamisRef.current?.(l.reduce((t, k) => t + (k.okunmamis || 0), 0));
    return l;
  }, []);

  useEffect(() => {
    listeyiYukle()
      .then((l) => {
        // Geniş ekranda (iki sütun) en son konuşma kendiliğinden açılsın.
        setSecili((s) => s ?? (genisEkran() && l.length ? l[0].id : null));
      })
      .catch((e) => setHata(hataMetni(t, e)));
  }, [listeyiYukle, t]);

  // Bildirim bağlantısı (aynı sayfadayken de): ?konusma=<id>
  useEffect(() => {
    const k = urlKonusmasi(location.search);
    if (k) setSecili(k);
  }, [location.search]);

  // Diğer konuşmaların okunmamışları ve yeni konuşmalar: ucuz özet, değişince liste.
  useYoklama(
    async () => {
      const o = await ozetGetir('client');
      onOkunmamisRef.current?.(o.okunmamis);
      const imza = `${o.son_mesaj_id}:${o.okunmamis}:${o.konusma_sayisi}:${o.degisiklik}`;
      if (imza !== imzaRef.current) {
        const ilk = imzaRef.current === '';
        imzaRef.current = imza;
        if (!ilk) await listeyiYukle();
      }
    },
    { aralik: LISTE_ARALIGI }
  );

  const seciliKonusma = useMemo(() => liste?.find((k) => k.id === secili) ?? null, [liste, secili]);
  const projeAdi = (id?: number | null) => projeler.find((p) => p.id === id)?.baslik;

  const yeniKonusma = async () => {
    if (!form || !form.konu.trim()) {
      toast.error(t('mesajlar.hata.konu_gerekli'));
      return;
    }
    setAciliyor(true);
    try {
      const k = await konusmaAc('client', { konu: form.konu.trim(), proje_id: form.proje ? Number(form.proje) : null });
      setForm(null);
      await listeyiYukle();
      setSecili(k.id);
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setAciliyor(false);
    }
  };

  return (
    <div className="space-y-4" data-mesajlar>
      <div>
        <h3 className="flex items-center gap-2 text-lg font-semibold">
          <MessagesSquare className="h-5 w-5 text-purple-400" aria-hidden="true" /> {t('mesajlar.baslik')}
        </h3>
        <p className="mt-1 text-sm text-muted-foreground">{t('mesajlar.aciklama')}</p>
      </div>
      <div className="cam-kart overflow-hidden rounded-2xl border border-white/10 bg-white/[0.03]">
        <div className="grid h-[70vh] min-h-[440px] md:grid-cols-[300px_minmax(0,1fr)]">
          <aside className={`${secili ? 'hidden md:flex' : 'flex'} min-h-0 flex-col border-white/10 md:border-e`} data-mesaj-listesi>
            <div className="flex items-center justify-between gap-2 border-b border-white/10 px-3 py-2.5">
              <span className="text-sm font-semibold">{t('mesajlar.konusmalar')}</span>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-8 !bg-transparent border-white/20 text-xs"
                onClick={() => setForm((f) => (f ? null : { konu: '', proje: '' }))}
                data-testid="yeni-konusma"
              >
                <Plus className="me-1 h-3.5 w-3.5" aria-hidden="true" /> {t('mesajlar.yeniKonusma')}
              </Button>
            </div>
            {form && (
              <div className="space-y-2 border-b border-white/10 p-3" data-yeni-konusma-formu>
                <label className="block text-xs text-muted-foreground">
                  {t('mesajlar.konu')}
                  <input
                    value={form.konu}
                    onChange={(e) => setForm({ ...form, konu: e.target.value })}
                    maxLength={200}
                    placeholder={t('mesajlar.konuYer')}
                    className="mt-1 h-9 w-full rounded-lg border border-white/10 bg-black/30 px-2 text-sm text-foreground"
                    data-testid="yeni-konusma-konu"
                  />
                </label>
                {projeler.length > 0 && (
                  <label className="block text-xs text-muted-foreground">
                    {t('mesajlar.proje')}
                    <select
                      value={form.proje}
                      onChange={(e) => setForm({ ...form, proje: e.target.value })}
                      className="mt-1 h-9 w-full rounded-lg border border-white/10 bg-black/40 px-2 text-sm text-foreground"
                    >
                      <option value="">{t('mesajlar.projeYok')}</option>
                      {projeler.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.baslik}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                <div className="flex justify-end gap-2">
                  <Button type="button" size="sm" variant="ghost" onClick={() => setForm(null)}>
                    {t('mesajlar.iptal')}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    disabled={aciliyor}
                    onClick={() => void yeniKonusma()}
                    className="bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0"
                    data-testid="yeni-konusma-olustur"
                  >
                    {aciliyor && <Loader2 className="me-1 h-3.5 w-3.5 animate-spin" aria-hidden="true" />}
                    {t('mesajlar.olustur')}
                  </Button>
                </div>
              </div>
            )}
            {liste === null ? (
              hata ? (
                <p className="px-4 py-8 text-center text-sm text-muted-foreground">{hata}</p>
              ) : (
                <p className="flex items-center justify-center px-4 py-8 text-sm text-muted-foreground">
                  <Loader2 className="me-2 h-4 w-4 animate-spin" aria-hidden="true" /> {t('mesajlar.yukleniyor')}
                </p>
              )
            ) : (
              <KonusmaListesi liste={liste} secili={secili} onSec={setSecili} />
            )}
          </aside>
          <section className={`${secili ? 'flex' : 'hidden md:flex'} min-h-0 flex-col`} data-mesaj-paneli>
            {secili ? (
              <SohbetAkisi
                key={secili}
                taraf="client"
                konusmaId={secili}
                baslik={seciliKonusma ? konusmaAdi(seciliKonusma, t) : '…'}
                altBaslik={
                  seciliKonusma?.durum === 'arsiv'
                    ? t('mesajlar.durumAdi.arsiv')
                    : projeAdi(seciliKonusma?.proje_id) ?? undefined
                }
                onGeri={() => setSecili(null)}
                onDegisti={() => void listeyiYukle().catch(() => {})}
              />
            ) : (
              <div className="flex h-full items-center justify-center p-6 text-center text-sm text-muted-foreground">
                {t('mesajlar.konusmaSec')}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
