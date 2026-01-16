"""
ElectriFix Diagnostics - Ninebot/Xiaomi Protocol Parser
Reference: https://github.com/etransport/ninebot-docs/wiki/protocol

Packet format: 5A A5 bLen bSrcAddr bDstAddr bCmd bArg bPayload[] wChecksumLE
Checksum: 0xFFFF XOR (16-bit sum of bSrcAddr through bPayload)
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import struct


@dataclass
class NinebotPacket:
    """Parsed Ninebot protocol packet."""
    raw_bytes: bytes
    header: bytes
    length: int
    src_addr: int
    dst_addr: int
    command: int
    argument: int
    payload: bytes
    checksum: int
    checksum_valid: bool
    
    # Human-readable interpretations
    src_name: str
    dst_name: str
    command_name: str


class NinebotParser:
    """Parser for Ninebot/Xiaomi e-scooter protocol."""
    
    # Packet headers
    HEADER_5AA5 = b'\x5a\xa5'
    HEADER_55AA = b'\x55\xaa'
    
    # Address mappings
    ADDRESSES = {
        0x20: "ESC",      # Electronic Speed Controller
        0x21: "BLE",      # Bluetooth Module
        0x22: "BMS",      # Battery Management System
        0x23: "EXT_BMS",  # External Battery
        0x3D: "APP",      # Smartphone App
        0x3E: "PC",       # PC/Debug
    }
    
    # Common commands
    COMMANDS = {
        0x01: "READ",
        0x02: "WRITE",
        0x03: "READ_RESPONSE",
        0x05: "WRITE_RESPONSE",
        0x64: "AUTH_INIT",
        0x65: "AUTH_CHALLENGE",
    }
    
    # Known register meanings (partial list)
    REGISTERS = {
        0x10: "serial_number",
        0x1A: "firmware_version",
        0x22: "total_mileage",
        0x25: "current_speed",
        0x26: "average_speed",
        0x29: "total_runtime",
        0x2A: "current_runtime",
        0x31: "bms_voltage",
        0x32: "bms_current",
        0x33: "bms_remaining_capacity",
        0x34: "bms_battery_percent",
        0x35: "bms_temperature_1",
        0x36: "bms_temperature_2",
        0x3A: "error_code",
        0x3B: "warning_code",
        0x50: "throttle_value",
        0x51: "brake_value",
        0x70: "lock_status",
        0xB0: "tail_light",
    }
    
    def __init__(self):
        self.packets: List[NinebotPacket] = []
        self.errors: List[str] = []
        self.stats = {
            "total_packets": 0,
            "valid_checksums": 0,
            "invalid_checksums": 0,
            "sources": {},
            "destinations": {},
            "commands": {}
        }
    
    def parse(self, data: bytes) -> List[NinebotPacket]:
        """Parse raw data into Ninebot packets."""
        self.packets = []
        self.errors = []
        self.stats = {
            "total_packets": 0,
            "valid_checksums": 0,
            "invalid_checksums": 0,
            "sources": {},
            "destinations": {},
            "commands": {}
        }
        
        pos = 0
        while pos < len(data) - 6:  # Minimum packet size
            # Look for packet header
            header_pos = self._find_header(data, pos)
            if header_pos < 0:
                break
            
            pos = header_pos
            packet = self._parse_packet(data, pos)
            
            if packet:
                self.packets.append(packet)
                self._update_stats(packet)
                pos += 2 + 1 + len(packet.payload) + 4 + 2  # header + len + payload + addresses/cmd/arg + checksum
            else:
                pos += 1  # Move past bad header
        
        return self.packets
    
    def _find_header(self, data: bytes, start: int) -> int:
        """Find next packet header starting from position."""
        for header in [self.HEADER_5AA5, self.HEADER_55AA]:
            pos = data.find(header, start)
            if pos >= 0:
                return pos
        return -1
    
    def _parse_packet(self, data: bytes, pos: int) -> Optional[NinebotPacket]:
        """Parse a single packet at position."""
        try:
            if len(data) - pos < 9:  # Minimum: header(2) + len(1) + src(1) + dst(1) + cmd(1) + arg(1) + checksum(2)
                return None
            
            header = data[pos:pos+2]
            length = data[pos+2]
            
            # Check if we have enough data
            if len(data) - pos < 2 + 1 + length + 2:
                return None
            
            src_addr = data[pos+3]
            dst_addr = data[pos+4]
            command = data[pos+5]
            argument = data[pos+6]
            
            payload_length = length - 2 if length > 2 else 0
            payload = data[pos+7:pos+7+payload_length] if payload_length > 0 else b''
            
            checksum_pos = pos + 5 + length
            if checksum_pos + 2 > len(data):
                return None
            
            checksum = struct.unpack('<H', data[checksum_pos:checksum_pos+2])[0]
            
            # Calculate expected checksum
            checksum_data = data[pos+3:checksum_pos]
            calculated_checksum = self._calculate_checksum(checksum_data)
            checksum_valid = (checksum == calculated_checksum)
            
            return NinebotPacket(
                raw_bytes=data[pos:checksum_pos+2],
                header=header,
                length=length,
                src_addr=src_addr,
                dst_addr=dst_addr,
                command=command,
                argument=argument,
                payload=payload,
                checksum=checksum,
                checksum_valid=checksum_valid,
                src_name=self.ADDRESSES.get(src_addr, f"0x{src_addr:02X}"),
                dst_name=self.ADDRESSES.get(dst_addr, f"0x{dst_addr:02X}"),
                command_name=self.COMMANDS.get(command, f"0x{command:02X}")
            )
            
        except Exception as e:
            self.errors.append(f"Parse error at position {pos}: {e}")
            return None
    
    def _calculate_checksum(self, data: bytes) -> int:
        """Calculate Ninebot checksum: 0xFFFF XOR (16-bit sum of bytes)."""
        total = sum(data)
        return 0xFFFF ^ (total & 0xFFFF)
    
    def _update_stats(self, packet: NinebotPacket):
        """Update statistics with parsed packet."""
        self.stats["total_packets"] += 1
        
        if packet.checksum_valid:
            self.stats["valid_checksums"] += 1
        else:
            self.stats["invalid_checksums"] += 1
        
        # Count by source
        src = packet.src_name
        self.stats["sources"][src] = self.stats["sources"].get(src, 0) + 1
        
        # Count by destination
        dst = packet.dst_name
        self.stats["destinations"][dst] = self.stats["destinations"].get(dst, 0) + 1
        
        # Count by command
        cmd = packet.command_name
        self.stats["commands"][cmd] = self.stats["commands"].get(cmd, 0) + 1
    
    def interpret_register(self, register: int, value: bytes) -> Dict:
        """Interpret a register value."""
        reg_name = self.REGISTERS.get(register, f"register_0x{register:02X}")
        
        result = {
            "register": register,
            "name": reg_name,
            "raw_value": value.hex(),
        }
        
        # Interpret common registers
        if len(value) >= 2:
            int_value = struct.unpack('<H', value[:2])[0]
            result["int_value"] = int_value
            
            if reg_name == "current_speed":
                result["interpreted"] = f"{int_value / 1000:.1f} km/h"
            elif reg_name == "bms_voltage":
                result["interpreted"] = f"{int_value / 100:.2f} V"
            elif reg_name == "bms_current":
                result["interpreted"] = f"{int_value / 100:.2f} A"
            elif reg_name == "bms_battery_percent":
                result["interpreted"] = f"{int_value}%"
            elif reg_name in ["bms_temperature_1", "bms_temperature_2"]:
                result["interpreted"] = f"{int_value / 10:.1f} °C"
        
        return result
    
    def get_summary(self) -> Dict:
        """Get parsing summary."""
        checksum_error_rate = 0
        if self.stats["total_packets"] > 0:
            checksum_error_rate = (self.stats["invalid_checksums"] / self.stats["total_packets"]) * 100

        return {
            "protocol": "ninebot",
            "total_packets": self.stats["total_packets"],
            "checksum_error_rate": round(checksum_error_rate, 2),
            "communication_sources": self.stats["sources"],
            "communication_destinations": self.stats["destinations"],
            "command_distribution": self.stats["commands"],
            "parse_errors": len(self.errors)
        }

    def parse_to_components(self, data: bytes) -> Optional[Dict]:
        """
        Parse raw packet into component-friendly format for real-time display.

        Returns a dictionary with all component states, or None if packet is invalid.
        """
        # Parse the data
        packets = self.parse(data)
        if not packets:
            return None

        # Initialize component data with defaults
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
            "battery_percent": 0,
            "protocol": "ninebot",
            "packet_valid": True
        }

        # Extract values from recent packets
        for packet in packets[-30:]:  # Look at last 30 packets
            if not packet.checksum_valid:
                continue

            # Check if this is a read response with data
            if packet.command == 0x03:  # READ_RESPONSE
                self._extract_register_value(packet, component_data)

        return component_data

    def _extract_register_value(self, packet: 'NinebotPacket', component_data: Dict):
        """Extract register value from a read response packet."""
        register = packet.argument
        payload = packet.payload

        if len(payload) < 2:
            return

        # Convert payload to integer value (little-endian)
        value = struct.unpack('<H', payload[:2])[0] if len(payload) >= 2 else 0

        # Map register to component field
        if register == 0x25:  # Current speed
            component_data["speed_kmh"] = value / 1000.0
            component_data["rpm"] = int(component_data["speed_kmh"] * 24.5)
        elif register == 0x31:  # BMS voltage
            component_data["voltage"] = value / 100.0
        elif register == 0x32:  # BMS current
            component_data["current"] = value / 100.0
        elif register == 0x34:  # Battery percent
            component_data["battery_percent"] = min(value, 100)
        elif register == 0x35:  # Temperature 1
            component_data["temperature"] = value / 10.0
        elif register == 0x3A:  # Error code
            component_data["error_code"] = value
            component_data["error_message"] = self._get_error_message(value)
        elif register == 0x50:  # Throttle
            component_data["throttle_raw"] = value
            component_data["throttle_percent"] = min(100, value / 2.55)  # Assuming 0-255 range
        elif register == 0x51:  # Brake
            component_data["brake_raw"] = value
            component_data["brake_percent"] = min(100, value / 2.55)
            component_data["brake_engaged"] = value > 25
        elif register == 0xB0:  # Tail light / headlight
            component_data["headlight"] = value > 0

    def _get_error_message(self, error_code: int) -> str:
        """Convert Ninebot error code to message."""
        error_messages = {
            0: "No error",
            10: "Undervoltage",
            11: "Overvoltage",
            12: "Motor hall sensor error",
            13: "Motor phase error",
            14: "BMS communication error",
            15: "Controller overheat",
            16: "Motor overheat",
            17: "Overcurrent",
            18: "Short circuit",
            19: "Motor stalled",
            21: "Throttle error",
            22: "Brake error",
            23: "Serial communication error",
            24: "Battery cell imbalance",
        }
        return error_messages.get(error_code, f"Unknown error ({error_code})")

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
            "battery_percent": 0,
            "protocol": "ninebot",
            "packet_valid": True
        }

        # Process last 30 packets
        for packet in self.packets[-30:]:
            if not packet.checksum_valid:
                continue

            if packet.command == 0x03:  # READ_RESPONSE
                self._extract_register_value(packet, component_data)

        return component_data
