import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, Loader2, Plus, Trash2, X } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { AiCevirDugmesi, Alan, Anahtar, CeviriAlanlari, DIS_DUGME, GorselSecici, KART, METIN_ALANI, SECIM } from '@/components/qrMenu/ortak';
import { hataMetni, type Magaza, type MenuApi, type MenuMeta, type MenuMod } from '@/lib/qrMenu';
import { DIL_ADLARI, GUNLER, type CalismaSaatleri, type Ceviriler, type MenuDili, type MenuGorsel } from '@/lib/qrMenuOrtak';

/** Faz 4M — mağaza görünümü (kimlik, diller, saatler, iletişim) ve sipariş ayarları. */

const SAAT_DILIMLERI = [
  'Europe/Istanbul',
  'Europe/London',
  'Europe/Berlin',
  'Europe/Moscow',
  'Asia/Dubai',
  'Asia/Riyadh',
  'Asia/Kolkata',
  'Asia/Shanghai',
  'Asia/Baku',
  'America/New_York',
];

export default function MagazaAyarlari({
  api,
  meta,
  magaza,
  bolum,
  yazilabilir,
  mod,
  onKaydedildi,
  onSilindi,
}: {
  api: MenuApi;
  meta: MenuMeta;
  magaza: Magaza;
  bolum: 'gorunum' | 'siparis';
  yazilabilir: boolean;
  mod: MenuMod;
  onKaydedildi: (m: Magaza) => void;
  onSilindi: () => void;
}) {
  const { t } = useTranslation();
  const [ad, setAd] = useState(magaza.ad);
  const [aciklama, setAciklama] = useState(magaza.aciklama);
  const [slug, setSlug] = useState(magaza.slug);
  const [logo, setLogo] = useState<MenuGorsel | null>(magaza.logo);
  const [kapak, setKapak] = useState<MenuGorsel | null>(magaza.kapak);
  const [tema, setTema] = useState(magaza.tema_rengi);
  const [varsayilanDil, setVarsayilanDil] = useState<MenuDili>(magaza.varsayilan_dil);
  const [ekDiller, setEkDiller] = useState<MenuDili[]>(magaza.ek_diller);
  const [ceviriler, setCeviriler] = useState<Ceviriler>(magaza.ceviriler);
  const [para, setPara] = useState(magaza.para_birimi);
  const [adres, setAdres] = useState(magaza.adres);
  const [telefon, setTelefon] = useState(magaza.telefon);
  const [whatsapp, setWhatsapp] = useState(magaza.whatsapp);
  const [saatler, setSaatler] = useState<CalismaSaatleri>(magaza.calisma_saatleri || {});
  const [saatDilimi, setSaatDilimi] = useState(magaza.saat_dilimi);
  const [aramaMotoru, setAramaMotoru] = useState(magaza.arama_motoru);
  const [aktif, setAktif] = useState(magaza.aktif);
  const [sa, setSa] = useState({ ...magaza.siparis_ayarlari, en_dusuk_tutar: String(magaza.siparis_ayarlari.en_dusuk_tutar), paket_ucreti: String(magaza.siparis_ayarlari.paket_ucreti) });
  const [saklama, setSaklama] = useState(String(magaza.saklama_gun));
  const [kaydediliyor, setKaydediliyor] = useState(false);
  const [ceviriliyor, setCeviriliyor] = useState(false);

  const govde = () =>
    bolum === 'gorunum'
      ? {
          ad: ad.trim(),
          aciklama: aciklama.trim(),
          slug: slug.trim().toLowerCase(),
          logo: logo?.anahtar ?? null,
          kapak: kapak?.anahtar ?? null,
          tema_rengi: tema,
          varsayilan_dil: varsayilanDil,
          ek_diller: ekDiller.filter((d) => d !== varsayilanDil),
          ceviriler,
          para_birimi: para,
          adres: adres.trim(),
          telefon: telefon.trim(),
          whatsapp: whatsapp.trim(),
          calisma_saatleri: saatler,
          saat_dilimi: saatDilimi.trim(),
          arama_motoru: aramaMotoru,
          aktif,
        }
      : {
          whatsapp: whatsapp.trim(),
          siparis_ayarlari: { ...sa, en_dusuk_tutar: sa.en_dusuk_tutar.trim() || '0', paket_ucreti: sa.paket_ucreti.trim() || '0' },
          saklama_gun: Number(saklama) || 90,
        };

  const kaydet = async () => {
    setKaydediliyor(true);
    try {
      const m = await api.guncelle(magaza.id, govde());
      onKaydedildi(m);
      toast.success(t('qrMenu.kaydedildi'));
      return m;
    } catch (e) {
      toast.error(hataMetni(t, e));
      return null;
    } finally {
      setKaydediliyor(false);
    }
  };

  const aiCevir = async () => {
    setCeviriliyor(true);
    try {
      if (!(await kaydet())) return;
      const y = await api.cevir(magaza.id, { tur: 'magaza' });
      const m = y.kayit as Magaza;
      setCeviriler(m.ceviriler);
      onKaydedildi(m);
      toast.success(t('qrMenu.ceviri.tamam'));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setCeviriliyor(false);
    }
  };

  const sil = async () => {
    if (!window.confirm(t('qrMenu.ayar.silOnay', { ad: magaza.ad }))) return;
    try {
      await api.sil(magaza.id);
      toast.success(t('qrMenu.ayar.silindi'));
      onSilindi();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const araligiGuncelle = (gun: string, i: number, j: 0 | 1, deger: string) => {
    const liste = [...(saatler[gun as keyof CalismaSaatleri] || [])];
    const a = [...liste[i]] as [string, string];
    a[j] = deger;
    liste[i] = a;
    setSaatler({ ...saatler, [gun]: liste });
  };

  const kaydetDugmesi = (
    <div className="flex justify-end">
      <Button onClick={() => void kaydet()} disabled={!yazilabilir || kaydediliyor} className="gap-1.5" data-testid="menu-ayar-kaydet">
        {kaydediliyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
        {t('qrMenu.kaydet')}
      </Button>
    </div>
  );

  if (bolum === 'siparis') {
    return (
      <div className={`${KART} space-y-5 p-4 sm:p-6`} data-testid="menu-siparis-ayarlari">
        {!whatsapp.trim() && (
          <p className="flex items-start gap-2 rounded-xl border border-amber-400/30 bg-amber-500/10 p-3 text-sm text-amber-100" role="status">
            <AlertTriangle className="mt-0.5 h-4 w-4 flex-none" aria-hidden="true" />
            {t('qrMenu.ayar.whatsappYok')}
          </p>
        )}
        <Alan etiket={t('qrMenu.ayar.whatsapp')} ipucu={t('qrMenu.ayar.whatsappIpucu')}>
          <Input value={whatsapp} onChange={(e) => setWhatsapp(e.target.value)} placeholder="+90 555 111 22 33" dir="ltr" inputMode="tel" data-testid="menu-ayar-whatsapp" />
        </Alan>
        <div className="grid gap-3 sm:grid-cols-2">
          <Anahtar acik={sa.whatsapp_acik} onDegis={(v) => setSa({ ...sa, whatsapp_acik: v })} etiket={t('qrMenu.ayar.whatsappSiparis')} testid="menu-ayar-wa-acik" />
          <Anahtar acik={sa.kapaliyken_siparis} onDegis={(v) => setSa({ ...sa, kapaliyken_siparis: v })} etiket={t('qrMenu.ayar.kapaliyken')} />
        </div>
        <fieldset>
          <legend className="mb-2 text-sm font-semibold">{t('qrMenu.ayar.teslimatlar')}</legend>
          <div className="flex flex-wrap gap-4">
            {(['gel_al', 'paket', 'masada'] as const).map((tur) => (
              <Anahtar key={tur} acik={sa[tur]} onDegis={(v) => setSa({ ...sa, [tur]: v })} etiket={t(`qrMenuSayfa.teslimat.${tur}`)} testid={`menu-ayar-${tur}`} />
            ))}
          </div>
        </fieldset>
        <div className="grid gap-4 sm:grid-cols-2">
          <Alan etiket={`${t('qrMenu.ayar.paketUcreti')} (${magaza.para_birimi})`}>
            <Input value={sa.paket_ucreti} onChange={(e) => setSa({ ...sa, paket_ucreti: e.target.value })} inputMode="decimal" dir="ltr" data-testid="menu-ayar-paket-ucreti" />
          </Alan>
          <Alan etiket={`${t('qrMenu.ayar.enDusuk')} (${magaza.para_birimi})`} ipucu={t('qrMenu.ayar.enDusukIpucu')}>
            <Input value={sa.en_dusuk_tutar} onChange={(e) => setSa({ ...sa, en_dusuk_tutar: e.target.value })} inputMode="decimal" dir="ltr" data-testid="menu-ayar-en-dusuk" />
          </Alan>
        </div>
        <Alan etiket={t('qrMenu.ayar.siparisNotu')} ipucu={t('qrMenu.ayar.siparisNotuIpucu')}>
          <textarea value={sa.siparis_notu} onChange={(e) => setSa({ ...sa, siparis_notu: e.target.value })} maxLength={300} className={METIN_ALANI} />
        </Alan>
        <Alan etiket={t('qrMenu.ayar.saklama')} ipucu={t('qrMenu.ayar.saklamaIpucu')}>
          <Input value={saklama} onChange={(e) => setSaklama(e.target.value.replace(/\D/g, ''))} inputMode="numeric" className="w-32" dir="ltr" />
        </Alan>
        {kaydetDugmesi}
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="menu-gorunum">
      <div className={`${KART} grid gap-4 p-4 sm:grid-cols-2 sm:p-6`}>
        <Alan etiket={t('qrMenu.ayar.ad')}>
          <Input value={ad} onChange={(e) => setAd(e.target.value)} maxLength={120} data-testid="menu-ayar-ad" />
        </Alan>
        <Alan etiket={t('qrMenu.ayar.slug')} ipucu={`${meta.menu_adres_tabani}${slug}`}>
          <Input value={slug} onChange={(e) => setSlug(e.target.value.toLowerCase())} maxLength={50} dir="ltr" data-testid="menu-ayar-slug" />
        </Alan>
        <Alan etiket={t('qrMenu.ayar.aciklama')} className="sm:col-span-2">
          <textarea value={aciklama} onChange={(e) => setAciklama(e.target.value)} maxLength={1000} className={METIN_ALANI} data-testid="menu-ayar-aciklama" />
        </Alan>
        <GorselSecici api={api} magazaId={magaza.id} gorsel={logo} onDegis={setLogo} etiket={t('qrMenu.ayar.logo')} testid="menu-ayar-logo" enCokMb={meta.gorsel_en_cok_mb} />
        <GorselSecici api={api} magazaId={magaza.id} gorsel={kapak} onDegis={setKapak} etiket={t('qrMenu.ayar.kapak')} testid="menu-ayar-kapak" enCokMb={meta.gorsel_en_cok_mb} />
        <Alan etiket={t('qrMenu.ayar.tema')}>
          <span className="flex items-center gap-2">
            <input type="color" value={tema} onChange={(e) => setTema(e.target.value)} className="h-10 w-14 cursor-pointer rounded border border-white/10 bg-transparent" aria-label={t('qrMenu.ayar.tema')} />
            <Input value={tema} onChange={(e) => setTema(e.target.value)} maxLength={7} className="w-28" dir="ltr" />
          </span>
        </Alan>
        <Alan etiket={t('qrMenu.ayar.paraBirimi')} ipucu={t('qrMenu.ayar.paraIpucu')}>
          <select className={SECIM} value={para} onChange={(e) => setPara(e.target.value)}>
            {meta.para_birimleri.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </Alan>
      </div>

      <div className={`${KART} space-y-4 p-4 sm:p-6`}>
        <h4 className="font-semibold">{t('qrMenu.ayar.diller')}</h4>
        <div className="grid gap-4 sm:grid-cols-2">
          <Alan etiket={t('qrMenu.ayar.varsayilanDil')}>
            <select className={SECIM} value={varsayilanDil} onChange={(e) => setVarsayilanDil(e.target.value as MenuDili)} data-testid="menu-ayar-varsayilan-dil">
              {meta.diller.map((d) => (
                <option key={d} value={d}>
                  {DIL_ADLARI[d]}
                </option>
              ))}
            </select>
          </Alan>
          <fieldset>
            <legend className="mb-1 text-sm font-medium">{t('qrMenu.ayar.ekDiller')}</legend>
            <div className="flex flex-wrap gap-3">
              {meta.diller
                .filter((d) => d !== varsayilanDil)
                .map((d) => (
                  <label key={d} className="flex items-center gap-1.5 text-sm">
                    <input
                      type="checkbox"
                      className="h-4 w-4 accent-purple-500"
                      checked={ekDiller.includes(d)}
                      onChange={(e) => setEkDiller((l) => (e.target.checked ? [...l, d] : l.filter((x) => x !== d)))}
                      data-ek-dil={d}
                    />
                    {DIL_ADLARI[d]}
                  </label>
                ))}
            </div>
          </fieldset>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-sm text-muted-foreground">{t('qrMenu.ceviri.magazaIpucu')}</span>
          <AiCevirDugmesi acik={meta.ai_ceviri} ekDilVar={ekDiller.filter((d) => d !== varsayilanDil).length > 0} yukleniyor={ceviriliyor} onTikla={() => void aiCevir()} testid="menu-magaza-ai" />
        </div>
        <CeviriAlanlari diller={ekDiller.filter((d) => d !== varsayilanDil)} ceviriler={ceviriler} onDegis={setCeviriler} aciklamaVar testid="menu-magaza-ceviri" />
      </div>

      <div className={`${KART} grid gap-4 p-4 sm:grid-cols-2 sm:p-6`}>
        <h4 className="font-semibold sm:col-span-2">{t('qrMenu.ayar.iletisim')}</h4>
        <Alan etiket={t('qrMenu.ayar.adres')} className="sm:col-span-2">
          <Input value={adres} onChange={(e) => setAdres(e.target.value)} maxLength={300} />
        </Alan>
        <Alan etiket={t('qrMenu.ayar.telefon')}>
          <Input value={telefon} onChange={(e) => setTelefon(e.target.value)} dir="ltr" inputMode="tel" placeholder="+90 212 000 00 00" />
        </Alan>
        <Alan etiket={t('qrMenu.ayar.whatsapp')} ipucu={t('qrMenu.ayar.whatsappIpucu')}>
          <Input value={whatsapp} onChange={(e) => setWhatsapp(e.target.value)} dir="ltr" inputMode="tel" placeholder="+90 555 111 22 33" />
        </Alan>
      </div>

      <div className={`${KART} space-y-3 p-4 sm:p-6`} data-testid="menu-ayar-saatler">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h4 className="font-semibold">{t('qrMenu.ayar.saatler')}</h4>
          <label className="block text-sm">
            <span className="mb-1 block text-muted-foreground">{t('qrMenu.ayar.saatDilimi')}</span>
            <Input value={saatDilimi} onChange={(e) => setSaatDilimi(e.target.value)} list="menu-saat-dilimleri" className="w-56" dir="ltr" />
            <datalist id="menu-saat-dilimleri">
              {SAAT_DILIMLERI.map((z) => (
                <option key={z} value={z} />
              ))}
            </datalist>
          </label>
        </div>
        <p className="text-xs text-muted-foreground">{t('qrMenu.ayar.saatIpucu')}</p>
        <ul className="divide-y divide-white/5 rounded-xl border border-white/10">
          {GUNLER.map((gun) => {
            const araliklar = saatler[gun] || [];
            return (
              <li key={gun} className="flex flex-wrap items-center gap-2 p-2.5" data-gun={gun}>
                <span className="w-28 flex-none text-sm">{t(`qrMenuSayfa.gun.${gun}`)}</span>
                {araliklar.length === 0 && <span className="text-xs text-muted-foreground">{t('qrMenuSayfa.kapali')}</span>}
                {araliklar.map((a, i) => (
                  <span key={i} className="flex items-center gap-1" dir="ltr">
                    <Input type="time" value={a[0]} onChange={(e) => araligiGuncelle(gun, i, 0, e.target.value)} className="h-8 w-[6.5rem]" aria-label={t('qrMenu.ayar.acilis')} />
                    <span aria-hidden="true">–</span>
                    <Input
                      type="time"
                      value={a[1] === '24:00' ? '23:59' : a[1]}
                      onChange={(e) => araligiGuncelle(gun, i, 1, e.target.value)}
                      className="h-8 w-[6.5rem]"
                      aria-label={t('qrMenu.ayar.kapanis')}
                    />
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-7 w-7"
                      aria-label={t('qrMenu.sil')}
                      onClick={() => setSaatler({ ...saatler, [gun]: araliklar.filter((_, j) => j !== i) })}
                    >
                      <X className="h-3.5 w-3.5" aria-hidden="true" />
                    </Button>
                  </span>
                ))}
                {araliklar.length < 3 && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-8 gap-1 text-xs"
                    onClick={() => setSaatler({ ...saatler, [gun]: [...araliklar, ['09:00', '22:00']] })}
                    data-testid="menu-saat-ekle"
                  >
                    <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                    {t('qrMenu.ayar.aralikEkle')}
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
        <Button
          size="sm"
          variant="outline"
          className={DIS_DUGME}
          onClick={() => {
            const ilk = saatler['0'] || [];
            const kopya: CalismaSaatleri = {};
            for (const g of GUNLER) kopya[g] = ilk.map((a) => [...a] as [string, string]);
            setSaatler(kopya);
          }}
        >
          {t('qrMenu.ayar.herGuneUygula')}
        </Button>
      </div>

      <div className={`${KART} space-y-3 p-4 sm:p-6`}>
        <Anahtar acik={aktif} onDegis={setAktif} etiket={t('qrMenu.ayar.aktif')} testid="menu-ayar-aktif" />
        <Anahtar acik={aramaMotoru} onDegis={setAramaMotoru} etiket={t('qrMenu.ayar.aramaMotoru')} />
        <p className="text-xs text-muted-foreground">{t('qrMenu.ayar.aramaMotoruIpucu')}</p>
      </div>

      {kaydetDugmesi}

      <div className="rounded-2xl border border-red-400/30 bg-red-500/[0.06] p-4 sm:p-6">
        <h4 className="font-semibold text-red-200">{t('qrMenu.ayar.tehlike')}</h4>
        <p className="mt-1 text-sm text-muted-foreground">{mod === 'yonetici' ? t('qrMenu.ayar.silAciklamaYonetici') : t('qrMenu.ayar.silAciklama')}</p>
        <Button variant="outline" className="mt-3 gap-1.5 border-red-400/40 !bg-transparent text-red-200" onClick={() => void sil()} data-testid="menu-ayar-sil">
          <Trash2 className="h-4 w-4" aria-hidden="true" />
          {t('qrMenu.ayar.sil')}
        </Button>
      </div>
    </div>
  );
}
