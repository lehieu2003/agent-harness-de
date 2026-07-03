"""
Sets up a small SQLite database simulating a real analytics warehouse,
with a deliberately planted data quality issue for the agent to find.

Run this once before using the Data Engineer agent:
    python -m scripts.db_setup
"""
import sqlite3
import os
import random
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "warehouse.db")


def setup():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE customers (
            customer_id INTEGER PRIMARY KEY,
            name TEXT,
            signup_date TEXT,
            country TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE orders (
            order_id INTEGER PRIMARY KEY,
            customer_id INTEGER,
            order_date TEXT,
            amount REAL,
            status TEXT,  -- 'completed', 'refunded', 'void' (legacy, should be excluded from revenue)
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        )
    """)

    cur.execute("""
        CREATE TABLE pipeline_runs (
            run_id INTEGER PRIMARY KEY,
            pipeline_name TEXT,
            run_date TEXT,
            status TEXT,  -- 'success', 'failed'
            error_message TEXT
        )
    """)

    # Seed customers
    countries = ["US", "UK", "DE", "VN", "JP"]
    for i in range(1, 21):
        cur.execute(
            "INSERT INTO customers VALUES (?, ?, ?, ?)",
            (i, f"Customer {i}", (datetime(2024, 1, 1) + timedelta(days=i * 5)).strftime("%Y-%m-%d"), random.choice(countries))
        )

    # Seed orders — INCLUDING a planted issue:
    # some rows have status='void' but were accidentally included in a
    # "revenue" transformation query, which is why yesterday's pipeline
    # reported inflated numbers. A senior DE should catch this.
    statuses_normal = ["completed"] * 7 + ["refunded"] * 2
    order_id = 1
    for day in range(30):
        order_date = (datetime(2025, 6, 1) + timedelta(days=day)).strftime("%Y-%m-%d")
        for _ in range(random.randint(3, 8)):
            status = random.choice(statuses_normal)
            cur.execute(
                "INSERT INTO orders VALUES (?, ?, ?, ?, ?)",
                (order_id, random.randint(1, 20), order_date, round(random.uniform(10, 500), 2), status)
            )
            order_id += 1

    # Plant some 'void' orders with unusually large amounts on the most recent day —
    # this is the "bug" a senior DE agent should discover when asked to investigate
    last_day = (datetime(2025, 6, 1) + timedelta(days=29)).strftime("%Y-%m-%d")
    for _ in range(5):
        cur.execute(
            "INSERT INTO orders VALUES (?, ?, ?, ?, ?)",
            (order_id, random.randint(1, 20), last_day, round(random.uniform(2000, 5000), 2), "void")
        )
        order_id += 1

    # Seed a failed pipeline run pointing at the real root cause
    cur.execute(
        "INSERT INTO pipeline_runs VALUES (?, ?, ?, ?, ?)",
        (1, "daily_revenue", last_day, "failed",
         "Revenue for 2025-06-30 is 3.2x the trailing 7-day average — anomaly threshold exceeded")
    )

    conn.commit()
    conn.close()
    print(f"Mock warehouse created at {DB_PATH}")
    print("Contains: customers, orders (with a planted data quality issue), pipeline_runs")


if __name__ == "__main__":
    setup()
