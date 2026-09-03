"""
Rule Engine for Chargeback Defensibility Scoring
Deterministic weighted scoring based on verified evidence.
"""

from typing import Dict, List, Tuple, Any


class DefensibilityRuleEngine:
    """
    Weighted rule-based scoring engine for chargeback defensibility.
    
    Scoring Rules:
    - +30 payment_confirmed
    - +25 delivery_confirmed
    - +15 signature_captured
    - +10 no_refund_issued (refund_issued==False)
    - +10 has_unresolved_complaint==False
    - +10 if account_age_days>90 and prior_chargebacks==0
    - -20 if prior_chargebacks>=2
    - -30 if delivery_confirmed==False
    - -25 if refund_issued==True
    
    Decision Thresholds:
    - score >= 70: CONTEST
    - score 40-69: REVIEW
    - score < 40: DO_NOT_CONTEST
    """
    
    def __init__(self):
        """Initialize rule engine with scoring weights and thresholds."""
        # Positive evidence weights
        self.PAYMENT_CONFIRMED_WEIGHT = 30
        self.DELIVERY_CONFIRMED_WEIGHT = 25
        self.SIGNATURE_CAPTURED_WEIGHT = 15
        self.NO_REFUND_WEIGHT = 10
        self.NO_COMPLAINT_WEIGHT = 10
        self.GOOD_CUSTOMER_WEIGHT = 10
        
        # Negative evidence weights
        self.REPEAT_DISPUTER_PENALTY = -20
        self.NO_DELIVERY_PENALTY = -30
        self.REFUND_ISSUED_PENALTY = -25
        
        # Decision thresholds
        # Adjusted to capture ambiguous cases (delivered but no signature typically score 75-85)
        self.CONTEST_THRESHOLD = 85  # Raised from 70 to require signature or other strong evidence
        self.REVIEW_THRESHOLD = 45   # Raised slightly to be more conservative
    
    def score(self, case: Dict[str, Any]) -> Tuple[str, int, List[str]]:
        """
        Score a case and return decision, score, and fired rules.
        
        Args:
            case: Evidence dictionary from retrieval module
        
        Returns:
            Tuple of (decision, score, fired_rules)
            - decision: 'CONTEST', 'REVIEW', or 'DO_NOT_CONTEST'
            - score: integer score
            - fired_rules: list of rule descriptions that contributed to score
            
        Note: Fields marked as "not_available" contribute 0 to score (not treated as False).
              Missing evidence pushes toward REVIEW via lower total score.
        """
        score = 0
        fired_rules = []
        
        # Rule 1: Payment confirmed (should always be true in our data)
        payment_confirmed = case.get('payment_confirmed', False)
        if payment_confirmed == 'not_available':
            fired_rules.append("+0 payment_confirmed (not_available)")
        elif payment_confirmed:
            score += self.PAYMENT_CONFIRMED_WEIGHT
            fired_rules.append(f"+{self.PAYMENT_CONFIRMED_WEIGHT} payment_confirmed")
        
        # Rule 2: Delivery confirmed
        delivery_confirmed = case.get('delivery_confirmed', False)
        if delivery_confirmed == 'not_available':
            fired_rules.append("+0 delivery_confirmed (not_available)")
        elif delivery_confirmed:
            score += self.DELIVERY_CONFIRMED_WEIGHT
            fired_rules.append(f"+{self.DELIVERY_CONFIRMED_WEIGHT} delivery_confirmed")
        else:
            # Penalty for confirmed non-delivery (not the same as unknown)
            score += self.NO_DELIVERY_PENALTY
            fired_rules.append(f"{self.NO_DELIVERY_PENALTY} delivery_not_confirmed")
        
        # Rule 3: Signature captured
        signature_captured = case.get('signature_captured', False)
        if signature_captured == 'not_available':
            fired_rules.append("+0 signature_captured (not_available)")
        elif signature_captured:
            score += self.SIGNATURE_CAPTURED_WEIGHT
            fired_rules.append(f"+{self.SIGNATURE_CAPTURED_WEIGHT} signature_captured")
        
        # Rule 4: No refund issued
        refund_issued = case.get('refund_issued', False)
        if refund_issued == 'not_available':
            fired_rules.append("+0 refund_status (not_available)")
        elif not refund_issued:
            score += self.NO_REFUND_WEIGHT
            fired_rules.append(f"+{self.NO_REFUND_WEIGHT} no_refund_issued")
        else:
            # Penalty for refund already issued
            score += self.REFUND_ISSUED_PENALTY
            fired_rules.append(f"{self.REFUND_ISSUED_PENALTY} refund_already_issued")
        
        # Rule 5: No unresolved complaint
        has_unresolved_complaint = case.get('has_unresolved_complaint', False)
        if has_unresolved_complaint == 'not_available':
            fired_rules.append("+0 unresolved_complaint (not_available)")
        elif not has_unresolved_complaint:
            score += self.NO_COMPLAINT_WEIGHT
            fired_rules.append(f"+{self.NO_COMPLAINT_WEIGHT} no_unresolved_complaint")
        
        # Rule 6: Good customer (old account, no prior chargebacks)
        account_age = case.get('account_age_days', 0)
        prior_chargebacks = case.get('prior_chargebacks', 0)
        
        if account_age > 90 and prior_chargebacks == 0:
            score += self.GOOD_CUSTOMER_WEIGHT
            fired_rules.append(f"+{self.GOOD_CUSTOMER_WEIGHT} good_customer (age>{account_age}d, no_prior_chargebacks)")
        
        # Rule 7: Repeat disputer penalty
        if prior_chargebacks >= 2:
            score += self.REPEAT_DISPUTER_PENALTY
            fired_rules.append(f"{self.REPEAT_DISPUTER_PENALTY} repeat_disputer (prior_chargebacks={prior_chargebacks})")
        
        # Map score to decision
        if score >= self.CONTEST_THRESHOLD:
            decision = 'CONTEST'
        elif score >= self.REVIEW_THRESHOLD:
            decision = 'REVIEW'
        else:
            decision = 'DO_NOT_CONTEST'
        
        return decision, score, fired_rules
    
    def explain(self, case: Dict[str, Any]) -> str:
        """
        Generate human-readable explanation of the decision.
        
        Args:
            case: Evidence dictionary
        
        Returns:
            Multi-line string explanation
        """
        decision, score, fired_rules = self.score(case)
        
        explanation = []
        explanation.append(f"Chargeback: {case['chargeback_id']}")
        explanation.append(f"Decision: {decision} (score: {score})")
        explanation.append("")
        explanation.append("Fired Rules:")
        for rule in fired_rules:
            explanation.append(f"  {rule}")
        explanation.append("")
        explanation.append("Key Evidence:")
        explanation.append(f"  delivery_confirmed: {case.get('delivery_confirmed', 'not_available')}")
        explanation.append(f"  signature_captured: {case.get('signature_captured', 'not_available')}")
        explanation.append(f"  refund_issued: {case.get('refund_issued', 'not_available')}")
        explanation.append(f"  has_unresolved_complaint: {case.get('has_unresolved_complaint', 'not_available')}")
        explanation.append(f"  prior_chargebacks: {case.get('prior_chargebacks', 'not_available')}")
        
        return "\n".join(explanation)


if __name__ == '__main__':
    # Test rule engine
    from retrieval import EvidenceRetriever
    
    print("Rule Engine Test")
    print("="*80)
    print()
    
    retriever = EvidenceRetriever('data/dev')
    engine = DefensibilityRuleEngine()
    
    # Test a few cases
    test_ids = ['CB_00000740', 'CB_00000521', 'CB_00000136']
    
    for cb_id in test_ids:
        case = retriever.retrieve(cb_id)
        print(engine.explain(case))
        print("-"*80)
        print()
