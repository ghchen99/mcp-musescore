"""Check the WebSocket connection to a running MuseScore by hand.

Sends getScore to the plugin and prints the result. Needs MuseScore open with
the plugin running. From the repository root, the check also runs as:

```
uv run python -m dev.check_websocket
```

Example:
    >>> import asyncio
    >>> from dev.check_websocket import test_websocket
    >>> asyncio.run(test_websocket())
"""

import asyncio
import json
import logging

import websockets

from src.utils.lilypond_converter import json_to_lilypond

logging.basicConfig(level=logging.INFO)


async def test_websocket() -> None:
    """Send getScore to MuseScore, and print the result and its LilyPond form.

    Prints the elements of the first measure and the whole score as LilyPond.
    A refused connection or another error is printed, not raised.
    """
    uri = "ws://localhost:8765"
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected to MuseScore WebSocket.")

            # Request score analysis
            command = {"action": "getScore", "params": {}}
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
                    for staff_name, elements in (
                        analysis["measures"][0].get("elements", {}).items()
                    ):
                        print(f"{staff_name}: {len(elements)} elements")
                        for el in elements:
                            print(
                                f"  - {el.get('name', 'Unknown')} (voice: {el.get('voice', 'N/A')}, pitch: {el.get('pitchMidi', 'N/A')})"
                            )

                print("\n=== LILYPOND CONVERSION ===")
                lily_str = json_to_lilypond(analysis)
                print(lily_str)
            else:
                print("Error from server:", response)

    except ConnectionRefusedError:
        print(
            "Connection refused. Make sure MuseScore is open and the plugin is running."
        )
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_websocket())
