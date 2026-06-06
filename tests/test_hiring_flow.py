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
                "temp_data_from_record",
                side_effect=lambda _conv: json.loads(stored["json"]) if stored else {},
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

    def test_refresh_replaces_stale_worker_state(self):
        number = "51999999999"
        session_service._sessions[number] = Session(
            whatsapp=number,
            state=session_service.STATE_HIRE_STEP1,
            data={"numero_cliente": number},
        )

        with (
            patch.object(session_service.conv_repo, "get", return_value={
                "paso_actual": STATE_HIRE_STEP2,
            }),
            patch.object(session_service.conv_repo, "temp_data_from_record", return_value={
                "numero_cliente": number,
                "fecha_evento": "15/10",
                "localidad": "Huancayo",
            }),
        ):
            refreshed = session_service.refresh_session(number)

        self.assertEqual(refreshed.state, STATE_HIRE_STEP2)
        self.assertEqual(refreshed.data["fecha_evento"], "15/10")
        self.assertEqual(refreshed.data["localidad"], "Huancayo")

    def test_confirmation_accepts_natural_yes(self):
        session = Session(
            whatsapp="51999999999",
            state=STATE_HIRE_CONFIRM,
            data={
                "fecha_evento": "15/10",
                "localidad": "Huancayo",
                "tipo_evento": "matrimonio",
                "horario_evento": "8 pm",
                "nombre_o_dni": "Ivan Baltazar",
            },
        )

        with patch.object(session_service, "_persist"):
            response = session_service.handle_flow(session, "Sí, está bien")

        self.assertTrue(response["completed"])
        self.assertEqual(response["kind"], "hire")

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

    def test_step3_uses_requested_copy(self):
        session = Session(whatsapp="51999999999")
        with patch.object(session_service, "_persist"):
            response = session_service._ask_hire_step3(session)

        self.assertIn("¿A nombre de quién dejamos la solicitud?", response["text"])
        self.assertIn(
            "Puedes pasarme tu nombre completo o tu DNI, como prefieras.",
            response["text"],
        )
        self.assertIn(
            "lo paso al manager para que te responda por este mismo chat",
            response["text"],
        )
        self.assertIn(
            "Si prefieres que te llamen, dime también a qué hora te acomoda mejor.",
            response["text"],
        )

    def test_step1_accepts_date_then_place(self):
        session = Session(
            whatsapp="51999999999",
            state=session_service.STATE_HIRE_STEP1,
            data={},
        )
        with (
            patch.object(session_service, "_persist"),
            patch.object(session_service, "_ai_fill_missing"),
        ):
            response = session_service.handle_flow(session, "Fecha 14/07")
            self.assertIn("Me falta la ciudad", response["text"])
            self.assertEqual(session.data["fecha_evento"], "14/07")

            response = session_service.handle_flow(session, "Lima")

        self.assertIn("¡Lima!", response["text"])
        self.assertEqual(session.data["fecha_evento"], "14/07")
        self.assertEqual(session.data["localidad"], "Lima")

    def test_step1_accepts_place_then_date_with_personalized_copy(self):
        session = Session(
            whatsapp="51999999999",
            state=session_service.STATE_HIRE_STEP1,
            data={},
        )
        with (
            patch.object(session_service, "_persist"),
            patch.object(session_service, "_ai_fill_missing"),
        ):
            response = session_service.handle_flow(session, "Lima")
            self.assertIn("¡Lima!", response["text"])
            self.assertIn("Me falta la fecha", response["text"])
            self.assertEqual(session.data["localidad"], "Lima")

            response = session_service.handle_flow(session, "14/07")

        self.assertIn("Tipo de evento", response["text"])
        self.assertEqual(session.data["fecha_evento"], "14/07")
        self.assertEqual(session.data["localidad"], "Lima")

    def test_confirmation_accepts_bare_date_and_bare_place(self):
        session = Session(
            whatsapp="51999999999",
            state=STATE_HIRE_CONFIRM,
            data={
                "fecha_evento": "fin de semana",
                "localidad": "Huancayo",
                "tipo_evento": "cumpleaños",
                "horario_evento": "8 pm",
                "nombre_o_dni": "",
            },
        )

        with patch.object(session_service, "_persist"):
            response = session_service.handle_flow(session, "14/07")
            self.assertIn("Fecha: 14/07", response["text"])
            self.assertIn("Lugar: Huancayo", response["text"])

            response = session_service.handle_flow(session, "Lima")

        self.assertIn("¡Lima!", response["text"])
        self.assertIn("Fecha: 14/07", response["text"])
        self.assertIn("Lugar: Lima", response["text"])
        self.assertEqual(session.data["tipo_evento"], "cumpleaños")
        self.assertEqual(session.data["horario_evento"], "8 pm")

    def test_confirmation_accepts_singular_birthday_correction(self):
        session = Session(
            whatsapp="51999999999",
            state=STATE_HIRE_CONFIRM,
            data={
                "fecha_evento": "14/07",
                "localidad": "Lima",
                "tipo_evento": "(por confirmar)",
                "horario_evento": "8 pm",
            },
        )

        with patch.object(session_service, "_persist"):
            response = session_service.handle_flow(
                session, "El evento es cumpleaños"
            )

        self.assertIn("Evento: cumpleaños", response["text"])
        self.assertEqual(session.data["localidad"], "Lima")

    def test_unknown_place_correction_replaces_old_personalized_copy(self):
        session = Session(
            whatsapp="51999999999",
            state=STATE_HIRE_CONFIRM,
            data={
                "fecha_evento": "14/07",
                "localidad": "Lima",
                "frase_contratacion": "¡Lima! Siempre hay un buen motivo para celebrar.",
                "tipo_evento": "cumpleaños",
                "horario_evento": "8 pm",
            },
        )

        with patch.object(session_service, "_persist"):
            response = session_service.handle_flow(session, "El lugar es Cusco")

        self.assertIn("Lugar: Cusco", response["text"])
        self.assertIn("Perfecto, podemos coordinar", response["text"])
        self.assertNotIn("¡Lima!", response["text"])

    def test_step3_understands_natural_no_name_phrases(self):
        for answer in ("Por ahora no mostraré mi nombre", "Ningún nombre"):
            with self.subTest(answer=answer):
                nombre, _, observacion = session_service._parse_name_contact(
                    answer,
                    "51934011041",
                )
                self.assertEqual(nombre, "")
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
