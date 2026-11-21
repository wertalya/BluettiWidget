"""Offline release-channel, download-origin and update UI checks."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings
from updates import (REPOSITORY, AutoUpdateMonitor, CHECK_INTERVAL_SECONDS,
                     UpdateDialog, check_releases, newer_release, version_key)


def release(tag, **changes):
    item = {'tag_name': tag, 'draft': False, 'prerelease': '-preview' in tag,
            'assets': [{'name': 'BluettiWidget-Setup.exe', 'state': 'uploaded',
                        'browser_download_url': f'{REPOSITORY}/releases/download/{tag}/BluettiWidget-Setup.exe'}]}
    item.update(changes)
    return item


class UpdateChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

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
        response.__enter__.return_value.read.return_value = json.dumps([release('v0.4.3-preview')]).encode()
        with patch('updates.urlopen', return_value=response) as fetch:
            self.assertEqual(check_releases().version, '0.4.3-preview')
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

    def test_automatic_schedule_is_delayed_and_throttled_across_restarts(self):
        with tempfile.TemporaryDirectory() as tmp, patch('updates.time.time', return_value=100_000), patch('updates.ReleaseCheck.start') as start:
            path = str(Path(tmp) / 'settings.ini')
            settings = QSettings(path, QSettings.Format.IniFormat)
            monitor = AutoUpdateMonitor(settings)
            monitor.start()
            self.assertAlmostEqual(monitor.timer.remainingTime(), 30_000, delta=1000)
            start.assert_not_called()
            monitor.check()
            start.assert_called_once()
            monitor.worker.finished.emit()
            self.assertAlmostEqual(monitor.timer.remainingTime(), CHECK_INTERVAL_SECONDS * 1000, delta=1000)
            monitor.stop()
            restored = AutoUpdateMonitor(QSettings(path, QSettings.Format.IniFormat))
            restored.start()
            self.assertAlmostEqual(restored.timer.remainingTime(), CHECK_INTERVAL_SECONDS * 1000, delta=1000)
            restored.stop()

    def test_disabled_checks_stop_timer_and_ignore_inflight_results(self):
        with tempfile.TemporaryDirectory() as tmp, patch('updates.ReleaseCheck.start') as start:
            monitor = AutoUpdateMonitor(QSettings(str(Path(tmp) / 'settings.ini'), QSettings.Format.IniFormat))
            monitor.start()
            monitor.set_enabled(False)
            self.assertFalse(monitor.timer.isActive())
            found = []
            monitor.notify.connect(found.append)
            monitor.check()
            monitor.on_checked(newer_release([release('v0.5.0')], '0.4.2-preview'))
            start.assert_not_called()
            self.assertEqual(found, [])
            monitor.set_enabled(True)
            self.assertTrue(monitor.timer.isActive())
            monitor.stop()

    def test_available_update_notifies_once_per_version_without_opening_browser(self):
        with tempfile.TemporaryDirectory() as tmp, patch('updates.QDesktopServices.openUrl') as browser:
            settings = QSettings(str(Path(tmp) / 'settings.ini'), QSettings.Format.IniFormat)
            monitor = AutoUpdateMonitor(settings)
            monitor.start()
            found = []
            notices = []
            monitor.available.connect(found.append)
            monitor.notify.connect(notices.append)
            candidate = newer_release([release('v0.5.0')], '0.4.2-preview')
            monitor.on_checked(candidate)
            monitor.on_checked(candidate)
            monitor.on_checked(None)
            self.assertEqual(len(found), 2)
            self.assertEqual(notices, [candidate])
            browser.assert_not_called()
            monitor.stop()
            restored = AutoUpdateMonitor(settings)
            restored.notify.connect(notices.append)
            restored.start()
            restored.on_checked(candidate)
            self.assertEqual(len(notices), 1)
            restored.stop()

    def test_failed_check_reschedules_without_alert_or_overlapping_request(self):
        with tempfile.TemporaryDirectory() as tmp, patch('updates.ReleaseCheck.start') as start:
            monitor = AutoUpdateMonitor(QSettings(str(Path(tmp) / 'settings.ini'), QSettings.Format.IniFormat))
            notices = []
            monitor.notify.connect(notices.append)
            monitor.start()
            monitor.check()
            monitor.worker.failed.emit()
            monitor.worker.finished.emit()
            self.assertEqual(notices, [])
            self.assertGreater(monitor.timer.remainingTime(), (CHECK_INTERVAL_SECONDS - 1) * 1000)
            with patch.object(monitor.worker, 'isRunning', return_value=True):
                monitor.check()
            start.assert_called_once()
            monitor.stop()

    def test_clock_change_or_invalid_timestamp_does_not_block_checks(self):
        with tempfile.TemporaryDirectory() as tmp, patch('updates.time.time', return_value=100_000):
            settings = QSettings(str(Path(tmp) / 'settings.ini'), QSettings.Format.IniFormat)
            monitor = AutoUpdateMonitor(settings)
            for value in ('broken', float('nan'), 999_999):
                settings.setValue('last_automatic_update_check', value)
                monitor.start()
                self.assertAlmostEqual(monitor.timer.remainingTime(), 30_000, delta=1000)
                monitor.stop()


if __name__ == '__main__':
    unittest.main()
