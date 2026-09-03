from pathlib import Path
import logging
import logging.handlers
import os
import tarfile
import tempfile

log_dir = Path.home() / "audio_controller_logs"

if not log_dir.exists():
    log_dir.mkdir()


def get_files():
    return [log_dir / name for name in os.listdir(log_dir)]


def get_logs_as_binary():
    """ Get content of all log files, as in a .tar file, as binary object """
    try:
        data = None
        log_files = get_files()
        tar_file = tempfile.TemporaryFile('w+b')
        with tar_file as tf:
            mode = "w:"  # "w:gz" gz seems to do not work properly on pi
            with tarfile.open(mode=mode, fileobj=tf) as tar_handle:
                for log_file in log_files:
                    tar_handle.add(str(log_file))
            tf.seek(0)
            data = tf.read()

        # to test creation of correct tar.gz file (at least server side):
        # with open(log_dir.parent / 'audio_controller_logs.tar.gz', 'wb') as f:
        #    f.write(data)

        return data
    except:
        return data


main_logger = logging.getLogger("main")
loggers = "main tornado.access tornado.application tornado.general".split()


def setup_logging():
    for name in loggers:
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)
        # Remove any existing handlers (may happen in tests)
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        filename = str(log_dir / f"{name}.log")
        handler = logging.handlers.RotatingFileHandler(filename, maxBytes=1000000, backupCount=5)
        formatter = logging.Formatter(fmt=r'%(asctime)s - %(levelname)s - %(message)s', datefmt=r'%Y-%m-%d %H:%M:%S')
        handler.setFormatter(formatter)
        logger.addHandler(handler)


def enable(enable: bool):
    """ Enable or disable all loggers """
    for name in loggers:
        logger = logging.getLogger(name)
        logger.disabled = not enable


setup_logging()
