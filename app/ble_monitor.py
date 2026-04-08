# ble_monitor.py
import asyncio
import sys
import os
import struct

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.ble_runner import run_ble

TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"  # BLE UART RX characteristic
DEVICE_NAME = "XIAO-SENSE"

class PacketParser:
    def __init__(self):
        self.buf = bytearray()  # Persistent buffer — BLE may split packets across notifications

    def feed(self, data: bytes):
        self.buf.extend(data)

        decoded_packets = []

        while len(self.buf) > 0:
            ptype = chr(self.buf[0])

            # R packet: 'R' + ts(uint32) + hr(int16 x100) + spo2(int16 x100)
            if ptype == "R":
                pkt_len = 9
                if len(self.buf) < pkt_len:
                    break  # Wait for the rest of the packet to arrive

                pkt = bytes(self.buf[:pkt_len])
                del self.buf[:pkt_len]

                ts = struct.unpack_from("<I", pkt, 1)[0]
                hr_i = struct.unpack_from("<h", pkt, 5)[0]
                spo2_i = struct.unpack_from("<h", pkt, 7)[0]

                # Negative values signal invalid/no reading from the firmware
                hr = None if hr_i <= 0 else hr_i / 100.0
                spo2 = None if spo2_i <= 0 else spo2_i / 100.0

                decoded_packets.append(("R", ts, hr, spo2))

            # M packet: 'M' + ts(uint32) + state(uint8) + event_val(int16 x100) + impact(int16 x100)
            elif ptype == "M":
                pkt_len = 10
                if len(self.buf) < pkt_len:
                    break  # Wait for the rest of the packet to arrive

                pkt = bytes(self.buf[:pkt_len])
                del self.buf[:pkt_len]

                ts = struct.unpack_from("<I", pkt, 1)[0]
                state = pkt[5]
                event_i = struct.unpack_from("<h", pkt, 6)[0]
                impact_i = struct.unpack_from("<h", pkt, 8)[0]

                event_val = event_i / 100.0
                impact = impact_i / 100.0

                decoded_packets.append(("M", ts, state, event_val, impact))

            # B packet: 'B' + ts(uint32) + vbat(int16 x100)
            elif ptype == "B":
                pkt_len = 7
                if len(self.buf) < pkt_len:
                    break  # Wait for the rest of the packet to arrive

                pkt = bytes(self.buf[:pkt_len])
                del self.buf[:pkt_len]

                ts = struct.unpack_from("<I", pkt, 1)[0]
                vbat_i = struct.unpack_from("<h", pkt, 5)[0]

                vbat = vbat_i / 100.0

                decoded_packets.append(("B", ts, vbat))

            # W packet: 'W' + ts(uint32) + rr(int16 x100)
            elif ptype == "W":
                pkt_len = 7
                if len(self.buf) < pkt_len:
                    break

                pkt = bytes(self.buf[:pkt_len])
                del self.buf[:pkt_len]

                ts = struct.unpack_from("<I", pkt, 1)[0]
                rr_i = struct.unpack_from("<h", pkt, 5)[0]

                rr = None if rr_i < 0 else rr_i / 100.0

                decoded_packets.append(("W", ts, rr))

            # P packet: 'P' + ts(uint32) + sbp(int16 x10) + dbp(int16 x10)
            elif ptype == "P":
                pkt_len = 9
                if len(self.buf) < pkt_len:
                    break

                pkt = bytes(self.buf[:pkt_len])
                del self.buf[:pkt_len]

                ts = struct.unpack_from("<I", pkt, 1)[0]
                sbp_i = struct.unpack_from("<h", pkt, 5)[0]
                dbp_i = struct.unpack_from("<h", pkt, 7)[0]

                sbp = None if sbp_i < 0 else sbp_i / 10.0
                dbp = None if dbp_i < 0 else dbp_i / 10.0

                decoded_packets.append(("P", ts, sbp, dbp))

            else:
                # Skip one byte if buffer is misaligned or contains unknown data
                bad = self.buf[0]
                del self.buf[0]
                decoded_packets.append(("UNKNOWN", bytes([bad])))

        return decoded_packets

parser = PacketParser()
t0 = None  # Timestamp of the first received packet — used to compute relative times

# Maps firmware fall state integers to human-readable names
STATE_NAMES = {
    0: "IDLE_FALL",
    1: "CHECK_FALL",
    2: "ANALYZE_IMPACT",
    3: "DETECTED_FALL",
    4: "STATIONARY_POST_FALL",
    5: "WALKING",
    6: "RUNNING",
    7: "JUMPING",
    8: "LIMPING",
    9: "SITTING",
    10: "SQUATTING",
}

def reset_state():
    # Called on reconnect — clears stale buffer and resets relative timestamp
    global t0, parser
    print("[BLE] Resetting parser state on reconnect.")
    t0 = None
    parser = PacketParser()

def handle_notification(sender: int, data: bytearray):
    global t0

    for decoded in parser.feed(data):
        ptype = decoded[0]

        if ptype == "R":
            _, ts, hr, spo2 = decoded

            # Anchor relative time to the first packet received
            if t0 is None:
                t0 = ts

            ts_rel = (ts - t0) / 1000.0

            hr_str = "---" if hr is None else f"{hr:.2f}"
            spo2_str = "---" if spo2 is None else f"{spo2:.2f}"

            print(f"[BLE RX][PPG] t={ts_rel:.0f}s hr={hr_str} bpm spo2={spo2_str} %")

        elif ptype == "M":
            _, ts, state, event_val, impact = decoded

            if t0 is None:
                t0 = ts

            ts_rel = (ts - t0) / 1000.0
            state_name = STATE_NAMES.get(state, f"UNKNOWN_STATE_{state}")

            print(
                f"[BLE RX][IMU] t={ts_rel:.0f}s "
                f"state={state_name} event={event_val:.2f} impact={impact:.2f}"
            )

        elif ptype == "B":
            _, ts, vbat = decoded

            if t0 is None:
                t0 = ts

            ts_rel = (ts - t0) / 1000.0

            print(f"[BLE RX][BAT] t={ts_rel:.0f}s vbat={vbat:.2f} V")

        elif ptype == "W":
            _, ts, rr = decoded

            if t0 is None:
                t0 = ts

            ts_rel = (ts - t0) / 1000.0
            rr_str = "---" if rr is None else f"{rr:.2f}"

            print(f"[BLE RX][RR] t={ts_rel:.0f}s rr={rr_str} BrPM")

        elif ptype == "P":
            _, ts, sbp, dbp = decoded

            if t0 is None:
                t0 = ts

            ts_rel = (ts - t0) / 1000.0
            sbp_str = "---" if sbp is None else f"{sbp:.1f}"
            dbp_str = "---" if dbp is None else f"{dbp:.1f}"

            print(f"[BLE RX][BP] t={ts_rel:.0f}s sbp={sbp_str} mmHg dbp={dbp_str} mmHg")
        
        else:
            _, raw = decoded
            print(f"[BLE RX] Unknown packet type: {raw[0]} (raw={raw.hex()})")

async def main():
    await run_ble(DEVICE_NAME, TX_CHAR_UUID, handle_notification, on_reconnect=reset_state)

if __name__ == "__main__":
    asyncio.run(main())