"""Duman testi: test altyapısı ayağa kalkıyor mu?"""


async def test_saglik_ucu(istemci):
    yanit = await istemci.get("/health")
    assert yanit.status_code == 200
    assert yanit.json() == {"status": "healthy"}


async def test_veritabani_saglik_ucu(istemci):
    yanit = await istemci.get("/database/health")
    assert yanit.status_code == 200
    assert yanit.json()["status"] == "healthy"


async def test_jeton_cozuluyor(istemci, yonetici_basligi, musteri_basligi):
    # Yönetici ucu: jetonsuz 403, müşteriyle 403, yöneticiyle 200.
    assert (await istemci.get("/api/v1/site-analizi/yonetim")).status_code == 403
    yanit = await istemci.get("/api/v1/site-analizi/yonetim", headers=musteri_basligi("a@test.dev"))
    assert yanit.status_code == 403
    yanit = await istemci.get("/api/v1/site-analizi/yonetim", headers=yonetici_basligi)
    assert yanit.status_code == 200
