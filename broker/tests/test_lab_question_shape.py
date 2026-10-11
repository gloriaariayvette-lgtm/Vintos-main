#!/usr/bin/env python3
"""Two shapes of question the identity check refused on 11 October, both of them answerable.

09:22, "the C2 domain in human Synaptotagmin-1 (Syt1)": C2 was demanded of the retrieved record as though it named
the target. A domain whose owner the question names is the feature asked about, not the target.
09:29, "bacteriophage reverse transcriptases (RTs) associated with CRISPR arrays": every row was refused for not
being named exactly the requested phrase, and the rows together as "multiple retrieved targets". The discovery lanes
screen a class, where several records are the point. The protein lane is unchanged.
Scratch workspace; the model and every sender are stubs; sockets and processes are refused."""
from pathlib import Path
import os, socket, subprocess, sys, tempfile, unittest
scratch = tempfile.TemporaryDirectory(prefix='lab-question-shape-')
os.environ.update(HOME=scratch.name, SPARK_WORKSPACE=scratch.name + '/workspace', VINTOS_SECRETS=scratch.name + '/secrets')
NET = []
def forbidden(*a, **k):
    NET.append(a); raise AssertionError('External operation forbidden')
socket.socket.connect = forbidden; socket.create_connection = forbidden; subprocess.Popen = forbidden
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import chemistry_lab as C
from lab_sources import question_entity_context as entity, human_question_symbols as symbols
C._ask = forbidden; C.urllib.request.urlopen = forbidden

SYT1 = {'question': ('What are the structural features of the C2 domain in human Synaptotagmin-1 (Syt1) and how does '
                     'its calcium-binding site coordination facilitate its role in rapid vesicle fusion?'),
        'uniprot_query': 'gene:SYT1 AND organism_id:9606 AND reviewed:true', 'browse_lane': 'protein'}
SYT1_RECORD = {'accession': 'P21579', 'protein_name': 'Synaptotagmin-1', 'taxon_id': 9606,
               'organism': 'Homo sapiens', 'genes': [{'geneName': {'value': 'SYT1'}}]}
PHAGE = {'question': ('What are the structural characteristics and genomic context of bacteriophage reverse '
                      'transcriptases (RTs) that are associated with CRISPR arrays?'),
         'uniprot_query': 'protein_name:"reverse transcriptase" AND taxonomy_id:10239', 'browse_lane': 'genome_mining'}
def phage(accession, name):
    return {'accession': accession, 'protein_name': name, 'taxon_id': 10239, 'organism': 'Caudoviricetes sp.'}

class QuestionShape(unittest.TestCase):
    def test_the_store_is_scratch_and_nothing_reaches_the_world(self):
        self.assertTrue(C.ROOT.startswith(scratch.name), C.ROOT)
        self.assertIs(C._ask, forbidden); self.assertIs(socket.socket.connect, forbidden); self.assertEqual(NET, [])

    def test_a_domain_whose_owner_is_named_is_not_the_target(self):
        self.assertEqual(symbols(SYT1['question']), [])
        self.assertEqual(symbols('the STAS domain in human Pendrin'), [])
        got = entity(SYT1, [SYT1_RECORD])
        self.assertEqual(got['status'], 'consistent', got)

    def test_a_domain_with_no_owner_named_is_still_the_target(self):
        self.assertEqual(symbols('What is the structural role of the BRCA1 domain?'), ['BRCA1'])
        self.assertEqual(symbols('the HR1 domain in human cells'), ['HR1'])        # a place is not an owner
        self.assertEqual(symbols('the SH3 domain-containing protein SH3BP2'), ['SH3', 'SH3BP2'])

    def test_the_wrong_record_is_still_refused_for_that_question(self):
        wrong = entity(SYT1, [{'accession': 'Q9BSJ8', 'protein_name': 'Extended synaptotagmin-1', 'taxon_id': 9606,
                               'organism': 'Homo sapiens', 'genes': [{'geneName': {'value': 'ESYT1'}}]}])
        self.assertEqual(wrong['status'], 'unresolved')
        self.assertIn('SYT1', '; '.join(wrong['issues']))

    def test_a_class_screen_keeps_the_rows_that_are_members(self):
        got = entity(PHAGE, [phage('A1', 'Group II intron reverse transcriptase/maturase'),
                             phage('A2', 'Putative reverse transcriptase family protein'),
                             phage('A3', 'Tail fiber protein')])
        self.assertEqual(got['status'], 'consistent', got)
        self.assertEqual(got['selected_accessions'], ['A1', 'A2'])   # the tail fiber is not a member

    def test_a_class_screen_with_no_member_at_all_is_still_refused(self):
        got = entity(PHAGE, [phage('A3', 'Tail fiber protein'), phage('A4', 'Major capsid protein')])
        self.assertEqual(got['status'], 'unresolved')
        self.assertIn('not established by the retrieved recommended name', '; '.join(got['issues']))

    def test_the_protein_lane_is_unchanged(self):
        single = {'question': 'What is the structural organization of the human calcium sensing receptor?',
                  'uniprot_query': 'protein_name:"calcium sensing receptor" AND taxonomy_id:9606', 'browse_lane': 'protein'}
        row = {'accession': 'P41180', 'protein_name': 'Extracellular calcium-sensing receptor', 'taxon_id': 9606}
        self.assertEqual(entity(single, [row])['status'], 'unresolved')
        two = dict(single, question='What is the structural organization of the human calcium sensing receptor?')
        self.assertIn('multiple retrieved targets', '; '.join(entity(two, [row, dict(row, accession='Q9NZ08')])['issues']))

    def test_an_exact_record_name_does_not_invent_a_second_target_from_its_suffix(self):
        cases = [
            ('Q51817', 'Lys-gingipain W83', 'Porphyromonas gingivalis'),
            ('P95493', 'Gingipain R2', 'Porphyromonas gingivalis (strain ATCC BAA-308 / W83)'),
        ]
        for accession, name, organism in cases:
            question = ('What does the curated UniProt record for %s (%s) establish about its organism, sequence '
                        'length, annotated domains, and membrane topology?' % (name, accession))
            got = entity({'question': question, 'uniprot_query': 'accession:' + accession},
                         [{'accession': accession, 'protein_name': name, 'organism': organism}])
            self.assertEqual(got['status'], 'consistent', got)

    def test_exact_accession_does_not_excuse_a_mismatched_name_or_gene_claim(self):
        row = {'accession': 'Q51817', 'protein_name': 'Lys-gingipain W83',
               'organism': 'Porphyromonas gingivalis'}
        wrong = entity({'question': 'What does Gingipain R2 (Q51817) establish?',
                        'uniprot_query': 'accession:Q51817'}, [row])
        self.assertEqual(wrong['status'], 'unresolved', wrong)
        self.assertIn('R2', '; '.join(wrong['issues']))
        explicit_gene = entity({'question': 'What does Lys-gingipain W83 (Q51817) establish?',
                                'uniprot_query': 'accession:Q51817 AND gene:W83'}, [row])
        self.assertEqual(explicit_gene['status'], 'unresolved', explicit_gene)
        self.assertIn('W83', '; '.join(explicit_gene['issues']))

    def test_a_ten_character_uniprot_accession_is_the_record_id_not_a_second_target(self):
        accession = 'A0A6B8MBU4'
        question = ('What does the curated UniProt record for Lipoyl synthase (%s) establish about its organism, '
                    'sequence length, annotated domains, and membrane topology?' % accession)
        self.assertNotIn(accession, symbols(question))
        got = entity({'question': question, 'uniprot_query': 'reviewed:true AND (accession:%s)' % accession},
                     [{'accession': accession, 'protein_name': 'Lipoyl synthase',
                       'organism': 'Candidatus Prometheoarchaeum syntrophicum'}])
        self.assertEqual(got['status'], 'consistent', got)

if __name__ == '__main__':
    unittest.main()
