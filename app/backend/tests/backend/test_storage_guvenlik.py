"""Faz 2H (A) — `/api/v1/storage/*` uçları yalnız yöneticiye açık + yol geçişi reddi.

Önceden giriş yapmış her kullanıcı başkasının nesnesini listeleyip
silebiliyor, indirme bağlantısı alabiliyordu. Ön yüz ve SDK kullanımı
taranınca müşteri akışı çıkmadı → hepsi yönetici. Nesne deposu (OSS) servisi
burada sahte: ağa çıkılmıyor.
"""

import pytest

from conftest import jeton_uret

UC = "/api/v1/storage"


class SahteDepo:
    cagrilar: list = []

    def __init__(self):
        pass

    async def create_bucket(self, istek):
        from schemas.storage import BucketResponse

        SahteDepo.cagrilar.append(("create_bucket", istek.bucket_name))
        return BucketResponse(bucket_name=istek.bucket_name, created_at="2026-10-01")

    async def list_buckets(self):
        from schemas.storage import BucketListResponse

        SahteDepo.cagrilar.append(("list_buckets", None))
        return BucketListResponse()

    async def list_objects(self, istek):
        from schemas.storage import ObjectInfo, ObjectListResponse

        SahteDepo.cagrilar.append(("list_objects", istek.bucket_name))
        return ObjectListResponse(objects=[ObjectInfo(bucket_name=istek.bucket_name, object_key="musteri/x/a.pdf")])

    async def get_object_info(self, istek):
        from schemas.storage import ObjectInfo

        SahteDepo.cagrilar.append(("get_object_info", istek.object_key))
        return ObjectInfo(bucket_name=istek.bucket_name, object_key=istek.object_key)

    async def rename_object(self, istek):
        from schemas.storage import RenameResponse

        SahteDepo.cagrilar.append(("rename_object", istek.target_key))
        return RenameResponse(success=True)

    async def delete_object(self, istek):
        from schemas.storage import DeleteResponse

        SahteDepo.cagrilar.append(("delete_object", istek.object_key))
        return DeleteResponse(success=True)

    async def create_upload_url(self, istek):
        from schemas.storage import FileUpDownResponse

        SahteDepo.cagrilar.append(("upload", istek.object_key))
        return FileUpDownResponse(upload_url="https://oss.example/u", expires_at="2026-10-01T00:00:00Z")

    async def create_download_url(self, istek):
        from schemas.storage import FileUpDownResponse

        SahteDepo.cagrilar.append(("download", istek.object_key))
        return FileUpDownResponse(download_url="https://oss.example/d", expires_at="2026-10-01T00:00:00Z")


@pytest.fixture(autouse=True)
def depo(monkeypatch):
    from routers import storage

    SahteDepo.cagrilar = []
    monkeypatch.setattr(storage, "StorageService", SahteDepo)
    return SahteDepo


KOVA = "musteri-dosyalari"
ANAHTAR = "musteri/abc123/fatura.pdf"
#: (metot, yol, sorgu, gövde)
UCLAR = [
    ("POST", "/create-bucket", None, {"bucket_name": KOVA}),
    ("GET", "/list-buckets", None, None),
    ("GET", "/list-objects", {"bucket_name": KOVA}, None),
    ("GET", "/get-object-info", {"bucket_name": KOVA, "object_key": ANAHTAR}, None),
    ("POST", "/rename-object", None, {"bucket_name": KOVA, "source_key": ANAHTAR, "target_key": "musteri/abc123/yeni.pdf"}),
    ("DELETE", "/delete-object", None, {"bucket_name": KOVA, "object_key": ANAHTAR}),
    ("POST", "/upload-url", None, {"bucket_name": KOVA, "object_key": ANAHTAR}),
    ("POST", "/download-url", None, {"bucket_name": KOVA, "object_key": ANAHTAR}),
]


async def _cagir(istemci, metot, yol, sorgu, govde, basliklar=None):
    return await istemci.request(metot, UC + yol, params=sorgu, json=govde, headers=basliklar or {})


@pytest.mark.parametrize("metot,yol,sorgu,govde", UCLAR, ids=[u[1] for u in UCLAR])
async def test_musteri_hicbir_storage_ucunu_kullanamaz(istemci, depo, metot, yol, sorgu, govde):
    musteri = {"Authorization": f"Bearer {jeton_uret('storage-musteri@test.dev')}"}
    y = await _cagir(istemci, metot, yol, sorgu, govde, musteri)
    assert y.status_code == 403, (yol, y.status_code, y.text)
    assert (await _cagir(istemci, metot, yol, sorgu, govde)).status_code == 401
    assert depo.cagrilar == []  # servis hiç çağrılmadı


@pytest.mark.parametrize("metot,yol,sorgu,govde", UCLAR, ids=[u[1] for u in UCLAR])
async def test_yonetici_storage_uclarini_kullanir(istemci, yonetici_basligi, depo, metot, yol, sorgu, govde):
    y = await _cagir(istemci, metot, yol, sorgu, govde, yonetici_basligi)
    assert y.status_code == 200, (yol, y.status_code, y.text)
    assert len(depo.cagrilar) == 1


GECIS = ["../baska-musteri/fatura.pdf", "musteri/../../etc/passwd", "/etc/passwd", "musteri\\..\\x", "C:/Windows/x", "a/\x00b", ".."]


@pytest.mark.parametrize("kotu", GECIS)
async def test_yol_gecisi_400(istemci, yonetici_basligi, depo, kotu):
    for metot, yol, sorgu, govde in (
        ("GET", "/get-object-info", {"bucket_name": KOVA, "object_key": kotu}, None),
        ("DELETE", "/delete-object", None, {"bucket_name": KOVA, "object_key": kotu}),
        ("POST", "/upload-url", None, {"bucket_name": KOVA, "object_key": kotu}),
        ("POST", "/download-url", None, {"bucket_name": KOVA, "object_key": kotu}),
        ("POST", "/rename-object", None, {"bucket_name": KOVA, "source_key": ANAHTAR, "target_key": kotu}),
        ("POST", "/rename-object", None, {"bucket_name": KOVA, "source_key": kotu, "target_key": ANAHTAR}),
    ):
        y = await _cagir(istemci, metot, yol, sorgu, govde, yonetici_basligi)
        assert y.status_code == 400, (yol, repr(kotu), y.status_code, y.text)
        assert y.json()["detail"]["kod"] == "gecersiz_anahtar"
    assert depo.cagrilar == []


def test_anahtar_denetimi():
    from routers.storage import anahtar_gecersiz_mi

    for iyi in ("musteri/abc/fatura.pdf", "poses/棚拍侧面.jpg", "a..b.txt", "klasor/..gizli", "", None):
        assert anahtar_gecersiz_mi(iyi) is False, iyi
    for kotu in GECIS:
        assert anahtar_gecersiz_mi(kotu) is True, kotu
