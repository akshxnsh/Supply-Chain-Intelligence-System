from src.agent.agents import create_root_agent
from src.agent.fivetran import FIVETRAN_TOOLS, create_fivetran_toolset


def test_adk_agent_topology(monkeypatch):
    monkeypatch.delenv("FIVETRAN_MCP_URL", raising=False)
    monkeypatch.delenv("FIVETRAN_MCP_COMMAND", raising=False)

    root = create_root_agent()

    assert root.name == "SupplyChainIntelligenceAgent"
    assert root.mode == "chat"
    assert {agent.name for agent in root.sub_agents} == {
        "DisruptionDetectionAgent",
        "FreshnessAgent",
        "SupplierRiskAgent",
        "ProcurementAgent",
        "CalibrationAgent",
    }
    assert all(agent.mode == "task" for agent in root.sub_agents)
    assert all(agent.tools for agent in root.sub_agents)


def test_fivetran_toolset_is_disabled_without_configuration(monkeypatch):
    monkeypatch.delenv("FIVETRAN_MCP_URL", raising=False)
    monkeypatch.delenv("FIVETRAN_MCP_COMMAND", raising=False)

    assert create_fivetran_toolset() is None
    assert FIVETRAN_TOOLS == [
        "check_connector_status",
        "get_last_sync_time",
        "list_connectors",
        "trigger_sync",
        "monitor_sync",
    ]
