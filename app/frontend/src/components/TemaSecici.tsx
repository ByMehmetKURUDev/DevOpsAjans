import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Check } from 'lucide-react';
import { temaOku, temaYaz, type Tema } from '@/lib/tema';

/**
 * Renk teması tuşu — dil seçicinin yanında.
 *
 * Kaydırmalı bir anahtar: arkadaki yuvarlak seçili renge kayıyor, seçili
 * örneğin üstünde onay işareti çıkıyor. Böylece "hangisi seçili" rengi
 * ayırt edemeyen biri için de belli oluyor; yalnızca renkle anlatmak
 * erişilebilir değil.
 *
 * Renk örnekleri temanın kendi değişkeninden değil SABİT değerlerden
 * çiziliyor. Değişkenden alsaydık yeşil temadayken yeşil örnek de yeşile
 * döner, iki seçenek birbirinin aynısı görünürdü.
 *
 * `radiogroup` olarak işaretli: ekran okuyucu "Yeşil, seçili, 2/2" diye
 * okuyor. Ok tuşlarıyla da geçilebiliyor — klavye kullanan biri tek tek
 * sekme tuşuna basmak zorunda kalmıyor.
 */

const SECENEKLER: { anahtar: Tema; ornek: string; golge: string }[] = [
  { anahtar: 'mor', ornek: 'linear-gradient(140deg,#a855f7,#8b3dff 55%,#5c27a3)', golge: '139,61,255' },
  { anahtar: 'yesil', ornek: 'linear-gradient(140deg,#4ce9b4,#00dc82 55%,#38bdf8)', golge: '0,220,130' },
];

interface TemaSeciciProps {
  /** Mobil menüde tuşlar biraz daha büyük. */
  buyuk?: boolean;
}

export default function TemaSecici({ buyuk = false }: TemaSeciciProps) {
  const { t } = useTranslation();
  const [tema, setTema] = useState<Tema>('mor');

  // İlk boyamada gerçek tema `index.html` tarafından zaten uygulanmış
  // oluyor; buradaki okuma yalnızca tuşu o duruma getirmek için.
  useEffect(() => setTema(temaOku()), []);

  const sec = (yeni: Tema) => {
    temaYaz(yeni);
    setTema(yeni);
  };

  /** Ok tuşları seçenekler arasında dolaşsın. */
  const klavye = (olay: React.KeyboardEvent) => {
    if (!['ArrowRight', 'ArrowLeft', 'ArrowUp', 'ArrowDown'].includes(olay.key)) return;
    olay.preventDefault();
    const simdiki = SECENEKLER.findIndex((s) => s.anahtar === tema);
    const yon = olay.key === 'ArrowRight' || olay.key === 'ArrowDown' ? 1 : -1;
    sec(SECENEKLER[(simdiki + yon + SECENEKLER.length) % SECENEKLER.length].anahtar);
  };

  // Kutu ölçüleri tek yerden: kayan yuvarlağın konumu bunlardan hesaplanıyor.
  const kutu = buyuk ? 34 : 26;
  const bosluk = buyuk ? 6 : 4;
  const ic = buyuk ? 4 : 3;
  const seciliSira = SECENEKLER.findIndex((s) => s.anahtar === tema);

  return (
    <div
      role="radiogroup"
      aria-label={t('tema.baslik')}
      onKeyDown={klavye}
      className="relative inline-flex items-center rounded-full border border-white/12 bg-white/[0.04] shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]"
      style={{ padding: ic, gap: bosluk }}
    >
      {/* Kayan yuvarlak — seçili örneğin arkasında duruyor. */}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute rounded-full bg-white/10 ring-1 ring-white/25 transition-transform duration-300 ease-out motion-reduce:transition-none"
        style={{
          width: kutu,
          height: kutu,
          insetInlineStart: ic,
          top: ic,
          transform: `translateX(${seciliSira * (kutu + bosluk)}px)`,
        }}
      />

      {SECENEKLER.map(({ anahtar, ornek, golge }) => {
        const aktif = tema === anahtar;
        return (
          <button
            key={anahtar}
            type="button"
            role="radio"
            aria-checked={aktif}
            tabIndex={aktif ? 0 : -1}
            title={t(`tema.${anahtar}`)}
            onClick={() => sec(anahtar)}
            className="relative grid place-items-center rounded-full outline-none"
            style={{ width: kutu, height: kutu }}
          >
            <span
              className={`grid place-items-center rounded-full transition-all duration-300 ease-out motion-reduce:transition-none ${
                aktif ? 'scale-100' : 'scale-[0.78] opacity-50 hover:scale-90 hover:opacity-90'
              }`}
              style={{
                width: kutu - (buyuk ? 10 : 8),
                height: kutu - (buyuk ? 10 : 8),
                backgroundImage: ornek,
                boxShadow: aktif ? `0 0 0 1px rgba(255,255,255,.35), 0 0 12px rgba(${golge},.55)` : 'none',
              }}
            >
              <Check
                className={`text-white drop-shadow transition-opacity duration-200 motion-reduce:transition-none ${
                  aktif ? 'opacity-100' : 'opacity-0'
                }`}
                style={{ width: buyuk ? 14 : 11, height: buyuk ? 14 : 11 }}
                strokeWidth={3.5}
                aria-hidden="true"
              />
            </span>
            <span className="sr-only">{t(`tema.${anahtar}`)}</span>
          </button>
        );
      })}
    </div>
  );
}
