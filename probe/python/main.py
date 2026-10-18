#!/usr/bin/env python3
"""Project Pulse: probe Linux entry point. Skeleton only (Step 1).

Check mode and Guard mode logic land in rules.py / model.py / report.py
once sensor features are flowing from the MCU over the Bridge (Step 2+).
"""

from arduino.app_utils import *

logger = Logger("project-pulse")
logger.info("Project Pulse probe starting (skeleton)")

App.run()
