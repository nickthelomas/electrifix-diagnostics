"""
ElectriFix Diagnostics - AI Engine
OpenRouter API integration for intelligent fault diagnosis.
"""

import os
import json
import httpx
from typing import Dict, List, Optional
from datetime import datetime


class AIEngine:
    """AI-powered diagnostic engine using OpenRouter."""
    
    OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.model = "anthropic/claude-3.5-haiku"  # Cost-effective and capable
        self.usage_log: List[Dict] = []
    
    def is_configured(self) -> bool:
        """Check if API is configured."""
        return self.api_key is not None and len(self.api_key) > 0
    
    def diagnose(
        self,
        model_name: str,
        protocol: str,
        customer_symptoms: str,
        comparison_summary: str,
        anomaly_list: List[str],
        packet_stats: Dict,
        similar_faults: List[Dict] = None
    ) -> Dict:
        """Generate AI diagnosis based on capture analysis."""
        if not self.is_configured():
            return {
                "error": "OpenRouter API not configured",
                "diagnosis": None,
                "confidence": None,
                "recommendations": []
            }
        
        prompt = self._build_diagnosis_prompt(
            model_name=model_name,
            protocol=protocol,
            customer_symptoms=customer_symptoms,
            comparison_summary=comparison_summary,
            anomaly_list=anomaly_list,
            packet_stats=packet_stats,
            similar_faults=similar_faults
        )
        
        try:
            response = httpx.post(
                self.OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "http://localhost:3003",
                    "X-Title": "ElectriFix Diagnostics"
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": 2000,
                    "temperature": 0.3
                },
                timeout=60.0
            )
            
            response.raise_for_status()
            data = response.json()
            
            # Log usage
            usage = data.get("usage", {})
            self.usage_log.append({
                "timestamp": datetime.now().isoformat(),
                "model": self.model,
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0)
            })
            
            # Extract response text
            response_text = data["choices"][0]["message"]["content"]
            return self._parse_diagnosis_response(response_text)
            
        except httpx.HTTPStatusError as e:
            return {
                "error": f"API error: {e.response.status_code} - {e.response.text}",
                "diagnosis": None,
                "confidence": None,
                "recommendations": []
            }
        except Exception as e:
            return {
                "error": f"Error: {str(e)}",
                "diagnosis": None,
                "confidence": None,
                "recommendations": []
            }
    
    def _build_diagnosis_prompt(
        self,
        model_name: str,
        protocol: str,
        customer_symptoms: str,
        comparison_summary: str,
        anomaly_list: List[str],
        packet_stats: Dict,
        similar_faults: List[Dict]
    ) -> str:
        """Build the diagnosis prompt."""
        
        similar_faults_text = "No similar faults in database."
        if similar_faults:
            fault_lines = []
            for fault in similar_faults[:5]:
                actual = fault.get("actual_fault", "Unknown")
                fix = fault.get("fix_applied", "Unknown")
                fault_lines.append(f"  - {actual} -> Fixed by: {fix}")
            similar_faults_text = "\n".join(fault_lines)
        
        anomalies_text = "\n".join(f"  - {a}" for a in anomaly_list) if anomaly_list else "  No anomalies detected"
        
        return f"""You are an expert e-scooter diagnostic AI. Analyze UART serial data between scooter dashboard and controller.

SCOOTER: {model_name}
PROTOCOL: {protocol}
SYMPTOMS: {customer_symptoms or 'None reported'}

ANALYSIS RESULTS:
{comparison_summary}

DETECTED ANOMALIES:
{anomalies_text}

PACKET STATS:
{json.dumps(packet_stats, indent=2)}

SIMILAR PAST FAULTS:
{similar_faults_text}

Provide:
1. LIKELY CAUSE (ranked by probability)
2. TESTS TO CONFIRM
3. RECOMMENDED FIX
4. CONFIDENCE: HIGH/MEDIUM/LOW

Be specific and actionable for a workshop technician."""
    
    def _parse_diagnosis_response(self, response_text: str) -> Dict:
        """Parse the AI response."""
        confidence = "MEDIUM"
        response_upper = response_text.upper()
        
        if "CONFIDENCE: HIGH" in response_upper or "CONFIDENCE LEVEL: HIGH" in response_upper:
            confidence = "HIGH"
        elif "CONFIDENCE: LOW" in response_upper or "CONFIDENCE LEVEL: LOW" in response_upper:
            confidence = "LOW"
        
        recommendations = []
        lines = response_text.split("\n")
        in_fix = False
        
        for line in lines:
            if "RECOMMENDED FIX" in line.upper() or "RECOMMENDATION" in line.upper():
                in_fix = True
                continue
            if in_fix and line.strip():
                if line.strip().startswith(("-", "•", "*", "1", "2", "3")):
                    recommendations.append(line.strip().lstrip("-•*0123456789. "))
                elif line.strip().startswith(("CONFIDENCE", "TEST", "LIKELY")):
                    in_fix = False
        
        return {
            "diagnosis": response_text,
            "confidence": confidence,
            "recommendations": recommendations[:5],
            "raw_response": response_text
        }
    
    def get_usage_stats(self) -> Dict:
        """Get API usage statistics."""
        if not self.usage_log:
            return {"total_calls": 0, "total_input_tokens": 0, "total_output_tokens": 0}
        
        return {
            "total_calls": len(self.usage_log),
            "total_input_tokens": sum(u["input_tokens"] for u in self.usage_log),
            "total_output_tokens": sum(u["output_tokens"] for u in self.usage_log),
            "model": self.model
        }


_ai_engine: Optional[AIEngine] = None


def get_ai_engine() -> AIEngine:
    """Get or create the global AI engine instance."""
    global _ai_engine
    if _ai_engine is None:
        _ai_engine = AIEngine()
    return _ai_engine


def configure_ai_engine(api_key: str):
    """Configure the AI engine with an API key."""
    global _ai_engine
    _ai_engine = AIEngine(api_key)
    return _ai_engine.is_configured()
