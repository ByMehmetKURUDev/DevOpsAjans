import { useCallback, useEffect, useState } from 'react';
import {
  Check,
  Code2,
  Globe,
  Loader2,
  Lock,
  Plus,
  RefreshCw,
  ShieldCheck,
  Trash2,
  Unlock,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  erisimKaydet,
  gommeKoduGetir,
  ISLEMLER,
  jetonYenile,
  PLATFORMLAR,
  siteEkle,
  siteGunluguGetir,
  siteSil,
  siteleriGetir,
  type GunlukSatiri,
  type MusteriSitesi,
  type SitePlatformu,
} from '@/lib/musteriSiteleri';

/**
 * Müşteri siteleri ve bakım erişimi.
 *
 * Müşterinin şifresi burada TUTULMUYOR. Bakım için ajansın kendi
 * hesabı açılıyor ve yapılan her iş erişim günlüğüne yazılıyor.
 * Müşteri izni kendi panelinden tek düğmeyle geri aldığında bu
 * ekrandan kayıt açılamıyor.
 *
 * Silme onayı satır içinde iki adımda; window.confirm tarayıcıyı
 * kilitlediği için panelde hiçbir yerde kullanılmıyor.
 */

const ISLEM_ETIKETI: Record<string, string> = {
  giris: 'Giriş',
  guncelleme: 'Güncelleme',
  yedek: 'Yedek',
  eklenti: 'Eklenti',
  duzeltme: 'Düzeltme',
  izin_acildi: 'İzin açıldı',
  izin_kapandi: 'İzin kapandı',
};

function tarih(deger?: string | null): string {
  if (!deger) return '—';
  const d = new Date(deger);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString('tr-TR');
}

export default function MusteriSiteleri() {
  const { t } = useTranslation();
  const [siteler, setSiteler] = useState<MusteriSitesi[]>([]);
  const [yukleniyor, setYukleniyor] = useState(true);

  const [eposta, setEposta] = useState('');
  const [ad, setAd] = useState('');
  const [adres, setAdres] = useState('');
  const [platform, setPlatform] = useState<SitePlatformu>('wordpress');
  const [atanan, setAtanan] = useState('');
  const [ekleniyor, setEkleniyor] = useState(false);

  const [acikSite, setAcikSite] = useState<number | null>(null);
  const [gunluk, setGunluk] = useState<GunlukSatiri[]>([]);
  const [gunlukYukleniyor, setGunlukYukleniyor] = useState(false);
  const [gomme, setGomme] = useState<string>('');
  const [kopyalandi, setKopyalandi] = useState(false);
  const [islem, setIslem] = useState<string>('guncelleme');
  const [aciklama, setAciklama] = useState('');
  const [kaydediliyor, setKaydediliyor] = useState(false);
  const [silinecek, setSilinecek] = useState<number | null>(null);

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    try {
      setSiteler(await siteleriGetir());
    } catch {
      toast.error(t('site.yuklenemedi', 'Siteler yüklenemedi.'));
    } finally {
      setYukleniyor(false);
    }
  }, [t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const detayAc = useCallback(
    async (site: MusteriSitesi) => {
      if (acikSite === site.id) {
        setAcikSite(null);
        return;
      }
      setAcikSite(site.id);
      setGunluk([]);
      setGomme('');
      setKopyalandi(false);
      setAciklama('');
      setGunlukYukleniyor(true);
      try {
        const [g, k] = await Promise.all([
          siteGunluguGetir(site.id),
          gommeKoduGetir(site.id).catch(() => null),
        ]);
        setGunluk(g);
        if (k) setGomme(k.kod);
      } catch {
        toast.error(t('site.gunlukAlinamadi', 'Günlük alınamadı.'));
      } finally {
        setGunlukYukleniyor(false);
      }
    },
    [acikSite, t],
  );

  const ekle = async () => {
    const e = eposta.trim().toLowerCase();
    if (!e.includes('@') || !ad.trim()) {
      toast.error(t('site.eksikAlan', 'Müşteri e-postası ve site adı gerekli.'));
      return;
    }
    setEkleniyor(true);
    try {
      const yeni = await siteEkle({
        client_email: e,
        ad: ad.trim(),
        adres: adres.trim() || undefined,
        platform,
        atanan: atanan.trim().toLowerCase() || undefined,
      });
      setSiteler((o) => [yeni, ...o]);
      setEposta('');
      setAd('');
      setAdres('');
      setAtanan('');
      toast.success(t('site.eklendi', 'Site eklendi.'));
    } catch {
      toast.error(t('site.eklenemedi', 'Site eklenemedi.'));
    } finally {
      setEkleniyor(false);
    }
  };

  const kaydet = async (site: MusteriSitesi) => {
    setKaydediliyor(true);
    try {
      const satir = await erisimKaydet(site.id, islem, aciklama.trim() || undefined);
      setGunluk((o) => [satir, ...o]);
      setAciklama('');
      toast.success(t('site.erisimYazildi', 'Erişim günlüğe yazıldı.'));
    } catch {
      // İzin kapalıysa sunucu 409 dönüyor; kullanıcıya nedenini söylüyoruz.
      toast.error(
        t('site.erisimYazilamadi', 'Kaydedilemedi. Müşteri bakım iznini kapatmış olabilir.'),
      );
    } finally {
      setKaydediliyor(false);
    }
  };

  const yenile = async (site: MusteriSitesi) => {
    try {
      const k = await jetonYenile(site.id);
      setGomme(k.kod);
      setKopyalandi(false);
      toast.success(t('site.jetonYenilendi', 'Jeton yenilendi. Eski kod artık çalışmıyor.'));
    } catch {
      toast.error(t('site.jetonYenilenemedi', 'Jeton yenilenemedi.'));
    }
  };

  const kopyala = async () => {
    try {
      await navigator.clipboard.writeText(gomme);
      setKopyalandi(true);
      setTimeout(() => setKopyalandi(false), 2000);
    } catch {
      toast.error(t('site.kopyalanamadi', 'Kopyalanamadı.'));
    }
  };

  const sil = async (id: number) => {
    try {
      await siteSil(id);
      setSiteler((o) => o.filter((s) => s.id !== id));
      if (acikSite === id) setAcikSite(null);
      toast.success(t('site.silindi', 'Site listeden çıkarıldı. Erişim günlüğü korundu.'));
    } catch {
      toast.error(t('site.silinemedi', 'Silinemedi.'));
    } finally {
      setSilinecek(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Yeni site */}
      <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
          <Globe className="h-4 w-4" />
          {t('site.yeniBaslik', 'Bakımını üstlendiğimiz site ekle')}
        </h3>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
          <Input
            value={eposta}
            onChange={(e) => setEposta(e.target.value)}
            placeholder={t('site.musteriEpostasi', 'Müşteri e-postası')}
          />
          <Input
            value={ad}
            onChange={(e) => setAd(e.target.value)}
            placeholder={t('site.siteAdi', 'Site adı')}
          />
          <Input
            value={adres}
            onChange={(e) => setAdres(e.target.value)}
            placeholder="https://..."
          />
          <select
            value={platform}
            onChange={(e) => setPlatform(e.target.value as SitePlatformu)}
            className="h-10 rounded-md border border-white/10 bg-background px-3 text-sm"
          >
            {PLATFORMLAR.map((p) => (
              <option key={p.anahtar} value={p.anahtar}>
                {p.etiket}
              </option>
            ))}
          </select>
          <Input
            value={atanan}
            onChange={(e) => setAtanan(e.target.value)}
            placeholder={t('site.bakanKisi', 'Bakan kişi (e-posta)')}
          />
        </div>
        <Button onClick={ekle} disabled={ekleniyor} className="mt-3" size="sm">
          {ekleniyor ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />}
          {t('site.ekle', 'Ekle')}
        </Button>
        <p className="mt-3 text-xs text-muted-foreground">
          {t(
            'site.sifreNotu',
            'Müşterinin şifresi panelde saklanmıyor. Bakım için ayrı bir hesap açılıyor; yapılan her iş günlüğe yazılıyor ve müşteri izni tek düğmeyle geri alabiliyor.',
          )}
        </p>
      </div>

      {/* Liste */}
      {yukleniyor ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          {t('genel.yukleniyor', 'Yükleniyor…')}
        </div>
      ) : siteler.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {t('site.bos', 'Henüz site eklenmemiş.')}
        </p>
      ) : (
        <div className="space-y-2">
          {siteler.map((site) => (
            <div key={site.id} className="rounded-xl border border-white/10 bg-white/[0.02]">
              <div className="flex flex-wrap items-center gap-3 p-4">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-medium">{site.ad}</span>
                    {site.bakim_izni ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] text-emerald-300">
                        <Unlock className="h-3 w-3" />
                        {t('site.izinAcik', 'Bakım izni açık')}
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-full bg-orange-500/15 px-2 py-0.5 text-[11px] text-orange-300">
                        <Lock className="h-3 w-3" />
                        {t('site.izinKapali', 'İzin kapalı')}
                      </span>
                    )}
                  </div>
                  <p className="truncate text-xs text-muted-foreground">
                    {site.client_email}
                    {site.adres ? ` · ${site.adres}` : ''}
                    {site.atanan ? ` · ${site.atanan}` : ''}
                  </p>
                </div>
                <Button variant="ghost" size="sm" onClick={() => void detayAc(site)}>
                  <ShieldCheck className="mr-2 h-4 w-4" />
                  {acikSite === site.id ? t('site.kapat', 'Kapat') : t('site.detay', 'Erişim ve kod')}
                </Button>
                {silinecek === site.id ? (
                  <div className="flex items-center gap-1">
                    <Button variant="destructive" size="sm" onClick={() => void sil(site.id)}>
                      {t('site.silOnay', 'Evet, sil')}
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => setSilinecek(null)}>
                      {t('genel.vazgec', 'Vazgeç')}
                    </Button>
                  </div>
                ) : (
                  <Button variant="ghost" size="sm" onClick={() => setSilinecek(site.id)}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                )}
              </div>

              {acikSite === site.id && (
                <div className="space-y-4 border-t border-white/10 p-4">
                  {/* Gömme kodu */}
                  <div>
                    <h4 className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      <Code2 className="h-3.5 w-3.5" />
                      {t('site.gommeBaslik', 'Geri bildirim düğmesi — siteye yapıştırılacak satır')}
                    </h4>
                    <pre className="overflow-x-auto rounded-lg border border-white/10 bg-black/40 p-3 text-[11px] leading-relaxed">
                      {gomme || '—'}
                    </pre>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <Button size="sm" variant="secondary" onClick={() => void kopyala()} disabled={!gomme}>
                        {kopyalandi ? <Check className="mr-2 h-4 w-4" /> : <Code2 className="mr-2 h-4 w-4" />}
                        {kopyalandi ? t('site.kopyalandi', 'Kopyalandı') : t('site.kopyala', 'Kopyala')}
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => void yenile(site)}>
                        <RefreshCw className="mr-2 h-4 w-4" />
                        {t('site.jetonYenile', 'Jetonu yenile')}
                      </Button>
                    </div>
                    <p className="mt-2 text-xs text-muted-foreground">
                      {t(
                        'site.gommeNotu',
                        'Bu satır müşterinin sitesinin </body> etiketinden hemen önce duruyor. Sayfanın kenarında logolu bir düğme çıkıyor; oradan yazılan her istek bu müşterinin hesabına destek talebi olarak düşüyor.',
                      )}
                    </p>
                  </div>

                  {/* Erişim kaydı */}
                  <div>
                    <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      {t('site.erisimBaslik', 'Yaptığın işi günlüğe yaz')}
                    </h4>
                    {site.bakim_izni ? (
                      <div className="flex flex-wrap gap-2">
                        <select
                          value={islem}
                          onChange={(e) => setIslem(e.target.value)}
                          className="h-9 rounded-md border border-white/10 bg-background px-3 text-sm"
                        >
                          {ISLEMLER.map((i) => (
                            <option key={i} value={i}>
                              {ISLEM_ETIKETI[i] ?? i}
                            </option>
                          ))}
                        </select>
                        <Input
                          value={aciklama}
                          onChange={(e) => setAciklama(e.target.value)}
                          placeholder={t('site.neYapildi', 'Ne yapıldı?')}
                          className="h-9 flex-1 min-w-[200px]"
                        />
                        <Button size="sm" onClick={() => void kaydet(site)} disabled={kaydediliyor}>
                          {kaydediliyor && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                          {t('site.yaz', 'Yaz')}
                        </Button>
                      </div>
                    ) : (
                      <p className="rounded-lg border border-orange-500/20 bg-orange-500/10 p-3 text-xs text-orange-200">
                        {t(
                          'site.izinYok',
                          'Müşteri bakım iznini kapatmış. İzin açılana kadar bu siteye erişim kaydı yazılamıyor.',
                        )}
                      </p>
                    )}
                  </div>

                  {/* Günlük */}
                  <div>
                    <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      {t('site.gunlukBaslik', 'Erişim günlüğü')}
                    </h4>
                    {gunlukYukleniyor ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : gunluk.length === 0 ? (
                      <p className="text-xs text-muted-foreground">
                        {t('site.gunlukBos', 'Henüz kayıt yok.')}
                      </p>
                    ) : (
                      <ul className="space-y-1 text-xs">
                        {gunluk.map((g) => (
                          <li
                            key={g.id}
                            className="flex flex-wrap items-baseline gap-x-2 rounded-md bg-white/[0.02] px-3 py-2"
                          >
                            <span className="font-medium">{ISLEM_ETIKETI[g.islem] ?? g.islem}</span>
                            <span className="text-muted-foreground">{g.kim}</span>
                            <span className="ml-auto text-muted-foreground">{tarih(g.created_at)}</span>
                            {g.aciklama && (
                              <span className="w-full text-muted-foreground">{g.aciklama}</span>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
