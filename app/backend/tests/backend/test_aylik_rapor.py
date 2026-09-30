"""Faz 2C — aylık müşteri raporu (veri toplamı, jeton, yayın → e-posta bir kez,
zamanlı taslak/analiz) + manifest, olay kataloğu, zamanlı görev kaydı ve ek
i18n paketlerinin (dosyalar, destek, aylikRapor) 7 dilde tutarlılığı."""

import json
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

RAPOR = "/api/v1/aylik-rapor"
ACIK = "/api/v1/rapor-aylik"
MUSTERI = "/api/v1/raporlarim/aylik"
MODUL = "/api/v1/moduller"
TR = timezone(timedelta(hours=3))
EK = Path(__file__).resolve().parents[3] / "frontend" / "src" / "i18n" / "ek"
DILLER = ("tr", "en", "de", "ru", "zh", "hi", "ar")


def _eposta(on: str = "aylik") -> str:
    return f"{on}-{uuid.uuid4().hex[:10]}@test.dev"


def _an(y, a, g, s=12):
    return datetime(y, a, g, s, 0, tzinfo=TR).astimezone(timezone.utc)


async def _modul_ac(istemci, yonetici_basligi, eposta):
    y = await istemci.put(f"{MODUL}/musteri/{eposta}/aylik_rapor", json={"acik": True}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text


async def _sahte_veri(db, eposta, alan):
    """Eylül 2026 için bilinen toplamlar; Ağustos'a düşen satırlar sayılmamalı."""
    from models.client_sites import Client_sites
    from models.credit_ledger import CreditLedger
    from models.destek_sla import TalepSla
    from models.project_events import Project_events
    from models.projects import Projects
    from models.site_analyses import Site_analyses
    from models.site_izleme import SiteIzleme, UptimeGunluk, UptimeKesintisi
    from models.support_tickets import Support_tickets

    p = Projects(title="Kurumsal site", description="d", category="Website", client_email=eposta, client_name="Deniz A.Ş.",
                 status="in_progress", stage="gelistirme", progress=60)
    bitmis = Projects(title="Logo", description="d", category="Tasarım", client_email=eposta, status="completed",
                      updated_at=_an(2026, 9, 20))
    db.add_all([p, bitmis])
    await db.flush()
    db.add_all([
        Project_events(project_id=p.id, event_type="note", title="Ana sayfa tasarımı", visible_to_client="1", created_at=_an(2026, 9, 3)),
        Project_events(project_id=p.id, event_type="delivery", title="İletişim formu", visible_to_client="1", created_at=_an(2026, 9, 28)),
        Project_events(project_id=p.id, event_type="note", title="İç not", visible_to_client="0", created_at=_an(2026, 9, 10)),
        Project_events(project_id=p.id, event_type="note", title="Ağustos işi", visible_to_client="1", created_at=_an(2026, 8, 30)),
        CreditLedger(musteri_eposta=eposta, miktar=10, tur="satin_alma", created_at=_an(2026, 9, 1), kaynak_ref=f"t:{uuid.uuid4().hex}"),
        CreditLedger(musteri_eposta=eposta, miktar=-2.5, tur="harcama", created_at=_an(2026, 9, 5)),
        CreditLedger(musteri_eposta=eposta, miktar=-1, tur="harcama", created_at=_an(2026, 9, 29)),
        CreditLedger(musteri_eposta=eposta, miktar=-3, tur="harcama", created_at=_an(2026, 8, 31)),
    ])
    t1 = Support_tickets(client_email=eposta, subject="A", message="m", status="closed", priority="normal", created_at=_an(2026, 9, 7, 10))
    t2 = Support_tickets(client_email=eposta, subject="B", message="m", status="open", priority="normal", created_at=_an(2026, 9, 14, 10))
    t_eski = Support_tickets(client_email=eposta, subject="C", message="m", status="open", priority="normal", created_at=_an(2026, 8, 3, 10))
    db.add_all([t1, t2, t_eski])
    await db.flush()
    # SLA: t1 zamanında yanıtlanıp 8 Eylül'de çözüldü; t2 hedefi (15 Eylül) geçti, yanıt yok.
    db.add_all([
        TalepSla(ticket_id=t1.id, oncelik="normal", baslangic=_an(2026, 9, 7, 10), ilk_yanit_hedef=_an(2026, 9, 7, 14),
                 cozum_hedef=_an(2026, 9, 10, 10), ilk_yanit_at=_an(2026, 9, 7, 11), cozum_at=_an(2026, 9, 8, 10),
                 uyari_ilk_at=_an(2026, 9, 7), eskalasyon_ilk_at=_an(2026, 9, 7)),
        TalepSla(ticket_id=t2.id, oncelik="normal", baslangic=_an(2026, 9, 14, 10), ilk_yanit_hedef=_an(2026, 9, 14, 14),
                 cozum_hedef=_an(2026, 9, 17, 10), uyari_ilk_at=_an(2026, 9, 14), eskalasyon_ilk_at=_an(2026, 9, 14),
                 uyari_cozum_at=_an(2026, 9, 17), eskalasyon_cozum_at=_an(2026, 9, 17)),
        TalepSla(ticket_id=t_eski.id, oncelik="normal", baslangic=_an(2026, 8, 3, 10), ilk_yanit_hedef=_an(2026, 8, 3, 14),
                 cozum_hedef=_an(2026, 8, 6, 10), uyari_ilk_at=_an(2026, 8, 3), eskalasyon_ilk_at=_an(2026, 8, 3),
                 uyari_cozum_at=_an(2026, 8, 6), eskalasyon_cozum_at=_an(2026, 8, 6)),
    ])
    site = Client_sites(client_email=eposta, ad="Deniz Site", adres=f"https://{alan}/")
    db.add(site)
    await db.flush()
    db.add_all([
        UptimeGunluk(kontrol_id=100000 + site.id, site_id=site.id, gun="2026-09-01", toplam=100, basarili=100),
        UptimeGunluk(kontrol_id=100000 + site.id, site_id=site.id, gun="2026-09-02", toplam=100, basarili=90),
        UptimeGunluk(kontrol_id=100000 + site.id, site_id=site.id, gun="2026-08-31", toplam=100, basarili=0),
        UptimeKesintisi(kontrol_id=100000 + site.id, site_id=site.id, baslangic=_an(2026, 9, 2, 10), bitis=_an(2026, 9, 2, 10) + timedelta(minutes=30)),
        UptimeKesintisi(kontrol_id=100000 + site.id, site_id=site.id, baslangic=_an(2026, 8, 20, 10), bitis=_an(2026, 8, 20, 11)),
        SiteIzleme(site_id=site.id, ssl_bitis=datetime.now(timezone.utc) + timedelta(days=40)),
        Site_analyses(alan_adi=alan, url=f"https://{alan}/", durum="tamam", puan=70, kaynak="aylik", created_at=_an(2026, 8, 2),
                      ozet_json=json.dumps({"bolumler": [{"anahtar": "seo", "puan": 60}]})),
        Site_analyses(alan_adi=alan, url=f"https://{alan}/", durum="tamam", puan=82, kaynak="aylik", created_at=_an(2026, 9, 2),
                      ozet_json=json.dumps({"bolumler": [{"anahtar": "seo", "puan": 80}, {"anahtar": "hiz", "puan": 84}]})),
        Site_analyses(alan_adi=alan, url=f"https://{alan}/", durum="tamam", puan=99, kaynak="aylik", created_at=_an(2026, 10, 2)),
    ])
    await db.commit()
    return {"t1": t1.id, "t2": t2.id}


async def test_aylik_rapor_verisi_beklenen_toplamlar(db_oturumu):
    from services.aylik_rapor import ozet_metni, veri_topla

    eposta = _eposta("veri")
    alan = f"{uuid.uuid4().hex[:8]}.example.com"
    await _sahte_veri(db_oturumu, eposta, alan)
    v = await veri_topla(db_oturumu, eposta, "2026-09")
    o = v["ozet"]
    assert v["musteri_adi"] == "Deniz A.Ş." and v["baslangic"] == "2026-09-01" and v["bitis"] == "2026-09-30"
    assert o["is_sayisi"] == 2 and [i["baslik"] for i in o["isler"]] == ["Ana sayfa tasarımı", "İletişim formu"]
    assert [p["baslik"] for p in o["tamamlanan_projeler"]] == ["Logo"]
    assert o["harcanan_kredi"] == 3.5 and o["yuklenen_kredi"] == 10
    assert o["acilan_talep"] == 2 and o["cozulen_talep"] == 1
    assert (o["sla_uyumlu"], o["sla_ihlal"], o["sla_uyum_yuzde"]) == (1, 1, 50.0)
    [s] = v["site_sagligi"]
    assert s["uptime_yuzde"] == 95.0 and s["olcum"] == 200 and s["kesinti_sayisi"] == 1 and s["kesinti_dk"] == 30
    assert 39 <= s["ssl_kalan"] <= 40
    [seo] = v["seo"]
    assert (seo["puan"], seo["onceki_puan"], seo["degisim"], seo["alan_adi"]) == (82, 70, 12, alan)  # Ekim analizi sayılmıyor
    assert seo["bolumler"] == [{"anahtar": "seo", "puan": 80}, {"anahtar": "hiz", "puan": 84}]
    assert [p["baslik"] for p in v["plan"]["acik_projeler"]] == ["Kurumsal site"]
    assert {t["konu"] for t in v["plan"]["acik_talepler"]} == {"B", "C"}
    metin = ozet_metni(v)
    assert metin.startswith("Eylül 2026:") and "3.5 saat" in metin and "SLA uyumu %50" in metin and "uptime %95" in metin


def test_donem_ve_jeton():
    from services.aylik_rapor import RaporHatasi, donem_dogrula, donem_sinirlari, jeton_dogru_mu, jeton_id, jeton_uret, onceki_donem

    assert onceki_donem(_an(2026, 1, 3)) == "2025-12" and onceki_donem(_an(2026, 10, 1, 0)) == "2026-09"
    bas, bit, ilk, son = donem_sinirlari("2026-02")
    assert (ilk, son) == (date(2026, 2, 1), date(2026, 2, 28))
    assert bas == datetime(2026, 1, 31, 21, tzinfo=timezone.utc)  # TR gece yarısı
    for kotu in ("2026-13", "26-01", "abc", None):
        with pytest.raises(RaporHatasi):
            donem_dogrula(kotu)

    class R:
        id, donem, client_email = 12, "2026-09", "a@b.co"

    j = jeton_uret(R)
    assert jeton_id(j) == 12 and jeton_dogru_mu(R, j)
    assert not jeton_dogru_mu(R, j[:-1] + ("0" if j[-1] != "0" else "1"))
    R2 = type("R2", (), {"id": 12, "donem": "2026-09", "client_email": "baska@b.co"})
    assert not jeton_dogru_mu(R2, j)  # başka müşterinin raporu aynı jetonla açılmaz
    assert jeton_id("12") is None and jeton_id("x-y") is None and jeton_id("12.abc") is None


async def test_olustur_onizle_yayinla_eposta_bir_kez(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    from models.notifications import Notifications

    eposta = _eposta("yayin")
    alan = f"{uuid.uuid4().hex[:8]}.example.com"
    await _sahte_veri(db_oturumu, eposta, alan)
    await _modul_ac(istemci, yonetici_basligi, eposta)

    assert (await istemci.post(f"{RAPOR}/olustur", json={"client_email": eposta, "donem": "2026-09"}, headers=musteri_basligi(eposta))).status_code == 403
    assert (await istemci.post(f"{RAPOR}/olustur", json={"client_email": eposta, "donem": "2026-9x"}, headers=yonetici_basligi)).status_code == 400
    r = (await istemci.post(f"{RAPOR}/olustur", json={"client_email": eposta, "donem": "2026-09"}, headers=yonetici_basligi)).json()
    assert r["durum"] == "taslak" and r["veri"]["ozet"]["harcanan_kredi"] == 3.5 and r["jeton"]
    # Aynı dönem tekrar → aynı satır (çift rapor yok), not korunur.
    await istemci.put(f"{RAPOR}/{r['id']}", json={"yonetici_notu": "Ekim'de SEO içerikleri başlıyor."}, headers=yonetici_basligi)
    r2 = (await istemci.post(f"{RAPOR}/olustur", json={"client_email": eposta, "donem": "2026-09"}, headers=yonetici_basligi)).json()
    assert r2["id"] == r["id"] and r2["yonetici_notu"] == "Ekim'de SEO içerikleri başlıyor."

    # Taslak: müşteri arşivinde yok; jetonla girişsiz açılmaz; yönetici oturumuyla açılır.
    assert (await istemci.get(MUSTERI, headers=musteri_basligi(eposta))).json() == []
    assert (await istemci.get(f"{ACIK}/{r['jeton']}")).status_code == 404
    on = await istemci.get(f"{ACIK}/{r['jeton']}", headers=yonetici_basligi)
    assert on.status_code == 200 and on.json()["durum"] == "taslak"
    # Abonelik rapor listesine karışmıyor.
    assert all(x["id"] != r["id"] for x in (await istemci.get("/api/v1/abonelik/raporlar", headers=yonetici_basligi)).json())

    # Yayınla iki kez → e-posta tek.
    y1 = (await istemci.post(f"{RAPOR}/{r['id']}/yayinla", headers=yonetici_basligi)).json()
    y2 = (await istemci.post(f"{RAPOR}/{r['id']}/yayinla", headers=yonetici_basligi)).json()
    assert y1["eposta_gonderildi"] is True and y2["eposta_gonderildi"] is False and y2["durum"] == "yayinlandi"
    db_oturumu.expire_all()
    satirlar = (
        await db_oturumu.execute(
            select(Notifications).where(Notifications.event_type == "aylik_rapor", Notifications.recipient_email == eposta)
        )
    ).scalars().all()
    assert len([n for n in satirlar if n.channel == "inapp"]) == 1
    assert satirlar[0].link == f"/rapor-aylik/{r['jeton']}" and "rapor-aylik" in satirlar[0].body

    # Yayında: müşteri arşivi + girişsiz jeton; kurcalanmış jeton 404; e-posta/iç alan yok.
    arsiv = (await istemci.get(MUSTERI, headers=musteri_basligi(eposta))).json()
    assert [a["id"] for a in arsiv] == [r["id"]] and arsiv[0]["jeton"] == r["jeton"]
    acik = await istemci.get(f"{ACIK}/{r['jeton']}")
    assert acik.status_code == 200 and acik.json()["yonetici_notu"].startswith("Ekim") and eposta not in acik.text
    assert (await istemci.get(f"{ACIK}/{r['id']}-{'0' * 32}")).status_code == 404
    # Başka müşteri kendi arşivinde görmez.
    baska = _eposta("baska")
    await _modul_ac(istemci, yonetici_basligi, baska)
    assert (await istemci.get(MUSTERI, headers=musteri_basligi(baska))).json() == []
    # Yayınlanmış rapor yeniden oluşturulamaz / not değişmez / silinmez.
    assert (await istemci.post(f"{RAPOR}/olustur", json={"client_email": eposta, "donem": "2026-09"}, headers=yonetici_basligi)).status_code == 409
    assert (await istemci.put(f"{RAPOR}/{r['id']}", json={"yonetici_notu": "x"}, headers=yonetici_basligi)).status_code == 409
    assert (await istemci.delete(f"{RAPOR}/{r['id']}", headers=yonetici_basligi)).status_code == 409


async def test_modul_bekcisi_aylik_rapor(istemci, yonetici_basligi, musteri_basligi):
    eposta = _eposta("bekci")
    y = await istemci.get(MUSTERI, headers=musteri_basligi(eposta))
    assert y.status_code == 403 and y.json()["detail"] == {"kod": "modul_kapali", "modul": "aylik_rapor"}
    await _modul_ac(istemci, yonetici_basligi, eposta)
    assert (await istemci.get(MUSTERI, headers=musteri_basligi(eposta))).status_code == 200
    assert (await istemci.get(MUSTERI)).status_code == 401


async def test_zamanli_taslaklar_ve_aylik_analiz(istemci, yonetici_basligi, db_oturumu, monkeypatch):
    from models.client_sites import Client_sites
    from models.site_analyses import Site_analyses
    from services import aylik_rapor
    from services import site_analizi as motor

    eposta = _eposta("zaman")
    await _modul_ac(istemci, yonetici_basligi, eposta)
    alan = f"{uuid.uuid4().hex[:8]}.example.com"
    db_oturumu.add(Client_sites(client_email=eposta, ad="Zaman", adres=f"https://{alan}/"))
    await db_oturumu.commit()

    assert (await aylik_rapor.aylik_taslaklar(db_oturumu, an=_an(2026, 10, 12)))["atlandi"] == "ay_basi_degil"
    sonuc = await aylik_rapor.aylik_taslaklar(db_oturumu, an=_an(2026, 10, 1, 9))
    assert sonuc["donem"] == "2026-09" and sonuc["acilan"] >= 1
    r = await aylik_rapor.rapor_bul(db_oturumu, eposta, "2026-09")
    assert r is not None and r.durum == "taslak"
    # İkinci tur aynı dönemi yeniden açmıyor.
    ikinci = await aylik_rapor.aylik_taslaklar(db_oturumu, an=_an(2026, 10, 2, 9))
    assert (await aylik_rapor.rapor_bul(db_oturumu, eposta, "2026-09")).id == r.id and ikinci["acilan"] == 0

    cagrilar = []

    async def sahte_analiz(url):
        cagrilar.append(url)
        return {"puan": 77, "bolumler": [], "ayrinti": {}}

    monkeypatch.setattr(motor, "analiz_et", sahte_analiz)
    monkeypatch.setattr(motor, "ozetle", lambda b: [])
    # Tur başına en çok bir analiz; son 25 günde analizi olan alan atlanıyor.
    for _ in range(4):
        await aylik_rapor.aylik_analizler(db_oturumu)
    db_oturumu.expire_all()
    kayitlar = (await db_oturumu.execute(select(Site_analyses).where(Site_analyses.alan_adi == alan))).scalars().all()
    assert len(kayitlar) == 1 and kayitlar[0].kaynak == "aylik" and kayitlar[0].puan == 77 and kayitlar[0].eposta == eposta
    assert sum(1 for c in cagrilar if alan in c) == 1


# ---------------------------------------------------------------------------
# Manifest, olaylar, zamanlı görevler, ek i18n paketleri
# ---------------------------------------------------------------------------
def test_manifest_faz2c():
    from core import moduller as mf

    d, kb, ar, destek = mf.modul("dosyalar"), mf.modul("bilgi_bankasi"), mf.modul("aylik_rapor"), mf.modul("destek")
    assert d.durum == "yayinda" and d.musteri_sekmesi == "dosyalar" and d.yonetici_sekmesi == "dosyalar"
    assert kb.durum == "yayinda" and kb.varsayilan_acik and kb.bagimliliklar == ("destek",) and kb.yonetici_sekmesi == "bilgiBankasi"
    assert ar.durum == "yayinda" and set(ar.bagimliliklar) == {"raporlar", "site_analizi"}
    assert destek.cekirdek
    assert mf.manifest_hatalari() == []


def test_olay_katalogu_ve_etiketler_faz2c():
    from services.bildirim_tercih import OLAYLAR

    yeni = ("dosya_eklendi", "belge_talebi", "belge_teslim", "belge_hatirlatma", "belge_gecikti",
            "sla_yaklasiyor", "sla_asildi", "aylik_rapor", "aylik_rapor_taslak")
    tr = json.loads((EK / "bildirim" / "tr.json").read_text(encoding="utf-8"))["bildirim"]["olay"]
    for olay in yeni:
        assert OLAYLAR[olay]["tetikleniyor"] is True
        for dil in DILLER:
            ek = json.loads((EK / "bildirim" / f"{dil}.json").read_text(encoding="utf-8"))["bildirim"]["olay"]
            assert ek[olay].strip(), (dil, olay)
            if dil != "tr":
                assert ek[olay] != tr[olay], (dil, olay)


def test_zamanli_gorev_kaydi_faz2c():
    from services.zamanli import GOREV_ADLARI

    for ad in ("sla_kontrolu", "belge_hatirlatmalari", "aylik_rapor_taslaklari", "aylik_site_analizi"):
        assert ad in GOREV_ADLARI
    assert GOREV_ADLARI[0] == "uptime" and GOREV_ADLARI[-1] == "aylik_site_analizi"


def _duz(d, on=""):
    for k, v in d.items():
        if isinstance(v, dict):
            yield from _duz(v, f"{on}{k}.")
        else:
            yield f"{on}{k}", v


@pytest.mark.parametrize("paket", ["dosyalar", "yardim", "aylikRapor"])
def test_ek_paket_yedi_dilde_ayni_anahtarlar_ve_gercek_ceviri(paket):
    paketler = {
        dil: dict(_duz(json.loads((EK / paket / f"{dil}.json").read_text(encoding="utf-8"))[paket])) for dil in DILLER
    }
    anahtarlar = set(paketler["tr"])
    assert len(anahtarlar) > 20
    for dil, p in paketler.items():
        assert set(p) == anahtarlar, (dil, sorted(set(p) ^ anahtarlar)[:5])
        assert all(isinstance(v, str) and v.strip() for v in p.values()), dil
    for dil in ("en", "de", "ru", "zh", "hi", "ar"):
        ayni = [k for k in anahtarlar if paketler[dil][k] == paketler["tr"][k] and len(paketler["tr"][k]) > 12]
        assert not ayni, (dil, ayni[:5])


def test_modul_ek_paketinde_bilgi_bankasi():
    from core import moduller as mf

    for dil in DILLER:
        m = json.loads((EK / "modul" / f"{dil}.json").read_text(encoding="utf-8"))["modul"]["m"]
        assert m["bilgi_bankasi"]["ad"] and m["bilgi_bankasi"]["aciklama"], dil
        if dil in ("tr", "en"):
            assert m["bilgi_bankasi"]["ad"] == mf.modul("bilgi_bankasi").ad_varsayilan[dil]
