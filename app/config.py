from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Variables existentes (NO renombrar) ---
    VERIFY_TOKEN: str
    WHATSAPP_TOKEN: str
    PHONE_NUMBER_ID: str
    WHATSAPP_API_VERSION: str = "v25.0"

    # --- Administradores ---
    # Lista separada por comas, ej: 519XXXXXXXX,519YYYYYYYY
    ADMIN_PHONE_NUMBERS: str = ""

    # --- Google Sheets (opcional) ---
    # Si está deshabilitado o faltan credenciales, el bot usa memoria temporal.
    GOOGLE_SHEETS_ENABLED: bool = False
    GOOGLE_SHEETS_ID: str = ""
    GOOGLE_APPLICATION_CREDENTIALS: str = ""

    # --- Identidad de la agrupación ---
    BOT_NAME: str = "Music Bot"
    GROUP_NAME: str = "la agrupación"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )

    @property
    def admin_numbers(self) -> list[str]:
        """Lista de números de administradores definidos en el .env (solo dígitos)."""
        raw = self.ADMIN_PHONE_NUMBERS or ""
        numbers = []
        for part in raw.split(","):
            digits = "".join(ch for ch in part if ch.isdigit())
            if digits:
                numbers.append(digits)
        return numbers


settings = Settings()
