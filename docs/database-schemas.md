# Database Schemas

PostgreSQL table definitions for the Unisolar Watchdog Service.

## Tables

### users

CREATE TABLE users (
    user_id           VARCHAR NOT NULL,
    user_name     VARCHAR NOT NULL,
    vendor             VARCHAR NOT NULL,
    phone              VARCHAR,
    email                VARCHAR,
    registered_on TIMESTAMP,

    PRIMARY KEY (user_id, username, vendor)
);

### plants

CREATE TABLE plants (
    plant_id      VARCHAR NOT NULL,
    plant_name    VARCHAR,
    user_name     VARCHAR NOT NULL,
    user_id       VARCHAR,
    created_date  DATE,
    vendor        VARCHAR NOT NULL,
    city          VARCHAR NOT NULL,
    latitude      VARCHAR NOT NULL,
    longitude     VARCHAR NOT NULL,
    peak_power    FLOAT NOT NULL,

    PRIMARY KEY (plant_id, vendor)
);

### inverters

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

### power_gen_history

CREATE TABLE power_gen_history (
    datetime      TIMESTAMP NOT NULL,
    user_name       VARCHAR NOT NULL,
    device_sn     VARCHAR NOT NULL,
    device_oem    VARCHAR NOT NULL,
    device_type   INTEGER NOT NULL,
    vendor        VARCHAR NOT NULL,
    plant_id      VARCHAR NOT NULL,
    data          JSON NOT NULL,
    status        VARCHAR NOT NULL,
    ppv           FLOAT NOT NULL,
    pac           FLOAT NOT NULL,
    eac_today     FLOAT NOT NULL,
    vpv1          FLOAT NOT NULL,
    vpv2          FLOAT NOT NULL,
    vpv3          FLOAT NOT NULL,
    vac1          FLOAT NOT NULL,
    vac2          FLOAT NOT NULL,
    vac3          FLOAT NOT NULL,
    temperature   FLOAT NOT NULL,
    fault_type    INTEGER NOT NULL,
    total_records_on_day INTEGER NOT NULL,
    
    PRIMARY KEY (device_sn, datetime)
);

### plant_daily_generation_history

CREATE TABLE plant_daily_generation_history (
    plant_id        VARCHAR NOT NULL,
    plant_name      VARCHAR,
    user_name       VARCHAR NOT NULL,
    vendor          VARCHAR NOT NULL,
    date            VARCHAR NOT NULL
    day_energy      FLOAT NOT NULL,
    last_updated_at TIMESTAMP NOT NULL,

    PRIMARY KEY (plant_id, vendor, date)
);

### plant_energy_summary

CREATE TABLE plant_energy_summary (
		plant_id        VARCHAR NOT NULL,
    plant_name      VARCHAR,
    user_name       VARCHAR NOT NULL,
    vendor          VARCHAR NOT NULL,
    peak_power      FLOAT NOT NULL,
    total_energy    FLOAT NOT NULL,
    yearly_energy   FLOAT NOT NULL,
    monthly_energy  FLOAT NOT NULL,
    today_energy    FLOAT NOT NULL,
    carbon_offset   FLOAT NOT NULL,
    last_updated_at TIMESTAMP NOT NULL,

    PRIMARY KEY (plant_id, vendor)
);

### disruption_events

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
    root_cause_analysis    VARCHAR NOT NULL,
    power_generation_during_disruption    VARCHAR NOT NULL,
    parameters_behaviour_during_disruption    VARCHAR NOT NULL,
    is_ongoing_event    VARCHAR NOT NULL,
    further_action_required    VARCHAR NOT NULL,
    
    UNIQUE (device_sn, event_date, start_time)
);

### analysis_ledger

CREATE TABLE analysis_ledger (
    device_sn       VARCHAR NOT NULL,
    vendor             VARCHAR NOT NULL,
    device_oem    VARCHAR NOT NULL,
    latest_analysis_date  TIMESTAMP NOT NULL,
    
    UNIQUE (device_sn, vendor, device_oem)
);

### android_device_tokens

CREATE TABLE android_device_tokens (
    token_id        UUID PRIMARY KEY,
    user_id         VARCHAR NOT NULL,
    token           VARCHAR NOT NULL,
    device_id       VARCHAR NOT NULL,
    is_active       BOOLEAN NOT NULL,
    notification_enabled BOOLEAN NOT NULL,
    created_at      TIMESTAMP NOT NULL,
    updated_at      TIMESTAMP NOT NULL,
    last_used_at    TIMESTAMP NOT NULL,   
    
    UNIQUE (user_id, device_id)
);

CREATE INDEX idx_device_tokens_token ON device_tokens(token);