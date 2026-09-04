"""Caja Facilito: recargas, juegos, pagos de servicio y compra de saldo.

Quien registra solo dice QUÉ producto y QUÉ valor mostró la plataforma.
El resto lo calcula la base de datos:
  · cuánto se le cobra al cliente (escalera de precios o tarifa de servicio)
  · cuánto te reconoce Facilito por ese producto
  · cómo quedan el efectivo y el saldo

Hay dos caminos para llegar a lo mismo: escribirlo (rápido) o subir la foto
del comprobante (cuando ayude). Los dos terminan en la misma confirmación.
"""

import streamlit as st
from lib import db, ocr

st.set_page_config(page_title="Facilito", page_icon="🧾", layout="centered")
cli = db.sesion()

st.title("Caja Facilito")

fac = next((c for c in db.cajas(cli) if c["tipo"] == "facilito"), None)
if not fac:
    st.warning("No hay caja Facilito cargada.")
    st.stop()
caja_id = fac["id"]

saldo = next(s for s in db.saldos(cli) if s["caja_id"] == caja_id)
c1, c2 = st.columns(2)
c1.metric("Efectivo en caja", db.dinero(saldo["efectivo"]))
c2.metric("Saldo Facilito", db.dinero(saldo["sistema"]))

catalogo = db.productos(cli)
por_id = {p["id"]: p for p in catalogo}


# ------------------------------------------------------------------ registro
def registrar(producto: dict, monto: float, referencia: str | None) -> None:
    """Calcula, muestra el resultado y guarda el movimiento."""
    calc = db.calcular_facilito(cli, producto["id"], monto)
    if not calc:
        st.error("No se pudo calcular este movimiento.")
        return

    total = float(calc["total_cobrar"])
    local = float(calc["comision_local"])
    prov = float(calc["comision_prov"])

    st.divider()
    a, b, c = st.columns(3)
    a.metric("Cóbrale al cliente", db.dinero(total))
    b.metric("Comisión física", db.dinero(local))
    c.metric("Ganancia total", db.dinero(local + prov, 4),
             help=f"{db.dinero(local)} del cliente + {db.dinero(prov, 4)} "
                  f"que te reconoce Facilito.")

    if monto - prov > float(saldo["sistema"]):
        st.error("No alcanza el saldo Facilito para este pago. Compra saldo primero.")
        return

    if st.button(f"Registrar · cobrar {db.dinero(total)}",
                 type="primary", use_container_width=True,
                 key=f"reg_{producto['id']}_{monto}"):
        try:
            mov = db.registrar(cli, {
                "caja_id": caja_id,
                "tipo": f"facilito_{calc['producto_tipo']}",
                "monto": monto,
                "comision_local": local,
                "comision_proveedor": prov,
                "comision_forma": "fisica",
                "operador": producto["nombre"],
                "referencia": referencia or None,
            })
            st.success(
                f"Movimiento #{mov['id']} registrado. "
                f"Efectivo {mov['delta_efectivo']:+.2f} · "
                f"Saldo Facilito {mov['delta_sistema']:+.2f}"
            )
            st.rerun()
        except Exception as e:
            st.error(f"No se pudo registrar: {e}")


tab_manual, tab_foto, tab_saldo = st.tabs(
    ["Registrar", "Desde una foto", "Comprar saldo"]
)

# -------------------------------------------------------------- 1. manual
with tab_manual:
    st.caption("Escribe parte del nombre para encontrar el producto: "
               "«tuenti», «claro megas», «agua chone»…")

    producto = st.selectbox(
        "¿Qué transacción se hizo?",
        catalogo,
        index=None,
        format_func=lambda p: p["nombre"],
        placeholder="Busca el producto",
    )

    monto = st.number_input("Valor que mostró la plataforma ($)",
                            min_value=0.0, step=0.05, format="%.2f",
                            key="monto_manual")
    ref = st.text_input("Referencia del comprobante (opcional)", key="ref_manual")

    if producto and monto > 0:
        comi = (f"{producto['comision_valor']:.2f} %"
                if producto["comision_tipo"] == "porcentual"
                else db.dinero(producto["comision_valor"], 4))
        st.caption(f"Facilito te reconoce **{comi}** por este producto.")
        registrar(producto, monto, ref)
    elif producto:
        st.info("Escribe el valor de la transacción.")

# ---------------------------------------------------------------- 2. foto
with tab_foto:
    if not ocr.hay_clave():
        st.info(
            "La lectura de fotos está apagada porque falta la clave del lector.\n\n"
            "Para encenderla: saca una clave gratis en "
            "https://aistudio.google.com/apikey y agrégala como "
            "`GEMINI_API_KEY` en tu archivo `.env` (y en los secrets de "
            "Streamlit Cloud si ya está publicada). No hace falta tocar código."
        )
    else:
        st.caption("Sube o toma la foto del comprobante. El lector propone el "
                   "producto y el valor; tú confirmas antes de guardar.")

        foto = st.file_uploader("Comprobante", type=["jpg", "jpeg", "png", "webp"])
        if foto is not None:
            st.image(foto, width=280)

            if st.button("Leer la foto", use_container_width=True):
                with st.spinner("Leyendo…"):
                    st.session_state["leido"] = ocr.leer_comprobante(
                        foto.getvalue(), foto.type or "image/jpeg")

        leido = st.session_state.get("leido")
        if leido:
            if leido["error"]:
                st.error(leido["error"] + "  \nRegístralo en la pestaña "
                         "**Registrar**, que siempre funciona.")
            else:
                st.write(f"Leyó: **{leido['producto'] or '—'}** · "
                         f"**{leido['valor'] if leido['valor'] is not None else '—'}**")

                candidatos = ocr.emparejar(leido["producto"], catalogo)
                if not candidatos:
                    st.warning("No reconocí el producto. Búscalo tú:")
                    candidatos = catalogo

                elegido = st.selectbox(
                    "Confirma el producto",
                    candidatos, index=0 if candidatos else None,
                    format_func=lambda p: p["nombre"],
                    key="prod_foto",
                )
                monto_f = st.number_input(
                    "Confirma el valor ($)", min_value=0.0, step=0.05,
                    format="%.2f", value=float(leido["valor"] or 0.0),
                    key="monto_foto",
                )
                ref_f = st.text_input("Referencia", key="ref_foto")

                st.caption("Revisa los dos datos antes de guardar: la lectura "
                           "acierta casi siempre, pero no siempre.")

                if elegido and monto_f > 0:
                    registrar(elegido, monto_f, ref_f)

# ---------------------------------------------------------- 3. compra saldo
with tab_saldo:
    st.caption("El saldo se compra con el efectivo de la propia caja Facilito: "
               "baja la gaveta y sube el saldo. Es la misma acreditación que se "
               "hace en los bancos.")

    valor = st.number_input("Valor del saldo comprado ($)", min_value=0.0,
                            step=10.0, format="%.2f", key="monto_saldo")

    hubo_recargo = st.checkbox("Se sacó dinero para el recargo", key="rec_saldo")
    recargo = 0.0
    if hubo_recargo:
        recargo = st.number_input("Recargo ($)", min_value=0.0, step=0.25,
                                  format="%.2f", key="valor_recargo")

    ref2 = st.text_input("Referencia", key="ref_saldo")

    if valor > 0:
        a, b = st.columns(2)
        a.metric("Efectivo después", db.dinero(float(saldo["efectivo"]) - valor - recargo))
        b.metric("Saldo Facilito después", db.dinero(float(saldo["sistema"]) + valor))

    if st.button("Registrar compra de saldo", type="primary",
                 use_container_width=True):
        if valor <= 0:
            st.error("El valor debe ser mayor que cero.")
        elif valor + recargo > float(saldo["efectivo"]):
            st.error("No hay tanto efectivo en la caja Facilito para comprar ese saldo.")
        else:
            try:
                mov = db.registrar(cli, {
                    "caja_id": caja_id,
                    "tipo": "acreditacion",
                    "monto": valor,
                    "hubo_recargo": hubo_recargo,
                    "recargo": recargo,
                    "motivo": "Compra de saldo Facilito",
                    "referencia": ref2 or None,
                })
                st.success(
                    f"Compra #{mov['id']} registrada. "
                    f"Efectivo {mov['delta_efectivo']:+.2f} · "
                    f"Saldo Facilito {mov['delta_sistema']:+.2f}"
                )
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo registrar: {e}")
