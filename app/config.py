from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Variables existentes (NO renombrar) ---
    VERIFY_TOKEN: str = ""
    WHATSAPP_TOKEN: str = ""
    PHONE_NUMBER_ID: str = ""
    WHATSAPP_API_VERSION: str = "v25.0"
    WHATSAPP_APP_SECRET: str = ""

    # --- Administradores ---
    # Lista separada por comas, ej: 519XXXXXXXX,519YYYYYYYY
    ADMIN_PHONE_NUMBERS: str = ""

    # Código de país por defecto (Perú=51). Si un número viene sin él (solo los
    # 9 dígitos nacionales), se le antepone al ENVIAR para que WhatsApp lo
    # entregue. Evita que admins no reciban notificaciones por falta del '51'.
    DEFAULT_COUNTRY_CODE: str = "51"

    # --- Google Sheets (opcional) ---
    # Si está deshabilitado o faltan credenciales, el bot usa memoria temporal.
    GOOGLE_SHEETS_ENABLED: bool = False
    GOOGLE_SHEETS_ID: str = ""
    GOOGLE_APPLICATION_CREDENTIALS: str = ""

    # --- Persistencia ---
    # sheets: Google Sheets, supabase: PostgreSQL/Supabase, memory: temporal local.
    STORAGE_BACKEND: str = ""
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""

    # --- Identidad de la agrupación ---
    BOT_NAME: str = "Music Bot"
    GROUP_NAME: str = "la agrupación"

    # --- IA / Gemini (opcional, respaldo inteligente) ---
    # Si está deshabilitada o falta GEMINI_API_KEY, el bot funciona solo con reglas.
    # Variables existentes (NO renombrar): AI_ENABLED, GEMINI_API_KEY, AI_PROVIDER, AI_MODEL.
    AI_ENABLED: bool = False
    GEMINI_API_KEY: str = ""
    AI_PROVIDER: str = "gemini"
    AI_MODEL: str = "gemini-2.5-flash-lite"

    # Variables nuevas (opcionales, con default seguro). Sirven de alias claros
    # para Gemini sin romper la configuración previa. No es obligatorio definirlas.
    GEMINI_ENABLED: bool = False
    GEMINI_MODEL: str = ""
    AI_FLOW_MIN_CONFIDENCE: float = 0.40

    # Plantilla aprobada por Meta para avisar fuera de la ventana de 24 horas.
    ADMIN_NOTIFICATION_TEMPLATE_NAME: str = ""
    ADMIN_NOTIFICATION_TEMPLATE_LANGUAGE: str = "es"

    # Si un admin toma control y no cierra/suelta, el caso vuelve a cola tras
    # este tiempo para que el cliente no quede bloqueado indefinidamente.
    ADMIN_CONTROL_TIMEOUT_HOURS: int = 48

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
        return (
            self.GEMINI_MODEL or self.AI_MODEL or "gemini-2.5-flash-lite"
        ).strip()

    @property
    def storage_backend(self) -> str:
        backend = (self.STORAGE_BACKEND or "").strip().lower()
        if backend in {"supabase", "memory", "sheets"}:
            return backend
        return "sheets" if self.GOOGLE_SHEETS_ENABLED else "memory"

    @property
    def supabase_enabled(self) -> bool:
        return bool(
            self.storage_backend == "supabase"
            and self.SUPABASE_URL
            and self.SUPABASE_SERVICE_ROLE_KEY
        )

    @property
    def production_health_ready(self) -> bool:
        required_values = (
            self.STORAGE_BACKEND,
            self.SUPABASE_URL,
            self.SUPABASE_SERVICE_ROLE_KEY,
            self.WHATSAPP_TOKEN,
            self.PHONE_NUMBER_ID,
            self.VERIFY_TOKEN,
        )
        valid_storage_backend = (self.STORAGE_BACKEND or "").strip().lower() in {
            "memory",
            "sheets",
            "supabase",
        }
        return valid_storage_backend and all(str(value or "").strip() for value in required_values)


settings = Settings()
