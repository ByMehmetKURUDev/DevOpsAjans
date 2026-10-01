import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { IdCard, Inbox, MessageSquareText, Star } from 'lucide-react';

import KartlarBolumu from '@/components/kartvizit/KartlarBolumu';
import MesajListesi from '@/components/kartvizit/MesajListesi';
import YorumSayfalari from '@/components/kartvizit/YorumSayfalari';
import { kartApi, yorumApi, type PanelMod } from '@/lib/kartvizit';
import '@/components/kartvizit/kartvizit.css';

/**
 * Faz 4K — "Dijital kartvizit" sekmesi. Yönetici panelinde (`mod="yonetici"`:
 * ajansın kendi kartları + müşteriler adına) ve müşteri panelinde
 * (`mod="musteri"`: etkin hesabın kartları; ekipte her kişi kendi kartını
 * yapabilir) aynı bileşen.
 *
 * Alt sekmeler: Kartlar, Kart mesajları (iletişim bırak formu), Yorum sayfaları
 * (Google), Geri bildirimler. Müşteride her bölüm kendi modülü açıksa görünüyor
 * (`dijital_kartvizit`, `google_yorum_sayfasi` ayrı satılıyor).
 * Bildirim bağlantısı `?alt=mesajlar|geri-bildirim` ilgili alt sekmeyi açıyor.
 */

type Alt = 'kartlar' | 'mesajlar' | 'yorumlar' | 'geri-bildirim';

function ilkAlt(secenekler: Alt[]): Alt {
  try {
    const istenen = new URLSearchParams(window.location.search).get('alt') as Alt | null;
    if (istenen && secenekler.includes(istenen)) return istenen;
  } catch {
    /* yoksay */
  }
  return secenekler[0] ?? 'kartlar';
}

export default function Kartvizit({ mod, kartAcik = true, yorumAcik = true }: { mod: PanelMod; kartAcik?: boolean; yorumAcik?: boolean }) {
  const { t } = useTranslation();
  const kApi = useMemo(() => kartApi(mod), [mod]);
  const yApi = useMemo(() => yorumApi(mod), [mod]);
  const secenekler = useMemo<{ key: Alt; ikon: typeof IdCard }[]>(
    () => [
      ...(kartAcik ? [{ key: 'kartlar' as Alt, ikon: IdCard }, { key: 'mesajlar' as Alt, ikon: Inbox }] : []),
      ...(yorumAcik ? [{ key: 'yorumlar' as Alt, ikon: Star }, { key: 'geri-bildirim' as Alt, ikon: MessageSquareText }] : []),
    ],
    [kartAcik, yorumAcik]
  );
  const [alt, setAlt] = useState<Alt>(() => ilkAlt(secenekler.map((s) => s.key)));
  const etkin = secenekler.some((s) => s.key === alt) ? alt : secenekler[0]?.key;

  return (
    <section aria-labelledby="kartvizit-baslik" data-testid="kartvizit-sekmesi">
      <div className="mb-5">
        <h2 id="kartvizit-baslik" className="flex items-center gap-2 text-2xl font-bold">
          <IdCard className="h-6 w-6 text-purple-300" aria-hidden="true" />
          {t('kartvizit.baslik')}
        </h2>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
          {mod === 'yonetici' ? t('kartvizit.aciklamaYonetici') : t('kartvizit.aciklama')}
        </p>
      </div>
      {secenekler.length > 1 && (
        <div className="mb-5 flex gap-1 overflow-x-auto rounded-xl border border-white/10 bg-white/[0.03] p-1" role="tablist" aria-label={t('kartvizit.baslik')}>
          {secenekler.map(({ key, ikon: Ikon }) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={etkin === key}
              onClick={() => setAlt(key)}
              className={`flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-2 text-sm transition ${
                etkin === key ? 'bg-purple-500/20 text-white' : 'text-muted-foreground hover:bg-white/5 hover:text-foreground'
              }`}
              data-testid={`kartvizit-alt-${key}`}
            >
              <Ikon className="h-4 w-4" aria-hidden="true" />
              {t(`kartvizit.alt.${key}`)}
            </button>
          ))}
        </div>
      )}
      {etkin === 'kartlar' && <KartlarBolumu api={kApi} mod={mod} />}
      {etkin === 'mesajlar' && (
        <MesajListesi
          tur="kart"
          mod={mod}
          getir={(p) => kApi.mesajlar(p)}
          okundu={(id, o) => kApi.mesajOkundu(id, o)}
          sil={(id) => kApi.mesajSil(id)}
        />
      )}
      {etkin === 'yorumlar' && <YorumSayfalari api={yApi} mod={mod} />}
      {etkin === 'geri-bildirim' && (
        <MesajListesi
          tur="yorum"
          mod={mod}
          getir={(p) => yApi.geriBildirimler(p)}
          okundu={(id, o) => yApi.geriBildirimOkundu(id, o)}
          sil={(id) => yApi.geriBildirimSil(id)}
        />
      )}
    </section>
  );
}
