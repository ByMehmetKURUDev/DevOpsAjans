import { useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowDown, ArrowUp, FlaskConical, Loader2, Pencil, Plus, Save, Trash2, Wand2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { hazirCevaplar, type HazirCevap } from '@/lib/destek';
import {
  EYLEM_TURLERI,
  EpostaHatasi,
  KOSUL_ISLECLERI,
  kuralEkle,
  kuralGuncelle,
  kuralSil,
  kurallar as kurallariGetir,
  kurallariDene,
  kurallariSirala,
  type DeneSonucu,
  type Eylem,
  type EylemTuru,
  type Kosul,
  type KosulAlani,
  type Kural,
  type KuralGirdisi,
} from '@/lib/destekEposta';
import { ekibiGetir, type Personel } from '@/lib/ekip';
import { HIZMETLER } from '@/lib/talepler';

/**
 * Yönetici › Destek › Kurallar (Faz 2F).
 *
 * Yeni talep açılınca (panel, web, e-posta) etkin kurallar yukarıdan aşağı
 * denenir; eşleşen kuralın eylemleri uygulanır, "durdur" varsa sonrakiler
 * denenmez. Sıra yukarı/aşağı düğmeleriyle değişir. "Dene" kutusu örnek bir
 * talebin hangi kurallara takılacağını gösterir, hiçbir şey kaydetmez.
 * Metinler `destekKurallari` ek paketinde (öncelik adları `yardim`da).
 */

const KART = 'cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6';
const SECIM = 'h-9 rounded-md border border-white/10 bg-black/40 px-2 text-sm text-white';
const ALANLAR = Object.keys(KOSUL_ISLECLERI) as KosulAlani[];
const ONCELIKLER = ['acil', 'yuksek', 'normal', 'dusuk'];
const KANALLAR = ['panel', 'eposta', 'web'];

const bosForm = (): KuralGirdisi & { id: number | null } => ({
  id: null,
  ad: '',
  aktif: true,
  eslesme: 'hepsi',
  kosullar: [{ alan: 'konu', islec: 'icerir', deger: '' }],
  eylemler: [{ tur: 'oncelik', deger: 'yuksek' }],
});

export default function DestekKurallari() {
  const { t } = useTranslation();
  const [liste, setListe] = useState<Kural[] | null>(null);
  const [ekip, setEkip] = useState<Personel[]>([]);
  const [cevaplar, setCevaplar] = useState<HazirCevap[]>([]);
  const [form, setForm] = useState<(KuralGirdisi & { id: number | null }) | null>(null);
  const [kaydediliyor, setKaydediliyor] = useState(false);
  const [silinecek, setSilinecek] = useState<number | null>(null);
  const [dene, setDene] = useState({ konu: '', metin: '', gonderen: '', kanal: 'eposta' });
  const [deneSonucu, setDeneSonucu] = useState<DeneSonucu | null>(null);
  const [deneniyor, setDeneniyor] = useState(false);

  const hata = useCallback(
    (h: unknown) => {
      const kod = h instanceof EpostaHatasi ? h.kod : 'genel';
      toast.error(t(`destekKurallari.hata.${kod}`, { defaultValue: t('destekKurallari.hata.genel') }));
    },
    [t]
  );

  const yukle = useCallback(() => {
    kurallariGetir().then(setListe).catch((h) => {
      setListe([]);
      hata(h);
    });
  }, [hata]);

  useEffect(() => {
    yukle();
    ekibiGetir().then(setEkip).catch(() => setEkip([]));
    hazirCevaplar().then(setCevaplar).catch(() => setCevaplar([]));
  }, [yukle]);

  const ekipAdi = useMemo(() => Object.fromEntries(ekip.map((k) => [k.email, k.ad])), [ekip]);
  const cevapAdi = useMemo(() => Object.fromEntries(cevaplar.map((c) => [String(c.id), c.baslik])), [cevaplar]);

  const degerMetni = (alan: string, deger: string | number | undefined): string => {
    const d = String(deger ?? '');
    if (alan === 'oncelik') return t(`yardim.oncelik.${d}`, { defaultValue: d });
    if (alan === 'kanal') return t(`destekKurallari.kanal.${d}`, { defaultValue: d });
    if (alan === 'hizmet') return t(`talep.hizmetler.${d}`, { defaultValue: d });
    if (alan === 'ata') return ekipAdi[d] || d;
    if (alan === 'hazir_cevap') return cevapAdi[d] || `#${d}`;
    return d;
  };

  const kosulOzeti = (k: Kosul) =>
    `${t(`destekKurallari.alan.${k.alan}`)} ${t(`destekKurallari.islec.${k.islec}`)} "${degerMetni(k.alan, k.deger)}"`;
  const eylemOzeti = (e: Eylem) =>
    e.tur === 'durdur' ? t('destekKurallari.eylem.durdur') : `${t(`destekKurallari.eylem.${e.tur}`)}: ${degerMetni(e.tur, e.deger)}`;

  // --- liste işlemleri --------------------------------------------------------
  const tasi = async (id: number, yon: -1 | 1) => {
    if (!liste) return;
    const i = liste.findIndex((k) => k.id === id);
    const j = i + yon;
    if (i < 0 || j < 0 || j >= liste.length) return;
    const yeni = [...liste];
    [yeni[i], yeni[j]] = [yeni[j], yeni[i]];
    setListe(yeni);
    try {
      setListe(await kurallariSirala(yeni.map((k) => k.id)));
    } catch (h) {
      hata(h);
      yukle();
    }
  };

  const aktifDegistir = async (k: Kural) => {
    try {
      const g = await kuralGuncelle(k.id, { ad: k.ad, aktif: !k.aktif, eslesme: k.eslesme, kosullar: k.kosullar, eylemler: k.eylemler });
      setListe((l) => (l ? l.map((x) => (x.id === k.id ? g : x)) : l));
    } catch (h) {
      hata(h);
    }
  };

  const sil = async (id: number) => {
    try {
      await kuralSil(id);
      toast.success(t('destekKurallari.silindi'));
      setSilinecek(null);
      yukle();
    } catch (h) {
      hata(h);
    }
  };

  // --- düzenleyici ------------------------------------------------------------
  const kaydet = async () => {
    if (!form) return;
    setKaydediliyor(true);
    const girdi: KuralGirdisi = {
      ad: form.ad.trim(),
      aktif: form.aktif,
      eslesme: form.eslesme,
      kosullar: form.kosullar.map((k) => ({ ...k, deger: String(k.deger).trim() })),
      eylemler: form.eylemler.map((e) => (e.tur === 'durdur' ? { tur: e.tur } : { tur: e.tur, deger: e.deger })),
    };
    try {
      if (form.id) await kuralGuncelle(form.id, girdi);
      else await kuralEkle(girdi);
      toast.success(t('destekKurallari.kaydedildi'));
      setForm(null);
      yukle();
    } catch (h) {
      hata(h);
    } finally {
      setKaydediliyor(false);
    }
  };

  const kosulDegis = (i: number, parca: Partial<Kosul>) => {
    if (!form) return;
    const kosullar = form.kosullar.map((k, j) => {
      if (j !== i) return k;
      const yeni = { ...k, ...parca };
      if (parca.alan && !KOSUL_ISLECLERI[parca.alan].includes(yeni.islec)) yeni.islec = KOSUL_ISLECLERI[parca.alan][0];
      if (parca.alan) {
        yeni.deger = parca.alan === 'kanal' ? 'eposta' : parca.alan === 'oncelik' ? 'acil' : parca.alan === 'hizmet' ? 'genel' : '';
      }
      return yeni;
    });
    setForm({ ...form, kosullar });
  };

  const varsayilanDeger = (tur: EylemTuru): string | number | undefined => {
    if (tur === 'oncelik') return 'yuksek';
    if (tur === 'ata') return ekip[0]?.email || '';
    if (tur === 'hizmet') return 'genel';
    if (tur === 'hazir_cevap') return cevaplar[0]?.id ?? '';
    if (tur === 'etiket') return '';
    return undefined;
  };

  const eylemDegis = (i: number, parca: Partial<Eylem>) => {
    if (!form) return;
    const eylemler = form.eylemler.map((e, j) => {
      if (j !== i) return e;
      if (parca.tur && parca.tur !== e.tur) return { tur: parca.tur, deger: varsayilanDeger(parca.tur) };
      return { ...e, ...parca };
    });
    setForm({ ...form, eylemler });
  };

  const kosulDegerAlani = (k: Kosul, i: number) => {
    const ortak = { 'aria-label': t('destekKurallari.deger'), 'data-testid': `kural-kosul-deger-${i}` };
    if (k.alan === 'kanal' || k.alan === 'oncelik' || k.alan === 'hizmet') {
      const secenekler = k.alan === 'kanal' ? KANALLAR : k.alan === 'oncelik' ? ONCELIKLER : [...HIZMETLER];
      return (
        <select className={`${SECIM} flex-1`} value={k.deger} onChange={(e) => kosulDegis(i, { deger: e.target.value })} {...ortak}>
          {secenekler.map((s) => (
            <option key={s} value={s}>
              {degerMetni(k.alan, s)}
            </option>
          ))}
        </select>
      );
    }
    return (
      <Input
        value={k.deger}
        onChange={(e) => kosulDegis(i, { deger: e.target.value })}
        placeholder={t(k.alan === 'gonderen' ? 'destekKurallari.gonderenYer' : 'destekKurallari.degerYer')}
        className="h-9 flex-1 bg-white/5"
        {...ortak}
      />
    );
  };

  const eylemDegerAlani = (e: Eylem, i: number) => {
    const ortak = { 'aria-label': t('destekKurallari.deger'), 'data-testid': `kural-eylem-deger-${i}` };
    const deger = String(e.deger ?? '');
    const sec = (secenekler: { v: string; ad: string }[]) => (
      <select className={`${SECIM} flex-1`} value={deger} onChange={(x) => eylemDegis(i, { deger: x.target.value })} {...ortak}>
        <option value="">{t('destekKurallari.secin')}</option>
        {secenekler.map((s) => (
          <option key={s.v} value={s.v}>
            {s.ad}
          </option>
        ))}
      </select>
    );
    if (e.tur === 'oncelik') return sec(ONCELIKLER.map((o) => ({ v: o, ad: degerMetni('oncelik', o) })));
    if (e.tur === 'ata') return sec(ekip.filter((k) => k.aktif !== false).map((k) => ({ v: k.email, ad: `${k.ad} (${k.email})` })));
    if (e.tur === 'hizmet') return sec(HIZMETLER.map((h) => ({ v: h, ad: degerMetni('hizmet', h) })));
    if (e.tur === 'hazir_cevap') return sec(cevaplar.map((c) => ({ v: String(c.id), ad: c.baslik })));
    if (e.tur === 'etiket')
      return (
        <Input
          value={deger}
          onChange={(x) => eylemDegis(i, { deger: x.target.value })}
          placeholder={t('destekKurallari.etiketYer')}
          className="h-9 flex-1 bg-white/5"
          {...ortak}
        />
      );
    return <span className="flex-1 text-xs text-muted-foreground">{t('destekKurallari.durdurAciklama')}</span>;
  };

  // --- dene ---------------------------------------------------------------------
  const deneCalistir = async () => {
    setDeneniyor(true);
    try {
      setDeneSonucu(await kurallariDene(dene));
    } catch (h) {
      hata(h);
    } finally {
      setDeneniyor(false);
    }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]" data-testid="destek-kurallari">
      <section className={KART}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="flex items-center gap-2 font-semibold">
              <Wand2 className="h-4 w-4 text-purple-300" aria-hidden="true" /> {t('destekKurallari.baslik')}
            </h3>
            <p className="mt-1 text-sm text-muted-foreground">{t('destekKurallari.aciklama')}</p>
          </div>
          {!form && (
            <Button size="sm" className="gap-2" onClick={() => setForm(bosForm())} data-testid="kural-yeni">
              <Plus className="h-4 w-4" /> {t('destekKurallari.yeni')}
            </Button>
          )}
        </div>

        {form && (
          <div className="mt-5 space-y-4 rounded-xl border border-white/10 bg-black/20 p-4" data-testid="kural-duzenleyici">
            <div className="flex flex-wrap items-end gap-3">
              <label className="min-w-[220px] flex-1 text-xs text-muted-foreground">
                {t('destekKurallari.ad')}
                <Input
                  value={form.ad}
                  onChange={(e) => setForm({ ...form, ad: e.target.value })}
                  placeholder={t('destekKurallari.adYer')}
                  className="mt-1 bg-white/5"
                  data-testid="kural-ad"
                />
              </label>
              <label className="flex items-center gap-2 pb-2 text-sm">
                <input type="checkbox" checked={form.aktif} onChange={(e) => setForm({ ...form, aktif: e.target.checked })} />
                {t('destekKurallari.aktif')}
              </label>
            </div>

            <fieldset className="space-y-2">
              <legend className="mb-1 flex flex-wrap items-center gap-2 text-xs font-medium uppercase tracking-widest text-muted-foreground">
                {t('destekKurallari.kosullar')}
                <select
                  className={`${SECIM} h-8 normal-case tracking-normal`}
                  value={form.eslesme}
                  onChange={(e) => setForm({ ...form, eslesme: e.target.value as Kural['eslesme'] })}
                  aria-label={t('destekKurallari.eslesmeEtiket')}
                  data-testid="kural-eslesme"
                >
                  <option value="hepsi">{t('destekKurallari.eslesme.hepsi')}</option>
                  <option value="herhangi">{t('destekKurallari.eslesme.herhangi')}</option>
                </select>
              </legend>
              {form.kosullar.length === 0 && <p className="text-xs text-muted-foreground">{t('destekKurallari.kosulYok')}</p>}
              {form.kosullar.map((k, i) => (
                <div key={i} className="flex flex-wrap items-center gap-2">
                  <select
                    className={SECIM}
                    value={k.alan}
                    onChange={(e) => kosulDegis(i, { alan: e.target.value as KosulAlani })}
                    aria-label={t('destekKurallari.alanEtiket')}
                    data-testid={`kural-kosul-alan-${i}`}
                  >
                    {ALANLAR.map((a) => (
                      <option key={a} value={a}>
                        {t(`destekKurallari.alan.${a}`)}
                      </option>
                    ))}
                  </select>
                  <select
                    className={SECIM}
                    value={k.islec}
                    onChange={(e) => kosulDegis(i, { islec: e.target.value })}
                    aria-label={t('destekKurallari.islecEtiket')}
                    data-testid={`kural-kosul-islec-${i}`}
                  >
                    {KOSUL_ISLECLERI[k.alan].map((o) => (
                      <option key={o} value={o}>
                        {t(`destekKurallari.islec.${o}`)}
                      </option>
                    ))}
                  </select>
                  {kosulDegerAlani(k, i)}
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={t('destekKurallari.kaldir')}
                    onClick={() => setForm({ ...form, kosullar: form.kosullar.filter((_, j) => j !== i) })}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              ))}
              <Button
                size="sm"
                variant="ghost"
                className="gap-1 text-xs"
                onClick={() => setForm({ ...form, kosullar: [...form.kosullar, { alan: 'konu', islec: 'icerir', deger: '' }] })}
                data-testid="kural-kosul-ekle"
              >
                <Plus className="h-3.5 w-3.5" /> {t('destekKurallari.kosulEkle')}
              </Button>
            </fieldset>

            <fieldset className="space-y-2">
              <legend className="mb-1 text-xs font-medium uppercase tracking-widest text-muted-foreground">
                {t('destekKurallari.eylemler')}
              </legend>
              {form.eylemler.map((e, i) => (
                <div key={i} className="flex flex-wrap items-center gap-2">
                  <select
                    className={SECIM}
                    value={e.tur}
                    onChange={(x) => eylemDegis(i, { tur: x.target.value as EylemTuru })}
                    aria-label={t('destekKurallari.eylemEtiket')}
                    data-testid={`kural-eylem-tur-${i}`}
                  >
                    {EYLEM_TURLERI.map((tur) => (
                      <option key={tur} value={tur}>
                        {t(`destekKurallari.eylem.${tur}`)}
                      </option>
                    ))}
                  </select>
                  {eylemDegerAlani(e, i)}
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={t('destekKurallari.kaldir')}
                    onClick={() => setForm({ ...form, eylemler: form.eylemler.filter((_, j) => j !== i) })}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              ))}
              <Button
                size="sm"
                variant="ghost"
                className="gap-1 text-xs"
                onClick={() => setForm({ ...form, eylemler: [...form.eylemler, { tur: 'etiket', deger: '' }] })}
                data-testid="kural-eylem-ekle"
              >
                <Plus className="h-3.5 w-3.5" /> {t('destekKurallari.eylemEkle')}
              </Button>
              {form.eylemler.some((e) => e.tur === 'hazir_cevap') && (
                <p className="text-xs text-amber-200/80">{t('destekKurallari.hazirCevapNotu')}</p>
              )}
            </fieldset>

            <div className="flex gap-2">
              <Button
                onClick={() => void kaydet()}
                disabled={kaydediliyor || !form.ad.trim() || form.eylemler.length === 0}
                className="gap-2"
                data-testid="kural-kaydet"
              >
                {kaydediliyor ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                {t('destekKurallari.kaydet')}
              </Button>
              <Button variant="ghost" onClick={() => setForm(null)}>
                {t('destekKurallari.vazgec')}
              </Button>
            </div>
          </div>
        )}

        {liste === null ? (
          <div className="flex justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : liste.length === 0 ? (
          <p className="mt-5 text-sm text-muted-foreground">{t('destekKurallari.bos')}</p>
        ) : (
          <ol className="mt-5 space-y-2">
            {liste.map((k, i) => (
              <li
                key={k.id}
                className={`rounded-xl border border-white/10 px-3 py-2.5 ${k.aktif ? 'bg-white/[0.02]' : 'opacity-60'}`}
                data-testid={`kural-satir-${k.id}`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="w-6 text-center text-xs text-muted-foreground">{i + 1}</span>
                  <p className="min-w-0 flex-1 truncate font-medium">{k.ad}</p>
                  <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <input
                      type="checkbox"
                      checked={k.aktif}
                      onChange={() => void aktifDegistir(k)}
                      data-testid={`kural-aktif-${k.id}`}
                    />
                    {k.aktif ? t('destekKurallari.aktif') : t('destekKurallari.pasif')}
                  </label>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={i === 0}
                    onClick={() => void tasi(k.id, -1)}
                    aria-label={t('destekKurallari.yukari')}
                    title={t('destekKurallari.yukari')}
                    data-testid={`kural-yukari-${k.id}`}
                  >
                    <ArrowUp className="h-4 w-4" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={i === liste.length - 1}
                    onClick={() => void tasi(k.id, 1)}
                    aria-label={t('destekKurallari.asagi')}
                    title={t('destekKurallari.asagi')}
                    data-testid={`kural-asagi-${k.id}`}
                  >
                    <ArrowDown className="h-4 w-4" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() =>
                      setForm({ id: k.id, ad: k.ad, aktif: k.aktif, eslesme: k.eslesme, kosullar: k.kosullar, eylemler: k.eylemler })
                    }
                    aria-label={t('destekKurallari.duzenle')}
                    title={t('destekKurallari.duzenle')}
                    data-testid={`kural-duzenle-${k.id}`}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  {silinecek === k.id ? (
                    <span className="flex items-center gap-1">
                      <span className="text-xs text-orange-300">{t('destekKurallari.silOnay')}</span>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-xs text-destructive"
                        onClick={() => void sil(k.id)}
                        data-testid={`kural-sil-evet-${k.id}`}
                      >
                        {t('destekKurallari.sil')}
                      </Button>
                      <Button size="sm" variant="ghost" className="text-xs" onClick={() => setSilinecek(null)}>
                        {t('destekKurallari.vazgec')}
                      </Button>
                    </span>
                  ) : (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-destructive hover:text-destructive"
                      onClick={() => setSilinecek(k.id)}
                      aria-label={t('destekKurallari.sil')}
                      title={t('destekKurallari.sil')}
                      data-testid={`kural-sil-${k.id}`}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  )}
                </div>
                <p className="mt-1 pl-8 text-xs text-muted-foreground">
                  <span className="text-foreground/70">{t('destekKurallari.eger')}</span>{' '}
                  {k.kosullar.length === 0
                    ? t('destekKurallari.herTalep')
                    : k.kosullar.map(kosulOzeti).join(k.eslesme === 'hepsi' ? ` ${t('destekKurallari.ve')} ` : ` ${t('destekKurallari.veya')} `)}
                  {' → '}
                  {k.eylemler.map(eylemOzeti).join(', ')}
                </p>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section className={`${KART} h-fit`}>
        <h3 className="flex items-center gap-2 font-semibold">
          <FlaskConical className="h-4 w-4 text-cyan-300" aria-hidden="true" /> {t('destekKurallari.dene.baslik')}
        </h3>
        <p className="mt-1 text-sm text-muted-foreground">{t('destekKurallari.dene.aciklama')}</p>
        <div className="mt-4 space-y-3">
          <Input
            value={dene.konu}
            onChange={(e) => setDene({ ...dene, konu: e.target.value })}
            placeholder={t('destekKurallari.dene.konu')}
            aria-label={t('destekKurallari.dene.konu')}
            className="bg-white/5"
            data-testid="dene-konu"
          />
          <Textarea
            value={dene.metin}
            onChange={(e) => setDene({ ...dene, metin: e.target.value })}
            placeholder={t('destekKurallari.dene.metin')}
            aria-label={t('destekKurallari.dene.metin')}
            rows={3}
            className="bg-white/5"
          />
          <div className="flex flex-wrap gap-2">
            <Input
              value={dene.gonderen}
              onChange={(e) => setDene({ ...dene, gonderen: e.target.value })}
              placeholder={t('destekKurallari.dene.gonderen')}
              aria-label={t('destekKurallari.dene.gonderen')}
              className="min-w-[180px] flex-1 bg-white/5"
              data-testid="dene-gonderen"
            />
            <select
              className={SECIM}
              value={dene.kanal}
              onChange={(e) => setDene({ ...dene, kanal: e.target.value })}
              aria-label={t('destekKurallari.dene.kanal')}
            >
              {KANALLAR.map((k) => (
                <option key={k} value={k}>
                  {t(`destekKurallari.kanal.${k}`)}
                </option>
              ))}
            </select>
          </div>
          <Button onClick={() => void deneCalistir()} disabled={deneniyor} className="gap-2" data-testid="dene-calistir">
            {deneniyor ? <Loader2 className="h-4 w-4 animate-spin" /> : <FlaskConical className="h-4 w-4" />}
            {t('destekKurallari.dene.calistir')}
          </Button>
          {deneSonucu && (
            <div className="rounded-xl border border-white/10 p-3 text-sm" data-testid="dene-sonuc" aria-live="polite">
              {deneSonucu.eslesen.length === 0 ? (
                <p className="text-muted-foreground">{t('destekKurallari.dene.sonucYok')}</p>
              ) : (
                <>
                  <p className="mb-2 text-xs uppercase tracking-widest text-muted-foreground">{t('destekKurallari.dene.eslesen')}</p>
                  <ol className="space-y-1.5">
                    {deneSonucu.eslesen.map((k) => (
                      <li key={k.id}>
                        <span className="font-medium">{k.ad}</span>
                        <span className="block text-xs text-muted-foreground">{k.eylemler.map(eylemOzeti).join(', ')}</span>
                      </li>
                    ))}
                  </ol>
                  {deneSonucu.durduruldu && <p className="mt-2 text-xs text-amber-200/80">{t('destekKurallari.dene.durduruldu')}</p>}
                </>
              )}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
