"""Deudas en sus tres dimensiones: por caja, por persona y entre cajas."""

import streamlit as st
import pandas as pd
from lib import db

st.set_page_config(page_title="Deudas", page_icon="🧾", layout="wide")
cli = db.sesion()

st.title("Deudas")

todas = db.cajas(cli)
nombres = {c["id"]: c["nombre"] for c in todas}

por_caja = db.deuda_por_caja(cli)
por_deudor = db.deuda_por_deudor(cli)
entre = db.deuda_entre_cajas(cli)

t_resumen, t_quien, t_detalle, t_prestamo = st.tabs(
    ["Resumen", "Quién debe", "Detalle y abonos", "Préstamo entre cajas"]
)

# ================================================================ RESUMEN
with t_resumen:
    total_cobrar = sum(float(c["por_cobrar_personas"]) for c in por_caja)
    total_entre = sum(float(e["neto"]) for e in entre)

    a, b = st.columns(2)
    a.metric("Por cobrar a personas", db.dinero(total_cobrar),
             help="Lo que deben los del equipo y la gente de afuera.")
    b.metric("Pendiente entre cajas", db.dinero(total_entre),
             help="Ya compensado: solo lo que falta mover de una gaveta a otra.")

    st.divider()
    st.subheader("Cada caja")
    st.caption("Lo que le deben, lo que debe a otra caja, y el neto.")

    df = pd.DataFrame(por_caja)
    st.dataframe(
        df[["nombre", "por_cobrar_personas", "por_cobrar_cajas", "por_pagar", "neto"]],
        hide_index=True, use_container_width=True,
        column_config={
            "nombre": "Caja",
            "por_cobrar_personas": st.column_config.NumberColumn(
                "Le deben (personas)", format="%.2f"),
            "por_cobrar_cajas": st.column_config.NumberColumn(
                "Le deben (otras cajas)", format="%.2f"),
            "por_pagar": st.column_config.NumberColumn("Ella debe", format="%.2f"),
            "neto": st.column_config.NumberColumn("Neto a favor", format="%.2f"),
        },
    )

    st.divider()
    st.subheader("Entre cajas, ya compensado")
    if not entre:
        st.success("Las cajas están a mano: ninguna le debe a otra.")
    else:
        for e in entre:
            linea = (f"**{e['deudora']}** le debe **{db.dinero(e['neto'])}** "
                     f"a **{e['acreedora']}**")
            if float(e["bruto_contrario"]) > 0:
                linea += (f"  \n<span style='opacity:.7'>Resulta de cruzar "
                          f"{db.dinero(e['bruto'])} contra "
                          f"{db.dinero(e['bruto_contrario'])} en sentido contrario."
                          f"</span>")
            st.markdown(linea, unsafe_allow_html=True)

# ============================================================== QUIÉN DEBE
with t_quien:
    if not por_deudor:
        st.success("Nadie debe nada ahora mismo.")
    else:
        dfd = pd.DataFrame(por_deudor)
        etiquetas = {"usuario": "Del equipo", "persona": "De afuera", "caja": "Otra caja"}
        dfd["quien"] = dfd["deudor_tipo"].map(etiquetas)

        equipo = dfd[dfd["deudor_tipo"] == "usuario"]
        fuera = dfd[dfd["deudor_tipo"] == "persona"]

        a, b, c = st.columns(3)
        a.metric("Debe el equipo", db.dinero(equipo["debe"].sum()))
        b.metric("Debe gente de afuera", db.dinero(fuera["debe"].sum()))
        c.metric("Deudor más antiguo",
                 f"{int(dfd['dias_mas_antigua'].max())} días")

        st.divider()
        st.dataframe(
            dfd[["quien", "deudor", "debe", "deudas_abiertas",
                 "dias_mas_antigua", "tiene_no_reembolsable"]]
            .sort_values("debe", ascending=False),
            hide_index=True, use_container_width=True,
            column_config={
                "quien": "Tipo", "deudor": "Quién",
                "debe": st.column_config.NumberColumn("Debe", format="%.2f"),
                "deudas_abiertas": st.column_config.NumberColumn("Deudas"),
                "dias_mas_antigua": st.column_config.NumberColumn("Días la más vieja"),
                "tiene_no_reembolsable": "Tiene alguna que no se devuelve",
            },
        )
        st.caption("Las deudas marcadas como no reembolsables siguen contando aquí "
                   "hasta que las des por saldadas: son gasto reconocido, no dinero "
                   "que vaya a volver.")

# =========================================================== DETALLE/ABONOS
with t_detalle:
    detalle = db.deudas_detalle(cli, abiertas=True)
    if not detalle:
        st.info("No hay deudas abiertas.")
    else:
        dfx = pd.DataFrame(detalle)
        dfx["creada_en"] = pd.to_datetime(dfx["creada_en"]).dt.strftime("%d/%m/%Y")
        st.dataframe(
            dfx[["id", "creada_en", "caja_acreedora", "deudor", "monto",
                 "abonado", "saldo_pendiente", "dias", "reembolsable", "motivo"]],
            hide_index=True, use_container_width=True,
            column_config={
                "id": "#", "creada_en": "Fecha", "caja_acreedora": "Caja",
                "deudor": "Quién debe",
                "monto": st.column_config.NumberColumn("Prestado", format="%.2f"),
                "abonado": st.column_config.NumberColumn("Abonado", format="%.2f"),
                "saldo_pendiente": st.column_config.NumberColumn("Pendiente", format="%.2f"),
                "dias": st.column_config.NumberColumn("Días"),
                "reembolsable": "Se devuelve",
            },
        )

        st.divider()
        st.subheader("Registrar un abono")
        opciones = {
            f"#{d['id']} · {d['deudor']} · debe {db.dinero(d['saldo_pendiente'])} "
            f"a {d['caja_acreedora']}": d
            for d in detalle
        }
        elegida = st.selectbox("¿Cuál deuda?", list(opciones))
        d = opciones[elegida]

        col1, col2 = st.columns(2)
        with col1:
            pago = db.campo_monto("¿Cuánto abona? ($)", f"abono_{d['id']}",
                                  valor=float(d["saldo_pendiente"]))
        destino = col2.radio(
            "¿Dónde entra el dinero?", ["efectivo", "sistema"],
            format_func=lambda v: ("A la gaveta (efectivo)" if v == "efectivo"
                                   else "A la cuenta (sistema)"),
        )

        if d["deudor_tipo"] == "caja":
            st.info(f"Como quien paga es una caja, el dinero también sale de "
                    f"**{d['deudor']}**: se registran los dos lados.")

        if st.button("Registrar abono", type="primary"):
            try:
                r = db.abonar(cli, d["id"], pago, destino)
                if r["estado"] == "pagada":
                    st.success(f"Deuda #{d['id']} saldada por completo.")
                else:
                    st.success(f"Abono registrado. Quedan "
                               f"{db.dinero(r['saldo_pendiente'])} pendientes.")
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo registrar: {e}")

# ============================================================== PRÉSTAMO
with t_prestamo:
    st.caption("Cuando una caja le pasa dinero a otra. Si es reembolsable queda "
               "como deuda de la caja que recibió, y se cruza automáticamente "
               "contra lo que la otra ya le debiera.")

    with st.form("traspaso"):
        a, b = st.columns(2)
        origen = a.selectbox("Sale de", todas, format_func=lambda c: c["nombre"])
        destino_caja = b.selectbox("Entra a", todas,
                                   index=1 if len(todas) > 1 else 0,
                                   format_func=lambda c: c["nombre"])
        valor = st.number_input("Monto ($)", min_value=0.0, step=10.0, format="%.2f")
        saldo_tipo = st.radio("¿Qué saldo se mueve?", ["efectivo", "sistema"],
                              horizontal=True)
        reembolsable = st.checkbox("Es reembolsable (crear deuda entre cajas)",
                                   value=True)
        motivo = st.text_input("Motivo")
        enviar = st.form_submit_button("Registrar traspaso", type="primary")

    if enviar:
        if origen["id"] == destino_caja["id"]:
            st.error("Las cajas de origen y destino deben ser distintas.")
        elif valor <= 0:
            st.error("El monto debe ser mayor que cero.")
        elif not motivo.strip():
            st.error("Escribe el motivo del traspaso.")
        else:
            try:
                envio = db.registrar(cli, {
                    "caja_id": origen["id"],
                    "tipo": f"traspaso_envio_{saldo_tipo}",
                    "monto": valor,
                    "beneficiario": destino_caja["nombre"],
                    "motivo": motivo,
                    "cuenta_comision": False,
                })
                db.registrar(cli, {
                    "caja_id": destino_caja["id"],
                    "tipo": f"traspaso_recepcion_{saldo_tipo}",
                    "monto": valor,
                    "beneficiario": origen["nombre"],
                    "motivo": f"{motivo} (mov #{envio['id']})",
                    "cuenta_comision": False,
                })
                if reembolsable:
                    db.crear_deuda(cli, envio["id"], origen["id"],
                                   deudor_tipo="caja",
                                   caja_deudora=destino_caja["id"],
                                   monto=valor, reembolsable=True, motivo=motivo)
                st.success("Traspaso registrado.")
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo registrar: {e}")
