import { useCallback, useEffect, useState } from 'react';
import { Eye, Globe, Loader2, Lock, ShieldCheck, Unlock } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  bakimIzni,
  kendiGunlugum,
  kendiSitelerim,
  type GunlukSatiri,
  type MusteriSitesi,
} from '@/lib/musteriSiteleri';

/**
 * Müşterinin kendi sitelerini ve bakım iznini yönettiği bölüm.
 *
 * Buranın varlık sebebi şu: ajansın müşterinin sitesine erişmesi için
 * onun şifresini almak yerine ayrı bir hesap açılıyor ve yapılan her
 * iş günlüğe yazılıyor. Müşteri o günlüğü burada görüyor, izni de
 * buradan tek düğmeyle geri alıyor.
 *
 * Günlüğü müşteriye açmak bu düzenin şartı — gören taraf olmadan
 * "denetlenebilir erişim" ajansın kendi kendine verdiği bir sözden
 * ibaret kalırdı.
 */

const ISLEM_ETIKETI: Record<string, string> = {
  giris: 'Giriş yapıldı',
  guncelleme: 'Güncelleme',
  yedek: 'Yedek alındı',
  eklenti: 'Eklenti işlemi',
  duzeltme: 'Düzeltme',
  izin_acildi: 'Bakım izni açıldı',
  izin_kapandi: 'Bakım izni kapatıldı',
};

function tarih(deger?: string | null): string {
  if (!deger) return '—';
  const d = new Date(deger);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString('tr-TR');
}

export default function SiteBakimIzni() {
  const { t } = useTranslation();
  const [siteler, setSiteler] = useState<MusteriSitesi[]>([]);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [degisen, setDegisen] = useState<number | null>(null);
  const [acik, setAcik] = useState<number | null>(null);
  const [gunluk, setGunluk] = useState<GunlukSatiri[]>([]);
  const [gunlukYukleniyor, setGunlukYukleniyor] = useState(false);

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    try {
      setSiteler(await kendiSitelerim());
    } catch {
      toast.error(t('sitem.yuklenemedi', 'Siteler yüklenemedi.'));
    } finally {
      setYukleniyor(false);
    }
  }, [t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const izinDegistir = async (site: MusteriSitesi) => {
    const yeni = !site.bakim_izni;
    setDegisen(site.id);
    try {
      const guncel = await bakimIzni(site.id, yeni);
      setSiteler((o) => o.map((s) => (s.id === site.id ? guncel : s)));
      toast.success(
        yeni
          ? t('sitem.izinVerildi', 'Bakım izni açıldı.')
          : t('sitem.izinAlindi', 'Bakım izni geri alındı.'),
      );
      if (acik === site.id) {
        setGunluk(await kendiGunlugum(site.id));
      }
    } catch {
      toast.error(t('sitem.izinDegismedi', 'İzin değiştirilemedi.'));
    } finally {
      setDegisen(null);
    }
  };

  const gunlukAc = async (site: MusteriSitesi) => {
    if (acik === site.id) {
      setAcik(null);
      return;
    }
    setAcik(site.id);
    setGunluk([]);
    setGunlukYukleniyor(true);
    try {
      setGunluk(await kendiGunlugum(site.id));
    } catch {
      toast.error(t('sitem.gunlukAlinamadi', 'Günlük alınamadı.'));
    } finally {
      setGunlukYukleniyor(false);
    }
  };

  if (yukleniyor) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        {t('genel.yukleniyor', 'Yükleniyor…')}
      </div>
    );
  }

  if (siteler.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        {t('sitem.bos', 'Bakımını üstlendiğimiz bir siteniz görünmüyor.')}
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/[0.06] p-4">
        <h3 className="mb-1 flex items-center gap-2 text-sm font-semibold">
          <ShieldCheck className="h-4 w-4 text-emerald-400" />
          {t('sitem.sozBaslik', 'Sitenize nasıl erişiyoruz')}
        </h3>
        <p className="text-xs leading-relaxed text-muted-foreground">
          {t(
            'sitem.sozMetni',
            'Şifrenizi istemiyoruz ve saklamıyoruz. Sitenizde bize ayrı bir hesap açılıyor; o hesapla yapılan her iş aşağıdaki günlüğe yazılıyor. Bakım iznini istediğiniz an tek düğmeyle geri alabilirsiniz — izin kapalıyken ekibimiz sitenize işlem kaydı açamaz.',
          )}
        </p>
      </div>

      {siteler.map((site) => (
        <div key={site.id} className="rounded-xl border border-white/10 bg-white/[0.02]">
          <div className="flex flex-wrap items-center gap-3 p-4">
            <Globe className="h-4 w-4 shrink-0 text-muted-foreground" />
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium">{site.ad}</p>
              <p className="truncate text-xs text-muted-foreground">
                {site.adres || '—'}
                {site.izin_at ? ` · ${t('sitem.sonDegisiklik', 'son değişiklik')}: ${tarih(site.izin_at)}` : ''}
              </p>
            </div>

            {site.bakim_izni ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2.5 py-1 text-[11px] text-emerald-300">
                <Unlock className="h-3 w-3" />
                {t('sitem.acik', 'Bakım izni açık')}
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 rounded-full bg-orange-500/15 px-2.5 py-1 text-[11px] text-orange-300">
                <Lock className="h-3 w-3" />
                {t('sitem.kapali', 'Bakım izni kapalı')}
              </span>
            )}

            <Button
              size="sm"
              variant={site.bakim_izni ? 'ghost' : 'default'}
              onClick={() => void izinDegistir(site)}
              disabled={degisen === site.id}
            >
              {degisen === site.id && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {site.bakim_izni
                ? t('sitem.geriAl', 'İzni geri al')
                : t('sitem.izinVer', 'Bakım izni ver')}
            </Button>

            <Button size="sm" variant="ghost" onClick={() => void gunlukAc(site)}>
              <Eye className="mr-2 h-4 w-4" />
              {acik === site.id ? t('sitem.gizle', 'Gizle') : t('sitem.gunluk', 'Erişim günlüğü')}
            </Button>
          </div>

          {acik === site.id && (
            <div className="border-t border-white/10 p-4">
              {gunlukYukleniyor ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : gunluk.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  {t('sitem.gunlukBos', 'Sitenize henüz hiçbir erişim yapılmamış.')}
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
                      {g.aciklama && <span className="w-full text-muted-foreground">{g.aciklama}</span>}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
