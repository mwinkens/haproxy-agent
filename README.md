# Haproxy Agent

Simple agent for haproxy to gradually degrade a service if it's ram is reaching its limits

## Getting started

You can start this agent simply by calling

```commandline
python agent.py -host <your host/localhost> -p <port> /path/to/moduledir
```

## Daemon installation

This agent can be run as a daemon.

For Ubuntu (or other linux):

### Installer

Just run `sudo ./install.sh` in the **root directory** of this repository.

### Manually

- Clone this repository to `/opt/`
- link the service file with

```commandline
ln -s /opt/haproxy-agent/haproxy-agent.service /etc/systemd/system/haproxy-agent.service
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
|               | high_load_degraded_threshold | 90      | Load percentage, at which stage 2 weight loss starts                                                                                                                          |
|               | high_load_degraded_weight    | 20      | Start weight of stage2 weight loss                                                                                                                                            |
|               | fully_degraded_threshold     | 110     | Load percentage at which the weight is 0. Please note, that check.general/min_weight and check.load/min_weight can clip the weight, so weight 0 might not be returned!        |
| check.ram     | weight                       | 100     | Start weight of the ram check for calculations                                                                                                                                |
|               | min_weight                   | 0       | Minimum weight the ram check can return. The default is set to 0, so high ram usage can cause servers to drain                                                                |
|               | degrading_threshold          | 30      | Start degrading at 30% **free ram** left                                                                                                                                      |
|               | degraded_weight              | 50      | Start weight of ram weight loss                                                                                                                                               |
|               | fully_degraded_threshold     | 5       | **Free ram** percentage at which the weight is 0. Please note, that check.general/min_weight and check.ram/min_weight can clip the weight, so weight 0 might not be returned! |

## License

See license file

## Author

Marvin Winkens <m.winkens@fz-juelich.de>