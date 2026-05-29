"""Modelo simple de evento de la agrupación."""

from dataclasses import dataclass, field
from datetime import datetime

# Estados posibles de un evento
EVENT_ACTIVE = "ACTIVO"
EVENT_INACTIVE = "INACTIVO"
EVENT_CANCELLED = "CANCELADO"


@dataclass
class Event:
    fecha: str
    hora: str
    ciudad: str
    lugar: str
    descripcion: str
    estado: str = EVENT_ACTIVE
    creado_por: str = ""
    id: str = ""
    fecha_registro: str = field(default_factory=lambda: datetime.utcnow().isoformat(timespec="seconds"))

    def as_row(self) -> list:
        """Representación ordenada según las columnas de la hoja 'Eventos'."""
        return [
            self.id,
            self.fecha,
            self.hora,
            self.ciudad,
            self.lugar,
            self.descripcion,
            self.estado,
            self.creado_por,
            self.fecha_registro,
        ]
