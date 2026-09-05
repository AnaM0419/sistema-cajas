"""Apariencia común de todas las pantallas.

Tres cosas viven aquí para que no haya que repetirlas:
  · la paleta y los estilos
  · el interruptor que tapa los montos (arranca TAPADO)
  · los componentes grandes: botones de operación y tablas de movimientos
"""

import streamlit as st

# ---------------------------------------------------------------- paleta
AZUL_TINTA = "#273b75"   # el más oscuro, para títulos y barra lateral
AZUL       = "#35649e"   # el de acción: botones y selección
CELESTE    = "#3b92b0"   # apoyo, gráficos
VINO       = "#9a336f"   # lo crítico y lo que no se debe pasar por alto

ENTRA = "#12775A"        # el dinero sube
SALE  = "#B03A2E"        # el dinero baja
OJO   = "#8A6100"        # avisos

ETIQUETAS = {
    "retiro":                     "Retiro",
    "deposito":                   "Depósito",
    "salida_sistema":             "Salida de la cuenta",
    "salida_efectivo":            "Salida de caja",
    "acreditacion":               "Acreditación",
    "cobro_deuda_efectivo":       "Cobro de deuda · efectivo",
    "cobro_deuda_sistema":        "Cobro de deuda · cuenta",
    "traspaso_envio_efectivo":    "Traspaso enviado · efectivo",
    "traspaso_recepcion_efectivo":"Traspaso recibido · efectivo",
    "traspaso_envio_sistema":     "Traspaso enviado · cuenta",
    "traspaso_recepcion_sistema": "Traspaso recibido · cuenta",
    "facilito_recarga":           "Recarga",
    "facilito_juego":             "Juego",
    "facilito_servicio":          "Pago de servicio",
    "ajuste":                     "Ajuste de corte",
}

_CSS = f"""
<style>
  :root {{
    --tinta:{AZUL_TINTA}; --azul:{AZUL}; --celeste:{CELESTE}; --vino:{VINO};
    --entra:{ENTRA}; --sale:{SALE}; --ojo:{OJO};
    --linea:#D6DEEA; --suave:#EDF2F8; --papel:#FFFFFF;
  }}

  /* ---------- base ---------- */
  html, body, [class*="css"] {{ font-family:"Inter","Segoe UI",system-ui,sans-serif; }}
  [data-testid="stAppViewContainer"] {{ background:#F5F8FC; }}
  [data-testid="stHeader"] {{ background:transparent; }}
  .block-container {{ padding-top:2.2rem; padding-bottom:4rem; max-width:1180px; }}

  h1 {{ color:var(--tinta); font-weight:800; letter-spacing:-.02em; }}
  h2, h3 {{ color:var(--tinta); font-weight:700; letter-spacing:-.01em; }}

  /* ---------- barra lateral ---------- */
  [data-testid="stSidebar"] {{ background:var(--tinta); }}
  [data-testid="stSidebar"] * {{ color:#E8EEF7 !important; }}
  [data-testid="stSidebar"] h1,
  [data-testid="stSidebar"] h2 {{ color:#FFFFFF !important; }}
  [data-testid="stSidebar"] a {{ border-radius:9px; }}
  [data-testid="stSidebar"] [data-testid="stSidebarNav"] a:hover {{ background:rgba(255,255,255,.10); }}
  [data-testid="stSidebar"] .stButton > button {{
    background:rgba(255,255,255,.12); border:1px solid rgba(255,255,255,.25);
    color:#FFFFFF !important; font-weight:600;
  }}
  [data-testid="stSidebar"] .stButton > button:hover {{ background:rgba(255,255,255,.22); }}

  /* ---------- tarjetas de saldo ---------- */
  [data-testid="stMetric"] {{
    background:var(--papel); border:1px solid var(--linea); border-radius:14px;
    padding:16px 18px;
    box-shadow:0 1px 2px rgba(39,59,117,.05), 0 12px 24px -20px rgba(39,59,117,.45);
  }}
  [data-testid="stMetricLabel"] p {{
    font-size:.80rem !important; font-weight:600; letter-spacing:.04em;
    text-transform:uppercase; color:#5A6B85 !important;
  }}
  [data-testid="stMetricValue"] {{
    color:var(--tinta); font-weight:800; font-size:1.85rem;
    font-variant-numeric:tabular-nums;
  }}

  /* ---------- botones ---------- */
  .stButton > button {{
    border-radius:12px; font-weight:600; min-height:2.9rem;
    border:1px solid var(--linea); background:var(--papel); color:var(--tinta);
    transition:transform .04s ease, box-shadow .12s ease;
  }}
  .stButton > button:hover {{ border-color:var(--azul); color:var(--azul); }}
  .stButton > button:active {{ transform:translateY(1px); }}
  .stButton > button[kind="primary"] {{
    background:var(--azul); border-color:var(--azul); color:#FFFFFF;
    box-shadow:0 8px 18px -10px rgba(53,100,158,.9);
  }}
  .stButton > button[kind="primary"]:hover {{ background:var(--tinta); border-color:var(--tinta); color:#FFF; }}

  /* botones grandes de operación */
  .op-grande .stButton > button {{
    min-height:5.2rem; font-size:1.02rem; line-height:1.3; padding:.7rem 1rem;
    white-space:normal; text-align:left; justify-content:flex-start;
  }}

  /* ---------- campos ---------- */
  [data-testid="stTextInput"] input,
  [data-testid="stNumberInput"] input,
  [data-testid="stTextArea"] textarea {{
    border-radius:10px; font-size:1.02rem;
  }}
  [data-testid="stNumberInput"] input {{ font-weight:700; font-size:1.15rem; color:var(--tinta); }}
  label p {{ font-weight:600 !important; color:#3A4A64 !important; }}

  /* ---------- pestañas ---------- */
  .stTabs [data-baseweb="tab-list"] {{ gap:6px; border-bottom:1px solid var(--linea); }}
  .stTabs [data-baseweb="tab"] {{
    height:2.9rem; border-radius:10px 10px 0 0; padding:0 18px;
    font-weight:600; color:#5A6B85;
  }}
  .stTabs [aria-selected="true"] {{ background:var(--suave); color:var(--tinta) !important; }}

  /* ---------- tablas ---------- */
  [data-testid="stDataFrame"] {{ border:1px solid var(--linea); border-radius:12px; }}

  /* ---------- avisos ---------- */
  [data-testid="stAlert"] {{ border-radius:12px; border-left-width:5px; }}

  /* ---------- piezas propias ---------- */
  .cinta {{
    background:linear-gradient(100deg, var(--tinta), var(--azul) 62%, var(--celeste));
    color:#FFF; border-radius:16px; padding:20px 24px; margin-bottom:22px;
  }}
  .cinta h1 {{ color:#FFF !important; margin:0; font-size:1.9rem; }}
  .cinta p {{ margin:6px 0 0; opacity:.88; font-size:1rem; }}

  .tapado {{ letter-spacing:.16em; color:#94A3B8; }}
</style>
"""


# ------------------------------------------------------------- arranque

def estilos(titulo: str, subtitulo: str | None = None,
            correo: str | None = None, al_salir=None) -> None:
    """Pinta la paleta, la cinta del título y la barra lateral.

    Se llama una vez al principio de cada pantalla.
    """
    st.markdown(_CSS, unsafe_allow_html=True)

    # Los montos arrancan TAPADOS en cada apertura o recarga.
    if "ocultar" not in st.session_state:
        st.session_state["ocultar"] = True

    with st.sidebar:
        st.markdown("### Sistema de Cajas")
        if correo:
            st.caption(correo)
        st.divider()

        tapado = st.session_state["ocultar"]
        if st.button("Mostrar los montos" if tapado else "Ocultar los montos",
                     use_container_width=True, key="btn_ocultar"):
            st.session_state["ocultar"] = not tapado
            st.rerun()
        st.caption("Los montos salen tapados cada vez que se abre la aplicación."
                   if tapado else "Los montos están a la vista.")

        if al_salir:
            st.divider()
            if st.button("Cerrar sesión", use_container_width=True, key="btn_salir"):
                al_salir()

    sub = f"<p>{subtitulo}</p>" if subtitulo else ""
    st.markdown(f'<div class="cinta"><h1>{titulo}</h1>{sub}</div>',
                unsafe_allow_html=True)


def tapado() -> bool:
    return bool(st.session_state.get("ocultar", True))


def monto(valor, decimales: int = 2) -> str:
    """El monto formateado, o puntos si están tapados."""
    from lib import db
    if tapado():
        return "• • • •"
    return db.dinero(valor, decimales)


def saldo_tarjeta(col, etiqueta: str, valor, ayuda: str | None = None,
                  decimales: int = 2) -> None:
    col.metric(etiqueta, monto(valor, decimales), help=ayuda)


# ------------------------------------------------- selector de operación

def selector(opciones: dict[str, str], clave: str, por_fila: int = 2) -> str:
    """Botones grandes en vez de una lista de puntitos.

    `opciones` es {código: "Texto visible"}. Devuelve el código elegido.
    """
    if clave not in st.session_state:
        st.session_state[clave] = next(iter(opciones))

    st.markdown('<div class="op-grande">', unsafe_allow_html=True)
    codigos = list(opciones)
    for i in range(0, len(codigos), por_fila):
        cols = st.columns(por_fila)
        for col, cod in zip(cols, codigos[i:i + por_fila]):
            elegido = st.session_state[clave] == cod
            if col.button(opciones[cod], key=f"{clave}_{cod}",
                          type="primary" if elegido else "secondary",
                          use_container_width=True):
                st.session_state[clave] = cod
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
    return st.session_state[clave]


# ------------------------------------------------------------- tablas

def tabla_movimientos(df, con_saldos: bool = False, alto: int | None = None):
    """Lista de movimientos con nombres en español y montos alineados."""
    import pandas as pd

    if df is None or len(df) == 0:
        st.info("No hay movimientos para mostrar.")
        return

    d = pd.DataFrame(df).copy()
    d["Movimiento"] = d["tipo"].map(ETIQUETAS).fillna(d["tipo"])
    if "fecha" in d:
        d["Cuándo"] = pd.to_datetime(d["fecha"]).dt.strftime("%d/%m %H:%M")

    columnas = ["id", "Cuándo", "caja", "Movimiento", "monto",
                "delta_efectivo", "delta_sistema"]
    if con_saldos:
        columnas += ["efectivo_despues", "sistema_despues"]
    columnas += ["beneficiario", "motivo"]
    if "anulado" in d:
        columnas += ["anulado"]
    columnas = [c for c in columnas if c in d.columns]

    oculto = tapado()
    fmt = "···" if oculto else "%.2f"
    fmt_mas = "···" if oculto else "%+.2f"

    # height=None ya no se acepta en las versiones nuevas de Streamlit:
    # el alto solo se pasa cuando de verdad se pidió uno.
    extra = {"height": int(alto)} if alto else {}
    st.dataframe(
        d[columnas], hide_index=True, use_container_width=True, **extra,
        column_config={
            "id": st.column_config.NumberColumn("#", width="small"),
            "Cuándo": st.column_config.TextColumn("Cuándo", width="small"),
            "caja": st.column_config.TextColumn("Caja", width="small"),
            "monto": st.column_config.NumberColumn("Monto", format=fmt),
            "delta_efectivo": st.column_config.NumberColumn("Movió caja", format=fmt_mas),
            "delta_sistema": st.column_config.NumberColumn("Movió sistema", format=fmt_mas),
            "efectivo_despues": st.column_config.NumberColumn("Quedó en caja", format=fmt),
            "sistema_despues": st.column_config.NumberColumn("Quedó en sistema", format=fmt),
            "beneficiario": st.column_config.TextColumn("Para quién"),
            "motivo": st.column_config.TextColumn("Motivo"),
            "anulado": st.column_config.CheckboxColumn("Anulado", width="small"),
        },
    )
