import logging
from dareplane_utils.logging.logger import get_logger

rootLogger = get_logger("")
rootLogger.setLevel(logging.DEBUG)

logging.info("info_root")

logger1 = logging.getLogger("myapp.area1")
logger2 = logging.getLogger("myapp.area2")
logger1.debug("debug1")
logger1.info("info1")
logger1.warning("debug1")
logger1.error("info1")
logger2.debug("debug2")
logger2.info("info2")
logger2.warning("debug2")
logger2.error("info2")
