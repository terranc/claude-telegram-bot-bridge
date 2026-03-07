"""
Project Chat Handler - Integrates Telegram with Claude Code SDK.
"""

import os
import re
import asyncio
import json
import logging
from collections import deque
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, Callable, Awaitable, Deque
from dataclasses import dataclass, field

from claude_code_sdk import (
    ClaudeSDKClient,
    ClaudeCodeOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    PermissionResultAllow,
    PermissionResultDeny,
)

from claude_code_sdk._internal.transport.subprocess_cli import SubprocessCLITransport

from telegram_bot.utils.chat_logger import log_chat
from telegram_bot.utils.config import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Suppress noisy "Task exception was never retrieved" errors from the SDK.
#
# The Claude Code SDK uses anyio task groups internally.  When we cancel a
# reader task the SDK may spawn a background disconnect() task that raises
# RuntimeError("Attempted to exit cancel scope …").  Because we never hold
# a reference to that orphan task, asyncio's Task.__del__ logs an ERROR via
# the "asyncio" logger.  The filter below silences that specific message.
# ---------------------------------------------------------------------------
class _CancelScopeLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.exc_info and record.exc_info[1]:
            exc = record.exc_info[1]
            if isinstance(exc, RuntimeError) and "cancel scope" in str(exc):
                return False
        return True


logging.getLogger("asyncio").addFilter(_CancelScopeLogFilter())


def _patch_sdk_cli_resolution() -> None:
    """Make SDK default transport honor configured CLAUDE_CLI_PATH."""
    marker = "_telegram_bot_cli_path_patch_applied"
    if getattr(SubprocessCLITransport, marker, False):
        return
    if not config.claude_cli_path:
        return

    cli_path = str(config.claude_cli_path)

    def patched_find_cli(self):
        return cli_path

    SubprocessCLITransport._find_cli = patched_find_cli
    setattr(SubprocessCLITransport, marker, True)
    logger.info(f"Patched SDK CLI resolution to use configured path: {cli_path}")


_patch_sdk_cli_resolution()

PROJECT_ROOT = Path(os.environ["PROJECT_ROOT"]).resolve()
PROJECT_DIR_NAME = str(PROJECT_ROOT).replace("/", "-").replace("_", "-")
CONVERSATIONS_DIR = Path.home() / ".claude" / "projects" / PROJECT_DIR_NAME

ALLOWED_TOOLS = [
    "Read", "Edit", "Write", "MultiEdit", "Glob", "Grep",
    "WebFetch", "WebSearch", "Task", "NotebookEdit", "TodoWrite", "Bash",
    # AskUserQuestion is handled via disallowed_tools + can_use_tool callback
]

PROCESS_TIMEOUT = int(os.getenv("CLAUDE_PROCESS_TIMEOUT", "600"))


def _format_ask_user_question(tool_input: dict):
    """Degrade AskUserQuestion to plain text for bot delivery.

    Returns (formatted_text: str, image_paths: list[str]).
    Extracts question text (which may include post content and image file paths
    as plain text) and numbered options so the bot's _extract_options can build
    an inline keyboard. Images are delivered separately via Read tool interception.
    """
    lines: list = []

    for q in tool_input.get("questions", []):
        question = q.get("question", "")
        if question:
            lines.append(question)

        options = q.get("options", [])

        if options:
            lines.append("")
        for i, opt in enumerate(options, 1):
            label = opt.get("label", "")
            desc = opt.get("description", "")
            lines.append(f"{i}. {label}" + (f" - {desc}" if desc else ""))

    return "\n".join(lines), []


def _detect_numbered_options(text: str) -> bool:
    """
    Detect if text contains numbered options format (e.g., "1. Option A").

    Returns True if the text appears to contain a question with numbered choices.
    """
    import re
    # Look for pattern: number followed by period and text, appearing multiple times
    # Must have at least 2 numbered items to be considered options
    pattern = r'^\s*\d+\.\s+.+$'
    matches = re.findall(pattern, text, re.MULTILINE)
    return len(matches) >= 2


# Callback type: async (chat_id, user_id, tool_name, tool_input) -> bool | PermissionResult
PermissionCallback = Callable[[int, int, str, Dict[str, Any]], Awaitable]
# Callback type: async () -> None, sends typing action
TypingCallback = Callable[[], Awaitable[None]]

TYPING_INTERVAL = 4  # Telegram typing status expires after ~5s


@dataclass
class ChatResponse:
    """Response from processing a message"""
    content: str
    success: bool = True
    error: Optional[str] = None
    session_id: Optional[str] = None
    has_options: bool = False
    streamed: bool = False  # Whether message was already sent via streaming


@dataclass
class _PendingRequest:
    user_id: int
    chat_id: int
    model: Optional[str]
    requested_session_id: Optional[str]
    permission_callback: Optional[PermissionCallback]
    typing_callback: Optional[TypingCallback]
    future: asyncio.Future
    sent_session_id: str = "default"
    last_typing_at: float = 0.0
    last_assistant_texts: List[str] = field(default_factory=list)
    synthetic_response: Optional[str] = None
    streaming_handler: Optional[Any] = None  # StreamingMessageHandler instance
    bot: Optional[Any] = None                 # PTB Bot instance for late delivery
    timed_out: bool = False                   # Flag: was this request timed out?


@dataclass
class _UserStreamState:
    client: ClaudeSDKClient
    model: Optional[str]
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    pending: Deque[_PendingRequest] = field(default_factory=deque)
    reader_task: Optional[asyncio.Task] = None
    typing_task: Optional[asyncio.Task] = None
    last_session_id: Optional[str] = None


class ProjectChatHandler:
    """
    Handles Telegram messages using a per-user long-lived Claude SDK stream.

    This allows multiple messages to be submitted quickly to the same live session
    before earlier responses are fully returned.
    """

    def __init__(self):
        self.project_root = PROJECT_ROOT
        self._active_tasks: Dict[int, asyncio.Task] = {}
        self._streams: Dict[int, _UserStreamState] = {}
        self._stream_init_locks: Dict[int, asyncio.Lock] = {}
        self._user_cwds: Dict[int, Path] = {}
        logger.info(f"ProjectChatHandler initialized for {self.project_root}")

    def get_user_cwd(self, user_id: int) -> Path:
        return self._user_cwds.get(user_id, self.project_root)

    def change_directory(self, user_id: int, new_path: Path) -> None:
        self._user_cwds[user_id] = new_path
        self.clear_user_stream(user_id)
        logger.info(f"Changed cwd for user {user_id} to {new_path}")

    def _get_stream_init_lock(self, user_id: int) -> asyncio.Lock:
        lock = self._stream_init_locks.get(user_id)
        if lock is None:
            lock = asyncio.Lock()
            self._stream_init_locks[user_id] = lock
        return lock

    async def _create_user_stream(self, user_id: int, model: Optional[str]) -> _UserStreamState:
        state_holder: Dict[str, _UserStreamState] = {}

        async def can_use_tool(tool_name, tool_input, _context=None):
            print(f"[DEBUG] can_use_tool called: {tool_name}")
            logger.debug(f"can_use_tool called: tool_name={tool_name}, tool_input type={type(tool_input)}")
            # AskUserQuestion: degrade to plain text instead of interactive dialog
            if tool_name == "AskUserQuestion" and isinstance(tool_input, dict):
                formatted, _ = _format_ask_user_question(tool_input)
                logger.debug(f"AskUserQuestion intercepted, formatted: {formatted[:200]}...")
                s = state_holder.get("state")
                if s and s.pending:
                    s.pending[0].synthetic_response = formatted
                    logger.debug(f"Set synthetic_response for user {user_id}")
                return PermissionResultDeny(
                    message=(
                        "AskUserQuestion tool is not available. "
                        "CRITICAL: You MUST output the question and numbered options to the user, then STOP and WAIT. "
                        "Do NOT continue execution. Do NOT make assumptions about the user's choice. "
                        "Output format:\n\n"
                        "[Question and context]\n\n"
                        "1. [First option]\n"
                        "2. [Second option]\n"
                        "3. [Third option]\n\n"
                        "After outputting the options, you MUST stop and wait for the user to respond with their choice."
                    )
                )
            state = state_holder.get("state")
            if not state or not state.pending:
                return PermissionResultAllow()
            req = state.pending[0]
            callback = req.permission_callback
            if not callback:
                return PermissionResultAllow()

            result = await callback(req.chat_id, user_id, tool_name, tool_input)
            if isinstance(result, (PermissionResultAllow, PermissionResultDeny)):
                return result
            return PermissionResultAllow() if result else PermissionResultDeny()

        # NOTE: append_system_prompt is passed as a CLI argument.  On Windows
        # the .CMD launcher runs via cmd.exe which breaks on literal newlines
        # inside arguments, causing the SDK initialisation to hang.  Keep the
        # prompt as a single line (spaces only).
        _ask_prompt = (
            "## Important: User Questions and Choices. "
            "The AskUserQuestion tool is NOT available in this environment. "
            "When you need to ask the user a question with multiple choice options: "
            "1) Output the question and context clearly; "
            "2) List options with numbers (1., 2., 3., etc.); "
            "3) STOP and WAIT for the user's response; "
            "4) Do NOT continue execution or make assumptions; "
            "5) Do NOT try to use AskUserQuestion tool. "
            "After outputting options, you MUST stop and wait for user input."
        )
        opts: Dict[str, Any] = {
            "cwd": str(self.get_user_cwd(user_id)),
            "allowed_tools": ALLOWED_TOOLS,
            "disallowed_tools": ["AskUserQuestion"],  # Disable to force degradation
            "append_system_prompt": _ask_prompt,
            "can_use_tool": can_use_tool,
            "permission_mode": "default",
        }
        if model:
            opts["model"] = model

        client = ClaudeSDKClient(options=ClaudeCodeOptions(**opts))
        await client.connect()
        state = _UserStreamState(client=client, model=model)
        state_holder["state"] = state
        state.reader_task = asyncio.create_task(self._reader_loop(user_id, state))
        state.typing_task = asyncio.create_task(self._typing_keepalive_loop(user_id, state))
        return state

    async def _disconnect_user_stream(self, user_id: int, cancel_message: Optional[str] = None) -> bool:
        state = self._streams.pop(user_id, None)
        if not state:
            return False

        # Cancel typing keepalive task
        if state.typing_task and not state.typing_task.done():
            state.typing_task.cancel()
            try:
                await asyncio.wait_for(state.typing_task, timeout=1.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            except Exception as e:
                logger.error(f"Error cancelling typing task for user {user_id}: {e}")

        # Cancel reader task first
        if state.reader_task and not state.reader_task.done():
            state.reader_task.cancel()
            try:
                await asyncio.wait_for(state.reader_task, timeout=2.0)
            except asyncio.TimeoutError:
                logger.warning(f"Reader task for user {user_id} did not complete within timeout")
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Error cancelling reader task for user {user_id}: {e}")

        # Fail all pending requests
        msg = cancel_message or "🛑 Task has been terminated."
        while state.pending:
            req = state.pending.popleft()
            if not req.future.done():
                try:
                    req.future.set_result(ChatResponse(content=msg, success=False, error=msg, session_id=state.last_session_id))
                except Exception as e:
                    logger.error(f"Error setting future result: {e}")

        # Disconnect client.  The cancel-scope RuntimeError is caught both
        # here (explicit call) and by the event-loop handler (orphan tasks).
        async def _safe_disconnect() -> None:
            try:
                await state.client.disconnect()
            except RuntimeError as e:
                if "cancel scope" in str(e):
                    logger.debug(f"Benign cancel-scope error during disconnect for user {user_id}: {e}")
                else:
                    logger.error(f"Error disconnecting client for user {user_id}: {e}")
            except Exception as e:
                logger.error(f"Error disconnecting client for user {user_id}: {e}")

        dc_task = asyncio.create_task(_safe_disconnect())
        done, _ = await asyncio.wait({dc_task}, timeout=3.0)
        if not done:
            logger.warning(f"Client disconnect for user {user_id} timed out")
            dc_task.cancel()
            try:
                await dc_task
            except (asyncio.CancelledError, Exception):
                pass

        return True

    async def _get_or_create_stream(
        self, user_id: int, model: Optional[str], new_session: bool
    ) -> _UserStreamState:
        lock = self._get_stream_init_lock(user_id)
        async with lock:
            state = self._streams.get(user_id)

            # Detect stale stream: reader task ended (e.g. after system sleep/wake)
            if state and state.reader_task is not None and state.reader_task.done():
                logger.warning(
                    f"Stale stream detected for user {user_id} (reader task exited), recreating"
                )
                await self._disconnect_user_stream(user_id)
                state = None

            if state and (new_session or state.model != model):
                await self._disconnect_user_stream(user_id)
                state = None

            if not state:
                state = await self._create_user_stream(user_id, model)
                self._streams[user_id] = state
            return state

    async def _typing_keepalive_loop(self, user_id: int, state: _UserStreamState) -> None:
        """Background task that sends typing actions at regular intervals.

        Keeps Telegram typing indicator alive during long tool calls when
        the SDK stream emits no messages.
        """
        try:
            while True:
                await asyncio.sleep(TYPING_INTERVAL)
                if not state.pending:
                    continue
                req = state.pending[0]
                if not req.typing_callback:
                    continue
                now = asyncio.get_event_loop().time()
                if now - req.last_typing_at < TYPING_INTERVAL:
                    continue
                req.last_typing_at = now
                try:
                    await req.typing_callback()
                except Exception:
                    pass
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Typing keepalive loop crashed for user {user_id}: {e}", exc_info=True)

    async def _reader_loop(self, user_id: int, state: _UserStreamState) -> None:
        try:
            async for msg in state.client.receive_messages():
                if not state.pending:
                    continue

                req = state.pending[0]
                now = asyncio.get_event_loop().time()
                if req.typing_callback and now - req.last_typing_at >= TYPING_INTERVAL:
                    req.last_typing_at = now
                    try:
                        await req.typing_callback()
                    except Exception:
                        pass

                if isinstance(msg, AssistantMessage):
                    logger.debug(f"Received AssistantMessage with {len(msg.content)} blocks")
                    req.last_assistant_texts = []
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            logger.debug(f"TextBlock: {len(block.text)} chars")
                            req.last_assistant_texts.append(block.text)
                            # Update streaming draft if handler is available
                            if req.streaming_handler:
                                try:
                                    await req.streaming_handler.update_if_needed(block.text)
                                except Exception as e:
                                    logger.error(f"Streaming update failed: {e}")
                            if os.environ.get("BOT_DEBUG"):
                                print(f"\033[36m[Claude]\033[0m {block.text[:200]}")
                        elif isinstance(block, ToolUseBlock):
                            if os.environ.get("BOT_DEBUG"):
                                print(f"\033[33m[Tool: {block.name}]\033[0m {str(block.input)[:150]}")
                    continue

                if isinstance(msg, ResultMessage):
                    state.last_session_id = msg.session_id or state.last_session_id
                    result_text = msg.result or "\n".join(req.last_assistant_texts)

                    # Finalize streaming drafts
                    if req.streaming_handler:
                        try:
                            await req.streaming_handler.finalize_all()
                        except Exception as e:
                            logger.error(f"Streaming finalization failed: {e}")

                    if req.synthetic_response:
                        content = self._clean_response(req.synthetic_response) or "(No response)"
                    else:
                        content = self._clean_response(result_text) or "(No response)"

                    logger.info(
                        f"ResultMessage: session={msg.session_id}, is_error={msg.is_error}, duration={msg.duration_ms}ms"
                    )

                    if msg.is_error:
                        logger.error(f"SDK returned error: {content[:500]}")
                        log_chat(req.user_id, msg.session_id or req.requested_session_id, "assistant", content, model=req.model, success=False)
                        response = ChatResponse(
                            content=f"❌ Processing failed: {content}",
                            success=False,
                            error=content,
                            session_id=msg.session_id,
                            streamed=bool(req.streaming_handler and req.streaming_handler.drafts),
                        )
                    else:
                        log_chat(req.user_id, msg.session_id or req.requested_session_id, "assistant", content, model=req.model)
                        # Check if response contains numbered options (even without synthetic_response)
                        has_options = req.synthetic_response is not None or _detect_numbered_options(content)
                        # Message is considered streamed if drafts were created, regardless of options
                        # Options will be sent separately by _reply_smart()/_send_smart()
                        is_streamed = bool(req.streaming_handler and req.streaming_handler.drafts)
                        logger.debug(f"Response ready: has_synthetic={bool(req.synthetic_response)}, has_numbered_options={_detect_numbered_options(content)}, has_options={has_options}, is_streamed={is_streamed}, content_len={len(content)}")
                        response = ChatResponse(
                            content=content, success=True, session_id=msg.session_id,
                            has_options=has_options,
                            streamed=is_streamed,
                        )

                    if not req.future.done():
                        try:
                            req.future.set_result(response)
                        except Exception as e:
                            logger.error(f"Error setting future result: {e}")
                    elif req.timed_out and req.bot:
                        # Future already resolved (timeout) — push late result to Telegram
                        asyncio.create_task(self._deliver_late_result(req, content))
                    state.pending.popleft()
        except asyncio.CancelledError:
            logger.debug(f"Reader loop cancelled for user {user_id}")
            raise
        except Exception as e:
            logger.error(f"Reader loop crashed for user {user_id}: {e}", exc_info=True)
            # Cancel typing keepalive to prevent orphan task
            if state.typing_task and not state.typing_task.done():
                state.typing_task.cancel()
            # Remove broken stream so the next request creates a fresh connection
            self._streams.pop(user_id, None)
            # Safely handle pending requests
            pending_copy = list(state.pending)
            state.pending.clear()
            for req in pending_copy:
                # Finalize streaming drafts on error
                if req.streaming_handler:
                    try:
                        await req.streaming_handler.finalize_all()
                    except Exception as finalize_err:
                        logger.error(f"Streaming finalization on error failed: {finalize_err}")
                err = str(e)
                log_chat(req.user_id, req.requested_session_id, "error", err, success=False)
                if not req.future.done():
                    try:
                        req.future.set_result(ChatResponse(content=f"❌ Error: {err}", success=False, error=err, session_id=state.last_session_id))
                    except Exception as set_err:
                        logger.error(f"Error setting error result: {set_err}")

    async def _deliver_late_result(self, req: _PendingRequest, content: str) -> None:
        """Push late result directly to Telegram when a timed-out task completes."""
        try:
            prefix = "✅ (delayed result)\n\n"
            full = prefix + content
            # Split for Telegram 4096 char limit
            for i in range(0, len(full), 4000):
                await req.bot.send_message(req.chat_id, full[i:i + 4000])
            logger.info(f"Delivered late result to user {req.user_id} ({len(full)} chars)")
        except Exception as e:
            logger.error(f"Failed to deliver late result to user {req.user_id}: {e}")

    async def process_message(
        self,
        user_message: str,
        user_id: int,
        chat_id: int,
        message_id: Optional[int] = None,
        session_id: Optional[str] = None,
        model: Optional[str] = None,
        new_session: bool = False,
        permission_callback: Optional[PermissionCallback] = None,
        typing_callback: Optional[TypingCallback] = None,
        bot: Optional[Any] = None,
    ) -> ChatResponse:
        del message_id
        logger.info(f"Processing message from user {user_id}: {user_message[:80]}...")
        log_chat(user_id, session_id, "user", user_message, model=model)

        task = asyncio.current_task()
        if task:
            self._active_tasks[user_id] = task

        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()

        # Create streaming handler if bot is provided
        streaming_handler = None
        if bot:
            from telegram_bot.core.streaming import StreamingMessageHandler
            streaming_handler = StreamingMessageHandler(bot, chat_id, user_id)

        request = _PendingRequest(
            user_id=user_id,
            chat_id=chat_id,
            model=model,
            requested_session_id=session_id,
            permission_callback=permission_callback,
            typing_callback=typing_callback,
            future=future,
            streaming_handler=streaming_handler,
        )
        state: Optional[_UserStreamState] = None

        try:
            state = await self._get_or_create_stream(user_id, model, new_session)
            async with state.send_lock:
                request.sent_session_id = session_id or state.last_session_id or "default"
                state.pending.append(request)
                await state.client.query(user_message, session_id=request.sent_session_id)
                logger.info(
                    f"Submitted message to live stream: user={user_id}, pending={len(state.pending)}, "
                    f"session_key={request.sent_session_id}"
                )
                if config.claude_cli_path:
                    logger.info(f"Using configured Claude CLI path: {config.claude_cli_path}")

            return await asyncio.wait_for(future, timeout=PROCESS_TIMEOUT)

        except asyncio.CancelledError:
            logger.info(f"Task cancelled for user {user_id} - cleaning up")
            # Clean up streaming drafts if active
            if streaming_handler:
                try:
                    await streaming_handler.cancel()
                except Exception as e:
                    logger.error(f"Failed to cancel streaming handler: {e}")
            await self.stop(user_id)
            # Don't return a message - bot.py will handle the user response
            raise

        except asyncio.TimeoutError:
            logger.warning(f"Query timed out for user {user_id} after {PROCESS_TIMEOUT}s — task continues in background")
            # Don't disconnect — let the task keep running in the background.
            # Mark the request so _reader_loop can push the result when ready.
            request.timed_out = True
            request.bot = bot
            msg = f"⏰ Still processing (>{PROCESS_TIMEOUT}s). Result will be sent when ready."
            return ChatResponse(content=msg, success=False, error=msg)

        except Exception as e:
            if state and request in state.pending:
                try:
                    state.pending.remove(request)
                except ValueError:
                    pass
            logger.error(f"Error processing message: {e}", exc_info=True)
            err = str(e)
            return ChatResponse(content=f"❌ Error: {err}", success=False, error=err)

        finally:
            self._active_tasks.pop(user_id, None)

    async def stop(self, user_id: int) -> bool:
        """Stop active stream for a user and fail all pending requests."""
        return await self._disconnect_user_stream(user_id, cancel_message="🛑 Task has been terminated.")

    async def cancel_user_streaming(self, user_id: int) -> bool:
        """Cancel streaming for a user by calling cancel() on all pending streaming handlers."""
        state = self._streams.get(user_id)
        if not state or not state.pending:
            return False

        cancelled = False
        for req in state.pending:
            if req.streaming_handler:
                try:
                    await req.streaming_handler.cancel()
                    cancelled = True
                except Exception as e:
                    logger.error(f"Failed to cancel streaming for user {user_id}: {e}")

        return cancelled

    def inflight_count(self, user_id: int) -> int:
        state = self._streams.get(user_id)
        if not state:
            return 0
        return len(state.pending)

    def is_user_busy(self, user_id: int) -> bool:
        return self.inflight_count(user_id) > 0

    def clear_user_stream(self, user_id: int) -> None:
        """Clear active stream for a user to force new SDK connection."""
        if user_id in self._streams:
            state = self._streams[user_id]
            # Cancel reader and typing tasks
            if state.reader_task and not state.reader_task.done():
                state.reader_task.cancel()
            if state.typing_task and not state.typing_task.done():
                state.typing_task.cancel()
            # Close SDK client
            try:
                if state.client:
                    asyncio.create_task(state.client.close())
            except Exception as e:
                logger.error(f"Error closing SDK client for user {user_id}: {e}")
            # Remove from streams dict
            del self._streams[user_id]
            logger.info(f"Cleared stream for user {user_id}")

    def clear_pending_permissions(self, user_id: int) -> None:
        """Clear pending permission futures for a user."""
        state = self._streams.get(user_id)
        if state:
            # Clear any pending permission requests
            for req in list(state.pending):
                if req.permission_future and not req.permission_future.done():
                    req.permission_future.cancel()
            logger.info(f"Cleared pending permissions for user {user_id}")

    def list_sessions(self, limit: int = 10) -> List[Tuple[str, str, float]]:
        """List recent conversations: [(session_id, first_user_msg, mtime)]"""
        conv_dir = CONVERSATIONS_DIR
        if not conv_dir.exists():
            return []
        files = sorted(conv_dir.glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)
        results = []
        for f in files[:limit * 2]:
            session_id = f.stem
            mtime = f.stat().st_mtime
            first_msg = self._extract_first_user_message(f)
            if first_msg:
                results.append((session_id, first_msg, mtime))
            if len(results) >= limit:
                break
        return results

    def get_session_last_assistant_message(self, session_id: str, max_chars: int = 300) -> Optional[str]:
        """Extract the last assistant text message from a session JSONL file."""
        filepath = CONVERSATIONS_DIR / f"{session_id}.jsonl"
        if not filepath.exists():
            return None
        try:
            last_text = None
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if d.get("type") != "assistant":
                        continue
                    msg = d.get("message", {})
                    if msg.get("role") != "assistant":
                        continue
                    content = msg.get("content", [])
                    if not isinstance(content, list):
                        continue
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = block.get("text", "").strip()
                            if text:
                                last_text = text
            if not last_text:
                return None
            if len(last_text) > max_chars:
                last_text = last_text[:max_chars] + "..."
            return last_text
        except Exception:
            return None

    def get_recent_messages(self, session_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get the last N messages from a session in chronological order."""
        filepath = CONVERSATIONS_DIR / f"{session_id}.jsonl"
        if not filepath.exists():
            return []

        try:
            all_messages = []
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    msg_type = d.get("type")
                    if msg_type not in ("user", "assistant"):
                        continue

                    msg = d.get("message", {})
                    role = msg.get("role")
                    if role not in ("user", "assistant"):
                        continue

                    content = msg.get("content", "")
                    text = ""
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text = block.get("text", "").strip()
                                if text:
                                    break
                    elif isinstance(content, str):
                        text = content.strip()

                    if not text:
                        continue

                    timestamp = d.get("timestamp", "")
                    all_messages.append({
                        "role": role,
                        "content": text,
                        "timestamp": timestamp
                    })

            return all_messages[-limit:] if all_messages else []
        except Exception as e:
            logger.error(f"Error reading session messages: {e}")
            return []

    def get_conversation_history(self, session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get conversation history with message index for revert operations.

        Returns list of USER messages only with index, timestamp, role, and content preview.
        Messages are returned in reverse chronological order (newest first).
        """
        filepath = CONVERSATIONS_DIR / f"{session_id}.jsonl"
        if not filepath.exists():
            return []

        try:
            all_messages = []
            with open(filepath, "r", encoding="utf-8") as f:
                for idx, line in enumerate(f):
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    msg_type = d.get("type")
                    if msg_type != "user":
                        continue

                    msg = d.get("message", {})
                    role = msg.get("role")
                    if role != "user":
                        continue

                    content = msg.get("content", "")
                    text = ""
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text = block.get("text", "").strip()
                                if text:
                                    break
                    elif isinstance(content, str):
                        text = content.strip()

                    if not text:
                        continue

                    timestamp = d.get("timestamp", "")
                    all_messages.append({
                        "index": idx,
                        "role": role,
                        "content": text,
                        "timestamp": timestamp
                    })

            # Return newest first (reverse order)
            recent_messages = all_messages[-limit:] if all_messages else []
            return list(reversed(recent_messages))
        except Exception as e:
            logger.error(f"Error reading conversation history: {e}")
            return []

    @staticmethod
    def _extract_first_user_message(filepath: Path) -> Optional[str]:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    d = json.loads(line)
                    if d.get("type") != "user":
                        continue
                    msg = d.get("message", {})
                    if msg.get("role") != "user":
                        continue
                    content = msg.get("content", "")
                    text = ""
                    if isinstance(content, list):
                        for c in content:
                            if isinstance(c, dict) and c.get("type") == "text":
                                text = c["text"]
                                break
                    elif isinstance(content, str):
                        text = content
                    text = text.strip()
                    if text and not text.startswith("<"):
                        return text[:80]
        except Exception:
            pass
        return None

    def _clean_response(self, response: str) -> str:
        ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        cleaned = ansi_escape.sub("", response)
        cleaned = "".join(char for char in cleaned if ord(char) >= 32 or char in "\n\r\t")
        return cleaned.strip()


project_chat_handler = ProjectChatHandler()
