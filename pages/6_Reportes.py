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

datos = (cli.table("v_movimientos_saldos").select("*")
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

# --------------------------------------- transacciones efectivas por dia
st.divider()
st.subheader("Transacciones efectivas por día")
st.caption("Cuántas transacciones de verdad se hicieron en cada caja. "
           "No cuentan las anuladas, sus espejos, ni los movimientos internos "
           "como acreditaciones, traspasos y cobros de deuda.")

tx = pd.DataFrame(db.transacciones_dia(cli))
if tx.empty:
    st.caption("Sin transacciones efectivas en el sistema.")
else:
    tx = tx[(tx["dia"] >= str(desde)) & (tx["dia"] <= str(hasta))
            & (tx["caja"].isin(elegidas))]

if not tx.empty:
    resumen = (tx.groupby("caja")
                 .agg(transacciones=("transacciones", "sum"),
                      cobrado=("cobrado_clientes", "sum"),
                      del_proveedor=("del_proveedor", "sum"),
                      ganancia=("ganancia", "sum"))
                 .reset_index())
    st.dataframe(
        resumen, hide_index=True, use_container_width=True,
        column_config={
            "caja": "Caja",
            "transacciones": st.column_config.NumberColumn("Transacciones"),
            "cobrado": st.column_config.NumberColumn("Cobrado a clientes", format="%.2f"),
            "del_proveedor": st.column_config.NumberColumn("Del proveedor", format="%.4f"),
            "ganancia": st.column_config.NumberColumn("Ganancia", format="%.4f"),
        },
    )
    st.caption(f"**{int(resumen['transacciones'].sum())}** transacciones efectivas "
               f"en el período.")

    with st.expander("Ver el detalle día por día"):
        dia_caja = (tx.pivot_table(index="dia", columns="caja",
                                   values="transacciones", aggfunc="sum")
                      .fillna(0).astype(int).sort_index(ascending=False))
        st.dataframe(dia_caja, use_container_width=True)

# ------------------------------------------- rastro de caja y sistema
st.divider()
st.subheader("Rastro de caja y sistema")
st.caption("Movimiento por movimiento, cómo quedaron la gaveta y la cuenta "
           "después de cada uno. Sirve para comprobar que los dos lados se "
           "movieron como debían.")

caja_rastro = st.selectbox("¿Qué caja quieres seguir?", sorted(df["caja"].unique()),
                           key="caja_rastro")
rastro = (df[df["caja"] == caja_rastro]
          .sort_values(["fecha", "id"])
          .copy())

if rastro.empty:
    st.caption("Sin movimientos de esta caja en el período.")
else:
    r1, r2 = st.columns(2)
    r1.metric(f"Efectivo al cierre del período", db.dinero(rastro["efectivo_despues"].iloc[-1]))
    r2.metric(f"Sistema al cierre del período", db.dinero(rastro["sistema_despues"].iloc[-1]))

    vista = rastro.sort_values(["fecha", "id"], ascending=False).copy()
    vista["momento"] = vista["fecha"].dt.strftime("%d/%m %H:%M")
    st.dataframe(
        vista[["id", "momento", "tipo", "monto", "delta_efectivo", "efectivo_despues",
               "delta_sistema", "sistema_despues", "beneficiario", "motivo", "anulado"]],
        hide_index=True, use_container_width=True,
        column_config={
            "id": "#", "momento": "Cuándo", "tipo": "Movimiento",
            "monto": st.column_config.NumberColumn("Monto", format="%.2f"),
            "delta_efectivo": st.column_config.NumberColumn("Movió caja", format="%+.2f"),
            "efectivo_despues": st.column_config.NumberColumn("Quedó en caja", format="%.2f"),
            "delta_sistema": st.column_config.NumberColumn("Movió sistema", format="%+.2f"),
            "sistema_despues": st.column_config.NumberColumn("Quedó en sistema", format="%.2f"),
            "beneficiario": "Para quién", "motivo": "Motivo", "anulado": "Anulado",
        },
    )

    st.line_chart(rastro.set_index("fecha")[["efectivo_despues", "sistema_despues"]],
                  height=260)

# ------------------------------------------------------------- detalle
st.divider()
st.subheader("Detalle")
detalle = df.copy()
detalle["fecha"] = detalle["fecha"].dt.strftime("%d/%m/%Y %H:%M")
st.dataframe(
    detalle[["id", "fecha", "caja", "tipo", "monto", "comision_local",
             "comision_proveedor", "ganancia", "delta_efectivo", "efectivo_despues",
             "delta_sistema", "sistema_despues",
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
