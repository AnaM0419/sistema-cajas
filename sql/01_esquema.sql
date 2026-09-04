-- =====================================================================
--  SISTEMA DE CAJAS · 01 · ESQUEMA
--  Pegar completo en Supabase > SQL Editor > New query > Run
--  Se puede volver a ejecutar: borra y recrea todo (¡borra los datos!)
-- =====================================================================

drop view   if exists v_alertas          cascade;
drop view   if exists v_saldos           cascade;
drop view   if exists v_movimientos_full cascade;
drop table  if exists deudas             cascade;
drop table  if exists movimientos        cascade;
drop table  if exists cortes             cascade;
drop table  if exists tarifas            cascade;
drop table  if exists cajas              cascade;

-- ---------------------------------------------------------------------
-- CAJAS
-- Cada caja tiene su propia gaveta de efectivo y su propio saldo de
-- sistema. Son independientes entre sí.
-- ---------------------------------------------------------------------
create table cajas (
  id                       smallint generated always as identity primary key,
  nombre                   text not null unique,
  tipo                     text not null check (tipo in ('banco','facilito')),

  -- saldos con los que arranca el sistema (se cargan una sola vez)
  efectivo_inicial         numeric(12,2) not null default 0,
  sistema_inicial          numeric(12,2) not null default 0,

  -- umbrales de alerta (null = sin alerta)
  alerta_sistema_aviso     numeric(12,2),   -- ej. 100  -> conviene acreditar
  alerta_sistema_critico   numeric(12,2),   -- ej.  50  -> urgente acreditar
  alerta_efectivo_aviso    numeric(12,2),   -- ej.  80  -> queda poco efectivo
  alerta_efectivo_critico  numeric(12,2),   -- ej.  30
  alerta_efectivo_tope     numeric(12,2),   -- ej. 800  -> demasiado efectivo, depositar

  activa                   boolean not null default true,
  creada_en                timestamptz not null default now()
);

comment on column cajas.alerta_sistema_aviso is
  'Cuando el saldo del sistema baja de aquí, hay que acreditar dinero de la caja.';

-- ---------------------------------------------------------------------
-- TARIFAS
-- Una sola tabla para las dos comisiones:
--   quien_cobra = 'sistema' -> lo que el proveedor nos cobra a nosotros
--   quien_cobra = 'local'   -> lo que nosotros le cobramos al cliente
-- El margen del negocio es local - sistema.
-- Es editable desde la app; agregar filas nuevas no requiere tocar código.
-- ---------------------------------------------------------------------
create table tarifas (
  id                   bigint generated always as identity primary key,
  caja_id              smallint not null references cajas(id) on delete cascade,
  quien_cobra          text not null check (quien_cobra in ('sistema','local')),
  tipo                 text not null,          -- recarga | juego | servicio | retiro | deposito
  operador             text,                   -- Claro, Movistar, CNT, Agua... null = cualquiera
  monto_desde          numeric(12,2) not null default 0,
  monto_hasta          numeric(12,2),          -- null = sin tope superior
  comision_fija        numeric(12,2) not null default 0,
  comision_porcentaje  numeric(7,4)  not null default 0,   -- en %, ej. 1.5 = 1,5 %
  vigente_desde        date not null default current_date,
  vigente_hasta        date,                   -- null = vigente
  notas                text
);

create index tarifas_busqueda on tarifas (caja_id, quien_cobra, tipo, monto_desde);

-- ---------------------------------------------------------------------
-- CORTES
-- Un corte congela un período. Puede ser de turno (varios al día) o
-- diario (el cierre del día).
-- ---------------------------------------------------------------------
create table cortes (
  id                   bigint generated always as identity primary key,
  caja_id              smallint not null references cajas(id),
  tipo                 text not null check (tipo in ('turno','diario')),
  desde                timestamptz not null,
  hasta                timestamptz not null,

  efectivo_inicial     numeric(12,2) not null,
  efectivo_esperado    numeric(12,2) not null,
  efectivo_contado     numeric(12,2) not null,
  diferencia_efectivo  numeric(12,2) not null,

  sistema_inicial      numeric(12,2) not null,
  sistema_esperado     numeric(12,2) not null,
  sistema_reportado    numeric(12,2),
  diferencia_sistema   numeric(12,2),

  deuda_total          numeric(12,2) not null default 0,
  n_movimientos        integer not null default 0,
  comisiones_periodo   numeric(12,2) not null default 0,

  usuario_id           uuid default auth.uid(),
  cerrado_en           timestamptz not null default now(),
  notas                text
);

create index cortes_caja_fecha on cortes (caja_id, hasta desc);

-- ---------------------------------------------------------------------
-- MOVIMIENTOS
-- El corazón del sistema. Una fila por operación.
-- delta_efectivo y delta_sistema los calcula un trigger: nunca se
-- escriben a mano desde la app.
-- ---------------------------------------------------------------------
create table movimientos (
  id                bigint generated always as identity primary key,
  caja_id           smallint not null references cajas(id),
  usuario_id        uuid default auth.uid(),
  fecha             timestamptz not null default now(),

  tipo              text not null,
  monto             numeric(12,2) not null check (monto >= 0),

  -- comisiones
  comision_local    numeric(12,2) not null default 0,  -- lo que cobramos
  comision_sistema  numeric(12,2) not null default 0,  -- lo que nos cobran
  comision_forma    text not null default 'ninguna'
                    check (comision_forma in ('fisica','sistema','ninguna')),
  cuenta_comision   boolean not null default true,     -- false en acreditaciones

  -- recargo (solo acreditaciones)
  hubo_recargo      boolean not null default false,
  recargo           numeric(12,2) not null default 0,

  -- salidas
  beneficiario      text,
  motivo            text,
  genera_deuda      boolean not null default false,    -- la casilla "esto se devuelve"

  -- facilito
  operador          text,

  referencia        text,

  -- efectos (los pone el trigger)
  delta_efectivo    numeric(12,2) not null default 0,
  delta_sistema     numeric(12,2) not null default 0,

  corte_id          bigint references cortes(id),
  reversa_de        bigint references movimientos(id),
  anulado           boolean not null default false,

  creado_en         timestamptz not null default now()
);

create index movimientos_caja_fecha on movimientos (caja_id, fecha desc);
create index movimientos_sin_cortar on movimientos (caja_id) where corte_id is null;
create index movimientos_tipo       on movimientos (tipo, fecha desc);

-- Los datos obligatorios de cada tipo se validan aquí, no en la app,
-- para que ninguna vía de entrada pueda saltárselos.
alter table movimientos add constraint mov_salida_exige_datos check (
  tipo not in ('salida_sistema','salida_efectivo')
  or (beneficiario is not null and length(trim(beneficiario)) > 0
      and motivo is not null and length(trim(motivo)) > 0)
);

alter table movimientos add constraint mov_retiro_exige_forma check (
  tipo <> 'retiro' or comision_local = 0 or comision_forma in ('fisica','sistema')
);

-- ---------------------------------------------------------------------
-- DEUDAS
-- El deudor puede ser una persona o (cuando una caja le presta a otra)
-- otra caja.
-- ---------------------------------------------------------------------
create table deudas (
  id               bigint generated always as identity primary key,
  movimiento_id    bigint not null references movimientos(id),
  caja_id          smallint not null references cajas(id),   -- caja acreedora
  deudor_tipo      text not null check (deudor_tipo in ('persona','caja')),
  persona          text,
  caja_deudora     smallint references cajas(id),
  monto            numeric(12,2) not null check (monto > 0),
  saldo_pendiente  numeric(12,2) not null,
  reembolsable     boolean not null default true,
  motivo           text,
  estado           text not null default 'abierta'
                   check (estado in ('abierta','pagada','condonada')),
  creada_en        timestamptz not null default now(),

  constraint deuda_deudor_coherente check (
    (deudor_tipo = 'persona' and persona is not null)
    or (deudor_tipo = 'caja' and caja_deudora is not null)
  )
);

create index deudas_abiertas on deudas (caja_id) where estado = 'abierta';
