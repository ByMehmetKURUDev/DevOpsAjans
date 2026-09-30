import { useCallback, useEffect, useState } from 'react';
import { Loader2, Trash2, UserPlus } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ekibiGetir, personelEkle, personelSil, type Personel } from '@/lib/ekip';
import { HIZMETLER } from '@/lib/talepler';

/**
 * Çalışan listesi.
 *
 * Kişi silindiğinde ona atanmış talepler silinmiyor, ataması
 * boşaltılıyor — iş kaybolmasın, kimsenin bakmadığı talep listede
 * "atanmamış" görünsün. Arka uç kaç talebin boşaldığını döndürüyor,
 * burada da söylüyoruz.
 */
export default function EkipPaneli() {
  const { t } = useTranslation();
  const [kisiler, setKisiler] = useState<Personel[]>([]);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [ad, setAd] = useState('');
  const [eposta, setEposta] = useState('');
  const [rol, setRol] = useState<'yonetici' | 'calisan'>('calisan');
  const [secilenHizmetler, setSecilenHizmetler] = useState<string[]>([]);
  const [ekleniyor, setEkleniyor] = useState(false);
  const [onayBekleyen, setOnayBekleyen] = useState<number | null>(null);

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    try {
      setKisiler(await ekibiGetir());
    } catch (e) {
      console.error(e);
      toast.error(t('ekip.yuklenemedi'));
    } finally {
      setYukleniyor(false);
    }
  }, [t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  async function ekle() {
    if (!ad.trim() || !eposta.includes('@')) {
      toast.error(t('ekip.bilgiEksik'));
      return;
    }
    setEkleniyor(true);
    try {
      await personelEkle({
        ad: ad.trim(),
        email: eposta.trim(),
        rol,
        hizmetler: secilenHizmetler.join(',') || undefined,
      });
      toast.success(t('ekip.eklendi'));
      setAd('');
      setEposta('');
      setSecilenHizmetler([]);
      await yukle();
    } catch (e) {
      console.error(e);
      toast.error(t('ekip.eklenemedi'));
    } finally {
      setEkleniyor(false);
    }
  }

  async function sil(kisi: Personel) {
    try {
      await personelSil(kisi.id);
      toast.success(t('ekip.silindi'));
      setOnayBekleyen(null);
      await yukle();
    } catch (e) {
      console.error(e);
      toast.error(t('ekip.silinemedi'));
    }
  }

  return (
    <div className="space-y-6">
      <div className="rounded-xl glass p-5">
        <h3 className="mb-4 text-sm font-semibold">{t('ekip.yeniKisi')}</h3>
        <div className="flex flex-wrap items-center gap-2">
          <Input
            value={ad}
            onChange={(e) => setAd(e.target.value)}
            placeholder={t('ekip.ad')}
            className="w-44 border-white/10 bg-white/5"
          />
          <Input
            value={eposta}
            onChange={(e) => setEposta(e.target.value)}
            placeholder={t('ekip.eposta')}
            className="w-64 border-white/10 bg-white/5"
          />
          <select
            value={rol}
            onChange={(e) => setRol(e.target.value as 'yonetici' | 'calisan')}
            className="rounded-md border border-white/10 bg-black/40 px-3 py-2 text-sm text-white"
            aria-label={t('ekip.rol')}
          >
            <option value="calisan">{t('ekip.roller.calisan')}</option>
            <option value="yonetici">{t('ekip.roller.yonetici')}</option>
          </select>
          <Button className="gap-2" disabled={ekleniyor} onClick={() => void ekle()}>
            {ekleniyor ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserPlus className="h-4 w-4" />}
            {t('ekip.ekle')}
          </Button>
        </div>

        <p className="mt-4 mb-2 text-xs uppercase tracking-widest text-muted-foreground">
          {t('ekip.hizmetler')}
        </p>
        <div className="flex flex-wrap gap-2">
          {HIZMETLER.map((h) => {
            const secili = secilenHizmetler.includes(h);
            return (
              <button
                key={h}
                type="button"
                aria-pressed={secili}
                onClick={() =>
                  setSecilenHizmetler(
                    secili ? secilenHizmetler.filter((x) => x !== h) : [...secilenHizmetler, h],
                  )
                }
                className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                  secili
                    ? 'border-primary/50 bg-primary/15 text-white'
                    : 'border-white/10 bg-white/[0.03] text-muted-foreground hover:border-white/25'
                }`}
              >
                {t(`talep.hizmetler.${h}`)}
              </button>
            );
          })}
        </div>
        <p className="mt-2 text-xs text-muted-foreground">{t('ekip.hizmetNotu')}</p>
      </div>

      <div className="grid gap-3">
        {yukleniyor ? (
          <div className="flex justify-center py-6">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        ) : (
          kisiler.map((k) => (
            <div key={k.id} className="flex flex-wrap items-center gap-4 rounded-xl glass p-4">
              <div className="min-w-[200px] flex-1">
                <div className="mb-1 flex flex-wrap items-center gap-2">
                  <span className="font-semibold">{k.ad}</span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[10px] uppercase tracking-widest ${
                      k.rol === 'yonetici'
                        ? 'bg-primary/15 text-primary'
                        : 'bg-white/5 text-muted-foreground'
                    }`}
                  >
                    {t(`ekip.roller.${k.rol || 'calisan'}`)}
                  </span>
                  {k.aktif === false ? (
                    <span className="rounded-full bg-white/5 px-2 py-0.5 text-[10px] uppercase tracking-widest text-muted-foreground">
                      {t('ekip.pasif')}
                    </span>
                  ) : null}
                </div>
                <p className="break-all text-xs text-muted-foreground">
                  {k.email}
                  {k.hizmetler
                    ? ` • ${k.hizmetler
                        .split(',')
                        .map((h) => t(`talep.hizmetler.${h.trim()}`, { defaultValue: h.trim() }))
                        .join(', ')}`
                    : ` • ${t('ekip.tumHizmetler')}`}
                </p>
              </div>

              {onayBekleyen === k.id ? (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-orange-300">{t('ekip.silOnay')}</span>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-xs text-destructive hover:text-destructive"
                    onClick={() => void sil(k)}
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
                  aria-label={t('ekip.sil')}
                  title={t('ekip.sil')}
                  className="text-destructive hover:text-destructive"
                  onClick={() => setOnayBekleyen(k.id)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              )}
            </div>
          ))
        )}

        {!yukleniyor && kisiler.length === 0 ? (
          <div className="rounded-xl glass p-8 text-center text-sm text-muted-foreground">
            {t('ekip.bosliste')}
          </div>
        ) : null}
      </div>
    </div>
  );
}
