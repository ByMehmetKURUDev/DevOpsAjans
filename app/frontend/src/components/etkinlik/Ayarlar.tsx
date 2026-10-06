import { useState, type ChangeEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Eye, ImagePlus, Loader2, Plus, Rocket, Save, Trash2, XCircle } from 'lucide-react';
import { toast } from 'sonner';

import GuvenliMarkdown from '@/components/asistanlar/GuvenliMarkdown';
import { Alan, Anahtar, DIS_DUGME, KART, METIN_ALANI, SECIM } from '@/components/randevu/ortak';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { hataMetni, yerelGirdi, yerelIso, type Etkinlik, type EtkinlikApi, type Meta } from '@/lib/etkinlik';
import { DIL_ADLARI, type Soru } from '@/lib/etkinlikOrtak';

/** Faz 6E — etkinlik ayarları: bilgiler, zaman/yer, kayıt kuralları, soru formu, yayın durumu. */

type Taslak = {
  baslik: string;
  slug: string;
  ozet: string;
  aciklama: string;
  renk: string;
  bicim: Etkinlik['bicim'];
  mekan_adi: string;
  adres: string;
  harita_url: string;
  online_baglanti: string;
  saat_dilimi: string;
  baslangic: string;
  bitis: string;
  oturumlar: { ad: string; baslangic: string; bitis: string }[];
  kapasite: string;
  kayit_acilis: string;
  kayit_kapanis: string;
  dil: Etkinlik['dil'];
  organizator_ad: string;
  organizator_eposta: string;
  organizator_url: string;
  iade_politikasi: string;
  kvkk_metni: string;
  odeme_notu: string;
  telefon: Etkinlik['telefon'];
  katilimci_adlari: boolean;
  bekleme_listesi: boolean;
  arama_motoru: boolean;
  listede_goster: boolean;
  iptal_sinir_saat: string;
  saklama_gun: string;
  sorular: Soru[];
};

function taslakKur(e: Etkinlik): Taslak {
  const tz = e.saat_dilimi;
  return {
    baslik: e.baslik, slug: e.slug, ozet: e.ozet, aciklama: e.aciklama, renk: e.renk, bicim: e.bicim, mekan_adi: e.mekan_adi,
    adres: e.adres, harita_url: e.harita_url, online_baglanti: e.online_baglanti, saat_dilimi: tz,
    baslangic: yerelGirdi(e.baslangic, tz), bitis: yerelGirdi(e.bitis, tz),
    oturumlar: e.oturumlar.map((o) => ({ ad: o.ad, baslangic: yerelGirdi(o.baslangic, tz), bitis: yerelGirdi(o.bitis, tz) })),
    kapasite: e.kapasite == null ? '' : String(e.kapasite), kayit_acilis: yerelGirdi(e.kayit_acilis, tz),
    kayit_kapanis: yerelGirdi(e.kayit_kapanis, tz), dil: e.dil, organizator_ad: e.organizator_ad,
    organizator_eposta: e.organizator_eposta, organizator_url: e.organizator_url, iade_politikasi: e.iade_politikasi,
    kvkk_metni: e.kvkk_metni, odeme_notu: e.odeme_notu, telefon: e.telefon, katilimci_adlari: e.katilimci_adlari,
    bekleme_listesi: e.bekleme_listesi, arama_motoru: e.arama_motoru, listede_goster: e.listede_goster,
    iptal_sinir_saat: String(e.iptal_sinir_saat), saklama_gun: String(e.saklama_gun), sorular: e.sorular,
  };
}

export default function Ayarlar({
  api,
  meta,
  etkinlik,
  onKaydedildi,
  onSilindi,
}: {
  api: EtkinlikApi;
  meta: Meta;
  etkinlik: Etkinlik;
  onKaydedildi: (e: Etkinlik) => void;
  onSilindi: () => void;
}) {
  const { t } = useTranslation();
  const [d, setD] = useState<Taslak>(() => taslakKur(etkinlik));
  const [kaydediliyor, setKaydediliyor] = useState(false);
  const [onizleme, setOnizleme] = useState(false);
  const alan = <K extends keyof Taslak>(k: K, v: Taslak[K]) => setD((x) => ({ ...x, [k]: v }));
  const metinAlani = (k: keyof Taslak) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => alan(k, e.target.value as never);

  const govde = () => {
    const tz = d.saat_dilimi;
    return {
      baslik: d.baslik, slug: d.slug, ozet: d.ozet, aciklama: d.aciklama, renk: d.renk, bicim: d.bicim, mekan_adi: d.mekan_adi,
      adres: d.adres, harita_url: d.harita_url, online_baglanti: d.online_baglanti, saat_dilimi: tz,
      baslangic: yerelIso(d.baslangic, tz), bitis: yerelIso(d.bitis, tz),
      oturumlar: d.oturumlar.filter((o) => o.baslangic && o.bitis).map((o) => ({ ad: o.ad, baslangic: yerelIso(o.baslangic, tz), bitis: yerelIso(o.bitis, tz) })),
      kapasite: d.kapasite.trim() === '' ? null : Number(d.kapasite), kayit_acilis: yerelIso(d.kayit_acilis, tz),
      kayit_kapanis: yerelIso(d.kayit_kapanis, tz), dil: d.dil, organizator_ad: d.organizator_ad,
      organizator_eposta: d.organizator_eposta, organizator_url: d.organizator_url, iade_politikasi: d.iade_politikasi,
      kvkk_metni: d.kvkk_metni, odeme_notu: d.odeme_notu, telefon: d.telefon, katilimci_adlari: d.katilimci_adlari,
      bekleme_listesi: d.bekleme_listesi, arama_motoru: d.arama_motoru, listede_goster: d.listede_goster,
      iptal_sinir_saat: Number(d.iptal_sinir_saat || 0), saklama_gun: Number(d.saklama_gun || 365),
      sorular: d.sorular.filter((s) => s.etiket.trim()),
    };
  };

  const kaydet = async (ek: Record<string, unknown> = {}) => {
    setKaydediliyor(true);
    try {
      const e = await api.guncelle(etkinlik.id, { ...govde(), ...ek });
      onKaydedildi(e);
      setD(taslakKur(e));
      toast.success(t('etkinlik.ayar.kaydedildi'));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setKaydediliyor(false);
    }
  };

  const durumDegistir = async (durum: Etkinlik['durum']) => {
    if (durum === 'iptal' && !window.confirm(t('etkinlik.ayar.iptalOnay'))) return;
    await kaydet({ durum });
  };

  const kapak = async (e: ChangeEvent<HTMLInputElement>) => {
    const dosya = e.target.files?.[0];
    e.target.value = '';
    if (!dosya) return;
    try {
      onKaydedildi(await api.kapakYukle(etkinlik.id, dosya));
      toast.success(t('etkinlik.ayar.kapakYuklendi'));
    } catch (h) {
      toast.error(hataMetni(t, h));
    }
  };

  const sil = async () => {
    if (!window.confirm(t('etkinlik.ayar.silOnay'))) return;
    try {
      await api.sil(etkinlik.id);
      toast.success(t('etkinlik.ayar.silindi'));
      onSilindi();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const soruGuncelle = (i: number, g: Partial<Soru>) => alan('sorular', d.sorular.map((s, j) => (j === i ? { ...s, ...g } : s)));
  const ucretliIpucu = meta.ucretli_bilet && etkinlik.ajans;

  return (
    <div className="space-y-4" data-testid="etkinlik-ayarlar">
      <div className={`${KART} flex flex-wrap items-center gap-2 p-4`}>
        <span className="me-auto text-sm text-muted-foreground">{t(`etkinlik.durumAciklama.${etkinlik.durum}`)}</span>
        {etkinlik.durum === 'taslak' && (
          <Button onClick={() => void durumDegistir('yayinda')} disabled={kaydediliyor} className="gap-1.5" data-testid="etkinlik-yayinla">
            <Rocket className="h-4 w-4" aria-hidden="true" />
            {t('etkinlik.ayar.yayinla')}
          </Button>
        )}
        {etkinlik.durum === 'yayinda' && (
          <>
            <Button variant="outline" className={DIS_DUGME} onClick={() => void durumDegistir('taslak')} disabled={kaydediliyor}>
              {t('etkinlik.ayar.taslagaAl')}
            </Button>
            <Button variant="outline" className={`${DIS_DUGME} text-red-200`} onClick={() => void durumDegistir('iptal')} disabled={kaydediliyor} data-testid="etkinlik-iptal-et">
              <XCircle className="h-4 w-4" aria-hidden="true" />
              {t('etkinlik.ayar.iptalEt')}
            </Button>
          </>
        )}
      </div>

      <div className={`${KART} grid gap-4 p-4 sm:p-6 md:grid-cols-2`}>
        <h3 className="text-base font-semibold md:col-span-2">{t('etkinlik.ayar.bilgiler')}</h3>
        <Alan etiket={t('etkinlik.alan.baslik')}>
          <Input value={d.baslik} onChange={metinAlani('baslik')} maxLength={160} data-testid="etkinlik-baslik-girdisi" />
        </Alan>
        <Alan etiket={t('etkinlik.alan.slug')} ipucu={`${meta.adres_tabani}${d.slug}`}>
          <Input value={d.slug} onChange={metinAlani('slug')} maxLength={50} dir="ltr" />
        </Alan>
        <Alan etiket={t('etkinlik.alan.ozet')} ipucu={t('etkinlik.ipucu.ozet')} className="md:col-span-2">
          <Input value={d.ozet} onChange={metinAlani('ozet')} maxLength={300} />
        </Alan>
        <div className="md:col-span-2">
          <div className="mb-1 flex items-center justify-between">
            <span className="text-sm font-medium text-white/90">{t('etkinlik.alan.aciklama')}</span>
            <button type="button" className="flex items-center gap-1 text-xs text-purple-200 hover:underline" onClick={() => setOnizleme((x) => !x)}>
              <Eye className="h-3.5 w-3.5" aria-hidden="true" />
              {onizleme ? t('etkinlik.ayar.duzenle') : t('etkinlik.ayar.onizle')}
            </button>
          </div>
          {onizleme ? (
            <div className="min-h-[120px] rounded-md border border-white/10 bg-black/20 p-3 text-sm">
              <GuvenliMarkdown metin={d.aciklama} />
            </div>
          ) : (
            <textarea className={`${METIN_ALANI} min-h-[160px]`} value={d.aciklama} onChange={metinAlani('aciklama')} maxLength={20000} />
          )}
          <span className="mt-1 block text-xs text-muted-foreground">{t('etkinlik.ipucu.markdown')}</span>
        </div>
        <div className="flex flex-wrap items-center gap-3 md:col-span-2">
          {etkinlik.kapak && <img src={etkinlik.kapak} alt="" className="h-16 w-28 rounded-lg object-cover" />}
          <label className="flex cursor-pointer items-center gap-1.5 rounded-md border border-white/20 px-3 py-2 text-sm hover:bg-white/[0.05]">
            <ImagePlus className="h-4 w-4" aria-hidden="true" />
            {t('etkinlik.ayar.kapak')}
            <input type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" onChange={(e) => void kapak(e)} />
          </label>
          {etkinlik.kapak && (
            <Button variant="ghost" size="sm" onClick={() => void api.kapakSil(etkinlik.id).then(onKaydedildi)}>
              {t('etkinlik.ayar.kapakKaldir')}
            </Button>
          )}
          <Alan etiket={t('etkinlik.alan.renk')}>
            <input type="color" value={d.renk} onChange={metinAlani('renk')} className="h-9 w-14 rounded border border-white/10 bg-transparent" />
          </Alan>
          <Alan etiket={t('etkinlik.alan.dil')}>
            <select className={SECIM} value={d.dil} onChange={(e) => alan('dil', e.target.value as Etkinlik['dil'])}>
              {meta.diller.map((x) => (
                <option key={x} value={x}>
                  {DIL_ADLARI[x]}
                </option>
              ))}
            </select>
          </Alan>
        </div>
      </div>

      <div className={`${KART} grid gap-4 p-4 sm:p-6 md:grid-cols-2`}>
        <h3 className="text-base font-semibold md:col-span-2">{t('etkinlik.ayar.zamanYer')}</h3>
        <Alan etiket={t('etkinlik.alan.baslangic')}>
          <Input type="datetime-local" value={d.baslangic} onChange={metinAlani('baslangic')} />
        </Alan>
        <Alan etiket={t('etkinlik.alan.bitis')}>
          <Input type="datetime-local" value={d.bitis} onChange={metinAlani('bitis')} />
        </Alan>
        <Alan etiket={t('etkinlik.alan.saatDilimi')}>
          <Input value={d.saat_dilimi} onChange={metinAlani('saat_dilimi')} dir="ltr" />
        </Alan>
        <Alan etiket={t('etkinlik.alan.bicim')}>
          <select className={SECIM} value={d.bicim} onChange={(e) => alan('bicim', e.target.value as Etkinlik['bicim'])} data-testid="etkinlik-bicim">
            {meta.bicimler.map((b) => (
              <option key={b} value={b}>
                {t(`etkinlik.bicim.${b}`)}
              </option>
            ))}
          </select>
        </Alan>
        {d.bicim !== 'online' && (
          <>
            <Alan etiket={t('etkinlik.alan.mekan')}>
              <Input value={d.mekan_adi} onChange={metinAlani('mekan_adi')} maxLength={160} />
            </Alan>
            <Alan etiket={t('etkinlik.alan.harita')} ipucu={t('etkinlik.ipucu.harita')}>
              <Input value={d.harita_url} onChange={metinAlani('harita_url')} dir="ltr" placeholder="https://maps.google.com/…" />
            </Alan>
            <Alan etiket={t('etkinlik.alan.adres')} className="md:col-span-2">
              <textarea className={METIN_ALANI} value={d.adres} onChange={metinAlani('adres')} maxLength={500} />
            </Alan>
          </>
        )}
        {d.bicim !== 'yuz_yuze' && (
          <Alan etiket={t('etkinlik.alan.online')} ipucu={t('etkinlik.ipucu.online')} className="md:col-span-2">
            <Input value={d.online_baglanti} onChange={metinAlani('online_baglanti')} dir="ltr" placeholder="https://meet.jit.si/…" data-testid="etkinlik-online" />
          </Alan>
        )}
        <div className="md:col-span-2">
          <span className="mb-1 block text-sm font-medium text-white/90">{t('etkinlik.alan.oturumlar')}</span>
          <span className="mb-2 block text-xs text-muted-foreground">{t('etkinlik.ipucu.oturumlar')}</span>
          {d.oturumlar.map((o, i) => (
            <div key={i} className="mb-2 grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto_auto_auto]">
              <Input value={o.ad} placeholder={t('etkinlik.alan.oturumAdi')} onChange={(e) => alan('oturumlar', d.oturumlar.map((x, j) => (j === i ? { ...x, ad: e.target.value } : x)))} />
              <Input type="datetime-local" value={o.baslangic} onChange={(e) => alan('oturumlar', d.oturumlar.map((x, j) => (j === i ? { ...x, baslangic: e.target.value } : x)))} />
              <Input type="datetime-local" value={o.bitis} onChange={(e) => alan('oturumlar', d.oturumlar.map((x, j) => (j === i ? { ...x, bitis: e.target.value } : x)))} />
              <Button variant="ghost" size="icon" aria-label={t('etkinlik.sil')} onClick={() => alan('oturumlar', d.oturumlar.filter((_, j) => j !== i))}>
                <Trash2 className="h-4 w-4" aria-hidden="true" />
              </Button>
            </div>
          ))}
          <Button variant="outline" size="sm" className={DIS_DUGME} onClick={() => alan('oturumlar', [...d.oturumlar, { ad: '', baslangic: d.baslangic, bitis: d.bitis }])}>
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('etkinlik.ayar.oturumEkle')}
          </Button>
        </div>
      </div>

      <div className={`${KART} grid gap-4 p-4 sm:p-6 md:grid-cols-2`}>
        <h3 className="text-base font-semibold md:col-span-2">{t('etkinlik.ayar.kayitKurallari')}</h3>
        <Alan etiket={t('etkinlik.alan.kapasite')} ipucu={meta.kapasite_siniri != null ? t('etkinlik.ipucu.kapasiteSiniri', { sinir: meta.kapasite_siniri }) : t('etkinlik.ipucu.kapasite')}>
          <Input type="number" min={1} value={d.kapasite} onChange={metinAlani('kapasite')} data-testid="etkinlik-kapasite" />
        </Alan>
        <Alan etiket={t('etkinlik.alan.telefon')}>
          <select className={SECIM} value={d.telefon} onChange={(e) => alan('telefon', e.target.value as Etkinlik['telefon'])}>
            {meta.telefon_secenekleri.map((x) => (
              <option key={x} value={x}>
                {t(`etkinlik.telefon.${x}`)}
              </option>
            ))}
          </select>
        </Alan>
        <Alan etiket={t('etkinlik.alan.kayitAcilis')} ipucu={t('etkinlik.ipucu.kayitAcilis')}>
          <Input type="datetime-local" value={d.kayit_acilis} onChange={metinAlani('kayit_acilis')} />
        </Alan>
        <Alan etiket={t('etkinlik.alan.kayitKapanis')} ipucu={t('etkinlik.ipucu.kayitKapanis')}>
          <Input type="datetime-local" value={d.kayit_kapanis} onChange={metinAlani('kayit_kapanis')} />
        </Alan>
        <Alan etiket={t('etkinlik.alan.iptalSinir')}>
          <Input type="number" min={0} max={1440} value={d.iptal_sinir_saat} onChange={metinAlani('iptal_sinir_saat')} />
        </Alan>
        <Alan etiket={t('etkinlik.alan.saklama')}>
          <Input type="number" min={30} max={1095} value={d.saklama_gun} onChange={metinAlani('saklama_gun')} />
        </Alan>
        <div className="grid gap-2 md:col-span-2 sm:grid-cols-2">
          <Anahtar acik={d.katilimci_adlari} onDegis={(v) => alan('katilimci_adlari', v)} etiket={t('etkinlik.alan.katilimciAdlari')} />
          <Anahtar acik={d.bekleme_listesi} onDegis={(v) => alan('bekleme_listesi', v)} etiket={t('etkinlik.alan.beklemeListesi')} />
          <Anahtar acik={d.arama_motoru} onDegis={(v) => alan('arama_motoru', v)} etiket={t('etkinlik.alan.aramaMotoru')} testid="etkinlik-arama-motoru" />
          <Anahtar acik={d.listede_goster} onDegis={(v) => alan('listede_goster', v)} etiket={t('etkinlik.alan.listedeGoster')} />
        </div>
        <div className="md:col-span-2">
          <span className="mb-1 block text-sm font-medium text-white/90">{t('etkinlik.alan.sorular')}</span>
          <span className="mb-2 block text-xs text-muted-foreground">{t('etkinlik.ipucu.sorular', { sayi: meta.en_cok_soru })}</span>
          {d.sorular.map((s, i) => (
            <div key={s.id || i} className="mb-2 grid gap-2 rounded-lg border border-white/10 p-2 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_auto_auto]">
              <Input value={s.etiket} placeholder={t('etkinlik.alan.soruEtiket')} maxLength={200} onChange={(e) => soruGuncelle(i, { etiket: e.target.value })} />
              <select className={SECIM} value={s.tur} onChange={(e) => soruGuncelle(i, { tur: e.target.value as Soru['tur'] })}>
                {meta.soru_turleri.map((x) => (
                  <option key={x} value={x}>
                    {t(`etkinlik.soruTuru.${x}`)}
                  </option>
                ))}
              </select>
              <Anahtar acik={s.zorunlu} onDegis={(v) => soruGuncelle(i, { zorunlu: v })} etiket={t('etkinlik.alan.zorunlu')} />
              <Button variant="ghost" size="icon" aria-label={t('etkinlik.sil')} onClick={() => alan('sorular', d.sorular.filter((_, j) => j !== i))}>
                <Trash2 className="h-4 w-4" aria-hidden="true" />
              </Button>
              {s.tur === 'secim' && (
                <Input
                  className="sm:col-span-4"
                  value={s.secenekler.join(', ')}
                  placeholder={t('etkinlik.alan.secenekler')}
                  onChange={(e) => soruGuncelle(i, { secenekler: e.target.value.split(',').map((x) => x.trim()).filter(Boolean) })}
                />
              )}
            </div>
          ))}
          {d.sorular.length < meta.en_cok_soru && (
            <Button variant="outline" size="sm" className={DIS_DUGME} onClick={() => alan('sorular', [...d.sorular, { id: '', etiket: '', tur: 'metin', zorunlu: false, secenekler: [] }])}>
              <Plus className="h-4 w-4" aria-hidden="true" />
              {t('etkinlik.ayar.soruEkle')}
            </Button>
          )}
        </div>
      </div>

      <div className={`${KART} grid gap-4 p-4 sm:p-6 md:grid-cols-2`}>
        <h3 className="text-base font-semibold md:col-span-2">{t('etkinlik.ayar.organizator')}</h3>
        <Alan etiket={t('etkinlik.alan.organizatorAd')}>
          <Input value={d.organizator_ad} onChange={metinAlani('organizator_ad')} maxLength={160} />
        </Alan>
        <Alan etiket={t('etkinlik.alan.organizatorEposta')}>
          <Input value={d.organizator_eposta} onChange={metinAlani('organizator_eposta')} type="email" dir="ltr" />
        </Alan>
        <Alan etiket={t('etkinlik.alan.organizatorUrl')} className="md:col-span-2">
          <Input value={d.organizator_url} onChange={metinAlani('organizator_url')} dir="ltr" placeholder="https://" />
        </Alan>
        <Alan etiket={t('etkinlik.alan.iadePolitikasi')} className="md:col-span-2">
          <textarea className={METIN_ALANI} value={d.iade_politikasi} onChange={metinAlani('iade_politikasi')} maxLength={3000} />
        </Alan>
        <Alan etiket={t('etkinlik.alan.odemeNotu')} ipucu={ucretliIpucu ? t('etkinlik.ipucu.odemeNotuAjans') : t('etkinlik.ipucu.odemeNotu')} className="md:col-span-2">
          <textarea className={METIN_ALANI} value={d.odeme_notu} onChange={metinAlani('odeme_notu')} maxLength={1000} />
        </Alan>
        <Alan etiket={t('etkinlik.alan.kvkk')} ipucu={t('etkinlik.ipucu.kvkk')} className="md:col-span-2">
          <textarea className={METIN_ALANI} value={d.kvkk_metni} onChange={metinAlani('kvkk_metni')} maxLength={3000} />
        </Alan>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <Button variant="ghost" className="gap-1.5 text-red-300" onClick={() => void sil()}>
          <Trash2 className="h-4 w-4" aria-hidden="true" />
          {t('etkinlik.ayar.sil')}
        </Button>
        <Button onClick={() => void kaydet()} disabled={kaydediliyor} className="gap-1.5" data-testid="etkinlik-kaydet">
          {kaydediliyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Save className="h-4 w-4" aria-hidden="true" />}
          {t('etkinlik.kaydet')}
        </Button>
      </div>
    </div>
  );
}
