import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, BarChart3, CalendarClock, Copy, FlaskConical, Loader2, Pause, Play, Plus, RefreshCw, Save, Send, Trash2, Users } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import BlokDuzenleyici from '@/components/epostaPazarlama/BlokDuzenleyici';
import {
  Alan,
  Anahtar,
  Bos,
  DIS_DUGME,
  DURUM_RENGI,
  GIRDI,
  KART,
  Rozet,
  SECIM,
  Yukleniyor,
  sayiYaz,
  yereldenIso,
} from '@/components/epostaPazarlama/ortak';
import {
  hataMetni,
  tarihYaz,
  yuzde,
  type Kampanya,
  type KitleOzeti,
  type Liste,
  type Meta,
  type PazarlamaApi,
  type Rapor,
  type Segment,
} from '@/lib/epostaPazarlama';
import { yerTutucuOrnekleri } from '@/lib/epostaSablonlari';

type Gorunum = { tur: 'liste' } | { tur: 'duzenle'; id: number } | { tur: 'rapor'; id: number };

/** Faz 5M — kampanyalar: liste, düzenleyici (kitle, A/B, bloklar, test, zamanla/gönder) ve rapor. */
export default function Kampanyalar({ api, meta }: { api: PazarlamaApi; meta: Meta }) {
  const [gorunum, setGorunum] = useState<Gorunum>({ tur: 'liste' });
  if (gorunum.tur === 'duzenle') return <Duzenleyici api={api} meta={meta} id={gorunum.id} geri={() => setGorunum({ tur: 'liste' })} rapor={(id) => setGorunum({ tur: 'rapor', id })} />;
  if (gorunum.tur === 'rapor') return <RaporGorunumu api={api} id={gorunum.id} geri={() => setGorunum({ tur: 'liste' })} />;
  return <KampanyaListesi api={api} ac={(k) => setGorunum(k.durum === 'taslak' ? { tur: 'duzenle', id: k.id } : { tur: 'rapor', id: k.id })} />;
}

function KampanyaListesi({ api, ac }: { api: PazarlamaApi; ac: (k: Kampanya) => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [kampanyalar, setKampanyalar] = useState<Kampanya[] | null>(null);
  const [ad, setAd] = useState('');
  const yukle = useCallback(async () => {
    try {
      setKampanyalar((await api.kampanyalar()).items);
    } catch (e) {
      toast.error(hataMetni(t, e));
      setKampanyalar([]);
    }
  }, [api, t]);
  useEffect(() => {
    void yukle();
  }, [yukle]);
  const olustur = async () => {
    try {
      const k = await api.kampanyaEkle({ ad: ad.trim(), konu: ad.trim(), dil: (dil || 'tr').slice(0, 2) });
      setAd('');
      ac(k);
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };
  if (kampanyalar === null) return <Yukleniyor />;
  return (
    <div className="space-y-4" data-testid="ep-kampanyalar">
      <div className={`${KART} flex flex-col gap-2 p-4 sm:flex-row`}>
        <input
          className={GIRDI}
          value={ad}
          onChange={(e) => setAd(e.target.value)}
          placeholder={t('epostaPazarlama.kampanya.yeniAd')}
          aria-label={t('epostaPazarlama.kampanya.yeniAd')}
          data-testid="ep-kampanya-ad"
        />
        <Button size="sm" onClick={() => void olustur()} disabled={!ad.trim()} className="shrink-0 gap-1.5" data-testid="ep-kampanya-yeni">
          <Plus className="h-4 w-4" aria-hidden="true" /> {t('epostaPazarlama.kampanya.yeni')}
        </Button>
      </div>
      {kampanyalar.length === 0 ? (
        <Bos>{t('epostaPazarlama.kampanya.bos')}</Bos>
      ) : (
        <ul className="space-y-2" data-testid="ep-kampanya-listesi">
          {kampanyalar.map((k) => (
            <li key={k.id} className={`${KART} flex flex-col gap-2 p-3 sm:flex-row sm:items-center sm:justify-between`} data-kampanya={k.ad}>
              <div className="min-w-0">
                <p className="truncate font-medium">{k.ad}</p>
                <p className="truncate text-xs text-muted-foreground">
                  {k.konu || '—'} · {tarihYaz(k.bitis_at || k.baslangic_at || k.zamanlanan_at, dil)}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <Rozet renk={DURUM_RENGI[k.durum]} testid="ep-kampanya-durum">{t(`epostaPazarlama.durum.${k.durum}`)}</Rozet>
                {k.istatistik && <Rozet>{t('epostaPazarlama.kampanya.gonderilenKisa', { sayi: sayiYaz(k.istatistik.gonderilen, dil) })}</Rozet>}
                <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => ac(k)} data-testid="ep-kampanya-ac">
                  {k.durum === 'taslak' ? t('epostaPazarlama.genel.duzenle') : t('epostaPazarlama.kampanya.rapor')}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={async () => {
                    try {
                      await api.kampanyaKopyala(k.id);
                      void yukle();
                    } catch (e) {
                      toast.error(hataMetni(t, e));
                    }
                  }}
                  title={t('epostaPazarlama.genel.kopyala')}
                >
                  <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                  <span className="sr-only">{t('epostaPazarlama.genel.kopyala')}</span>
                </Button>
                {!k.baslangic_at && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={async () => {
                      if (!window.confirm(t('epostaPazarlama.kampanya.silOnay'))) return;
                      try {
                        await api.kampanyaSil(k.id);
                        void yukle();
                      } catch (e) {
                        toast.error(hataMetni(t, e));
                      }
                    }}
                    title={t('epostaPazarlama.genel.sil')}
                  >
                    <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                    <span className="sr-only">{t('epostaPazarlama.genel.sil')}</span>
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Duzenleyici({ api, meta, id, geri, rapor }: { api: PazarlamaApi; meta: Meta; id: number; geri: () => void; rapor: (id: number) => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [k, setK] = useState<Kampanya | null>(null);
  const [listeler, setListeler] = useState<Liste[]>([]);
  const [segmentler, setSegmentler] = useState<Segment[]>([]);
  const [kitle, setKitle] = useState<KitleOzeti | null>(null);
  const [testAdresleri, setTestAdresleri] = useState('');
  const [zaman, setZaman] = useState('');
  const [mesgul, setMesgul] = useState<string | null>(null);

  useEffect(() => {
    let iptal = false;
    Promise.all([api.kampanya(id), api.listeler(), api.segmentler()])
      .then(([kk, l, s]) => {
        if (iptal) return;
        setK(kk);
        setListeler(l.items);
        setSegmentler(s.items);
      })
      .catch((e) => toast.error(hataMetni(t, e)));
    return () => {
      iptal = true;
    };
  }, [api, id, t]);

  if (!k) return <Yukleniyor />;
  const degis = (g: Partial<Kampanya>) => {
    setK({ ...k, ...g });
    if (g.hedef) setKitle(null);
  };
  const secim = (alan: 'listeler' | 'segmentler' | 'haric_listeler', kimlik: number, acik: boolean) =>
    degis({ hedef: { ...k.hedef, [alan]: acik ? [...(k.hedef[alan] || []), kimlik] : (k.hedef[alan] || []).filter((x) => x !== kimlik) } });

  const kaydet = async (sessiz = false): Promise<boolean> => {
    setMesgul('kaydet');
    try {
      const yeni = await api.kampanyaGuncelle(k.id, {
        ad: k.ad,
        konu: k.konu,
        onizleme_metni: k.onizleme_metni,
        gonderen_adi: k.gonderen_adi,
        yanit_adresi: k.yanit_adresi,
        dil: k.dil,
        bloklar: k.bloklar,
        hedef: k.hedef,
        ab: k.ab,
      });
      setK(yeni);
      if (!sessiz) toast.success(t('epostaPazarlama.genel.kaydedildi'));
      return true;
    } catch (e) {
      toast.error(hataMetni(t, e));
      return false;
    } finally {
      setMesgul(null);
    }
  };
  const kitleHesapla = async () => {
    if (!(await kaydet(true))) return;
    try {
      setKitle(await api.kitle(k.id));
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };
  const testGonder = async () => {
    if (!(await kaydet(true))) return;
    setMesgul('test');
    try {
      const adresler = testAdresleri.split(/[\s,;]+/).filter(Boolean);
      const s = await api.test(k.id, adresler);
      const basarili = s.sonuc.filter((x) => x.durum === 'gonderildi').length;
      if (basarili === s.sonuc.length) toast.success(t('epostaPazarlama.kampanya.testGitti', { sayi: basarili }));
      else toast.error(t('epostaPazarlama.kampanya.testHata'));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(null);
    }
  };
  const gonder = async (zamanli: boolean) => {
    if (!(await kaydet(true))) return;
    const iso = zamanli ? yereldenIso(zaman) : null;
    if (zamanli && !iso) {
      toast.error(t('epostaPazarlama.hata.zaman_gecersiz'));
      return;
    }
    let ozet = kitle;
    try {
      ozet = await api.kitle(k.id);
      setKitle(ozet);
    } catch (e) {
      toast.error(hataMetni(t, e));
      return;
    }
    if (!window.confirm(t(zamanli ? 'epostaPazarlama.kampanya.zamanlaOnay' : 'epostaPazarlama.kampanya.gonderOnay', { sayi: ozet?.gonderilebilir ?? 0 }))) return;
    setMesgul('gonder');
    try {
      const s = await api.gonder(k.id, iso);
      toast.success(t(zamanli ? 'epostaPazarlama.kampanya.zamanlandi' : 'epostaPazarlama.kampanya.gonderildi'));
      rapor(s.kampanya.id);
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(null);
    }
  };

  return (
    <div className="space-y-4" data-testid="ep-kampanya-duzenleyici" data-kampanya-id={k.id}>
      <Button size="sm" variant="ghost" className="gap-1.5" onClick={geri}>
        <ArrowLeft className="h-4 w-4 rtl:rotate-180" aria-hidden="true" /> {t('epostaPazarlama.genel.geri')}
      </Button>

      <div className={`${KART} grid gap-3 p-4 sm:grid-cols-2`}>
        <Alan etiket={t('epostaPazarlama.kampanya.ad')}>
          <input className={GIRDI} value={k.ad} onChange={(e) => degis({ ad: e.target.value })} />
        </Alan>
        <Alan etiket={t('epostaPazarlama.kampanya.konu')} ipucu={t('epostaPazarlama.kampanya.konuIpucu', yerTutucuOrnekleri(t))}>
          <input className={GIRDI} value={k.konu} onChange={(e) => degis({ konu: e.target.value })} data-testid="ep-kampanya-konu" />
        </Alan>
        <Alan etiket={t('epostaPazarlama.kampanya.onizlemeMetni')} ipucu={t('epostaPazarlama.kampanya.onizlemeIpucu')}>
          <input className={GIRDI} value={k.onizleme_metni} onChange={(e) => degis({ onizleme_metni: e.target.value })} />
        </Alan>
        <Alan etiket={t('epostaPazarlama.kampanya.gonderenAdi')} ipucu={meta.yonetici ? undefined : t('epostaPazarlama.kampanya.viaIpucu')}>
          <input className={GIRDI} value={k.gonderen_adi} onChange={(e) => degis({ gonderen_adi: e.target.value })} placeholder={meta.kimlik.gonderen_adi} />
        </Alan>
        <Alan etiket={t('epostaPazarlama.kampanya.yanitAdresi')}>
          <input className={GIRDI} type="email" value={k.yanit_adresi} onChange={(e) => degis({ yanit_adresi: e.target.value })} placeholder={meta.kimlik.yanit_adresi} />
        </Alan>
        <Alan etiket={t('epostaPazarlama.kampanya.dil')} ipucu={t('epostaPazarlama.kampanya.dilIpucu')}>
          <select className={SECIM} value={k.dil} onChange={(e) => degis({ dil: e.target.value })}>
            {meta.diller.map((x) => (
              <option key={x} value={x}>
                {x.toUpperCase()}
              </option>
            ))}
          </select>
        </Alan>
      </div>

      <div className={`${KART} space-y-3 p-4`} data-testid="ep-kitle">
        <h3 className="flex items-center gap-2 font-semibold">
          <Users className="h-4 w-4 text-purple-300" aria-hidden="true" /> {t('epostaPazarlama.kampanya.kitle')}
        </h3>
        <div className="grid gap-3 sm:grid-cols-3">
          <div>
            <p className="mb-1 text-xs text-muted-foreground">{t('epostaPazarlama.alt.listeler')}</p>
            {listeler.map((l) => (
              <Anahtar key={l.id} acik={k.hedef.listeler.includes(l.id)} onDegis={(v) => secim('listeler', l.id, v)} etiket={`${l.ad} (${sayiYaz(l.aktif, dil)})`} testid={`ep-hedef-liste-${l.id}`} />
            ))}
          </div>
          <div>
            <p className="mb-1 text-xs text-muted-foreground">{t('epostaPazarlama.alt.segmentler')}</p>
            {segmentler.length === 0 && <p className="text-xs text-muted-foreground">—</p>}
            {segmentler.map((s) => (
              <Anahtar key={s.id} acik={k.hedef.segmentler.includes(s.id)} onDegis={(v) => secim('segmentler', s.id, v)} etiket={s.ad} />
            ))}
          </div>
          <div>
            <p className="mb-1 text-xs text-muted-foreground">{t('epostaPazarlama.kampanya.haric')}</p>
            {listeler.map((l) => (
              <Anahtar key={l.id} acik={k.hedef.haric_listeler.includes(l.id)} onDegis={(v) => secim('haric_listeler', l.id, v)} etiket={l.ad} />
            ))}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => void kitleHesapla()} data-testid="ep-kitle-hesapla">
            {t('epostaPazarlama.kampanya.kitleHesapla')}
          </Button>
          {kitle && (
            <span className="flex flex-wrap gap-1.5 text-xs" data-testid="ep-kitle-ozet">
              <Rozet renk="border-emerald-400/30 bg-emerald-400/10 text-emerald-200">
                {t('epostaPazarlama.kampanya.gonderilebilir', { sayi: sayiYaz(kitle.gonderilebilir, dil) })}
              </Rozet>
              {Object.entries(kitle.atlanacak).map(([neden, sayi]) => (
                <Rozet key={neden} renk="border-amber-400/30 bg-amber-400/10 text-amber-200">
                  {t(`epostaPazarlama.neden.${neden}`, { defaultValue: neden })}: {sayiYaz(sayi, dil)}
                </Rozet>
              ))}
              {kitle.kota_kalan !== null && kitle.kota_kalan !== undefined && <Rozet>{t('epostaPazarlama.kampanya.kotaKalan', { sayi: sayiYaz(kitle.kota_kalan, dil) })}</Rozet>}
            </span>
          )}
        </div>
        <p className="text-xs text-muted-foreground">{t('epostaPazarlama.kampanya.izinNotu')}</p>
      </div>

      <div className={`${KART} space-y-3 p-4`}>
        <Anahtar
          acik={k.ab.acik}
          onDegis={(v) => degis({ ab: v ? { acik: true, konu_b: k.ab.konu_b || '', oran: k.ab.oran || 20, bekleme_saat: k.ab.bekleme_saat || 4, olcut: k.ab.olcut || 'acilma' } : { acik: false } })}
          etiket={
            <span className="flex items-center gap-1.5">
              <FlaskConical className="h-4 w-4 text-fuchsia-300" aria-hidden="true" /> {t('epostaPazarlama.ab.baslik')}
            </span>
          }
          testid="ep-ab-acik"
        />
        {k.ab.acik && (
          <div className="grid gap-3 sm:grid-cols-2">
            <Alan etiket={t('epostaPazarlama.ab.konuB')}>
              <input className={GIRDI} value={k.ab.konu_b || ''} onChange={(e) => degis({ ab: { ...k.ab, konu_b: e.target.value } })} />
            </Alan>
            <Alan etiket={t('epostaPazarlama.ab.olcut')}>
              <select className={SECIM} value={k.ab.olcut || 'acilma'} onChange={(e) => degis({ ab: { ...k.ab, olcut: e.target.value as 'acilma' | 'tiklama' } })}>
                <option value="acilma">{t('epostaPazarlama.ab.acilma')}</option>
                <option value="tiklama">{t('epostaPazarlama.ab.tiklama')}</option>
              </select>
            </Alan>
            <Alan etiket={t('epostaPazarlama.ab.oran')}>
              <input className={GIRDI} type="number" min={10} max={50} value={k.ab.oran || 20} onChange={(e) => degis({ ab: { ...k.ab, oran: Number(e.target.value) } })} />
            </Alan>
            <Alan etiket={t('epostaPazarlama.ab.bekleme')}>
              <input className={GIRDI} type="number" min={1} max={72} value={k.ab.bekleme_saat || 4} onChange={(e) => degis({ ab: { ...k.ab, bekleme_saat: Number(e.target.value) } })} />
            </Alan>
            <p className="text-xs text-muted-foreground sm:col-span-2">{t('epostaPazarlama.ab.aciklama')}</p>
          </div>
        )}
      </div>

      <BlokDuzenleyici
        api={api}
        bloklar={k.bloklar}
        onDegis={(b) => degis({ bloklar: b })}
        konu={k.konu}
        onizlemeMetni={k.onizleme_metni}
        dil={k.dil}
        gonderenAdi={k.gonderen_adi}
      />

      <div className={`${KART} space-y-3 p-4`}>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => void kaydet()} disabled={!!mesgul} data-testid="ep-kampanya-kaydet">
            {mesgul === 'kaydet' ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Save className="h-4 w-4" aria-hidden="true" />}
            {t('epostaPazarlama.genel.kaydet')}
          </Button>
        </div>
        <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
          <input
            className={GIRDI}
            value={testAdresleri}
            onChange={(e) => setTestAdresleri(e.target.value)}
            placeholder={t('epostaPazarlama.kampanya.testAdresleri')}
            aria-label={t('epostaPazarlama.kampanya.testAdresleri')}
            data-testid="ep-test-adres"
          />
          <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => void testGonder()} disabled={!!mesgul || !testAdresleri.trim()} data-testid="ep-test-gonder">
            {mesgul === 'test' ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <FlaskConical className="h-4 w-4" aria-hidden="true" />}
            {t('epostaPazarlama.kampanya.testGonder')}
          </Button>
        </div>
        <div className="grid gap-2 sm:grid-cols-[1fr_auto_auto]">
          <input
            className={GIRDI}
            type="datetime-local"
            value={zaman}
            onChange={(e) => setZaman(e.target.value)}
            aria-label={t('epostaPazarlama.kampanya.zaman')}
          />
          <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => void gonder(true)} disabled={!!mesgul || !zaman}>
            <CalendarClock className="h-4 w-4" aria-hidden="true" /> {t('epostaPazarlama.kampanya.zamanla')}
          </Button>
          <Button size="sm" onClick={() => void gonder(false)} disabled={!!mesgul} className="gap-1.5" data-testid="ep-kampanya-gonder">
            {mesgul === 'gonder' ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Send className="h-4 w-4" aria-hidden="true" />}
            {t('epostaPazarlama.kampanya.simdiGonder')}
          </Button>
        </div>
      </div>
    </div>
  );
}

function RaporGorunumu({ api, id, geri }: { api: PazarlamaApi; id: number; geri: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [r, setR] = useState<Rapor | null>(null);
  const yukle = useCallback(async () => {
    try {
      setR(await api.rapor(id));
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  }, [api, id, t]);
  useEffect(() => {
    void yukle();
  }, [yukle]);
  if (!r) return <Yukleniyor />;
  const k = r.kampanya;
  const islem = async (f: () => Promise<Kampanya>) => {
    try {
      await f();
      void yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };
  const kartlar: { anahtar: string; deger: number; oran?: number | null }[] = [
    { anahtar: 'gonderilen', deger: r.sayilar.gonderilen },
    { anahtar: 'teslim', deger: r.sayilar.teslim, oran: r.oranlar.teslim },
    { anahtar: 'geri_donen', deger: r.sayilar.geri_donen, oran: r.oranlar.geri_donme },
    { anahtar: 'ret', deger: r.sayilar.ret, oran: r.oranlar.ret },
    { anahtar: 'sikayet', deger: r.sayilar.sikayet, oran: r.oranlar.sikayet },
    { anahtar: 'acilan', deger: r.sayilar.acilan, oran: r.oranlar.acilma },
    { anahtar: 'tiklayan', deger: r.sayilar.tiklayan, oran: r.oranlar.tiklama },
    { anahtar: 'atlanan', deger: r.sayilar.atlanan },
  ];
  return (
    <div className="space-y-4" data-testid="ep-rapor" data-durum={k.durum}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Button size="sm" variant="ghost" className="gap-1.5" onClick={geri}>
          <ArrowLeft className="h-4 w-4 rtl:rotate-180" aria-hidden="true" /> {t('epostaPazarlama.genel.geri')}
        </Button>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => void yukle()}>
            <RefreshCw className="h-4 w-4" aria-hidden="true" /> {t('epostaPazarlama.genel.yenile')}
          </Button>
          {['gonderiliyor', 'ab_test', 'zamanlandi'].includes(k.durum) && (
            <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => void islem(() => api.durdur(k.id))}>
              <Pause className="h-4 w-4" aria-hidden="true" /> {t('epostaPazarlama.kampanya.durdur')}
            </Button>
          )}
          {k.durum === 'duraklatildi' && (
            <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => void islem(() => api.devam(k.id))}>
              <Play className="h-4 w-4" aria-hidden="true" /> {t('epostaPazarlama.kampanya.devam')}
            </Button>
          )}
        </div>
      </div>
      <div className={`${KART} p-4`}>
        <h3 className="flex flex-wrap items-center gap-2 text-lg font-semibold">
          <BarChart3 className="h-5 w-5 text-purple-300" aria-hidden="true" /> {k.ad}
          <Rozet renk={DURUM_RENGI[k.durum]} testid="ep-rapor-durum">{t(`epostaPazarlama.durum.${k.durum}`)}</Rozet>
        </h3>
        <p className="mt-1 text-xs text-muted-foreground">
          {k.konu} · {t('epostaPazarlama.kampanya.hedefSayisi', { sayi: sayiYaz(k.hedef_sayisi, dil) })}
          {k.zamanlanan_at && ` · ${t('epostaPazarlama.kampanya.zamanlanan', { zaman: tarihYaz(k.zamanlanan_at, dil) })}`}
          {k.duraklatma_nedeni && ` · ${t(`epostaPazarlama.duraklatma.${k.duraklatma_nedeni}`, { defaultValue: k.duraklatma_nedeni })}`}
        </p>
        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {kartlar.map((c) => (
            <div key={c.anahtar} className="rounded-lg border border-white/10 px-3 py-2">
              <p className="text-[11px] text-muted-foreground">{t(`epostaPazarlama.rapor.${c.anahtar}`)}</p>
              <p className="text-lg font-semibold" data-testid={`ep-rapor-${c.anahtar}`}>
                {sayiYaz(c.deger, dil)}
              </p>
              {c.oran !== undefined && <p className="text-[11px] text-muted-foreground">{yuzde(c.oran, dil)}</p>}
            </div>
          ))}
        </div>
        {!k.takip_acilma && <p className="mt-2 text-xs text-muted-foreground">{t('epostaPazarlama.rapor.takipKapali')}</p>}
      </div>
      {Object.keys(r.atlama_nedenleri).length > 0 && (
        <div className={`${KART} p-4`}>
          <h4 className="mb-2 text-sm font-semibold">{t('epostaPazarlama.rapor.atlamaNedenleri')}</h4>
          <ul className="flex flex-wrap gap-1.5">
            {Object.entries(r.atlama_nedenleri).map(([n, s]) => (
              <Rozet key={n} renk="border-amber-400/30 bg-amber-400/10 text-amber-200">
                {t(`epostaPazarlama.neden.${n}`, { defaultValue: n })}: {sayiYaz(s, dil)}
              </Rozet>
            ))}
          </ul>
        </div>
      )}
      {k.ab.acik && (
        <div className={`${KART} p-4`}>
          <h4 className="mb-2 text-sm font-semibold">{t('epostaPazarlama.ab.baslik')}</h4>
          <ul className="space-y-1 text-sm">
            {(['a', 'b'] as const).map((v) => (
              <li key={v} className="flex flex-wrap justify-between gap-2">
                <span>
                  {v.toUpperCase()}: {v === 'a' ? k.konu : k.ab.konu_b} {k.kazanan === v && <Rozet renk="border-emerald-400/30 bg-emerald-400/10 text-emerald-200">{t('epostaPazarlama.ab.kazanan')}</Rozet>}
                </span>
                <span className="text-xs text-muted-foreground">
                  {sayiYaz(r.varyantlar[v]?.gonderilen ?? 0, dil)} · {sayiYaz(r.varyantlar[v]?.acilan ?? 0, dil)} {t('epostaPazarlama.rapor.acilan')}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {r.baglantilar.length > 0 && k.takip_tiklama && (
        <div className={`${KART} p-4`}>
          <h4 className="mb-2 text-sm font-semibold">{t('epostaPazarlama.rapor.baglantilar')}</h4>
          <ul className="space-y-1 text-xs">
            {r.baglantilar.map((b) => (
              <li key={b.indeks} className="flex justify-between gap-2">
                <span className="min-w-0 truncate">{b.url}</span>
                <span>{sayiYaz(b.tiklama, dil)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className={`${KART} p-4`}>
        <h4 className="mb-2 text-sm font-semibold">{t('epostaPazarlama.rapor.alicilar')}</h4>
        <ul className="divide-y divide-white/5 text-xs" data-testid="ep-rapor-alicilar">
          {r.alicilar.map((a, i) => (
            <li key={i} className="flex flex-wrap justify-between gap-2 py-1.5">
              <span className="min-w-0 truncate">{a.eposta || '—'}</span>
              <span className="text-muted-foreground">
                {t(`epostaPazarlama.satirDurum.${a.durum}`, { defaultValue: a.durum })}
                {a.neden ? ` · ${t(`epostaPazarlama.neden.${a.neden}`, { defaultValue: a.neden })}` : ''}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
