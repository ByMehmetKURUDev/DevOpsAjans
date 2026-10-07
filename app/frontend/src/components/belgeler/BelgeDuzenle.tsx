import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Bold,
  CheckSquare,
  Code,
  Eye,
  Heading2,
  Italic,
  Link2,
  List,
  ListOrdered,
  Loader2,
  PenLine,
  Quote,
  Save,
  Sparkles,
  Table,
  Wand2,
  X,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  hataMetni,
  type AiIslem,
  type AiSonucu,
  type Alan,
  type BelgeApi,
  type BelgeAyrintisi,
  type BelgeGovdesi,
  type Gorunurluk,
  type Meta,
  type StratejiIcerigi,
  type Uyari,
} from '@/lib/belgeler';

import { AiUyarilari, ALAN_ETIKETI, etiketleriAyir, KART, SECIM } from './ortak';
import StratejiIzgarasi from './StratejiIzgarasi';

/**
 * Faz 5B — belge / strateji düzenleyici.
 *
 * Belge: Markdown metin alanı + araç çubuğu (başlık, kalın, eğik, liste, numaralı liste, onay
 * kutusu, bağlantı, tablo, kod, alıntı) + "Önizleme" (HTML sunucuda üretilip temizleniyor) +
 * AI ile yaz / özetle / düzelt (öneri; kullanıcı ekler). Strateji: şablon ızgarası + işletme
 * tanımı + "AI ile taslak doldur" (kutu kutu ya da toptan uygulanır). Kaydetmede editörün açtığı
 * sürüm gönderilir; başkası arada kaydettiyse sunucu 409 verir (üzerine yazılmaz).
 */

export interface MusteriSecenegi {
  eposta: string;
  ad: string | null;
}
export interface ProjeSecenegi {
  id: number;
  title: string;
  client_email?: string | null;
}

interface Ozellikler {
  api: BelgeApi;
  meta: Meta;
  /** Yoksa yeni belge. */
  belge?: BelgeAyrintisi | null;
  tur: string;
  musteriler?: MusteriSecenegi[];
  projeler?: ProjeSecenegi[];
  onKaydedildi: (b: BelgeAyrintisi) => void;
  onVazgec: () => void;
}

type AracAnahtari = 'baslik' | 'kalin' | 'egik' | 'liste' | 'numarali' | 'yapilacak' | 'baglanti' | 'tablo' | 'kod' | 'alinti';
const ARACLAR: { anahtar: AracAnahtari; ikon: typeof Bold }[] = [
  { anahtar: 'baslik', ikon: Heading2 },
  { anahtar: 'kalin', ikon: Bold },
  { anahtar: 'egik', ikon: Italic },
  { anahtar: 'liste', ikon: List },
  { anahtar: 'numarali', ikon: ListOrdered },
  { anahtar: 'yapilacak', ikon: CheckSquare },
  { anahtar: 'baglanti', ikon: Link2 },
  { anahtar: 'tablo', ikon: Table },
  { anahtar: 'kod', ikon: Code },
  { anahtar: 'alinti', ikon: Quote },
];

export default function BelgeDuzenle({ api, meta, belge, tur, musteriler = [], projeler = [], onKaydedildi, onVazgec }: Ozellikler) {
  const { t, i18n } = useTranslation();
  const yonetici = api.mod === 'yonetici';
  const strateji = tur !== 'belge';
  const sablon = useMemo(() => meta.strateji_sablonlari.find((s) => s.tur === tur) || null, [meta, tur]);

  const [baslik, setBaslik] = useState(belge?.baslik ?? '');
  const [etiketMetni, setEtiketMetni] = useState((belge?.etiketler ?? []).join(', '));
  const [icerik, setIcerik] = useState(belge?.icerik ?? '');
  const [stratejiIcerigi, setStratejiIcerigi] = useState<StratejiIcerigi>(
    belge?.strateji_icerik ?? { isletme: '', kutular: {} }
  );
  const [alan, setAlan] = useState<Alan>(belge?.alan ?? 'ajans');
  const [musteri, setMusteri] = useState(belge?.musteri_email ?? '');
  const [projeId, setProjeId] = useState<string>(belge?.proje_id ? String(belge.proje_id) : '');
  const [gorunurluk, setGorunurluk] = useState<Gorunurluk>(belge?.gorunurluk ?? 'ekip');
  const [sabit, setSabit] = useState(!!belge?.sabit);
  const [kaydediliyor, setKaydediliyor] = useState(false);
  const [onizleme, setOnizleme] = useState<string | null>(null);
  const [onizlemeYukleniyor, setOnizlemeYukleniyor] = useState(false);

  const [aiIslem, setAiIslem] = useState<AiIslem | null>(null);
  const [aiCalisiyor, setAiCalisiyor] = useState(false);
  const [talimat, setTalimat] = useState('');
  const [aiSonuc, setAiSonuc] = useState<AiSonucu | null>(null);
  const [secim, setSecim] = useState<{ bas: number; son: number } | null>(null);
  const alanRef = useRef<HTMLTextAreaElement | null>(null);

  const ilk = useRef(JSON.stringify([baslik, etiketMetni, icerik, stratejiIcerigi, alan, musteri, projeId, gorunurluk, sabit]));
  const kirli = JSON.stringify([baslik, etiketMetni, icerik, stratejiIcerigi, alan, musteri, projeId, gorunurluk, sabit]) !== ilk.current;

  const vazgec = () => {
    if (kirli && !window.confirm(t('belgeler.durum.kaydedilmediOnay'))) return;
    onVazgec();
  };

  // ------------------------------------------------------------------ Araç çubuğu
  const sec = (bas: number, son: number) => {
    window.requestAnimationFrame(() => {
      const a = alanRef.current;
      if (!a) return;
      a.focus();
      a.setSelectionRange(bas, son);
    });
  };

  const arac = (anahtar: AracAnahtari) => {
    const a = alanRef.current;
    const bas = a ? a.selectionStart : icerik.length;
    const son = a ? a.selectionEnd : icerik.length;
    const secili = icerik.slice(bas, son);
    const satirBasi = icerik.lastIndexOf('\n', bas - 1) + 1;
    const sar = (on: string, arka: string, yer: string) => {
      const ic = secili || yer;
      const yeni = icerik.slice(0, bas) + on + ic + arka + icerik.slice(son);
      setIcerik(yeni);
      sec(bas + on.length, bas + on.length + ic.length);
    };
    const onEk = (on: string) => {
      // Seçili her satırın başına ekle (seçim yoksa imlecin satırı).
      const bitis = son > bas ? son : bas;
      const blok = icerik.slice(satirBasi, bitis);
      const yeniBlok = blok
        .split('\n')
        .map((s, i) => (on === '1. ' ? `${i + 1}. ${s}` : on + s))
        .join('\n');
      const yeni = icerik.slice(0, satirBasi) + yeniBlok + icerik.slice(bitis);
      setIcerik(yeni);
      sec(satirBasi + yeniBlok.length, satirBasi + yeniBlok.length);
    };
    const blokEkle = (blok: string, secimBas: number, secimSon: number) => {
      const once = icerik.slice(0, bas);
      const ayrac = once && !once.endsWith('\n\n') ? (once.endsWith('\n') ? '\n' : '\n\n') : '';
      const yeni = once + ayrac + blok + '\n' + icerik.slice(son);
      setIcerik(yeni);
      const k = once.length + ayrac.length;
      sec(k + secimBas, k + secimSon);
    };
    switch (anahtar) {
      case 'baslik':
        return onEk('## ');
      case 'kalin':
        return sar('**', '**', t('belgeler.arac.metin'));
      case 'egik':
        return sar('*', '*', t('belgeler.arac.metin'));
      case 'liste':
        return onEk('- ');
      case 'numarali':
        return onEk('1. ');
      case 'yapilacak':
        return secili ? onEk('- [ ] ') : blokEkle(`- [ ] ${t('belgeler.arac.yapilacakMetni')}`, 6, 6 + t('belgeler.arac.yapilacakMetni').length);
      case 'baglanti': {
        const yazi = secili || t('belgeler.arac.baglantiMetni');
        const yeni = icerik.slice(0, bas) + `[${yazi}](https://)` + icerik.slice(son);
        setIcerik(yeni);
        const k = bas + yazi.length + 3;
        return sec(k, k + 8);
      }
      case 'tablo': {
        const b1 = t('belgeler.arac.sutun', { sayi: 1 });
        const b2 = t('belgeler.arac.sutun', { sayi: 2 });
        return blokEkle(`| ${b1} | ${b2} |\n|---|---|\n|  |  |`, 2, 2 + b1.length);
      }
      case 'kod':
        return secili.includes('\n') || !secili
          ? blokEkle('```\n' + (secili || t('belgeler.arac.kodMetni')) + '\n```', 4, 4 + (secili || t('belgeler.arac.kodMetni')).length)
          : sar('`', '`', '');
      case 'alinti':
        return onEk('> ');
    }
  };

  const onizlemeAc = async () => {
    if (onizleme !== null) {
      setOnizleme(null);
      return;
    }
    setOnizlemeYukleniyor(true);
    try {
      const y = await api.onizle(icerik);
      setOnizleme(y.html);
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setOnizlemeYukleniyor(false);
    }
  };

  // ------------------------------------------------------------------ Kaydet
  const govde = (): BelgeGovdesi => {
    const g: BelgeGovdesi = {
      baslik: baslik.trim(),
      etiketler: etiketleriAyir(etiketMetni),
      sabit,
      gorunurluk,
      icerik: strateji ? stratejiIcerigi : icerik,
    };
    if (!belge) g.tur = tur;
    else g.surum = belge.surum;
    if (yonetici) {
      g.alan = alan;
      if (alan === 'musteri') g.musteri_email = musteri.trim().toLowerCase();
      if (alan === 'proje' || (alan === 'musteri' && projeId)) g.proje_id = projeId ? Number(projeId) : null;
      if (alan === 'musteri' && !projeId) g.proje_id = null;
    }
    return g;
  };

  const kaydet = useCallback(async () => {
    if (!baslik.trim()) {
      toast.error(t('belgeler.hata.baslikGerekli'));
      return;
    }
    setKaydediliyor(true);
    try {
      const b = belge ? await api.guncelle(belge.id, govde()) : await api.olustur(govde());
      toast.success(t('belgeler.durum.kaydedildi'));
      onKaydedildi(b);
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setKaydediliyor(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, belge, baslik, etiketMetni, icerik, stratejiIcerigi, alan, musteri, projeId, gorunurluk, sabit]);

  useEffect(() => {
    const tus = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault();
        void kaydet();
      }
    };
    window.addEventListener('keydown', tus);
    return () => window.removeEventListener('keydown', tus);
  }, [kaydet]);

  // ------------------------------------------------------------------ Yapay zekâ
  const aiCalistir = async (islem: AiIslem) => {
    setAiIslem(islem);
    setAiSonuc(null);
    if (islem === 'yaz' && !talimat.trim()) return; // önce talimat istenir
    const a = alanRef.current;
    const s = a && a.selectionEnd > a.selectionStart ? { bas: a.selectionStart, son: a.selectionEnd } : null;
    setSecim(s);
    const metin = s ? icerik.slice(s.bas, s.son) : icerik;
    setAiCalisiyor(true);
    try {
      const y =
        islem === 'taslak'
          ? await api.ai({ islem, tur, isletme: stratejiIcerigi.isletme, dil: i18n.language })
          : await api.ai({ islem, metin: metin.slice(0, 12000), talimat: islem === 'yaz' ? talimat.trim() : undefined, dil: i18n.language });
      setAiSonuc(y);
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setAiCalisiyor(false);
    }
  };

  const sonaEkle = (metin: string) => {
    setIcerik((x) => (x.trimEnd() ? `${x.trimEnd()}\n\n${metin}\n` : `${metin}\n`));
    setAiSonuc(null);
    setAiIslem(null);
  };
  const degistir = (metin: string) => {
    setIcerik((x) => (secim ? x.slice(0, secim.bas) + metin + x.slice(secim.son) : metin));
    setAiSonuc(null);
    setAiIslem(null);
  };
  const kutuyaUygula = (kutu: string) => {
    const oneri = aiSonuc?.kutular?.[kutu];
    if (!oneri) return;
    setStratejiIcerigi((s) => ({ ...s, kutular: { ...s.kutular, [kutu]: oneri } }));
    setAiSonuc((y) => {
      if (!y?.kutular) return y;
      const kalan = { ...y.kutular };
      delete kalan[kutu];
      return Object.keys(kalan).length ? { ...y, kutular: kalan } : null;
    });
  };
  const tumunuUygula = () => {
    if (!aiSonuc?.kutular) return;
    setStratejiIcerigi((s) => ({ ...s, kutular: { ...s.kutular, ...aiSonuc.kutular } }));
    setAiSonuc(null);
  };

  const aiKapali = !meta.ai_hazir;
  const metinUyarilari = (aiSonuc && Array.isArray(aiSonuc.uyarilar) ? aiSonuc.uyarilar : undefined) as Uyari[] | undefined;
  const kutuUyarilari = (aiSonuc && !Array.isArray(aiSonuc.uyarilar) ? aiSonuc.uyarilar : null) as Record<string, Uyari[]> | null;
  const musteriProjeleri = alan === 'musteri' && musteri ? projeler.filter((p) => (p.client_email || '').toLowerCase() === musteri.trim().toLowerCase()) : projeler;

  return (
    <div className="space-y-4" data-testid="belge-duzenleyici">
      <div className={KART}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="flex items-center gap-2 text-lg font-semibold">
            <PenLine className="h-5 w-5 text-purple-300" aria-hidden="true" />
            {belge ? t('belgeler.duzenle.baslik') : strateji ? t(`belgeler.sablon.${tur}.ad`) : t('belgeler.yeni.belge')}
          </h3>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" className="gap-1 !bg-transparent" onClick={vazgec} data-testid="belge-vazgec">
              <X className="h-4 w-4" aria-hidden="true" />
              {t('belgeler.eylem.vazgec')}
            </Button>
            <Button size="sm" className="gap-1" onClick={() => void kaydet()} disabled={kaydediliyor} data-testid="belge-kaydet">
              {kaydediliyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Save className="h-4 w-4" aria-hidden="true" />}
              {t('belgeler.eylem.kaydet')}
            </Button>
          </div>
        </div>
        {kirli && <p className="mt-1 text-xs text-amber-200/80">{t('belgeler.durum.kaydedilmedi')}</p>}

        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <label className="block md:col-span-2">
            <span className={ALAN_ETIKETI}>{t('belgeler.alanlar.baslik')}</span>
            <Input value={baslik} onChange={(e) => setBaslik(e.target.value)} maxLength={200} className="bg-white/5" data-testid="belge-baslik" />
          </label>
          <label className="block">
            <span className={ALAN_ETIKETI}>{t('belgeler.alanlar.etiketler')}</span>
            <Input
              value={etiketMetni}
              onChange={(e) => setEtiketMetni(e.target.value)}
              placeholder={t('belgeler.alanlar.etiketIpucu')}
              className="bg-white/5"
              data-testid="belge-etiketler"
            />
          </label>
          {yonetici ? (
            <label className="block">
              <span className={ALAN_ETIKETI}>{t('belgeler.alan.baslik')}</span>
              <select className={SECIM} value={alan} onChange={(e) => setAlan(e.target.value as Alan)} data-testid="belge-alan">
                <option value="ajans">{t('belgeler.alan.ajans')}</option>
                <option value="musteri">{t('belgeler.alan.musteriSecenek')}</option>
                <option value="proje">{t('belgeler.alan.projeSecenek')}</option>
              </select>
            </label>
          ) : (
            <label className="block">
              <span className={ALAN_ETIKETI}>{t('belgeler.gorunurluk.baslik')}</span>
              <select className={SECIM} value={gorunurluk} onChange={(e) => setGorunurluk(e.target.value as Gorunurluk)} data-testid="belge-gorunurluk">
                <option value="ekip">{t('belgeler.gorunurluk.musteriEkip')}</option>
                <option value="paylasilan">{t('belgeler.gorunurluk.musteriPaylasilan')}</option>
              </select>
            </label>
          )}
          {yonetici && alan === 'musteri' && (
            <label className="block">
              <span className={ALAN_ETIKETI}>{t('belgeler.alan.musteriSec')}</span>
              <Input
                value={musteri}
                onChange={(e) => setMusteri(e.target.value)}
                list="belge-musteri-listesi"
                placeholder="musteri@ornek.com"
                className="bg-white/5"
                data-testid="belge-musteri"
              />
              <datalist id="belge-musteri-listesi">
                {musteriler.map((m) => (
                  <option key={m.eposta} value={m.eposta}>
                    {m.ad || m.eposta}
                  </option>
                ))}
              </datalist>
            </label>
          )}
          {yonetici && alan !== 'ajans' && (
            <label className="block">
              <span className={ALAN_ETIKETI}>{t('belgeler.alan.projeSec')}</span>
              <select className={SECIM} value={projeId} onChange={(e) => setProjeId(e.target.value)} data-testid="belge-proje">
                <option value="">{alan === 'proje' ? t('belgeler.alan.projeYok') : t('belgeler.alan.projesiz')}</option>
                {musteriProjeleri.map((p) => (
                  <option key={p.id} value={String(p.id)}>
                    {p.title}
                    {p.client_email ? ` — ${p.client_email}` : ''}
                  </option>
                ))}
              </select>
            </label>
          )}
          {yonetici && alan !== 'ajans' && (
            <label className="block">
              <span className={ALAN_ETIKETI}>{t('belgeler.gorunurluk.baslik')}</span>
              <select className={SECIM} value={gorunurluk} onChange={(e) => setGorunurluk(e.target.value as Gorunurluk)} data-testid="belge-gorunurluk">
                <option value="ekip">{t('belgeler.gorunurluk.ekip')}</option>
                <option value="paylasilan">{t('belgeler.gorunurluk.paylasilan')}</option>
              </select>
            </label>
          )}
          <label className="flex items-center gap-2 text-sm md:col-span-2">
            <input type="checkbox" checked={sabit} onChange={(e) => setSabit(e.target.checked)} className="h-4 w-4 accent-emerald-500" />
            {t('belgeler.alanlar.sabit')}
          </label>
        </div>
      </div>

      {/* --- Yapay zekâ --- */}
      <div className={KART} data-testid="belge-ai">
        <div className="flex flex-wrap items-center gap-2">
          <span className="mr-1 flex items-center gap-1.5 text-sm font-medium">
            <Sparkles className="h-4 w-4 text-fuchsia-300" aria-hidden="true" />
            {t('belgeler.ai.baslik')}
          </span>
          {(strateji ? (['taslak'] as AiIslem[]) : (['yaz', 'ozetle', 'duzelt'] as AiIslem[])).map((islem) => (
            <Button
              key={islem}
              size="sm"
              variant={aiIslem === islem ? 'default' : 'outline'}
              className={`gap-1 ${aiIslem === islem ? '' : '!bg-transparent'}`}
              disabled={aiKapali || aiCalisiyor || (islem === 'taslak' && !stratejiIcerigi.isletme.trim()) || ((islem === 'ozetle' || islem === 'duzelt') && !icerik.trim())}
              title={aiKapali ? t('belgeler.ai.kapali') : undefined}
              onClick={() => void aiCalistir(islem)}
              data-testid={`belge-ai-${islem}`}
            >
              {aiCalisiyor && aiIslem === islem ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <Wand2 className="h-3.5 w-3.5" aria-hidden="true" />}
              {t(`belgeler.ai.${islem}`)}
            </Button>
          ))}
        </div>
        {aiKapali ? (
          <p className="mt-2 text-xs text-amber-100" data-testid="belge-ai-kapali">{t('belgeler.ai.kapali')}</p>
        ) : (
          <p className="mt-2 text-xs text-muted-foreground">
            {strateji ? t('belgeler.ai.taslakNot') : t('belgeler.ai.secimNot')}
            {meta.kullanim && ` · ${t('belgeler.ai.kullanim', { ay: meta.kullanim.ay, bugun: meta.kullanim.bugun })}`}
          </p>
        )}
        {aiIslem === 'yaz' && !aiKapali && (
          <div className="mt-3 flex flex-col gap-2 sm:flex-row">
            <Input
              value={talimat}
              onChange={(e) => setTalimat(e.target.value)}
              placeholder={t('belgeler.ai.talimatIpucu')}
              maxLength={1000}
              className="bg-white/5"
              aria-label={t('belgeler.ai.talimat')}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && talimat.trim()) void aiCalistir('yaz');
              }}
              data-testid="belge-ai-talimat"
            />
            <Button size="sm" className="shrink-0" disabled={!talimat.trim() || aiCalisiyor} onClick={() => void aiCalistir('yaz')} data-testid="belge-ai-olustur">
              {t('belgeler.ai.olustur')}
            </Button>
          </div>
        )}
        {aiSonuc?.metin !== undefined && (
          <div className="mt-3 rounded-xl border border-fuchsia-400/30 bg-fuchsia-500/10 p-3" data-testid="belge-ai-sonuc">
            <p className="mb-1 text-xs font-medium text-fuchsia-100">
              {t('belgeler.ai.oneri')}
              {aiSonuc.sahte && <span className="ml-2 text-sky-200">({t('belgeler.ai.sahte')})</span>}
            </p>
            <pre className="overflow-auto whitespace-pre-wrap break-words font-sans text-sm text-white" style={{ maxHeight: '16rem' }}>{aiSonuc.metin}</pre>
            <AiUyarilari uyarilar={metinUyarilari} />
            <div className="mt-2 flex flex-wrap gap-2">
              {aiSonuc.islem === 'duzelt' ? (
                <Button size="sm" onClick={() => degistir(aiSonuc.metin || '')} data-testid="belge-ai-degistir">
                  {secim ? t('belgeler.ai.degistir') : t('belgeler.ai.tumunuDegistir')}
                </Button>
              ) : (
                <Button size="sm" onClick={() => sonaEkle(aiSonuc.metin || '')} data-testid="belge-ai-ekle">
                  {t('belgeler.ai.ekle')}
                </Button>
              )}
              <Button size="sm" variant="outline" className="!bg-transparent" onClick={() => { setAiSonuc(null); setAiIslem(null); }}>
                {t('belgeler.ai.reddet')}
              </Button>
            </div>
          </div>
        )}
        {aiSonuc?.kutular && (
          <div className="mt-3 flex flex-wrap items-center gap-2 rounded-xl border border-fuchsia-400/30 bg-fuchsia-500/10 p-3 text-sm text-white" data-testid="belge-ai-taslak-sonuc">
            <span>{t('belgeler.ai.taslakHazir')}</span>
            {aiSonuc.sahte && <span className="text-xs text-sky-200">({t('belgeler.ai.sahte')})</span>}
            <Button size="sm" onClick={tumunuUygula} data-testid="belge-ai-tumunu-uygula">
              {t('belgeler.ai.kabul')}
            </Button>
            <Button size="sm" variant="outline" className="!bg-transparent" onClick={() => setAiSonuc(null)}>
              {t('belgeler.ai.reddet')}
            </Button>
          </div>
        )}
      </div>

      {/* --- İçerik --- */}
      {strateji && sablon ? (
        <div className={KART}>
          <label className="mb-3 block">
            <span className={ALAN_ETIKETI}>{t('belgeler.alanlar.isletme')}</span>
            <Textarea
              value={stratejiIcerigi.isletme}
              onChange={(e) => setStratejiIcerigi((s) => ({ ...s, isletme: e.target.value }))}
              placeholder={t('belgeler.alanlar.isletmeIpucu')}
              maxLength={1000}
              rows={2}
              className="bg-white/5"
              data-testid="belge-isletme"
            />
          </label>
          <StratejiIzgarasi
            sablon={sablon}
            icerik={stratejiIcerigi}
            duzenlenebilir
            onDegis={(k, m) => setStratejiIcerigi((s) => ({ ...s, kutular: { ...s.kutular, [k]: m } }))}
            oneriler={aiSonuc?.kutular ?? null}
            oneriUyarilari={kutuUyarilari}
            onOneriUygula={kutuyaUygula}
          />
        </div>
      ) : (
        <div className={KART}>
          <div className="mb-2 flex flex-wrap items-center gap-1" role="toolbar" aria-label={t('belgeler.arac.etiket')}>
            {ARACLAR.map(({ anahtar, ikon: Ikon }) => (
              <button
                key={anahtar}
                type="button"
                onClick={() => arac(anahtar)}
                disabled={onizleme !== null}
                title={t(`belgeler.arac.${anahtar}`)}
                aria-label={t(`belgeler.arac.${anahtar}`)}
                className="rounded-md p-2 text-muted-foreground hover:bg-white/10 hover:text-white disabled:opacity-40"
                data-arac={anahtar}
              >
                <Ikon className="h-4 w-4" aria-hidden="true" />
              </button>
            ))}
            <span className="mx-1 h-5 w-px bg-white/10" aria-hidden="true" />
            <Button
              size="sm"
              variant={onizleme !== null ? 'default' : 'outline'}
              className={`gap-1 ${onizleme !== null ? '' : '!bg-transparent'}`}
              onClick={() => void onizlemeAc()}
              data-testid="belge-onizle"
            >
              {onizlemeYukleniyor ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <Eye className="h-3.5 w-3.5" aria-hidden="true" />}
              {onizleme !== null ? t('belgeler.arac.yaz') : t('belgeler.arac.onizle')}
            </Button>
          </div>
          {onizleme !== null ? (
            <div
              className="belge-icerik prose prose-invert max-w-none rounded-md border border-white/10 bg-white/[0.02] p-4"
              style={{ minHeight: '16rem' }}
              // Sunucu ham HTML'i kaçışladı ve izinli etiket listesiyle temizledi (services/guvenli_html.belge_html).
              dangerouslySetInnerHTML={{ __html: onizleme }}
              data-testid="belge-onizleme"
            />
          ) : (
            <textarea
              ref={alanRef}
              value={icerik}
              onChange={(e) => setIcerik(e.target.value)}
              className="w-full resize-y rounded-md border border-white/10 bg-white/5 p-3 font-mono text-sm leading-relaxed text-foreground"
              style={{ minHeight: '18rem' }}
              maxLength={meta.sinirlar.icerik || 100000}
              aria-label={t('belgeler.alanlar.icerik')}
              data-testid="belge-icerik"
            />
          )}
          <p className="mt-2 text-xs text-muted-foreground">{t('belgeler.arac.ipucu')}</p>
        </div>
      )}
    </div>
  );
}
