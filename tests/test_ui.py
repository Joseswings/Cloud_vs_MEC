"""Tk smoke checks. Requires an interactive Windows desktop (no real endpoints)."""
import ctypes
import sys
import unittest
from unittest.mock import patch
from app import App
from meccloud.core import Runner
from tests.test_core import sample


class UITests(unittest.TestCase):
    def setUp(self):
        self.app = App()
        self.app.withdraw()

    def tearDown(self):
        self.app.close()

    def test_separate_series_and_session(self):
        a = self.app
        a.samples.append(sample(10))
        a.refresh()
        self.assertIn('10.00 ms', a.metrics['MEC'].cget('text'))
        a.condition.set('Recuperado')
        a.change_condition()
        self.assertEqual(a.selected_samples(), [])
        self.assertEqual(len(a.samples), 1)
        # An old runner's queued measurement must never enter the new session.
        old = Runner(a.session_id, 'Base', {}, 1, 1, 1, a.out)
        with patch('app.messagebox.askyesno', return_value=True):
            a.new_session()
        a.out.put(('sample', old, sample(20)))
        a.poll()
        self.assertEqual(a.samples, [])
        a.geometry('900x740')
        a.update()
        a.draw()

    @unittest.skipUnless(sys.platform == 'win32', 'Windows native power notification')
    def test_windows_suspend_notification(self):
        a = self.app
        runner = Runner(a.session_id, a.active_condition, {}, 1, 1, 1, a.out)
        a.runner = runner
        from ctypes import wintypes
        user32 = ctypes.WinDLL('user32')
        user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.SendMessageW.restype = ctypes.c_ssize_t
        user32.SendMessageW(a.power.hwnd, 0x218, 4, 0)
        self.assertTrue(runner.stop.is_set())
        self.assertTrue(runner.suspended.is_set())
        a.runner = None


if __name__ == '__main__':
    unittest.main()
