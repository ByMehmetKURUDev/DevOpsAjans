import { useCallback, useEffect, useState } from 'react';
import {
  AlertCircle,
  ArrowLeftRight,
  Banknote,
  Clock,
  Percent,
  RefreshCw,
  Trash2,
  Webhook,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  odemeleriGetir,
  odemeSil,
  paraBicimle,
  shopierMutabakati,
  shopierWebhookKur,
  type Odeme,
  type OdemeDurumu,
  type OdemeOzeti,
} from '@/lib/odemeler';

/**
 * Tahsilat ekranı.
 *
 * Fatura sekmesi "kime ne kadar borç kestik" diyor; burası "ne geldi"
 * diyor. İkisi ayrı tabloda çünkü kısmi ödeme, iade ve başarısız deneme
 * tek satıra sığmıyor.
 *
 * Veriyi kendisi çekiyor: AdminPanel'in açılışta attığı toplu isteğe
 * eklenmedi, çünkü bu sekmeye girilmeden bilgiye gerek yok.
 */

const DURUM_RENGI: Record<OdemeDurumu, string> = {
  odendi: 'bg-emerald-500/15 text-emerald-300',
  bekliyor: 'bg-orange-500/15 text-orange-300',
  basarisiz: 'bg-red-500/15 text-red-300',
  iade: 'bg-purple-500/15 text-purple-300',
  iptal: 'bg-white/5 text-muted-foreground',
};

function Ozet({
  ikon: Ikon,
  etiket,
  deger,
  alt,
  renk,
}: {
  ikon: typeof Banknote;
  etiket: string;
  deger: string;
  alt?: string;
  renk?: string;
}) {
  return (
    <div className="p-4 rounded-xl glass">
      <div className="flex items-center gap-2 mb-2">
        <Ikon className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
        <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">{etiket}</p>
      </div>
      <p className={`text-2xl font-bold tabular-nums ${renk || 'gradient-text'}`}>{deger}</p>
      {alt ? <p className="text-xs text-muted-foreground mt-1">{alt}</p> : null}
    </div>
  );
}

export default function OdemePaneli() {
  const { t } = useTranslation();
  const [satirlar, setSatirlar] = useState<Odeme[]>([]);
  const [ozet, setOzet] = useState<OdemeOzeti | null>(null);
  const [mutabakatta, setMutabakatta] = useState(false);
  const [kuruluyor, setKuruluyor] = useState(false);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [silinen, setSilinen] = useState<number | null>(null);
  const [onayBekleyen, setOnayBekleyen] = useState<number | null>(null);

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    try {
      const sonuc = await odemeleriGetir();
      setSatirlar(sonuc.items);
      setOzet(sonuc.ozet);
    } catch (hata) {
      console.error(hata);
      toast.error(t('odeme.yuklenemedi'));
    } finally {
      setYukleniyor(false);
    }
  }, [t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  /**
   * Kaydı siler. İki adımlı: ilk tıklama satırda "Silinsin mi?" uyarısı
   * açıyor, ikincisi siliyor. Tarayıcının `confirm` kutusu yerine
   * satır içi onay, çünkü silinen kayıt `odendi` ise fatura da yeniden
   * açılıyor — kullanıcının neyi onayladığını satırda görmesi gerek.
   */
  const sil = useCallback(
    async (satir: Odeme) => {
      setSilinen(satir.id);
      try {
        await odemeSil(satir.id);
        toast.success(t('odeme.silindi'));
        setOnayBekleyen(null);
        await yukle();
      } catch (hata) {
        console.error(hata);
        toast.error(t('odeme.silinemedi'));
      } finally {
        setSilinen(null);
      }
    },
    [t, yukle],
  );

  /**
   * Shopier'e "ödeme olunca haber ver" aboneliğini kurar.
   *
   * Bir kez basılması yeterli. İlk canlı denemede ödeme alındı ama
   * panele düşmedi: webhook ucu hazırdı, Shopier adresimizi
   * bilmiyordu. Bu düğme o kaydı yapıyor.
   */
  const webhookKur = useCallback(async () => {
    setKuruluyor(true);
    try {
      const sonuc = await shopierWebhookKur();
      toast.success(sonuc.mesaj || t('odeme.webhookKuruldu'));
    } catch {
      toast.error(t('odeme.webhookHata'));
    } finally {
      setKuruluyor(false);
    }
  }, [t]);

  /**
   * Shopier'deki siparişlerle kayıtları karşılaştırır.
   *
   * Webhook'un yedeği. Bildirim kaybolursa ödeme alınmış ama fatura
   * açık kalır; bu düğme o boşluğu kapatıyor.
   */
  const mutabakatYap = useCallback(async () => {
    setMutabakatta(true);
    try {
      const sonuc = await shopierMutabakati();
      if (sonuc.islenen > 0) {
        toast.success(t('odeme.mutabakatBulundu', { sayi: sonuc.islenen }));
        await yukle();
      } else {
        toast.success(t('odeme.mutabakatTemiz'));
      }
    } catch {
      toast.error(t('odeme.mutabakatHata'));
    } finally {
      setMutabakatta(false);
    }
  }, [t, yukle]);

  const paraBirimi = satirlar[0]?.para_birimi || 'TRY';

  return (
    <div>
      <div className="flex flex-wrap justify-between items-center gap-3 mb-6">
        <h2 className="text-xl font-semibold">
          {t('odeme.baslik')} {ozet ? `(${ozet.adet})` : ''}
        </h2>
        <div className="flex items-center gap-2">
          {ozet?.shopier_hazir ? (
            <Button
              variant="ghost"
              size="sm"
              className="gap-2"
              disabled={kuruluyor}
              onClick={() => void webhookKur()}
            >
              <Webhook className={`h-4 w-4 ${kuruluyor ? 'animate-pulse' : ''}`} />
              {t('odeme.webhookKur')}
            </Button>
          ) : null}
          {ozet?.shopier_hazir ? (
            <Button
              variant="ghost"
              size="sm"
              className="gap-2"
              disabled={mutabakatta}
              onClick={() => void mutabakatYap()}
            >
              <ArrowLeftRight className={`h-4 w-4 ${mutabakatta ? 'animate-pulse' : ''}`} />
              {t('odeme.mutabakat', 'Shopier mutabakatı')}
            </Button>
          ) : null}
          <Button variant="ghost" size="sm" className="gap-2" onClick={() => void yukle()}>
            <RefreshCw className={`h-4 w-4 ${yukleniyor ? 'animate-spin' : ''}`} />
            {t('odeme.yenile')}
          </Button>
        </div>
      </div>

      {ozet && !ozet.saglayici_hazir ? (
        <div className="mb-6 flex items-start gap-3 rounded-xl border border-orange-500/35 bg-orange-500/[0.07] p-4">
          <AlertCircle className="h-4 w-4 flex-none text-orange-400 mt-0.5" aria-hidden="true" />
          <p className="text-sm text-muted-foreground">{t('odeme.saglayiciYok')}</p>
        </div>
      ) : null}

      {ozet ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 mb-6">
          <Ozet
            ikon={Banknote}
            etiket={t('odeme.tahsilEdilen')}
            deger={paraBicimle(ozet.tahsil_edilen, paraBirimi)}
          />
          <Ozet
            ikon={Clock}
            etiket={t('odeme.bekleyen')}
            deger={paraBicimle(ozet.bekleyen, paraBirimi)}
            renk="text-orange-300"
          />
          <Ozet
            ikon={Percent}
            etiket={t('odeme.komisyon')}
            deger={paraBicimle(ozet.komisyon, paraBirimi)}
            renk="text-muted-foreground"
          />
          <Ozet
            ikon={Banknote}
            etiket={t('odeme.kayitSayisi')}
            deger={String(ozet.adet)}
            renk="text-foreground"
          />
        </div>
      ) : null}

      <div className="grid gap-3">
        {satirlar.map((satir) => {
          const durum = (satir.durum || 'bekliyor') as OdemeDurumu;
          return (
            <div key={satir.id} className="p-4 rounded-xl glass flex flex-wrap items-center gap-4">
              <div className="flex-1 min-w-[200px]">
                <div className="flex items-center gap-2 mb-1 flex-wrap">
                  <span className="font-semibold">{satir.invoice_no || `#${satir.id}`}</span>
                  <span
                    className={`text-[10px] uppercase tracking-widest px-2 py-0.5 rounded-full ${DURUM_RENGI[durum]}`}
                  >
                    {t(`odeme.durum.${durum}`)}
                  </span>
                  {satir.saglayici ? (
                    <span className="text-[10px] uppercase tracking-widest px-2 py-0.5 rounded-full border border-white/10 text-muted-foreground">
                      {satir.saglayici}
                    </span>
                  ) : null}
                </div>
                <p className="text-xs text-muted-foreground break-all">
                  {satir.client_email || '—'}
                  {satir.hata_mesaji ? ` • ${satir.hata_mesaji}` : ''}
                  {satir.odendi_at
                    ? ` • ${new Date(satir.odendi_at).toLocaleString('tr-TR')}`
                    : satir.created_at
                      ? ` • ${new Date(satir.created_at).toLocaleDateString('tr-TR')}`
                      : ''}
                </p>
              </div>
              <p
                className={`text-lg font-bold tabular-nums ${
                  durum === 'odendi'
                    ? 'text-emerald-300'
                    : durum === 'bekliyor'
                      ? 'text-orange-300'
                      : 'text-muted-foreground'
                }`}
              >
                {paraBicimle(satir.tutar, satir.para_birimi)}
              </p>
              {onayBekleyen === satir.id ? (
                <div className="flex w-full items-center justify-end gap-2 sm:w-auto">
                  <span className="text-xs text-orange-300">
                    {durum === 'odendi' ? t('odeme.silOnayOdenmis') : t('odeme.silOnay')}
                  </span>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={silinen === satir.id}
                    onClick={() => void sil(satir)}
                    className="text-xs text-destructive hover:text-destructive"
                  >
                    {t('odeme.silEvet')}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-xs"
                    onClick={() => setOnayBekleyen(null)}
                  >
                    {t('odeme.silVazgec')}
                  </Button>
                </div>
              ) : (
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label={t('odeme.sil')}
                  title={t('odeme.sil')}
                  onClick={() => setOnayBekleyen(satir.id)}
                  className="text-destructive hover:text-destructive"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              )}
            </div>
          );
        })}

        {!yukleniyor && satirlar.length === 0 ? (
          <div className="p-8 rounded-xl glass text-center">
            <p className="text-sm text-muted-foreground">{t('odeme.bosliste')}</p>
          </div>
        ) : null}
      </div>
    </div>
  );
}
