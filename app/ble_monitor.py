# ble_monitor.py
import asyncio
import sys
import os
import struct

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.ble_runner import run_ble

TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
DEVICE_NAME = "XIAO-SENSE"

class PacketParser:
    def __init__(self):
        self.buf = bytearray()

    def feed(self, data: bytes):
        self.buf.extend(data)

        decoded_packets = []

        while len(self.buf) > 0:
            ptype = chr(self.buf[0])

            # R packet: 'R' + ts(uint32) + hr(int16 x100) + spo2(int16 x100)
            if ptype == "R":
                pkt_len = 9
                if len(self.buf) < pkt_len:
                    break

                pkt = bytes(self.buf[:pkt_len])
                del self.buf[:pkt_len]

                ts = struct.unpack_from("<I", pkt, 1)[0]
                hr_i = struct.unpack_from("<h", pkt, 5)[0]
                spo2_i = struct.unpack_from("<h", pkt, 7)[0]

                hr = None if hr_i < 0 else hr_i / 100.0
                spo2 = None if spo2_i < 0 else spo2_i / 100.0

                decoded_packets.append(("R", ts, hr, spo2))

            # M packet: 'M' + ts(uint32) + state(uint8) + event_val(int16 x100) + impact(int16 x100)
            elif ptype == "M":
                pkt_len = 10
                if len(self.buf) < pkt_len:
                    break

                pkt = bytes(self.buf[:pkt_len])
                del self.buf[:pkt_len]

                ts = struct.unpack_from("<I", pkt, 1)[0]
                state = pkt[5]
                event_i = struct.unpack_from("<h", pkt, 6)[0]
                impact_i = struct.unpack_from("<h", pkt, 8)[0]

                event_val = event_i / 100.0
                impact = impact_i / 100.0

                decoded_packets.append(("M", ts, state, event_val, impact))

            else:
                # Skip one byte if buffer is misaligned or contains unknown data
                bad = self.buf[0]
                del self.buf[0]
                decoded_packets.append(("UNKNOWN", bytes([bad])))

        return decoded_packets


parser = PacketParser()
t0 = None

STATE_NAMES = {
    0: "IDLE_FALL",
    1: "CHECK_FALL",
    2: "ANALYZE_IMPACT",
    3: "DETECTED_FALL",
    4: "STATIONARY_POST_FALL",
    5: "WALKING",
    6: "RUNNING",
    7: "JUMPING_OR_QUICK_SIT",
}


def handle_notification(sender: int, data: bytearray):
    global t0

    for decoded in parser.feed(data):
        ptype = decoded[0]

        if ptype == "R":
            _, ts, hr, spo2 = decoded

            if t0 is None:
                t0 = ts

            ts_rel = (ts - t0) / 1000.0

            hr_str = "---" if hr is None else f"{hr:.2f}"
            spo2_str = "---" if spo2 is None else f"{spo2:.2f}"

            print(f"[BLE RX][PPG] t={ts_rel:.2f}s hr={hr_str} bpm spo2={spo2_str} %")

        elif ptype == "M":
            _, ts, state, event_val, impact = decoded

            if t0 is None:
                t0 = ts

            ts_rel = (ts - t0) / 1000.0
            state_name = STATE_NAMES.get(state, f"UNKNOWN_STATE_{state}")

            print(
                f"[BLE RX][IMU] t={ts_rel:.2f}s "
                f"state={state_name} event={event_val:.2f} impact={impact:.2f}"
            )

        else:
            _, raw = decoded
            print(f"[BLE RX] Unknown packet type: {raw[0]} (raw={raw.hex()})")


async def main():
    await run_ble(DEVICE_NAME, TX_CHAR_UUID, handle_notification)


if __name__ == "__main__":
    asyncio.run(main())