"""Dispatch real Tk events: widget bindings must not steal transport keys."""
from unittest.mock import Mock, patch

import pytest
import test_workspace

from backend.compact_widgets import LINE


@pytest.fixture
def session():
    case = test_workspace.WorkspaceTests()
    case.setUp()
    case.app.focus_force()
    case.app.update()
    try:
        yield case
    finally:
        case.tearDown()


def press(app, key):
    target = app.focus_get()
    assert target is not None
    target.event_generate(f"<KeyPress-{key}>")
    target.event_generate(f"<KeyRelease-{key}>")
    app.update()


def test_mouse_clicked_buttons_release_focus_and_space_controls_transport(session):
    app = session.app
    buttons = (app.load_button, app.render_button, app.render_mp3_button, app.play_button)
    with patch.object(app, "toggle_playback") as transport:
        for button in buttons:
            command = Mock()
            with patch.object(button, "command", command):
                app.fade_in_spinbox.focus_set()
                app.update()
                button.event_generate("<ButtonPress-1>", x=10, y=10)
                button.event_generate("<ButtonRelease-1>", x=10, y=10)
                app.update()
                command.assert_called_once_with()
                assert app.focus_get() == app
                assert button.itemcget(button.find_all()[0], "outline") == LINE
                press(app, "space")
                transport.assert_called_once_with()
                command.assert_called_once_with()
                transport.reset_mock()


def test_keyboard_focused_button_uses_enter_but_space_still_controls_transport(session):
    app = session.app
    button = app.load_button
    with patch.object(button, "command") as command, patch.object(app, "toggle_playback") as transport:
        button.focus_set()
        app.update()
        press(app, "space")
        transport.assert_called_once_with()
        command.assert_not_called()
        press(app, "Return")
        command.assert_called_once_with()


@pytest.mark.parametrize("mouse_button", (1, 3))
def test_waveform_click_leaves_numeric_input_and_space_controls_transport(session, mouse_button):
    app = session.app
    app.fade_in_spinbox.focus_set()
    app.update()
    app.wave_canvas.event_generate(f"<ButtonPress-{mouse_button}>", x=80, y=30)
    app.wave_canvas.event_generate(f"<ButtonRelease-{mouse_button}>", x=120, y=30)
    app.update()
    assert app.focus_get() == app.wave_canvas
    with patch.object(app, "toggle_playback") as transport:
        press(app, "space")
        transport.assert_called_once_with()


def test_space_in_numeric_entry_or_settings_does_not_start_playback(session):
    app = session.app
    with patch.object(app, "toggle_playback") as transport:
        app.fade_in_spinbox.focus_set()
        app.update()
        press(app, "space")
        transport.assert_not_called()
        # Restore valid text before exercising the independent modal guard.
        app.fade_in_var.set(.02)
        app.open_render_settings()
        app._dialog.focus_set()
        app.update()
        press(app, "space")
        transport.assert_not_called()
        app._close_render_settings()
