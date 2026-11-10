import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cloud_client import AccessDenied
from desktop import DropperWindow


class AccessFlowTests(unittest.TestCase):
    def manager(self):
        manager = DropperWindow.__new__(DropperWindow)
        manager.vault = Mock()
        manager.status = Mock()
        manager.show_loading = Mock()
        manager.hide_loading = Mock()
        manager.connect_dialog = Mock()
        manager.auth_required = False
        return manager

    def test_first_launch_requests_password(self):
        manager = self.manager()
        manager.vault.read.return_value = None
        manager.try_connect = Mock()
        manager.auto_connect()
        manager.connect_dialog.assert_called_once()
        manager.try_connect.assert_not_called()

    def test_revoked_password_clears_saved_access_and_requests_new_password(self):
        manager = self.manager()
        panel = SimpleNamespace(stop=Mock())
        manager.panels = {'first': panel}
        manager.cloud_failed(AccessDenied('Contraseña cambiada'))
        self.assertTrue(manager.auth_required)
        manager.vault.delete.assert_called_once()
        manager.connect_dialog.assert_called_once()
        panel.stop.assert_not_called()

    def test_update_asks_for_new_password_when_revoked(self):
        manager = self.manager()
        manager.refreshing = manager.closing = False
        manager.client = Mock()
        manager.auth_required = True
        manager.refresh()
        manager.connect_dialog.assert_called_once()
        manager.client.list_profiles.assert_not_called()

    def test_saved_password_is_checked_on_launch(self):
        manager = self.manager()
        manager.vault.read.return_value = 'saved-password'
        manager.try_connect = Mock()
        manager.auto_connect()
        manager.try_connect.assert_called_once_with('saved-password')

    def login_manager(self):
        manager = self.manager()
        manager.connecting = False
        manager.root = Mock()
        manager.connected = Mock()
        manager.apply_profiles = Mock()
        manager.access_dialog = Mock()
        manager.access_dialog.winfo_exists.return_value = True
        manager.background = lambda work, complete, failed: complete([{'id': 'one'}])
        return manager

    def test_successful_login_closes_stored_password_window_without_dialog_argument(self):
        manager = self.login_manager()
        dialog = manager.access_dialog
        with patch('desktop.CloudClient'):
            manager.try_connect('password')
        manager.apply_profiles.assert_called_once_with([{'id': 'one'}])
        manager.show_loading.assert_called_once()
        manager.hide_loading.assert_called_once()
        dialog.grab_release.assert_called_once()
        dialog.destroy.assert_called_once()
        self.assertIsNone(manager.access_dialog)
        self.assertFalse(manager.connecting)

    def test_successful_login_closes_explicit_dialog_once(self):
        manager = self.login_manager()
        dialog = manager.access_dialog
        with patch('desktop.CloudClient'):
            manager.try_connect('password', remember=True, dialog=dialog)
        dialog.destroy.assert_called_once()
        manager.vault.write.assert_called_once_with('password')

    def test_bad_password_keeps_window_open_for_retry(self):
        manager = self.login_manager()
        dialog = manager.access_dialog
        manager.show_error = Mock()
        manager.background = lambda work, complete, failed: failed(AccessDenied('incorrecta'))
        with patch('desktop.CloudClient'):
            manager.try_connect('password', dialog=dialog)
        dialog.destroy.assert_not_called()
        self.assertFalse(manager.connecting)
        manager.show_error.assert_called_once()

    def test_sidebar_scrollbar_hides_when_content_fits_and_returns_on_overflow(self):
        manager = DropperWindow.__new__(DropperWindow)
        manager.side_canvas = Mock()
        manager.side_scroll = Mock()
        manager.list_window = 1
        manager.side_canvas.winfo_width.return_value = 236
        manager.side_canvas.winfo_height.return_value = 400
        manager.side_canvas.bbox.return_value = (0, 0, 236, 150)
        manager.side_scroll.winfo_manager.return_value = 'pack'
        manager.layout_sidebar()
        manager.side_scroll.pack_forget.assert_called_once()
        manager.side_canvas.yview_moveto.assert_called_once_with(0)
        manager.side_canvas.bbox.return_value = (0, 0, 236, 900)
        manager.side_scroll.winfo_manager.return_value = ''
        manager.layout_sidebar()
        manager.side_scroll.pack.assert_called_once_with(side='right', fill='y', before=manager.side_canvas)


