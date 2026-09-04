-- =====================================================================
--  SISTEMA DE CAJAS · 02 · REGLAS DE NEGOCIO
--  Aquí vive TODA la lógica de flujo de caja. La app solo dice qué pasó;
--  la base decide cómo se mueven los saldos.
--  Ejecutar después de 01_esquema.sql
-- =====================================================================

-- ---------------------------------------------------------------------
-- TRIGGER DE EFECTOS
-- Traduce cada tipo de movimiento a sus dos deltas.
-- Para agregar un tipo nuevo en el futuro: una rama más en este CASE.
-- ---------------------------------------------------------------------
create or replace function fn_calcular_deltas()
returns trigger
language plpgsql
as $$
declare
  ef numeric(12,2) := 0;
  si numeric(12,2) := 0;
begin
  -- Un reverso trae los deltas ya invertidos por anular_movimiento().
  if new.reversa_de is not null then
    return new;
  end if;

  case new.tipo

    -- El cliente se lleva efectivo. Baja la gaveta, sube la cuenta.
    -- La comisión es el caso importante: puede quedarse en físico
    -- (entra a la gaveta) o venir acreditada junto al valor (sube la cuenta).
    when 'retiro' then
      ef := -new.monto + case when new.comision_forma = 'fisica' then new.comision_local else 0 end;
      si :=  new.monto + case when new.comision_forma = 'sistema' then new.comision_local else 0 end;

    -- El cliente entrega efectivo. La comisión siempre la paga en físico.
    when 'deposito' then
      ef :=  new.monto + new.comision_local;
      si := -new.monto;

    -- Sale plata de la cuenta hacia afuera. No toca la gaveta.
    when 'salida_sistema' then
      si := -new.monto;

    -- Sale efectivo de la gaveta hacia afuera.
    when 'salida_efectivo' then
      ef := -new.monto;

    -- Abonamos dinero propio a la cuenta: sale de la gaveta.
    -- El recargo, si lo hubo, también sale de la gaveta.
    -- No cuenta como transacción con comisión.
    when 'acreditacion' then
      ef := -new.monto - case when new.hubo_recargo then new.recargo else 0 end;
      si :=  new.monto;
      new.cuenta_comision := false;

    -- Alguien devuelve una deuda.
    when 'cobro_deuda_efectivo' then ef :=  new.monto;
    when 'cobro_deuda_sistema'  then si :=  new.monto;

    -- Traspasos entre cajas. La app inserta SIEMPRE los dos lados.
    -- El envío desde el sistema del banco + la recepción en el sistema de
    -- Facilito es exactamente la "compra de saldo Facilito".
    when 'traspaso_envio_efectivo'     then ef := -new.monto;
    when 'traspaso_recepcion_efectivo' then ef :=  new.monto;
    when 'traspaso_envio_sistema'      then si := -new.monto;
    when 'traspaso_recepcion_sistema'  then si :=  new.monto;

    -- Facilito: el cliente paga en efectivo el valor más nuestra comisión;
    -- el saldo prepagado baja el valor más lo que nos cobra el proveedor.
    -- El margen del negocio es comision_local - comision_sistema.
    when 'facilito_recarga', 'facilito_juego', 'facilito_servicio' then
      ef :=   new.monto + new.comision_local;
      si := -(new.monto + new.comision_sistema);

    -- Ajuste manual: se usa solo para cargar saldos o corregir con
    -- autorización. Los deltas vienen dados por quien lo registra.
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

drop trigger if exists trg_calcular_deltas on movimientos;
create trigger trg_calcular_deltas
  before insert on movimientos
  for each row execute function fn_calcular_deltas();

-- ---------------------------------------------------------------------
-- BLOQUEO DE MOVIMIENTOS CERRADOS
-- Un movimiento que ya entró en un corte no se edita ni se borra.
-- ---------------------------------------------------------------------
create or replace function fn_proteger_movimientos()
returns trigger
language plpgsql
as $$
begin
  if tg_op = 'DELETE' then
    raise exception 'Los movimientos no se borran. Usa anular_movimiento(%).', old.id;
  end if;
  if old.corte_id is not null and new.corte_id is not distinct from old.corte_id then
    raise exception 'El movimiento % pertenece al corte % y ya no se puede modificar.', old.id, old.corte_id;
  end if;
  return new;
end;
$$;

drop trigger if exists trg_proteger_movimientos on movimientos;
create trigger trg_proteger_movimientos
  before update or delete on movimientos
  for each row execute function fn_proteger_movimientos();

-- ---------------------------------------------------------------------
-- ANULAR
-- No borra: inserta el movimiento espejo con los deltas invertidos.
-- Los dos quedan en el historial y se anulan entre sí.
-- ---------------------------------------------------------------------
create or replace function anular_movimiento(p_id bigint, p_motivo text)
returns bigint
language plpgsql
security definer
as $$
declare
  m       movimientos;
  nuevo   bigint;
begin
  select * into m from movimientos where id = p_id;
  if not found then
    raise exception 'El movimiento % no existe.', p_id;
  end if;
  if m.anulado then
    raise exception 'El movimiento % ya fue anulado.', p_id;
  end if;
  if m.corte_id is not null then
    raise exception 'El movimiento % pertenece a un corte cerrado. Registra un ajuste en su lugar.', p_id;
  end if;

  insert into movimientos (
    caja_id, tipo, monto, comision_local, comision_sistema, comision_forma,
    cuenta_comision, hubo_recargo, recargo, beneficiario, motivo, operador,
    referencia, delta_efectivo, delta_sistema, reversa_de
  ) values (
    m.caja_id, m.tipo, m.monto, m.comision_local, m.comision_sistema, m.comision_forma,
    false, m.hubo_recargo, m.recargo, m.beneficiario,
    'REVERSO del #' || p_id || coalesce(' — ' || p_motivo, ''), m.operador,
    m.referencia, -m.delta_efectivo, -m.delta_sistema, p_id
  ) returning id into nuevo;

  update movimientos set anulado = true where id = p_id;

  update deudas
     set estado = 'condonada', saldo_pendiente = 0
   where movimiento_id = p_id and estado = 'abierta';

  return nuevo;
end;
$$;

-- ---------------------------------------------------------------------
-- BUSCAR TARIFA
-- Devuelve la comisión que corresponde a un movimiento.
-- Prioriza la fila más específica: operador exacto antes que genérico,
-- y el rango más alto que el monto alcance.
-- ---------------------------------------------------------------------
create or replace function buscar_tarifa(
  p_caja     smallint,
  p_quien    text,
  p_tipo     text,
  p_operador text,
  p_monto    numeric
) returns numeric
language sql
stable
as $$
  select round(coalesce(t.comision_fija, 0)
             + coalesce(t.comision_porcentaje, 0) * p_monto / 100, 2)
  from tarifas t
  where t.caja_id     = p_caja
    and t.quien_cobra = p_quien
    and t.tipo        = p_tipo
    and (t.operador is null or t.operador = p_operador)
    and p_monto >= t.monto_desde
    and (t.monto_hasta is null or p_monto <= t.monto_hasta)
    and t.vigente_desde <= current_date
    and (t.vigente_hasta is null or t.vigente_hasta >= current_date)
  order by (t.operador is not null) desc, t.monto_desde desc
  limit 1;
$$;

-- ---------------------------------------------------------------------
-- SALDOS EN VIVO
-- Nota: los movimientos anulados SÍ se suman, porque su reverso también
-- está sumado y los dos dan cero. Así el historial nunca miente.
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

-- ---------------------------------------------------------------------
-- ALERTAS
-- Una fila por aviso pendiente. La app solo la lee y la pinta.
-- ---------------------------------------------------------------------
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

-- ---------------------------------------------------------------------
-- CERRAR CORTE
-- Calcula lo esperado, lo compara con lo contado, congela el período y
-- marca los movimientos. El siguiente corte arranca del efectivo CONTADO,
-- no del esperado, para que un descuadre no se arrastre en silencio.
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
  v_ef_ini    numeric(12,2);
  v_si_ini    numeric(12,2);
  v_ef_delta  numeric(12,2);
  v_si_delta  numeric(12,2);
  v_n         integer;
  v_com       numeric(12,2);
  v_deuda     numeric(12,2);
  v_corte     cortes;
begin
  -- punto de partida: el último corte de esta caja, o los saldos iniciales
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
         coalesce(sum(case when m.cuenta_comision then m.comision_local - m.comision_sistema else 0 end), 0)
    into v_ef_delta, v_si_delta, v_n, v_com
  from movimientos m
  where m.caja_id = p_caja and m.corte_id is null and m.fecha <= v_hasta;

  select coalesce(sum(d.saldo_pendiente), 0) into v_deuda
  from deudas d where d.caja_id = p_caja and d.estado = 'abierta';

  insert into cortes (
    caja_id, tipo, desde, hasta,
    efectivo_inicial, efectivo_esperado, efectivo_contado, diferencia_efectivo,
    sistema_inicial,  sistema_esperado,  sistema_reportado, diferencia_sistema,
    deuda_total, n_movimientos, comisiones_periodo, notas
  ) values (
    p_caja, p_tipo, v_desde, v_hasta,
    v_ef_ini, v_ef_ini + v_ef_delta, p_efectivo_contado,
    p_efectivo_contado - (v_ef_ini + v_ef_delta),
    v_si_ini, v_si_ini + v_si_delta, p_sistema_reportado,
    case when p_sistema_reportado is null then null
         else p_sistema_reportado - (v_si_ini + v_si_delta) end,
    v_deuda, v_n, v_com, p_notas
  ) returning * into v_corte;

  update movimientos
     set corte_id = v_corte.id
   where caja_id = p_caja and corte_id is null and fecha <= v_hasta;

  -- Si hubo descuadre, se registra como ajuste dentro de este mismo corte.
  -- Así el saldo que muestra el tablero es el dinero que de verdad hay,
  -- y el descuadre queda documentado en vez de arrastrarse en silencio.
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
-- VISTA DE MOVIMIENTOS PARA REPORTES
-- ---------------------------------------------------------------------
create or replace view v_movimientos_full as
select
  m.id, m.fecha, c.nombre as caja, m.tipo, m.monto,
  m.comision_local, m.comision_sistema,
  (m.comision_local - m.comision_sistema) as margen,
  m.comision_forma, m.cuenta_comision,
  m.beneficiario, m.motivo, m.operador, m.referencia,
  m.delta_efectivo, m.delta_sistema,
  m.corte_id, m.anulado, m.reversa_de
from movimientos m
join cajas c on c.id = m.caja_id;
