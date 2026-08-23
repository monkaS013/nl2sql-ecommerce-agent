# Dataset

This project uses the **Brazilian E-Commerce Public Dataset by Olist**, a public
dataset of ~100k orders. It is **not** committed to this repo.

1. Download it from Kaggle: <https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce>
2. Unzip the CSVs into this `data/` folder. You should end up with files like:

```
data/
├── olist_orders_dataset.csv
├── olist_order_items_dataset.csv
├── olist_order_payments_dataset.csv
├── olist_order_reviews_dataset.csv
├── olist_products_dataset.csv
├── olist_customers_dataset.csv
├── olist_sellers_dataset.csv
├── olist_geolocation_dataset.csv
└── product_category_name_translation.csv
```

3. In the app sidebar, click **Build / rebuild database**. Each CSV becomes a
   table (the `olist_` prefix and `_dataset` suffix are stripped, so
   `olist_order_items_dataset.csv` becomes the table `order_items`).

The CSVs and the generated `olist.duckdb` are gitignored.
