"""Compatibility layer — delegates everything to tmux_session.py.

The real implementation moved to TmuxSession in tmux_session.py.
This module re-exports the same public API so main.py and callers
don't need to change.
"""

import tmux_session as _ts

# Re-export all public functions and constants so existing imports work.
# The TmuxSession is the singleton managed by tmux_session module-level
# functions — identical names, identical signatures.

check_tmux = _ts.check_tmux
strip_ansi = _ts.strip_ansi

start_session = _ts.start_session
stop_session = _ts.stop_session
send_prompt = _ts.send_prompt
get_session_status = _ts.get_session_status
open_terminal = _ts.open_terminal
list_saved_sessions = _ts.list_saved_sessions
get_saved_session = _ts.get_saved_session
archive_saved_session = _ts.archive_saved_session
load_session = _ts.load_session
