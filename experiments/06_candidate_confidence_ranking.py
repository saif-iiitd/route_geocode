"""Experiment 06: unified candidate confidence scoring + joint disambiguation
for resolved mentions (step 3, continued).

Targets the handoff's named gap directly: "It does not implement the
manuscript's implied contextual confidence/ranking logic. No joint
disambiguation across co-mentioned places."

Small cached sample, all real: three cases pulled from actual corpus tweets
mentioning "Krishna Nagar" (a real gazetteer entry, appearing 16 times in the
corpus, and -- confirmed live before building anything -- genuinely ambiguous:
OpenCage returns two real Delhi locations ~14 km apart for it, both at
confidence 8-9), "Madhuban Chowk" (a control case: 3 candidates but they
cluster within 350 m, i.e. one real place, not ambiguous), and "Chirag Delhi"
(a second clustered control case).

Case 1 -- clustered, no ambiguity (Madhuban Chowk): should resolve
CONFIDENCE_HIGH with no anchor needed.
Case 2 -- ambiguous, WITH a real anchor from the same tweet: the corpus
contains "Traffic is normal at Road no. 57 from Krishna Nagar towards
Shahdra." "Shahdra"/"Shahdara" resolves cleanly (tight cluster, East Delhi).
Using it as an anchor should correctly select the East Delhi "Krishna Nagar,
Road Number 57, Preet Vihar" candidate over the unrelated South Delhi one --
independently confirmable, since the tweet itself names "Road no. 57" and the
correct candidate's own address is "Road Number 57, Preet Vihar".
Case 3 -- ambiguous, WITHOUT an anchor (Krishna Nagar alone): must not
silently pick one candidate at high confidence; both real candidates are kept
and confidence is explicitly low.

Run: python -B experiments/06_candidate_confidence_ranking.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.confidence import rank_candidates  # noqa: E402
from src.geocoding import GeocodeCache  # noqa: E402

CACHE_PATH = ROOT / 'experiments/06_opencage_cache.json'


def main():
    cache = GeocodeCache(CACHE_PATH)
    results = {}

    print('=== Case 1: Madhuban Chowk (control -- clustered, no ambiguity) ===')
    r1 = rank_candidates('Madhuban Chowk', 'EXACT', cache)
    print(f"  confidence={r1['confidence']}  method={r1['method']}  spread={r1['spread_m']}m")
    print(f"  chosen: {r1['chosen']['formatted']}")
    print(f"  reason: {r1['reason']}")
    results['case_1_madhuban_chowk'] = r1

    from src.confidence import CONFIDENCE_HIGH

    print('\n=== Case 2a: anchor candidate that turned out NOT valid (Shahdara) ===')
    # From the real tweet "Traffic is normal at Road no. 57 from Krishna Nagar
    # towards Shahdra." -- tested as an anchor first. Its own 4 candidates
    # span 888m, just over the 500m cluster threshold (a genuine boundary
    # case: mostly the same East Delhi locality, one outlier pair pulls the
    # max-pairwise spread over the line -- see the write-up). Per the design
    # contract ("another already CONFIDENCE_HIGH mention"), this is correctly
    # refused as an anchor rather than used anyway.
    shahdara = rank_candidates('Shahdara', 'EXACT', cache)
    print(f"  Shahdara: confidence={shahdara['confidence']} (spread={shahdara['spread_m']}m) "
          f"-- {'valid' if shahdara['confidence'] == CONFIDENCE_HIGH else 'NOT valid'} as an anchor")
    results['case_2a_shahdara_anchor_rejected'] = shahdara

    print('\n=== Case 2b: Krishna Nagar, WITH a genuinely valid anchor (Jagatpuri, same real tweet family) ===')
    # From "Traffic is heavy in the carriageway from Krishna Nagar towards
    # Jagatpuri due to ongoing PWD work." Jagatpuri geocodes to a single
    # candidate (spread=0), whose own address independently names "Preet
    # Vihar" -- the same East Delhi area as the correct Krishna Nagar.
    anchor = rank_candidates('Jagatpuri', 'EXACT', cache)
    print(f"  anchor (Jagatpuri) confidence={anchor['confidence']} (spread={anchor['spread_m']}m)  "
          f"chosen: {anchor['chosen']['formatted']}")
    anchor_list = [(anchor['chosen']['lat'], anchor['chosen']['lng'])] if anchor['confidence'] == CONFIDENCE_HIGH else []
    r2 = rank_candidates('Krishna Nagar', 'EXACT', cache, anchors=anchor_list)
    print(f"  confidence={r2['confidence']}  method={r2['method']}  spread={r2['spread_m']}m")
    print(f"  chosen: {r2['chosen']['formatted']}")
    print(f"  reason: {r2['reason']}")
    print(f"  independent check: chosen address contains 'Preet Vihar'? "
          f"{'Preet Vihar' in r2['chosen']['formatted']} "
          f"(both mentions are from the same real East-Delhi tweet family)")
    results['case_2b_krishna_nagar_with_valid_anchor'] = {**r2, 'anchor': anchor}

    print('\n=== Case 3: Krishna Nagar, WITHOUT any anchor ===')
    r3 = rank_candidates('Krishna Nagar', 'EXACT', cache)
    print(f"  confidence={r3['confidence']}  method={r3['method']}  spread={r3['spread_m']}m")
    print(f"  candidates kept: {len(r3['candidates'])}")
    for c in r3['candidates']:
        print(f"    - {c['formatted']}")
    print(f"  reason: {r3['reason']}")
    results['case_3_krishna_nagar_no_anchor'] = r3

    print('\n=== Case 4: a FUZZY-tier match is capped below CONFIDENCE_HIGH even when clustered ===')
    r4 = rank_candidates('Mehrauli', 'FUZZY', cache)
    print(f"  confidence={r4['confidence']} (capped from a clustered result by FUZZY match tier)")
    results['case_4_fuzzy_cap'] = r4

    out_path = Path(__file__).with_suffix('.json')
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'\nWrote {out_path}')
    print(f'OpenCage response cache: {CACHE_PATH}')


if __name__ == '__main__':
    main()
