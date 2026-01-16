"""
ElectriFix Diagnostics - Generic Protocol Parser
Handles unknown protocols with raw data analysis and pattern detection.
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from collections import Counter
import re


@dataclass
class GenericPacket:
    """Generic packet representation."""
    raw_bytes: bytes
    hex_string: str
    possible_checksum: Optional[int]
    pattern_match: Optional[str]


class GenericParser:
    """Parser for unknown protocols - provides raw analysis."""
    
    # Common packet lengths in e-scooter protocols
    COMMON_LENGTHS = [8, 10, 12, 15, 16, 20, 24, 32]
    
    def __init__(self):
        self.raw_data: bytes = b''
        self.detected_patterns: List[Dict] = []
        self.stats = {
            "total_bytes": 0,
            "byte_distribution": {},
            "potential_headers": [],
            "potential_packet_length": None,
            "repeating_patterns": []
        }
    
    def analyze(self, data: bytes) -> Dict:
        """Perform comprehensive analysis on raw data."""
        self.raw_data = data
        self.stats["total_bytes"] = len(data)
        
        # Analyze byte distribution
        self._analyze_byte_distribution(data)
        
        # Find potential packet headers
        self._find_potential_headers(data)
        
        # Detect packet length
        self._detect_packet_length(data)
        
        # Find repeating patterns
        self._find_repeating_patterns(data)
        
        return self.get_summary()
    
    def _analyze_byte_distribution(self, data: bytes):
        """Analyze byte value distribution."""
        counter = Counter(data)
        
        # Get most common bytes
        most_common = counter.most_common(10)
        self.stats["byte_distribution"] = {
            "most_common": [(f"0x{b:02X}", c) for b, c in most_common],
            "unique_bytes": len(counter),
            "zero_count": counter.get(0, 0),
            "ff_count": counter.get(0xFF, 0),
        }
        
        # Calculate entropy-like metric
        total = len(data)
        if total > 0:
            entropy = len(counter) / 256  # Simplified: ratio of unique values
            self.stats["byte_distribution"]["diversity_ratio"] = round(entropy, 3)
    
    def _find_potential_headers(self, data: bytes):
        """Find potential packet headers (repeating 2-byte sequences at regular intervals)."""
        if len(data) < 30:
            return
        
        # Find all 2-byte sequences and their positions
        two_byte_seqs = {}
        for i in range(len(data) - 1):
            seq = data[i:i+2]
            if seq not in two_byte_seqs:
                two_byte_seqs[seq] = []
            two_byte_seqs[seq].append(i)
        
        # Look for sequences that appear at regular intervals
        potential_headers = []
        for seq, positions in two_byte_seqs.items():
            if len(positions) < 3:
                continue
            
            # Check for regular intervals
            intervals = [positions[i+1] - positions[i] for i in range(len(positions)-1)]
            
            # Find most common interval
            interval_counter = Counter(intervals)
            most_common_interval, count = interval_counter.most_common(1)[0]
            
            if count >= 2 and most_common_interval in self.COMMON_LENGTHS:
                potential_headers.append({
                    "header": f"0x{seq.hex().upper()}",
                    "occurrences": len(positions),
                    "likely_packet_length": most_common_interval,
                    "confidence": round(count / len(positions), 2)
                })
        
        # Sort by confidence
        potential_headers.sort(key=lambda x: x["confidence"], reverse=True)
        self.stats["potential_headers"] = potential_headers[:5]  # Top 5
    
    def _detect_packet_length(self, data: bytes):
        """Attempt to detect packet length from patterns."""
        if self.stats["potential_headers"]:
            # Use the most confident header's packet length
            self.stats["potential_packet_length"] = self.stats["potential_headers"][0]["likely_packet_length"]
        else:
            # Try autocorrelation on smaller data
            if len(data) >= 100:
                best_length = None
                best_score = 0
                
                for length in self.COMMON_LENGTHS:
                    score = self._autocorrelation_score(data, length)
                    if score > best_score:
                        best_score = score
                        best_length = length
                
                if best_score > 0.3:
                    self.stats["potential_packet_length"] = best_length
    
    def _autocorrelation_score(self, data: bytes, length: int) -> float:
        """Calculate autocorrelation score for a given length."""
        if len(data) < length * 3:
            return 0
        
        matches = 0
        comparisons = 0
        
        for i in range(0, len(data) - length * 2, length):
            for j in range(min(4, length)):  # Compare first few bytes
                if data[i + j] == data[i + length + j]:
                    matches += 1
                comparisons += 1
        
        return matches / comparisons if comparisons > 0 else 0
    
    def _find_repeating_patterns(self, data: bytes):
        """Find any repeating byte patterns."""
        patterns = []
        
        # Check for specific lengths
        for length in [4, 6, 8]:
            pattern_counts = Counter()
            for i in range(0, len(data) - length, 1):
                pattern = data[i:i+length]
                pattern_counts[pattern] += 1
            
            # Find patterns that repeat
            for pattern, count in pattern_counts.most_common(3):
                if count >= 3:
                    patterns.append({
                        "pattern": pattern.hex(),
                        "length": length,
                        "occurrences": count
                    })
        
        self.stats["repeating_patterns"] = patterns[:10]
    
    def extract_packets(self, header: bytes, length: int) -> List[bytes]:
        """Extract packets using specified header and length."""
        packets = []
        pos = 0
        
        while pos < len(self.raw_data) - length:
            header_pos = self.raw_data.find(header, pos)
            if header_pos < 0:
                break
            
            if header_pos + length <= len(self.raw_data):
                packets.append(self.raw_data[header_pos:header_pos + length])
            
            pos = header_pos + length
        
        return packets
    
    def get_summary(self) -> Dict:
        """Get analysis summary."""
        quality_assessment = "unknown"
        
        if self.stats["total_bytes"] < 10:
            quality_assessment = "insufficient_data"
        elif self.stats["byte_distribution"].get("diversity_ratio", 0) < 0.05:
            quality_assessment = "likely_noise"
        elif self.stats["potential_headers"]:
            quality_assessment = "structured_data"
        else:
            quality_assessment = "unstructured_data"
        
        return {
            "protocol": "unknown",
            "total_bytes": self.stats["total_bytes"],
            "quality_assessment": quality_assessment,
            "byte_distribution": self.stats["byte_distribution"],
            "potential_headers": self.stats["potential_headers"],
            "potential_packet_length": self.stats["potential_packet_length"],
            "repeating_patterns": self.stats["repeating_patterns"]
        }
    
    def get_hex_dump(self, start: int = 0, length: int = 256) -> str:
        """Get formatted hex dump of raw data."""
        data = self.raw_data[start:start + length]
        lines = []
        
        for i in range(0, len(data), 16):
            chunk = data[i:i+16]
            hex_part = ' '.join(f'{b:02X}' for b in chunk)
            ascii_part = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in chunk)
            lines.append(f"{start+i:04X}  {hex_part:<48}  {ascii_part}")
        
        return '\n'.join(lines)
