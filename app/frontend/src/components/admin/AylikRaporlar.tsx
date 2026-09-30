import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import { BarChart3, ExternalLink, Loader2, RefreshCw, Send, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { modulMusterileriGetir, type ModulMusterisi } from '@/lib/moduller';
import {
  RaporHatasi,
  donemAdi,
  oncekiDonem,
  raporGetir,
  raporListesi,
  raporNotu,
  raporOlustur,
  raporSil,
  raporYayinla,
  raporYenile,
  type AylikRapor,
  type RaporSatiri,
} from '@/lib/aylikRapor';

/**
 * Yönetici › Raporlar ve abonelik › Aylık müşteri raporları (Faz 2C).
 *
 * "Şimdi oluştur" (müşteri + dönem) ya da ayın 1'inde zamanlı görevin açtığı
 * taslak → önizle (yazdırmaya uygun sayfa, yeni sekme) → not ekle →
 * yayınla (müşteriye e-posta bir kez). Yayınlanan rapor değişmiyor.
 */

const KART = 'cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6';

export default function AylikRaporlar() {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [liste, setListe] = useState<RaporSatiri[]>([]);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [musteriler, setMusteriler] = useState<ModulMusterisi[]>([]);
  const [eposta, setEposta] = useState('');
  const [donem, setDonem] = useState(oncekiDonem());
  const [secili, setSecili] = useState<AylikRapor | null>(null);
  const [not, setNot] = useState('');
  const [calisiyor, setCalisiyor] = useState<string | null>(null);

  const hata = useCallback(
    (h: unknown) => toast.error(t(`aylikRapor.hata.${h instanceof RaporHatasi ? h.kod : 'genel'}`, { defaultValue: t('aylikRapor.hata.genel') })),
    [t]
  );

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    try {
      setListe(await raporListesi());
    } catch (h) {
      hata(h);
    } finally {
      setYukleniyor(false);
    }
  }, [hata]);

  useEffect(() => {
    void yukle();
    modulMusterileriGetir()
      .then(setMusteriler)
      .catch(() => setMusteriler([]));
  }, [yukle]);

  const sec = async (id: number) => {
    try {
      const r = await raporGetir(id);
      setSecili(r);
      setNot(r.yonetici_notu ?? '');
    } catch (h) {
      hata(h);
    }
  };

  const olustur = async (e: FormEvent) => {
    e.preventDefault();
    if (!eposta.trim() || !/^\d{4}-\d{2}$/.test(donem)) return;
    setCalisiyor('olustur');
    try {
      const r = await raporOlustur(eposta.trim().toLowerCase(), donem);
      setSecili(r);
      setNot(r.yonetici_notu ?? '');
      toast.success(t('aylikRapor.yonetim.olusturuldu'));
      await yukle();
    } catch (h) {
      hata(h);
    } finally {
      setCalisiyor(null);
    }
  };

  const islem = async (ad: string, fn: () => Promise<AylikRapor | void>, basari: string) => {
    setCalisiyor(ad);
    try {
      const r = await fn();
      if (r) {
        setSecili(r);
        setNot(r.yonetici_notu ?? '');
      }
      toast.success(basari);
      await yukle();
    } catch (h) {
      hata(h);
    } finally {
      setCalisiyor(null);
    }
  };

  const onizlemeYolu = secili?.jeton ? `/rapor-aylik/${secili.jeton}` : null;
  const taslakSayisi = useMemo(() => liste.filter((r) => r.durum === 'taslak').length, [liste]);

  return (
    <div className={`${KART} mt-8`} data-testid="aylik-raporlar">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-xl font-semibold">
            <BarChart3 className="h-5 w-5 text-cyan-300" aria-hidden="true" /> {t('aylikRapor.yonetim.baslik')}
          </h2>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{t('aylikRapor.yonetim.aciklama')}</p>
        </div>
        <Button size="sm" variant="ghost" className="gap-2" onClick={() => void yukle()}>
          <RefreshCw className={`h-4 w-4 ${yukleniyor ? 'animate-spin' : ''}`} aria-hidden="true" />
          {t('aylikRapor.yonetim.yenileListe')}
        </Button>
      </div>

      <form onSubmit={olustur} className="mt-5 grid gap-3 md:grid-cols-[1fr_160px_auto]">
        <Input
          value={eposta}
          onChange={(e) => setEposta(e.target.value)}
          list="aylik-rapor-musteriler"
          placeholder={t('aylikRapor.yonetim.musteri')}
          aria-label={t('aylikRapor.yonetim.musteri')}
          className="bg-white/5"
          data-testid="aylik-rapor-eposta"
        />
        <datalist id="aylik-rapor-musteriler">
          {musteriler.map((m) => (
            <option key={m.eposta} value={m.eposta}>
              {m.ad ?? ''}
            </option>
          ))}
        </datalist>
        <Input
          type="month"
          value={donem}
          onChange={(e) => setDonem(e.target.value)}
          aria-label={t('aylikRapor.yonetim.donem')}
          className="bg-white/5"
          data-testid="aylik-rapor-donem"
        />
        <Button type="submit" disabled={calisiyor !== null || !eposta.trim()} className="gap-2" data-testid="aylik-rapor-olustur">
          {calisiyor === 'olustur' ? <Loader2 className="h-4 w-4 animate-spin" /> : <BarChart3 className="h-4 w-4" />}
          {t('aylikRapor.yonetim.simdiOlustur')}
        </Button>
      </form>

      {secili && (
        <div className="mt-6 rounded-xl border border-white/10 bg-white/[0.02] p-4" data-testid="aylik-rapor-secili">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="font-medium">
              {secili.client_email} · <span className="capitalize">{donemAdi(secili.donem, dil)}</span>
            </p>
            <span
              className={`rounded-full px-2.5 py-0.5 text-xs ${
                secili.durum === 'yayinlandi' ? 'bg-emerald-500/15 text-emerald-200' : 'bg-amber-500/15 text-amber-200'
              }`}
              data-testid="aylik-rapor-durum"
            >
              {t(`aylikRapor.durum.${secili.durum}`)}
            </span>
          </div>
          {secili.ozet && <p className="mt-2 text-sm text-muted-foreground">{secili.ozet}</p>}
          <label className="mt-3 block text-xs text-muted-foreground">
            {t('aylikRapor.yonetim.not')}
            <Textarea
              value={not}
              onChange={(e) => setNot(e.target.value)}
              rows={3}
              disabled={secili.durum === 'yayinlandi'}
              placeholder={t('aylikRapor.yonetim.notYer')}
              className="mt-1 bg-white/5"
              data-testid="aylik-rapor-not"
            />
          </label>
          <div className="mt-3 flex flex-wrap gap-2">
            {onizlemeYolu && (
              <a
                href={onizlemeYolu}
                target="_blank"
                rel="noopener"
                className="inline-flex h-9 items-center gap-2 rounded-md border border-white/15 px-3 text-sm hover:border-white/30"
                data-testid="aylik-rapor-onizle"
              >
                <ExternalLink className="h-4 w-4" aria-hidden="true" /> {t('aylikRapor.yonetim.onizle')}
              </a>
            )}
            {secili.durum === 'taslak' && (
              <>
                <Button
                  variant="outline"
                  className="!bg-transparent"
                  disabled={calisiyor !== null}
                  onClick={() => void islem('not', () => raporNotu(secili.id, not), t('aylikRapor.yonetim.notKaydedildi'))}
                  data-testid="aylik-rapor-not-kaydet"
                >
                  {t('aylikRapor.yonetim.notKaydet')}
                </Button>
                <Button
                  variant="outline"
                  className="gap-2 !bg-transparent"
                  disabled={calisiyor !== null}
                  onClick={() => void islem('yenile', () => raporYenile(secili.id), t('aylikRapor.yonetim.veriYenilendi'))}
                >
                  <RefreshCw className="h-4 w-4" /> {t('aylikRapor.yonetim.veriYenile')}
                </Button>
                <Button
                  className="gap-2"
                  disabled={calisiyor !== null}
                  onClick={() => {
                    if (!window.confirm(t('aylikRapor.yonetim.yayinlaOnay'))) return;
                    void islem(
                      'yayinla',
                      async () => {
                        if ((secili.yonetici_notu ?? '') !== not) await raporNotu(secili.id, not);
                        return raporYayinla(secili.id);
                      },
                      t('aylikRapor.yonetim.yayinlandi')
                    );
                  }}
                  data-testid="aylik-rapor-yayinla"
                >
                  {calisiyor === 'yayinla' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                  {t('aylikRapor.yonetim.yayinla')}
                </Button>
                <Button
                  variant="ghost"
                  className="text-destructive hover:text-destructive"
                  disabled={calisiyor !== null}
                  onClick={() => {
                    if (!window.confirm(t('aylikRapor.yonetim.silOnay'))) return;
                    void islem(
                      'sil',
                      async () => {
                        await raporSil(secili.id);
                        setSecili(null);
                      },
                      t('aylikRapor.yonetim.silindi')
                    );
                  }}
                  aria-label={t('aylikRapor.yonetim.sil')}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </>
            )}
          </div>
        </div>
      )}

      <div className="mt-6">
        <p className="mb-2 text-xs text-muted-foreground">{t('aylikRapor.yonetim.liste', { sayi: liste.length, taslak: taslakSayisi })}</p>
        {yukleniyor ? (
          <div className="flex justify-center py-6">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : liste.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('aylikRapor.yonetim.bos')}</p>
        ) : (
          <ul className="divide-y divide-white/5 rounded-xl border border-white/10">
            {liste.map((r) => (
              <li key={r.id}>
                <button
                  type="button"
                  onClick={() => void sec(r.id)}
                  className={`flex w-full flex-wrap items-center gap-3 px-4 py-2 text-left text-sm hover:bg-white/[0.03] ${
                    secili?.id === r.id ? 'bg-white/[0.04]' : ''
                  }`}
                  data-testid={`aylik-rapor-satir-${r.id}`}
                >
                  <span className="min-w-0 flex-1 break-all">{r.client_email}</span>
                  <span className="capitalize text-muted-foreground">{donemAdi(r.donem, dil)}</span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[11px] ${
                      r.durum === 'yayinlandi' ? 'bg-emerald-500/15 text-emerald-200' : 'bg-amber-500/15 text-amber-200'
                    }`}
                  >
                    {t(`aylikRapor.durum.${r.durum ?? 'taslak'}`)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
