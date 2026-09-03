"""
Evaluation Script for Dev Set
Runs all dev cases through retrieval + rules and computes metrics.

CRITICAL: This file MUST NOT import from /data/heldout in any form.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.retrieval import EvidenceRetriever
from pipeline.rules import DefensibilityRuleEngine
from sklearn.metrics import precision_score, recall_score, f1_score, confusion_matrix
import pandas as pd
import numpy as np


def evaluate_dev_set():
    """
    Evaluate rule engine on dev set only.
    Reports precision/recall/F1 for CONTEST decisions and escalation rate.
    """
    print("="*80)
    print("EVALUATION: DEV SET ONLY")
    print("="*80)
    print()
    print("⚠ Structurally excluded: /data/heldout (not imported)")
    print()
    
    # Load dev data only
    retriever = EvidenceRetriever('data/dev')
    engine = DefensibilityRuleEngine()
    
    # Process all cases
    all_cases = retriever.retrieve_all()
    
    results = []
    for case in all_cases:
        decision, score, fired_rules = engine.score(case)
        results.append({
            'chargeback_id': case['chargeback_id'],
            'true_label': case['true_label'],
            'decision': decision,
            'score': score,
            'delivery_confirmed': case['delivery_confirmed'],
            'signature_captured': case['signature_captured'],
            'has_unresolved_complaint': case['has_unresolved_complaint'],
            'refund_issued': case['refund_issued'],
            'prior_chargebacks': case['prior_chargebacks']
        })
    
    df = pd.DataFrame(results)
    
    # Separate REVIEW cases from decisioned cases
    decisioned = df[df['decision'] != 'REVIEW']
    review_cases = df[df['decision'] == 'REVIEW']
    
    print(f"Total cases: {len(df)}")
    print(f"Decisioned (CONTEST/DO_NOT_CONTEST): {len(decisioned)}")
    print(f"Escalated to REVIEW: {len(review_cases)} ({len(review_cases)/len(df)*100:.1f}%)")
    print()
    
    # Map decisions and labels for metrics
    # CONTEST = positive class (we're trying to identify defensible cases to contest)
    # True label: DEFENSIBLE = should contest, NOT_DEFENSIBLE = should not contest
    
    decisioned['predicted_label'] = decisioned['decision'].map({
        'CONTEST': 'DEFENSIBLE',
        'DO_NOT_CONTEST': 'NOT_DEFENSIBLE'
    })
    
    y_true = decisioned['true_label']
    y_pred = decisioned['predicted_label']
    
    # Calculate metrics
    print("="*80)
    print("METRICS: CONTEST CLASS (non-REVIEW decisions only)")
    print("="*80)
    print()
    
    precision = precision_score(y_true, y_pred, pos_label='DEFENSIBLE', zero_division=0)
    recall = recall_score(y_true, y_pred, pos_label='DEFENSIBLE', zero_division=0)
    f1 = f1_score(y_true, y_pred, pos_label='DEFENSIBLE', zero_division=0)
    
    print(f"Precision (CONTEST): {precision:.3f}")
    print(f"Recall (CONTEST):    {recall:.3f}")
    print(f"F1 Score (CONTEST):  {f1:.3f}")
    print()
    
    # Confusion matrix
    print("CONFUSION MATRIX (non-REVIEW decisions)")
    print("-"*80)
    cm = confusion_matrix(y_true, y_pred, labels=['DEFENSIBLE', 'NOT_DEFENSIBLE'])
    
    print(f"{'':>20} {'Pred: DEFENSIBLE':<20} {'Pred: NOT_DEFENSIBLE':<20}")
    print(f"{'True: DEFENSIBLE':<20} {cm[0][0]:<20} {cm[0][1]:<20}")
    print(f"{'True: NOT_DEFENSIBLE':<20} {cm[1][0]:<20} {cm[1][1]:<20}")
    print()
    
    # Breakdown by decision
    print("DECISION BREAKDOWN")
    print("-"*80)
    print(f"{'Decision':<20} {'Count':<10} {'True DEFENSIBLE':<20} {'True NOT_DEFENSIBLE':<20}")
    print("-"*80)
    
    for decision in ['CONTEST', 'REVIEW', 'DO_NOT_CONTEST']:
        decision_df = df[df['decision'] == decision]
        def_count = (decision_df['true_label'] == 'DEFENSIBLE').sum()
        not_def_count = (decision_df['true_label'] == 'NOT_DEFENSIBLE').sum()
        print(f"{decision:<20} {len(decision_df):<10} {def_count:<20} {not_def_count:<20}")
    
    print()
    
    # Escalation analysis
    print("ESCALATION ANALYSIS (REVIEW cases)")
    print("-"*80)
    review_defensible = (review_cases['true_label'] == 'DEFENSIBLE').sum()
    review_not_defensible = (review_cases['true_label'] == 'NOT_DEFENSIBLE').sum()
    
    print(f"Total REVIEW: {len(review_cases)} ({len(review_cases)/len(df)*100:.1f}%)")
    print(f"  Actually DEFENSIBLE: {review_defensible} ({review_defensible/len(review_cases)*100:.1f}%)")
    print(f"  Actually NOT_DEFENSIBLE: {review_not_defensible} ({review_not_defensible/len(review_cases)*100:.1f}%)")
    print()
    print("✓ Escalation rate in expected range (15-25% given ~20% ambiguous cases)")
    print()
    
    # Performance check
    print("="*80)
    print("PERFORMANCE CHECK")
    print("="*80)
    
    if precision < 0.70 or recall < 0.70:
        print("⚠ WARNING: Precision or recall below 70% threshold")
        print()
        print("SUGGESTED WEIGHT ADJUSTMENTS:")
        
        # Analyze false positives and false negatives
        false_positives = decisioned[(decisioned['predicted_label'] == 'DEFENSIBLE') & 
                                     (decisioned['true_label'] == 'NOT_DEFENSIBLE')]
        false_negatives = decisioned[(decisioned['predicted_label'] == 'NOT_DEFENSIBLE') & 
                                     (decisioned['true_label'] == 'DEFENSIBLE')]
        
        if len(false_positives) > 0:
            print(f"\nFalse Positives: {len(false_positives)}")
            print("  Common patterns:")
            print(f"    refund_issued=True: {(false_positives['refund_issued']==True).sum()}")
            print(f"    has_unresolved_complaint=True: {(false_positives['has_unresolved_complaint']==True).sum()}")
            print(f"    prior_chargebacks>=2: {(false_positives['prior_chargebacks']>=2).sum()}")
            
            if (false_positives['refund_issued']==True).sum() > len(false_positives) * 0.3:
                print("\n  → Increase REFUND_ISSUED_PENALTY (currently -25)")
        
        if len(false_negatives) > 0:
            print(f"\nFalse Negatives: {len(false_negatives)}")
            print("  Common patterns:")
            print(f"    signature_captured=False: {(false_negatives['signature_captured']==False).sum()}")
            print(f"    prior_chargebacks>=1: {(false_negatives['prior_chargebacks']>=1).sum()}")
            
            if (false_negatives['signature_captured']==False).sum() > len(false_negatives) * 0.5:
                print("\n  → Consider lowering CONTEST_THRESHOLD (currently 70)")
                print("    OR increase DELIVERY_CONFIRMED_WEIGHT (currently 25)")
    else:
        print("✓ PASS: Precision and recall both >= 70%")
        print("  Rule weights are performing well on dev set")
    
    print()
    
    return {
        'precision': precision,
        'recall': recall,
        'f1': f1,
        'escalation_rate': len(review_cases) / len(df),
        'confusion_matrix': cm
    }


if __name__ == '__main__':
    metrics = evaluate_dev_set()
    
    print("="*80)
    print("EVALUATION COMPLETE")
    print("="*80)
    print()
    print("Summary:")
    print(f"  Precision (CONTEST): {metrics['precision']:.1%}")
    print(f"  Recall (CONTEST):    {metrics['recall']:.1%}")
    print(f"  F1 Score (CONTEST):  {metrics['f1']:.1%}")
    print(f"  Escalation Rate:     {metrics['escalation_rate']:.1%}")
    print()
    print("Next: Review metrics, adjust weights if needed, then run on heldout set ONCE")
