"""Tarifas: las dos tablas de comisiones, editables sin tocar el código.

Las dos son INGRESO:
  · 'local'     -> lo que le cobras al cliente
  · 'proveedor' -> lo que el proveedor te reconoce y te abona al saldo
"""

import streamlit as st
import pandas as pd
from lib import db, ui

st.set_page_config(page_title="Tarifas", page_icon="🧾", layout="wide",
                   initial_sidebar_state="expanded")

cli = db.sesion()
ui.estilos("Tablas de comisiones", "Lo que cobras al cliente y lo que te da el proveedor",
           correo=st.session_state.get("correo"),
           al_salir=db.cerrar_sesion)

todas = db.cajas(cli)
nombres = {c["id"]: c["nombre"] for c in todas}
caja = st.selectbox("Caja", todas, format_func=lambda c: c["nombre"])

t_local, t_prov = st.tabs(["Lo que cobras al cliente", "Lo que te da el proveedor"])


def tabla(quien: str, clave: str) -> None:
    filas = (cli.table("tarifas").select("*")
             .eq("caja_id", caja["id"]).eq("quien_cobra", quien)
             .order("tipo").order("monto_desde").execute().data)

    if filas:
        df = pd.DataFrame(filas)
        st.dataframe(
            df[["id", "tipo", "operador", "monto_desde", "monto_hasta",
                "comision_fija", "comision_porcentaje", "vigente_desde", "notas"]],
            hide_index=True, use_container_width=True,
            column_config={
                "id": "#", "tipo": "Tipo", "operador": "Operador",
                "monto_desde": st.column_config.NumberColumn("Desde $", format="%.2f"),
                "monto_hasta": st.column_config.NumberColumn("Hasta $", format="%.2f"),
                "comision_fija": st.column_config.NumberColumn("Fija $", format="%.4f"),
                "comision_porcentaje": st.column_config.NumberColumn("%", format="%.4f"),
                "vigente_desde": "Vigente desde", "notas": "Notas",
            },
        )
    else:
        st.info("Todavía no hay tarifas cargadas aquí.")

    with st.expander("Agregar una tarifa"):
        with st.form(f"nueva_{clave}"):
            a, b, c = st.columns(3)
            tipo = a.selectbox("Tipo", ["recarga", "juego", "servicio", "retiro", "deposito"],
                               key=f"t_{clave}")
            operador = b.text_input("Operador (vacío = cualquiera)", key=f"o_{clave}")
            notas = c.text_input("Notas", key=f"n_{clave}")

            d, e, f, g = st.columns(4)
            desde = d.number_input("Desde $", min_value=0.0, step=1.0,
                                   format="%.2f", key=f"d_{clave}")
            hasta = e.number_input("Hasta $ (0 = sin tope)", min_value=0.0, step=1.0,
                                   format="%.2f", key=f"h_{clave}")
            fija = f.number_input("Comisión fija $", min_value=0.0, step=0.001,
                                  format="%.4f", key=f"f_{clave}")
            pct = g.number_input("Comisión %", min_value=0.0, step=0.1,
                                 format="%.4f", key=f"p_{clave}")

            if st.form_submit_button("Agregar", type="primary"):
                try:
                    cli.table("tarifas").insert({
                        "caja_id": caja["id"], "quien_cobra": quien, "tipo": tipo,
                        "operador": operador.strip() or None,
                        "monto_desde": desde,
                        "monto_hasta": hasta if hasta > 0 else None,
                        "comision_fija": fija, "comision_porcentaje": pct,
                        "notas": notas.strip() or None,
                    }).execute()
                    st.success("Tarifa agregada.")
                    st.rerun()
                except Exception as ex:
                    st.error(f"No se pudo agregar: {ex}")

    if filas:
        with st.expander("Dar de baja una tarifa"):
            st.caption("No se borra: se le pone fecha de fin y deja de aplicar desde hoy.")
            tid = st.number_input("Número de la tarifa", min_value=1, step=1,
                                  key=f"baja_{clave}")
            if st.button("Dar de baja", key=f"btn_{clave}"):
                try:
                    cli.table("tarifas").update(
                        {"vigente_hasta": str(pd.Timestamp.today().date())}
                    ).eq("id", int(tid)).execute()
                    st.success("Tarifa dada de baja.")
                    st.rerun()
                except Exception as ex:
                    st.error(f"No se pudo: {ex}")


with t_local:
    st.caption("Estas comisiones son tu ingreso. Se autocompletan al registrar un pago.")
    tabla("local", "local")

with t_prov:
    st.caption("Lo que el proveedor te reconoce por cada movimiento y te abona "
               "al saldo. La ganancia del negocio es la SUMA de las dos tablas.")
    tabla("proveedor", "proveedor")

# --------------------------------------------------------------- probar
st.divider()
st.subheader("Probar una tarifa")
st.caption("Escribe un caso y comprueba qué comisión saldría, antes de que pase en caja.")

a, b, c = st.columns(3)
p_tipo = a.selectbox("Tipo", ["recarga", "juego", "servicio", "retiro", "deposito"])
p_op = b.text_input("Operador") or None
p_monto = c.number_input("Monto $", min_value=0.0, step=1.0, format="%.2f")

if p_monto > 0:
    cobro = db.tarifa(cli, caja["id"], "local", p_tipo, p_op, p_monto)
    recibe = db.tarifa(cli, caja["id"], "proveedor", p_tipo, p_op, p_monto)
    x, y, z = st.columns(3)
    x.metric("Cobras al cliente", db.dinero(cobro))
    y.metric("Te da el proveedor", db.dinero(recibe, 4))
    z.metric("Ganancia", db.dinero(cobro + recibe, 4))
