-- =====================================================================
--  SISTEMA DE CAJAS · 03 · DATOS INICIALES
--  Cambia los saldos y los umbrales por los tuyos reales antes de usar.
--  Ejecutar después de 02_reglas.sql
-- =====================================================================

insert into cajas (nombre, tipo, efectivo_inicial, sistema_inicial,
                   alerta_sistema_aviso, alerta_sistema_critico,
                   alerta_efectivo_aviso, alerta_efectivo_critico,
                   alerta_efectivo_tope)
values
  ('Pichincha', 'banco',    0, 0, 100, 50, 80, 30, 1000),
  ('Guayaquil', 'banco',    0, 0, 100, 50, 80, 30, 1000),
  ('Facilito',  'facilito', 0, 0, 100, 50, 80, 30, 1000);

-- ---------------------------------------------------------------------
-- TARIFAS DE FACILITO
-- 06_comisiones.sql vuelve a cargar estas dos filas con la precisión
-- correcta, así que aquí quedan solo como referencia.
-- Las recargas y los juegos se cargan desde la pantalla Tarifas.
-- ---------------------------------------------------------------------
insert into tarifas (caja_id, quien_cobra, tipo, operador,
                     monto_desde, monto_hasta, comision_fija, notas)
select id, 'local', 'servicio', null, 0, 150, 0.50,
       'Pago de servicio hasta $150'
from cajas where nombre = 'Facilito';

insert into tarifas (caja_id, quien_cobra, tipo, operador,
                     monto_desde, monto_hasta, comision_fija, notas)
select id, 'local', 'servicio', null, 150.01, null, 1.00,
       'Pago de servicio superior a $150'
from cajas where nombre = 'Facilito';

-- ---------------------------------------------------------------------
-- PLANTILLAS para cuando tengas las tablas reales.
-- Descomenta, duplica y ajusta. No hace falta tocar el código de la app:
-- también puedes cargarlas desde la pantalla Tarifas.
-- ---------------------------------------------------------------------
-- Lo que TÚ le cobras al cliente por una recarga Claro de $1 a $5:
-- insert into tarifas (caja_id, quien_cobra, tipo, operador, monto_desde, monto_hasta, comision_fija)
-- select id, 'local', 'recarga', 'Claro', 1, 5, 0.25 from cajas where nombre = 'Facilito';

-- Lo que FACILITO TE RECONOCE a ti por esa misma recarga (porcentaje):
-- insert into tarifas (caja_id, quien_cobra, tipo, operador, monto_desde, monto_hasta, comision_porcentaje)
-- select id, 'proveedor', 'recarga', 'Claro', 1, 5, 0.33 from cajas where nombre = 'Facilito';

-- Las comisiones de retiro y depósito de los bancos las carga 06_comisiones.sql:
--   $0,50 hasta $199,99 · $1,00 desde $200.
