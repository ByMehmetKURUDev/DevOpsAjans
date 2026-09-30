import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Check,
  Copy,
  ExternalLink,
  Loader2,
  Mail,
  Pencil,
  Plus,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { icerikTaslagiUret } from '@/lib/icerikAi';
import { hatirlatmaGonder } from '@/lib/icerikHatirlatma';
import {
  KANALLAR,
  KANAL_ADRESI,
  KANAL_SINIRI,
  gecikenler,
  girdiyeCevir,
  gonderiGuncelle,
  gonderiMetni,
  gonderiOlustur,
  gonderiSil,
  gonderileriGetir,
  isoyaCevir,
  type Gonderi,
  type Kanal,
} from '@/lib/icerikPlani';

/**
 * İçerik takvimi paneli.
 *
 * Bu ekran GÖNDERİ ATMIYOR, gönderi hazırlıyor. Akış: planla → AI
 * taslağı yaz → onayla → zamanı gelince "Kopyala ve aç" ile metni panoya
 * al, kanalın yazma ekranında yapıştır, paylaş, "Paylaşıldı" işaretle.
 *
 * Otomatik yayın neden yok: Instagram/Facebook/LinkedIn program
 * üzerinden gönderi için onaylı uygulama hesabı istiyor, X'in API'si
 * ücretli, ayrıca arka uç ücretsiz planda uykuya geçtiği için
 * zamanlanmış iş saatinde çalışmıyor. Çalışmayan bir "otomatik paylaş"
 * tuşu koymaktansa, elle adımı hızlandırmak daha dürüst.
 *
 * Hatırlatma e-postası da sözü verilmiyor: sunucuda e-posta sağlayıcısı
 * yapılandırılmamış. Onun yerine zamanı geçmiş gönderiler panelin en
 * üstünde duruyor.
 */

type Taslak = Partial<Gonderi> & { id?: number };

const BOS: Taslak = {
  title: '',
  channel: 'instagram',
  body: '',
  hashtags: '',
  image_url: '',
  link_url: '',
  scheduled_at: '',
  status: 'draft',
  campaign: '',
  notes: '',
};

const DURUM_RENGI: Record<string, string> = {
  draft: 'bg-white/10 text-muted-foreground',
  approved: 'bg-amber-500/15 text-amber-200',
  published: 'bg-primary/15 text-primary',
};

export default function IcerikPlani() {
  const { t } = useTranslation();
  const [liste, setListe] = useState<Gonderi[] | null>(null);
  const [duzenlenen, setDuzenlenen] = useState<Taslak | null>(null);
  const [kaydediliyor, setKaydediliyor] = useState(false);
  const [aiCalisiyor, setAiCalisiyor] = useState(false);
  const [aiYonlendirme, setAiYonlendirme] = useState('');
  const [hatirlatmaGidiyor, setHatirlatmaGidiyor] = useState(false);
  const [kanalSuzgeci, setKanalSuzgeci] = useState<string>('hepsi');

  const yukle = () => {
    void gonderileriGetir()
      .then(setListe)
      .catch(() => {
        setListe([]);
        toast.error(t('icerik.listeHatasi'));
      });
  };

  useEffect(yukle, []); // eslint-disable-line react-hooks/exhaustive-deps

  const geciken = useMemo(() => (liste ? gecikenler(liste) : []), [liste]);

  /**
   * Gecikenleri yöneticiye e-postayla yollar.
   *
   * Gönderim BAŞARISIZ olsa bile uç 200 dönüyor (kanal kapalı olabilir,
   * adres tanımlı olmayabilir). O yüzden "gitti" demeden önce durumu
   * okuyoruz; yoksa panel yalan söylemiş olur.
   */
  const hatirlat = async () => {
    setHatirlatmaGidiyor(true);
    try {
      const sonuc = await hatirlatmaGonder();
      if (sonuc.epostaGitti) {
        toast.success(t('icerik.hatirlatildi', { count: sonuc.aliciSayisi }));
      } else {
        toast.warning(
          t('icerik.hatirlatmaGitmedi', {
            ayrinti: sonuc.epostaAyrinti || sonuc.epostaDurumu,
          }),
        );
      }
    } catch {
      toast.error(t('icerik.hatirlatmaHatasi'));
    } finally {
      setHatirlatmaGidiyor(false);
    }
  };
  const gosterilen = useMemo(() => {
    if (!liste) return [];
    if (kanalSuzgeci === 'hepsi') return liste;
    return liste.filter((g) => g.channel === kanalSuzgeci);
  }, [liste, kanalSuzgeci]);

  const kaydet = async () => {
    if (!duzenlenen) return;
    const baslik = (duzenlenen.title || '').trim();
    if (!baslik) {
      toast.error(t('icerik.baslikGerekli'));
      return;
    }
    setKaydediliyor(true);
    try {
      const veri: Partial<Gonderi> = {
        ...duzenlenen,
        title: baslik,
        scheduled_at: isoyaCevir(duzenlenen.scheduled_at || '') ?? undefined,
      };
      delete (veri as { id?: number }).id;
      if (duzenlenen.id) await gonderiGuncelle(duzenlenen.id, veri);
      else await gonderiOlustur(veri);
      toast.success(t('icerik.kaydedildi'));
      setDuzenlenen(null);
      setAiYonlendirme('');
      yukle();
    } catch (e) {
      const err = e as { message?: string };
      toast.error(err?.message || t('icerik.kaydetmeHatasi'));
    } finally {
      setKaydediliyor(false);
    }
  };

  const taslakUret = async () => {
    if (!duzenlenen) return;
    const konu = (duzenlenen.title || '').trim();
    if (!konu) {
      toast.error(t('icerik.aiKonuGerekli'));
      return;
    }
    setAiCalisiyor(true);
    try {
      const metin = await icerikTaslagiUret({
        konu,
        kanal: (duzenlenen.channel as Kanal) || 'instagram',
        yonlendirme: aiYonlendirme,
      });
      setDuzenlenen({ ...duzenlenen, body: metin });
      toast.success(t('icerik.aiHazir'));
    } catch {
      // AI kapalıysa ya da ağ koparsa uydurma metin göstermiyoruz.
      toast.error(t('icerik.aiHatasi'));
    } finally {
      setAiCalisiyor(false);
    }
  };

  const kopyalaVeAc = async (g: Gonderi) => {
    const metin = gonderiMetni(g);
    try {
      await navigator.clipboard.writeText(metin);
      toast.success(t('icerik.kopyalandi'));
    } catch {
      toast.warning(t('icerik.kopyalanamadi'));
    }
    const adres = KANAL_ADRESI[(g.channel as Kanal) || 'instagram'];
    if (adres) window.open(adres, '_blank', 'noopener');
  };

  const paylasildiIsaretle = async (g: Gonderi) => {
    try {
      await gonderiGuncelle(g.id, {
        status: 'published',
        published_at: new Date().toISOString(),
      });
      yukle();
    } catch {
      toast.error(t('icerik.kaydetmeHatasi'));
    }
  };

  const sil = async (g: Gonderi) => {
    if (!confirm(t('icerik.silmeOnayi', { title: g.title }))) return;
    try {
      await gonderiSil(g.id);
      toast.success(t('icerik.silindi'));
      yukle();
    } catch {
      toast.error(t('icerik.silmeHatasi'));
    }
  };

  const alan = 'bg-white/5 border-white/10';
  const etiket = 'mb-2 block text-xs uppercase tracking-widest text-muted-foreground';
  const sekme =
    'rounded-lg px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-purple-400';

  const govdeUzunlugu = duzenlenen ? gonderiMetni(duzenlenen as Gonderi).length : 0;
  const govdeSiniri = duzenlenen ? KANAL_SINIRI[(duzenlenen.channel as Kanal) || 'instagram'] : undefined;
  const sinirAsildi = Boolean(govdeSiniri && govdeUzunlugu > govdeSiniri);

  return (
    <div>
      <div className="mb-4 rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3">
        <p className="text-xs leading-relaxed text-muted-foreground">{t('icerik.nasilCalisir')}</p>
      </div>

      {geciken.length > 0 && (
        <div className="mb-4 flex items-start gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-none text-amber-300" aria-hidden="true" />
          <div className="min-w-0">
            <p className="text-sm text-amber-100">
              {t('icerik.gecikenUyari', { count: geciken.length })}
            </p>
            {/*
              Hatırlatma ZAMANLANMIŞ İŞ DEĞİL, düğmeye basınca gidiyor.
              Ücretsiz sunucu uykuya geçtiği için saat başı çalışacak bir
              iş tam saatinde çalışmıyor; sessizce çalışmayan hatırlatma,
              hiç olmamasından kötü.
            */}
            <Button
              size="sm"
              variant="ghost"
              disabled={hatirlatmaGidiyor}
              onClick={hatirlat}
              className="mt-2 gap-2 px-0 text-amber-200 hover:text-amber-100"
            >
              {hatirlatmaGidiyor ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Mail className="h-4 w-4" />
              )}
              {t('icerik.hatirlat')}
            </Button>
          </div>
        </div>
      )}

      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex flex-wrap items-center gap-1 rounded-xl border border-white/10 bg-white/[0.03] p-1">
          <button
            type="button"
            onClick={() => setKanalSuzgeci('hepsi')}
            aria-pressed={kanalSuzgeci === 'hepsi'}
            className={`${sekme} ${
              kanalSuzgeci === 'hepsi'
                ? 'bg-purple-500/20 text-foreground'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {t('icerik.hepsi')}
          </button>
          {KANALLAR.map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => setKanalSuzgeci(k)}
              aria-pressed={kanalSuzgeci === k}
              className={`${sekme} ${
                kanalSuzgeci === k
                  ? 'bg-purple-500/20 text-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {t(`icerik.kanal.${k}`)}
            </button>
          ))}
        </div>

        <Button
          onClick={() => {
            setDuzenlenen({ ...BOS });
            setAiYonlendirme('');
          }}
          className="h-11 border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white"
        >
          <Plus className="me-2 h-4 w-4" /> {t('icerik.yeni')}
        </Button>
      </div>

      {liste === null && (
        <p className="flex items-center gap-2 py-12 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> {t('icerik.yukleniyor')}
        </p>
      )}

      {liste !== null && gosterilen.length === 0 && (
        <p className="rounded-xl border border-white/10 bg-white/[0.03] px-6 py-10 text-center text-sm text-muted-foreground">
          {t('icerik.bos')}
        </p>
      )}

      <div className="space-y-2">
        {gosterilen.map((g) => {
          const durum = g.status || 'draft';
          const zaman = g.scheduled_at ? new Date(g.scheduled_at) : null;
          const zamanMetni =
            zaman && !Number.isNaN(zaman.getTime())
              ? zaman.toLocaleString('tr-TR', { dateStyle: 'short', timeStyle: 'short' })
              : t('icerik.zamansiz');
          const gecikti = geciken.some((x) => x.id === g.id);

          return (
            <div
              key={g.id}
              className={`rounded-xl border bg-white/[0.03] px-4 py-3 ${
                gecikti ? 'border-amber-500/40' : 'border-white/10'
              }`}
            >
              <div className="flex flex-wrap items-center gap-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold">{g.title}</p>
                  <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                    {t(`icerik.kanal.${g.channel || 'instagram'}`)} · {zamanMetni}
                    {g.campaign ? ` · ${g.campaign}` : ''}
                  </p>
                </div>

                <span
                  className={`rounded-full px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider ${
                    DURUM_RENGI[durum] ?? DURUM_RENGI.draft
                  }`}
                >
                  {t(`icerik.durum.${durum}`)}
                </span>

                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => kopyalaVeAc(g)}
                  className="!bg-transparent !hover:bg-transparent border-white/20"
                  title={t('icerik.kopyalaVeAc')}
                >
                  <Copy className="h-4 w-4" />
                  <ExternalLink className="ms-1 h-3 w-3" />
                </Button>
                {durum !== 'published' && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => paylasildiIsaretle(g)}
                    className="!bg-transparent !hover:bg-transparent border-white/20"
                    title={t('icerik.paylasildi')}
                  >
                    <Check className="h-4 w-4" />
                  </Button>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setDuzenlenen({ ...g, scheduled_at: girdiyeCevir(g.scheduled_at) });
                    setAiYonlendirme('');
                  }}
                  className="!bg-transparent !hover:bg-transparent border-white/20"
                  title={t('icerik.duzenle')}
                >
                  <Pencil className="h-4 w-4" />
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => sil(g)}
                  className="!bg-transparent !hover:bg-transparent border-white/20 text-red-300"
                  title={t('icerik.sil')}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>

              {g.body && (
                <p className="mt-2 line-clamp-2 whitespace-pre-line text-sm text-muted-foreground">
                  {g.body}
                </p>
              )}
            </div>
          );
        })}
      </div>

      {/* Gönderi formu */}
      {duzenlenen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-background/80 p-4 backdrop-blur-sm">
          <div className="glass relative my-8 w-full max-w-2xl rounded-2xl border border-purple-500/30 p-8">
            <button
              className="absolute right-4 top-4 rounded-lg p-2 hover:bg-white/5"
              onClick={() => setDuzenlenen(null)}
              aria-label={t('icerik.kapat')}
            >
              <X className="h-4 w-4" />
            </button>
            <h3 className="mb-6 text-2xl font-bold">
              {duzenlenen.id ? t('icerik.duzenleBaslik') : t('icerik.yeniBaslik')}
            </h3>

            <div className="space-y-4">
              <div>
                <Label className={etiket}>{t('icerik.fKonu')} *</Label>
                <Input
                  className={alan}
                  placeholder={t('icerik.fKonuIpucu')}
                  value={duzenlenen.title || ''}
                  onChange={(e) => setDuzenlenen({ ...duzenlenen, title: e.target.value })}
                />
              </div>

              <div className="grid gap-4 sm:grid-cols-3">
                <div>
                  <Label className={etiket}>{t('icerik.fKanal')}</Label>
                  <select
                    value={duzenlenen.channel || 'instagram'}
                    onChange={(e) => setDuzenlenen({ ...duzenlenen, channel: e.target.value })}
                    className="h-10 w-full rounded-md border border-white/10 bg-white/5 px-3 text-sm"
                  >
                    {KANALLAR.map((k) => (
                      <option key={k} value={k} className="bg-background">
                        {t(`icerik.kanal.${k}`)}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <Label className={etiket}>{t('icerik.fZaman')}</Label>
                  <Input
                    type="datetime-local"
                    className={alan}
                    value={duzenlenen.scheduled_at || ''}
                    onChange={(e) =>
                      setDuzenlenen({ ...duzenlenen, scheduled_at: e.target.value })
                    }
                  />
                </div>
                <div>
                  <Label className={etiket}>{t('icerik.fDurum')}</Label>
                  <select
                    value={duzenlenen.status || 'draft'}
                    onChange={(e) => setDuzenlenen({ ...duzenlenen, status: e.target.value })}
                    className="h-10 w-full rounded-md border border-white/10 bg-white/5 px-3 text-sm"
                  >
                    {['draft', 'approved', 'published'].map((d) => (
                      <option key={d} value={d} className="bg-background">
                        {t(`icerik.durum.${d}`)}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* AI taslağı */}
              <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                <Label className={etiket}>{t('icerik.aiBaslik')}</Label>
                <div className="flex flex-col gap-2 sm:flex-row">
                  <Input
                    className={alan}
                    placeholder={t('icerik.aiIpucu')}
                    value={aiYonlendirme}
                    onChange={(e) => setAiYonlendirme(e.target.value)}
                  />
                  <Button
                    onClick={taslakUret}
                    disabled={aiCalisiyor}
                    className="h-10 flex-none border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white"
                  >
                    {aiCalisiyor ? (
                      <Loader2 className="me-2 h-4 w-4 animate-spin" />
                    ) : (
                      <Sparkles className="me-2 h-4 w-4" />
                    )}
                    {t('icerik.aiYaz')}
                  </Button>
                </div>
                <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
                  {t('icerik.aiUyari')}
                </p>
              </div>

              <div>
                <Label className={etiket}>{t('icerik.fMetin')}</Label>
                <Textarea
                  rows={8}
                  className={alan}
                  value={duzenlenen.body || ''}
                  onChange={(e) => setDuzenlenen({ ...duzenlenen, body: e.target.value })}
                />
                <p
                  className={`mt-1 text-right font-mono text-[11px] ${
                    sinirAsildi ? 'text-amber-300' : 'text-muted-foreground'
                  }`}
                >
                  {govdeUzunlugu}
                  {govdeSiniri ? ` / ${govdeSiniri}` : ''}
                  {sinirAsildi ? ` — ${t('icerik.sinirAsildi')}` : ''}
                </p>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <Label className={etiket}>{t('icerik.fBaglanti')}</Label>
                  <Input
                    className={alan}
                    placeholder="https://mehmetkuru.dev/…"
                    value={duzenlenen.link_url || ''}
                    onChange={(e) => setDuzenlenen({ ...duzenlenen, link_url: e.target.value })}
                  />
                </div>
                <div>
                  <Label className={etiket}>{t('icerik.fEtiketler')}</Label>
                  <Input
                    className={alan}
                    placeholder="#webtasarim #eticaret"
                    value={duzenlenen.hashtags || ''}
                    onChange={(e) => setDuzenlenen({ ...duzenlenen, hashtags: e.target.value })}
                  />
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <Label className={etiket}>{t('icerik.fGorsel')}</Label>
                  <Input
                    className={alan}
                    value={duzenlenen.image_url || ''}
                    onChange={(e) => setDuzenlenen({ ...duzenlenen, image_url: e.target.value })}
                  />
                </div>
                <div>
                  <Label className={etiket}>{t('icerik.fKampanya')}</Label>
                  <Input
                    className={alan}
                    placeholder={t('icerik.fKampanyaIpucu')}
                    value={duzenlenen.campaign || ''}
                    onChange={(e) => setDuzenlenen({ ...duzenlenen, campaign: e.target.value })}
                  />
                </div>
              </div>

              <div>
                <Label className={etiket}>{t('icerik.fNot')}</Label>
                <Textarea
                  rows={2}
                  className={alan}
                  value={duzenlenen.notes || ''}
                  onChange={(e) => setDuzenlenen({ ...duzenlenen, notes: e.target.value })}
                />
              </div>
            </div>

            <div className="mt-6 flex gap-3">
              <Button
                onClick={kaydet}
                disabled={kaydediliyor}
                className="h-11 flex-1 border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white"
              >
                {kaydediliyor && <Loader2 className="me-2 h-4 w-4 animate-spin" />}
                {t('icerik.kaydet')}
              </Button>
              <Button
                variant="outline"
                onClick={() => setDuzenlenen(null)}
                className="h-11 border-white/20 !bg-transparent !hover:bg-transparent"
              >
                {t('icerik.vazgec')}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
