-- =====================================================================
--  SISTEMA DE CAJAS · 09 · PRECIOS DE RECARGA Y SALDOS EN REPORTES
--
--  1. Nueva regla de precio de recarga, una sola para todos los casos:
--     se le cobra al cliente el PRIMER precio de cierre que sea
--     ESTRICTAMENTE MAYOR al valor que muestra la plataforma.
--     Pasado el último cierre, sigue de $0,50 en $0,50.
--
--       2,05 -> 2,20      2,20 -> 2,50      2,50 -> 3,00
--       3,20 -> 3,30      3,30 -> 3,50      3,50 -> 4,00
--       5,15 -> 5,50      5,50 -> 6,00
--
--     Reemplaza la tabla de tramos anterior, que ya no se usa.
--
--  2. Una vista para ver, movimiento por movimiento, cómo quedaron el
--     efectivo y el saldo después de cada uno.
--
--  Se puede correr dos veces.
--  Ejecutar después de 08_deudas_iniciales.sql
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. LOS PRECIOS DE CIERRE
--    Editables desde aquí o desde Supabase. Agregar un cierre nuevo es
--    insertar una fila; quitar uno es poner activo = false.
-- ---------------------------------------------------------------------
create table if not exists precios_cierre (
  precio  numeric(14,4) primary key,
  activo  boolean not null default true,
  notas   text
);

delete from precios_cierre;

insert into precios_cierre (precio, notas) values
  (1.10, 'Recargas de $1 a $1,05'),
  (1.50, 'Recargas hasta $1,45'),
  (2.00, 'Recargas hasta $1,95'),
  (2.20, 'Las de 2 cierran aquí'),
  (2.50, 'Desde $2,20'),
  (3.00, 'Desde $2,50'),
  (3.30, 'Las de 3 cierran aquí'),
  (3.50, 'Desde $3,30'),
  (4.00, 'Desde $3,50'),
  (4.50, 'Desde $4,00');

-- ---------------------------------------------------------------------
-- 2. LA REGLA
-- ---------------------------------------------------------------------
create or replace function precio_recarga(p_monto numeric)
returns numeric
language plpgsql
stable
as $$
declare
  v_precio numeric(14,4);
  v_paso   numeric(14,4) := 0.50;   -- el escalón de $5 en adelante
begin
  if p_monto is null or p_monto <= 0 then
    return 0;
  end if;

  -- El primer cierre estrictamente mayor al valor.
  select min(pc.precio) into v_precio
  from precios_cierre pc
  where pc.activo and pc.precio > p_monto;

  if v_precio is not null then
    return v_precio;
  end if;

  -- Pasado el último cierre: el siguiente múltiplo de $0,50, y si el
  -- valor ya es múltiplo exacto, el siguiente (5,50 se cobra 6,00).
  return round(floor(p_monto / v_paso) * v_paso + v_paso, 2);
end;
$$;

-- La tabla de tramos vieja queda sin uso.
drop table if exists precios_recarga cascade;

-- ---------------------------------------------------------------------
-- 3. SALDOS MOVIMIENTO A MOVIMIENTO
--    Después de cada línea, cuánto quedó en la gaveta y cuánto en el
--    sistema de esa caja. Sirve para seguir el rastro de un retiro y
--    comprobar que los dos lados se movieron como debían.
-- ---------------------------------------------------------------------
create or replace view v_movimientos_saldos as
select
  m.id,
  m.fecha,
  c.nombre                                            as caja,
  m.caja_id,
  m.tipo,
  m.monto,
  m.comision_local,
  m.comision_proveedor,
  (m.comision_local + m.comision_proveedor)           as ganancia,
  m.delta_efectivo,
  m.delta_sistema,
  c.efectivo_inicial + sum(m.delta_efectivo) over w   as efectivo_despues,
  c.sistema_inicial  + sum(m.delta_sistema)  over w   as sistema_despues,
  m.comision_forma,
  m.cuenta_comision,
  m.beneficiario,
  m.motivo,
  m.operador,
  m.referencia,
  m.corte_id,
  m.anulado,
  m.reversa_de
from movimientos m
join cajas c on c.id = m.caja_id
window w as (partition by m.caja_id
             order by m.fecha, m.id
             rows between unbounded preceding and current row);

-- ---------------------------------------------------------------------
-- 4. PERMISOS
-- ---------------------------------------------------------------------
alter table precios_cierre enable row level security;
drop policy if exists "leer cierres"   on precios_cierre;
drop policy if exists "editar cierres" on precios_cierre;
create policy "leer cierres"   on precios_cierre for select to authenticated using (true);
create policy "editar cierres" on precios_cierre for all    to authenticated using (true) with check (true);

grant select  on precios_cierre, v_movimientos_saldos to authenticated;
grant execute on function precio_recarga(numeric)     to authenticated;

-- ---------------------------------------------------------------------
-- 5. COMPROBACIÓN — debe salir exactamente esto:
--      1,00→1,10  1,05→1,10  1,95→2,00  2,05→2,20  2,20→2,50
--      2,50→3,00  3,20→3,30  3,30→3,50  3,50→4,00  4,30→4,50
--      5,15→5,50  5,50→6,00  10,00→10,50
-- ---------------------------------------------------------------------
select v                          as "valor plataforma",
       precio_recarga(v)          as "se cobra",
       precio_recarga(v) - v      as "comision fisica"
from (values (1.00),(1.05),(1.95),(2.05),(2.20),(2.50),(3.20),(3.30),
             (3.50),(4.30),(5.15),(5.50),(10.00)) t(v);
