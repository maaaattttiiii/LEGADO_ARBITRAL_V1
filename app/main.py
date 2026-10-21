from fastapi import FastAPI

from app.routes import (
    arbitros,
    canchas,
    designaciones,
    partidos,
    tarifas,
    tesoreria,
    torneos,
)

app = FastAPI(title="CABM - Colegio de Árbitros", version="0.1.0")
app.include_router(arbitros.router)
app.include_router(partidos.router)
app.include_router(designaciones.router)
app.include_router(tesoreria.router)
app.include_router(canchas.router)
app.include_router(torneos.router)
app.include_router(tarifas.router)
