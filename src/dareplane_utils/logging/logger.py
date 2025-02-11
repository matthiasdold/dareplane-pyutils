import logging
import logging.config

default_dareplane_config = {
    "version": 1,
    "formatters": {
        "dareplane_standard_color": {
            "()": "colorlog.ColoredFormatter",
            "format": "%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(reset)s %(white)s%(message)s",
        },
        "dareplane_standard": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "dareplane_standard_color",
        },
        "socket": {
            "formatter": "dareplane_standard",
            "class": "dareplane_utils.logging.ujson_socket_handler.UJsonSocketHandler",
            "host": "localhost",
            "port": 9020,
        },
    },
    "root": {
        "handlers": ["console", "socket"],
    },
}

# overwriting defaults
colors = {"DEBUG": "cyan"}

logging.config.dictConfig(default_dareplane_config)


# have this as a simple wrapper to ensure the updated config is used
def get_logger(
    name: str,
    add_console_handler: bool = False,
    colors: dict = colors,
    no_socket_handler: bool = False,  # opt out for socket handler / TCP streaming
) -> logging.Logger:
    """
    Get a configured logger.

    Parameters
    ----------
    name : str
        The name of the logger.
    add_console_handler : bool, optional
        If True, add a console handler to the logger (default is False).
    colors : dict, optional
        A dictionary of colors for log levels (default is `colors`).
    no_socket_handler : bool, optional
        If True, opt out of adding a socket handler for TCP streaming (default is False).

    Returns
    -------
    logging.Logger
        The configured logger.
    """
    logger = logging.getLogger(name)
    root_logger = logging.getLogger()

    if add_console_handler:
        hdl = root_logger.handlers[0]
        hdl.formatter.log_colors.update(colors)
        logger.addHandler(hdl)

    logger.addHandler(root_logger.handlers[-1])  # add socket handler

    if no_socket_handler:
        logger.handlers = [
            h
            for h in logger.handlers
            if not isinstance(h, logging.handlers.SocketHandler)
        ]

    # do not propergate messages to root logger
    logger.propagate = False

    return logger
