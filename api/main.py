"""
DisputeLens API - FastAPI backend for chargeback evidence system
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from typing import List, Dict, Any, Optional
import sys
import os
import math
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.retrieval import EvidenceRetriever
from pipeline.rules import DefensibilityRuleEngine
from pipeline.evidence_writer import EvidenceWriter
import pandas as pd


def sanitize_for_json(obj):
    """Convert NaN and inf values to None for JSON serialization."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    elif isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(item) for item in obj]
    return obj

app = FastAPI(title="DisputeLens API", version="1.0.0")

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize components
retriever = EvidenceRetriever('data/dev')
engine = DefensibilityRuleEngine()

# Check for GEMINI_API_KEY at startup
gemini_api_key = os.environ.get('GEMINI_API_KEY')
if not gemini_api_key:
    print("=" * 80)
    print("⚠️  WARNING: GEMINI_API_KEY not found!")
    print("=" * 80)
    print("LLM summaries will be disabled.")
    print("To enable LLM summaries:")
    print("  1. Set GEMINI_API_KEY in .env file")
    print("  2. Or export GEMINI_API_KEY='your-key' before starting the server")
    print("=" * 80)
    llm_enabled = False
    writer = None
else:
    print("=" * 80)
    print("✓ GEMINI_API_KEY loaded successfully")
    print(f"  Key prefix: {gemini_api_key[:15]}...")
    print("=" * 80)
    # Try to initialize LLM writer (graceful fallback if initialization fails)
    try:
        writer = EvidenceWriter()
        llm_enabled = True
        print("✓ EvidenceWriter initialized successfully")
    except Exception as e:
        print(f"⚠️  Warning: EvidenceWriter initialization failed: {e}")
        writer = None
        llm_enabled = False
    print("=" * 80)

# Load precomputed summaries (if available)
PRECOMPUTED_SUMMARIES_FILE = 'data/dev/llm_summaries.json'
precomputed_summaries = {}

if os.path.exists(PRECOMPUTED_SUMMARIES_FILE):
    try:
        with open(PRECOMPUTED_SUMMARIES_FILE, 'r') as f:
            data = json.load(f)
            precomputed_summaries = data.get('summaries', {})
        print("=" * 80)
        print(f"✓ Loaded {len(precomputed_summaries)} precomputed summaries")
        print(f"  From: {PRECOMPUTED_SUMMARIES_FILE}")
        print("  API will serve precomputed summaries (no live Gemini calls)")
        print("=" * 80)
    except Exception as e:
        print(f"⚠️  Warning: Failed to load precomputed summaries: {e}")
        precomputed_summaries = {}
else:
    if llm_enabled:
        print("=" * 80)
        print("⚠️  No precomputed summaries found")
        print(f"  Expected at: {PRECOMPUTED_SUMMARIES_FILE}")
        print("  API will call Gemini live (may be slow and hit rate limits)")
        print("  Run: python3 precompute_summaries.py")
        print("=" * 80)


def build_audit_trail(chargeback_id: str, retrieval_time: float, rules_time: float, llm_time: Optional[float]) -> List[Dict]:
    """Build audit trail with timestamps for each pipeline stage."""
    now = datetime.now()
    trail = [
        {
            "step": "retrieval",
            "timestamp": now.isoformat(),
            "detail": f"Retrieved evidence from 6 tables in {retrieval_time*1000:.0f}ms"
        },
        {
            "step": "rule_evaluation",
            "timestamp": now.isoformat(),
            "detail": f"Evaluated rule engine in {rules_time*1000:.0f}ms"
        }
    ]
    
    if llm_time is not None:
        trail.append({
            "step": "llm_generation",
            "timestamp": now.isoformat(),
            "detail": f"Generated LLM summary in {llm_time*1000:.0f}ms"
        })
    
    return trail


def format_evidence_items(case: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Format evidence items with gap detection.
    Distinguishes between directly masked fields and their dependent fields.
    """
    items = []
    
    # Define which fields are dependent on others
    dependent_fields = {
        'delivered_at': 'delivery_confirmed'
    }
    
    # Key evidence fields to display
    evidence_fields = [
        ('payment_confirmed', 'Payment Confirmed'),
        ('delivery_confirmed', 'Delivery Confirmed'),
        ('delivered_at', 'Delivered At'),
        ('signature_captured', 'Signature Captured'),
        ('has_unresolved_complaint', 'Has Unresolved Complaint'),
        ('refund_issued', 'Refund Issued'),
        ('prior_chargebacks', 'Prior Chargebacks'),
        ('account_age_days', 'Account Age (Days)'),
        ('transaction_amount', 'Transaction Amount'),
        ('chargeback_amount', 'Chargeback Amount'),
    ]
    
    for field_name, display_name in evidence_fields:
        value = case.get(field_name)
        
        is_gap = value == 'not_available' or (isinstance(value, float) and pd.isna(value))
        
        # Check if this is a dependent field that was masked due to parent masking
        is_dependent_gap = False
        if is_gap and field_name in dependent_fields:
            parent_field = dependent_fields[field_name]
            parent_value = case.get(parent_field)
            if parent_value == 'not_available':
                is_dependent_gap = True
        
        items.append({
            "field": field_name,
            "label": display_name,
            "value": str(value) if not is_gap else "not_available",
            "is_gap": is_gap,
            "is_dependent_gap": is_dependent_gap,
            "source_field": field_name
        })
    
    return items


@app.get("/")
def root():
    """API health check."""
    return {
        "service": "DisputeLens API",
        "status": "running",
        "llm_enabled": llm_enabled
    }


@app.get("/chargebacks")
def list_chargebacks():
    """List all dev-set cases with id, amount, decision, confidence."""
    import time
    
    all_cases = retriever.retrieve_all()
    
    results = []
    for case in all_cases:
        start = time.time()
        decision, score, _ = engine.score(case)
        elapsed = time.time() - start
        
        # Determine confidence level
        if score >= 85:
            confidence = "high"
        elif score >= 70:
            confidence = "medium-high"
        elif score >= 45:
            confidence = "medium"
        elif score >= 30:
            confidence = "low-medium"
        else:
            confidence = "low"
        
        # Check if case has gaps
        has_gaps = '_masked_field' in case
        
        results.append({
            "id": case['chargeback_id'],
            "amount": float(case['chargeback_amount']),
            "decision": decision,
            "confidence": confidence,
            "score": score,
            "has_gaps": has_gaps,
            "is_noise_case": case.get('noise_case', False)
        })
    
    return {"chargebacks": results, "total": len(results)}


@app.get("/chargebacks/{chargeback_id}")
def get_chargeback_detail(chargeback_id: str):
    """Get full case detail with evidence, LLM summary, decision, audit trail."""
    import time
    
    # Retrieval
    start = time.time()
    try:
        case = retriever.retrieve(chargeback_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    retrieval_time = time.time() - start
    
    # Rule evaluation
    start = time.time()
    decision, score, fired_rules = engine.score(case)
    rules_time = time.time() - start
    
    # Confidence level
    if score >= 85:
        confidence = "high"
    elif score >= 70:
        confidence = "medium-high"
    elif score >= 45:
        confidence = "medium"
    elif score >= 30:
        confidence = "low-medium"
    else:
        confidence = "low"
    
    # Format evidence items
    evidence_items = format_evidence_items(case)
    
    # Identify gaps
    gaps = [item for item in evidence_items if item['is_gap']]
    
    # LLM summary - try precomputed first, fallback to live generation
    llm_summary = None
    llm_time = None
    
    # Check precomputed summaries first
    if chargeback_id in precomputed_summaries:
        llm_summary = precomputed_summaries[chargeback_id]
        llm_time = llm_summary.get('generation_time_ms', 0) / 1000  # Convert ms to seconds
    elif llm_enabled and writer:
        # Fallback to live generation if precomputed not available
        start = time.time()
        try:
            llm_output = writer.write_summary(case, decision, score, fired_rules)
            llm_summary = llm_output
            llm_time = time.time() - start
        except Exception as e:
            print(f"LLM error: {e}")
            llm_summary = {"error": str(e)}
            llm_time = time.time() - start
    
    # Build audit trail
    audit_trail = build_audit_trail(chargeback_id, retrieval_time, rules_time, llm_time)
    
    result = {
        "chargeback_id": chargeback_id,
        "transaction_id": case['transaction_id'],
        "customer_id": case['customer_id'],
        "amount": float(case['chargeback_amount']),
        "reason_code": case['reason_code'],
        "decision": decision,
        "confidence": confidence,
        "score": score,
        "evidence": evidence_items,
        "gaps": gaps,
        "fired_rules": fired_rules,
        "llm_summary": llm_summary,
        "audit_trail": audit_trail,
        "metadata": {
            "has_gaps": '_masked_field' in case,
            "masked_field": case.get('_masked_field'),
            "is_noise_case": case.get('noise_case', False),
            "noise_type": case.get('noise_type'),
            "true_label": case.get('true_label')  # For evaluation only
        }
    }
    
    # Sanitize NaN values
    return sanitize_for_json(result)


@app.get("/metrics")
def get_metrics():
    """Get precision/recall/F1, confusion matrix, cost estimates, masked/noise breakdowns."""
    import time
    
    # Run evaluation on dev set
    all_cases = retriever.retrieve_all()
    
    # Initialize counters
    tp = fp = tn = fn = 0
    escalated = 0
    
    # Breakdown by category
    masked_stats = {'tp': 0, 'fp': 0, 'tn': 0, 'fn': 0, 'total': 0}
    unmasked_stats = {'tp': 0, 'fp': 0, 'tn': 0, 'fn': 0, 'total': 0}
    noise_stats = {'tp': 0, 'fp': 0, 'tn': 0, 'fn': 0, 'total': 0}
    regular_stats = {'tp': 0, 'fp': 0, 'tn': 0, 'fn': 0, 'total': 0}
    
    for case in all_cases:
        decision, score, _ = engine.score(case)
        true_label = case['true_label']
        
        # Skip REVIEW for precision/recall (escalated to human)
        if decision == 'REVIEW':
            escalated += 1
            continue
        
        # Determine if prediction matches ground truth
        predicted_defensible = (decision == 'CONTEST')
        actually_defensible = (true_label == 'DEFENSIBLE')
        
        # Update confusion matrix
        if predicted_defensible and actually_defensible:
            tp += 1
            category_tp = True
        elif predicted_defensible and not actually_defensible:
            fp += 1
            category_tp = False
        elif not predicted_defensible and not actually_defensible:
            tn += 1
            category_tp = None
        else:  # not predicted_defensible and actually_defensible
            fn += 1
            category_tp = None
        
        # Update category breakdowns
        is_masked = '_masked_field' in case
        is_noise = case.get('noise_case', False)
        
        if is_masked:
            masked_stats['total'] += 1
            if category_tp is True:
                masked_stats['tp'] += 1
            elif category_tp is False:
                masked_stats['fp'] += 1
            elif fn > 0 and category_tp is None and actually_defensible:
                masked_stats['fn'] += 1
            elif tn > 0 and category_tp is None:
                masked_stats['tn'] += 1
        else:
            unmasked_stats['total'] += 1
            if category_tp is True:
                unmasked_stats['tp'] += 1
            elif category_tp is False:
                unmasked_stats['fp'] += 1
            elif fn > 0 and category_tp is None and actually_defensible:
                unmasked_stats['fn'] += 1
            elif tn > 0 and category_tp is None:
                unmasked_stats['tn'] += 1
        
        if is_noise:
            noise_stats['total'] += 1
            if category_tp is True:
                noise_stats['tp'] += 1
            elif category_tp is False:
                noise_stats['fp'] += 1
            elif fn > 0 and category_tp is None and actually_defensible:
                noise_stats['fn'] += 1
            elif tn > 0 and category_tp is None:
                noise_stats['tn'] += 1
        else:
            regular_stats['total'] += 1
            if category_tp is True:
                regular_stats['tp'] += 1
            elif category_tp is False:
                regular_stats['fp'] += 1
            elif fn > 0 and category_tp is None and actually_defensible:
                regular_stats['fn'] += 1
            elif tn > 0 and category_tp is None:
                regular_stats['tn'] += 1
    
    # Calculate metrics
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    
    escalation_rate = escalated / len(all_cases)
    
    # Cost estimates (example values)
    avg_chargeback_amount = sum(c['chargeback_amount'] for c in all_cases) / len(all_cases)
    fp_cost = fp * avg_chargeback_amount  # False contest -> lose money
    fn_cost = fn * avg_chargeback_amount * 0.3  # False do-not-contest -> lose 30% in potential recovery
    
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(f1, 4),
        "confusion_matrix": {
            "true_positive": tp,
            "false_positive": fp,
            "true_negative": tn,
            "false_negative": fn
        },
        "escalation_rate": round(escalation_rate, 4),
        "escalated_count": escalated,
        "total_cases": len(all_cases),
        "cost_estimates": {
            "false_positive_cost": round(fp_cost, 2),
            "false_negative_cost": round(fn_cost, 2),
            "total_estimated_cost": round(fp_cost + fn_cost, 2),
            "avg_chargeback_amount": round(avg_chargeback_amount, 2)
        },
        "breakdown": {
            "masked_cases": {
                "total": masked_stats['total'],
                "precision": round(masked_stats['tp'] / (masked_stats['tp'] + masked_stats['fp']), 4) if (masked_stats['tp'] + masked_stats['fp']) > 0 else 0,
                "recall": round(masked_stats['tp'] / (masked_stats['tp'] + masked_stats['fn']), 4) if (masked_stats['tp'] + masked_stats['fn']) > 0 else 0
            },
            "unmasked_cases": {
                "total": unmasked_stats['total'],
                "precision": round(unmasked_stats['tp'] / (unmasked_stats['tp'] + unmasked_stats['fp']), 4) if (unmasked_stats['tp'] + unmasked_stats['fp']) > 0 else 0,
                "recall": round(unmasked_stats['tp'] / (unmasked_stats['tp'] + unmasked_stats['fn']), 4) if (unmasked_stats['tp'] + unmasked_stats['fn']) > 0 else 0
            },
            "noise_cases": {
                "total": noise_stats['total'],
                "precision": round(noise_stats['tp'] / (noise_stats['tp'] + noise_stats['fp']), 4) if (noise_stats['tp'] + noise_stats['fp']) > 0 else 0,
                "recall": round(noise_stats['tp'] / (noise_stats['tp'] + noise_stats['fn']), 4) if (noise_stats['tp'] + noise_stats['fn']) > 0 else 0
            },
            "regular_cases": {
                "total": regular_stats['total'],
                "precision": round(regular_stats['tp'] / (regular_stats['tp'] + regular_stats['fp']), 4) if (regular_stats['tp'] + regular_stats['fp']) > 0 else 0,
                "recall": round(regular_stats['tp'] / (regular_stats['tp'] + regular_stats['fn']), 4) if (regular_stats['tp'] + regular_stats['fn']) > 0 else 0
            }
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
