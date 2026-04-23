import asyncio

from livekit import api


async def main():
    livekit_api = api.LiveKitAPI(
        "http://localhost:7880", "devkey", "devsecret"
    )
    print("Connected to API")
    try:
        dispatch = await livekit_api.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name="taigi-agent",
                room="playground",
            )
        )
        print("Dispatch created:", dispatch)
    except Exception as e:
        print("Failed to dispatch:", e)
    finally:
        await livekit_api.aclose()

if __name__ == "__main__":
    asyncio.run(main())
