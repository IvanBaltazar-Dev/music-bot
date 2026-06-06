import unittest
from unittest.mock import patch

from app.routes import whatsapp_webhook


class WhatsAppStatusTest(unittest.TestCase):
    def test_logs_failed_delivery_details(self):
        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "statuses": [{
                            "id": "wamid.test-message",
                            "recipient_id": "51999999999",
                            "status": "failed",
                            "errors": [{
                                "code": 131047,
                                "title": "Re-engagement message",
                                "error_data": {
                                    "details": "Message outside allowed window"
                                },
                            }],
                        }]
                    }
                }]
            }]
        }

        with patch("builtins.print") as print_mock:
            count = whatsapp_webhook._log_delivery_statuses(payload)

        self.assertEqual(count, 1)
        line = print_mock.call_args.args[0]
        self.assertIn("delivery_status=failed", line)
        self.assertIn("code=131047", line)
        self.assertNotIn("51999999999", line)


if __name__ == "__main__":
    unittest.main()
