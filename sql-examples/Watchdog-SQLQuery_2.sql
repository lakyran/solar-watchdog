SELECT *
FROM power_gen_history
WHERE
    user_name = 'veeraiah'
    AND DATE(datetime) = '2025-04-05'

SELECT pg_size_pretty( pg_total_relation_size('power_gen_history') );

CREATE TABLE disruption_events (
    event_id          UUID PRIMARY KEY,
    created_at      TIMESTAMP NOT NULL,
    user_name      VARCHAR NOT NULL,
    user_id            VARCHAR,
    vendor             VARCHAR NOT NULL,
    device_sn       VARCHAR NOT NULL,
    device_oem    VARCHAR NOT NULL,
    device_type    INTEGER NOT NULL,
    plant_id           VARCHAR NOT NULL,
    event_date      DATE NOT NULL,
    start_time       TIMESTAMP NOT NULL,
    end_time        TIMESTAMP NOT NULL,
    total_duration    VARCHAR NOT NULL,
    fault_details    VARCHAR NOT NULL,
    impact_of_event  VARCHAR,
    root_cause_analysis    VARCHAR NOT NULL,
    power_generation_during_disruption    VARCHAR NOT NULL,
    parameters_behaviour_during_disruption    VARCHAR NOT NULL,
    is_ongoing_event    VARCHAR NOT NULL,
    further_action_required    VARCHAR NOT NULL,
    
    UNIQUE (device_sn, event_date, start_time)
)

SELECT * FROM disruption_events WHERE device_sn = 'BEJACFM00T' 

CREATE TABLE users (
    user_id        VARCHAR NOT NULL,
    user_name      VARCHAR NOT NULL,
    vendor         VARCHAR NOT NULL,
    phone          VARCHAR,
    email          VARCHAR,
    registered_on  TIMESTAMP,
    password_hash  VARCHAR(255),
    role           VARCHAR(50) DEFAULT 'user' NOT NULL,

    PRIMARY KEY (user_id, user_name, vendor)
);

SELECT user_name FROM users

CREATE TABLE plants (
    plant_id           VARCHAR NOT NULL,
    plant_name    VARCHAR,
    user_name     VARCHAR NOT NULL,
    user_id            VARCHAR,
    vendor             VARCHAR NOT NULL,
    city                   VARCHAR NOT NULL,
    latitude            FLOAT NOT NULL,
    longitude         FLOAT NOT NULL,
    peak_power    FLOAT NOT NULL,

    PRIMARY KEY (plant_id, vendor)
);

SELECT * FROM plants

CREATE TABLE inverters (
    device_sn       VARCHAR NOT NULL,
    user_name     VARCHAR NOT NULL,
    user_id            VARCHAR,
    vendor             VARCHAR NOT NULL,
    plant_id           VARCHAR NOT NULL,
    device_oem    VARCHAR NOT NULL,
    device_type    INTEGER NOT NULL,
    latitude            FLOAT NOT NULL,
    longitude         FLOAT NOT NULL,

    PRIMARY KEY (device_sn, vendor)
);

SELECT * FROM inverters

INSERT INTO plants
(plant_id, user_name, user_id, vendor, city, latitude, longitude, peak_power)
VALUES
    ('1791216', 'dhruthifoods', '2017405', 'unisolarpower', 'Hyderabad', '17.528', '78.43523', 38)

UPDATE plants
SET plant_name = 'Blossom City'
WHERE user_name = 'blossomcity'


SELECT * FROM plants

INSERT INTO inverters
(device_sn, user_name, user_id, vendor, plant_id, device_oem, device_type, latitude, longitude)
VALUES
    ('CZGBCL2141', 'veeraiah', '3094724', 'unisolarpower', '9332016', 'growatt', 7, '18.663718597292', '78.113592215591'),
    ('CZGME630L4', 'vijayavani3kw', '3199231', 'unisolarpower', '9990803', 'growatt', 7, '17.37528', '78.474442'),
    ('CLJACLR001', 'blossomcity', '2278874', 'unisolarpower', '2085203', 'growatt', 1, '17.30579', '78.60268'),
    ('BEJACFM00T', 'dhruthifoods', '2017405', 'unisolarpower', '1791216', 'growatt', 1, '17.528', '78.43523')


SELECT * FROM inverters

CREATE TABLE analysis_ledger (
    device_sn       VARCHAR NOT NULL,
    vendor             VARCHAR NOT NULL,
    device_oem    VARCHAR NOT NULL,
    latest_analysis_date  TIMESTAMP NOT NULL,
    last_update_at     TIMESTAMP,
    
    PRIMARY KEY (device_sn, vendor)
)

SELECT * FROM analysis_ledger

CREATE TABLE plant_energy_summary (
	plant_id        VARCHAR NOT NULL,
    plant_name      VARCHAR,
    user_name       VARCHAR NOT NULL,
    vendor          VARCHAR NOT NULL,
    peak_power      FLOAT NOT NULL,
    current_power   FLOAT NOT NULL,
    total_energy    FLOAT NOT NULL,
    yearly_energy   FLOAT NOT NULL,
    monthly_energy  FLOAT NOT NULL,
    today_energy    FLOAT NOT NULL,
    carbon_offset   FLOAT NOT NULL,
    last_updated_at TIMESTAMP NOT NULL,

    PRIMARY KEY (plant_id, vendor)
);

SELECT * FROM plant_energy_summary

CREATE TABLE daily_expected_generation (
	month                   VARCHAR NOT NULL PRIMARY KEY,
    generation_per_day      FLOAT NOT NULL
);

CREATE TABLE plant_daily_generation_history (
    plant_id        VARCHAR NOT NULL,
    plant_name      VARCHAR,
    user_name       VARCHAR NOT NULL,
    vendor          VARCHAR NOT NULL,
    date            VARCHAR NOT NULL,
    day_energy      FLOAT NOT NULL,
    last_updated_at TIMESTAMP NOT NULL,

    PRIMARY KEY (plant_id, vendor, date)
);


SELECT plant_id, plant_name, max(date), max(day_energy)
FROM plant_daily_generation_history
WHERE date = '2025-05-07'
GROUP BY plant_id, plant_name