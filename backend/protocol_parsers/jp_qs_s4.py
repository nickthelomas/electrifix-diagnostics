"""
ElectriFix Diagnostics - JP/QS-S4 Protocol Parser
Reference: https://github.com/teixeluis/escooter-lcd-esc-decode

This protocol is used by many Chinese e-scooters with QS-S4 displays.
Packet format: 15 bytes, last byte is XOR checksum of bytes 0-13
Baud rate: 1200
"""

from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class JPPacket:
    """Parsed JP/QS-S4 protocol packet."""
    raw_bytes: bytes
    checksum: int
    checksum_valid: bool
    direction: str  # 'dash_to_controller' or 'controller_to_dash'
    
    # Parsed fields (depend on direction)
    fields: Dict


class JPParser:
    """Parser for JP/QS-S4 e-scooter protocol."""
    
    PACKET_LENGTH = 15
    
    # Packet headers
    HEADER_DASH_TO_CTRL = b'\x01\x03'    # Dashboard → Controller
    HEADER_CTRL_TO_DASH = b'\x01\x04'    # Controller → Dashboard (some variants)
    
    # Byte mappings for Dashboard → Controller packets
    DASH_TO_CTRL_MAP = {
        0: "header_1",
        1: "header_2", 
        2: "throttle_raw",       # 0-255 throttle input
        3: "brake_raw",          # 0-255 brake input
        4: "mode",               # Speed mode 0-2
        5: "headlight",          # 0=off, 1=on
        6: "unknown_1",
        7: "cruise_control",     # 0=off, 1=on
        8: "unknown_2",
        9: "unknown_3",
        10: "unknown_4",
        11: "unknown_5",
        12: "unknown_6",
        13: "unknown_7",
        14: "checksum",
    }
    
    # Byte mappings for Controller → Dashboard packets
    CTRL_TO_DASH_MAP = {
        0: "header_1",
        1: "header_2",
        2: "speed_low",          # Speed LSB
        3: "speed_high",         # Speed MSB (speed = (high * 256 + low) / 10 km/h)
        4: "voltage_low",        # Voltage LSB
        5: "voltage_high",       # Voltage MSB (voltage = (high * 256 + low) / 10 V)
        6: "current_low",        # Current LSB
        7: "current_high",       # Current MSB
        8: "error_code",         # Error code
        9: "temperature",        # Controller temperature
        10: "unknown_1",
        11: "unknown_2",
        12: "unknown_3",
        13: "unknown_4",
        14: "checksum",
    }
    
    # Error codes
    ERROR_CODES = {
        0x00: "No error",
        0x01: "Motor hall sensor error",
        0x02: "Throttle error",
        0x03: "Motor phase error",
        0x04: "Motor stalled",
        0x05: "Controller overheat",
        0x06: "Overcurrent",
        0x07: "Battery low voltage",
        0x08: "Battery high voltage",
        0x09: "BMS communication error",
        0x0A: "Motor hall sensor error B",
        0x0B: "Motor hall sensor error C",
    }
    
    def __init__(self):
        self.packets: List[JPPacket] = []
        self.errors: List[str] = []
        self.stats = {
            "total_packets": 0,
            "valid_checksums": 0,
            "invalid_checksums": 0,
            "dash_to_ctrl": 0,
            "ctrl_to_dash": 0,
            "unknown_direction": 0,
            "error_codes_seen": {}
        }
    
    def parse(self, data: bytes) -> List[JPPacket]:
        """Parse raw data into JP packets."""
        self.packets = []
        self.errors = []
        self.stats = {
            "total_packets": 0,
            "valid_checksums": 0,
            "invalid_checksums": 0,
            "dash_to_ctrl": 0,
            "ctrl_to_dash": 0,
            "unknown_direction": 0,
            "error_codes_seen": {}
        }
        
        pos = 0
        while pos <= len(data) - self.PACKET_LENGTH:
            # Look for packet header
            if data[pos:pos+2] == self.HEADER_DASH_TO_CTRL:
                packet = self._parse_packet(data[pos:pos+self.PACKET_LENGTH], "dash_to_controller")
            elif data[pos:pos+2] == self.HEADER_CTRL_TO_DASH:
                packet = self._parse_packet(data[pos:pos+self.PACKET_LENGTH], "controller_to_dash")
            elif data[pos] == 0x01:
                # Try to detect packet by structure
                packet = self._parse_packet(data[pos:pos+self.PACKET_LENGTH], "unknown")
            else:
                pos += 1
                continue
            
            if packet:
                self.packets.append(packet)
                self._update_stats(packet)
                pos += self.PACKET_LENGTH
            else:
                pos += 1
        
        return self.packets
    
    def _parse_packet(self, data: bytes, direction: str) -> Optional[JPPacket]:
        """Parse a single 15-byte packet."""
        try:
            if len(data) != self.PACKET_LENGTH:
                return None
            
            # Calculate checksum (XOR of bytes 0-13)
            calculated_checksum = 0
            for i in range(0, 14):
                calculated_checksum ^= data[i]
            
            checksum = data[14]
            checksum_valid = (checksum == calculated_checksum)
            
            # Parse fields based on direction
            if direction == "dash_to_controller":
                fields = self._parse_dash_to_ctrl(data)
            elif direction == "controller_to_dash":
                fields = self._parse_ctrl_to_dash(data)
            else:
                # Try to auto-detect based on byte 2 patterns
                if data[2] > 0 and data[3] == 0:  # Throttle with no brake likely dash→ctrl
                    fields = self._parse_dash_to_ctrl(data)
                    direction = "dash_to_controller"
                else:
                    fields = self._parse_ctrl_to_dash(data)
                    direction = "controller_to_dash"
            
            return JPPacket(
                raw_bytes=data,
                checksum=checksum,
                checksum_valid=checksum_valid,
                direction=direction,
                fields=fields
            )
            
        except Exception as e:
            self.errors.append(f"Parse error: {e}")
            return None
    
    def _parse_dash_to_ctrl(self, data: bytes) -> Dict:
        """Parse dashboard to controller packet."""
        throttle_raw = data[2]
        throttle_percent = round(throttle_raw / 255 * 100, 1)
        
        brake_raw = data[3]
        brake_percent = round(brake_raw / 255 * 100, 1)
        
        return {
            "throttle_raw": throttle_raw,
            "throttle_percent": throttle_percent,
            "brake_raw": brake_raw,
            "brake_percent": brake_percent,
            "mode": data[4],
            "headlight": data[5] == 1,
            "cruise_control": data[7] == 1,
            "raw_hex": data.hex()
        }
    
    def _parse_ctrl_to_dash(self, data: bytes) -> Dict:
        """Parse controller to dashboard packet."""
        speed_raw = data[2] + (data[3] << 8)
        speed_kmh = speed_raw / 10
        
        voltage_raw = data[4] + (data[5] << 8)
        voltage = voltage_raw / 10
        
        current_raw = data[6] + (data[7] << 8)
        current = current_raw / 10
        
        error_code = data[8]
        error_message = self.ERROR_CODES.get(error_code, f"Unknown error 0x{error_code:02X}")
        
        temperature = data[9]
        
        return {
            "speed_raw": speed_raw,
            "speed_kmh": speed_kmh,
            "voltage_raw": voltage_raw,
            "voltage": voltage,
            "current_raw": current_raw,
            "current": current,
            "error_code": error_code,
            "error_message": error_message,
            "temperature": temperature,
            "raw_hex": data.hex()
        }
    
    def _update_stats(self, packet: JPPacket):
        """Update statistics with parsed packet."""
        self.stats["total_packets"] += 1

        if packet.checksum_valid:
            self.stats["valid_checksums"] += 1
        else:
            self.stats["invalid_checksums"] += 1

        if packet.direction == "dash_to_controller":
            self.stats["dash_to_ctrl"] += 1
            # Track throttle values for stuck throttle detection
            throttle = packet.fields.get("throttle_raw", 0)
            if "throttle_values" not in self.stats:
                self.stats["throttle_values"] = []
            self.stats["throttle_values"].append(throttle)
        elif packet.direction == "controller_to_dash":
            self.stats["ctrl_to_dash"] += 1
            # Track error codes
            if "error_code" in packet.fields:
                error = packet.fields["error_code"]
                if error != 0:
                    key = f"0x{error:02X}"
                    self.stats["error_codes_seen"][key] = self.stats["error_codes_seen"].get(key, 0) + 1
            # Track voltage for overvoltage/undervoltage detection
            voltage = packet.fields.get("voltage", 0)
            if voltage > 0:
                if "voltage_min" not in self.stats or voltage < self.stats["voltage_min"]:
                    self.stats["voltage_min"] = voltage
                if "voltage_max" not in self.stats or voltage > self.stats["voltage_max"]:
                    self.stats["voltage_max"] = voltage
        else:
            self.stats["unknown_direction"] += 1
    
    def get_summary(self) -> Dict:
        """Get parsing summary."""
        checksum_error_rate = 0
        if self.stats["total_packets"] > 0:
            checksum_error_rate = (self.stats["invalid_checksums"] / self.stats["total_packets"]) * 100

        # Analyze throttle for stuck detection
        throttle_stuck = False
        throttle_values = self.stats.get("throttle_values", [])
        if len(throttle_values) > 10:
            # Check if throttle is stuck at a non-zero value
            # (very low variance + moderately high value = stuck)
            non_zero = [t for t in throttle_values if t > 50]  # Filter out idle
            if len(non_zero) > len(throttle_values) * 0.8:
                # Check variance - stuck throttle has very low variance
                avg = sum(non_zero) / len(non_zero)
                variance = sum((t - avg) ** 2 for t in non_zero) / len(non_zero)
                # If variance is very low and average is moderately high, it's stuck
                if variance < 100 and avg > 80:
                    throttle_stuck = True

        return {
            "protocol": "jp_qs_s4",
            "total_packets": self.stats["total_packets"],
            "checksum_error_rate": round(checksum_error_rate, 2),
            "dash_to_controller_packets": self.stats["dash_to_ctrl"],
            "controller_to_dash_packets": self.stats["ctrl_to_dash"],
            "unknown_direction_packets": self.stats["unknown_direction"],
            "error_codes_seen": self.stats["error_codes_seen"],
            "voltage_min": self.stats.get("voltage_min"),
            "voltage_max": self.stats.get("voltage_max"),
            "throttle_stuck": throttle_stuck,
            "parse_errors": len(self.errors)
        }
    
    def analyze_throttle_response(self) -> Dict:
        """Analyze throttle input vs speed response correlation."""
        throttle_values = []
        speed_values = []

        for packet in self.packets:
            if packet.direction == "dash_to_controller":
                throttle_values.append(packet.fields.get("throttle_percent", 0))
            elif packet.direction == "controller_to_dash":
                speed_values.append(packet.fields.get("speed_kmh", 0))

        # Simple analysis
        has_throttle_input = any(t > 5 for t in throttle_values)
        has_speed_response = any(s > 0 for s in speed_values)

        return {
            "throttle_samples": len(throttle_values),
            "speed_samples": len(speed_values),
            "max_throttle": max(throttle_values) if throttle_values else 0,
            "max_speed": max(speed_values) if speed_values else 0,
            "has_throttle_input": has_throttle_input,
            "has_speed_response": has_speed_response,
            "potential_issue": has_throttle_input and not has_speed_response
        }

    def parse_to_components(self, data: bytes) -> Optional[Dict]:
        """
        Parse raw packet into component-friendly format for real-time display.

        Returns a dictionary with all component states, or None if packet is invalid.
        """
        # Try to parse latest packets
        packets = self.parse(data)
        if not packets:
            return None

        # Get the most recent data from both directions
        component_data = {
            "timestamp": None,
            "throttle_percent": 0,
            "throttle_raw": 0,
            "brake_engaged": False,
            "brake_percent": 0,
            "brake_raw": 0,
            "speed_kmh": 0,
            "voltage": 0,
            "current": 0,
            "temperature": 0,
            "mode": 0,  # 0=Eco, 1=Sport, 2=Turbo
            "mode_name": "eco",
            "headlight": False,
            "cruise": False,
            "rpm": 0,
            "error_code": 0,
            "error_message": "No error",
            "protocol": "jp_qs_s4",
            "packet_valid": True
        }

        # Process packets to extract latest values
        for packet in packets[-20:]:  # Look at last 20 packets for freshest data
            if not packet.checksum_valid:
                continue

            if packet.direction == "dash_to_controller":
                fields = packet.fields
                component_data["throttle_percent"] = fields.get("throttle_percent", 0)
                component_data["throttle_raw"] = fields.get("throttle_raw", 0)
                component_data["brake_percent"] = fields.get("brake_percent", 0)
                component_data["brake_raw"] = fields.get("brake_raw", 0)
                component_data["brake_engaged"] = fields.get("brake_percent", 0) > 10
                component_data["mode"] = fields.get("mode", 0)
                component_data["mode_name"] = ["eco", "sport", "turbo"][min(fields.get("mode", 0), 2)]
                component_data["headlight"] = fields.get("headlight", False)
                component_data["cruise"] = fields.get("cruise_control", False)

            elif packet.direction == "controller_to_dash":
                fields = packet.fields
                component_data["speed_kmh"] = fields.get("speed_kmh", 0)
                component_data["voltage"] = fields.get("voltage", 0)
                component_data["current"] = fields.get("current", 0)
                component_data["temperature"] = fields.get("temperature", 0)
                component_data["error_code"] = fields.get("error_code", 0)
                component_data["error_message"] = fields.get("error_message", "No error")
                # Estimate RPM from speed (typical e-scooter wheel ~8.5" diameter)
                # RPM = (speed_kmh * 1000 / 60) / (wheel_circumference_m)
                # For ~8.5" wheel: circumference ≈ 0.68m, so RPM ≈ speed * 24.5
                component_data["rpm"] = int(component_data["speed_kmh"] * 24.5)

        return component_data

    def get_latest_components(self) -> Dict:
        """Get component data from already-parsed packets (for use with existing session)."""
        if not self.packets:
            return None

        component_data = {
            "timestamp": None,
            "throttle_percent": 0,
            "throttle_raw": 0,
            "brake_engaged": False,
            "brake_percent": 0,
            "brake_raw": 0,
            "speed_kmh": 0,
            "voltage": 0,
            "current": 0,
            "temperature": 0,
            "mode": 0,
            "mode_name": "eco",
            "headlight": False,
            "cruise": False,
            "rpm": 0,
            "error_code": 0,
            "error_message": "No error",
            "protocol": "jp_qs_s4",
            "packet_valid": True
        }

        # Process last 20 packets for freshest data
        for packet in self.packets[-20:]:
            if not packet.checksum_valid:
                continue

            if packet.direction == "dash_to_controller":
                fields = packet.fields
                component_data["throttle_percent"] = fields.get("throttle_percent", 0)
                component_data["throttle_raw"] = fields.get("throttle_raw", 0)
                component_data["brake_percent"] = fields.get("brake_percent", 0)
                component_data["brake_raw"] = fields.get("brake_raw", 0)
                component_data["brake_engaged"] = fields.get("brake_percent", 0) > 10
                component_data["mode"] = fields.get("mode", 0)
                component_data["mode_name"] = ["eco", "sport", "turbo"][min(fields.get("mode", 0), 2)]
                component_data["headlight"] = fields.get("headlight", False)
                component_data["cruise"] = fields.get("cruise_control", False)

            elif packet.direction == "controller_to_dash":
                fields = packet.fields
                component_data["speed_kmh"] = fields.get("speed_kmh", 0)
                component_data["voltage"] = fields.get("voltage", 0)
                component_data["current"] = fields.get("current", 0)
                component_data["temperature"] = fields.get("temperature", 0)
                component_data["error_code"] = fields.get("error_code", 0)
                component_data["error_message"] = fields.get("error_message", "No error")
                component_data["rpm"] = int(component_data["speed_kmh"] * 24.5)

        return component_data
