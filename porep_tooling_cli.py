#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Entry point for the CLI app
# This file is supposed to be python 2 compatible

import __future__
import os
import sys

_ = __future__

LOG_FILE = "logs/logs.log"
ERROR_LOG_FILE = "logs/error.logs"


def configure_logger():
    import logging

    def logging_level_str_to_int(level_str: str | None) -> int:
        DEFAULT = logging.DEBUG

        return {
            "disabled": sys.maxsize,
            "critical": logging.CRITICAL,
            "fatal": logging.FATAL,
            "error": logging.ERROR,
            "warning": logging.WARNING,
            "warn": logging.WARN,
            "info": logging.INFO,
            "debug": logging.DEBUG,
            "notset": logging.NOTSET,
            "all": logging.NOTSET
        }.get(level_str.strip().lower(), DEFAULT) if level_str else DEFAULT

    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

    logging_format = "%(levelname)-10s%(asctime)s %(name)s:%(funcName)-16s: %(message)s"
    level = logging_level_str_to_int(os.getenv("_FILE_LOGGING_LEVEL"))

    log_formatter = logging.Formatter(logging_format)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(level)
    root_logger.addHandler(file_handler)


def main():
    configure_logger()

    from cli import cli
    cli()


if __name__ == "__main__":
    import platform

    if sys.version_info < (3, 10, 0):
        print("Python >= v3.10.0 required to run %s, you have %s" % (sys.argv[0], platform.python_version()), file=sys.stderr)
        sys.exit(1)

    DEBUG = False

    try:
        import dotenv

        dotenv.load_dotenv()
        DEBUG = os.getenv("DEBUG", default="false").strip().lower() == "true"
        LOG_FILE = os.getenv("_LOG_FILE", default=LOG_FILE)
        ERROR_LOG_FILE = os.getenv("_ERROR_LOG_FILE", default=ERROR_LOG_FILE)

        main()

    except ImportError as e:
        name = e.name
        path = " located at %s" % e.path if e.path else ""
        err_msg = "No module named %s%s" % (name, path) if name else str(e).capitalize()
        print("%s, please try 'pip install -r requirements.txt'" % err_msg, file=sys.stderr)

        if DEBUG:
            raise
        else:
            sys.exit(1)

    except Exception as e:
        print("Internal error occurred: %s: %s\nSee %s for more logs." % (type(e).__name__, e, ERROR_LOG_FILE), file=sys.stderr)

        # write ERROR_LOG_FILE
        try:
            import traceback

            os.makedirs(os.path.dirname(ERROR_LOG_FILE), exist_ok=True)

            open(ERROR_LOG_FILE, "w", encoding="utf-8").close()
            if not os.path.exists(LOG_FILE):
                open(LOG_FILE, "w", encoding="utf-8").close()

            with open(ERROR_LOG_FILE, "a", encoding="utf-8") as error_file:
                with open(LOG_FILE, encoding="utf-8") as log_file:
                    error_file.writelines(log_file.readlines()[-300:])

                error_file.write("\n")
                error_file.write(traceback.format_exc())
                error_file.write("**********************************************************************************************\n\n")
        except Exception as _e:
            print("Unable to prepare error report: %s: %s" % (type(_e).__name__, _e), file=sys.stderr)

            if DEBUG:
                raise
            else:
                sys.exit(1)

        if DEBUG:
            raise
        else:
            sys.exit(1)
