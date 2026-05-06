{{ config(materialized='view', alias='suburbs_scores') }}

SELECT
    m.suburb_name,
    m.state,
    m.dining_count,
    m.parks_count,
    m.wellness_count,
    m.childcare_count,
    m.transport_count,
    m.shopping_count,
    m.education_count,
    m.healthcare_count,
    ROUND((m.dining_count     ::NUMERIC / 100) * 100, 1) AS dining_score,
    ROUND((m.parks_count      ::NUMERIC / 100) * 100, 1) AS parks_score,
    ROUND((m.wellness_count   ::NUMERIC / 100) * 100, 1) AS wellness_score,
    ROUND((m.childcare_count  ::NUMERIC / 100) * 100, 1) AS childcare_score,
    ROUND((m.transport_count  ::NUMERIC / 100) * 100, 1) AS transport_score,
    ROUND((m.shopping_count   ::NUMERIC / 100) * 100, 1) AS shopping_score,
    ROUND((m.education_count  ::NUMERIC / 100) * 100, 1) AS education_score,
    ROUND((m.healthcare_count ::NUMERIC / 100) * 100, 1) AS healthcare_score,
    ROUND((
        (m.dining_count + m.parks_count + m.wellness_count + m.childcare_count +
         m.transport_count + m.shopping_count + m.education_count + m.healthcare_count)
        ::NUMERIC / 800) * 100, 1
    ) AS livability_score,
    r.fetched_at,
    r.latitude,
    r.longitude
FROM {{ source('public', 'suburbs_metrics') }} m
JOIN {{ source('public', 'suburbs_raw') }} r
    ON m.suburb_name = r.suburb_name

