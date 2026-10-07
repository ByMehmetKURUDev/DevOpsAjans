import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Banknote,
  Camera,
  CheckCircle2,
  CloudOff,
  CloudUpload,
  CreditCard,
  FileText,
  Landmark,
  Loader2,
  Lock,
  Minus,
  Percent,
  Plus,
  Receipt,
  RotateCcw,
  Search,
  Shuffle,
  Trash2,
  UserRound,
  Wifi,
  WifiOff,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Alan, Anahtar, DIS_DUGME, GIRDI, KART, Pencere, Rozet, SECIM } from '@/components/stokPos/ortak';
import { Fis, ZRaporu } from '@/components/stokPos/Fis';
import { KuyrukPaneli, useKuyruk } from '@/components/stokPos/Kuyruk';
import {
  cevrimdisiNo,
  hesapOzeti,
  katalogOku,
  katalogUrunu,
  katalogYaz,
  koddanBul,
  sonrakiSira,
  stokDus,
  yerelAra,
  type Katalog,
} from '@/lib/posKuyruk';
import {
  StokHatasi,
  hataMetni,
  kurusaCevir,
  miktarYaz,
  para,
  sayiCevir,
  sepetHesapla,
  tarihSaat,
  yeniKimlik,
  yerelSepetOku,
  yerelSepetYaz,
  yuvarla,
  type Alici,
  type Meta,
  type OdemeTuru,
  type Oturum,
  type Ozet,
  type Satis,
  type SatisOzeti,
  type SepetKalemi,
  type StokApi,
  type Urun,
} from '@/lib/stokPos';

/** Kasa ekranının ürün kartı: sunucudan gelen ürün ya da çevrimdışı katalog satırı. */
type KasaUrunu = Pick<Urun, 'id' | 'ad' | 'barkod' | 'birim' | 'satis_fiyati' | 'kdv_orani' | 'stok_takibi' | 'kritik' | 'stok'>;
type Mesaj = { tur: 'hata' | 'bilgi' | 'ag' | 'uyari'; metin: string; kuyrukTeklif?: boolean };
/** Bağlantı varken çevrimdışı kataloğun tazelenme aralığı. */
const KATALOG_ARALIGI_MS = 5 * 60_000;

const Okutucu = lazy(() => import('@/components/stokPos/Okutucu'));

const tl = (kurus: number) => (kurus / 100).toFixed(2);
const ODEMELER: { tur: OdemeTuru; ikon: typeof Banknote }[] = [
  { tur: 'nakit', ikon: Banknote },
  { tur: 'kart', ikon: CreditCard },
  { tur: 'havale', ikon: Landmark },
  { tur: 'karma', ikon: Shuffle },
];

/**
 * Faz 6P — kasa (POS) ekranı: dokunmatik/mobil uyumlu. Barkod okuyucu (USB/Bluetooth) klavye gibi yazar —
 * arama alanı odakta; Enter'da önce birebir barkod/SKU aranır. Kamera (`BarcodeDetector`) desteklenen
 * tarayıcıda. Sepet her değişimde bu cihazda saklanır (ağ koparsa satış kaybolmasın); satış sunucuda
 * yeniden hesaplanır ve `istemci_kimligi` (UUID) ile tekrar gönderimde tek kayıt olur.
 *
 * Faz 6Q — çevrimdışı kuyruk: kasa SAYFASI AÇIKKEN bağlantı koparsa satışa devam edilir. Ürün kataloğu (fiyat,
 * KDV, şube stoku) son eşitlemede cihaza (IndexedDB; yoksa bellek) alınır; arama/okutma ondan yapılır. İlk
 * çevrimdışı satışta kasiyer onaylar ("kuyruğa al"), sonrakiler doğrudan "ÇEVRİMDIŞI-n" fişiyle kuyruğa yazılır
 * (fiş "çevrimdışı — eşitlenecek" notuyla basılabilir). Bağlantı gelince kuyruk sırayla gönderilir
 * (`Kuyruk.tsx`). Sayfanın internetsiz SIFIRDAN açılması kapsam dışı (arayüzde yazılı).
 */
export default function Kasa({ api, meta, onMeta, onKuyruk }: { api: StokApi; meta: Meta; onMeta: () => void; onKuyruk?: (sayi: number) => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const pb = meta.ayarlar.para_birimi;
  const p = useCallback((n: number) => para(n, pb, dil), [pb, dil]);
  const konumlar = meta.konumlar.filter((k) => k.aktif);
  const [konumId, setKonumId] = useState<number>(() => (konumlar.find((k) => k.varsayilan) || konumlar[0])?.id);
  const [oturumlar, setOturumlar] = useState<Oturum[]>(meta.acik_oturumlar);
  const oturum = oturumlar.find((o) => o.konum_id === konumId) || null;

  const yerel = useMemo(() => yerelSepetOku(meta.hesap), [meta.hesap]);
  const [kalemler, setKalemler] = useState<SepetKalemi[]>(yerel?.kalemler || []);
  const [toplamIndirim, setToplamIndirim] = useState<number>(yerel?.toplamIndirim || 0);
  const [kimlik, setKimlik] = useState<string>(yerel?.istemciKimligi || yeniKimlik());
  const [musteriAd, setMusteriAd] = useState(yerel?.musteriAd || '');
  const [alici, setAlici] = useState<Alici | null>(null);
  const [geriYuklendi] = useState(!!yerel?.kalemler.length);

  const [ara, setAra] = useState('');
  const [sonuclar, setSonuclar] = useState<KasaUrunu[] | null>(null);
  const [hizli, setHizli] = useState<KasaUrunu[]>([]);
  const [katalog, setKatalog] = useState<Katalog | null>(null);
  const katalogRef = useRef<Katalog | null>(null);
  katalogRef.current = katalog;
  /** Bu kopuşta kasiyer çevrimdışı satışı onayladı (bağlantı gelince sıfırlanır). */
  const [cevrimdisiOnay, setCevrimdisiOnay] = useState(false);
  const [odemeTuru, setOdemeTuru] = useState<OdemeTuru>('nakit');
  const [alinan, setAlinan] = useState('');
  const [kartTutar, setKartTutar] = useState('');
  const [havaleTutar, setHavaleTutar] = useState('');
  const [mesgul, setMesgul] = useState(false);
  const [mesaj, setMesaj] = useState<Mesaj | null>(null);
  const [fis, setFis] = useState<Satis | null>(null);
  const [sonSatislar, setSonSatislar] = useState<SatisOzeti[]>([]);
  const [okutucu, setOkutucu] = useState(false);
  const [cevrimici, setCevrimici] = useState(() => (typeof navigator === 'undefined' ? true : navigator.onLine !== false));
  const [iadeSatis, setIadeSatis] = useState<Satis | null>(null);
  const [faturaSatis, setFaturaSatis] = useState<Satis | null>(null);
  const [kapanis, setKapanis] = useState<{ ozet: Ozet; oturum: Oturum } | null>(null);
  const [zGoster, setZGoster] = useState<{ ozet: Ozet; oturum: Oturum } | null>(null);
  const [indirimSatiri, setIndirimSatiri] = useState<number | null>(null);
  const [aliciPencere, setAliciPencere] = useState(false);
  const [acilisNakit, setAcilisNakit] = useState('');
  const aramaRef = useRef<HTMLInputElement | null>(null);

  const toplamlar = useMemo(() => sepetHesapla(kalemler, toplamIndirim), [kalemler, toplamIndirim]);
  const iadeYetkisi = meta.yetki.stok || meta.ayarlar.kasa_iade;

  // ------------------------------------------------------------ yerel sepet
  useEffect(() => {
    yerelSepetYaz(meta.hesap, { kalemler, toplamIndirim, istemciKimligi: kimlik, musteriAd, aliciId: alici?.id ?? null });
  }, [meta.hesap, kalemler, toplamIndirim, kimlik, musteriAd, alici]);

  // ------------------------------------------------------------ çevrimdışı katalog (Faz 6Q)
  const katalogEsitle = useCallback(async () => {
    try {
      const urunler: Urun[] = [];
      for (let sayfa = 1; sayfa <= 20; sayfa++) {
        const r = await api.urunler({ adet: 500, sayfa });
        urunler.push(...r.items);
        if (!r.items.length || urunler.length >= r.toplam) break;
      }
      const k: Katalog = { hesap: meta.hesap, zaman: new Date().toISOString(), urunler: urunler.map(katalogUrunu) };
      await katalogYaz(k);
      setKatalog(k);
    } catch {
      /* bağlantı yok: eldeki katalog kalır */
    }
  }, [api, meta.hesap]);

  useEffect(() => {
    let iptal = false;
    void katalogOku(meta.hesap).then((k) => {
      if (!iptal && k && !katalogRef.current) setKatalog(k);
    });
    void katalogEsitle();
    const z = window.setInterval(() => {
      if (navigator.onLine !== false) void katalogEsitle();
    }, KATALOG_ARALIGI_MS);
    return () => {
      iptal = true;
      window.clearInterval(z);
    };
  }, [katalogEsitle, meta.hesap]);

  const yerelStokDus = useCallback(
    (satilan: { urun_id: number; adet: number }[]) => {
      setKatalog((k) => {
        if (!k) return k;
        const yeni = { ...k, urunler: stokDus(k.urunler, satilan, konumId) };
        void katalogYaz(yeni);
        return yeni;
      });
      setHizli((l) => stokDus(l, satilan, konumId));
      setSonuclar((l) => (l ? stokDus(l, satilan, konumId) : l));
    },
    [konumId]
  );

  // Okuyucu cihaz klavye gibi yazar: odak başka bir alanda değilse arama alanına taşı.
  useEffect(() => {
    const tus = (e: KeyboardEvent) => {
      const hedef = e.target as HTMLElement | null;
      if (!hedef || ['INPUT', 'TEXTAREA', 'SELECT'].includes(hedef.tagName) || hedef.isContentEditable) return;
      if (e.ctrlKey || e.metaKey || e.altKey || e.key.length !== 1) return;
      if (document.querySelector('[role=dialog]')) return;
      aramaRef.current?.focus();
    };
    window.addEventListener('keydown', tus);
    return () => window.removeEventListener('keydown', tus);
  }, []);

  const sonSatislariYukle = useCallback(async () => {
    if (!oturum) return setSonSatislar([]);
    try {
      setSonSatislar((await api.satislar({ oturum_id: oturum.id })).items);
    } catch {
      /* liste ikincil */
    }
  }, [api, oturum]);

  useEffect(() => {
    void sonSatislariYukle();
  }, [sonSatislariYukle]);

  useEffect(() => {
    api
      .urunler({ adet: 24 })
      .then((r) => setHizli(r.items))
      .catch(() =>
        // Çevrimdışı: son eşitlenen katalogdan
        katalogOku(meta.hesap).then((k) => k && setHizli(k.urunler.slice(0, 24)))
      );
  }, [api, meta.hesap]);

  const oturumlariYenile = useCallback(async () => {
    try {
      setOturumlar((await api.kasa()).acik);
    } catch (e) {
      setMesaj({ tur: 'hata', metin: hataMetni(t, e) });
    }
  }, [api, t]);

  // ------------------------------------------------------------ çevrimdışı kuyruk (Faz 6Q)
  const kuyruk = useKuyruk(api, meta, (gonderilen, hatali) => {
    const eksi = [...new Set(gonderilen.flatMap((s) => (s.eksi_stok || []).map((e) => e.ad)))];
    const metin = [
      gonderilen.length ? t('stokPos.kuyruk.esitlendi', { sayi: gonderilen.length }) : '',
      hatali ? t('stokPos.kuyruk.cozumBekliyor', { sayi: hatali }) : '',
      eksi.length ? t('stokPos.kuyruk.eksiDustu', { urunler: eksi.join(', ') }) : '',
    ]
      .filter(Boolean)
      .join(' ');
    setMesaj({ tur: hatali || eksi.length ? 'uyari' : 'bilgi', metin });
    void sonSatislariYukle();
    void oturumlariYenile();
    void katalogEsitle();
    if (gonderilen.some((s) => s.kritik?.length)) onMeta();
  });
  const kuyrukEsitle = kuyruk.esitle;

  useEffect(() => {
    onKuyruk?.(kuyruk.kayitlar.length);
  }, [kuyruk.kayitlar.length, onKuyruk]);

  useEffect(() => {
    const ac = () => {
      setCevrimici(true);
      setCevrimdisiOnay(false);
      void kuyrukEsitle();
    };
    const kapa = () => setCevrimici(false);
    window.addEventListener('online', ac);
    window.addEventListener('offline', kapa);
    return () => {
      window.removeEventListener('online', ac);
      window.removeEventListener('offline', kapa);
    };
  }, [kuyrukEsitle]);

  // Kasa ekranı açılınca (bağlantı varsa) önceki oturumdan kalan kuyruk gönderilir.
  useEffect(() => {
    if (navigator.onLine !== false) void kuyrukEsitle();
  }, [kuyrukEsitle]);

  // ------------------------------------------------------------ sepet
  const ekle = useCallback((u: KasaUrunu) => {
    setMesaj(null);
    setKalemler((liste) => {
      const i = liste.findIndex((k) => k.urun_id === u.id);
      if (i >= 0) {
        const kopya = [...liste];
        kopya[i] = { ...kopya[i], adet: Math.round((kopya[i].adet + 1) * 1000) / 1000 };
        return kopya;
      }
      return [
        ...liste,
        { urun_id: u.id, ad: u.ad, barkod: u.barkod, birim: u.birim, birim_fiyat: u.satis_fiyati, kdv_orani: u.kdv_orani, adet: 1, indirim: 0 },
      ];
    });
  }, []);

  const adetDegistir = (i: number, adet: number) => {
    setKalemler((liste) => {
      const kopya = [...liste];
      const k = kopya[i];
      const tam = k.birim === 'adet' || k.birim === 'paket';
      const yeni = tam ? Math.round(adet) : Math.round(adet * 1000) / 1000;
      if (yeni <= 0) kopya.splice(i, 1);
      else kopya[i] = { ...k, adet: yeni, indirim: Math.min(k.indirim, yuvarla(k.birim_fiyat, Math.round(yeni * 1000), 1000)) };
      return kopya;
    });
  };

  /** Çevrimdışı: son eşitlenen katalogda birebir kod, yoksa ad araması. */
  const yereldeBul = useCallback(
    (kod: string) => {
      const urunler = katalogRef.current?.urunler || [];
      const u = koddanBul(urunler, kod);
      if (u) {
        ekle(u);
        setAra('');
        setSonuclar(null);
        return;
      }
      const r = yerelAra(urunler, kod);
      if (r.length === 1) {
        ekle(r[0]);
        setAra('');
        setSonuclar(null);
      } else {
        setSonuclar(r);
        if (!r.length) setMesaj({ tur: 'hata', metin: t('stokPos.kasa.bulunamadi', { kod }) });
      }
    },
    [ekle, t]
  );

  const kodlaEkle = useCallback(
    async (ham: string) => {
      const kod = ham.trim();
      if (!kod) return;
      if (navigator.onLine === false && katalogRef.current) return yereldeBul(kod);
      try {
        const u = await api.urunKodla(kod);
        ekle(u);
        setAra('');
        setSonuclar(null);
      } catch (e) {
        if (e instanceof StokHatasi && (e.durum === 404 || e.kod === 'urun_yok')) {
          try {
            const r = await api.urunler({ ara: kod, adet: 30 });
            if (r.items.length === 1) {
              ekle(r.items[0]);
              setAra('');
              setSonuclar(null);
            } else {
              setSonuclar(r.items);
              if (!r.items.length) setMesaj({ tur: 'hata', metin: t('stokPos.kasa.bulunamadi', { kod }) });
            }
          } catch (e2) {
            if (e2 instanceof StokHatasi && e2.kod === 'ag' && katalogRef.current) return yereldeBul(kod);
            setMesaj({ tur: e2 instanceof StokHatasi && e2.kod === 'ag' ? 'ag' : 'hata', metin: hataMetni(t, e2) });
          }
        } else if (e instanceof StokHatasi && e.kod === 'ag' && katalogRef.current) {
          yereldeBul(kod);
        } else {
          setMesaj({ tur: e instanceof StokHatasi && e.kod === 'ag' ? 'ag' : 'hata', metin: hataMetni(t, e) });
        }
      }
    },
    [api, ekle, t, yereldeBul]
  );

  // Yazarken arama (rakamlı kodlarda okuyucunun Enter'ını bekle).
  useEffect(() => {
    const a = ara.trim();
    if (a.length < 2 || /^\d+$/.test(a)) {
      if (!a) setSonuclar(null);
      return;
    }
    const z = window.setTimeout(() => {
      const yerel = () => katalogRef.current && setSonuclar(yerelAra(katalogRef.current.urunler, a));
      if (navigator.onLine === false) return void yerel();
      api
        .urunler({ ara: a, adet: 30 })
        .then((r) => setSonuclar(r.items))
        .catch(yerel);
    }, 250);
    return () => window.clearTimeout(z);
  }, [api, ara]);

  // ------------------------------------------------------------ ödeme
  const toplam = toplamlar.toplam;
  const kart = odemeTuru === 'kart' ? toplam : odemeTuru === 'karma' ? kurusaCevir(kartTutar) || 0 : 0;
  const havale = odemeTuru === 'havale' ? toplam : odemeTuru === 'karma' ? kurusaCevir(havaleTutar) || 0 : 0;
  const nakit = odemeTuru === 'nakit' ? toplam : odemeTuru === 'karma' ? toplam - kart - havale : 0;
  const alinanKurus = alinan.trim() ? kurusaCevir(alinan) : nakit;
  const paraUstu = alinanKurus !== null && nakit > 0 ? alinanKurus - nakit : 0;
  const odemeGecersiz = nakit < 0 || alinanKurus === null || (nakit > 0 && (alinanKurus ?? 0) < nakit);

  const temizle = () => {
    setKalemler([]);
    setToplamIndirim(0);
    setMusteriAd('');
    setAlici(null);
    setAlinan('');
    setKartTutar('');
    setHavaleTutar('');
    setOdemeTuru('nakit');
    setKimlik(yeniKimlik());
  };

  /** Sunucuya giden satış gövdesi (kişisel veri hariç — müşteri adı / alıcı ayrıca, yalnız çevrimiçi). */
  const satisGovdesi = () => ({
    konum_id: konumId,
    kalemler: kalemler.map((k) => ({ urun_id: k.urun_id, adet: k.adet, indirim: k.indirim ? tl(k.indirim) : undefined })),
    toplam_indirim: toplamIndirim ? tl(toplamIndirim) : undefined,
    odeme: {
      tur: odemeTuru,
      kart: odemeTuru === 'karma' ? tl(kart) : undefined,
      havale: odemeTuru === 'karma' ? tl(havale) : undefined,
      nakit_alinan: nakit > 0 && alinanKurus !== null ? tl(alinanKurus) : undefined,
    },
    istemci_kimligi: kimlik,
    beklenen_toplam: tl(toplam),
  });

  /** Cihazdaki fiş (kuyruktaki satış; sunucu numarası yok, "ÇEVRİMDIŞI-n"). Kişisel veri yok. */
  const yerelFis = (no: string, zaman: string): Satis => {
    const a = meta.ayarlar;
    return {
      id: 0,
      no,
      durum: 'tamamlandi',
      zaman,
      konum_id: konumId,
      oturum_id: oturum?.id ?? 0,
      kasiyer: '',
      musteri_ad: null,
      toplam,
      iade_toplam: 0,
      odeme_turu: odemeTuru,
      fatura_no: null,
      para_birimi: pb,
      tarih_metni: '',
      alici_id: null,
      ara_toplam: toplamlar.ara_toplam,
      satir_indirim: toplamlar.satir_indirim,
      toplam_indirim: toplamlar.toplam_indirim,
      kdv_toplam: toplamlar.kdv_dokumu.reduce((x, d) => x + d.kdv, 0),
      kdv_dokumu: toplamlar.kdv_dokumu,
      nakit,
      kart,
      havale,
      nakit_alinan: nakit > 0 ? alinanKurus ?? nakit : 0,
      para_ustu: Math.max(0, paraUstu),
      notlar: null,
      fatura_at: null,
      fatura_alici: null,
      kalemler: kalemler.map((k, i) => {
        const satir = toplamlar.satirlar[i];
        const satirIndirim = Math.max(0, Math.min(k.indirim || 0, satir?.brut ?? 0));
        return {
          id: -(i + 1),
          urun_id: k.urun_id,
          ad: k.ad,
          barkod: k.barkod,
          birim: k.birim,
          adet: k.adet,
          adet_binde: Math.round(k.adet * 1000),
          birim_fiyat: k.birim_fiyat,
          brut: satir?.brut ?? 0,
          satir_indirim: satirIndirim,
          indirim: (satir?.brut ?? 0) - (satir?.tutar ?? 0),
          tutar: satir?.tutar ?? 0,
          kdv_orani: k.kdv_orani,
          kdv: 0,
          iade_adet: 0,
          iade_adet_binde: 0,
          iade_tutar: 0,
        };
      }),
      iadeler: [],
      firma: { ad: a.firma_adi, adres: a.adres, telefon: a.telefon, eposta: a.eposta, vergi_dairesi: a.vergi_dairesi, vergi_no: a.vergi_no, fis_notu: a.fis_notu },
      mali_degil: meta.notlar.fis,
      cevrimdisi_no: no,
      yerel: true,
    };
  };

  /** Çevrimdışı satış: kuyruğa "ÇEVRİMDIŞI-n" fişiyle yaz (stok kuralı son eşitlenen stokla). */
  const kuyrugaAl = async () => {
    if (!oturum || !kalemler.length || odemeGecersiz) return;
    const urunler = new Map((katalogRef.current?.urunler || []).map((u) => [u.id, u]));
    const eksiler: { ad: string; mevcut: number }[] = [];
    for (const k of kalemler) {
      const u = urunler.get(k.urun_id);
      if (!u || !u.stok_takibi) continue;
      const mevcut = u.stok.konumlar[String(konumId)] ?? 0;
      if (mevcut - k.adet < 0) eksiler.push({ ad: k.ad, mevcut });
    }
    if (eksiler.length && !meta.ayarlar.eksi_stok) {
      // Ayardaki kural: eksi stok kapalıysa yetersiz stokta çevrimdışı satış da yapılmaz.
      setMesaj({
        tur: 'hata',
        metin: `${hataMetni(t, new StokHatasi(409, 'yetersiz_stok', { ad: eksiler[0].ad, mevcut: miktarYaz(eksiler[0].mevcut, dil) }))} ${t('stokPos.kuyruk.sonEsitlemeyeGore')}`,
      });
      return;
    }
    setMesgul(true);
    try {
      const sira = await sonrakiSira(meta.hesap);
      const no = cevrimdisiNo(sira);
      const zaman = new Date().toISOString();
      const fisi = yerelFis(no, zaman);
      await kuyruk.ekle({
        istemci_kimligi: kimlik,
        hesap: await hesapOzeti(meta.hesap),
        kisi_ozeti: kuyruk.benim,
        no,
        sira,
        zaman,
        toplam,
        govde: { ...satisGovdesi(), cevrimdisi: true, cevrimdisi_no: no, istemci_zamani: zaman, oturum_id: oturum.id },
        durum: 'bekliyor',
        deneme: 0,
        fis: fisi,
      });
      yerelStokDus(kalemler.map((k) => ({ urun_id: k.urun_id, adet: k.adet })));
      setFis(fisi);
      temizle();
      setMesaj(eksiler.length ? { tur: 'uyari', metin: t('stokPos.kuyruk.eksiUyari', { urunler: eksiler.map((e) => e.ad).join(', ') }) } : null);
    } catch (e) {
      setMesaj({ tur: 'hata', metin: hataMetni(t, e) });
    } finally {
      setMesgul(false);
    }
  };

  const tamamla = async () => {
    if (!oturum || !kalemler.length || odemeGecersiz || mesgul) return;
    if (cevrimdisiOnay && navigator.onLine === false) return void kuyrugaAl();
    setMesgul(true);
    setMesaj(null);
    let kuyruga = false;
    try {
      const s = await api.satisEkle({ ...satisGovdesi(), musteri_ad: musteriAd.trim() || undefined, alici_id: alici?.id });
      setFis(s);
      yerelStokDus(kalemler.map((k) => ({ urun_id: k.urun_id, adet: k.adet })));
      temizle();
      void sonSatislariYukle();
      if (s.kritik?.length) onMeta();
    } catch (e) {
      if (e instanceof StokHatasi && e.kod === 'ag') {
        // Ağ yok: kasiyer bu kopuşta çevrimdışı satışı onayladıysa doğrudan kuyruğa; değilse sorulur.
        if (cevrimdisiOnay) kuyruga = true;
        else setMesaj({ tur: 'ag', metin: t('stokPos.kasa.agYok'), kuyrukTeklif: true });
      } else {
        setMesaj({ tur: 'hata', metin: hataMetni(t, e) });
        if (e instanceof StokHatasi && e.kod === 'kasa_kapali') void oturumlariYenile();
      }
    } finally {
      setMesgul(false);
    }
    if (kuyruga) await kuyrugaAl();
  };

  const satisAc = async (id: number, hedef: 'fis' | 'iade' | 'fatura') => {
    try {
      const s = await api.satis(id);
      if (hedef === 'fis') setFis(s);
      else if (hedef === 'iade') setIadeSatis(s);
      else setFaturaSatis(s);
    } catch (e) {
      setMesaj({ tur: 'hata', metin: hataMetni(t, e) });
    }
  };

  const kasaAc = async () => {
    setMesgul(true);
    try {
      await api.kasaAc({ konum_id: konumId, acilis_nakit: acilisNakit.trim() ? acilisNakit.trim().replace(',', '.') : 0 });
      setAcilisNakit('');
      await oturumlariYenile();
      onMeta();
    } catch (e) {
      setMesaj({ tur: 'hata', metin: hataMetni(t, e) });
    } finally {
      setMesgul(false);
    }
  };

  const kapatmaBaslat = async () => {
    if (!oturum) return;
    try {
      const r = await api.kasaOzeti(oturum.id);
      setKapanis({ ozet: r.ozet, oturum: r.oturum });
    } catch (e) {
      setMesaj({ tur: 'hata', metin: hataMetni(t, e) });
    }
  };

  const konumAdi = konumlar.find((k) => k.id === konumId)?.ad || '';
  const liste = sonuclar ?? hizli;

  return (
    <div
      className="flex flex-col gap-4 lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(320px,400px)] lg:grid-rows-[auto_auto_1fr] lg:items-start"
      data-testid="pos-kasa"
      data-katalog={katalog?.urunler.length ?? 0}
      data-cevrimici={cevrimici ? '1' : '0'}
    >
      {/* ----------------------------------------------------------- üst: kasa durumu + arama */}
      <div className="flex min-w-0 flex-col gap-3 lg:col-start-1 lg:row-start-1">
        <div className={`${KART} flex flex-wrap items-center gap-2 p-3`}>
          {konumlar.length > 1 && (
            <select className={cn(SECIM, 'w-auto min-w-[10rem]')} value={konumId} onChange={(e) => setKonumId(Number(e.target.value))} aria-label={t('stokPos.konum')} data-testid="pos-konum">
              {konumlar.map((k) => (
                <option key={k.id} value={k.id}>
                  {k.ad}
                </option>
              ))}
            </select>
          )}
          {oturum ? (
            <>
              <Rozet renk="border-emerald-400/40 bg-emerald-500/15 text-emerald-200" testid="pos-kasa-acik">
                {t('stokPos.kasa.acik', { saat: tarihSaat(oturum.acilis_at, dil) })}
              </Rozet>
              <span className="text-xs text-muted-foreground">{oturum.acan}</span>
              <Button size="sm" variant="outline" className={`${DIS_DUGME} ms-auto`} onClick={() => void kapatmaBaslat()} data-testid="pos-kasa-kapat">
                <Lock className="h-4 w-4" aria-hidden="true" />
                {t('stokPos.kasa.gunSonu')}
              </Button>
            </>
          ) : (
            <Rozet renk="border-amber-400/40 bg-amber-500/15 text-amber-200">{t('stokPos.kasa.kapali')}</Rozet>
          )}
          {!cevrimici ? (
            <Rozet renk="border-red-400/40 bg-red-500/15 text-red-200" testid="pos-cevrimdisi">
              <WifiOff className="h-3 w-3" aria-hidden="true" />
              {t('stokPos.kasa.cevrimdisi')}
            </Rozet>
          ) : (
            <Rozet renk="border-emerald-400/30 bg-emerald-500/10 text-emerald-200" testid="pos-cevrimici">
              <Wifi className="h-3 w-3" aria-hidden="true" />
              {t('stokPos.kuyruk.cevrimici')}
            </Rozet>
          )}
          {kuyruk.kayitlar.length > 0 && (
            <Rozet renk="border-amber-400/40 bg-amber-500/15 text-amber-100" testid="pos-kuyruk-rozet">
              <CloudUpload className="h-3 w-3" aria-hidden="true" />
              {t('stokPos.kuyruk.rozet')}
              <span className="sr-only">:</span>
              <span className="font-semibold tabular-nums" data-testid="pos-kuyruk-sayisi">
                {kuyruk.kayitlar.length}
              </span>
            </Rozet>
          )}
        </div>
        {!cevrimici && (
          <p className="rounded-lg border border-amber-400/30 bg-amber-500/10 p-2 text-xs text-amber-100" data-testid="pos-cevrimdisi-bilgi">
            {t('stokPos.kuyruk.cevrimdisiBilgi')}
            {katalog ? ` ${t('stokPos.kuyruk.katalog', { sayi: katalog.urunler.length, saat: tarihSaat(katalog.zaman, dil) })}` : ` ${t('stokPos.kuyruk.katalogYok')}`}
          </p>
        )}

        {!oturum ? (
          <div className={`${KART} p-4`} data-testid="pos-kasa-ac-kart">
            <p className="mb-3 text-sm text-muted-foreground">{t('stokPos.kasa.acAciklama', { konum: konumAdi })}</p>
            <div className="flex flex-wrap items-end gap-2">
              <Alan etiket={t('stokPos.kasa.acilisNakit')} className="w-40">
                <input className={GIRDI} inputMode="decimal" value={acilisNakit} onChange={(e) => setAcilisNakit(e.target.value)} placeholder="0" data-testid="pos-acilis-nakit" />
              </Alan>
              <Button onClick={() => void kasaAc()} disabled={mesgul} className="h-10 gap-1.5" data-testid="pos-kasa-ac">
                {mesgul ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Lock className="h-4 w-4" aria-hidden="true" />}
                {t('stokPos.kasa.ac')}
              </Button>
            </div>
          </div>
        ) : (
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              void kodlaEkle(ara);
            }}
          >
            <div className="relative min-w-0 flex-1">
              <Search className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
              <input
                ref={aramaRef}
                className={cn(GIRDI, 'h-12 ps-9 text-base')}
                value={ara}
                onChange={(e) => setAra(e.target.value)}
                placeholder={t('stokPos.kasa.araIpucu')}
                aria-label={t('stokPos.kasa.ara')}
                autoComplete="off"
                autoFocus
                enterKeyHint="search"
                data-testid="pos-ara"
              />
            </div>
            <Button type="button" variant="outline" className={`${DIS_DUGME} h-12 w-12 flex-none p-0`} onClick={() => setOkutucu(true)} aria-label={t('stokPos.kasa.kamera')} data-testid="pos-kamera">
              <Camera className="h-5 w-5" aria-hidden="true" />
            </Button>
          </form>
        )}
        {mesaj && (
          <div
            role="alert"
            className={`flex flex-wrap items-start gap-2 rounded-lg border p-3 text-sm ${
              mesaj.tur === 'ag' || mesaj.tur === 'uyari'
                ? 'border-amber-400/40 bg-amber-500/10 text-amber-100'
                : mesaj.tur === 'bilgi'
                  ? 'border-sky-400/40 bg-sky-500/10 text-sky-100'
                  : 'border-red-400/40 bg-red-500/10 text-red-100'
            }`}
            data-testid="pos-mesaj"
            data-tur={mesaj.tur}
          >
            {mesaj.tur === 'ag' && <CloudOff className="mt-0.5 h-4 w-4 flex-none" aria-hidden="true" />}
            <span className="min-w-0 flex-1">{mesaj.metin}</span>
            {mesaj.kuyrukTeklif && oturum && kalemler.length > 0 && (
              <Button
                size="sm"
                className="h-9 gap-1.5"
                disabled={mesgul || odemeGecersiz}
                onClick={() => {
                  setCevrimdisiOnay(true);
                  setMesaj(null);
                  void kuyrugaAl();
                }}
                data-testid="pos-kuyruga-al"
              >
                <CloudUpload className="h-4 w-4" aria-hidden="true" />
                {t('stokPos.kuyruk.kuyrugaAl')}
              </Button>
            )}
          </div>
        )}
        <KuyrukPaneli kuyruk={kuyruk} para={p} cevrimici={cevrimici} onFis={setFis} />
        {geriYuklendi && kalemler.length > 0 && !mesaj && (
          <p className="text-xs text-sky-200" data-testid="pos-geri-yuklendi">
            {t('stokPos.kasa.geriYuklendi')}
          </p>
        )}
      </div>

      {/* ----------------------------------------------------------- sepet + ödeme */}
      <div className={`${KART} flex flex-col gap-3 p-3 sm:p-4 lg:sticky lg:top-4 lg:col-start-2 lg:row-span-3 lg:row-start-1`} data-testid="pos-sepet">
        <div className="flex items-center justify-between gap-2">
          <h3 className="font-semibold">{t('stokPos.kasa.sepet', { sayi: kalemler.length })}</h3>
          {kalemler.length > 0 && (
            <button type="button" className="text-xs text-muted-foreground hover:text-white" onClick={temizle} data-testid="pos-sepet-temizle">
              {t('stokPos.kasa.temizle')}
            </button>
          )}
        </div>
        {kalemler.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">{t('stokPos.kasa.sepetBos')}</p>
        ) : (
          <ul className="divide-y divide-white/5" data-testid="pos-sepet-liste">
            {kalemler.map((k, i) => {
              const satir = toplamlar.satirlar[i];
              const tam = k.birim === 'adet' || k.birim === 'paket';
              return (
                <li key={k.urun_id} className="py-2" data-testid="pos-sepet-satir" data-urun-id={k.urun_id}>
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{k.ad}</p>
                      <p className="text-xs text-muted-foreground">
                        {p(k.birim_fiyat)}
                        {!tam && ` / ${t(`stokPos.birim.${k.birim}`)}`} · %{k.kdv_orani}
                      </p>
                    </div>
                    <div className="text-end">
                      <p className="text-sm font-semibold tabular-nums" data-testid="pos-satir-tutar">
                        {p(satir?.brut ?? 0)}
                      </p>
                      {k.indirim > 0 && <p className="text-xs text-emerald-300">−{p(k.indirim)}</p>}
                    </div>
                  </div>
                  <div className="mt-1.5 flex items-center gap-1.5">
                    <Button size="icon" variant="outline" className={`${DIS_DUGME} h-9 w-9`} onClick={() => adetDegistir(i, k.adet - (tam ? 1 : 0.1))} aria-label={t('stokPos.kasa.azalt')}>
                      <Minus className="h-4 w-4" aria-hidden="true" />
                    </Button>
                    <input
                      className={cn(GIRDI, 'h-9 w-20 text-center tabular-nums')}
                      inputMode={tam ? 'numeric' : 'decimal'}
                      value={String(k.adet).replace('.', dil === 'en' || dil === 'zh' || dil === 'hi' ? '.' : ',')}
                      onChange={(e) => {
                        const v = sayiCevir(e.target.value);
                        if (v !== null && v >= 0) adetDegistir(i, v);
                      }}
                      aria-label={t('stokPos.kasa.miktar')}
                      data-testid="pos-satir-adet"
                    />
                    <Button size="icon" variant="outline" className={`${DIS_DUGME} h-9 w-9`} onClick={() => adetDegistir(i, k.adet + (tam ? 1 : 0.1))} aria-label={t('stokPos.kasa.arttir')} data-testid="pos-satir-arttir">
                      <Plus className="h-4 w-4" aria-hidden="true" />
                    </Button>
                    <Button size="icon" variant="ghost" className="h-9 w-9" onClick={() => setIndirimSatiri(i)} aria-label={t('stokPos.kasa.satirIndirim')} data-testid="pos-satir-indirim">
                      <Percent className="h-4 w-4" aria-hidden="true" />
                    </Button>
                    <Button size="icon" variant="ghost" className="ms-auto h-9 w-9 text-red-300 hover:text-red-200" onClick={() => adetDegistir(i, 0)} aria-label={t('stokPos.sil')}>
                      <Trash2 className="h-4 w-4" aria-hidden="true" />
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        {kalemler.length > 0 && (
          <>
            <div className="flex flex-wrap items-center gap-2 border-t border-white/10 pt-3">
              <span className="text-sm text-muted-foreground">{t('stokPos.kasa.toplamIndirim')}</span>
              <input
                className={cn(GIRDI, 'h-9 w-24')}
                inputMode="decimal"
                value={toplamIndirim ? tl(toplamIndirim).replace('.', ',') : ''}
                placeholder="0"
                onChange={(e) => setToplamIndirim(kurusaCevir(e.target.value) ?? 0)}
                aria-label={t('stokPos.kasa.toplamIndirim')}
                data-testid="pos-toplam-indirim"
              />
              {[5, 10].map((y) => (
                <Button
                  key={y}
                  size="sm"
                  variant="outline"
                  className={`${DIS_DUGME} h-9`}
                  onClick={() => setToplamIndirim(yuvarla(toplamlar.ara_toplam - toplamlar.satir_indirim, y, 100))}
                >
                  %{y}
                </Button>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <UserRound className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
              {alici ? (
                <Rozet renk="border-purple-400/40 bg-purple-500/15 text-purple-100">
                  {alici.ad}
                  <button type="button" className="ms-1" onClick={() => setAlici(null)} aria-label={t('stokPos.kaldir')}>
                    ×
                  </button>
                </Rozet>
              ) : (
                <input
                  className={cn(GIRDI, 'h-9 min-w-0 flex-1')}
                  value={musteriAd}
                  onChange={(e) => setMusteriAd(e.target.value)}
                  placeholder={t('stokPos.kasa.musteriIpucu')}
                  aria-label={t('stokPos.kasa.musteri')}
                  maxLength={160}
                />
              )}
              <Button size="sm" variant="ghost" className="h-9" onClick={() => setAliciPencere(true)} data-testid="pos-alici-sec">
                {t('stokPos.kasa.musteriSec')}
              </Button>
              {!cevrimici && (musteriAd.trim() || alici) && <p className="w-full text-xs text-amber-200">{t('stokPos.kuyruk.musteriNotu')}</p>}
            </div>

            <dl className="space-y-1 border-t border-white/10 pt-3 text-sm">
              <div className="flex justify-between">
                <dt className="text-muted-foreground">{t('stokPos.kasa.araToplam')}</dt>
                <dd className="tabular-nums">{p(toplamlar.ara_toplam)}</dd>
              </div>
              {toplamlar.satir_indirim + toplamlar.toplam_indirim > 0 && (
                <div className="flex justify-between text-emerald-300">
                  <dt>{t('stokPos.kasa.indirim')}</dt>
                  <dd className="tabular-nums">−{p(toplamlar.satir_indirim + toplamlar.toplam_indirim)}</dd>
                </div>
              )}
              {toplamlar.kdv_dokumu
                .filter((d) => d.kdv > 0)
                .map((d) => (
                  <div key={d.oran} className="flex justify-between text-xs text-muted-foreground">
                    <dt>{t('stokPos.fis.kdv', { oran: d.oran })}</dt>
                    <dd className="tabular-nums">{p(d.kdv)}</dd>
                  </div>
                ))}
              <div className="flex justify-between pt-1 text-xl font-bold">
                <dt>{t('stokPos.kasa.toplam')}</dt>
                <dd className="tabular-nums" data-testid="pos-toplam">
                  {p(toplam)}
                </dd>
              </div>
            </dl>

            <div className="grid grid-cols-4 gap-1.5" role="radiogroup" aria-label={t('stokPos.kasa.odemeTuru')}>
              {ODEMELER.map(({ tur, ikon: Ikon }) => (
                <button
                  key={tur}
                  type="button"
                  role="radio"
                  aria-checked={odemeTuru === tur}
                  onClick={() => setOdemeTuru(tur)}
                  className={`flex min-h-[52px] flex-col items-center justify-center gap-0.5 rounded-lg border text-xs transition-colors ${
                    odemeTuru === tur ? 'border-purple-400 bg-purple-500/25 text-white' : 'border-white/10 bg-white/[0.03] text-muted-foreground hover:text-white'
                  }`}
                  data-odeme={tur}
                >
                  <Ikon className="h-5 w-5" aria-hidden="true" />
                  {t(`stokPos.odeme.${tur}`)}
                </button>
              ))}
            </div>
            {odemeTuru === 'karma' && (
              <div className="grid grid-cols-2 gap-2">
                <Alan etiket={t('stokPos.odeme.kart')}>
                  <input className={GIRDI} inputMode="decimal" value={kartTutar} onChange={(e) => setKartTutar(e.target.value)} placeholder="0" data-testid="pos-karma-kart" />
                </Alan>
                <Alan etiket={t('stokPos.odeme.havale')}>
                  <input className={GIRDI} inputMode="decimal" value={havaleTutar} onChange={(e) => setHavaleTutar(e.target.value)} placeholder="0" />
                </Alan>
              </div>
            )}
            {(odemeTuru === 'nakit' || (odemeTuru === 'karma' && nakit > 0)) && (
              <div className="space-y-2">
                {odemeTuru === 'karma' && <p className="text-xs text-muted-foreground">{t('stokPos.kasa.kalanNakit', { tutar: p(Math.max(0, nakit)) })}</p>}
                <div className="flex flex-wrap items-end gap-2">
                  <Alan etiket={t('stokPos.kasa.alinan')} className="w-32">
                    <input className={GIRDI} inputMode="decimal" value={alinan} onChange={(e) => setAlinan(e.target.value)} placeholder={tl(nakit).replace('.', ',')} data-testid="pos-alinan" />
                  </Alan>
                  {[nakit, 5000, 10000, 20000]
                    .filter((v, i, a) => v >= nakit && a.indexOf(v) === i)
                    .slice(0, 3)
                    .map((v) => (
                      <Button key={v} size="sm" variant="outline" className={`${DIS_DUGME} h-10`} onClick={() => setAlinan(tl(v))}>
                        {p(v)}
                      </Button>
                    ))}
                </div>
                <p className={`text-base font-semibold ${paraUstu < 0 ? 'text-red-300' : 'text-emerald-300'}`} data-testid="pos-para-ustu">
                  {paraUstu < 0 ? t('stokPos.kasa.eksik', { tutar: p(-paraUstu) }) : t('stokPos.kasa.paraUstu', { tutar: p(paraUstu) })}
                </p>
              </div>
            )}
            {odemeTuru !== 'nakit' && odemeTuru !== 'havale' && <p className="text-xs text-muted-foreground">{t('stokPos.kasa.kartNotu')}</p>}
            <Button
              className="h-14 gap-2 text-base"
              disabled={!oturum || mesgul || odemeGecersiz || !kalemler.length}
              onClick={() => void tamamla()}
              data-testid="pos-tamamla"
            >
              {mesgul ? <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" /> : <CheckCircle2 className="h-5 w-5" aria-hidden="true" />}
              {t('stokPos.kasa.tamamla', { tutar: p(toplam) })}
            </Button>
          </>
        )}
      </div>

      {/* ----------------------------------------------------------- ürünler */}
      {oturum && (
        <div className="min-w-0 lg:col-start-1 lg:row-start-2">
          <h3 className="mb-2 text-sm font-semibold text-muted-foreground">{sonuclar ? t('stokPos.kasa.sonuclar', { sayi: sonuclar.length }) : t('stokPos.kasa.hizli')}</h3>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-4" data-testid="pos-urunler">
            {liste.map((u) => (
              <button
                key={u.id}
                type="button"
                onClick={() => {
                  ekle(u);
                  setAra('');
                  setSonuclar(null);
                  aramaRef.current?.focus();
                }}
                className={`${KART} flex min-h-[76px] flex-col items-start justify-between gap-1 p-3 text-start transition-colors hover:border-purple-400/50 hover:bg-purple-500/10`}
                data-testid="pos-urun"
                data-urun-id={u.id}
              >
                <span className="line-clamp-2 text-sm font-medium">{u.ad}</span>
                <span className="flex w-full items-center justify-between gap-1 text-xs">
                  <span className="font-semibold text-white">{p(u.satis_fiyati)}</span>
                  {u.stok_takibi && (
                    <span className={u.kritik ? 'text-amber-300' : 'text-muted-foreground'}>
                      {miktarYaz(u.stok.konumlar[String(konumId)] ?? 0, dil)} {u.birim === 'adet' ? '' : t(`stokPos.birim.${u.birim}`)}
                    </span>
                  )}
                </span>
              </button>
            ))}
            {!liste.length && <p className="col-span-full py-6 text-center text-sm text-muted-foreground">{t('stokPos.kasa.urunYok')}</p>}
          </div>
        </div>
      )}

      {/* ----------------------------------------------------------- son satışlar */}
      {oturum && (
        <div className={`${KART} min-w-0 p-3 lg:col-start-1 lg:row-start-3`}>
          <h3 className="mb-2 text-sm font-semibold">{t('stokPos.kasa.sonSatislar')}</h3>
          {sonSatislar.length === 0 ? (
            <p className="py-4 text-center text-sm text-muted-foreground">{t('stokPos.kasa.satisYok')}</p>
          ) : (
            <ul className="divide-y divide-white/5" data-testid="pos-son-satislar">
              {sonSatislar.slice(0, 12).map((s) => (
                <li key={s.id} className="flex flex-wrap items-center gap-2 py-2 text-sm" data-testid="pos-son-satis" data-satis-id={s.id}>
                  <span className="font-mono text-xs">{s.no}</span>
                  <span className="text-xs text-muted-foreground">{tarihSaat(s.zaman, dil)}</span>
                  {s.durum !== 'tamamlandi' && <Rozet renk="border-amber-400/40 bg-amber-500/15 text-amber-200">{t(`stokPos.durum.${s.durum}`)}</Rozet>}
                  {s.cevrimdisi_no && (
                    <Rozet renk="border-sky-400/40 bg-sky-500/10 text-sky-200" testid="pos-son-satis-cevrimdisi">
                      <CloudUpload className="h-3 w-3" aria-hidden="true" />
                      {s.cevrimdisi_no}
                    </Rozet>
                  )}
                  <span className="ms-auto font-semibold tabular-nums">{p(s.toplam - s.iade_toplam)}</span>
                  <div className="flex w-full justify-end gap-1 sm:w-auto">
                    <Button size="sm" variant="ghost" className="h-8 gap-1 px-2" onClick={() => void satisAc(s.id, 'fis')} data-testid="pos-fis-ac">
                      <Receipt className="h-4 w-4" aria-hidden="true" />
                      {t('stokPos.kasa.fis')}
                    </Button>
                    {iadeYetkisi && s.durum !== 'iade' && s.durum !== 'iptal' && (
                      <Button size="sm" variant="ghost" className="h-8 gap-1 px-2" onClick={() => void satisAc(s.id, 'iade')} data-testid="pos-iade-ac">
                        <RotateCcw className="h-4 w-4" aria-hidden="true" />
                        {t('stokPos.kasa.iade')}
                      </Button>
                    )}
                    {s.durum !== 'iptal' && (
                      <Button size="sm" variant="ghost" className="h-8 gap-1 px-2" onClick={() => void satisAc(s.id, 'fatura')} data-testid="pos-fatura-ac">
                        <FileText className="h-4 w-4" aria-hidden="true" />
                        {s.fatura_no ? s.fatura_no : t('stokPos.kasa.fatura')}
                      </Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {okutucu && (
        <Suspense fallback={null}>
          <Okutucu
            onKod={(kod) => {
              void kodlaEkle(kod);
            }}
            onKapat={() => setOkutucu(false)}
          />
        </Suspense>
      )}
      {fis && (
        <Fis
          satis={fis}
          onKapat={() => setFis(null)}
          onPdf={fis.yerel ? undefined : () => void api.fisPdf(fis, dil).catch((e) => setMesaj({ tur: 'hata', metin: hataMetni(t, e) }))}
        />
      )}
      {indirimSatiri !== null && kalemler[indirimSatiri] && (
        <SatirIndirimi
          kalem={kalemler[indirimSatiri]}
          brut={toplamlar.satirlar[indirimSatiri]?.brut ?? 0}
          para={p}
          onKaydet={(indirim) => {
            setKalemler((l) => l.map((k, i) => (i === indirimSatiri ? { ...k, indirim } : k)));
            setIndirimSatiri(null);
          }}
          onKapat={() => setIndirimSatiri(null)}
        />
      )}
      {aliciPencere && (
        <AliciSecici
          api={api}
          onSec={(a) => {
            setAlici(a);
            setMusteriAd('');
            setAliciPencere(false);
          }}
          onKapat={() => setAliciPencere(false)}
        />
      )}
      {iadeSatis && (
        <IadePenceresi
          api={api}
          satis={iadeSatis}
          para={p}
          onBitti={(s) => {
            setIadeSatis(null);
            setFis(s);
            void sonSatislariYukle();
          }}
          onKapat={() => setIadeSatis(null)}
        />
      )}
      {faturaSatis && (
        <FaturaPenceresi
          api={api}
          satis={faturaSatis}
          onBitti={() => {
            setFaturaSatis(null);
            void sonSatislariYukle();
          }}
          onKapat={() => setFaturaSatis(null)}
        />
      )}
      {kapanis && (
        <KapanisPenceresi
          api={api}
          ozet={kapanis.ozet}
          oturum={kapanis.oturum}
          para={p}
          onBitti={(r) => {
            setKapanis(null);
            setZGoster(r);
            void oturumlariYenile();
            onMeta();
          }}
          onKapat={() => setKapanis(null)}
        />
      )}
      {zGoster && <ZRaporu ozet={zGoster.ozet} oturum={zGoster.oturum} konum={konumAdi} onKapat={() => setZGoster(null)} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pencereler
// ---------------------------------------------------------------------------
function SatirIndirimi({ kalem, brut, para: p, onKaydet, onKapat }: { kalem: SepetKalemi; brut: number; para: (n: number) => string; onKaydet: (kurus: number) => void; onKapat: () => void }) {
  const { t } = useTranslation();
  const [tur, setTur] = useState<'tutar' | 'yuzde'>('yuzde');
  const [deger, setDeger] = useState('');
  const kurus = tur === 'yuzde' ? yuvarla(brut, Math.min(100, Math.max(0, sayiCevir(deger) || 0)), 100) : Math.min(brut, kurusaCevir(deger) || 0);
  return (
    <Pencere baslik={t('stokPos.kasa.satirIndirim')} onKapat={onKapat} testid="pos-indirim-pencere">
      <p className="mb-3 text-sm text-muted-foreground">
        {kalem.ad} · {p(brut)}
      </p>
      <div className="flex gap-2">
        <select className={cn(SECIM, 'w-28')} value={tur} onChange={(e) => setTur(e.target.value as 'tutar' | 'yuzde')} aria-label={t('stokPos.kasa.indirimTuru')}>
          <option value="yuzde">%</option>
          <option value="tutar">{t('stokPos.kasa.tutar')}</option>
        </select>
        <input className={GIRDI} inputMode="decimal" value={deger} onChange={(e) => setDeger(e.target.value)} autoFocus data-testid="pos-indirim-deger" />
      </div>
      <p className="mt-2 text-sm text-emerald-300">−{p(kurus)}</p>
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="ghost" onClick={() => onKaydet(0)}>
          {t('stokPos.kaldir')}
        </Button>
        <Button onClick={() => onKaydet(kurus)} data-testid="pos-indirim-kaydet">
          {t('stokPos.uygula')}
        </Button>
      </div>
    </Pencere>
  );
}

function AliciSecici({ api, onSec, onKapat }: { api: StokApi; onSec: (a: Alici) => void; onKapat: () => void }) {
  const { t } = useTranslation();
  const [ara, setAra] = useState('');
  const [liste, setListe] = useState<Alici[]>([]);
  const [yeni, setYeni] = useState({ ad: '', vergi_no: '', eposta: '', telefon: '' });
  const [hata, setHata] = useState<string | null>(null);
  useEffect(() => {
    const z = window.setTimeout(() => {
      api
        .alicilar(ara.trim() || undefined)
        .then((r) => setListe(r.items))
        .catch((e) => setHata(hataMetni(t, e)));
    }, 200);
    return () => window.clearTimeout(z);
  }, [api, ara, t]);
  const kaydet = async () => {
    try {
      onSec(await api.aliciEkle({ ad: yeni.ad, vergi_no: yeni.vergi_no || null, eposta: yeni.eposta || null, telefon: yeni.telefon || null }));
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  };
  return (
    <Pencere baslik={t('stokPos.kasa.musteriSec')} onKapat={onKapat}>
      <input className={GIRDI} value={ara} onChange={(e) => setAra(e.target.value)} placeholder={t('stokPos.ara')} />
      <ul className="my-3 max-h-56 divide-y divide-white/5 overflow-y-auto">
        {liste.map((a) => (
          <li key={a.id}>
            <button type="button" className="w-full px-1 py-2 text-start text-sm hover:bg-white/5" onClick={() => onSec(a)}>
              {a.ad} {a.vergi_no && <span className="text-xs text-muted-foreground">· {a.vergi_no}</span>}
            </button>
          </li>
        ))}
        {!liste.length && <li className="py-3 text-center text-xs text-muted-foreground">{t('stokPos.kasa.aliciYok')}</li>}
      </ul>
      <div className="space-y-2 border-t border-white/10 pt-3">
        <p className="text-sm font-medium">{t('stokPos.kasa.yeniAlici')}</p>
        <input className={GIRDI} value={yeni.ad} onChange={(e) => setYeni({ ...yeni, ad: e.target.value })} placeholder={t('stokPos.alici.ad')} />
        <div className="grid grid-cols-2 gap-2">
          <input className={GIRDI} value={yeni.vergi_no} onChange={(e) => setYeni({ ...yeni, vergi_no: e.target.value })} placeholder={t('stokPos.alici.vergiNo')} inputMode="numeric" />
          <input className={GIRDI} value={yeni.telefon} onChange={(e) => setYeni({ ...yeni, telefon: e.target.value })} placeholder={t('stokPos.alici.telefon')} />
        </div>
        <input className={GIRDI} value={yeni.eposta} onChange={(e) => setYeni({ ...yeni, eposta: e.target.value })} placeholder={t('stokPos.alici.eposta')} />
        <p className="text-xs text-muted-foreground">{t('stokPos.alici.kvkk')}</p>
        {hata && <p className="text-sm text-red-300">{hata}</p>}
        <div className="flex justify-end">
          <Button onClick={() => void kaydet()} disabled={!yeni.ad.trim()}>
            {t('stokPos.kaydet')}
          </Button>
        </div>
      </div>
    </Pencere>
  );
}

function IadePenceresi({ api, satis, para: p, onBitti, onKapat }: { api: StokApi; satis: Satis; para: (n: number) => string; onBitti: (s: Satis) => void; onKapat: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [adetler, setAdetler] = useState<Record<number, string>>({});
  const [odeme, setOdeme] = useState<'nakit' | 'kart' | 'havale'>(satis.kart && !satis.nakit ? 'kart' : satis.havale && !satis.nakit ? 'havale' : 'nakit');
  const [neden, setNeden] = useState('');
  const [hepsi, setHepsi] = useState(false);
  const [mesgul, setMesgul] = useState(false);
  const [hata, setHata] = useState<string | null>(null);
  const iade = async () => {
    setMesgul(true);
    setHata(null);
    try {
      const kalemler = hepsi
        ? 'hepsi'
        : Object.entries(adetler)
            .map(([id, v]) => ({ kalem_id: Number(id), adet: sayiCevir(v) || 0 }))
            .filter((k) => k.adet > 0);
      onBitti(await api.iade(satis.id, { kalemler, odeme_turu: odeme, neden: neden || undefined }));
    } catch (e) {
      setHata(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };
  const iptal = async () => {
    if (!window.confirm(t('stokPos.kasa.iptalOnay'))) return;
    setMesgul(true);
    try {
      onBitti(await api.iptal(satis.id, { neden: neden || undefined }));
    } catch (e) {
      setHata(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };
  return (
    <Pencere baslik={t('stokPos.kasa.iadeBaslik', { no: satis.no })} onKapat={onKapat} testid="pos-iade-pencere">
      <ul className="divide-y divide-white/5">
        {satis.kalemler.map((k) => {
          const kalan = Math.round((k.adet - k.iade_adet) * 1000) / 1000;
          return (
            <li key={k.id} className="flex items-center gap-2 py-2 text-sm">
              <span className="min-w-0 flex-1 truncate">
                {k.ad}
                <span className="block text-xs text-muted-foreground">
                  {miktarYaz(kalan, dil)} / {miktarYaz(k.adet, dil)} · {p(k.tutar)}
                </span>
              </span>
              <input
                className={cn(GIRDI, 'h-9 w-20 text-center')}
                inputMode="decimal"
                disabled={hepsi || kalan <= 0}
                value={adetler[k.id] ?? ''}
                placeholder="0"
                onChange={(e) => setAdetler({ ...adetler, [k.id]: e.target.value })}
                aria-label={t('stokPos.kasa.iadeAdet', { ad: k.ad })}
                data-testid="pos-iade-adet"
              />
            </li>
          );
        })}
      </ul>
      <div className="mt-3 space-y-3">
        <Anahtar acik={hepsi} onDegis={setHepsi} etiket={t('stokPos.kasa.hepsiniIade')} testid="pos-iade-hepsi" />
        <div className="grid grid-cols-2 gap-2">
          <Alan etiket={t('stokPos.kasa.iadeOdeme')}>
            <select className={SECIM} value={odeme} onChange={(e) => setOdeme(e.target.value as 'nakit' | 'kart' | 'havale')}>
              {(['nakit', 'kart', 'havale'] as const).map((o) => (
                <option key={o} value={o}>
                  {t(`stokPos.odeme.${o}`)}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('stokPos.kasa.neden')}>
            <input className={GIRDI} value={neden} onChange={(e) => setNeden(e.target.value)} maxLength={300} />
          </Alan>
        </div>
        {hata && (
          <p className="text-sm text-red-300" role="alert">
            {hata}
          </p>
        )}
        <div className="flex flex-wrap justify-end gap-2">
          {satis.durum === 'tamamlandi' && (
            <Button variant="outline" className={DIS_DUGME} onClick={() => void iptal()} disabled={mesgul} data-testid="pos-iptal">
              {t('stokPos.kasa.iptalEt')}
            </Button>
          )}
          <Button onClick={() => void iade()} disabled={mesgul} data-testid="pos-iade-onayla">
            <RotateCcw className="h-4 w-4" aria-hidden="true" />
            {t('stokPos.kasa.iadeEt')}
          </Button>
        </div>
      </div>
    </Pencere>
  );
}

function FaturaPenceresi({ api, satis, onBitti, onKapat }: { api: StokApi; satis: Satis; onBitti: () => void; onKapat: () => void }) {
  const { t, i18n } = useTranslation();
  const [a, setA] = useState({ ad: satis.musteri_ad || '', vergi_dairesi: '', vergi_no: '', adres: '', eposta: '' });
  const [kaydet, setKaydet] = useState(false);
  const [mesgul, setMesgul] = useState(false);
  const [hata, setHata] = useState<string | null>(null);
  const indir = async () => {
    try {
      await api.faturaPdf(satis, i18n.language);
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  };
  const kes = async () => {
    setMesgul(true);
    setHata(null);
    try {
      const s = await api.faturaKes(satis.id, satis.alici_id ? { alici_id: satis.alici_id } : { alici: a, kaydet });
      await api.faturaPdf(s, i18n.language);
      onBitti();
    } catch (e) {
      setHata(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };
  return (
    <Pencere baslik={t('stokPos.fatura.baslik', { no: satis.no })} onKapat={onKapat} testid="pos-fatura-pencere">
      <p className="mb-3 rounded-lg border border-amber-400/30 bg-amber-500/10 p-2 text-xs text-amber-100">{t('stokPos.fatura.uyari')}</p>
      {satis.fatura_no ? (
        <div className="space-y-3">
          <p className="text-sm">{t('stokPos.fatura.kesildi', { no: satis.fatura_no })}</p>
          <Button onClick={() => void indir()} className="gap-1.5">
            <FileText className="h-4 w-4" aria-hidden="true" />
            {t('stokPos.fatura.pdf')}
          </Button>
        </div>
      ) : satis.alici_id ? (
        <Button onClick={() => void kes()} disabled={mesgul}>
          {t('stokPos.fatura.kes')}
        </Button>
      ) : (
        <div className="space-y-2">
          <Alan etiket={t('stokPos.alici.ad')}>
            <input className={GIRDI} value={a.ad} onChange={(e) => setA({ ...a, ad: e.target.value })} data-testid="pos-fatura-ad" />
          </Alan>
          <div className="grid grid-cols-2 gap-2">
            <Alan etiket={t('stokPos.alici.vergiDairesi')}>
              <input className={GIRDI} value={a.vergi_dairesi} onChange={(e) => setA({ ...a, vergi_dairesi: e.target.value })} />
            </Alan>
            <Alan etiket={t('stokPos.alici.vergiNo')}>
              <input className={GIRDI} value={a.vergi_no} onChange={(e) => setA({ ...a, vergi_no: e.target.value })} inputMode="numeric" />
            </Alan>
          </div>
          <Alan etiket={t('stokPos.alici.adres')}>
            <input className={GIRDI} value={a.adres} onChange={(e) => setA({ ...a, adres: e.target.value })} />
          </Alan>
          <Alan etiket={t('stokPos.alici.eposta')}>
            <input className={GIRDI} value={a.eposta} onChange={(e) => setA({ ...a, eposta: e.target.value })} type="email" />
          </Alan>
          <Anahtar acik={kaydet} onDegis={setKaydet} etiket={t('stokPos.fatura.kaydet')} />
          {hata && <p className="text-sm text-red-300">{hata}</p>}
          <div className="flex justify-end">
            <Button onClick={() => void kes()} disabled={mesgul || !a.ad.trim()} data-testid="pos-fatura-kes">
              {t('stokPos.fatura.kes')}
            </Button>
          </div>
        </div>
      )}
    </Pencere>
  );
}

function KapanisPenceresi({ api, ozet, oturum, para: p, onBitti, onKapat }: { api: StokApi; ozet: Ozet; oturum: Oturum; para: (n: number) => string; onBitti: (r: { ozet: Ozet; oturum: Oturum }) => void; onKapat: () => void }) {
  const { t } = useTranslation();
  const [sayilan, setSayilan] = useState('');
  const [notlar, setNotlar] = useState('');
  const [mesgul, setMesgul] = useState(false);
  const [hata, setHata] = useState<string | null>(null);
  const sayilanKurus = kurusaCevir(sayilan);
  const beklenen = ozet.nakit?.beklenen ?? 0;
  const kapat = async () => {
    if (sayilanKurus === null) return;
    setMesgul(true);
    try {
      const r = await api.kasaKapat(oturum.id, { sayilan_nakit: tl(sayilanKurus), notlar: notlar || undefined });
      onBitti({ ozet: r.ozet, oturum: r.oturum });
    } catch (e) {
      setHata(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };
  return (
    <Pencere baslik={t('stokPos.kasa.gunSonu')} onKapat={onKapat} testid="pos-kapanis">
      <dl className="space-y-1 text-sm">
        <div className="flex justify-between">
          <dt className="text-muted-foreground">{t('stokPos.z.satisSayisi')}</dt>
          <dd>{ozet.satis_sayisi}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted-foreground">{t('stokPos.z.net')}</dt>
          <dd className="font-semibold">{p(ozet.net)}</dd>
        </div>
        {(['nakit', 'kart', 'havale'] as const).map((tur) => (
          <div key={tur} className="flex justify-between">
            <dt className="text-muted-foreground">{t(`stokPos.odeme.${tur}`)}</dt>
            <dd>{p(ozet.odemeler[tur])}</dd>
          </div>
        ))}
        <div className="flex justify-between border-t border-white/10 pt-1">
          <dt>{t('stokPos.z.beklenen')}</dt>
          <dd className="font-semibold" data-testid="pos-beklenen">
            {p(beklenen)}
          </dd>
        </div>
      </dl>
      <div className="mt-3 space-y-2">
        <Alan etiket={t('stokPos.z.sayilan')}>
          <input className={GIRDI} inputMode="decimal" value={sayilan} onChange={(e) => setSayilan(e.target.value)} autoFocus data-testid="pos-sayilan" />
        </Alan>
        {sayilanKurus !== null && (
          <p className={`text-sm font-semibold ${sayilanKurus - beklenen === 0 ? 'text-emerald-300' : 'text-amber-300'}`}>
            {t('stokPos.z.fark')}: {p(sayilanKurus - beklenen)}
          </p>
        )}
        <Alan etiket={t('stokPos.kasa.not')}>
          <input className={GIRDI} value={notlar} onChange={(e) => setNotlar(e.target.value)} maxLength={500} />
        </Alan>
        <p className="text-xs text-muted-foreground">{t('stokPos.z.maliDegil')}</p>
        {hata && <p className="text-sm text-red-300">{hata}</p>}
        <div className="flex justify-end">
          <Button onClick={() => void kapat()} disabled={mesgul || sayilanKurus === null} data-testid="pos-kapanis-onayla">
            <Lock className="h-4 w-4" aria-hidden="true" />
            {t('stokPos.kasa.kapatOnay')}
          </Button>
        </div>
      </div>
    </Pencere>
  );
}
