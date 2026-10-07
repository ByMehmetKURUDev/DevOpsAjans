import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, Plus, RotateCcw, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Alan, Anahtar, GIRDI, KART, Not, Rozet, SECIM, Yukleniyor } from '@/components/hukuk/ortak';
import { gunYaz, hataMetni, type Ayarlar as AyarTipi, type Dosya, type HukukApi, type Meta, type Muvekkil, type Tatil } from '@/lib/hukuk';

/**
 * Faz 6H — hukuk ayarları: büro adı, hatırlatma günleri ve saati, adli tatil (HMK m.102/104 varsayılanları
 * değiştirilebilir), resmî tatiller (sabit ulusal günler hazır; dini bayramlar her yıl elle) ve silinenler.
 */
export default function Ayarlar({ api, meta }: { api: HukukApi; meta: Meta }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [a, setA] = useState<AyarTipi | null>(null);
  const [gunlerMetni, setGunlerMetni] = useState('');
  const [kayit, setKayit] = useState(false);
  const [tatiller, setTatiller] = useState<Tatil[] | null>(null);
  const [yeni, setYeni] = useState({ ad: '', tarih: '', bitis: '', yarim: false, tekrar: false, tur: 'dini' });
  const [silinen, setSilinen] = useState<{ muvekkiller: Muvekkil[]; dosyalar: Dosya[]; gun: number } | null>(null);

  const yukle = useCallback(async () => {
    try {
      const [x, tl, sl] = await Promise.all([api.ayarlar(), api.tatiller(), api.silinenler()]);
      setA(x);
      setGunlerMetni(x.hatirlatma_gunleri.join(', '));
      setTatiller(tl.items);
      setSilinen(sl);
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  }, [api, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  if (!a) return <Yukleniyor />;

  const kaydet = async () => {
    setKayit(true);
    try {
      const gunler = gunlerMetni
        .split(/[,\s]+/)
        .map((x) => Number(x))
        .filter((x) => Number.isInteger(x) && x >= 0);
      const x = await api.ayarlariKaydet({ ...a, hatirlatma_gunleri: gunler });
      setA(x);
      setGunlerMetni(x.hatirlatma_gunleri.join(', '));
      toast.success(t('hukuk.ortak.kaydedildi'));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setKayit(false);
    }
  };

  const tatilEkle = async () => {
    try {
      await api.tatilEkle({ ad: yeni.ad, tarih: yeni.tarih, bitis: yeni.bitis || null, yarim: yeni.yarim, tekrar: yeni.tekrar, tur: yeni.tur as Tatil['tur'] });
      setYeni({ ad: '', tarih: '', bitis: '', yarim: false, tekrar: false, tur: 'dini' });
      setTatiller((await api.tatiller()).items);
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const tatilTarihi = (x: Tatil) => {
    if (x.tekrar) {
      const g = new Intl.DateTimeFormat(dil, { day: 'numeric', month: 'long', timeZone: 'UTC' });
      return `${g.format(new Date(`2000-${x.ay_gun}T00:00:00Z`))} · ${t('hukuk.ayar.tatil.tekrar')}`;
    }
    return x.bitis ? `${gunYaz(x.tarih, dil)} – ${gunYaz(x.bitis, dil)}` : gunYaz(x.tarih, dil);
  };

  return (
    <div className="space-y-4" data-testid="hukuk-ayarlar">
      <div className={`${KART} space-y-3 p-4 sm:p-6`}>
        <h3 className="text-base font-semibold">{t('hukuk.ayar.baslik')}</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          <Alan etiket={t('hukuk.ayar.buroAdi')}>
            <input className={GIRDI} value={a.buro_adi} maxLength={160} onChange={(e) => setA({ ...a, buro_adi: e.target.value })} data-testid="hukuk-ayar-buro" />
          </Alan>
          <Alan etiket={t('hukuk.ayar.hatirlatma')} ipucu={t('hukuk.ayar.hatirlatmaIpucu')}>
            <input className={GIRDI} value={gunlerMetni} onChange={(e) => setGunlerMetni(e.target.value)} dir="ltr" />
          </Alan>
          <Alan etiket={t('hukuk.ayar.sabah')}>
            <input className={GIRDI} type="time" value={a.sabah_saati} onChange={(e) => setA({ ...a, sabah_saati: e.target.value })} />
          </Alan>
          <div className="grid grid-cols-3 gap-2">
            <Alan etiket={t('hukuk.ayar.adliBas')}>
              <input className={GIRDI} value={a.adli_tatil_bas} maxLength={5} dir="ltr" onChange={(e) => setA({ ...a, adli_tatil_bas: e.target.value })} />
            </Alan>
            <Alan etiket={t('hukuk.ayar.adliBit')}>
              <input className={GIRDI} value={a.adli_tatil_bit} maxLength={5} dir="ltr" onChange={(e) => setA({ ...a, adli_tatil_bit: e.target.value })} />
            </Alan>
            <Alan etiket={t('hukuk.ayar.adliUzatma')}>
              <input className={GIRDI} type="number" min={0} max={60} value={a.adli_tatil_uzatma_gun} onChange={(e) => setA({ ...a, adli_tatil_uzatma_gun: Number(e.target.value) || 0 })} />
            </Alan>
          </div>
        </div>
        <Anahtar acik={a.adli_tatil_varsayilan} onDegis={(v) => setA({ ...a, adli_tatil_varsayilan: v })} etiket={t('hukuk.ayar.adliVarsayilan')} />
        <Not>{t('hukuk.ayar.yasalNot')}</Not>
        <Button onClick={() => void kaydet()} disabled={kayit} className="gap-1.5" data-testid="hukuk-ayar-kaydet">
          {kayit && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
          {t('hukuk.ortak.kaydet')}
        </Button>
      </div>

      <div className={`${KART} space-y-3 p-4 sm:p-6`} data-testid="hukuk-tatiller">
        <h3 className="text-base font-semibold">{t('hukuk.ayar.tatil.baslik')}</h3>
        <Not tur="uyari" testid="hukuk-tatil-notu">
          {t('hukuk.ayar.tatil.aciklama')}
        </Not>
        <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_150px_150px_130px] sm:items-end">
          <Alan etiket={t('hukuk.ayar.tatil.ad')}>
            <input className={GIRDI} value={yeni.ad} maxLength={120} onChange={(e) => setYeni({ ...yeni, ad: e.target.value })} data-testid="hukuk-tatil-ad" />
          </Alan>
          <Alan etiket={t('hukuk.ayar.tatil.tarih')}>
            <input className={GIRDI} type="date" value={yeni.tarih} onChange={(e) => setYeni({ ...yeni, tarih: e.target.value })} data-testid="hukuk-tatil-tarih" />
          </Alan>
          <Alan etiket={t('hukuk.ayar.tatil.bitis')}>
            <input className={GIRDI} type="date" value={yeni.bitis} onChange={(e) => setYeni({ ...yeni, bitis: e.target.value })} />
          </Alan>
          <Alan etiket={t('hukuk.ayar.tatil.turEtiket')}>
            <select className={SECIM} value={yeni.tur} onChange={(e) => setYeni({ ...yeni, tur: e.target.value })}>
              {(['dini', 'diger', 'sabit'] as const).map((x) => (
                <option key={x} value={x}>
                  {t(`hukuk.ayar.tatil.tur.${x}`)}
                </option>
              ))}
            </select>
          </Alan>
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <Anahtar acik={yeni.yarim} onDegis={(v) => setYeni({ ...yeni, yarim: v })} etiket={t('hukuk.ayar.tatil.yarim')} />
          <Anahtar acik={yeni.tekrar} onDegis={(v) => setYeni({ ...yeni, tekrar: v })} etiket={t('hukuk.ayar.tatil.tekrar')} />
          <Button size="sm" className="gap-1" disabled={!yeni.ad.trim() || !yeni.tarih} onClick={() => void tatilEkle()} data-testid="hukuk-tatil-ekle">
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('hukuk.ayar.tatil.ekle')}
          </Button>
        </div>
        {tatiller === null ? (
          <Yukleniyor />
        ) : tatiller.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('hukuk.ayar.tatil.bos')}</p>
        ) : (
          <ul className="space-y-1" data-testid="hukuk-tatil-liste">
            {tatiller.map((x) => (
              <li key={x.id} className="flex flex-wrap items-center gap-2 border-b border-white/5 py-1.5 text-sm" data-tatil-tur={x.tur}>
                <span className="min-w-0 flex-1 truncate">{x.ad}</span>
                <span className="text-xs text-muted-foreground">{tatilTarihi(x)}</span>
                <Rozet>{t(`hukuk.ayar.tatil.tur.${x.tur}`)}</Rozet>
                {x.yarim && <Rozet renk="border-amber-400/40 bg-amber-500/15 text-amber-200">{t('hukuk.ayar.tatil.yarim')}</Rozet>}
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-7 w-7"
                  aria-label={t('hukuk.ortak.sil')}
                  onClick={async () => {
                    await api.tatilSil(x.id).catch((e) => toast.error(hataMetni(t, e)));
                    setTatiller((await api.tatiller()).items);
                  }}
                >
                  <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className={`${KART} space-y-3 p-4 sm:p-6`} data-testid="hukuk-silinenler">
        <h3 className="text-base font-semibold">{t('hukuk.ayar.silinenler.baslik')}</h3>
        <p className="text-xs text-muted-foreground">{t('hukuk.ayar.silinenler.aciklama', { gun: meta.silinenler_gun })}</p>
        {!silinen ? (
          <Yukleniyor />
        ) : silinen.muvekkiller.length + silinen.dosyalar.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('hukuk.ayar.silinenler.bos')}</p>
        ) : (
          <ul className="space-y-1">
            {[...silinen.dosyalar.map((d) => ({ tur: 'dosya' as const, id: d.id, ad: `${d.baslik} · ${d.muvekkil_ad || ''}`, at: d.silindi_at })),
              ...silinen.muvekkiller.map((m) => ({ tur: 'muvekkil' as const, id: m.id, ad: m.ad, at: m.silindi_at }))].map((x) => (
              <li key={`${x.tur}-${x.id}`} className="flex flex-wrap items-center gap-2 border-b border-white/5 py-1.5 text-sm">
                <Rozet>{x.tur === 'dosya' ? t('hukuk.alt.dosyalar') : t('hukuk.alt.muvekkiller')}</Rozet>
                <span className="min-w-0 flex-1 truncate">{x.ad}</span>
                <span className="text-xs text-muted-foreground">{gunYaz(x.at, dil)}</span>
                <Button
                  size="sm"
                  variant="ghost"
                  className="gap-1"
                  onClick={async () => {
                    try {
                      if (x.tur === 'dosya') await api.dosyaGeriAl(x.id);
                      else await api.muvekkilGeriAl(x.id);
                      setSilinen(await api.silinenler());
                    } catch (e) {
                      toast.error(hataMetni(t, e));
                    }
                  }}
                >
                  <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('hukuk.ayar.silinenler.geriAl')}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
