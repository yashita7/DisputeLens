"""
DisputeLens Synthetic Data Generator
Generates 6 correlated tables for chargeback evidence system testing.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random
import os

# Set random seeds for reproducibility
np.random.seed(42)
random.seed(42)

# Configuration
TOTAL_CHARGEBACKS = 1000
DEV_SPLIT = 0.7  # 700 dev, 300 heldout
AMBIGUOUS_RATE = 0.18  # 15-20% ambiguous cases (tightened from ~30%)

# Reason codes for chargebacks
REASON_CODES = [
    "fraudulent_transaction",
    "product_not_received",
    "product_not_as_described",
    "duplicate_charge",
    "cancelled_subscription",
    "unauthorized_transaction"
]

PRODUCT_CATEGORIES = [
    "electronics", "clothing", "books", "home_goods", 
    "software", "subscription", "gaming", "food_delivery"
]

PAYMENT_METHODS = ["credit_card", "debit_card", "upi", "netbanking", "wallet"]
CHANNELS = ["email", "phone", "chat", "support_ticket"]

def generate_correlated_data():
    """Generate all 6 tables with realistic correlations."""
    
    print("Generating correlated synthetic data...")
    print(f"Total chargebacks: {TOTAL_CHARGEBACKS}")
    print(f"Dev split: {int(TOTAL_CHARGEBACKS * DEV_SPLIT)} | Heldout: {int(TOTAL_CHARGEBACKS * (1-DEV_SPLIT))}")
    print()
    
    # Step 1: Generate customers first (base layer)
    num_customers = int(TOTAL_CHARGEBACKS * 0.6)  # Multiple chargebacks per customer possible
    customers_data = []
    
    for i in range(num_customers):
        # Create customer profiles with varying risk levels
        account_age_days = np.random.choice([
            np.random.randint(7, 90),      # 30% new accounts
            np.random.randint(90, 365),    # 40% medium age
            np.random.randint(365, 1825)   # 30% old accounts
        ], p=[0.3, 0.4, 0.3])
        
        prior_orders = min(int(account_age_days / 30) + np.random.poisson(2), 50)
        prior_chargebacks = np.random.choice([0, 1, 2, 3, 4], p=[0.7, 0.15, 0.08, 0.05, 0.02])
        prior_refunds = np.random.choice([0, 1, 2, 3], p=[0.5, 0.3, 0.15, 0.05])
        
        customers_data.append({
            'customer_id': f'CUST_{i:06d}',
            'account_age_days': account_age_days,
            'prior_orders': prior_orders,
            'prior_chargebacks': prior_chargebacks,
            'prior_refunds': prior_refunds
        })
    
    customers_df = pd.DataFrame(customers_data)
    
    # Step 2: Generate transactions and chargebacks with correlated labels
    transactions_data = []
    orders_data = []
    fulfillment_data = []
    communications_data = []
    chargebacks_data = []
    
    for cb_idx in range(TOTAL_CHARGEBACKS):
        transaction_id = f'TXN_{cb_idx:08d}'
        order_id = f'ORD_{cb_idx:08d}'
        chargeback_id = f'CB_{cb_idx:08d}'
        
        # Select customer (some repeat customers)
        customer = customers_df.sample(1).iloc[0]
        customer_id = customer['customer_id']
        
        # Transaction details
        amount = round(np.random.lognormal(7, 1.5), 2)  # Mean ~1100, varied distribution
        payment_method = random.choice(PAYMENT_METHODS)
        product_category = random.choice(PRODUCT_CATEGORIES)
        
        # Transaction timestamp (past 6 months)
        days_ago = np.random.randint(30, 180)
        transaction_ts = datetime.now() - timedelta(days=days_ago)
        
        # Decide case type: DEFENSIBLE, NOT_DEFENSIBLE, or AMBIGUOUS
        case_type = np.random.choice(
            ['DEFENSIBLE', 'NOT_DEFENSIBLE', 'AMBIGUOUS'],
            p=[0.47, 0.35, AMBIGUOUS_RATE]  # Adjusted to hit 15-20% ambiguous
        )
        
        # Generate correlated evidence based on case type
        if case_type == 'DEFENSIBLE':
            # Clear defensible case
            order_status = 'completed'
            delivery_confirmed = True
            signature_captured = np.random.choice([True, False], p=[0.8, 0.2])
            refund_issued = False
            has_unresolved_complaint = False  # Key: no unresolved non-delivery complaints
            
            shipped_at = transaction_ts + timedelta(days=np.random.randint(1, 3))
            delivered_at = shipped_at + timedelta(days=np.random.randint(2, 7))
            
            # DEFENSIBLE cases may have benign communication (tracking inquiries, delivery confirmations)
            # but NOT unresolved non-delivery complaints
            has_benign_communication = np.random.choice([True, False], p=[0.3, 0.7])
            
            true_label = 'DEFENSIBLE'
            
        elif case_type == 'NOT_DEFENSIBLE':
            # Clear non-defensible case
            scenario = random.choice(['no_delivery', 'refund_issued', 'unresolved_complaint'])
            
            if scenario == 'no_delivery':
                order_status = random.choice(['shipped', 'processing', 'cancelled'])
                delivery_confirmed = False
                signature_captured = False
                refund_issued = False
                has_unresolved_complaint = True  # Customer complained, never got item
                has_benign_communication = False
                
                shipped_at = transaction_ts + timedelta(days=np.random.randint(1, 5)) if order_status == 'shipped' else None
                delivered_at = None
                
            elif scenario == 'refund_issued':
                order_status = random.choice(['refunded', 'cancelled'])
                delivery_confirmed = np.random.choice([True, False], p=[0.3, 0.7])
                signature_captured = False
                refund_issued = True
                has_unresolved_complaint = False  # Complaint was resolved with refund
                has_benign_communication = True  # Had communication about refund
                
                shipped_at = transaction_ts + timedelta(days=np.random.randint(1, 3))
                delivered_at = shipped_at + timedelta(days=np.random.randint(2, 7)) if delivery_confirmed else None
                
            else:  # unresolved_complaint
                order_status = random.choice(['completed', 'shipped', 'processing'])
                delivery_confirmed = False  # Key: complaint about non-delivery
                signature_captured = False
                refund_issued = False
                has_unresolved_complaint = True  # Complained, no resolution
                has_benign_communication = False
                
                shipped_at = transaction_ts + timedelta(days=np.random.randint(1, 5))
                delivered_at = None
            
            true_label = 'NOT_DEFENSIBLE'
            
        else:  # AMBIGUOUS
            # Partial evidence - could go either way
            scenario = random.choice([
                'delivered_no_signature',
                'late_delivery',
                'quality_complaint'
            ])
            
            if scenario == 'delivered_no_signature':
                order_status = 'completed'
                delivery_confirmed = True
                signature_captured = False  # Key ambiguity
                refund_issued = False
                has_unresolved_complaint = False
                has_benign_communication = np.random.choice([True, False], p=[0.4, 0.6])
                
                shipped_at = transaction_ts + timedelta(days=np.random.randint(1, 4))
                delivered_at = shipped_at + timedelta(days=np.random.randint(2, 8))
                
            elif scenario == 'late_delivery':
                order_status = 'completed'
                delivery_confirmed = True
                signature_captured = np.random.choice([True, False], p=[0.5, 0.5])
                refund_issued = False
                has_unresolved_complaint = False  # Complained about lateness, not non-delivery
                has_benign_communication = True  # Inquiry about delay
                
                shipped_at = transaction_ts + timedelta(days=np.random.randint(5, 10))
                delivered_at = shipped_at + timedelta(days=np.random.randint(8, 15))  # Very late
                
            else:  # quality_complaint
                order_status = 'completed'
                delivery_confirmed = True
                signature_captured = True
                refund_issued = False
                has_unresolved_complaint = False  # Complaint is about quality, not delivery
                has_benign_communication = True  # Quality issue communication
                
                shipped_at = transaction_ts + timedelta(days=np.random.randint(1, 3))
                delivered_at = shipped_at + timedelta(days=np.random.randint(2, 6))
            
            # Ambiguous cases labeled based on preponderance of evidence
            evidence_score = 0
            if delivery_confirmed: evidence_score += 3
            if signature_captured: evidence_score += 2
            if not refund_issued: evidence_score += 2
            if not has_unresolved_complaint: evidence_score += 2
            
            true_label = 'DEFENSIBLE' if evidence_score >= 6 else 'NOT_DEFENSIBLE'
        
        # Store transaction
        transactions_data.append({
            'transaction_id': transaction_id,
            'customer_id': customer_id,
            'merchant_id': f'MERCH_{np.random.randint(0, 50):04d}',
            'amount': amount,
            'payment_method': payment_method,
            'timestamp': transaction_ts.strftime('%Y-%m-%d %H:%M:%S')
        })
        
        # Store order
        orders_data.append({
            'order_id': order_id,
            'transaction_id': transaction_id,
            'status': order_status,
            'product_category': product_category
        })
        
        # Store fulfillment
        fulfillment_data.append({
            'order_id': order_id,
            'shipped_at': shipped_at.strftime('%Y-%m-%d %H:%M:%S') if shipped_at else None,
            'delivered_at': delivered_at.strftime('%Y-%m-%d %H:%M:%S') if delivered_at else None,
            'delivery_confirmed': delivery_confirmed,
            'signature_captured': signature_captured
        })
        
        # Store communications (split into unresolved complaints vs. benign)
        # Store per-transaction to avoid cross-contamination between multiple chargebacks from same customer
        if has_unresolved_complaint:
            # Serious unresolved non-delivery complaint
            complaint_time = transaction_ts + timedelta(
                days=np.random.randint(5, min(days_ago - 3, 30))
            )
            
            message = random.choice([
                "order not received",
                "package not delivered",
                "still waiting for delivery",
                "shipment never arrived",
                "where is my order"
            ])
            
            communications_data.append({
                'customer_id': customer_id,
                'transaction_id': transaction_id,  # Link to specific transaction
                'timestamp': complaint_time.strftime('%Y-%m-%d %H:%M:%S'),
                'channel': random.choice(CHANNELS),
                'message_summary': message
            })
            
        elif has_benign_communication:
            # Benign inquiry or resolved issue
            contact_time = transaction_ts + timedelta(
                days=np.random.randint(2, min(days_ago - 2, 20))
            )
            
            # Choose message type based on scenario
            if refund_issued:
                message = random.choice([
                    "refund requested",
                    "return initiated",
                    "cancellation requested"
                ])
            elif 'late' in locals().get('scenario', ''):
                message = random.choice([
                    "asked about delivery delay",
                    "inquired about shipping status",
                    "when will order arrive"
                ])
            elif 'quality' in locals().get('scenario', ''):
                message = random.choice([
                    "complained item damaged",
                    "product quality issue",
                    "item not as described"
                ])
            else:
                message = random.choice([
                    "asked for tracking number",
                    "delivery date inquiry",
                    "confirmed delivery received",
                    "thanked for fast shipping"
                ])
            
            communications_data.append({
                'customer_id': customer_id,
                'transaction_id': transaction_id,  # Link to specific transaction
                'timestamp': contact_time.strftime('%Y-%m-%d %H:%M:%S'),
                'channel': random.choice(CHANNELS),
                'message_summary': message
            })
        
        # Store chargeback
        reason_code = random.choice(REASON_CODES)
        if not delivery_confirmed and 'not_received' in reason_code:
            reason_code = 'product_not_received'
        elif refund_issued:
            reason_code = random.choice(['duplicate_charge', 'cancelled_subscription'])
        
        chargebacks_data.append({
            'chargeback_id': chargeback_id,
            'transaction_id': transaction_id,
            'reason_code': reason_code,
            'amount': amount,
            'true_label': true_label
        })
    
    # Create DataFrames
    transactions_df = pd.DataFrame(transactions_data)
    orders_df = pd.DataFrame(orders_data)
    fulfillment_df = pd.DataFrame(fulfillment_data)
    communications_df = pd.DataFrame(communications_data)
    chargebacks_df = pd.DataFrame(chargebacks_data)
    
    # Apply label noise to simulate real-world edge cases
    chargebacks_df = apply_label_noise(chargebacks_df, fulfillment_df, communications_df)
    
    return transactions_df, orders_df, fulfillment_df, customers_df, communications_df, chargebacks_df


def apply_label_noise(chargebacks_df, fulfillment_df, communications_df):
    """
    Apply deliberate label noise to simulate real-world edge cases where 
    delivery_confirmed/has_unresolved_complaint don't perfectly predict defensibility.
    
    Two types of noise:
    1. "Friendly fraud": delivery_confirmed=True, no complaint, but NOT_DEFENSIBLE
       (customer disputes despite evidence - item not as described, unauthorized claim)
    2. "Legitimate despite noise": has_unresolved_complaint=True but DEFENSIBLE
       (complaint about packaging/delay, not non-receipt; item was delivered)
    
    Noise rate: 3-5% of cases
    """
    NOISE_RATE = 0.04  # 4% of cases get label flipped
    
    # Track noise cases (for analysis only, never exposed to pipeline)
    chargebacks_df['noise_case'] = False
    chargebacks_df['noise_type'] = None
    
    # Build lookup for has_unresolved_complaint
    unresolved_keywords = ['not received', 'not delivered', 'still waiting', 'never arrived', 'where is']
    txns_with_unresolved = set()
    for txn_id in communications_df['transaction_id'].unique():
        messages = communications_df[communications_df['transaction_id'] == txn_id]['message_summary'].tolist()
        if any(any(kw in msg for kw in unresolved_keywords) for msg in messages):
            txns_with_unresolved.add(txn_id)
    
    # Build lookup for delivery_confirmed
    fulf_lookup = {}
    for _, row in fulfillment_df.iterrows():
        # Extract transaction_id from order_id (ORD_XXXXXXXX -> TXN_XXXXXXXX)
        txn_id = row['order_id'].replace('ORD_', 'TXN_')
        fulf_lookup[txn_id] = row['delivery_confirmed']
    
    noise_candidates_friendly_fraud = []
    noise_candidates_legitimate = []
    
    for idx, row in chargebacks_df.iterrows():
        txn_id = row['transaction_id']
        delivery_confirmed = fulf_lookup.get(txn_id, False)
        has_unresolved_complaint = txn_id in txns_with_unresolved
        current_label = row['true_label']
        
        # Candidate for friendly fraud: delivered, no complaint, currently DEFENSIBLE
        if delivery_confirmed and not has_unresolved_complaint and current_label == 'DEFENSIBLE':
            noise_candidates_friendly_fraud.append(idx)
        
        # Candidate for legitimate despite noise: has complaint, currently NOT_DEFENSIBLE
        if has_unresolved_complaint and current_label == 'NOT_DEFENSIBLE':
            noise_candidates_legitimate.append(idx)
    
    # Deterministically select noise cases
    random.seed(42)  # Fixed seed for reproducibility
    
    # Allocate noise budget between two types
    total_noise = int(len(chargebacks_df) * NOISE_RATE)
    friendly_fraud_count = total_noise // 2
    legitimate_count = total_noise - friendly_fraud_count
    
    # Select cases to flip
    if len(noise_candidates_friendly_fraud) >= friendly_fraud_count:
        friendly_fraud_indices = random.sample(noise_candidates_friendly_fraud, friendly_fraud_count)
    else:
        friendly_fraud_indices = noise_candidates_friendly_fraud
    
    if len(noise_candidates_legitimate) >= legitimate_count:
        legitimate_indices = random.sample(noise_candidates_legitimate, legitimate_count)
    else:
        legitimate_indices = noise_candidates_legitimate
    
    # Apply friendly fraud flips
    for idx in friendly_fraud_indices:
        chargebacks_df.at[idx, 'true_label'] = 'NOT_DEFENSIBLE'
        chargebacks_df.at[idx, 'noise_case'] = True
        chargebacks_df.at[idx, 'noise_type'] = 'friendly_fraud'
        # Update reason_code to reflect this
        chargebacks_df.at[idx, 'reason_code'] = random.choice([
            'item_significantly_not_as_described',
            'unauthorized_transaction_claim',
            'product_defective'
        ])
    
    # Apply legitimate despite noise flips
    for idx in legitimate_indices:
        chargebacks_df.at[idx, 'true_label'] = 'DEFENSIBLE'
        chargebacks_df.at[idx, 'noise_case'] = True
        chargebacks_df.at[idx, 'noise_type'] = 'legitimate_despite_complaint'
    
    print(f"Label noise applied: {len(friendly_fraud_indices)} friendly fraud, {len(legitimate_indices)} legitimate despite complaint")
    
    return chargebacks_df


def split_and_save(transactions_df, orders_df, fulfillment_df, customers_df, communications_df, chargebacks_df):
    """Split data into dev/heldout BEFORE any label usage, then save to CSV."""
    
    # Shuffle chargebacks for split
    chargebacks_shuffled = chargebacks_df.sample(frac=1, random_state=42).reset_index(drop=True)
    
    split_idx = int(len(chargebacks_shuffled) * DEV_SPLIT)
    
    dev_chargebacks = chargebacks_shuffled.iloc[:split_idx]
    heldout_chargebacks = chargebacks_shuffled.iloc[split_idx:]
    
    dev_txn_ids = set(dev_chargebacks['transaction_id'])
    heldout_txn_ids = set(heldout_chargebacks['transaction_id'])
    
    # Split all tables by transaction_id
    dev_transactions = transactions_df[transactions_df['transaction_id'].isin(dev_txn_ids)]
    heldout_transactions = transactions_df[transactions_df['transaction_id'].isin(heldout_txn_ids)]
    
    dev_orders = orders_df[orders_df['transaction_id'].isin(dev_txn_ids)]
    heldout_orders = orders_df[orders_df['transaction_id'].isin(heldout_txn_ids)]
    
    dev_order_ids = set(dev_orders['order_id'])
    heldout_order_ids = set(heldout_orders['order_id'])
    
    dev_fulfillment = fulfillment_df[fulfillment_df['order_id'].isin(dev_order_ids)]
    heldout_fulfillment = fulfillment_df[fulfillment_df['order_id'].isin(heldout_order_ids)]
    
    # Communications are now linked to transaction_id
    dev_communications = communications_df[communications_df['transaction_id'].isin(dev_txn_ids)]
    heldout_communications = communications_df[communications_df['transaction_id'].isin(heldout_txn_ids)]
    
    # Customers need to be available in both sets
    # (same customer may have chargebacks in both splits)
    # Customers need to be available in both sets
    # (same customer may have chargebacks in both splits)
    dev_customer_ids = set(dev_transactions['customer_id'])
    heldout_customer_ids = set(heldout_transactions['customer_id'])
    
    dev_customers = customers_df[customers_df['customer_id'].isin(dev_customer_ids)]
    heldout_customers = customers_df[customers_df['customer_id'].isin(heldout_customer_ids)]
    
    # Create directories
    os.makedirs('data/dev', exist_ok=True)
    os.makedirs('data/heldout', exist_ok=True)
    
    # Save dev set
    dev_transactions.to_csv('data/dev/transactions.csv', index=False)
    dev_orders.to_csv('data/dev/orders.csv', index=False)
    dev_fulfillment.to_csv('data/dev/fulfillment.csv', index=False)
    dev_customers.to_csv('data/dev/customers.csv', index=False)
    dev_communications.to_csv('data/dev/communications.csv', index=False)
    dev_chargebacks.to_csv('data/dev/chargebacks.csv', index=False)
    
    # Save heldout set
    heldout_transactions.to_csv('data/heldout/transactions.csv', index=False)
    heldout_orders.to_csv('data/heldout/orders.csv', index=False)
    heldout_fulfillment.to_csv('data/heldout/fulfillment.csv', index=False)
    heldout_customers.to_csv('data/heldout/customers.csv', index=False)
    heldout_communications.to_csv('data/heldout/communications.csv', index=False)
    heldout_chargebacks.to_csv('data/heldout/chargebacks.csv', index=False)
    
    print("✓ Data saved to data/dev/ and data/heldout/")
    print()
    
    return dev_chargebacks, heldout_chargebacks, dev_fulfillment, heldout_fulfillment, dev_communications, heldout_communications


def print_summary_stats(dev_chargebacks, heldout_chargebacks, dev_fulfillment, heldout_fulfillment, 
                       dev_communications, heldout_communications):
    """Print comprehensive summary statistics for both splits."""
    
    print("="*80)
    print("SYNTHETIC DATA GENERATION SUMMARY")
    print("="*80)
    print()
    
    # Label distribution
    print("LABEL DISTRIBUTION")
    print("-"*80)
    print(f"{'Split':<15} {'DEFENSIBLE':<15} {'NOT_DEFENSIBLE':<20} {'Total':<10}")
    print("-"*80)
    
    dev_def = (dev_chargebacks['true_label'] == 'DEFENSIBLE').sum()
    dev_not_def = (dev_chargebacks['true_label'] == 'NOT_DEFENSIBLE').sum()
    dev_total = len(dev_chargebacks)
    
    heldout_def = (heldout_chargebacks['true_label'] == 'DEFENSIBLE').sum()
    heldout_not_def = (heldout_chargebacks['true_label'] == 'NOT_DEFENSIBLE').sum()
    heldout_total = len(heldout_chargebacks)
    
    print(f"{'Dev':<15} {dev_def} ({dev_def/dev_total*100:.1f}%){'':<3} {dev_not_def} ({dev_not_def/dev_total*100:.1f}%){'':<8} {dev_total}")
    print(f"{'Heldout':<15} {heldout_def} ({heldout_def/heldout_total*100:.1f}%){'':<3} {heldout_not_def} ({heldout_not_def/heldout_total*100:.1f}%){'':<8} {heldout_total}")
    print()
    
    # Evidence completeness
    print("EVIDENCE COMPLETENESS STATS")
    print("-"*80)
    
    def calc_evidence_stats(chargebacks, fulfillment, communications):
        cb_order_ids = set(chargebacks['transaction_id'].apply(lambda x: f"ORD_{x.split('_')[1]}"))
        fulf = fulfillment[fulfillment['order_id'].isin(cb_order_ids)]
        
        delivery_confirmed = (fulf['delivery_confirmed'] == True).sum()
        signature_captured = (fulf['signature_captured'] == True).sum()
        both_confirmed = ((fulf['delivery_confirmed'] == True) & (fulf['signature_captured'] == True)).sum()
        neither_confirmed = ((fulf['delivery_confirmed'] == False) & (fulf['signature_captured'] == False)).sum()
        
        cb_customer_ids = chargebacks.merge(
            pd.DataFrame({'transaction_id': list(chargebacks['transaction_id'])}).assign(
                customer_id=lambda x: x['transaction_id']  # simplified for stats
            ), on='transaction_id', how='left'
        )
        
        has_communication = len(communications) > 0
        
        return {
            'delivery_confirmed': delivery_confirmed,
            'signature_captured': signature_captured,
            'both_confirmed': both_confirmed,
            'neither_confirmed': neither_confirmed,
            'partial_evidence': (delivery_confirmed - both_confirmed + signature_captured - both_confirmed) / 2 if delivery_confirmed > 0 else 0,
            'has_communication_pct': len(communications) / len(chargebacks) * 100 if len(chargebacks) > 0 else 0
        }
    
    dev_stats = calc_evidence_stats(dev_chargebacks, dev_fulfillment, dev_communications)
    heldout_stats = calc_evidence_stats(heldout_chargebacks, heldout_fulfillment, heldout_communications)
    
    print(f"{'Metric':<40} {'Dev':<15} {'Heldout':<15}")
    print("-"*80)
    print(f"{'Delivery confirmed':<40} {dev_stats['delivery_confirmed']:<15} {heldout_stats['delivery_confirmed']:<15}")
    print(f"{'Signature captured':<40} {dev_stats['signature_captured']:<15} {heldout_stats['signature_captured']:<15}")
    print(f"{'Both delivery + signature':<40} {dev_stats['both_confirmed']:<15} {heldout_stats['both_confirmed']:<15}")
    print(f"{'Neither delivery nor signature':<40} {dev_stats['neither_confirmed']:<15} {heldout_stats['neither_confirmed']:<15}")
    dev_comm_pct = f"{dev_stats['has_communication_pct']:.1f}%"
    heldout_comm_pct = f"{heldout_stats['has_communication_pct']:.1f}%"
    print(f"{'Cases with customer communications':<40} {dev_comm_pct:<15} {heldout_comm_pct:<15}")
    print()
    
    # Ambiguous case detection (partial evidence = should produce REVIEW)
    print("AMBIGUOUS EVIDENCE MARKERS (cases likely to produce REVIEW)")
    print("-"*80)
    
    def find_ambiguous(chargebacks, fulfillment):
        cb_order_ids = set(chargebacks['transaction_id'].apply(lambda x: f"ORD_{x.split('_')[1]}"))
        fulf = fulfillment[fulfillment['order_id'].isin(cb_order_ids)]
        
        delivered_no_sig = ((fulf['delivery_confirmed'] == True) & (fulf['signature_captured'] == False)).sum()
        total = len(fulf)
        
        return delivered_no_sig, total
    
    dev_ambig, dev_total_fulf = find_ambiguous(dev_chargebacks, dev_fulfillment)
    heldout_ambig, heldout_total_fulf = find_ambiguous(heldout_chargebacks, heldout_fulfillment)
    
    print(f"{'Delivered but no signature':<40} {dev_ambig} ({dev_ambig/dev_total_fulf*100:.1f}%){'':<3} {heldout_ambig} ({heldout_ambig/heldout_total_fulf*100:.1f}%)")
    print()
    
    # Correlation strength indicator
    print("CORRELATION STRENGTH CHECK")
    print("-"*80)
    print("For DEFENSIBLE cases, we expect:")
    print("  - High delivery_confirmed rate")
    print("  - Low communication (complaint) rate")
    print()
    
    def check_correlation(chargebacks, fulfillment, communications):
        defensible = chargebacks[chargebacks['true_label'] == 'DEFENSIBLE']
        def_txn_ids = set(defensible['transaction_id'])
        def_order_ids = set([f"ORD_{txn.split('_')[1]}" for txn in def_txn_ids])
        
        def_fulf = fulfillment[fulfillment['order_id'].isin(def_order_ids)]
        def_delivery_rate = (def_fulf['delivery_confirmed'] == True).sum() / len(def_fulf) * 100 if len(def_fulf) > 0 else 0
        
        return def_delivery_rate
    
    dev_corr = check_correlation(dev_chargebacks, dev_fulfillment, dev_communications)
    heldout_corr = check_correlation(heldout_chargebacks, heldout_fulfillment, heldout_communications)
    
    print(f"{'DEFENSIBLE → delivery_confirmed %':<40} {dev_corr:.1f}%{'':<10} {heldout_corr:.1f}%")
    print()
    print("✓ Correlation strength: " + ("STRONG" if dev_corr > 70 else "MODERATE" if dev_corr > 50 else "WEAK"))
    print("  (>70% = strong signal, rules should perform well)")
    print()
    
    print("="*80)
    print("Data generation complete. Ready for rule engine development.")
    print("="*80)


if __name__ == '__main__':
    print()
    print("DisputeLens Data Generator")
    print("Generating correlated synthetic chargeback evidence data...")
    print()
    
    # Generate data
    transactions_df, orders_df, fulfillment_df, customers_df, communications_df, chargebacks_df = generate_correlated_data()
    
    # Split and save
    dev_chargebacks, heldout_chargebacks, dev_fulfillment, heldout_fulfillment, dev_communications, heldout_communications = split_and_save(
        transactions_df, orders_df, fulfillment_df, customers_df, communications_df, chargebacks_df
    )
    
    # Print summary
    print_summary_stats(dev_chargebacks, heldout_chargebacks, dev_fulfillment, heldout_fulfillment, 
                       dev_communications, heldout_communications)
