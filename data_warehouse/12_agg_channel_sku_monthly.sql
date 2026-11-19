-- 12. AGG CHANNEL SKU MONTHLY
CREATE OR REPLACE TABLE `sales_marts_som.agg_channel_sku_monthly` AS
SELECT
  DATE_TRUNC(sent_on, MONTH) AS month,
  brand,
  category,
  sub_category,
  variant,
  product_name,
  type_of_item,
  channel_group,
  channel,
  sub_channel_group,
  sub_channel,
  region,
  area,
  SUM(quantity) AS quantity,
  SUM(quantity * COALESCE(unit_price, 0)) AS revenue
FROM `sales_marts_som.fact_sell_in`
GROUP BY
  month,
  brand,
  category,
  sub_category,
  variant,
  product_name,
  type_of_item,
  channel_group,
  channel,
  sub_channel_group,
  sub_channel,
  region,
  area
ORDER BY month DESC
