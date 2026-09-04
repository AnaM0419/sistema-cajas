"""Tablero: los saldos de las tres cajas y las alertas, al momento."""

import streamlit as st
import pandas as pd

from lib import db

st.set_page_config(page_title="Sistema de Cajas", page_icon="🧾", layout="wide")

cli = db.sesion()

with st.sidebar:
    st.caption(f"Sesión: {st.session_state.get('correo','')}")
    if st.button("Cerrar sesión"):
        db.cerrar_sesion()

st.title("Estado de las cajas")

filas = db.saldos(cli)
if not filas:
    st.warning("No hay cajas cargadas. Ejecuta el archivo 03_datos.sql en Supabase.")
    st.stop()

# ---------------------------------------------------------------- alertas
avisos = db.alertas(cli)
for a in avisos:
    texto = f"**{a['caja']}** · {a['mensaje']}"
    if a["nivel"] == "critico":
        st.error(texto, icon="🔴")
    else:
        st.warning(texto, icon="🟡")

# ---------------------------------------------------------------- saldos
deuda_caja = {d["caja_id"]: d for d in db.deuda_por_caja(cli)}

cols = st.columns(len(filas))
for col, f in zip(cols, filas):
    d = deuda_caja.get(f["caja_id"], {})
    with col:
        st.subheader(f["nombre"])
        st.metric("Efectivo en caja", db.dinero(f["efectivo"]))
        st.metric("Saldo en el sistema", db.dinero(f["sistema"]))
        st.metric("Deuda neta a favor", db.dinero(d.get("neto", 0)),
                  help=f"Le deben {db.dinero(d.get('por_cobrar', 0))} · "
                       f"ella debe {db.dinero(d.get('por_pagar', 0))}")

# ---------------------------------------------------------------- total
st.divider()
tot_ef = sum(float(f["efectivo"]) for f in filas)
tot_si = sum(float(f["sistema"]) for f in filas)
# Solo la deuda de personas: lo que las cajas se deben entre sí ya está
# contado en el efectivo de la caja que recibió, y sumarlo lo duplicaría.
tot_de = sum(float(d["por_cobrar_personas"]) for d in deuda_caja.values())

a, b, c, d = st.columns(4)
a.metric("Efectivo total", db.dinero(tot_ef))
b.metric("Sistema total", db.dinero(tot_si))
c.metric("Deuda de personas", db.dinero(tot_de))
d.metric("Respaldo total", db.dinero(tot_ef + tot_si + tot_de),
         help="Efectivo + sistema + deuda por cobrar: todo el dinero del negocio.")

# ---------------------------------------------------------------- deudas
st.divider()
st.subheader("Deudas")

entre = db.deuda_entre_cajas(cli)
deudores = db.deuda_por_deudor(cli)

equipo = sum(float(d["debe"]) for d in deudores if d["deudor_tipo"] == "usuario")
fuera = sum(float(d["debe"]) for d in deudores if d["deudor_tipo"] == "persona")

x, y, z = st.columns(3)
x.metric("Debe el equipo", db.dinero(equipo))
y.metric("Debe gente de afuera", db.dinero(fuera))
z.metric("Pendiente entre cajas", db.dinero(sum(float(e["neto"]) for e in entre)))

if entre:
    for e in entre:
        st.caption(f"→ {e['deudora']} le debe {db.dinero(e['neto'])} a {e['acreedora']}")
else:
    st.caption("Las cajas están a mano entre sí.")

# ---------------------------------------------------------------- pendientes
st.divider()
st.subheader("Movimientos sin cortar")

pend = db.movimientos_abiertos(cli)
if not pend:
    st.info("No hay movimientos pendientes desde el último corte.")
else:
    df = pd.DataFrame(pend)
    df["fecha"] = pd.to_datetime(df["fecha"]).dt.strftime("%d/%m %H:%M")
    st.dataframe(
        df[["id", "fecha", "caja", "tipo", "monto", "comision_local",
            "delta_efectivo", "delta_sistema", "beneficiario", "motivo", "anulado"]],
        hide_index=True, use_container_width=True,
        column_config={
            "id": "#",
            "comision_local": st.column_config.NumberColumn("Comisión", format="%.2f"),
            "monto": st.column_config.NumberColumn("Monto", format="%.2f"),
            "delta_efectivo": st.column_config.NumberColumn("Δ Efectivo", format="%.2f"),
            "delta_sistema": st.column_config.NumberColumn("Δ Sistema", format="%.2f"),
        },
    )
    st.caption(f"{len(pend)} movimientos entrarán en el próximo corte.")
