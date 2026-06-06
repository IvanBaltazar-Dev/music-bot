"""Test que valida retorno de actualizaciones en admin service.

Verifica que cuando una actualización a Supabase falla, no se cambie el estado
de conversación y se notifique al admin.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services import admin_service
from app.repositories import conversation_repository as conv_repo
from app.repositories import hiring_request_repository as hiring_repo


@pytest.mark.asyncio
async def test_apply_state_by_code_validates_update():
    """Verifica que apply_state_by_code valide el retorno de update()."""
    admin_number = "5519999999999"
    code = "SOL-0001"

    # Mock de una solicitud existente
    sol = {
        "codigo_solicitud": code,
        "estado": hiring_repo.ESTADO_EN_CONVERSACION,
        "numero_cliente": "5511888888888",
        "observaciones": "test",
    }

    with patch('app.services.admin_service.hiring_repo.get_by_code', return_value=sol):
        with patch('app.services.admin_service.hiring_repo.update', return_value=False) as mock_update:
            with patch('app.services.admin_service._send_admin') as mock_send_admin:
                result = await admin_service.apply_state_by_code(admin_number, "close", code)

                # Debe retornar None (no tuvo éxito)
                assert result is None

                # Debe notificar al admin del error
                mock_send_admin.assert_called_once()
                call_args = mock_send_admin.call_args[0]
                assert "⚠️" in call_args[1]  # Debe tener advertencia
                assert "no se pudo guardar" in call_args[1].lower()

    # Verificar que se llamó a update
    assert mock_update.called


@pytest.mark.asyncio
async def test_apply_state_by_code_succeeds_with_valid_update():
    """Verifica que apply_state_by_code funcione cuando update() es exitoso."""
    admin_number = "5519999999999"
    code = "SOL-0001"

    sol = {
        "codigo_solicitud": code,
        "estado": hiring_repo.ESTADO_EN_CONVERSACION,
        "numero_cliente": "5511888888888",
        "nombre_o_dni": "Test Client",
        "observaciones": "test",
    }

    # get_by_code se llama dos veces: lectura inicial y re-lectura de verificación.
    closed = {**sol, "estado": hiring_repo.ESTADO_CERRADA}
    with patch('app.services.admin_service.hiring_repo.get_by_code', side_effect=[sol, closed]):
        with patch('app.services.admin_service.hiring_repo.update', return_value=True):
            with patch('app.services.admin_service.conv_repo.set_state'):
                with patch('app.services.admin_service._send_admin') as mock_send_admin:
                    result = await admin_service.apply_state_by_code(admin_number, "close", code)

                    # Debe retornar dict con resultado
                    assert result is not None
                    assert result["codigo_solicitud"] == code
                    assert result["estado"] == hiring_repo.ESTADO_CERRADA

                    # Debe notificar el éxito (verificable con call count)
                    assert mock_send_admin.called


@pytest.mark.asyncio
async def test_apply_state_by_code_rejects_when_not_persisted():
    """Si update() devuelve True pero la re-lectura muestra que el estado NO
    persistió, NO debe responder '✅ cerrada' ni retornar éxito."""
    admin_number = "5519999999999"
    code = "SOL-0001"
    sol = {
        "codigo_solicitud": code,
        "estado": hiring_repo.ESTADO_EN_CONVERSACION,
        "numero_cliente": "5511888888888",
        "nombre_o_dni": "Test Client",
        "observaciones": "test",
    }
    # La re-lectura devuelve la solicitud TODAVÍA pendiente (no persistió).
    still_open = {**sol, "estado": hiring_repo.ESTADO_ABIERTA}

    with patch('app.services.admin_service.hiring_repo.get_by_code', side_effect=[sol, still_open]):
        with patch('app.services.admin_service.hiring_repo.update', return_value=True):
            with patch('app.services.admin_service.conv_repo.set_state'):
                with patch('app.services.admin_service._send_admin') as mock_send_admin:
                    result = await admin_service.apply_state_by_code(admin_number, "close", code)

    assert result is None
    # Debe avisar que no pudo confirmar (no un falso "✅ cerrada").
    mensaje = mock_send_admin.call_args[0][1]
    assert "⚠️" in mensaje
    assert "✅" not in mensaje


@pytest.mark.asyncio
async def test_close_current_request_validates_update():
    """Verifica que close_current_request valide el retorno de update()."""
    admin_number = "5519999999999"
    client_number = "5511888888888"

    sol = {
        "codigo_solicitud": "SOL-0001",
        "estado": hiring_repo.ESTADO_EN_CONVERSACION,
        "numero_cliente": client_number,
        "nombre_o_dni": "Test Client",
        "observaciones": "test",
    }

    with patch('app.services.admin_service.controlling_client_of', return_value=client_number):
        with patch('app.services.admin_service.hiring_repo.get_active_by_client', return_value=sol):
            with patch('app.services.admin_service.hiring_repo.get_by_client', return_value=sol):
                with patch('app.services.admin_service.hiring_repo.update', return_value=False) as mock_update:
                    with patch('app.services.admin_service._send_admin') as mock_send_admin:
                        result = await admin_service.close_current_request(admin_number, hiring_repo.ESTADO_CERRADA)

                        # Debe retornar None (no tuvo éxito)
                        assert result is None

                        # Debe notificar al admin del error
                        mock_send_admin.assert_called_once()
                        call_args = mock_send_admin.call_args[0]
                        assert "⚠️" in call_args[1]


@pytest.mark.asyncio
async def test_set_pending_by_code_validates_update():
    """Verifica que set_pending_by_code valide el retorno de update()."""
    admin_number = "5519999999999"
    code = "SOL-0001"

    sol = {
        "codigo_solicitud": code,
        "estado": hiring_repo.ESTADO_EN_CONVERSACION,
        "numero_cliente": "5511888888888",
        "observaciones": "test",
    }

    with patch('app.services.admin_service.hiring_repo.get_by_code', return_value=sol):
        with patch('app.services.admin_service.hiring_repo.update', return_value=False):
            with patch('app.services.admin_service._send_admin') as mock_send_admin:
                result = await admin_service.set_pending_by_code(admin_number, code)

                # Debe retornar None (no tuvo éxito)
                assert result is None

                # Debe notificar al admin del error
                mock_send_admin.assert_called_once()
                assert "⚠️" in mock_send_admin.call_args[0][1]


@pytest.mark.asyncio
async def test_activate_control_validates_update():
    """Verifica que _activate_control valide el retorno de update()."""
    admin_number = "5519999999999"
    code = "SOL-0001"

    sol = {
        "codigo_solicitud": code,
        "numero_cliente": "5511888888888",
        "nombre_o_dni": "Test Client",
    }

    with patch('app.services.admin_service.hiring_repo.update', return_value=False):
        with patch('app.services.admin_service.send_text_message') as mock_send:
            result = await admin_service._activate_control(admin_number, code, sol)

            # Debe retornar None (no tuvo éxito)
            assert result is None

            # Debe notificar al admin del error
            assert mock_send.called
