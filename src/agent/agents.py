import os
from collections.abc import Callable

from google.adk.agents import LlmAgent

from src.agent.business_registry import get_business
from src.agent.fivetran import create_fivetran_toolset
from src.agent.freshness_config import FRESHNESS_TABLES as _FRESHNESS_TABLES
from src.agent.freshness_agent import (
    check_bigquery_table_freshness,
    get_connector_status,
    identify_stale_tables,
    refresh_all_stale_tables,
    refresh_connector,
    refresh_stale_table,
    sync_postgres_table_to_bigquery,
    wait_for_connector_completion,
)
from src.agent.observability import (
    after_agent,
    after_tool,
    before_agent,
    before_tool,
    on_tool_error,
)
from src.agent.schemas import SupplyChainAnalysis
from src.agent.tools import (
    calculate_impact,
    detect_black_swan,
    detect_disruptions,
    generate_owner_email,
    generate_purchase_order,
    get_business_suppliers,
    get_inventory,
    get_pending_orders,
    get_port_activity,
    get_recent_disruptions,
    get_shipment_timetable,
    get_supplier_reviews,
    get_severity_calibration_drift,
    get_tariff_updates,
    get_weather_alerts,
    query_calibration_baseline,
    query_recent_cycle_performance,
    save_alert_record,
    search_alternative_suppliers,
    score_suppliers,
)


MODEL = os.getenv("MODEL_NAME", "gemini-2.0-flash").removeprefix("models/")

_VALID_FRESHNESS_TABLES = ", ".join(sorted(_FRESHNESS_TABLES.keys()))


def _instruction(extra: str) -> Callable:
    import logging

    _log = logging.getLogger(__name__)

    def provider(context) -> str:
        business_id = (
            context.state.get("business_id")
            if context and hasattr(context, "state")
            else None
        )
        if not business_id:
            _log.warning(
                "business_id missing from session state; falling back to demo-business-001"
            )
            business_id = "demo-business-001"
        business = get_business(business_id)
        return (
            f"Analyze only {business['name']} (business_id={business_id}). "
            f"Industry: {business['industry']}. "
            f"Primary port: {business['primary_port']}. "
            "Use tools for facts and never invent database values. "
            f"{extra}"
        )

    return provider


def _callbacks() -> dict:
    return {
        "before_agent_callback": before_agent,
        "after_agent_callback": after_agent,
        "before_tool_callback": before_tool,
        "after_tool_callback": after_tool,
        "on_tool_error_callback": on_tool_error,
    }


def create_root_agent() -> LlmAgent:
    disruption_agent = LlmAgent(
        name="DisruptionDetectionAgent",
        model=MODEL,
        mode="task",
        description=(
            "Analyzes disruption events, weather, tariffs, ports, and anomaly signals."
        ),
        instruction=_instruction(
            "Run multi-signal disruption detection. Use detect_disruptions as "
            "the authoritative aggregation, inspect supporting signals when "
            "needed, and evaluate black-swan conditions. Return affected "
            "supplier IDs, source signals, stable disruption IDs, dates, "
            "regions, and tariff cost impact."
        ),
        tools=[
            detect_disruptions,
            get_recent_disruptions,
            get_weather_alerts,
            get_port_activity,
            get_tariff_updates,
            detect_black_swan,
        ],
        output_key="disruption_analysis",
        generate_content_config={"temperature": 0.1},
        **_callbacks(),
    )

    supplier_risk_agent = LlmAgent(
        name="SupplierRiskAgent",
        model=MODEL,
        mode="task",
        description=(
            "Calculates financial exposure, inventory coverage, and supplier risk."
        ),
        instruction=_instruction(
            "Use the disruption findings supplied by the coordinator. "
            "Call get_shipment_timetable to find inbound supplier shipments at risk, "
            "get_pending_orders to see client demand, and get_inventory to check "
            "if on-hand stock can cover client orders despite the disruption. "
            "Then calculate_impact with the affected supplier IDs, rank all viable "
            "alternative suppliers, and return the top three with full metrics."
        ),
        tools=[
            get_business_suppliers,
            get_shipment_timetable,
            get_pending_orders,
            get_inventory,
            calculate_impact,
            search_alternative_suppliers,
            score_suppliers,
            get_supplier_reviews,
        ],
        output_key="supplier_risk_analysis",
        generate_content_config={"temperature": 0.1},
        **_callbacks(),
    )

    procurement_agent = LlmAgent(
        name="ProcurementAgent",
        model=MODEL,
        mode="task",
        description=(
            "Creates mitigation recommendations, purchase orders, and owner "
            "communications."
        ),
        instruction=_instruction(
            "Use the selected ranked alternatives and impact figures. Draft a "
            "purchase order only for the top supplier and generate the owner "
            "email. If a black swan was detected, do not generate a PO and "
            "require human review. After drafting, call save_alert_record with "
            "the disruption_id, severity_score, and exposure_usd from the "
            "analysis to persist the alert to BigQuery."
        ),
        tools=[generate_purchase_order, generate_owner_email, save_alert_record],
        output_key="procurement_analysis",
        generate_content_config={"temperature": 0.1},
        **_callbacks(),
    )

    calibration_agent = LlmAgent(
        name="CalibrationAgent",
        model=MODEL,
        mode="task",
        description=(
            "Calibrates recommendations against historical outcomes and confidence."
        ),
        instruction=_instruction(
            "Query the closest historical event type and region using query_calibration_baseline. "
            "Also call query_recent_cycle_performance to review whether recent agent cycles have "
            "been succeeding and how severity scores have trended across the last 10 runs. "
            "Call get_severity_calibration_drift to check whether predicted severities are "
            "drifting above or below the historical baseline — if the absolute drift exceeds 0.15, "
            "explicitly recommend a corrective adjustment in your output. "
            "Return the weighted baseline severity, confidence, record count, drift, and a "
            "concise adjustment recommendation. Do not replace measured exposure or inventory facts."
        ),
        tools=[query_calibration_baseline, query_recent_cycle_performance, get_severity_calibration_drift],
        output_key="calibration_analysis",
        generate_content_config={"temperature": 0.1},
        **_callbacks(),
    )

    freshness_agent = LlmAgent(
        name="FreshnessAgent",
        model=MODEL,
        mode="task",
        description=(
            "Checks BigQuery table freshness and refreshes stale PostgreSQL-backed tables."
        ),
        instruction=_instruction(
            "Check configured BigQuery table freshness before analysis when source data may "
            "be stale. Identify stale tables, map each table to its configured connector, "
            "request connector refresh through the Fivetran MCP interface, wait for completion, "
            "run the PostgreSQL-to-BigQuery sync for that table, and verify freshness after "
            f"sync. Use the MCP-backed freshness tools and do not call Fivetran REST APIs. "
            f"Valid table names are: {_VALID_FRESHNESS_TABLES}."
        ),
        tools=[
            check_bigquery_table_freshness,
            identify_stale_tables,
            refresh_connector,
            get_connector_status,
            wait_for_connector_completion,
            sync_postgres_table_to_bigquery,
            refresh_stale_table,
            refresh_all_stale_tables,
        ],
        output_key="freshness_analysis",
        generate_content_config={"temperature": 0.1},
        **_callbacks(),
    )

    root_tools = []
    fivetran_toolset = create_fivetran_toolset()
    if fivetran_toolset:
        root_tools.append(fivetran_toolset)

    return LlmAgent(
        name="SupplyChainIntelligenceAgent",
        model=MODEL,
        mode="chat",
        description=(
            "Coordinates complete supply-chain disruption analysis and final "
            "recommendations."
        ),
        instruction=_instruction(
            "You are the root supply-chain intelligence coordinator. Delegate "
            "freshness checks, disruption analysis, supplier risk, calibration, "
            "and procurement work to the specialist agents. Use the FreshnessAgent "
            f"when source data may be stale — valid table names are: {_VALID_FRESHNESS_TABLES}. "
            "Freshness refreshes must go through the configured Fivetran MCP server. Fire an "
            "alert whenever at least one pending shipment is affected. Do not "
            "fire an alert when there is no affected shipment and no financial "
            "impact. Severity must reflect inventory coverage, expected loss, "
            "and calibration. Return only the structured final result. The "
            "disruption object must contain a stable id. Include up to three "
            "ranked alternatives and draft a PO only for rank one. Black-swan "
            "results require human review and prohibit automatic PO generation."
        ),
        sub_agents=[
            disruption_agent,
            freshness_agent,
            supplier_risk_agent,
            calibration_agent,
            procurement_agent,
        ],
        tools=root_tools,
        output_schema=SupplyChainAnalysis,
        output_key="final_analysis",
        generate_content_config={"temperature": 0.1},
        **_callbacks(),
    )
