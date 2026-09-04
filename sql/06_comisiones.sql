-- =====================================================================
--  SISTEMA DE CAJAS · 06 · COMISIONES CORREGIDAS
--
--  CAMBIO DE FONDO: la comisión del proveedor NO es un costo, es un
--  ingreso. Facilito le entrega a la caja un valor por cada movimiento,
--  abonado al propio saldo prepagado. Antes estaba restada; ahora suma.
--
--      ganancia = comisión que cobras al cliente + comisión del proveedor
--
--  Además, esa comisión llega con fracciones de centavo ($0,051), así
--  que los montos pasan de dos a cuatro decimales. Con dos decimales,
--  cada movimiento perdía hasta medio centavo por redondeo, y sobre
--  miles de recargas eso es plata que desaparece sin explicación.
--
--  Ejecutar después de 05_deudas.sql
-- =====================================================================

drop view if exists v_alertas          cascade;
drop view if exists v_saldos           cascade;
drop view if exists v_movimientos_full cascade;

-- ---------------------------------------------------------------------
-- 1. El nombre correcto
-- ---------------------------------------------------------------------
do $$
begin
  if exists (select 1 from information_schema.columns
             where table_name = 'movimientos' and column_name = 'comision_sistema') then
    alter table movimientos rename column comision_sistema to comision_proveedor;
  end if;
end
$$;

comment on column movimientos.comision_proveedor is
  'Lo que el proveedor te ENTREGA por el movimiento. Es ingreso, no costo.';
comment on column movimientos.comision_local is
  'Lo que le cobras al cliente. También es ingreso.';

-- ---------------------------------------------------------------------
-- 2. Cuatro decimales donde hacen falta
-- ---------------------------------------------------------------------
alter table movimientos
  alter column comision_local     type numeric(12,4),
  alter column comision_proveedor type numeric(12,4),
  alter column delta_efectivo     type numeric(14,4),
  alter column delta_sistema      type numeric(14,4),
  alter column monto              type numeric(14,4),
  alter column recargo            type numeric(12,4);

alter table cajas
  alter column efectivo_inicial type numeric(14,4),
  alter column sistema_inicial  type numeric(14,4);

-- Los rangos también: si monto_desde se queda en dos decimales, el
-- 150,0001 que separa "$0,50" de "$1" se redondea a 150,00 y un pago de
-- exactamente $150 cae en el tramo equivocado.
alter table tarifas
  alter column comision_fija type numeric(12,4),
  alter column monto_desde   type numeric(14,4),
  alter column monto_hasta   type numeric(14,4);

alter table cortes
  alter column efectivo_inicial    type numeric(14,4),
  alter column efectivo_esperado   type numeric(14,4),
  alter column efectivo_contado    type numeric(14,4),
  alter column diferencia_efectivo type numeric(14,4),
  alter column sistema_inicial     type numeric(14,4),
  alter column sistema_esperado    type numeric(14,4),
  alter column sistema_reportado   type numeric(14,4),
  alter column diferencia_sistema  type numeric(14,4),
  alter column comisiones_periodo  type numeric(14,4);

-- ---------------------------------------------------------------------
-- 3. 'sistema' pasa a llamarse 'proveedor' en la tabla de tarifas
-- ---------------------------------------------------------------------
alter table tarifas drop constraint if exists tarifas_quien_cobra_check;
update tarifas set quien_cobra = 'proveedor' where quien_cobra = 'sistema';
alter table tarifas add constraint tarifas_quien_cobra_check
  check (quien_cobra in ('proveedor','local'));

comment on column tarifas.quien_cobra is
  'local = lo que cobras al cliente · proveedor = lo que el proveedor te entrega. Las dos son ingreso.';

-- ---------------------------------------------------------------------
-- 4. La regla de Facilito, corregida
--
--    El cliente entrega en efectivo el valor más tu comisión.
--    Del saldo prepagado te descuentan el valor MENOS lo que el
--    proveedor te reconoce.
--
--    Ejemplo: recarga de $15,50, le cobras $0,25 al cliente y el
--    proveedor te reconoce $0,051.
--        efectivo  +15,7500
--        saldo     -15,4490
--        ganancia    0,3010
-- ---------------------------------------------------------------------
create or replace function fn_calcular_deltas()
returns trigger
language plpgsql
as $$
declare
  ef numeric(14,4) := 0;
  si numeric(14,4) := 0;
begin
  if new.reversa_de is not null then
    return new;
  end if;

  case new.tipo

    when 'retiro' then
      ef := -new.monto + case when new.comision_forma = 'fisica' then new.comision_local else 0 end;
      si :=  new.monto + case when new.comision_forma = 'sistema' then new.comision_local else 0 end;

    when 'deposito' then
      ef :=  new.monto + new.comision_local;
      si := -new.monto;

    when 'salida_sistema'  then si := -new.monto;
    when 'salida_efectivo' then ef := -new.monto;

    when 'acreditacion' then
      ef := -new.monto - case when new.hubo_recargo then new.recargo else 0 end;
      si :=  new.monto;
      new.cuenta_comision := false;

    when 'cobro_deuda_efectivo' then ef := new.monto;
    when 'cobro_deuda_sistema'  then si := new.monto;

    when 'traspaso_envio_efectivo'     then ef := -new.monto;
    when 'traspaso_recepcion_efectivo' then ef :=  new.monto;
    when 'traspaso_envio_sistema'      then si := -new.monto;
    when 'traspaso_recepcion_sistema'  then si :=  new.monto;

    when 'facilito_recarga', 'facilito_juego', 'facilito_servicio' then
      ef :=   new.monto + new.comision_local;
      si := -(new.monto - new.comision_proveedor);

    when 'ajuste' then
      ef := new.delta_efectivo;
      si := new.delta_sistema;

    else
      raise exception 'Tipo de movimiento desconocido: %', new.tipo;
  end case;

  new.delta_efectivo := ef;
  new.delta_sistema  := si;
  return new;
end;
$$;

-- ---------------------------------------------------------------------
-- 5. Vistas, con la ganancia sumando las dos comisiones
-- ---------------------------------------------------------------------
create or replace view v_saldos as
select
  c.id                                                     as caja_id,
  c.nombre,
  c.tipo,
  c.efectivo_inicial + coalesce(sum(m.delta_efectivo), 0)  as efectivo,
  c.sistema_inicial  + coalesce(sum(m.delta_sistema),  0)  as sistema,
  coalesce((select sum(d.saldo_pendiente) from deudas d
             where d.caja_id = c.id and d.estado = 'abierta'), 0) as deuda,
  c.alerta_sistema_aviso,
  c.alerta_sistema_critico,
  c.alerta_efectivo_aviso,
  c.alerta_efectivo_critico,
  c.alerta_efectivo_tope
from cajas c
left join movimientos m on m.caja_id = c.id
where c.activa
group by c.id;

create or replace view v_alertas as
select nombre as caja, 'critico' as nivel,
       'Saldo del sistema en $' || to_char(sistema, 'FM999990.00')
       || ' — hay que acreditar dinero de la caja ya.' as mensaje
from v_saldos
where alerta_sistema_critico is not null and sistema <= alerta_sistema_critico
union all
select nombre, 'aviso',
       'Saldo del sistema en $' || to_char(sistema, 'FM999990.00')
       || ' — conviene acreditar pronto.'
from v_saldos
where alerta_sistema_aviso is not null and sistema <= alerta_sistema_aviso
  and (alerta_sistema_critico is null or sistema > alerta_sistema_critico)
union all
select nombre, 'critico',
       'Efectivo en $' || to_char(efectivo, 'FM999990.00')
       || ' — no alcanza para retiros grandes.'
from v_saldos
where alerta_efectivo_critico is not null and efectivo <= alerta_efectivo_critico
union all
select nombre, 'aviso',
       'Efectivo en $' || to_char(efectivo, 'FM999990.00') || ' — queda poco.'
from v_saldos
where alerta_efectivo_aviso is not null and efectivo <= alerta_efectivo_aviso
  and (alerta_efectivo_critico is null or efectivo > alerta_efectivo_critico)
union all
select nombre, 'aviso',
       'Efectivo en $' || to_char(efectivo, 'FM999990.00')
       || ' — pasa del tope, toca depositar.'
from v_saldos
where alerta_efectivo_tope is not null and efectivo >= alerta_efectivo_tope;

create or replace view v_movimientos_full as
select
  m.id, m.fecha, c.nombre as caja, m.tipo, m.monto,
  m.comision_local, m.comision_proveedor,
  (m.comision_local + m.comision_proveedor) as ganancia,
  m.comision_forma, m.cuenta_comision,
  m.beneficiario, m.motivo, m.operador, m.referencia,
  m.delta_efectivo, m.delta_sistema,
  m.corte_id, m.anulado, m.reversa_de, m.deuda_id
from movimientos m
join cajas c on c.id = m.caja_id;

-- ---------------------------------------------------------------------
-- 6. El corte suma las dos comisiones
-- ---------------------------------------------------------------------
create or replace function cerrar_corte(
  p_caja              smallint,
  p_tipo              text,
  p_efectivo_contado  numeric,
  p_sistema_reportado numeric default null,
  p_notas             text    default null
) returns cortes
language plpgsql
security definer
as $$
declare
  v_desde     timestamptz;
  v_hasta     timestamptz := now();
  v_ef_ini    numeric(14,4);
  v_si_ini    numeric(14,4);
  v_ef_delta  numeric(14,4);
  v_si_delta  numeric(14,4);
  v_n         integer;
  v_com       numeric(14,4);
  v_cobrar    numeric(12,2);
  v_pagar     numeric(12,2);
  v_corte     cortes;
begin
  select c.hasta, c.efectivo_contado, coalesce(c.sistema_reportado, c.sistema_esperado)
    into v_desde, v_ef_ini, v_si_ini
  from cortes c
  where c.caja_id = p_caja
  order by c.hasta desc
  limit 1;

  if not found then
    select cj.creada_en, cj.efectivo_inicial, cj.sistema_inicial
      into v_desde, v_ef_ini, v_si_ini
    from cajas cj where cj.id = p_caja;
  end if;

  select coalesce(sum(m.delta_efectivo), 0),
         coalesce(sum(m.delta_sistema),  0),
         count(*),
         coalesce(sum(case when m.cuenta_comision
                           then m.comision_local + m.comision_proveedor
                           else 0 end), 0)
    into v_ef_delta, v_si_delta, v_n, v_com
  from movimientos m
  where m.caja_id = p_caja and m.corte_id is null and m.fecha <= v_hasta;

  select por_cobrar, por_pagar into v_cobrar, v_pagar
  from v_deuda_por_caja where caja_id = p_caja;

  insert into cortes (
    caja_id, tipo, desde, hasta,
    efectivo_inicial, efectivo_esperado, efectivo_contado, diferencia_efectivo,
    sistema_inicial,  sistema_esperado,  sistema_reportado, diferencia_sistema,
    deuda_total, deuda_por_pagar, n_movimientos, comisiones_periodo, notas
  ) values (
    p_caja, p_tipo, v_desde, v_hasta,
    v_ef_ini, v_ef_ini + v_ef_delta, p_efectivo_contado,
    p_efectivo_contado - (v_ef_ini + v_ef_delta),
    v_si_ini, v_si_ini + v_si_delta, p_sistema_reportado,
    case when p_sistema_reportado is null then null
         else p_sistema_reportado - (v_si_ini + v_si_delta) end,
    coalesce(v_cobrar, 0), coalesce(v_pagar, 0),
    v_n, v_com, p_notas
  ) returning * into v_corte;

  update movimientos
     set corte_id = v_corte.id
   where caja_id = p_caja and corte_id is null and fecha <= v_hasta;

  if v_corte.diferencia_efectivo <> 0 or coalesce(v_corte.diferencia_sistema, 0) <> 0 then
    insert into movimientos (
      caja_id, tipo, monto, cuenta_comision, motivo,
      delta_efectivo, delta_sistema, corte_id
    ) values (
      p_caja, 'ajuste', 0, false,
      'Descuadre del corte #' || v_corte.id,
      v_corte.diferencia_efectivo,
      coalesce(v_corte.diferencia_sistema, 0),
      v_corte.id
    );
  end if;

  return v_corte;
end;
$$;

-- ---------------------------------------------------------------------
-- 7. LAS TARIFAS QUE YA ESTÁN DEFINIDAS
--
--    Bancos (Pichincha y Guayaquil): $0,50 hasta $199,99 · $1,00 de $200
--    Facilito, pago de servicio:     $0,50 hasta $150,00 · $1,00 sobre $150
--
--    Las recargas y los juegos quedan pendientes: son cambiantes y se
--    cargan desde la pantalla Tarifas cuando tengas la tabla.
-- ---------------------------------------------------------------------
delete from tarifas
where tipo in ('retiro','deposito')
  and caja_id in (select id from cajas where tipo = 'banco');

insert into tarifas (caja_id, quien_cobra, tipo, monto_desde, monto_hasta,
                     comision_fija, notas)
select c.id, 'local', t.tipo, r.desde, r.hasta, r.comision, r.nota
from cajas c
cross join (values ('retiro'), ('deposito')) as t(tipo)
cross join (values
  (0::numeric,      199.9999::numeric, 0.50::numeric, 'Hasta $199,99'),
  (200::numeric,    null::numeric,     1.00::numeric, 'Desde $200')
) as r(desde, hasta, comision, nota)
where c.tipo = 'banco';

-- Facilito: se rehace por si el umbral quedó mal cargado antes.
delete from tarifas
where tipo = 'servicio' and caja_id in (select id from cajas where tipo = 'facilito');

insert into tarifas (caja_id, quien_cobra, tipo, monto_desde, monto_hasta,
                     comision_fija, notas)
select c.id, 'local', 'servicio', r.desde, r.hasta, r.comision, r.nota
from cajas c
cross join (values
  (0::numeric,      150::numeric,  0.50::numeric, 'Pago de servicio hasta $150'),
  (150.0001::numeric, null::numeric, 1.00::numeric, 'Pago de servicio superior a $150')
) as r(desde, hasta, comision, nota)
where c.tipo = 'facilito';

-- ---------------------------------------------------------------------
-- 8. Permisos de las vistas recreadas
-- ---------------------------------------------------------------------
grant select on v_saldos, v_alertas, v_movimientos_full to authenticated;
grant execute on function cerrar_corte(smallint, text, numeric, numeric, text) to authenticated;
