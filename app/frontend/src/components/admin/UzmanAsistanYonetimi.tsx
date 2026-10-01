import { useCallback, useEffect, useMemo, useState } from 'react';
import { Bot, Loader2, Pencil, Play, Save, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import GuvenliMarkdown from '@/components/asistanlar/GuvenliMarkdown';
import {
  CEVIRI_DILLERI,
  hataMetni,
  asistanDene,
  asistanGuncelle,
  ayarlariKaydet,
  kullanimGetir,
  yonetimGetir,
  type AsistanAyarlari,
  type CeviriDili,
  type KullanimOzeti,
  type YonetimAsistani,
  type YonetimVerisi,
} from '@/lib/uzmanAsistanlar';

/**
 * Faz 3U — yönetici paneli › Uzman Asistanlar.
 *
 * * Ayarlar: model, max_tokens, hesap başına günlük mesaj, mesaj başı kredi;
 *   herkese açık yapay zekâ uçlarının günlük bütçesi ve modeli.
 * * Liste: aktif anahtarı, sıra, düzenleme (ad/açıklama/örnek sorular 7 dil
 *   — kaynaklardaki dil seçicili düzen — ve sistem istemi), "Dene" kutusu
 *   (yöneticinin kendisi dener; hiçbir şey kaydedilmez).
 * * Kullanım özeti (son 30 gün) ve kaynak/lisans bildirimi.
 * Modülün müşteri bazında açılması Modüller sekmesinden.
 */

type FormDili = 'tr' | CeviriDili;

interface Taslak {
  anahtar: string;
  kategori: string;
  ad: string;
  aciklama: string;
  sorular: string;
  sistem_istemi: string;
  ceviriler: Record<CeviriDili, { ad: string; aciklama: string; sorular: string }>;
}

const alanSinifi = 'bg-white/5 border-white/10';
const etiketSinifi = 'mb-1.5 block text-xs uppercase tracking-widest text-muted-foreground';

function taslakYap(a: YonetimAsistani): Taslak {
  const ceviriler = {} as Taslak['ceviriler'];
  for (const d of CEVIRI_DILLERI) {
    const c = a.ceviriler?.[d];
    ceviriler[d] = { ad: c?.ad ?? '', aciklama: c?.aciklama ?? '', sorular: (c?.ornek_sorular ?? []).join('\n') };
  }
  return {
    anahtar: a.anahtar,
    kategori: a.kategori,
    ad: a.ad,
    aciklama: a.aciklama,
    sorular: a.ornek_sorular.join('\n'),
    sistem_istemi: a.sistem_istemi,
    ceviriler,
  };
}

const satirlar = (metin: string) =>
  metin
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean);

export default function UzmanAsistanYonetimi() {
  const { t, i18n } = useTranslation();
  const dil = (i18n.language || 'tr').slice(0, 2);
  const [veri, setVeri] = useState<YonetimVerisi | null>(null);
  const [kullanim, setKullanim] = useState<KullanimOzeti | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [duzenlenen, setDuzenlenen] = useState<Taslak | null>(null);
  const [deneme, setDeneme] = useState<YonetimAsistani | null>(null);

  const yukle = useCallback(async () => {
    try {
      const [v, k] = await Promise.all([yonetimGetir(), kullanimGetir(30)]);
      setVeri(v);
      setKullanim(k);
      setHata(null);
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  }, [t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const kategoriAdi = useCallback(
    (anahtar: string) => {
      const k = veri?.kategoriler.find((x) => x.anahtar === anahtar);
      return k?.ad?.[dil] || k?.ad?.tr || anahtar;
    },
    [veri, dil]
  );

  const yama = async (a: YonetimAsistani, govde: Partial<YonetimAsistani>) => {
    try {
      const yeni = await asistanGuncelle(a.anahtar, govde);
      setVeri((v) => (v ? { ...v, asistanlar: v.asistanlar.map((x) => (x.anahtar === yeni.anahtar ? yeni : x)) } : v));
      toast.success(t('uzmanAsistanlar.yonetim.kaydedildi'));
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  if (!veri) {
    return (
      <div className="py-20 text-center text-sm text-muted-foreground" data-uzman-asistan-yonetimi>
        {hata ?? <Loader2 className="mx-auto h-5 w-5 animate-spin" aria-hidden="true" />}
      </div>
    );
  }

  return (
    <div className="space-y-6" data-uzman-asistan-yonetimi>
      <div>
        <h3 className="flex items-center gap-2 text-xl font-semibold">
          <Bot className="h-5 w-5 text-purple-400" aria-hidden="true" /> {t('uzmanAsistanlar.baslik')}
        </h3>
        <p className="mt-1 text-sm text-muted-foreground">{t('uzmanAsistanlar.yonetim.aciklama')}</p>
      </div>

      <AyarKarti
        ayarlar={veri.ayarlar}
        onKaydet={(a) => setVeri((v) => (v ? { ...v, ayarlar: a } : v))}
      />

      <div className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-4 sm:p-6">
        <h4 className="mb-3 font-semibold">{t('uzmanAsistanlar.yonetim.liste', { sayi: veri.asistanlar.length })}</h4>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm" data-asistan-tablosu>
            <thead>
              <tr className="border-b border-white/10 text-start text-xs text-muted-foreground">
                <th className="py-2 pe-3 text-start font-medium">{t('uzmanAsistanlar.yonetim.ad')}</th>
                <th className="py-2 pe-3 text-start font-medium">{t('uzmanAsistanlar.yonetim.kategori')}</th>
                <th className="py-2 pe-3 text-start font-medium">{t('uzmanAsistanlar.yonetim.sira')}</th>
                <th className="py-2 pe-3 text-start font-medium">{t('uzmanAsistanlar.yonetim.aktif')}</th>
                <th className="py-2 text-end font-medium" />
              </tr>
            </thead>
            <tbody>
              {veri.asistanlar.map((a) => (
                <tr key={a.anahtar} className="border-b border-white/5" data-yonetim-asistan={a.anahtar}>
                  <td className="py-2 pe-3">
                    <span className="font-medium">{a.ad}</span>
                    <span className="block font-mono text-[11px] text-muted-foreground" dir="ltr">
                      {a.anahtar}
                    </span>
                  </td>
                  <td className="py-2 pe-3 text-muted-foreground">{kategoriAdi(a.kategori)}</td>
                  <td className="py-2 pe-3">
                    <Input
                      type="number"
                      min={0}
                      defaultValue={a.sira}
                      className={`${alanSinifi} h-8 w-20`}
                      aria-label={t('uzmanAsistanlar.yonetim.sira')}
                      onBlur={(e) => {
                        const sira = Number(e.target.value);
                        if (Number.isInteger(sira) && sira >= 0 && sira !== a.sira) void yama(a, { sira });
                      }}
                    />
                  </td>
                  <td className="py-2 pe-3">
                    <label className="inline-flex cursor-pointer items-center gap-2 text-xs">
                      <input
                        type="checkbox"
                        className="h-4 w-4 accent-purple-500"
                        checked={a.aktif}
                        onChange={(e) => void yama(a, { aktif: e.target.checked })}
                        data-aktif-anahtari={a.anahtar}
                      />
                      {a.aktif ? t('uzmanAsistanlar.yonetim.acik') : t('uzmanAsistanlar.yonetim.kapali')}
                    </label>
                  </td>
                  <td className="py-2 text-end">
                    <div className="inline-flex gap-1">
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        className="h-8 !bg-transparent border-white/20 text-xs"
                        onClick={() => setDeneme(a)}
                        data-dene={a.anahtar}
                      >
                        <Play className="me-1 h-3.5 w-3.5" aria-hidden="true" /> {t('uzmanAsistanlar.yonetim.dene')}
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        className="h-8 !bg-transparent border-white/20 text-xs"
                        onClick={() => setDuzenlenen(taslakYap(a))}
                        data-duzenle={a.anahtar}
                      >
                        <Pencil className="me-1 h-3.5 w-3.5" aria-hidden="true" /> {t('uzmanAsistanlar.yonetim.duzenle')}
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs text-muted-foreground">{t('uzmanAsistanlar.yonetim.modulNotu')}</p>
      </div>

      {kullanim && <KullanimKarti kullanim={kullanim} adlar={veri.asistanlar} />}

      <div className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-4 text-xs text-muted-foreground sm:p-6" data-kaynak-bildirimi>
        <p>
          {t('uzmanAsistanlar.atif', { ad: veri.kaynak.ad, lisans: veri.kaynak.lisans })}{' '}
          {veri.kaynak.depo && (
            <a href={veri.kaynak.depo} target="_blank" rel="noopener noreferrer" className="underline" dir="ltr">
              {veri.kaynak.depo}
            </a>
          )}
          {veri.kaynak.commit && <span dir="ltr"> @ {veri.kaynak.commit.slice(0, 10)}</span>}
        </p>
        {veri.kaynak.lisans_metni && (
          <details className="mt-2">
            <summary className="cursor-pointer">{t('uzmanAsistanlar.lisans')}</summary>
            <pre className="mt-2 whitespace-pre-wrap font-mono text-[11px]" dir="ltr">
              {veri.kaynak.lisans_metni}
            </pre>
          </details>
        )}
      </div>

      {duzenlenen && (
        <DuzenlemeFormu
          taslak={duzenlenen}
          kategoriler={veri.kategoriler.map((k) => ({ anahtar: k.anahtar, ad: kategoriAdi(k.anahtar) }))}
          onKapat={() => setDuzenlenen(null)}
          onKaydedildi={(yeni) => {
            setVeri((v) => (v ? { ...v, asistanlar: v.asistanlar.map((x) => (x.anahtar === yeni.anahtar ? yeni : x)) } : v));
            setDuzenlenen(null);
          }}
        />
      )}
      {deneme && <DenemeKutusu asistan={deneme} onKapat={() => setDeneme(null)} />}
    </div>
  );
}

function AyarKarti({ ayarlar, onKaydet }: { ayarlar: AsistanAyarlari; onKaydet: (a: AsistanAyarlari) => void }) {
  const { t } = useTranslation();
  const [form, setForm] = useState(ayarlar);
  const [kaydediliyor, setKaydediliyor] = useState(false);
  useEffect(() => setForm(ayarlar), [ayarlar]);

  const kaydet = async () => {
    setKaydediliyor(true);
    try {
      const yeni = await ayarlariKaydet({
        asistan_model: form.asistan_model.trim(),
        asistan_max_tokens: Number(form.asistan_max_tokens),
        asistan_gunluk_sinir: Number(form.asistan_gunluk_sinir),
        asistan_mesaj_kredi: Number(form.asistan_mesaj_kredi),
        ai_acik_gunluk_butce: Number(form.ai_acik_gunluk_butce),
        ai_acik_model: form.ai_acik_model.trim(),
      });
      onKaydet(yeni);
      toast.success(t('uzmanAsistanlar.yonetim.kaydedildi'));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setKaydediliyor(false);
    }
  };

  const sayi = (alan: keyof AsistanAyarlari, adim = 1) => (
    <Input
      id={`ayar-${alan}`}
      type="number"
      min={0}
      step={adim}
      className={alanSinifi}
      value={String(form[alan] ?? '')}
      onChange={(e) => setForm({ ...form, [alan]: e.target.value as unknown as number })}
      data-ayar={alan}
    />
  );

  return (
    <div className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-4 sm:p-6" data-asistan-ayarlari>
      <h4 className="mb-4 font-semibold">{t('uzmanAsistanlar.yonetim.ayarlar')}</h4>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div>
          <Label className={etiketSinifi} htmlFor="ayar-asistan_model">
            {t('uzmanAsistanlar.yonetim.model')}
          </Label>
          <Input
            id="ayar-asistan_model"
            dir="ltr"
            className={`${alanSinifi} font-mono text-xs`}
            placeholder={ayarlar.varsayilan_model}
            value={form.asistan_model}
            onChange={(e) => setForm({ ...form, asistan_model: e.target.value })}
            data-ayar="asistan_model"
          />
        </div>
        <div>
          <Label className={etiketSinifi} htmlFor="ayar-asistan_max_tokens">
            {t('uzmanAsistanlar.yonetim.maxTokens')}
          </Label>
          {sayi('asistan_max_tokens', 50)}
        </div>
        <div>
          <Label className={etiketSinifi} htmlFor="ayar-asistan_gunluk_sinir">
            {t('uzmanAsistanlar.yonetim.gunlukSinir')}
          </Label>
          {sayi('asistan_gunluk_sinir')}
        </div>
        <div>
          <Label className={etiketSinifi} htmlFor="ayar-asistan_mesaj_kredi">
            {t('uzmanAsistanlar.yonetim.mesajKredi')}
          </Label>
          {sayi('asistan_mesaj_kredi', 0.25)}
        </div>
        <div>
          <Label className={etiketSinifi} htmlFor="ayar-ai_acik_gunluk_butce">
            {t('uzmanAsistanlar.yonetim.acikButce')}
          </Label>
          {sayi('ai_acik_gunluk_butce', 50)}
        </div>
        <div>
          <Label className={etiketSinifi} htmlFor="ayar-ai_acik_model">
            {t('uzmanAsistanlar.yonetim.acikModel')}
          </Label>
          <Input
            id="ayar-ai_acik_model"
            dir="ltr"
            className={`${alanSinifi} font-mono text-xs`}
            placeholder={ayarlar.varsayilan_model}
            value={form.ai_acik_model}
            onChange={(e) => setForm({ ...form, ai_acik_model: e.target.value })}
            data-ayar="ai_acik_model"
          />
        </div>
      </div>
      <p className="mt-3 text-[11px] text-muted-foreground">{t('uzmanAsistanlar.yonetim.ayarIpucu')}</p>
      <div className="mt-4 flex justify-end">
        <Button
          type="button"
          onClick={() => void kaydet()}
          disabled={kaydediliyor}
          className="border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white"
          data-testid="ayarlari-kaydet"
        >
          {kaydediliyor ? <Loader2 className="me-1 h-4 w-4 animate-spin" aria-hidden="true" /> : <Save className="me-1 h-4 w-4" aria-hidden="true" />}
          {t('uzmanAsistanlar.yonetim.kaydet')}
        </Button>
      </div>
    </div>
  );
}

function KullanimKarti({ kullanim, adlar }: { kullanim: KullanimOzeti; adlar: YonetimAsistani[] }) {
  const { t, i18n } = useTranslation();
  const ad = (anahtar: string) => adlar.find((a) => a.anahtar === anahtar)?.ad || anahtar;
  const sayi = (n: number) => n.toLocaleString(i18n.language);
  return (
    <div className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-4 sm:p-6" data-kullanim-ozeti>
      <h4 className="mb-1 font-semibold">{t('uzmanAsistanlar.yonetim.kullanim', { gun: kullanim.gun })}</h4>
      <p className="mb-4 text-xs text-muted-foreground">
        {t('uzmanAsistanlar.yonetim.toplam', {
          mesaj: sayi(kullanim.toplam.asistan_mesaji),
          giris: sayi(kullanim.toplam.token_giris),
          cikis: sayi(kullanim.toplam.token_cikis),
        })}
      </p>
      {kullanim.hesaplar.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('uzmanAsistanlar.yonetim.kullanimYok')}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-sm">
            <thead>
              <tr className="border-b border-white/10 text-xs text-muted-foreground">
                <th className="py-2 pe-3 text-start font-medium">{t('uzmanAsistanlar.yonetim.hesap')}</th>
                <th className="py-2 pe-3 text-end font-medium">{t('uzmanAsistanlar.yonetim.soru')}</th>
                <th className="py-2 pe-3 text-end font-medium">{t('uzmanAsistanlar.yonetim.yanit')}</th>
                <th className="py-2 pe-3 text-end font-medium">{t('uzmanAsistanlar.yonetim.jeton')}</th>
                <th className="py-2 text-end font-medium">{t('uzmanAsistanlar.yonetim.son')}</th>
              </tr>
            </thead>
            <tbody>
              {kullanim.hesaplar.map((h) => (
                <tr key={h.hesap_email} className="border-b border-white/5" data-kullanim-hesap={h.hesap_email}>
                  <td className="py-2 pe-3" dir="ltr">
                    {h.hesap_email}
                  </td>
                  <td className="py-2 pe-3 text-end">{sayi(h.kullanici_mesaji)}</td>
                  <td className="py-2 pe-3 text-end">{sayi(h.asistan_mesaji)}</td>
                  <td className="py-2 pe-3 text-end" dir="ltr">
                    {sayi(h.token_giris)} / {sayi(h.token_cikis)}
                  </td>
                  <td className="py-2 text-end text-xs text-muted-foreground">
                    {h.son_mesaj_at ? new Date(h.son_mesaj_at).toLocaleDateString(i18n.language) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {kullanim.asistanlar.length > 0 && (
        <p className="mt-3 text-xs text-muted-foreground">
          {t('uzmanAsistanlar.yonetim.enCok')}:{' '}
          {kullanim.asistanlar
            .slice(0, 5)
            .map((a) => `${ad(a.anahtar)} (${sayi(a.asistan_mesaji)})`)
            .join(' · ')}
        </p>
      )}
      {kullanim.gunluk.length > 0 && (
        <details className="mt-3 text-xs text-muted-foreground">
          <summary className="cursor-pointer">{t('uzmanAsistanlar.yonetim.gunlukSayac')}</summary>
          <ul className="mt-2 space-y-0.5 font-mono" dir="ltr">
            {kullanim.gunluk.map((g) => (
              <li key={`${g.gun}-${g.kapsam}`}>
                {g.gun} · {t(`uzmanAsistanlar.yonetim.kapsam.${g.kapsam}`, { defaultValue: g.kapsam })}: {sayi(g.istek)} ·{' '}
                {sayi(g.token_giris)}/{sayi(g.token_cikis)}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function DuzenlemeFormu({
  taslak,
  kategoriler,
  onKapat,
  onKaydedildi,
}: {
  taslak: Taslak;
  kategoriler: { anahtar: string; ad: string }[];
  onKapat: () => void;
  onKaydedildi: (a: YonetimAsistani) => void;
}) {
  const { t } = useTranslation();
  const [form, setForm] = useState(taslak);
  const [formDili, setFormDili] = useState<FormDili>('tr');
  const [kaydediliyor, setKaydediliyor] = useState(false);
  const cevirili = useMemo(
    () => CEVIRI_DILLERI.filter((d) => form.ceviriler[d].ad || form.ceviriler[d].aciklama).length,
    [form.ceviriler]
  );

  useEffect(() => {
    const kapat = (e: KeyboardEvent) => e.key === 'Escape' && onKapat();
    window.addEventListener('keydown', kapat);
    return () => window.removeEventListener('keydown', kapat);
  }, [onKapat]);

  const kaydet = async () => {
    setKaydediliyor(true);
    try {
      const ceviriler: YonetimAsistani['ceviriler'] = {};
      for (const d of CEVIRI_DILLERI) {
        const c = form.ceviriler[d];
        ceviriler[d] = { ad: c.ad.trim(), aciklama: c.aciklama.trim(), ornek_sorular: satirlar(c.sorular) };
      }
      const yeni = await asistanGuncelle(form.anahtar, {
        ad: form.ad,
        aciklama: form.aciklama,
        ornek_sorular: satirlar(form.sorular),
        kategori: form.kategori,
        sistem_istemi: form.sistem_istemi,
        ceviriler,
      });
      toast.success(t('uzmanAsistanlar.yonetim.kaydedildi'));
      onKaydedildi(yeni);
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setKaydediliyor(false);
    }
  };

  const ceviriYaz = (alan: 'ad' | 'aciklama' | 'sorular', deger: string) => {
    if (formDili === 'tr') return;
    const d = formDili;
    setForm((f) => ({ ...f, ceviriler: { ...f.ceviriler, [d]: { ...f.ceviriler[d], [alan]: deger } } }));
  };
  const deger = (alan: 'ad' | 'aciklama' | 'sorular') => (formDili === 'tr' ? form[alan] : form.ceviriler[formDili][alan]);
  const yaz = (alan: 'ad' | 'aciklama' | 'sorular', d: string) =>
    formDili === 'tr' ? setForm((f) => ({ ...f, [alan]: d })) : ceviriYaz(alan, d);

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-background/80 p-4 backdrop-blur-sm">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="asistan-form-baslik"
        className="relative mx-auto my-8 max-w-3xl rounded-2xl border border-white/10 bg-background p-6 shadow-2xl"
        data-asistan-formu={form.anahtar}
      >
        <button
          type="button"
          className="absolute end-4 top-4 rounded-lg p-2 hover:bg-white/5"
          onClick={onKapat}
          aria-label={t('uzmanAsistanlar.yonetim.kapat')}
        >
          <X className="h-4 w-4" />
        </button>
        <h3 id="asistan-form-baslik" className="mb-1 text-2xl font-bold">
          {t('uzmanAsistanlar.yonetim.duzenleBaslik')}
        </h3>
        <p className="mb-5 font-mono text-xs text-muted-foreground" dir="ltr">
          {form.anahtar}
        </p>

        <div className="mb-5 flex flex-wrap items-center gap-1.5" role="group" aria-label={t('marketplaceCeviri.dilSecimi', 'Düzenlenen dil')}>
          {(['tr', ...CEVIRI_DILLERI] as FormDili[]).map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => setFormDili(d)}
              aria-pressed={formDili === d}
              data-dil={d}
              className={`rounded-md px-2.5 py-1 text-xs font-semibold uppercase ${
                formDili === d ? 'bg-primary text-background' : 'border border-white/10 text-muted-foreground hover:text-foreground'
              }`}
            >
              {d}
            </button>
          ))}
          <span className="ms-2 text-[11px] text-muted-foreground">
            {formDili !== 'tr'
              ? t('marketplaceCeviri.ipucu', 'Boş bırakılan alan sitede Türkçe görünür. Soluk yazı Türkçe değerdir.')
              : t('marketplaceCeviri.durum', 'çeviri {{sayi}}/{{toplam}}', { sayi: cevirili, toplam: CEVIRI_DILLERI.length })}
          </span>
        </div>

        <div className="space-y-4" dir={formDili === 'ar' ? 'rtl' : undefined}>
          <div>
            <Label className={etiketSinifi} htmlFor="asistan-ad">
              {t('uzmanAsistanlar.yonetim.ad')} ({formDili.toUpperCase()})
            </Label>
            <Input
              id="asistan-ad"
              className={`${alanSinifi} placeholder:text-white/30`}
              placeholder={formDili === 'tr' ? '' : form.ad}
              value={deger('ad')}
              maxLength={120}
              onChange={(e) => yaz('ad', e.target.value)}
              data-alan="ad"
            />
          </div>
          <div>
            <Label className={etiketSinifi} htmlFor="asistan-aciklama">
              {t('uzmanAsistanlar.yonetim.aciklamaAlani')} ({formDili.toUpperCase()})
            </Label>
            <Textarea
              id="asistan-aciklama"
              rows={2}
              maxLength={600}
              className={`${alanSinifi} placeholder:text-white/30`}
              placeholder={formDili === 'tr' ? '' : form.aciklama}
              value={deger('aciklama')}
              onChange={(e) => yaz('aciklama', e.target.value)}
            />
          </div>
          <div>
            <Label className={etiketSinifi} htmlFor="asistan-sorular">
              {t('uzmanAsistanlar.yonetim.ornekSorular')} ({formDili.toUpperCase()})
            </Label>
            <Textarea
              id="asistan-sorular"
              rows={3}
              className={`${alanSinifi} placeholder:text-white/30`}
              placeholder={formDili === 'tr' ? '' : form.sorular}
              value={deger('sorular')}
              onChange={(e) => yaz('sorular', e.target.value)}
            />
            <p className="mt-1 text-[11px] text-muted-foreground">{t('uzmanAsistanlar.yonetim.satirBasina')}</p>
          </div>
        </div>

        {formDili === 'tr' && (
          <div className="mt-4 space-y-4">
            <div>
              <Label className={etiketSinifi} htmlFor="asistan-kategori">
                {t('uzmanAsistanlar.yonetim.kategori')}
              </Label>
              <select
                id="asistan-kategori"
                value={form.kategori}
                onChange={(e) => setForm({ ...form, kategori: e.target.value })}
                className="h-10 w-full rounded-md border border-white/10 bg-white/5 px-3 text-sm"
              >
                {kategoriler.map((k) => (
                  <option key={k.anahtar} value={k.anahtar} className="bg-background">
                    {k.ad}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <Label className={etiketSinifi} htmlFor="asistan-istem">
                {t('uzmanAsistanlar.yonetim.sistemIstemi')}
              </Label>
              <Textarea
                id="asistan-istem"
                rows={12}
                dir="ltr"
                maxLength={20000}
                className={`${alanSinifi} font-mono text-xs`}
                value={form.sistem_istemi}
                onChange={(e) => setForm({ ...form, sistem_istemi: e.target.value })}
                data-alan="sistem_istemi"
              />
              <p className="mt-1 text-[11px] text-muted-foreground">{t('uzmanAsistanlar.yonetim.istemIpucu')}</p>
            </div>
          </div>
        )}

        <div className="mt-6 flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onKapat}>
            {t('uzmanAsistanlar.yonetim.vazgec')}
          </Button>
          <Button
            type="button"
            onClick={() => void kaydet()}
            disabled={kaydediliyor || !form.ad.trim() || !form.sistem_istemi.trim()}
            className="border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white"
            data-testid="asistan-kaydet"
          >
            {kaydediliyor && <Loader2 className="me-1 h-4 w-4 animate-spin" aria-hidden="true" />}
            {t('uzmanAsistanlar.yonetim.kaydet')}
          </Button>
        </div>
      </div>
    </div>
  );
}

function DenemeKutusu({ asistan, onKapat }: { asistan: YonetimAsistani; onKapat: () => void }) {
  const { t } = useTranslation();
  const [soru, setSoru] = useState(asistan.ornek_sorular[0] || '');
  const [istem, setIstem] = useState(asistan.sistem_istemi);
  const [yanit, setYanit] = useState<{ icerik: string; model: string; token_giris?: number | null; token_cikis?: number | null } | null>(null);
  const [bekliyor, setBekliyor] = useState(false);

  useEffect(() => {
    const kapat = (e: KeyboardEvent) => e.key === 'Escape' && onKapat();
    window.addEventListener('keydown', kapat);
    return () => window.removeEventListener('keydown', kapat);
  }, [onKapat]);

  const dene = async () => {
    if (!soru.trim()) return;
    setBekliyor(true);
    setYanit(null);
    try {
      setYanit(await asistanDene(asistan.anahtar, soru.trim(), istem !== asistan.sistem_istemi ? istem : undefined));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setBekliyor(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-background/80 p-4 backdrop-blur-sm">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="asistan-dene-baslik"
        className="relative mx-auto my-8 max-w-3xl rounded-2xl border border-white/10 bg-background p-6 shadow-2xl"
        data-dene-kutusu={asistan.anahtar}
      >
        <button
          type="button"
          className="absolute end-4 top-4 rounded-lg p-2 hover:bg-white/5"
          onClick={onKapat}
          aria-label={t('uzmanAsistanlar.yonetim.kapat')}
        >
          <X className="h-4 w-4" />
        </button>
        <h3 id="asistan-dene-baslik" className="mb-1 text-xl font-bold">
          {t('uzmanAsistanlar.yonetim.denemeBaslik', { ad: asistan.ad })}
        </h3>
        <p className="mb-4 text-xs text-muted-foreground">{t('uzmanAsistanlar.yonetim.denemeNotu')}</p>
        <Label className={etiketSinifi} htmlFor="dene-soru">
          {t('uzmanAsistanlar.yonetim.soru')}
        </Label>
        <Textarea
          id="dene-soru"
          rows={3}
          maxLength={8000}
          className={alanSinifi}
          value={soru}
          onChange={(e) => setSoru(e.target.value)}
          dir="auto"
          data-testid="dene-soru"
        />
        <details className="mt-3">
          <summary className="cursor-pointer text-xs text-muted-foreground">{t('uzmanAsistanlar.yonetim.istemTaslagi')}</summary>
          <Textarea
            rows={8}
            dir="ltr"
            maxLength={20000}
            className={`${alanSinifi} mt-2 font-mono text-xs`}
            value={istem}
            onChange={(e) => setIstem(e.target.value)}
            aria-label={t('uzmanAsistanlar.yonetim.sistemIstemi')}
          />
        </details>
        <div className="mt-4 flex justify-end">
          <Button
            type="button"
            onClick={() => void dene()}
            disabled={bekliyor || !soru.trim()}
            className="border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white"
            data-testid="dene-gonder"
          >
            {bekliyor ? <Loader2 className="me-1 h-4 w-4 animate-spin" aria-hidden="true" /> : <Play className="me-1 h-4 w-4" aria-hidden="true" />}
            {t('uzmanAsistanlar.yonetim.dene')}
          </Button>
        </div>
        {yanit && (
          <div className="mt-4 rounded-xl border border-white/10 bg-white/[0.04] p-4 text-sm" data-dene-yaniti>
            <GuvenliMarkdown metin={yanit.icerik} />
            <p className="mt-3 font-mono text-[10px] text-muted-foreground" dir="ltr">
              {yanit.model} · {yanit.token_giris ?? '?'} / {yanit.token_cikis ?? '?'}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
