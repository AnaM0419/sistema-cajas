-- =====================================================================
--  SISTEMA DE CAJAS · 04 · SEGURIDAD (RLS)
--  Las 2-5 personas tienen el mismo rol: quien inició sesión puede
--  trabajar; quien no, no ve nada.
--  Ejecutar después de 03_datos.sql
-- =====================================================================

alter table cajas       enable row level security;
alter table tarifas     enable row level security;
alter table movimientos enable row level security;
alter table deudas      enable row level security;
alter table cortes      enable row level security;

-- Lectura: cualquier usuario autenticado
create policy "leer cajas"       on cajas       for select to authenticated using (true);
create policy "leer tarifas"     on tarifas     for select to authenticated using (true);
create policy "leer movimientos" on movimientos for select to authenticated using (true);
create policy "leer deudas"      on deudas      for select to authenticated using (true);
create policy "leer cortes"      on cortes      for select to authenticated using (true);

-- Escritura
create policy "registrar movimientos" on movimientos for insert to authenticated with check (true);
create policy "registrar deudas"      on deudas      for insert to authenticated with check (true);
create policy "actualizar deudas"     on deudas      for update to authenticated using (true);
create policy "editar tarifas"        on tarifas     for all    to authenticated using (true) with check (true);
create policy "editar cajas"          on cajas       for update to authenticated using (true);
create policy "crear cortes"          on cortes      for insert to authenticated with check (true);

-- Ojo: los movimientos NO tienen policy de UPDATE ni de DELETE a propósito.
-- Un movimiento registrado no se toca; se anula con anular_movimiento(),
-- que corre con permisos elevados y deja el rastro.

-- Las vistas heredan el RLS de las tablas que consultan.
grant select on v_saldos, v_alertas, v_movimientos_full to authenticated;
grant execute on function anular_movimiento(bigint, text)                      to authenticated;
grant execute on function buscar_tarifa(smallint, text, text, text, numeric)   to authenticated;
grant execute on function cerrar_corte(smallint, text, numeric, numeric, text) to authenticated;
