import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, Plus, RotateCcw, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Alan, Anahtar, DIS_DUGME, GIRDI, KART, SECIM, YasalNot, Yukleniyor } from '@/components/ik/ortak';
import { dar, gunAdlari, gunYaz, hataMetni, type Ayarlar, type IkApi, type KidemKurali, type Meta, type Tatiller } from '@/lib/ik';

const YASAL = ['dogum', 'babalik', 'evlilik', 'olum'] as const;

/** Faz 6I — İK ayarları: çalışma günleri, yıllık izin kuralları (4857 m.53 varsayılanı), yasal izin günleri,
 *  resmi tatiller (sabitler kapatılabilir; dini bayramlar elle eklenir), vardiya uyarıları. Bilgilendirme amaçlıdır. */
export default function AyarlarBolumu({ api, meta, onMeta }: { api: IkApi; meta: Meta; onMeta: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [a, setA] = useState<Ayarlar>(meta.ayarlar);
  const [mesgul, setMesgul] = useState(false);
  const [yil, setYil] = useState(Number(meta.bugun.slice(0, 4)));
  const [tatiller, setTatiller] = useState<Tatiller | null>(null);
  const [yeni, setYeni] = useState({ tarih: '', bitis: '', ad: '', yarim: false });
  const salt = meta.salt_okunur;
  const gunler = gunAdlari(dil, 'long');

  useEffect(() => setA(meta.ayarlar), [meta.ayarlar]);

  const tatilYukle = useCallback(async () => {
    try {
      setTatiller(await api.tatiller(yil));
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  }, [api, yil, t]);

  useEffect(() => {
    void tatilYukle();
  }, [tatilYukle]);

  const kaydet = async (g: Record<string, unknown>, mesaj = t('ik.kaydedildi')) => {
    setMesgul(true);
    try {
      const yeniA = await api.ayarlarKaydet(g);
      setA(yeniA);
      toast.success(mesaj);
      onMeta();
      await tatilYukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  const kidemDegis = (i: number, alan: keyof KidemKurali, deger: string) => {
    const k = a.kidem_kurallari.map((x) => ({ ...x }));
    k[i][alan] = Number(deger.replace(/\D/g, '') || 0);
    setA({ ...a, kidem_kurallari: k });
  };

  const tatilEkle = async () => {
    try {
      await api.tatilEkle({ tarih: yeni.tarih, bitis: yeni.bitis || undefined, ad: yeni.ad.trim(), yarim: yeni.yarim });
      setYeni({ tarih: '', bitis: '', ad: '', yarim: false });
      toast.success(t('ik.ayar.tatilEklendi'));
      await tatilYukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const sabitDegis = (anahtar: string, acik: boolean) => {
    const kume = new Set(a.kapali_sabitler);
    if (acik) kume.delete(anahtar);
    else kume.add(anahtar);
    void kaydet({ kapali_sabitler: [...kume] });
  };

  return (
    <fieldset disabled={salt} className="space-y-4">
      <YasalNot />
      <div className={`${KART} space-y-3 p-4`}>
        <h3 className="text-base font-semibold">{t('ik.ayar.genel')}</h3>
        <Alan etiket={t('ik.ayar.firmaAdi')} ipucu={t('ik.ayar.firmaIpucu')}>
          <input className={GIRDI} value={a.firma_adi} onChange={(e) => setA({ ...a, firma_adi: e.target.value })} maxLength={160} data-testid="ik-ayar-firma" />
        </Alan>
        <div>
          <span className="mb-1 block text-sm font-medium text-white/90">{t('ik.ayar.calismaGunleri')}</span>
          <div className="flex flex-wrap gap-2" data-testid="ik-ayar-gunler">
            {gunler.map((g, i) => (
              <label key={g} className="flex items-center gap-1.5 rounded-lg border border-white/10 px-2 py-1 text-sm">
                <input
                  type="checkbox"
                  className="h-4 w-4 accent-purple-500"
                  checked={a.calisma_gunleri.includes(i)}
                  onChange={(e) =>
                    setA({ ...a, calisma_gunleri: e.target.checked ? [...a.calisma_gunleri, i].sort() : a.calisma_gunleri.filter((x) => x !== i) })
                  }
                />
                {g}
              </label>
            ))}
          </div>
          <p className="mt-1 text-xs text-muted-foreground">{t('ik.ayar.calismaIpucu')}</p>
        </div>
      </div>

      <div className={`${KART} space-y-3 p-4`}>
        <h3 className="text-base font-semibold">{t('ik.ayar.yillikBaslik')}</h3>
        <p className="text-xs text-muted-foreground">{t('ik.ayar.yillikAciklama')}</p>
        <ul className="space-y-2" data-testid="ik-ayar-kidem">
          {a.kidem_kurallari.map((k, i) => (
            <li key={i} className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-muted-foreground">{t('ik.ayar.kidemEnAz')}</span>
              <input className={dar(GIRDI, 'w-20')} inputMode="numeric" value={k.yil} onChange={(e) => kidemDegis(i, 'yil', e.target.value)} aria-label={t('ik.ayar.kidemYil')} />
              <span className="text-muted-foreground">{t('ik.ayar.kidemYilSonra')}</span>
              <input className={dar(GIRDI, 'w-20')} inputMode="numeric" value={k.gun} onChange={(e) => kidemDegis(i, 'gun', e.target.value)} aria-label={t('ik.ayar.kidemGun')} />
              <span className="text-muted-foreground">{t('ik.gun')}</span>
              {a.kidem_kurallari.length > 1 && (
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-8 w-8"
                  aria-label={t('ik.sil')}
                  onClick={() => setA({ ...a, kidem_kurallari: a.kidem_kurallari.filter((_, j) => j !== i) })}
                >
                  <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                </Button>
              )}
            </li>
          ))}
        </ul>
        {a.kidem_kurallari.length < 6 && (
          <button
            type="button"
            className="flex items-center gap-1 text-xs text-purple-200 hover:underline"
            onClick={() => {
              const son = a.kidem_kurallari[a.kidem_kurallari.length - 1];
              setA({ ...a, kidem_kurallari: [...a.kidem_kurallari, { yil: (son?.yil || 0) + 5, gun: son?.gun || 14 }] });
            }}
          >
            <Plus className="h-3.5 w-3.5" aria-hidden="true" />
            {t('ik.ayar.kuralEkle')}
          </button>
        )}
        <Alan etiket={t('ik.ayar.yasEnAz')} ipucu={t('ik.ayar.yasIpucu')}>
          <input className={dar(GIRDI, 'w-24')} inputMode="numeric" value={a.yas_en_az_gun} onChange={(e) => setA({ ...a, yas_en_az_gun: Number(e.target.value.replace(/\D/g, '') || 0) })} />
        </Alan>
        <div className="grid gap-2 sm:grid-cols-4">
          {YASAL.map((k) => (
            <Alan key={k} etiket={t(`ik.tur.${k}`)} ipucu={k === 'dogum' ? t('ik.ayar.takvimGunu') : t('ik.ayar.isGunu')}>
              <input
                className={GIRDI}
                inputMode="numeric"
                value={a.yasal_gunler[k] ?? ''}
                onChange={(e) => setA({ ...a, yasal_gunler: { ...a.yasal_gunler, [k]: Number(e.target.value.replace(/\D/g, '') || 0) } })}
              />
            </Alan>
          ))}
        </div>
        <p className="text-xs text-muted-foreground">{t('ik.ayar.yasalKaynak')}</p>
      </div>

      <div className={`${KART} space-y-3 p-4`}>
        <h3 className="text-base font-semibold">{t('ik.ayar.vardiyaBaslik')}</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          <Anahtar acik={a.uyari_izinli} onDegis={(v) => setA({ ...a, uyari_izinli: v })} etiket={t('ik.ayar.uyariIzinli')} />
          <Anahtar acik={a.uyari_cakisma} onDegis={(v) => setA({ ...a, uyari_cakisma: v })} etiket={t('ik.ayar.uyariCakisma')} />
          <div className="space-y-1">
            <Anahtar acik={a.uyari_dinlenme} onDegis={(v) => setA({ ...a, uyari_dinlenme: v })} etiket={t('ik.ayar.uyariDinlenme')} />
            <input
              className={dar(GIRDI, 'w-24')}
              inputMode="numeric"
              value={a.en_az_dinlenme_saat}
              onChange={(e) => setA({ ...a, en_az_dinlenme_saat: Number(e.target.value.replace(/\D/g, '') || 0) })}
              aria-label={t('ik.ayar.dinlenmeSaat')}
            />
          </div>
          <div className="space-y-1">
            <Anahtar acik={a.uyari_haftalik} onDegis={(v) => setA({ ...a, uyari_haftalik: v })} etiket={t('ik.ayar.uyariHaftalik')} />
            <input
              className={dar(GIRDI, 'w-24')}
              inputMode="numeric"
              value={a.haftalik_en_cok_saat}
              onChange={(e) => setA({ ...a, haftalik_en_cok_saat: Number(e.target.value.replace(/\D/g, '') || 0) })}
              aria-label={t('ik.ayar.haftalikSaat')}
            />
          </div>
        </div>
        <p className="text-xs text-muted-foreground">{t('ik.ayar.vardiyaKaynak')}</p>
      </div>

      {!salt && (
        <div className="flex flex-wrap justify-between gap-2">
          <Button variant="outline" className={DIS_DUGME} disabled={mesgul} onClick={() => window.confirm(t('ik.ayar.varsayilanOnay')) && void kaydet({ varsayilana_don: true }, t('ik.ayar.varsayilanaDonuldu'))}>
            <RotateCcw className="h-4 w-4" aria-hidden="true" />
            {t('ik.ayar.varsayilan')}
          </Button>
          <Button
            disabled={mesgul}
            onClick={() =>
              void kaydet({
                firma_adi: a.firma_adi,
                calisma_gunleri: a.calisma_gunleri,
                kidem_kurallari: a.kidem_kurallari,
                yas_en_az_gun: a.yas_en_az_gun,
                yasal_gunler: a.yasal_gunler,
                uyari_izinli: a.uyari_izinli,
                uyari_cakisma: a.uyari_cakisma,
                uyari_dinlenme: a.uyari_dinlenme,
                en_az_dinlenme_saat: a.en_az_dinlenme_saat,
                uyari_haftalik: a.uyari_haftalik,
                haftalik_en_cok_saat: a.haftalik_en_cok_saat,
              })
            }
            data-testid="ik-ayar-kaydet"
          >
            {mesgul && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {t('ik.kaydet')}
          </Button>
        </div>
      )}

      <div className={`${KART} space-y-3 p-4`} data-testid="ik-ayar-tatiller">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-base font-semibold">{t('ik.ayar.tatillerBaslik')}</h3>
          <select className={dar(SECIM, 'w-auto')} value={yil} onChange={(e) => setYil(Number(e.target.value))} aria-label={t('ik.ayar.yil')}>
            {[yil - 1, yil, yil + 1, yil + 2].map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </div>
        <p className="text-xs text-amber-100">{t('ik.ayar.diniBayramNotu')}</p>
        {!tatiller ? (
          <Yukleniyor />
        ) : (
          <>
            <ul className="grid gap-1.5 sm:grid-cols-2">
              {tatiller.sabit.map((x) => (
                <li key={x.sabit} className="flex items-center justify-between gap-2 rounded-lg border border-white/10 bg-black/20 px-3 py-1.5 text-xs">
                  <span className="min-w-0">
                    <span className="block font-medium">{t(`ik.ayar.sabit.${x.anahtar}`)}</span>
                    <span className="text-muted-foreground">{gunYaz(x.tarih, dil)}</span>
                  </span>
                  <Anahtar acik={!x.kapali} onDegis={(v) => sabitDegis(x.sabit, v)} etiket={t('ik.ayar.tatilSayilsin')} />
                </li>
              ))}
            </ul>
            <h4 className="pt-2 text-sm font-semibold">{t('ik.ayar.eklenenler')}</h4>
            {tatiller.eklenen.length === 0 ? (
              <p className="text-xs text-muted-foreground">{t('ik.ayar.eklenenYok')}</p>
            ) : (
              <ul className="space-y-1">
                {tatiller.eklenen.map((x) => (
                  <li key={x.id} className="flex items-center gap-2 rounded-lg border border-white/10 bg-black/20 px-3 py-1.5 text-xs">
                    <span className="min-w-0 flex-1 truncate">
                      {gunYaz(x.tarih, dil)} — {x.ad}
                      {x.yarim ? ` (${t('ik.ayar.yarimGun')})` : ''}
                    </span>
                    {!salt && (
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-7 w-7"
                        aria-label={t('ik.sil')}
                        onClick={() =>
                          void api
                            .tatilSil(x.id)
                            .then(tatilYukle)
                            .catch((e) => toast.error(hataMetni(t, e)))
                        }
                      >
                        <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {!salt && (
              <div className="grid gap-2 border-t border-white/10 pt-3 sm:grid-cols-4">
                <Alan etiket={t('ik.ayar.tatilTarih')}>
                  <input className={GIRDI} type="date" value={yeni.tarih} onChange={(e) => setYeni({ ...yeni, tarih: e.target.value })} data-testid="ik-tatil-tarih" />
                </Alan>
                <Alan etiket={t('ik.ayar.tatilBitis')}>
                  <input className={GIRDI} type="date" value={yeni.bitis} min={yeni.tarih} onChange={(e) => setYeni({ ...yeni, bitis: e.target.value })} />
                </Alan>
                <Alan etiket={t('ik.ayar.tatilAd')} className="sm:col-span-2">
                  <input className={GIRDI} value={yeni.ad} onChange={(e) => setYeni({ ...yeni, ad: e.target.value })} maxLength={120} placeholder={t('ik.ayar.tatilAdOrnek')} data-testid="ik-tatil-ad" />
                </Alan>
                <div className="sm:col-span-3">
                  <Anahtar acik={yeni.yarim} onDegis={(v) => setYeni({ ...yeni, yarim: v })} etiket={t('ik.ayar.ilkGunYarim')} />
                </div>
                <Button onClick={() => void tatilEkle()} disabled={!yeni.tarih || !yeni.ad.trim()} data-testid="ik-tatil-ekle">
                  <Plus className="h-4 w-4" aria-hidden="true" />
                  {t('ik.ayar.tatilEkle')}
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </fieldset>
  );
}
