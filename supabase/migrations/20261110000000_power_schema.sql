-- Long-term store for power-monitor. Everything lives in the "power" schema, which the
-- Supabase Data API doesn't expose (only "public" and "graphql_public" are exposed).
create schema if not exists power;

-- Pulse readings, aggregated per minute by the collector. Raw 10 s data stays in Prometheus.
create table power.reading_1m (
    ts               timestamptz primary key,  -- start of the minute
    samples          smallint not null,        -- readings in the minute (6 when complete)
    power_avg_w      real not null,
    power_min_w      real not null,
    power_max_w      real not null,
    energy_kwh       real,                     -- meter energy consumed in the minute
    voltage_l1_v     real,
    voltage_l2_v     real,
    voltage_l3_v     real,
    voltage_min_v    real,                     -- lowest phase voltage in the minute
    current_l1_max_a real,
    current_l2_max_a real,                     -- always null on an IT grid
    current_l3_max_a real,
    power_factor     real
);

-- Hourly consumption and cost from Tibber (backfilled from the first day as a customer).
create table power.consumption_hourly (
    ts          timestamptz primary key,
    kwh         real,
    cost_nok    real,                          -- energy cost incl. VAT, excl. grid tariff
    unit_price  real                           -- NOK/kWh
);

-- Spot prices. One row per source, area, start and resolution, so hourly and 15-minute
-- prices and different sources sit side by side.
create table power.spot_price (
    source          text not null check (source in ('tibber', 'entsoe')),
    area            text not null,             -- e.g. NO1
    ts              timestamptz not null,
    resolution_min  smallint not null check (resolution_min in (15, 60)),
    currency        text not null,
    energy          real,                      -- spot (+ supplier markup for Tibber), per kWh
    tax             real,                      -- Tibber: taxes incl. VAT
    total           real not null,             -- Tibber: what the customer pays per kWh; ENTSO-E: spot per kWh
    level           text,                      -- Tibber price level, e.g. CHEAP
    primary key (source, area, ts, resolution_min)
);

-- Grid tariff energy charge per hour (Elvia), from July 2022.
create table power.grid_tariff_hourly (
    ts            timestamptz primary key,
    tariff_key    text not null,
    energy_nok    real not null,               -- incl. VAT, per kWh
    energy_ex_vat real
);

-- Capacity steps (kapasitetsledd) as published per day.
create table power.capacity_step (
    valid_from    date not null,
    tariff_key    text not null,
    min_kwh       real not null,
    max_kwh       real,                        -- null for the top step
    monthly_nok   real not null,               -- incl. VAT
    primary key (valid_from, tariff_key, min_kwh)
);

-- Events to annotate dashboards (strømstøtte, Norgespris, tariff changes).
create table power.event (
    ts          timestamptz not null,
    title       text not null,
    description text,
    tags        text[] not null default '{}',
    primary key (ts, title)
);

-- Elvia's capacity charge: average of the 3 highest hours on different days per month.
create view power.monthly_capacity as
with daily_peak as (
    select date_trunc('month', ts at time zone 'Europe/Oslo') as month,
           (ts at time zone 'Europe/Oslo')::date as day,
           max(kwh) as peak_kwh
    from power.consumption_hourly
    group by 1, 2
), ranked as (
    select month, day, peak_kwh,
           row_number() over (partition by month order by peak_kwh desc) as rank
    from daily_peak
)
select month,
       avg(peak_kwh) filter (where rank <= 3) as top3_avg_kwh,
       array_agg(round(peak_kwh::numeric, 2) order by rank) filter (where rank <= 3) as top3_kwh
from ranked
group by month;

-- Roles: the collector writes, Grafana reads. Passwords are set outside the repo.
do $$
begin
    if not exists (select from pg_roles where rolname = 'power_writer') then
        create role power_writer login;
    end if;
    if not exists (select from pg_roles where rolname = 'power_reader') then
        create role power_reader login;
    end if;
end $$;

grant usage on schema power to power_writer, power_reader;
grant select, insert, update on all tables in schema power to power_writer;
grant select on all tables in schema power to power_reader;
alter default privileges in schema power grant select, insert, update on tables to power_writer;
alter default privileges in schema power grant select on tables to power_reader;
