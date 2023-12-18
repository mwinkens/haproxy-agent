#!/usr/bin/env python3
#
#   Copyright Hari Sekhon 2007
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 2 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program; if not, write to the Free Software
#   Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
#
#
#   some small modifications by b.von.st.vieth@fz-juelich.de
#

from sys import exit
from optparse import OptionParser

# Standard Exit Codes for Nagios
OK = 0
WARNING = 1
CRITICAL = 2
UNKNOWN = 3


def check_ram(warning_threshold, critical_threshold, percent, verbosity, nocache):
    """Takes warning and critical thresholds in KB or percentage if third argument is true,
    and returns a result depending on whether the amount free ram is less than the thresholds"""

    if verbosity >= 3:
        print("Opening /proc/meminfo")
    try:
        f = open('/proc/meminfo')
    except Exception as e:
        print("RAM CRITICAL: Error opening /proc/meminfo - %s" % str(e))
        return CRITICAL

    output = f.readlines()
    memtotal = None
    memfree = None
    memcached = None
    membuffers = 0
    memavailable = None
    for x in range(len(output)):
        y = output[x].split()
        if y[0] == "MemTotal:":
            memtotal = int(y[1])
        elif y[0] == "MemFree:":
            memfree = int(y[1])
        elif y[0] == "Cached:":
            memcached = int(y[1])
        elif y[0] == "Buffers:":
            membuffers = int(y[1])
        elif y[0] == "MemAvailable:":
            memavailable = int(y[1])

    if memtotal is None or memfree is None or memcached is None:
        print("UNKNOWN: failed to get mem stats")
        return UNKNOWN

    if nocache:
        total_free = memfree
    elif memavailable:
        total_free = memavailable
    else:
        total_free = memfree + memcached + membuffers

    total_used_megs = float(memtotal - memfree - memcached - membuffers) / 1024
    total_free_megs = float(total_free) / 1024
    memtotal_megs = float(memtotal) / 1024

    if percent:
        percentage_free = int(float(total_free) / float(memtotal) * 100)
        if percentage_free < critical_threshold:
            MESSAGE = "RAM CRITICAL: %d%% ram free (%d/%d MB used)" % (percentage_free, total_used_megs, memtotal_megs)
            STATE = CRITICAL
        elif percentage_free < warning_threshold:
            MESSAGE = "RAM WARNING: %d%% ram free (%d/%d MB used)" % (percentage_free, total_used_megs, memtotal_megs)
            STATE = WARNING
        else:
            MESSAGE = "RAM OK: %d%% ram free" % percentage_free
            STATE = OK
    else:
        if total_free < critical_threshold:
            MESSAGE = "RAM CRITICAL: %dMB ram free (%d/%d MB used)" % (total_free_megs, total_used_megs, memtotal_megs)
            STATE = CRITICAL
        elif total_free < warning_threshold:
            MESSAGE = "RAM WARNING: %dMB ram free (%d/%d MB used)" % (total_free_megs, total_used_megs, memtotal_megs)
            STATE = WARNING
        else:
            MESSAGE = "RAM OK: %dMB ram free" % total_free_megs
            STATE = OK
    MESSAGE += "|memused=%d;%d;" % (total_used_megs, memtotal_megs)
    return [MESSAGE, STATE]


def main():
    """main func, parse args, do sanity checks and call check_ram func"""

    parser = OptionParser()

    parser.add_option("-n", "--no-include-cache", action="store_true", dest="nocache",
                      help="Do not include cache as free ram. Linux tends to gobble up free ram "
                           + "as disk cache, but this is freely reusable so this plugin counts it as "
                           + "free space by default since this is nearly always what you want. This "
                           + "switch disables this behaviour so you use only the pure free ram. Not advised.")
    parser.add_option("-c", "--critical", dest="critical_threshold",
                      help="Critical threshold. Returns a critical status if the amount of free ram "
                           + "is less than this number. Specify KB,MB or GB after to specify units of "
                           + "KiloBytes, MegaBytes or GigaBytes respectively or % afterwards to indicate"
                           + "a percentage. KiloBytes is used if not specified")
    parser.add_option("-v", "--verbose", action="count", dest="verbosity",
                      help="Verbose mode. Good for testing plugin. By default only one result line "
                           + "is printed as per Nagios standards. Use multiple times for increasing "
                           + "verbosity (3 times = debug)")
    parser.add_option("-w", "--warning", dest="warning_threshold",
                      help="warning threshold. Returns a warning status if the amount of free ram "
                           + "is less than this number. Specify KB,MB or GB after to specify units of "
                           + "KiloBytes, MegaBytes or GigaBytes respectively or % afterwards to indicate "
                           + "a percentage. KiloBytes is used if not specified")

    options, args = parser.parse_args()

    # This script doesn't take any args, only options, so we print
    # usage and exit if any are found
    if args:
        parser.print_help()
        return UNKNOWN

    warning_threshold = options.warning_threshold
    critical_threshold = options.critical_threshold
    nocache = options.nocache
    verbosity = options.verbosity or 0

    # ====================================================================================#
    #                                Sanity Checks                                       #
    #   This is TOO big really, but it allows for nice flexibility on the command line    #
    # ====================================================================================#
    if warning_threshold is None:
        print("UNKNOWN: you did not specify a warning threshold\n")
        parser.print_help()
        return UNKNOWN
    elif critical_threshold is None:
        print("UNKNOWN: you did not specify a critical threshold\n")
        parser.print_help()
        return UNKNOWN
    else:
        warning_threshold = str(warning_threshold)
        critical_threshold = str(critical_threshold)

    megs = ["MB", "Mb", "mb", "mB", "M", "m"]
    gigs = ["GB", "Gb", "gb", "gB", "G", "g"]

    W_percent = False
    C_percent = False

    def get_threshold(input_value):
        """takes one arg and returns the float threshold value"""

        try:
            threshold = float(input_value)
        except ValueError:
            print("UNKNOWN: invalid threshold given")
            exit(UNKNOWN)

        return threshold

    # Find out if the supplied argument is a percent or a size
    # and get its value
    if warning_threshold[-1] == "%":
        warning_threshold = get_threshold(warning_threshold[:-1])
        W_percent = True
    elif warning_threshold[-2:] in megs:
        warning_threshold = get_threshold(warning_threshold[:-2]) * 1024
    elif warning_threshold[-1] in megs:
        warning_threshold = get_threshold(warning_threshold[:-1]) * 1024
    elif warning_threshold[-2:] in gigs:
        warning_threshold = get_threshold(warning_threshold[:-2]) * 1024 * 1024
    elif warning_threshold[-1] in gigs:
        warning_threshold = get_threshold(warning_threshold[:-1]) * 1024 * 1024
    else:
        warning_threshold = get_threshold(warning_threshold)

    if critical_threshold[-1] == "%":
        critical_threshold = get_threshold(critical_threshold[:-1])
        C_percent = True
    elif critical_threshold[-2:] in megs:
        critical_threshold = get_threshold(critical_threshold[:-2]) * 1024
    elif critical_threshold[-1] in megs:
        critical_threshold = get_threshold(critical_threshold[:-1]) * 1024
    elif critical_threshold[-2:] in gigs:
        critical_threshold = get_threshold(critical_threshold[:-2]) * 1024 * 1024
    elif critical_threshold[-1] in gigs:
        critical_threshold = get_threshold(critical_threshold[:-1]) * 1024 * 1024
    else:
        critical_threshold = get_threshold(critical_threshold)

    # Make sure that we use either percentages or units but not both as this makes
    # the code more ugly and complex
    if W_percent and C_percent:
        percent_true = True
    elif not W_percent and not C_percent:
        percent_true = False
    else:
        print("UNKNOWN: please make thresholds either units or percentages, not one of each")
        return UNKNOWN

    # This assumes that the percentage units are numeric, which they must be to have gotten
    # through the get_threhold func above
    if W_percent:
        if (warning_threshold < 0) or (warning_threshold > 100):
            exit_invalid_warning("warning percentage must be between 0 and 100")  # XXX Nagios callback?
    if C_percent:
        if (critical_threshold < 0) or (critical_threshold > 100):
            exit_invalid_critical("critical percentage must be between 0 and 100")  # XXX Nagios callback?

    if warning_threshold <= critical_threshold:
        print("UNKNOWN: Critical threshold must be less than Warning threshold")
        return UNKNOWN

    # End of Sanity Checks

    result = check_ram(warning_threshold, critical_threshold, percent_true, verbosity, nocache)
    return result


if __name__ == "__main__":
    result = main()
    print(result[0])
    exit(result[1])
