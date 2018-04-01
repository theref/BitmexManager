import sys
import daiquiri


def setup(verbosity):
    daiquiri.setup(
        level='DEBUG',
        outputs=(daiquiri.output.Stream(sys.stdout, level=verbosity.upper())))
