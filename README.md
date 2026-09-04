# Sistema de Cajas

Control de flujo de efectivo, saldo en cuenta y deuda para las cajas de
Pichincha, Guayaquil y Facilito.

## Puesta en marcha rápida

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # y pega tus datos de Supabase
streamlit run app.py
```

En Supabase, ejecutar los archivos de `sql/` **en orden**:
`01_esquema.sql` → `02_reglas.sql` → `03_datos.sql` → `04_seguridad.sql` →
`05_deudas.sql` → `06_comisiones.sql`.

## Cómo está armado

La idea central: el sistema no guarda "operaciones", guarda **efectos**.
Cada movimiento escribe dos números, `delta_efectivo` y `delta_sistema`,
que los calcula un trigger en la base de datos. El corte de caja es
entonces una suma, y agregar un tipo de movimiento nuevo es agregar una
rama al `CASE` de `fn_calcular_deltas()` — nada más se toca.

| Archivo | Qué contiene |
|---|---|
| `sql/01_esquema.sql` | Las cinco tablas |
| `sql/02_reglas.sql` | **Toda la lógica del flujo de caja** |
| `sql/03_datos.sql` | Las tres cajas y las tarifas conocidas |
| `sql/04_seguridad.sql` | Permisos (RLS) |
| `sql/05_deudas.sql` | Deudas por caja, por persona y entre cajas |
| `sql/06_comisiones.sql` | Comisiones corregidas, umbrales y 4 decimales |
| `app.py` | Tablero: saldos y alertas |
| `pages/1_Registrar.py` | Retiros, depósitos, salidas, acreditaciones |
| `pages/2_Facilito.py` | Recargas, juegos, servicios, compra de saldo |
| `pages/3_Cortes.py` | Cortes de turno y diarios de las tres cajas |
| `pages/4_Deudas.py` | Deudas: resumen, quién debe, abonos y préstamos |
| `pages/5_Tarifas.py` | Las dos tablas de comisiones, editables |
| `pages/6_Reportes.py` | Filtros, resúmenes y descarga a Excel |

## Reglas de oro

1. **Un movimiento no se borra ni se edita.** Se anula con
   `anular_movimiento()`, que crea el espejo. Los dos quedan en el historial.
2. **Las comisiones no van en el código.** Viven en la tabla `tarifas` y se
   editan desde la app. Las dos son ingreso: lo que cobras al cliente **más**
   lo que el proveedor te reconoce.
3. **La lógica vive en la base, no en la pantalla.** Si mañana cambias
   Streamlit por otra cosa, las reglas siguen intactas.
4. **Las deudas entre cajas se compensan solas.** Si dos cajas se deben
   mutuamente, el sistema muestra solo el neto: lo que de verdad falta mover.

## Comisiones vigentes

| Caja | Movimiento | Comisión |
|---|---|---|
| Pichincha y Guayaquil | retiro y depósito hasta $199,99 | $0,50 |
| Pichincha y Guayaquil | retiro y depósito desde $200 | $1,00 |
| Facilito | pago de servicio hasta $150 | $0,50 |
| Facilito | pago de servicio sobre $150 | $1,00 |
| Facilito | recargas y juegos | pendiente, se cargan desde la app |

La comisión del proveedor se abona al saldo Facilito, así que del saldo se
descuenta el valor **menos** esa comisión. Los montos se guardan con cuatro
decimales porque esa comisión trae fracciones de centavo.

## Pendiente

- La tabla real de recargas y juegos de Facilito, por operador y rango, en
  sus dos versiones: lo que cobras y lo que el proveedor te reconoce.
