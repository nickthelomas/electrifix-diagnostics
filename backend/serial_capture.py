"""
ElectriFix Diagnostics - Serial Capture Engine
Handles USB-TTL serial communication with baud rate auto-detection
"""

import serial
import serial.tools.list_ports
import time
import asyncio
from typing import Optional, List, Dict, Callable, Tuple
from dataclasses import dataclass
from datetime import datetime
import threading
import queue


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


class SerialCapture:
    """Serial port capture and auto-detection engine."""

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
        
        if not self.connect(port, baud_rate):
            return False
        
        self.is_capturing = True
        self.current_session = CaptureSession(
            start_time=datetime.now(),
            end_time=None,
            baud_rate=baud_rate,
            port=port,
            packets=[],
            total_bytes=0,
            checksum_errors=0,
            protocol_detected=None
        )
        
        if callback:
            self._callbacks.append(callback)
        
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()
        
        return True
    
    def _capture_loop(self):
        """Background capture loop."""
        start_ms = int(time.time() * 1000)
        error_occurred = False

        while self.is_capturing and self.serial_port and self.serial_port.is_open:
            try:
                if self.serial_port.in_waiting > 0:
                    data = self.serial_port.read(self.serial_port.in_waiting)
                    timestamp_ms = int(time.time() * 1000) - start_ms

                    packet = CapturePacket(
                        timestamp_ms=timestamp_ms,
                        raw_bytes=data,
                        hex_string=data.hex()
                    )

                    with self._lock:
                        if self.current_session:
                            self.current_session.packets.append(packet)
                            self.current_session.total_bytes += len(data)

                    # Notify callbacks
                    for callback in self._callbacks:
                        try:
                            callback(packet)
                        except Exception as e:
                            print(f"Callback error: {e}")

                    # Put in queue for async consumers
                    self.capture_queue.put(packet)

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
