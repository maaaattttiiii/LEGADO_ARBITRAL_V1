from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.cancha import Cancha
from app.presentacion import es_htmx, respuesta_o_fragmento, toast
from app.services.canchas import CanchaInvalida, actualizar_cancha, cambiar_estado, crear_cancha
from app.seguridad import requiere_tesorero
from app.templating import templates

router = APIRouter(dependencies=[Depends(requiere_tesorero)])

_PAGINA = "canchas/index.html"
_PARCIAL_LISTADO = "partials/canchas/listado.html"
_PARCIAL_ALTA = "partials/canchas/modal.html"
_PARCIAL_EDITAR = "partials/canchas/modal_editar.html"
_MODAL_ALTA = "modalCancha"


def _contexto(
    db: Session,
    *,
    error: str | None = None,
    form: dict[str, str] | None = None,
    abrir_alta: bool = False,
    editar_error_id: int | None = None,
) -> dict:
    canchas = (
        db.execute(select(Cancha).order_by(Cancha.nombre, Cancha.id))
        .scalars()
        .all()
    )
    return {
        "seccion": "canchas",
        "canchas": canchas,
        "error": error,
        "form": form or {},
        "abrir_alta": abrir_alta,
        "editar_error_id": editar_error_id,
    }


def _render(
    request: Request,
    db: Session,
    *,
    error: str | None = None,
    form: dict[str, str] | None = None,
    status_code: int = 200,
    abrir_alta: bool = False,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        _PAGINA,
        _contexto(db, error=error, form=form, abrir_alta=abrir_alta),
        status_code=status_code,
    )


def _obtener(db: Session, cancha_id: int) -> Cancha:
    cancha = db.get(Cancha, cancha_id)
    if cancha is None:
        raise HTTPException(status_code=404, detail="No existe la cancha.")
    return cancha


def _fragmento_listado(request: Request, db: Session, mensaje: str, modal: str | None = None):
    return respuesta_o_fragmento(
        request,
        completa=_PAGINA,
        parcial=_PARCIAL_LISTADO,
        contexto=_contexto(db),
        trigger=toast("success", mensaje, cerrar_modal=modal),
    )


@router.get("/canchas", response_class=HTMLResponse)
def listar_canchas(request: Request, db: Session = Depends(get_db)):
    return _render(request, db)


@router.post("/canchas", response_class=HTMLResponse)
def alta_cancha(
    request: Request,
    db: Session = Depends(get_db),
    nombre: str = Form(""),
    localidad: str = Form(""),
    direccion: str = Form(""),
    litros_viatico: str = Form(""),
):
    form = {
        "nombre": nombre,
        "localidad": localidad,
        "direccion": direccion,
        "litros_viatico": litros_viatico,
    }
    try:
        crear_cancha(
            db,
            nombre=nombre,
            localidad=localidad,
            direccion=direccion,
            litros_viatico=litros_viatico,
        )
        db.commit()
    except CanchaInvalida as exc:
        db.rollback()
        if es_htmx(request):
            return respuesta_o_fragmento(
                request,
                completa=_PAGINA,
                parcial=_PARCIAL_ALTA,
                contexto=_contexto(db, error=str(exc), form=form, abrir_alta=True),
                status_code=400,
                headers={
                    "HX-Retarget": f"#{_MODAL_ALTA}",
                    "HX-Reswap": "outerHTML",
                },
                trigger=toast("error", str(exc)),
            )
        return _render(
            request, db, error=str(exc), form=form, status_code=400, abrir_alta=True
        )

    if es_htmx(request):
        return _fragmento_listado(
            request, db, "Cancha creada correctamente.", _MODAL_ALTA
        )

    return RedirectResponse("/canchas", status_code=303)


@router.post("/canchas/{cancha_id}", response_class=HTMLResponse)
def editar_cancha(
    cancha_id: int,
    request: Request,
    db: Session = Depends(get_db),
    nombre: str = Form(""),
    localidad: str = Form(""),
    direccion: str = Form(""),
    litros_viatico: str = Form(""),
):
    cancha = _obtener(db, cancha_id)
    form = {
        "nombre": nombre,
        "localidad": localidad,
        "direccion": direccion,
        "litros_viatico": litros_viatico,
    }
    try:
        actualizar_cancha(
            db,
            cancha,
            nombre=nombre,
            localidad=localidad,
            direccion=direccion,
            litros_viatico=litros_viatico,
        )
        db.commit()
    except CanchaInvalida as exc:
        db.rollback()
        if es_htmx(request):
            return respuesta_o_fragmento(
                request,
                completa=_PAGINA,
                parcial=_PARCIAL_EDITAR,
                contexto={
                    **_contexto(
                        db,
                        error=str(exc),
                        form=form,
                        editar_error_id=cancha.id,
                    ),
                    "cancha": cancha,
                },
                status_code=400,
                headers={
                    "HX-Retarget": f"#modalEditar{cancha.id}",
                    "HX-Reswap": "outerHTML",
                },
                trigger=toast("error", str(exc)),
            )
        return _render(request, db, error=str(exc), status_code=400)

    if es_htmx(request):
        return _fragmento_listado(
            request, db, "Cancha actualizada.", f"modalEditar{cancha.id}"
        )

    return RedirectResponse("/canchas", status_code=303)


@router.post("/canchas/{cancha_id}/estado")
def estado_cancha(
    cancha_id: int,
    request: Request,
    db: Session = Depends(get_db),
    activo: str = Form(""),
):
    cancha = _obtener(db, cancha_id)
    cambiar_estado(db, cancha, activo=activo)
    db.commit()
    if es_htmx(request):
        return _fragmento_listado(request, db, "Estado de la cancha actualizado.")
    return RedirectResponse("/canchas", status_code=303)
