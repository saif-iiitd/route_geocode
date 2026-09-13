"""Semantic-role assignment for already-recognized place mentions in a traffic tweet.

Scope: this module answers "what job does each mention play in the route" (origin,
destination, named road, via-point, landmark, or a standalone point), and what
relations connect them (from/to/towards/via/on/along/near/under/between). It does
NOT do entity recognition itself -- callers supply mention spans (from spaCy plus the
existing gazetteer/EntityRuler, or from a test fixture); recognizing which text spans
are place mentions is a separate, later step (candidate-based entity resolution).

This directly replaces the notebook's failure mode found by the fidelity audit:
`extract_origin_destination` was defined twice with incompatible contracts, so
behavior depended on which definition ran last; different handlers inferred roles
by ad hoc suffix/counter checks that could silently drop or overwrite a role as the
token loop progressed; `via`, `between`, and multi-clause text had no systematic
representation. There is exactly one function here, one execution path, and no
partial-array mutation -- every mention keeps its own role for its own record.

Output schema mirrors src/translation_bakeoff/schema.py's structured-alignment shape
(mention_order, feature_type, uncertain, relations by mention_order) deliberately,
since both describe the same thing: a set of place mentions and the relations
between them, extracted from one sentence.
"""
import re
from dataclasses import dataclass, field

ORIGIN = 'ORIGIN'
DESTINATION = 'DESTINATION'
NAMED_ROAD = 'NAMED_ROAD'
VIA_ROAD = 'VIA_ROAD'
VIA_POINT = 'VIA_POINT'
LANDMARK = 'LANDMARK'
SEGMENT_BOUND = 'SEGMENT_BOUND'
POINT = 'POINT'
UNCLEAR = 'UNCLEAR'

# Feature-type hints a caller may attach to a mention (from a gazetteer or lexical
# suffix check); used only to disambiguate "on X"/"at X" between a road and a point.
ROAD_FEATURES = {'road', 'marg', 'route', 'flyover_approach'}
POINT_FEATURES = {'junction', 'chowk', 'circle', 'crossing', 'flyover', 'underpass',
                   'bridge', 'metro_station', 'bus_stand', 'gate', 'unknown'}

# Cue phrases checked longest-first so "in the carriageway from" doesn't get
# shadowed by a bare "from" match, and so word-boundary regexes never partially
# consume a longer cue.
_CUE_PATTERNS = [
    ('from', r'\bfrom\b'),
    ('towards', r'\btowards?\b'),
    ('to', r'\bto\b'),
    ('via', r'\bvia\b'),
    ('through', r'\bthrough\b'),
    ('between', r'\bbetween\b'),
    ('on', r'\bon\b|\balong\b'),
    ('near', r'\bnear\b'),
    ('under', r'\bunder\b'),
    ('at', r'\bat\b'),
]
_LIST_MARKER = re.compile(r'(?<![\w.])\d{1,2}\s*[.)]\s+(?=[A-Z0-9])')
_CONJUNCTION = re.compile(r'^\s*(?:,|&|and)\s*$', re.I)
_BARE_SEPARATOR = re.compile(r'^\s*(?:,|&|\band\b)\s*$', re.I)


@dataclass
class Mention:
    start: int
    end: int
    text: str
    feature_type: str = 'unknown'
    # Filled in by assign_roles(); left unset on the caller-supplied input.
    mention_order: int = 0
    role: str = UNCLEAR
    uncertain: bool = False


@dataclass
class Relation:
    relation: str
    source_mention_order: int
    target_mention_order: int
    uncertain: bool = False


def _clause_spans(text):
    """Split on explicit numbered-list markers only ("1.", "01)", ...).

    Sentence-splitting on bare periods is not attempted: abbreviations
    ("Rd.", "No.", "T-point.") are common in this corpus and a wrong split would
    silently sever an origin from its destination. A tweet with no numbered list
    is therefore always exactly one clause, even if it reads as several sentences.
    """
    marks = [m.start() for m in _LIST_MARKER.finditer(text)]
    if not marks:
        return [(0, len(text))]
    bounds = marks + [len(text)]
    return [(bounds[i], bounds[i + 1]) for i in range(len(marks))]


def dependency_vetoes(doc, mentions=()):
    """Character start-offsets of a 'to'/'towards' token whose dependency parse
    shows it is not a spatial preposition at all: `dep_ == 'pcomp'` is the
    complement of "due" ("due **to** the demonstration"), and `dep_ == 'aux'`
    is the infinitive marker before a verb ("route **to** take Ring Road").
    Both were confirmed against the real corpus in
    experiments/02_entity_dependency_audit.py: of every 'to'/'towards' token
    sampled, 81 were 'due to' (dep_=pcomp), 4 were infinitival (dep_=aux), and
    the remaining 125 were real spatial prepositions (dep_=prep).

    The 'aux' case needs one guard the raw parse doesn't give for free: on this
    corpus's terse, proper-noun-heavy tweet style, the small model sometimes
    mistags a place name's first word as a verb -- observed directly on "from
    Nehru Place **to Modi Mill**", where "Modi" (part of the real place "Modi
    Mill") was tagged pos_=VERB, making "to" look infinitival when it is a real
    destination. Since the supposed "verb" being inside a known mention span is
    exactly what would make that tag wrong, an 'aux' veto is only honored when
    its head token does *not* fall inside any supplied mention; 'pcomp' has no
    such failure mode observed and is vetoed unconditionally. `doc=None` skips
    dependency evidence entirely and falls back to adjacency alone.
    """
    vetoes = set()
    for tok in doc:
        if tok.text.lower() not in ('to', 'towards'):
            continue
        if tok.dep_ == 'pcomp':
            vetoes.add(tok.idx)
        elif tok.dep_ == 'aux':
            head = tok.head
            inside_mention = any(m['start'] <= head.idx < m['end'] if isinstance(m, dict)
                                  else m.start <= head.idx < m.end for m in mentions)
            if not inside_mention:
                vetoes.add(tok.idx)
    return vetoes


def _cue_before(text, mention_start, clause_start, prev_end, vetoes=frozenset()):
    """Return the relation cue immediately before this mention -- immediately
    meaning nothing but whitespace sits between the cue word and the mention,
    not merely "the closest cue found anywhere earlier in the clause".

    That distinction matters: "kindly avoid this route to take Ring Road" has
    "to" in it well before "Ring Road", but "take" sits in between, so "to" is
    not describing Ring Road as a destination. A window-wide nearest-match scan
    would wrongly attach "to" to "Ring Road" regardless of "take" sitting
    between them; requiring adjacency catches this without a phrase blacklist.
    `vetoes` (see dependency_vetoes) catches the remaining case adjacency alone
    cannot: "due to" and "up to" both put a real mention immediately after "to",
    same as a genuine destination would.

    If the gap since the previous mention in this clause is only a bare separator
    (",", "&", "and" -- a list continuation, e.g. "via A, B and C"), the cue is not
    re-searched at all: the previous mention's cue carries over, since a comma
    here is a list continuation, not a fresh unstated relation.
    """
    if prev_end is not None and _BARE_SEPARATOR.match(text[prev_end:mention_start]):
        return 'CONTINUE'
    window = text[clause_start:mention_start]
    for cue, pattern in _CUE_PATTERNS:
        match = re.search(pattern + r'\s*$', window, re.I)
        if match and (clause_start + match.start()) in vetoes:
            continue  # e.g. this "to" is 'due to' or infinitival -- try the next pattern
        if match:
            return cue
    return None


def _is_conjunction_only(text, start, end):
    return bool(_CONJUNCTION.match(text[start:end]))


def assign_roles(text, mentions, doc=None):
    """Assign a role to each mention and build the relations between them.

    mentions: iterable of Mention (or objects/dicts with start/end/text/feature_type)
              in any order; spans must not overlap.
    doc: optional spaCy Doc for `text` (from the notebook's own nlp_tweet, or any
         pipeline with a dependency parser). When supplied, dependency_vetoes(doc)
         disambiguates "to"/"towards" precisely (see that function); when omitted,
         only the weaker adjacency check applies and a small, real class of cases
         ("due to X", "up to X") will still be misread as directional.
    Returns (mentions, relations, route_clause_count) -- mentions is a new list,
    ordered by position in `text` and numbered 1..N (consecutive, no gaps or reuse,
    matching the translation bake-off's alignment schema); relations reference that
    numbering, never raw spans.
    """
    vetoes = dependency_vetoes(doc, mentions) if doc is not None else frozenset()
    normalized = []
    for m in mentions:
        if isinstance(m, Mention):
            normalized.append(Mention(m.start, m.end, m.text, m.feature_type))
        else:
            normalized.append(Mention(m['start'], m['end'], m['text'], m.get('feature_type', 'unknown')))
    normalized.sort(key=lambda m: m.start)
    for order, m in enumerate(normalized, 1):
        m.mention_order = order

    clauses = _clause_spans(text)

    def clause_of(pos):
        for start, end in clauses:
            if start <= pos < end:
                return start, end
        return clauses[-1]

    relations = []
    # Per clause: the most recent ORIGIN/DESTINATION/road/pending-between mention,
    # so "near X", list continuations ("A, B and C") and "X between A and B" can
    # attach to something instead of floating free.
    clause_state = {}

    def apply_cue(cue, m, state):
        """One code path per cue, shared by a direct match and a 'CONTINUE' list
        continuation -- so "via A, B and C" assigns B and C the same role as A
        without a second, divergent implementation to fall out of sync with this
        one.
        """
        if cue == 'from':
            m.role = ORIGIN
            state['last_endpoint'] = m.mention_order
        elif cue in ('towards', 'to'):
            m.role = DESTINATION
            if state['last_endpoint'] is not None:
                relations.append(Relation(cue if cue != 'to' else 'to', state['last_endpoint'], m.mention_order))
            state['last_endpoint'] = m.mention_order
        elif cue in ('via', 'through'):
            m.role = VIA_ROAD if m.feature_type in ROAD_FEATURES else VIA_POINT
            if state['last_endpoint'] is not None:
                relations.append(Relation('via', state['last_endpoint'], m.mention_order))
            # A destination stated after a via-mention links to the via mention,
            # not the original origin, because this leaves last_endpoint on m.
            state['last_endpoint'] = m.mention_order
        elif cue == 'between':
            m.role = SEGMENT_BOUND
            if state['last_between'] is not None:
                relations.append(Relation('between', state['last_between'], m.mention_order))
                state['last_between'] = None
            else:
                state['last_between'] = m.mention_order
        elif cue == 'on':
            if m.feature_type in ROAD_FEATURES:
                m.role = NAMED_ROAD
            elif m.feature_type in POINT_FEATURES and m.feature_type != 'unknown':
                m.role = POINT
            else:
                m.role = NAMED_ROAD
                m.uncertain = True  # 'on X' with no feature-type evidence either way
            state['last_endpoint'] = state['last_endpoint'] or m.mention_order
        elif cue == 'near':
            m.role = LANDMARK
            if state['last_endpoint'] is not None:
                relations.append(Relation('near', m.mention_order, state['last_endpoint']))
            elif state['last_road'] is not None:
                relations.append(Relation('near', m.mention_order, state['last_road']))
        elif cue == 'under':
            m.role = LANDMARK
            if state['last_endpoint'] is not None:
                relations.append(Relation('under', m.mention_order, state['last_endpoint']))
        elif cue == 'at':
            # No from/to/road seen yet in this clause: a bare "at X" names the
            # whole event's location, not a route -- e.g. "Traffic is normal at
            # Chirag Delhi" is a single point, never a fabricated one-mention
            # route (Reviewer 1's Table 1 point-vs-line example).
            if state['last_endpoint'] is None and state['last_road'] is None:
                m.role = POINT
            else:
                m.role = LANDMARK
                if state['last_endpoint'] is not None:
                    relations.append(Relation('at', m.mention_order, state['last_endpoint']))
        if m.role == NAMED_ROAD:
            state['last_road'] = m.mention_order

    for m in normalized:
        if _is_conjunction_only(text, m.start, m.end):
            continue
        c_start, c_end = clause_of(m.start)
        state = clause_state.setdefault((c_start, c_end),
            {'last_endpoint': None, 'last_road': None, 'last_between': None, 'last_cue': None, 'prev_end': None})
        cue = _cue_before(text, m.start, c_start, state['prev_end'], vetoes)
        state['prev_end'] = m.end

        if cue == 'CONTINUE':
            cue = state['last_cue']
        if cue is not None:
            state['last_cue'] = cue
            apply_cue(cue, m, state)
            continue

        # No cue at all. Two real corpus patterns land here: a bare named road
        # ("X is closed due to...") with nothing before it, or -- very common in
        # this corpus -- an implicit origin with no "from" ("BRT towards Press
        # Enclave Road"). Distinguished by reusing _cue_before on the *next*
        # mention rather than a second, separately-adjacent-checked scan: if
        # that mention's own cue resolves to "to"/"towards", it is this
        # mention's destination and this mention is its implicit origin.
        next_in_clause = next((mm for mm in normalized if mm.start >= m.end and clause_of(mm.start) == (c_start, c_end)), None)
        is_clause_first = state['last_endpoint'] is None and state['last_road'] is None and state['last_between'] is None
        next_cue = _cue_before(text, next_in_clause.start, c_start, m.end, vetoes) if next_in_clause else None
        if is_clause_first and next_cue in ('to', 'towards'):
            m.role, m.uncertain = ORIGIN, True
            state['last_endpoint'] = m.mention_order
        else:
            m.role = NAMED_ROAD if m.feature_type in ROAD_FEATURES else POINT
            m.uncertain = True
            if m.role == NAMED_ROAD:
                state['last_road'] = m.mention_order

    route_clause_count = sum(
        1 for c_start, c_end in clauses
        if any(c_start <= m.start < c_end for m in normalized)
    )
    return normalized, relations, route_clause_count


def to_dict(mentions, relations, route_clause_count):
    """JSON-friendly projection, field names matching the translation bake-off's
    structured-alignment schema so both can share downstream tooling.
    """
    return {
        'place_mentions': [
            {'text': m.text, 'mention_order': m.mention_order, 'role': m.role,
             'feature_type': m.feature_type, 'uncertain': m.uncertain}
            for m in mentions
        ],
        'spatial_relations': [
            {'relation': r.relation, 'source_mention_order': r.source_mention_order,
             'target_mention_order': r.target_mention_order, 'uncertain': r.uncertain}
            for r in relations
        ],
        'route_clause_count': route_clause_count,
    }
