import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock
from PIL import Image
from newsbot.config import Config, ROOT, now
from newsbot.demo import example_story, example_draft, create_demo
from newsbot.models import validate_story, validate_draft, duplicate
from newsbot.store import Store
from newsbot.app import App
from newsbot.editor import consulted_urls


class NewsroomTests(unittest.TestCase):
    def setUp(self):
        test_root = ROOT / 'data' / 'test-temp'
        test_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=test_root)
        self.root = Path(self.temp.name)
        assert self.root.resolve().is_relative_to(test_root.resolve())
        self.store = Store(self.root / 'test.sqlite3')
        self.story = example_story()
        self.ident = self.store.add(self.story)
        self.tg, self.editor = Mock(), Mock()
        self.config = Config('test', 'a-secure-local-pairing-code')
        self.app = App(self.config, self.store, self.editor, self.tg, self.root / 'output')

    def tearDown(self):
        self.temp.cleanup()

    def update(self, uid=10, text='/start a-secure-local-pairing-code', number=1):
        return {'update_id': number, 'message': {'from': {'id': uid}, 'chat': {'id': uid, 'type': 'private'}, 'text': text}}

    def pair(self):
        self.app.handle(self.update())
        self.tg.reset_mock()

    def test_pairing_and_owner_lock(self):
        self.app.handle(self.update(text='/start wrong'))
        self.assertEqual(self.app.owner(), '')
        self.pair()
        self.app.handle(self.update(uid=20, text='/cari'))
        self.assertIsNone(self.store.claim())
        self.tg.send.assert_not_called()

    def test_duplicate_articles_and_tracking_urls(self):
        copied = self.story.model_copy(deep=True)
        copied.event_key = 'different-slug'
        copied.sources[0].url += '?utm_source=other'
        self.assertTrue(duplicate(self.story, copied))
        self.assertIsNone(self.store.add(copied))

    def test_rejects_unconsulted_source(self):
        with self.assertRaises(ValueError):
            validate_story(self.story, ['https://other.example/'])

    def test_rejects_old_event_reposted_today(self):
        self.story.event_at = (now() - timedelta(days=7)).isoformat()
        with self.assertRaises(ValueError):
            validate_story(self.story, ['https://example.com/simulasi'])

    def test_rejects_syndication_as_independent(self):
        self.story.sources[0].primary = False
        self.story.sources.append(self.story.sources[0].model_copy())
        with self.assertRaises(ValueError):
            validate_story(self.story, ['https://example.com/simulasi'])

    def test_rejects_missing_fact_evidence(self):
        self.story.facts[0].source_urls = ['https://example.com/other']
        with self.assertRaises(ValueError):
            validate_story(self.story, ['https://example.com/simulasi'])

    def test_double_click_creates_one_job(self):
        self.pair()
        self.app.action(f'build:{self.ident}:1')
        self.app.action(f'build:{self.ident}:1')
        self.assertIsNotNone(self.store.claim())
        self.assertIsNone(self.store.claim())

    def test_old_button_rejected(self):
        self.pair()
        self.store.update(self.ident, version=2)
        self.app.action(f'build:{self.ident}:1')
        self.assertIsNone(self.store.claim())

    def test_changed_fact_requires_new_approval(self):
        self.pair()
        self.editor.recheck.return_value = Mock(material_change=True, story=self.story, explanation='Ada koreksi angka.')
        self.app.action(f'build:{self.ident}:1')
        self.app.work_once()
        row = self.store.story(self.ident)
        self.assertEqual(row['version'], 2)
        self.assertEqual(row['status'], 'candidate')
        self.editor.produce.assert_not_called()

    def test_complete_approval_preview_final_flow(self):
        self.pair()
        self.editor.recheck.return_value = Mock(material_change=False, story=self.story)
        self.editor.produce.return_value = example_draft()
        self.app.action(f'build:{self.ident}:1')
        self.app.work_once()
        row = self.store.story(self.ident)
        self.assertEqual(row['status'], 'preview')
        self.assertTrue(Path(row['package']).exists())
        self.app.action(f'final:{self.ident}:1')
        self.app.work_once()
        self.assertEqual(self.store.story(self.ident)['status'], 'final')
        self.assertEqual(self.editor.produce.call_count, 1)
        self.assertEqual(self.editor.recheck.call_count, 2)

    def test_cancel_during_research_discards_result(self):
        self.pair()
        def cancel(_):
            self.app.action(f'cancel:{self.ident}:1')
            return Mock(material_change=False, story=self.story)
        self.editor.recheck.side_effect = cancel
        self.app.action(f'build:{self.ident}:1')
        self.app.work_once()
        self.assertEqual(self.store.story(self.ident)['status'], 'cancelled')
        self.editor.produce.assert_not_called()

    def test_limit_reserves_failed_calls_too(self):
        self.store.reserve_call('search', 1)
        with self.assertRaises(ValueError):
            self.store.reserve_call('search', 1)

    def test_recovery_requires_manual_retry(self):
        self.store.enqueue('job', 'build', self.ident, 1)
        self.store.claim()
        self.store.update(self.ident, status='working')
        self.assertEqual(self.store.recover(), 1)
        self.assertIsNone(self.store.claim())
        self.store.failed_retry(self.ident, 1)
        self.assertIsNotNone(self.store.claim())

    def test_schedule_quiet_hours_and_pause(self):
        self.pair()
        self.app.tick(now().replace(hour=23, minute=0))
        self.assertIsNone(self.store.claim())
        self.store.set('paused', 1)
        self.app.tick(now().replace(hour=12, minute=30))
        self.assertIsNone(self.store.claim())

    def test_schedule_slot_is_deduplicated(self):
        self.pair()
        clock = now().replace(hour=10, minute=5)
        self.app.tick(clock)
        self.app.tick(clock)
        self.assertIsNotNone(self.store.claim())
        self.assertIsNone(self.store.claim())

    def test_draft_requires_valid_fact_ids(self):
        draft = example_draft()
        draft.slides[0].fact_ids = ['invented']
        with self.assertRaises(ValueError):
            validate_draft(draft, self.story)

    def test_render_and_long_text_fit(self):
        draft = example_draft()
        draft.slides[0].title = 'Kebijakan perekonomian Indonesia mengalami perubahan yang perlu dicermati investor'
        draft.slides[0].body = 'Ekonomi dan investasi membutuhkan sumber yang akurat. ' * 6
        from newsbot.render import render_package
        paths, bundle = render_package(self.story, draft, self.root / 'render', 'ARUS', 1, 1)
        self.assertTrue(bundle.exists())
        with Image.open(paths[0]) as image:
            self.assertEqual(image.size, (1080, 1350))

    def test_sources_only_from_tool_metadata(self):
        response = Mock()
        response.model_dump.return_value = {'output': [
            {'type': 'web_search_call', 'action': {'sources': [{'url': 'https://example.com/real'}]}},
            {'type': 'message', 'content': [{'text': 'https://fake.example/invented', 'annotations': []}]}]}
        self.assertEqual(consulted_urls(response), {'https://example.com/real'})

    def test_scan_failure_is_not_reported_as_no_news(self):
        self.pair()
        self.editor.scan.side_effect = RuntimeError('fail')
        self.store.enqueue('manual', 'scan', payload='notify')
        self.app.work_once()
        self.assertEqual(self.store.get('last_scan'), '')
        self.assertIn('Proses belum selesai', self.tg.send.call_args.args[1])

    def test_candidate_limit_and_no_repeat(self):
        self.pair()
        self.config.daily_candidates = 1
        self.assertEqual(self.app.deliver_candidates(), 1)
        self.assertEqual(self.app.deliver_candidates(), 0)


if __name__ == '__main__':
    unittest.main()
