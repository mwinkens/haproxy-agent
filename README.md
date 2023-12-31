# Haproxy Agent
[![Tests](https://github.com/mwinkens/haproxy-agent/actions/workflows/test.yaml/badge.svg?branch=main)](https://github.com/mwinkens/haproxy-agent/actions/workflows/test.yaml)
[![contributions welcome](https://img.shields.io/badge/contributions-welcome-brightgreen.svg?style=flat)](https://github.com/mwinkens/haproxy-agent/issues)

Simple agent for haproxy to gradually degrade a service if it's ram or load is reaching its limits

## Getting started

You can start this agent simply by calling

```commandline
python agent.py -host <your host/localhost> -p <port> /path/to/modules
```

This agent comes with buildin modules under `buildins`, which you need to initialize with

```commandline
git submodule update --init
```

## Weighting

The weights of the agent are configurable. In the following you can see the default values, but you may need to adjust this for your needs in the `haproxy-service.ini` configuration file. 

### Load profile:

![haproxy-agent-load](https://github.com/mwinkens/haproxy-agent/assets/104770531/8720df1c-667f-46f7-812d-906f937dc8b9)

Notes:
- Why is the minimum weight 1 and not 0? A high load shouldn't cause the instances to go into the drain state. The drain state is caused by a weight of 0 and an instance isn't allowing any new connections. If all your nodes experience a high load this might cause users to not find any available instances.
- Why allow for more than 100% load? Because sometimes a service is just busy, calculating, installing updates and this shouldn't kick out the instance completly

The number of new connections an instance will get is not only determined by its weight but also by the weight of all other instances.

### Ram profile:

![haproxy-agent-ram](https://github.com/mwinkens/haproxy-agent/assets/104770531/ad01ce98-94a6-4f10-81e9-b8d2395fc686)

Notes:
- Why do you have a threshold, where you set the weight to 0 and start draining the instance? Because 5% of the ram is reserved for a system administrator to intervene, check logs and be able to run commands. As soon as all of the ram is taken this will get significantly harder.

### Combination:
In order to combine all checks the minimum is taken. For example, if you instance is not high loaded, but has no ram left, it shouldn't allow new connections.

## Daemon installation

This agent can be run as a daemon.

For Ubuntu (or other linux):

### Packages

```commandline
apt install gcc build-base linux-headers
git submodule update --init
pip install -r buildins/requirements.txt
```

Note: The python dependencies are only comming from the buildins.

### Installer

Just run `sudo ./install-service.sh` in the **root directory** of this repository.

### Install Manually

- Edit the `haproxy-agent.service` file for your needs
  - Adjust `WorkingDirectory` and `ExecStart`
- link the service file with

```commandline
ln -s /path/to/haproxy-agent.service /etc/systemd/system/haproxy-agent.service
```

- reload the daemons with `systemctl daemon-reload`
- start the agent with `systemctl start haproxy-agent`

Additional Notes for manual installation:

If you want to install this repository at another place, you have to change the symlink and
the `haproxy-agent.service` file!

This agent starts with the default buildins as defined in `start.sh`.

## Configure HAproxy

According to this [guide](https://www.haproxy.com/blog/how-to-enable-health-checks-in-haproxy#agent-health-checks)
you can simply add the agent-check configurations for haproxy:

```
backend webservers
  balance roundrobin
  server server1 192.168.123.123:443 check  weight 100  agent-check agent-inter 5s  agent-addr 192.168.123.123  agent-port 3000
```

Note, that the agent-addr is the same as the servers address, as it runs on the server, but the agent port differs!

Find more for the server configuration [in the official documentation](https://www.haproxy.com/documentation/aloha/latest/load-balancing/health-checks/agent-checks/#configure-the-servers)

## Configure HAproxy-Agent

The haproxy-agent comes with a variety of configuration options. These are all defined in `haproxy-agent.ini`.

### Start options

The program itself has just a few start options, where every argument except of the module path are optional.
The agent comes with its own buildin modules, do you can use `buildins` for this.

```
python3 agent.py -host 0.0.0.0 -p 3000 -c haproxy-agent.ini buildins
```

Note: The arguments directly given to the agent overwrite the haproxy-agent.ini file configuration!

### Variables

Description of the variables in the haproxy-agent.ini file:

| section       | variable                     | default | description                                                                                                                                                                   |
|---------------|------------------------------|---------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| server        | host                         | 0.0.0.0 | Binding host of the agent                                                                                                                                                     |
|               | port                         | 3000    | Binding port of the agent                                                                                                                                                     |
| check.general | max_weight                   | 100     | Maximum weight the agent sends to the haproxy. This setting clips every other maximum weight!                                                                                 |
|               | min_weight                   | 0       | Minimum weight the agent sends to the haproxy. This setting clips every other minimum weight! Set to 1 if you don't want to go into the drain state of haproxy ever!          |
| check.load    | weight                       | 100     | Start weight of the load check for calculations                                                                                                                               |
|               | min_weight                   | 1       | Minimum weight the load check can return. The default is set to 1, so high loads don't cause every server to drain                                                            |
|               | max_weight                   | 100     | Maximum weight the load check can return                                                                                                                                      |
|               | degrading_threshold          | 50      | Load percentage, at which stage 1 weight loss starts                                                                                                                          |
|               | degraded_weight              | 50      | Start weight of stage 1 weight loss                                                                                                                                           |
|               | high_load_degraded_threshold | 80      | Load percentage, at which stage 2 weight loss starts                                                                                                                          |
|               | high_load_degraded_weight    | 20      | Start weight of stage2 weight loss                                                                                                                                            |
|               | fully_degraded_threshold     | 120     | Load percentage at which the weight is 0. Please note, that check.general/min_weight and check.load/min_weight can clip the weight, so weight 0 might not be returned!        |
| check.ram     | weight                       | 100     | Start weight of the ram check for calculations                                                                                                                                |
|               | min_weight                   | 0       | Minimum weight the ram check can return. The default is set to 0, so high ram usage can cause servers to drain                                                                |
|               | degrading_threshold          | 30      | Start degrading at 30% **free ram** left                                                                                                                                      |
|               | degraded_weight              | 50      | Start weight of ram weight loss                                                                                                                                               |
|               | fully_degraded_threshold     | 5       | **Free ram** percentage at which the weight is 0. Please note, that check.general/min_weight and check.ram/min_weight can clip the weight, so weight 0 might not be returned! |

## License

See license file

## Author

Marvin Winkens <m.winkens@fz-juelich.de>
