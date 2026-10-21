from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.arbitro import Arbitro
from app.models.enums import CategoriaArbitro, EstadoArbitro
from app.services.arbitros import ArbitroInvalido, crear_arbitro
from app.seguridad import requiere_tesorero
from app.templating import templates

router = APIRouter(dependencies=[Depends(requiere_tesorero)])

CATEGORIA_ETIQUETAS = {
    CategoriaArbitro.CAT_A.value: "A",
    CategoriaArbitro.CAT_A1.value: "A1",
    CategoriaArbitro.CAT_B.value: "B",
    CategoriaArbitro.PROMOCIONAL.value: "Promocional",
    CategoriaArbitro.UNICA.value: "Única",
}

ESTADO_ETIQUETAS = {
    EstadoArbitro.ACTIVO.value: "Activo",
    EstadoArbitro.SUSPENDIDO.value: "Suspendido",
    EstadoArbitro.INACTIVO.value: "Inactivo",
}

ESTADO_CLASES = {
    EstadoArbitro.ACTIVO.value: "success",
    EstadoArbitro.SUSPENDIDO.value: "warning",
    EstadoArbitro.INACTIVO.value: "secondary",
}


def _render_listado(
    request: Request,
    db: Session,
    *,
    error: str | None = None,
    form: dict[str, str] | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    arbitros = (
        db.execute(
            select(Arbitro).order_by(Arbitro.apellido, Arbitro.nombre, Arbitro.id)
        )
        .scalars()
        .all()
    )

    return templates.TemplateResponse(
        request,
        "arbitros/index.html",
        {
            "seccion": "arbitros",
            "arbitros": arbitros,
            "categorias": list(CategoriaArbitro),
            "estados": list(EstadoArbitro),
            "categoria_etiquetas": CATEGORIA_ETIQUETAS,
            "estado_etiquetas": ESTADO_ETIQUETAS,
            "estado_clases": ESTADO_CLASES,
            "error": error,
            "form": form or {},
        },
        status_code=status_code,
    )


@router.get("/", include_in_schema=False)
def raiz() -> RedirectResponse:
    return RedirectResponse("/arbitros", status_code=303)


@router.get("/arbitros", response_class=HTMLResponse)
def listar_arbitros(request: Request, db: Session = Depends(get_db)):
    return _render_listado(request, db)


@router.post("/arbitros", response_class=HTMLResponse)
def alta_arbitro(
    request: Request,
    db: Session = Depends(get_db),
    legajo: str = Form(""),
    nombre: str = Form(""),
    apellido: str = Form(""),
    dni: str = Form(""),
    categoria: str = Form(""),
    estado: str = Form(""),
    tiene_auto: str = Form(""),
    email: str = Form(""),
    telefono: str = Form(""),
    localidad: str = Form(""),
):
    form = {
        "legajo": legajo,
        "nombre": nombre,
        "apellido": apellido,
        "dni": dni,
        "categoria": categoria,
        "estado": estado,
        "tiene_auto": tiene_auto,
        "email": email,
        "telefono": telefono,
        "localidad": localidad,
    }
    try:
        crear_arbitro(
            db,
            legajo=legajo,
            nombre=nombre,
            apellido=apellido,
            dni=dni,
            categoria=categoria,
            estado=estado,
            tiene_auto=tiene_auto,
            email=email,
            telefono=telefono,
            localidad=localidad,
        )
        db.commit()
    except ArbitroInvalido as exc:
        db.rollback()
        return _render_listado(request, db, error=str(exc), form=form, status_code=400)

    return RedirectResponse("/arbitros", status_code=303)
