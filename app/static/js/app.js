/*
 * CABM — comportamiento propio del Active Stack.
 *
 * Stores de Alpine para modales nativos y notificaciones, más la reapertura
 * declarativa de un modal cuando el servidor re-renderiza un formulario con
 * errores (``data-abrir-modal="true"``).
 */
document.documentElement.classList.add("js");

/*
 * HTMX no intercambia respuestas 4xx por defecto. El contrato de la interfaz
 * devuelve fragmentos con 400 (validación), 401/429 (login) y 403 (guardas)
 * más cabeceras ``HX-Retarget`` / ``HX-Reswap`` cuando corresponde; se
 * habilita el swap para esos códigos sin alterar el status HTTP.
 */
const ESTADOS_CON_SWAP = new Set([400, 401, 403, 404, 429]);

document.addEventListener("htmx:beforeSwap", (evento) => {
  const detalle = evento.detail || {};
  if (detalle.xhr && ESTADOS_CON_SWAP.has(detalle.xhr.status)) {
    detalle.shouldSwap = true;
    detalle.isError = false;
  }
});

/*
 * Estado de carga accesible para HTMX.
 *
 * La región que se va a reemplazar expone ``aria-busy="true"`` mientras la
 * petición está en curso y una región viva anuncia el estado a lectores de
 * pantalla. Al terminar (éxito, error o aborto) se limpia el estado.
 */
const anunciarCarga = (mensaje) => {
  const region = document.getElementById("cabm-estado-htmx");
  if (region) region.textContent = mensaje;
};

const objetivoHtmx = (evento) => {
  const detalle = (evento && evento.detail) || {};
  return detalle.target || detalle.elt || null;
};

document.addEventListener("htmx:beforeRequest", (evento) => {
  const objetivo = objetivoHtmx(evento);
  if (objetivo && objetivo.setAttribute) {
    objetivo.setAttribute("aria-busy", "true");
  }
  anunciarCarga("Cargando…");
});

const finalizarCarga = (evento) => {
  const objetivo = objetivoHtmx(evento);
  if (objetivo && objetivo.removeAttribute) {
    objetivo.removeAttribute("aria-busy");
  }
  anunciarCarga("");
};

["htmx:afterRequest", "htmx:responseError", "htmx:sendError", "htmx:abort"].forEach(
  (nombre) => document.addEventListener(nombre, finalizarCarga)
);

document.addEventListener("alpine:init", () => {
  Alpine.store("modales", {
    abrir(id) {
      if (!id) return;
      window.dispatchEvent(
        new CustomEvent("cabm:abrir-modal", { detail: { id } })
      );
    },
  });

  Alpine.store("toasts", {
    items: [],
    maximo: 3,
    duracion: 5000,
    duracionError: 8000,
    anuncioError: "",
    _secuencia: 0,
    _temporizadores: {},
    _restante: {},

    agregar(detalle) {
      const tipo = (detalle && detalle.tipo) || "info";
      const mensaje = (detalle && detalle.mensaje) || "";
      if (!mensaje) return;
      const toast = { id: ++this._secuencia, mensaje, tipo };
      this.items.push(toast);
      while (this.items.length > this.maximo) {
        this.quitar(this.items[0].id);
      }
      if (tipo === "error") {
        this.anuncioError = "";
        queueMicrotask(() => {
          this.anuncioError = mensaje;
        });
      }
      this._programar(
        toast.id,
        tipo === "error" ? this.duracionError : this.duracion
      );
    },

    quitar(id) {
      this._limpiar(id);
      delete this._restante[id];
      this.items = this.items.filter((toast) => toast.id !== id);
    },

    pausar(id) {
      if (this._restante[id] === undefined) {
        const toast = this.items.find((item) => item.id === id);
        this._restante[id] =
          toast && toast.tipo === "error" ? this.duracionError : this.duracion;
      }
      this._limpiar(id);
    },

    reanudar(id) {
      const restante = this._restante[id];
      delete this._restante[id];
      this._programar(id, restante === undefined ? this.duracion : restante);
    },

    reanudarTodos() {
      this.items.forEach((toast) => this.reanudar(toast.id));
    },

    _programar(id, duracion) {
      this._limpiar(id);
      this._temporizadores[id] = window.setTimeout(
        () => this.quitar(id),
        duracion
      );
    },

    _limpiar(id) {
      const temporizador = this._temporizadores[id];
      if (temporizador) {
        clearTimeout(temporizador);
        delete this._temporizadores[id];
      }
    },
  });

  window.addEventListener("cabm:toast", (evento) => {
    Alpine.store("toasts").agregar(evento.detail || {});
  });

  const reabrirPendientes = () => {
    document.querySelectorAll('[data-abrir-modal="true"]').forEach((dialogo) => {
      window.dispatchEvent(
        new CustomEvent("cabm:abrir-modal", { detail: { id: dialogo.id } })
      );
    });
  };

  document.addEventListener("alpine:initialized", reabrirPendientes);
  document.addEventListener("htmx:afterSwap", reabrirPendientes);
  window.setTimeout(reabrirPendientes, 0);
});
