CREATE TABLE IF NOT EXISTS assets (
    asset_id TEXT PRIMARY KEY,
    asset_name TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    dataset_name TEXT NOT NULL,
    dataset_doi TEXT,
    source_archive_sha256 TEXT,
    timestamp_interpretation TEXT NOT NULL,
    nominal_interval_seconds SMALLINT NOT NULL
        CHECK (nominal_interval_seconds > 0),
    gap_threshold_seconds SMALLINT NOT NULL
        CHECK (gap_threshold_seconds >= nominal_interval_seconds),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS telemetry (
    asset_id TEXT NOT NULL REFERENCES assets (asset_id),
    observed_at TIMESTAMPTZ NOT NULL,
    source_row_number BIGINT NOT NULL CHECK (source_row_number > 0),
    source_index BIGINT NOT NULL CHECK (source_index >= 0),
    tp2_bar NUMERIC(12, 6) NOT NULL,
    tp3_bar NUMERIC(12, 6) NOT NULL,
    h1_bar NUMERIC(12, 6) NOT NULL,
    dv_pressure_bar NUMERIC(12, 6) NOT NULL,
    reservoirs_bar NUMERIC(12, 6) NOT NULL,
    oil_temperature_c NUMERIC(12, 6) NOT NULL,
    motor_current_a NUMERIC(12, 6) NOT NULL,
    comp BOOLEAN NOT NULL,
    dv_electric BOOLEAN NOT NULL,
    towers BOOLEAN NOT NULL,
    mpg BOOLEAN NOT NULL,
    lps BOOLEAN NOT NULL,
    pressure_switch BOOLEAN NOT NULL,
    oil_level BOOLEAN NOT NULL,
    caudal_impulses BOOLEAN NOT NULL,
    PRIMARY KEY (asset_id, observed_at),
    UNIQUE (asset_id, source_row_number),
    UNIQUE (asset_id, source_index)
);

CREATE INDEX IF NOT EXISTS idx_telemetry_observed_at
    ON telemetry (asset_id, observed_at);

CREATE INDEX IF NOT EXISTS idx_telemetry_source_index
    ON telemetry (asset_id, source_index);

CREATE TABLE IF NOT EXISTS failure_events (
    event_id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL REFERENCES assets (asset_id),
    source_event_id INTEGER NOT NULL,
    source_id_occurrence SMALLINT NOT NULL DEFAULT 1
        CHECK (source_id_occurrence > 0),
    source_failure_type TEXT NOT NULL,
    failure_type TEXT NOT NULL,
    severity TEXT,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ NOT NULL,
    maintenance_remark TEXT,
    source_text TEXT,
    source_document TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (ended_at > started_at)
);

CREATE INDEX IF NOT EXISTS idx_failure_events_started_at
    ON failure_events (asset_id, started_at);

CREATE OR REPLACE VIEW sensor_field_catalog AS
SELECT
    source_column,
    db_column,
    field_role,
    unit,
    description
FROM (
    VALUES
        ('Unnamed: 0', 'source_index', 'identifier', 'source row identifier',
         'Source CSV index; increases by 10 and is not a timestamp.'),
        ('timestamp', 'observed_at', 'time', 'UTC timestamp',
         'Naive source timestamp interpreted as UTC by project convention.'),
        ('TP2', 'tp2_bar', 'analog', 'bar', 'Compressor pressure.'),
        ('TP3', 'tp3_bar', 'analog', 'bar', 'Pneumatic panel pressure.'),
        ('H1', 'h1_bar', 'analog', 'bar', 'Cyclone separator discharge pressure.'),
        ('DV_pressure', 'dv_pressure_bar', 'analog', 'bar',
         'Dryer tower discharge pressure drop.'),
        ('Reservoirs', 'reservoirs_bar', 'analog', 'bar',
         'Downstream reservoir pressure.'),
        ('Oil_temperature', 'oil_temperature_c', 'analog', 'degC',
         'Oil temperature.'),
        ('Motor_current', 'motor_current_a', 'analog', 'A',
         'Motor current.'),
        ('COMP', 'comp', 'digital_binary', '0/1',
         'Compressor inlet valve electrical signal.'),
        ('DV_eletric', 'dv_electric', 'digital_binary', '0/1',
         'Compressor outlet valve control signal.'),
        ('Towers', 'towers', 'digital_binary', '0/1',
         'Dryer tower selection signal.'),
        ('MPG', 'mpg', 'digital_binary', '0/1',
         'Low-pressure start electrical signal.'),
        ('LPS', 'lps', 'digital_binary', '0/1',
         'Low-pressure detection signal.'),
        ('Pressure_switch', 'pressure_switch', 'digital_binary', '0/1',
         'Pilot control valve pressure signal.'),
        ('Oil_level', 'oil_level', 'digital_binary', '0/1',
         'Low oil level detection signal.'),
        ('Caudal_impulses', 'caudal_impulses', 'digital_pulse', '0/1',
         'Flowmeter pulse signal; not a monotonic cumulative counter.')
) AS fields (
    source_column,
    db_column,
    field_role,
    unit,
    description
);
