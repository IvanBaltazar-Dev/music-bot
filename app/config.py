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

    # --- IA / Gemini (opcional, respaldo inteligente) ---
    # Si está deshabilitada o falta GEMINI_API_KEY, el bot funciona solo con reglas.
    # Variables existentes (NO renombrar): AI_ENABLED, GEMINI_API_KEY, AI_PROVIDER, AI_MODEL.
    AI_ENABLED: bool = False
    GEMINI_API_KEY: str = ""
    AI_PROVIDER: str = "gemini"
    AI_MODEL: str = "gemini-2.5-flash"

    # Variables nuevas (opcionales, con default seguro). Sirven de alias claros
    # para Gemini sin romper la configuración previa. No es obligatorio definirlas.
    GEMINI_ENABLED: bool = False
    GEMINI_MODEL: str = ""

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

    @property
    def gemini_enabled(self) -> bool:
        """Gemini activo solo si hay API key y está habilitado (AI_ o GEMINI_)."""
        return bool((self.AI_ENABLED or self.GEMINI_ENABLED) and self.GEMINI_API_KEY)

    @property
    def gemini_model(self) -> str:
        """Modelo de Gemini: GEMINI_MODEL si se definió, si no AI_MODEL."""
        return (self.GEMINI_MODEL or self.AI_MODEL or "gemini-1.5-flash").strip()


settings = Settings()
