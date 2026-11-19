-- 9. FACT SELL IN
CREATE OR REPLACE TABLE `sales_marts_som.fact_sell_in` AS
WITH base AS (
  SELECT *
  FROM `sales_marts_som.fact_sales`
  WHERE sent_on >= DATE('2025-01-01')
    AND (
      brand IN ('SCARLETT', 'BIO BEAUTY LAB', 'WHITEINC', 'BUENA')
      OR brand IS NULL
    )
    AND UPPER(COALESCE(type_of_item, '')) NOT IN ('MERCHANDISE', 'SAMPLE')
    AND UPPER(COALESCE(sales_type, '')) NOT IN (
      'ENDORSE',
      'ENDORSE AFFILIATE',
      'EVENT',
      'INTSCARLETT',
      'KIRIM ULANG'
    )
    AND UPPER(COALESCE(sub_sales_type, '')) <> 'INTERCOMPANY'
    AND NOT (
      UPPER(COALESCE(brand, '')) = 'WHITEINC'
      AND UPPER(COALESCE(sub_channel, '')) IN (
        'SHOPEE',
        'SHOPEE MALL',
        'SHOPEE STAR',
        'TIKTOK SHOP',
        'SOCIAL MEDIA'
      )
    )
),
mapped AS (
  SELECT
    b.*,
    CASE
      WHEN sub_channel = 'DISTRIBUTOR' THEN 'GT-DIST'
      WHEN sub_channel = 'GT ONLINE INDEPENDENT' THEN 'GT-RESELLER ONLINE'
      WHEN sub_channel = 'RESELLER STOCK POINT' THEN 'GT-RSP'
      WHEN sub_channel = 'COSMETIC KEY ACCOUNT' THEN 'MT-COSMETIC'
      WHEN sub_channel = 'HABA KEY ACCOUNT' THEN 'MT-HABA'
      WHEN sub_channel = 'HYPERMARKET SUPERMARKET KEY ACCOUNT' THEN 'MT-HYP/SPM'
      WHEN sub_channel = 'MINIMARKET KEY ACCOUNT' THEN 'MT-MINIS'
      WHEN sub_channel IN (
        'LOCAL KEY ACCOUNT',
        'MODERN TRADE INDEPENDENT',
        'MT ONLINE INDEPENDENT'
      ) THEN 'MT-OTHERS'
      WHEN sub_channel IN (
        'SHOPEE',
        'SHOPEE MALL',
        'SHOPEE STAR'
      ) THEN 'OL-SHOPEE'
      WHEN sub_channel = 'TIKTOK SHOP' THEN 'OL-TIKTOK'
      WHEN sub_channel IN (
        'LAZADA',
        'TOKOPEDIA',
        'WEBSITE',
        'ZALORA',
        'SOCIAL MEDIA',
        'MANUAL'
      ) THEN 'OL-OTHERS'
      ELSE 'GT-RESELLER OFFLINE'
    END AS sub_channel_group,
    COALESCE(a.area, 'OTHERS') AS area,
    COALESCE(a.region, 'OTHERS') AS region
  FROM base b
  LEFT JOIN `sales_staging_som.dim_area` a
    ON UPPER(TRIM(b.province)) = a.province
)
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
  area,
  region,

  CASE
    WHEN UPPER(sub_channel_group) LIKE 'GT%' THEN 'OFFLINE GT'
    WHEN sub_channel_group IN ('OL-SHOPEE', 'OL-TIKTOK', 'OL-OTHERS')
      THEN 'ONLINE OFFICIAL'
    ELSE 'OFFLINE MT'
  END AS channel_group,

  channel,
  sub_channel,
  sub_channel_group,
  brand,
  category,
  sub_category,
  variant,
  product_name,
  type_of_item,
  product_type,
  source
FROM mapped
