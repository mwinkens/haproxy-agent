OK = 0
WARNING = 1
CRITICAL = 2
UNKNOWN = 3

def check_ram(warning_threshold, critical_threshold, percent, verbosity, nocache):
    MESSAGE = "RAM WARNING: %d%% ram free (%d/%d MB used)" % (100, 100, 100)
    STATE = OK
    return [MESSAGE, STATE]