import ujson
import logging
import logging.config

default_dareplane_config = {
    "version": 1,
    "formatters": {
        "dareplane_standard": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "dareplane_standard",
        },
        "socket": {
            "class": "dareplane_utils.logging.ujson_socket_handler.UJsonSocketHandler",
            "host": "localhost",
            "port": 9020,
        },
    },
    "root": {
        "handlers": ["console", "socket"],
    },
}

logging.config.dictConfig(default_dareplane_config)


# have this as a simple wrapper to ensure the updated config is used
def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
