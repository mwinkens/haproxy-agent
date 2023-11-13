import importlib
import socketserver
import argparse
import sys
from pathlib import Path
import importlib.util
import logging
from importlib.machinery import SourceFileLoader

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

ram_check_module_name = "check_ram"
ram_check_copy_path = "check_ram_copy.py"


def import_ramcheck_module(file_path: Path):
    """
    Imports the module at filepath and adds it to the known system modules
    :param file_path:
    :return:
    """
    sfl = SourceFileLoader(ram_check_module_name, str(file_path.absolute()))
    spec = importlib.util.spec_from_loader(ram_check_module_name, sfl)
    if spec is None:
        raise ValueError("Could not load module from path")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules[ram_check_module_name] = module


class TCPHaproxyHandler(socketserver.BaseRequestHandler):
    """
    The request handler class for our server.

    It is instantiated once per connection to the server, and must
    override the handle() method to implement communication to the
    client.
    """

    def handle(self):
        # get ram state
        check_ram = importlib.import_module(ram_check_module_name)
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

        haproxy_answer = f"{weight}%\n"
        logger.info(f"Set haproxy weight to {weight}%")
        self.request.sendall(str.encode(haproxy_answer, encoding="utf-8"))


def main(host, port, check_ram_path):
    # check that the nagios ram check exists
    ram_check = Path(check_ram_path)
    if not ram_check.is_file():
        logger.warning(f"{ram_check.absolute()} does not exist or is not a file, using build in ram check!")
        ram_check = Path(ram_check_copy_path)

    # import the ram check module from nagios
    try:
        import_ramcheck_module(ram_check)
    except ValueError:
        logger.warning(f"Could not load {ram_check}!")
        ram_check = Path(ram_check_copy_path)
        import_ramcheck_module(ram_check)

    # Create the server, binding to localhost on the port
    logger.info(f"Starting TCP server on {host}:{port}")
    with socketserver.TCPServer((host, port), TCPHaproxyHandler, bind_and_activate=False) as server:
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
