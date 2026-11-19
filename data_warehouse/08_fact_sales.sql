-- 8. FACT SALES
CREATE OR REPLACE TABLE `sales_marts_som.fact_sales` AS

SELECT
    created_on,
    sent_on,
    sales_type,
    sub_sales_type,
    order_number,
    item_name,
    quantity,
    unit_price,
    discount_value,
    customer_name,
    province,
    city,
    channel_group,
    channel,
    sub_channel,
    brand,
    category,
    sub_category,
    variant,
    product_name,
    type_of_item,
    product_type,
    source

FROM `sales_staging_som.anchanto_report`

WHERE LOWER(order_status) = 'delivered'
   OR (
        LOWER(order_status) = 'dispatched'
        AND (
            (
                sent_on >= DATE('2025-06-01')
                AND sent_on < DATE('2025-08-01')
            )
        )
   )

UNION ALL

SELECT
    created_on,
    sent_on,
    sales_type,
    sub_sales_type,
    order_number,
    item_name,
    quantity,
    unit_price,
    discount_value,
    customer_name,
    province,
    city,
    channel_group,
    channel,
    sub_channel,
    brand,
    category,
    sub_category,
    variant,
    product_name,
    type_of_item,
    product_type,
    source

FROM `sales_staging_som.accurate_report`

UNION ALL

SELECT
    created_on,
    sent_on,
    sales_type,
    sub_sales_type,
    order_number,
    item_name,
    quantity,
    unit_price,
    discount_value,
    customer_name,
    province,
    city,
    channel_group,
    channel,
    sub_channel,
    brand,
    category,
    sub_category,
    variant,
    product_name,
    type_of_item,
    product_type,
    source

FROM `sales_staging_som.odoo_report`;
