import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Eye,
  EyeOff,
  Info,
  Loader2,
  Pencil,
  Plus,
  Star,
  Trash2,
  X,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  BAGLANTI_TURLERI,
  KAYNAK_CEVIRI_DILLERI,
  KaynakIstekHatasi,
  kaynakEkle,
  kaynakGuncelle,
  kaynakSil,
  kaynakYama,
  kaynaklariSirala,
  yonetimListesi,
  type KaynakCevirisi,
  type KaynakGirdisi,
  type YonetimKaynagi,
  type YonetimListesi,
} from '@/lib/kaynakYonetimi';

/**
 * Faz 3K — Kaynaklar sekmesi.
 *
 * Liste (arama, yayında / öne çıkan anahtarı, sıra okları), düzenleme
 * formu (marketplace'teki dil seçicili çeviri düzeni: TR ana alanlar,
 * diğer diller Türkçe değeri soluk yer tutucu olarak gösteren çeviri
 * alanları), yeni kaynak ve silme (çöp kutusuna).
 *
 * Panelden eklenen kaynak sitede hemen (API'den) görünüyor; arama
 * motorlarının gördüğü prerender HTML'i bir sonraki yayında üretiliyor —
 * formun üstündeki bilgi satırı bunu söylüyor.
 */

const CEVIRI_ALANLARI = ['baslik', 'ozet', 'aciklama', 'adimlar'] as const;
type CeviriAlani = (typeof CEVIRI_ALANLARI)[number];
/** Formda her alan düz metin; adımlar satır satır. */
type CeviriFormu = Record<string, Record<CeviriAlani, string>>;

interface Taslak {
  id?: number;
  baslik: string;
  slug: string;
  kategori: string;
  sira: string;
  ozet: string;
  aciklama: string;
  adimlar: string;
  etiketler: string;
  baglanti: string;
  baglanti_turu: string;
  lisans: string;
  youtube_short: string;
  dogrulama_tarihi: string;
  ucretsiz: boolean;
  acik_kaynak: boolean;
  one_cikan: boolean;
  yayinda: boolean;
}

const BUGUN = () => new Date().toISOString().slice(0, 10);

function bosTaslak(kategori: string): Taslak {
  return {
    baslik: '',
    slug: '',
    kategori,
    sira: '100',
    ozet: '',
    aciklama: '',
    adimlar: '',
    etiketler: '',
    baglanti: '',
    baglanti_turu: 'github',
    lisans: '',
    youtube_short: '',
    dogrulama_tarihi: BUGUN(),
    ucretsiz: true,
    acik_kaynak: true,
    one_cikan: false,
    yayinda: true,
  };
}

function taslagaCevir(k: YonetimKaynagi): Taslak {
  return {
    id: k.id,
    baslik: k.baslik,
    slug: k.slug,
    kategori: k.kategori,
    sira: String(k.sira ?? 100),
    ozet: k.ozet ?? '',
    aciklama: k.aciklama ?? '',
    adimlar: (k.adimlar ?? []).join('\n'),
    etiketler: (k.etiketler ?? []).join(', '),
    baglanti: k.baglanti,
    baglanti_turu: k.baglanti_turu || 'site',
    lisans: k.lisans ?? '',
    youtube_short: k.youtube_short ?? '',
    dogrulama_tarihi: k.dogrulama_tarihi ?? '',
    ucretsiz: k.ucretsiz,
    acik_kaynak: k.acik_kaynak,
    one_cikan: k.one_cikan,
    yayinda: k.yayinda,
  };
}

function ceviriFormuKur(k?: YonetimKaynagi): CeviriFormu {
  const form: CeviriFormu = {};
  for (const d of KAYNAK_CEVIRI_DILLERI) {
    const c: KaynakCevirisi = k?.ceviriler?.[d] ?? {};
    form[d] = {
      baslik: c.baslik ?? '',
      ozet: c.ozet ?? '',
      aciklama: c.aciklama ?? '',
      adimlar: (c.adimlar ?? []).join('\n'),
    };
  }
  return form;
}

const satirlar = (metin: string) =>
  metin
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean);

/** Dolu çeviri alanları; boş alan kaydedilmez (sitede Türkçeye düşer). */
function ceviriFormunuTopla(form: CeviriFormu): Record<string, KaynakCevirisi> {
  const sonuc: Record<string, KaynakCevirisi> = {};
  for (const d of KAYNAK_CEVIRI_DILLERI) {
    const f = form[d];
    if (!f) continue;
    const c: KaynakCevirisi = {};
    if (f.baslik.trim()) c.baslik = f.baslik.trim();
    if (f.ozet.trim()) c.ozet = f.ozet.trim();
    if (f.aciklama.trim()) c.aciklama = f.aciklama.trim();
    const adimlar = satirlar(f.adimlar);
    if (adimlar.length) c.adimlar = adimlar;
    if (Object.keys(c).length) sonuc[d] = c;
  }
  return sonuc;
}

function ceviriliDilSayisi(k: YonetimKaynagi): number {
  return KAYNAK_CEVIRI_DILLERI.filter((d) => Object.keys(k.ceviriler?.[d] ?? {}).length > 0).length;
}

/** Başlıktan URL'ye uygun kısa ad (Türkçe harfler karşılıklarına düşer). */
function slugla(metin: string): string {
  const harita: Record<string, string> = {
    ç: 'c', ğ: 'g', ı: 'i', ö: 'o', ş: 's', ü: 'u', â: 'a', î: 'i', û: 'u',
    Ç: 'c', Ğ: 'g', İ: 'i', Ö: 'o', Ş: 's', Ü: 'u', Â: 'a', Î: 'i', Û: 'u',
  };
  return metin
    .split('')
    .map((k) => harita[k] ?? k)
    .join('')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80)
    .replace(/-+$/g, '');
}

const httpMi = (adres: string) => /^https?:\/\/\S+$/i.test(adres.trim());

export default function KaynakYonetimi() {
  const { t, i18n } = useTranslation();
  const [veri, setVeri] = useState<YonetimListesi | null>(null);
  const [listeHatasi, setListeHatasi] = useState(false);
  const [arama, setArama] = useState('');
  const [duzenlenen, setDuzenlenen] = useState<Taslak | null>(null);
  const [formDili, setFormDili] = useState<string>('tr');
  const [ceviriFormu, setCeviriFormu] = useState<CeviriFormu>({});
  const [kaydediliyor, setKaydediliyor] = useState(false);
  const [mesgul, setMesgul] = useState<number | null>(null);

  const hataMetni = useCallback(
    (hata: unknown) => {
      const kod = hata instanceof KaynakIstekHatasi ? hata.kod : 'genel';
      return t(`kaynakYonetimi.hataKod.${kod}`, t('kaynakYonetimi.hataKod.genel'));
    },
    [t],
  );

  const yukle = useCallback(async () => {
    try {
      setVeri(await yonetimListesi());
      setListeHatasi(false);
    } catch {
      setListeHatasi(true);
      setVeri((onceki) => onceki ?? { kaynaklar: [], kategoriler: [] });
    }
  }, []);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const kategoriAdi = useCallback(
    (anahtar: string) => {
      const k = veri?.kategoriler.find((c) => c.anahtar === anahtar);
      const dil = (i18n.language || 'tr').slice(0, 2);
      return k?.ad?.[dil] || k?.ad?.tr || anahtar;
    },
    [veri, i18n.language],
  );

  const gorunen = useMemo(() => {
    const liste = veri?.kaynaklar ?? [];
    const q = arama.trim().toLocaleLowerCase('tr');
    if (!q) return liste;
    return liste.filter((k) =>
      [k.baslik, k.slug, k.ozet, ...(k.etiketler ?? [])].join(' ').toLocaleLowerCase('tr').includes(q),
    );
  }, [veri, arama]);

  const duzenlemeyeBasla = (k?: YonetimKaynagi) => {
    setFormDili('tr');
    setCeviriFormu(ceviriFormuKur(k));
    setDuzenlenen(k ? taslagaCevir(k) : bosTaslak(veri?.kategoriler[0]?.anahtar ?? 'ajan'));
  };

  const degistir = <A extends keyof Taslak>(alan: A, deger: Taslak[A]) =>
    setDuzenlenen((onceki) => (onceki ? { ...onceki, [alan]: deger } : onceki));

  const kaydet = async () => {
    if (!duzenlenen) return;
    const baslik = duzenlenen.baslik.trim();
    if (!baslik) {
      setFormDili('tr');
      toast.error(t('kaynakYonetimi.hataKod.baslik_gerekli'));
      return;
    }
    if (!httpMi(duzenlenen.baglanti)) {
      setFormDili('tr');
      toast.error(t('kaynakYonetimi.hataKod.gecersiz_baglanti'));
      return;
    }
    const sira = Number.parseInt(duzenlenen.sira, 10);
    const girdi: KaynakGirdisi = {
      slug: duzenlenen.slug.trim() || slugla(baslik),
      kategori: duzenlenen.kategori,
      baslik,
      ozet: duzenlenen.ozet.trim(),
      aciklama: duzenlenen.aciklama.trim(),
      adimlar: satirlar(duzenlenen.adimlar),
      ceviriler: ceviriFormunuTopla(ceviriFormu),
      etiketler: duzenlenen.etiketler
        .split(',')
        .map((e) => e.trim())
        .filter(Boolean),
      baglanti: duzenlenen.baglanti.trim(),
      baglanti_turu: duzenlenen.baglanti_turu,
      lisans: duzenlenen.lisans.trim() || null,
      ucretsiz: duzenlenen.ucretsiz,
      acik_kaynak: duzenlenen.acik_kaynak,
      youtube_short: duzenlenen.youtube_short.trim() || null,
      one_cikan: duzenlenen.one_cikan,
      sira: Number.isFinite(sira) ? sira : 100,
      yayinda: duzenlenen.yayinda,
      dogrulama_tarihi: duzenlenen.dogrulama_tarihi || null,
    };
    setKaydediliyor(true);
    try {
      if (duzenlenen.id) await kaynakGuncelle(duzenlenen.id, girdi);
      else await kaynakEkle(girdi);
      toast.success(t('kaynakYonetimi.kaydedildi'));
      setDuzenlenen(null);
      await yukle();
    } catch (hata) {
      toast.error(hataMetni(hata));
    } finally {
      setKaydediliyor(false);
    }
  };

  const yamala = async (k: YonetimKaynagi, yama: Parameters<typeof kaynakYama>[1]) => {
    setMesgul(k.id);
    try {
      await kaynakYama(k.id, yama);
      toast.success(t('kaynakYonetimi.guncellendi'));
      await yukle();
    } catch (hata) {
      toast.error(hataMetni(hata));
    } finally {
      setMesgul(null);
    }
  };

  const sil = async (k: YonetimKaynagi) => {
    if (!confirm(t('kaynakYonetimi.silOnay', { baslik: k.baslik }))) return;
    setMesgul(k.id);
    try {
      await kaynakSil(k.id);
      toast.success(t('kaynakYonetimi.silindi'));
      await yukle();
    } catch (hata) {
      toast.error(hataMetni(hata));
    } finally {
      setMesgul(null);
    }
  };

  /** Komşusuyla yer değiştirir (öne çıkanlar kendi aralarında; sitede de önce onlar). */
  const tasi = async (index: number, yon: -1 | 1) => {
    const liste = veri?.kaynaklar ?? [];
    const hedef = index + yon;
    if (hedef < 0 || hedef >= liste.length || liste[hedef].one_cikan !== liste[index].one_cikan) return;
    const yeni = [...liste];
    [yeni[index], yeni[hedef]] = [yeni[hedef], yeni[index]];
    setVeri((onceki) => (onceki ? { ...onceki, kaynaklar: yeni } : onceki));
    setMesgul(liste[index].id);
    try {
      await kaynaklariSirala(yeni.map((k) => k.id));
    } catch (hata) {
      toast.error(hataMetni(hata));
    } finally {
      setMesgul(null);
      await yukle();
    }
  };

  const alanSinifi = 'bg-white/5 border-white/10';
  const etiketSinifi = 'mb-2 block text-xs uppercase tracking-widest text-muted-foreground';
  const ipucuSinifi = 'mt-1 text-[11px] text-muted-foreground';
  const siraliMi = !arama.trim();
  const tumu = veri?.kaynaklar ?? [];

  return (
    <div data-kaynak-yonetimi>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">{t('kaynakYonetimi.aciklama')}</p>
        <Button
          onClick={() => duzenlemeyeBasla()}
          data-testid="kaynak-yeni"
          className="h-11 border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white"
        >
          <Plus className="me-2 h-4 w-4" /> {t('kaynakYonetimi.yeni')}
        </Button>
      </div>

      <p
        className="mb-6 flex items-start gap-2 rounded-xl border border-sky-400/30 bg-sky-500/10 px-4 py-3 text-xs text-muted-foreground"
        data-kaynak-bilgi
      >
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-sky-300" aria-hidden="true" />
        {t('kaynakYonetimi.bilgi')}
      </p>

      <div className="mb-4 max-w-md">
        <Input
          type="search"
          value={arama}
          onChange={(e) => setArama(e.target.value)}
          placeholder={t('kaynakYonetimi.ara')}
          aria-label={t('kaynakYonetimi.ara')}
          className={alanSinifi}
          data-testid="kaynak-ara"
        />
      </div>

      {veri === null && (
        <p className="flex items-center gap-2 py-12 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> {t('kaynakYonetimi.yukleniyor')}
        </p>
      )}

      {listeHatasi && <p className="mb-4 text-sm text-red-300">{t('kaynakYonetimi.listeHatasi')}</p>}

      {veri !== null && gorunen.length === 0 && (
        <p className="rounded-xl border border-white/10 bg-white/[0.03] px-6 py-10 text-center text-sm text-muted-foreground">
          {tumu.length === 0 ? t('kaynakYonetimi.bos') : t('kaynakYonetimi.eslesmeYok')}
        </p>
      )}

      {veri !== null && gorunen.length > 0 && (
        <div className="space-y-2">
          {gorunen.map((k) => {
            const index = tumu.indexOf(k);
            const ustteMi = index <= 0 || tumu[index - 1].one_cikan !== k.one_cikan;
            const alttaMi = index >= tumu.length - 1 || tumu[index + 1].one_cikan !== k.one_cikan;
            const bekliyor = mesgul === k.id;
            const dugme = '!bg-transparent !hover:bg-transparent border-white/20';
            return (
              <div
                key={k.id}
                data-kaynak-satiri={k.slug}
                className="cam-kart flex flex-wrap items-center gap-3 rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3"
              >
                {siraliMi && (
                  <div className="flex flex-col">
                    <button
                      type="button"
                      onClick={() => void tasi(index, -1)}
                      disabled={ustteMi || mesgul !== null}
                      aria-label={t('kaynakYonetimi.yukari')}
                      data-islem="yukari"
                      className="rounded p-0.5 text-muted-foreground hover:text-foreground disabled:opacity-30"
                    >
                      <ChevronUp className="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => void tasi(index, 1)}
                      disabled={alttaMi || mesgul !== null}
                      aria-label={t('kaynakYonetimi.asagi')}
                      data-islem="asagi"
                      className="rounded p-0.5 text-muted-foreground hover:text-foreground disabled:opacity-30"
                    >
                      <ChevronDown className="h-4 w-4" />
                    </button>
                  </div>
                )}

                <div className="min-w-0 flex-1">
                  <p className="flex items-center gap-2 truncate font-semibold">
                    {k.one_cikan && (
                      <Star className="h-3.5 w-3.5 shrink-0 fill-amber-400 text-amber-400" aria-label={t('kaynakYonetimi.oneCikan')} />
                    )}
                    <span className="truncate">{k.baslik}</span>
                  </p>
                  {/* Büyük harf yok: Türkçe yerelde slug "/MONEYPRİNTER…" gibi yanıltıcı görünüyordu. */}
                  <p className="font-mono text-[10px] tracking-wider text-muted-foreground">
                    /{k.slug} · {kategoriAdi(k.kategori)} · {t('kaynakYonetimi.sira', { sayi: k.sira })} ·{' '}
                    {t('marketplaceCeviri.durum', 'çeviri {{sayi}}/{{toplam}}', {
                      sayi: ceviriliDilSayisi(k),
                      toplam: KAYNAK_CEVIRI_DILLERI.length,
                    })}
                  </p>
                </div>

                <span
                  data-durum={k.yayinda ? 'yayinda' : 'taslak'}
                  className={`rounded-full px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider ${
                    k.yayinda ? 'bg-primary/15 text-primary' : 'bg-white/10 text-muted-foreground'
                  }`}
                >
                  {k.yayinda ? t('kaynakYonetimi.yayinda') : t('kaynakYonetimi.taslak')}
                </span>

                <Button
                  variant="outline"
                  size="sm"
                  disabled={bekliyor}
                  onClick={() => void yamala(k, { yayinda: !k.yayinda })}
                  aria-label={k.yayinda ? t('kaynakYonetimi.yayindanKaldir') : t('kaynakYonetimi.yayinla')}
                  title={k.yayinda ? t('kaynakYonetimi.yayindanKaldir') : t('kaynakYonetimi.yayinla')}
                  data-islem="yayin"
                  className={dugme}
                >
                  {k.yayinda ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={bekliyor}
                  onClick={() => void yamala(k, { one_cikan: !k.one_cikan })}
                  aria-label={k.one_cikan ? t('kaynakYonetimi.oneCikandanKaldir') : t('kaynakYonetimi.oneCikar')}
                  title={k.one_cikan ? t('kaynakYonetimi.oneCikandanKaldir') : t('kaynakYonetimi.oneCikar')}
                  aria-pressed={k.one_cikan}
                  data-islem="one-cikan"
                  className={dugme}
                >
                  <Star className={`h-4 w-4 ${k.one_cikan ? 'fill-amber-400 text-amber-400' : ''}`} />
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => duzenlemeyeBasla(k)}
                  aria-label={t('kaynakYonetimi.duzenle')}
                  title={t('kaynakYonetimi.duzenle')}
                  data-islem="duzenle"
                  className={dugme}
                >
                  <Pencil className="h-4 w-4" />
                </Button>
                {k.yayinda && (
                  <Button asChild variant="outline" size="sm" className={dugme}>
                    <a
                      href={`/kaynaklar/${k.slug}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      aria-label={t('kaynakYonetimi.sitedeGor')}
                      title={t('kaynakYonetimi.sitedeGor')}
                    >
                      <ExternalLink className="h-4 w-4" />
                    </a>
                  </Button>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  disabled={bekliyor}
                  onClick={() => void sil(k)}
                  aria-label={t('kaynakYonetimi.sil')}
                  title={t('kaynakYonetimi.sil')}
                  data-islem="sil"
                  className={`${dugme} text-red-300`}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            );
          })}
        </div>
      )}

      {/* Düzenleme formu */}
      {duzenlenen && (
        // Blok düzen (flex ortalama değil): form ekrandan uzunsa üstü kaydırılarak erişilebilir kalıyor.
        <div className="fixed inset-0 z-50 overflow-y-auto bg-background/80 p-4 backdrop-blur-sm">
          <div
            className="glass relative mx-auto my-8 w-full max-w-2xl rounded-2xl border border-purple-500/30 p-6 sm:p-8"
            role="dialog"
            aria-modal="true"
            aria-labelledby="kaynak-form-baslik"
            data-testid="kaynak-form"
          >
            <button
              type="button"
              className="absolute end-4 top-4 rounded-lg p-2 hover:bg-white/5"
              onClick={() => setDuzenlenen(null)}
              aria-label={t('kaynakYonetimi.form.kapat')}
            >
              <X className="h-4 w-4" />
            </button>
            <h3 id="kaynak-form-baslik" className="mb-6 text-2xl font-bold">
              {duzenlenen.id ? t('kaynakYonetimi.form.duzenleBaslik') : t('kaynakYonetimi.form.yeniBaslik')}
            </h3>

            <div
              className="mb-5 flex flex-wrap items-center gap-1.5"
              role="group"
              aria-label={t('marketplaceCeviri.dilSecimi', 'Düzenlenen dil')}
            >
              {['tr', ...KAYNAK_CEVIRI_DILLERI].map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => setFormDili(d)}
                  aria-pressed={formDili === d}
                  data-dil={d}
                  className={`rounded-md px-2.5 py-1 text-xs font-semibold uppercase ${
                    formDili === d
                      ? 'bg-primary text-background'
                      : 'border border-white/10 text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {d}
                </button>
              ))}
              {formDili !== 'tr' && (
                <span className="ms-2 text-[11px] text-muted-foreground">
                  {t('marketplaceCeviri.ipucu', 'Boş bırakılan alan sitede Türkçe görünür. Soluk yazı Türkçe değerdir.')}
                </span>
              )}
            </div>

            {formDili !== 'tr' ? (
              <div className="space-y-4" dir={formDili === 'ar' ? 'rtl' : undefined}>
                {CEVIRI_ALANLARI.map((a) => {
                  const deger = ceviriFormu[formDili]?.[a] ?? '';
                  const yerTutucu = duzenlenen[a] || '';
                  const yaz = (yeni: string) =>
                    setCeviriFormu((onceki) => ({ ...onceki, [formDili]: { ...onceki[formDili], [a]: yeni } }));
                  return (
                    <div key={a}>
                      <Label className={etiketSinifi} htmlFor={`kaynak-ceviri-${a}`}>
                        {t(`kaynakYonetimi.form.${a}`)} ({formDili.toUpperCase()})
                      </Label>
                      {a === 'baslik' ? (
                        <Input
                          id={`kaynak-ceviri-${a}`}
                          name={`ceviri-${a}`}
                          className={`${alanSinifi} placeholder:text-white/30`}
                          placeholder={yerTutucu}
                          value={deger}
                          onChange={(e) => yaz(e.target.value)}
                        />
                      ) : (
                        <Textarea
                          id={`kaynak-ceviri-${a}`}
                          name={`ceviri-${a}`}
                          rows={a === 'ozet' ? 2 : a === 'aciklama' ? 6 : 4}
                          className={`${alanSinifi} placeholder:text-white/30`}
                          placeholder={yerTutucu}
                          value={deger}
                          onChange={(e) => yaz(e.target.value)}
                        />
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="space-y-4">
                <div>
                  <Label className={etiketSinifi} htmlFor="kaynak-baslik">
                    {t('kaynakYonetimi.form.baslik')} *
                  </Label>
                  <Input
                    id="kaynak-baslik"
                    name="baslik"
                    className={alanSinifi}
                    value={duzenlenen.baslik}
                    onChange={(e) => degistir('baslik', e.target.value)}
                  />
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <Label className={etiketSinifi} htmlFor="kaynak-slug">
                      {t('kaynakYonetimi.form.slug')}
                    </Label>
                    <Input
                      id="kaynak-slug"
                      name="slug"
                      dir="ltr"
                      className={`${alanSinifi} font-mono text-xs`}
                      placeholder={slugla(duzenlenen.baslik)}
                      value={duzenlenen.slug}
                      onChange={(e) => degistir('slug', e.target.value)}
                    />
                    <p className={ipucuSinifi}>{t('kaynakYonetimi.form.slugIpucu')}</p>
                  </div>
                  <div className="grid grid-cols-3 gap-3">
                    <div className="col-span-2">
                      <Label className={etiketSinifi} htmlFor="kaynak-kategori">
                        {t('kaynakYonetimi.form.kategori')}
                      </Label>
                      <select
                        id="kaynak-kategori"
                        name="kategori"
                        value={duzenlenen.kategori}
                        onChange={(e) => degistir('kategori', e.target.value)}
                        className="h-10 w-full rounded-md border border-white/10 bg-white/5 px-3 text-sm"
                      >
                        {(veri?.kategoriler ?? []).map((c) => (
                          <option key={c.anahtar} value={c.anahtar} className="bg-background">
                            {kategoriAdi(c.anahtar)}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <Label className={etiketSinifi} htmlFor="kaynak-sira">
                        {t('kaynakYonetimi.form.sira')}
                      </Label>
                      <Input
                        id="kaynak-sira"
                        name="sira"
                        type="number"
                        className={alanSinifi}
                        value={duzenlenen.sira}
                        onChange={(e) => degistir('sira', e.target.value)}
                      />
                    </div>
                  </div>
                </div>

                <div>
                  <Label className={etiketSinifi} htmlFor="kaynak-ozet">
                    {t('kaynakYonetimi.form.ozet')}{' '}
                    <span className={duzenlenen.ozet.length > 160 ? 'text-amber-300' : ''}>
                      ({t('kaynakYonetimi.form.karakter', { sayi: duzenlenen.ozet.length })})
                    </span>
                  </Label>
                  <Textarea
                    id="kaynak-ozet"
                    name="ozet"
                    rows={2}
                    className={alanSinifi}
                    value={duzenlenen.ozet}
                    onChange={(e) => degistir('ozet', e.target.value)}
                  />
                  <p className={ipucuSinifi}>{t('kaynakYonetimi.form.ozetIpucu')}</p>
                </div>

                <div>
                  <Label className={etiketSinifi} htmlFor="kaynak-aciklama">
                    {t('kaynakYonetimi.form.aciklama')}
                  </Label>
                  <Textarea
                    id="kaynak-aciklama"
                    name="aciklama"
                    rows={6}
                    className={alanSinifi}
                    value={duzenlenen.aciklama}
                    onChange={(e) => degistir('aciklama', e.target.value)}
                  />
                  <p className={ipucuSinifi}>{t('kaynakYonetimi.form.aciklamaIpucu')}</p>
                </div>

                <div>
                  <Label className={etiketSinifi} htmlFor="kaynak-adimlar">
                    {t('kaynakYonetimi.form.adimlar')}
                  </Label>
                  <Textarea
                    id="kaynak-adimlar"
                    name="adimlar"
                    rows={4}
                    className={alanSinifi}
                    value={duzenlenen.adimlar}
                    onChange={(e) => degistir('adimlar', e.target.value)}
                  />
                  <p className={ipucuSinifi}>{t('kaynakYonetimi.form.adimlarIpucu')}</p>
                </div>

                <div>
                  <Label className={etiketSinifi} htmlFor="kaynak-etiketler">
                    {t('kaynakYonetimi.form.etiketler')}
                  </Label>
                  <Input
                    id="kaynak-etiketler"
                    name="etiketler"
                    className={alanSinifi}
                    value={duzenlenen.etiketler}
                    onChange={(e) => degistir('etiketler', e.target.value)}
                  />
                  <p className={ipucuSinifi}>{t('kaynakYonetimi.form.etiketlerIpucu')}</p>
                </div>

                <div className="grid gap-4 sm:grid-cols-3">
                  <div className="sm:col-span-2">
                    <Label className={etiketSinifi} htmlFor="kaynak-baglanti">
                      {t('kaynakYonetimi.form.baglanti')} *
                    </Label>
                    <Input
                      id="kaynak-baglanti"
                      name="baglanti"
                      type="url"
                      dir="ltr"
                      inputMode="url"
                      placeholder="https://…"
                      className={alanSinifi}
                      value={duzenlenen.baglanti}
                      onChange={(e) => degistir('baglanti', e.target.value)}
                    />
                  </div>
                  <div>
                    <Label className={etiketSinifi} htmlFor="kaynak-baglanti-turu">
                      {t('kaynakYonetimi.form.baglantiTuru')}
                    </Label>
                    <select
                      id="kaynak-baglanti-turu"
                      name="baglanti_turu"
                      value={duzenlenen.baglanti_turu}
                      onChange={(e) => degistir('baglanti_turu', e.target.value)}
                      className="h-10 w-full rounded-md border border-white/10 bg-white/5 px-3 text-sm"
                    >
                      {BAGLANTI_TURLERI.map((tur) => (
                        <option key={tur} value={tur} className="bg-background">
                          {t(`kaynakYonetimi.tur.${tur}`)}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="grid gap-4 sm:grid-cols-3">
                  <div>
                    <Label className={etiketSinifi} htmlFor="kaynak-lisans">
                      {t('kaynakYonetimi.form.lisans')}
                    </Label>
                    <Input
                      id="kaynak-lisans"
                      name="lisans"
                      dir="ltr"
                      className={alanSinifi}
                      placeholder="MIT"
                      value={duzenlenen.lisans}
                      onChange={(e) => degistir('lisans', e.target.value)}
                    />
                  </div>
                  <div className="sm:col-span-2">
                    <Label className={etiketSinifi} htmlFor="kaynak-youtube">
                      {t('kaynakYonetimi.form.youtube')}
                    </Label>
                    <Input
                      id="kaynak-youtube"
                      name="youtube_short"
                      type="url"
                      dir="ltr"
                      inputMode="url"
                      className={alanSinifi}
                      placeholder="https://youtube.com/shorts/…"
                      value={duzenlenen.youtube_short}
                      onChange={(e) => degistir('youtube_short', e.target.value)}
                    />
                    <p className={ipucuSinifi}>{t('kaynakYonetimi.form.youtubeIpucu')}</p>
                  </div>
                </div>

                <div className="grid items-end gap-4 sm:grid-cols-2">
                  <div>
                    <Label className={etiketSinifi} htmlFor="kaynak-dogrulama">
                      {t('kaynakYonetimi.form.dogrulama')}
                    </Label>
                    <Input
                      id="kaynak-dogrulama"
                      name="dogrulama_tarihi"
                      type="date"
                      className={alanSinifi}
                      value={duzenlenen.dogrulama_tarihi}
                      onChange={(e) => degistir('dogrulama_tarihi', e.target.value)}
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    {(
                      [
                        ['ucretsiz', 'kaynakYonetimi.form.ucretsiz'],
                        ['acik_kaynak', 'kaynakYonetimi.form.acikKaynak'],
                        ['one_cikan', 'kaynakYonetimi.form.oneCikan'],
                        ['yayinda', 'kaynakYonetimi.form.yayinda'],
                      ] as const
                    ).map(([alan, anahtar]) => (
                      <label key={alan} className="flex items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          name={alan}
                          checked={duzenlenen[alan]}
                          onChange={(e) => degistir(alan, e.target.checked)}
                          className="h-4 w-4 accent-primary"
                        />
                        {t(anahtar)}
                      </label>
                    ))}
                  </div>
                </div>
              </div>
            )}

            <div className="mt-6 flex gap-3">
              <Button
                onClick={() => void kaydet()}
                disabled={kaydediliyor}
                data-testid="kaynak-kaydet"
                className="h-11 flex-1 border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white"
              >
                {kaydediliyor && <Loader2 className="me-2 h-4 w-4 animate-spin" />}
                {t('kaynakYonetimi.form.kaydet')}
              </Button>
              <Button
                variant="outline"
                onClick={() => setDuzenlenen(null)}
                className="h-11 border-white/20 !bg-transparent !hover:bg-transparent"
              >
                {t('kaynakYonetimi.form.vazgec')}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
