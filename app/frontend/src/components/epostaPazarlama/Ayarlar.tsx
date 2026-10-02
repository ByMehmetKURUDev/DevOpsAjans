import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Copy, Loader2, Save, ShieldAlert } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Alan, Anahtar, DIS_DUGME, GIRDI, KART, METIN_ALANI, Rozet, SECIM, Yukleniyor, kopyala, sayiYaz } from '@/components/epostaPazarlama/ortak';
import { hataMetni, type Ayarlar as AyarVeri, type HesapSagligi, type Meta, type PazarlamaApi } from '@/lib/epostaPazarlama';

/** Faz 5M — ayarlar: gönderen kimliği, marka, takip (varsayılan kapalı), sıklık sınırı, İYS bilgisi; yönetici: webhook + hesap sağlığı. */
export default function Ayarlar({ api, meta, yenile }: { api: PazarlamaApi; meta: Meta; yenile: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [a, setA] = useState<AyarVeri | null>(null);
  const [mesgul, setMesgul] = useState(false);
  const [logoYukleniyor, setLogoYukleniyor] = useState(false);

  useEffect(() => {
    api.ayarlar().then(setA).catch((e) => toast.error(hataMetni(t, e)));
  }, [api, t]);

  if (!a) return <Yukleniyor />;
  const kaydet = async () => {
    setMesgul(true);
    try {
      const govde: Partial<AyarVeri> = {
        gonderen_adi: a.gonderen_adi,
        yanit_adresi: a.yanit_adresi,
        logo_url: a.logo_url,
        marka_rengi: a.marka_rengi,
        dil: a.dil,
        iys_durumu: a.iys_durumu,
        iys_marka_kodu: a.iys_marka_kodu,
        acilma_takibi: a.acilma_takibi,
        tiklama_takibi: a.tiklama_takibi,
        gunluk_kisi_siniri: a.gunluk_kisi_siniri,
        ...(meta.yonetici ? {} : { unvan: a.unvan, adres: a.adres }),
      };
      setA(await api.ayarlarYaz(govde));
      toast.success(t('epostaPazarlama.genel.kaydedildi'));
      yenile();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  return (
    <div className="space-y-5" data-testid="ep-ayarlar">
      {a.askida && (
        <p className="flex items-start gap-2 rounded-xl border border-rose-400/30 bg-rose-400/10 px-4 py-3 text-sm text-rose-100" data-testid="ep-askida">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          {t('epostaPazarlama.ayar.askida', { neden: t(`epostaPazarlama.ayar.askidaNeden.${a.askida_neden || 'elle'}`) })}
        </p>
      )}
      <div className={`${KART} space-y-3 p-4`}>
        <h3 className="font-semibold">{t('epostaPazarlama.ayar.kimlik')}</h3>
        <p className="text-xs text-muted-foreground">{meta.yonetici ? t('epostaPazarlama.ayar.kimlikAjans') : t('epostaPazarlama.ayar.kimlikMusteri')}</p>
        <div className="grid gap-3 sm:grid-cols-2">
          {meta.yonetici ? (
            <>
              <Alan etiket={t('epostaPazarlama.ayar.unvan')}>
                <input className={GIRDI} value={meta.kimlik.unvan} readOnly aria-readonly="true" />
              </Alan>
              <Alan etiket={t('epostaPazarlama.ayar.adres')}>
                <input className={GIRDI} value={meta.kimlik.adres} readOnly aria-readonly="true" />
              </Alan>
            </>
          ) : (
            <>
              <Alan etiket={t('epostaPazarlama.ayar.unvan')}>
                <input className={GIRDI} value={a.unvan} onChange={(e) => setA({ ...a, unvan: e.target.value })} data-testid="ep-ayar-unvan" />
              </Alan>
              <Alan etiket={t('epostaPazarlama.ayar.adres')}>
                <textarea className={METIN_ALANI} value={a.adres} onChange={(e) => setA({ ...a, adres: e.target.value })} data-testid="ep-ayar-adres" />
              </Alan>
            </>
          )}
          <Alan etiket={t('epostaPazarlama.ayar.gonderenAdi')} ipucu={meta.yonetici ? undefined : t('epostaPazarlama.kampanya.viaIpucu')}>
            <input className={GIRDI} value={a.gonderen_adi} onChange={(e) => setA({ ...a, gonderen_adi: e.target.value })} data-testid="ep-ayar-gonderen" />
          </Alan>
          <Alan etiket={t('epostaPazarlama.ayar.yanitAdresi')}>
            <input className={GIRDI} type="email" value={a.yanit_adresi} onChange={(e) => setA({ ...a, yanit_adresi: e.target.value })} />
          </Alan>
          <Alan etiket={t('epostaPazarlama.ayar.gonderenAdresi')} ipucu={t('epostaPazarlama.ayar.gonderenAdresiIpucu')}>
            <input className={GIRDI} value={meta.gonderen_adresi} readOnly aria-readonly="true" />
          </Alan>
        </div>
      </div>

      <div className={`${KART} space-y-3 p-4`}>
        <h3 className="font-semibold">{t('epostaPazarlama.ayar.marka')}</h3>
        <div className="grid gap-3 sm:grid-cols-3">
          <Alan etiket={t('epostaPazarlama.ayar.renk')}>
            <span className="flex items-center gap-2">
              <input type="color" value={a.marka_rengi} onChange={(e) => setA({ ...a, marka_rengi: e.target.value })} className="h-10 w-12 rounded border border-white/10 bg-transparent" aria-label={t('epostaPazarlama.ayar.renk')} />
              <input className={GIRDI} value={a.marka_rengi} onChange={(e) => setA({ ...a, marka_rengi: e.target.value })} />
            </span>
          </Alan>
          <Alan etiket={t('epostaPazarlama.ayar.logo')}>
            <input className={GIRDI} value={a.logo_url} onChange={(e) => setA({ ...a, logo_url: e.target.value })} placeholder="https://" />
          </Alan>
          <Alan etiket={t('epostaPazarlama.ayar.logoYukle')}>
            <span className="flex items-center gap-2">
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp"
                className="block w-full min-w-0 text-xs text-muted-foreground file:me-2 file:rounded-md file:border-0 file:bg-white/10 file:px-2 file:py-1.5 file:text-white"
                onChange={async (e) => {
                  const f = e.target.files?.[0];
                  if (!f) return;
                  setLogoYukleniyor(true);
                  try {
                    const g = await api.gorselYukle(f);
                    setA({ ...a, logo_url: g.url });
                  } catch (h) {
                    toast.error(hataMetni(t, h));
                  } finally {
                    setLogoYukleniyor(false);
                  }
                }}
              />
              {logoYukleniyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            </span>
          </Alan>
          <Alan etiket={t('epostaPazarlama.ayar.dil')}>
            <select className={SECIM} value={a.dil} onChange={(e) => setA({ ...a, dil: e.target.value })}>
              {meta.diller.map((x) => (
                <option key={x} value={x}>
                  {x.toUpperCase()}
                </option>
              ))}
            </select>
          </Alan>
        </div>
      </div>

      <div className={`${KART} space-y-3 p-4`}>
        <h3 className="font-semibold">{t('epostaPazarlama.ayar.takipBaslik')}</h3>
        <p className="text-xs text-muted-foreground">{t('epostaPazarlama.ayar.takipAciklama')}</p>
        <Anahtar acik={a.acilma_takibi} onDegis={(v) => setA({ ...a, acilma_takibi: v })} etiket={t('epostaPazarlama.ayar.acilma')} testid="ep-ayar-acilma" />
        <Anahtar acik={a.tiklama_takibi} onDegis={(v) => setA({ ...a, tiklama_takibi: v })} etiket={t('epostaPazarlama.ayar.tiklama')} testid="ep-ayar-tiklama" />
        <Alan etiket={t('epostaPazarlama.ayar.gunlukSinir')} ipucu={t('epostaPazarlama.ayar.gunlukSinirIpucu')} className="max-w-xs">
          <input className={GIRDI} type="number" min={1} max={5} value={a.gunluk_kisi_siniri} onChange={(e) => setA({ ...a, gunluk_kisi_siniri: Number(e.target.value) })} />
        </Alan>
      </div>

      <div className={`${KART} space-y-3 p-4`} data-testid="ep-ayar-iys">
        <h3 className="font-semibold">{t('epostaPazarlama.iys.baslik')}</h3>
        <p className="text-xs text-muted-foreground">{t('epostaPazarlama.iys.metin')}</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Alan etiket={t('epostaPazarlama.iys.soru')}>
            <select className={SECIM} value={a.iys_durumu} onChange={(e) => setA({ ...a, iys_durumu: e.target.value as AyarVeri['iys_durumu'] })} data-testid="ep-ayar-iys-durum">
              {(['bilinmiyor', 'var', 'yok'] as const).map((x) => (
                <option key={x} value={x}>
                  {t(`epostaPazarlama.iys.durum.${x}`)}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('epostaPazarlama.iys.markaKodu')}>
            <input className={GIRDI} value={a.iys_marka_kodu} onChange={(e) => setA({ ...a, iys_marka_kodu: e.target.value })} />
          </Alan>
        </div>
        {a.iys_durumu === 'yok' && <p className="text-xs text-amber-200">{t('epostaPazarlama.iys.yokUyari')}</p>}
        <p className="text-[11px] text-muted-foreground">{t('epostaPazarlama.iys.entegrasyonYok')}</p>
      </div>

      <Button onClick={() => void kaydet()} disabled={mesgul} className="gap-1.5" data-testid="ep-ayar-kaydet">
        {mesgul ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Save className="h-4 w-4" aria-hidden="true" />}
        {t('epostaPazarlama.genel.kaydet')}
      </Button>

      {meta.yonetici && meta.webhook && (
        <div className={`${KART} space-y-2 p-4`} data-testid="ep-webhook">
          <h3 className="font-semibold">{t('epostaPazarlama.ayar.webhookBaslik')}</h3>
          <p className="text-xs text-muted-foreground">{t('epostaPazarlama.ayar.webhookAciklama', { degisken: meta.webhook.ortam_degiskeni })}</p>
          <div className="flex flex-col gap-2 sm:flex-row">
            <input className={GIRDI} value={meta.webhook.adres} readOnly aria-label={t('epostaPazarlama.ayar.webhookBaslik')} />
            <Button size="sm" variant="outline" className={`${DIS_DUGME} shrink-0`} onClick={() => void kopyala(meta.webhook!.adres, t('epostaPazarlama.genel.kopyalandi'), t('epostaPazarlama.genel.kopyalanamadi'))}>
              <Copy className="h-4 w-4" aria-hidden="true" /> {t('epostaPazarlama.genel.kopyala')}
            </Button>
          </div>
          <Rozet renk={meta.webhook.imza_tanimli ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200' : 'border-amber-400/30 bg-amber-400/10 text-amber-200'}>
            {meta.webhook.imza_tanimli ? t('epostaPazarlama.ayar.imzaVar') : t('epostaPazarlama.ayar.imzaYok')}
          </Rozet>
        </div>
      )}
      {meta.yonetici && <HesapSagligiKarti api={api} dil={dil} />}
    </div>
  );
}

function HesapSagligiKarti({ api, dil }: { api: PazarlamaApi; dil: string }) {
  const { t } = useTranslation();
  const [hesaplar, setHesaplar] = useState<HesapSagligi[] | null>(null);
  const yukle = useCallback(async () => {
    try {
      setHesaplar((await api.hesaplar()).items);
    } catch (e) {
      toast.error(hataMetni(t, e));
      setHesaplar([]);
    }
  }, [api, t]);
  useEffect(() => {
    void yukle();
  }, [yukle]);
  return (
    <div className={`${KART} p-4`} data-testid="ep-hesaplar">
      <h3 className="font-semibold">{t('epostaPazarlama.ayar.hesaplarBaslik')}</h3>
      <p className="mb-3 text-xs text-muted-foreground">{t('epostaPazarlama.ayar.hesaplarAciklama')}</p>
      {hesaplar === null ? (
        <Yukleniyor />
      ) : hesaplar.length === 0 ? (
        <p className="text-sm text-muted-foreground">—</p>
      ) : (
        <ul className="divide-y divide-white/5 text-sm">
          {hesaplar.map((h) => (
            <li key={h.kapsam} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span className="min-w-0 truncate">{h.hesap ?? t('epostaPazarlama.ayar.ajans')}</span>
              <span className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                {t('epostaPazarlama.ayar.hesapSatiri', {
                  kisi: sayiYaz(h.kisi, dil),
                  gonderilen: sayiYaz(h.gonderilen_30, dil),
                  sikayet: sayiYaz(h.sikayet_30, dil),
                  geri: sayiYaz(h.geri_donen_30, dil),
                })}
                {h.askida && <Rozet renk="border-rose-400/30 bg-rose-400/10 text-rose-200">{t('epostaPazarlama.ayar.askidaKisa')}</Rozet>}
                <Button
                  size="sm"
                  variant="outline"
                  className={`${DIS_DUGME} h-7 text-xs`}
                  onClick={async () => {
                    try {
                      await api.hesapAskida(h.kapsam, !h.askida);
                      void yukle();
                    } catch (e) {
                      toast.error(hataMetni(t, e));
                    }
                  }}
                >
                  {h.askida ? t('epostaPazarlama.ayar.askiKaldir') : t('epostaPazarlama.ayar.askiyaAl')}
                </Button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
