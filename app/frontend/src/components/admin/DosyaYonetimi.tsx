import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import {
  Copy,
  Database,
  Download,
  Eye,
  EyeOff,
  FileText,
  FolderOpen,
  Link2,
  Loader2,
  RefreshCw,
  Share2,
  Trash2,
  Upload,
  X,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { modulMusterileriGetir, type ModulMusterisi } from '@/lib/moduller';
import {
  DosyaHatasi,
  adresiIndir,
  belgeTalebiAc,
  belgeTalebiIptal,
  belgeTalepleri,
  boyutBicimle,
  boyutSiniriKaydet,
  depoBilgisi,
  dosyaSil,
  klasorKaydet,
  paylasimIptal,
  paylasimOlustur,
  paylasimlar,
  tarihBicimle,
  yoneticiDosyalari,
  yoneticiIndirmeAdresi,
  yoneticiYukle,
  type BelgeTalebi,
  type DepoBilgisi,
  type Dosya,
  type Gorunurluk,
  type Klasor,
  type Paylasim,
} from '@/lib/dosyalar';

/**
 * Yönetici paneli › Dosyalar (Faz 2C).
 *
 * Bir müşteri seçilir: klasörleri (müşteri görür / yalnız ekip), dosyaları,
 * yükleme, imzalı indirme, süreli + parolalı + sayılı paylaşım bağlantısı ve
 * müşteriden belge talebi. Depo türü (R2 / veritabanı) ve boyut sınırı üstte.
 */

const KART = 'cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6';
const SECIM = 'h-10 w-full rounded-md border border-white/10 bg-white/5 px-3 text-sm text-foreground';
const EPOSTA = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function DosyaYonetimi() {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;

  const [depo, setDepo] = useState<DepoBilgisi | null>(null);
  const [sinirTaslak, setSinirTaslak] = useState('');
  const [musteriler, setMusteriler] = useState<ModulMusterisi[]>([]);
  const [arama, setArama] = useState('');
  const [secili, setSecili] = useState<string | null>(null);

  const [dosyalar, setDosyalar] = useState<Dosya[]>([]);
  const [klasorler, setKlasorler] = useState<Klasor[]>([]);
  const [talepler, setTalepler] = useState<BelgeTalebi[]>([]);
  const [yukleniyor, setYukleniyor] = useState(false);

  const [secilenDosya, setSecilenDosya] = useState<File | null>(null);
  const [klasor, setKlasor] = useState('Genel');
  const [gorunurluk, setGorunurluk] = useState<Gorunurluk>('musteri');
  const [gonderiliyor, setGonderiliyor] = useState(false);
  // Yükleme sonrası dosya seçicisini boşaltmak için yeniden bağlama anahtarı.
  const [girdiAnahtari, setGirdiAnahtari] = useState(0);

  const [paylasilan, setPaylasilan] = useState<Dosya | null>(null);

  const [talepForm, setTalepForm] = useState({ baslik: '', aciklama: '', son_tarih: '', turler: 'pdf,jpg,png' });

  const hata = useCallback(
    (h: unknown) => {
      const kod = h instanceof DosyaHatasi ? h.kod : 'genel';
      const ek = h instanceof DosyaHatasi ? h.ek : {};
      toast.error(t(`dosyalar.hata.${kod}`, { defaultValue: t('dosyalar.hata.genel'), ...ek }));
    },
    [t]
  );

  useEffect(() => {
    depoBilgisi()
      .then((d) => {
        setDepo(d);
        setSinirTaslak(String(d.boyut_siniri_mb));
      })
      .catch(() => setDepo(null));
    modulMusterileriGetir()
      .then(setMusteriler)
      .catch(() => setMusteriler([]));
  }, []);

  const yukle = useCallback(
    async (eposta: string) => {
      setYukleniyor(true);
      try {
        const [d, bt] = await Promise.all([yoneticiDosyalari(eposta), belgeTalepleri(eposta)]);
        setDosyalar(d.dosyalar);
        setKlasorler(d.klasorler);
        setTalepler(bt);
      } catch (h) {
        hata(h);
      } finally {
        setYukleniyor(false);
      }
    },
    [hata]
  );

  useEffect(() => {
    if (secili) void yukle(secili);
  }, [secili, yukle]);

  const aramaTemiz = arama.trim().toLowerCase();
  const suzulmus = useMemo(
    () =>
      (aramaTemiz
        ? musteriler.filter((m) => m.eposta.includes(aramaTemiz) || (m.ad || '').toLowerCase().includes(aramaTemiz))
        : musteriler
      ).slice(0, 30),
    [musteriler, aramaTemiz]
  );
  const yeniEposta = EPOSTA.test(aramaTemiz) && !musteriler.some((m) => m.eposta === aramaTemiz) ? aramaTemiz : null;

  const klasorGrubu = useMemo(() => {
    const gruplar = new Map<string, Dosya[]>();
    for (const d of dosyalar) {
      if (!gruplar.has(d.klasor)) gruplar.set(d.klasor, []);
      gruplar.get(d.klasor)!.push(d);
    }
    for (const k of klasorler) if (!gruplar.has(k.ad)) gruplar.set(k.ad, []);
    return [...gruplar.entries()].sort(([a], [b]) => a.localeCompare(b, dil));
  }, [dosyalar, klasorler, dil]);

  const klasorYetkisi = (ad: string): Gorunurluk => klasorler.find((k) => k.ad === ad)?.gorunurluk ?? 'ekip';

  const sinirKaydet = async () => {
    const mb = Number(sinirTaslak);
    if (!Number.isInteger(mb) || mb < 1 || mb > 100) {
      toast.error(t('dosyalar.hata.gecersiz_sinir'));
      return;
    }
    try {
      await boyutSiniriKaydet(mb);
      setDepo((d) => (d ? { ...d, boyut_siniri_mb: mb } : d));
      toast.success(t('dosyalar.yonetim.sinirKaydedildi', { sayi: mb }));
    } catch (h) {
      hata(h);
    }
  };

  const gonder = async (e: FormEvent) => {
    e.preventDefault();
    if (!secili || !secilenDosya) return;
    setGonderiliyor(true);
    try {
      await yoneticiYukle(secili, secilenDosya, klasor.trim() || 'Genel', gorunurluk);
      toast.success(t('dosyalar.yuklendi', { ad: secilenDosya.name }));
      setSecilenDosya(null);
      setGirdiAnahtari((n) => n + 1);
      await yukle(secili);
    } catch (h) {
      hata(h);
    } finally {
      setGonderiliyor(false);
    }
  };

  const indir = async (d: Dosya) => {
    try {
      adresiIndir((await yoneticiIndirmeAdresi(d.id)).adres);
    } catch (h) {
      hata(h);
    }
  };

  const sil = async (d: Dosya) => {
    if (!window.confirm(t('dosyalar.yonetim.silOnay', { ad: d.ad }))) return;
    try {
      await dosyaSil(d.id);
      toast.success(t('dosyalar.yonetim.silindi'));
      if (secili) await yukle(secili);
    } catch (h) {
      hata(h);
    }
  };

  const yetkiDegistir = async (ad: string, yeni: Gorunurluk) => {
    if (!secili) return;
    try {
      await klasorKaydet(secili, ad, yeni);
      toast.success(t('dosyalar.yonetim.yetkiDegisti'));
      await yukle(secili);
    } catch (h) {
      hata(h);
    }
  };

  const talepGonder = async (e: FormEvent) => {
    e.preventDefault();
    if (!secili || !talepForm.baslik.trim()) return;
    try {
      await belgeTalebiAc({
        client_email: secili,
        baslik: talepForm.baslik.trim(),
        aciklama: talepForm.aciklama.trim() || undefined,
        son_tarih: talepForm.son_tarih || undefined,
        kabul_turleri: talepForm.turler
          .split(',')
          .map((x) => x.trim())
          .filter(Boolean),
      });
      toast.success(t('dosyalar.talep.gonderildi'));
      setTalepForm({ baslik: '', aciklama: '', son_tarih: '', turler: talepForm.turler });
      await yukle(secili);
    } catch (h) {
      hata(h);
    }
  };

  return (
    <div className="space-y-6" data-testid="dosya-yonetimi">
      <div className={KART}>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="flex items-center gap-2 text-xl font-semibold">
              <FolderOpen className="h-5 w-5 text-purple-300" aria-hidden="true" />
              {t('dosyalar.yonetim.baslik')}
            </h2>
            <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{t('dosyalar.yonetim.aciklama')}</p>
          </div>
          {depo && (
            <div className="min-w-[240px] rounded-xl border border-white/10 bg-white/[0.02] p-3 text-xs" data-testid="depo-bilgisi">
              <p className="flex items-center gap-2 font-medium">
                <Database className="h-4 w-4 text-cyan-300" aria-hidden="true" />
                {t(`dosyalar.depo.${depo.tur}`)}
              </p>
              {depo.oneri && <p className="mt-1 text-amber-200/90">{t('dosyalar.depo.oneri')}</p>}
              <label className="mt-3 flex items-center gap-2">
                <span className="text-muted-foreground">{t('dosyalar.yonetim.boyutSiniri')}</span>
                <Input
                  value={sinirTaslak}
                  onChange={(e) => setSinirTaslak(e.target.value)}
                  inputMode="numeric"
                  className="h-8 w-16 bg-white/5 px-2 text-xs"
                  aria-label={t('dosyalar.yonetim.boyutSiniri')}
                />
                <span>MB</span>
                <Button size="sm" variant="outline" className="h-8 !bg-transparent px-2 text-xs" onClick={() => void sinirKaydet()}>
                  {t('dosyalar.kaydet')}
                </Button>
              </label>
            </div>
          )}
        </div>

        <div className="mt-5">
          <label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground" htmlFor="dosya-musteri-ara">
            {t('dosyalar.yonetim.musteriSec')}
          </label>
          <Input
            id="dosya-musteri-ara"
            value={arama}
            onChange={(e) => setArama(e.target.value)}
            placeholder={t('dosyalar.yonetim.musteriAra')}
            className="bg-white/5"
            data-testid="dosya-musteri-ara"
            onKeyDown={(e) => {
              // Tam bir e-posta yazıp Enter: listede olsun olmasın o müşteriyi seç.
              if (e.key === 'Enter' && EPOSTA.test(aramaTemiz)) setSecili(aramaTemiz);
            }}
          />
          <div className="mt-2 flex flex-wrap gap-2">
            {yeniEposta && (
              <Button size="sm" variant="outline" className="!bg-transparent" onClick={() => setSecili(yeniEposta)} data-testid="dosya-musteri-yeni">
                {yeniEposta}
              </Button>
            )}
            {suzulmus.map((m) => (
              <button
                key={m.eposta}
                type="button"
                onClick={() => setSecili(m.eposta)}
                aria-pressed={secili === m.eposta}
                className={`max-w-full truncate rounded-full border px-3 py-1 text-xs transition-colors ${
                  secili === m.eposta
                    ? 'border-purple-400/60 bg-purple-500/20 text-white'
                    : 'border-white/10 bg-white/[0.03] text-muted-foreground hover:border-white/25'
                }`}
              >
                {m.ad ? `${m.ad} · ${m.eposta}` : m.eposta}
              </button>
            ))}
          </div>
        </div>
      </div>

      {!secili ? (
        <p className="text-sm text-muted-foreground">{t('dosyalar.yonetim.secimYok')}</p>
      ) : (
        <>
          <div className={KART}>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
              <h3 className="break-all font-semibold" data-testid="dosya-secili">
                {secili}
              </h3>
              <Button size="sm" variant="ghost" className="gap-2" onClick={() => void yukle(secili)}>
                <RefreshCw className={`h-4 w-4 ${yukleniyor ? 'animate-spin' : ''}`} aria-hidden="true" />
                {t('dosyalar.yenile')}
              </Button>
            </div>

            <form onSubmit={gonder} className="grid gap-3 rounded-xl border border-white/10 bg-white/[0.02] p-4 md:grid-cols-[1fr_160px_170px_auto]">
              <input
                key={girdiAnahtari}
                id="dosya-sec-yonetici"
                type="file"
                onChange={(e) => setSecilenDosya(e.target.files?.[0] ?? null)}
                className="min-w-0 text-sm file:mr-3 file:rounded-md file:border-0 file:bg-white/10 file:px-3 file:py-1.5 file:text-sm file:text-foreground"
                aria-label={t('dosyalar.dosyaSec')}
                data-testid="yonetici-dosya-input"
              />
              <Input
                value={klasor}
                onChange={(e) => setKlasor(e.target.value)}
                list="klasor-listesi"
                placeholder={t('dosyalar.klasor')}
                aria-label={t('dosyalar.klasor')}
                className="bg-white/5"
                data-testid="yonetici-klasor"
              />
              <datalist id="klasor-listesi">
                {klasorler.map((k) => (
                  <option key={k.ad} value={k.ad} />
                ))}
              </datalist>
              <select
                value={gorunurluk}
                onChange={(e) => setGorunurluk(e.target.value as Gorunurluk)}
                className={SECIM}
                aria-label={t('dosyalar.gorunurluk.baslik')}
              >
                <option value="musteri">{t('dosyalar.gorunurluk.musteri')}</option>
                <option value="ekip">{t('dosyalar.gorunurluk.ekip')}</option>
              </select>
              <Button type="submit" disabled={!secilenDosya || gonderiliyor} className="gap-2" data-testid="yonetici-yukle">
                {gonderiliyor ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
                {t('dosyalar.yukle')}
              </Button>
              <p className="text-xs text-muted-foreground md:col-span-4">
                {t('dosyalar.kurallar', { sayi: depo?.boyut_siniri_mb ?? 20, turler: (depo?.izinli_turler ?? []).join(', ') })}
              </p>
            </form>

            {yukleniyor && dosyalar.length === 0 ? (
              <div className="flex justify-center py-8">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : klasorGrubu.length === 0 ? (
              <p className="mt-5 text-sm text-muted-foreground">{t('dosyalar.bos')}</p>
            ) : (
              <div className="mt-5 space-y-4">
                {klasorGrubu.map(([ad, liste]) => (
                  <div key={ad} className="rounded-xl border border-white/10" data-testid={`klasor-${ad}`}>
                    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 px-4 py-2">
                      <p className="flex items-center gap-2 text-sm font-medium">
                        <FolderOpen className="h-4 w-4 text-amber-300" aria-hidden="true" /> {ad}
                        <span className="text-xs text-muted-foreground">({liste.length})</span>
                      </p>
                      <button
                        type="button"
                        onClick={() => void yetkiDegistir(ad, klasorYetkisi(ad) === 'musteri' ? 'ekip' : 'musteri')}
                        className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] ${
                          klasorYetkisi(ad) === 'musteri'
                            ? 'border-emerald-400/40 text-emerald-200'
                            : 'border-amber-400/40 text-amber-200'
                        }`}
                        title={t('dosyalar.yonetim.yetkiDegistir')}
                      >
                        {klasorYetkisi(ad) === 'musteri' ? <Eye className="h-3 w-3" /> : <EyeOff className="h-3 w-3" />}
                        {t(`dosyalar.gorunurluk.${klasorYetkisi(ad)}`)}
                      </button>
                    </div>
                    <ul className="divide-y divide-white/5">
                      {liste.map((d) => (
                        <li key={d.id} className="flex flex-wrap items-center gap-3 px-4 py-2 text-sm" data-testid={`dosya-${d.id}`}>
                          <FileText className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                          <span className="min-w-0 flex-1">
                            <span className="block break-words">{d.ad}</span>
                            <span className="block text-xs text-muted-foreground">
                              {boyutBicimle(d.boyut, dil)} · v{d.surum} · {tarihBicimle(d.created_at, dil)} ·{' '}
                              {t(`dosyalar.yukleyen.${d.yukleyen_rol === 'client' ? 'musteri' : 'ajans'}`)}
                            </span>
                          </span>
                          <span className="flex gap-1">
                            <Button size="sm" variant="ghost" onClick={() => void indir(d)} title={t('dosyalar.indir')} aria-label={t('dosyalar.indir')}>
                              <Download className="h-4 w-4" />
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => setPaylasilan(d)}
                              title={t('dosyalar.paylasim.baslik')}
                              aria-label={t('dosyalar.paylasim.baslik')}
                              data-testid={`paylas-${d.id}`}
                            >
                              <Share2 className="h-4 w-4" />
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              className="text-destructive hover:text-destructive"
                              onClick={() => void sil(d)}
                              title={t('dosyalar.yonetim.sil')}
                              aria-label={t('dosyalar.yonetim.sil')}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className={KART}>
            <h3 className="font-semibold">{t('dosyalar.talep.baslik')}</h3>
            <p className="mt-1 text-sm text-muted-foreground">{t('dosyalar.talep.aciklama')}</p>
            <form onSubmit={talepGonder} className="mt-4 grid gap-3 md:grid-cols-2">
              <Input
                value={talepForm.baslik}
                onChange={(e) => setTalepForm({ ...talepForm, baslik: e.target.value })}
                placeholder={t('dosyalar.talep.belgeAdi')}
                aria-label={t('dosyalar.talep.belgeAdi')}
                className="bg-white/5"
                data-testid="talep-baslik"
              />
              <div className="grid grid-cols-2 gap-3">
                <Input
                  type="date"
                  value={talepForm.son_tarih}
                  onChange={(e) => setTalepForm({ ...talepForm, son_tarih: e.target.value })}
                  aria-label={t('dosyalar.talep.sonTarih')}
                  className="bg-white/5"
                  data-testid="talep-son-tarih"
                />
                <Input
                  value={talepForm.turler}
                  onChange={(e) => setTalepForm({ ...talepForm, turler: e.target.value })}
                  aria-label={t('dosyalar.talep.turler')}
                  title={t('dosyalar.talep.turler')}
                  className="bg-white/5"
                />
              </div>
              <Textarea
                value={talepForm.aciklama}
                onChange={(e) => setTalepForm({ ...talepForm, aciklama: e.target.value })}
                placeholder={t('dosyalar.talep.aciklamaYer')}
                rows={2}
                className="bg-white/5 md:col-span-2"
              />
              <div className="md:col-span-2">
                <Button type="submit" disabled={!talepForm.baslik.trim()} data-testid="talep-gonder">
                  {t('dosyalar.talep.iste')}
                </Button>
              </div>
            </form>

            {talepler.length > 0 && (
              <ul className="mt-5 divide-y divide-white/5 rounded-xl border border-white/10">
                {talepler.map((bt) => (
                  <li key={bt.id} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm" data-testid={`belge-talebi-${bt.id}`}>
                    <span className="min-w-0 flex-1">
                      <span className="font-medium">{bt.baslik}</span>
                      <span className="block text-xs text-muted-foreground">
                        {bt.son_tarih ? `${t('dosyalar.talep.sonTarih')}: ${tarihBicimle(bt.son_tarih, dil)}` : t('dosyalar.talep.sonTarihYok')}
                        {bt.kabul_turleri.length ? ` · ${bt.kabul_turleri.join(', ')}` : ''}
                      </span>
                    </span>
                    <TalepRozeti talep={bt} />
                    {bt.dosya && (
                      <Button size="sm" variant="outline" className="gap-1 !bg-transparent" onClick={() => void indir(bt.dosya!)} data-testid={`talep-dosya-${bt.id}`}>
                        <Download className="h-3.5 w-3.5" /> {bt.dosya.ad}
                      </Button>
                    )}
                    {bt.durum === 'bekliyor' && (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-xs"
                        onClick={() =>
                          void belgeTalebiIptal(bt.id)
                            .then(() => yukle(secili))
                            .catch(hata)
                        }
                      >
                        {t('dosyalar.talep.iptalEt')}
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}

      {paylasilan && <PaylasimPenceresi dosya={paylasilan} kapat={() => setPaylasilan(null)} hata={hata} />}
    </div>
  );
}

export function TalepRozeti({ talep }: { talep: BelgeTalebi }) {
  const { t } = useTranslation();
  const gecikti = talep.durum === 'bekliyor' && talep.kalan_gun !== null && talep.kalan_gun < 0;
  const renk =
    talep.durum === 'teslim_edildi'
      ? 'bg-emerald-500/15 text-emerald-200'
      : talep.durum === 'iptal'
        ? 'bg-white/10 text-muted-foreground'
        : gecikti
          ? 'bg-red-500/15 text-red-200'
          : 'bg-amber-500/15 text-amber-200';
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-[11px] ${renk}`} data-durum={talep.durum}>
      {gecikti ? t('dosyalar.talep.durum.gecikti') : t(`dosyalar.talep.durum.${talep.durum}`)}
    </span>
  );
}

function PaylasimPenceresi({ dosya, kapat, hata }: { dosya: Dosya; kapat: () => void; hata: (h: unknown) => void }) {
  const { t, i18n } = useTranslation();
  const [gun, setGun] = useState('7');
  const [sifre, setSifre] = useState('');
  const [sinir, setSinir] = useState('');
  const [liste, setListe] = useState<Paylasim[]>([]);
  const [yeni, setYeni] = useState<Paylasim | null>(null);
  const [calisiyor, setCalisiyor] = useState(false);

  const listele = useCallback(() => {
    paylasimlar(dosya.id)
      .then(setListe)
      .catch(() => setListe([]));
  }, [dosya.id]);

  useEffect(listele, [listele]);

  const olustur = async (e: FormEvent) => {
    e.preventDefault();
    setCalisiyor(true);
    try {
      const p = await paylasimOlustur(dosya.id, {
        gun: Number(gun),
        sifre: sifre.trim() || undefined,
        indirme_siniri: sinir.trim() ? Number(sinir) : null,
      });
      setYeni(p);
      listele();
    } catch (h) {
      hata(h);
    } finally {
      setCalisiyor(false);
    }
  };

  const tamAdres = yeni?.yol ? `${window.location.origin}${yeni.yol}` : '';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="dialog" aria-modal="true" aria-labelledby="paylasim-baslik">
      <div className="cam-kart max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-white/10 bg-background p-6">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h3 id="paylasim-baslik" className="flex items-center gap-2 font-semibold">
              <Link2 className="h-4 w-4 text-purple-300" /> {t('dosyalar.paylasim.baslik')}
            </h3>
            <p className="mt-1 break-all text-xs text-muted-foreground">{dosya.ad}</p>
          </div>
          <Button size="sm" variant="ghost" onClick={kapat} aria-label={t('dosyalar.kapat')}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        <form onSubmit={olustur} className="grid gap-3 sm:grid-cols-3">
          <label className="text-xs text-muted-foreground">
            {t('dosyalar.paylasim.gun')}
            <select value={gun} onChange={(e) => setGun(e.target.value)} className={`${SECIM} mt-1`} data-testid="paylasim-gun">
              {[1, 3, 7, 14, 30].map((g) => (
                <option key={g} value={g}>
                  {t('dosyalar.paylasim.gunSecenek', { sayi: g })}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-muted-foreground">
            {t('dosyalar.paylasim.sifre')}
            <Input
              value={sifre}
              onChange={(e) => setSifre(e.target.value)}
              type="text"
              autoComplete="off"
              placeholder={t('dosyalar.paylasim.istegeBagli')}
              className="mt-1 bg-white/5"
              data-testid="paylasim-sifre"
            />
          </label>
          <label className="text-xs text-muted-foreground">
            {t('dosyalar.paylasim.sinir')}
            <Input
              value={sinir}
              onChange={(e) => setSinir(e.target.value)}
              inputMode="numeric"
              placeholder={t('dosyalar.paylasim.sinirsiz')}
              className="mt-1 bg-white/5"
              data-testid="paylasim-sinir"
            />
          </label>
          <div className="sm:col-span-3">
            <Button type="submit" disabled={calisiyor} className="gap-2" data-testid="paylasim-olustur">
              {calisiyor ? <Loader2 className="h-4 w-4 animate-spin" /> : <Share2 className="h-4 w-4" />}
              {t('dosyalar.paylasim.olustur')}
            </Button>
          </div>
        </form>

        {yeni && (
          <div className="mt-4 rounded-xl border border-emerald-400/30 bg-emerald-500/10 p-3 text-sm">
            <p className="text-emerald-100">{t('dosyalar.paylasim.hazir')}</p>
            <div className="mt-2 flex items-center gap-2">
              <code className="min-w-0 flex-1 break-all rounded bg-black/30 px-2 py-1 text-xs" data-testid="paylasim-adres">
                {tamAdres}
              </code>
              <Button
                size="sm"
                variant="outline"
                className="!bg-transparent"
                onClick={() => {
                  void navigator.clipboard?.writeText(tamAdres).then(
                    () => toast.success(t('dosyalar.paylasim.kopyalandi')),
                    () => undefined
                  );
                }}
                aria-label={t('dosyalar.paylasim.kopyala')}
              >
                <Copy className="h-4 w-4" />
              </Button>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">{t('dosyalar.paylasim.birKez')}</p>
          </div>
        )}

        {liste.length > 0 && (
          <ul className="mt-4 divide-y divide-white/5 rounded-xl border border-white/10 text-xs">
            {liste.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center gap-2 px-3 py-2">
                <span className="flex-1">
                  {t('dosyalar.paylasim.sonKullanma')}: {tarihBicimle(p.son_kullanma, i18n.language, true)}
                  {' · '}
                  {p.indirme_siniri ? `${p.indirme_sayisi}/${p.indirme_siniri}` : p.indirme_sayisi}
                  {p.sifreli ? ` · ${t('dosyalar.paylasim.sifreli')}` : ''}
                </span>
                <span className="text-muted-foreground">{t(`dosyalar.paylasim.durum.${p.durum}`)}</span>
                {p.durum === 'gecerli' && (
                  <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => void paylasimIptal(p.id).then(listele).catch(hata)}>
                    {t('dosyalar.paylasim.iptal')}
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
