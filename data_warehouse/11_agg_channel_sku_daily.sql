-- 11. AGG CHANNEL SKU DAILY
CREATE OR REPLACE TABLE `sales_marts_som.agg_channel_sku_daily` AS
SELECT
  created_on,
  sent_on,
  brand,
  category,
  sub_category,
  variant,
  product_name,
  type_of_item,
  channel_group,
  sub_channel_group,
  sub_channel,
  SUM(quantity) AS quantity,
  SUM(quantity * COALESCE(unit_price, 0)) AS revenue
FROM `sales_marts_som.fact_sell_in`
GROUP BY
  created_on,
  sent_on,
  brand,
  category,
  sub_category,
  variant,
  product_name,
  type_of_item,
  channel_group,
  sub_channel_group,
  sub_channel
