-- Rebuild the Anchanto external table over normalized CSV exports.
-- The normalization workflow maps source header aliases and column order to this schema.
CREATE OR REPLACE EXTERNAL TABLE `sales_raw_som.raw_anchanto` (
    marketplace STRING,
    order_date STRING,
    order_number STRING,
    item_upc STRING,
    item_name STRING,
    ordered_quantity STRING,
    order_status STRING,
    customer_name STRING,
    shipping_city STRING,
    shipping_postcode STRING,
    order_packing_date STRING,
    delivery_date STRING,
    dispatch_scheduled_date STRING,
    unit_price STRING,
    dispatch_date STRING,
    discount_value STRING
)
OPTIONS (
    format = 'CSV',
    uris = ['gs://bucket_som/sales_parquet/raw/online/anchanto/scrwms/*.csv'],
    skip_leading_rows = 1,
    field_delimiter = ',',
    quote = '"',
    allow_quoted_newlines = TRUE,
    encoding = 'UTF-8'
);
