import { useCallback, useEffect, useRef, useState } from 'react';
import { Archive, ArchiveRestore, ClipboardList, LifeBuoy, Loader2, MessageSquareText, MessagesSquare, Plus, Search, Trash2 } from 'lucide-react';
import { useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { useYoklama } from '@/hooks/useYoklama';
import { hazirCevaplar, type HazirCevap } from '@/lib/destek';
import {
  goreveCevir,
  hazirCevabiDoldur,
  konusmaAc,
  konusmaDetayi,
  konusmaGuncelle,
  konusmaSil,
  konusmalariGetir,
  ozetGetir,
  talebeCevir,
  type Konusma,
  type KonusmaDetayi,
  type Mesaj,
} from '@/lib/mesajlar';
import KonusmaListesi, { konusmaAdi } from '@/components/mesajlar/KonusmaListesi';
import SohbetAkisi, { hataMetni } from '@/components/mesajlar/SohbetAkisi';

const LISTE_ARALIGI = 10000;
type DurumSuzgeci = 'acik' | 'arsiv' | '';

function urlKonusmasi(arama: string): number | null {
  try {
    const k = Number(new URLSearchParams(arama).get('konusma'));
    return Number.isInteger(k) && k > 0 ? k : null;
  } catch {
    return null;
  }
}

/**
 * Faz 2G — yönetici paneli › Müşteri sohbetleri: bütün hesapların konuşmaları
 * (son mesaja göre), arama, okunmamış süzgeci, hazır cevap, konuşmadan destek
 * talebi ya da göreve çevirme (mevcut talep/görev akışlarıyla), arşiv ve silme
 * (çöp kutusuna).
 */
export default function MesajYonetimi({ onOkunmamis }: { onOkunmamis?: (sayi: number) => void }) {
  const { t } = useTranslation();
  const location = useLocation();
  const [liste, setListe] = useState<Konusma[] | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [secili, setSecili] = useState<number | null>(() => urlKonusmasi(location.search));
  const [detay, setDetay] = useState<KonusmaDetayi | null>(null);
  const [ara, setAra] = useState('');
  const [aranan, setAranan] = useState('');
  const [durum, setDurum] = useState<DurumSuzgeci>('acik');
  const [okunmamis, setOkunmamis] = useState(false);
  const [form, setForm] = useState<{ eposta: string; konu: string } | null>(null);
  const [gorevProjesi, setGorevProjesi] = useState<string>('');
  const [cevaplar, setCevaplar] = useState<HazirCevap[]>([]);
  const [islem, setIslem] = useState<string | null>(null);
  const imzaRef = useRef('');
  const onOkunmamisRef = useRef(onOkunmamis);
  onOkunmamisRef.current = onOkunmamis;

  // Arama kutusu: yazmayı bitirince (400 ms).
  useEffect(() => {
    const z = window.setTimeout(() => setAranan(ara.trim()), 400);
    return () => window.clearTimeout(z);
  }, [ara]);

  const listeyiYukle = useCallback(async () => {
    const l = await konusmalariGetir('admin', { durum, q: aranan, okunmamis });
    setListe(l);
    setHata(null);
    return l;
  }, [durum, aranan, okunmamis]);

  useEffect(() => {
    listeyiYukle().catch((e) => setHata(hataMetni(t, e)));
  }, [listeyiYukle, t]);

  useEffect(() => {
    const k = urlKonusmasi(location.search);
    if (k) setSecili(k);
  }, [location.search]);

  useEffect(() => {
    hazirCevaplar()
      .then(setCevaplar)
      .catch(() => setCevaplar([]));
  }, []);

  const detayiYukle = useCallback(async (id: number) => {
    try {
      const d = await konusmaDetayi(id);
      setDetay(d);
      setGorevProjesi((eski) => eski || String(d.proje_id ?? d.projeler[0]?.id ?? ''));
    } catch (e) {
      setDetay(null);
      toast.error(hataMetni(t, e));
    }
  }, [t]);

  useEffect(() => {
    setDetay(null);
    setGorevProjesi('');
    if (secili) void detayiYukle(secili);
  }, [secili, detayiYukle]);

  useYoklama(
    async () => {
      const o = await ozetGetir('admin');
      onOkunmamisRef.current?.(o.okunmamis);
      const imza = `${o.son_mesaj_id}:${o.okunmamis}:${o.konusma_sayisi}:${o.degisiklik}`;
      if (imza !== imzaRef.current) {
        const ilk = imzaRef.current === '';
        imzaRef.current = imza;
        if (!ilk) await listeyiYukle();
      }
    },
    { aralik: LISTE_ARALIGI, anahtar: `${durum}|${aranan}|${okunmamis}` }
  );

  const degisti = () => {
    void listeyiYukle().catch(() => {});
    void ozetGetir('admin')
      .then((o) => onOkunmamisRef.current?.(o.okunmamis))
      .catch(() => {});
  };

  const calistir = async (ad: string, fn: () => Promise<void>) => {
    setIslem(ad);
    try {
      await fn();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setIslem(null);
    }
  };

  const yeniKonusma = () =>
    calistir('yeni', async () => {
      if (!form) return;
      const k = await konusmaAc('admin', { hesap_email: form.eposta.trim(), konu: form.konu.trim() });
      setForm(null);
      await listeyiYukle();
      setSecili(k.id);
    });

  const arsivDegistir = () =>
    calistir('arsiv', async () => {
      if (!detay) return;
      const yeni = await konusmaGuncelle(detay.id, { durum: detay.durum === 'arsiv' ? 'acik' : 'arsiv' });
      setDetay({ ...detay, durum: yeni.durum });
      degisti();
    });

  const sil = () =>
    calistir('sil', async () => {
      if (!detay || !window.confirm(t('mesajlar.konusmaSilOnay'))) return;
      await konusmaSil(detay.id);
      toast.success(t('mesajlar.konusmaSilindi'));
      setSecili(null);
      degisti();
    });

  const talep = (m: Mesaj) =>
    calistir(`talep-${m.id}`, async () => {
      if (!secili) return;
      const y = await talebeCevir(secili, m.id);
      toast.success(t('mesajlar.talepAcildi', { no: y.talep_id }));
    });

  const gorev = (m: Mesaj) =>
    calistir(`gorev-${m.id}`, async () => {
      if (!secili) return;
      if (!gorevProjesi) {
        toast.error(t('mesajlar.projeSecin'));
        return;
      }
      const y = await goreveCevir(secili, Number(gorevProjesi), m.id);
      toast.success(t('mesajlar.gorevEklendi', { baslik: y.baslik }));
    });

  const baslik = detay ? konusmaAdi(detay, t) : liste?.find((k) => k.id === secili)?.konu ?? '…';
  const hesap = detay ? (detay.hesap_adi ? `${detay.hesap_adi} · ${detay.hesap_email}` : detay.hesap_email) : undefined;

  return (
    <div className="space-y-4" data-mesaj-yonetimi>
      <div>
        <h2 className="flex items-center gap-2 text-2xl font-bold">
          <MessagesSquare className="h-6 w-6 text-purple-400" aria-hidden="true" /> {t('mesajlar.yonetimBaslik')}
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">{t('mesajlar.yonetimAciklama')}</p>
      </div>
      <div className="cam-kart overflow-hidden rounded-2xl border border-white/10 bg-white/[0.03]">
        <div className="grid h-[72vh] min-h-[460px] md:grid-cols-[320px_minmax(0,1fr)]">
          <aside className={`${secili ? 'hidden md:flex' : 'flex'} min-h-0 flex-col border-white/10 md:border-e`}>
            <div className="space-y-2 border-b border-white/10 p-3">
              <div className="relative">
                <Search className="pointer-events-none absolute start-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
                <input
                  value={ara}
                  onChange={(e) => setAra(e.target.value)}
                  placeholder={t('mesajlar.ara')}
                  aria-label={t('mesajlar.ara')}
                  className="h-9 w-full rounded-lg border border-white/10 bg-black/30 ps-8 pe-2 text-sm"
                  data-testid="mesaj-ara"
                />
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <select
                  value={durum}
                  onChange={(e) => setDurum(e.target.value as DurumSuzgeci)}
                  aria-label={t('mesajlar.durum')}
                  className="h-8 rounded-md border border-white/10 bg-black/40 px-2 text-xs"
                  data-testid="mesaj-durum"
                >
                  <option value="acik">{t('mesajlar.durumAdi.acik')}</option>
                  <option value="arsiv">{t('mesajlar.durumAdi.arsiv')}</option>
                  <option value="">{t('mesajlar.hepsi')}</option>
                </select>
                <label className="inline-flex items-center gap-1.5 text-muted-foreground">
                  <input type="checkbox" checked={okunmamis} onChange={(e) => setOkunmamis(e.target.checked)} data-testid="mesaj-okunmamis" />
                  {t('mesajlar.okunmamisSuzgec')}
                </label>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="ms-auto h-8 !bg-transparent border-white/20 text-xs"
                  onClick={() => setForm((f) => (f ? null : { eposta: '', konu: '' }))}
                >
                  <Plus className="me-1 h-3.5 w-3.5" aria-hidden="true" /> {t('mesajlar.yeniKonusma')}
                </Button>
              </div>
              {form && (
                <div className="space-y-2 pt-1">
                  <input
                    value={form.eposta}
                    onChange={(e) => setForm({ ...form, eposta: e.target.value })}
                    type="email"
                    placeholder={t('mesajlar.hesapEposta')}
                    aria-label={t('mesajlar.hesapEposta')}
                    className="h-9 w-full rounded-lg border border-white/10 bg-black/30 px-2 text-sm"
                  />
                  <input
                    value={form.konu}
                    onChange={(e) => setForm({ ...form, konu: e.target.value })}
                    maxLength={200}
                    placeholder={`${t('mesajlar.konu')} — ${t('mesajlar.genel')}`}
                    aria-label={t('mesajlar.konu')}
                    className="h-9 w-full rounded-lg border border-white/10 bg-black/30 px-2 text-sm"
                  />
                  <div className="flex justify-end gap-2">
                    <Button type="button" size="sm" variant="ghost" onClick={() => setForm(null)}>
                      {t('mesajlar.iptal')}
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      disabled={islem === 'yeni' || !form.eposta.includes('@')}
                      onClick={() => void yeniKonusma()}
                      className="bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0"
                    >
                      {t('mesajlar.baslat')}
                    </Button>
                  </div>
                </div>
              )}
            </div>
            {liste === null ? (
              hata ? (
                <p className="px-4 py-8 text-center text-sm text-muted-foreground">{hata}</p>
              ) : (
                <p className="flex items-center justify-center px-4 py-8 text-sm text-muted-foreground">
                  <Loader2 className="me-2 h-4 w-4 animate-spin" aria-hidden="true" /> {t('mesajlar.yukleniyor')}
                </p>
              )
            ) : (
              <KonusmaListesi liste={liste} secili={secili} onSec={setSecili} yonetici />
            )}
          </aside>
          <section className={`${secili ? 'flex' : 'hidden md:flex'} min-h-0 flex-col`}>
            {secili ? (
              <SohbetAkisi
                key={secili}
                taraf="admin"
                konusmaId={secili}
                baslik={baslik}
                altBaslik={hesap}
                onGeri={() => setSecili(null)}
                onDegisti={degisti}
                ustAraclar={
                  detay && (
                    <div className="flex shrink-0 items-center gap-1">
                      {detay.projeler.length > 0 && (
                        <select
                          value={gorevProjesi}
                          onChange={(e) => setGorevProjesi(e.target.value)}
                          className="hidden h-8 max-w-[10rem] rounded-md border border-white/10 bg-black/40 px-1.5 text-xs lg:block"
                          aria-label={t('mesajlar.gorevProjesi')}
                          title={t('mesajlar.gorevProjesi')}
                        >
                          {detay.projeler.map((p) => (
                            <option key={p.id} value={p.id}>
                              {p.baslik}
                            </option>
                          ))}
                        </select>
                      )}
                      <button
                        type="button"
                        onClick={() => void arsivDegistir()}
                        disabled={islem === 'arsiv'}
                        className="inline-flex h-8 w-8 items-center justify-center rounded-lg hover:bg-white/10"
                        aria-label={detay.durum === 'arsiv' ? t('mesajlar.yenidenAc') : t('mesajlar.arsivle')}
                        title={detay.durum === 'arsiv' ? t('mesajlar.yenidenAc') : t('mesajlar.arsivle')}
                        data-testid="konusma-arsiv"
                      >
                        {detay.durum === 'arsiv' ? <ArchiveRestore className="h-4 w-4" aria-hidden="true" /> : <Archive className="h-4 w-4" aria-hidden="true" />}
                      </button>
                      <button
                        type="button"
                        onClick={() => void sil()}
                        disabled={islem === 'sil'}
                        className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-red-300 hover:bg-red-500/10"
                        aria-label={t('mesajlar.konusmaSil')}
                        title={t('mesajlar.konusmaSil')}
                        data-testid="konusma-sil"
                      >
                        <Trash2 className="h-4 w-4" aria-hidden="true" />
                      </button>
                    </div>
                  )
                }
                mesajAraclari={(m) =>
                  m.yazan_rol === 'client' ? (
                    <div className="mt-1.5 flex flex-wrap gap-3 border-t border-white/10 pt-1 text-[11px] text-muted-foreground">
                      <button
                        type="button"
                        onClick={() => void talep(m)}
                        disabled={islem === `talep-${m.id}`}
                        className="inline-flex items-center gap-1 hover:text-foreground"
                        data-testid="mesaj-talep"
                      >
                        <LifeBuoy className="h-3 w-3" aria-hidden="true" /> {t('mesajlar.talebeCevir')}
                      </button>
                      {detay && detay.projeler.length > 0 && (
                        <button
                          type="button"
                          onClick={() => void gorev(m)}
                          disabled={islem === `gorev-${m.id}`}
                          className="inline-flex items-center gap-1 hover:text-foreground"
                          data-testid="mesaj-gorev"
                        >
                          <ClipboardList className="h-3 w-3" aria-hidden="true" /> {t('mesajlar.goreveCevir')}
                        </button>
                      )}
                    </div>
                  ) : null
                }
                yazmaAraclari={(ekle) =>
                  cevaplar.length > 0 ? (
                    <label className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
                      <MessageSquareText className="h-4 w-4 shrink-0" aria-hidden="true" />
                      <select
                        value=""
                        onChange={(e) => {
                          const id = Number(e.target.value);
                          if (!id || !secili) return;
                          hazirCevabiDoldur(secili, id)
                            .then((s) => ekle(s.metin))
                            .catch((err) => toast.error(hataMetni(t, err)));
                        }}
                        className="h-8 max-w-full rounded-md border border-white/10 bg-black/40 px-2 text-xs text-foreground"
                        aria-label={t('mesajlar.hazirCevap')}
                        data-testid="mesaj-hazir-cevap"
                      >
                        <option value="">{t('mesajlar.hazirCevap')}</option>
                        {cevaplar.map((h) => (
                          <option key={h.id} value={h.id}>
                            {h.baslik}
                          </option>
                        ))}
                      </select>
                    </label>
                  ) : null
                }
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
