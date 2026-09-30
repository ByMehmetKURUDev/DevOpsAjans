"""Faz 2B — proje görevleri: CRUD + yetki, bağımlılık/üst görev döngüsü, tamam kuralı,
kontrol listesi, Kanban toplu sıra, saat girişi, revizyon sayacı (ay sınırı),
krediden düşme, 1E revizyon isteği → görev, modül bekçisi ve bildirimler.
"""

import json
import uuid
from datetime import date

import pytest
from sqlalchemy import select

G = "/api/v1/gorevler"
GM = "/api/v1/gorevlerim"
MODUL = "/api/v1/moduller"
KREDI = "/api/v1/kredi/yonetim"


def _eposta(on: str = "gorev") -> str:
    return f"{on}-{uuid.uuid4().hex[:10]}@test.dev"


async def _proje(db, eposta, **ek):
    from models.projects import Projects

    alanlar = dict(title=f"Proje {uuid.uuid4().hex[:6]}", description="d", category="Website",
                   client_email=eposta, client_name="Müşteri", stage="build", status="in_progress", progress=40)
    alanlar.update(ek)
    kayit = Projects(**alanlar)
    db.add(kayit)
    await db.commit()
    await db.refresh(kayit)
    return kayit


async def _gorev(istemci, basliklar, proje_id, beklenen=200, **govde):
    govde.setdefault("baslik", f"Görev {uuid.uuid4().hex[:4]}")
    y = await istemci.post(f"{G}/proje/{proje_id}", json=govde, headers=basliklar)
    assert y.status_code == beklenen, y.text
    return y.json()


async def _bildirimler(db, olay, eposta=None, ref_id=None):
    from models.notifications import Notifications

    sorgu = select(Notifications).where(Notifications.event_type == olay, Notifications.channel == "inapp")
    if eposta:
        sorgu = sorgu.where(Notifications.recipient_email == eposta)
    if ref_id is not None:
        sorgu = sorgu.where(Notifications.ref_id == ref_id)
    return list((await db.execute(sorgu)).scalars().all())


# ---------------------------------------------------------------------------
# Yetki
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "metot,yol",
    [
        ("GET", f"{G}/proje/1"),
        ("POST", f"{G}/proje/1"),
        ("PUT", f"{G}/proje/1/sira"),
        ("PATCH", f"{G}/1"),
        ("DELETE", f"{G}/1"),
        ("POST", f"{G}/1/kontrol"),
        ("POST", f"{G}/1/bagimlilik"),
        ("POST", f"{G}/1/saat"),
        ("PUT", f"{G}/proje/1/revizyon"),
    ],
)
async def test_yonetici_uclari_anonime_401_musteriye_403(istemci, musteri_basligi, metot, yol):
    govde = {} if metot in ("POST", "PUT", "PATCH") else None
    assert (await istemci.request(metot, yol, json=govde)).status_code == 401
    assert (await istemci.request(metot, yol, json=govde, headers=musteri_basligi())).status_code == 403


async def test_musteri_ucu_oturumsuz_401(istemci):
    assert (await istemci.get(f"{GM}/proje/1")).status_code == 401
    assert (await istemci.get(f"{GM}/revizyon")).status_code == 401


# ---------------------------------------------------------------------------
# CRUD + müşteri görünümü
# ---------------------------------------------------------------------------


async def test_gorev_crud_ve_musteri_yalniz_gorunenleri_gorur(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    a, b = _eposta("a"), _eposta("b")
    proje = await _proje(db_oturumu, a)
    baska = await _proje(db_oturumu, b)
    g1 = await _gorev(istemci, yonetici_basligi, proje.id, baslik="Tasarım", musteriye_gorunur=True, kilometre_tasi=True,
                      bitis_tarihi="2026-10-15", atanan=None, etiketler=["Tasarim", "tasarim", " "])
    g2 = await _gorev(istemci, yonetici_basligi, proje.id, baslik="Geliştirme", musteriye_gorunur=True, durum="tamam")
    gizli = await _gorev(istemci, yonetici_basligi, proje.id, baslik="İç not: sunucu şifresini değiştir", musteriye_gorunur=False)
    assert g1["etiketler"] == ["tasarim"] and g1["bitis_tarihi"] == "2026-10-15" and g1["kilometre_tasi"] is True
    assert g2["tamamlandi_at"] is not None and g1["sira"] == 0

    # Doğrulamalar
    await _gorev(istemci, yonetici_basligi, proje.id, 400, baslik="   ")
    await _gorev(istemci, yonetici_basligi, proje.id, 400, durum="bitti")
    await _gorev(istemci, yonetici_basligi, proje.id, 400, oncelik="hemen")
    await _gorev(istemci, yonetici_basligi, proje.id, 400, bitis_tarihi="31/12/2026")
    await _gorev(istemci, yonetici_basligi, proje.id, 400, atanan="yabanci@test.dev")  # ekipte değil
    await _gorev(istemci, yonetici_basligi, proje.id, 400, tahmini_saat=1.3)
    await _gorev(istemci, yonetici_basligi, 999999, 404)

    # Yönetici listesi hepsini görür
    y = await istemci.get(f"{G}/proje/{proje.id}", headers=yonetici_basligi)
    assert y.status_code == 200
    assert {g["id"] for g in y.json()["gorevler"]} == {g1["id"], g2["id"], gizli["id"]}
    assert y.json()["proje"]["client_email"] == a

    # Müşteri yalnız görünür 2 görevi, iç alanlar olmadan
    y = await istemci.get(f"{GM}/proje/{proje.id}", headers=musteri_basligi(a))
    assert y.status_code == 200, y.text
    govde = y.json()
    assert {g["baslik"] for g in govde["gorevler"]} == {"Tasarım", "Geliştirme"}
    assert "sunucu" not in json.dumps(govde)
    assert all("atanan" not in g and "harcanan_saat" not in g and "etiketler" not in g for g in govde["gorevler"])
    assert govde["ilerleme"] == {"toplam": 2, "tamam": 1, "yuzde": 50}
    assert [k["baslik"] for k in govde["kilometre_taslari"]] == ["Tasarım"]

    # Başkasının projesi 404 (varlığı sızmaz); yönetici her projeyi görebilir
    assert (await istemci.get(f"{GM}/proje/{proje.id}", headers=musteri_basligi(b))).status_code == 404
    assert (await istemci.get(f"{GM}/proje/{baska.id}", headers=musteri_basligi(a))).status_code == 404
    assert (await istemci.get(f"{GM}/proje/999999", headers=musteri_basligi(a))).status_code == 404

    # Güncelle / sil
    y = await istemci.patch(f"{G}/{g1['id']}", json={"baslik": "Tasarım v2", "oncelik": "yuksek", "musteriye_gorunur": False}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["baslik"] == "Tasarım v2" and y.json()["musteriye_gorunur"] is False
    y = await istemci.get(f"{GM}/proje/{proje.id}", headers=musteri_basligi(a))
    assert [g["baslik"] for g in y.json()["gorevler"]] == ["Geliştirme"]
    assert (await istemci.delete(f"{G}/{gizli['id']}", headers=yonetici_basligi)).status_code == 200
    assert (await istemci.patch(f"{G}/{gizli['id']}", json={"baslik": "x"}, headers=yonetici_basligi)).status_code == 404


async def test_atanan_ekipten_olmali(istemci, yonetici_basligi, db_oturumu):
    from models.staff import Staff

    kisi = _eposta("ekip")
    db_oturumu.add(Staff(ad="Ekip Kişi", email=kisi, rol="calisan", aktif=True))
    await db_oturumu.commit()
    proje = await _proje(db_oturumu, _eposta())
    g = await _gorev(istemci, yonetici_basligi, proje.id, atanan=kisi.upper())
    assert g["atanan"] == kisi
    y = await istemci.get(f"{G}/proje/{proje.id}", headers=yonetici_basligi)
    assert any(e["email"] == kisi for e in y.json()["ekip"])


# ---------------------------------------------------------------------------
# Alt görev, bağımlılık, tamam kuralı
# ---------------------------------------------------------------------------


async def test_ust_gorev_ayni_proje_ve_dongu_engeli(istemci, yonetici_basligi, db_oturumu):
    proje = await _proje(db_oturumu, _eposta())
    baska = await _proje(db_oturumu, _eposta())
    ana = await _gorev(istemci, yonetici_basligi, proje.id)
    alt = await _gorev(istemci, yonetici_basligi, proje.id, ust_gorev_id=ana["id"])
    torun = await _gorev(istemci, yonetici_basligi, proje.id, ust_gorev_id=alt["id"])
    assert alt["ust_gorev_id"] == ana["id"]
    diger = await _gorev(istemci, yonetici_basligi, baska.id)
    await _gorev(istemci, yonetici_basligi, proje.id, 400, ust_gorev_id=diger["id"])
    y = await istemci.patch(f"{G}/{ana['id']}", json={"ust_gorev_id": torun["id"]}, headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "ust_gorev_dongusu"
    y = await istemci.patch(f"{G}/{ana['id']}", json={"ust_gorev_id": ana["id"]}, headers=yonetici_basligi)
    assert y.status_code == 409
    # Üst silinince alt görev üstsüz kalır
    assert (await istemci.delete(f"{G}/{ana['id']}", headers=yonetici_basligi)).status_code == 200
    y = await istemci.get(f"{G}/proje/{proje.id}", headers=yonetici_basligi)
    assert {g["id"]: g["ust_gorev_id"] for g in y.json()["gorevler"]}[alt["id"]] is None


async def test_bagimlilik_dongusu_ve_tamam_kurali(istemci, yonetici_basligi, db_oturumu):
    proje = await _proje(db_oturumu, _eposta())
    a = await _gorev(istemci, yonetici_basligi, proje.id, baslik="A")
    b = await _gorev(istemci, yonetici_basligi, proje.id, baslik="B")
    c = await _gorev(istemci, yonetici_basligi, proje.id, baslik="C")
    baska = await _gorev(istemci, yonetici_basligi, (await _proje(db_oturumu, _eposta())).id)

    ekle = lambda g, h: istemci.post(f"{G}/{g}/bagimlilik", json={"bagli_oldugu_id": h}, headers=yonetici_basligi)  # noqa: E731
    assert (await ekle(a["id"], b["id"])).status_code == 200  # A, B'ye bağlı
    assert (await ekle(b["id"], c["id"])).status_code == 200  # B, C'ye bağlı
    y = await ekle(c["id"], a["id"])  # C → A: döngü
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "bagimlilik_dongusu"
    assert (await ekle(a["id"], a["id"])).status_code == 409
    assert (await ekle(a["id"], baska["id"])).status_code == 400
    assert (await ekle(a["id"], b["id"])).status_code == 200  # tekrar eklemek zararsız

    # A, B bitmeden tamama geçemez
    y = await istemci.patch(f"{G}/{a['id']}", json={"durum": "tamam"}, headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"] == {"kod": "bagimlilik_bitmedi", "gorevler": [b["id"]]}
    y = await istemci.get(f"{G}/proje/{proje.id}", headers=yonetici_basligi)
    ga = next(g for g in y.json()["gorevler"] if g["id"] == a["id"])
    assert ga["bagimliliklar"] == [b["id"]] and ga["bekleyen_bagimliliklar"] == [b["id"]] and ga["durum"] == "yapilacak"
    # Tamama geçmeyen durumlar serbest
    assert (await istemci.patch(f"{G}/{a['id']}", json={"durum": "incelemede"}, headers=yonetici_basligi)).status_code == 200

    # Zincir: C → B → A
    assert (await istemci.patch(f"{G}/{c['id']}", json={"durum": "tamam"}, headers=yonetici_basligi)).status_code == 200
    assert (await istemci.patch(f"{G}/{b['id']}", json={"durum": "tamam"}, headers=yonetici_basligi)).status_code == 200
    y = await istemci.patch(f"{G}/{a['id']}", json={"durum": "tamam"}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["bekleyen_bagimliliklar"] == []

    # Bağımlılık kaldırılabilir
    y = await istemci.delete(f"{G}/{b['id']}/bagimlilik/{c['id']}", headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["bagimliliklar"] == []


async def test_kontrol_listesi(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    m = _eposta()
    proje = await _proje(db_oturumu, m)
    g = await _gorev(istemci, yonetici_basligi, proje.id, musteriye_gorunur=True)
    y = await istemci.post(f"{G}/{g['id']}/kontrol", json={"metin": "Logo yükle"}, headers=yonetici_basligi)
    y = await istemci.post(f"{G}/{g['id']}/kontrol", json={"metin": "Renkleri seç"}, headers=yonetici_basligi)
    assert y.status_code == 200 and [k["metin"] for k in y.json()["kontrol_listesi"]] == ["Logo yükle", "Renkleri seç"]
    assert (await istemci.post(f"{G}/{g['id']}/kontrol", json={"metin": "  "}, headers=yonetici_basligi)).status_code == 400
    k1 = y.json()["kontrol_listesi"][0]["id"]
    y = await istemci.patch(f"{G}/kontrol/{k1}", json={"tamam": True}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["kontrol_listesi"][0]["tamam"] is True
    y = await istemci.get(f"{GM}/proje/{proje.id}", headers=musteri_basligi(m))
    assert y.json()["gorevler"][0]["kontrol"] == {"tamam": 1, "toplam": 2}
    y = await istemci.delete(f"{G}/kontrol/{k1}", headers=yonetici_basligi)
    assert [k["metin"] for k in y.json()["kontrol_listesi"]] == ["Renkleri seç"]
    assert (await istemci.patch(f"{G}/kontrol/99999999", json={"tamam": True}, headers=yonetici_basligi)).status_code == 404


async def test_kanban_toplu_sira_ve_bagimlilik_hep_ya_da_hic(istemci, yonetici_basligi, db_oturumu):
    m = _eposta()
    proje = await _proje(db_oturumu, m)
    a = await _gorev(istemci, yonetici_basligi, proje.id, baslik="A", musteriye_gorunur=True)
    b = await _gorev(istemci, yonetici_basligi, proje.id, baslik="B", musteriye_gorunur=True)
    c = await _gorev(istemci, yonetici_basligi, proje.id, baslik="C", musteriye_gorunur=False)
    await istemci.post(f"{G}/{a['id']}/bagimlilik", json={"bagli_oldugu_id": b["id"]}, headers=yonetici_basligi)

    # A'yı tamama taşımak (B hâlâ yapılacak) — hiçbir şey değişmez
    y = await istemci.put(
        f"{G}/proje/{proje.id}/sira",
        json={"gorevler": [{"id": c["id"], "durum": "suruyor", "sira": 0}, {"id": a["id"], "durum": "tamam", "sira": 0}]},
        headers=yonetici_basligi,
    )
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "bagimlilik_bitmedi" and y.json()["detail"]["gorev"] == a["id"]
    liste = {g["id"]: g for g in (await istemci.get(f"{G}/proje/{proje.id}", headers=yonetici_basligi)).json()["gorevler"]}
    assert liste[c["id"]]["durum"] == "yapilacak"

    # Aynı istekte B de tamama gidiyorsa kural son duruma göre: geçer
    y = await istemci.put(
        f"{G}/proje/{proje.id}/sira",
        json={"gorevler": [
            {"id": b["id"], "durum": "tamam", "sira": 0},
            {"id": a["id"], "durum": "tamam", "sira": 1},
            {"id": c["id"], "durum": "incelemede", "sira": 0},
        ]},
        headers=yonetici_basligi,
    )
    assert y.status_code == 200, y.text
    liste = {g["id"]: g for g in y.json()["gorevler"]}
    assert (liste[b["id"]]["durum"], liste[b["id"]]["sira"]) == ("tamam", 0)
    assert (liste[a["id"]]["durum"], liste[a["id"]]["sira"]) == ("tamam", 1)
    # Bildirim: yalnız müşteriye görünen ve tamam/incelemede olanlar (C gizli)
    bildirimler = await _bildirimler(db_oturumu, "gorev_guncellendi", m)
    assert {n.ref_id for n in bildirimler} == {a["id"], b["id"]}
    assert all(n.link == "/client?sekme=projects" for n in bildirimler)

    # Geçersiz istekler
    baska = await _gorev(istemci, yonetici_basligi, (await _proje(db_oturumu, _eposta())).id)
    assert (await istemci.put(f"{G}/proje/{proje.id}/sira", json={"gorevler": [{"id": baska["id"], "durum": "tamam", "sira": 0}]}, headers=yonetici_basligi)).status_code == 404
    assert (await istemci.put(f"{G}/proje/{proje.id}/sira", json={"gorevler": [{"id": a["id"], "durum": "x", "sira": 0}]}, headers=yonetici_basligi)).status_code == 400


async def test_suruyor_bildirim_gondermez_incelemede_gonderir(istemci, yonetici_basligi, db_oturumu):
    m = _eposta()
    proje = await _proje(db_oturumu, m)
    g = await _gorev(istemci, yonetici_basligi, proje.id, musteriye_gorunur=True)
    await istemci.patch(f"{G}/{g['id']}", json={"durum": "suruyor"}, headers=yonetici_basligi)
    assert not await _bildirimler(db_oturumu, "gorev_guncellendi", m, g["id"])
    await istemci.patch(f"{G}/{g['id']}", json={"durum": "incelemede"}, headers=yonetici_basligi)
    assert len(await _bildirimler(db_oturumu, "gorev_guncellendi", m, g["id"])) == 1


# ---------------------------------------------------------------------------
# Saat, revizyon sayacı, kredi
# ---------------------------------------------------------------------------


@pytest.fixture
def bugun_eylul(monkeypatch):
    from services import gorevler as gs

    monkeypatch.setattr(gs, "_bugun", lambda: date(2026, 9, 20))


async def test_revizyon_sayaci_ay_siniri_ve_elle_hak(istemci, yonetici_basligi, musteri_basligi, db_oturumu, bugun_eylul):
    m = _eposta("rev")
    proje = await _proje(db_oturumu, m)
    rev = await _gorev(istemci, yonetici_basligi, proje.id, etiketler=["revizyon"], musteriye_gorunur=True)
    normal = await _gorev(istemci, yonetici_basligi, proje.id)

    async def saat(gid, s, tarih, beklenen=200, **ek):
        y = await istemci.post(f"{G}/{gid}/saat", json={"saat": s, "tarih": tarih, **ek}, headers=yonetici_basligi)
        assert y.status_code == beklenen, y.text
        return y.json()

    await saat(rev["id"], 2, "2026-08-31")   # önceki ay: sayılmaz
    await saat(rev["id"], 1.5, "2026-09-01")  # ayın ilk günü: sayılır
    await saat(rev["id"], 1, "2026-09-30")    # ayın son günü: sayılır
    await saat(rev["id"], 4, "2026-10-01")    # sonraki ay: sayılmaz
    await saat(normal["id"], 5, "2026-09-10")  # revizyon etiketi yok: sayılmaz
    await saat(rev["id"], 0, "2026-09-10", 400)
    await saat(rev["id"], 0.3, "2026-09-10", 400)

    y = await istemci.get(f"{GM}/revizyon", headers=musteri_basligi(m))
    assert y.status_code == 200, y.text
    s = y.json()
    assert s["ay"] == "2026-09" and s["kullanilan"] == 2.5 and s["hak"] is None and s["kaynak"] is None and s["asildi"] is False
    assert "paket" not in s

    # Paket yok → projeye elle hak
    y = await istemci.put(f"{G}/proje/{proje.id}/revizyon", json={"aylik_revizyon_saati": 2}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["revizyon"]["hak"] == 2.0
    s = (await istemci.get(f"{GM}/revizyon", headers=musteri_basligi(m))).json()
    assert (s["hak"], s["kaynak"], s["kalan"], s["asim"], s["asildi"]) == (2.0, "proje", -0.5, 0.5, True)

    # Görev etiketi değişince girişleri de değişir
    await istemci.patch(f"{G}/{normal['id']}", json={"etiketler": ["revizyon"]}, headers=yonetici_basligi)
    s = (await istemci.get(f"{GM}/revizyon", headers=musteri_basligi(m))).json()
    assert s["kullanilan"] == 7.5
    await istemci.patch(f"{G}/{normal['id']}", json={"etiketler": []}, headers=yonetici_basligi)

    # Harcanan saat görevde toplam
    y = await istemci.get(f"{G}/proje/{proje.id}", headers=yonetici_basligi)
    assert next(g for g in y.json()["gorevler"] if g["id"] == rev["id"])["harcanan_saat"] == 8.5


async def test_revizyon_hakki_paketten_ve_asim_bildirimi_ayda_bir(istemci, yonetici_basligi, musteri_basligi, db_oturumu, bugun_eylul):
    from models.pricing import Pricing_inquiries, Pricing_scales

    m = _eposta("paket")
    if not (await db_oturumu.execute(select(Pricing_scales).where(Pricing_scales.kod == "BETA"))).scalars().first():
        db_oturumu.add(Pricing_scales(kod="BETA", sira=2, ad="Beta", alt_baslik="x", calisan_araligi="1-10", aciklama="x",
                                      baz_aylik_fiyat_usd=100, revizyon_saat="8s"))
    db_oturumu.add(Pricing_inquiries(scale_kod="BETA", hesaplanan_tutar=100, musteri_eposta=m, durum="kabul"))
    await db_oturumu.commit()
    proje = await _proje(db_oturumu, m, aylik_revizyon_saati=1)  # paket öncelikli
    rev = await _gorev(istemci, yonetici_basligi, proje.id, etiketler=["revizyon"])

    y = await istemci.post(f"{G}/{rev['id']}/saat", json={"saat": 6, "tarih": "2026-09-05"}, headers=yonetici_basligi)
    s = y.json()["revizyon"]
    assert (s["hak"], s["kaynak"], s["kullanilan"], s["asildi"]) == (8.0, "paket", 6.0, False)
    once = len(await _bildirimler(db_oturumu, "revizyon_asildi", "yonetici@test.dev"))
    y = await istemci.post(f"{G}/{rev['id']}/saat", json={"saat": 3, "tarih": "2026-09-06"}, headers=yonetici_basligi)
    s = y.json()["revizyon"]
    assert s["asildi"] is True and s["asim"] == 1.0
    await istemci.post(f"{G}/{rev['id']}/saat", json={"saat": 1, "tarih": "2026-09-07"}, headers=yonetici_basligi)
    sonra = await _bildirimler(db_oturumu, "revizyon_asildi", "yonetici@test.dev")
    assert len(sonra) == once + 1  # aynı ay ikinci kez bildirilmez
    assert m in sonra[-1].body


def test_revizyon_saati_cozumleme():
    from services.gorevler import revizyon_saati_coz

    assert revizyon_saati_coz("8s") == 8.0
    assert revizyon_saati_coz("16 saat") == 16.0
    assert revizyon_saati_coz("2,5h") == 2.5
    assert revizyon_saati_coz("Kullandıkça Öde") is None
    assert revizyon_saati_coz(None) is None


async def test_saat_krediden_dus_ve_modul_kapaliyken_engel(istemci, yonetici_basligi, musteri_basligi, db_oturumu, bugun_eylul):
    from models.credit_ledger import CreditLedger

    m = _eposta("kredi")
    proje = await _proje(db_oturumu, m)
    g = await _gorev(istemci, yonetici_basligi, proje.id, etiketler=["revizyon"])

    # Bakiye yok → 409, giriş de yazılmaz
    y = await istemci.post(f"{G}/{g['id']}/saat", json={"saat": 1, "krediden_dus": True}, headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "yetersiz_bakiye"
    assert (await istemci.get(f"{G}/{g['id']}/saat", headers=yonetici_basligi)).json()["girisler"] == []

    y = await istemci.post(f"{KREDI}/yukle", json={"eposta": m, "saat": 5, "tur": "hediye", "aciklama": "x"}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    y = await istemci.post(f"{G}/{g['id']}/saat", json={"saat": 2, "krediden_dus": True, "kredi_saat": 1.5, "aciklama": "logo"}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    assert y.json()["giris"]["kredi_saat"] == 1.5 and y.json()["kredi_bakiye"] == 3.5
    satir = (await db_oturumu.execute(select(CreditLedger).where(CreditLedger.musteri_eposta == m, CreditLedger.tur == "harcama"))).scalar_one()
    assert satir.miktar == -1.5 and satir.proje_id == proje.id
    # Krediden düşülen saat revizyon hakkından yemiyor
    s = (await istemci.get(f"{GM}/revizyon", headers=musteri_basligi(m))).json()
    assert (s["kullanilan"], s["krediden"]) == (2.0, 1.5)
    assert (await istemci.post(f"{G}/{g['id']}/saat", json={"saat": 1, "krediden_dus": True, "kredi_saat": 2}, headers=yonetici_basligi)).status_code == 400

    # Sonradan düşme + çift düşme engeli + krediden düşülmüş giriş silinemez
    y = await istemci.post(f"{G}/{g['id']}/saat", json={"saat": 1}, headers=yonetici_basligi)
    gid = y.json()["giris"]["id"]
    y = await istemci.post(f"{G}/saat/{gid}/kredi", json={}, headers=yonetici_basligi)
    assert y.status_code == 200 and y.json()["giris"]["kredi_saat"] == 1.0 and y.json()["kredi_bakiye"] == 2.5
    assert (await istemci.post(f"{G}/saat/{gid}/kredi", json={}, headers=yonetici_basligi)).status_code == 409
    assert (await istemci.delete(f"{G}/saat/{gid}", headers=yonetici_basligi)).status_code == 409
    y = await istemci.post(f"{G}/{g['id']}/saat", json={"saat": 0.5}, headers=yonetici_basligi)
    assert (await istemci.delete(f"{G}/saat/{y.json()['giris']['id']}", headers=yonetici_basligi)).status_code == 200

    # Kredi modülü kapalıysa krediden düşülemez
    y = await istemci.put(f"{MODUL}/musteri/{m}/krediler", json={"acik": False}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    y = await istemci.post(f"{G}/{g['id']}/saat", json={"saat": 1, "krediden_dus": True}, headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "kredi_modulu_kapali"


async def test_imzali_revizyon_istegi_revizyon_gorevi_acar(istemci, yonetici_basligi, musteri_basligi, db_oturumu, bugun_eylul):
    from routers.imzali_islemler import hiz_siniri

    hiz_siniri.temizle()
    m = _eposta("imza")
    proje = await _proje(db_oturumu, m, stage="review")
    y = await istemci.post("/api/v1/islem-yonetim/olustur", json={"tur": "teslimat_onay", "hedef_id": proje.id}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    jeton = y.json()["baglanti"].rsplit("/", 1)[-1]
    y = await istemci.post(f"/api/v1/islem/{jeton}", json={"sonuc": "revizyon", "not": "Başlık rengi koyu olsun"})
    assert y.status_code == 200, y.text
    gorevler = (await istemci.get(f"{GM}/proje/{proje.id}", headers=musteri_basligi(m))).json()["gorevler"]
    assert len(gorevler) == 1 and gorevler[0]["baslik"].startswith("Revizyon:")
    tam = (await istemci.get(f"{G}/proje/{proje.id}", headers=yonetici_basligi)).json()
    assert tam["gorevler"][0]["etiketler"] == ["revizyon"] and "koyu" in tam["gorevler"][0]["aciklama"]
    hiz_siniri.temizle()


# ---------------------------------------------------------------------------
# Modül bekçisi
# ---------------------------------------------------------------------------


async def test_gorevler_modulu_kapaliyken_musteri_403_yonetici_etkilenmez(istemci, yonetici_basligi, musteri_basligi, db_oturumu):
    m = _eposta("kapali")
    proje = await _proje(db_oturumu, m)
    y = await istemci.put(f"{MODUL}/musteri/{m}/gorevler", json={"acik": False}, headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    y = await istemci.get(f"{GM}/proje/{proje.id}", headers=musteri_basligi(m))
    assert y.status_code == 403 and y.json()["detail"] == {"kod": "modul_kapali", "modul": "gorevler"}
    assert (await istemci.get(f"{GM}/revizyon", headers=musteri_basligi(m))).status_code == 403
    assert (await istemci.get(f"{G}/proje/{proje.id}", headers=yonetici_basligi)).status_code == 200


def test_manifest_faz2b():
    from core import moduller as mf

    for anahtar in ("gorevler", "geri_bildirim", "duyurular", "oneri_kutusu"):
        m = mf.modul(anahtar)
        assert m and m.varsayilan_acik and m.bagimliliklar == ("projeler",) and m.musteri_sekmesi is None, anahtar
    assert mf.modul("oneri_kutusu").durum == "beta"
    assert mf.modul("geri_bildirim").yonetici_sekmesi == "geriBildirim"
    assert mf.modul("duyurular").yonetici_sekmesi == "duyurular"
    assert mf.manifest_hatalari() == []
