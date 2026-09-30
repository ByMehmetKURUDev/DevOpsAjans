"""Faz 2D — çöp kutusu: silinen kayıt yakalanıyor, geri alınıyor (aynı kimlik),
grup halinde geri alma, müşteri yalnız kendininkini görür/geri alır, kimlik
çakışması 409, teknik tablolar yakalanmaz, kanca hatası silmeyi bozmaz,
dosya içeriği bekletilir, saklama süresi dolunca temizlik.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

Y = "/api/v1/cop-kutusu"
M = "/api/v1/cop-kutum"
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _eposta(on: str = "cop") -> str:
    return f"{on}-{uuid.uuid4().hex[:10]}@test.dev"


async def _cop(db, tablo, kayit_id):
    from models.cop_kutusu import CopKutusu

    return list(
        (
            await db.execute(
                select(CopKutusu)
                .where(CopKutusu.tablo == tablo, CopKutusu.kayit_id == str(kayit_id))
                .execution_options(populate_existing=True)
            )
        ).scalars().all()
    )


async def _hazir_cevap(istemci, yonetici_basligi, baslik=None):
    y = await istemci.post(
        "/api/v1/destek/hazir-cevaplar",
        json={"baslik": baslik or f"Karşılama {uuid.uuid4().hex[:6]}", "metin": "Merhaba, talebinizi aldık."},
        headers=yonetici_basligi,
    )
    assert y.status_code == 200, y.text
    return y.json()


@pytest.fixture(autouse=True)
def nesne_deposu_yok(monkeypatch):
    for ad in ("S3_ENDPOINT_URL", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY", "S3_BUCKET", "S3_REGION"):
        monkeypatch.delenv(ad, raising=False)


# ---------------------------------------------------------------------------
# Yetki
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "yontem,yol",
    [("GET", Y), ("GET", f"{Y}/1"), ("POST", f"{Y}/1/geri-al"), ("DELETE", f"{Y}/1"), ("PUT", f"{Y}/ayar")],
)
async def test_yonetici_uclari_401_403(istemci, musteri_basligi, yontem, yol):
    govde = {"gun": 10} if yontem == "PUT" else None
    assert (await istemci.request(yontem, yol, json=govde)).status_code == 401
    assert (await istemci.request(yontem, yol, json=govde, headers=musteri_basligi())).status_code == 403


async def test_musteri_uclari_401(istemci):
    assert (await istemci.get(M)).status_code == 401
    assert (await istemci.post(f"{M}/1/geri-al")).status_code == 401


# ---------------------------------------------------------------------------
# Sil → listede → geri al → aynı kimlik
# ---------------------------------------------------------------------------
async def test_sil_listede_geri_al_ayni_id(istemci, yonetici_basligi, db_oturumu):
    from models.audit_log import AuditLog

    h = await _hazir_cevap(istemci, yonetici_basligi, "Çöp testi hazır cevap")
    assert (await istemci.delete(f"/api/v1/destek/hazir-cevaplar/{h['id']}", headers=yonetici_basligi)).status_code == 200

    satirlar = await _cop(db_oturumu, "hazir_cevaplar", h["id"])
    assert len(satirlar) == 1
    s = satirlar[0]
    assert s.silen_email == "yonetici@test.dev" and s.silen_rol == "admin"
    assert s.etiket == "Çöp testi hazır cevap"
    veri = json.loads(s.veri)
    assert veri["metin"] == "Merhaba, talebinizi aldık." and veri["id"] == h["id"]

    liste = (await istemci.get(Y, params={"tablo": "hazir_cevaplar", "q": "Çöp testi"}, headers=yonetici_basligi)).json()
    assert [i["id"] for i in liste["items"]] == [s.id]
    assert liste["saklama_gun"] == 30 and "hazir_cevaplar" in liste["tablolar"]
    ayrinti = (await istemci.get(f"{Y}/{s.id}", headers=yonetici_basligi)).json()
    assert ayrinti["veri"]["baslik"] == "Çöp testi hazır cevap"

    y = await istemci.post(f"{Y}/{s.id}/geri-al", headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    tum = (await istemci.get("/api/v1/destek/hazir-cevaplar", headers=yonetici_basligi)).json()
    geri = [x for x in tum if x["id"] == h["id"]]
    assert geri and geri[0]["baslik"] == "Çöp testi hazır cevap"

    # Listeden düştü; ikinci kez geri alma 409.
    liste = (await istemci.get(Y, params={"tablo": "hazir_cevaplar", "q": "Çöp testi"}, headers=yonetici_basligi)).json()
    assert liste["items"] == []
    y = await istemci.post(f"{Y}/{s.id}/geri-al", headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "zaten_geri_alindi"
    # Geri alma denetim kaydında.
    db_oturumu.expire_all()
    den = (
        await db_oturumu.execute(
            select(AuditLog).where(AuditLog.tablo == "hazir_cevaplar", AuditLog.kayit_id == str(h["id"]))
        )
    ).scalars().all()
    assert any("geri alındı" in (d.ozet or "") for d in den)
    assert {d.islem for d in den} >= {"sil", "olustur"}


async def test_genel_entity_silme_ucu_da_yakalaniyor(istemci, yonetici_basligi, db_oturumu):
    y = await istemci.post(
        "/api/v1/entities/invoices",
        json={"invoice_no": f"F-{uuid.uuid4().hex[:6]}", "client_email": "fatura@test.dev", "client_name": "F",
              "amount": 1250.5, "currency": "TRY", "status": "pending", "issue_date": "2026-09-01"},
        headers=yonetici_basligi,
    )
    assert y.status_code in (200, 201), y.text
    fatura = y.json()
    assert (await istemci.delete(f"/api/v1/entities/invoices/{fatura['id']}", headers=yonetici_basligi)).status_code == 200
    s = (await _cop(db_oturumu, "invoices", fatura["id"]))[0]
    assert s.sahip_email == "fatura@test.dev" and s.etiket == fatura["invoice_no"]
    assert (await istemci.post(f"{Y}/{s.id}/geri-al", headers=yonetici_basligi)).status_code == 200
    geri = (await istemci.get(f"/api/v1/entities/invoices/{fatura['id']}", headers=yonetici_basligi)).json()
    assert geri["amount"] == 1250.5 and geri["invoice_no"] == fatura["invoice_no"]


async def test_kimlik_cakismasi_409(istemci, yonetici_basligi, db_oturumu):
    from models.destek_sla import HazirCevaplar

    h = await _hazir_cevap(istemci, yonetici_basligi)
    assert (await istemci.delete(f"/api/v1/destek/hazir-cevaplar/{h['id']}", headers=yonetici_basligi)).status_code == 200
    s = (await _cop(db_oturumu, "hazir_cevaplar", h["id"]))[0]
    # Aynı kimlikle yeni bir kayıt (SQLite en büyük kimliği yeniden kullanabiliyor; burada açıkça).
    db_oturumu.add(HazirCevaplar(id=h["id"], baslik="Yerine gelen", metin="x"))
    await db_oturumu.commit()
    y = await istemci.post(f"{Y}/{s.id}/geri-al", headers=yonetici_basligi)
    assert y.status_code == 409 and y.json()["detail"]["kod"] == "cakisma"
    # Çöp kaydı yerinde duruyor.
    assert (await _cop(db_oturumu, "hazir_cevaplar", h["id"]))[0].geri_alindi is False


# ---------------------------------------------------------------------------
# Grup: görev + kontrol listesi + bağımlılık birlikte
# ---------------------------------------------------------------------------
async def test_grup_geri_alma_ebeveyn_cocuk(istemci, yonetici_basligi, db_oturumu):
    from models.projects import Projects
    from models.proje_gorevleri import ProjectTasks, TaskChecklist, TaskDependencies

    sahip = _eposta("grup")
    p = Projects(title="Grup projesi", description="x", category="Website", client_email=sahip, published=False)
    db_oturumu.add(p)
    await db_oturumu.flush()
    g = ProjectTasks(proje_id=p.id, baslik="Silinecek görev", durum="yapilacak", sira=1)
    diger = ProjectTasks(proje_id=p.id, baslik="Bağlı görev", durum="yapilacak", sira=2)
    db_oturumu.add_all([g, diger])
    await db_oturumu.flush()
    db_oturumu.add_all(
        [
            TaskChecklist(gorev_id=g.id, metin="Madde 1", sira=1),
            TaskChecklist(gorev_id=g.id, metin="Madde 2", sira=2),
            TaskDependencies(gorev_id=diger.id, bagli_oldugu_id=g.id),
        ]
    )
    await db_oturumu.commit()
    gorev_id, diger_id = g.id, diger.id

    assert (await istemci.delete(f"/api/v1/gorevler/{gorev_id}", headers=yonetici_basligi)).status_code == 200
    ana = (await _cop(db_oturumu, "project_tasks", gorev_id))[0]
    assert ana.sahip_email == sahip
    from models.cop_kutusu import CopKutusu

    grup = (await db_oturumu.execute(select(CopKutusu).where(CopKutusu.grup == ana.grup))).scalars().all()
    assert sorted(x.tablo for x in grup) == ["project_tasks", "task_checklist", "task_checklist", "task_dependencies"]

    # Listede yalnız ana satır; bağlı sayısı 3.
    liste = (await istemci.get(Y, params={"q": "Silinecek görev"}, headers=yonetici_basligi)).json()
    assert [i["tablo"] for i in liste["items"]] == ["project_tasks"] and liste["items"][0]["bagli_sayisi"] == 3

    y = await istemci.post(f"{Y}/{ana.id}/geri-al", headers=yonetici_basligi)
    assert y.status_code == 200, y.text
    assert [x["tablo"] for x in y.json()["geri_alinan"]][0] == "project_tasks"
    db_oturumu.expire_all()
    assert (await db_oturumu.execute(select(ProjectTasks).where(ProjectTasks.id == gorev_id))).scalar_one().baslik == "Silinecek görev"
    maddeler = (await db_oturumu.execute(select(TaskChecklist).where(TaskChecklist.gorev_id == gorev_id))).scalars().all()
    assert sorted(m.metin for m in maddeler) == ["Madde 1", "Madde 2"]
    bag = (await db_oturumu.execute(select(TaskDependencies).where(TaskDependencies.gorev_id == diger_id))).scalars().all()
    assert [b.bagli_oldugu_id for b in bag] == [gorev_id]


async def test_tek_kontrol_maddesi_silinmesi_cope_dusmez(istemci, yonetici_basligi, db_oturumu):
    from models.projects import Projects
    from models.proje_gorevleri import ProjectTasks, TaskChecklist

    p = Projects(title="Tek madde", description="x", category="Website", client_email=_eposta(), published=False)
    db_oturumu.add(p)
    await db_oturumu.flush()
    g = ProjectTasks(proje_id=p.id, baslik="Görev", durum="yapilacak", sira=1)
    db_oturumu.add(g)
    await db_oturumu.flush()
    k = TaskChecklist(gorev_id=g.id, metin="Tek", sira=1)
    db_oturumu.add(k)
    await db_oturumu.commit()
    assert (await istemci.delete(f"/api/v1/gorevler/kontrol/{k.id}", headers=yonetici_basligi)).status_code == 200
    assert await _cop(db_oturumu, "task_checklist", k.id) == []


# ---------------------------------------------------------------------------
# Müşteri: yalnız kendi sildiği kendi kaydı
# ---------------------------------------------------------------------------
async def _musteri_siler(db, eposta, nesne, *, aktor=None):
    """Müşteri bağlamında (aktör = müşteri) ORM ile siler."""
    from services import denetim

    token = denetim._BAGLAM.set(None)
    try:
        denetim.aktor_ata(aktor or eposta, "client")
        await db.delete(nesne)
        await db.commit()
    finally:
        denetim._BAGLAM.reset(token)


async def test_musteri_yalniz_kendininkini_gorur_ve_geri_alir(istemci, musteri_basligi, yonetici_basligi, db_oturumu):
    from models.support_tickets import Support_tickets

    a, b = _eposta("ma"), _eposta("mb")
    ta = Support_tickets(client_name="A", client_email=a, subject="A'nın talebi", message="m", status="open")
    tb = Support_tickets(client_name="B", client_email=b, subject="B'nin talebi", message="m", status="open")
    tc = Support_tickets(client_name="A", client_email=a, subject="Yöneticinin sildiği", message="m", status="open")
    db_oturumu.add_all([ta, tb, tc])
    await db_oturumu.commit()
    ta_id, tb_id, tc_id = ta.id, tb.id, tc.id
    await _musteri_siler(db_oturumu, a, ta)
    await _musteri_siler(db_oturumu, b, tb)
    await _musteri_siler(db_oturumu, a, tc, aktor="yonetici@test.dev")  # silen başkası

    la = (await istemci.get(M, headers=musteri_basligi(a))).json()
    assert [i["kayit_id"] for i in la["items"]] == [str(ta_id)]
    assert la["items"][0]["silen_email"] is None and la["items"][0]["sahip_email"] is None
    cop_b = (await _cop(db_oturumu, "support_tickets", tb_id))[0]
    cop_c = (await _cop(db_oturumu, "support_tickets", tc_id))[0]
    # Başkasının kaydı ve başkasının sildiği kendi kaydı: 404.
    assert (await istemci.post(f"{M}/{cop_b.id}/geri-al", headers=musteri_basligi(a))).status_code == 404
    assert (await istemci.post(f"{M}/{cop_c.id}/geri-al", headers=musteri_basligi(a))).status_code == 404
    # Müşteri kalıcı silemez (yönetici ucu 403).
    assert (await istemci.delete(f"{Y}/{cop_b.id}", headers=musteri_basligi(b))).status_code == 403

    cop_a = (await _cop(db_oturumu, "support_tickets", ta_id))[0]
    y = await istemci.post(f"{M}/{cop_a.id}/geri-al", headers=musteri_basligi(a))
    assert y.status_code == 200, y.text
    db_oturumu.expire_all()
    assert (await db_oturumu.execute(select(Support_tickets).where(Support_tickets.id == ta_id))).scalar_one().subject == "A'nın talebi"
    assert (await istemci.get(M, headers=musteri_basligi(a))).json()["items"] == []


# ---------------------------------------------------------------------------
# Kapsam, hata dayanıklılığı
# ---------------------------------------------------------------------------
async def test_teknik_tablolar_yakalanmaz(db_oturumu):
    from models.auth import OIDCState
    from models.cop_kutusu import CopKutusu
    from models.oturumlar import Oturumlar

    o = Oturumlar(sid=uuid.uuid4().hex, email=_eposta())
    s = OIDCState(state=uuid.uuid4().hex, nonce="n", code_verifier="v",
                  expires_at=datetime.now(timezone.utc) + timedelta(minutes=5))
    db_oturumu.add_all([o, s])
    await db_oturumu.commit()
    once = (await db_oturumu.execute(select(CopKutusu.id))).all()
    await db_oturumu.delete(o)
    await db_oturumu.delete(s)
    await db_oturumu.commit()
    assert (await db_oturumu.execute(select(CopKutusu.id))).all() == once


async def test_kanca_hatasi_silmeyi_bozmaz(istemci, yonetici_basligi, db_oturumu, monkeypatch):
    from models.destek_sla import HazirCevaplar
    from services import cop_kutusu

    def patla():
        raise RuntimeError("yazılamadı")

    monkeypatch.setattr(cop_kutusu, "_ekleme_sorgusu", patla)
    h = await _hazir_cevap(istemci, yonetici_basligi)
    assert (await istemci.delete(f"/api/v1/destek/hazir-cevaplar/{h['id']}", headers=yonetici_basligi)).status_code == 200
    db_oturumu.expire_all()
    assert (await db_oturumu.execute(select(HazirCevaplar).where(HazirCevaplar.id == h["id"]))).scalar_one_or_none() is None
    assert await _cop(db_oturumu, "hazir_cevaplar", h["id"]) == []


# ---------------------------------------------------------------------------
# Dosyalar: içerik bekletilir, geri alınınca indirilebilir; kalıcı silmede gider
# ---------------------------------------------------------------------------
async def test_dosya_icerigi_bekletilir_ve_kalici_silmede_gider(istemci, yonetici_basligi, db_oturumu):
    from models.dosyalar import DosyaIcerikleri, Dosyalar

    eposta = _eposta("dosya")
    y = await istemci.post(
        "/api/v1/dosyalar/yukle",
        data={"client_email": eposta, "klasor": "Genel"},
        files={"dosya": ("teklif.pdf", PDF, "application/octet-stream")},
        headers=yonetici_basligi,
    )
    assert y.status_code == 200, y.text
    d = y.json()
    anahtar = (await db_oturumu.execute(select(Dosyalar.depolama_anahtari).where(Dosyalar.id == d["id"]))).scalar_one()
    assert (await istemci.delete(f"/api/v1/dosyalar/{d['id']}", headers=yonetici_basligi)).status_code == 200

    async def icerik_var():
        return (await db_oturumu.execute(select(DosyaIcerikleri.id).where(DosyaIcerikleri.anahtar == anahtar))).first() is not None

    assert await icerik_var()  # çöpte: içerik duruyor
    s = (await _cop(db_oturumu, "files", d["id"]))[0]
    assert s.sahip_email == eposta and s.etiket == "teklif.pdf"
    assert "veri" not in json.loads(s.veri)  # ikili içerik yok
    assert (await istemci.post(f"{Y}/{s.id}/geri-al", headers=yonetici_basligi)).status_code == 200
    indir = await istemci.post(f"/api/v1/dosyalar/{d['id']}/indirme-baglantisi", headers=yonetici_basligi)
    assert indir.status_code == 200
    adres = indir.json().get("adres") or indir.json().get("url")
    if adres:
        yol = adres.split("://", 1)[-1].split("/", 1)[-1]
        icerik = await istemci.get("/" + yol)
        assert icerik.status_code == 200 and icerik.content == PDF

    # Tekrar sil → kalıcı sil → içerik de gidiyor.
    assert (await istemci.delete(f"/api/v1/dosyalar/{d['id']}", headers=yonetici_basligi)).status_code == 200
    s2 = [x for x in await _cop(db_oturumu, "files", d["id"]) if not x.geri_alindi][0]
    assert await icerik_var()
    assert (await istemci.delete(f"{Y}/{s2.id}", headers=yonetici_basligi)).status_code == 200
    assert not await icerik_var()
    assert [x for x in await _cop(db_oturumu, "files", d["id"]) if not x.geri_alindi] == []


# ---------------------------------------------------------------------------
# Saklama
# ---------------------------------------------------------------------------
async def test_sure_dolunca_temizlik_ve_ayar(istemci, yonetici_basligi, db_oturumu):
    from models.cop_kutusu import CopKutusu
    from services import cop_kutusu, zamanli

    assert "cop_kutusu_temizligi" in zamanli.GOREV_ADLARI
    eski = CopKutusu(tablo="blog_posts", kayit_id="990001", veri="{}", grup=str(uuid.uuid4()),
                     silinme=datetime.now(timezone.utc) - timedelta(days=31))
    yeni = CopKutusu(tablo="blog_posts", kayit_id="990002", veri="{}", grup=str(uuid.uuid4()),
                     silinme=datetime.now(timezone.utc) - timedelta(days=5))
    db_oturumu.add_all([eski, yeni])
    await db_oturumu.commit()
    sonuc = await cop_kutusu.suresi_dolanlari_temizle(db_oturumu)
    assert sonuc["gun"] == 30 and sonuc["silinen"] >= 1
    assert await _cop(db_oturumu, "blog_posts", "990001") == []
    assert len(await _cop(db_oturumu, "blog_posts", "990002")) == 1

    # Ayar 3 güne inince 5 günlük kayıt da gidiyor.
    assert (await istemci.put(f"{Y}/ayar", json={"gun": 3}, headers=yonetici_basligi)).json() == {"saklama_gun": 3}
    try:
        assert (await istemci.put(f"{Y}/ayar", json={"gun": 0}, headers=yonetici_basligi)).status_code == 422
        await cop_kutusu.suresi_dolanlari_temizle(db_oturumu)
        assert await _cop(db_oturumu, "blog_posts", "990002") == []
    finally:
        await istemci.put(f"{Y}/ayar", json={"gun": 30}, headers=yonetici_basligi)
