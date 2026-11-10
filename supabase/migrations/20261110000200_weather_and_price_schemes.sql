-- Outdoor temperature, the strømstøtte rules, and views for the long-term dashboards.

create table power.weather_hourly (
    ts            timestamptz primary key,
    temperature_c real not null,
    forecast      boolean not null default false
);

-- Strømstøtte: share of the spot price above a threshold that the state pays (excl. VAT).
-- Until Sep 2023 it used the area's monthly average; since then each hour's price.
create table power.support_scheme (
    valid_from        date primary key,
    threshold_ex_vat  real not null,   -- NOK/kWh
    coverage          real not null,   -- 0..1
    hourly            boolean not null
);
insert into power.support_scheme values
    ('2021-12-01', 0.70, 0.55, false),
    ('2022-01-01', 0.70, 0.80, false),
    ('2022-09-01', 0.70, 0.90, false),
    ('2023-09-01', 0.70, 0.90, true),
    ('2024-01-01', 0.73, 0.90, true),
    ('2025-01-01', 0.75, 0.90, true),
    ('2026-01-01', 0.77, 0.90, true);

-- Norgespris: fixed price incl. VAT per kWh, up to a monthly cap per home. The 2027 price is
-- proposed (45 øre excl. VAT); update when adopted.
create table power.norgespris (
    valid_from     date primary key,
    price_incl_vat real not null,
    monthly_cap_kwh real not null
);
insert into power.norgespris values
    ('2025-10-01', 0.50, 5000);

grant select on power.weather_hourly, power.support_scheme, power.norgespris to power_reader;
grant select, insert, update on power.weather_hourly to power_writer;

-- Hourly consumption with everything needed to price it three ways.
create view power.hourly_priced as
select c.ts,
       c.kwh,
       c.cost_nok                                            as spot_cost_nok,   -- Tibber, incl. VAT
       p.energy                                              as spot_ex_vat,     -- per kWh
       g.energy_nok                                          as grid_energy_nok, -- per kWh, incl. VAT
       s.threshold_ex_vat, s.coverage, s.hourly as support_hourly,
       w.temperature_c
from power.consumption_hourly c
left join power.spot_price p
       on p.source = 'tibber' and p.resolution_min = 60 and p.ts = c.ts
left join power.grid_tariff_hourly g on g.ts = c.ts
left join lateral (select * from power.support_scheme
                   where valid_from <= (c.ts at time zone 'Europe/Oslo')::date
                   order by valid_from desc limit 1) s on true
left join power.weather_hourly w on w.ts = c.ts
where c.kwh is not null;

-- Per month: what the energy cost with spot price and strømstøtte, and what it would have
-- cost with Norgespris (50 øre incl. VAT; before Oct 2025 a "what if").
create view power.monthly_price_schemes as
with h as (
    select date_trunc('month', ts at time zone 'Europe/Oslo') as month, *
    from power.hourly_priced
), m as (
    select month,
           sum(kwh) as kwh,
           sum(spot_cost_nok) as spot_cost_nok,
           avg(spot_ex_vat) as avg_spot_ex_vat,
           -- hourly support (since Sep 2023)
           sum(case when support_hourly
                    then coverage * greatest(spot_ex_vat - threshold_ex_vat, 0) * 1.25 * kwh end) as support_hourly_nok,
           max(threshold_ex_vat) filter (where not support_hourly) as m_threshold,
           max(coverage) filter (where not support_hourly) as m_coverage,
           sum(kwh) filter (where not support_hourly) as m_kwh,
           sum(kwh * grid_energy_nok) as grid_energy_cost_nok
    from h group by month
)
select month,
       kwh,
       spot_cost_nok,
       coalesce(support_hourly_nok, 0)
         + coalesce(m_coverage * greatest(avg_spot_ex_vat - m_threshold, 0) * 1.25 * m_kwh, 0) as support_nok,
       spot_cost_nok
         - coalesce(support_hourly_nok, 0)
         - coalesce(m_coverage * greatest(avg_spot_ex_vat - m_threshold, 0) * 1.25 * m_kwh, 0) as spot_net_nok,
       least(kwh, 5000) * 0.50 + greatest(kwh - 5000, 0) * spot_cost_nok / nullif(kwh, 0) as norgespris_nok,
       grid_energy_cost_nok
from m;

-- Capacity step per month: the top-3 average and what that step cost.
create view power.monthly_capacity_cost as
select mc.month,
       mc.top3_avg_kwh,
       mc.top3_kwh,
       cs.min_kwh as step_min_kwh,
       cs.max_kwh as step_max_kwh,
       cs.monthly_nok
from power.monthly_capacity mc
left join lateral (
    select * from power.capacity_step s
    where s.valid_from <= (mc.month + interval '1 month - 1 day')::date
      and s.min_kwh <= mc.top3_avg_kwh and (s.max_kwh is null or mc.top3_avg_kwh < s.max_kwh)
    order by s.valid_from desc limit 1
) cs on true;

grant select on power.hourly_priced, power.monthly_price_schemes, power.monthly_capacity_cost,
                power.monthly_capacity to power_reader;
