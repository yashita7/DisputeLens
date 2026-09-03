"""
Evaluation Script for Heldout Set
Runs all heldout cases through retrieval + rules and computes metrics.

CRITICAL: Run EXACTLY ONCE. No tuning afterward. Final reported metrics.
"""

import sys
import os
import json
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.retrieval import EvidenceRetriever
from pipeline.rules import DefensibilityRuleEngine
from sklearn.metrics import precision_score, recall_score, f1_score, confusion_matrix
import pandas as pd
import numpy as np


def evaluate_heldout_set():
    """
    Evaluate rule engine on heldout set.
    Reports precision/recall/F1 for CONTEST decisions and escalation rate.
    
    ZERO GEMINI API CALLS - only uses retrieval.py and rules.py
    """
    print("="*80)
    print("EVALUATION: HELDOUT SET (FINAL)")
    print("="*80)
    print()
    print("⚠ This script runs EXACTLY ONCE - no tuning afterward")
    print("⚠ Zero Gemini API calls - deterministic rule engine only")
    print()
    
    # Load heldout data
    retriever = EvidenceRetriever('data/heldout')
    engine = DefensibilityRuleEngine()
    
    # Process all cases
    all_cases = retriever.retrieve_all()
    
    print(f"Processing {len(all_cases)} heldout cases...")
    print()
    
    results = []
    for case in all_cases:
        decision, score, fired_rules = engine.score(case)
        results.append({
            'chargeback_id': case['chargeback_id'],
            'true_label': case['true_label'],
            'decision': decision,
            'score': score,
            'fired_rules': fired_rules,
            'delivery_confirmed': case['delivery_confirmed'],
            'signature_captured': case['signature_captured'],
            'has_unresolved_complaint': case['has_unresolved_complaint'],
            'refund_issued': case['refund_issued'],
            'prior_chargebacks': case['prior_chargebacks'],
            'noise_case': case.get('noise_case', False),
            'noise_type': case.get('noise_type', None),
            # Track masked fields for analysis
            'has_gaps': any(
                case.get(field) == 'not_available' 
                for field in ['delivery_confirmed', 'signature_captured', 
                             'has_unresolved_complaint', 'refund_issued']
            )
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
    
    decision_breakdown = {}
    for decision in ['CONTEST', 'REVIEW', 'DO_NOT_CONTEST']:
        decision_df = df[df['decision'] == decision]
        def_count = (decision_df['true_label'] == 'DEFENSIBLE').sum()
        not_def_count = (decision_df['true_label'] == 'NOT_DEFENSIBLE').sum()
        print(f"{decision:<20} {len(decision_df):<10} {def_count:<20} {not_def_count:<20}")
        decision_breakdown[decision] = {
            'count': int(len(decision_df)),
            'true_defensible': int(def_count),
            'true_not_defensible': int(not_def_count)
        }
    
    print()
    
    # Masking impact analysis
    print("EVIDENCE MASKING IMPACT")
    print("-"*80)
    masked_cases = df[df['has_gaps'] == True]
    unmasked_cases = df[df['has_gaps'] == False]
    
    print(f"Masked cases: {len(masked_cases)} ({len(masked_cases)/len(df)*100:.1f}%)")
    print(f"Unmasked cases: {len(unmasked_cases)} ({len(unmasked_cases)/len(df)*100:.1f}%)")
    print()
    
    # Metrics by masking status
    masking_breakdown = {}
    for label, subset in [('Masked', masked_cases), ('Unmasked', unmasked_cases)]:
        subset_decisioned = subset[subset['decision'] != 'REVIEW']
        if len(subset_decisioned) > 0:
            y_true_subset = subset_decisioned['true_label']
            y_pred_subset = subset_decisioned['decision'].map({
                'CONTEST': 'DEFENSIBLE',
                'DO_NOT_CONTEST': 'NOT_DEFENSIBLE'
            })
            
            p = precision_score(y_true_subset, y_pred_subset, pos_label='DEFENSIBLE', zero_division=0)
            r = recall_score(y_true_subset, y_pred_subset, pos_label='DEFENSIBLE', zero_division=0)
            f = f1_score(y_true_subset, y_pred_subset, pos_label='DEFENSIBLE', zero_division=0)
            esc_rate = len(subset[subset['decision'] == 'REVIEW']) / len(subset)
            
            print(f"{label} - P: {p:.3f}, R: {r:.3f}, F1: {f:.3f}, Escalation: {esc_rate:.1%}")
            
            masking_breakdown[label.lower()] = {
                'precision': float(p),
                'recall': float(r),
                'f1': float(f),
                'escalation_rate': float(esc_rate),
                'total_cases': int(len(subset))
            }
    
    print()
    
    # Noise case analysis
    print("LABEL NOISE IMPACT")
    print("-"*80)
    noise_cases = df[df['noise_case'] == True]
    regular_cases = df[df['noise_case'] == False]
    
    print(f"Noise cases: {len(noise_cases)} ({len(noise_cases)/len(df)*100:.1f}%)")
    print(f"Regular cases: {len(regular_cases)} ({len(regular_cases)/len(df)*100:.1f}%)")
    print()
    
    noise_breakdown = {}
    for label, subset in [('Noise', noise_cases), ('Regular', regular_cases)]:
        subset_decisioned = subset[subset['decision'] != 'REVIEW']
        if len(subset_decisioned) > 0:
            y_true_subset = subset_decisioned['true_label']
            y_pred_subset = subset_decisioned['decision'].map({
                'CONTEST': 'DEFENSIBLE',
                'DO_NOT_CONTEST': 'NOT_DEFENSIBLE'
            })
            
            p = precision_score(y_true_subset, y_pred_subset, pos_label='DEFENSIBLE', zero_division=0)
            r = recall_score(y_true_subset, y_pred_subset, pos_label='DEFENSIBLE', zero_division=0)
            f = f1_score(y_true_subset, y_pred_subset, pos_label='DEFENSIBLE', zero_division=0)
            
            print(f"{label} - P: {p:.3f}, R: {r:.3f}, F1: {f:.3f}")
            
            noise_breakdown[label.lower()] = {
                'precision': float(p),
                'recall': float(r),
                'f1': float(f),
                'total_cases': int(len(subset))
            }
    
    print()
    
    # Escalation analysis
    print("ESCALATION ANALYSIS (REVIEW cases)")
    print("-"*80)
    review_defensible = (review_cases['true_label'] == 'DEFENSIBLE').sum()
    review_not_defensible = (review_cases['true_label'] == 'NOT_DEFENSIBLE').sum()
    
    print(f"Total REVIEW: {len(review_cases)} ({len(review_cases)/len(df)*100:.1f}%)")
    print(f"  Actually DEFENSIBLE: {review_defensible} ({review_defensible/len(review_cases)*100:.1f}% if len(review_cases) > 0 else 0)")
    print(f"  Actually NOT_DEFENSIBLE: {review_not_defensible} ({review_not_defensible/len(review_cases)*100:.1f}% if len(review_cases) > 0 else 0)")
    print()
    
    # Prepare output
    output = {
        'evaluated_at': datetime.now().isoformat(),
        'dataset': 'heldout',
        'total_cases': int(len(df)),
        'decisioned_cases': int(len(decisioned)),
        'review_cases': int(len(review_cases)),
        'metrics': {
            'precision': float(precision),
            'recall': float(recall),
            'f1': float(f1),
            'escalation_rate': float(len(review_cases) / len(df))
        },
        'confusion_matrix': {
            'true_positive': int(cm[0][0]),
            'false_negative': int(cm[0][1]),
            'false_positive': int(cm[1][0]),
            'true_negative': int(cm[1][1])
        },
        'decision_breakdown': decision_breakdown,
        'masking_breakdown': masking_breakdown,
        'noise_breakdown': noise_breakdown,
        'review_breakdown': {
            'total': int(len(review_cases)),
            'actually_defensible': int(review_defensible),
            'actually_not_defensible': int(review_not_defensible)
        },
        'note': 'Evaluated ONCE on heldout set. No tuning performed after this run.'
    }
    
    return output, df


if __name__ == '__main__':
    print()
    print("⚠️  WARNING: This script should only be run ONCE")
    print("⚠️  Results will be saved to eval/heldout_results.json")
    print()
    
    results, df = evaluate_heldout_set()
    
    # Save results
    output_file = 'eval/heldout_results.json'
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print("="*80)
    print("HELDOUT EVALUATION COMPLETE")
    print("="*80)
    print()
    print("Summary:")
    print(f"  Precision (CONTEST): {results['metrics']['precision']:.1%}")
    print(f"  Recall (CONTEST):    {results['metrics']['recall']:.1%}")
    print(f"  F1 Score (CONTEST):  {results['metrics']['f1']:.1%}")
    print(f"  Escalation Rate:     {results['metrics']['escalation_rate']:.1%}")
    print()
    print(f"Results saved to: {output_file}")
    print()
    print("⚠️  DO NOT re-run this script or tune thresholds based on these numbers")
    print("⚠️  These are the final reported heldout metrics")
