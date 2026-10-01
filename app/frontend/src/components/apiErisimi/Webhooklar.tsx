import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown, ChevronUp, History, Loader2, Pencil, Plus, RefreshCw, RotateCcw, Send, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { ALAN, BirKezKutusu, DurumRozeti, KART, ROZET, tarihYaz } from '@/components/apiErisimi/ortak';
import {
  anahtarAdi,
  hataMetni,
  type ApiErisimApi,
  type ApiMeta,
  type ApiMod,
  type Teslimat,
  type WebhookUcu,
} from '@/lib/apiErisimi';

/** Faz 4A — webhook uç noktaları: oluştur (sır BİR KEZ), düzenle, aç/kapa, test, sır yenile, sil, teslimat geçmişi. */
export default function Webhooklar({
  api,
  mod,
  meta,
  onDegisti,
}: {
  api: ApiErisimApi;
  mod: ApiMod;
  meta: ApiMeta | null;
  onDegisti: () => void;
}) {
  const { t } = useTranslation();
  const [liste, setListe] = useState<WebhookUcu[] | null>(null);
  const [hepsi, setHepsi] = useState(false);
  const [form, setForm] = useState<{ uc: WebhookUcu | null } | null>(null);
  const [gizli, setGizli] = useState<{ deger: string } | null>(null);
  const [acik, setAcik] = useState<number | null>(null);

  const yukle = useCallback(async () => {
    try {
      setListe(await api.uclar(mod === 'yonetici' && hepsi));
    } catch (e) {
      toast.error(hataMetni(t, e));
      setListe([]);
    }
  }, [api, mod, hepsi, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const sinirDolu = !!meta && meta.webhook_sayisi >= meta.webhook_siniri;
  const yenile = async () => {
    await yukle();
    onDegisti();
  };

  return (
    <div className="space-y-4" data-testid="api-webhooklar">
      {gizli && (
        <BirKezKutusu deger={gizli.deger} uyari={t('apiErisimi.webhook.gizliBirKez')} testId="api-webhook-gizli" onKapat={() => setGizli(null)} />
      )}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          {meta && (
            <span className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-xs text-muted-foreground">
              {t('apiErisimi.webhook.hak', { sayi: meta.webhook_sayisi, sinir: meta.webhook_siniri })}
            </span>
          )}
          {mod === 'yonetici' && (
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <input type="checkbox" checked={hepsi} onChange={(e) => setHepsi(e.target.checked)} />
              {t('apiErisimi.webhook.hepsi')}
            </label>
          )}
        </div>
        {!form && (
          <Button
            type="button"
            className="gap-1.5"
            data-testid="api-webhook-yeni"
            onClick={() =>
              sinirDolu ? toast.error(t('apiErisimi.hata.webhook_siniri', { sinir: meta?.webhook_siniri })) : setForm({ uc: null })
            }
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('apiErisimi.webhook.yeni')}
          </Button>
        )}
      </div>

      {form && meta && (
        <UcFormu
          api={api}
          mod={mod}
          meta={meta}
          uc={form.uc}
          onVazgec={() => setForm(null)}
          onKaydedildi={async (yeniGizli) => {
            setForm(null);
            if (yeniGizli) setGizli({ deger: yeniGizli });
            await yenile();
          }}
        />
      )}

      <p className="text-xs text-muted-foreground">{t('apiErisimi.webhook.yenidenDenemeBilgisi', { sayi: meta?.en_cok_deneme ?? 8, esik: meta?.pasif_esigi ?? 20 })}</p>

      {liste === null ? (
        <div className="flex justify-center py-10 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
        </div>
      ) : liste.length === 0 ? (
        <p className={`${KART} p-6 text-sm text-muted-foreground`}>{t('apiErisimi.webhook.bos')}</p>
      ) : (
        <ul className="space-y-3">
          {liste.map((u) => (
            <UcKarti
              key={u.id}
              api={api}
              mod={mod}
              uc={u}
              gecmisAcik={acik === u.id}
              onGecmis={() => setAcik((x) => (x === u.id ? null : u.id))}
              onDuzenle={() => setForm({ uc: u })}
              onGizli={(g) => setGizli({ deger: g })}
              onDegisti={yenile}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function UcKarti({
  api,
  mod,
  uc,
  gecmisAcik,
  onGecmis,
  onDuzenle,
  onGizli,
  onDegisti,
}: {
  api: ApiErisimApi;
  mod: ApiMod;
  uc: WebhookUcu;
  gecmisAcik: boolean;
  onGecmis: () => void;
  onDuzenle: () => void;
  onGizli: (g: string) => void;
  onDegisti: () => Promise<void>;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [mesgul, setMesgul] = useState<string | null>(null);
  const [yenileme, setYenileme] = useState(0);

  const calistir = async (ad: string, is: () => Promise<void>) => {
    setMesgul(ad);
    try {
      await is();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(null);
    }
  };

  return (
    <li className={`${KART} p-4`} data-uc-id={uc.id}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <DurumRozeti durum={uc.aktif ? 'aktif' : 'pasif'} metin={uc.aktif ? t('apiErisimi.webhook.aktif') : t('apiErisimi.webhook.pasif')} />
            {uc.bekleyen > 0 && (
              <span className={`${ROZET} border-sky-400/30 bg-sky-500/10 text-sky-200`}>{t('apiErisimi.webhook.bekleyen', { sayi: uc.bekleyen })}</span>
            )}
            {uc.ardisik_hata > 0 && (
              <span className={`${ROZET} border-red-400/40 bg-red-500/10 text-red-200`}>
                {t('apiErisimi.webhook.ardisikHata', { sayi: uc.ardisik_hata })}
              </span>
            )}
            {uc.tum_musteriler && (
              <span className={`${ROZET} border-purple-400/30 bg-purple-500/10 text-purple-100`}>{t('apiErisimi.webhook.tumMusterilerKisa')}</span>
            )}
            {mod === 'yonetici' && uc.sahip_tur === 'musteri' && (
              <span className={`${ROZET} border-white/10 text-muted-foreground`} dir="ltr">
                {uc.hesap_email}
              </span>
            )}
          </div>
          <p className="mt-1 break-all font-mono text-sm text-purple-200" dir="ltr" data-testid="api-webhook-url">
            {uc.url}
          </p>
          {uc.aciklama && (
            <p className="mt-1 text-xs text-muted-foreground" dir="auto">
              {uc.aciklama}
            </p>
          )}
          {uc.pasif_sebebi && <p className="mt-1 text-xs text-red-200">{t('apiErisimi.webhook.pasifSebebi')}</p>}
          {uc.gizli_gecis_bitis && (
            <p className="mt-1 text-xs text-amber-200">{t('apiErisimi.webhook.gecis', { tarih: tarihYaz(uc.gizli_gecis_bitis, dil) })}</p>
          )}
          <div className="mt-2 flex flex-wrap gap-1.5">
            {uc.olaylar.map((o) => (
              <span key={o} className={`${ROZET} border-white/10 bg-white/[0.04] text-slate-200`} title={o}>
                {t(`apiErisimi.olay.${anahtarAdi(o)}`)}
              </span>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          className="gap-1.5"
          disabled={!!mesgul}
          data-testid="api-webhook-test"
          onClick={() =>
            void calistir('test', async () => {
              const s = await api.testGonder(uc.id);
              if (s.basarili) toast.success(t('apiErisimi.webhook.testBasarili', { kod: s.durum_kodu }));
              else toast.error(t('apiErisimi.webhook.testBasarisiz', { hata: s.hata || s.durum_kodu || '—' }));
              setYenileme((x) => x + 1);
              await onDegisti();
            })
          }
        >
          {mesgul === 'test' ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Send className="h-4 w-4" aria-hidden="true" />}
          {t('apiErisimi.webhook.test')}
        </Button>
        <Button type="button" size="sm" variant="outline" className="gap-1.5" onClick={onGecmis} data-testid="api-webhook-gecmis">
          <History className="h-4 w-4" aria-hidden="true" />
          {t('apiErisimi.webhook.gecmis')}
          {gecmisAcik ? <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" /> : <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={!!mesgul}
          onClick={() =>
            void calistir('aktif', async () => {
              await api.ucGuncelle(uc.id, { aktif: !uc.aktif });
              await onDegisti();
            })
          }
          data-testid="api-webhook-ac-kapa"
        >
          {uc.aktif ? t('apiErisimi.webhook.durdur') : t('apiErisimi.webhook.etkinlestir')}
        </Button>
        <Button type="button" size="sm" variant="outline" className="gap-1.5" onClick={onDuzenle}>
          <Pencil className="h-4 w-4" aria-hidden="true" />
          {t('apiErisimi.webhook.duzenle')}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="gap-1.5"
          disabled={!!mesgul}
          onClick={() => {
            if (!window.confirm(t('apiErisimi.webhook.gizliYenileOnay'))) return;
            void calistir('gizli', async () => {
              const s = await api.gizliYenile(uc.id);
              onGizli(s.gizli);
              await onDegisti();
            });
          }}
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          {t('apiErisimi.webhook.gizliYenile')}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="gap-1.5 text-red-200"
          disabled={!!mesgul}
          onClick={() => {
            if (!window.confirm(t('apiErisimi.webhook.silOnay', { url: uc.url }))) return;
            void calistir('sil', async () => {
              await api.ucSil(uc.id);
              toast.success(t('apiErisimi.webhook.silindi'));
              await onDegisti();
            });
          }}
        >
          <Trash2 className="h-4 w-4" aria-hidden="true" />
          {t('apiErisimi.webhook.sil')}
        </Button>
      </div>

      {gecmisAcik && <TeslimatGecmisi api={api} ucId={uc.id} yenileme={yenileme} />}
    </li>
  );
}

function TeslimatGecmisi({ api, ucId, yenileme }: { api: ApiErisimApi; ucId: number; yenileme: number }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [liste, setListe] = useState<Teslimat[] | null>(null);
  const [sonraki, setSonraki] = useState<number | null>(null);
  const [acik, setAcik] = useState<number | null>(null);
  const [mesgul, setMesgul] = useState<number | null>(null);

  const yukle = useCallback(async () => {
    try {
      const s = await api.teslimatlar(ucId);
      setListe(s.items);
      setSonraki(s.sonraki_once);
    } catch (e) {
      toast.error(hataMetni(t, e));
      setListe([]);
    }
  }, [api, ucId, t]);

  useEffect(() => {
    void yukle();
  }, [yukle, yenileme]);

  const dahaFazla = async () => {
    if (!sonraki) return;
    try {
      const s = await api.teslimatlar(ucId, sonraki);
      setListe((l) => [...(l || []), ...s.items]);
      setSonraki(s.sonraki_once);
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  return (
    <div className="mt-4 border-t border-white/10 pt-4" data-testid="api-teslimat-gecmisi">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h4 className="text-sm font-semibold">{t('apiErisimi.webhook.gecmis')}</h4>
        <button type="button" className="text-xs text-purple-200 hover:underline" onClick={() => void yukle()}>
          {t('apiErisimi.yenile')}
        </button>
      </div>
      {liste === null ? (
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" aria-hidden="true" />
      ) : liste.length === 0 ? (
        <p className="text-xs text-muted-foreground">{t('apiErisimi.webhook.gecmisBos')}</p>
      ) : (
        <ul className="space-y-2">
          {liste.map((d) => (
            <li key={d.id} className="rounded-xl border border-white/10 bg-black/20 p-3" data-teslimat-id={d.id} data-teslimat-tur={d.tur}>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <DurumRozeti durum={d.durum} metin={t(`apiErisimi.teslimatDurum.${d.durum}`)} />
                <span className="font-mono text-slate-200" dir="ltr">
                  {d.tur}
                </span>
                <span className="text-muted-foreground">{tarihYaz(d.olusturma, dil)}</span>
                {d.son_durum_kodu !== null && (
                  <span className="font-mono text-slate-300" dir="ltr">
                    HTTP {d.son_durum_kodu}
                  </span>
                )}
                {d.son_sure_ms !== null && <span className="text-muted-foreground">{t('apiErisimi.webhook.sure', { ms: d.son_sure_ms })}</span>}
                <span className="text-muted-foreground">{t('apiErisimi.webhook.denemeSayisi', { sayi: d.deneme_sayisi })}</span>
              </div>
              {d.son_hata && (
                <p className="mt-1 break-all font-mono text-[11px] text-red-200" dir="ltr">
                  {d.son_hata}
                </p>
              )}
              {d.sonraki_deneme && (
                <p className="mt-1 text-[11px] text-sky-200">{t('apiErisimi.webhook.sonrakiDeneme', { tarih: tarihYaz(d.sonraki_deneme, dil) })}</p>
              )}
              <div className="mt-2 flex flex-wrap gap-2">
                <button
                  type="button"
                  className="text-xs text-purple-200 hover:underline"
                  onClick={() => setAcik((x) => (x === d.id ? null : d.id))}
                >
                  {acik === d.id ? t('apiErisimi.kapat') : t('apiErisimi.webhook.ayrinti')}
                </button>
                <button
                  type="button"
                  className="inline-flex items-center gap-1 text-xs text-purple-200 hover:underline disabled:opacity-50"
                  disabled={mesgul === d.id}
                  data-testid="api-teslimat-yeniden"
                  onClick={async () => {
                    setMesgul(d.id);
                    try {
                      const s = await api.yenidenGonder(ucId, d.id);
                      if (s.basarili) toast.success(t('apiErisimi.webhook.yenidenGonderildi'));
                      else toast.error(t('apiErisimi.webhook.testBasarisiz', { hata: s.hata || s.durum_kodu || '—' }));
                      await yukle();
                    } catch (e) {
                      toast.error(hataMetni(t, e));
                    } finally {
                      setMesgul(null);
                    }
                  }}
                >
                  <RotateCcw className="h-3 w-3" aria-hidden="true" />
                  {t('apiErisimi.webhook.yenidenGonder')}
                </button>
              </div>
              {acik === d.id && (
                <div className="mt-2 space-y-2">
                  <p className="text-[11px] uppercase tracking-wider text-muted-foreground">{t('apiErisimi.webhook.govde')}</p>
                  <pre className="max-w-full overflow-x-auto rounded-lg bg-black/50 p-2 text-[11px] text-slate-200" dir="ltr">
                    {JSON.stringify(d.govde, null, 2)}
                  </pre>
                  <ol className="space-y-1">
                    {(d.denemeler || []).map((x) => (
                      <li key={x.deneme_no} className="rounded-lg border border-white/10 p-2 text-[11px]">
                        <div className="flex flex-wrap gap-2">
                          <span className="font-medium">{t('apiErisimi.webhook.deneme', { sayi: x.deneme_no })}</span>
                          <span className="text-muted-foreground">{t(`apiErisimi.webhook.tetik.${x.tetik}`)}</span>
                          <span className={x.basarili ? 'text-emerald-200' : 'text-red-200'} dir="ltr">
                            {x.durum_kodu !== null ? `HTTP ${x.durum_kodu}` : x.hata}
                          </span>
                          {x.sure_ms !== null && <span className="text-muted-foreground">{t('apiErisimi.webhook.sure', { ms: x.sure_ms })}</span>}
                          <span className="text-muted-foreground">{tarihYaz(x.zaman, dil)}</span>
                        </div>
                        {x.yanit && (
                          <pre className="mt-1 max-w-full overflow-x-auto whitespace-pre-wrap break-all text-slate-300" dir="ltr">
                            {x.yanit}
                          </pre>
                        )}
                      </li>
                    ))}
                  </ol>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {sonraki && (
        <button type="button" className="mt-2 text-xs text-purple-200 hover:underline" onClick={() => void dahaFazla()}>
          {t('apiErisimi.dahaFazla')}
        </button>
      )}
    </div>
  );
}

function UcFormu({
  api,
  mod,
  meta,
  uc,
  onVazgec,
  onKaydedildi,
}: {
  api: ApiErisimApi;
  mod: ApiMod;
  meta: ApiMeta;
  uc: WebhookUcu | null;
  onVazgec: () => void;
  onKaydedildi: (gizli: string | null) => void;
}) {
  const { t } = useTranslation();
  const [url, setUrl] = useState(uc?.url || 'https://');
  const [aciklama, setAciklama] = useState(uc?.aciklama || '');
  const [olaylar, setOlaylar] = useState<string[]>(uc?.olaylar || meta.olaylar.filter((o) => o.varsayilan).map((o) => o.anahtar));
  const [tum, setTum] = useState(uc?.tum_musteriler || false);
  const [gonderiliyor, setGonderiliyor] = useState(false);

  const degistir = (o: string) => setOlaylar((l) => (l.includes(o) ? l.filter((x) => x !== o) : [...l, o]));

  const gonder = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!olaylar.length) {
      toast.error(t('apiErisimi.hata.olay_gerekli'));
      return;
    }
    setGonderiliyor(true);
    try {
      const g = { url: url.trim(), olaylar, aciklama: aciklama.trim() || null, ...(mod === 'yonetici' ? { tum_musteriler: tum } : {}) };
      if (uc) {
        await api.ucGuncelle(uc.id, g);
        toast.success(t('apiErisimi.webhook.kaydedildi'));
        onKaydedildi(null);
      } else {
        const s = await api.ucOlustur(g);
        onKaydedildi(s.gizli);
      }
    } catch (hata) {
      toast.error(hataMetni(t, hata));
    } finally {
      setGonderiliyor(false);
    }
  };

  return (
    <form onSubmit={gonder} className={`${KART} space-y-5 p-5`} data-testid="api-webhook-formu">
      <div>
        <label className="mb-1 block text-sm font-medium" htmlFor="api-webhook-url">
          {t('apiErisimi.webhook.url')}
        </label>
        <input id="api-webhook-url" className={`${ALAN} font-mono`} dir="ltr" value={url} onChange={(e) => setUrl(e.target.value)} />
        <p className="mt-1 text-xs text-muted-foreground">{t('apiErisimi.webhook.urlAciklama')}</p>
      </div>
      <div>
        <label className="mb-1 block text-sm font-medium" htmlFor="api-webhook-aciklama">
          {t('apiErisimi.webhook.aciklama')}
        </label>
        <input id="api-webhook-aciklama" className={ALAN} maxLength={200} value={aciklama} onChange={(e) => setAciklama(e.target.value)} />
      </div>
      <fieldset>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <legend className="text-sm font-medium">{t('apiErisimi.webhook.olaylar')}</legend>
          <button
            type="button"
            className="text-xs text-purple-200 hover:underline"
            onClick={() => setOlaylar(meta.olaylar.filter((o) => !o.yuksek_hacim).map((o) => o.anahtar))}
          >
            {t('apiErisimi.webhook.hepsiniSec')}
          </button>
        </div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {meta.olaylar.map((o) => (
            <label key={o.anahtar} className="flex items-start gap-2 rounded-lg border border-white/10 p-2 text-sm">
              <input type="checkbox" className="mt-1" checked={olaylar.includes(o.anahtar)} onChange={() => degistir(o.anahtar)} data-olay={o.anahtar} />
              <span className="min-w-0">
                <span className="block">{t(`apiErisimi.olay.${anahtarAdi(o.anahtar)}`)}</span>
                <span className="block font-mono text-[11px] text-muted-foreground" dir="ltr">
                  {o.anahtar}
                  {o.yuksek_hacim ? ` · ${t('apiErisimi.webhook.yuksekHacim')}` : ''}
                </span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>
      {mod === 'yonetici' && (
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-1" checked={tum} onChange={(e) => setTum(e.target.checked)} />
          <span>
            <span className="block">{t('apiErisimi.webhook.tumMusteriler')}</span>
            <span className="block text-xs text-muted-foreground">{t('apiErisimi.webhook.tumMusterilerAciklama')}</span>
          </span>
        </label>
      )}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={gonderiliyor} className="gap-1.5" data-testid="api-webhook-kaydet">
          {gonderiliyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
          {uc ? t('apiErisimi.webhook.kaydet') : t('apiErisimi.webhook.olustur')}
        </Button>
        <Button type="button" variant="outline" onClick={onVazgec}>
          {t('apiErisimi.vazgec')}
        </Button>
      </div>
    </form>
  );
}
