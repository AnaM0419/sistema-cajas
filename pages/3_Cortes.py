"""Cortes de caja: por turno durante la jornada y el cierre diario.

Las tres cajas se cortan juntas: cuentas el efectivo de cada gaveta y el
sistema cierra las tres de una sola vez, con un consolidado al final.
"""

import streamlit as st
import pandas as pd
from lib import db, ui

st.set_page_config(page_title="Cortes", page_icon="🧾", layout="wide",
                   initial_sidebar_state="expanded")

cli = db.sesion()
ui.estilos("Corte de caja", "Cuenta el efectivo, compara y cierra el período",
           correo=st.session_state.get("correo"),
           al_salir=db.cerrar_sesion)

tipo = st.radio(
    "Tipo de corte",
    ["turno", "diario"],
    format_func=lambda t: ("Cambio de turno — para saber si la caja quedó cuadrada"
                           if t == "turno" else "Cierre del día"),
    horizontal=True,
)

todas = db.cajas(cli)
saldos = {s["caja_id"]: s for s in db.saldos(cli)}

st.divider()
st.subheader("Cuenta el efectivo de cada gaveta")

contado: dict[int, float] = {}
reportado: dict[int, float | None] = {}

cols = st.columns(len(todas))
for col, caja in zip(cols, todas):
    s = saldos[caja["id"]]
    with col:
        st.markdown(f"**{caja['nombre']}**")
        st.caption(f"Esperado: {ui.monto(s['efectivo'])}")
        contado[caja["id"]] = db.campo_monto(
            "Efectivo contado ($)", f"ef_{caja['id']}")
        st.caption(f"Sistema esperado: {ui.monto(s['sistema'])}")
        rep = db.campo_monto(
            "Sistema según el banco ($)", f"si_{caja['id']}",
            ayuda="Opcional. Déjalo vacío si no lo vas a verificar ahora.")
        reportado[caja["id"]] = rep if rep > 0 else None

        dif = contado[caja["id"]] - float(s["efectivo"])
        if contado[caja["id"]] > 0:
            if abs(dif) < 0.005:
                st.success("Cuadrada")
            elif dif > 0:
                st.warning(f"Sobra {db.dinero(dif)}")
            else:
                st.error(f"Falta {db.dinero(-dif)}")

notas = st.text_area("Notas del corte (opcional)", height=70)

st.divider()
confirmar = st.checkbox("Ya conté el efectivo de las tres cajas y los valores son correctos")

if st.button("Cerrar corte de las tres cajas", type="primary", disabled=not confirmar):
    resultados = []
    for caja in todas:
        try:
            r = db.cerrar_corte(cli, caja["id"], tipo,
                                contado[caja["id"]], reportado[caja["id"]], notas)
            r = r[0] if isinstance(r, list) else r
            r["caja"] = caja["nombre"]
            resultados.append(r)
        except Exception as e:
            st.error(f"{caja['nombre']}: no se pudo cerrar — {e}")

    if resultados:
        st.success("Corte cerrado.")
        df = pd.DataFrame(resultados)
        st.dataframe(
            df[["caja", "efectivo_esperado", "efectivo_contado", "diferencia_efectivo",
                "sistema_esperado", "deuda_total", "n_efectivas", "n_movimientos",
                "comisiones_periodo"]],
            hide_index=True, use_container_width=True,
            column_config={
                "caja": "Caja",
                "efectivo_esperado": st.column_config.NumberColumn("Efectivo esperado", format="%.2f"),
                "efectivo_contado": st.column_config.NumberColumn("Contado", format="%.2f"),
                "diferencia_efectivo": st.column_config.NumberColumn("Diferencia", format="%.2f"),
                "sistema_esperado": st.column_config.NumberColumn("Sistema", format="%.2f"),
                "deuda_total": st.column_config.NumberColumn("Deuda", format="%.2f"),
                "n_efectivas": st.column_config.NumberColumn(
                    "Transacciones", help="Efectivas: sin anuladas ni espejos."),
                "n_movimientos": st.column_config.NumberColumn(
                    "Filas", help="Todo lo registrado, incluidos anulados y ajustes."),
                "comisiones_periodo": st.column_config.NumberColumn("Ganancia", format="%.2f"),
            },
        )
        a, b, c, d = st.columns(4)
        a.metric("Efectivo total contado", ui.monto(df["efectivo_contado"].sum()))
        b.metric("Descuadre total", db.dinero(df["diferencia_efectivo"].sum()))
        c.metric("Transacciones efectivas", int(df["n_efectivas"].sum()))
        d.metric("Ganancia del período", db.dinero(df["comisiones_periodo"].sum()))

# ------------------------------------------------------------- historial
st.divider()
st.subheader("Cortes anteriores")

hist = (cli.table("cortes").select("*").order("hasta", desc=True)
        .limit(60).execute().data)
if hist:
    dfh = pd.DataFrame(hist)
    nombres = {c["id"]: c["nombre"] for c in todas}
    dfh["caja"] = dfh["caja_id"].map(nombres)
    dfh["hasta"] = pd.to_datetime(dfh["hasta"]).dt.strftime("%d/%m/%Y %H:%M")
    st.dataframe(
        dfh[["hasta", "caja", "tipo", "efectivo_esperado", "efectivo_contado",
             "diferencia_efectivo", "deuda_total", "comisiones_periodo"]],
        hide_index=True, use_container_width=True,
    )
else:
    st.info("Todavía no hay cortes registrados.")
