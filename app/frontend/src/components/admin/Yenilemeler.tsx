import { useCallback, useEffect, useState } from 'react';
import { CalendarClock, Check, Copy, ExternalLink, Loader2, Receipt, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  BakimHatasi,
  bitisRengi,
  tarihBicimle,
  yenilemeFaturasiKes,
  yenilemeleriGetir,
  type YenilemeKalemi,
} from '@/lib/siteBakim';

const ARALIKLAR = [30, 60, 90, 180, 365];
const PARA_BIRIMLERI = ['TRY', 'USD', 'EUR'];

function anahtar(k: YenilemeKalemi) {
  return `${k.tur}-${k.ref_id}`;
}

/**
 * Yönetici › Siteler › Yenilemeler (Faz 2A).
 *
 * Alan adı, hosting, elle yenilenen SSL ve aktif abonelikler bitiş
 * tarihine göre tek listede. "Yenileme faturası kes" mevcut fatura +
 * `/ode/<jeton>` akışıyla fatura ve ödeme bağlantısı üretiyor; tutar
 * formdan, müşteriye e-posta isteğe bağlı.
 */
export default function Yenilemeler() {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [gun, setGun] = useState(90);
  const [kalemler, setKalemler] = useState<YenilemeKalemi[]>([]);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [acik, setAcik] = useState<string | null>(null);
  const [form, setForm] = useState({ tutar: '', para_birimi: 'TRY', aciklama: '', eposta_gonder: true });
  const [gonderiliyor, setGonderiliyor] = useState(false);
  const [kopyalanan, setKopyalanan] = useState<string | null>(null);

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    try {
      setKalemler((await yenilemeleriGetir(gun)).kalemler);
    } catch {
      toast.error(t('siteBakim.hata.yuklenemedi'));
    } finally {
      setYukleniyor(false);
    }
  }, [gun, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const formAc = (k: YenilemeKalemi) => {
    if (acik === anahtar(k)) {
      setAcik(null);
      return;
    }
    setAcik(anahtar(k));
    setForm({
      tutar: k.tutar ? String(k.tutar) : '',
      para_birimi: k.para_birimi && PARA_BIRIMLERI.includes(k.para_birimi) ? k.para_birimi : 'TRY',
      aciklama: '',
      eposta_gonder: true,
    });
  };

  const kes = async (k: YenilemeKalemi) => {
    const tutar = Number(String(form.tutar).replace(',', '.'));
    if (!Number.isFinite(tutar) || tutar <= 0) {
      toast.error(t('siteBakim.hata.tutar_gecersiz'));
      return;
    }
    setGonderiliyor(true);
    try {
      const f = await yenilemeFaturasiKes({
        tur: k.tur,
        ref_id: k.ref_id,
        tutar,
        para_birimi: form.para_birimi,
        aciklama: form.aciklama.trim() || undefined,
        eposta_gonder: form.eposta_gonder,
      });
      setKalemler((o) => o.map((x) => (anahtar(x) === anahtar(k) ? { ...x, fatura: f } : x)));
      setAcik(null);
      toast.success(t(f.mevcut ? 'siteBakim.yenileme.mevcut' : 'siteBakim.yenileme.kesildi'));
    } catch (h) {
      const kod = h instanceof BakimHatasi ? h.kod : 'genel';
      toast.error(t(`siteBakim.hata.${kod}`, { defaultValue: t('siteBakim.hata.genel') }));
    } finally {
      setGonderiliyor(false);
    }
  };

  const kopyala = async (adres: string) => {
    try {
      await navigator.clipboard.writeText(`${window.location.origin}${adres}`);
      setKopyalanan(adres);
      setTimeout(() => setKopyalanan(null), 2000);
    } catch {
      /* bağlantı zaten görünür */
    }
  };

  const kalanMetni = (g: number) =>
    g < 0 ? t('siteBakim.rozet.gecti', { sayi: Math.abs(g) }) : g === 0 ? t('siteBakim.rozet.bugun') : t('siteBakim.rozet.kalan', { sayi: g });

  return (
    <div className="space-y-4" data-testid="yenilemeler">
      <div className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <h3 className="flex items-center gap-2 text-sm font-semibold">
              <CalendarClock className="h-4 w-4" />
              {t('siteBakim.yenileme.baslik')}
            </h3>
            <p className="mt-1 text-xs text-muted-foreground">{t('siteBakim.yenileme.aciklama')}</p>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={gun}
              onChange={(e) => setGun(Number(e.target.value))}
              className="h-9 rounded-md border border-white/10 bg-background px-2 text-sm"
              aria-label={t('siteBakim.yenileme.aralikEtiket')}
            >
              {ARALIKLAR.map((a) => (
                <option key={a} value={a}>
                  {t('siteBakim.yenileme.aralik', { sayi: a })}
                </option>
              ))}
            </select>
            <Button size="sm" variant="ghost" onClick={() => void yukle()} aria-label={t('siteBakim.yenileme.yenile')}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>

      {yukleniyor ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
        </div>
      ) : kalemler.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('siteBakim.yenileme.bos')}</p>
      ) : (
        <ul className="space-y-2">
          {kalemler.map((k) => (
            <li
              key={anahtar(k)}
              className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-4"
              data-testid={`yenileme-${anahtar(k)}`}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full border border-white/15 px-2 py-0.5 text-[11px] uppercase tracking-wide">
                  {t(`siteBakim.yenileme.tur.${k.tur}`)}
                </span>
                <span className="min-w-0 flex-1 truncate font-medium">{k.baslik}</span>
                <span className={`rounded-full border px-2 py-0.5 text-[11px] ${bitisRengi(k.kalan_gun)}`}>
                  {tarihBicimle(k.bitis, dil)} · {kalanMetni(k.kalan_gun)}
                </span>
              </div>
              <p className="mt-1 truncate text-xs text-muted-foreground">
                {k.client_email}
                {k.saglayici ? ` · ${k.saglayici}` : ''}
                {k.tur !== 'abonelik' && !k.modul_acik ? ` · ${t('siteBakim.yenileme.modulKapali')}` : ''}
              </p>

              <div className="mt-3 flex flex-wrap items-center gap-2">
                {k.fatura ? (
                  <>
                    <span className="inline-flex items-center gap-1 text-xs">
                      <Receipt className="h-3.5 w-3.5" />
                      {t('siteBakim.yenileme.fatura', { no: k.fatura.invoice_no })} ·{' '}
                      {t(`siteBakim.yenileme.durum.${k.fatura.status === 'paid' ? 'paid' : 'pending'}`)}
                    </span>
                    {k.fatura.odeme_adresi && (
                      <>
                        <a
                          href={k.fatura.odeme_adresi}
                          target="_blank"
                          rel="noreferrer noopener"
                          className="inline-flex items-center gap-1 break-all text-xs text-cyan-300 hover:underline"
                          data-testid="yenileme-odeme-baglantisi"
                        >
                          {k.fatura.odeme_adresi}
                          <ExternalLink className="h-3 w-3 shrink-0" />
                        </a>
                        <Button size="sm" variant="ghost" className="h-7" onClick={() => void kopyala(k.fatura!.odeme_adresi!)}>
                          {kopyalanan === k.fatura.odeme_adresi ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                          <span className="sr-only">{t('siteBakim.durumSayfasi.kopyala')}</span>
                        </Button>
                      </>
                    )}
                  </>
                ) : null}
                <Button
                  size="sm"
                  variant={acik === anahtar(k) ? 'secondary' : 'default'}
                  className="ms-auto"
                  onClick={() => formAc(k)}
                  data-testid={`yenileme-kes-${anahtar(k)}`}
                >
                  <Receipt className="mr-2 h-4 w-4" />
                  {acik === anahtar(k) ? t('siteBakim.yenileme.vazgec') : t('siteBakim.yenileme.faturaKes')}
                </Button>
              </div>

              {acik === anahtar(k) && (
                <div className="mt-3 grid gap-2 rounded-xl border border-white/10 bg-black/20 p-3 sm:grid-cols-[140px_110px_1fr]">
                  <Input
                    type="number"
                    min={0}
                    step="0.01"
                    value={form.tutar}
                    placeholder={t('siteBakim.yenileme.tutar')}
                    aria-label={t('siteBakim.yenileme.tutar')}
                    onChange={(e) => setForm({ ...form, tutar: e.target.value })}
                    className="h-9"
                    data-testid="yenileme-tutar"
                  />
                  <select
                    value={form.para_birimi}
                    onChange={(e) => setForm({ ...form, para_birimi: e.target.value })}
                    className="h-9 rounded-md border border-white/10 bg-background px-2 text-sm"
                    aria-label={t('siteBakim.yenileme.paraBirimi')}
                  >
                    {PARA_BIRIMLERI.map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </select>
                  <Input
                    value={form.aciklama}
                    placeholder={t('siteBakim.yenileme.aciklamaAlan')}
                    aria-label={t('siteBakim.yenileme.aciklamaAlan')}
                    onChange={(e) => setForm({ ...form, aciklama: e.target.value })}
                    className="h-9"
                  />
                  <label className="flex items-center gap-2 text-xs text-muted-foreground sm:col-span-2">
                    <input
                      type="checkbox"
                      checked={form.eposta_gonder}
                      onChange={(e) => setForm({ ...form, eposta_gonder: e.target.checked })}
                    />
                    {t('siteBakim.yenileme.epostaGonder')}
                  </label>
                  <Button size="sm" onClick={() => void kes(k)} disabled={gonderiliyor} data-testid="yenileme-gonder">
                    {gonderiliyor && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    {t('siteBakim.yenileme.kes')}
                  </Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
