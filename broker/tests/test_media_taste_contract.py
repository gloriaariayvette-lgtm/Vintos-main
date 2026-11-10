"""Synthetic acceptance cases for the offline media-taste design, no encoders or stores."""
import copy
import importlib.util
from pathlib import Path
import socket
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('media_taste_design', ROOT/'experiments/nonllm-judges/media_taste.py')
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)


class MediaTasteContract(unittest.TestCase):
    def setUp(self):
        self.encoder = dict(id='synthetic-encoder', artifact_sha256='a'*64, dim=3,
                            copied_at='2026-01-01T00:00:00Z', frozen_at='2026-01-01T00:00:00Z',
                            freeze_source='copy_time')
        self.items = [self.item(str(i), i+1) for i in range(1,4)]
        self.candidate = self.item('f', 9)
        self.ratings = [dict(id='synthetic-rating-'+str(i), media_id=r['media_id'],
                            at='2026-01-%02dT12:00:00Z' % (i+2), value='landed',
                            binding='exact_media_revision') for i,r in enumerate(self.items)]
        self.cutoff = '2026-01-08T00:00:00Z'
        self.pins = {}

    def item(self, value, day):
        return dict(media_id='sha256:'+value*64, sha256=value*64, kind='video',
                    created_at='2026-01-%02dT00:00:00Z' % day,
                    encoded_at='2026-01-%02dT01:00:00Z' % day,
                    encoder=copy.deepcopy(self.encoder), vec=[1.,0.,0.])

    def run_case(self):
        # Pure design probe: neither a live read/write nor an encoder/service call is possible.
        with patch('builtins.open', side_effect=AssertionError('I/O forbidden')), \
             patch.object(socket, 'socket', side_effect=AssertionError('network forbidden')):
            return M.assess(self.candidate, self.items, self.ratings, self.encoder, self.pins, self.cutoff)

    def rejected(self): self.assertEqual(self.run_case()['status'], 'abstain')

    def sync_encoder(self):
        for row in self.items+[self.candidate]: row['encoder'] = copy.deepcopy(self.encoder)

    def test_qualified_exact_revisions_produce_only_descriptive_similarity(self):
        before = copy.deepcopy((self.items, self.ratings, self.candidate))
        result = self.run_case()
        self.assertEqual(result['status'], 'diagnostic')
        self.assertEqual(result['references'], 3)
        self.assertEqual(result['mean_cosine'], 1.)
        self.assertFalse(result['predicts_landing'])
        self.assertFalse(result['source_claims_verified'])
        self.assertEqual(before, (self.items, self.ratings, self.candidate))

    def test_vector_angle_changes_similarity(self):
        self.candidate['vec'] = [0.,1.,0.]
        self.assertEqual(self.run_case()['mean_cosine'], 0.)

    def test_path_title_or_short_art_id_cannot_replace_full_revision(self):
        for name in ('art:1234', 'synthetic-title', '/synthetic/file.mp4'):
            self.candidate['media_id'] = name
            self.rejected()

    def test_no_caption_similarity_or_missing_revision_fallback(self):
        self.ratings[0]['media_id'] = 'sha256:'+'e'*64
        self.rejected()

    def test_newer_partly_or_missed_cancels_prior_positive(self):
        for value in ('partly','missed'):
            self.ratings.append(dict(self.ratings[0], id='later', at='2026-01-07T00:00:00Z', value=value))
            self.rejected(); self.ratings.pop()

    def test_future_rating_does_not_cancel_prior_rating_or_supply_anchor(self):
        self.ratings.append(dict(self.ratings[0], id='future', at=self.cutoff, value='missed'))
        self.assertEqual(self.run_case()['status'], 'diagnostic')
        self.ratings[1]['at'] = self.cutoff
        self.rejected()

    def test_duplicate_rows_do_not_increase_reference_count(self):
        self.items *= 2; self.ratings *= 2
        self.assertEqual(self.run_case()['references'], 3)

    def test_conflicting_rating_or_revision_abstains(self):
        self.ratings.append(dict(self.ratings[0], value='missed'))
        self.rejected(); self.ratings.pop()
        self.items.append(dict(self.items[0], vec=[0.,1.,0.]))
        self.rejected()

    def test_tied_ratings_abstain_without_input_order_tiebreak(self):
        self.ratings.append(dict(self.ratings[0], id='tie', value='missed'))
        self.rejected()

    def test_same_item_is_not_its_own_reference(self):
        self.candidate = copy.deepcopy(self.items[0]); self.cutoff = self.candidate['created_at']
        self.rejected()

    def test_single_day_is_sparse(self):
        for r in self.ratings: r['at'] = '2026-01-06T12:00:00Z'
        self.rejected()

    def test_no_cross_kind_call_or_film_frame_pool(self):
        for kind in ('audio', 'call_audio', 'film_frame'):
            self.items[0]['kind'] = kind
            self.rejected()

    def test_raw_existing_rows_cannot_gain_freeze_from_name_or_width(self):
        self.items[0].pop('encoder')
        self.rejected()

    def test_invalid_vectors_are_not_repaired(self):
        for vec in ([0.,0.,0.], [1.,0.], [True,0.,0.], [float('nan'),0.,0.], [float('inf'),0.,0.]):
            self.candidate['vec'] = vec
            self.rejected()

    def test_freeze_later_than_reference_and_late_encoding_refuse(self):
        self.encoder.update(copied_at='2026-01-03T00:00:00Z', frozen_at='2026-01-03T00:00:00Z')
        self.sync_encoder(); self.rejected()
        self.setUp(); self.items[0]['encoded_at'] = self.cutoff; self.rejected()

    def test_published_pin_needs_exact_reviewed_external_artifact(self):
        self.encoder.update(freeze_source='published_artifact', pin_receipt_sha256='b'*64)
        self.sync_encoder(); self.rejected()
        key = (self.encoder['id'], self.encoder['artifact_sha256'])
        self.pins[key] = dict(published_at=self.encoder['frozen_at'], external_pretrained=True,
                              subject_trained=False, receipt_sha256='b'*64)
        self.assertEqual(self.run_case()['status'], 'diagnostic')
        self.pins[key]['subject_trained'] = True; self.rejected()

    def test_unqualified_clocks_binding_and_encoder_mixes_refuse(self):
        self.candidate['created_at'] = '2026-01-09T00:00:00'; self.rejected()
        self.setUp(); self.ratings[0]['binding'] = 'nearest_title'; self.rejected()
        self.setUp(); self.items[0]['encoder']['artifact_sha256'] = 'd'*64; self.rejected()


if __name__ == '__main__': unittest.main()
