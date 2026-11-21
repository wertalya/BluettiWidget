"""Offline release-channel, download-origin and update UI checks."""
import json
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from updates import REPOSITORY, UpdateDialog, check_releases, newer_release, version_key


def release(tag, **changes):
    item = {'tag_name': tag, 'draft': False, 'prerelease': '-preview' in tag,
            'assets': [{'name': 'BluettiWidget-Setup.exe', 'state': 'uploaded',
                        'browser_download_url': f'{REPOSITORY}/releases/download/{tag}/BluettiWidget-Setup.exe'}]}
    item.update(changes)
    return item


class UpdateChecks(unittest.TestCase):
    def test_preview_channel_sorts_versions_and_accepts_stable(self):
        items = [release('v0.4.1-preview'), release('v0.4.0'), release('v0.10.0-preview')]
        self.assertEqual(newer_release(items, '0.4.0-preview').version, '0.10.0-preview')
        self.assertGreater(version_key('0.4.1'), version_key('0.4.1-preview.9'))
        self.assertIsNone(newer_release(items, '0.10.0-preview'))

    def test_stable_users_do_not_receive_preview_or_draft(self):
        items = [release('v0.5.0-preview'), release('v0.5.0', draft=True), release('v0.4.1')]
        self.assertEqual(newer_release(items, '0.4.0').version, '0.4.1')

    def test_release_needs_finished_installer_from_this_repository(self):
        foreign = release('v0.4.1-preview')
        foreign['assets'][0]['browser_download_url'] = 'https://example.com/setup.exe'
        uploading = release('v0.4.2-preview')
        uploading['assets'][0]['state'] = 'uploading'
        self.assertIsNone(newer_release([foreign, uploading, release('v0.5.0', assets=[]),
                                        release('v999.0.0-malformed'), None], '0.4.0-preview'))

    def test_request_does_not_include_settings_or_station_data(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps([release('v0.4.2-preview')]).encode()
        with patch('updates.urlopen', return_value=response) as fetch:
            self.assertEqual(check_releases().version, '0.4.2-preview')
        request = fetch.call_args.args[0]
        self.assertIsNone(request.data)
        self.assertEqual(request.full_url, 'https://api.github.com/repos/wertalya/BluettiWidget/releases?per_page=100')
        self.assertEqual(fetch.call_args.kwargs['timeout'], 10)

    def test_bad_or_oversized_responses_fail_without_download(self):
        for payload in (b'{}', b'invalid', b'x' * 1_000_001):
            with self.subTest(size=len(payload)), patch('updates.urlopen') as fetch:
                fetch.return_value.__enter__.return_value.read.return_value = payload
                with self.assertRaises(ValueError):
                    check_releases()

    def test_download_requires_user_action_and_network_failure_can_retry(self):
        app = QApplication.instance() or QApplication([])
        with patch('updates.ReleaseCheck.start'), patch('updates.QDesktopServices.openUrl', return_value=True) as browser:
            dialog = UpdateDialog()
            self.assertFalse(dialog.download.isEnabled())
            dialog.on_checked(newer_release([release('v0.4.2-preview')], '0.4.1-preview'))
            browser.assert_not_called()
            dialog.download.click()
            self.assertEqual(browser.call_args.args[0].toString(), f'{REPOSITORY}/releases/download/v0.4.2-preview/BluettiWidget-Setup.exe')
            dialog.check()
            dialog.on_failed()
            dialog.worker.finished.emit()
            self.assertTrue(dialog.retry.isEnabled())
            self.assertFalse(dialog.download.isEnabled())
            dialog.close()


if __name__ == '__main__':
    unittest.main()
