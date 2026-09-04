"""Reportes con filtros y descarga a Excel."""

import io
from datetime import date, timedelta

import streamlit as st
import pandas as pd
from lib import db

st.set_page_config(page_title="Reportes", page_icon="🧾", layout="wide")
cli = db.sesion()

st.title("Reportes")

todas = db.cajas(cli)

a, b, c = st.columns([1, 1, 2])
desde = a.date_input("Desde", value=date.today() - timedelta(days=30))
hasta = b.date_input("Hasta", value=date.today())
elegidas = c.multiselect("Cajas", [x["nombre"] for x in todas],
                         default=[x["nombre"] for x in todas])

datos = (cli.table("v_movimientos_full").select("*")
         .gte("fecha", str(desde))
         .lte("fecha", str(hasta + timedelta(days=1)))
         .order("fecha", desc=True).execute().data)

df = pd.DataFrame(datos)
if df.empty:
    st.info("No hay movimientos en ese rango.")
    st.stop()

df = df[df["caja"].isin(elegidas)]
df["fecha"] = pd.to_datetime(df["fecha"])

# ------------------------------------------------------------- resumen
con_comision = df[(df["cuenta_comision"]) & (~df["anulado"]) & (df["reversa_de"].isna())]

k1, k2, k3, k4 = st.columns(4)
k1.metric("Movimientos", len(df))
k2.metric("Con comisión", len(con_comision))
k3.metric("Cobrado a clientes", db.dinero(con_comision["comision_local"].sum()))
k4.metric("Ganancia total", db.dinero(con_comision["ganancia"].sum()),
          help="Lo que cobraste a los clientes más lo que te reconoció el proveedor.")

st.divider()

# ------------------------------------------------------------- por caja
st.subheader("Por caja")
por_caja = con_comision.groupby("caja").agg(
    movimientos=("id", "count"),
    cobrado=("comision_local", "sum"),
    del_proveedor=("comision_proveedor", "sum"),
    ganancia=("ganancia", "sum"),
).reset_index()
st.dataframe(por_caja, hide_index=True, use_container_width=True)

# ------------------------------------------------------------- por tipo
st.subheader("Por tipo de movimiento")
por_tipo = df.groupby("tipo").agg(
    movimientos=("id", "count"),
    monto=("monto", "sum"),
    comision=("comision_local", "sum"),
).reset_index().sort_values("movimientos", ascending=False)
st.dataframe(por_tipo, hide_index=True, use_container_width=True)

# ------------------------------------------------------------- evolución
st.subheader("Ganancia por día")
diario = (con_comision.set_index("fecha")
          .resample("D")["ganancia"].sum().reset_index())
if not diario.empty:
    st.bar_chart(diario, x="fecha", y="ganancia", height=260)

# ------------------------------------------------------------- salidas
st.subheader("Salidas de dinero por beneficiario")
salidas = df[df["tipo"].isin(["salida_efectivo", "salida_sistema"])]
if salidas.empty:
    st.caption("No hubo salidas en este período.")
else:
    st.dataframe(
        salidas.groupby("beneficiario").agg(
            veces=("id", "count"), total=("monto", "sum")
        ).reset_index().sort_values("total", ascending=False),
        hide_index=True, use_container_width=True,
    )

# ------------------------------------------------------------- detalle
st.divider()
st.subheader("Detalle")
detalle = df.copy()
detalle["fecha"] = detalle["fecha"].dt.strftime("%d/%m/%Y %H:%M")
st.dataframe(
    detalle[["id", "fecha", "caja", "tipo", "monto", "comision_local",
             "comision_proveedor", "ganancia", "delta_efectivo", "delta_sistema",
             "beneficiario", "motivo", "operador", "anulado"]],
    hide_index=True, use_container_width=True,
)

# ------------------------------------------------------------- descarga
buffer = io.BytesIO()
with pd.ExcelWriter(buffer, engine="openpyxl") as w:
    detalle.to_excel(w, sheet_name="Detalle", index=False)
    por_caja.to_excel(w, sheet_name="Por caja", index=False)
    por_tipo.to_excel(w, sheet_name="Por tipo", index=False)

st.download_button(
    "Descargar en Excel",
    buffer.getvalue(),
    file_name=f"reporte_cajas_{desde}_{hasta}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    type="primary",
)
