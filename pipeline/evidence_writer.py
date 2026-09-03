"""
LLM Evidence Writer
Takes verified evidence and rule engine decision, produces human-readable summary.
The LLM never makes decisions - only formats evidence for human review.
"""

import os
import json
import time
from datetime import datetime
from typing import Dict, List, Tuple, Any
from google import genai


class EvidenceWriter:
    """
    LLM-powered evidence writer that formats case summaries.
    
    Key principle: The LLM sees only verified evidence and the already-made decision.
    It cannot alter the decision or invent facts - only formats what it's given.
    """
    
    SYSTEM_PROMPT = """You are a chargeback evidence summarizer. You will be given a structured JSON object containing only VERIFIED facts about a transaction, and a decision that has ALREADY been made by a separate rule engine, with its numeric score and the rules that fired. Your job: (1) write a 3-6 sentence case summary using ONLY the facts given, never inferring or adding anything, (2) list each evidence item as claim → source_field → value, (3) list evidence gaps explicitly (fields marked not_available), (4) restate the recommendation and confidence exactly as given — never soften or strengthen it. If a fact is missing, say 'not available,' never guess. Output valid JSON: {summary, evidence: [{claim, source_field, value}], gaps, recommendation, confidence}."""
    
    def __init__(self, api_key: str = None):
        """
        Initialize evidence writer with Google Gemini API.
        
        Args:
            api_key: Google API key (defaults to GEMINI_API_KEY env var)
        """
        self.api_key = api_key or os.environ.get('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment")
        
        # Initialize the new google.genai client
        self.client = genai.Client(api_key=self.api_key)
        
        # Configure generation settings
        self.generation_config = {
            "response_mime_type": "application/json"
        }
    
    def write_summary(
        self, 
        case: Dict[str, Any], 
        decision: str, 
        score: int, 
        fired_rules: List[str]
    ) -> Dict[str, Any]:
        """
        Generate human-readable evidence summary using LLM.
        
        Args:
            case: Evidence dictionary from retrieval (with ground truth removed)
            decision: Rule engine decision (CONTEST/REVIEW/DO_NOT_CONTEST)
            score: Numeric score from rule engine
            fired_rules: List of rule descriptions that fired
        
        Returns:
            Parsed JSON response with summary, evidence, gaps, recommendation, confidence
        """
        # Prepare case dict - remove ground truth and internal flags
        case_for_llm = self._sanitize_case(case)
        
        # Prepare input for LLM
        input_data = {
            "case": case_for_llm,
            "decision": {
                "recommendation": decision,
                "score": score,
                "confidence": self._score_to_confidence(score),
                "fired_rules": fired_rules
            }
        }
        
        # Build user message
        user_message = f"Please summarize this chargeback case:\n\n{json.dumps(input_data, indent=2)}"
        
        # Call LLM with timing and error logging
        print(f"    [{datetime.now().strftime('%H:%M:%S')}] Calling Gemini API...")
        start_time = time.time()
        
        try:
            response = self._call_llm(user_message)
            elapsed = time.time() - start_time
            print(f"    [{datetime.now().strftime('%H:%M:%S')}] API call completed ({elapsed:.2f}s)")
            return response
        except json.JSONDecodeError as e:
            # Retry once on parse failure
            elapsed = time.time() - start_time
            print(f"    [{datetime.now().strftime('%H:%M:%S')}] JSON parse failed after {elapsed:.2f}s, retrying...")
            print(f"    Parse error: {e}")
            
            start_time = time.time()
            response = self._call_llm(user_message)
            elapsed = time.time() - start_time
            print(f"    [{datetime.now().strftime('%H:%M:%S')}] Retry completed ({elapsed:.2f}s)")
            return response
        except Exception as e:
            elapsed = time.time() - start_time
            print(f"    [{datetime.now().strftime('%H:%M:%S')}] API call FAILED after {elapsed:.2f}s")
            print(f"    Exception type: {type(e).__name__}")
            print(f"    Exception details: {e}")
            raise
    
    def _sanitize_case(self, case: Dict[str, Any]) -> Dict[str, Any]:
        """
        Remove ground truth and internal flags from case before sending to LLM.
        
        The LLM must NEVER see:
        - true_label (ground truth)
        - noise_case (internal flag)
        - noise_type (internal flag)
        - _masked_field (internal debug info)
        """
        sanitized = case.copy()
        
        # Remove ground truth and internal flags
        fields_to_remove = ['true_label', 'noise_case', 'noise_type', '_masked_field']
        for field in fields_to_remove:
            sanitized.pop(field, None)
        
        return sanitized
    
    def _score_to_confidence(self, score: int) -> str:
        """Convert numeric score to confidence level."""
        if score >= 85:
            return "high"
        elif score >= 70:
            return "medium-high"
        elif score >= 45:
            return "medium"
        elif score >= 30:
            return "low-medium"
        else:
            return "low"
    
    def _call_llm(self, user_message: str) -> Dict[str, Any]:
        """
        Call Google Gemini API and parse JSON response.
        
        Args:
            user_message: The formatted case and decision
        
        Returns:
            Parsed JSON response
        """
        # Build the full prompt with system instruction
        full_prompt = f"{self.SYSTEM_PROMPT}\n\n{user_message}"
        
        try:
            # Call Gemini API using new client with Flash-Lite model (higher free tier quota)
            response = self.client.models.generate_content(
                model='gemini-3.5-flash-lite',
                contents=full_prompt,
                config=self.generation_config
            )
            
            # Extract text from response
            response_text = response.text
            
        except Exception as api_error:
            # Log API errors verbatim (rate limits, auth errors, etc.)
            print(f"    API ERROR: {type(api_error).__name__}")
            print(f"    Details: {api_error}")
            
            # Check for rate limit specifically
            error_str = str(api_error)
            if '429' in error_str or 'RESOURCE_EXHAUSTED' in error_str or 'rate limit' in error_str.lower():
                print(f"    ⚠️  RATE LIMIT DETECTED - free tier quota exceeded")
            
            raise
        
        # Parse JSON
        try:
            parsed = json.loads(response_text)
            return parsed
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
                parsed = json.loads(response_text)
                return parsed
            else:
                print(f"    RAW RESPONSE (first 500 chars): {response_text[:500]}")
                raise


def format_evidence_report(
    chargeback_id: str,
    llm_output: Dict[str, Any],
    decision: str,
    score: int
) -> str:
    """
    Format LLM output into human-readable report.
    
    Args:
        chargeback_id: The chargeback identifier
        llm_output: Parsed JSON from LLM
        decision: Rule engine decision
        score: Rule engine score
    
    Returns:
        Formatted report string
    """
    lines = []
    lines.append("="*80)
    lines.append(f"CHARGEBACK EVIDENCE REPORT: {chargeback_id}")
    lines.append("="*80)
    lines.append("")
    
    lines.append("DECISION")
    lines.append("-"*80)
    lines.append(f"Recommendation: {llm_output.get('recommendation', decision)}")
    lines.append(f"Confidence: {llm_output.get('confidence', 'unknown')}")
    lines.append(f"Score: {score}")
    lines.append("")
    
    lines.append("CASE SUMMARY")
    lines.append("-"*80)
    lines.append(llm_output.get('summary', 'No summary provided'))
    lines.append("")
    
    lines.append("EVIDENCE")
    lines.append("-"*80)
    evidence_items = llm_output.get('evidence', [])
    if evidence_items:
        for item in evidence_items:
            claim = item.get('claim', 'Unknown claim')
            source = item.get('source_field', 'unknown')
            value = item.get('value', 'unknown')
            lines.append(f"• {claim}")
            lines.append(f"  Source: {source} = {value}")
    else:
        lines.append("No evidence items listed")
    lines.append("")
    
    lines.append("EVIDENCE GAPS")
    lines.append("-"*80)
    gaps = llm_output.get('gaps', [])
    if gaps:
        for gap in gaps:
            lines.append(f"• {gap}")
    else:
        lines.append("No evidence gaps identified")
    lines.append("")
    
    return "\n".join(lines)


if __name__ == '__main__':
    # Test the evidence writer
    print("Evidence Writer Module")
    print("="*80)
    print()
    print("This module provides LLM-powered evidence summarization.")
    print("The LLM sees only verified evidence and the already-made decision.")
    print("It cannot alter decisions or invent facts.")
    print()
    print("Usage:")
    print("  from evidence_writer import EvidenceWriter")
    print("  writer = EvidenceWriter()")
    print("  summary = writer.write_summary(case, decision, score, fired_rules)")
    print()
    print("Required: GEMINI_API_KEY environment variable")
