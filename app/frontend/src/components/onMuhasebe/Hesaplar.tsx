import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Archive, ArrowLeftRight, CreditCard, Landmark, Loader2, Pencil, Plus, Store, Trash2, Wallet } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { VirmanFormu } from '@/components/onMuhasebe/Form';
import { Alan, Anahtar, Bos, DIS_DUGME, GIRDI, HataSatiri, KART, METIN_ALANI, Not, Pencere, Rozet, SECIM, Tutar } from '@/components/onMuhasebe/ortak';
import { bugun, hataMetni, kurusMetni, para, type BolumProps, type Hesap, type HesapTuru } from '@/lib/onMuhasebe';

const IKON = { kasa: Wallet, banka: Landmark, kredi_karti: CreditCard, pos: Store } as const;

/** Faz 6M — hesaplar: kasa, banka (IBAN yalnız son 4 hane gösterilir), kredi kartı (son 4 hane), POS / sanal POS; bakiye,
 * arşiv, virman. */
export default function Hesaplar({ api, meta, yenile }: BolumProps) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const salt = meta.salt_okunur;
  const [form, setForm] = useState<Hesap | 'yeni' | null>(null);
  const [virman, setVirman] = useState(false);
  const [hata, setHata] = useState<string | null>(null);
  const aktif = meta.hesaplar.filter((h) => !h.arsiv);
  const arsiv = meta.hesaplar.filter((h) => h.arsiv);
  const toplamlar = aktif.reduce<Record<string, number>>((a, h) => ({ ...a, [h.para_birimi]: (a[h.para_birimi] || 0) + h.bakiye }), {});

  const sil = async (h: Hesap) => {
    if (!window.confirm(t('onMuhasebe.hesap.silOnay', { ad: h.ad }))) return;
    try {
      await api.hesapSil(h.id);
      yenile();
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  };

  const arsivle = async (h: Hesap, deger: boolean) => {
    try {
      await api.hesapGuncelle(h.id, { arsiv: deger });
      yenile();
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  };

  const kart = (h: Hesap) => {
    const Ikon = IKON[h.tur];
    return (
      <li key={h.id} className={`${KART} flex flex-col gap-2 p-4 ${h.arsiv ? 'opacity-60' : ''}`} data-testid="mh-hesap" data-tur={h.tur}>
        <div className="flex items-start justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <Ikon className="h-5 w-5 flex-none text-purple-300" aria-hidden="true" />
            <div className="min-w-0">
              <p className="truncate font-semibold">{h.ad}</p>
              <p className="truncate text-xs text-muted-foreground">
                {t(`onMuhasebe.hesapTuru.${h.tur}`)}
                {h.banka_adi ? ` · ${h.banka_adi}` : ''}
                {h.iban_maske ? ` · ${h.iban_maske}` : ''}
                {h.son4 ? ` · •••• ${h.son4}` : ''}
              </p>
            </div>
          </div>
          {h.arsiv && <Rozet>{t('onMuhasebe.hesap.arsivde')}</Rozet>}
        </div>
        <p className="text-2xl font-semibold" data-testid="mh-hesap-bakiye">
          <Tutar deger={h.bakiye} metin={para(h.bakiye, h.para_birimi, dil)} notr={h.bakiye >= 0} />
        </p>
        <p className="text-xs text-muted-foreground">{t('onMuhasebe.hesap.hareketSayisi', { sayi: h.hareket_sayisi })}</p>
        {!salt && (
          <div className="flex flex-wrap gap-1">
            <Button type="button" size="sm" variant="ghost" className="h-8 gap-1 px-2" onClick={() => setForm(h)} data-testid="mh-hesap-duzenle">
              <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
              {t('onMuhasebe.ortak.duzenle')}
            </Button>
            <Button type="button" size="sm" variant="ghost" className="h-8 gap-1 px-2" onClick={() => void arsivle(h, !h.arsiv)}>
              <Archive className="h-3.5 w-3.5" aria-hidden="true" />
              {h.arsiv ? t('onMuhasebe.hesap.arsivdenCikar') : t('onMuhasebe.hesap.arsiveAl')}
            </Button>
            {h.hareket_sayisi === 0 && (
              <Button type="button" size="sm" variant="ghost" className="h-8 gap-1 px-2 text-rose-200" onClick={() => void sil(h)}>
                <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                {t('onMuhasebe.ortak.sil')}
              </Button>
            )}
          </div>
        )}
      </li>
    );
  };

  return (
    <div className="space-y-4" data-testid="mh-hesaplar">
      <div className="flex flex-wrap items-center gap-2">
        {!salt && (
          <>
            <Button type="button" size="sm" className="gap-1.5" onClick={() => setForm('yeni')} data-testid="mh-hesap-yeni">
              <Plus className="h-4 w-4" aria-hidden="true" />
              {t('onMuhasebe.hesap.yeni')}
            </Button>
            <Button type="button" size="sm" variant="outline" className={DIS_DUGME} onClick={() => setVirman(true)} disabled={aktif.length < 2} data-testid="mh-hesap-virman">
              <ArrowLeftRight className="h-4 w-4" aria-hidden="true" />
              {t('onMuhasebe.hesap.virman')}
            </Button>
          </>
        )}
        <span className="flex-1" />
        {meta.hesap_siniri !== null && (
          <span className="text-xs text-muted-foreground">{t('onMuhasebe.hesap.sinir', { sayi: aktif.length, enCok: meta.hesap_siniri })}</span>
        )}
      </div>
      {Object.keys(toplamlar).length > 0 && (
        <div className="flex flex-wrap gap-2 text-sm" data-testid="mh-hesap-toplam">
          {Object.entries(toplamlar).map(([pb, v]) => (
            <span key={pb} className={`${KART} px-3 py-2`}>
              {t('onMuhasebe.hesap.toplamBakiye')}: <b>{para(v, pb, dil)}</b>
            </span>
          ))}
        </div>
      )}
      <HataSatiri hata={hata} />
      {aktif.length ? <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{aktif.map(kart)}</ul> : <Bos>{t('onMuhasebe.hesap.bos')}</Bos>}
      {arsiv.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-muted-foreground">{t('onMuhasebe.hesap.arsivListesi', { sayi: arsiv.length })}</summary>
          <ul className="mt-2 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{arsiv.map(kart)}</ul>
        </details>
      )}
      {form && (
        <HesapFormu
          api={api}
          paraBirimleri={meta.sabitler.para_birimleri}
          turler={meta.sabitler.hesap_turleri}
          varsayilanPb={meta.ayarlar.para_birimi}
          hesap={form === 'yeni' ? null : form}
          onKaydet={() => {
            setForm(null);
            yenile();
          }}
          onKapat={() => setForm(null)}
        />
      )}
      {virman && (
        <VirmanFormu
          api={api}
          meta={meta}
          onKaydet={() => {
            setVirman(false);
            yenile();
          }}
          onKapat={() => setVirman(false)}
        />
      )}
    </div>
  );
}

function HesapFormu({
  api,
  paraBirimleri,
  turler,
  varsayilanPb,
  hesap,
  onKaydet,
  onKapat,
}: {
  api: BolumProps['api'];
  paraBirimleri: string[];
  turler: HesapTuru[];
  varsayilanPb: string;
  hesap: Hesap | null;
  onKaydet: () => void;
  onKapat: () => void;
}) {
  const { t } = useTranslation();
  const [tur, setTur] = useState<HesapTuru>(hesap?.tur ?? 'kasa');
  const [ad, setAd] = useState(hesap?.ad ?? '');
  const [bankaAdi, setBankaAdi] = useState(hesap?.banka_adi ?? '');
  // Tam IBAN sunucudan hiç gelmez: düzenlemede alan boş başlar; boş bırakılırsa kayıtlı IBAN korunur.
  const [iban, setIban] = useState('');
  const [son4, setSon4] = useState(hesap?.son4 ?? '');
  const [pb, setPb] = useState(hesap?.para_birimi ?? varsayilanPb ?? 'TRY');
  const [acilis, setAcilis] = useState(hesap ? kurusMetni(hesap.acilis_bakiyesi) : '');
  const [acilisTarihi, setAcilisTarihi] = useState(hesap?.acilis_tarihi ?? bugun());
  const [notlar, setNotlar] = useState(hesap?.notlar ?? '');
  const [arsiv, setArsiv] = useState(hesap?.arsiv ?? false);
  const [hata, setHata] = useState<string | null>(null);
  const [kaydediliyor, setKaydediliyor] = useState(false);

  const kaydet = async () => {
    setHata(null);
    setKaydediliyor(true);
    const g: Record<string, unknown> = { tur, ad, para_birimi: pb, acilis_bakiyesi: acilis, acilis_tarihi: acilisTarihi, notlar };
    if (tur !== 'kasa') g.banka_adi = bankaAdi;
    if (tur === 'banka' && (!hesap || iban.trim())) g.iban = iban;
    if (tur === 'kredi_karti') g.son4 = son4;
    if (hesap) g.arsiv = arsiv;
    try {
      if (hesap) await api.hesapGuncelle(hesap.id, g);
      else await api.hesapEkle(g);
      onKaydet();
    } catch (e) {
      setHata(hataMetni(t, e));
    } finally {
      setKaydediliyor(false);
    }
  };

  return (
    <Pencere baslik={hesap ? t('onMuhasebe.hesap.duzenle') : t('onMuhasebe.hesap.yeni')} onKapat={onKapat} testid="mh-hesap-formu">
      <div className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <Alan etiket={t('onMuhasebe.ortak.tur')}>
            <select className={SECIM} value={tur} disabled={!!hesap} onChange={(e) => setTur(e.target.value as HesapTuru)} data-testid="mh-hesap-tur">
              {turler.map((x) => (
                <option key={x} value={x}>
                  {t(`onMuhasebe.hesapTuru.${x}`)}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('onMuhasebe.hesap.ad')}>
            <input className={GIRDI} maxLength={120} value={ad} onChange={(e) => setAd(e.target.value)} data-testid="mh-hesap-ad" />
          </Alan>
          {tur !== 'kasa' && (
            <Alan etiket={tur === 'pos' ? t('onMuhasebe.hesap.saglayici') : t('onMuhasebe.hesap.banka')}>
              <input className={GIRDI} maxLength={120} value={bankaAdi} onChange={(e) => setBankaAdi(e.target.value)} data-testid="mh-hesap-banka-adi" />
            </Alan>
          )}
          {tur === 'banka' && (
            <Alan
              etiket="IBAN"
              ipucu={hesap?.iban_maske ? t('onMuhasebe.hesap.ibanKayitli', { maske: hesap.iban_maske }) : t('onMuhasebe.hesap.ibanIpucu')}
            >
              <input
                className={GIRDI}
                maxLength={42}
                value={iban}
                autoComplete="off"
                placeholder={hesap?.iban_maske || 'TR00 0000 0000 0000 0000 0000 00'}
                onChange={(e) => setIban(e.target.value)}
                data-testid="mh-hesap-iban"
              />
            </Alan>
          )}
          {tur === 'kredi_karti' && (
            <Alan etiket={t('onMuhasebe.hesap.son4')} ipucu={t('onMuhasebe.hesap.son4Ipucu')}>
              <input className={GIRDI} inputMode="numeric" maxLength={4} value={son4} onChange={(e) => setSon4(e.target.value.replace(/\D/g, ''))} data-testid="mh-hesap-son4" />
            </Alan>
          )}
          <Alan etiket={t('onMuhasebe.ortak.paraBirimi')}>
            <select className={SECIM} value={pb} onChange={(e) => setPb(e.target.value)} data-testid="mh-hesap-pb">
              {paraBirimleri.map((x) => (
                <option key={x} value={x}>
                  {x}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('onMuhasebe.hesap.acilis')} ipucu={tur === 'kredi_karti' ? t('onMuhasebe.hesap.kartAcilisIpucu') : undefined}>
            <input className={GIRDI} inputMode="decimal" placeholder="0,00" value={acilis} onChange={(e) => setAcilis(e.target.value)} data-testid="mh-hesap-acilis" />
          </Alan>
          <Alan etiket={t('onMuhasebe.hesap.acilisTarihi')}>
            <input type="date" className={GIRDI} value={acilisTarihi} onChange={(e) => setAcilisTarihi(e.target.value)} />
          </Alan>
          <Alan etiket={t('onMuhasebe.hesap.notlar')} className="sm:col-span-2">
            <textarea className={METIN_ALANI} maxLength={1000} value={notlar} onChange={(e) => setNotlar(e.target.value)} />
          </Alan>
        </div>
        {hesap && <Anahtar acik={arsiv} onDegis={setArsiv} etiket={t('onMuhasebe.hesap.arsiveAl')} />}
        <Not>{t('onMuhasebe.hesap.guvenlikNot')}</Not>
        <HataSatiri hata={hata} />
        <div className="flex flex-wrap justify-end gap-2">
          <Button type="button" variant="outline" className={DIS_DUGME} onClick={onKapat}>
            {t('onMuhasebe.ortak.iptal')}
          </Button>
          <Button type="button" onClick={() => void kaydet()} disabled={kaydediliyor || !ad.trim()} data-testid="mh-hesap-kaydet">
            {kaydediliyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {t('onMuhasebe.ortak.kaydet')}
          </Button>
        </div>
      </div>
    </Pencere>
  );
}
