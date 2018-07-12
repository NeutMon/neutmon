# README #

Simple TCP speedtest & traceroute

## Requirements ##

Python 2.7

## Install ##

	$ git clone https://<your_username>@bitbucket.org/ValerioLuconi/neutmon.git
	
## Configuration ##

In `neutmon/handlers.py` change the value of the variable `DEFAULT_SERVER_ADDRESS`
with the name or IP address of your server machine.

## Run test ##

Needs root.

On server:

	$ ./server.py

On client:

	$ ./client.py

Use option `-h` or `--help` with client to obtain more options.

## License ##

This software is available under the MIT license.
