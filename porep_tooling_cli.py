#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# noinspection PyUnresolvedReferences
import __future__
import sys
import os
import dotenv

dotenv.load_dotenv()

LOG_FILE = 'logs/logs.log'
ERROR_LOG_FILE = 'logs/logs.error'


def configure_logger():
    import logging

    def logging_level_str_to_int(level_str):
        return {
            'disabled': sys.maxsize,
            'critical': logging.CRITICAL,
            'fatal': logging.FATAL,
            'error': logging.ERROR,
            'warning': logging.WARNING,
            'warn': logging.WARN,
            'info': logging.INFO,
            'debug': logging.DEBUG,
            'notset': logging.NOTSET,
            'all': logging.NOTSET
        }[level_str.strip().lower()]

    logging_format = '%(levelname)-10s%(asctime)s %(name)s:%(funcName)-16s: %(message)s'
    level = logging_level_str_to_int(os.getenv('_FILE_LOGGING_LEVEL', default='DEBUG'))

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
        print('Python >= v3.10.0 required to run %s, you have %s' % (sys.argv[0], platform.python_version()))
        sys.exit(4)

    DEBUG = os.getenv('DEBUG', default='false').lower() == 'true'

    try:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        main()

    except (ImportError, ModuleNotFoundError) as e:
        name = e.name
        path = ' located at %s' % e.path if e.path else ''
        err_msg = 'No module named %s%s' % (name, path) if name else str(e).capitalize()
        print("%s, please try 'pip install -r requirements.txt'" % err_msg)
        if DEBUG: raise e

    except Exception as e:
        print('Internal error occurred:\n%s: %s\nSee %s for more logs.' % (type(e).__name__, e, ERROR_LOG_FILE))

        # write logs
        try:
            import traceback

            open(ERROR_LOG_FILE, 'w').close()
            if not os.path.exists(LOG_FILE):
                open(LOG_FILE, 'w').close()

            with open(ERROR_LOG_FILE, 'a') as error_file:
                with open(LOG_FILE) as log_file:
                    error_file.writelines(log_file.readlines()[-300:])

                error_file.write('\n')
                error_file.write(traceback.format_exc())
                error_file.write('**********************************************************************************************\n\n')
        except Exception as _e:
            print('Unable to prepare error report: %s: %s' % (type(_e).__name__, _e))

        if DEBUG: raise e
