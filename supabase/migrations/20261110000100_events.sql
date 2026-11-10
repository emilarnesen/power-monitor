-- Policy and market events, shown as annotations on the history dashboards.
-- Sources: snl.no/strømstøtte, regjeringen.no, Stortinget Innst. 78 L (2024-2025), SDAC 15-min go-live.
insert into power.event (ts, title, description, tags) values
    ('2021-12-01 00:00+01', 'Strømstøtte innført',
     '55 % av månedlig snittpris over 70 øre/kWh eks. mva.', '{policy,stromstotte}'),
    ('2022-01-01 00:00+01', 'Strømstøtte 80 %',
     'Dekningsgraden økt til 80 %.', '{policy,stromstotte}'),
    ('2022-07-01 00:00+02', 'Ny nettleiemodell',
     'Kapasitetsledd: snittet av de tre høyeste timene i måneden, på ulike dager.', '{policy,nettleie}'),
    ('2022-09-01 00:00+02', 'Strømstøtte 90 %',
     'Dekningsgraden økt til 90 %.', '{policy,stromstotte}'),
    ('2023-09-01 00:00+02', 'Strømstøtte per time',
     'Beregnes per time i stedet for månedssnitt. Terskel 70 øre/kWh eks. mva.', '{policy,stromstotte}'),
    ('2025-01-01 00:00+01', 'Strømstøtte: terskel 75 øre',
     'Terskelen økt til 75 øre/kWh eks. mva.', '{policy,stromstotte}'),
    ('2025-10-01 00:00+02', 'Norgespris og kvartersmarked',
     'Norgespris 40 øre/kWh eks. mva. (50 øre inkl.) som valgfri ordning, avregnet på nettleien. Day-ahead-markedet går over til 15-minutters priser.',
     '{policy,norgespris,market}'),
    ('2026-01-01 00:00+01', 'Strømstøtte: terskel 77 øre',
     'Terskelen økt til 77 øre/kWh eks. mva. (96,25 øre inkl.).', '{policy,stromstotte}')
on conflict (ts, title) do update set description = excluded.description, tags = excluded.tags;
