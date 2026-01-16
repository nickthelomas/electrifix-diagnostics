"""
ElectriFix Diagnostics - Analysis Module
Baseline comparison and anomaly detection.
"""

import json
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

from protocol_parsers import NinebotParser, JPParser, GenericParser


@dataclass
class Anomaly:
    """Detected anomaly in capture data."""
    anomaly_type: str
    severity: str  # 'low', 'medium', 'high', 'critical'
    description: str
    byte_position: Optional[int] = None
    expected_value: Optional[str] = None
    actual_value: Optional[str] = None


@dataclass
class ComparisonResult:
    """Result of baseline vs capture comparison."""
    match_percentage: float
    anomalies: List[Anomaly]
    packet_stats: Dict
    summary: str


class DiagnosticAnalyzer:
    """Analyzes capture data against baselines."""
    
    def __init__(self):
        self.baseline_data: Optional[Dict] = None
        self.capture_data: bytes = b''
        self.protocol: Optional[str] = None
        self.parser = None
        self.anomalies: List[Anomaly] = []
    
    def set_baseline(self, baseline: Dict):
        """Set the baseline data for comparison."""
        self.baseline_data = baseline
    
    def analyze_capture(self, capture_data: bytes, protocol: str = "auto") -> ComparisonResult:
        """
        Analyze captured data and compare against baseline.
        
        Args:
            capture_data: Raw captured bytes
            protocol: Protocol type or "auto" for auto-detection
            
        Returns:
            ComparisonResult with anomalies and statistics
        """
        self.capture_data = capture_data
        self.anomalies = []
        
        # Select parser based on protocol
        if protocol == "auto":
            protocol = self._detect_protocol(capture_data)
        
        self.protocol = protocol
        
        if protocol == "ninebot":
            self.parser = NinebotParser()
            packets = self.parser.parse(capture_data)
            stats = self.parser.get_summary()
        elif protocol == "jp_qs_s4":
            self.parser = JPParser()
            packets = self.parser.parse(capture_data)
            stats = self.parser.get_summary()
        else:
            self.parser = GenericParser()
            stats = self.parser.analyze(capture_data)
            packets = []
        
        # Analyze for anomalies
        self._check_communication_health(stats)
        self._check_error_codes(stats)
        self._check_data_quality(stats)
        self._check_voltage_anomalies(stats)
        self._check_throttle_anomalies(stats)

        # Compare against baseline if available
        if self.baseline_data:
            self._compare_to_baseline(packets, stats)
        
        # Calculate match percentage
        match_pct = self._calculate_match_percentage(stats)
        
        # Generate summary
        summary = self._generate_summary(stats)
        
        return ComparisonResult(
            match_percentage=match_pct,
            anomalies=self.anomalies,
            packet_stats=stats,
            summary=summary
        )
    
    def _detect_protocol(self, data: bytes) -> str:
        """Auto-detect protocol from data patterns."""
        # Check for Ninebot headers
        if b'\x5a\xa5' in data or b'\x55\xaa' in data:
            return "ninebot"
        
        # Check for JP/QS-S4 header
        if b'\x01\x03' in data:
            return "jp_qs_s4"
        
        return "unknown"
    
    def _check_communication_health(self, stats: Dict):
        """Check for communication issues."""
        total_packets = stats.get("total_packets", 0)
        
        if total_packets == 0:
            self.anomalies.append(Anomaly(
                anomaly_type="no_communication",
                severity="critical",
                description="No valid packets detected - check wiring connections"
            ))
            return
        
        # Check checksum error rate
        error_rate = stats.get("checksum_error_rate", 0)
        if error_rate > 50:
            self.anomalies.append(Anomaly(
                anomaly_type="high_checksum_errors",
                severity="critical",
                description=f"Checksum error rate {error_rate}% - likely baud rate mismatch or signal integrity issue"
            ))
        elif error_rate > 20:
            self.anomalies.append(Anomaly(
                anomaly_type="elevated_checksum_errors",
                severity="high",
                description=f"Checksum error rate {error_rate}% - possible interference or loose connection"
            ))
        elif error_rate > 5:
            self.anomalies.append(Anomaly(
                anomaly_type="minor_checksum_errors",
                severity="medium",
                description=f"Checksum error rate {error_rate}% - minor signal quality issues"
            ))
        
        # Protocol-specific checks
        if self.protocol == "jp_qs_s4":
            dash_to_ctrl = stats.get("dash_to_controller_packets", 0)
            ctrl_to_dash = stats.get("controller_to_dash_packets", 0)
            
            if dash_to_ctrl == 0:
                self.anomalies.append(Anomaly(
                    anomaly_type="no_dash_communication",
                    severity="high",
                    description="No dashboard→controller packets - dashboard may be faulty"
                ))
            
            if ctrl_to_dash == 0:
                self.anomalies.append(Anomaly(
                    anomaly_type="no_controller_response",
                    severity="high",
                    description="No controller→dashboard packets - controller may be faulty"
                ))
        
        elif self.protocol == "ninebot":
            sources = stats.get("communication_sources", {})
            
            if "ESC" not in sources:
                self.anomalies.append(Anomaly(
                    anomaly_type="no_esc_communication",
                    severity="high",
                    description="No ESC communication detected - controller may be faulty"
                ))
            
            if "BMS" not in sources and "BLE" not in sources:
                self.anomalies.append(Anomaly(
                    anomaly_type="limited_communication",
                    severity="medium",
                    description="Limited device communication - some modules may be offline"
                ))
    
    def _check_error_codes(self, stats: Dict):
        """Check for error codes in parsed data."""
        error_codes = stats.get("error_codes_seen", {})
        
        # JP/QS-S4 error code descriptions
        jp_errors = {
            "0x01": ("Motor hall sensor error", "high"),
            "0x02": ("Throttle error", "high"),
            "0x03": ("Motor phase error", "critical"),
            "0x04": ("Motor stalled", "high"),
            "0x05": ("Controller overheat", "high"),
            "0x06": ("Overcurrent protection", "high"),
            "0x07": ("Battery low voltage", "medium"),
            "0x08": ("Battery high voltage", "high"),
            "0x09": ("BMS communication error", "high"),
        }
        
        for code, count in error_codes.items():
            if code in jp_errors:
                desc, severity = jp_errors[code]
                self.anomalies.append(Anomaly(
                    anomaly_type="error_code",
                    severity=severity,
                    description=f"{desc} (code {code}) - occurred {count} times"
                ))
            else:
                self.anomalies.append(Anomaly(
                    anomaly_type="unknown_error_code",
                    severity="medium",
                    description=f"Unknown error code {code} - occurred {count} times"
                ))
    
    def _check_data_quality(self, stats: Dict):
        """Check overall data quality."""
        if self.protocol == "unknown":
            quality = stats.get("quality_assessment", "")

            if quality == "likely_noise":
                self.anomalies.append(Anomaly(
                    anomaly_type="signal_noise",
                    severity="critical",
                    description="Data appears to be noise - check baud rate and connections"
                ))
            elif quality == "insufficient_data":
                self.anomalies.append(Anomaly(
                    anomaly_type="insufficient_data",
                    severity="high",
                    description="Not enough data captured - ensure scooter is powered on"
                ))

    def _check_voltage_anomalies(self, stats: Dict):
        """Check for voltage-related anomalies."""
        voltage_min = stats.get("voltage_min")
        voltage_max = stats.get("voltage_max")

        if voltage_max is not None and voltage_max > 70:
            self.anomalies.append(Anomaly(
                anomaly_type="overvoltage",
                severity="critical",
                description=f"Overvoltage detected: {voltage_max}V - battery or charger issue, risk of damage"
            ))
        elif voltage_max is not None and voltage_max > 62:
            self.anomalies.append(Anomaly(
                anomaly_type="high_voltage_warning",
                severity="high",
                description=f"High voltage detected: {voltage_max}V - check battery/charger"
            ))

        if voltage_min is not None and voltage_min < 35 and voltage_min > 0:
            self.anomalies.append(Anomaly(
                anomaly_type="undervoltage",
                severity="high",
                description=f"Undervoltage detected: {voltage_min}V - battery low or BMS issue"
            ))
        elif voltage_min is not None and voltage_min < 40 and voltage_min > 0:
            self.anomalies.append(Anomaly(
                anomaly_type="low_voltage_warning",
                severity="medium",
                description=f"Low voltage detected: {voltage_min}V - battery may need charging"
            ))

    def _check_throttle_anomalies(self, stats: Dict):
        """Check for throttle-related anomalies."""
        if stats.get("throttle_stuck"):
            self.anomalies.append(Anomaly(
                anomaly_type="stuck_throttle",
                severity="critical",
                description="Throttle appears stuck at high value - SAFETY HAZARD, check throttle sensor/wiring"
            ))

    def _compare_to_baseline(self, packets: List, stats: Dict):
        """Compare capture to stored baseline."""
        if not self.baseline_data:
            return
        
        baseline_stats = self.baseline_data.get("stats", {})
        
        # Compare packet counts
        baseline_packets = baseline_stats.get("total_packets", 0)
        current_packets = stats.get("total_packets", 0)
        
        if baseline_packets > 0:
            ratio = current_packets / baseline_packets
            
            if ratio < 0.5:
                self.anomalies.append(Anomaly(
                    anomaly_type="reduced_packet_count",
                    severity="medium",
                    description=f"Packet count significantly lower than baseline ({current_packets} vs {baseline_packets})"
                ))
        
        # Compare error rates
        baseline_error_rate = baseline_stats.get("checksum_error_rate", 0)
        current_error_rate = stats.get("checksum_error_rate", 0)
        
        if current_error_rate > baseline_error_rate + 10:
            self.anomalies.append(Anomaly(
                anomaly_type="degraded_signal",
                severity="medium",
                description=f"Signal quality degraded compared to baseline ({current_error_rate}% vs {baseline_error_rate}%)"
            ))
    
    def _calculate_match_percentage(self, stats: Dict) -> float:
        """Calculate how well capture matches expected behavior."""
        if not stats.get("total_packets"):
            return 0.0
        
        score = 100.0
        
        # Deduct for checksum errors
        error_rate = stats.get("checksum_error_rate", 0)
        score -= min(error_rate, 50)
        
        # Deduct for each anomaly
        for anomaly in self.anomalies:
            if anomaly.severity == "critical":
                score -= 25
            elif anomaly.severity == "high":
                score -= 15
            elif anomaly.severity == "medium":
                score -= 8
            elif anomaly.severity == "low":
                score -= 3
        
        return max(0.0, min(100.0, score))
    
    def _generate_summary(self, stats: Dict) -> str:
        """Generate human-readable summary."""
        lines = []
        
        protocol_name = {
            "ninebot": "Ninebot/Xiaomi",
            "jp_qs_s4": "JP/QS-S4 (Chinese)",
            "unknown": "Unknown"
        }.get(self.protocol, self.protocol)
        
        lines.append(f"Protocol: {protocol_name}")
        lines.append(f"Total packets: {stats.get('total_packets', 0)}")
        lines.append(f"Checksum error rate: {stats.get('checksum_error_rate', 0)}%")
        
        critical_count = sum(1 for a in self.anomalies if a.severity == "critical")
        high_count = sum(1 for a in self.anomalies if a.severity == "high")
        
        if critical_count > 0:
            lines.append(f"CRITICAL ISSUES: {critical_count}")
        if high_count > 0:
            lines.append(f"High priority issues: {high_count}")
        
        return "\n".join(lines)
    
    def get_anomalies_for_ai(self) -> List[str]:
        """Get anomaly list formatted for AI prompt."""
        return [
            f"[{a.severity.upper()}] {a.anomaly_type}: {a.description}"
            for a in self.anomalies
        ]
