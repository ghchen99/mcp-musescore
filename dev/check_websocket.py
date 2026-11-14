"""Manual check of the WebSocket connection: sends getScore to a running MuseScore and prints the result.

Needs MuseScore open with the plugin running. Run from the repository root:

    uv run python -m dev.check_websocket
"""

import asyncio
import json
import logging

import websockets

from src.utils.lilypond_converter import json_to_lilypond

logging.basicConfig(level=logging.INFO)

async def test_websocket() -> None:
    uri = "ws://localhost:8765"
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected to MuseScore WebSocket.")
            
            # Request score analysis
            command = {
                "action": "getScore",
                "params": {}
            }
            await websocket.send(json.dumps(command))
            print("Sent getScore command.")
            
            response_str = await websocket.recv()
            print("Received response.")
            
            response = json.loads(response_str)
            if response.get("status") == "success":
                result = response.get("result", {})
                analysis = result.get("analysis", {})
                
                print("\n=== RAW JSON SAMPLE (First Measure Elements) ===")
                # Just print elements of the first track of the first measure for debugging
                if "measures" in analysis and analysis["measures"]:
                    for staff_name, elements in analysis["measures"][0].get("elements", {}).items():
                        print(f"{staff_name}: {len(elements)} elements")
                        for el in elements:
                            print(f"  - {el.get('name', 'Unknown')} (voice: {el.get('voice', 'N/A')}, pitch: {el.get('pitchMidi', 'N/A')})")
                
                print("\n=== LILYPOND CONVERSION ===")
                lily_str = json_to_lilypond(analysis)
                print(lily_str)
            else:
                print("Error from server:", response)
                
    except ConnectionRefusedError:
        print("Connection refused. Make sure MuseScore is open and the plugin is running.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_websocket())
