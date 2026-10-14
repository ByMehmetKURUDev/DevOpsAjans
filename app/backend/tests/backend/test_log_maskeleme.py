"""Parti 14: erişim kaydı maskeleme ve 4xx için traceback yazılmaması."""

import logging

import pytest
from fastapi import HTTPException

from core import database
from core.log_maskeleme import ErisimKaydiMaskesi, erisim_kaydini_maskele, sorguyu_maskele


def test_oauth_kodu_ve_state_maskelenir():
    yol = "/api/v1/baglantilar/meta/geri-donus?code=AQBx-gizli&state=abc.def"
    assert sorguyu_maskele(yol) == "/api/v1/baglantilar/meta/geri-donus?code=***&state=***"


def test_zararsiz_parametreler_ve_yol_aynen_kalir():
    assert sorguyu_maskele("/api/v1/blog?sayfa=2&dil=tr") == "/api/v1/blog?sayfa=2&dil=tr"
    assert sorguyu_maskele("/health") == "/health"
    # Ad büyük/küçük harf duyarsız; boş değer ve değersiz bayrak bozulmaz.
    assert sorguyu_maskele("/x?Token=abc&code=&bayrak") == "/x?Token=***&code=&bayrak"


def test_filtre_uvicorn_kaydinin_yol_argumanini_degistirir():
    kayit = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("1.2.3.4:0", "GET", "/api/v1/x?code=gizli&a=1", "1.1", 302),
        None,
    )
    assert ErisimKaydiMaskesi().filter(kayit) is True
    mesaj = kayit.getMessage()
    assert "gizli" not in mesaj
    assert "/api/v1/x?code=***&a=1" in mesaj


def test_filtre_beklenmeyen_bicimde_kayda_dokunmaz():
    kayit = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, "düz mesaj", None, None)
    assert ErisimKaydiMaskesi().filter(kayit) is True
    assert kayit.getMessage() == "düz mesaj"


def test_filtre_bir_kez_takilir():
    erisim_kaydini_maskele()
    erisim_kaydini_maskele()
    sayi = sum(isinstance(f, ErisimKaydiMaskesi) for f in logging.getLogger("uvicorn.access").filters)
    assert sayi == 1


def test_istemci_hatasi_ayrimi():
    assert database._istemci_hatasi_mi(HTTPException(status_code=401, detail={"kod": "oturum_gerekli"}))
    assert database._istemci_hatasi_mi(HTTPException(status_code=404))
    assert not database._istemci_hatasi_mi(HTTPException(status_code=500))
    assert not database._istemci_hatasi_mi(RuntimeError("veritabanı koptu"))


class _SahteOturum:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


async def test_get_db_401_icin_traceback_yazmaz(monkeypatch, caplog):
    monkeypatch.setattr(database.db_manager, "async_session_maker", lambda: _SahteOturum())
    caplog.set_level(logging.DEBUG, logger="core.database")
    uretec = database.get_db()
    await uretec.__anext__()
    with pytest.raises(HTTPException):
        await uretec.athrow(HTTPException(status_code=401, detail={"kod": "oturum_gerekli"}))
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


async def test_get_db_gercek_hatayi_yine_yazar(monkeypatch, caplog):
    monkeypatch.setattr(database.db_manager, "async_session_maker", lambda: _SahteOturum())
    caplog.set_level(logging.DEBUG, logger="core.database")
    uretec = database.get_db()
    await uretec.__anext__()
    with pytest.raises(RuntimeError):
        await uretec.athrow(RuntimeError("beklenmeyen"))
    hatalar = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert hatalar and hatalar[0].exc_info
