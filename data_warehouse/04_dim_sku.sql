-- 4. DIM SKU
CREATE OR REPLACE TABLE `sales_staging_som.dim_sku` AS
SELECT
  UPPER(TRIM(ItemName)) AS item_name,
  ANY_VALUE(Brand) AS brand,
  ANY_VALUE(Category) AS category,
  ANY_VALUE(Sub_Category) AS sub_category,
  ANY_VALUE(Variant) AS variant,
  ANY_VALUE(Product_Name) AS product_name,
  ANY_VALUE(Type_of_Item) AS type_of_item,
  ANY_VALUE(Product_Type) AS product_type
FROM `sales_raw_som.raw_master_sku`
WHERE TRIM(ItemName) <> ''
GROUP BY 1;
