"""Tests que protegen contra valores inválidos de estado/modo_atencion.

El bug original: al cerrar/cotizar/descartar una solicitud se enviaba
modo_atencion="CERRADO", pero la BD (Supabase) solo admite BOT/ADMIN en la
columna attention_mode. El CHECK constraint rechazaba TODA la actualización con
un error 400 -> RuntimeError -> update() devolvía False -> la solicitud se
quedaba en su estado anterior (p. ej. pendiente/ABIERTA).

Estos tests capturan los payloads que el código manda a hiring_repo.update y
verifican que modo_atencion siempre sea un valor permitido por la BD.
"""

import pytest
from unittest.mock import patch
from app.services import admin_service
from app.repositories import hiring_request_repository as hiring_repo

# Valores válidos según el CHECK constraint hiring_requests_attention_mode_chk.
VALID_ATTENTION_MODES = {"BOT", "ADMIN"}
# Valores válidos según hiring_requests_status_chk.
VALID_STATUSES = {
    "ABIERTA", "EN_SEGUIMIENTO", "TOMADA_POR_ADMIN", "EN_CONVERSACION",
    "COTIZADA", "CERRADA", "DESCARTADA",
}


def _assert_payload_valid(payload: dict):
    """Verifica que un payload de update no viole los CHECK constraints."""
    if "modo_atencion" in payload:
        assert payload["modo_atencion"] in VALID_ATTENTION_MODES, (
            f"modo_atencion='{payload['modo_atencion']}' no es válido. "
            f"La BD solo admite {VALID_ATTENTION_MODES}."
        )
    if "estado" in payload:
        assert payload["estado"] in VALID_STATUSES, (
            f"estado='{payload['estado']}' no es válido. "
            f"La BD solo admite {VALID_STATUSES}."
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("action,expected_state", [
    ("close", hiring_repo.ESTADO_CERRADA),
    ("quote", hiring_repo.ESTADO_COTIZADA),
    ("discard", hiring_repo.ESTADO_DESCARTADA),
])
async def test_apply_state_by_code_uses_valid_attention_mode(action, expected_state):
    """apply_state_by_code no debe mandar modo_atencion inválido al cerrar."""
    code = "SOL-0001"
    sol = {
        "codigo_solicitud": code,
        "estado": hiring_repo.ESTADO_EN_CONVERSACION,
        "numero_cliente": "51999888777",
        "nombre_o_dni": "Cliente Test",
        "observaciones": "",
    }
    captured = {}

    def fake_update(c, updates):
        captured["payload"] = updates
        return True

    with patch.object(admin_service.hiring_repo, "get_by_code", return_value=sol):
        with patch.object(admin_service.hiring_repo, "update", side_effect=fake_update):
            with patch.object(admin_service.conv_repo, "set_state"):
                with patch.object(admin_service, "_send_admin"):
                    result = await admin_service.apply_state_by_code(
                        "51900000000", action, code
                    )

    assert captured.get("payload"), "no se llamó a hiring_repo.update"
    _assert_payload_valid(captured["payload"])
    assert captured["payload"]["estado"] == expected_state
    assert result is not None


@pytest.mark.asyncio
async def test_close_current_request_uses_valid_attention_mode():
    """close_current_request no debe mandar modo_atencion inválido."""
    code = "SOL-0002"
    client = "51999888777"
    sol = {
        "codigo_solicitud": code,
        "estado": hiring_repo.ESTADO_EN_CONVERSACION,
        "numero_cliente": client,
        "nombre_o_dni": "Cliente Test",
        "admin_asignado": "51900000000",
        "observaciones": "",
    }
    captured = {}

    def fake_update(c, updates):
        captured["payload"] = updates
        return True

    with patch.object(admin_service, "controlling_client_of", return_value=client):
        with patch.object(admin_service.hiring_repo, "get_active_by_client", return_value=sol):
            with patch.object(admin_service.hiring_repo, "get_by_client", return_value=sol):
                with patch.object(admin_service.hiring_repo, "update", side_effect=fake_update):
                    with patch.object(admin_service.conv_repo, "set_state"):
                        with patch.object(admin_service, "_send_admin"):
                            result = await admin_service.close_current_request(
                                "51900000000", hiring_repo.ESTADO_CERRADA
                            )

    assert captured.get("payload"), "no se llamó a hiring_repo.update"
    _assert_payload_valid(captured["payload"])
    assert result is not None


def test_no_invalid_attention_mode_literals_in_source():
    """Salvaguarda estática: no debe quedar modo_atencion='CERRADO' en el código."""
    import pathlib
    src = pathlib.Path(admin_service.__file__).read_text(encoding="utf-8")
    assert '"modo_atencion": "CERRADO"' not in src, (
        "Se encontró modo_atencion='CERRADO', valor que la BD rechaza."
    )
    assert "'modo_atencion': 'CERRADO'" not in src
