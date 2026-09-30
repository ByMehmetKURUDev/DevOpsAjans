"""Gizli site ayarları (webhook jetonu, yönetici adresleri) herkese açık okumada görünmemeli."""

from routers.site_settings import gizli_ayar_mi


def test_desen():
    for k in ["shopier_webhook_token", "admin_emails", "notify_admin_phone", "lemon_api_key", "smtp_password"]:
        assert gizli_ayar_mi(k), k
    for k in ["site_gorunum", "hero_title", "contact_email", "contact_phone", "seo_title_tr"]:
        assert not gizli_ayar_mi(k), k


async def test_ziyaretci_ve_musteri_gizliyi_goremez(istemci, yonetici_basligi, musteri_basligi):
    for anahtar, deger in [("deneme_webhook_token", "cok-gizli"), ("deneme_api_key", "baska-gizli"), ("deneme_acik_baslik", "Merhaba")]:
        r = await istemci.post(
            "/api/v1/entities/site_settings",
            json={"setting_key": anahtar, "setting_value": deger, "group_name": "t"},
            headers=yonetici_basligi,
        )
        assert r.status_code == 201, r.text
    gizli_id = None
    for baslik in ({}, musteri_basligi("m@x.dev")):
        for yol in ("/api/v1/entities/site_settings?limit=500", "/api/v1/entities/site_settings/all?limit=500"):
            r = await istemci.get(yol, headers=baslik)
            assert r.status_code == 200
            govde = r.text
            assert "cok-gizli" not in govde and "baska-gizli" not in govde and "deneme_webhook_token" not in govde
            assert "deneme_acik_baslik" in govde
    r = await istemci.get("/api/v1/entities/site_settings/all?limit=500", headers=yonetici_basligi)
    ogeler = r.json()["items"]
    assert any(o["setting_key"] == "deneme_webhook_token" for o in ogeler)
    gizli_id = next(o["id"] for o in ogeler if o["setting_key"] == "deneme_webhook_token")
    assert (await istemci.get(f"/api/v1/entities/site_settings/{gizli_id}")).status_code == 404
    assert (await istemci.get(f"/api/v1/entities/site_settings/{gizli_id}", headers=yonetici_basligi)).status_code == 200
    for o in ogeler:
        if o["setting_key"].startswith("deneme_"):
            await istemci.delete(f"/api/v1/entities/site_settings/{o['id']}", headers=yonetici_basligi)
