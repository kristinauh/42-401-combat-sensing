# utils/ble_runner.py
import asyncio
from bleak import BleakClient, BleakScanner


async def run_ble(
    device_name: str,
    char_uuid: str,
    on_notify,
    timeout: float = 15.0,
    on_reconnect=None,   # Called after each successful connection
    on_disconnect=None,  # Called when connection is lost or device not found
):
    # Reconnect loop — runs indefinitely until KeyboardInterrupt
    while True:
        print(f"Scanning for BLE device '{device_name}'...")
        device = await BleakScanner.find_device_by_name(device_name, timeout=timeout)

        if device is None:
            print("Device not found. Retrying...")
            if on_disconnect is not None:
                on_disconnect()
            await asyncio.sleep(2.0)
            continue

        try:
            print("Connecting...")
            async with BleakClient(device) as client:
                print("Connected.")

                if on_reconnect is not None:
                    on_reconnect()

                await client.start_notify(char_uuid, on_notify)
                print("Streaming BLE... Ctrl+C to stop.\n")

                # Poll connection state — bleak doesn't surface disconnects as exceptions
                while client.is_connected:
                    await asyncio.sleep(1.0)

                print("Disconnected. Reconnecting...")
                if on_disconnect is not None:
                    on_disconnect()

        except KeyboardInterrupt:
            print("\nStopping...")
            return  # Exit the reconnect loop cleanly

        except Exception as e:
            print(f"Connection error: {e}. Retrying...")
            if on_disconnect is not None:
                on_disconnect()
            await asyncio.sleep(2.0)