"""Registro de movimientos de las cajas de banco (Pichincha y Guayaquil)."""

import streamlit as st
from lib import db, ui

st.set_page_config(page_title="Registrar", page_icon="🧾",
                   layout="wide", initial_sidebar_state="expanded")

cli = db.sesion()
ui.estilos("Registrar movimiento",
           "Elige la caja, marca qué pasó y escribe el monto",
           correo=st.session_state.get("correo"),
           al_salir=db.cerrar_sesion)

bancos = [c for c in db.cajas(cli) if c["tipo"] == "banco"]
if not bancos:
    st.warning("No hay cajas de banco cargadas.")
    st.stop()

izq, der = st.columns([3, 2], gap="large")

# ================================================================ IZQUIERDA
with izq:
    caja = st.selectbox("Caja", bancos, format_func=lambda c: c["nombre"])
    caja_id = caja["id"]
    saldo = next(s for s in db.saldos(cli) if s["caja_id"] == caja_id)

    c1, c2 = st.columns(2)
    ui.saldo_tarjeta(c1, "Efectivo", saldo["efectivo"])
    ui.saldo_tarjeta(c2, "Sistema", saldo["sistema"])

    st.markdown("#### ¿Qué pasó?")
    OPERACIONES = {
        "retiro":          "Retiro\n\nEl cliente se lleva efectivo",
        "deposito":        "Depósito\n\nEl cliente entrega efectivo",
        "salida_sistema":  "Sacar plata de la cuenta",
        "salida_efectivo": "Sacar dinero de la caja",
        "acreditacion":    "Acreditar dinero a la cuenta",
    }
    tipo = ui.selector(OPERACIONES, "op_banco", por_fila=2)

    equipo = db.perfiles(cli)
    st.divider()

    # El monto va fuera del formulario para que la comisión se autocomplete
    # desde la tabla de tarifas apenas lo escribes.
    monto = db.campo_monto("Monto ($)", "monto_banco")

    sugerida = 0.0
    if monto > 0 and tipo in ("retiro", "deposito"):
        sugerida = db.tarifa(cli, caja_id, "local", tipo, None, monto)
        if sugerida:
            st.caption(f"Según la tabla de tarifas, la comisión de este monto es "
                       f"{db.dinero(sugerida)}. Puedes cambiarla si el caso lo amerita.")

    with st.form("movimiento", clear_on_submit=True):
        comision = 0.0
        forma = "ninguna"
        beneficiario = motivo = None
        genera_deuda = False
        reembolsable = True
        hubo_recargo = False
        recargo = 0.0
        deudor_tipo = "persona"
        usuario_deudor = None

        if tipo == "retiro":
            comision = st.number_input("Comisión cobrada ($)", min_value=0.0,
                                       value=float(sugerida), step=0.25, format="%.2f")
            forma = st.radio(
                "¿Cómo entró la comisión?",
                ["fisica", "sistema"],
                format_func=lambda v: ("En físico — el cliente la pagó aparte"
                                       if v == "fisica"
                                       else "Acreditada — vino junto al valor en la cuenta"),
            )

        elif tipo == "deposito":
            comision = st.number_input("Comisión cobrada en físico ($)", min_value=0.0,
                                       value=float(sugerida), step=0.25, format="%.2f")
            forma = "fisica"
            st.caption("En depósitos la comisión siempre la paga el cliente en efectivo.")

        elif tipo in ("salida_sistema", "salida_efectivo"):
            quien = st.radio(
                "¿Quién se lleva el dinero?",
                ["usuario", "persona"],
                format_func=lambda v: ("Alguien del equipo" if v == "usuario"
                                       else "Otra persona"),
                horizontal=True,
            )
            if quien == "usuario":
                elegido = st.selectbox("¿Quién?", equipo,
                                       format_func=lambda p: p["nombre"])
                usuario_deudor = elegido["id"] if elegido else None
                beneficiario = elegido["nombre"] if elegido else None
                if not equipo:
                    st.warning("No hay personas cargadas. Créalas en Supabase, en "
                               "Authentication → Users.")
            else:
                beneficiario = st.text_input("¿Para quién es el dinero?")

            deudor_tipo = quien
            motivo = st.text_area("Motivo", height=70)
            genera_deuda = st.checkbox("Esto se devuelve (crear deuda)", value=True)
            if genera_deuda:
                reembolsable = st.checkbox("Es reembolsable en efectivo", value=True)

        elif tipo == "acreditacion":
            st.caption("El dinero sale del efectivo de la caja y sube el saldo del "
                       "sistema. No cuenta como transacción con comisión.")
            hubo_recargo = st.checkbox("Se sacó dinero para el recargo")
            if hubo_recargo:
                recargo = st.number_input("Recargo ($)", min_value=0.0,
                                          step=0.25, format="%.2f")

        referencia = st.text_input("Referencia o comprobante (opcional)")
        guardar = st.form_submit_button("Registrar", type="primary",
                                        use_container_width=True)

    if guardar:
        errores = []
        if monto <= 0:
            errores.append("El monto debe ser mayor que cero.")
        if tipo in ("salida_sistema", "salida_efectivo"):
            if not (beneficiario or "").strip():
                errores.append("Falta el nombre de para quién es el dinero.")
            if not (motivo or "").strip():
                errores.append("Falta el motivo.")

        # avisos de saldo insuficiente: no bloquean, pero se advierten
        if tipo in ("retiro", "salida_efectivo", "acreditacion") \
           and monto > float(saldo["efectivo"]):
            st.warning("Ojo: el monto supera el efectivo disponible en esta caja.")
        if tipo in ("deposito", "salida_sistema") and monto > float(saldo["sistema"]):
            st.warning("Ojo: el monto supera el saldo del sistema de esta caja.")

        if errores:
            for e in errores:
                st.error(e)
        else:
            fila = {
                "caja_id": caja_id,
                "tipo": tipo,
                "monto": monto,
                "comision_local": comision,
                "comision_forma": forma,
                "beneficiario": beneficiario,
                "motivo": motivo,
                "genera_deuda": genera_deuda,
                "hubo_recargo": hubo_recargo,
                "recargo": recargo,
                "referencia": referencia or None,
            }
            try:
                mov = db.registrar(cli, fila)
                if genera_deuda:
                    db.crear_deuda(
                        cli, mov["id"], caja_id,
                        deudor_tipo=deudor_tipo,
                        persona=beneficiario if deudor_tipo == "persona" else None,
                        usuario_deudor=usuario_deudor if deudor_tipo == "usuario" else None,
                        monto=monto, reembolsable=reembolsable, motivo=motivo,
                    )
                st.success(
                    f"Movimiento #{mov['id']} registrado. "
                    f"Efectivo {mov['delta_efectivo']:+.2f} · "
                    f"Sistema {mov['delta_sistema']:+.2f}"
                )
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo registrar: {e}")

# ================================================================ DERECHA
with der:
    st.markdown("#### Últimos movimientos de esta caja")
    st.caption("Aquí sale el número que necesitas si hay que anular algo.")

    recientes = [m for m in db.movimientos_abiertos(cli)
                 if m["caja"] == caja["nombre"]][:25]
    ui.tabla_movimientos(recientes, alto=430)

    with st.expander("Anular un movimiento"):
        st.caption("No se borra nada: se registra el movimiento espejo y los dos "
                   "quedan en el historial.")
        mid = st.number_input("Número del movimiento", min_value=1, step=1)
        mot = st.text_input("¿Por qué se anula?")
        if st.button("Anular", use_container_width=True):
            if not mot.strip():
                st.error("Escribe el motivo de la anulación.")
            else:
                try:
                    nuevo = db.anular(cli, int(mid), mot)
                    st.success(f"Anulado. Se creó el reverso #{nuevo}.")
                    st.rerun()
                except Exception as e:
                    st.error(f"No se pudo anular: {e}")
