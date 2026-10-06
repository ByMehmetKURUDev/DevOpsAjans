"""Faz 2E — müşteri hesabında birden çok kişi (kişi bazlı yetki) + hesaplar arası geçiş.

Kapsam:
* Rol/izin matrisi: BÜTÜN müşteri uçları için sahip (başlıksız) geçer, izinli
  üye (`X-MK-Hesap`) geçer, izinsiz üye 403 `hesap_izni_yok`, üye olmayan 403
  `hesap_uyesi_degil`.
* Tarama: başkasının hesabını başlıkla isteyen üye-olmayan kişi, kişisel ya da
  herkese açık olarak işaretlenmemiş HİÇBİR uçtan 2xx almamalı (gözden kaçan uç kalmasın).
* Davet akışı, süre, tek kullanım, yanlış e-posta; üyelik silinince/pasifte
  erişim anında düşer; hesap yöneticisi yetki yükseltemez; bildirim alıcı
  genişletmesi; kişi yazar / hesap sahiplik ayrımı; güvenlik incelemesindeki
  IDOR düzeltmeleri.
"""

import io
import json
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from conftest import jeton_uret

BASLIK = "X-MK-Hesap"


def _e(on: str) -> str:
    return f"{on}-{uuid.uuid4().hex[:8]}@ekip.dev"


def _b(eposta: str, hesap: str | None = None, rol: str = "user") -> dict:
    h = {"Authorization": f"Bearer {jeton_uret(eposta, rol)}"}
    if hesap:
        h[BASLIK] = hesap
    return h


@pytest.fixture(autouse=True)
def _ortam(monkeypatch):
    """Modül kapısı bu dosyada konu değil: hepsi açık. Önbellek/hız sınırı temiz."""
    from routers import hesap_ekibi as r
    from services import hesap_ekibi as s
    from services import moduller

    async def _hep_acik(db, eposta, anahtar):
        return True

    monkeypatch.setattr(moduller, "modul_acik_mi", _hep_acik)
    from routers import site_bakim

    monkeypatch.setattr(site_bakim, "modul_acik_mi", _hep_acik)
    s.onbellegi_temizle()
    r._hiz.temizle()
    yield
    s.onbellegi_temizle()


async def _uye_ekle(db, hesap, uye, rol, izinler=None, durum="aktif"):
    from models.hesap_uyeleri import HesapUyeleri
    from services import hesap_ekibi as s

    satir = HesapUyeleri(
        hesap_email=hesap,
        uye_email=uye,
        rol=rol,
        izinler=json.dumps(list(izinler if izinler is not None else s.ROL_VARSAYILAN[rol])),
        durum=durum,
        olusturma=s.simdi(),
    )
    db.add(satir)
    await db.commit()
    await db.refresh(satir)
    s.onbellegi_temizle()
    return satir


async def _ekle(db, nesne):
    db.add(nesne)
    await db.commit()
    await db.refresh(nesne)
    return nesne


@pytest.fixture
async def ekip(db_oturumu):
    """Sahip + uye + fatura + kısıtlı (izinsiz) üye + yabancı; sahibin kayıtları."""
    from models.client_sites import Client_sites
    from models.dosyalar import BelgeTalepleri
    from models.geri_bildirim import FeedbackItems
    from models.inquiries import Inquiries
    from models.invoices import Invoices
    from models.pricing import Pricing_inquiries
    from models.projects import Projects
    from models.site_analyses import Site_analyses
    from models.support_tickets import Support_tickets
    from services import imzali_islem

    db = db_oturumu
    k = {
        "sahip": _e("sahip"),
        "uye": _e("uye"),
        "fatura": _e("fatura"),
        "kisitli": _e("kisitli"),
        "yabanci": _e("yabanci"),
    }
    await _uye_ekle(db, k["sahip"], k["uye"], "uye")
    await _uye_ekle(db, k["sahip"], k["fatura"], "fatura")
    await _uye_ekle(db, k["sahip"], k["kisitli"], "uye", izinler=[])

    s = k["sahip"]
    p = await _ekle(db, Projects(title="Gizli proje", description="d", category="Web", client_email=s,
                                  client_name="Sahip A.Ş.", published=False, status="in_progress"))
    f = await _ekle(db, Invoices(invoice_no=f"F-{uuid.uuid4().hex[:5]}", client_email=s, amount=100.0, status="unpaid"))
    t = await _ekle(db, Support_tickets(client_email=s, subject="Konu", message="Mesaj", status="open"))
    q = await _ekle(db, Inquiries(name="Sahip", email=s, message="Merhaba"))
    site = await _ekle(db, Client_sites(client_email=s, ad="Sahip sitesi", adres="https://sahip.example"))
    a = await _ekle(db, Site_analyses(alan_adi="sahip.example", url="https://sahip.example", durum="tamam", eposta=s,
                                       kaynak="musteri"))
    g = await _ekle(db, FeedbackItems(musteri_eposta=s, baslik="Hata", tur="hata", durum="yeni", oncelik="normal"))
    bt = await _ekle(db, BelgeTalepleri(client_email=s, baslik="Vergi levhası", durum="bekliyor"))
    teklif = await _ekle(db, Pricing_inquiries(scale_kod="kobi", profile_kod="standart", period="aylik",
                                               hesaplanan_tutar=100.0, musteri_eposta=s, kaynak="website"))
    _, islem_proje = await imzali_islem.olustur(db, "teslimat_onay", ("projects", p.id), s, "Teslim onayı")
    _, islem_teklif = await imzali_islem.olustur(db, "teklif_kabul", ("pricing_inquiries", teklif.id), s, "Teklif")
    # Faz 2G: sahibin konuşması ve ajansın bir mesajı.
    from models.mesajlar import KonusmaMesajlari, Konusmalar

    konusma = await _ekle(db, Konusmalar(hesap_email=s, konu="Ekip konuşması", durum="acik", degisiklik=0))
    ajans_mesaji = await _ekle(db, KonusmaMesajlari(konusma_id=konusma.id, yazan_email="yonetici@test.dev",
                                                    yazan_rol="admin", metin="Merhaba", silindi=False))
    konusma.son_mesaj_id = konusma.son_admin_mesaj_id = ajans_mesaji.id
    await db.commit()
    # Faz 3U: sahibin bir uzman asistan sohbeti (kişiye özel: üye 404 alır — "gecti").
    from models.uzman_asistanlar import AsistanSohbetleri

    asistan_sohbeti = await _ekle(db, AsistanSohbetleri(hesap_email=s, kisi_email=s, asistan_anahtar="seo-specialist",
                                                        baslik="Sahibin sohbeti", silindi=False))
    # Faz 4Q: sahibin bir dinamik QR kaydı.
    from models.dinamik_qr import DinamikQr

    qr = await _ekle(db, DinamikQr(hesap_email=s, kod=uuid.uuid4().hex[:7], ad="Sahibin QR'ı", tur="url",
                                   alanlar=json.dumps({"url": "https://sahip.example"}), hedef="https://sahip.example",
                                   tarama_sayisi=0))
    k.update(P=p.id, F=f.id, T=t.id, Q=q.id, S=site.id, A=a.id, G=g.id, B=bt.id,
             I_PROJE=islem_proje.id, I_TEKLIF=islem_teklif.id, K=konusma.id, KM=ajans_mesaji.id,
             AS=asistan_sohbeti.id, QR=qr.id)
    # Faz 4K: sahibin bir dijital kartviziti, yorum sayfası ve ikisine gelmiş birer mesaj.
    from models.kartvizit import KartvizitMesajlari, Kartvizitler, YorumSayfalari

    kart = await _ekle(db, Kartvizitler(hesap_email=s, kod="K" + uuid.uuid4().hex[:6], slug="sahip-" + uuid.uuid4().hex[:8],
                                        ad_soyad="Sahip Kişi", icerik=json.dumps({"ad_soyad": "Sahip Kişi"})))
    yorum = await _ekle(db, YorumSayfalari(hesap_email=s, kod="Y" + uuid.uuid4().hex[:6], slug="kafe-" + uuid.uuid4().hex[:8],
                                           isletme_adi="Sahip Kafe", place_id="ChIJN1t_tDeuEmsRUsoyG83frY4"))
    kart_mesaji = await _ekle(db, KartvizitMesajlari(sahip_tur="kart", sahip_id=kart.id, hesap_email=s, ad="Ziyaretçi",
                                                     eposta="z@ornek.com"))
    yorum_mesaji = await _ekle(db, KartvizitMesajlari(sahip_tur="yorum", sahip_id=yorum.id, hesap_email=s, mesaj="Geri bildirim"))
    k.update(KV=kart.id, YS=yorum.id, KVM=kart_mesaji.id, YSM=yorum_mesaji.id)
    # Faz 4M: sahibin bir QR menüsü (kategori + ürün + kupon + sipariş).
    from models.qr_menu import MenuKategorileri, MenuKuponlari, MenuMagazalari, MenuSiparisleri, MenuUrunleri

    menu = await _ekle(db, MenuMagazalari(hesap_email=s, slug=f"ekip-{uuid.uuid4().hex[:8]}", duzen="menu",
                                          ad="Sahibin menüsü", whatsapp="+905551112233"))
    mkat = await _ekle(db, MenuKategorileri(magaza_id=menu.id, ad="İçecekler", sira=1))
    murun = await _ekle(db, MenuUrunleri(magaza_id=menu.id, kategori_id=mkat.id, ad="Çay", fiyat=2000, sira=1))
    mkupon = await _ekle(db, MenuKuponlari(magaza_id=menu.id, kod="EKIP10", tur="yuzde", deger=10))
    msip = await _ekle(db, MenuSiparisleri(magaza_id=menu.id, siparis_no=uuid.uuid4().hex[:8].upper(), kalemler="[]",
                                           musteri_ad="Ali"))
    k.update(MM=menu.id, MK=mkat.id, MU=murun.id, MC=mkupon.id, MS=msip.id)
    # Faz 4A: `api` izni yalnız hesap yöneticisinin varsayılanında — izinli üye ayrıca; sahibin
    # bir API anahtarı ve (pasif: başka testlerin kayıtlarından olay üretmesin) bir webhook uç noktası.
    from models.api_erisimi import ApiAnahtarlari, WebhookUcNoktalari

    k["apici"] = _e("apici")
    await _uye_ekle(db, s, k["apici"], "uye", izinler=["projeler", "api"])
    ak = await _ekle(db, ApiAnahtarlari(sahip_tur="musteri", hesap_email=s, ad="Ekip anahtarı", onek=uuid.uuid4().hex[:8],
                                        anahtar_ozeti=uuid.uuid4().hex + uuid.uuid4().hex, kapsamlar='["projeler:oku"]',
                                        dakika_siniri=60, olusturan=s))
    wh = await _ekle(db, WebhookUcNoktalari(sahip_tur="musteri", hesap_email=s, url="https://ekip.ornek.com/kanca",
                                            olaylar='["fatura.odendi"]', aktif=False, gizli_anahtar="d1:whsec_ekip",
                                            ardisik_hata=0))
    k.update(AK=ak.id, WH=wh.id)
    # Faz 5R: sahibin randevu sayfası (kişi + tür + gelecekte bir randevu).
    from datetime import datetime as _dt
    from datetime import timezone as _tz

    from models.randevu import Randevular, RandevuKisileri, RandevuSayfalari, RandevuTurleri

    rs = await _ekle(db, RandevuSayfalari(hesap_email=s, slug=f"ekip-{uuid.uuid4().hex[:8]}", baslik="Sahibin randevuları"))
    rk_ = await _ekle(db, RandevuKisileri(sayfa_id=rs.id, eposta=s, ad="Sahip", haftalik="{}"))
    rt = await _ekle(db, RandevuTurleri(sayfa_id=rs.id, slug="tanisma", ad="Tanışma", kisiler=f"[{rk_.id}]"))
    rbas = _dt(2030, 1, 7, 9, 0, tzinfo=_tz.utc)
    rr = await _ekle(db, Randevular(uid=uuid.uuid4().hex, sayfa_id=rs.id, tur_id=rt.id, kisi_id=rk_.id, hesap_email=s,
                                    baslangic=rbas, bitis=rbas + timedelta(minutes=30), dolu_bas=rbas,
                                    dolu_bit=rbas + timedelta(minutes=30), koltuk=0, ad="Ziyaretçi", eposta="z@ornek.com"))
    k.update(RS=rs.id, RK=rk_.id, RT=rt.id, RR=rr.id)
    # Faz 4W: `otomasyon` izni yalnız hesap yöneticisinin varsayılanında — API üyesine (apici) ayrıca
    # veriliyor (üye sayısı değişmesin); sahibin bir (pasif) kuralı.
    from models.hesap_uyeleri import HesapUyeleri
    from models.otomasyon import OtomasyonKurallari
    from services import hesap_ekibi as _he
    from sqlalchemy import update as _update

    await db.execute(_update(HesapUyeleri).where(HesapUyeleri.hesap_email == s, HesapUyeleri.uye_email == k["apici"])
                     .values(izinler=json.dumps(["projeler", "api", "otomasyon"])))
    await db.commit()
    _he.onbellegi_temizle()
    ok = await _ekle(db, OtomasyonKurallari(sahip_tur="musteri", hesap_email=s, ad="Sahibin kuralı", aktif=False,
                                            tetik="destek.olusturuldu", eylemler='[{"tur": "bildirim", "alici": "hesap", "baslik": "x"}]'))
    k.update(OK=ok.id)
    # Faz 5A: sahibin AI asistanı (bir metin kaynağı + bir ziyaretçi sohbeti).
    from models.ai_asistan import AiAsistanKaynaklari, AiAsistanlar, AiAsistanSohbetleri
    from services.ai_asistan import yeni_anahtar

    aia = await _ekle(db, AiAsistanlar(hesap_email=s, anahtar=yeni_anahtar(), ad="Sahibin asistanı", dizin_surumu=0))
    aik = await _ekle(db, AiAsistanKaynaklari(asistan_id=aia.id, hesap_email=s, tur="metin", baslik="Not", metin="Sahibin notu.",
                                              durum="hazir"))
    ais = await _ekle(db, AiAsistanSohbetleri(asistan_id=aia.id, hesap_email=s, oturum_ozeti=uuid.uuid4().hex, kaynak="sayfa"))
    k.update(AIA=aia.id, AIK=aik.id, AIS=ais.id)
    # Faz 5I: sahibin içerik stüdyosu kayıtları (marka, şablon, kendi gönderisi).
    from models.content_posts import Content_posts
    from models.icerik_studyosu import IcerikMarkalari, IcerikSablonlari

    im = await _ekle(db, IcerikMarkalari(hesap_email=s, ad="Sahibin markası", ton="{}"))
    isb = await _ekle(db, IcerikSablonlari(hesap_email=s, ad="Sahibin şablonu", alanlar="[]", istem="Yaz"))
    ig = await _ekle(db, Content_posts(title="Sahibin gönderisi", hesap_email=s, yoneten="musteri", status="taslak",
                                       kanallar='["instagram"]', channel="instagram", body="Merhaba"))
    k.update(IM=im.id, IS=isb.id, IG=ig.id)
    # Faz 5M: `pazarlama` izni yalnız hesap yöneticisinin varsayılanında — izinli üye ayrıca; sahibin
    # e-posta pazarlama kayıtları (liste, kişi, form, segment, taslak kampanya, dizi).
    from models.eposta_pazarlama import EpDiziler, EpFormlar, EpKampanyalar, EpKisiler, EpListeler, EpSegmentler

    k["pazarlamaci"] = _e("pazarlamaci")
    await _uye_ekle(db, s, k["pazarlamaci"], "uye", izinler=["projeler", "pazarlama"])
    el = await _ekle(db, EpListeler(hesap_email=s, ad="Sahibin bülteni"))
    ek_ = await _ekle(db, EpKisiler(kapsam=s, hesap_email=s, eposta=f"abone-{uuid.uuid4().hex[:6]}@ornek.com", alici_turu="bireysel",
                                    izin_durumu="izinsiz", kaynak="manuel", etiketler="[]", ozel_alanlar="{}", dil="tr"))
    ef = await _ekle(db, EpFormlar(hesap_email=s, liste_id=el.id, ad="Sahibin formu", genel_anahtar="ekip" + uuid.uuid4().hex[:10]))
    es = await _ekle(db, EpSegmentler(hesap_email=s, ad="Sahibin segmenti",
                                      kurallar=json.dumps({"birlesim": "ve", "kurallar": [{"alan": "kaynak", "op": "esit", "deger": "manuel"}]})))
    ekp = await _ekle(db, EpKampanyalar(hesap_email=s, ad="Sahibin kampanyası", durum="taslak", konu="Merhaba",
                                        bloklar=json.dumps([{"tur": "metin", "metin": "Merhaba"}])))
    ed = await _ekle(db, EpDiziler(hesap_email=s, ad="Sahibin dizisi", tetik="abonelik_onaylandi", liste_id=el.id, aktif=False))
    k.update(EL=el.id, EK=ek_.id, EF=ef.id, ES=es.id, EKP=ekp.id, ED=ed.id)
    # Faz 6S: saha servisi izinleri (`saha_yonetim`, `saha_teknisyen`) üye/fatura rolünün varsayılanında
    # yok — izinli üye ("sahaci") ayrıca; sahibin servis kayıtları ve sahacıya atanmış bir iş emri.
    from models.saha_servisi import (
        SahaCihazlari,
        SahaIsAtamalari,
        SahaIsEmirleri,
        SahaLokasyonlari,
        SahaMalzemeleri,
        SahaMusterileri,
        SahaSablonlari,
        SahaTeknisyenleri,
    )

    k["sahaci"] = _e("sahaci")
    await _uye_ekle(db, s, k["sahaci"], "uye", izinler=["projeler", "saha_yonetim", "saha_teknisyen"])
    st = await _ekle(db, SahaTeknisyenleri(hesap_email=s, eposta=k["sahaci"], ad="Sahacı"))
    sm = await _ekle(db, SahaMusterileri(hesap_email=s, ad="Servis müşterisi", eposta="servis@ornek.com"))
    sl = await _ekle(db, SahaLokasyonlari(hesap_email=s, musteri_id=sm.id, ad="Ev", adres="Ekip Sk. 1"))
    sc = await _ekle(db, SahaCihazlari(hesap_email=s, musteri_id=sm.id, lokasyon_id=sl.id, tur="Klima"))
    ss = await _ekle(db, SahaSablonlari(hesap_email=s, ad="Ekip şablonu", maddeler="[]"))
    smz = await _ekle(db, SahaMalzemeleri(hesap_email=s, ad="Gaz", birim="kg", birim_fiyat=100, stok=10.0))
    si = await _ekle(db, SahaIsEmirleri(hesap_email=s, no=f"IE-EKIP-{uuid.uuid4().hex[:4]}", uid=uuid.uuid4().hex, tur="ariza",
                                        durum="yeni", baslik="Ekip işi", musteri_id=sm.id, lokasyon_id=sl.id,
                                        kontrol_listesi="[]", kontrol_yanitlari="{}"))
    await _ekle(db, SahaIsAtamalari(is_emri_id=si.id, teknisyen_id=st.id, hesap_email=s))
    k.update(ST=st.id, SM=sm.id, SL=sl.id, SC=sc.id, SS=ss.id, SMZ=smz.id, SI=si.id)
    # Faz 6E: `etkinlik` (yönetim) izni üyenin varsayılanında yok — pazarlama üyesine (pazarlamaci) ayrıca
    # veriliyor (üye sayısı değişmesin); `etkinlik_giris` (yalnız okutma) üyede var. Sahibin bir etkinliği
    # (tür + indirim + kayıt + bilet).
    from datetime import datetime as _dt6
    from datetime import timezone as _tz6

    from models.etkinlik import EtkinlikBiletleri, EtkinlikBiletTurleri, EtkinlikIndirimKodlari, Etkinlikler, EtkinlikSiparisleri

    await db.execute(_update(HesapUyeleri).where(HesapUyeleri.hesap_email == s, HesapUyeleri.uye_email == k["pazarlamaci"])
                     .values(izinler=json.dumps(["projeler", "pazarlama", "etkinlik"])))
    await db.commit()
    _he.onbellegi_temizle()
    eb = _dt6(2030, 1, 7, 9, 0, tzinfo=_tz6.utc)
    et = await _ekle(db, Etkinlikler(hesap_email=s, slug=f"ekip-{uuid.uuid4().hex[:8]}", baslik="Sahibin etkinliği",
                                     baslangic=eb, bitis=eb + timedelta(hours=3), durum="yayinda", kapasite=50))
    ett = await _ekle(db, EtkinlikBiletTurleri(etkinlik_id=et.id, ad="Standart", fiyat=0))
    eti = await _ekle(db, EtkinlikIndirimKodlari(etkinlik_id=et.id, kod="SAHIP10", tur="yuzde", deger=10))
    ets = await _ekle(db, EtkinlikSiparisleri(etkinlik_id=et.id, hesap_email=s, kod=uuid.uuid4().hex[:8].upper(), ad="Katılımcı",
                                              eposta="katilimci@ornek.com", durum="onayli"))
    etb = await _ekle(db, EtkinlikBiletleri(etkinlik_id=et.id, siparis_id=ets.id, tur_id=ett.id,
                                            kod=uuid.uuid4().hex[:10].upper(), durum="gecerli", koltuk=0))
    k.update(ET=et.id, ETT=ett.id, ETI=eti.id, ETS=ets.id, ETB=etb.id)
    return k


# ---------------------------------------------------------------------------
# Müşteri uçları × izin matrisi
# ---------------------------------------------------------------------------
#: (metot, yol, izinler (biri yeterli; None = her aktif üye), gövde, sahip için beklenen)
#: Beklenen `"gecti"`: hesap/izin kontrolünden geçti (401 ya da hesap 403'ü değil);
#: kayıt yok (404), gövde geçersiz (422), iş kuralı (409) olabilir.
GOVDE_DOSYA = "__dosya__"
#: Faz 6S: router düzeyinde iki izinden biri yeterli (yönetim ya da teknisyen).
SAHA = ("saha_yonetim", "saha_teknisyen")
MUSTERI_UCLARI = [
    ("GET", "/api/v1/entities/projects", ("projeler",), None, 200),
    ("GET", "/api/v1/entities/projects/all", ("projeler",), None, 200),
    ("GET", "/api/v1/entities/projects/{P}", ("projeler",), None, 200),
    ("GET", "/api/v1/entities/project_events?project_id={P}", ("projeler",), None, 200),
    ("GET", "/api/v1/entities/inquiries", ("projeler",), None, 200),
    ("GET", "/api/v1/entities/inquiries/all", ("projeler",), None, 200),
    ("GET", "/api/v1/entities/inquiries/{Q}", ("projeler",), None, 200),
    ("GET", "/api/v1/entities/invoices", ("faturalar",), None, 200),
    ("GET", "/api/v1/entities/invoices/all", ("faturalar",), None, 200),
    ("GET", "/api/v1/entities/invoices/{F}", ("faturalar",), None, 200),
    ("GET", "/api/v1/entities/support_tickets", ("destek",), None, 200),
    ("GET", "/api/v1/entities/support_tickets/all", ("destek",), None, 200),
    ("GET", "/api/v1/entities/support_tickets/{T}", ("destek",), None, 200),
    ("POST", "/api/v1/entities/support_tickets", ("destek",), {"subject": "Yeni", "message": "Metin"}, 201),
    ("GET", "/api/v1/talep/{T}/mesajlar", ("destek",), None, 200),
    ("POST", "/api/v1/talep/{T}/mesaj", ("destek",), {"mesaj": "Ekipten yanıt"}, 200),
    ("POST", "/api/v1/talep/{T}/ekler/999999/indirme-baglantisi", ("destek",), None, "gecti"),
    ("GET", "/api/v1/destek/sla-bilgisi", ("destek",), None, 200),
    ("GET", "/api/v1/kredilerim", ("krediler",), None, 200),
    ("GET", "/api/v1/dosyalarim", ("dosyalar",), None, 200),
    ("POST", "/api/v1/dosyalarim/yukle", ("dosyalar",), GOVDE_DOSYA, "gecti"),
    ("POST", "/api/v1/dosyalarim/999999/indirme-baglantisi", ("dosyalar",), None, "gecti"),
    ("GET", "/api/v1/dosyalarim/talepler", ("dosyalar",), None, 200),
    ("POST", "/api/v1/dosyalarim/talepler/{B}/yukle", ("dosyalar",), GOVDE_DOSYA, "gecti"),
    ("GET", "/api/v1/gorevlerim/revizyon", ("gorevler",), None, 200),
    ("GET", "/api/v1/gorevlerim/proje/{P}", ("gorevler",), None, 200),
    ("GET", "/api/v1/islemlerim", ("faturalar", "projeler", "raporlar"), None, 200),
    ("POST", "/api/v1/islemlerim/{I_PROJE}", ("projeler",), {"sonuc": "onay"}, "gecti"),
    ("POST", "/api/v1/islemlerim/{I_TEKLIF}", ("faturalar",), {"sonuc": "red", "not": "pahalı"}, "gecti"),
    ("GET", "/api/v1/raporlarim", ("raporlar", "abonelikler"), None, 200),
    ("GET", "/api/v1/raporlarim/aylik", ("raporlar",), None, 200),
    ("GET", "/api/v1/site-analizi/benim", ("siteler",), None, 200),
    ("POST", "/api/v1/site-analizi/benim", ("siteler",), {}, "gecti"),
    ("GET", "/api/v1/site-analizi/benim/{A}", ("siteler",), None, 200),
    ("GET", "/api/v1/sitelerim", ("siteler",), None, 200),
    ("POST", "/api/v1/sitelerim/{S}/izin", ("siteler",), {"izin": True}, 200),
    ("GET", "/api/v1/sitelerim/{S}/gunluk", ("siteler",), None, 200),
    ("GET", "/api/v1/sitelerim-bakim", ("siteler",), None, 200),
    ("POST", "/api/v1/sitelerim-bakim/{S}/durum-sayfasi", ("siteler",), {"acik": False}, 200),
    # Faz 2H — teknik SEO + hız izleme (tarama ağsız: conftest DNS'i kapatıyor → hata satırı, 200).
    ("GET", "/api/v1/sitelerim/{S}/seo-gecmisi", ("siteler",), None, 200),
    ("POST", "/api/v1/sitelerim/{S}/seo-tara", ("siteler",), None, "gecti"),
    ("GET", "/api/v1/geri-bildirimlerim", ("projeler", "destek"), None, 200),
    ("POST", "/api/v1/geri-bildirimlerim", ("projeler", "destek"), {"__form__": {"baslik": "Buton bozuk"}}, 200),
    ("POST", "/api/v1/geri-bildirimlerim/{G}/ek", ("projeler", "destek"), GOVDE_DOSYA, "gecti"),
    ("GET", "/api/v1/geri-bildirim-ek/999999", ("projeler", "destek"), None, "gecti"),
    ("GET", "/api/v1/cop-kutum", None, None, 200),
    ("POST", "/api/v1/cop-kutum/999999/geri-al", None, None, "gecti"),
    ("GET", "/api/v1/denetim/benim", None, None, 200),
    ("GET", "/api/v1/modullerim", None, None, 200),
    ("GET", "/api/v1/duyurularim", None, None, 200),
    ("POST", "/api/v1/duyurularim/999999/okundu", None, None, "gecti"),
    ("POST", "/api/v1/duyurularim/999999/kapat", None, None, "gecti"),
    ("GET", "/api/v1/hesabim/uyeler", None, None, 200),
    # Faz 2G — mesajlaşma (`mesajlar` izni).
    ("GET", "/api/v1/mesajlarim/ozet", ("mesajlar",), None, 200),
    ("GET", "/api/v1/mesajlarim/konusmalar", ("mesajlar",), None, 200),
    ("POST", "/api/v1/mesajlarim/konusmalar", ("mesajlar",), {"konu": "Ekipten konu"}, 200),
    ("GET", "/api/v1/mesajlarim/konusmalar/{K}/mesajlar", ("mesajlar",), None, 200),
    ("POST", "/api/v1/mesajlarim/konusmalar/{K}/mesajlar", ("mesajlar",), {"metin": "Ekipten mesaj"}, 200),
    ("POST", "/api/v1/mesajlarim/konusmalar/{K}/okundu", ("mesajlar",), {"mesaj_id": 1}, 200),
    ("PUT", "/api/v1/mesajlarim/mesajlar/{KM}", ("mesajlar",), {"metin": "değiştir"}, "gecti"),
    ("DELETE", "/api/v1/mesajlarim/mesajlar/{KM}", ("mesajlar",), None, "gecti"),
    ("POST", "/api/v1/mesajlarim/ekler", ("mesajlar",), GOVDE_DOSYA, "gecti"),
    ("POST", "/api/v1/mesajlarim/mesajlar/{KM}/ekler/999999/indirme-baglantisi", ("mesajlar",), None, "gecti"),
    # Faz 3U — Uzman Asistanlar (model çağrısı conftest'te "ağ yok": mesaj ucu 503/409 → "gecti").
    ("GET", "/api/v1/asistanlarim", ("asistanlar",), None, 200),
    ("GET", "/api/v1/asistanlarim/sohbetler", ("asistanlar",), None, 200),
    ("POST", "/api/v1/asistanlarim/sohbetler", ("asistanlar",), {"asistan_anahtar": "seo-specialist"}, "gecti"),
    ("GET", "/api/v1/asistanlarim/sohbetler/{AS}", ("asistanlar",), None, 200),
    ("POST", "/api/v1/asistanlarim/sohbetler/{AS}/mesaj", ("asistanlar",), {"icerik": "Merhaba"}, "gecti"),
    ("DELETE", "/api/v1/asistanlarim/sohbetler/999999", ("asistanlar",), None, "gecti"),
    # Faz 4Q — Dinamik QR ve kısa link (`qr` izni).
    ("GET", "/api/v1/qr-kodlarim/meta", ("qr",), None, 200),
    ("GET", "/api/v1/qr-kodlarim", ("qr",), None, 200),
    ("POST", "/api/v1/qr-kodlarim", ("qr",), {"ad": "Ekip QR", "tur": "url", "alanlar": {"url": "https://ornek.com"}}, 200),
    ("POST", "/api/v1/qr-kodlarim/onizleme", ("qr",), {"tur": "url"}, 200),
    ("POST", "/api/v1/qr-kodlarim/toplu/onizleme", ("qr",), GOVDE_DOSYA, "gecti"),
    ("POST", "/api/v1/qr-kodlarim/toplu/olustur", ("qr",), {"satirlar": []}, "gecti"),
    ("POST", "/api/v1/qr-kodlarim/zip", ("qr",), {"idler": [999999], "bicim": "svg"}, "gecti"),
    ("GET", "/api/v1/qr-kodlarim/{QR}", ("qr",), None, 200),
    ("PUT", "/api/v1/qr-kodlarim/{QR}", ("qr",), {"ad": "Yeni ad"}, 200),
    ("GET", "/api/v1/qr-kodlarim/{QR}/analiz", ("qr",), None, 200),
    ("GET", "/api/v1/qr-kodlarim/{QR}/gorsel?bicim=svg", ("qr",), None, 200),
    ("DELETE", "/api/v1/qr-kodlarim/999999", ("qr",), None, "gecti"),
    # Faz 4K — Dijital kartvizit ve Google yorum sayfası (`kartvizit` izni).
    ("GET", "/api/v1/kartvizitlerim/meta", ("kartvizit",), None, 200),
    ("GET", "/api/v1/kartvizitlerim/slug-uygun?slug=ekip-karti", ("kartvizit",), None, 200),
    ("GET", "/api/v1/kartvizitlerim/mesajlar", ("kartvizit",), None, 200),
    ("PUT", "/api/v1/kartvizitlerim/mesajlar/{KVM}", ("kartvizit",), {"okundu": True}, 200),
    ("DELETE", "/api/v1/kartvizitlerim/mesajlar/999999", ("kartvizit",), None, "gecti"),
    ("GET", "/api/v1/kartvizitlerim", ("kartvizit",), None, 200),
    ("POST", "/api/v1/kartvizitlerim", ("kartvizit",), {"icerik": {"ad_soyad": "Ekip Kartı"}}, 200),
    ("GET", "/api/v1/kartvizitlerim/{KV}", ("kartvizit",), None, 200),
    ("PUT", "/api/v1/kartvizitlerim/{KV}", ("kartvizit",), {"aktif": True}, 200),
    ("POST", "/api/v1/kartvizitlerim/{KV}/gorsel", ("kartvizit",), GOVDE_DOSYA, "gecti"),
    ("DELETE", "/api/v1/kartvizitlerim/{KV}/gorsel/999999", ("kartvizit",), None, "gecti"),
    ("PUT", "/api/v1/kartvizitlerim/{KV}/galeri-sira", ("kartvizit",), {"idler": []}, 200),
    ("GET", "/api/v1/kartvizitlerim/{KV}/analiz", ("kartvizit",), None, 200),
    ("GET", "/api/v1/kartvizitlerim/{KV}/qr?bicim=svg", ("kartvizit",), None, 200),
    ("DELETE", "/api/v1/kartvizitlerim/999999", ("kartvizit",), None, "gecti"),
    ("GET", "/api/v1/yorum-sayfalarim/meta", ("kartvizit",), None, 200),
    ("GET", "/api/v1/yorum-sayfalarim/slug-uygun?slug=ekip-kafe", ("kartvizit",), None, 200),
    ("GET", "/api/v1/yorum-sayfalarim/geri-bildirimler", ("kartvizit",), None, 200),
    ("PUT", "/api/v1/yorum-sayfalarim/geri-bildirimler/{YSM}", ("kartvizit",), {"okundu": True}, 200),
    ("DELETE", "/api/v1/yorum-sayfalarim/geri-bildirimler/999999", ("kartvizit",), None, "gecti"),
    ("GET", "/api/v1/yorum-sayfalarim", ("kartvizit",), None, 200),
    ("POST", "/api/v1/yorum-sayfalarim", ("kartvizit",), {"isletme_adi": "Ekip Kafe", "place_id": "ChIJN1t_tDeuEmsRUsoyG83frY4"}, 200),
    ("GET", "/api/v1/yorum-sayfalarim/{YS}", ("kartvizit",), None, 200),
    ("PUT", "/api/v1/yorum-sayfalarim/{YS}", ("kartvizit",), {"aktif": True}, 200),
    ("POST", "/api/v1/yorum-sayfalarim/{YS}/logo", ("kartvizit",), GOVDE_DOSYA, "gecti"),
    ("DELETE", "/api/v1/yorum-sayfalarim/{YS}/logo", ("kartvizit",), None, 200),
    ("GET", "/api/v1/yorum-sayfalarim/{YS}/analiz", ("kartvizit",), None, 200),
    ("GET", "/api/v1/yorum-sayfalarim/{YS}/qr?bicim=svg", ("kartvizit",), None, 200),
    ("DELETE", "/api/v1/yorum-sayfalarim/999999", ("kartvizit",), None, "gecti"),
    # Faz 4M — QR menü ve WhatsApp katalog (`menu` izni). Sahibin zaten bir menüsü var:
    # yeni mağaza sınırda (409) → "gecti".
    ("GET", "/api/v1/menulerim/meta", ("menu",), None, 200),
    ("GET", "/api/v1/menulerim/siparis-ozeti", ("menu",), None, 200),
    ("GET", "/api/v1/menulerim", ("menu",), None, 200),
    ("POST", "/api/v1/menulerim", ("menu",), {"ad": "Ekip menüsü", "duzen": "menu"}, "gecti"),
    ("GET", "/api/v1/menulerim/{MM}", ("menu",), None, 200),
    ("PUT", "/api/v1/menulerim/{MM}", ("menu",), {"aciklama": "Ekipten"}, 200),
    ("GET", "/api/v1/menulerim/{MM}/icerik", ("menu",), None, 200),
    ("POST", "/api/v1/menulerim/{MM}/kategoriler", ("menu",), {"ad": "Tatlılar"}, 200),
    ("POST", "/api/v1/menulerim/{MM}/kategoriler/sirala", ("menu",), {"idler": []}, 200),
    ("PUT", "/api/v1/menulerim/{MM}/kategoriler/{MK}", ("menu",), {"ad": "Sıcak içecekler"}, 200),
    ("DELETE", "/api/v1/menulerim/{MM}/kategoriler/999999", ("menu",), None, "gecti"),
    ("POST", "/api/v1/menulerim/{MM}/urunler", ("menu",), {"kategori_id": 999999, "ad": "Kahve", "fiyat": "45"}, "gecti"),
    ("POST", "/api/v1/menulerim/{MM}/urunler/sirala", ("menu",), {"idler": []}, 200),
    ("PUT", "/api/v1/menulerim/{MM}/urunler/{MU}", ("menu",), {"fiyat": "25,50"}, 200),
    ("DELETE", "/api/v1/menulerim/{MM}/urunler/999999", ("menu",), None, "gecti"),
    ("POST", "/api/v1/menulerim/{MM}/gorsel", ("menu",), GOVDE_DOSYA, "gecti"),
    ("POST", "/api/v1/menulerim/{MM}/ceviri", ("menu",), {"tur": "magaza"}, "gecti"),
    ("GET", "/api/v1/menulerim/{MM}/kuponlar", ("menu",), None, 200),
    ("POST", "/api/v1/menulerim/{MM}/kuponlar", ("menu",), {"kod": "YENI5", "tur": "yuzde", "deger": 5}, "gecti"),
    ("PUT", "/api/v1/menulerim/{MM}/kuponlar/{MC}", ("menu",), {"aktif": True}, 200),
    ("DELETE", "/api/v1/menulerim/{MM}/kuponlar/999999", ("menu",), None, "gecti"),
    ("GET", "/api/v1/menulerim/{MM}/siparisler", ("menu",), None, 200),
    ("GET", "/api/v1/menulerim/{MM}/siparisler/{MS}", ("menu",), None, 200),
    ("PUT", "/api/v1/menulerim/{MM}/siparisler/{MS}", ("menu",), {"durum": "hazirlaniyor"}, 200),
    ("GET", "/api/v1/menulerim/{MM}/analiz", ("menu",), None, 200),
    ("GET", "/api/v1/menulerim/{MM}/qr?bicim=svg", ("menu",), None, 200),
    ("POST", "/api/v1/menulerim/{MM}/masa-qr", ("menu",), {"bas": 1, "bit": 2, "bicim": "svg"}, "gecti"),
    ("POST", "/api/v1/menulerim/{MM}/ice-aktar/onizleme", ("menu",), GOVDE_DOSYA, "gecti"),
    ("POST", "/api/v1/menulerim/{MM}/ice-aktar", ("menu",), {"satirlar": []}, "gecti"),
    ("DELETE", "/api/v1/menulerim/999999", ("menu",), None, "gecti"),
    # Faz 5R — randevu ve toplantılar (`randevu` izni). Sahibin zaten bir sayfası var: yeni sayfa 409 → "gecti".
    ("GET", "/api/v1/randevularim/meta", ("randevu",), None, 200),
    ("GET", "/api/v1/randevularim", ("randevu",), None, 200),
    ("POST", "/api/v1/randevularim", ("randevu",), {"baslik": "Ekip sayfası"}, "gecti"),
    ("GET", "/api/v1/randevularim/{RS}", ("randevu",), None, 200),
    ("PUT", "/api/v1/randevularim/{RS}", ("randevu",), {"karsilama": "Ekipten"}, 200),
    ("DELETE", "/api/v1/randevularim/999999", ("randevu",), None, "gecti"),
    ("POST", "/api/v1/randevularim/{RS}/logo", ("randevu",), GOVDE_DOSYA, "gecti"),
    ("DELETE", "/api/v1/randevularim/{RS}/logo", ("randevu",), None, 200),
    ("POST", "/api/v1/randevularim/{RS}/besleme/yenile", ("randevu",), None, 200),
    ("GET", "/api/v1/randevularim/{RS}/qr?bicim=svg", ("randevu",), None, 200),
    ("GET", "/api/v1/randevularim/{RS}/analiz", ("randevu",), None, 200),
    ("GET", "/api/v1/randevularim/{RS}/turler", ("randevu",), None, 200),
    ("POST", "/api/v1/randevularim/{RS}/turler", ("randevu",), {"ad": "Ekip türü"}, "gecti"),
    ("PUT", "/api/v1/randevularim/{RS}/turler/{RT}", ("randevu",), {"aciklama": "Ekipten"}, 200),
    ("DELETE", "/api/v1/randevularim/{RS}/turler/999999", ("randevu",), None, "gecti"),
    ("GET", "/api/v1/randevularim/{RS}/kisiler", ("randevu",), None, 200),
    ("POST", "/api/v1/randevularim/{RS}/kisiler", ("randevu",), {"eposta": "aday-degil@ornek.com"}, "gecti"),
    ("PUT", "/api/v1/randevularim/{RS}/kisiler/{RK}", ("randevu",), {"ad": "Sahip"}, 200),
    ("DELETE", "/api/v1/randevularim/{RS}/kisiler/999999", ("randevu",), None, "gecti"),
    ("GET", "/api/v1/randevularim/{RS}/istisnalar", ("randevu",), None, 200),
    ("POST", "/api/v1/randevularim/{RS}/istisnalar", ("randevu",), {"tarih": "2030-01-02", "araliklar": []}, 200),
    ("DELETE", "/api/v1/randevularim/{RS}/istisnalar/999999", ("randevu",), None, "gecti"),
    ("GET", "/api/v1/randevularim/{RS}/randevular", ("randevu",), None, 200),
    ("GET", "/api/v1/randevularim/{RS}/randevular/{RR}", ("randevu",), None, 200),
    ("POST", "/api/v1/randevularim/{RS}/randevular/999999/iptal", ("randevu",), {}, "gecti"),
    ("PUT", "/api/v1/randevularim/{RS}/randevular/{RR}/katilim", ("randevu",), {"katilim": "geldi"}, "gecti"),
    # Faz 3T — faturalarım (bakiye, PDF, ödeme bağlantısı), tekliflerim, sözleşmelerim (`faturalar` izni).
    ("GET", "/api/v1/faturalarim", ("faturalar",), None, 200),
    ("GET", "/api/v1/faturalarim/{F}", ("faturalar",), None, 200),
    ("GET", "/api/v1/faturalarim/{F}/pdf", ("faturalar",), None, 200),
    ("POST", "/api/v1/faturalarim/{F}/odeme-baglantisi", ("faturalar",), None, 200),
    ("GET", "/api/v1/faturalarim/{F}/odemeler/999999/dekont", ("faturalar",), None, "gecti"),
    ("GET", "/api/v1/tekliflerim", ("faturalar",), None, 200),
    ("GET", "/api/v1/tekliflerim/999999", ("faturalar",), None, "gecti"),
    ("POST", "/api/v1/tekliflerim/999999/karar", ("faturalar",), {"sonuc": "kabul", "ad_soyad": "Ekip Üyesi"}, "gecti"),
    ("GET", "/api/v1/tekliflerim/999999/pdf", ("faturalar",), None, "gecti"),
    ("GET", "/api/v1/sozlesmelerim", ("faturalar",), None, 200),
    ("GET", "/api/v1/sozlesmelerim/999999", ("faturalar",), None, "gecti"),
    ("POST", "/api/v1/sozlesmelerim/999999/imza", ("faturalar",), {"ad_soyad": "Ekip Üyesi", "onay": True}, "gecti"),
    ("GET", "/api/v1/sozlesmelerim/999999/pdf", ("faturalar",), None, "gecti"),
    # Faz 3Z — projenin harcanan süre özeti (`projeler` izni; modül + proje ayarı kapalıysa 403/404 → "gecti").
    ("GET", "/api/v1/zamanim/proje/{P}", ("projeler",), None, "gecti"),
    # Faz 4A — API anahtarları ve webhook'lar (`api` izni). Webhook adresi DNS'siz test ortamında
    # çözülemiyor (400) → "gecti"; test gönderimi 200 (teslimat başarısız kaydedilir).
    ("GET", "/api/v1/api-erisimim/meta", ("api",), None, 200),
    ("GET", "/api/v1/api-erisimim/anahtarlar", ("api",), None, 200),
    ("POST", "/api/v1/api-erisimim/anahtarlar", ("api",), {"ad": "Ekip", "kapsamlar": ["projeler:oku"]}, 200),
    ("POST", "/api/v1/api-erisimim/anahtarlar/{AK}/iptal", ("api",), None, 200),
    ("GET", "/api/v1/api-erisimim/webhooklar", ("api",), None, 200),
    ("POST", "/api/v1/api-erisimim/webhooklar", ("api",), {"url": "https://x.ornek.com/k", "olaylar": ["fatura.odendi"]}, "gecti"),
    ("PUT", "/api/v1/api-erisimim/webhooklar/{WH}", ("api",), {"aciklama": "Ekip"}, 200),
    ("POST", "/api/v1/api-erisimim/webhooklar/{WH}/gizli-yenile", ("api",), None, 200),
    ("POST", "/api/v1/api-erisimim/webhooklar/{WH}/test", ("api",), None, 200),
    ("GET", "/api/v1/api-erisimim/webhooklar/{WH}/teslimatlar", ("api",), None, 200),
    ("POST", "/api/v1/api-erisimim/webhooklar/{WH}/teslimatlar/999999/yeniden-gonder", ("api",), None, "gecti"),
    ("DELETE", "/api/v1/api-erisimim/webhooklar/999999", ("api",), None, "gecti"),
    # Faz 4W — otomasyon kuralları (`otomasyon` izni) ve özel alanlar (görünürler, salt okunur).
    ("GET", "/api/v1/otomasyonlarim/meta", ("otomasyon",), None, 200),
    ("GET", "/api/v1/otomasyonlarim/ornek-baglam?tetik=destek.olusturuldu", ("otomasyon",), None, 200),
    ("GET", "/api/v1/otomasyonlarim/kurallar", ("otomasyon",), None, 200),
    ("POST", "/api/v1/otomasyonlarim/kurallar", ("otomasyon",),
     {"ad": "Ekip", "tetik": "destek.olusturuldu", "eylemler": [{"tur": "bildirim", "alici": "hesap", "baslik": "x"}]}, 200),
    ("POST", "/api/v1/otomasyonlarim/kurallar/sablondan", ("otomasyon",), {"sablon": "destek_acil_bildirim"}, 200),
    ("GET", "/api/v1/otomasyonlarim/kurallar/{OK}", ("otomasyon",), None, 200),
    ("PUT", "/api/v1/otomasyonlarim/kurallar/{OK}", ("otomasyon",), {"aciklama": "Ekip"}, 200),
    ("POST", "/api/v1/otomasyonlarim/kurallar/{OK}/test", ("otomasyon",), {}, 200),
    ("POST", "/api/v1/otomasyonlarim/test", ("otomasyon",),
     {"kural": {"tetik": "destek.olusturuldu", "eylemler": [{"tur": "bildirim", "alici": "hesap", "baslik": "x"}]}}, 200),
    ("GET", "/api/v1/otomasyonlarim/gunluk", ("otomasyon",), None, 200),
    ("GET", "/api/v1/otomasyonlarim/gunluk/999999", ("otomasyon",), None, "gecti"),
    ("DELETE", "/api/v1/otomasyonlarim/kurallar/999999", ("otomasyon",), None, "gecti"),
    ("GET", "/api/v1/ozel-alanlarim/proje/{P}", ("projeler",), None, 200),
    ("GET", "/api/v1/ozel-alanlarim/destek/{T}", ("destek",), None, 200),
    # Faz 5A — AI asistan ve bilgi bankası (`asistan` izni). Sahibin zaten bir asistanı var: yeni asistan 409 → "gecti".
    ("GET", "/api/v1/ai-asistanim/meta", ("asistan",), None, 200),
    ("GET", "/api/v1/ai-asistanim", ("asistan",), None, 200),
    ("POST", "/api/v1/ai-asistanim", ("asistan",), {"ad": "Ekip asistanı"}, "gecti"),
    ("GET", "/api/v1/ai-asistanim/{AIA}", ("asistan",), None, 200),
    ("PUT", "/api/v1/ai-asistanim/{AIA}", ("asistan",), {"karsilama": "Ekipten merhaba"}, 200),
    ("DELETE", "/api/v1/ai-asistanim/999999", ("asistan",), None, "gecti"),
    ("POST", "/api/v1/ai-asistanim/{AIA}/anahtar", ("asistan",), None, 200),
    ("POST", "/api/v1/ai-asistanim/{AIA}/avatar", ("asistan",), GOVDE_DOSYA, "gecti"),
    ("DELETE", "/api/v1/ai-asistanim/{AIA}/avatar", ("asistan",), None, 200),
    ("GET", "/api/v1/ai-asistanim/{AIA}/ice-aktarim", ("asistan",), None, 200),
    ("GET", "/api/v1/ai-asistanim/{AIA}/kaynaklar", ("asistan",), None, 200),
    ("POST", "/api/v1/ai-asistanim/{AIA}/kaynaklar", ("asistan",), {"tur": "metin", "baslik": "Ekip", "metin": "Ekip notu."}, 200),
    ("POST", "/api/v1/ai-asistanim/{AIA}/kaynaklar/belge", ("asistan",), GOVDE_DOSYA, 200),
    ("GET", "/api/v1/ai-asistanim/{AIA}/kaynaklar/{AIK}", ("asistan",), None, 200),
    ("PUT", "/api/v1/ai-asistanim/{AIA}/kaynaklar/{AIK}", ("asistan",), {"baslik": "Ekipten"}, 200),
    ("POST", "/api/v1/ai-asistanim/{AIA}/kaynaklar/{AIK}/isle", ("asistan",), None, 200),
    ("DELETE", "/api/v1/ai-asistanim/{AIA}/kaynaklar/999999", ("asistan",), None, "gecti"),
    ("GET", "/api/v1/ai-asistanim/{AIA}/sohbetler", ("asistan",), None, 200),
    ("GET", "/api/v1/ai-asistanim/{AIA}/sohbetler/{AIS}", ("asistan",), None, 200),
    ("POST", "/api/v1/ai-asistanim/{AIA}/sohbetler/{AIS}/anonimlestir", ("asistan",), None, 200),
    ("DELETE", "/api/v1/ai-asistanim/{AIA}/sohbetler/999999", ("asistan",), None, "gecti"),
    ("GET", "/api/v1/ai-asistanim/{AIA}/kullanim", ("asistan",), None, 200),
    # Faz 5I — İçerik stüdyosu (`icerik` izni; üyenin varsayılanında). AI kapalı → 503 → "gecti".
    ("GET", "/api/v1/icerik-studyom/meta", ("icerik",), None, 200),
    ("GET", "/api/v1/icerik-studyom/kullanim", ("icerik",), None, 200),
    ("GET", "/api/v1/icerik-studyom/markalar", ("icerik",), None, 200),
    ("POST", "/api/v1/icerik-studyom/markalar", ("icerik",), {"ad": "Ekip markası"}, "gecti"),
    ("GET", "/api/v1/icerik-studyom/markalar/{IM}", ("icerik",), None, 200),
    ("PUT", "/api/v1/icerik-studyom/markalar/{IM}", ("icerik",), {"sektor": "Kafe"}, 200),
    ("DELETE", "/api/v1/icerik-studyom/markalar/999999", ("icerik",), None, "gecti"),
    ("POST", "/api/v1/icerik-studyom/markalar/{IM}/ses-cikar", ("icerik",), {}, "gecti"),
    ("GET", "/api/v1/icerik-studyom/sablonlar", ("icerik",), None, 200),
    ("POST", "/api/v1/icerik-studyom/sablonlar", ("icerik",), {"ad": "Ekip şablonu", "alanlar": [], "istem": "Yaz"}, 200),
    ("PUT", "/api/v1/icerik-studyom/sablonlar/{IS}", ("icerik",), {"ad": "Yeni ad"}, 200),
    ("DELETE", "/api/v1/icerik-studyom/sablonlar/999999", ("icerik",), None, "gecti"),
    ("POST", "/api/v1/icerik-studyom/uret", ("icerik",), {"sablon": "instagram_gonderi", "girdi": {"konu": "x"}}, "gecti"),
    ("POST", "/api/v1/icerik-studyom/ince-ayar", ("icerik",), {"islem": "emoji_cikar", "metin": "Selam"}, 200),
    ("GET", "/api/v1/icerik-studyom/uretimler", ("icerik",), None, 200),
    ("GET", "/api/v1/icerik-studyom/uretimler/999999", ("icerik",), None, "gecti"),
    ("GET", "/api/v1/icerik-studyom/gonderiler", ("icerik",), None, 200),
    ("POST", "/api/v1/icerik-studyom/gonderiler", ("icerik",), {"baslik": "Ekip gönderisi"}, "gecti"),
    ("GET", "/api/v1/icerik-studyom/gonderiler/{IG}", ("icerik",), None, 200),
    ("PUT", "/api/v1/icerik-studyom/gonderiler/{IG}", ("icerik",), {"notlar": "Ekipten"}, 200),
    ("DELETE", "/api/v1/icerik-studyom/gonderiler/999999", ("icerik",), None, "gecti"),
    ("POST", "/api/v1/icerik-studyom/gonderiler/{IG}/durum", ("icerik",), {"durum": "incelemede"}, "gecti"),
    ("POST", "/api/v1/icerik-studyom/gonderiler/{IG}/kisa-link", ("icerik",), None, "gecti"),
    ("GET", "/api/v1/icerik-studyom/gonderiler/{IG}/paket", ("icerik",), None, 200),
    ("GET", "/api/v1/icerik-studyom/gonderiler/{IG}/gorseller.zip", ("icerik",), None, "gecti"),
    ("GET", "/api/v1/icerik-studyom/disa-aktar.csv", ("icerik",), None, 200),
    ("GET", "/api/v1/icerik-studyom/gorseller", ("icerik",), None, 200),
    ("POST", "/api/v1/icerik-studyom/gorseller", ("icerik",), GOVDE_DOSYA, "gecti"),
    # Onay bekleyen içerikler (modülden bağımsız; yalnız `icerik` izni).
    ("GET", "/api/v1/icerik-onaylarim", ("icerik",), None, 200),
    ("POST", "/api/v1/icerik-onaylarim/999999", ("icerik",), {"sonuc": "onay"}, "gecti"),
    # Faz 5M — e-posta pazarlama (`pazarlama` izni). Gönderim/test Resend kurulu değil → 409 → "gecti".
    ("GET", "/api/v1/eposta-pazarlamam/meta", ("pazarlama",), None, 200),
    ("GET", "/api/v1/eposta-pazarlamam/ozet", ("pazarlama",), None, 200),
    ("GET", "/api/v1/eposta-pazarlamam/ayarlar", ("pazarlama",), None, 200),
    ("PUT", "/api/v1/eposta-pazarlamam/ayarlar", ("pazarlama",), {"gonderen_adi": "Ekip"}, 200),
    ("GET", "/api/v1/eposta-pazarlamam/kisiler", ("pazarlama",), None, 200),
    ("POST", "/api/v1/eposta-pazarlamam/kisiler", ("pazarlama",), {"eposta": "yeni-abone@ornek.com"}, "gecti"),
    ("GET", "/api/v1/eposta-pazarlamam/kisiler/{EK}", ("pazarlama",), None, 200),
    ("PUT", "/api/v1/eposta-pazarlamam/kisiler/{EK}", ("pazarlama",), {"ad": "Abone"}, 200),
    ("POST", "/api/v1/eposta-pazarlamam/kisiler/999999/ret", ("pazarlama",), None, "gecti"),
    ("DELETE", "/api/v1/eposta-pazarlamam/kisiler/999999", ("pazarlama",), None, "gecti"),
    ("POST", "/api/v1/eposta-pazarlamam/kisiler/ice-aktar/onizleme", ("pazarlama",), GOVDE_DOSYA, "gecti"),
    ("POST", "/api/v1/eposta-pazarlamam/kisiler/ice-aktar", ("pazarlama",), GOVDE_DOSYA, "gecti"),
    ("GET", "/api/v1/eposta-pazarlamam/bastirma", ("pazarlama",), None, 200),
    ("POST", "/api/v1/eposta-pazarlamam/bastirma", ("pazarlama",), {"eposta": "istemiyor@ornek.com"}, 200),
    ("DELETE", "/api/v1/eposta-pazarlamam/bastirma/999999", ("pazarlama",), None, "gecti"),
    ("GET", "/api/v1/eposta-pazarlamam/listeler", ("pazarlama",), None, 200),
    ("POST", "/api/v1/eposta-pazarlamam/listeler", ("pazarlama",), {"ad": "Ekip listesi"}, 200),
    ("PUT", "/api/v1/eposta-pazarlamam/listeler/{EL}", ("pazarlama",), {"aciklama": "Ekipten"}, 200),
    ("DELETE", "/api/v1/eposta-pazarlamam/listeler/999999", ("pazarlama",), None, "gecti"),
    ("POST", "/api/v1/eposta-pazarlamam/listeler/{EL}/uyeler", ("pazarlama",), {"kisi_idleri": []}, 200),
    ("DELETE", "/api/v1/eposta-pazarlamam/listeler/{EL}/uyeler/999999", ("pazarlama",), None, "gecti"),
    ("GET", "/api/v1/eposta-pazarlamam/formlar", ("pazarlama",), None, 200),
    ("POST", "/api/v1/eposta-pazarlamam/formlar", ("pazarlama",), {"ad": "Ekip formu", "liste_id": 999999}, "gecti"),
    ("PUT", "/api/v1/eposta-pazarlamam/formlar/{EF}", ("pazarlama",), {"baslik": "Bültene katılın"}, 200),
    ("DELETE", "/api/v1/eposta-pazarlamam/formlar/999999", ("pazarlama",), None, "gecti"),
    ("GET", "/api/v1/eposta-pazarlamam/segmentler", ("pazarlama",), None, 200),
    ("POST", "/api/v1/eposta-pazarlamam/segmentler", ("pazarlama",),
     {"ad": "Ekip segmenti", "kurallar": {"kurallar": [{"alan": "alici_turu", "op": "esit", "deger": "kurumsal"}]}}, 200),
    ("POST", "/api/v1/eposta-pazarlamam/segmentler/onizleme", ("pazarlama",),
     {"kurallar": {"kurallar": [{"alan": "kaynak", "op": "esit", "deger": "manuel"}]}}, 200),
    ("PUT", "/api/v1/eposta-pazarlamam/segmentler/{ES}", ("pazarlama",), {"ad": "Yeni ad"}, 200),
    ("DELETE", "/api/v1/eposta-pazarlamam/segmentler/999999", ("pazarlama",), None, "gecti"),
    ("POST", "/api/v1/eposta-pazarlamam/gorseller", ("pazarlama",), GOVDE_DOSYA, "gecti"),
    ("POST", "/api/v1/eposta-pazarlamam/onizleme", ("pazarlama",), {"bloklar": [{"tur": "metin", "metin": "Merhaba"}]}, 200),
    ("GET", "/api/v1/eposta-pazarlamam/kampanyalar", ("pazarlama",), None, 200),
    ("POST", "/api/v1/eposta-pazarlamam/kampanyalar", ("pazarlama",), {"ad": "Ekip kampanyası"}, 200),
    ("GET", "/api/v1/eposta-pazarlamam/kampanyalar/{EKP}", ("pazarlama",), None, 200),
    ("PUT", "/api/v1/eposta-pazarlamam/kampanyalar/{EKP}", ("pazarlama",), {"onizleme_metni": "Ekipten"}, 200),
    ("DELETE", "/api/v1/eposta-pazarlamam/kampanyalar/999999", ("pazarlama",), None, "gecti"),
    ("POST", "/api/v1/eposta-pazarlamam/kampanyalar/{EKP}/kopyala", ("pazarlama",), None, 200),
    ("POST", "/api/v1/eposta-pazarlamam/kampanyalar/{EKP}/onizleme", ("pazarlama",), None, 200),
    ("POST", "/api/v1/eposta-pazarlamam/kampanyalar/{EKP}/kitle", ("pazarlama",), {}, 200),
    ("POST", "/api/v1/eposta-pazarlamam/kampanyalar/{EKP}/test", ("pazarlama",), {"adresler": ["test@ornek.com"]}, "gecti"),
    ("POST", "/api/v1/eposta-pazarlamam/kampanyalar/{EKP}/gonder", ("pazarlama",), {}, "gecti"),
    ("POST", "/api/v1/eposta-pazarlamam/kampanyalar/{EKP}/durdur", ("pazarlama",), None, "gecti"),
    ("POST", "/api/v1/eposta-pazarlamam/kampanyalar/{EKP}/devam", ("pazarlama",), None, "gecti"),
    ("GET", "/api/v1/eposta-pazarlamam/kampanyalar/{EKP}/rapor", ("pazarlama",), None, 200),
    ("GET", "/api/v1/eposta-pazarlamam/diziler", ("pazarlama",), None, 200),
    ("POST", "/api/v1/eposta-pazarlamam/diziler", ("pazarlama",), {"ad": "Ekip dizisi", "liste_id": "{EL}"}, "gecti"),
    ("GET", "/api/v1/eposta-pazarlamam/diziler/{ED}", ("pazarlama",), None, 200),
    ("PUT", "/api/v1/eposta-pazarlamam/diziler/{ED}", ("pazarlama",), {"ad": "Yeni dizi adı"}, 200),
    ("DELETE", "/api/v1/eposta-pazarlamam/diziler/999999", ("pazarlama",), None, "gecti"),
    ("GET", "/api/v1/eposta-pazarlamam/diziler/{ED}/rapor", ("pazarlama",), None, 200),
    # Faz 6S — saha servisi (`saha_yonetim` sevk/yönetim; `saha_teknisyen` yalnız kendine atanan işler).
    ("GET", "/api/v1/saha-servisim/meta", SAHA, None, 200),
    ("GET", "/api/v1/saha-servisim/ayarlar", ("saha_yonetim",), None, 200),
    ("PUT", "/api/v1/saha-servisim/ayarlar", ("saha_yonetim",), {"firma_adi": "Ekip Servis"}, 200),
    ("GET", "/api/v1/saha-servisim/teknisyenler", ("saha_yonetim",), None, 200),
    ("POST", "/api/v1/saha-servisim/teknisyenler", ("saha_yonetim",), {"eposta": "aday-degil@ornek.com"}, "gecti"),
    ("PUT", "/api/v1/saha-servisim/teknisyenler/{ST}", ("saha_yonetim",), {"ad": "Sahacı Usta"}, 200),
    ("DELETE", "/api/v1/saha-servisim/teknisyenler/999999", ("saha_yonetim",), None, "gecti"),
    ("GET", "/api/v1/saha-servisim/rizam", SAHA, None, 200),
    ("POST", "/api/v1/saha-servisim/rizam", SAHA, {"surum": "eski", "onay": True}, "gecti"),
    ("DELETE", "/api/v1/saha-servisim/rizam", SAHA, None, "gecti"),
    ("GET", "/api/v1/saha-servisim/musteriler", ("saha_yonetim",), None, 200),
    ("POST", "/api/v1/saha-servisim/musteriler", ("saha_yonetim",), {"ad": "Ekip müşterisi"}, 200),
    ("GET", "/api/v1/saha-servisim/musteriler/{SM}", ("saha_yonetim",), None, 200),
    ("PUT", "/api/v1/saha-servisim/musteriler/{SM}", ("saha_yonetim",), {"notlar": "Ekipten"}, 200),
    ("DELETE", "/api/v1/saha-servisim/musteriler/999999", ("saha_yonetim",), None, "gecti"),
    ("POST", "/api/v1/saha-servisim/musteriler/{SM}/lokasyonlar", ("saha_yonetim",), {"ad": "Depo", "adres": "Sanayi"}, 200),
    ("PUT", "/api/v1/saha-servisim/lokasyonlar/{SL}", ("saha_yonetim",), {"notlar": "Kapı kodu 12"}, 200),
    ("DELETE", "/api/v1/saha-servisim/lokasyonlar/999999", ("saha_yonetim",), None, "gecti"),
    ("POST", "/api/v1/saha-servisim/musteriler/{SM}/cihazlar", ("saha_yonetim",), {"tur": "Kombi"}, 200),
    ("PUT", "/api/v1/saha-servisim/cihazlar/{SC}", ("saha_yonetim",), {"notlar": "Ekipten"}, 200),
    ("DELETE", "/api/v1/saha-servisim/cihazlar/999999", ("saha_yonetim",), None, "gecti"),
    ("GET", "/api/v1/saha-servisim/cihazlar/{SC}/gecmis", ("saha_yonetim",), None, 200),
    ("POST", "/api/v1/saha-servisim/cihazlar/{SC}/bakim-is-emri", ("saha_yonetim",), {}, "gecti"),
    ("GET", "/api/v1/saha-servisim/sablonlar", ("saha_yonetim",), None, 200),
    ("POST", "/api/v1/saha-servisim/sablonlar", ("saha_yonetim",), {"ad": "Ekip listesi", "maddeler": []}, 200),
    ("PUT", "/api/v1/saha-servisim/sablonlar/{SS}", ("saha_yonetim",), {"ad": "Ekip şablonu 2"}, 200),
    ("DELETE", "/api/v1/saha-servisim/sablonlar/999999", ("saha_yonetim",), None, "gecti"),
    ("GET", "/api/v1/saha-servisim/malzemeler", SAHA, None, 200),
    ("POST", "/api/v1/saha-servisim/malzemeler", ("saha_yonetim",), {"ad": "Vida"}, 200),
    ("PUT", "/api/v1/saha-servisim/malzemeler/{SMZ}", ("saha_yonetim",), {"stok": 50}, 200),
    ("DELETE", "/api/v1/saha-servisim/malzemeler/999999", ("saha_yonetim",), None, "gecti"),
    ("GET", "/api/v1/saha-servisim/is-emirleri", ("saha_yonetim",), None, 200),
    ("POST", "/api/v1/saha-servisim/is-emirleri", ("saha_yonetim",), {"musteri_id": 999999, "baslik": "Ekip işi"}, "gecti"),
    ("GET", "/api/v1/saha-servisim/is-emirleri/{SI}", SAHA, None, 200),
    ("PUT", "/api/v1/saha-servisim/is-emirleri/{SI}", ("saha_yonetim",), {"aciklama": "Ekipten"}, 200),
    ("PUT", "/api/v1/saha-servisim/is-emirleri/{SI}/plan", ("saha_yonetim",), {"plan_bas": "2030-01-08T09:00:00Z"}, 200),
    ("DELETE", "/api/v1/saha-servisim/is-emirleri/999999", ("saha_yonetim",), None, "gecti"),
    ("POST", "/api/v1/saha-servisim/is-emirleri/{SI}/durum", SAHA, {"durum": "uydurma"}, "gecti"),
    ("PUT", "/api/v1/saha-servisim/is-emirleri/{SI}/kontrol", SAHA, {"yanitlar": {}}, 200),
    ("PUT", "/api/v1/saha-servisim/is-emirleri/{SI}/saha", SAHA, {"teknisyen_notu": "Ekipten"}, 200),
    ("POST", "/api/v1/saha-servisim/is-emirleri/{SI}/fotograflar", SAHA, GOVDE_DOSYA, "gecti"),
    ("DELETE", "/api/v1/saha-servisim/is-emirleri/{SI}/fotograflar/999999", SAHA, None, "gecti"),
    ("POST", "/api/v1/saha-servisim/is-emirleri/{SI}/malzemeler", SAHA, {"ad": "Kablo", "miktar": 1}, 200),
    ("DELETE", "/api/v1/saha-servisim/is-emirleri/{SI}/malzemeler/999999", SAHA, None, "gecti"),
    ("POST", "/api/v1/saha-servisim/is-emirleri/{SI}/imza", SAHA, {"ad": "Ekip", "png": ""}, "gecti"),
    ("GET", "/api/v1/saha-servisim/is-emirleri/{SI}/pdf", SAHA, None, 200),
    ("POST", "/api/v1/saha-servisim/is-emirleri/{SI}/musteri-baglantisi", ("saha_yonetim",), None, 200),
    ("GET", "/api/v1/saha-servisim/pano", ("saha_yonetim",), None, 200),
    ("GET", "/api/v1/saha-servisim/islerim", SAHA, None, 200),
    ("GET", "/api/v1/saha-servisim/raporlar", ("saha_yonetim",), None, 200),
    ("GET", "/api/v1/saha-servisim/bakim", ("saha_yonetim",), None, 200),
    # Faz 6E — etkinlik ve bilet (`etkinlik` yönetim; okutma/sayaç/giriş listesi `etkinlik_giris` da yeter).
    ("GET", "/api/v1/etkinliklerim/meta", ("etkinlik",), None, 200),
    ("GET", "/api/v1/etkinliklerim/giris-listesi", ("etkinlik", "etkinlik_giris"), None, 200),
    ("GET", "/api/v1/etkinliklerim/liste-ayari", ("etkinlik",), None, 200),
    ("PUT", "/api/v1/etkinliklerim/liste-ayari", ("etkinlik",), {"baslik": "Ekip etkinlikleri"}, "gecti"),
    ("GET", "/api/v1/etkinliklerim", ("etkinlik",), None, 200),
    ("POST", "/api/v1/etkinliklerim", ("etkinlik",),
     {"baslik": "Ekip etkinliği", "baslangic": "2030-01-08T09:00:00Z", "bitis": "2030-01-08T12:00:00Z"}, 200),
    ("GET", "/api/v1/etkinliklerim/{ET}", ("etkinlik",), None, 200),
    ("PUT", "/api/v1/etkinliklerim/{ET}", ("etkinlik",), {"ozet": "Ekipten"}, 200),
    ("DELETE", "/api/v1/etkinliklerim/999999", ("etkinlik",), None, "gecti"),
    ("POST", "/api/v1/etkinliklerim/{ET}/kapak", ("etkinlik",), GOVDE_DOSYA, "gecti"),
    ("DELETE", "/api/v1/etkinliklerim/{ET}/kapak", ("etkinlik",), None, 200),
    ("GET", "/api/v1/etkinliklerim/{ET}/qr?bicim=svg", ("etkinlik",), None, 200),
    ("GET", "/api/v1/etkinliklerim/{ET}/bilet-turleri", ("etkinlik",), None, 200),
    ("POST", "/api/v1/etkinliklerim/{ET}/bilet-turleri", ("etkinlik",), {"ad": "Ekip türü"}, 200),
    ("PUT", "/api/v1/etkinliklerim/{ET}/bilet-turleri/{ETT}", ("etkinlik",), {"aciklama": "Ekipten"}, 200),
    ("DELETE", "/api/v1/etkinliklerim/{ET}/bilet-turleri/999999", ("etkinlik",), None, "gecti"),
    ("GET", "/api/v1/etkinliklerim/{ET}/indirimler", ("etkinlik",), None, 200),
    ("POST", "/api/v1/etkinliklerim/{ET}/indirimler", ("etkinlik",), {"kod": "EKIP", "tur": "yuzde", "deger": 10}, "gecti"),
    ("PUT", "/api/v1/etkinliklerim/{ET}/indirimler/{ETI}", ("etkinlik",), {"deger": 15}, 200),
    ("DELETE", "/api/v1/etkinliklerim/{ET}/indirimler/999999", ("etkinlik",), None, "gecti"),
    ("GET", "/api/v1/etkinliklerim/{ET}/katilimcilar", ("etkinlik",), None, 200),
    ("GET", "/api/v1/etkinliklerim/{ET}/katilimcilar.csv", ("etkinlik",), None, 200),
    ("POST", "/api/v1/etkinliklerim/{ET}/katilimcilar", ("etkinlik",),
     {"ad": "Kapıda", "eposta": "kapi@ornek.com", "tur_id": 999999, "bildir": False}, "gecti"),
    ("POST", "/api/v1/etkinliklerim/{ET}/siparisler/999999/iptal", ("etkinlik",), {}, "gecti"),
    ("POST", "/api/v1/etkinliklerim/{ET}/siparisler/999999/odendi", ("etkinlik",), None, "gecti"),
    ("POST", "/api/v1/etkinliklerim/{ET}/biletler/999999/iptal", ("etkinlik",), {}, "gecti"),
    ("POST", "/api/v1/etkinliklerim/{ET}/biletler/{ETB}/iade", ("etkinlik",), {"durum": "yok"}, 200),
    ("POST", "/api/v1/etkinliklerim/{ET}/biletler/{ETB}/giris", ("etkinlik", "etkinlik_giris"), None, 200),
    ("DELETE", "/api/v1/etkinliklerim/{ET}/biletler/{ETB}/giris", ("etkinlik",), None, 200),
    ("GET", "/api/v1/etkinliklerim/{ET}/bekleme", ("etkinlik",), None, 200),
    ("POST", "/api/v1/etkinliklerim/{ET}/bekleme/999999/davet", ("etkinlik",), None, "gecti"),
    ("DELETE", "/api/v1/etkinliklerim/{ET}/bekleme/999999", ("etkinlik",), None, "gecti"),
    ("GET", "/api/v1/etkinliklerim/{ET}/istatistik", ("etkinlik",), None, 200),
    ("GET", "/api/v1/etkinliklerim/{ET}/satis", ("etkinlik",), None, 200),
    ("GET", "/api/v1/etkinliklerim/{ET}/sayac", ("etkinlik", "etkinlik_giris"), None, 200),
    ("POST", "/api/v1/etkinliklerim/{ET}/okut", ("etkinlik", "etkinlik_giris"), {"kod": "ZZZZZZZZZZ"}, 200),
    ("POST", "/api/v1/etkinliklerim/{ET}/duyuru", ("etkinlik",), {"konu": "Bilgi", "metin": "Ekip duyurusu"}, "gecti"),
    ("POST", "/api/v1/etkinliklerim/{ET}/tesekkur", ("etkinlik",), None, "gecti"),
    ("GET", "/api/v1/etkinliklerim/{ET}/gorevli", ("etkinlik",), None, 200),
    ("POST", "/api/v1/etkinliklerim/{ET}/gorevli", ("etkinlik",), {}, 200),
    ("GET", "/api/v1/etkinliklerim/{ET}/pazarlama", ("etkinlik",), None, 200),
    ("POST", "/api/v1/etkinliklerim/{ET}/pazarlama", ("etkinlik",), {"liste_id": 999999}, "gecti"),
]


def _kod(yanit) -> str:
    try:
        d = yanit.json().get("detail")
    except Exception:  # noqa: BLE001
        return ""
    return d.get("kod", "") if isinstance(d, dict) else ""


async def _cagir(istemci, metot, yol, govde, basliklar):
    if govde == GOVDE_DOSYA:
        dosya = {"dosya" if "geri-bildirim" not in yol else "ekran": ("not.txt", io.BytesIO(b"merhaba"), "text/plain")}
        return await istemci.request(metot, yol, files=dosya, headers=basliklar)
    if isinstance(govde, dict) and "__form__" in govde:
        return await istemci.request(metot, yol, data=govde["__form__"], headers=basliklar)
    if govde is None:
        return await istemci.request(metot, yol, headers=basliklar)
    return await istemci.request(metot, yol, json=govde, headers=basliklar)


def _gecti_mi(yanit) -> bool:
    if yanit.status_code == 401:
        return False
    return not (yanit.status_code == 403 and _kod(yanit) in ("hesap_izni_yok", "hesap_uyesi_degil"))


def _beklenen(yanit, beklenen) -> bool:
    return _gecti_mi(yanit) if beklenen == "gecti" else yanit.status_code == beklenen


def _izinli_uye(k, izinler):
    from services.hesap_ekibi import ROL_VARSAYILAN

    if izinler is None:
        return k["kisitli"]
    if izinler == ("api",):  # Faz 4A: üye/fatura rolünün varsayılanında yok
        return k["apici"]
    if izinler == ("otomasyon",):  # Faz 4W: üye/fatura rolünün varsayılanında yok (apici'ye ayrıca verildi)
        return k["apici"]
    if izinler == ("pazarlama",):  # Faz 5M: üye/fatura rolünün varsayılanında yok
        return k["pazarlamaci"]
    if set(izinler) <= set(SAHA):  # Faz 6S: üye/fatura rolünün varsayılanında yok
        return k["sahaci"]
    if izinler == ("etkinlik",):  # Faz 6E: yönetim izni üyenin varsayılanında yok (pazarlamaci'ye ayrıca verildi)
        return k["pazarlamaci"]
    for rol, kisi in (("uye", k["uye"]), ("fatura", k["fatura"])):
        if any(i in ROL_VARSAYILAN[rol] for i in izinler):
            return kisi
    raise AssertionError(izinler)


@pytest.mark.parametrize("metot,yol,izinler,govde,beklenen", MUSTERI_UCLARI, ids=[f"{m} {y}" for m, y, *_ in MUSTERI_UCLARI])
async def test_musteri_ucu_izin_matrisi(istemci, ekip, metot, yol, izinler, govde, beklenen):
    k = ekip
    yol = yol.format(**k)
    s = k["sahip"]

    # 1) Sahip, başlıksız (eski davranış) — ve kendi e-postasını başlıkta verse de aynı.
    y = await _cagir(istemci, metot, yol, govde, _b(s))
    assert _beklenen(y, beklenen), (yol, y.status_code, y.text[:300])
    y = await _cagir(istemci, metot, yol, govde, _b(s, s))
    assert _gecti_mi(y), (yol, y.status_code, y.text[:300])

    # 2) İzinli üye, sahibin hesabında.
    y = await _cagir(istemci, metot, yol, govde, _b(_izinli_uye(k, izinler), s))
    assert _gecti_mi(y), ("izinli üye", yol, y.status_code, y.text[:300])

    # 3) İzinsiz üye (hiç izni yok) → 403 hesap_izni_yok.
    if izinler is not None:
        y = await _cagir(istemci, metot, yol, govde, _b(k["kisitli"], s))
        assert y.status_code == 403 and _kod(y) == "hesap_izni_yok", ("izinsiz üye", yol, y.status_code, y.text[:300])

    # 4) Üye olmayan, başlıkla → 403 hesap_uyesi_degil (kendi hesabına sessizce düşmez).
    y = await _cagir(istemci, metot, yol, govde, _b(k["yabanci"], s))
    assert y.status_code == 403 and _kod(y) == "hesap_uyesi_degil", ("yabancı", yol, y.status_code, y.text[:300])


async def test_uye_sahibin_kayitlarini_gorur_yabanci_kendi_bos_hesabini(istemci, ekip):
    k = ekip
    y = await istemci.get("/api/v1/entities/projects/all", headers=_b(k["uye"], k["sahip"]))
    assert y.status_code == 200
    assert [p["id"] for p in y.json()["items"] if p["id"] == k["P"]] == [k["P"]]
    # Başlıksız aynı kişi: kendi (boş) hesabı.
    y = await istemci.get("/api/v1/entities/projects/all", headers=_b(k["uye"]))
    assert all(p["id"] != k["P"] for p in y.json()["items"])
    # Sorguda başka hesap yazmak işe yaramaz (süzgeç etkin hesabı zorluyor).
    sorgu = json.dumps({"client_email": k["sahip"]})
    y = await istemci.get(f"/api/v1/entities/invoices?query={sorgu}", headers=_b(k["yabanci"]))
    assert y.status_code == 200 and y.json()["items"] == []


async def test_fatura_rolu_proje_ve_destek_goremez(istemci, ekip):
    k = ekip
    b = _b(k["fatura"], k["sahip"])
    for yol in ("/api/v1/entities/projects", f"/api/v1/entities/support_tickets/{k['T']}", "/api/v1/gorevlerim/revizyon",
                f"/api/v1/talep/{k['T']}/mesajlar", "/api/v1/dosyalarim"):
        y = await istemci.get(yol, headers=b)
        assert y.status_code == 403 and _kod(y) == "hesap_izni_yok", (yol, y.text)
    y = await istemci.get("/api/v1/entities/invoices", headers=b)
    assert y.status_code == 200 and [i["id"] for i in y.json()["items"]] == [k["F"]]
    # İşlemler: yalnız teklif görünür; teslim onayı (projeler) kararı 403.
    y = await istemci.get("/api/v1/islemlerim", headers=b)
    assert {i["tur"] for i in y.json()} == {"teklif_kabul"}
    y = await istemci.post(f"/api/v1/islemlerim/{k['I_PROJE']}", json={"sonuc": "onay"}, headers=b)
    assert y.status_code == 403 and _kod(y) == "hesap_izni_yok"


async def test_uye_rolu_faturalari_goremez(istemci, ekip):
    k = ekip
    y = await istemci.get(f"/api/v1/entities/invoices/{k['F']}", headers=_b(k["uye"], k["sahip"]))
    assert y.status_code == 403 and _kod(y) == "hesap_izni_yok"
    y = await istemci.get("/api/v1/islemlerim", headers=_b(k["uye"], k["sahip"]))
    assert {i["tur"] for i in y.json()} == {"teslimat_onay"}


# ---------------------------------------------------------------------------
# Tarama: gözden kaçan müşteri ucu var mı?
# ---------------------------------------------------------------------------
#: Başlıktan bağımsız (kişiye ait ya da herkese açık) olduğu için üye-olmayan
#: kişinin başlıkla 2xx alabileceği uçlar. Buraya eklenen her satır bilinçli bir karar.
KISISEL_YA_DA_ACIK = {
    # Kişiye ait: oturumlar, bildirim tercihleri/çanı, profil, hesap listesi.
    ("GET", "/api/v1/oturumlarim"),
    ("POST", "/api/v1/oturumlarim/digerlerini-kapat"),
    ("GET", "/api/v1/bildirim/tercihlerim"),
    ("PUT", "/api/v1/bildirim/tercihlerim"),
    ("POST", "/api/v1/bildirim/push/dene"),
    # Ajans personeli: kendine atanmış siteler (müşteri hesabıyla ilgisi yok; müşteriye boş liste).
    ("GET", "/api/v1/musteri-sitesi"),
    # Faz 3Z: "personel miyim?" — kişiye ait (hesaptan bağımsız); veri yok, yalnız bayrak.
    ("GET", "/api/v1/zaman/ben"),
    ("GET", "/api/v1/bildirim/push/anahtar"),
    ("DELETE", "/api/v1/bildirim/push/abone"),
    ("GET", "/api/v1/entities/notifications"),
    ("GET", "/api/v1/hesaplarim"),
    ("GET", "/api/v1/auth/me"),
    # Herkese açık katalog / içerik.
    ("GET", "/api/v1/moduller"),
    ("GET", "/api/v1/marketplace"),
    # Faz 3K: sitedeki Kaynaklar listesi ve ayrıntısı (yalnız yayındakiler).
    ("GET", "/api/v1/kaynaklar"),
    ("GET", "/api/v1/kaynaklar/{slug}"),
    ("GET", "/api/v1/fiyat-hesapla"),
    ("GET", "/api/v1/talep/hizmetler"),
    ("GET", "/api/v1/destek/eposta-bilgisi"),
    ("GET", "/api/v1/entities/project_events/stages"),
}
# Faz 2H: `/api/v1/storage/` artık yalnız yönetici — taramadan çıkarılmadı, taranıyor.
TARAMA_ATLA_ONEK = ("/api/v1/auth/",)


def _yolu_doldur(yol: str, k: dict) -> str:
    import re

    yerine = {"hesap_email": k["sahip"], "eposta": k["sahip"]}
    return re.sub(r"\{(\w+)\}", lambda m: yerine.get(m.group(1), "1" if m.group(1).endswith("id") else "x"), yol)


def _rotalar(app):
    def gez(rotalar):
        for r in rotalar:
            if hasattr(r, "original_router"):
                yield from gez(r.original_router.routes)
                continue
            if getattr(r, "methods", None) and getattr(r, "endpoint", None) is not None:
                yield r

    return list(gez(app.routes))


async def test_tarama_uye_olmayan_baslikla_hicbir_hesap_ucundan_veri_alamaz(istemci, ekip, uygulama):
    k = ekip
    b = _b(k["yabanci"], k["sahip"])
    sizanlar = []
    for r in _rotalar(uygulama):
        if not r.path.startswith("/api/") or r.path.startswith(TARAMA_ATLA_ONEK):
            continue
        for metot in sorted(r.methods - {"HEAD", "OPTIONS"}):
            if (metot, r.path) in KISISEL_YA_DA_ACIK:
                continue
            yol = _yolu_doldur(r.path, k)
            if metot in ("GET", "DELETE"):
                y = await istemci.request(metot, yol, headers=b)
            else:
                y = await istemci.request(metot, yol, json={}, headers=b)
            if 200 <= y.status_code < 300:
                sizanlar.append(f"{metot} {r.path} → {y.status_code}")
    # Herkese açık okumalar (vitrin, blog, katalog, imzalı bağlantılar…) zaten
    # oturumsuz da açık; onları ayırmak için aynı isteği oturumsuz deniyoruz.
    gercek = []
    for satir in sizanlar:
        metot, yol = satir.split(" ")[0], satir.split(" ")[1]
        y = await istemci.request(metot, _yolu_doldur(yol, k), **({} if metot in ("GET", "DELETE") else {"json": {}}))
        if not (200 <= y.status_code < 300):
            gercek.append(satir)
    assert gercek == [], "Hesap bağlamına geçirilmemiş uç(lar):\n" + "\n".join(gercek)


# ---------------------------------------------------------------------------
# Davet akışı
# ---------------------------------------------------------------------------
def _jeton(yanit_json) -> str:
    baglanti = yanit_json["baglanti"]
    assert baglanti.startswith("https://mehmetkuru.dev/hesap-davet/")
    return baglanti.rsplit("/", 1)[1]


async def test_davet_olustur_kabul_erisim(istemci, db_oturumu):
    from models.hesap_uyeleri import HesapUyeleri
    from models.invoices import Invoices
    from services.hesap_ekibi import jeton_ozeti

    sahip, kisi = _e("sahip"), _e("yeni")
    await _ekle(db_oturumu, Invoices(invoice_no="D-1", client_email=sahip, amount=5.0))
    y = await istemci.post("/api/v1/hesabim/uyeler", json={"email": kisi.upper(), "rol": "fatura"}, headers=_b(sahip))
    assert y.status_code == 200, y.text
    govde = y.json()
    assert govde["uye"]["durum"] == "davet" and govde["uye"]["uye_email"] == kisi
    assert govde["uye"]["izinler"] == ["faturalar", "krediler", "abonelikler"]
    assert govde["eposta_durumu"] in ("sent", "skipped", "failed", "off")
    jeton = _jeton(govde)

    # Ham jeton veritabanında yok; yalnız özeti.
    satir = (await db_oturumu.execute(select(HesapUyeleri).where(HesapUyeleri.uye_email == kisi))).scalar_one()
    assert satir.davet_jetonu_ozet == jeton_ozeti(jeton) and jeton not in json.dumps(govde["uye"])

    # Davet henüz kabul edilmedi: erişim yok.
    y = await istemci.get("/api/v1/entities/invoices", headers=_b(kisi, sahip))
    assert y.status_code == 403 and _kod(y) == "hesap_uyesi_degil"

    # Girişsiz bilgi: maskeli.
    y = await istemci.get(f"/api/v1/hesap-davet/{jeton}")
    assert y.status_code == 200
    assert y.json()["davet_eposta"].startswith(kisi[0] + "***@") and y.json()["rol"] == "fatura"
    assert sahip not in y.text and kisi not in y.text

    # Girişsiz kabul → 401; başka e-postayla → 403 + açıklama.
    assert (await istemci.post(f"/api/v1/hesap-davet/{jeton}/kabul")).status_code == 401
    y = await istemci.post(f"/api/v1/hesap-davet/{jeton}/kabul", headers=_b(_e("baskasi")))
    assert y.status_code == 403 and _kod(y) == "eposta_uyusmuyor" and "***@" in y.json()["detail"]["beklenen"]

    y = await istemci.post(f"/api/v1/hesap-davet/{jeton}/kabul", headers=_b(kisi))
    assert y.status_code == 200 and y.json()["hesap_email"] == sahip

    # İkinci kullanım: bağlantı artık yok.
    y = await istemci.post(f"/api/v1/hesap-davet/{jeton}/kabul", headers=_b(kisi))
    assert y.status_code == 404
    assert (await istemci.get(f"/api/v1/hesap-davet/{jeton}")).status_code == 404

    # Erişim: faturaları görür, projeleri göremez; hesap listesinde sahip var.
    y = await istemci.get("/api/v1/entities/invoices", headers=_b(kisi, sahip))
    assert y.status_code == 200 and [i["invoice_no"] for i in y.json()["items"]] == ["D-1"]
    y = await istemci.get("/api/v1/entities/projects", headers=_b(kisi, sahip))
    assert y.status_code == 403
    y = await istemci.get("/api/v1/hesaplarim", headers=_b(kisi))
    hesaplar = {h["hesap_email"]: h for h in y.json()["hesaplar"]}
    assert hesaplar[kisi]["kendi"] is True and hesaplar[sahip]["rol"] == "fatura"


async def test_davet_suresi_dolmus_ve_yenileme(istemci, db_oturumu):
    from models.hesap_uyeleri import HesapUyeleri
    from services.hesap_ekibi import simdi

    sahip, kisi = _e("sahip"), _e("gec")
    y = await istemci.post("/api/v1/hesabim/uyeler", json={"email": kisi, "rol": "uye"}, headers=_b(sahip))
    jeton, uye_id = _jeton(y.json()), y.json()["uye"]["id"]
    satir = (await db_oturumu.execute(select(HesapUyeleri).where(HesapUyeleri.id == uye_id))).scalar_one()
    satir.davet_bitis = simdi() - timedelta(minutes=1)
    await db_oturumu.commit()

    assert (await istemci.get(f"/api/v1/hesap-davet/{jeton}")).json()["durum"] == "suresi_doldu"
    y = await istemci.post(f"/api/v1/hesap-davet/{jeton}/kabul", headers=_b(kisi))
    assert y.status_code == 410 and _kod(y) == "davet_suresi_doldu"

    # Yenile: eski bağlantı geçersiz, yenisi çalışır.
    y = await istemci.post(f"/api/v1/hesabim/uyeler/{uye_id}/davet-yenile", headers=_b(sahip))
    assert y.status_code == 200
    yeni = _jeton(y.json())
    assert yeni != jeton
    assert (await istemci.get(f"/api/v1/hesap-davet/{jeton}")).status_code == 404
    assert (await istemci.post(f"/api/v1/hesap-davet/{yeni}/kabul", headers=_b(kisi))).status_code == 200
    # Aktif üyenin daveti yenilenemez.
    y = await istemci.post(f"/api/v1/hesabim/uyeler/{uye_id}/davet-yenile", headers=_b(sahip))
    assert y.status_code == 409 and _kod(y) == "davet_degil"


async def test_davet_kurallari(istemci):
    sahip = _e("sahip")
    b = _b(sahip)
    assert (await istemci.post("/api/v1/hesabim/uyeler", json={"email": sahip, "rol": "uye"}, headers=b)).json()[
        "detail"
    ]["kod"] == "sahip_eklenemez"
    assert (await istemci.post("/api/v1/hesabim/uyeler", json={"email": "bozuk", "rol": "uye"}, headers=b)).status_code == 400
    y = await istemci.post("/api/v1/hesabim/uyeler", json={"email": _e("x"), "rol": "patron"}, headers=b)
    assert _kod(y) == "rol_gecersiz"
    y = await istemci.post("/api/v1/hesabim/uyeler", json={"email": _e("x"), "rol": "uye", "izinler": ["hepsi"]}, headers=b)
    assert _kod(y) == "izin_gecersiz"
    kisi = _e("iki")
    assert (await istemci.post("/api/v1/hesabim/uyeler", json={"email": kisi}, headers=b)).status_code == 200
    y = await istemci.post("/api/v1/hesabim/uyeler", json={"email": kisi}, headers=b)
    assert y.status_code == 409 and _kod(y) == "zaten_uye"
    # Özel izinler: yalnız destek.
    y = await istemci.post(
        "/api/v1/hesabim/uyeler", json={"email": _e("ozel"), "rol": "uye", "izinler": ["destek"]}, headers=b
    )
    assert y.json()["uye"]["izinler"] == ["destek"]


# ---------------------------------------------------------------------------
# Üyelik bitince erişim anında düşer
# ---------------------------------------------------------------------------
async def test_uye_silinince_ve_pasifte_erisim_aninda_duser(istemci, ekip):
    k = ekip
    b = _b(k["uye"], k["sahip"])
    assert (await istemci.get(f"/api/v1/entities/projects/{k['P']}", headers=b)).status_code == 200  # önbellek dolu

    liste = (await istemci.get("/api/v1/hesabim/uyeler", headers=_b(k["sahip"]))).json()["uyeler"]
    uye_id = next(u["id"] for u in liste if u["uye_email"] == k["uye"])

    y = await istemci.put(f"/api/v1/hesabim/uyeler/{uye_id}", json={"durum": "pasif"}, headers=_b(k["sahip"]))
    assert y.status_code == 200 and y.json()["durum"] == "pasif"
    y = await istemci.get(f"/api/v1/entities/projects/{k['P']}", headers=b)
    assert y.status_code == 403 and _kod(y) == "hesap_uyesi_degil"
    assert k["sahip"] not in {h["hesap_email"] for h in (await istemci.get("/api/v1/hesaplarim", headers=_b(k["uye"]))).json()["hesaplar"]}

    await istemci.put(f"/api/v1/hesabim/uyeler/{uye_id}", json={"durum": "aktif"}, headers=_b(k["sahip"]))
    assert (await istemci.get(f"/api/v1/entities/projects/{k['P']}", headers=b)).status_code == 200

    y = await istemci.delete(f"/api/v1/hesabim/uyeler/{uye_id}", headers=_b(k["sahip"]))
    assert y.status_code == 200
    y = await istemci.get(f"/api/v1/entities/projects/{k['P']}", headers=b)
    assert y.status_code == 403 and _kod(y) == "hesap_uyesi_degil"


async def test_rol_degisince_izinler_aninda_gecerli(istemci, ekip):
    k = ekip
    liste = (await istemci.get("/api/v1/hesabim/uyeler", headers=_b(k["sahip"]))).json()["uyeler"]
    uye_id = next(u["id"] for u in liste if u["uye_email"] == k["uye"])
    b = _b(k["uye"], k["sahip"])
    assert (await istemci.get("/api/v1/entities/invoices", headers=b)).status_code == 403
    y = await istemci.put(f"/api/v1/hesabim/uyeler/{uye_id}", json={"rol": "fatura"}, headers=_b(k["sahip"]))
    assert y.json()["izinler"] == ["faturalar", "krediler", "abonelikler"]
    assert (await istemci.get("/api/v1/entities/invoices", headers=b)).status_code == 200
    assert (await istemci.get("/api/v1/entities/projects", headers=b)).status_code == 403


# ---------------------------------------------------------------------------
# Ekip yönetimi yetkileri
# ---------------------------------------------------------------------------
async def test_hesap_yoneticisi_yetki_yukseltemez(istemci, db_oturumu):
    sahip, yon, diger = _e("sahip"), _e("yon"), _e("diger")
    # Yönetici, faturaları hariç her şeye yetkili.
    await _uye_ekle(db_oturumu, sahip, yon, "yonetici",
                    izinler=["projeler", "gorevler", "destek", "dosyalar", "siteler", "raporlar"])
    genis = await _uye_ekle(db_oturumu, sahip, diger, "fatura")
    b = _b(yon, sahip)

    # Kendinde olmayan izni veremez.
    y = await istemci.post("/api/v1/hesabim/uyeler", json={"email": _e("a"), "rol": "fatura"}, headers=b)
    assert y.status_code == 403 and _kod(y) == "yetki_yukseltilemez"
    y = await istemci.post("/api/v1/hesabim/uyeler", json={"email": _e("a"), "rol": "yonetici"}, headers=b)
    assert y.status_code == 403 and _kod(y) == "yetki_yukseltilemez"
    # Alt kümeyle ekleyebilir.
    y = await istemci.post("/api/v1/hesabim/uyeler", json={"email": _e("a"), "rol": "uye", "izinler": ["destek"]}, headers=b)
    assert y.status_code == 200, y.text
    yeni_id = y.json()["uye"]["id"]
    y = await istemci.put(f"/api/v1/hesabim/uyeler/{yeni_id}", json={"izinler": ["destek", "faturalar"]}, headers=b)
    assert y.status_code == 403 and _kod(y) == "yetki_yukseltilemez"
    # Kendinden geniş izinli üyeye dokunamaz; kendini düzenleyemez.
    y = await istemci.delete(f"/api/v1/hesabim/uyeler/{genis.id}", headers=b)
    assert y.status_code == 403 and _kod(y) == "yetki_yukseltilemez"
    liste = (await istemci.get("/api/v1/hesabim/uyeler", headers=b)).json()
    assert liste["yonetebilir"] is True and liste["rolum"] == "yonetici"
    kendi_id = next(u["id"] for u in liste["uyeler"] if u["uye_email"] == yon)
    y = await istemci.put(f"/api/v1/hesabim/uyeler/{kendi_id}", json={"rol": "yonetici", "izinler": ["faturalar"]}, headers=b)
    assert y.status_code == 403 and _kod(y) in ("kendini_duzenleyemez", "yetki_yukseltilemez")
    # Sahip her şeyi yapabilir.
    assert (await istemci.delete(f"/api/v1/hesabim/uyeler/{genis.id}", headers=_b(sahip))).status_code == 200


async def test_uye_ve_fatura_rolu_ekibi_yonetemez(istemci, ekip):
    k = ekip
    for kisi in (k["uye"], k["fatura"]):
        b = _b(kisi, k["sahip"])
        y = await istemci.get("/api/v1/hesabim/uyeler", headers=b)
        assert y.status_code == 200 and y.json()["yonetebilir"] is False  # salt okunur
        y = await istemci.post("/api/v1/hesabim/uyeler", json={"email": _e("z")}, headers=b)
        assert y.status_code == 403 and _kod(y) == "ekip_yetkisi_yok"
        uyeler = (await istemci.get("/api/v1/hesabim/uyeler", headers=b)).json()["uyeler"]
        uye_id = next(u["id"] for u in uyeler if u["uye_email"] != kisi)
        y = await istemci.delete(f"/api/v1/hesabim/uyeler/{uye_id}", headers=b)
        assert y.status_code == 403


async def test_baska_hesabin_uyeligi_yok_sayilir(istemci, ekip):
    """Kendi hesabındaki sahip, başka hesabın üyelik kimliğini değiştiremez (404)."""
    k = ekip
    liste = (await istemci.get("/api/v1/hesabim/uyeler", headers=_b(k["sahip"]))).json()["uyeler"]
    uye_id = liste[0]["id"]
    y = await istemci.delete(f"/api/v1/hesabim/uyeler/{uye_id}", headers=_b(k["yabanci"]))
    assert y.status_code == 404 and _kod(y) == "uye_yok"


async def test_yonetici_basligi_yok_sayar_ve_musteri_adina_yonetir(istemci, ekip, yonetici_basligi):
    k = ekip
    b = {**yonetici_basligi, BASLIK: _e("rastgele")}
    y = await istemci.get("/api/v1/entities/invoices/all", headers=b)
    assert y.status_code == 200 and y.json()["total"] >= 1
    y = await istemci.get(f"/api/v1/musteri-hesaplari/{k['sahip']}/uyeler", headers=yonetici_basligi)
    # Faz 4A: fikstürde `api` izinli dördüncü üye (apici) var; Faz 5M: `pazarlama` izinli beşinci (pazarlamaci);
    # Faz 6S: saha servisi izinli altıncı (sahaci).
    assert y.status_code == 200 and len(y.json()["uyeler"]) == 6
    y = await istemci.post(
        f"/api/v1/musteri-hesaplari/{k['sahip']}/uyeler", json={"email": _e("ajans"), "rol": "uye"}, headers=yonetici_basligi
    )
    assert y.status_code == 200 and y.json()["uye"]["ekleyen"] == "yonetici@test.dev"
    uye_id = y.json()["uye"]["id"]
    y = await istemci.delete(f"/api/v1/musteri-hesaplari/{k['sahip']}/uyeler/{uye_id}", headers=yonetici_basligi)
    assert y.status_code == 200
    # Müşteri ajans ucunu kullanamaz.
    y = await istemci.get(f"/api/v1/musteri-hesaplari/{k['sahip']}/uyeler", headers=_b(k["sahip"]))
    assert y.status_code == 403


# ---------------------------------------------------------------------------
# Kişi yazar / hesap sahiplik
# ---------------------------------------------------------------------------
async def test_uye_talebi_hesap_adina_acar_yazar_kendisi(istemci, ekip, db_oturumu):
    from models.support_tickets import Support_tickets
    from models.ticket_replies import Ticket_replies

    k = ekip
    b = _b(k["uye"], k["sahip"])
    y = await istemci.post(
        "/api/v1/entities/support_tickets",
        json={"subject": "Ekipten", "message": "m", "client_email": "saldirgan@x.dev"},
        headers=b,
    )
    assert y.status_code == 201
    assert y.json()["client_email"] == k["sahip"] and y.json()["acan_email"] == k["uye"]

    y = await istemci.post(f"/api/v1/talep/{k['T']}/mesaj", json={"mesaj": "Ben yazdım"}, headers=b)
    assert y.status_code == 200
    satir = (
        await db_oturumu.execute(select(Ticket_replies).where(Ticket_replies.ticket_id == k["T"]).order_by(Ticket_replies.id.desc()))
    ).scalars().first()
    assert satir.yazan == "musteri" and satir.yazan_email == k["uye"]
    talep = (await db_oturumu.execute(select(Support_tickets).where(Support_tickets.id == k["T"]))).scalar_one()
    assert talep.client_email == k["sahip"]


async def test_uyelik_degisiklikleri_denetime_duser_jeton_ozeti_maskeli(istemci, db_oturumu):
    from models.audit_log import AuditLog

    sahip, kisi = _e("sahip"), _e("denetim")
    y = await istemci.post("/api/v1/hesabim/uyeler", json={"email": kisi, "rol": "uye"}, headers=_b(sahip))
    uye_id = y.json()["uye"]["id"]
    await istemci.put(f"/api/v1/hesabim/uyeler/{uye_id}", json={"izinler": ["destek"]}, headers=_b(sahip))
    satirlar = (
        await db_oturumu.execute(
            select(AuditLog).where(AuditLog.tablo == "hesap_uyeleri", AuditLog.kayit_id == str(uye_id)).order_by(AuditLog.id)
        )
    ).scalars().all()
    assert [s.islem for s in satirlar][:2] == ["olustur", "guncelle"]
    assert all(s.ilgili_eposta == sahip and s.aktor_eposta == sahip for s in satirlar)
    olusturma = json.loads(satirlar[0].degisiklik_json)
    assert olusturma["davet_jetonu_ozet"][1] == "***"
    # Sahibin "hesap hareketleri"nde görünüyor.
    y = await istemci.get("/api/v1/denetim/benim", headers=_b(sahip))
    assert any(h["tablo"] == "hesap_uyeleri" for h in y.json())


# ---------------------------------------------------------------------------
# Bildirim alıcı genişletmesi
# ---------------------------------------------------------------------------
async def test_bildirim_alicilari_izne_gore_genisler(ekip, db_oturumu):
    from models.notifications import Notifications
    from services.notify import dispatch

    k = ekip
    await _uye_ekle(db_oturumu, k["sahip"], _e("pasif"), "yonetici", durum="pasif")

    async def alicilar(olay):
        satirlar = await dispatch(
            db_oturumu,
            event_type=olay,
            title=f"{olay} {uuid.uuid4().hex[:6]}",
            body="b",
            recipients=[{"email": k["sahip"], "role": "client"}],
            link="/client?sekme=invoices",
        )
        return {s.recipient_email: s for s in satirlar if s.channel == "inapp"}

    fatura = await alicilar("invoice")
    assert set(fatura) == {k["sahip"], k["fatura"]}
    assert fatura[k["sahip"]].link == "/client?sekme=invoices"
    assert fatura[k["fatura"]].link == f"/client?sekme=invoices&hesap={k['sahip'].replace('@', '%40')}"
    assert set(await alicilar("ticket_reply")) == {k["sahip"], k["uye"]}
    # Kişisel / bağlantı taşıyan olaylar genişlemez.
    assert set(await alicilar("yeni_oturum")) == {k["sahip"]}
    assert set(await alicilar("imzali_islem")) == {k["sahip"]}
    assert (await db_oturumu.execute(select(Notifications).where(Notifications.recipient_email == k["kisitli"]))).first() is None


# ---------------------------------------------------------------------------
# Güvenlik incelemesi: eski IDOR'lar
# ---------------------------------------------------------------------------
async def test_proje_zaman_cizelgesi_yalniz_hesabin_projesi_ve_yalniz_acik_kayitlar(istemci, ekip, db_oturumu):
    from models.project_events import Project_events

    k = ekip
    db_oturumu.add(Project_events(project_id=k["P"], event_type="note", title="İç not", visible_to_client="0"))
    db_oturumu.add(Project_events(project_id=k["P"], event_type="note", title="Açık not", visible_to_client="1"))
    await db_oturumu.commit()
    y = await istemci.get(f"/api/v1/entities/project_events?project_id={k['P']}", headers=_b(k["yabanci"]))
    assert y.status_code == 404
    y = await istemci.get(f"/api/v1/entities/project_events?project_id={k['P']}&client_view=false", headers=_b(k["sahip"]))
    assert [e["title"] for e in y.json()["items"]] == ["Açık not"]


async def test_bildirimler_kisiye_daraltilir(istemci, ekip, db_oturumu):
    from services.notify import dispatch

    k = ekip
    await dispatch(db_oturumu, event_type="yeni_oturum", title="Gizli", body="", recipients=[{"email": k["sahip"], "role": "client"}])
    y = await istemci.get(f"/api/v1/entities/notifications?recipient_email={k['sahip']}", headers=_b(k["yabanci"]))
    assert y.status_code == 200 and y.json()["items"] == []
    y = await istemci.get(f"/api/v1/entities/notifications?recipient_email={k['sahip']}", headers=_b(k["sahip"]))
    assert any(i["title"] == "Gizli" for i in y.json()["items"])
    assert (await istemci.get("/api/v1/entities/notifications/log", headers=_b(k["sahip"]))).status_code == 403


async def test_toplu_olusturma_ve_teklif_okuma_yoneticide(istemci, ekip, yonetici_basligi):
    k = ekip
    y = await istemci.post(
        "/api/v1/entities/support_tickets/batch",
        json={"items": [{"subject": "s", "message": "m", "client_email": "baskasi@x.dev"}]},
        headers=_b(k["sahip"]),
    )
    assert y.status_code == 403
    assert (await istemci.post("/api/v1/entities/inquiries/batch", json={"items": []})).status_code == 401
    for tablo in ("pricing_inquiries", "content_posts", "analytics_snapshots", "marketplace_items"):
        assert (await istemci.get(f"/api/v1/entities/{tablo}", headers=_b(k["sahip"]))).status_code == 403, tablo
    assert (await istemci.get("/api/v1/entities/pricing_inquiries", headers=yonetici_basligi)).status_code == 200


async def test_imzali_baglanti_ve_durum_sayfasi_etkilenmez(istemci, ekip, db_oturumu):
    """1E imzalı işlem bağlantısı jetonla çalışır; başlık (geçersiz bile olsa) onu etkilemez."""
    from services import imzali_islem

    k = ekip
    from models.projects import Projects

    p = await _ekle(db_oturumu, Projects(title="T", description="d", category="W", client_email=k["sahip"], stage="review"))
    jeton, _ = await imzali_islem.olustur(db_oturumu, "teslimat_onay", ("projects", p.id), k["sahip"], "Onay")
    y = await istemci.get(f"/api/v1/islem/{jeton}", headers=_b(k["yabanci"], k["sahip"]))
    assert y.status_code == 200
    y = await istemci.get("/api/v1/durum/olmayan-sayfa", headers=_b(k["yabanci"], k["sahip"]))
    assert y.status_code == 404 and _kod(y) == "sayfa_yok"


async def test_destek_izinli_uye_epostayla_yanitlayabilir_izinsiz_yanitlayamaz(ekip, db_oturumu):
    """Faz 2F e-posta yanıtı: talep yanıt bildirimi `destek` izinli üyeye de gidiyor;
    onun yanıtı talebe ekleniyor, izinsiz üyeninki (fatura rolü) ayrı talep oluyor."""
    from models.ticket_replies import Ticket_replies
    from services.eposta_gelen import isle

    k = ekip

    async def yanitla(gonderen, metin):
        return await isle(
            db_oturumu,
            {"message_id": f"<{uuid.uuid4().hex}@t>", "gonderen": gonderen, "konu": f"Re: [#T-{k['T']}] Konu", "metin": metin},
        )

    s = await yanitla(k["uye"], "Ekipten e-posta yanıtı")
    assert s["neden"] == "mesaj_eklendi" and s["talep_id"] == k["T"], s
    db_oturumu.expire_all()
    son = (
        await db_oturumu.execute(select(Ticket_replies).where(Ticket_replies.ticket_id == k["T"]).order_by(Ticket_replies.id.desc()))
    ).scalars().first()
    assert son.yazan_email == k["uye"] and son.mesaj == "Ekipten e-posta yanıtı"

    s = await yanitla(k["fatura"], "Faturacıdan")
    assert s["talep_id"] != k["T"] and s["neden"] == "yeni_talep_yetkisiz_belirtec", s
