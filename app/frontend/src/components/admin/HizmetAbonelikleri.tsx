import { useCallback, useEffect, useState } from 'react';
import { FileText, Loader2, Pause, Play, Plus, Send, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  abonelikDurumu,
  abonelikEkle,
  abonelikSil,
  abonelikleriGetir,
  raporSil,
  raporYayimla,
  raporYaz,
  raporlariGetir,
  type Abonelik,
  type Rapor,
} from '@/lib/abonelikler';
import { HIZMETLER } from '@/lib/talepler';

/**
 * Hizmet abonelikleri ve aylık raporlar.
 *
 * Bir abonelik "her ay şu iş yapılıyor" demek; raporu o aboneliğin
 * altında yazılıyor. Taslak müşteri panelinde görünmüyor — yarım
 * rapor müşteriye gitmesin diye. Yayınlandığında abonelik bir sonraki
 * döneme ilerliyor, yani "sıradaki rapor" hep doğru ayı gösteriyor.
 */

const DURUM_RENGI: Record<string, string> = {
  aktif: 'bg-emerald-500/15 text-emerald-300',
  duraklatildi: 'bg-orange-500/15 text-orange-300',
  iptal: 'bg-white/5 text-muted-foreground',
};

export default function HizmetAbonelikleri() {
  const { t } = useTranslation();
  const [abonelikler, setAbonelikler] = useState<Abonelik[]>([]);
  const [raporlar, setRaporlar] = useState<Rapor[]>([]);
  const [yukleniyor, setYukleniyor] = useState(true);

  const [eposta, setEposta] = useState('');
  const [musteriAdi, setMusteriAdi] = useState('');
  const [hizmet, setHizmet] = useState<string>(HIZMETLER[0]);
  const [tutar, setTutar] = useState('');
  const [ekleniyor, setEkleniyor] = useState(false);

  // Rapor yazılan abonelik ve taslak metni.
  const [raporAbonelik, setRaporAbonelik] = useState<number | null>(null);
  const [raporOzet, setRaporOzet] = useState('');
  const [raporBaslik, setRaporBaslik] = useState('');
  const [kaydediliyor, setKaydediliyor] = useState(false);
  const [silinecek, setSilinecek] = useState<number | null>(null);

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    try {
      const [a, r] = await Promise.all([abonelikleriGetir(), raporlariGetir()]);
      setAbonelikler(a);
      setRaporlar(r);
    } catch (e) {
      console.error(e);
      toast.error(t('abonelik.yuklenemedi'));
    } finally {
      setYukleniyor(false);
    }
  }, [t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  async function ekle() {
    if (!eposta.includes('@')) {
      toast.error(t('abonelik.epostaGerekli'));
      return;
    }
    setEkleniyor(true);
    try {
      const sayi = tutar.trim().replace(',', '.');
      await abonelikEkle({
        client_email: eposta.trim(),
        client_name: musteriAdi.trim() || undefined,
        hizmet,
        tutar: sayi ? Number(sayi) : undefined,
        periyot: 'aylik',
      });
      toast.success(t('abonelik.eklendi'));
      setEposta('');
      setMusteriAdi('');
      setTutar('');
      await yukle();
    } catch (e) {
      console.error(e);
      toast.error(t('abonelik.eklenemedi'));
    } finally {
      setEkleniyor(false);
    }
  }

  async function durumDegistir(a: Abonelik) {
    const yeni = a.durum === 'aktif' ? 'duraklatildi' : 'aktif';
    try {
      await abonelikDurumu(a.id, yeni);
      await yukle();
    } catch (e) {
      console.error(e);
      toast.error(t('abonelik.durumDegismedi'));
    }
  }

  async function raporKaydet(a: Abonelik) {
    if (!raporOzet.trim()) {
      toast.error(t('abonelik.ozetGerekli'));
      return;
    }
    setKaydediliyor(true);
    try {
      await raporYaz({
        subscription_id: a.id,
        baslik: raporBaslik.trim() || undefined,
        ozet: raporOzet.trim(),
      });
      toast.success(t('abonelik.raporKaydedildi'));
      setRaporAbonelik(null);
      setRaporOzet('');
      setRaporBaslik('');
      await yukle();
    } catch (e) {
      console.error(e);
      toast.error(t('abonelik.raporKaydedilemedi'));
    } finally {
      setKaydediliyor(false);
    }
  }

  async function yayimla(r: Rapor) {
    try {
      await raporYayimla(r.id);
      toast.success(t('abonelik.raporYayimlandi'));
      await yukle();
    } catch (e) {
      console.error(e);
      toast.error(t('abonelik.raporYayimlanamadi'));
    }
  }

  const raporlariBul = (abonelikId: number) =>
    raporlar.filter((r) => r.subscription_id === abonelikId);

  return (
    <div className="space-y-6">
      <div className="rounded-xl glass p-5">
        <h3 className="mb-4 text-sm font-semibold">{t('abonelik.yeni')}</h3>
        <div className="flex flex-wrap items-center gap-2">
          <Input
            value={eposta}
            onChange={(e) => setEposta(e.target.value)}
            placeholder={t('abonelik.musteriEposta')}
            className="w-64 border-white/10 bg-white/5"
          />
          <Input
            value={musteriAdi}
            onChange={(e) => setMusteriAdi(e.target.value)}
            placeholder={t('abonelik.musteriAdi')}
            className="w-44 border-white/10 bg-white/5"
          />
          <select
            value={hizmet}
            onChange={(e) => setHizmet(e.target.value)}
            aria-label={t('talep.hizmetSec')}
            className="rounded-md border border-white/10 bg-black/40 px-3 py-2 text-sm text-white"
          >
            {HIZMETLER.map((h) => (
              <option key={h} value={h}>
                {t(`talep.hizmetler.${h}`)}
              </option>
            ))}
          </select>
          <Input
            value={tutar}
            onChange={(e) => setTutar(e.target.value)}
            inputMode="decimal"
            placeholder={t('abonelik.aylikTutar')}
            className="w-36 border-white/10 bg-white/5"
          />
          <Button className="gap-2" disabled={ekleniyor} onClick={() => void ekle()}>
            {ekleniyor ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            {t('abonelik.ekle')}
          </Button>
        </div>
      </div>

      {yukleniyor ? (
        <div className="flex justify-center py-8">
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        </div>
      ) : abonelikler.length === 0 ? (
        <div className="rounded-xl glass p-8 text-center text-sm text-muted-foreground">
          {t('abonelik.bosliste')}
        </div>
      ) : (
        <div className="grid gap-3">
          {abonelikler.map((a) => {
            const kendiRaporlari = raporlariBul(a.id);
            return (
              <div key={a.id} className="rounded-xl glass p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-[220px]">
                    <div className="mb-1 flex flex-wrap items-center gap-2">
                      <span className="font-semibold">
                        {t(`talep.hizmetler.${a.hizmet}`, { defaultValue: a.hizmet })}
                      </span>
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] uppercase tracking-widest ${
                          DURUM_RENGI[a.durum || 'aktif']
                        }`}
                      >
                        {t(`abonelik.durum.${a.durum || 'aktif'}`)}
                      </span>
                    </div>
                    <p className="break-all text-xs text-muted-foreground">
                      {a.client_name ? `${a.client_name} • ` : ''}
                      {a.client_email}
                      {a.tutar ? ` • ${a.tutar} ${a.para_birimi || 'TRY'}/${t('abonelik.ay')}` : ''}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {t('abonelik.sonrakiRapor')}: <span className="text-primary">{a.sonraki_rapor || '—'}</span>
                    </p>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      size="sm"
                      variant="ghost"
                      className="gap-2 text-xs"
                      onClick={() => {
                        setRaporAbonelik(raporAbonelik === a.id ? null : a.id);
                        setRaporOzet('');
                        setRaporBaslik('');
                      }}
                    >
                      <FileText className="h-4 w-4" />
                      {raporAbonelik === a.id ? t('abonelik.vazgec') : t('abonelik.raporYaz')}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="gap-2 text-xs"
                      onClick={() => void durumDegistir(a)}
                    >
                      {a.durum === 'aktif' ? (
                        <Pause className="h-4 w-4" />
                      ) : (
                        <Play className="h-4 w-4" />
                      )}
                      {a.durum === 'aktif' ? t('abonelik.duraklat') : t('abonelik.devamEttir')}
                    </Button>

                    {silinecek === a.id ? (
                      <span className="flex items-center gap-2">
                        <span className="text-xs text-orange-300">{t('abonelik.silOnay')}</span>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="text-xs text-destructive hover:text-destructive"
                          onClick={async () => {
                            try {
                              await abonelikSil(a.id);
                              toast.success(t('abonelik.silindi'));
                              setSilinecek(null);
                              await yukle();
                            } catch (e) {
                              console.error(e);
                              toast.error(t('abonelik.silinemedi'));
                            }
                          }}
                        >
                          {t('odeme.silEvet')}
                        </Button>
                        <Button size="sm" variant="ghost" className="text-xs" onClick={() => setSilinecek(null)}>
                          {t('odeme.silVazgec')}
                        </Button>
                      </span>
                    ) : (
                      <Button
                        size="sm"
                        variant="ghost"
                        aria-label={t('abonelik.sil')}
                        title={t('abonelik.sil')}
                        className="text-destructive hover:text-destructive"
                        onClick={() => setSilinecek(a.id)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                </div>

                {raporAbonelik === a.id ? (
                  <div className="mt-4 space-y-2 rounded-lg border border-dashed border-primary/30 bg-primary/[0.04] p-3">
                    <p className="text-xs text-muted-foreground">
                      {t('abonelik.raporDonem', { donem: a.sonraki_rapor || '—' })}
                    </p>
                    <Input
                      value={raporBaslik}
                      onChange={(e) => setRaporBaslik(e.target.value)}
                      placeholder={t('abonelik.raporBaslik')}
                      className="border-white/10 bg-black/40 text-sm"
                    />
                    <Textarea
                      rows={4}
                      value={raporOzet}
                      onChange={(e) => setRaporOzet(e.target.value)}
                      placeholder={t('abonelik.raporOzet')}
                      className="border-white/10 bg-black/40 text-sm"
                    />
                    <Button
                      size="sm"
                      className="gap-2 text-xs"
                      disabled={kaydediliyor}
                      onClick={() => void raporKaydet(a)}
                    >
                      {kaydediliyor ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <FileText className="h-3.5 w-3.5" />
                      )}
                      {t('abonelik.taslakKaydet')}
                    </Button>
                  </div>
                ) : null}

                {kendiRaporlari.length > 0 ? (
                  <div className="mt-4 space-y-2 border-t border-white/10 pt-3">
                    {kendiRaporlari.map((r) => (
                      <div
                        key={r.id}
                        className="flex flex-wrap items-center justify-between gap-3 text-sm"
                      >
                        <div className="min-w-[180px]">
                          <span className="font-mono text-xs text-primary">{r.donem}</span>
                          <span className="ml-2">{r.baslik || t('abonelik.raporsuzBaslik')}</span>
                          <span
                            className={`ml-2 rounded-full px-2 py-0.5 text-[10px] uppercase tracking-widest ${
                              r.durum === 'yayinlandi'
                                ? 'bg-emerald-500/15 text-emerald-300'
                                : 'bg-white/5 text-muted-foreground'
                            }`}
                          >
                            {t(`abonelik.raporDurum.${r.durum || 'taslak'}`)}
                          </span>
                        </div>
                        <div className="flex items-center gap-1">
                          {r.durum !== 'yayinlandi' ? (
                            <Button
                              size="sm"
                              variant="ghost"
                              className="gap-1.5 text-xs"
                              onClick={() => void yayimla(r)}
                            >
                              <Send className="h-3.5 w-3.5" />
                              {t('abonelik.yayimla')}
                            </Button>
                          ) : null}
                          <Button
                            size="sm"
                            variant="ghost"
                            aria-label={t('abonelik.raporSil')}
                            title={t('abonelik.raporSil')}
                            className="text-destructive hover:text-destructive"
                            onClick={async () => {
                              try {
                                await raporSil(r.id);
                                await yukle();
                              } catch (e) {
                                console.error(e);
                                toast.error(t('abonelik.silinemedi'));
                              }
                            }}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
