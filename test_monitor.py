import unittest
from unittest.mock import patch
import monitor


class MonitorTests(unittest.TestCase):
    @patch("monitor.send")
    def test_manual_test_does_not_change_state(self, send):
        with patch("monitor.load_state") as state:
            monitor.run("test", "owner/repo", "gh", "bot", "@channel", "sha")
            send.assert_called_once()
            state.assert_not_called()

    @patch("monitor.save_state", return_value="next")
    @patch("monitor.load_state", return_value=(None, None))
    @patch("monitor.tags", return_value=["release-1", "release-2"])
    @patch("monitor.send")
    def test_first_run_seeds_without_message(self, send, tags, load, save):
        monitor.run("check", "owner/repo", "gh", "bot", "@channel", "sha")
        send.assert_not_called()
        save.assert_called_once_with("owner/repo", "gh", {"release-1", "release-2"}, None)

    @patch("monitor.save_state", return_value="newsha")
    @patch("monitor.load_state", return_value=({"release-1"}, "oldsha"))
    @patch("monitor.tags", return_value=["release-1", "release-2"])
    @patch("monitor.send")
    def test_new_tag_is_sent_and_recorded(self, send, tags, load, save):
        monitor.run("check", "owner/repo", "gh", "bot", "@channel", "sha")
        self.assertIn("release-2", send.call_args.args[2])
        save.assert_called_once_with("owner/repo", "gh", {"release-1", "release-2"}, "oldsha")

    @patch("monitor.save_state")
    @patch("monitor.load_state", return_value=({"release-1"}, "oldsha"))
    @patch("monitor.tags", return_value=["release-1", "release-2"])
    @patch("monitor.send", side_effect=ValueError("failed"))
    def test_failed_send_does_not_record_tag(self, send, tags, load, save):
        with self.assertRaises(ValueError):
            monitor.run("check", "owner/repo", "gh", "bot", "@channel", "sha")
        save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
