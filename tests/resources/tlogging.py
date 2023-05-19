import logging
from dareplane_utils.logging.logger import get_logger

root_logger = get_logger("")
root_logger.setLevel(logging.DEBUG)

logging.info("info_root")

logger1 = get_logger("myapp.area1")
logger2 = get_logger("myapp.area2")
logger1.debug("debug1")
logger1.info("info1")
logger1.warning("debug1")
logger1.error("info1")
logger2.debug("debug2")
logger2.info("info2")
logger2.warning("debug2")
logger2.error("info2")
