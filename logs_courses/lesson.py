import logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler

if __name__ == '__main__':
    print('Log levels :')
    print(f'DEBUG:{logging.DEBUG}')
    print(f'INFO:{logging.INFO}')
    print(f'WARNING:{logging.WARNING}')
    print(f'ERROR:{logging.ERROR}')
    print(f'CRITICAL:{logging.CRITICAL}')
    print(f'Default level:{logging.getLevelName(logging.getLogger().level)}')
    print(f'Default logger:{logging.getLogger()}')
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.WARNING)
    """logging.basicConfig(
        filename='config.log',
        format='%(asctime)s %(msecs)03d|%(name)s|%(message)s',
        datefmt='%Y-%m-%d'
    ) """
    logger_formatter = logging.Formatter(
        fmt='%(asctime)s %(msecs)03d|%(name)s|%(levelname)s|%(message)s',
        datefmt='%Y-%m-%d %H:%M:%S')
    console = logging.StreamHandler()

    """ file_rotate = RotatingFileHandler(
        filename='rotate_size.log',
        maxBytes=100,
        backupCount=7
    ) """

    file_rotate = TimedRotatingFileHandler(
        filename='rotate_time.log',
        when="s",
        interval=10,
        backupCount=10
    )

    # file_logs = logging.FileHandler('app.log')
    file_rotate.setFormatter(logger_formatter)
    # file_logs.setFormatter(logger_formatter)

    logger.addHandler(file_rotate)

    # logger.addHandler(file_logs)
    # logging.error('Root MSG')
    logger.info('INFO Message')
    logger.warning('WARN Message')
    logger.error('Error Message')
