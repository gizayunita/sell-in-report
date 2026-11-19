-- 7. ANCHANTO REPORT
CREATE OR REPLACE TABLE `sales_staging_som.anchanto_report` AS

WITH base_anchanto AS (
    SELECT
        DATE(order_date) AS created_on,
        delivery_date,
        dispatch_date AS parsed_dispatch_date,

        REPLACE(
            UPPER(
                SPLIT(marketplace, '_')[
                    ORDINAL(
                        ARRAY_LENGTH(SPLIT(marketplace, '_'))
                    )
                ]
            ),
            'NEXUS',
            'ENDORSE'
        ) AS sales_type,

        order_number,
        UPPER(TRIM(item_name)) AS item_name,
        ordered_quantity AS quantity,
        COALESCE(shipping_postcode, '-') AS post_code,
        unit_price,
        discount_value,
        UPPER(TRIM(customer_name)) AS customer_name,
        LOWER(order_status) AS order_status,
        UPPER(TRIM(shipping_city)) AS raw_city

    FROM `sales_raw_som.raw_anchanto_internal`

    WHERE NOT CONTAINS_SUBSTR(
        marketplace,
        'MPL_INTScarlett'
    )
      AND UPPER(customer_name) NOT LIKE '%OPTO LUMBUNG%'
),

prepared AS (
    SELECT
        *,

        CASE
            WHEN order_status = 'dispatched'
                 AND (
                     (
                         DATE(parsed_dispatch_date) >= DATE('2025-06-01')
                         AND DATE(parsed_dispatch_date) < DATE('2025-08-01')
                     )
                 )
            THEN DATE(parsed_dispatch_date)

            ELSE DATE(delivery_date)
        END AS sent_on

    FROM base_anchanto
)

SELECT
    b.created_on,
    b.sent_on,
    b.sales_type,

    CAST(NULL AS STRING) AS sub_sales_type,

    UPPER(TRIM(b.order_number)) AS order_number,
    b.item_name,
    b.quantity,

    CAST(b.unit_price AS FLOAT64) AS unit_price,
    CAST(b.discount_value AS FLOAT64) AS discount_value,

    b.customer_name,
    b.order_status,

    COALESCE(
        CAST(o.ADM1 AS STRING),
        CAST(k.province AS STRING),
        '-'
    ) AS province,

    COALESCE(
        CAST(o.ADM2_Standardized AS STRING),
        CAST(k.city AS STRING),
        CAST(b.raw_city AS STRING),
        '-'
    ) AS city,

    c.channel_group,
    c.channel,
    c.sub_channel,

    s.brand,
    s.category,
    s.sub_category,
    s.variant,
    s.product_name,
    s.type_of_item,
    s.product_type,

    'ANCHANTO' AS source

FROM prepared b

LEFT JOIN `sales_staging_som.dim_kodepos` k
    ON b.post_code = k.kode_pos

LEFT JOIN `sales_staging_som.dim_channel` c
    ON UPPER(TRIM(b.sales_type))
       = UPPER(TRIM(c.sales_type))
   AND (
        c.sub_sales_type IS NULL
        OR UPPER(TRIM(c.sub_sales_type)) = 'NONE'
   )

LEFT JOIN `sales_staging_som.dim_sku` s
    ON b.item_name = s.item_name

LEFT JOIN `sales_staging_som.staging_sales_pcc_order_number` o
    ON UPPER(TRIM(b.order_number))
       = UPPER(TRIM(o.Order_Number))
;