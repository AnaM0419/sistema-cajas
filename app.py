"""Tablero: los saldos de las tres cajas, las alertas y el día de hoy."""

from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
import pandas as pd

from lib import db, ui

st.set_page_config(page_title="Sistema de Cajas", page_icon="🧾",
                   layout="wide", initial_sidebar_state="expanded")

cli = db.sesion()
ui.estilos("Estado de las cajas",
           "Cómo está todo ahora mismo",
           correo=st.session_state.get("correo"),
           al_salir=db.cerrar_sesion)

filas = db.saldos(cli)
if not filas:
    st.warning("No hay cajas cargadas. Ejecuta el archivo 03_datos.sql en Supabase.")
    st.stop()

# ---------------------------------------------------------------- alertas
for a in db.alertas(cli):
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
        st.markdown(f"#### {f['nombre']}")
        ui.saldo_tarjeta(col, "Efectivo en caja", f["efectivo"])
        ui.saldo_tarjeta(col, "Saldo en el sistema", f["sistema"])
        ui.saldo_tarjeta(
            col, "Deuda neta a favor", d.get("neto", 0),
            ayuda=f"Le deben {ui.monto(d.get('por_cobrar', 0))} · "
                  f"ella debe {ui.monto(d.get('por_pagar', 0))}")

# ---------------------------------------------------------------- totales
st.divider()
tot_ef = sum(float(f["efectivo"]) for f in filas)
tot_si = sum(float(f["sistema"]) for f in filas)
# Solo la deuda de personas: lo que las cajas se deben entre sí ya está
# contado en el efectivo de la caja que recibió, y sumarlo lo duplicaría.
tot_de = sum(float(d["por_cobrar_personas"]) for d in deuda_caja.values())

a, b, c, d = st.columns(4)
a.metric("Efectivo total", ui.monto(tot_ef))
b.metric("Sistema total", ui.monto(tot_si))
c.metric("Deuda de personas", ui.monto(tot_de))
d.metric("Respaldo total", ui.monto(tot_ef + tot_si + tot_de),
         help="Efectivo + sistema + deuda por cobrar: todo el dinero del negocio.")

# ------------------------------------------------------- hoy, por caja
st.divider()
st.subheader("Transacciones de hoy")
st.caption("Solo las efectivas: las que cobraron comisión a un cliente. "
           "Las anuladas y sus espejos no cuentan.")

hoy = datetime.now(ZoneInfo("America/Guayaquil")).date().isoformat()
tx = {t["caja"]: t for t in db.transacciones_dia(cli, hoy)}

cols_tx = st.columns(len(filas))
for col, f in zip(cols_tx, filas):
    t = tx.get(f["nombre"], {})
    col.metric(f["nombre"], int(t.get("transacciones", 0) or 0),
               help=f"Ganancia de hoy: {ui.monto(t.get('ganancia', 0), 4)}")

total_tx = sum(int(t.get("transacciones", 0) or 0) for t in tx.values())
total_gan = sum(float(t.get("ganancia", 0) or 0) for t in tx.values())
st.caption(f"**{total_tx}** transacciones efectivas hoy entre las tres cajas · "
           f"ganancia {ui.monto(total_gan, 4)}")

# ---------------------------------------------------------------- deudas
st.divider()
st.subheader("Deudas")

entre = db.deuda_entre_cajas(cli)
deudores = db.deuda_por_deudor(cli)

equipo = sum(float(x["debe"]) for x in deudores if x["deudor_tipo"] == "usuario")
fuera = sum(float(x["debe"]) for x in deudores if x["deudor_tipo"] == "persona")

x, y, z = st.columns(3)
x.metric("Debe el equipo", ui.monto(equipo))
y.metric("Debe gente de afuera", ui.monto(fuera))
z.metric("Pendiente entre cajas", ui.monto(sum(float(e["neto"]) for e in entre)))

if entre:
    for e in entre:
        st.caption(f"→ {e['deudora']} le debe {ui.monto(e['neto'])} a {e['acreedora']}")
else:
    st.caption("Las cajas están a mano entre sí.")

# ---------------------------------------------------------------- pendientes
st.divider()
st.subheader("Movimientos sin cortar")

pend = db.movimientos_abiertos(cli)
if not pend:
    st.info("No hay movimientos pendientes desde el último corte.")
else:
    ui.tabla_movimientos(pend, alto=360)
    st.caption(f"{len(pend)} movimientos entrarán en el próximo corte.")
