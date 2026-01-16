"""
ElectriFix Diagnostics - Serial Capture Engine
Handles USB-TTL serial communication with baud rate auto-detection
Includes simulation mode for testing without real hardware
"""

import serial
import serial.tools.list_ports
import time
import asyncio
import random
import math
from typing import Optional, List, Dict, Callable, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import threading
import queue


class SimulationFault(Enum):
    """Types of faults that can be injected during simulation."""
    NONE = "none"
    STUCK_THROTTLE = "stuck_throttle"
    CHECKSUM_ERRORS = "checksum_errors"
    NO_RESPONSE = "no_response"
    INTERMITTENT = "intermittent"
    OVERVOLTAGE = "overvoltage"
    UNDERVOLTAGE = "undervoltage"
    MOTOR_ERROR = "motor_error"


@dataclass
class SimulationConfig:
    """Configuration for simulation mode."""
    enabled: bool = False
    protocol: str = "jp_qs_s4"  # 'jp_qs_s4' or 'ninebot'
    fault: SimulationFault = SimulationFault.NONE
    fault_probability: float = 0.1  # Probability of fault occurrence per packet
    simulate_power_on: bool = True
    throttle_response: bool = True
    base_voltage: float = 48.0
    base_speed: float = 0.0


@dataclass
class CapturePacket:
    """Single captured data packet with timestamp."""
    timestamp_ms: int
    raw_bytes: bytes
    hex_string: str


@dataclass
class CaptureSession:
    """Complete capture session data."""
    start_time: datetime
    end_time: Optional[datetime]
    baud_rate: int
    port: str
    packets: List[CapturePacket]
    total_bytes: int
    checksum_errors: int
    protocol_detected: Optional[str]
    is_simulated: bool = False


class ScooterSimulator:
    """Simulates e-scooter UART data for testing without real hardware."""

    def __init__(self, config: SimulationConfig):
        self.config = config
        self.state = {
            "powered_on": False,
            "power_on_time": None,
            "throttle": 0,
            "brake": 0,
            "speed": 0.0,
            "voltage": config.base_voltage,
            "current": 0.0,
            "temperature": 25,
            "error_code": 0,
            "mode": 1,
            "headlight": False,
            "cruise_control": False,
            "packet_count": 0,
        }
        self._last_packet_time = 0
        self._stuck_throttle_value = random.randint(100, 255)

    def power_on_sequence(self) -> List[bytes]:
        """Generate power-on sequence packets."""
        self.state["powered_on"] = True
        self.state["power_on_time"] = time.time()
        packets = []

        if self.config.protocol == "ninebot":
            # Ninebot init sequence - ESC to BLE auth packets
            packets.append(self._generate_ninebot_packet(0x20, 0x21, 0x64, 0x00, b'\x00\x00\x00\x00'))
            packets.append(self._generate_ninebot_packet(0x21, 0x20, 0x65, 0x00, b'\x01\x00\x00\x00'))
        else:
            # JP protocol - initial zero throttle packets
            for _ in range(3):
                packets.append(self._generate_jp_dash_to_ctrl(0, 0, 1, False))
                packets.append(self._generate_jp_ctrl_to_dash(0, self.config.base_voltage, 0, 0, 25))

        return packets

    def generate_packet(self) -> bytes:
        """Generate a single simulated packet based on current state."""
        self.state["packet_count"] += 1

        # Apply fault injection
        if self.config.fault != SimulationFault.NONE:
            if random.random() < self.config.fault_probability:
                return self._generate_faulty_packet()

        # Simulate throttle response
        if self.config.throttle_response:
            self._update_physics()

        if self.config.protocol == "ninebot":
            return self._generate_ninebot_normal_packet()
        else:
            return self._generate_jp_normal_packet()

    def _update_physics(self):
        """Update simulated physics based on throttle input."""
        # Gradually change throttle (simulating user input)
        elapsed = time.time() - (self.state.get("power_on_time") or time.time())

        if elapsed < 2:
            # Power-on phase - no throttle
            self.state["throttle"] = 0
        elif elapsed < 5:
            # Initial throttle ramp up
            self.state["throttle"] = min(128, int((elapsed - 2) * 40))
        else:
            # Vary throttle with sine wave for realistic capture
            self.state["throttle"] = int(128 + 80 * math.sin(elapsed * 0.5))

        # Speed responds to throttle with lag
        target_speed = (self.state["throttle"] / 255) * 45  # Max 45 km/h
        self.state["speed"] = self.state["speed"] * 0.9 + target_speed * 0.1

        # Current increases with throttle
        self.state["current"] = (self.state["throttle"] / 255) * 15  # Max 15A

        # Voltage sags under load
        self.state["voltage"] = self.config.base_voltage - (self.state["current"] * 0.1)

        # Temperature slowly rises
        if self.state["current"] > 5:
            self.state["temperature"] = min(65, self.state["temperature"] + 0.01)

    def _generate_faulty_packet(self) -> bytes:
        """Generate a packet with the configured fault."""
        if self.config.fault == SimulationFault.STUCK_THROTTLE:
            # Throttle byte stuck at a high value
            if self.config.protocol == "jp_qs_s4":
                return self._generate_jp_dash_to_ctrl(
                    self._stuck_throttle_value, 0, 1, False
                )
            else:
                # Ninebot throttle stuck
                return self._generate_ninebot_packet(
                    0x20, 0x21, 0x01, 0x50,  # Throttle register
                    bytes([self._stuck_throttle_value, 0])
                )

        elif self.config.fault == SimulationFault.CHECKSUM_ERRORS:
            # Generate packet with bad checksum
            packet = self._generate_jp_normal_packet() if self.config.protocol == "jp_qs_s4" else self._generate_ninebot_normal_packet()
            # Corrupt the checksum
            packet = bytearray(packet)
            packet[-1] ^= 0xFF
            return bytes(packet)

        elif self.config.fault == SimulationFault.NO_RESPONSE:
            # Return empty or garbage data
            return b'\xff' * 15 if self.config.protocol == "jp_qs_s4" else b'\xff' * 10

        elif self.config.fault == SimulationFault.INTERMITTENT:
            # Sometimes no data
            if random.random() < 0.3:
                return b''
            return self._generate_jp_normal_packet() if self.config.protocol == "jp_qs_s4" else self._generate_ninebot_normal_packet()

        elif self.config.fault == SimulationFault.OVERVOLTAGE:
            # Voltage reading too high
            return self._generate_jp_ctrl_to_dash(
                self.state["speed"], 75.0, self.state["current"], 0x08, self.state["temperature"]
            )

        elif self.config.fault == SimulationFault.UNDERVOLTAGE:
            # Voltage reading too low
            return self._generate_jp_ctrl_to_dash(
                self.state["speed"], 32.0, self.state["current"], 0x07, self.state["temperature"]
            )

        elif self.config.fault == SimulationFault.MOTOR_ERROR:
            # Motor hall sensor error
            return self._generate_jp_ctrl_to_dash(
                0, self.state["voltage"], 0, 0x01, self.state["temperature"]
            )

        # Default - normal packet
        return self._generate_jp_normal_packet() if self.config.protocol == "jp_qs_s4" else self._generate_ninebot_normal_packet()

    def _generate_jp_normal_packet(self) -> bytes:
        """Generate normal JP protocol packet."""
        # Alternate between dash->ctrl and ctrl->dash
        if self.state["packet_count"] % 2 == 0:
            return self._generate_jp_dash_to_ctrl(
                self.state["throttle"],
                self.state["brake"],
                self.state["mode"],
                self.state["headlight"]
            )
        else:
            return self._generate_jp_ctrl_to_dash(
                self.state["speed"],
                self.state["voltage"],
                self.state["current"],
                self.state["error_code"],
                self.state["temperature"]
            )

    def _generate_jp_dash_to_ctrl(self, throttle: int, brake: int, mode: int, headlight: bool) -> bytes:
        """Generate JP dashboard to controller packet."""
        packet = bytearray(15)
        packet[0] = 0x01  # Header
        packet[1] = 0x03  # Header
        packet[2] = min(255, max(0, throttle))  # Throttle
        packet[3] = min(255, max(0, brake))  # Brake
        packet[4] = mode  # Mode
        packet[5] = 1 if headlight else 0  # Headlight
        packet[6] = 0  # Unknown
        packet[7] = 1 if self.state.get("cruise_control") else 0  # Cruise
        packet[8:14] = b'\x00' * 6  # Unknown bytes

        # Calculate checksum (XOR of bytes 0-13)
        checksum = 0
        for i in range(14):
            checksum ^= packet[i]
        packet[14] = checksum

        return bytes(packet)

    def _generate_jp_ctrl_to_dash(self, speed: float, voltage: float, current: float,
                                   error_code: int, temperature: int) -> bytes:
        """Generate JP controller to dashboard packet."""
        packet = bytearray(15)
        packet[0] = 0x01  # Header
        packet[1] = 0x04  # Header (some use 0x03)

        # Speed (x10, little endian)
        speed_raw = int(speed * 10)
        packet[2] = speed_raw & 0xFF
        packet[3] = (speed_raw >> 8) & 0xFF

        # Voltage (x10, little endian)
        voltage_raw = int(voltage * 10)
        packet[4] = voltage_raw & 0xFF
        packet[5] = (voltage_raw >> 8) & 0xFF

        # Current (x10, little endian)
        current_raw = int(current * 10)
        packet[6] = current_raw & 0xFF
        packet[7] = (current_raw >> 8) & 0xFF

        packet[8] = error_code  # Error code
        packet[9] = min(255, max(0, temperature))  # Temperature
        packet[10:14] = b'\x00' * 4  # Unknown bytes

        # Calculate checksum
        checksum = 0
        for i in range(14):
            checksum ^= packet[i]
        packet[14] = checksum

        return bytes(packet)

    def _generate_ninebot_normal_packet(self) -> bytes:
        """Generate normal Ninebot protocol packet."""
        # Alternate between different packet types
        packet_type = self.state["packet_count"] % 3

        if packet_type == 0:
            # Speed reading
            speed_raw = int(self.state["speed"] * 1000)
            return self._generate_ninebot_packet(0x20, 0x21, 0x03, 0x25,
                                                  speed_raw.to_bytes(2, 'little'))
        elif packet_type == 1:
            # Battery voltage
            voltage_raw = int(self.state["voltage"] * 100)
            return self._generate_ninebot_packet(0x22, 0x21, 0x03, 0x31,
                                                  voltage_raw.to_bytes(2, 'little'))
        else:
            # Battery percent
            percent = int((self.state["voltage"] - 36) / (54 - 36) * 100)
            percent = max(0, min(100, percent))
            return self._generate_ninebot_packet(0x22, 0x21, 0x03, 0x34,
                                                  bytes([percent, 0]))

    def _generate_ninebot_packet(self, src: int, dst: int, cmd: int, arg: int, payload: bytes) -> bytes:
        """Generate a Ninebot protocol packet."""
        packet = bytearray()
        packet.extend(b'\x5a\xa5')  # Header
        packet.append(2 + len(payload))  # Length
        packet.append(src)  # Source
        packet.append(dst)  # Destination
        packet.append(cmd)  # Command
        packet.append(arg)  # Argument
        packet.extend(payload)  # Payload

        # Calculate checksum: 0xFFFF XOR (16-bit sum of bytes after header)
        checksum_data = packet[3:]
        total = sum(checksum_data)
        checksum = 0xFFFF ^ (total & 0xFFFF)
        packet.extend(checksum.to_bytes(2, 'little'))

        return bytes(packet)

    def set_throttle(self, value: int):
        """Manually set throttle value (0-255)."""
        self.state["throttle"] = max(0, min(255, value))

    def set_fault(self, fault: SimulationFault):
        """Set the active fault type."""
        self.config.fault = fault


class SerialCapture:
    """Serial port capture and auto-detection engine with simulation support."""

    # Common baud rates for e-scooters, ordered by likelihood
    BAUD_RATES = [1200, 9600, 115200, 19200, 2400, 4800, 57600]

    # Known packet headers for protocol detection
    PROTOCOL_HEADERS = {
        "ninebot": [b'\x5a\xa5', b'\x55\xaa'],  # Ninebot/Xiaomi
        "jp_qs_s4": [b'\x01\x03'],  # JP/QS-S4/Chinese generic
    }

    def __init__(self):
        self.serial_port: Optional[serial.Serial] = None
        self.is_capturing = False
        self.capture_queue = queue.Queue()
        self.current_session: Optional[CaptureSession] = None
        self.last_session: Optional[CaptureSession] = None  # Preserve last completed session
        self._capture_thread: Optional[threading.Thread] = None
        self._callbacks: List[Callable] = []
        self._lock = threading.Lock()  # Thread safety for session access

        # Simulation mode
        self.simulation_config = SimulationConfig()
        self.simulator: Optional[ScooterSimulator] = None
        self._checksum_error_count = 0
        self._total_packet_count = 0

    def configure_simulation(self, enabled: bool, protocol: str = "jp_qs_s4",
                            fault: str = "none", fault_probability: float = 0.1):
        """Configure simulation mode settings."""
        try:
            fault_enum = SimulationFault(fault)
        except ValueError:
            fault_enum = SimulationFault.NONE

        self.simulation_config = SimulationConfig(
            enabled=enabled,
            protocol=protocol,
            fault=fault_enum,
            fault_probability=fault_probability,
            simulate_power_on=True,
            throttle_response=True,
            base_voltage=48.0 if protocol == "jp_qs_s4" else 36.0,
        )

        if enabled:
            self.simulator = ScooterSimulator(self.simulation_config)
        else:
            self.simulator = None

    def get_signal_quality(self) -> Dict:
        """Get current signal quality metrics."""
        if self._total_packet_count == 0:
            return {
                "status": "no_data",
                "color": "red",
                "checksum_error_rate": 0,
                "total_packets": 0,
                "checksum_errors": 0
            }

        error_rate = (self._checksum_error_count / self._total_packet_count) * 100

        if error_rate < 5:
            status = "good"
            color = "green"
        elif error_rate < 20:
            status = "fair"
            color = "yellow"
        else:
            status = "poor"
            color = "red"

        return {
            "status": status,
            "color": color,
            "checksum_error_rate": round(error_rate, 2),
            "total_packets": self._total_packet_count,
            "checksum_errors": self._checksum_error_count
        }
    
    @staticmethod
    def list_available_ports() -> List[Dict]:
        """List all available serial ports with details."""
        ports = []
        for port in serial.tools.list_ports.comports():
            ports.append({
                "device": port.device,
                "description": port.description,
                "hwid": port.hwid,
                "manufacturer": port.manufacturer or "Unknown",
                "product": port.product or "Unknown",
                "is_usb": "USB" in port.hwid.upper() if port.hwid else False
            })
        return ports
    
    def connect(self, port: str, baud_rate: int = 9600, timeout: float = 1.0) -> bool:
        """Connect to a serial port."""
        try:
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.close()
            
            self.serial_port = serial.Serial(
                port=port,
                baudrate=baud_rate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=timeout
            )
            return True
        except serial.SerialException as e:
            print(f"Failed to connect to {port}: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from serial port."""
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
            self.serial_port = None
    
    def auto_detect_baud_rate(self, port: str, test_duration: float = 2.0) -> Tuple[Optional[int], Optional[str]]:
        """
        Auto-detect baud rate by testing each rate and analyzing data quality.
        Returns (baud_rate, detected_protocol) or (None, None) if detection fails.
        """
        best_baud = None
        best_score = 0
        best_protocol = None
        
        for baud in self.BAUD_RATES:
            print(f"Testing baud rate: {baud}")
            
            if not self.connect(port, baud, timeout=0.1):
                continue
            
            # Collect data for test duration
            start_time = time.time()
            data_buffer = bytearray()
            
            while time.time() - start_time < test_duration:
                if self.serial_port.in_waiting > 0:
                    data_buffer.extend(self.serial_port.read(self.serial_port.in_waiting))
                time.sleep(0.01)
            
            self.disconnect()
            
            if len(data_buffer) == 0:
                continue
            
            # Score this baud rate
            score, protocol = self._score_data_quality(bytes(data_buffer))
            print(f"  Baud {baud}: {len(data_buffer)} bytes, score={score}, protocol={protocol}")
            
            if score > best_score:
                best_score = score
                best_baud = baud
                best_protocol = protocol
        
        return best_baud, best_protocol
    
    def _score_data_quality(self, data: bytes) -> Tuple[int, Optional[str]]:
        """
        Score data quality for baud rate detection.
        Higher score = more likely correct baud rate.
        """
        if len(data) < 5:
            return 0, None
        
        score = 0
        detected_protocol = None
        
        # Penalize all zeros or all 0xFF (wrong baud rate noise)
        zero_count = data.count(0x00)
        ff_count = data.count(0xFF)
        noise_ratio = (zero_count + ff_count) / len(data)
        
        if noise_ratio > 0.8:
            return 0, None  # Likely wrong baud rate
        
        score += int((1 - noise_ratio) * 50)  # Up to 50 points for clean data
        
        # Check for known protocol headers
        for protocol, headers in self.PROTOCOL_HEADERS.items():
            for header in headers:
                header_count = data.count(header)
                if header_count > 0:
                    score += header_count * 20  # 20 points per header found
                    detected_protocol = protocol
        
        # Bonus for printable ASCII (some protocols use text)
        printable_count = sum(1 for b in data if 32 <= b <= 126)
        printable_ratio = printable_count / len(data)
        if 0.1 < printable_ratio < 0.5:
            score += 10  # Some printable chars suggests structure
        
        # Bonus for repeating patterns (packet structure)
        if len(data) >= 30:
            # Check for 15-byte packet pattern (JP/QS-S4)
            if self._has_repeating_pattern(data, 15):
                score += 30
        
        return score, detected_protocol
    
    def _has_repeating_pattern(self, data: bytes, pattern_length: int) -> bool:
        """Check if data has a repeating pattern of given length."""
        if len(data) < pattern_length * 2:
            return False
        
        # Compare first pattern with subsequent ones
        first_pattern = data[:pattern_length]
        match_count = 0
        
        for i in range(pattern_length, len(data) - pattern_length, pattern_length):
            if data[i:i+2] == first_pattern[:2]:  # Just check header
                match_count += 1
        
        return match_count >= 2
    
    def start_capture(self, port: str, baud_rate: int, callback: Optional[Callable] = None) -> bool:
        """Start capturing serial data in background thread."""
        if self.is_capturing:
            return False

        is_simulated = self.simulation_config.enabled

        # For simulation, skip actual connection
        if not is_simulated:
            if not self.connect(port, baud_rate):
                return False

        self.is_capturing = True
        self._checksum_error_count = 0
        self._total_packet_count = 0

        # Initialize simulator if needed
        if is_simulated and self.simulator is None:
            self.simulator = ScooterSimulator(self.simulation_config)

        self.current_session = CaptureSession(
            start_time=datetime.now(),
            end_time=None,
            baud_rate=baud_rate,
            port=port if not is_simulated else "SIMULATED",
            packets=[],
            total_bytes=0,
            checksum_errors=0,
            protocol_detected=self.simulation_config.protocol if is_simulated else None,
            is_simulated=is_simulated
        )

        if callback:
            self._callbacks.append(callback)

        if is_simulated:
            self._capture_thread = threading.Thread(target=self._simulation_loop, daemon=True)
        else:
            self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()

        return True

    def _simulation_loop(self):
        """Background simulation loop - generates fake scooter data."""
        start_ms = int(time.time() * 1000)

        # Generate power-on sequence if enabled
        if self.simulation_config.simulate_power_on and self.simulator:
            power_on_packets = self.simulator.power_on_sequence()
            for pkt_data in power_on_packets:
                if not self.is_capturing:
                    break
                timestamp_ms = int(time.time() * 1000) - start_ms
                packet = CapturePacket(
                    timestamp_ms=timestamp_ms,
                    raw_bytes=pkt_data,
                    hex_string=pkt_data.hex()
                )
                with self._lock:
                    if self.current_session:
                        self.current_session.packets.append(packet)
                        self.current_session.total_bytes += len(pkt_data)
                        self._total_packet_count += 1
                self.capture_queue.put(packet)
                time.sleep(0.05)  # 50ms between power-on packets

        # Main simulation loop
        packet_interval = 0.015 if self.simulation_config.protocol == "jp_qs_s4" else 0.01

        while self.is_capturing and self.simulator:
            try:
                data = self.simulator.generate_packet()

                if data:
                    timestamp_ms = int(time.time() * 1000) - start_ms

                    packet = CapturePacket(
                        timestamp_ms=timestamp_ms,
                        raw_bytes=data,
                        hex_string=data.hex()
                    )

                    # Check for checksum errors (for signal quality tracking)
                    is_checksum_error = self._check_checksum_error(data)

                    with self._lock:
                        if self.current_session:
                            self.current_session.packets.append(packet)
                            self.current_session.total_bytes += len(data)
                            self._total_packet_count += 1
                            if is_checksum_error:
                                self.current_session.checksum_errors += 1
                                self._checksum_error_count += 1

                    # Notify callbacks
                    for callback in self._callbacks:
                        try:
                            callback(packet)
                        except Exception as e:
                            print(f"Callback error: {e}")

                    self.capture_queue.put(packet)

                time.sleep(packet_interval)

            except Exception as e:
                print(f"Simulation error: {e}")
                break

    def _check_checksum_error(self, data: bytes) -> bool:
        """Check if packet has checksum error."""
        if len(data) < 2:
            return False

        # JP protocol checksum check
        if data[0:2] == b'\x01\x03' or data[0:2] == b'\x01\x04':
            if len(data) == 15:
                calculated = 0
                for i in range(14):
                    calculated ^= data[i]
                return calculated != data[14]

        # Ninebot protocol checksum check
        if data[0:2] == b'\x5a\xa5' or data[0:2] == b'\x55\xaa':
            if len(data) >= 9:
                checksum_data = data[3:-2]
                total = sum(checksum_data)
                calculated = 0xFFFF ^ (total & 0xFFFF)
                actual = int.from_bytes(data[-2:], 'little')
                return calculated != actual

        return False
    
    def _capture_loop(self):
        """Background capture loop for real serial data."""
        start_ms = int(time.time() * 1000)
        error_occurred = False
        data_buffer = bytearray()

        while self.is_capturing and self.serial_port and self.serial_port.is_open:
            try:
                if self.serial_port.in_waiting > 0:
                    data = self.serial_port.read(self.serial_port.in_waiting)
                    timestamp_ms = int(time.time() * 1000) - start_ms

                    # Add to buffer for packet-level checksum validation
                    data_buffer.extend(data)

                    # Check for checksum errors in complete packets
                    is_checksum_error = self._check_checksum_error(bytes(data_buffer[-20:])) if len(data_buffer) >= 15 else False

                    packet = CapturePacket(
                        timestamp_ms=timestamp_ms,
                        raw_bytes=data,
                        hex_string=data.hex()
                    )

                    with self._lock:
                        if self.current_session:
                            self.current_session.packets.append(packet)
                            self.current_session.total_bytes += len(data)
                            self._total_packet_count += 1
                            if is_checksum_error:
                                self.current_session.checksum_errors += 1
                                self._checksum_error_count += 1

                    # Notify callbacks
                    for callback in self._callbacks:
                        try:
                            callback(packet)
                        except Exception as e:
                            print(f"Callback error: {e}")

                    # Put in queue for async consumers
                    self.capture_queue.put(packet)

                    # Keep buffer limited
                    if len(data_buffer) > 1000:
                        data_buffer = data_buffer[-500:]

                time.sleep(0.001)  # 1ms polling

            except serial.SerialException as e:
                print(f"Serial error during capture: {e}")
                error_occurred = True
                break
            except OSError as e:
                print(f"OS error during capture (port disconnected?): {e}")
                error_occurred = True
                break

        # Cleanup on exit (whether normal or due to error)
        self.is_capturing = False
        if error_occurred:
            # Finalize the session even on error so data isn't lost
            with self._lock:
                if self.current_session:
                    self.current_session.end_time = datetime.now()
                    self.last_session = self.current_session
            # Clean up serial port
            try:
                if self.serial_port and self.serial_port.is_open:
                    self.serial_port.close()
            except Exception:
                pass
            self.serial_port = None
    
    def stop_capture(self) -> Optional[CaptureSession]:
        """Stop capturing and return session data."""
        self.is_capturing = False

        if self._capture_thread:
            self._capture_thread.join(timeout=2.0)
            self._capture_thread = None

        self.disconnect()
        self._callbacks.clear()

        with self._lock:
            if self.current_session:
                self.current_session.end_time = datetime.now()
                session = self.current_session
                self.last_session = session  # Preserve for later access
                self.current_session = None
                return session

        return self.last_session  # Return last session if no current session
    
    def get_combined_data(self) -> bytes:
        """Get all captured data combined."""
        if not self.current_session:
            return b''
        return b''.join(p.raw_bytes for p in self.current_session.packets)
    
    async def capture_for_duration(self, port: str, baud_rate: int, duration_seconds: float) -> CaptureSession:
        """Capture data for a specific duration (async)."""
        self.start_capture(port, baud_rate)
        await asyncio.sleep(duration_seconds)
        return self.stop_capture()


# Singleton instance for global access
_capture_instance: Optional[SerialCapture] = None


def get_capture_instance() -> SerialCapture:
    """Get or create the global SerialCapture instance."""
    global _capture_instance
    if _capture_instance is None:
        _capture_instance = SerialCapture()
    return _capture_instance


if __name__ == "__main__":
    # Test port listing
    capture = SerialCapture()
    ports = capture.list_available_ports()
    print("Available ports:")
    for p in ports:
        print(f"  {p['device']}: {p['description']}")
