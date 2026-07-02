# schema warehouse tables customers orders pipeline context gotchas

**Tables in this warehouse:**

- `customers(customer_id, name, signup_date, country)`
- `orders(order_id, customer_id, order_date, amount, status)`
  - `status` can be `'completed'`, `'refunded'`, or `'void'`
  - **Gotcha:** `'void'` orders should almost always be EXCLUDED from
    revenue calculations — they represent orders that never actually
    completed. A common bug in this warehouse's history has been
    revenue queries that forget to filter out `'void'` status,
    causing inflated numbers.
- `pipeline_runs(run_id, pipeline_name, run_date, status, error_message)`
  - Check this table first when investigating "why did pipeline X fail"
    questions — it often already contains the root-cause hint.

**Known pipelines:** `daily_revenue` (aggregates completed order
amounts per day).
