-- 6. ODOO REPORT
CREATE OR REPLACE TABLE `sales_staging_som.odoo_report` AS
SELECT
  o.CreatedOn AS created_on,
  o.SentOn AS sent_on,
  UPPER(TRIM(o.CustomerLevel1)) AS sales_type,
  UPPER(TRIM(o.CustomerLevel2)) AS sub_sales_type,
  UPPER(TRIM(o.OrderReference)) AS order_number,
  UPPER(TRIM(o.ItemName)) AS item_name,
  o.Quantity AS quantity,
  CAST(NULL AS FLOAT64) AS unit_price,
  CAST(NULL AS FLOAT64) AS discount_value,
  UPPER(TRIM(o.CustomerName)) AS customer_name,
  UPPER(TRIM(REPLACE(o.CustomerState, ' (ID)', ''))) AS province,
  UPPER(TRIM(o.CustomerCity)) AS city,
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
  'ODOO_OPTOLUMBUNG' AS source
FROM `sales_raw_som.raw_odoo_internal` o
LEFT JOIN `sales_staging_som.dim_channel` c
  ON UPPER(TRIM(o.CustomerLevel1)) = UPPER(TRIM(c.sales_type))
  AND COALESCE(UPPER(TRIM(o.CustomerLevel2)), 'NONE') =
      COALESCE(UPPER(TRIM(c.sub_sales_type)), 'NONE')
LEFT JOIN `sales_staging_som.dim_sku` s
  ON UPPER(TRIM(o.ItemName)) = s.item_name
WHERE
  (o.Checked IS NULL OR UPPER(TRIM(o.Checked)) <> 'REPORTED')
  AND o.SentOn >= DATE('2025-01-01')
  AND UPPER(TRIM(o.ItemName)) NOT IN (
    'SALES',
    'DOWN PAYMENTS',
    'SALES DOWN PAYMENTS',
    '[DISC] DISCOUNT',
    '[ONGKOS KIRIM] DELIVERY FEE'
  );
