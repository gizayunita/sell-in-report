-- 5. ACCURATE REPORT
CREATE OR REPLACE TABLE `sales_staging_som.accurate_report` AS
SELECT
  a.CreatedOn AS created_on,
  a.SentOn AS sent_on,
  UPPER(TRIM(a.Sales_Type)) AS sales_type,
  CAST(NULL AS STRING) AS sub_sales_type,
  UPPER(TRIM(a.DO_Number)) AS order_number,
  UPPER(TRIM(a.Item_Name)) AS item_name,
  a.Quantity AS quantity,
  SAFE_DIVIDE(a.Revenue, NULLIF(a.Quantity, 0)) AS unit_price,
  CAST(NULL AS FLOAT64) AS discount_value,
  UPPER(TRIM(a.Customer)) AS customer_name,
  UPPER(TRIM(a.Province)) AS province,
  UPPER(TRIM(a.City)) AS city,
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
  'ACCURATE' AS source
FROM `sales_raw_som.raw_accurate_internal` a
LEFT JOIN `sales_staging_som.dim_channel` c
  ON UPPER(TRIM(a.Sales_Type)) = UPPER(TRIM(c.sales_type))
  AND COALESCE(UPPER(TRIM(c.sub_sales_type)), 'NONE') = 'NONE'
LEFT JOIN `sales_staging_som.dim_sku` s
  ON UPPER(TRIM(a.Item_Name)) = s.item_name
WHERE UPPER(TRIM(a.Customer)) NOT LIKE '%EMPLOYE%';
