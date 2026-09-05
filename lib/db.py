"""Conexión a Supabase, inicio de sesión y consultas comunes."""

import os
import streamlit as st
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()


def _config(clave: str) -> str:
    """Lee de .env en tu computadora y de los secrets en Streamlit Cloud."""
    valor = os.getenv(clave)
    if not valor:
        try:
            valor = st.secrets[clave]
        except Exception:
            valor = None
    if not valor:
        st.error(
            f"Falta la configuración {clave}. "
            "Revisa tu archivo .env (o los secrets si ya está publicada)."
        )
        st.stop()
    return valor


@st.cache_resource
def _cliente() -> Client:
    return create_client(_config("SUPABASE_URL"), _config("SUPABASE_ANON_KEY"))


def sesion() -> Client:
    """Devuelve el cliente ya autenticado. Si no hay sesión, muestra el login."""
    cli = _cliente()

    if "token" in st.session_state:
        cli.postgrest.auth(st.session_state["token"])
        return cli

    st.title("Sistema de Cajas")
    st.caption("Ingresa con tu correo y contraseña.")

    with st.form("login"):
        correo = st.text_input("Correo")
        clave = st.text_input("Contraseña", type="password")
        entrar = st.form_submit_button("Entrar", type="primary")

    if entrar:
        try:
            r = cli.auth.sign_in_with_password({"email": correo, "password": clave})
            st.session_state["token"] = r.session.access_token
            st.session_state["correo"] = correo
            st.rerun()
        except Exception:
            st.error("Correo o contraseña incorrectos.")
    st.stop()


def cerrar_sesion() -> None:
    for k in ("token", "correo"):
        st.session_state.pop(k, None)
    st.rerun()


# ---------------------------------------------------------------- consultas

def cajas(cli: Client) -> list[dict]:
    return cli.table("cajas").select("*").eq("activa", True).order("id").execute().data


def saldos(cli: Client) -> list[dict]:
    return cli.table("v_saldos").select("*").order("caja_id").execute().data


def alertas(cli: Client) -> list[dict]:
    return cli.table("v_alertas").select("*").execute().data


def movimientos_abiertos(cli: Client, caja_id: int | None = None) -> list[dict]:
    """Movimientos que todavía no entraron en ningún corte."""
    q = cli.table("v_movimientos_full").select("*").is_("corte_id", "null")
    if caja_id:
        q = q.eq("caja", nombre_caja(cli, caja_id))
    return q.order("fecha", desc=True).execute().data


def nombre_caja(cli: Client, caja_id: int) -> str:
    for c in cajas(cli):
        if c["id"] == caja_id:
            return c["nombre"]
    return ""


def registrar(cli: Client, datos: dict) -> dict:
    """Inserta un movimiento. Los deltas los calcula la base de datos."""
    return cli.table("movimientos").insert(datos).execute().data[0]


def crear_deuda(cli: Client, movimiento_id: int, caja_id: int, **kw) -> dict:
    fila = {
        "movimiento_id": movimiento_id,
        "caja_id": caja_id,
        "deudor_tipo": kw.get("deudor_tipo", "persona"),
        "persona": kw.get("persona"),
        "usuario_deudor": kw.get("usuario_deudor"),
        "caja_deudora": kw.get("caja_deudora"),
        "monto": kw["monto"],
        "saldo_pendiente": kw["monto"],
        "reembolsable": kw.get("reembolsable", True),
        "motivo": kw.get("motivo"),
    }
    return cli.table("deudas").insert(fila).execute().data[0]


# ------------------------------------------------------------------ deudas

def perfiles(cli: Client) -> list[dict]:
    """Las personas que usan el sistema."""
    return (cli.table("perfiles").select("*").eq("activo", True)
            .order("nombre").execute().data)


def deuda_por_deudor(cli: Client) -> list[dict]:
    return cli.table("v_deuda_por_deudor").select("*").execute().data


def deuda_por_caja(cli: Client) -> list[dict]:
    return cli.table("v_deuda_por_caja").select("*").order("caja_id").execute().data


def deuda_entre_cajas(cli: Client) -> list[dict]:
    return cli.table("v_deuda_entre_cajas").select("*").execute().data


def deudas_detalle(cli: Client, abiertas: bool = True) -> list[dict]:
    q = cli.table("v_deudas_detalle").select("*")
    if abiertas:
        q = q.eq("estado", "abierta")
    return q.order("creada_en", desc=True).execute().data


def abonar(cli: Client, deuda_id: int, monto: float, destino: str = "efectivo") -> dict:
    r = cli.rpc("abonar_deuda", {
        "p_deuda": deuda_id, "p_monto": monto, "p_destino": destino,
    }).execute().data
    return r[0] if isinstance(r, list) else r


def tarifa(cli: Client, caja_id: int, quien: str, tipo: str,
           operador: str | None, monto: float) -> float:
    r = cli.rpc("buscar_tarifa", {
        "p_caja": caja_id, "p_quien": quien, "p_tipo": tipo,
        "p_operador": operador, "p_monto": monto,
    }).execute()
    return float(r.data or 0)


# ----------------------------------------------------------------- facilito

@st.cache_data(ttl=600, show_spinner=False)
def _productos(_cli: Client, tipo: str | None) -> list[dict]:
    q = _cli.table("productos_facilito").select("*").eq("activo", True)
    if tipo:
        q = q.eq("tipo", tipo)
    filas, desde = [], 0
    while True:                      # la API pagina de 1000 en 1000
        lote = q.range(desde, desde + 999).order("nombre").execute().data
        filas += lote
        if len(lote) < 1000:
            break
        desde += 1000
    return filas


def productos(cli: Client, tipo: str | None = None) -> list[dict]:
    """Los 880 productos de Facilito, opcionalmente filtrados por tipo."""
    return _productos(cli, tipo)


def calcular_facilito(cli: Client, producto_id: int, monto: float) -> dict:
    """Total a cobrar y las dos comisiones. Todo lo calcula la base."""
    r = cli.rpc("calcular_facilito",
                {"p_producto": producto_id, "p_monto": monto}).execute().data
    return (r[0] if isinstance(r, list) else r) or {}


def anular(cli: Client, movimiento_id: int, motivo: str) -> int:
    return cli.rpc("anular_movimiento",
                   {"p_id": movimiento_id, "p_motivo": motivo}).execute().data


def cerrar_corte(cli: Client, caja_id: int, tipo: str,
                 efectivo_contado: float, sistema_reportado: float | None,
                 notas: str | None) -> dict:
    return cli.rpc("cerrar_corte", {
        "p_caja": caja_id,
        "p_tipo": tipo,
        "p_efectivo_contado": efectivo_contado,
        "p_sistema_reportado": sistema_reportado,
        "p_notas": notas,
    }).execute().data


def campo_monto(etiqueta: str, clave: str, ayuda: str | None = None,
                valor: float | None = None) -> float:
    """Campo de dinero que se teclea en centavos, sin borrar nada primero.

    Arranca VACÍO: no hay un 0.00 que haya que seleccionar y borrar.
    Escribes 1000 y queda $10,00 · escribes 205 y queda $2,05 ·
    escribes 5 y queda $0,05. El punto se acomoda solo.
    """
    inicial = "" if not valor else str(int(round(float(valor) * 100)))
    texto = st.text_input(
        etiqueta, value=inicial, key=clave, help=ayuda,
        placeholder="Teclea los centavos: 1000 = $10,00",
    )
    digitos = "".join(c for c in texto if c.isdigit())
    monto = int(digitos) / 100 if digitos else 0.0
    if digitos:
        st.markdown(
            f"<div style='margin-top:-10px;margin-bottom:6px;font-size:1.7rem;"
            f"font-weight:700;line-height:1.2'>{dinero(monto)}</div>",
            unsafe_allow_html=True,
        )
    return monto


def movimientos_saldos(cli: Client, desde: str, hasta: str) -> list[dict]:
    """Movimientos con el efectivo y el saldo que quedaron después de cada uno."""
    return (cli.table("v_movimientos_saldos").select("*")
            .gte("fecha", desde).lte("fecha", hasta)
            .order("fecha", desc=True).execute().data)


def dinero(v, decimales: int = 2) -> str:
    """Formato ecuatoriano: $ 1.234,56 — con más decimales cuando la
    comisión del proveedor trae fracciones de centavo."""
    texto = f"{float(v or 0):,.{decimales}f}"
    return "$ " + texto.replace(",", "@").replace(".", ",").replace("@", ".")
