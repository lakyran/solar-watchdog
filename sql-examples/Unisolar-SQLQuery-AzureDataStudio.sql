select  datetime
,user_name
,device_sn
,device_oem
,device_type
,vendor
,plant_id
,status
,ppv
,pac
,eac_today
,vpv1
,vpv2
,vpv3
,vac1
,vac2
,vac3
,temperature
,fault_type
,total_records_on_day
from power_gen_history
WHERE device_sn = 'CZGBCL2141'
AND DATE(datetime) = '2025-10-15'
ORDER BY datetime DESC
LIMIT 1000


SELECT device_sn, min(user_name), max(datetime) as datetime, count(*)
from power_gen_history
group by device_sn
order by datetime desc

SELECT device_sn, min(user_name), date(datetime) as day, count(*) as entries
from power_gen_history
where --device_sn = 'CLJ3BKC01Q'
date(datetime) >= '2025-10-01'
group by device_sn, day
order by device_sn, day desc

SELECT device_sn, min(user_name), date(datetime) as day, count(*) as entries
from power_gen_history
where --device_sn = 'CLJ3BKC01Q'
date(datetime) >= '2025-10-01'
group by device_sn, day
order by device_sn, day desc

# device_sn = 'CLJACLR001', 'CZGBCL2141', 'CZGME630L4' 
# user_name = 'blossomcity', 'veeraiah', 'vijayavani3kw'

SELECT plant_name, MAX(date)
FROM plant_daily_generation_history
GROUP BY plant_name