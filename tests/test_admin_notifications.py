import unittest
from unittest.mock import AsyncMock, patch

from app.services import admin_service


class AdminNotificationTest(unittest.IsolatedAsyncioTestCase):
    async def test_reports_missing_admin_configuration(self):
        with patch.object(admin_service, "admin_numbers", return_value=[]):
            report = await admin_service.notify_new_request({
                "codigo_solicitud": "SOL-0001",
            })

        self.assertEqual(report, {
            "configured": 0,
            "delivered": 0,
            "failed": 0,
        })

    async def test_reports_successful_delivery(self):
        with (
            patch.object(
                admin_service, "admin_numbers", return_value=["51999999999"]
            ),
            patch.object(
                admin_service, "_send_admin", new=AsyncMock(return_value=True)
            ),
        ):
            report = await admin_service.notify_new_request({
                "codigo_solicitud": "SOL-0001",
                "numero_cliente": "51911111111",
                "nombre_o_dni": "Pedro Infante",
            })

        self.assertEqual(report["delivered"], 1)
        self.assertEqual(report["failed"], 0)

    async def test_uses_template_when_free_form_delivery_fails(self):
        with (
            patch.object(
                admin_service, "admin_numbers", return_value=["51999999999"]
            ),
            patch.object(
                admin_service, "_send_admin", new=AsyncMock(return_value=False)
            ),
            patch.object(
                admin_service.settings,
                "ADMIN_NOTIFICATION_TEMPLATE_NAME",
                "nueva_solicitud_admin",
            ),
            patch.object(
                admin_service,
                "send_template_message",
                new=AsyncMock(return_value={"messages": [{"id": "wamid.test"}]}),
            ) as send_template,
        ):
            report = await admin_service.notify_new_request({
                "codigo_solicitud": "SOL-0001",
                "numero_cliente": "51911111111",
                "nombre_o_dni": "Pedro Infante",
                "fecha_evento": "15/10",
                "localidad": "Lima",
                "tipo_evento": "cumpleaños",
            })

        self.assertEqual(report["delivered"], 1)
        send_template.assert_awaited_once()

    async def test_falls_back_to_free_form_when_template_is_unavailable(self):
        with (
            patch.object(
                admin_service, "admin_numbers", return_value=["51999999999"]
            ),
            patch.object(
                admin_service.settings,
                "ADMIN_NOTIFICATION_TEMPLATE_NAME",
                "nueva_solicitud_admin",
            ),
            patch.object(
                admin_service,
                "send_template_message",
                new=AsyncMock(return_value=None),
            ),
            patch.object(
                admin_service, "_send_admin", new=AsyncMock(return_value=True)
            ) as send_free_form,
        ):
            report = await admin_service.notify_new_request({
                "codigo_solicitud": "SOL-0001",
                "numero_cliente": "51911111111",
                "nombre_o_dni": "Pedro Infante",
            })

        self.assertEqual(report["delivered"], 1)
        self.assertEqual(report["failed"], 0)
        send_free_form.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
