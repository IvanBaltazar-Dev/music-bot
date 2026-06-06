import json
import unittest
from unittest.mock import patch

from app.models.session import (
    Session,
    STATE_HIRE_CONFIRM,
    STATE_HIRE_STEP2,
    STATE_HIRE_STEP3,
)
from app.services import session_service


class HiringFlowTest(unittest.TestCase):
    def tearDown(self):
        session_service._sessions.clear()

    def test_hire_flow_persists_and_restores_between_messages(self):
        stored = {}

        def fake_get(_number):
            if not stored:
                return None
            return {
                "paso_actual": stored["state"],
                "datos_temporales_json": stored["json"],
            }

        patches = (
            patch.object(session_service.conv_repo, "get", side_effect=fake_get),
            patch.object(
                session_service.conv_repo,
                "get_temp_data",
                side_effect=lambda _number: json.loads(stored["json"]) if stored else {},
            ),
            patch.object(
                session_service.conv_repo,
                "save_flow",
                side_effect=lambda _number, state, data: stored.update(
                    state=state, json=json.dumps(data)
                ),
            ),
            patch.object(
                session_service.conv_repo,
                "clear_flow",
                side_effect=lambda _number: stored.clear(),
            ),
        )
        with patches[0], patches[1], patches[2], patches[3]:
            number = "51999999999"
            session_service.clear_session(number)
            session_service.start_hire(number)
            response = session_service.handle_flow(
                session_service.get_session(number), "El fin de semana en Lima"
            )

            self.assertIn("Tipo de evento", response["text"])

            session_service._sessions.clear()
            restored = session_service.get_session(number)
            self.assertEqual(restored.state, STATE_HIRE_STEP2)
            self.assertEqual(restored.data["fecha_evento"], "fin de semana")
            self.assertEqual(restored.data["localidad"], "Lima")

    def test_confirmation_correction_only_changes_named_field(self):
        session = Session(
            whatsapp="51999999999",
            state=STATE_HIRE_CONFIRM,
            data={
                "fecha_evento": "fin de semana",
                "localidad": "Huancayo",
                "tipo_evento": "matrimonio",
                "horario_evento": "8 pm",
                "nombre_o_dni": "Ivan Baltazar",
            },
        )

        with patch.object(session_service, "_persist"):
            response = session_service.handle_flow(session, "La fecha es 15/10")

        self.assertIn("Actualizado", response["text"])
        self.assertEqual(session.data["fecha_evento"], "15/10")
        self.assertEqual(session.data["localidad"], "Huancayo")
        self.assertEqual(session.data["tipo_evento"], "matrimonio")
        self.assertEqual(session.data["horario_evento"], "8 pm")
        self.assertEqual(session.data["nombre_o_dni"], "Ivan Baltazar")

    def test_step3_does_not_store_ack_as_name(self):
        session = Session(
            whatsapp="51999999999",
            state=STATE_HIRE_STEP3,
            data={
                "fecha_evento": "15/10",
                "localidad": "Huancayo",
                "tipo_evento": "matrimonio",
                "horario_evento": "8 pm",
            },
        )

        with patch.object(session_service, "_persist"):
            response = session_service.handle_flow(session, "Ok")

        self.assertIn("nombre completo o DNI", response["text"])
        self.assertNotIn("nombre_o_dni", session.data)
        self.assertEqual(session.state, STATE_HIRE_STEP3)

    def test_step3_accepts_without_name(self):
        nombre, contacto, observacion = session_service._parse_name_contact(
            "sin nombre",
            "51934011041",
        )

        self.assertEqual(nombre, "")
        self.assertEqual(contacto, "51934011041")
        self.assertIn("No brindo nombre/DNI.", observacion)

    def test_complete_transcript_keeps_context_and_allows_correction(self):
        session = Session(whatsapp="51999999999")

        with patch.object(session_service, "_persist"):
            session.data = {
                "numero_cliente": session.whatsapp,
                "ultimo_mensaje_cliente": "",
            }
            session.state = session_service.STATE_HIRE_STEP1

            response = session_service.handle_flow(
                session, "El fin de semana en Lima"
            )
            self.assertIn("Tipo de evento", response["text"])
            self.assertEqual(session.data["fecha_evento"], "fin de semana")
            self.assertEqual(session.data["localidad"], "Lima")

            response = session_service.handle_flow(
                session, "Matrimonio desde las 8 pm"
            )
            self.assertIn("nombre completo o tu DNI", response["text"])
            self.assertEqual(session.data["tipo_evento"], "matrimonio")
            self.assertEqual(session.data["horario_evento"], "8 pm")

            response = session_service.handle_flow(session, "Ok")
            self.assertIn("Para no registrar un dato incorrecto", response["text"])
            self.assertEqual(session.state, STATE_HIRE_STEP3)

            response = session_service.handle_flow(session, "sin nombre")
            self.assertIn("Antes de enviarla", response["text"])
            self.assertIn("Fecha: fin de semana", response["text"])
            self.assertIn("Lugar: Lima", response["text"])

            response = session_service.handle_flow(session, "La fecha es 15/10")
            self.assertIn("Fecha: 15/10", response["text"])
            self.assertIn("Lugar: Lima", response["text"])
            self.assertIn("Evento: matrimonio", response["text"])
            self.assertIn("Hora: 8 pm", response["text"])

            response = session_service.handle_flow(session, "Sí, está bien")
            self.assertTrue(response["completed"])
            self.assertEqual(response["kind"], "hire")
            self.assertEqual(response["data"]["fecha_evento"], "15/10")


if __name__ == "__main__":
    unittest.main()
