-- 3. ODOO
CREATE OR REPLACE TABLE sales_raw_som.raw_odoo_internal AS
SELECT
  SAFE_CAST(CreatedOn AS DATE) AS CreatedOn,

  CustomerLevel1,
  CustomerLevel2,
  CustomerState,
  CustomerCity,
  CustomerName,
  CustomerEntity,
  SalesPerson,
  ItemName,
  OrderReference,

  SAFE_CAST(REPLACE(Qty_Ordered, ',', '') AS INT64) AS Qty_Ordered,
  SAFE_CAST(REPLACE(Qty_To_Deliver, ',', '') AS INT64) AS Qty_To_Deliver,
  SAFE_CAST(REPLACE(Qty_Delivered, ',', '') AS INT64) AS Qty_Delivered,
  SAFE_CAST(REPLACE(Qty_To_Invoice, ',', '') AS INT64) AS Qty_To_Invoice,
  SAFE_CAST(REPLACE(Qty_Invoiced, ',', '') AS INT64) AS Qty_Invoiced,

  Status,
  DO_Number,
  SO_Number,
  Invoice_Status,

  SAFE_CAST(SentOn AS DATE) AS SentOn,

  Delivery_Status,
  Payment_Terms,
  Address,

  SAFE_CAST(REPLACE(Quantity, ',', '') AS INT64) AS Quantity,
  Checked,
  Customer_and_Address,

  SAFE_CAST(InvoiceOn AS DATE) AS InvoiceOn
FROM `sales_raw_som.raw_odoo`
WHERE ItemName IS NOT NULL
  AND TRIM(ItemName) <> ''
  AND UPPER(TRIM(ItemName)) <> 'ITEMNAME';
