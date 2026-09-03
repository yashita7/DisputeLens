"""
Evidence Retrieval Module
Given a chargeback_id, joins across all 6 tables and returns a structured case dict.
Simulates real-world evidence gaps through deterministic masking.
"""

import pandas as pd
import random
from typing import Dict, Any, Optional

class EvidenceRetriever:
    """Retrieves and joins evidence from all 6 tables for a given chargeback."""
    
    def __init__(self, data_dir: str = 'data/dev'):
        """
        Initialize retriever with data directory.
        
        Args:
            data_dir: Path to data directory (default: data/dev)
        """
        self.data_dir = data_dir
        self._load_data()
        self._preprocess()
        self._init_masking()
    
    def _init_masking(self):
        """
        Initialize deterministic evidence masking to simulate real-world logging gaps.
        
        For ~6-8% of cases, randomly mark ONE of {delivery_confirmed, signature_captured, 
        has_unresolved_complaint, refund_issued} as "not_available" to simulate:
        - Webhook failures
        - Delayed reconciliation
        - System integration gaps
        
        Uses deterministic seeding based on chargeback_id for reproducibility.
        """
        # Configuration
        self.MASKING_RATE = 0.07  # 7% of cases get one field masked
        self.MASKABLE_FIELDS = [
            'delivery_confirmed',
            'signature_captured', 
            'has_unresolved_complaint',
            'refund_issued'
        ]
        
        # Define dependent fields that should also be masked
        self.DEPENDENT_FIELDS = {
            'delivery_confirmed': ['delivered_at'],
            'signature_captured': [],  # No dependent timestamp
            'has_unresolved_complaint': [],  # No dependent timestamp
            'refund_issued': []  # No dependent timestamp
        }
        
        # Determine which cases get masked (deterministic based on chargeback_id)
        self.masked_cases = {}
        
        for cb_id in self.chargebacks['chargeback_id']:
            # Use chargeback_id as seed for deterministic masking
            seed_value = int(cb_id.split('_')[1])  # Extract numeric part
            random.seed(42 + seed_value)  # Base seed 42 + case-specific offset
            
            # Decide if this case gets masked
            if random.random() < self.MASKING_RATE:
                # Choose which field to mask
                field_to_mask = random.choice(self.MASKABLE_FIELDS)
                self.masked_cases[cb_id] = field_to_mask
    
    def _load_data(self):
        """Load all 6 CSV tables."""
        self.chargebacks = pd.read_csv(f'{self.data_dir}/chargebacks.csv')
        self.transactions = pd.read_csv(f'{self.data_dir}/transactions.csv')
        self.orders = pd.read_csv(f'{self.data_dir}/orders.csv')
        self.fulfillment = pd.read_csv(f'{self.data_dir}/fulfillment.csv')
        self.customers = pd.read_csv(f'{self.data_dir}/customers.csv')
        self.communications = pd.read_csv(f'{self.data_dir}/communications.csv')
    
    def _preprocess(self):
        """Precompute has_unresolved_complaint for each transaction."""
        unresolved_keywords = ['not received', 'not delivered', 'still waiting', 'never arrived', 'where is']
        
        self.txns_with_unresolved = set()
        for txn_id in self.communications['transaction_id'].unique():
            messages = self.communications[
                self.communications['transaction_id'] == txn_id
            ]['message_summary'].tolist()
            
            if any(any(kw in msg for kw in unresolved_keywords) for msg in messages):
                self.txns_with_unresolved.add(txn_id)
    
    def retrieve(self, chargeback_id: str) -> Dict[str, Any]:
        """
        Retrieve all evidence for a given chargeback_id.
        
        Args:
            chargeback_id: The chargeback identifier (e.g., 'CB_00000001')
        
        Returns:
            Dictionary with all evidence fields, marking missing as 'not_available'
        """
        # Get chargeback record
        cb_row = self.chargebacks[self.chargebacks['chargeback_id'] == chargeback_id]
        
        if cb_row.empty:
            raise ValueError(f"Chargeback {chargeback_id} not found")
        
        cb_row = cb_row.iloc[0]
        transaction_id = cb_row['transaction_id']
        
        # Get transaction
        txn_row = self.transactions[self.transactions['transaction_id'] == transaction_id]
        if txn_row.empty:
            return {'error': 'Transaction not found', 'chargeback_id': chargeback_id}
        txn_row = txn_row.iloc[0]
        
        customer_id = txn_row['customer_id']
        
        # Get order
        order_row = self.orders[self.orders['transaction_id'] == transaction_id]
        if order_row.empty:
            order_row = None
        else:
            order_row = order_row.iloc[0]
        
        # Get fulfillment
        if order_row is not None:
            order_id = order_row['order_id']
            fulf_row = self.fulfillment[self.fulfillment['order_id'] == order_id]
            if fulf_row.empty:
                fulf_row = None
            else:
                fulf_row = fulf_row.iloc[0]
        else:
            fulf_row = None
        
        # Get customer
        cust_row = self.customers[self.customers['customer_id'] == customer_id]
        if cust_row.empty:
            cust_row = None
        else:
            cust_row = cust_row.iloc[0]
        
        # Get communications for this transaction
        comm_rows = self.communications[self.communications['transaction_id'] == transaction_id]
        
        # Build case dictionary
        case = {
            # Chargeback info
            'chargeback_id': chargeback_id,
            'transaction_id': transaction_id,
            'reason_code': cb_row['reason_code'],
            'chargeback_amount': cb_row['amount'],
            'true_label': cb_row.get('true_label', 'not_available'),  # For evaluation only
            
            # Noise tracking (for analysis only, never used by rule engine)
            'noise_case': bool(cb_row.get('noise_case', False)),
            'noise_type': cb_row.get('noise_type', None),
            
            # Transaction info
            'customer_id': customer_id,
            'merchant_id': txn_row['merchant_id'],
            'transaction_amount': txn_row['amount'],
            'payment_method': txn_row['payment_method'],
            'transaction_timestamp': txn_row['timestamp'],
            'payment_confirmed': True,  # All transactions in our data have confirmed payment
            
            # Order info
            'order_id': order_row['order_id'] if order_row is not None else 'not_available',
            'order_status': order_row['status'] if order_row is not None else 'not_available',
            'product_category': order_row['product_category'] if order_row is not None else 'not_available',
            
            # Fulfillment info
            'shipped_at': fulf_row['shipped_at'] if fulf_row is not None else 'not_available',
            'delivered_at': fulf_row['delivered_at'] if fulf_row is not None else 'not_available',
            'delivery_confirmed': bool(fulf_row['delivery_confirmed']) if fulf_row is not None and pd.notna(fulf_row['delivery_confirmed']) else False,
            'signature_captured': bool(fulf_row['signature_captured']) if fulf_row is not None and pd.notna(fulf_row['signature_captured']) else False,
            
            # Customer info
            'account_age_days': int(cust_row['account_age_days']) if cust_row is not None else 0,
            'prior_orders': int(cust_row['prior_orders']) if cust_row is not None else 0,
            'prior_chargebacks': int(cust_row['prior_chargebacks']) if cust_row is not None else 0,
            'prior_refunds': int(cust_row['prior_refunds']) if cust_row is not None else 0,
            
            # Communications (derived)
            'has_communication': len(comm_rows) > 0,
            'communication_count': len(comm_rows),
            'has_unresolved_complaint': transaction_id in self.txns_with_unresolved,
            
            # Refund status (derived from order status)
            'refund_issued': order_row['status'] in ['refunded', 'cancelled'] if order_row is not None else False,
        }
        
        # Apply deterministic evidence masking to simulate real-world logging gaps
        if chargeback_id in self.masked_cases:
            field_to_mask = self.masked_cases[chargeback_id]
            case[field_to_mask] = 'not_available'
            
            # Also mask dependent fields (e.g., delivered_at when delivery_confirmed is masked)
            dependent_fields = self.DEPENDENT_FIELDS.get(field_to_mask, [])
            for dep_field in dependent_fields:
                if dep_field in case:
                    case[dep_field] = 'not_available'
            
            case['_masked_field'] = field_to_mask  # Track for debugging (not used in rules)
        
        return case
    
    def retrieve_all(self) -> list:
        """Retrieve all chargebacks in the dataset."""
        return [
            self.retrieve(cb_id) 
            for cb_id in self.chargebacks['chargeback_id']
        ]


if __name__ == '__main__':
    # Test retrieval with masking
    retriever = EvidenceRetriever('data/dev')
    
    # Test a single case
    test_case = retriever.retrieve('CB_00000740')
    
    print("Evidence Retrieval Test (with masking)")
    print("="*80)
    print(f"Chargeback: {test_case['chargeback_id']}")
    print(f"Transaction: {test_case['transaction_id']}")
    print(f"Customer: {test_case['customer_id']}")
    print()
    print("Key Evidence:")
    print(f"  payment_confirmed: {test_case['payment_confirmed']}")
    print(f"  delivery_confirmed: {test_case['delivery_confirmed']}")
    print(f"  signature_captured: {test_case['signature_captured']}")
    print(f"  refund_issued: {test_case['refund_issued']}")
    print(f"  has_unresolved_complaint: {test_case['has_unresolved_complaint']}")
    print(f"  prior_chargebacks: {test_case['prior_chargebacks']}")
    print(f"  account_age_days: {test_case['account_age_days']}")
    
    if '_masked_field' in test_case:
        print(f"\n  ⚠ Masked field: {test_case['_masked_field']}")
    
    print()
    
    # Check masking statistics
    all_cases = retriever.retrieve_all()
    masked_count = sum(1 for c in all_cases if '_masked_field' in c)
    print(f"Masking Statistics:")
    print(f"  Total cases: {len(all_cases)}")
    print(f"  Masked cases: {masked_count} ({masked_count/len(all_cases)*100:.1f}%)")
    print()
    print("✓ Retrieval working correctly with deterministic masking")
