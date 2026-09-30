import { useState } from 'react';
import {
  Check,
  Copy,
  ExternalLink,
  Loader2,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Save,
  Settings2,
  Trash2,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import BitisRozetleri from '@/components/BitisRozetleri';
import UptimeGrafigi from '@/components/UptimeGrafigi';
import UptimeOzetSatiri from '@/components/UptimeOzetSatiri';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  BakimHatasi,
  bakimKarti,
  izlemeGuncelle,
  kontrolEkle,
  kontrolGuncelle,
  kontrolSil,
  simdiTara,
  tarihBicimle,
  tarihGirdisi,
  yoneticiDurumSayfasi,
  yuzdeBicimle,
  type BakimKarti,
  type UptimeKontrolu,
} from '@/lib/siteBakim';

/**
 * Yönetici › Siteler › site satırının bakım kartı (Faz 2A).
 *
 * Kapalıyken: bitiş rozetleri + uptime özeti (24s/7g/30g, son kesinti).
 * "Bakım" düğmesiyle açılınca: bitiş tarihleri/sağlayıcılar (parola YOK),
 * uptime kontrolleri (ekle/duraklat/sil), 90 günlük grafik, durum sayfası.
 */
export default function SiteBakimKarti({
  kart,
  onGuncel,
}: {
  kart: BakimKarti;
  onGuncel: (k: BakimKarti) => void;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const id = kart.site_id;
  const iz = kart.izleme;
  const [acik, setAcik] = useState(false);
  const [mesgul, setMesgul] = useState<string | null>(null);
  const [kopyalandi, setKopyalandi] = useState(false);

  const [form, setForm] = useState({
    alan_adi: iz.alan_adi ?? '',
    alan_bitis: iz.alan_bitis_kaynak === 'elle' ? tarihGirdisi(iz.alan_bitis) : '',
    alan_saglayici: iz.alan_saglayici ?? '',
    hosting_bitis: tarihGirdisi(iz.hosting_bitis),
    hosting_saglayici: iz.hosting_saglayici ?? '',
    ssl_elle_yenilenir: iz.ssl_elle_yenilenir,
    notlar: iz.notlar ?? '',
  });
  const [yeni, setYeni] = useState({ url: kart.adres ?? '', aralik_dk: 5, anahtar_kelime: '', beklenen_kod: 200 });

  const hataGoster = (h: unknown) => {
    const kod = h instanceof BakimHatasi ? h.kod : 'genel';
    toast.error(t(`siteBakim.hata.${kod}`, { defaultValue: t('siteBakim.hata.genel') }));
  };

  const yenile = async () => onGuncel(await bakimKarti(id));

  const calistir = async (ad: string, is: () => Promise<void>) => {
    setMesgul(ad);
    try {
      await is();
    } catch (h) {
      hataGoster(h);
    } finally {
      setMesgul(null);
    }
  };

  const kaydet = () =>
    calistir('kaydet', async () => {
      const k = await izlemeGuncelle(id, {
        alan_adi: form.alan_adi,
        alan_bitis: form.alan_bitis,
        alan_saglayici: form.alan_saglayici,
        hosting_bitis: form.hosting_bitis,
        hosting_saglayici: form.hosting_saglayici,
        ssl_elle_yenilenir: form.ssl_elle_yenilenir,
        notlar: form.notlar,
      });
      onGuncel(k);
      toast.success(t('siteBakim.bilgi.kaydedildi'));
    });

  const tara = () =>
    calistir('tara', async () => {
      onGuncel(await simdiTara(id));
      toast.success(t('siteBakim.bilgi.tarandi'));
    });

  const ekle = () =>
    calistir('ekle', async () => {
      await kontrolEkle(id, {
        url: yeni.url.trim(),
        aralik_dk: Number(yeni.aralik_dk) || 5,
        anahtar_kelime: yeni.anahtar_kelime.trim() || undefined,
        beklenen_kod: Number(yeni.beklenen_kod) || 200,
      });
      setYeni((o) => ({ ...o, anahtar_kelime: '' }));
      await yenile();
      toast.success(t('siteBakim.kontrol.eklendi'));
    });

  const kontrolDegis = (k: UptimeKontrolu, girdi: Parameters<typeof kontrolGuncelle>[1]) =>
    calistir(`k${k.id}`, async () => {
      await kontrolGuncelle(k.id, girdi);
      await yenile();
      toast.success(t('siteBakim.kontrol.guncellendi'));
    });

  const sil = (k: UptimeKontrolu) =>
    calistir(`s${k.id}`, async () => {
      await kontrolSil(k.id);
      await yenile();
      toast.success(t('siteBakim.kontrol.silindi'));
    });

  const durumSayfasi = (ac: boolean, index?: boolean) =>
    calistir('durum', async () => {
      await yoneticiDurumSayfasi(id, ac, index);
      await yenile();
      if (index === undefined) toast.success(t(ac ? 'siteBakim.durumSayfasi.acildi' : 'siteBakim.durumSayfasi.kapandi'));
    });

  const tamAdres = kart.durum_adresi ? `${window.location.origin}${kart.durum_adresi}` : '';
  const kopyala = async () => {
    try {
      await navigator.clipboard.writeText(tamAdres);
      setKopyalandi(true);
      setTimeout(() => setKopyalandi(false), 2000);
    } catch {
      /* pano izni yoksa bağlantı zaten görünür */
    }
  };

  const girdiSinifi = 'h-9';
  const etiketSinifi = 'mb-1 block text-[11px] uppercase tracking-wide text-muted-foreground';

  return (
    <div className="space-y-2 border-t border-white/10 px-4 py-3" data-testid={`bakim-karti-${id}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1 space-y-1.5">
          <BitisRozetleri izleme={iz} siteId={id} />
          {kart.uptime && kart.uptime.kontrol_sayisi ? (
            <UptimeOzetSatiri ozet={kart.uptime} siteId={id} />
          ) : (
            <p className="text-xs text-muted-foreground">{t('siteBakim.kontrol.bos')}</p>
          )}
        </div>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => setAcik((o) => !o)}
          data-testid={`bakim-duzenle-${id}`}
          aria-expanded={acik}
        >
          <Settings2 className="mr-2 h-4 w-4" />
          {acik ? t('siteBakim.bilgi.kapat') : t('siteBakim.bilgi.duzenle')}
        </Button>
      </div>

      {acik && (
        <div className="space-y-5 pt-2">
          {/* Bitiş tarihleri ve sağlayıcılar */}
          <section className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h4 className="text-sm font-semibold">{t('siteBakim.bilgi.baslik')}</h4>
              <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                {t('siteBakim.bilgi.sonTarama', { zaman: tarihBicimle(iz.alan_kontrol_at, dil, true) })}
                <Button size="sm" variant="secondary" onClick={() => void tara()} disabled={mesgul === 'tara'}>
                  {mesgul === 'tara' ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
                  {t('siteBakim.bilgi.tara')}
                </Button>
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <label>
                <span className={etiketSinifi}>{t('siteBakim.bilgi.alanAdi')}</span>
                <Input className={girdiSinifi} value={form.alan_adi} placeholder="ornek.com"
                  onChange={(e) => setForm({ ...form, alan_adi: e.target.value })} />
              </label>
              <label>
                <span className={etiketSinifi}>
                  {t('siteBakim.bilgi.alanBitis')}
                  {iz.alan_bitis_kaynak === 'rdap' && ` · ${t('siteBakim.bilgi.alanKaynakRdap')}`}
                </span>
                <Input className={girdiSinifi} type="date" value={form.alan_bitis}
                  onChange={(e) => setForm({ ...form, alan_bitis: e.target.value })} />
                <span className="mt-1 block text-[11px] text-muted-foreground">
                  {iz.alan_rdap_hata === 'desteklenmiyor'
                    ? t('siteBakim.bilgi.rdapDesteklenmiyor')
                    : iz.alan_rdap_hata
                      ? t('siteBakim.bilgi.rdapHata', { kod: iz.alan_rdap_hata })
                      : iz.alan_bitis_kaynak === 'rdap'
                        ? `${t('siteBakim.bilgi.alanKaynakRdap')}: ${tarihBicimle(iz.alan_bitis, dil)}`
                        : t('siteBakim.bilgi.elleNotu')}
                </span>
              </label>
              <label>
                <span className={etiketSinifi}>{t('siteBakim.bilgi.alanSaglayici')}</span>
                <Input className={girdiSinifi} value={form.alan_saglayici}
                  onChange={(e) => setForm({ ...form, alan_saglayici: e.target.value })} />
              </label>
              <label>
                <span className={etiketSinifi}>{t('siteBakim.bilgi.hostingBitis')}</span>
                <Input className={girdiSinifi} type="date" value={form.hosting_bitis}
                  data-testid={`hosting-bitis-${id}`}
                  onChange={(e) => setForm({ ...form, hosting_bitis: e.target.value })} />
              </label>
              <label>
                <span className={etiketSinifi}>{t('siteBakim.bilgi.hostingSaglayici')}</span>
                <Input className={girdiSinifi} value={form.hosting_saglayici}
                  onChange={(e) => setForm({ ...form, hosting_saglayici: e.target.value })} />
              </label>
              <div>
                <span className={etiketSinifi}>{t('siteBakim.bilgi.sslBitis')}</span>
                <p className="flex h-9 items-center text-sm">
                  {iz.ssl_bitis ? tarihBicimle(iz.ssl_bitis, dil) : iz.ssl_hata ? t('siteBakim.bilgi.sslOlculemedi') : '—'}
                </p>
                <label className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                  <input type="checkbox" checked={form.ssl_elle_yenilenir}
                    onChange={(e) => setForm({ ...form, ssl_elle_yenilenir: e.target.checked })} />
                  {t('siteBakim.bilgi.sslElle')}
                </label>
              </div>
              <label className="sm:col-span-2 lg:col-span-3">
                <span className={etiketSinifi}>{t('siteBakim.bilgi.notlar')}</span>
                <textarea
                  value={form.notlar}
                  onChange={(e) => setForm({ ...form, notlar: e.target.value })}
                  rows={2}
                  className="w-full rounded-md border border-white/10 bg-background px-3 py-2 text-sm"
                />
              </label>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <Button size="sm" onClick={() => void kaydet()} disabled={mesgul === 'kaydet'} data-testid={`bakim-kaydet-${id}`}>
                {mesgul === 'kaydet' ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                {t('siteBakim.bilgi.kaydet')}
              </Button>
              <span className="text-[11px] text-muted-foreground">{t('siteBakim.bilgi.sifreNotu')}</span>
            </div>
          </section>

          {/* Uptime */}
          <section className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-4">
            <h4 className="mb-3 text-sm font-semibold">{t('siteBakim.kontrol.baslik')}</h4>
            {!kart.uptime_modulu && (
              <p className="mb-3 rounded-lg border border-amber-500/20 bg-amber-500/10 p-2 text-xs text-amber-200">
                {t('siteBakim.kontrol.modulKapali')}
              </p>
            )}
            {kart.uptime && kart.uptime.kontrol_sayisi ? (
              <div className="mb-4">
                <p className="mb-1 text-[11px] uppercase tracking-wide text-muted-foreground">
                  {t('siteBakim.uptime.grafikBaslik')} · {t('siteBakim.uptime.son90')}{' '}
                  {yuzdeBicimle(kart.uptime.oran_90g, dil)}
                </p>
                <UptimeGrafigi gunler={kart.uptime.gunler} ortalama={kart.uptime.oran_90g} testId={`uptime-grafik-${id}`} />
              </div>
            ) : null}
            <ul className="space-y-2">
              {(kart.kontroller ?? []).map((k) => (
                <li key={k.id} className="flex flex-wrap items-center gap-2 rounded-lg bg-white/[0.03] px-3 py-2 text-xs">
                  <span className={`h-2 w-2 shrink-0 rounded-full ${k.son_durum === 'up' ? 'bg-emerald-400' : k.son_durum === 'down' ? 'bg-red-500' : 'bg-white/30'}`} />
                  <span className="min-w-0 flex-1 truncate font-mono" title={k.url}>{k.url}</span>
                  <span className="text-muted-foreground">
                    {t('siteBakim.kontrol.ozet', { sayi: k.aralik_dk, kod: k.beklenen_kod })}
                    {k.anahtar_kelime ? ` · “${k.anahtar_kelime}”` : ''}
                  </span>
                  <span className="text-muted-foreground">
                    {t(`siteBakim.kontrol.${k.son_durum ?? 'ilk'}`)}
                    {k.son_kontrol_at ? ` · ${tarihBicimle(k.son_kontrol_at, dil, true)}` : ''}
                  </span>
                  <Button size="sm" variant="ghost" className="h-7 px-2" disabled={mesgul === `k${k.id}`}
                    onClick={() => void kontrolDegis(k, { acik: !k.acik })}
                    title={k.acik ? t('siteBakim.kontrol.duraklat') : t('siteBakim.kontrol.surdur')}>
                    {k.acik ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
                    <span className="sr-only">{k.acik ? t('siteBakim.kontrol.duraklat') : t('siteBakim.kontrol.surdur')}</span>
                  </Button>
                  <Button size="sm" variant="ghost" className="h-7 px-2" disabled={mesgul === `s${k.id}`}
                    onClick={() => void sil(k)} title={t('siteBakim.kontrol.sil')}>
                    <Trash2 className="h-3.5 w-3.5" />
                    <span className="sr-only">{t('siteBakim.kontrol.sil')}</span>
                  </Button>
                </li>
              ))}
            </ul>
            <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_90px_1fr_90px_auto]">
              <Input className={girdiSinifi} value={yeni.url} placeholder={t('siteBakim.kontrol.adres')}
                aria-label={t('siteBakim.kontrol.adres')} data-testid={`uptime-url-${id}`}
                onChange={(e) => setYeni({ ...yeni, url: e.target.value })} />
              <Input className={girdiSinifi} type="number" min={5} value={yeni.aralik_dk}
                aria-label={t('siteBakim.kontrol.aralik')} title={t('siteBakim.kontrol.aralik')}
                onChange={(e) => setYeni({ ...yeni, aralik_dk: Number(e.target.value) })} />
              <Input className={girdiSinifi} value={yeni.anahtar_kelime} placeholder={t('siteBakim.kontrol.anahtarKelime')}
                aria-label={t('siteBakim.kontrol.anahtarKelime')}
                onChange={(e) => setYeni({ ...yeni, anahtar_kelime: e.target.value })} />
              <Input className={girdiSinifi} type="number" value={yeni.beklenen_kod}
                aria-label={t('siteBakim.kontrol.beklenenKod')} title={t('siteBakim.kontrol.beklenenKod')}
                onChange={(e) => setYeni({ ...yeni, beklenen_kod: Number(e.target.value) })} />
              <Button size="sm" className="h-9" onClick={() => void ekle()} disabled={mesgul === 'ekle' || !yeni.url.trim()}
                data-testid={`uptime-ekle-${id}`}>
                {mesgul === 'ekle' ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />}
                {t('siteBakim.kontrol.ekle')}
              </Button>
            </div>
            <p className="mt-2 text-[11px] text-muted-foreground">{t('siteBakim.kontrol.not')}</p>
          </section>

          {/* Durum sayfası */}
          <section className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h4 className="text-sm font-semibold">{t('siteBakim.durumSayfasi.baslik')}</h4>
              <Button
                size="sm"
                variant={iz.durum_sayfasi_acik ? 'secondary' : 'default'}
                onClick={() => void durumSayfasi(!iz.durum_sayfasi_acik)}
                disabled={mesgul === 'durum'}
                data-testid={`durum-sayfasi-ac-${id}`}
              >
                {mesgul === 'durum' && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {iz.durum_sayfasi_acik ? t('siteBakim.durumSayfasi.kapat') : t('siteBakim.durumSayfasi.ac')}
              </Button>
            </div>
            {kart.durum_adresi && (
              <div className="mt-3 space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <a href={kart.durum_adresi} target="_blank" rel="noreferrer noopener"
                    className="inline-flex min-w-0 items-center gap-1 break-all text-sm text-cyan-300 hover:underline"
                    data-testid={`durum-baglanti-${id}`}>
                    {tamAdres}
                    <ExternalLink className="h-3.5 w-3.5 shrink-0" />
                  </a>
                  <Button size="sm" variant="ghost" onClick={() => void kopyala()}>
                    {kopyalandi ? <Check className="mr-2 h-4 w-4" /> : <Copy className="mr-2 h-4 w-4" />}
                    {kopyalandi ? t('siteBakim.durumSayfasi.kopyalandi') : t('siteBakim.durumSayfasi.kopyala')}
                  </Button>
                </div>
                <label className="flex items-center gap-2 text-xs text-muted-foreground">
                  <input type="checkbox" checked={iz.durum_index} disabled={mesgul === 'durum'}
                    onChange={(e) => void durumSayfasi(true, e.target.checked)} />
                  {t('siteBakim.durumSayfasi.index')}
                </label>
              </div>
            )}
            <p className="mt-2 text-[11px] text-muted-foreground">{t('siteBakim.durumSayfasi.indexNotu')}</p>
          </section>
        </div>
      )}
    </div>
  );
}
