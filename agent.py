"""
Agent/TCP Server for haproxy checks
"""

import importlib
import importlib.util
from importlib.machinery import SourceFileLoader

import socketserver
import argparse
import sys
import logging
import configparser
from pathlib import Path

from typing import Any, Dict, List

logger = logging.getLogger("haproxy-agent")
logger.setLevel(logging.WARNING)

formatter = logging.Formatter("%(asctime)s %(name)s %(levelname)s: %(message)s")

fh = logging.FileHandler("haproxy-agent.log")
fh.setLevel(logging.DEBUG)
fh.setFormatter(formatter)

ch = logging.StreamHandler()
ch.setLevel(logging.WARNING)
ch.setFormatter(formatter)
logger.addHandler(ch)
logger.addHandler(fh)

CHECK_RAM_MODULE_NAME = "check_ram"
CHECK_LOAD_MODULE_NAME = "check_load"
CHECK_RAM_COPY_PATH = "buildins/check_ram.py"
CHECK_LOAD_COPY_PATH = "buildins/check_load.py"

BUILTIN_MODULES = {
    CHECK_RAM_MODULE_NAME: CHECK_RAM_COPY_PATH,
    CHECK_LOAD_MODULE_NAME: CHECK_LOAD_COPY_PATH,
}


def import_module(file_path: Path, module_name: str):
    """
    Imports the module at filepath and adds it to the known system modules
    :param file_path: path of the resource to import
    :param module_name: module name under which the resource should be known
    :return: module
    """
    sfl = SourceFileLoader(module_name, str(file_path.absolute()))
    spec = importlib.util.spec_from_loader(module_name, sfl)
    if spec is None:
        raise ValueError("Could not load module from path")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules[module_name] = module
    return module


class TCPHaproxyHandler(socketserver.BaseRequestHandler):
    """
    The request handler class for our server.

    It is instantiated once per connection to the server, and must
    override the handle() method to implement communication to the
    client.
    """

    def __init__(self, request, client_address, server, config, check_modules):
        self.conf_load = config["check.load"]
        self.conf_ram = config["check.ram"]
        self.conf_general = config["check.general"]

        # LOAD
        # only use last 1 min for now
        self.load_weight = int(self.conf_load.get("weight", 100))

        self.load_min_weight = int(self.conf_load.get("min_weight", 0))

        # max weight, but can be more, the cpu can be overloaded
        self.load_max_weight = int(self.conf_load.get("max_weight", 100))

        # start degrading at 50 percent load
        self.load_degrading_threshold = int(
            self.conf_load.get("degrading_threshold", 50)
        )

        # directly half the weight at 50%, because the traffic
        # balancing is proportional to weights of other instances
        self.load_degraded_weight = int(self.conf_load.get("degraded_weight", 50))

        # high load, but don't set weight to 0 yet
        self.load_high_load_degraded_threshold = int(
            self.conf_load.get("high_load_degraded_threshold", 80)
        )

        # weight at high load, e.g. 80
        self.load_high_load_degraded_weight = int(
            self.conf_load.get("high_load_degraded_weight", 20)
        )

        # set weight to 0 at threshold, drain instance
        self.load_fully_degraded_threshold = int(
            self.conf_load.get("fully_degraded_threshold", 120)
        )

        # RAM
        # weight is how good the service currently is, everything up to 70% ram usage is still valid
        # ram warnings usually start at 80%
        self.ram_weight = int(self.conf_ram.get("weight", 100))

        self.ram_min_weight = int(self.conf_ram.get("min_weight", 0))

        # start degrading service at the last 30% free ram
        self.ram_degrading_threshold = int(self.conf_ram.get("degrading_threshold", 30))

        # directly half the weight at 70%, because the traffic
        # balancing is proportional to weights of other instances
        self.ram_degraded_weight = int(self.conf_ram.get("degraded_weight", 50))

        # set weight to 0 at threshold
        self.ram_fully_degraded_threshold = int(
            self.conf_ram.get("fully_degraded_threshold", 5)
        )

        # GENERAL
        self.general_max_weight = int(self.conf_general.get("max_weight", 100))
        self.general_min_weight = int(self.conf_general.get("min_weight", 0))

        # Modules
        self.check_modules = check_modules

        super().__init__(request, client_address, server)

    def handle_load(self) -> int:
        """
        Check load and apply custom weights
        """
        check_load = self.check_modules[CHECK_LOAD_MODULE_NAME]
        load_1, load_5, load_15 = check_load.check_load()
        load_int_1 = int(load_1 * 100)
        load_int_5 = int(load_5 * 100)
        load_int_15 = int(load_15 * 100)

        logger.debug(
            "load_1 {load_int_1}%, load_5 {load_int_5}%, load_15 {load_int_15}%",
            load_int_1=load_int_1,
            load_int_5=load_int_5,
            load_int_15=load_int_15,
        )

        weight = self.load_weight
        # only 5% load left, set the weight to 0, other instances should handle
        if load_int_1 > self.load_fully_degraded_threshold:
            weight = 0
        elif load_int_1 > self.load_high_load_degraded_threshold:
            load_left = self.load_fully_degraded_threshold - load_int_1
            weight = (self.load_high_load_degraded_weight * load_left) // (
                self.load_fully_degraded_threshold
                - self.load_high_load_degraded_threshold
            )
        # proportional weight degrading, starting at degraded_weight
        elif load_int_1 > self.load_degrading_threshold:
            # linear descent, 25% load capacity left would make weight to 25
            load_left = self.load_max_weight - load_int_1
            weight = (self.load_degraded_weight * load_left) // (
                self.load_max_weight - self.load_degrading_threshold
            )

        return max(
            weight, self.load_min_weight
        )  # make sure we don't have negative weight

    def handle_ram(self) -> int:
        """
        Check ram and apply weights
        """
        # get ram state
        check_ram = self.check_modules[CHECK_RAM_MODULE_NAME]
        message, _ = check_ram.check_ram(
            warning_threshold=20,
            critical_threshold=10,
            percent=True,
            verbosity=False,
            nocache=False,
        )
        # TODO maybe we also want to check the state, maybe not

        # message parsing
        text_chunks = message.split()
        ram_percentage = text_chunks[2][:-1]  # third chunk, remove '%' text
        logger.debug(f"{ram_percentage}% ram left")
        ram_percentage = int(ram_percentage)

        weight = self.ram_weight

        # only 5% ram left, set the weight to 0, other instances should handle
        if ram_percentage < self.ram_fully_degraded_threshold:
            weight = 0
        # proportional weight degrading, starting at degraded_weight
        elif ram_percentage < self.ram_degrading_threshold:
            # linear descent, 15% ram left would make weight to 50%
            weight = (
                self.ram_degraded_weight * ram_percentage
            ) // self.ram_degrading_threshold

        return max(weight, self.ram_min_weight)

    def handle_default_check(self, module_name) -> int:
        """
        do a default check of a named module
        """
        # get module
        check = self.check_modules[module_name]
        return check.check()

    def handle(self):
        min_weight = self.general_max_weight
        weight_ram = self.general_max_weight
        weight_load = self.general_max_weight
        for module_name in self.check_modules.keys():
            current_weight = 100
            if module_name == CHECK_RAM_MODULE_NAME:
                current_weight = self.handle_ram()
                weight_ram = current_weight
            elif module_name == CHECK_LOAD_MODULE_NAME:
                current_weight = self.handle_load()
                weight_load = current_weight
            else:
                current_weight = self.handle_default_check(module_name)
            min_weight = min(min_weight, current_weight)

        logger.debug(
            "weight load: {weight_load}\nweight ram: {weight_ram}\nweight all: {min_weight}",
            weight_load=weight_load,
            weight_ram=weight_ram,
            min_weight=min_weight,
        )
        weight = max(min(min_weight, self.general_max_weight), self.general_min_weight)

        haproxy_answer = f"{weight}%\n"
        logger.info(f"Set haproxy weight to {weight}%")
        self.request.sendall(str.encode(haproxy_answer, encoding="utf-8"))


def create_module_dictionary(
    check_directory_path: Path, check_modules: List[str]
) -> Dict[str, Any]:
    """
    Create a module dictionary by name
    """
    module_dictionary = {}

    for module_name in check_modules:
        if not module_name:
            continue

        module_filename = f"{module_name}.py"

        # check that the module name exists
        check_path = check_directory_path.joinpath(module_filename)
        if not check_path.is_file():
            if module_name in BUILTIN_MODULES.keys():
                logger.warning(
                    "{path} does not exist or is not a file, using build in check!",
                    path=check_path.absolute(),
                )
                check_path = Path(BUILTIN_MODULES[module_name])
            else:
                logger.error(
                    "{path} does not exist or is not a file, module not found",
                    path=check_path.absolute(),
                )
                continue

        # check that the module can be loaded
        loaded_module = None
        try:
            loaded_module = import_module(check_path, module_name)
            if module_name not in BUILTIN_MODULES.keys():
                if not "check" in dir(loaded_module):
                    raise ValueError(
                        f"custom module {module_name} does not contain 'check' method"
                    )
                value = loaded_module.check()
                if not isinstance(value, int):
                    raise ValueError(
                        f"check of custom module {module_name} is invalid, does not return type int"
                    )
        except ValueError as ve:
            logger.warning(f"Exception from {module_name}:")
            logger.warning(ve)
            logger.warning(f"Could not load {module_name}, skipping it!")
            continue

        except ModuleNotFoundError as me:
            logger.error(me)
            logger.error(
                "Could not import check {module_name}, did you forget to install the requirements?",
                module_name=module_name,
            )
            sys.exit(1)

        except FileNotFoundError as fe:
            logger.error(fe)
            logger.error(
                "Could not find buildin check {module_name}, did you forget to install the buildins?",
                module_name=module_name,
            )
            sys.exit(1)

        if loaded_module:
            module_dictionary[module_name] = loaded_module
    return module_dictionary


def main(host, port, check_directory_path, config_path):
    """
    Checks the configs and parameters and ultimately starts a TCP server
    """
    # check config is there and can be loaded
    if not Path(config_path).is_file():
        logger.critical(f"Config {config_path} does not exist or is not a file")
        sys.exit(1)
    config = configparser.ConfigParser()
    config.read(config_path)
    conf_server = config["server"]
    check_module_names = config["check.general"].get(
        "check_modules", f"{CHECK_RAM_MODULE_NAME}, {CHECK_LOAD_MODULE_NAME}"
    )
    check_modules = [s.strip() for s in check_module_names.split(",")]

    # check host and port
    if host == "":
        host = conf_server.get("host", "0.0.0.0")
    if port == 0:  # don't use port 0, like ever!
        port = int(conf_server.get("port", "3000"))

    # check checks directory exists
    check_directory_path = Path(check_directory_path)
    if not check_directory_path.is_dir():
        logger.warning(
            "{check_directory_path} does not exist or is not a directory, using build in checks!",
            check_directory_path=check_directory_path,
        )
        check_directory_path = Path("buildins")

    module_dictionary = create_module_dictionary(check_directory_path, check_modules)

    if not module_dictionary.keys():
        logger.error("Empty module dictionary, no modules to load")
        sys.exit(1)

    # Create the server, binding to localhost on the port
    logger.info(f"Starting TCP server on {host}:{port}")
    with socketserver.TCPServer(
        (host, port),
        lambda request, client_address, tcp_server: TCPHaproxyHandler(
            request,
            client_address,
            tcp_server,
            config=config,
            check_modules=module_dictionary,
        ),
        bind_and_activate=False,
    ) as server:
        server.allow_reuse_address = True
        server.server_bind()
        server.server_activate()
        # Activate the server; this will keep running until you
        # interrupt the program with Ctrl-C
        server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="health-agent",
        description="health check agent for haproxy using configurable modules",
        epilog="I can't believe somebody is reading this",
    )
    parser.add_argument("-host", "--hostname", required=False, default="")
    parser.add_argument("-p", "--port", type=int, required=False, default=0)
    parser.add_argument("-c", "--config", required=False, default="haproxy-agent.ini")
    parser.add_argument("module_path")
    args = parser.parse_args()

    main(args.hostname, args.port, args.module_path, args.config)
