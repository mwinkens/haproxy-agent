# Haproxy Nagios Agent

Simple agent for haproxy to gradually degrade a service if it's ram is reaching its limits

## Getting started
You can start this agent simply by calling

```commandline
python agent.py -host <your host/localhost> -p <port> /path/to/nagiosramcheck.py
```

The path of the nagios ram check is usually given by puppet and may be different for different os

## Daemon installation

This agent can be run as a daemon:

For Ubuntu:
- Clone this repository to `/opt/`
- link the service file
```commandline
ln -s /opt/haproxy-nagios-agent/haproxy-nagios-agent.service /etc/systemd/system/haproxy-agent.service
```
- reload the daemons with `systemctl daemon-reload`
- start the agent with `systemctl start haproxy-agent`

Additional Notes:

If you want to install this repository at another place, you have to change the symlink and the `haproxy-nagios-agent.service` file!

Also, this agent starts with some default values defined in `start.sh`.

## Configure HAproxy

According to this [guide](https://www.haproxy.com/blog/how-to-enable-health-checks-in-haproxy#agent-health-checks)
you can simply add the agent-check configurations for haproxy:
```
backend webservers
  balance roundrobin
  server server1 192.168.50.2:80 check  weight 100  agent-check agent-inter 5s  agent-addr 192.168.50.2  agent-port 3000
```

Note, that the agent-addr is the same as the servers address, as it runs on the server, but the agent port differs!

Find more on the server configuration [in the official documentation](https://www.haproxy.com/documentation/aloha/latest/load-balancing/health-checks/agent-checks/#configure-the-servers)

## Additional notes

inspired by [haproxy-agent-check-example](https://github.com/haproxytechblog/haproxy-agent-check-example)

## Author

Marvin Winkens <m.winkens@fz-juelich.de>