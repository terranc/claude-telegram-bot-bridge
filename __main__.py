import argparse
import logging
import os
import sys
from pathlib import Path as _Path

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", help="Project path")
    parser.add_argument("--path", dest="path_opt", help="Project path")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()

    if args.debug:
        os.environ["BOT_DEBUG"] = "1"

    path = args.path_opt or args.path
    if path:
        os.environ["PROJECT_ROOT"] = str(_Path(path).expanduser().resolve())

    if "PROJECT_ROOT" not in os.environ:
        print(
            "Error: Please specify project path via argument or PROJECT_ROOT environment variable"
        )
        sys.exit(1)

    from telegram_bot.utils.config import setup_logging
    from telegram_bot.core.bot import bot

    setup_logging()
    logger = logging.getLogger(__name__)
    try:
        bot.run()
    except SystemExit as e:
        if e.code and str(e.code) != "0":
            logger.error(str(e.code))
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
