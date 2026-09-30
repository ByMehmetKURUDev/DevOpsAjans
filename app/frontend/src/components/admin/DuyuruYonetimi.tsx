import { useCallback, useEffect, useState } from 'react';
import { Lightbulb, Loader2, Megaphone, RefreshCw, ThumbsUp, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  DUYURU_HEDEFLERI,
  DUYURU_ONEMLERI,
  ONERI_DURUMLARI,
  ProjeHatasi,
  duyuruEkle,
  duyuruGuncelle,
  duyuruListesi,
  duyuruSil,
  oneriGuncelle,
  oneriYonetimi,
  tarihGoster,
  toplulukAyari,
  type DuyuruHedefi,
  type DuyuruOnemi,
  type OneriDurumu,
  type YoneticiDuyurusu,
  type YoneticiOnerisi,
} from '@/lib/projeYonetimi';

const SECIM =
  'h-9 w-full rounded-md border border-white/10 bg-white/5 px-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-purple-500/40';

const ONEM_RENGI: Record<DuyuruOnemi, string> = {
  bilgi: 'bg-sky-500/15 text-sky-200',
  onemli: 'bg-amber-500/15 text-amber-200',
  kritik: 'bg-rose-500/20 text-rose-200',
};

/**
 * Yönetici › Duyurular (Faz 2B): duyuru yayınlama (tüm müşteriler / seçili
 * müşteriler / ekip; önem, bitiş) + okunma sayıları; ikinci alt görünüm
 * öneri kutusu (durum, not, Yol haritası "Topluluktan" ayarı).
 */
export default function DuyuruYonetimi() {
  const { t } = useTranslation();
  const [alt, setAlt] = useState<'duyurular' | 'oneriler'>('duyurular');
  return (
    <section className="space-y-5" data-testid="duyuru-yonetim">
      <div className="flex flex-wrap gap-2">
        {(
          [
            ['duyurular', t('duyurular.sekme.duyurular'), Megaphone],
            ['oneriler', t('duyurular.sekme.oneriler'), Lightbulb],
          ] as const
        ).map(([k, etiket, Ikon]) => (
          <button
            key={k}
            type="button"
            onClick={() => setAlt(k)}
            aria-pressed={alt === k}
            className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs transition-colors ${
              alt === k ? 'bg-purple-500/20 text-purple-200 ring-1 ring-purple-400/40' : 'bg-white/5 text-muted-foreground hover:text-foreground'
            }`}
            data-testid={`duyuru-alt-${k}`}
          >
            <Ikon className="h-3.5 w-3.5" /> {etiket}
          </button>
        ))}
      </div>
      {alt === 'duyurular' ? <Duyurular /> : <OneriYonetimi />}
    </section>
  );
}

function Duyurular() {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [liste, setListe] = useState<YoneticiDuyurusu[]>([]);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [mesgul, setMesgul] = useState(false);
  const bos = { baslik: '', metin: '', onem: 'bilgi' as DuyuruOnemi, hedef: 'tum' as DuyuruHedefi, alicilar: '', bitis: '', bildirim: false };
  const [form, setForm] = useState(bos);

  const hata = (h: unknown) =>
    toast.error(h instanceof ProjeHatasi ? t(`duyurular.hata.${h.kod}`, { defaultValue: t('duyurular.hata.genel') }) : t('duyurular.hata.genel'));

  const yukle = useCallback(async () => {
    try {
      setListe(await duyuruListesi());
    } catch {
      toast.error(t('duyurular.hata.yuklenemedi'));
    } finally {
      setYukleniyor(false);
    }
  }, [t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const yayinla = async () => {
    if (!form.baslik.trim()) {
      toast.error(t('duyurular.hata.baslik_gerekli'));
      return;
    }
    setMesgul(true);
    try {
      const d = await duyuruEkle({
        baslik: form.baslik.trim(),
        metin: form.metin.trim() || undefined,
        onem: form.onem,
        hedef: form.hedef,
        hedef_epostalar: form.hedef === 'secili' ? form.alicilar.split(/[\s,;]+/).map((x) => x.trim()).filter(Boolean) : [],
        bitis: form.bitis || undefined,
        yayinda: true,
        bildirim_gonder: form.bildirim,
      });
      setListe((l) => [d, ...l]);
      setForm(bos);
      toast.success(t('duyurular.yonetici.yayinlandi'));
    } catch (h) {
      hata(h);
    } finally {
      setMesgul(false);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h2 className="flex items-center gap-2 text-xl font-semibold">
          <Megaphone className="h-5 w-5 text-purple-300" /> {t('duyurular.yonetici.baslik')}
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">{t('duyurular.yonetici.aciklama')}</p>
      </div>

      <form
        className="cam-kart grid gap-3 rounded-2xl border border-white/10 bg-white/[0.03] p-4 md:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          void yayinla();
        }}
      >
        <label className="grid gap-1 text-xs md:col-span-2">
          {t('duyurular.yonetici.baslikAlan')}
          <Input value={form.baslik} onChange={(e) => setForm({ ...form, baslik: e.target.value })} maxLength={200} data-testid="duyuru-baslik" />
        </label>
        <label className="grid gap-1 text-xs md:col-span-2">
          {t('duyurular.yonetici.metin')}
          <textarea
            value={form.metin}
            onChange={(e) => setForm({ ...form, metin: e.target.value })}
            rows={3}
            maxLength={4000}
            className="rounded-md border border-white/10 bg-white/5 p-2 text-sm"
            data-testid="duyuru-metin"
          />
        </label>
        <label className="grid gap-1 text-xs">
          {t('duyurular.yonetici.onem')}
          <select value={form.onem} onChange={(e) => setForm({ ...form, onem: e.target.value as DuyuruOnemi })} className={SECIM} data-testid="duyuru-onem">
            {DUYURU_ONEMLERI.map((o) => (
              <option key={o} value={o}>
                {t(`duyurular.onem.${o}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="grid gap-1 text-xs">
          {t('duyurular.yonetici.hedef')}
          <select value={form.hedef} onChange={(e) => setForm({ ...form, hedef: e.target.value as DuyuruHedefi })} className={SECIM} data-testid="duyuru-hedef">
            {DUYURU_HEDEFLERI.map((h) => (
              <option key={h} value={h}>
                {t(`duyurular.hedef.${h}`)}
              </option>
            ))}
          </select>
        </label>
        {form.hedef === 'secili' && (
          <label className="grid gap-1 text-xs md:col-span-2">
            {t('duyurular.yonetici.alicilar')}
            <textarea
              value={form.alicilar}
              onChange={(e) => setForm({ ...form, alicilar: e.target.value })}
              rows={2}
              className="rounded-md border border-white/10 bg-white/5 p-2 text-sm"
              placeholder="ornek@firma.com, diger@firma.com"
              data-testid="duyuru-alicilar"
            />
            <span className="text-[10px] text-muted-foreground">{t('duyurular.yonetici.aliciIpucu')}</span>
          </label>
        )}
        <label className="grid gap-1 text-xs">
          {t('duyurular.yonetici.bitis')}
          <Input type="date" value={form.bitis} onChange={(e) => setForm({ ...form, bitis: e.target.value })} />
          <span className="text-[10px] text-muted-foreground">{t('duyurular.yonetici.bitisIpucu')}</span>
        </label>
        <label className="inline-flex items-center gap-2 self-center text-xs">
          <input type="checkbox" checked={form.bildirim} onChange={(e) => setForm({ ...form, bildirim: e.target.checked })} className="h-4 w-4 accent-purple-500" />
          {t('duyurular.yonetici.bildirim')}
        </label>
        <div className="md:col-span-2">
          <Button type="submit" disabled={mesgul} data-testid="duyuru-yayinla">
            {mesgul ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : null}
            {t('duyurular.yonetici.yayinla')}
          </Button>
        </div>
      </form>

      {yukleniyor ? (
        <div className="flex justify-center py-8 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
        </div>
      ) : liste.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('duyurular.yonetici.bos')}</p>
      ) : (
        <ul className="grid gap-3">
          {liste.map((d) => (
            <li key={d.id} className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-4" data-testid={`duyuru-satir-${d.id}`}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="mb-1 flex flex-wrap items-center gap-1.5 text-[11px]">
                    <span className={`rounded-full px-2 py-0.5 ${ONEM_RENGI[d.onem]}`}>{t(`duyurular.onem.${d.onem}`)}</span>
                    <span className="rounded-full bg-white/10 px-2 py-0.5">{t(`duyurular.hedef.${d.hedef}`)}</span>
                    <span className={`rounded-full px-2 py-0.5 ${d.etkin ? 'bg-emerald-500/15 text-emerald-200' : 'bg-white/5 text-muted-foreground'}`}>
                      {d.etkin ? t('duyurular.yonetici.etkin') : t('duyurular.yonetici.pasif')}
                    </span>
                    <span className="text-muted-foreground">{tarihGoster(d.created_at, dil)}</span>
                    {d.bitis_at && (
                      <span className="text-muted-foreground">→ {tarihGoster(d.bitis_at, dil)}</span>
                    )}
                  </div>
                  <p className="break-words font-medium">{d.baslik}</p>
                  {d.metin && <p className="mt-1 whitespace-pre-line break-words text-sm text-muted-foreground">{d.metin}</p>}
                  {d.hedef === 'secili' && <p className="mt-1 break-all text-[11px] text-muted-foreground">{d.hedef_epostalar.join(', ')}</p>}
                  <p className="mt-2 text-[11px] text-muted-foreground">
                    {t('duyurular.yonetici.okunma', { sayi: d.okunma_sayisi })} · {t('duyurular.yonetici.kapatma', { sayi: d.kapatma_sayisi })}
                  </p>
                </div>
                <div className="flex gap-1">
                  <Button
                    size="sm"
                    variant="outline"
                    className="!bg-transparent text-xs"
                    onClick={async () => {
                      try {
                        const y = await duyuruGuncelle(d.id, { yayinda: !d.yayinda });
                        setListe((l) => l.map((x) => (x.id === d.id ? y : x)));
                      } catch (h) {
                        hata(h);
                      }
                    }}
                  >
                    {d.yayinda ? t('duyurular.yonetici.yayindanKaldir') : t('duyurular.yonetici.yayinaAl')}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-destructive"
                    aria-label={t('duyurular.yonetici.sil')}
                    onClick={async () => {
                      if (!window.confirm(t('duyurular.yonetici.silOnay'))) return;
                      try {
                        await duyuruSil(d.id);
                        setListe((l) => l.filter((x) => x.id !== d.id));
                      } catch (h) {
                        hata(h);
                      }
                    }}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function OneriYonetimi() {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [liste, setListe] = useState<YoneticiOnerisi[]>([]);
  const [topluluk, setTopluluk] = useState(false);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [notlar, setNotlar] = useState<Record<number, string>>({});

  const hata = (h: unknown) =>
    toast.error(h instanceof ProjeHatasi ? t(`duyurular.hata.${h.kod}`, { defaultValue: t('duyurular.hata.genel') }) : t('duyurular.hata.genel'));

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    try {
      const y = await oneriYonetimi();
      setListe(y.oneriler);
      setTopluluk(y.topluluk_yol_haritasi);
    } catch {
      toast.error(t('duyurular.hata.yuklenemedi'));
    } finally {
      setYukleniyor(false);
    }
  }, [t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const guncelle = async (o: YoneticiOnerisi, girdi: Partial<{ durum: OneriDurumu; yonetici_notu: string }>) => {
    try {
      const y = await oneriGuncelle(o.id, girdi);
      setListe((l) => l.map((x) => (x.id === o.id ? y : x)));
      if (girdi.yonetici_notu !== undefined) toast.success(t('duyurular.oneriYonetimi.kaydedildi'));
    } catch (h) {
      hata(h);
    }
  };

  return (
    <div className="space-y-4" data-testid="oneri-yonetim">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="flex items-center gap-2 text-xl font-semibold">
            <Lightbulb className="h-5 w-5 text-amber-300" /> {t('duyurular.oneriYonetimi.baslik')}
            <span className="rounded-full bg-purple-500/20 px-2 py-0.5 text-[10px] font-normal text-purple-200">{t('duyurular.oneri.beta')}</span>
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">{t('duyurular.oneriYonetimi.aciklama')}</p>
        </div>
        <Button size="sm" variant="ghost" onClick={() => void yukle()} aria-label={t('duyurular.yenile')}>
          <RefreshCw className="h-4 w-4" />
        </Button>
      </div>
      <label className="cam-kart flex items-start gap-2 rounded-2xl border border-white/10 bg-white/[0.03] p-3 text-sm">
        <input
          type="checkbox"
          checked={topluluk}
          onChange={async (e) => {
            const deger = e.target.checked;
            try {
              await toplulukAyari(deger);
              setTopluluk(deger);
            } catch (h) {
              hata(h);
            }
          }}
          className="mt-0.5 h-4 w-4 accent-purple-500"
          data-testid="topluluk-ayari"
        />
        {t('duyurular.oneriYonetimi.topluluk')}
      </label>
      {yukleniyor ? (
        <div className="flex justify-center py-8 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
        </div>
      ) : liste.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('duyurular.oneriYonetimi.bos')}</p>
      ) : (
        <ul className="grid gap-3">
          {liste.map((o) => (
            <li key={o.id} className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-4" data-testid={`oneri-yonetim-${o.id}`}>
              <div className="flex flex-wrap items-start gap-3">
                <div className="flex shrink-0 flex-col items-center rounded-xl bg-white/5 px-3 py-2 text-sm">
                  <ThumbsUp className="h-4 w-4 text-purple-300" aria-hidden="true" />
                  <span className="font-semibold">{o.oy_sayisi}</span>
                </div>
                <div className="min-w-0 flex-1">
                  <p className="break-words font-medium">{o.baslik}</p>
                  {o.aciklama && <p className="mt-1 whitespace-pre-line break-words text-sm text-muted-foreground">{o.aciklama}</p>}
                  <p className="mt-1 break-all text-[11px] text-muted-foreground">
                    {t('duyurular.oneriYonetimi.sahip')}: {o.sahip_eposta} · {tarihGoster(o.created_at, dil)}
                  </p>
                  <form
                    className="mt-2 flex flex-wrap gap-2"
                    onSubmit={(e) => {
                      e.preventDefault();
                      void guncelle(o, { yonetici_notu: notlar[o.id] ?? o.yonetici_notu ?? '' });
                    }}
                  >
                    <Input
                      value={notlar[o.id] ?? o.yonetici_notu ?? ''}
                      onChange={(e) => setNotlar((n) => ({ ...n, [o.id]: e.target.value }))}
                      placeholder={t('duyurular.oneriYonetimi.not')}
                      aria-label={t('duyurular.oneriYonetimi.not')}
                      className="h-8 min-w-0 flex-1"
                      maxLength={1000}
                    />
                    <Button type="submit" size="sm" variant="outline" className="h-8 !bg-transparent">
                      {t('duyurular.oneriYonetimi.notKaydet')}
                    </Button>
                  </form>
                </div>
                <select
                  value={o.durum}
                  onChange={(e) => void guncelle(o, { durum: e.target.value as OneriDurumu })}
                  className={SECIM + ' sm:w-40'}
                  aria-label={t('duyurular.oneriYonetimi.durum')}
                  data-testid={`oneri-durum-${o.id}`}
                >
                  {ONERI_DURUMLARI.map((d) => (
                    <option key={d} value={d}>
                      {t(`duyurular.oneriDurum.${d}`)}
                    </option>
                  ))}
                </select>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
