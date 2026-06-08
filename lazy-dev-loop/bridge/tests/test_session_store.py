import json
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import session_store as ss


class TestSessionStore(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.orig_dir = ss.STORE_DIR
        ss.STORE_DIR = Path(self.tmpdir)

    def tearDown(self):
        ss.STORE_DIR = self.orig_dir
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_create_session(self):
        data = ss.create_session("sess_001", {"workspace": "C:\\test"}, 14096)
        self.assertEqual(data["session_id"], "sess_001")
        self.assertEqual(data["port"], 14096)
        self.assertEqual(data["messages"], [])
        self.assertIsNone(data["finished_at"])
        self.assertFalse(data["archived"])

    def test_append_user_message(self):
        ss.create_session("sess_002", {"workspace": "C:\\test"}, 14096)
        entry = ss.append_message("sess_002", "user", "Hello")
        self.assertEqual(entry["role"], "user")
        self.assertEqual(entry["content"], "Hello")
        self.assertIn("timestamp", entry)

        saved = ss.get_session("sess_002")
        self.assertEqual(len(saved["messages"]), 1)
        self.assertEqual(saved["metadata"]["total_prompts"], 1)

    def test_append_assistant_message(self):
        ss.create_session("sess_003", {"workspace": "C:\\test"}, 14096)
        ss.append_message("sess_003", "user", "Explain")
        ss.append_message("sess_003", "assistant", "This is a response")
        saved = ss.get_session("sess_003")
        self.assertEqual(len(saved["messages"]), 2)
        self.assertEqual(saved["messages"][0]["role"], "user")
        self.assertEqual(saved["messages"][1]["role"], "assistant")
        self.assertEqual(saved["metadata"]["total_prompts"], 1)

    def test_finalize_session(self):
        ss.create_session("sess_004", {"workspace": "C:\\test"}, 14096)
        result = ss.finalize_session("sess_004")
        self.assertIsNotNone(result["finished_at"])
        saved = ss.get_session("sess_004")
        self.assertIsNotNone(saved["finished_at"])

    def test_archive_session(self):
        ss.create_session("sess_005", {"workspace": "C:\\test"}, 14096)
        ss.archive_session("sess_005")
        saved = ss.get_session("sess_005")
        self.assertTrue(saved["archived"])

    def test_list_sessions(self):
        ss.create_session("sess_a", {"workspace": "C:\\a"}, 14096)
        ss.create_session("sess_b", {"workspace": "C:\\b"}, 14096)
        ss.append_message("sess_a", "user", "Hi")
        lst = ss.list_sessions()
        self.assertEqual(len(lst), 2)
        ids = [s["session_id"] for s in lst]
        self.assertIn("sess_a", ids)
        self.assertIn("sess_b", ids)

    def test_get_nonexistent_session(self):
        self.assertIsNone(ss.get_session("nonexistent"))

    def test_delete_session(self):
        ss.create_session("sess_del", {"workspace": "C:\\test"}, 14096)
        self.assertTrue(ss.delete_session("sess_del"))
        self.assertFalse(ss.delete_session("nonexistent"))

    def test_messages_persist_on_disk(self):
        ss.create_session("sess_disk", {"workspace": "C:\\test"}, 14096)
        ss.append_message("sess_disk", "user", "prompt 1")
        ss.append_message("sess_disk", "assistant", "response 1")
        ss.append_message("sess_disk", "user", "prompt 2")
        data = json.loads((Path(self.tmpdir) / "sess_disk.json").read_text())
        self.assertEqual(len(data["messages"]), 3)
        self.assertEqual(data["metadata"]["total_prompts"], 2)

    def test_list_only_returns_summary(self):
        ss.create_session("sess_sum", {"workspace": "C:\\sum"}, 14096)
        ss.append_message("sess_sum", "user", "hello")
        lst = ss.list_sessions()
        self.assertIn("session_id", lst[0])
        self.assertIn("total_prompts", lst[0])
        self.assertNotIn("messages", lst[0])


if __name__ == "__main__":
    unittest.main()
