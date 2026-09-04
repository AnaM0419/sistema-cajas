"""Lectura de comprobantes de Facilito desde una foto.

Usa la API de Gemini, que tiene capa gratuita. Si no hay clave configurada,
la app sigue funcionando: solo se desactiva la pestaña de la foto.

Para activarla, agrega a tu .env (y a los secrets de Streamlit Cloud):
    GEMINI_API_KEY=...

La clave se saca gratis en https://aistudio.google.com/apikey
"""

import base64
import json
import os
import re
import difflib

import requests

MODELO = os.getenv("GEMINI_MODELO", "gemini-2.0-flash")
URL = "https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"

INSTRUCCION = """Eres un lector de comprobantes de la plataforma Facilito (Ecuador).
De la imagen extrae solo dos datos y responde ÚNICAMENTE con este JSON:

{"producto": "<nombre del producto tal como aparece>", "valor": <número>}

Reglas:
- "producto" es el nombre del servicio o recarga, por ejemplo "TUENTI - PAQ",
  "CLARO - MEGAS", "AGUA - CHONE". Cópialo literal, sin traducir ni corregir.
- "valor" es el monto de la transacción en dólares, como número sin símbolo.
  Si aparecen varios montos, toma el valor de la recarga o del pago, no el
  total con comisiones ni el saldo.
- Si no puedes leer alguno de los dos con seguridad, ponlo en null.
No agregues explicaciones ni texto fuera del JSON."""


def hay_clave() -> bool:
    return bool(_clave())


def _clave() -> str | None:
    clave = os.getenv("GEMINI_API_KEY")
    if clave:
        return clave
    try:
        import streamlit as st
        return st.secrets.get("GEMINI_API_KEY")
    except Exception:
        return None


def leer_comprobante(imagen: bytes, mime: str = "image/jpeg") -> dict:
    """Devuelve {'producto': str|None, 'valor': float|None, 'error': str|None}."""
    clave = _clave()
    if not clave:
        return {"producto": None, "valor": None,
                "error": "No hay GEMINI_API_KEY configurada."}

    cuerpo = {
        "contents": [{
            "parts": [
                {"text": INSTRUCCION},
                {"inline_data": {"mime_type": mime,
                                 "data": base64.b64encode(imagen).decode()}},
            ]
        }],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 200},
    }

    try:
        r = requests.post(URL.format(m=MODELO), params={"key": clave},
                          json=cuerpo, timeout=30)
        r.raise_for_status()
        texto = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return {"producto": None, "valor": None, "error": f"No se pudo leer: {e}"}

    # el modelo a veces envuelve el JSON en ```json ... ```
    limpio = re.sub(r"^```(?:json)?|```$", "", texto.strip(), flags=re.M).strip()
    try:
        d = json.loads(limpio)
    except Exception:
        return {"producto": None, "valor": None,
                "error": f"Respuesta inesperada del lector: {texto[:120]}"}

    valor = d.get("valor")
    try:
        valor = float(valor) if valor is not None else None
    except (TypeError, ValueError):
        valor = None

    return {"producto": d.get("producto"), "valor": valor, "error": None}


def emparejar(leido: str | None, productos: list[dict], n: int = 5) -> list[dict]:
    """Ordena los productos por parecido con lo que se leyó en la foto.

    Los nombres de la base traen prefijo de familia ('MRF - TUENTI - PAQ.')
    y el comprobante normalmente no, así que se compara contra las dos formas.
    """
    if not leido:
        return []

    objetivo = _normalizar(leido)
    indice = {}
    for p in productos:
        completo = _normalizar(p["nombre"])
        sin_familia = _normalizar(p["nombre"].split(" - ", 1)[-1])
        indice.setdefault(completo, p)
        indice.setdefault(sin_familia, p)

    claves = list(indice)
    cercanos = difflib.get_close_matches(objetivo, claves, n=n * 2, cutoff=0.45)

    vistos, salida = set(), []
    for c in cercanos:
        p = indice[c]
        if p["id"] not in vistos:
            vistos.add(p["id"])
            salida.append(p)
    return salida[:n]


def _normalizar(t: str) -> str:
    t = t.upper().strip()
    t = t.replace("Á", "A").replace("É", "E").replace("Í", "I")
    t = t.replace("Ó", "O").replace("Ú", "U").replace("Ñ", "N")
    return re.sub(r"[^A-Z0-9 ]+", " ", t).strip()
