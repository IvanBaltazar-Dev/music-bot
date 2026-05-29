from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    VERIFY_TOKEN: str
    WHATSAPP_TOKEN: str
    PHONE_NUMBER_ID: str
    WHATSAPP_API_VERSION: str = "v25.0"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )


settings = Settings()