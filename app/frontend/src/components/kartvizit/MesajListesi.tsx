import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, Handshake, Loader2, Mail, Phone, RotateCcw, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { KART, tarihYaz } from '@/components/dinamikQr/ortak';
import { hataMetni, type Mesaj, type PanelMod } from '@/lib/kartvizit';

/**
 * Faz 4K — gelen kutusu: kartın "iletişim bırak" mesajları (`tur="kart"`) ya da
 * yorum sayfasının özel geri bildirimleri (`tur="yorum"`). Ajansın kendi
 * kartından gelen mesaj CRM'e de aday olarak düştüğü için yöneticide "CRM'de
 * aç" bağlantısı var; müşteri kartlarının mesajları CRM'e karışmıyor.
 */
export default function MesajListesi({
  tur,
  mod,
  getir,
  okundu,
  sil,
}: {
  tur: 'kart' | 'yorum';
  mod: PanelMod;
  getir: (p: { okunmamis?: boolean }) => Promise<{ items: Mesaj[]; okunmamis: number }>;
  okundu: (id: number, o: boolean) => Promise<unknown>;
  sil: (id: number) => Promise<unknown>;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [liste, setListe] = useState<Mesaj[] | null>(null);
  const [yalnizOkunmamis, setYalnizOkunmamis] = useState(false);
  const [hata, setHata] = useState<string | null>(null);
  const on = tur === 'kart' ? 'kartvizit.mesajlar' : 'kartvizit.geriBildirimler';

  const yukle = useCallback(async () => {
    setHata(null);
    try {
      setListe((await getir({ okunmamis: yalnizOkunmamis || undefined })).items);
    } catch (e) {
      setHata(hataMetni(t, e));
      setListe([]);
    }
  }, [getir, yalnizOkunmamis, t]);

  useEffect(() => {
    void yukle();
    // getir her çizimde yeni fonksiyon: yalnız süzgeç değişince yeniden yükle.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [yalnizOkunmamis]);

  const isaretle = async (m: Mesaj) => {
    try {
      await okundu(m.id, !m.okundu);
      setListe((l) => (l || []).map((x) => (x.id === m.id ? { ...x, okundu: !m.okundu } : x)));
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };
  const kaldir = async (m: Mesaj) => {
    if (!window.confirm(t('kartvizit.mesajlar.silOnay'))) return;
    try {
      await sil(m.id);
      setListe((l) => (l || []).filter((x) => x.id !== m.id));
      toast.success(t('kartvizit.mesajlar.silindi'));
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  return (
    <div className={`${KART} p-4 sm:p-6`} data-testid={`mesajlar-${tur}`}>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-base font-semibold">{t(`${on}.baslik`)}</h3>
          <p className="text-xs text-muted-foreground">{t(`${on}.aciklama`)}</p>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={yalnizOkunmamis} onChange={(e) => setYalnizOkunmamis(e.target.checked)} className="h-4 w-4 accent-purple-500" />
          {t('kartvizit.mesajlar.yalnizOkunmamis')}
        </label>
      </div>
      {hata && (
        <p className="mb-3 text-sm text-red-300" role="alert">
          {hata}
        </p>
      )}
      {liste === null ? (
        <div className="flex justify-center py-10 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
        </div>
      ) : liste.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted-foreground">{t(`${on}.bos`)}</p>
      ) : (
        <ul className="space-y-2.5">
          {liste.map((m) => (
            <li
              key={m.id}
              className={`rounded-xl border p-3 ${m.okundu ? 'border-white/10 bg-black/10' : 'border-purple-400/30 bg-purple-500/[0.06]'}`}
              data-testid="mesaj-satiri"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="font-medium">
                    {m.ad || t('kartvizit.mesajlar.adsiz')}
                    {!m.okundu && <span className="ms-2 rounded-full kv-mesaj-yeni px-1.5 py-0.5 text-[10px] text-purple-100">{t('kartvizit.mesajlar.yeni')}</span>}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {m.sahip_baslik || '—'} · {tarihYaz(m.created_at, dil)}
                    {mod === 'yonetici' && ` · ${m.hesap_email || t('kartvizit.liste.ajans')}`}
                  </p>
                </div>
                <div className="flex shrink-0 gap-1">
                  {m.crm_aday_id && mod === 'yonetici' && (
                    <Button size="sm" variant="ghost" className="h-8 gap-1 text-xs" asChild>
                      <a href={`/admin?sekme=crm&aday=${m.crm_aday_id}`}>
                        <Handshake className="h-3.5 w-3.5" aria-hidden="true" />
                        {t('kartvizit.mesajlar.crm')}
                      </a>
                    </Button>
                  )}
                  <Button size="sm" variant="ghost" className="h-8 w-8 p-0" onClick={() => void isaretle(m)} aria-label={t(m.okundu ? 'kartvizit.mesajlar.okunmadi' : 'kartvizit.mesajlar.okundu')} title={t(m.okundu ? 'kartvizit.mesajlar.okunmadi' : 'kartvizit.mesajlar.okundu')}>
                    {m.okundu ? <RotateCcw className="h-4 w-4" aria-hidden="true" /> : <Check className="h-4 w-4" aria-hidden="true" />}
                  </Button>
                  <Button size="sm" variant="ghost" className="h-8 w-8 p-0 text-red-300" onClick={() => void kaldir(m)} aria-label={t('kartvizit.mesajlar.sil')} title={t('kartvizit.mesajlar.sil')}>
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                  </Button>
                </div>
              </div>
              {m.mesaj && <p className="mt-2 whitespace-pre-line break-words text-sm">{m.mesaj}</p>}
              <div className="mt-2 flex flex-wrap gap-3 text-xs">
                {m.eposta && (
                  <a href={`mailto:${m.eposta}`} className="flex items-center gap-1 text-purple-300 hover:underline" dir="ltr">
                    <Mail className="h-3.5 w-3.5" aria-hidden="true" />
                    {m.eposta}
                  </a>
                )}
                {m.telefon && (
                  <a href={`tel:${m.telefon.replace(/[^\d+]/g, '')}`} className="flex items-center gap-1 text-purple-300 hover:underline" dir="ltr">
                    <Phone className="h-3.5 w-3.5" aria-hidden="true" />
                    {m.telefon}
                  </a>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
