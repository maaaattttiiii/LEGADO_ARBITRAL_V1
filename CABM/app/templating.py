from decimal import Decimal
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.formato import formatear_moneda
from app.periodos import periodo_de
from app.tiempo import formatear

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.filters["fecha_local"] = formatear
templates.env.filters["moneda"] = formatear_moneda
templates.env.filters["periodo_local"] = periodo_de

__all__ = ["formatear_moneda", "templates"]
