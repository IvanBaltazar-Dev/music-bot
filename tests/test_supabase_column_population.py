"""Tests de poblamiento de columnas en la capa Supabase.

Verifican que los mappers `_to_*` rellenen las columnas que antes quedaban
vacías, derivándolas de los campos disponibles, y que las marcas de transición
se preserven entre actualizaciones (no se re-sellen en cada PATCH).

Son tests de funciones puras (mappers), no requieren una BD viva.
"""

import pytest
from app.repositories import supabase_store as store


# --- Fechas de evento -------------------------------------------------------
def test_to_event_populates_real_date_from_ddmmyyyy():
    payload = store._to_event({"id_evento": "EVT-1", "fecha_evento": "15/06/2026", "ciudad": "Lima"})
    assert payload["event_date"] == "2026-06-15"
    assert payload["event_date_text"] == "15/06/2026"


def test_to_event_populates_real_date_from_iso():
    payload = store._to_event({"fecha_evento": "2026-12-01", "ciudad": "Huancayo"})
    assert payload["event_date"] == "2026-12-01"


def test_to_event_date_none_when_unparseable():
    payload = store._to_event({"fecha_evento": "por confirmar", "ciudad": "Lima"})
    assert payload["event_date"] is None
    assert payload["event_date_text"] == "por confirmar"


def test_to_iso_date_handles_sheets_serial():
    # 46188 ≈ 15/06/2026 en el sistema de seriales de Sheets.
    iso = store._to_iso_date("46188")
    assert iso and iso.startswith("2026-")


# --- Marcas de transición de solicitudes ------------------------------------
def test_transition_timestamp_seals_on_target_state():
    ts = store._transition_timestamp("", "CERRADA", "CERRADA")
    assert ts is not None


def test_transition_timestamp_none_when_state_differs():
    assert store._transition_timestamp("", "ABIERTA", "CERRADA") is None


def test_transition_timestamp_preserves_existing():
    existing = "2026-06-06T10:00:00+00:00"
    assert store._transition_timestamp(existing, "CERRADA", "CERRADA") == existing


def test_to_hiring_seals_closed_at_only_when_cerrada(monkeypatch):
    # Evitamos I/O de _ensure_client / _ensure_thread / _admin_by_phone.
    monkeypatch.setattr(store, "_ensure_client", lambda *a, **k: {"id": "c1"})
    monkeypatch.setattr(store, "_ensure_thread", lambda *a, **k: {"id": "t1"})
    monkeypatch.setattr(store, "_admin_by_phone", lambda *a, **k: None)

    abierta = store._to_hiring({"codigo_solicitud": "SOL-1", "numero_cliente": "51999888777", "estado": "ABIERTA"})
    assert abierta["closed_at"] is None
    assert abierta["status"] == "ABIERTA"

    cerrada = store._to_hiring({"codigo_solicitud": "SOL-1", "numero_cliente": "51999888777", "estado": "CERRADA"})
    assert cerrada["closed_at"] is not None
    assert cerrada["quoted_at"] is None
    assert cerrada["discarded_at"] is None


def test_to_hiring_preserves_existing_closed_at(monkeypatch):
    monkeypatch.setattr(store, "_ensure_client", lambda *a, **k: {"id": "c1"})
    monkeypatch.setattr(store, "_ensure_thread", lambda *a, **k: {"id": "t1"})
    monkeypatch.setattr(store, "_admin_by_phone", lambda *a, **k: None)

    existing = "2026-06-06T10:00:00+00:00"
    payload = store._to_hiring({
        "codigo_solicitud": "SOL-1", "numero_cliente": "51999888777",
        "estado": "CERRADA", "fecha_cierre": existing,
    })
    assert payload["closed_at"] == existing


def test_to_hiring_populates_last_interaction(monkeypatch):
    monkeypatch.setattr(store, "_ensure_client", lambda *a, **k: {"id": "c1"})
    monkeypatch.setattr(store, "_ensure_thread", lambda *a, **k: {"id": "t1"})
    monkeypatch.setattr(store, "_admin_by_phone", lambda *a, **k: None)
    payload = store._to_hiring({
        "codigo_solicitud": "SOL-1", "numero_cliente": "51999888777",
        "estado": "ABIERTA", "fecha_ultima_interaccion": "2026-06-06T09:00:00+00:00",
    })
    assert payload["last_interaction_at"] == "2026-06-06T09:00:00+00:00"


def test_to_hiring_parses_quote_amount(monkeypatch):
    monkeypatch.setattr(store, "_ensure_client", lambda *a, **k: {"id": "c1"})
    monkeypatch.setattr(store, "_ensure_thread", lambda *a, **k: {"id": "t1"})
    monkeypatch.setattr(store, "_admin_by_phone", lambda *a, **k: None)
    payload = store._to_hiring({
        "codigo_solicitud": "SOL-1", "numero_cliente": "51999888777",
        "estado": "COTIZADA", "monto_cotizado": "1500.50",
    })
    assert payload["quote_amount"] == 1500.50


# --- Conversaciones ---------------------------------------------------------
def test_to_conversation_populates_last_interaction(monkeypatch):
    monkeypatch.setattr(store, "_ensure_client", lambda *a, **k: {"id": "c1"})
    monkeypatch.setattr(store, "_admin_by_phone", lambda *a, **k: None)
    payload = store._to_conversation({
        "numero_usuario": "51999888777", "estado_conversacion": "BOT_ACTIVO",
        "fecha_ultima_interaccion": "2026-06-06T09:00:00+00:00",
    })
    assert payload["last_interaction_at"] == "2026-06-06T09:00:00+00:00"


def test_to_conversation_passes_profile_name_to_client(monkeypatch):
    captured = {}

    def fake_ensure_client(phone, name="", profile_name=""):
        captured["profile_name"] = profile_name
        return {"id": "c1"}

    monkeypatch.setattr(store, "_ensure_client", fake_ensure_client)
    monkeypatch.setattr(store, "_admin_by_phone", lambda *a, **k: None)
    store._to_conversation({
        "numero_usuario": "51999888777", "estado_conversacion": "BOT_ACTIVO",
        "profile_name": "Juan Pérez",
    })
    assert captured["profile_name"] == "Juan Pérez"


# --- Round-trip de marcas de transición -------------------------------------
def test_from_hiring_exposes_transition_marks():
    sheet = store._from_hiring({
        "code": "SOL-1", "status": "CERRADA", "client_phone": "51999888777",
        "closed_at": "2026-06-06T10:00:00+00:00",
        "quoted_at": "", "discarded_at": "",
    })
    assert sheet["fecha_cierre"] == "2026-06-06T10:00:00+00:00"
    assert sheet["fecha_cotizacion"] == ""
    assert sheet["fecha_descarte"] == ""
