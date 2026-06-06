import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.models.session import Session, STATE_HIRE_CONFIRM
from app.services import conversation_service, intent_service


class ConversationRoutingTest(unittest.IsolatedAsyncioTestCase):
    async def test_active_flow_does_not_reclassify_with_ai(self):
        session = Session(
            whatsapp="51999999999",
            state=STATE_HIRE_CONFIRM,
            data={"fecha_evento": "15/10", "localidad": "Lima"},
        )
        detect_intent = Mock(
            side_effect=AssertionError(
                "No debe clasificar intención pública dentro de un flujo activo"
            )
        )

        with (
            patch.object(conversation_service.admin_service, "is_admin", return_value=False),
            patch.object(conversation_service.conv_repo, "upsert"),
            patch.object(
                conversation_service.session_service,
                "refresh_session",
                return_value=session,
            ),
            patch.object(conversation_service, "_log_msg"),
            patch.object(
                conversation_service.admin_service,
                "control_context_for_client",
                return_value=None,
            ),
            patch.object(
                conversation_service.intent_service,
                "detect_intent",
                detect_intent,
            ),
            patch.object(
                conversation_service.session_service,
                "handle_flow",
                return_value={"text": "Sigue revisando", "completed": False},
            ),
            patch.object(
                conversation_service,
                "_send_text",
                new=AsyncMock(),
            ),
            patch.object(
                conversation_service,
                "_notify_followers_if_any",
                new=AsyncMock(),
            ),
        ):
            await conversation_service._route(
                "51999999999",
                "Sí",
                "",
                "Ivan",
                "",
            )

        detect_intent.assert_not_called()


if __name__ == "__main__":
    unittest.main()
