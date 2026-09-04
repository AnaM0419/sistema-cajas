-- =====================================================================
--  SISTEMA DE CAJAS · 05 · DEUDAS COMPLETAS
--  Tres dimensiones de la misma tabla:
--    · lo que le deben a cada caja
--    · lo que debe cada persona que usa el sistema
--    · lo que se deben las cajas entre sí, ya compensado
--  Ejecutar después de 04_seguridad.sql
-- =====================================================================

-- ---------------------------------------------------------------------
-- PERFILES
-- Espejo público de los usuarios que inician sesión. Hace falta porque
-- la tabla auth.users de Supabase no se puede leer desde la app, y sin
-- ella no se puede armar la lista de "¿quién se llevó el dinero?".
-- ---------------------------------------------------------------------
create table if not exists perfiles (
  id      uuid primary key references auth.users(id) on delete cascade,
  nombre  text not null,
  correo  text,
  activo  boolean not null default true
);

-- Cada usuario nuevo aparece solo en la lista.
create or replace function fn_nuevo_perfil()
returns trigger
language plpgsql
security definer
as $$
begin
  insert into perfiles (id, nombre, correo)
  values (
    new.id,
    coalesce(nullif(trim(new.raw_user_meta_data ->> 'nombre'), ''),
             split_part(new.email, '@', 1)),
    new.email
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists trg_nuevo_perfil on auth.users;
create trigger trg_nuevo_perfil
  after insert on auth.users
  for each row execute function fn_nuevo_perfil();

-- Carga los usuarios que ya existían antes de correr este archivo.
insert into perfiles (id, nombre, correo)
select u.id,
       coalesce(nullif(trim(u.raw_user_meta_data ->> 'nombre'), ''),
                split_part(u.email, '@', 1)),
       u.email
from auth.users u
on conflict (id) do nothing;

-- ---------------------------------------------------------------------
-- DEUDAS: ahora el deudor puede ser tres cosas
--   'usuario' -> una de las personas que usan el sistema
--   'persona' -> alguien de afuera, identificado por nombre
--   'caja'    -> otra caja
-- ---------------------------------------------------------------------
alter table deudas add column if not exists usuario_deudor uuid references perfiles(id);
alter table deudas add column if not exists saldada_en     timestamptz;

alter table deudas drop constraint if exists deudas_deudor_tipo_check;
alter table deudas add  constraint deudas_deudor_tipo_check
  check (deudor_tipo in ('usuario','persona','caja'));

alter table deudas drop constraint if exists deuda_deudor_coherente;
alter table deudas add  constraint deuda_deudor_coherente check (
     (deudor_tipo = 'usuario' and usuario_deudor is not null)
  or (deudor_tipo = 'persona' and persona is not null)
  or (deudor_tipo = 'caja'    and caja_deudora is not null)
);

-- Una caja no se debe a sí misma.
alter table deudas drop constraint if exists deuda_caja_distinta;
alter table deudas add  constraint deuda_caja_distinta
  check (deudor_tipo <> 'caja' or caja_deudora <> caja_id);

create index if not exists deudas_usuario  on deudas (usuario_deudor) where estado = 'abierta';
create index if not exists deudas_entre    on deudas (caja_deudora)   where estado = 'abierta';

-- Enlaza cada pago con la deuda que abona, para poder reconstruir el
-- estado de cuenta de cualquier deudor.
alter table movimientos add column if not exists deuda_id bigint references deudas(id);
create index if not exists movimientos_deuda on movimientos (deuda_id) where deuda_id is not null;

-- ---------------------------------------------------------------------
-- QUIÉN DEBE — la lista unificada
-- Una fila por deudor, sin importar si es usuario, persona o caja.
-- ---------------------------------------------------------------------
create or replace view v_deuda_por_deudor as
select
  d.deudor_tipo,
  case d.deudor_tipo
    when 'usuario' then coalesce(p.nombre, 'Usuario eliminado')
    when 'persona' then d.persona
    when 'caja'    then cd.nombre
  end                                              as deudor,
  d.usuario_deudor,
  d.caja_deudora,
  sum(d.saldo_pendiente)                           as debe,
  sum(d.monto)                                     as prestado_total,
  count(*)                                         as deudas_abiertas,
  min(d.creada_en)                                 as mas_antigua,
  (current_date - min(d.creada_en)::date)          as dias_mas_antigua,
  bool_or(not d.reembolsable)                      as tiene_no_reembolsable
from deudas d
left join perfiles p  on p.id  = d.usuario_deudor
left join cajas    cd on cd.id = d.caja_deudora
where d.estado = 'abierta' and d.saldo_pendiente > 0
group by d.deudor_tipo, 2, d.usuario_deudor, d.caja_deudora;

-- ---------------------------------------------------------------------
-- DEUDA POR CAJA
-- Cada caja tiene un valor que le deben; y a veces le debe a otra caja.
-- Aquí se ven los dos lados y el neto.
-- ---------------------------------------------------------------------
create or replace view v_deuda_por_caja as
select
  c.id   as caja_id,
  c.nombre,
  coalesce((select sum(d.saldo_pendiente) from deudas d
            where d.caja_id = c.id and d.estado = 'abierta'), 0)        as por_cobrar,
  coalesce((select sum(d.saldo_pendiente) from deudas d
            where d.caja_id = c.id and d.estado = 'abierta'
              and d.deudor_tipo in ('usuario','persona')), 0)           as por_cobrar_personas,
  coalesce((select sum(d.saldo_pendiente) from deudas d
            where d.caja_id = c.id and d.estado = 'abierta'
              and d.deudor_tipo = 'caja'), 0)                           as por_cobrar_cajas,
  coalesce((select sum(d.saldo_pendiente) from deudas d
            where d.caja_deudora = c.id and d.estado = 'abierta'), 0)   as por_pagar,
  coalesce((select sum(d.saldo_pendiente) from deudas d
            where d.caja_id = c.id and d.estado = 'abierta'), 0)
  - coalesce((select sum(d.saldo_pendiente) from deudas d
            where d.caja_deudora = c.id and d.estado = 'abierta'), 0)   as neto
from cajas c
where c.activa;

-- ---------------------------------------------------------------------
-- ENTRE CAJAS — ya compensado
-- Si Pichincha le debe $50 a Facilito y Facilito le debe $30 a
-- Pichincha, aquí sale una sola fila: Pichincha debe $20.
-- Solo aparecen las parejas con saldo real a favor de alguien.
-- ---------------------------------------------------------------------
create or replace view v_deuda_entre_cajas as
with pares as (
  select caja_id as acreedora, caja_deudora as deudora,
         sum(saldo_pendiente) as bruto
  from deudas
  where estado = 'abierta' and deudor_tipo = 'caja' and saldo_pendiente > 0
  group by 1, 2
)
select
  ca.nombre                        as acreedora,
  cd.nombre                        as deudora,
  p.acreedora                      as acreedora_id,
  p.deudora                        as deudora_id,
  p.bruto,
  coalesce(q.bruto, 0)             as bruto_contrario,
  p.bruto - coalesce(q.bruto, 0)   as neto
from pares p
left join pares q on q.acreedora = p.deudora and q.deudora = p.acreedora
join cajas ca on ca.id = p.acreedora
join cajas cd on cd.id = p.deudora
where p.bruto - coalesce(q.bruto, 0) > 0;

-- ---------------------------------------------------------------------
-- ESTADO DE CUENTA
-- El detalle de una deuda: cuánto se prestó, qué se ha abonado y cuándo.
-- ---------------------------------------------------------------------
create or replace view v_deudas_detalle as
select
  d.id, d.creada_en, d.estado, d.reembolsable, d.motivo,
  c.nombre                                     as caja_acreedora,
  d.deudor_tipo,
  case d.deudor_tipo
    when 'usuario' then coalesce(p.nombre, 'Usuario eliminado')
    when 'persona' then d.persona
    when 'caja'    then cd.nombre
  end                                          as deudor,
  d.monto,
  d.monto - d.saldo_pendiente                  as abonado,
  d.saldo_pendiente,
  (current_date - d.creada_en::date)           as dias,
  d.movimiento_id,
  d.saldada_en
from deudas d
join cajas c        on c.id  = d.caja_id
left join perfiles p  on p.id  = d.usuario_deudor
left join cajas   cd  on cd.id = d.caja_deudora;

-- ---------------------------------------------------------------------
-- REGISTRAR UN ABONO
-- Hace las tres cosas de una vez y de forma atómica: mueve el saldo de
-- la caja, baja la deuda y la cierra si quedó en cero.
-- ---------------------------------------------------------------------
create or replace function abonar_deuda(
  p_deuda   bigint,
  p_monto   numeric,
  p_destino text default 'efectivo'   -- 'efectivo' o 'sistema'
) returns deudas
language plpgsql
security definer
as $$
declare
  d        deudas;
  v_nombre text;
  mov_id   bigint;
begin
  select * into d from deudas where id = p_deuda for update;
  if not found then
    raise exception 'La deuda % no existe.', p_deuda;
  end if;
  if d.estado <> 'abierta' then
    raise exception 'La deuda % ya está %.', p_deuda, d.estado;
  end if;
  if p_monto <= 0 then
    raise exception 'El abono debe ser mayor que cero.';
  end if;
  if p_monto > d.saldo_pendiente then
    raise exception 'El abono ($%) es mayor que el saldo pendiente ($%).',
      p_monto, d.saldo_pendiente;
  end if;
  if p_destino not in ('efectivo','sistema') then
    raise exception 'El destino debe ser efectivo o sistema.';
  end if;

  select case d.deudor_tipo
           when 'usuario' then (select pf.nombre from perfiles pf where pf.id = d.usuario_deudor)
           when 'persona' then d.persona
           when 'caja'    then (select cj.nombre from cajas cj where cj.id = d.caja_deudora)
         end into v_nombre;

  insert into movimientos (caja_id, tipo, monto, cuenta_comision,
                           beneficiario, motivo, deuda_id)
  values (d.caja_id, 'cobro_deuda_' || p_destino, p_monto, false,
          v_nombre, 'Abono a la deuda #' || p_deuda, p_deuda)
  returning id into mov_id;

  -- Si el deudor es una caja, el dinero también sale de esa caja.
  if d.deudor_tipo = 'caja' then
    insert into movimientos (caja_id, tipo, monto, cuenta_comision,
                             beneficiario, motivo, deuda_id)
    values (d.caja_deudora,
            case when p_destino = 'efectivo'
                 then 'traspaso_envio_efectivo'
                 else 'traspaso_envio_sistema' end,
            p_monto, false,
            (select cj.nombre from cajas cj where cj.id = d.caja_id),
            'Pago de la deuda #' || p_deuda, p_deuda);
  end if;

  update deudas
     set saldo_pendiente = saldo_pendiente - p_monto,
         estado    = case when saldo_pendiente - p_monto <= 0.004
                          then 'pagada' else 'abierta' end,
         saldada_en = case when saldo_pendiente - p_monto <= 0.004
                          then now() else null end
   where id = p_deuda
   returning * into d;

  return d;
end;
$$;

-- ---------------------------------------------------------------------
-- EL CORTE AHORA REPORTA LOS DOS LADOS
-- ---------------------------------------------------------------------
alter table cortes add column if not exists deuda_por_pagar numeric(12,2) not null default 0;

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
                           then m.comision_local - m.comision_sistema else 0 end), 0)
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
-- PERMISOS
-- ---------------------------------------------------------------------
alter table perfiles enable row level security;

drop policy if exists "leer perfiles"     on perfiles;
drop policy if exists "editar mi perfil"  on perfiles;
create policy "leer perfiles"    on perfiles for select to authenticated using (true);
create policy "editar mi perfil" on perfiles for update to authenticated using (id = auth.uid());

grant select on v_deuda_por_deudor, v_deuda_por_caja,
                v_deuda_entre_cajas, v_deudas_detalle to authenticated;
grant execute on function abonar_deuda(bigint, numeric, text) to authenticated;
grant execute on function cerrar_corte(smallint, text, numeric, numeric, text) to authenticated;
