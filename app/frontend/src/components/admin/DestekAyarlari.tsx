import { Suspense, useCallback, useEffect, useState, type FormEvent } from 'react';
import { CalendarOff, Clock, Loader2, MessageSquareText, Pencil, Save, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { ekliLazy } from '@/i18n/ekliLazy';
import {
  DestekHatasi,
  hazirCevapEkle,
  hazirCevapGuncelle,
  hazirCevapSil,
  hazirCevaplar,
  slaAyarlari,
  slaAyarlariKaydet,
  type HazirCevap,
  type Oncelik,
  type SlaAyarlari,
} from '@/lib/destek';

/**
 * Yönetici › Destek › "SLA ve hazır cevaplar" (Faz 2C).
 *
 * SLA: mesai saatleri (Türkiye), çalışma günleri, tatil günleri listesi ve
 * öncelik başına ilk yanıt / çözüm hedefleri (mesai dakikası; burada saat
 * olarak giriliyor). Hazır cevaplar: başlık + metin, {musteri_adi},
 * {talep_no}, {konu} değişkenleri.
 */

// Faz 2F: "E-postadan talep" kurulum kartı (ek paket `destekKurallari`).
const EpostaTalepKarti = ekliLazy('destekKurallari', () => import('@/components/admin/EpostaTalepKarti'));

const KART = 'cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6';
const ONCELIKLER: Oncelik[] = ['acil', 'yuksek', 'normal', 'dusuk'];

export default function DestekAyarlari() {
  const { t } = useTranslation();
  const [ayar, setAyar] = useState<SlaAyarlari | null>(null);
  const [tatilMetni, setTatilMetni] = useState('');
  const [kaydediliyor, setKaydediliyor] = useState(false);
  const [cevaplar, setCevaplar] = useState<HazirCevap[]>([]);
  const [form, setForm] = useState<{ id: number | null; baslik: string; metin: string }>({ id: null, baslik: '', metin: '' });

  const hata = useCallback(
    (h: unknown) => toast.error(t(`yardim.hata.${h instanceof DestekHatasi ? h.kod : 'genel'}`, { defaultValue: t('yardim.hata.genel') })),
    [t]
  );

  const cevaplariYukle = useCallback(() => {
    hazirCevaplar()
      .then(setCevaplar)
      .catch(hata);
  }, [hata]);

  useEffect(() => {
    slaAyarlari()
      .then((a) => {
        setAyar(a);
        setTatilMetni(a.tatiller.join('\n'));
      })
      .catch(hata);
    cevaplariYukle();
  }, [hata, cevaplariYukle]);

  const kaydet = async () => {
    if (!ayar) return;
    setKaydediliyor(true);
    try {
      const tatiller = tatilMetni
        .split(/[\s,;]+/)
        .map((x) => x.trim())
        .filter(Boolean);
      const sonuc = await slaAyarlariKaydet({ ...ayar, tatiller });
      setAyar(sonuc);
      setTatilMetni(sonuc.tatiller.join('\n'));
      toast.success(t('yardim.sla.kaydedildi'));
    } catch (h) {
      hata(h);
    } finally {
      setKaydediliyor(false);
    }
  };

  const hedefDegis = (o: Oncelik, alan: 'ilk_yanit_dk' | 'cozum_dk', saat: string) => {
    if (!ayar) return;
    const dk = Math.round(Number(saat.replace(',', '.')) * 60);
    if (!Number.isFinite(dk) || dk <= 0) return;
    setAyar({ ...ayar, hedefler: { ...ayar.hedefler, [o]: { ...ayar.hedefler[o], [alan]: dk } } });
  };

  const cevapGonder = async (e: FormEvent) => {
    e.preventDefault();
    if (!form.baslik.trim() || !form.metin.trim()) return;
    try {
      if (form.id) await hazirCevapGuncelle(form.id, form.baslik, form.metin);
      else await hazirCevapEkle(form.baslik, form.metin);
      toast.success(t('yardim.hazirCevap.kaydedildi'));
      setForm({ id: null, baslik: '', metin: '' });
      cevaplariYukle();
    } catch (h) {
      hata(h);
    }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-2" data-testid="destek-ayarlari">
      <section className={KART}>
        <h3 className="flex items-center gap-2 font-semibold">
          <Clock className="h-4 w-4 text-cyan-300" aria-hidden="true" /> {t('yardim.sla.ayarBaslik')}
        </h3>
        <p className="mt-1 text-sm text-muted-foreground">{t('yardim.sla.ayarAciklama')}</p>
        {!ayar ? (
          <div className="flex justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="mt-4 space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <label className="text-xs text-muted-foreground">
                {t('yardim.sla.mesaiBas')}
                <Input
                  type="time"
                  value={ayar.mesai.bas}
                  onChange={(e) => setAyar({ ...ayar, mesai: { ...ayar.mesai, bas: e.target.value } })}
                  className="mt-1 bg-white/5"
                />
              </label>
              <label className="text-xs text-muted-foreground">
                {t('yardim.sla.mesaiBit')}
                <Input
                  type="time"
                  value={ayar.mesai.bit}
                  onChange={(e) => setAyar({ ...ayar, mesai: { ...ayar.mesai, bit: e.target.value } })}
                  className="mt-1 bg-white/5"
                />
              </label>
            </div>
            <fieldset>
              <legend className="mb-2 text-xs text-muted-foreground">{t('yardim.sla.gunler')}</legend>
              <div className="flex flex-wrap gap-2">
                {[0, 1, 2, 3, 4, 5, 6].map((g) => {
                  const secili = ayar.mesai.gunler.includes(g);
                  return (
                    <button
                      key={g}
                      type="button"
                      aria-pressed={secili}
                      onClick={() =>
                        setAyar({
                          ...ayar,
                          mesai: {
                            ...ayar.mesai,
                            gunler: secili ? ayar.mesai.gunler.filter((x) => x !== g) : [...ayar.mesai.gunler, g].sort(),
                          },
                        })
                      }
                      className={`rounded-full border px-3 py-1 text-xs ${
                        secili ? 'border-cyan-400/50 bg-cyan-500/15 text-white' : 'border-white/10 text-muted-foreground'
                      }`}
                    >
                      {t(`yardim.gun.${g}`)}
                    </button>
                  );
                })}
              </div>
            </fieldset>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[320px] text-sm">
                <thead>
                  <tr className="text-left text-xs text-muted-foreground">
                    <th className="py-1 pr-2 font-normal">{t('yardim.sla.oncelik')}</th>
                    <th className="py-1 pr-2 font-normal">{t('yardim.sla.ilkYanitSaat')}</th>
                    <th className="py-1 font-normal">{t('yardim.sla.cozumSaat')}</th>
                  </tr>
                </thead>
                <tbody>
                  {ONCELIKLER.map((o) => (
                    <tr key={o}>
                      <td className="py-1 pr-2">{t(`yardim.oncelik.${o}`)}</td>
                      {(['ilk_yanit_dk', 'cozum_dk'] as const).map((alan) => (
                        <td key={alan} className="py-1 pr-2">
                          <Input
                            defaultValue={String(ayar.hedefler[o][alan] / 60)}
                            onBlur={(e) => hedefDegis(o, alan, e.target.value)}
                            inputMode="decimal"
                            className="h-8 w-24 bg-white/5"
                            aria-label={`${t(`yardim.oncelik.${o}`)} — ${t(alan === 'ilk_yanit_dk' ? 'yardim.sla.ilkYanitSaat' : 'yardim.sla.cozumSaat')}`}
                          />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <label className="block text-xs text-muted-foreground">
              <span className="flex items-center gap-1">
                <CalendarOff className="h-3.5 w-3.5" aria-hidden="true" /> {t('yardim.sla.tatiller')}
              </span>
              <Textarea value={tatilMetni} onChange={(e) => setTatilMetni(e.target.value)} rows={5} className="mt-1 bg-white/5 font-mono text-xs" />
              <span className="mt-1 block">{t('yardim.sla.tatilIpucu')}</span>
            </label>
            <Button onClick={() => void kaydet()} disabled={kaydediliyor} className="gap-2">
              {kaydediliyor ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              {t('yardim.kaydet')}
            </Button>
          </div>
        )}
      </section>

      <section className={KART}>
        <h3 className="flex items-center gap-2 font-semibold">
          <MessageSquareText className="h-4 w-4 text-purple-300" aria-hidden="true" /> {t('yardim.hazirCevap.baslik')}
        </h3>
        <p className="mt-1 text-sm text-muted-foreground">{t('yardim.hazirCevap.aciklama')}</p>
        <form onSubmit={cevapGonder} className="mt-4 space-y-3">
          <Input
            value={form.baslik}
            onChange={(e) => setForm({ ...form, baslik: e.target.value })}
            placeholder={t('yardim.hazirCevap.baslikYer')}
            className="bg-white/5"
            data-testid="hazir-cevap-baslik"
          />
          <Textarea
            value={form.metin}
            onChange={(e) => setForm({ ...form, metin: e.target.value })}
            placeholder={t('yardim.hazirCevap.metinYer')}
            rows={4}
            className="bg-white/5"
            data-testid="hazir-cevap-metin"
          />
          <div className="flex flex-wrap gap-2">
            {['{musteri_adi}', '{talep_no}', '{konu}'].map((d) => (
              <button
                key={d}
                type="button"
                className="rounded-full border border-white/10 px-2 py-0.5 font-mono text-[11px] text-muted-foreground hover:border-white/30"
                onClick={() => setForm({ ...form, metin: `${form.metin}${d}` })}
              >
                {d}
              </button>
            ))}
          </div>
          <div className="flex gap-2">
            <Button type="submit" disabled={!form.baslik.trim() || !form.metin.trim()} data-testid="hazir-cevap-kaydet">
              {form.id ? t('yardim.guncelle') : t('yardim.ekle')}
            </Button>
            {form.id && (
              <Button type="button" variant="ghost" onClick={() => setForm({ id: null, baslik: '', metin: '' })}>
                {t('yardim.vazgec')}
              </Button>
            )}
          </div>
        </form>
        {cevaplar.length === 0 ? (
          <p className="mt-5 text-sm text-muted-foreground">{t('yardim.hazirCevap.bos')}</p>
        ) : (
          <ul className="mt-5 divide-y divide-white/5 rounded-xl border border-white/10">
            {cevaplar.map((h) => (
              <li key={h.id} className="flex items-start gap-2 px-3 py-2 text-sm">
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{h.baslik}</p>
                  <p className="line-clamp-2 whitespace-pre-wrap text-xs text-muted-foreground">{h.metin}</p>
                </div>
                <Button size="sm" variant="ghost" onClick={() => setForm({ id: h.id, baslik: h.baslik, metin: h.metin })} aria-label={t('yardim.duzenle')}>
                  <Pencil className="h-4 w-4" />
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-destructive hover:text-destructive"
                  onClick={() => {
                    if (!window.confirm(t('yardim.hazirCevap.silOnay'))) return;
                    void hazirCevapSil(h.id).then(cevaplariYukle).catch(hata);
                  }}
                  aria-label={t('yardim.sil')}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <Suspense fallback={null}>
        <EpostaTalepKarti />
      </Suspense>
    </div>
  );
}
