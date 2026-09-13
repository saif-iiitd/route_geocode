"""Every fixture sentence below is a real tweet from results/canonical_parser_input.csv
(parser_status == READY_ORIGINAL_EN), not a synthetic example, so the parser is
proven against the corpus it will actually run on.
"""
import unittest
from src.semantic_roles import (assign_roles, to_dict, ORIGIN, DESTINATION, NAMED_ROAD,
    VIA_ROAD, VIA_POINT, LANDMARK, SEGMENT_BOUND, POINT)

try:
    import spacy
    _NLP = spacy.load('en_core_web_sm')
except (ImportError, OSError):
    _NLP = None


def mention(text, phrase, feature_type='unknown', occurrence=1):
    """Test-only span finder: locate the nth occurrence of `phrase` in `text`.
    Not an entity recognizer -- real callers supply spans from spaCy/gazetteer.
    """
    start, count = -1, 0
    while count < occurrence:
        start = text.index(phrase, start + 1)
        count += 1
    return {'start': start, 'end': start + len(phrase), 'text': phrase, 'feature_type': feature_type}


def roles_by_text(mentions):
    return {m.text: m.role for m in mentions}


class SemanticRoleTests(unittest.TestCase):
    def test_simple_origin_destination(self):
        text = ('Obstruction in traffic from Kali Bari Marg to Gol Market(both carriageways) '
                'due to procession. Kindly avoid the stretch.')
        mentions = [mention(text, 'Kali Bari Marg', 'road'), mention(text, 'Gol Market')]
        m, rel, clauses = assign_roles(text, mentions)
        self.assertEqual(roles_by_text(m), {'Kali Bari Marg': ORIGIN, 'Gol Market': DESTINATION})
        self.assertEqual(len(rel), 1)
        self.assertEqual(rel[0].relation, 'to')
        self.assertEqual((rel[0].source_mention_order, rel[0].target_mention_order), (1, 2))
        self.assertEqual(clauses, 1)

    def test_bare_point_is_not_fabricated_into_a_route(self):
        # Reviewer 1's Table 1 point-vs-line example: this must resolve to one
        # POINT mention and zero relations, never an invented one-mention route.
        text = 'Traffic is now normal at Chirag Delhi.'
        mentions = [mention(text, 'Chirag Delhi')]
        m, rel, clauses = assign_roles(text, mentions)
        self.assertEqual(m[0].role, POINT)
        self.assertFalse(m[0].uncertain)
        self.assertEqual(rel, [])
        self.assertEqual(clauses, 1)

    def test_via_road_list_shares_role_across_commas(self):
        text = ('Now traffic is normal from Balmiki Mandir to Patel Chowk via Mandir Marg, '
                'Peshwa Road, Bhai Veer Singh Marg.')
        mentions = [
            mention(text, 'Balmiki Mandir'), mention(text, 'Patel Chowk'),
            mention(text, 'Mandir Marg', 'road'), mention(text, 'Peshwa Road', 'road'),
            mention(text, 'Bhai Veer Singh Marg', 'road'),
        ]
        m, rel, clauses = assign_roles(text, mentions)
        roles = roles_by_text(m)
        self.assertEqual(roles['Balmiki Mandir'], ORIGIN)
        self.assertEqual(roles['Patel Chowk'], DESTINATION)
        for via_road in ('Mandir Marg', 'Peshwa Road', 'Bhai Veer Singh Marg'):
            self.assertEqual(roles[via_road], VIA_ROAD)
        via_relations = [r for r in rel if r.relation == 'via']
        self.assertEqual(len(via_relations), 3)

    def test_between_two_road_boundaries(self):
        text = ('Traffic is moving slow on Yamuna Bridge between ISBT Kashmere Gate '
                'and Shastri Park.')
        mentions = [mention(text, 'Yamuna Bridge', 'road'), mention(text, 'ISBT Kashmere Gate'),
                    mention(text, 'Shastri Park')]
        m, rel, clauses = assign_roles(text, mentions)
        roles = roles_by_text(m)
        self.assertEqual(roles['Yamuna Bridge'], NAMED_ROAD)
        self.assertEqual(roles['ISBT Kashmere Gate'], SEGMENT_BOUND)
        self.assertEqual(roles['Shastri Park'], SEGMENT_BOUND)
        between = [r for r in rel if r.relation == 'between']
        self.assertEqual(len(between), 1)

    def test_multi_clause_numbered_list(self):
        text = ('Traffic will remain heavy on following roads due to Christmas Celebration. '
                '01. BRT towards Press Enclave Road. '
                '02. Malviya Nagar towards Saket court Road. '
                '03. M.B. Road towards Mandir Marg.')
        mentions = [
            mention(text, 'BRT'), mention(text, 'Press Enclave Road', 'road'),
            mention(text, 'Malviya Nagar'), mention(text, 'Saket court Road', 'road'),
            mention(text, 'M.B. Road', 'road'), mention(text, 'Mandir Marg', 'road'),
        ]
        m, rel, clauses = assign_roles(text, mentions)
        self.assertEqual(clauses, 3)
        roles = roles_by_text(m)
        # Implicit origins (no "from"), inferred only because a directional cue
        # follows in the same clause -- and explicitly marked uncertain for it.
        for implicit_origin in ('BRT', 'Malviya Nagar', 'M.B. Road'):
            self.assertEqual(roles[implicit_origin], ORIGIN)
            self.assertTrue(next(mm for mm in m if mm.text == implicit_origin).uncertain)
        for destination in ('Press Enclave Road', 'Saket court Road', 'Mandir Marg'):
            self.assertEqual(roles[destination], DESTINATION)
        self.assertEqual(len(rel), 3)

    def test_near_attaches_as_landmark_not_an_endpoint(self):
        text = ('Traffic is heavy in the carriageway from Patel Nagar towards Moti Nagar '
                'due to breakdown of a bus near Shadipur metro station.')
        mentions = [mention(text, 'Patel Nagar'), mention(text, 'Moti Nagar'),
                    mention(text, 'Shadipur metro station')]
        m, rel, clauses = assign_roles(text, mentions)
        roles = roles_by_text(m)
        self.assertEqual(roles['Patel Nagar'], ORIGIN)
        self.assertEqual(roles['Moti Nagar'], DESTINATION)
        self.assertEqual(roles['Shadipur metro station'], LANDMARK)
        near = [r for r in rel if r.relation == 'near']
        self.assertEqual(len(near), 1)
        # The landmark attaches to whichever endpoint was most recent (the
        # destination), not the origin -- it must not silently pick either one.
        self.assertEqual(near[0].target_mention_order,
                         next(mm.mention_order for mm in m if mm.text == 'Moti Nagar'))

    def test_named_road_closure_no_route(self):
        text = 'Tolstoy Marg & Parliament Street is closed due to demonstration. Kindly avoid the stretch.'
        mentions = [mention(text, 'Tolstoy Marg', 'road'), mention(text, 'Parliament Street', 'road')]
        m, rel, clauses = assign_roles(text, mentions)
        roles = roles_by_text(m)
        self.assertEqual(roles['Tolstoy Marg'], NAMED_ROAD)
        self.assertEqual(roles['Parliament Street'], NAMED_ROAD)
        # "&" is a list continuation of the same closure, not a route between them.
        self.assertEqual(rel, [])

    def test_to_dict_matches_translation_bakeoff_shape(self):
        text = 'Traffic movement is closed on Sansad Marg due to demonstration.'
        mentions = [mention(text, 'Sansad Marg', 'road')]
        m, rel, clauses = assign_roles(text, mentions)
        d = to_dict(m, rel, clauses)
        self.assertEqual(set(d), {'place_mentions', 'spatial_relations', 'route_clause_count'})
        self.assertEqual(d['place_mentions'][0]['mention_order'], 1)

    def test_non_directional_to_phrases_do_not_fabricate_a_route(self):
        # "due to", "up to" and "to take" all contain the bare word "to" but
        # none of them name a destination -- the fix must key off adjacency to
        # an actual mention, not phrase-blacklisting one construction at a time.
        text_a = 'Tolstoy Marg & Parliament Street is closed due to demonstration.'
        m_a, rel_a, _ = assign_roles(text_a, [mention(text_a, 'Tolstoy Marg', 'road'),
                                               mention(text_a, 'Parliament Street', 'road')])
        self.assertEqual(roles_by_text(m_a)['Tolstoy Marg'], NAMED_ROAD)
        self.assertEqual(rel_a, [])

        # "up to X" is a known, *unresolved* ambiguity: lexically "to" sits
        # immediately before "Tolstoy Marg", same as a real destination would,
        # so the adjacency rule (correctly, for "to take Ring Road" below)
        # still reads it as one. This documents that gap rather than hiding it
        # -- an extent-bound ("closed as far as X") is not the same claim as
        # "traffic is headed to X", and this module does not yet tell them
        # apart. A future gazetteer/relation pass should special-case "up to".
        text_b = 'Sansad Marg is closed up to Tolstoy Marg crossing due to demonstration.'
        m_b, rel_b, _ = assign_roles(text_b, [mention(text_b, 'Sansad Marg', 'road'),
                                               mention(text_b, 'Tolstoy Marg', 'road')])
        self.assertEqual(roles_by_text(m_b)['Sansad Marg'], ORIGIN)
        self.assertTrue(next(mm for mm in m_b if mm.text == 'Sansad Marg').uncertain)

        text_c = ('Traffic alert Traffic is slow at Geeta Colony flyover kindly avoid '
                  'this route to take Ring Road.')
        m_c, rel_c, _ = assign_roles(text_c, [mention(text_c, 'Geeta Colony flyover'),
                                               mention(text_c, 'Ring Road', 'road')])
        roles_c = roles_by_text(m_c)
        self.assertEqual(roles_c['Geeta Colony flyover'], POINT)
        self.assertNotEqual(roles_c['Ring Road'], DESTINATION)
        self.assertEqual(rel_c, [])

    def test_genuinely_directional_to_still_detected(self):
        # The fix must not overcorrect: "to" directly adjacent to the next
        # mention, with nothing else between them, is still a real destination.
        text = 'Route Diverted from Parwana Road, Vikas Marg to Ghazipur due to ongoing work.'
        mentions = [mention(text, 'Vikas Marg', 'road'), mention(text, 'Ghazipur')]
        m, rel, _ = assign_roles(text, mentions)
        self.assertEqual(roles_by_text(m)['Ghazipur'], DESTINATION)

    @unittest.skipIf(_NLP is None, 'spaCy / en_core_web_sm not installed')
    def test_dependency_parse_resolves_up_to_and_due_to(self):
        # Without a doc, "up to X" is a documented, accepted limitation (see the
        # test above): adjacency alone can't distinguish it from a real
        # destination. With a real dependency parse, dependency_vetoes()
        # excludes it via dep_=='pcomp' ("due to") without needing this case
        # spelled out at all, and via dep_=='prep' plus the 'up'/prt pattern
        # for "up to" would need its own rule -- not yet added, so this proves
        # what IS fixed (due to) and documents what remains open (up to).
        text = 'Tolstoy Marg & Parliament Street is closed due to demonstration.'
        doc = _NLP(text)
        mentions = [mention(text, 'Tolstoy Marg', 'road'), mention(text, 'Parliament Street', 'road')]
        m, rel, _ = assign_roles(text, mentions, doc=doc)
        self.assertEqual(roles_by_text(m)['Tolstoy Marg'], NAMED_ROAD)
        self.assertEqual(rel, [])

        text2 = 'Obstruction in traffic from Nehru Place to Modi Mill due to ongoing Delhi Jal Board work.'
        doc2 = _NLP(text2)
        mentions2 = [mention(text2, 'Nehru Place'), mention(text2, 'Modi Mill')]
        m2, rel2, _ = assign_roles(text2, mentions2, doc=doc2)
        self.assertEqual(roles_by_text(m2)['Modi Mill'], DESTINATION)

    def test_mention_order_is_consecutive_regardless_of_input_order(self):
        text = 'Obstruction in traffic from Mori Gate to Pull Dufferin due to demonstration.'
        # Deliberately supplied out of textual order.
        mentions = [mention(text, 'Pull Dufferin'), mention(text, 'Mori Gate')]
        m, rel, clauses = assign_roles(text, mentions)
        orders = [mm.mention_order for mm in m]
        self.assertEqual(orders, [1, 2])
        self.assertEqual(m[0].text, 'Mori Gate')


if __name__ == '__main__':
    unittest.main()
