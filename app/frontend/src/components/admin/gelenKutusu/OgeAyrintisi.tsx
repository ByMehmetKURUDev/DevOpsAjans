import { useCallback, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import {
  ArrowLeft,
  Blocks,
  Briefcase,
  CalendarClock,
  CheckCheck,
  CheckCircle2,
  Copy,
  ExternalLink,
  ListTodo,
  Loader2,
  Mail,
  RotateCcw,
  Send,
  Sparkles,
  XCircle,
  type LucideIcon,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import UzmanPromptlari from '@/components/admin/UzmanPromptlari';
import { SUPPORTED_LANGUAGES } from '@/i18n';
import { tamZaman } from '@/lib/denetim';
import { zamanYaz } from '@/lib/toplantiZaman';
import {
  ayrintiGetir,
  epostaGonder,
  eylemiCalistir,
  GelenKutusuHatasi,
  istek,
  taslakUret,
  type AyrintiYaniti,
  type Eylem,
  type Kaynak,
} from '@/lib/gelenKutusu';
import { DURUM_RENGI, KAYNAK_IKONU } from './ortak';

/** AdminPanel'in "projeye çevir" akışının beklediği talep (eski İletişim formu sekmesindeki `Inquiry`). */
export interface ProjeyeCevrilecekTalep {
  id: number;
  name: string;
  email: string;
  phone?: string;
  subject?: string;
  message: string;
  status?: string;
  source?: string;
  brief?: string | null;
}

interface YazismaSatiri {
  id: number | string;
  taraf: 'musteri' | 'ajans';
  ad?: string | null;
  metin: string;
  zaman?: string | null;
}

const EYLEM_IKONU: Record<string, LucideIcon> = {
  okundu: CheckCheck,
  kapat: XCircle,
  cozuldu: CheckCircle2,
  projeye_cevir: Briefcase,
  uzman_istem: Sparkles,
  yeniden_ac: RotateCcw,
  goreve_donustur: ListTodo,
  paket_uygula: Blocks,
  toplanti_planla: CalendarClock,
};

function metinAl(deger: unknown): string {
  if (deger === null || deger === undefined) return '';
  if (Array.isArray(deger)) return deger.map(String).join(', ');
  return String(deger);
}

interface Props {
  kaynak: Kaynak;
  kimlik: number;
  aiHazir?: boolean;
  epostaHazir?: boolean;
  onDegisti: () => void;
  onGeri: () => void;
  onProjeyeCevir: (talep: ProjeyeCevrilecekTalep) => void;
}

/**
 * Seçili gelen kutusu öğesi: tam metin, kaynağa özgü alanlar, (destek/sohbette)
 * yazışma, eylemler ve yanıt kutusu (AI taslak → düzenle → kaynağın kendi yanıt
 * yoluyla gönder). Taslak kendiliğinden GİTMEZ.
 */
export default function OgeAyrintisi({ kaynak, kimlik, aiHazir, epostaHazir, onDegisti, onGeri, onProjeyeCevir }: Props) {
  const { t, i18n } = useTranslation();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [veri, setVeri] = useState<AyrintiYaniti | null>(null);
  const [hata, setHata] = useState(false);
  const [yazisma, setYazisma] = useState<YazismaSatiri[] | null>(null);
  const [calisan, setCalisan] = useState<string | null>(null);
  const [uzmanAcik, setUzmanAcik] = useState(false);
  const [metin, setMetin] = useState('');
  const [konu, setKonu] = useState('');
  const [dilSecimi, setDilSecimi] = useState('');
  const [taslakBilgisi, setTaslakBilgisi] = useState<{ dil: string; sahte: boolean } | null>(null);
  const [uretiliyor, setUretiliyor] = useState(false);
  const [gonderiliyor, setGonderiliyor] = useState(false);
  const dil = i18n.language;

  const yukle = useCallback(async () => {
    try {
      const g = await ayrintiGetir(kaynak, kimlik);
      setVeri(g);
      setHata(false);
      setKonu((eski) => eski || (g.oge.baslik ? `Re: ${g.oge.baslik}` : 'Re: mehmetkuru.dev'));
    } catch {
      setHata(true);
    }
  }, [kaynak, kimlik]);

  const yazismayiYukle = useCallback(async () => {
    try {
      if (kaynak === 'destek') {
        const g = await istek<{ mesajlar: { id: number; yazan: string; yazan_ad?: string | null; mesaj: string; created_at?: string | null }[] }>(
          'GET',
          `/api/v1/talep/${kimlik}/mesajlar`
        );
        setYazisma(
          (g.mesajlar || []).map((m) => ({
            id: `${m.id}-${m.created_at || ''}`,
            taraf: m.yazan === 'musteri' ? 'musteri' : 'ajans',
            ad: m.yazan_ad,
            metin: m.mesaj,
            zaman: m.created_at,
          }))
        );
      } else if (kaynak === 'sohbet') {
        const g = await istek<{
          mesajlar: { id: number; yazan_rol: string; yazan_ad?: string | null; metin: string; silindi: boolean; created_at?: string | null }[];
        }>('GET', `/api/v1/mesajlar/konusmalar/${kimlik}/mesajlar?adet=20`);
        setYazisma(
          (g.mesajlar || [])
            .filter((m) => !m.silindi)
            .map((m) => ({ id: m.id, taraf: m.yazan_rol === 'client' ? 'musteri' : 'ajans', ad: m.yazan_ad, metin: m.metin, zaman: m.created_at }))
        );
      }
    } catch {
      setYazisma([]);
    }
  }, [kaynak, kimlik]);

  useEffect(() => {
    void yukle();
    void yazismayiYukle();
  }, [yukle, yazismayiYukle]);

  // Faz 7K — "bilgi" öğesi (teklif kararı) yanıt beklemiyor: ayrıntısı açılınca okundu sayılıp kapanır.
  const bilgiKapat = veri?.oge.ek.bilgi && veri.oge.durum === 'yeni' ? veri.oge.eylemler.find((e) => e.anahtar === 'okundu') : undefined;
  useEffect(() => {
    if (!bilgiKapat) return;
    let iptal = false;
    eylemiCalistir(bilgiKapat)
      .then(async () => {
        if (iptal) return;
        await yukle();
        onDegisti();
      })
      .catch(() => undefined);
    return () => {
      iptal = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bilgiKapat?.istek?.yol]);

  const oge = veri?.oge;
  const ayrinti = veri?.ayrinti || {};
  const aiAcik = aiHazir ?? veri?.meta.ai_hazir ?? false;
  const epostaAcik = epostaHazir ?? veri?.meta.eposta_hazir ?? false;

  const hataMetni = (h: unknown, varsayilan: string) =>
    h instanceof GelenKutusuHatasi ? t(`gelenKutusu.hataKod.${h.kod}`, { defaultValue: varsayilan }) : varsayilan;

  async function eylem(e: Eylem) {
    if (!oge) return;
    if (e.anahtar === 'projeye_cevir') {
      onProjeyeCevir({
        id: oge.kimlik,
        name: metinAl(ayrinti.ad) || oge.kisi_ad || '',
        email: metinAl(ayrinti.eposta) || oge.kisi_eposta || '',
        phone: metinAl(ayrinti.telefon) || undefined,
        subject: metinAl(ayrinti.konu) || undefined,
        message: metinAl(ayrinti.mesaj),
        status: metinAl(ayrinti.durum_ham) || undefined,
        source: metinAl(ayrinti.kaynak_etiketi) || undefined,
        brief: (ayrinti.brief as string | null | undefined) ?? null,
      });
      return;
    }
    if (e.anahtar === 'uzman_istem') {
      setUzmanAcik(true);
      return;
    }
    if (e.anahtar === 'toplanti_planla') {
      // Faz 6T: müşterinin toplantı talebi → Toplantılar, talepten ön doldurulmuş form açık.
      navigate(`/admin?sekme=toplantilar&talep=${oge.kimlik}`);
      return;
    }
    if (e.anahtar === 'paket_uygula') {
      // Faz 6R: vitrin paket talebi + müşteri hesabı → Modüller ekranı, müşteri seçili, paket formu açık.
      const eposta = oge.kisi_eposta || '';
      const paket = typeof oge.ek.paket === 'string' ? oge.ek.paket : '';
      navigate(`/admin?sekme=moduller&musteri=${encodeURIComponent(eposta)}&paket=${encodeURIComponent(paket)}`);
      return;
    }
    setCalisan(e.anahtar);
    try {
      await eylemiCalistir(e);
      toast.success(t('gelenKutusu.eylemTamam'));
      await yukle();
      onDegisti();
    } catch (h) {
      toast.error(hataMetni(h, t('gelenKutusu.eylemHata')));
    } finally {
      setCalisan(null);
    }
  }

  async function taslakOlustur() {
    setUretiliyor(true);
    try {
      const g = await taslakUret(kaynak, kimlik, { dil: dilSecimi || null });
      setMetin(g.taslak);
      if (g.konu) setKonu(g.konu);
      setTaslakBilgisi({ dil: g.dil, sahte: g.sahte });
    } catch (h) {
      toast.error(hataMetni(h, t('gelenKutusu.hataKod.ai_hatasi')));
    } finally {
      setUretiliyor(false);
    }
  }

  async function gonder() {
    if (!oge?.yanit) return;
    const govde = metin.trim();
    if (!govde) {
      toast.error(t('gelenKutusu.yanit.bos'));
      return;
    }
    setGonderiliyor(true);
    try {
      if (oge.yanit.tur === 'talep') await istek('POST', oge.yanit.yol, { mesaj: govde });
      else if (oge.yanit.tur === 'sohbet') await istek('POST', oge.yanit.yol, { metin: govde });
      else await epostaGonder(kaynak, kimlik, { konu, metin: govde });
      toast.success(t('gelenKutusu.yanit.gonderildi'));
      setMetin('');
      setTaslakBilgisi(null);
      await Promise.all([yukle(), yazismayiYukle()]);
      onDegisti();
    } catch (h) {
      toast.error(hataMetni(h, t('gelenKutusu.yanit.gonderilemedi')));
      // Faz 7K: gönderilemeyen e-posta yanıtı da yazışma geçmişinde ("gönderilemedi").
      if (oge.yanit.tur === 'eposta') void yukle();
    } finally {
      setGonderiliyor(false);
    }
  }

  async function kopyala() {
    try {
      await navigator.clipboard.writeText(metin);
      toast.success(t('gelenKutusu.yanit.kopyalandi'));
    } catch {
      toast.warning(t('gelenKutusu.yanit.kopyalanamadi'));
    }
  }

  const alanlar = useMemo(() => {
    const a = ayrinti;
    const s: [string, string, boolean?][] = [];
    const ekle = (anahtar: string, deger: unknown, uzun = false) => {
      const m = metinAl(deger).trim();
      if (m) s.push([anahtar, m, uzun]);
    };
    switch (kaynak) {
      case 'iletisim':
        ekle('konu', a.konu);
        ekle('mesaj', a.mesaj, true);
        ekle('telefon', a.telefon);
        ekle('kaynakEtiketi', a.kaynak_etiketi);
        break;
      case 'fiyat_teklifi':
        ekle('paket', [a.paket, a.profil, a.donem, a.ai_pm].filter(Boolean).join(' / '));
        ekle('eklentiler', a.eklentiler);
        ekle('tutar', a.tutar ? `${a.tutar} ${metinAl(a.para_birimi)}` : '');
        ekle('karar', a.karar ? t(`gelenKutusu.karar.${metinAl(a.karar)}`, { defaultValue: metinAl(a.karar) }) : '');
        ekle('karar_notu', a.karar_notu, true);
        break;
      case 'destek':
        ekle('konu', a.konu);
        ekle('oncelik', a.oncelik);
        break;
      case 'sohbet':
        ekle('konu', a.konu);
        break;
      case 'kartvizit':
        ekle('mesaj', a.mesaj, true);
        ekle('telefon', a.telefon);
        ekle('nereden', a.sahip_baslik);
        break;
      case 'randevu':
        ekle('tur', a.tur_adi);
        ekle('baslangic', tamZaman(metinAl(a.baslangic), dil));
        ekle('yanitlar', a.yanitlar, true);
        ekle('telefon', a.telefon);
        ekle('konum', a.konum);
        break;
      case 'geri_bildirim':
        ekle('konu', a.baslik);
        ekle('mesaj', a.aciklama, true);
        ekle('sayfa', a.sayfa_adresi);
        ekle('oncelik', a.oncelik);
        break;
      case 'icerik_revizyon':
        ekle('gonderi', a.gonderi_baslik);
        ekle('not', a.not, true);
        break;
      case 'belge':
        ekle('belge', a.baslik);
        ekle('dosya', a.dosya_adi);
        ekle('mesaj', a.aciklama, true);
        break;
      case 'egitim':
        ekle('kurs', a.kurs);
        ekle('ogrenci', a.cocuk ? `${metinAl(a.ogrenci)} (${t('gelenKutusu.egitimDurum.cocuk')})` : a.ogrenci);
        ekle('kayitDurumu', a.durum_ham ? t(`gelenKutusu.egitimDurum.${metinAl(a.durum_ham)}`, { defaultValue: metinAl(a.durum_ham) }) : '');
        ekle('telefon', a.telefon);
        ekle('veli', [a.veli_ad, a.veli_telefon].map(metinAl).filter(Boolean).join(' · '));
        break;
      case 'izin_talebi':
        ekle('personel', a.personel);
        ekle('departman', a.departman);
        ekle('izinTuru', a.izin_turu ? t(`gelenKutusu.izinTuru.${metinAl(a.izin_turu)}`, { defaultValue: metinAl(a.izin_turu) }) : '');
        ekle('tarih', a.baslangic === a.bitis ? a.baslangic : `${metinAl(a.baslangic)} – ${metinAl(a.bitis)}`);
        ekle('isGunu', a.gun);
        ekle('kayitDurumu', a.durum_ham ? t(`gelenKutusu.izinDurum.${metinAl(a.durum_ham)}`, { defaultValue: metinAl(a.durum_ham) }) : '');
        ekle('mesaj', a.aciklama, true);
        break;
      case 'ortak_basvurusu':
        ekle('web', a.web);
        ekle('tanitim', a.tanitim, true);
        ekle('pazarlama', a.pazarlama_izni ? '✓' : '');
        break;
      case 'belge_paylasim':
        ekle('belge', a.baslik);
        ekle('olay', t(`gelenKutusu.belgeOlayi.${a.olay === 'onayladi' ? 'onayladi' : 'paylasti'}`, { sayi: a.surum ?? 1 }));
        break;
      case 'crm_form':
        ekle('form', a.form_baslik && a.form_baslik !== a.form ? `${metinAl(a.form)} — ${metinAl(a.form_baslik)}` : a.form);
        ekle('mesaj', a.mesaj, true);
        ekle('telefon', a.telefon);
        ekle('firma', a.firma);
        ekle('butce', a.butce);
        ekle('pazarlamaIzni', a.pazarlama_izni ? t('gelenKutusu.evet') : '');
        break;
      case 'toplanti_talebi': {
        // Faz 6T: tercih edilen zaman aralıkları İstanbul saatiyle (UTC saklanıyor).
        const araliklar = Array.isArray(a.araliklar) ? (a.araliklar as { bas?: string; bit?: string }[]) : [];
        ekle('konu', a.konu);
        ekle(
          'araliklar',
          araliklar.map((x) => `${zamanYaz(metinAl(x.bas), dil)} – ${zamanYaz(metinAl(x.bit), dil)}`).join('\n'),
          true
        );
        ekle('mesaj', a.not, true);
        ekle('talepDurumu', a.durum_ham ? t(`gelenKutusu.toplantiTalebiDurum.${metinAl(a.durum_ham)}`) : '');
        break;
      }
      case 'teklif_karari':
        ekle('teklif', [a.no, a.baslik].map(metinAl).filter(Boolean).join(' — '));
        ekle('karar', a.karar ? t(`gelenKutusu.karar.${metinAl(a.karar) === 'ret' ? 'red' : metinAl(a.karar)}`) : '');
        ekle('kararVeren', a.karar_ad);
        ekle('tutar', a.tutar ? `${metinAl(a.tutar)} ${metinAl(a.para_birimi)}` : '');
        ekle('karar_notu', a.karar_notu, true);
        break;
    }
    return s;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [veri, kaynak, dil]);

  if (hata) {
    return (
      <div className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6 text-sm text-muted-foreground" data-testid="gk-ayrinti-hata">
        <GeriDugmesi onGeri={onGeri} />
        {t('gelenKutusu.hata')}
      </div>
    );
  }
  if (!oge) {
    return (
      <div className="flex justify-center py-12">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" aria-hidden="true" />
      </div>
    );
  }

  const Ikon = KAYNAK_IKONU[oge.kaynak];
  const acSorgu = (() => {
    try {
      return new URL(oge.ac_baglantisi, window.location.origin).search;
    } catch {
      return '';
    }
  })();
  const mailto = oge.kisi_eposta
    ? `mailto:${encodeURIComponent(oge.kisi_eposta)}?subject=${encodeURIComponent(konu)}&body=${encodeURIComponent(metin)}`
    : '';

  return (
    <article className="cam-kart min-w-0 space-y-4 rounded-2xl border border-white/10 bg-white/[0.03] p-4 sm:p-6" data-testid="gk-ayrinti" data-gk-ayrinti={oge.anahtar}>
      <GeriDugmesi onGeri={onGeri} />
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-2 py-0.5 uppercase tracking-wider text-muted-foreground">
            <Ikon className="h-3.5 w-3.5" aria-hidden="true" />
            {t(`gelenKutusu.kaynak.${oge.kaynak}`)}
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-white/10 px-2 py-0.5" data-gk-ayrinti-durum={oge.durum}>
            <span className={`h-2 w-2 rounded-full ${DURUM_RENGI[oge.durum]}`} aria-hidden="true" />
            {t(`gelenKutusu.durum.${oge.durum}`)}
          </span>
          {oge.ek.cevrildi ? (
            <span className="rounded-full bg-purple-500/15 px-2 py-0.5 text-purple-200" data-testid="gk-cevrildi">
              {t('gelenKutusu.cevrildi')}
            </span>
          ) : null}
          {oge.zaman ? (
            <time className="text-muted-foreground" dateTime={oge.zaman}>
              {tamZaman(oge.zaman, dil)}
            </time>
          ) : null}
        </div>
        <h3 className="break-words text-lg font-semibold">
          <bdi>{oge.baslik || oge.kisi_ad || oge.kisi_eposta || '—'}</bdi>
        </h3>
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
          {oge.kisi_ad ? (
            <span className="text-foreground">
              <bdi>{oge.kisi_ad}</bdi>
            </span>
          ) : null}
          {oge.kisi_eposta ? (
            <a href={`mailto:${oge.kisi_eposta}`} className="inline-flex items-center gap-1 hover:text-foreground" dir="ltr">
              <Mail className="h-3.5 w-3.5" aria-hidden="true" />
              {oge.kisi_eposta}
            </a>
          ) : null}
          {oge.hesap_email ? (
            <span className="rounded-full bg-purple-500/15 px-2 py-0.5 text-[11px] text-purple-200" data-testid="gk-musteri-hesabi">
              {t('gelenKutusu.musteriHesabi')}
            </span>
          ) : null}
        </p>
      </header>

      {alanlar.length ? (
        <dl className="space-y-2 text-sm">
          {alanlar.map(([anahtar, deger, uzun]) => (
            <div key={anahtar} className={uzun ? '' : 'flex flex-wrap gap-x-2'}>
              <dt className="text-xs uppercase tracking-wider text-muted-foreground">{t(`gelenKutusu.alan.${anahtar}`)}</dt>
              <dd className={uzun ? 'mt-1 whitespace-pre-wrap break-words rounded-xl border border-white/10 bg-black/20 p-3' : 'break-words'}>
                <bdi>{deger}</bdi>
              </dd>
            </div>
          ))}
        </dl>
      ) : null}

      {yazisma ? (
        <section aria-label={t('gelenKutusu.alan.yazisma')}>
          <h4 className="mb-2 text-xs uppercase tracking-wider text-muted-foreground">{t('gelenKutusu.alan.yazisma')}</h4>
          <div className="max-h-72 space-y-2 overflow-y-auto pe-1" data-testid="gk-yazisma">
            {yazisma.map((m) => (
              <div key={m.id} className={`flex ${m.taraf === 'ajans' ? 'justify-end' : 'justify-start'}`}>
                <div
                  className={`max-w-[85%] rounded-xl px-3 py-2 text-sm ${
                    m.taraf === 'ajans' ? 'bg-primary/15' : 'border border-white/10 bg-white/[0.04]'
                  }`}
                >
                  <p className="mb-1 text-[10px] uppercase tracking-wider text-muted-foreground">
                    {m.taraf === 'ajans' ? t('gelenKutusu.alan.ajans') : m.ad || t('gelenKutusu.alan.musteri')}
                    {m.zaman ? ` • ${tamZaman(m.zaman, dil)}` : ''}
                  </p>
                  <p className="whitespace-pre-wrap break-words">
                    <bdi>{m.metin}</bdi>
                  </p>
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {/* Faz 7K — e-postayla verilen yanıtlar (kim, kime, ne zaman; gönderilemeyenler de). */}
      {veri?.yanitlar?.length ? (
        <section aria-label={t('gelenKutusu.epostaGecmisi')}>
          <h4 className="mb-2 text-xs uppercase tracking-wider text-muted-foreground">{t('gelenKutusu.epostaGecmisi')}</h4>
          <div className="max-h-72 space-y-2 overflow-y-auto pe-1" data-testid="gk-eposta-gecmisi">
            {veri.yanitlar.map((y) => (
              <div key={y.id} className="flex justify-end" data-gk-yanit-durum={y.durum}>
                <div
                  className={`max-w-[85%] rounded-xl px-3 py-2 text-sm ${
                    y.durum === 'gonderildi' ? 'bg-primary/15' : 'border border-amber-400/40 bg-amber-500/10'
                  }`}
                >
                  <p className="mb-1 flex flex-wrap items-center gap-x-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
                    <span className={y.yazan ? 'normal-case tracking-normal' : undefined} dir={y.yazan ? 'ltr' : undefined}>
                      {y.yazan || t('gelenKutusu.alan.ajans')}
                    </span>
                    <span aria-hidden="true">→</span>
                    <span className="normal-case tracking-normal" dir="ltr">
                      {y.alici}
                    </span>
                    {y.zaman ? <span>• {tamZaman(y.zaman, dil)}</span> : null}
                    <span className={y.durum === 'gonderildi' ? 'text-emerald-300' : 'text-amber-200'}>
                      • {t(`gelenKutusu.yanitDurum.${y.durum}`)}
                      {y.neden ? ` (${t(`gelenKutusu.yanitNeden.${y.neden}`, { defaultValue: y.neden })})` : ''}
                    </span>
                  </p>
                  {y.konu ? (
                    <p className="text-xs font-medium">
                      <bdi>{y.konu}</bdi>
                    </p>
                  ) : null}
                  <p className="whitespace-pre-wrap break-words">
                    <bdi>{y.metin}</bdi>
                  </p>
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {oge.ek.bilgi ? (
        <p className="rounded-xl border border-sky-400/30 bg-sky-500/10 px-3 py-2 text-xs text-sky-100" data-testid="gk-bilgi-notu">
          {t('gelenKutusu.bilgiNotu')}
        </p>
      ) : null}

      {/* Eylemler */}
      <div className="flex flex-wrap gap-2" data-testid="gk-eylemler">
        {oge.eylemler.map((e) => {
          const EIkon = EYLEM_IKONU[e.anahtar] || CheckCircle2;
          const etiket =
            e.anahtar === 'uzman_istem' && oge.ek.brief_var ? t('gelenKutusu.eylem.uzman_istem_hazir') : t(`gelenKutusu.eylem.${e.anahtar}`);
          return (
            <Button
              key={e.anahtar}
              type="button"
              size="sm"
              variant="outline"
              disabled={calisan !== null}
              onClick={() => void eylem(e)}
              className="gap-1.5 border-white/15 !bg-transparent"
              data-gk-eylem={e.anahtar}
            >
              {calisan === e.anahtar ? <Loader2 className="h-4 w-4 animate-spin" /> : <EIkon className="h-4 w-4" aria-hidden="true" />}
              {etiket}
            </Button>
          );
        })}
        <Button asChild size="sm" variant="ghost" className="gap-1.5">
          <Link to={{ pathname, search: acSorgu }} data-testid="gk-bolumde-ac">
            <ExternalLink className="h-4 w-4" aria-hidden="true" />
            {t('gelenKutusu.bolumdeAc')}
          </Link>
        </Button>
      </div>

      {/* Yanıt + AI taslak */}
      <section className="space-y-2 border-t border-white/10 pt-4" aria-label={t('gelenKutusu.yanit.baslik')} data-testid="gk-yanit">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h4 className="text-sm font-semibold">{t('gelenKutusu.yanit.baslik')}</h4>
          <div className="flex flex-wrap items-center gap-2">
            <label className="inline-flex items-center gap-1 text-xs text-muted-foreground">
              {t('gelenKutusu.yanit.dil')}
              <select
                value={dilSecimi}
                onChange={(e) => setDilSecimi(e.target.value)}
                className="h-8 rounded-lg border border-white/10 bg-white/5 px-2 text-xs text-foreground"
                data-testid="gk-dil"
              >
                <option value="">{t('gelenKutusu.yanit.dilOtomatik')}</option>
                {SUPPORTED_LANGUAGES.map((l) => (
                  <option key={l.code} value={l.code}>
                    {l.full}
                  </option>
                ))}
              </select>
            </label>
            <Button
              type="button"
              size="sm"
              onClick={() => void taslakOlustur()}
              disabled={!aiAcik || uretiliyor}
              className="gap-1.5 border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white"
              data-testid="gk-ai-taslak"
              title={!aiAcik ? t('gelenKutusu.yanit.aiKapali') : undefined}
            >
              {uretiliyor ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" aria-hidden="true" />}
              {uretiliyor ? t('gelenKutusu.yanit.aiUretiliyor') : t('gelenKutusu.yanit.aiTaslak')}
            </Button>
          </div>
        </div>
        {!aiAcik ? (
          <p className="text-xs text-muted-foreground" data-testid="gk-ai-kapali">
            {t('gelenKutusu.yanit.aiKapali')}
          </p>
        ) : null}
        {oge.yanit?.tur === 'eposta' ? (
          <label className="block text-xs text-muted-foreground">
            {t('gelenKutusu.yanit.konu')}
            <input
              value={konu}
              onChange={(e) => setKonu(e.target.value)}
              maxLength={200}
              className="mt-1 h-9 w-full rounded-lg border border-white/10 bg-white/5 px-3 text-sm text-foreground"
              data-testid="gk-konu"
            />
          </label>
        ) : null}
        <Textarea
          value={metin}
          onChange={(e) => setMetin(e.target.value)}
          rows={6}
          placeholder={t('gelenKutusu.yanit.yerTutucu')}
          className="bg-white/5 text-sm"
          data-testid="gk-yanit-metni"
          dir="auto"
        />
        {taslakBilgisi ? (
          <p className="text-xs text-amber-200/90" data-testid="gk-taslak-notu">
            {t('gelenKutusu.yanit.aiNot')}{' '}
            <span className="text-muted-foreground">
              ({t('gelenKutusu.yanit.dil')}: {SUPPORTED_LANGUAGES.find((l) => l.code === taslakBilgisi.dil)?.full || taslakBilgisi.dil})
            </span>
          </p>
        ) : null}
        <div className="flex flex-wrap items-center gap-2">
          {oge.yanit && (oge.yanit.tur !== 'eposta' || epostaAcik) ? (
            <Button
              type="button"
              size="sm"
              onClick={() => void gonder()}
              disabled={gonderiliyor || !metin.trim()}
              className="gap-1.5"
              data-testid="gk-gonder"
            >
              {gonderiliyor ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4 rtl:-scale-x-100" aria-hidden="true" />}
              {oge.yanit.tur === 'talep'
                ? t('gelenKutusu.yanit.talepGonder')
                : oge.yanit.tur === 'sohbet'
                  ? t('gelenKutusu.yanit.sohbetGonder')
                  : t('gelenKutusu.yanit.epostaGonder')}
            </Button>
          ) : null}
          <Button type="button" size="sm" variant="outline" onClick={() => void kopyala()} disabled={!metin.trim()} className="gap-1.5 border-white/15 !bg-transparent" data-testid="gk-kopyala">
            <Copy className="h-4 w-4" aria-hidden="true" />
            {t('gelenKutusu.yanit.kopyala')}
          </Button>
          {oge.yanit?.tur === 'eposta' && mailto ? (
            <Button asChild size="sm" variant="ghost" className="gap-1.5">
              <a href={mailto} data-testid="gk-mailto">
                <Mail className="h-4 w-4" aria-hidden="true" />
                {t('gelenKutusu.yanit.epostaAc')}
              </a>
            </Button>
          ) : null}
        </div>
        {oge.yanit?.tur === 'eposta' && !epostaAcik ? (
          <p className="text-xs text-muted-foreground" data-testid="gk-eposta-kapali">
            {t('gelenKutusu.yanit.epostaKapali')}
          </p>
        ) : null}
        {!oge.yanit ? <p className="text-xs text-muted-foreground">{t('gelenKutusu.yanit.epostaYok')}</p> : null}
      </section>

      {/* Pencere gövdeye çiziliyor: Modern görünümde cam kartın backdrop-filter'ı `fixed`ı kırpmasın. */}
      {uzmanAcik && oge.kaynak === 'iletisim' ? createPortal(
        <UzmanPromptlari
          kayitTuru="inquiries"
          talepId={oge.kimlik}
          musteri={metinAl(ayrinti.ad) || oge.kisi_ad || ''}
          musteriEposta={oge.kisi_eposta || ''}
          konu={metinAl(ayrinti.konu)}
          mesaj={metinAl(ayrinti.mesaj)}
          kayitliBrief={(ayrinti.brief as string | null | undefined) ?? null}
          onSaved={() => {
            void yukle();
            onDegisti();
          }}
          onClose={() => setUzmanAcik(false)}
        />,
        document.body
      ) : null}
    </article>
  );
}

function GeriDugmesi({ onGeri }: { onGeri: () => void }) {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      onClick={onGeri}
      className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground lg:hidden"
      data-testid="gk-geri"
    >
      <ArrowLeft className="h-4 w-4 rtl:-scale-x-100" aria-hidden="true" />
      {t('gelenKutusu.listeyeDon')}
    </button>
  );
}
