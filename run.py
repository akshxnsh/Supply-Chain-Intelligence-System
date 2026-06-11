import sys

from src.agent.runtime import run_agent_cycle, run_loop
from dotenv import load_dotenv
from src.agent.model_config import configure_llm_provider
load_dotenv()
configure_llm_provider()
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "once":
        business_id = sys.argv[2] if len(sys.argv) > 2 else "demo-business-001"
        result = run_agent_cycle(business_id)
        print(result)
    else:
        run_loop()
