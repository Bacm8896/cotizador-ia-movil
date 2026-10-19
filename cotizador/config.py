"""Configuración y datos fijos de la empresa (tomados del Excel modelo)."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

TEMPLATES_DIR = BASE_DIR / "templates"
LOGO_PATH = BASE_DIR / "assets" / "logo_alarmec.png"

ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-5-5")
TRANSCRIPTION_MODEL = os.getenv("TRANSCRIPTION_MODEL", "gpt-4o-mini-transcribe")


@dataclass(frozen=True)
class Empresa:
    """Membrete y firma que aparecen en toda cotización."""

    nombre: str = "ALARMEC"
    giro: str = (
        "Sistemas de alarmas: venta instalación, reinstalación, chequeos, "
        "mantenimientos, porteros eléctricos CCTV, Cercas eléctricas, "
        "motores de garaje, domótica."
    )
    direccion: str = "GUILLERMO CORNEJO N60-53 Y FLAVIO ALFARO"
    telefono: str = "098 700 3533"
    ciudad_emision: str = "Quito"
    firmante: str = "Sr LUIS CARVAJAL"
    firmante_nombre: str = "LUIS CARVAJAL V."
    cargo: str = "ASESOR EN SEGURIDAD"


@dataclass(frozen=True)
class CondicionesPorDefecto:
    """Textos que el Excel modelo repite en cada cotización."""

    forma_pago: str = "50% A LA FIRMA DEL CONTRATO"
    saldo: str = "CONTRAENTREGA"
    tiempo_entrega: str = (
        "DE 2 A 4 DIAS LABORABLES DEPENDIENDO INCONVENIENTES CLIMATICOS"
    )
    garantia: str = (
        "UN AÑO EN EQUIPO E INSTALACIÓN,EXCEPTO POR VARIACIONES DE VOLTAJE, "
        "SABOTAJE O MAL USO DE LOS MISMOS"
    )
    ciudad_cliente: str = "QUITO-ECUADOR"


EMPRESA = Empresa()
DEFECTOS = CondicionesPorDefecto()
