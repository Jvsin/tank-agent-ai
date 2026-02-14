import argparse
from typing import Any, Dict

from fastapi import Body, FastAPI
import uvicorn

from agent_core import ActionCommand, SmartAgent


app = FastAPI(
    title="Odjazd Simple Agent",
    description="WorldModel + Utility + A*",
    version="4.0.0",
)

agent = SmartAgent()


@app.get("/")
async def root():
    return {"message": f"Agent {agent.name} is running", "destroyed": agent.is_destroyed}


@app.post("/agent/action", response_model=ActionCommand)
async def get_action(payload: Dict[str, Any] = Body(...)):
    return agent.get_action(
        current_tick=payload.get("current_tick", 0),
        my_tank_status=payload.get("my_tank_status", {}),
        sensor_data=payload.get("sensor_data", {}),
        enemies_remaining=payload.get("enemies_remaining", 0),
    )


@app.post("/agent/destroy", status_code=204)
async def destroy():
    agent.destroy()


@app.post("/agent/end", status_code=204)
async def end(payload: Dict[str, Any] = Body(...)):
    agent.end(
        damage_dealt=payload.get("damage_dealt", 0.0),
        tanks_killed=payload.get("tanks_killed", 0),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run smart simple agent")
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--name", type=str, default=None)
    args = parser.parse_args()

    if args.name:
        agent.name = args.name
    else:
        agent.name = f"OdjazdBot_{args.port}"

    print(f"Starting {agent.name} on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning", access_log=False)