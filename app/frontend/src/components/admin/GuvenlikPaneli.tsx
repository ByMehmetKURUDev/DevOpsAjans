import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Filter, Loader2, LogOut, RefreshCw, ShieldAlert, ShieldCheck, XCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { goreliZaman, tamZaman } from '@/lib/denetim';
import {
  GuvenlikHatasi,
  kullaniciyiCikar,
  oturumListesi,
  oturumuKapat,
  type YoneticiOturumu,
} from '@/lib/guvenlik';

/**
 * Yönetici paneli › Güvenlik.
 *
 * Açık oturumlar (kim, hangi cihazdan, en son ne zaman). Tek bir oturum
 * kapatılabilir ya da bir kullanıcı bütün cihazlardan çıkarılabilir — o
 * kullanıcının bu ana kadar aldığı bütün jetonlar (eski usul, oturumsuz
 * olanlar dahil) geçersiz olur. Yönetici kendi şu anki oturumunu buradan
 * kapatamaz (sunucu da reddediyor); bunun için "Çıkış yap" var.
 */

const ADET = 50;

function hataMetni(t: (k: string, o?: Record<string, unknown>) => string, hata: unknown): string {
  const kod = hata instanceof GuvenlikHatasi ? hata.kod : 'genel';
  return t(`guvenlik.hataKod.${kod}`, { defaultValue: t('guvenlik.hataKod.genel') });
}

export default function GuvenlikPaneli() {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [satirlar, setSatirlar] = useState<YoneticiOturumu[]>([]);
  const [toplam, setToplam] = useState(0);
  const [sayfa, setSayfa] = useState(1);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [hata, setHata] = useState(false);
  const [eposta, setEposta] = useState('');
  const [yalnizEtkin, setYalnizEtkin] = useState(true);
  const [filtre, setFiltre] = useState<{ email: string; yalniz_etkin: boolean }>({ email: '', yalniz_etkin: true });
  const [cikarEposta, setCikarEposta] = useState('');
  const [calisan, setCalisan] = useState<string | null>(null);

  const yukle = useCallback(
    async (hangiSayfa = 1) => {
      setYukleniyor(true);
      setHata(false);
      try {
        const g = await oturumListesi(filtre, hangiSayfa, ADET);
        setSatirlar((onceki) => (hangiSayfa === 1 ? g.items : [...onceki, ...g.items]));
        setToplam(g.toplam);
        setSayfa(hangiSayfa);
      } catch {
        setHata(true);
      } finally {
        setYukleniyor(false);
      }
    },
    [filtre]
  );

  useEffect(() => {
    void yukle(1);
  }, [yukle]);

  const filtrele = (e: FormEvent) => {
    e.preventDefault();
    setFiltre({ email: eposta.trim(), yalniz_etkin: yalnizEtkin });
  };

  const cihazAdi = (s: YoneticiOturumu) => s.cihaz || t('guvenlik.bilinmeyenCihaz');

  const kapat = async (s: YoneticiOturumu) => {
    if (!window.confirm(t('guvenlik.kapatOnay', { cihaz: cihazAdi(s), eposta: s.email }))) return;
    setCalisan(`kapat-${s.id}`);
    try {
      await oturumuKapat(s.id);
      toast.success(t('guvenlik.kapatildi'));
      await yukle(1);
    } catch (h) {
      toast.error(hataMetni(t, h));
    } finally {
      setCalisan(null);
    }
  };

  const cikar = async (e: FormEvent) => {
    e.preventDefault();
    const hedef = cikarEposta.trim().toLowerCase();
    if (!hedef) return;
    if (!window.confirm(t('guvenlik.cikar.onay', { eposta: hedef }))) return;
    setCalisan('cikar');
    try {
      const g = await kullaniciyiCikar(hedef);
      toast.success(t('guvenlik.cikar.basarili', { eposta: hedef, sayi: g.kapatilan }));
      setCikarEposta('');
      await yukle(1);
    } catch (h) {
      toast.error(hataMetni(t, h));
    } finally {
      setCalisan(null);
    }
  };

  const durum = (s: YoneticiOturumu) => {
    if (s.iptal_zamani) return { metin: t('guvenlik.durum.iptal'), sinif: 'border-red-400/30 bg-red-500/10 text-red-300' };
    if (!s.etkin) return { metin: t('guvenlik.durum.bitti'), sinif: 'border-white/10 bg-white/5 text-muted-foreground' };
    return { metin: t('guvenlik.durum.etkin'), sinif: 'border-emerald-400/30 bg-emerald-500/10 text-emerald-300' };
  };

  return (
    <div className="space-y-6" data-testid="guvenlik-paneli">
      <div className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="flex items-center gap-2 text-xl font-semibold">
              <ShieldCheck className="h-5 w-5 text-purple-400" aria-hidden="true" />
              {t('guvenlik.baslik')}
            </h2>
            <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t('guvenlik.aciklama')}</p>
          </div>
          <Button variant="outline" size="icon" onClick={() => void yukle(1)} aria-label={t('guvenlik.yenile')}>
            <RefreshCw className={`h-4 w-4 ${yukleniyor ? 'animate-spin' : ''}`} aria-hidden="true" />
          </Button>
        </div>

        <form onSubmit={filtrele} className="mt-5 flex flex-wrap items-end gap-3">
          <label className="min-w-[14rem] flex-1 text-xs text-muted-foreground">
            {t('guvenlik.filtre.eposta')}
            <Input
              value={eposta}
              onChange={(e) => setEposta(e.target.value)}
              placeholder={t('guvenlik.filtre.epostaOrnek')}
              className="mt-1 bg-white/5 border-white/10"
              data-testid="guvenlik-eposta"
            />
          </label>
          <label className="flex h-10 items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={yalnizEtkin}
              onChange={(e) => setYalnizEtkin(e.target.checked)}
              className="h-4 w-4 accent-purple-500"
            />
            {t('guvenlik.filtre.yalnizEtkin')}
          </label>
          <Button type="submit" variant="outline" className="h-10">
            <Filter className="mr-2 h-4 w-4" aria-hidden="true" />
            {t('guvenlik.filtre.uygula')}
          </Button>
        </form>
      </div>

      <form
        onSubmit={cikar}
        className="cam-kart rounded-2xl border border-red-400/20 bg-red-500/[0.03] p-6"
        data-testid="guvenlik-cikar-formu"
      >
        <h3 className="flex items-center gap-2 font-semibold">
          <ShieldAlert className="h-5 w-5 text-red-300" aria-hidden="true" />
          {t('guvenlik.cikar.baslik')}
        </h3>
        <p className="mt-1 text-sm text-muted-foreground">{t('guvenlik.cikar.aciklama')}</p>
        <div className="mt-4 flex flex-wrap items-end gap-3">
          <label className="min-w-[14rem] flex-1 text-xs text-muted-foreground">
            {t('guvenlik.cikar.eposta')}
            <Input
              type="email"
              value={cikarEposta}
              onChange={(e) => setCikarEposta(e.target.value)}
              className="mt-1 bg-white/5 border-white/10"
              data-testid="guvenlik-cikar-eposta"
            />
          </label>
          <Button
            type="submit"
            disabled={!cikarEposta.trim() || calisan === 'cikar'}
            className="h-10 bg-red-600/80 text-white hover:bg-red-600"
            data-testid="guvenlik-cikar"
          >
            {calisan === 'cikar' ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <LogOut className="mr-2 h-4 w-4" aria-hidden="true" />
            )}
            {t('guvenlik.cikar.dugme')}
          </Button>
        </div>
      </form>

      <div className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-2 sm:p-4">
        {yukleniyor && satirlar.length === 0 ? (
          <div className="flex justify-center py-10 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
          </div>
        ) : hata ? (
          <p className="p-4 text-sm text-red-300">{t('guvenlik.hata')}</p>
        ) : satirlar.length === 0 ? (
          <p className="p-4 text-sm text-muted-foreground" data-testid="guvenlik-bos">
            {t('guvenlik.bos')}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="text-xs text-muted-foreground">
                <tr className="border-b border-white/10">
                  <th className="px-3 py-2 font-medium">{t('guvenlik.sutun.kisi')}</th>
                  <th className="px-3 py-2 font-medium">{t('guvenlik.sutun.cihaz')}</th>
                  <th className="px-3 py-2 font-medium">{t('guvenlik.sutun.acilis')}</th>
                  <th className="px-3 py-2 font-medium">{t('guvenlik.sutun.sonGorulme')}</th>
                  <th className="px-3 py-2 font-medium">{t('guvenlik.sutun.durum')}</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {satirlar.map((s) => {
                  const d = durum(s);
                  return (
                    <tr key={s.id} className="border-b border-white/5 align-top last:border-0" data-testid={`oturum-satiri-${s.id}`}>
                      <td className="px-3 py-3">
                        <span className="block break-all">{s.email}</span>
                        <span className="text-[11px] text-muted-foreground">
                          {t(`guvenlik.rol.${s.rol === 'admin' ? 'admin' : 'user'}`)}
                        </span>
                      </td>
                      <td className="px-3 py-3">
                        <span className="flex flex-wrap items-center gap-2">
                          {cihazAdi(s)}
                          {s.bu_cihaz && (
                            <span className="rounded-full border border-purple-400/30 bg-purple-500/10 px-2 py-0.5 text-[11px] text-purple-200">
                              {t('guvenlik.buCihaz')}
                            </span>
                          )}
                        </span>
                        {s.ip_ozet && (
                          <span className="block font-mono text-[11px] text-muted-foreground" title={t('guvenlik.sutun.ip')}>
                            {t('guvenlik.sutun.ip')}: {s.ip_ozet}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-3 whitespace-nowrap" title={tamZaman(s.olusturma, dil)}>
                        {goreliZaman(s.olusturma, dil)}
                      </td>
                      <td className="px-3 py-3 whitespace-nowrap" title={tamZaman(s.son_gorulme, dil)}>
                        {goreliZaman(s.son_gorulme, dil)}
                      </td>
                      <td className="px-3 py-3">
                        <span className={`inline-block whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] ${d.sinif}`}>
                          {d.metin}
                        </span>
                        {s.iptal_eden && (
                          <span className="mt-1 block break-all text-[11px] text-muted-foreground">
                            {t('guvenlik.iptalEden', { kisi: s.iptal_eden })}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-3 text-right">
                        {s.etkin && !s.bu_cihaz && (
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={calisan === `kapat-${s.id}`}
                            onClick={() => void kapat(s)}
                            data-testid={`oturum-kapat-${s.id}`}
                          >
                            {calisan === `kapat-${s.id}` ? (
                              <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                            ) : (
                              <XCircle className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
                            )}
                            {t('guvenlik.kapat')}
                          </Button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {satirlar.length > 0 && (
          <div className="flex flex-wrap items-center justify-between gap-2 px-3 pt-3 text-xs text-muted-foreground">
            <span>{t('guvenlik.gosterilen', { sayi: satirlar.length, toplam })}</span>
            {satirlar.length < toplam && (
              <Button variant="outline" size="sm" disabled={yukleniyor} onClick={() => void yukle(sayfa + 1)}>
                {t('guvenlik.dahaFazla')}
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
