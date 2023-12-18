#!/bin/bash

service_file="haproxy-agent.service"
key_start="ExecStart"
new_exec_start_value="$(pwd)/start.sh"
key_working="WorkingDirectory"
new_working_value="$(pwd)"

# Check if the service file exists
if [ -f "$service_file" ]; then
    # Edit the specified key in the [Service] section
    sed -i "s|\($key_start *= *\).*|\1$new_exec_start_value|" "$service_file"
    sed -i "s|\($key_working *= *\).*|\1$new_working_value|" "$service_file"

    echo "Service file updated successfully."

    # Link the service file from dir
    ln -s "$(pwd)/haproxy-agent.service" /etc/systemd/system/haproxy-agent.service
    
    # Reload systemd to apply changes
    sudo systemctl daemon-reload
    sudo systemctl restart haproxy-agent
else
    echo "Service file not found: $service_file"
fi
