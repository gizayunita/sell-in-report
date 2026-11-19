-- 1. ANCHANTO
CREATE OR REPLACE TABLE `sales_raw_som.raw_anchanto_internal` AS

SELECT
    marketplace,

    SAFE.PARSE_DATETIME(
        '%d/%m/%Y, %H:%M:%S',
        order_date
    ) AS order_date,

    order_number,
    item_upc,
    item_name,

    SAFE_CAST(
        ordered_quantity AS INT64
    ) AS ordered_quantity,

    order_status,
    customer_name,
    shipping_city,
    shipping_postcode,

    SAFE.PARSE_DATETIME(
        '%d/%m/%Y, %H:%M:%S',
        order_packing_date
    ) AS order_packing_date,

    -- DELIVERY DATE: normalized upstream to DD/MM/YYYY, HH:MM:SS.
    -- Date-only source values are represented as 00:00:00.
    SAFE.PARSE_DATETIME(
        '%d/%m/%Y, %H:%M:%S',
        NULLIF(TRIM(delivery_date), '')
    ) AS delivery_date,

    SAFE.PARSE_DATETIME(
        '%d/%m/%Y, %H:%M:%S',
        dispatch_scheduled_date
    ) AS dispatch_scheduled_date,

    SAFE_CAST(
        unit_price AS FLOAT64
    ) AS unit_price,

    SAFE.PARSE_DATETIME(
        '%d/%m/%Y, %H:%M:%S',
        dispatch_date
    ) AS dispatch_date,

    SAFE_CAST(
        discount_value AS FLOAT64
    ) AS discount_value

FROM `sales_raw_som.raw_anchanto`;
