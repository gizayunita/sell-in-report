-- 2. ACCURATE
CREATE OR REPLACE TABLE `sales_raw_som.raw_accurate_internal` AS
SELECT
  SAFE_CAST(CreatedOn AS DATE) AS CreatedOn,
  SAFE_CAST(SentOn AS DATE) AS SentOn,
  SO_Number,
  DO_Number,
  Sales_Type,
  Customer,
  City,
  Province,
  Item_Name,
  SAFE_CAST(Qty_Sales AS INT64) AS Qty_Sales,
  SAFE_CAST(Revenue AS INT64) AS Revenue,
  SAFE_CAST(Qty_Return AS INT64) AS Qty_Return,
  SAFE_CAST(Quantity AS INT64) AS Quantity
FROM `sales_raw_som.raw_accurate`
WHERE SO_Number IS NOT NULL
  AND TRIM(SO_Number) <> ''
  AND UPPER(TRIM(SO_Number)) <> 'SO NUMBER';
