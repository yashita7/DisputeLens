"""
Precompute LLM Summaries for All Dev Cases

Generates case summaries for all 700 dev cases and stores them in a JSON file.
This avoids live Gemini API calls during demo/video recording.
"""

import os
import json
import time
from datetime import datetime
from dotenv import load_dotenv
from pipeline.retrieval import EvidenceRetriever
from pipeline.rules import DefensibilityRuleEngine
from pipeline.evidence_writer import EvidenceWriter

# Load environment variables
load_dotenv()

# Configuration
DELAY_BETWEEN_CALLS = 2.5  # seconds (to avoid rate limits)
OUTPUT_FILE = 'data/dev/llm_summaries.json'


def main():
    print("=" * 80)
    print("DisputeLens - LLM Summary Precomputation")
    print("=" * 80)
    print()
    
    # Check for API key
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        print("ERROR: GEMINI_API_KEY not found in environment")
        print("Please set it in .env file or export it before running this script")
        return
    
    print(f"✓ GEMINI_API_KEY loaded: {api_key[:15]}...")
    print()
    
    # Initialize components
    print("Initializing components...")
    retriever = EvidenceRetriever('data/dev')
    engine = DefensibilityRuleEngine()
    writer = EvidenceWriter()
    print("✓ Components initialized")
    print()
    
    # Load all cases
    print("Loading cases...")
    all_cases = retriever.retrieve_all()
    total_cases = len(all_cases)
    print(f"✓ Loaded {total_cases} cases")
    print()
    
    # Load existing summaries if file exists
    existing_summaries = {}
    if os.path.exists(OUTPUT_FILE):
        print(f"Found existing summaries at {OUTPUT_FILE}")
        with open(OUTPUT_FILE, 'r') as f:
            existing_data = json.load(f)
            existing_summaries = existing_data.get('summaries', {})
        print(f"✓ Loaded {len(existing_summaries)} existing summaries")
        print()
    
    # Filter cases to only those missing summaries
    cases_to_process = [case for case in all_cases if case['chargeback_id'] not in existing_summaries]
    print(f"Cases already completed: {len(existing_summaries)}")
    print(f"Cases still missing: {len(cases_to_process)}")
    print()
    
    if len(cases_to_process) == 0:
        print("All summaries already generated! Nothing to do.")
        return
    
    # Generate summaries (starting with existing ones)
    summaries = existing_summaries.copy()
    errors = []
    start_time = time.time()
    
    print(f"Generating summaries for {len(cases_to_process)} remaining cases...")
    print(f"Delay between calls: {DELAY_BETWEEN_CALLS}s (rate limit protection)")
    print(f"Estimated time: {(len(cases_to_process) * DELAY_BETWEEN_CALLS) / 60:.1f} minutes")
    print()
    print("-" * 80)
    
    for i, case in enumerate(cases_to_process, 1):
        case_id = case['chargeback_id']
        
        # Get decision and rules
        decision, score, fired_rules = engine.score(case)
        
        # Generate summary
        try:
            print(f"[{i}/{len(cases_to_process)}] {case_id} ({decision}, score={score})...", end=" ", flush=True)
            
            call_start = time.time()
            llm_output = writer.write_summary(case, decision, score, fired_rules)
            call_elapsed = time.time() - call_start
            
            # Store summary
            summaries[case_id] = {
                "summary": llm_output.get("summary", ""),
                "evidence": llm_output.get("evidence", []),
                "gaps": llm_output.get("gaps", []),
                "recommendation": llm_output.get("recommendation", decision),
                "confidence": llm_output.get("confidence", "unknown"),
                "generated_at": datetime.now().isoformat(),
                "generation_time_ms": int(call_elapsed * 1000)
            }
            
            print(f"✓ ({call_elapsed:.2f}s)")
            
            # Rate limiting delay (except for last case)
            if i < len(cases_to_process):
                time.sleep(DELAY_BETWEEN_CALLS)
        
        except Exception as e:
            print(f"✗ ERROR: {e}")
            errors.append({
                "case_id": case_id,
                "error": str(e)
            })
    
    elapsed = time.time() - start_time
    
    print("-" * 80)
    print()
    print("SUMMARY")
    print("=" * 80)
    print(f"Total cases in dataset:     {total_cases}")
    print(f"Previously completed:       {len(existing_summaries)}")
    print(f"Attempted this run:         {len(cases_to_process)}")
    print(f"Successful this run:        {len(summaries) - len(existing_summaries)}")
    print(f"Errors this run:            {len(errors)}")
    print(f"Total summaries now:        {len(summaries)}/{total_cases}")
    print(f"Total time this run:        {elapsed:.1f}s ({elapsed/60:.1f} minutes)")
    if len(cases_to_process) > 0:
        print(f"Avg time/case:              {elapsed/len(cases_to_process):.2f}s")
    print()
    
    if errors:
        print("Errors encountered:")
        for err in errors[:10]:  # Show first 10 errors
            print(f"  {err['case_id']}: {err['error']}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more")
        print()
    
    # Save to file
    print(f"Saving summaries to {OUTPUT_FILE}...")
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    
    output_data = {
        "generated_at": datetime.now().isoformat(),
        "total_cases": total_cases,
        "successful": len(summaries),
        "errors": total_cases - len(summaries),
        "summaries": summaries
    }
    
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(output_data, f, indent=2)
    
    print(f"✓ Saved {len(summaries)} total summaries ({len(summaries) - len(existing_summaries)} new)")
    print()
    
    if len(summaries) < total_cases:
        remaining = total_cases - len(summaries)
        print("=" * 80)
        print(f"⚠️  {remaining} cases still missing summaries")
        print("Likely hit API quota limit. Run this script again later to complete.")
        print("=" * 80)
    else:
        print("=" * 80)
        print("✅ Precomputation complete! All cases have summaries.")
        print(f"Summary file: {OUTPUT_FILE}")
        print()
        print("Next steps:")
        print("  1. Restart the API server")
        print("  2. API will now serve precomputed summaries (no live Gemini calls)")
        print("=" * 80)


if __name__ == '__main__':
    main()
