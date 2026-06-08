import sys
from src.agent.loop import run_loop, run_agent_cycle

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "once":
        business_id = sys.argv[2] if len(sys.argv) > 2 else "demo-business-001"
        result = run_agent_cycle(business_id)
        print(result)
    else:
        run_loop()
