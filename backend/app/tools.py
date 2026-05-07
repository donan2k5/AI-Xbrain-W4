"""
L3 Tools: Query monitoring API and SQLite for real-time & historical data
"""

import json
import sqlite3
from datetime import datetime
from typing import Any

import httpx


# Monitoring API endpoints
MONITORING_API_BASE = "http://localhost:8000"

# SQLite database path
SQLITE_PATH = "geekbrain.db"


def fetch_service_metrics(service_name: str) -> dict[str, Any]:
    """Fetch real-time metrics for a service from monitoring API."""
    try:
        response = httpx.get(f"{MONITORING_API_BASE}/metrics/{service_name}", timeout=5.0)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": f"Failed to fetch metrics for {service_name}: {str(e)}"}


def fetch_all_services_metrics() -> dict[str, Any]:
    """Fetch real-time metrics for all services."""
    try:
        response = httpx.get(f"{MONITORING_API_BASE}/services", timeout=5.0)
        response.raise_for_status()
        services = response.json()

        all_metrics = {}
        for service in services:
            all_metrics[service] = fetch_service_metrics(service)
        return all_metrics
    except Exception as e:
        return {"error": f"Failed to fetch services: {str(e)}"}


def query_database(query: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Execute SQL query on SQLite database and return results. Use ? for parameters."""
    try:
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row  # Return rows as dictionaries
        cursor = conn.cursor()
        cursor.execute(query, params)
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results
    except Exception as e:
        return [{"error": f"Database query failed: {str(e)}"}]


def get_service_costs(service_name: str, month: str = None) -> list[dict[str, Any]]:
    """Get monthly costs for a service (or specific month)."""
    if month:
        query = "SELECT * FROM monthly_costs WHERE service = ? AND month = ? ORDER BY month DESC"
        return query_database(query, (service_name, month))
    else:
        query = "SELECT * FROM monthly_costs WHERE service = ? ORDER BY month DESC"
        return query_database(query, (service_name,))


def get_all_costs(month: str = None) -> list[dict[str, Any]]:
    """Get all monthly costs (or for specific month)."""
    if month:
        query = "SELECT * FROM monthly_costs WHERE month = ? ORDER BY total_cost DESC"
        return query_database(query, (month,))
    else:
        query = "SELECT * FROM monthly_costs ORDER BY month DESC, total_cost DESC"
        return query_database(query)


def get_service_incidents(service_name: str) -> list[dict[str, Any]]:
    """Get all incidents for a service."""
    query = "SELECT * FROM incidents WHERE service = ? ORDER BY date DESC"
    return query_database(query, (service_name,))


def get_sla_targets(service_name: str = None) -> list[dict[str, Any]]:
    """Get SLA targets for service(s)."""
    if service_name:
        query = "SELECT * FROM sla_targets WHERE service = ?"
        return query_database(query, (service_name,))
    else:
        query = "SELECT * FROM sla_targets ORDER BY service"
        return query_database(query)


def get_daily_metrics(service_name: str, date_from: str = None, date_to: str = None) -> list[dict[str, Any]]:
    """Get daily metrics for a service within date range."""
    where_clauses = ["service = ?"]
    params = [service_name]

    if date_from:
        where_clauses.append("date >= ?")
        params.append(date_from)
    if date_to:
        where_clauses.append("date <= ?")
        params.append(date_to)

    where = " AND ".join(where_clauses)
    query = f"SELECT * FROM daily_metrics WHERE {where} ORDER BY date DESC"
    return query_database(query, tuple(params))


def get_service_status(service_name: str) -> dict[str, Any]:
    """Get current status (real-time) + SLA targets for a service."""
    metrics = fetch_service_metrics(service_name)
    sla = get_sla_targets(service_name)

    return {
        "service": service_name,
        "current_metrics": metrics,
        "sla_targets": sla,
    }


def get_service_comparison(metric_name: str = "latency_p99_ms") -> list[dict[str, Any]]:
    """Compare a metric across all services (latest from daily_metrics)."""
    # Whitelist known metrics to prevent SQL injection
    ALLOWED_METRICS = {
        "latency_p99_ms", "latency_p95_ms", "latency_p50_ms",
        "error_rate_percent", "requests_per_minute", "availability_percent"
    }
    if metric_name not in ALLOWED_METRICS:
        metric_name = "latency_p99_ms"

    query = f"""
        SELECT service, {metric_name}, date
        FROM daily_metrics
        WHERE date = (SELECT MAX(date) FROM daily_metrics)
        ORDER BY {metric_name} DESC
    """
    return query_database(query)


def get_q1_costs_summary() -> dict[str, Any]:
    """Get Q1 2026 costs summary by service."""
    query = """
        SELECT service,
               SUM(total_cost) as total_q1,
               AVG(total_cost) as avg_monthly
        FROM monthly_costs
        WHERE month IN ('2026-01', '2026-02', '2026-03')
        GROUP BY service
        ORDER BY total_q1 DESC
    """
    results = query_database(query)
    return {"q1_summary": results, "timestamp": datetime.now().isoformat()}


# Format results nicely for LLM
def format_for_llm(data: Any) -> str:
    """Format database/API results as readable text for LLM."""
    if isinstance(data, list) and data and "error" in data[0]:
        return json.dumps(data[0], indent=2)
    return json.dumps(data, indent=2, default=str)
