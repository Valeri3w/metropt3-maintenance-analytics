CREATE OR REPLACE VIEW telemetry_gaps AS
WITH ordered_telemetry AS (
    SELECT
        t.asset_id,
        t.observed_at,
        t.source_row_number,
        LAG(t.observed_at) OVER (
            PARTITION BY t.asset_id
            ORDER BY t.observed_at
        ) AS previous_observed_at,
        LAG(t.source_row_number) OVER (
            PARTITION BY t.asset_id
            ORDER BY t.observed_at
        ) AS previous_source_row_number,
        a.nominal_interval_seconds,
        a.gap_threshold_seconds
    FROM telemetry AS t
    JOIN assets AS a ON a.asset_id = t.asset_id
)
SELECT
    asset_id,
    previous_observed_at,
    observed_at AS next_observed_at,
    previous_observed_at
        + make_interval(secs => nominal_interval_seconds) AS gap_started_at,
    observed_at AS gap_ended_at,
    EXTRACT(EPOCH FROM (observed_at - previous_observed_at))::BIGINT
        - nominal_interval_seconds AS unobserved_seconds,
    (
        EXTRACT(EPOCH FROM (observed_at - previous_observed_at))
        - nominal_interval_seconds
    ) / 3600.0 AS unobserved_hours,
    previous_source_row_number,
    source_row_number
FROM ordered_telemetry
WHERE EXTRACT(EPOCH FROM (observed_at - previous_observed_at))
    > gap_threshold_seconds;

CREATE OR REPLACE VIEW failure_event_metrics AS
WITH event_sequence AS (
    SELECT
        event_id,
        asset_id,
        source_event_id,
        source_id_occurrence,
        source_failure_type,
        failure_type,
        severity,
        started_at,
        ended_at,
        maintenance_remark,
        source_document,
        LAG(event_id) OVER (
            PARTITION BY asset_id
            ORDER BY started_at, event_id
        ) AS previous_event_id,
        LAG(ended_at) OVER (
            PARTITION BY asset_id
            ORDER BY started_at, event_id
        ) AS previous_event_ended_at
    FROM failure_events
)
SELECT
    event_id,
    asset_id,
    source_event_id,
    source_id_occurrence,
    source_failure_type,
    failure_type,
    severity,
    started_at,
    ended_at,
    maintenance_remark,
    source_document,
    EXTRACT(EPOCH FROM (ended_at - started_at)) AS duration_seconds,
    EXTRACT(EPOCH FROM (ended_at - started_at)) / 3600.0
        AS duration_hours,
    previous_event_id,
    previous_event_ended_at,
    EXTRACT(EPOCH FROM (started_at - previous_event_ended_at))
        AS seconds_since_previous_annotation,
    EXTRACT(EPOCH FROM (started_at - previous_event_ended_at)) / 3600.0
        AS hours_since_previous_annotation
FROM event_sequence;

CREATE OR REPLACE VIEW failure_type_pareto AS
WITH grouped AS (
    SELECT
        failure_type,
        COUNT(*) AS event_count,
        SUM(EXTRACT(EPOCH FROM (ended_at - started_at)))
            AS cumulative_seconds
    FROM failure_events
    GROUP BY failure_type
),
with_share AS (
    SELECT
        failure_type,
        event_count,
        cumulative_seconds,
        cumulative_seconds / 3600.0 AS cumulative_hours,
        100.0 * cumulative_seconds
            / NULLIF(SUM(cumulative_seconds) OVER (), 0)
            AS cumulative_share_pct
    FROM grouped
)
SELECT
    failure_type,
    event_count,
    cumulative_seconds,
    cumulative_hours,
    cumulative_share_pct,
    SUM(cumulative_share_pct) OVER (
        ORDER BY cumulative_seconds DESC, failure_type
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_cumulative_share_pct
FROM with_share
ORDER BY cumulative_seconds DESC, failure_type;

CREATE OR REPLACE VIEW data_quality_summary AS
WITH bounds AS (
    SELECT
        asset_id,
        COUNT(*) AS telemetry_row_count,
        MIN(observed_at) AS first_observed_at,
        MAX(observed_at) AS last_observed_at,
        EXTRACT(EPOCH FROM (MAX(observed_at) - MIN(observed_at)))
            AS calendar_span_seconds
    FROM telemetry
    GROUP BY asset_id
),
gap_summary AS (
    SELECT
        asset_id,
        COUNT(*) AS gap_count,
        COALESCE(SUM(unobserved_seconds), 0) AS unobserved_seconds
    FROM telemetry_gaps
    GROUP BY asset_id
)
SELECT
    b.asset_id,
    b.telemetry_row_count,
    b.first_observed_at,
    b.last_observed_at,
    b.calendar_span_seconds,
    b.calendar_span_seconds / 3600.0 AS calendar_span_hours,
    COALESCE(g.gap_count, 0) AS gap_count,
    COALESCE(g.unobserved_seconds, 0) AS unobserved_seconds,
    COALESCE(g.unobserved_seconds, 0) / 3600.0 AS unobserved_hours,
    b.calendar_span_seconds - COALESCE(g.unobserved_seconds, 0)
        AS effective_monitoring_seconds,
    (
        b.calendar_span_seconds - COALESCE(g.unobserved_seconds, 0)
    ) / 3600.0 AS effective_monitoring_hours,
    100.0 * (
        b.calendar_span_seconds - COALESCE(g.unobserved_seconds, 0)
    ) / NULLIF(b.calendar_span_seconds, 0) AS calendar_coverage_pct
FROM bounds AS b
LEFT JOIN gap_summary AS g ON g.asset_id = b.asset_id;

CREATE OR REPLACE VIEW failure_overall_metrics AS
WITH totals AS (
    SELECT
        COUNT(*) AS event_count,
        AVG(EXTRACT(EPOCH FROM (ended_at - started_at)))
            AS average_duration_seconds,
        MAX(EXTRACT(EPOCH FROM (ended_at - started_at)))
            AS longest_duration_seconds,
        SUM(EXTRACT(EPOCH FROM (ended_at - started_at)))
            AS cumulative_duration_seconds
    FROM failure_events
),
longest AS (
    SELECT
        event_id AS longest_event_id,
        failure_type AS longest_failure_type,
        started_at AS longest_started_at,
        ended_at AS longest_ended_at
    FROM failure_events
    ORDER BY ended_at - started_at DESC, event_id
    LIMIT 1
),
quality AS (
    SELECT effective_monitoring_seconds
    FROM data_quality_summary
    LIMIT 1
)
SELECT
    t.event_count,
    t.average_duration_seconds,
    t.average_duration_seconds / 3600.0 AS average_duration_hours,
    t.longest_duration_seconds,
    t.longest_duration_seconds / 3600.0 AS longest_duration_hours,
    t.cumulative_duration_seconds,
    t.cumulative_duration_seconds / 3600.0 AS cumulative_duration_hours,
    l.longest_event_id,
    l.longest_failure_type,
    l.longest_started_at,
    l.longest_ended_at,
    q.effective_monitoring_seconds,
    q.effective_monitoring_seconds / 3600.0 AS effective_monitoring_hours,
    100.0 * t.cumulative_duration_seconds
        / NULLIF(q.effective_monitoring_seconds, 0)
        AS annotated_share_of_effective_time_pct
FROM totals AS t
CROSS JOIN quality AS q
LEFT JOIN longest AS l ON TRUE;

CREATE OR REPLACE VIEW failure_gap_overlap AS
SELECT
    e.event_id,
    g.gap_started_at,
    g.gap_ended_at,
    g.unobserved_hours,
    GREATEST(e.started_at, g.gap_started_at) AS overlap_started_at,
    LEAST(e.ended_at, g.gap_ended_at) AS overlap_ended_at,
    EXTRACT(
        EPOCH FROM (
            LEAST(e.ended_at, g.gap_ended_at)
            - GREATEST(e.started_at, g.gap_started_at)
        )
    ) AS overlap_seconds
FROM failure_events AS e
JOIN telemetry_gaps AS g
    ON g.asset_id = e.asset_id
    AND g.gap_started_at < e.ended_at
    AND g.gap_ended_at > e.started_at;

CREATE OR REPLACE VIEW failure_event_gap_summary AS
WITH overlap_summary AS (
    SELECT
        event_id,
        COUNT(*) AS gap_count,
        COALESCE(SUM(overlap_seconds), 0) AS gap_overlap_seconds
    FROM failure_gap_overlap
    GROUP BY event_id
)
SELECT
    e.event_id,
    e.failure_type,
    e.started_at,
    e.ended_at,
    EXTRACT(EPOCH FROM (e.ended_at - e.started_at)) AS duration_seconds,
    COALESCE(o.gap_count, 0) AS gap_count,
    COALESCE(o.gap_overlap_seconds, 0) AS gap_overlap_seconds,
    COALESCE(o.gap_overlap_seconds, 0) / 3600.0
        AS gap_overlap_hours,
    (
        EXTRACT(EPOCH FROM (e.ended_at - e.started_at))
        - COALESCE(o.gap_overlap_seconds, 0)
    ) AS observed_seconds_within_annotation,
    100.0 * (
        EXTRACT(EPOCH FROM (e.ended_at - e.started_at))
        - COALESCE(o.gap_overlap_seconds, 0)
    ) / NULLIF(EXTRACT(EPOCH FROM (e.ended_at - e.started_at)), 0)
        AS observed_coverage_pct
FROM failure_events AS e
LEFT JOIN overlap_summary AS o ON o.event_id = e.event_id;

DROP FUNCTION IF EXISTS report_period_quality(
    TIMESTAMPTZ,
    TIMESTAMPTZ
) CASCADE;

CREATE OR REPLACE FUNCTION report_period_quality(
    p_started_at TIMESTAMPTZ,
    p_ended_at TIMESTAMPTZ
)
RETURNS TABLE (
    period_started_at TIMESTAMPTZ,
    period_ended_at TIMESTAMPTZ,
    telemetry_started_at TIMESTAMPTZ,
    telemetry_ended_at TIMESTAMPTZ,
    bounded_period_seconds DOUBLE PRECISION,
    gap_count BIGINT,
    unobserved_seconds DOUBLE PRECISION,
    unobserved_hours DOUBLE PRECISION,
    effective_monitoring_seconds DOUBLE PRECISION,
    effective_monitoring_hours DOUBLE PRECISION,
    calendar_coverage_pct DOUBLE PRECISION
)
LANGUAGE SQL
STABLE
AS $$
WITH bounds AS (
    SELECT
        MIN(observed_at) AS first_observed_at,
        MAX(observed_at) AS last_observed_at
    FROM telemetry
),
clipped AS (
    SELECT
        GREATEST(p_started_at, b.first_observed_at) AS period_started_at,
        LEAST(p_ended_at, b.last_observed_at) AS period_ended_at,
        b.first_observed_at AS telemetry_started_at,
        b.last_observed_at AS telemetry_ended_at
    FROM bounds AS b
),
gap_overlap AS (
    SELECT
        COUNT(*)::BIGINT AS gap_count,
        COALESCE(
            SUM(
                EXTRACT(
                    EPOCH FROM (
                        LEAST(c.period_ended_at, g.gap_ended_at)
                        - GREATEST(c.period_started_at, g.gap_started_at)
                    )
                )
            ),
            0
        )::DOUBLE PRECISION AS unobserved_seconds
    FROM telemetry_gaps AS g
    CROSS JOIN clipped AS c
    WHERE c.period_started_at < c.period_ended_at
      AND g.gap_started_at < c.period_ended_at
      AND g.gap_ended_at > c.period_started_at
)
SELECT
    c.period_started_at,
    c.period_ended_at,
    c.telemetry_started_at,
    c.telemetry_ended_at,
    CASE
        WHEN c.period_started_at < c.period_ended_at
        THEN EXTRACT(EPOCH FROM (c.period_ended_at - c.period_started_at))
        ELSE 0
    END::DOUBLE PRECISION AS bounded_period_seconds,
    g.gap_count,
    g.unobserved_seconds,
    g.unobserved_seconds / 3600.0 AS unobserved_hours,
    GREATEST(
        0,
        CASE
            WHEN c.period_started_at < c.period_ended_at
            THEN EXTRACT(EPOCH FROM (c.period_ended_at - c.period_started_at))
            ELSE 0
        END - g.unobserved_seconds
    )::DOUBLE PRECISION AS effective_monitoring_seconds,
    GREATEST(
        0,
        CASE
            WHEN c.period_started_at < c.period_ended_at
            THEN EXTRACT(EPOCH FROM (c.period_ended_at - c.period_started_at))
            ELSE 0
        END - g.unobserved_seconds
    ) / 3600.0 AS effective_monitoring_hours,
    100.0 * GREATEST(
        0,
        CASE
            WHEN c.period_started_at < c.period_ended_at
            THEN EXTRACT(EPOCH FROM (c.period_ended_at - c.period_started_at))
            ELSE 0
        END - g.unobserved_seconds
    ) / NULLIF(
        CASE
            WHEN c.period_started_at < c.period_ended_at
            THEN EXTRACT(EPOCH FROM (c.period_ended_at - c.period_started_at))
            ELSE 0
        END,
        0
    ) AS calendar_coverage_pct
FROM clipped AS c
CROSS JOIN gap_overlap AS g;
$$;

CREATE OR REPLACE FUNCTION report_period_metrics(
    p_started_at TIMESTAMPTZ,
    p_ended_at TIMESTAMPTZ
)
RETURNS TABLE (
    period_started_at TIMESTAMPTZ,
    period_ended_at TIMESTAMPTZ,
    event_count BIGINT,
    average_duration_seconds DOUBLE PRECISION,
    average_duration_hours DOUBLE PRECISION,
    longest_duration_seconds DOUBLE PRECISION,
    longest_duration_hours DOUBLE PRECISION,
    cumulative_duration_seconds DOUBLE PRECISION,
    cumulative_duration_hours DOUBLE PRECISION,
    longest_event_id TEXT,
    longest_failure_type TEXT,
    longest_started_at TIMESTAMPTZ,
    longest_ended_at TIMESTAMPTZ,
    effective_monitoring_seconds DOUBLE PRECISION,
    effective_monitoring_hours DOUBLE PRECISION,
    period_effective_hours DOUBLE PRECISION,
    annotated_share_of_effective_time_pct DOUBLE PRECISION
)
LANGUAGE SQL
STABLE
AS $$
WITH quality AS (
    SELECT *
    FROM report_period_quality(p_started_at, p_ended_at)
),
selected AS (
    SELECT *
    FROM failure_event_metrics
    WHERE started_at >= p_started_at
      AND started_at < p_ended_at
),
totals AS (
    SELECT
        COUNT(*)::BIGINT AS event_count,
        AVG(duration_seconds) AS average_duration_seconds,
        MAX(duration_seconds) AS longest_duration_seconds,
        COALESCE(SUM(duration_seconds), 0) AS cumulative_duration_seconds
    FROM selected
),
longest AS (
    SELECT
        event_id,
        failure_type,
        started_at,
        ended_at
    FROM selected
    ORDER BY duration_seconds DESC, event_id
    LIMIT 1
)
SELECT
    q.period_started_at,
    q.period_ended_at,
    t.event_count,
    t.average_duration_seconds,
    t.average_duration_seconds / 3600.0 AS average_duration_hours,
    t.longest_duration_seconds,
    t.longest_duration_seconds / 3600.0 AS longest_duration_hours,
    t.cumulative_duration_seconds,
    t.cumulative_duration_seconds / 3600.0 AS cumulative_duration_hours,
    l.event_id AS longest_event_id,
    l.failure_type AS longest_failure_type,
    l.started_at AS longest_started_at,
    l.ended_at AS longest_ended_at,
    q.effective_monitoring_seconds,
    q.effective_monitoring_hours,
    q.effective_monitoring_hours AS period_effective_hours,
    100.0 * t.cumulative_duration_seconds
        / NULLIF(q.effective_monitoring_seconds, 0)
        AS annotated_share_of_effective_time_pct
FROM totals AS t
CROSS JOIN quality AS q
LEFT JOIN longest AS l ON TRUE;
$$;

DROP FUNCTION IF EXISTS report_failure_pareto(TIMESTAMPTZ, TIMESTAMPTZ);

CREATE OR REPLACE FUNCTION report_failure_pareto(
    p_started_at TIMESTAMPTZ,
    p_ended_at TIMESTAMPTZ
)
RETURNS TABLE (
    failure_type TEXT,
    event_count BIGINT,
    cumulative_hours DOUBLE PRECISION,
    cumulative_share_pct DOUBLE PRECISION
)
LANGUAGE SQL
STABLE
AS $$
WITH grouped AS (
    SELECT
        failure_type,
        COUNT(*)::BIGINT AS event_count,
        SUM(duration_seconds) AS cumulative_seconds
    FROM failure_event_metrics
    WHERE started_at >= p_started_at
      AND started_at < p_ended_at
    GROUP BY failure_type
),
with_share AS (
    SELECT
        failure_type,
        event_count,
        cumulative_seconds,
        cumulative_seconds / 3600.0 AS cumulative_hours,
        100.0 * cumulative_seconds
            / NULLIF(SUM(cumulative_seconds) OVER (), 0)
            AS cumulative_share_pct
    FROM grouped
)
SELECT
    failure_type,
    event_count,
    cumulative_hours,
    SUM(cumulative_share_pct) OVER (
        ORDER BY cumulative_seconds DESC, failure_type
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_share_pct
FROM with_share
ORDER BY cumulative_seconds DESC, failure_type;
$$;

CREATE OR REPLACE FUNCTION report_failure_events(
    p_started_at TIMESTAMPTZ,
    p_ended_at TIMESTAMPTZ
)
RETURNS TABLE (
    event_id TEXT,
    source_event_id INTEGER,
    source_id_occurrence SMALLINT,
    source_failure_type TEXT,
    failure_type TEXT,
    severity TEXT,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    duration_seconds DOUBLE PRECISION,
    duration_hours DOUBLE PRECISION,
    previous_event_id TEXT,
    previous_event_ended_at TIMESTAMPTZ,
    seconds_since_previous_annotation DOUBLE PRECISION,
    hours_since_previous_annotation DOUBLE PRECISION,
    gap_count BIGINT,
    gap_overlap_hours DOUBLE PRECISION,
    observed_coverage_pct DOUBLE PRECISION,
    maintenance_remark TEXT,
    source_document TEXT
)
LANGUAGE SQL
STABLE
AS $$
SELECT
    m.event_id,
    m.source_event_id,
    m.source_id_occurrence,
    m.source_failure_type,
    m.failure_type,
    m.severity,
    m.started_at,
    m.ended_at,
    m.duration_seconds,
    m.duration_hours,
    m.previous_event_id,
    m.previous_event_ended_at,
    m.seconds_since_previous_annotation,
    m.hours_since_previous_annotation,
    COALESCE(g.gap_count, 0) AS gap_count,
    COALESCE(g.gap_overlap_seconds, 0) / 3600.0 AS gap_overlap_hours,
    COALESCE(g.observed_coverage_pct, 100.0) AS observed_coverage_pct,
    m.maintenance_remark,
    m.source_document
FROM failure_event_metrics AS m
LEFT JOIN failure_event_gap_summary AS g ON g.event_id = m.event_id
WHERE m.started_at >= p_started_at
  AND m.started_at < p_ended_at
ORDER BY m.started_at, m.event_id;
$$;

CREATE OR REPLACE FUNCTION failure_event_trace(p_event_id TEXT)
RETURNS TABLE (
    event_id TEXT,
    failure_type TEXT,
    severity TEXT,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    duration_hours DOUBLE PRECISION,
    maintenance_remark TEXT,
    source_document TEXT,
    sample_count BIGINT,
    first_sample_at TIMESTAMPTZ,
    last_sample_at TIMESTAMPTZ,
    first_source_row_number BIGINT,
    last_source_row_number BIGINT,
    first_source_index BIGINT,
    last_source_index BIGINT
)
LANGUAGE SQL
STABLE
AS $$
WITH target AS (
    SELECT *
    FROM failure_events
    WHERE event_id = p_event_id
),
summary AS (
    SELECT
        e.event_id,
        COUNT(t.observed_at)::BIGINT AS sample_count,
        MIN(t.observed_at) AS first_sample_at,
        MAX(t.observed_at) AS last_sample_at,
        MIN(t.source_row_number) AS first_source_row_number,
        MAX(t.source_row_number) AS last_source_row_number
    FROM target AS e
    LEFT JOIN telemetry AS t
        ON t.asset_id = e.asset_id
       AND t.observed_at >= e.started_at
       AND t.observed_at <= e.ended_at
    GROUP BY e.event_id
),
first_sample AS (
    SELECT t.source_index
    FROM target AS e
    JOIN telemetry AS t
      ON t.asset_id = e.asset_id
     AND t.observed_at >= e.started_at
     AND t.observed_at <= e.ended_at
    ORDER BY t.observed_at
    LIMIT 1
),
last_sample AS (
    SELECT t.source_index
    FROM target AS e
    JOIN telemetry AS t
      ON t.asset_id = e.asset_id
     AND t.observed_at >= e.started_at
     AND t.observed_at <= e.ended_at
    ORDER BY t.observed_at DESC
    LIMIT 1
)
SELECT
    e.event_id,
    e.failure_type,
    e.severity,
    e.started_at,
    e.ended_at,
    EXTRACT(EPOCH FROM (e.ended_at - e.started_at)) / 3600.0,
    e.maintenance_remark,
    e.source_document,
    s.sample_count,
    s.first_sample_at,
    s.last_sample_at,
    s.first_source_row_number,
    s.last_source_row_number,
    f.source_index,
    l.source_index
FROM target AS e
JOIN summary AS s ON s.event_id = e.event_id
LEFT JOIN first_sample AS f ON TRUE
LEFT JOIN last_sample AS l ON TRUE;
$$;

CREATE OR REPLACE FUNCTION failure_event_samples(
    p_event_id TEXT,
    p_limit INTEGER DEFAULT 8
)
RETURNS TABLE (
    sample_side TEXT,
    observed_at TIMESTAMPTZ,
    source_row_number BIGINT,
    source_index BIGINT,
    tp2_bar NUMERIC,
    tp3_bar NUMERIC,
    h1_bar NUMERIC,
    dv_pressure_bar NUMERIC,
    reservoirs_bar NUMERIC,
    oil_temperature_c NUMERIC,
    motor_current_a NUMERIC,
    comp BOOLEAN,
    dv_electric BOOLEAN,
    towers BOOLEAN,
    mpg BOOLEAN,
    lps BOOLEAN,
    pressure_switch BOOLEAN,
    oil_level BOOLEAN,
    caudal_impulses BOOLEAN
)
LANGUAGE SQL
STABLE
AS $$
WITH target AS (
    SELECT *
    FROM failure_events
    WHERE event_id = p_event_id
),
bounded_limit AS (
    SELECT GREATEST(1, LEAST(COALESCE(p_limit, 8), 50))::INTEGER AS row_limit
),
first_rows AS (
    SELECT
        'start'::TEXT AS sample_side,
        t.*
    FROM target AS e
    CROSS JOIN bounded_limit AS b
    JOIN telemetry AS t
      ON t.asset_id = e.asset_id
     AND t.observed_at >= e.started_at
     AND t.observed_at <= e.ended_at
    ORDER BY t.observed_at
    LIMIT (SELECT row_limit FROM bounded_limit)
),
last_rows AS (
    SELECT
        'end'::TEXT AS sample_side,
        t.*
    FROM target AS e
    CROSS JOIN bounded_limit AS b
    JOIN telemetry AS t
      ON t.asset_id = e.asset_id
     AND t.observed_at >= e.started_at
     AND t.observed_at <= e.ended_at
    ORDER BY t.observed_at DESC
    LIMIT (SELECT row_limit FROM bounded_limit)
)
SELECT
    combined.sample_side,
    combined.observed_at,
    combined.source_row_number,
    combined.source_index,
    combined.tp2_bar,
    combined.tp3_bar,
    combined.h1_bar,
    combined.dv_pressure_bar,
    combined.reservoirs_bar,
    combined.oil_temperature_c,
    combined.motor_current_a,
    combined.comp,
    combined.dv_electric,
    combined.towers,
    combined.mpg,
    combined.lps,
    combined.pressure_switch,
    combined.oil_level,
    combined.caudal_impulses
FROM (
    SELECT * FROM first_rows
    UNION
    SELECT * FROM last_rows
) AS combined
ORDER BY combined.observed_at;
$$;
