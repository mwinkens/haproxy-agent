import importlib
import socketserver
import argparse
import sys
from pathlib import Path
import importlib.util
import logging
from importlib.machinery import SourceFileLoader
import subprocess

logger = logging.getLogger("haproxy-agent")
logger.setLevel(logging.WARNING)

formatter = logging.Formatter('%(asctime)s %(name)s %(levelname)s: %(message)s')

fh = logging.FileHandler('haproxy-nagios-agent.log')
fh.setLevel(logging.DEBUG)
fh.setFormatter(formatter)

ch = logging.StreamHandler()
ch.setLevel(logging.WARNING)
ch.setFormatter(formatter)
logger.addHandler(ch)
logger.addHandler(fh)

check_ram_module_name = "check_ram"
check_load_module_name = "check_load"
check_ram_copy_path = "check_ram_copy.py"
check_load_copy_path = "check_load"


def import_ramcheck_module(file_path: Path):
    """
    Imports the module at filepath and adds it to the known system modules
    :param file_path:
    :return:
    """
    sfl = SourceFileLoader(check_ram_module_name, str(file_path.absolute()))
    spec = importlib.util.spec_from_loader(check_ram_module_name, sfl)
    if spec is None:
        raise ValueError("Could not load module from path")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules[check_ram_module_name] = module


class TCPHaproxyHandler(socketserver.BaseRequestHandler):
    """
    The request handler class for our server.

    It is instantiated once per connection to the server, and must
    override the handle() method to implement communication to the
    client.
    """

    def __init__(self, request, client_address, server, load_check: Path):
        self.load_check = load_check
        super().__init__(request, client_address, server)

    def handle_load(self) -> int:
        command = f"{str(self.load_check.absolute())} -r -w 15,10,5 -c 30,25,20"
        completed_process = subprocess.run(command,
                                           capture_output=True,
                                           shell=True)
        if completed_process.returncode != 0:
            logger.warning(
                f"Could not compute load with {command}:\n{completed_process.stderr}\n{completed_process.stdout}")
            return 100
        load_text_stdout = completed_process.stdout
        logger.debug(f"load output:\n{load_text_stdout}")
        load_text = load_text_stdout.split()

        load_1 = float(load_text[4][:-1])  # remove comma, then to float
        load_5 = float(load_text[5][:-1])  # remove comma, then to float
        load_15 = float(load_text[6].split(sep=b'|')[0])  # split at pipe, use first one, then to float
        load_int_1 = int(load_1 * 100)
        load_int_5 = int(load_5 * 100)
        load_int_15 = int(load_15 * 100)

        logger.debug(f"load_1 {load_int_1}%, load_5 {load_int_5}%, load_15 {load_int_15}%")

        # only use last 1 min for now
        weight = 100
        max_weight = 100  # max weight, but can be more, the cpu can be overloaded
        degrading_threshold = 50  # start degrading at 50 percent load
        # directly half the weight at 50%, because the traffic
        # balancing is proportional to weights of other instances
        degraded_weight = 50
        high_load_degraded_threshold = 90 # high load, but don't set weight to 0 yet
        high_load_degraded_weight = 20  # weight at high load, e.g. 90
        fully_degraded_threshold = 110 # set weight to 0 at threshold, drain instance



        # only 5% load left, set the weight to 0, other instances should handle
        if load_int_1 > fully_degraded_threshold:
            weight = 0
        elif load_int_1 > high_load_degraded_threshold:
            load_left = fully_degraded_threshold - load_int_1
            weight = (high_load_degraded_weight * load_left) // (fully_degraded_threshold - high_load_degraded_threshold)
        # proportional weight degrading, starting at degraded_weight
        elif load_int_1 > degrading_threshold:
            # linear descent, 25% load capacity left would make weight to 25
            load_left = max_weight - load_int_1
            weight = (degraded_weight * load_left) // (max_weight - degrading_threshold)

        return max(weight, 0)  # make sure we don't have negative weight

    def handle_ram(self) -> int:
        # get ram state
        check_ram = importlib.import_module(check_ram_module_name)
        message, state = check_ram.check_ram(warning_threshold=20, critical_threshold=10, percent=True, verbosity=False,
                                             nocache=False)
        # TODO maybe we also want to check the state, maybe not

        # message parsing
        text_chunks = message.split()
        ram_percentage = text_chunks[2][:-1]  # third chunk, remove '%' text
        logger.debug(f"{ram_percentage}% ram left")
        ram_percentage = int(ram_percentage)

        # weight is how good the service currently is, everything up to 70% ram usage is still valid
        # ram warnings usually start at 80%
        weight = 100
        degrading_threshold = 30  # start degrading service at the last 30% free ram

        # directly half the weight at 70%, because the traffic
        # balancing is proportional to weights of other instances
        degraded_weight = 50
        fully_degraded_threshold = 5  # set weight to 0 at threshold

        # only 5% ram left, set the weight to 0, other instances should handle
        if ram_percentage < fully_degraded_threshold:
            weight = 0
        # proportional weight degrading, starting at degraded_weight
        elif ram_percentage < degrading_threshold:
            # linear descent, 15% ram left would make weight to 50%
            weight = (degraded_weight * ram_percentage) // degrading_threshold

        return weight

    def handle(self):
        weight_load = self.handle_load()
        weight_ram = self.handle_ram()
        logger.debug(f"weight load: {weight_load}\nweight ram: {weight_ram}")
        weight = min(weight_ram, weight_load, 100)

        haproxy_answer = f"{weight}%\n"
        logger.info(f"Set haproxy weight to {weight}%")
        self.request.sendall(str.encode(haproxy_answer, encoding="utf-8"))


def main(host, port, nagios_plugin_path):
    nagios_plugin_path = Path(nagios_plugin_path)
    if not nagios_plugin_path.is_dir():
        logger.warning(f"{nagios_plugin_path} does not exist or is not a directory, using build in checks!")
        nagios_plugin_path = Path(".")

    # check that the nagios ram check exists
    ram_check = nagios_plugin_path.joinpath(check_ram_module_name)
    if not ram_check.is_file():
        logger.warning(f"{ram_check.absolute()} does not exist or is not a file, using build in ram check!")
        ram_check = Path(check_ram_copy_path)

    # check load check exists
    load_check = nagios_plugin_path.joinpath(check_load_module_name)
    if not load_check.is_file():
        logger.warning(f"{load_check.absolute()} does not exist or is not a file, using build in load check!")
        load_check = Path(check_load_copy_path)

    # import the ram check module from nagios
    try:
        import_ramcheck_module(ram_check)
    except ValueError:
        logger.warning(f"Could not load {ram_check}!")
        ram_check = Path(check_ram_copy_path)
        import_ramcheck_module(ram_check)

    # Create the server, binding to localhost on the port
    logger.info(f"Starting TCP server on {host}:{port}")
    with socketserver.TCPServer((host, port),
                                lambda *args, **kwargs: TCPHaproxyHandler(*args, **kwargs, load_check=load_check),
                                bind_and_activate=False) as server:
        server.allow_reuse_address = True
        server.server_bind()
        server.server_activate()
        # Activate the server; this will keep running until you
        # interrupt the program with Ctrl-C
        server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog='health-agent',
                                     description='health check agent for haproxy using nagios ramcheck',
                                     epilog="I can't believe somebody is reading this")
    parser.add_argument('-host', '--hostname', required=False, default="127.0.0.1")
    parser.add_argument('-p', '--port', type=int, required=False, default=3000)
    parser.add_argument('nagios_path')
    args = parser.parse_args()
    main(args.hostname, args.port, args.nagios_path)
